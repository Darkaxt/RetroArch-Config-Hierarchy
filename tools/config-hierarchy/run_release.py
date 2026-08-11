#!/usr/bin/env python3
"""CLI orchestration for the transactional nightly release workflow."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

import nightly_pipeline
from extract_apk_revision import extract_revision_from_apk
from release_notes import render as render_release_notes
from verify_release import require_signing_environment, sha256


def validate_apk(path):
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Downloaded payload is not a ZIP/APK: {path}")
    with zipfile.ZipFile(path) as archive:
        bad_entry = archive.testzip()
        if bad_entry:
            raise ValueError(f"APK archive integrity failure at {bad_entry}")
        if not any(name.endswith("/libretroarch-activity.so") for name in archive.namelist()):
            raise ValueError(f"APK lacks libretroarch-activity.so: {path}")


def atomic_download(url, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part-{uuid.uuid4().hex}")
    digest = hashlib.sha256()
    headers = {}
    try:
        with urllib.request.urlopen(url) as response, open(temporary, "xb") as output:
            headers = {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_length": response.headers.get("Content-Length"),
            }
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                digest.update(block)
            output.flush()
            os.fsync(output.fileno())
        validate_apk(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"sha256": digest.hexdigest(), "headers": headers, "size": destination.stat().st_size}


def remote_headers(url):
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request) as response:
        return {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_length": response.headers.get("Content-Length"),
        }


def write_provenance(
    *,
    date,
    upstream_revision,
    normal_hash,
    aarch64_hash,
    patch_revision,
    previous_version_code,
    state_path,
    asset_path,
    upstream_apk_remote=None,
    upstream_apk_revision=None,
    upstream_revision_exact=True,
):
    embedded = {
        "schema": 1,
        "nightly_date": date,
        "upstream_revision": upstream_revision,
        "upstream_apk_revision": upstream_apk_revision or upstream_revision[:7],
        "upstream_revision_exact": bool(upstream_revision_exact),
        "upstream_apk_sha256": {"normal": normal_hash, "aarch64": aarch64_hash},
        "patch_revision": patch_revision,
    }
    state = {**embedded, "date": date, "version_code": int(previous_version_code)}
    if upstream_apk_remote:
        state["upstream_apk_remote"] = upstream_apk_remote
    state_path = Path(state_path)
    asset_path = Path(asset_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(state_path, state)
    _write_json(asset_path, embedded)
    return state


def metadata_commit_action(last_subject):
    return "amend" if last_subject.strip() == "release: nightly metadata" else "commit"


def next_version_code(previous_version_code, current_epoch_seconds):
    previous = int(previous_version_code or 0)
    current = int(current_epoch_seconds)
    return max(current, previous + 1)


def assemble_release_metadata(state, normal, aarch64, assets, fork_revision):
    for field in ("version_code", "version_name", "signer_sha256"):
        if normal.get(field) != aarch64.get(field):
            raise ValueError(f"Release pair {field.replace('_', ' ')} mismatch")
    if int(normal["version_code"]) != int(state["version_code"]):
        raise ValueError(
            f"Built version code {normal['version_code']} does not match planned {state['version_code']}"
        )
    return {
        "nightly_date": state["date"],
        "upstream_revision": state["upstream_revision"],
        "upstream_apk_revision": state.get(
            "upstream_apk_revision", state["upstream_revision"][:7]
        ),
        "upstream_revision_exact": state.get("upstream_revision_exact", True),
        "fork_revision": fork_revision,
        "patch_revision": state["patch_revision"],
        "signer_sha256": normal["signer_sha256"],
        "version_name": normal["version_name"],
        "version_code": normal["version_code"],
        "assets": assets,
        "upstream_apk_sha256": state.get("upstream_apk_sha256", {}),
    }


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_git_revision(short_revision):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{short_revision}^{{commit}}"],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return None
    return result.stdout.strip()


def git_is_ancestor(old_revision, new_revision):
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", old_revision, new_revision]
    ).returncode == 0


def prepare_release_assets(directory):
    directory = Path(directory)
    assets = (
        directory / "RetroArch.apk",
        directory / "RetroArch_aarch64.apk",
    )
    return {path.name: sha256(path) for path in assets}


def extract_upstream_assets(apk_path, target_directory):
    target_directory = Path(target_directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_root = target_directory.resolve()
    with zipfile.ZipFile(apk_path) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if not path.parts or path.parts[0] != "assets" or len(path.parts) == 1:
                continue
            relative = PurePosixPath(*path.parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe upstream asset path: {member.filename}")
            destination = target_directory.joinpath(*relative.parts)
            resolved = destination.resolve()
            if target_root not in resolved.parents and resolved != target_root:
                raise ValueError(f"Unsafe upstream asset destination: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(destination, "wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def verify_asset_manifest(directory, manifest):
    directory = Path(directory)
    actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_names != set(manifest):
        raise ValueError(
            f"Release asset set mismatch: expected {sorted(manifest)}, found {sorted(actual_names)}"
        )
    for name, expected_hash in manifest.items():
        actual_hash = sha256(directory / name)
        if actual_hash != expected_hash:
            raise ValueError(f"Release asset hash mismatch for {name}")


def _write_json(path, value):
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with open(temporary, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def command_discover(args):
    state = load_state(args.state)
    nightly_pipeline.check_processed_remote_metadata(state, remote_headers)
    with urllib.request.urlopen(args.index_url) as response:
        html = response.read().decode("utf-8", errors="replace")
    pairs = nightly_pipeline.discover_pairs(html, args.index_url)
    pair = nightly_pipeline.select_next_pair(pairs, state.get("date"))
    output = {"ready": pair is not None, "last_state": state}
    if pair:
        output.update(
            {"date": pair.date, "normal_url": pair.normal_url, "aarch64_url": pair.aarch64_url}
        )
    print(json.dumps(output, sort_keys=True))


def command_download(args):
    directory = Path(args.directory)
    normal = directory / f"{args.date}-RetroArch.apk"
    aarch64 = directory / f"{args.date}-RetroArch_aarch64.apk"
    output = {
        "normal": {**atomic_download(args.normal_url, normal), "url": args.normal_url},
        "aarch64": {**atomic_download(args.aarch64_url, aarch64), "url": args.aarch64_url},
        "normal_path": str(normal),
        "aarch64_path": str(aarch64),
    }
    print(json.dumps(output, sort_keys=True))


def command_resolve(args):
    normal_revision = extract_revision_from_apk(args.normal_apk)
    aarch64_revision = extract_revision_from_apk(args.aarch64_apk)
    resolution = nightly_pipeline.select_build_revision(
        normal_revision,
        aarch64_revision,
        resolve_git_revision,
        args.fallback_revision,
    )
    nightly_pipeline.ensure_forward_revision(
        args.previous_revision, resolution.build_revision, git_is_ancestor
    )
    print(
        json.dumps(
            {
                "upstream_apk_revision": resolution.apk_reported_revision,
                "upstream_revision": resolution.build_revision,
                "upstream_revision_exact": resolution.exact,
            },
            sort_keys=True,
        )
    )


def command_provenance(args):
    upstream_apk_remote = None
    if args.download_metadata:
        downloaded = load_state(args.download_metadata)
        upstream_apk_remote = {
            variant: {
                "url": downloaded[variant]["url"],
                **downloaded[variant]["headers"],
            }
            for variant in ("normal", "aarch64")
        }
    state = write_provenance(
        date=args.date,
        upstream_revision=args.upstream_revision,
        normal_hash=args.normal_hash,
        aarch64_hash=args.aarch64_hash,
        patch_revision=args.patch_revision,
        previous_version_code=args.version_code,
        state_path=args.state,
        asset_path=args.asset,
        upstream_apk_remote=upstream_apk_remote,
        upstream_apk_revision=args.upstream_apk_revision,
        upstream_revision_exact=args.upstream_revision_exact == "true",
    )
    print(json.dumps(state, sort_keys=True))


def command_release_assets(args):
    print(json.dumps(prepare_release_assets(args.directory), sort_keys=True))


def command_extract_assets(args):
    extract_upstream_assets(args.apk, args.target)


def command_verify_assets(args):
    manifest = load_state(args.manifest)
    verify_asset_manifest(args.directory, manifest)


def command_notes(args):
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    Path(args.output).write_text(render_release_notes(metadata), encoding="utf-8", newline="\n")


def command_version_code(args):
    state = load_state(args.state)
    print(next_version_code(state.get("version_code", 0), time.time()))


def command_release_metadata(args):
    state = load_state(args.state)
    normal = load_state(args.normal_verification)
    aarch64 = load_state(args.aarch64_verification)
    assets = load_state(args.assets)
    metadata = assemble_release_metadata(
        state, normal, aarch64, assets, args.fork_revision
    )
    _write_json(args.output, metadata)
    print(json.dumps(metadata, sort_keys=True))


def command_signer_preflight(args):
    if not os.environ.get("RELEASE_KEYSTORE_BASE64"):
        raise ValueError("Missing release-signing input: RELEASE_KEYSTORE_BASE64")
    require_signing_environment(
        {
            **os.environ,
            "RELEASE_STORE_FILE": args.keystore,
        }
    )


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("--index-url", required=True)
    discover.add_argument("--state", type=Path, required=True)
    discover.set_defaults(function=command_discover)

    download = subparsers.add_parser("download")
    download.add_argument("--date", required=True)
    download.add_argument("--normal-url", required=True)
    download.add_argument("--aarch64-url", required=True)
    download.add_argument("--directory", type=Path, required=True)
    download.set_defaults(function=command_download)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--normal-apk", type=Path, required=True)
    resolve.add_argument("--aarch64-apk", type=Path, required=True)
    resolve.add_argument("--previous-revision")
    resolve.add_argument("--fallback-revision")
    resolve.set_defaults(function=command_resolve)

    provenance = subparsers.add_parser("provenance")
    provenance.add_argument("--date", required=True)
    provenance.add_argument("--upstream-revision", required=True)
    provenance.add_argument("--upstream-apk-revision", required=True)
    provenance.add_argument(
        "--upstream-revision-exact", choices=("true", "false"), required=True
    )
    provenance.add_argument("--normal-hash", required=True)
    provenance.add_argument("--aarch64-hash", required=True)
    provenance.add_argument("--patch-revision", required=True)
    provenance.add_argument("--version-code", type=int, required=True)
    provenance.add_argument("--state", type=Path, required=True)
    provenance.add_argument("--asset", type=Path, required=True)
    provenance.add_argument("--download-metadata", type=Path)
    provenance.set_defaults(function=command_provenance)

    release_assets = subparsers.add_parser("release-assets")
    release_assets.add_argument("--directory", type=Path, required=True)
    release_assets.set_defaults(function=command_release_assets)

    extract_assets = subparsers.add_parser("extract-assets")
    extract_assets.add_argument("--apk", type=Path, required=True)
    extract_assets.add_argument("--target", type=Path, required=True)
    extract_assets.set_defaults(function=command_extract_assets)

    verify_assets = subparsers.add_parser("verify-assets")
    verify_assets.add_argument("--directory", type=Path, required=True)
    verify_assets.add_argument("--manifest", type=Path, required=True)
    verify_assets.set_defaults(function=command_verify_assets)

    notes = subparsers.add_parser("notes")
    notes.add_argument("--metadata", type=Path, required=True)
    notes.add_argument("--output", type=Path, required=True)
    notes.set_defaults(function=command_notes)

    version_code = subparsers.add_parser("version-code")
    version_code.add_argument("--state", type=Path, required=True)
    version_code.set_defaults(function=command_version_code)

    metadata = subparsers.add_parser("release-metadata")
    metadata.add_argument("--state", type=Path, required=True)
    metadata.add_argument("--normal-verification", type=Path, required=True)
    metadata.add_argument("--aarch64-verification", type=Path, required=True)
    metadata.add_argument("--assets", type=Path, required=True)
    metadata.add_argument("--fork-revision", required=True)
    metadata.add_argument("--output", type=Path, required=True)
    metadata.set_defaults(function=command_release_metadata)

    signer = subparsers.add_parser("signer-preflight")
    signer.add_argument("--keystore", type=Path, required=True)
    signer.set_defaults(function=command_signer_preflight)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.function(args)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
