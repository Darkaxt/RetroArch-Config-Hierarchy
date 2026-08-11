#!/usr/bin/env python3
"""Final-APK verification helpers and CLI."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

from extract_apk_revision import extract_revision_from_apk


SIGNING_ENVIRONMENT = (
    "RELEASE_STORE_FILE",
    "RELEASE_STORE_PASSWORD",
    "RELEASE_KEY_ALIAS",
    "RELEASE_KEY_PASSWORD",
)


def require_signing_environment(environment):
    missing = [name for name in SIGNING_ENVIRONMENT if not environment.get(name)]
    if missing:
        raise ValueError("Missing release-signing input(s): " + ", ".join(missing))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_aapt_badging(output):
    match = re.search(
        r"package:\s+name='([^']+)'\s+versionCode='(\d+)'\s+versionName='([^']*)'",
        output,
    )
    if not match:
        raise ValueError("Could not parse APK package/version metadata")
    return match.group(1), int(match.group(2)), match.group(3)


def parse_signer_sha256(output):
    match = re.search(r"certificate SHA-256 digest:\s*([0-9A-Fa-f:]+)", output)
    if not match:
        raise ValueError("Could not parse APK signer SHA-256")
    return normalize_fingerprint(match.group(1))


def normalize_fingerprint(value):
    normalized = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
    if not normalized or len(normalized) % 2:
        raise ValueError(f"Invalid SHA-256 fingerprint: {value!r}")
    return normalized


def inspect_archive(apk_path):
    with zipfile.ZipFile(apk_path) as archive:
        bad_entry = archive.testzip()
        if bad_entry:
            raise ValueError(f"APK archive integrity failure at {bad_entry}")
        abis = sorted(
            {
                match.group(1)
                for name in archive.namelist()
                if (match := re.fullmatch(r"lib/([^/]+)/libretroarch-activity\.so", name))
            }
        )
        provenance_path = "assets/config-hierarchy-provenance.json"
        try:
            provenance = json.loads(archive.read(provenance_path))
        except KeyError as error:
            raise ValueError("APK is missing config hierarchy provenance") from error
    return {
        "abis": abis,
        "fork_revision": extract_revision_from_apk(apk_path),
        "provenance": provenance,
    }


def run_checked(command):
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def verify_apk(
    apk_path,
    expected_package,
    expected_abis,
    expected_signer,
    expected_fork_revision,
    expected_upstream_revision,
    expected_patch_revision,
    aapt,
    apksigner,
    zipalign,
):
    archive = inspect_archive(apk_path)
    if archive["abis"] != sorted(expected_abis):
        raise ValueError(f"Unexpected APK ABIs: {archive['abis']}")
    if not expected_fork_revision.startswith(archive["fork_revision"]):
        raise ValueError(f"Unexpected embedded fork revision: {archive['fork_revision']}")
    provenance = archive["provenance"]
    if provenance.get("upstream_revision") != expected_upstream_revision:
        raise ValueError("Unexpected embedded upstream provenance")
    if provenance.get("patch_revision") != expected_patch_revision:
        raise ValueError("Unexpected embedded patch identity")

    package, version_code, version_name = parse_aapt_badging(
        run_checked([str(aapt), "dump", "badging", str(apk_path)])
    )
    if package != expected_package:
        raise ValueError(f"Unexpected package ID: {package}")
    signer_output = run_checked(
        [str(apksigner), "verify", "--verbose", "--print-certs", str(apk_path)]
    )
    signer = parse_signer_sha256(signer_output)
    if signer != normalize_fingerprint(expected_signer):
        raise ValueError(f"Unexpected signer: {signer}")
    run_checked([str(zipalign), "-c", "-v", "4", str(apk_path)])
    return {
        "package": package,
        "version_code": version_code,
        "version_name": version_name,
        "signer_sha256": signer,
        **archive,
        "sha256": sha256(apk_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--abis", required=True)
    parser.add_argument("--signer", required=True)
    parser.add_argument("--fork-revision", required=True)
    parser.add_argument("--upstream-revision", required=True)
    parser.add_argument("--patch-revision", required=True)
    parser.add_argument("--aapt", type=Path, required=True)
    parser.add_argument("--apksigner", type=Path, required=True)
    parser.add_argument("--zipalign", type=Path, required=True)
    args = parser.parse_args()
    require_signing_environment(os.environ)
    result = verify_apk(
        args.apk,
        args.package,
        args.abis.split(","),
        args.signer,
        args.fork_revision,
        args.upstream_revision,
        args.patch_revision,
        args.aapt,
        args.apksigner,
        args.zipalign,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
