import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import extract_apk_revision
import nightly_pipeline
import release_notes
import run_release
import verify_release


class NightlyDiscoveryTests(unittest.TestCase):
    INDEX = """
      <a href="2026-08-07-RetroArch.apk">normal</a>
      <a href="2026-08-07-RetroArch_aarch64.apk">aarch64</a>
      <a href="2026-08-08-RetroArch.apk">partial</a>
      <a href="2026-08-09-RetroArch_aarch64.apk">aarch64</a>
      <a href="2026-08-09-RetroArch.apk">normal</a>
    """

    def test_only_completed_pairs_are_discovered(self):
        pairs = nightly_pipeline.discover_pairs(self.INDEX, "https://buildbot.example/android/")
        self.assertEqual(["2026-08-07", "2026-08-09"], [pair.date for pair in pairs])
        self.assertTrue(pairs[1].normal_url.endswith("2026-08-09-RetroArch.apk"))
        self.assertTrue(pairs[1].aarch64_url.endswith("2026-08-09-RetroArch_aarch64.apk"))

    def test_missed_completed_date_is_selected_oldest_first(self):
        pairs = nightly_pipeline.discover_pairs(self.INDEX, "https://buildbot.example/android/")
        selected = nightly_pipeline.select_next_pair(pairs, "2026-08-06")
        self.assertEqual("2026-08-07", selected.date)

    def test_repeated_heartbeat_for_released_dates_is_noop(self):
        pairs = nightly_pipeline.discover_pairs(self.INDEX, "https://buildbot.example/android/")
        self.assertIsNone(nightly_pipeline.select_next_pair(pairs, "2026-08-09"))

    def test_divergent_embedded_revisions_are_rejected(self):
        with self.assertRaisesRegex(nightly_pipeline.ProvenanceError, "divergent"):
            nightly_pipeline.resolve_pair_revision("abc1234", "def5678", lambda value: value * 2)

    def test_short_revision_must_resolve_to_full_commit(self):
        full = "a" * 40
        self.assertEqual(
            full,
            nightly_pipeline.resolve_pair_revision("abc1234", "abc1234", lambda value: full),
        )
        with self.assertRaisesRegex(nightly_pipeline.ProvenanceError, "resolve"):
            nightly_pipeline.resolve_pair_revision("abc1234", "abc1234", lambda value: None)

    def test_unpublished_revision_uses_disclosed_public_fallback(self):
        fallback = "b" * 40
        resolution = nightly_pipeline.select_build_revision(
            "31c4e00", "31c4e00", lambda value: None, fallback
        )
        self.assertEqual("31c4e00", resolution.apk_reported_revision)
        self.assertEqual(fallback, resolution.build_revision)
        self.assertFalse(resolution.exact)

    def test_resolvable_revision_wins_over_public_fallback(self):
        exact = "a" * 40
        resolution = nightly_pipeline.select_build_revision(
            "abc1234", "abc1234", lambda value: exact, "b" * 40
        )
        self.assertEqual(exact, resolution.build_revision)
        self.assertTrue(resolution.exact)

    def test_revision_rollback_is_rejected(self):
        with self.assertRaisesRegex(nightly_pipeline.ProvenanceError, "rollback"):
            nightly_pipeline.ensure_forward_revision("old", "new", lambda old, new: False)

    def test_changed_processed_upstream_pair_is_rejected(self):
        state = {
            "date": "2026-08-09",
            "upstream_apk_sha256": {"normal": "one", "aarch64": "two"},
        }
        with self.assertRaisesRegex(nightly_pipeline.ProvenanceError, "replaced"):
            nightly_pipeline.check_processed_pair(
                "2026-08-09", {"normal": "changed", "aarch64": "two"}, state
            )

    def test_changed_processed_remote_metadata_is_rejected(self):
        state = {
            "date": "2026-08-09",
            "upstream_apk_remote": {
                "normal": {
                    "url": "https://example/RetroArch.apk",
                    "etag": "old",
                    "last_modified": "yesterday",
                    "content_length": "100",
                },
                "aarch64": {
                    "url": "https://example/RetroArch_aarch64.apk",
                    "etag": "same",
                    "last_modified": "yesterday",
                    "content_length": "90",
                },
            },
        }

        def lookup(url):
            variant = "aarch64" if "aarch64" in url else "normal"
            actual = state["upstream_apk_remote"][variant].copy()
            if variant == "normal":
                actual["etag"] = "replacement"
            return actual

        with self.assertRaisesRegex(nightly_pipeline.ProvenanceError, "metadata changed"):
            nightly_pipeline.check_processed_remote_metadata(state, lookup)

    def test_matching_processed_remote_metadata_is_allowed(self):
        metadata = {
            "url": "https://example/RetroArch.apk",
            "etag": "same",
            "last_modified": "today",
            "content_length": "100",
        }
        state = {
            "date": "2026-08-09",
            "upstream_apk_remote": {
                "normal": metadata,
                "aarch64": {**metadata, "url": "https://example/RetroArch_aarch64.apk"},
            },
        }
        nightly_pipeline.check_processed_remote_metadata(
            state,
            lambda url: state["upstream_apk_remote"][
                "aarch64" if "aarch64" in url else "normal"
            ],
        )


class WorkflowContractTests(unittest.TestCase):
    def test_android_command_line_tools_are_set_up_before_sdkmanager(self):
        repository = TOOLS_DIR.parents[1]
        workflow = (repository / ".github/workflows/config-hierarchy-nightly.yml").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            workflow.index("android-actions/setup-android@v4"),
            workflow.index("sdkmanager --install"),
        )

    def test_publication_uses_workflow_capable_release_token(self):
        repository = TOOLS_DIR.parents[1]
        workflow = (repository / ".github/workflows/config-hierarchy-nightly.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("RELEASE_PAT: ${{ secrets.RELEASE_PAT }}", workflow)
        self.assertIn(
            'git remote set-url origin "https://x-access-token:${RELEASE_PAT}@github.com/${GITHUB_REPOSITORY}.git"',
            workflow,
        )

    def test_release_commit_reaches_main_before_draft_creation(self):
        repository = TOOLS_DIR.parents[1]
        workflow = (repository / ".github/workflows/config-hierarchy-nightly.yml").read_text(
            encoding="utf-8"
        )
        publication = workflow.split(
            "- name: Draft, re-download, and transactionally publish prerelease", 1
        )[1]
        advance = publication.index('origin "HEAD:refs/heads/${ORIGINAL_BRANCH}"')
        mark_advanced = publication.index("branch_advanced=true")
        create_draft = publication.index('gh release create "$tag"')
        self.assertLess(advance, create_draft)
        self.assertLess(mark_advanced, create_draft)


class ElfRevisionTests(unittest.TestCase):
    def test_extracts_revision_from_named_elf_symbol(self):
        elf = build_elf64_with_symbol("retroarch_git_version", b"31c4e00\0")
        self.assertEqual(
            "31c4e00",
            extract_apk_revision.extract_elf_symbol(elf, "retroarch_git_version").decode(),
        )

    def test_extracts_revision_from_32_bit_elf_symbol(self):
        elf = build_elf32_with_symbol("retroarch_git_version", b"31c4e00\0")
        self.assertEqual(
            "31c4e00",
            extract_apk_revision.extract_elf_symbol(elf, "retroarch_git_version").decode(),
        )

    def test_apk_requires_same_revision_in_every_native_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "fixture.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(
                    "lib/arm64-v8a/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"abc1234\0"),
                )
                archive.writestr(
                    "lib/x86_64/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"abc1234\0"),
                )
            self.assertEqual("abc1234", extract_apk_revision.extract_revision_from_apk(apk))

    def test_apk_rejects_divergent_native_abi_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "fixture.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(
                    "lib/arm64-v8a/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"abc1234\0"),
                )
                archive.writestr(
                    "lib/x86_64/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"def5678\0"),
                )
            with self.assertRaisesRegex(ValueError, "divergent"):
                extract_apk_revision.extract_revision_from_apk(apk)


class ReleaseVerificationTests(unittest.TestCase):
    def test_missing_signing_inputs_fail_preflight(self):
        with self.assertRaisesRegex(ValueError, "RELEASE_STORE_FILE"):
            verify_release.require_signing_environment({})

    def test_aliases_must_be_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            dated = directory / "2026-08-09-RetroArch.apk"
            alias = directory / "RetroArch.apk"
            dated.write_bytes(b"same")
            alias.write_bytes(b"same")
            verify_release.verify_alias(dated, alias)
            alias.write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "alias"):
                verify_release.verify_alias(dated, alias)

    def test_aapt_badging_parser_returns_package_and_versions(self):
        output = "package: name='com.retroarch.aarch64' versionCode='123' versionName='1.2.3_GIT'\n"
        self.assertEqual(
            ("com.retroarch.aarch64", 123, "1.2.3_GIT"),
            verify_release.parse_aapt_badging(output),
        )

    def test_signer_parser_normalizes_pinned_sha256(self):
        output = "Signer #1 certificate SHA-256 digest: AA:bb:01\n"
        self.assertEqual("AABB01", verify_release.parse_signer_sha256(output))

    def test_archive_inspection_reads_abis_revision_and_provenance(self):
        provenance = {"upstream_revision": "f" * 40, "patch_revision": "patch-v1"}
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "fixture.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(
                    "lib/arm64-v8a/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"abc1234\0"),
                )
                archive.writestr(
                    "assets/config-hierarchy-provenance.json", json.dumps(provenance)
                )
            inspected = verify_release.inspect_archive(apk)
            self.assertEqual(["arm64-v8a"], inspected["abis"])
            self.assertEqual("abc1234", inspected["fork_revision"])
            self.assertEqual(provenance, inspected["provenance"])

    def test_apk_verification_captures_zipalign_output(self):
        provenance = {"upstream_revision": "f" * 40, "patch_revision": "patch-v1"}
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "fixture.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(
                    "lib/arm64-v8a/libretroarch-activity.so",
                    build_elf64_with_symbol("retroarch_git_version", b"abc1234\0"),
                )
                archive.writestr(
                    "assets/config-hierarchy-provenance.json", json.dumps(provenance)
                )
            outputs = [
                "package: name='com.retroarch.aarch64' versionCode='123' versionName='1_GIT'\n",
                "Signer #1 certificate SHA-256 digest: AA:BB\n",
                "Verification successful\n",
            ]
            with mock.patch.object(verify_release, "run_checked", side_effect=outputs), mock.patch.object(
                verify_release.subprocess,
                "run",
                side_effect=AssertionError("verifier subprocess output was not captured"),
            ):
                result = verify_release.verify_apk(
                    apk,
                    "com.retroarch.aarch64",
                    ["arm64-v8a"],
                    "AABB",
                    "abc1234" + "0" * 33,
                    "f" * 40,
                    "patch-v1",
                    "aapt",
                    "apksigner",
                    "zipalign",
                )
            self.assertEqual("com.retroarch.aarch64", result["package"])

    def test_release_notes_include_required_provenance_and_hashes(self):
        body = release_notes.render(
            {
                "nightly_date": "2026-08-09",
                "upstream_revision": "a" * 40,
                "upstream_apk_revision": "31c4e00",
                "upstream_revision_exact": False,
                "fork_revision": "b" * 40,
                "patch_revision": "4c1a5e4182",
                "signer_sha256": "CCDD",
                "version_name": "1.2.3_GIT",
                "version_code": 123,
                "assets": {"RetroArch.apk": "deadbeef"},
            }
        )
        for expected in ("2026-08-09", "a" * 40, "b" * 40, "4c1a5e4182", "CCDD", "deadbeef"):
            self.assertIn(expected, body)
        self.assertIn("official RetroArch APK must be uninstalled", body)
        self.assertIn("APK-reported revision: `31c4e00`", body)
        self.assertIn("Exact APK/source match: `false`", body)


class ReleaseOrchestrationTests(unittest.TestCase):
    def test_version_code_is_monotonic_when_clock_does_not_advance(self):
        self.assertEqual(101, run_release.next_version_code(100, 99))
        self.assertEqual(123, run_release.next_version_code(100, 123))

    def test_provenance_files_capture_exact_upstream_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            state_path = directory / "state.json"
            asset_path = directory / "provenance.json"
            metadata = run_release.write_provenance(
                date="2026-08-09",
                upstream_revision="a" * 40,
                normal_hash="normal-hash",
                aarch64_hash="aarch64-hash",
                patch_revision="public-config-v1",
                previous_version_code=123,
                state_path=state_path,
                asset_path=asset_path,
            )
            self.assertEqual(metadata, json.loads(state_path.read_text()))
            embedded = json.loads(asset_path.read_text())
            self.assertEqual("a" * 40, embedded["upstream_revision"])
            self.assertEqual("public-config-v1", embedded["patch_revision"])
            self.assertNotIn("previous_version_code", embedded)

    def test_provenance_discloses_unpublished_apk_revision_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            metadata = run_release.write_provenance(
                date="2026-08-10",
                upstream_revision="b" * 40,
                upstream_apk_revision="31c4e00",
                upstream_revision_exact=False,
                normal_hash="normal-hash",
                aarch64_hash="aarch64-hash",
                patch_revision="public-config-v1",
                previous_version_code=123,
                state_path=directory / "state.json",
                asset_path=directory / "provenance.json",
            )
            self.assertEqual("31c4e00", metadata["upstream_apk_revision"])
            self.assertFalse(metadata["upstream_revision_exact"])

    def test_provenance_state_records_upstream_remote_identity(self):
        remote = {
            "normal": {
                "url": "https://example/RetroArch.apk",
                "etag": "normal-etag",
                "last_modified": "today",
                "content_length": "100",
            },
            "aarch64": {
                "url": "https://example/RetroArch_aarch64.apk",
                "etag": "aarch64-etag",
                "last_modified": "today",
                "content_length": "90",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            state = run_release.write_provenance(
                date="2026-08-09",
                upstream_revision="a" * 40,
                normal_hash="normal-hash",
                aarch64_hash="aarch64-hash",
                patch_revision="public-config-v1",
                previous_version_code=123,
                state_path=directory / "state.json",
                asset_path=directory / "provenance.json",
                upstream_apk_remote=remote,
            )
            self.assertEqual(remote, state["upstream_apk_remote"])
            embedded = json.loads((directory / "provenance.json").read_text())
            self.assertNotIn("upstream_apk_remote", embedded)

    def test_metadata_commit_is_amended_after_first_release(self):
        self.assertEqual("commit", run_release.metadata_commit_action("automation: pipeline"))
        self.assertEqual("amend", run_release.metadata_commit_action("release: nightly metadata"))

    def test_download_validation_rejects_non_zip_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "not-an-apk.apk"
            payload.write_bytes(b"html error")
            with self.assertRaisesRegex(ValueError, "ZIP"):
                run_release.validate_apk(payload)

    def test_upstream_assets_are_reused_without_apk_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            apk = directory / "upstream.apk"
            target = directory / "assets"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("assets/assets/ozone/icon.png", b"icon")
                archive.writestr("assets/autoconfig/android/pad.cfg", b"pad")
                archive.writestr("lib/arm64-v8a/libretroarch-activity.so", b"native")
            run_release.extract_upstream_assets(apk, target)
            self.assertEqual(b"icon", (target / "assets/ozone/icon.png").read_bytes())
            self.assertEqual(b"pad", (target / "autoconfig/android/pad.cfg").read_bytes())
            self.assertFalse((target / "lib").exists())

    def test_pair_metadata_rejects_mismatched_versions(self):
        normal = {"version_code": 123, "version_name": "1_GIT", "signer_sha256": "AA"}
        aarch64 = {**normal, "version_code": 124}
        with self.assertRaisesRegex(ValueError, "version"):
            run_release.assemble_release_metadata(
                {"date": "2026-08-09", "upstream_revision": "a" * 40, "patch_revision": "v1", "version_code": 123},
                normal,
                aarch64,
                {"RetroArch.apk": "hash"},
                "b" * 40,
            )

    def test_pair_metadata_records_verified_release_contract(self):
        verification = {
            "version_code": 123,
            "version_name": "1_GIT",
            "signer_sha256": "AA",
        }
        result = run_release.assemble_release_metadata(
            {"date": "2026-08-09", "upstream_revision": "a" * 40, "patch_revision": "v1", "version_code": 123},
            verification,
            verification,
            {"RetroArch.apk": "hash"},
            "b" * 40,
        )
        self.assertEqual("2026-08-09", result["nightly_date"])
        self.assertEqual(123, result["version_code"])
        self.assertEqual("b" * 40, result["fork_revision"])

    def test_pair_metadata_rejects_unplanned_version_code(self):
        verification = {
            "version_code": 124,
            "version_name": "1_GIT",
            "signer_sha256": "AA",
        }
        with self.assertRaisesRegex(ValueError, "planned"):
            run_release.assemble_release_metadata(
                {"date": "2026-08-09", "upstream_revision": "a" * 40, "patch_revision": "v1", "version_code": 123},
                verification,
                verification,
                {"RetroArch.apk": "hash"},
                "b" * 40,
            )

    def test_downloaded_release_assets_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            asset = directory / "RetroArch.apk"
            asset.write_bytes(b"release")
            manifest = {asset.name: hashlib.sha256(b"release").hexdigest()}
            run_release.verify_asset_manifest(directory, manifest)
            asset.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash"):
                run_release.verify_asset_manifest(directory, manifest)


def build_elf64_with_symbol(symbol_name, value):
    shstr = b"\0.rodata\0.dynsym\0.dynstr\0.shstrtab\0"
    dynstr = b"\0" + symbol_name.encode() + b"\0"
    rodata = value
    null_symbol = b"\0" * 24
    symbol = struct.pack("<IBBHQQ", 1, 0x11, 0, 1, 0x1000, len(value))
    dynsym = null_symbol + symbol

    parts = []
    offset = 64
    for blob, alignment in ((rodata, 8), (dynsym, 8), (dynstr, 1), (shstr, 1)):
        offset = align(offset, alignment)
        parts.append((offset, blob))
        offset += len(blob)
    section_header_offset = align(offset, 8)

    header = bytearray(64)
    header[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIQQQIHHHHHH", header, 16, 3, 183, 1, 0, 0, section_header_offset, 0, 64, 0, 0, 64, 5, 4)
    image = bytearray(section_header_offset + 5 * 64)
    image[:64] = header
    for part_offset, blob in parts:
        image[part_offset : part_offset + len(blob)] = blob

    names = {name: shstr.index(name.encode()) for name in (".rodata", ".dynsym", ".dynstr", ".shstrtab")}
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (names[".rodata"], 1, 2, 0x1000, parts[0][0], len(rodata), 0, 0, 8, 0),
        (names[".dynsym"], 11, 2, 0, parts[1][0], len(dynsym), 3, 1, 8, 24),
        (names[".dynstr"], 3, 2, 0, parts[2][0], len(dynstr), 0, 0, 1, 0),
        (names[".shstrtab"], 3, 0, 0, parts[3][0], len(shstr), 0, 0, 1, 0),
    ]
    for index, section in enumerate(sections):
        struct.pack_into("<IIQQQQIIQQ", image, section_header_offset + index * 64, *section)
    return bytes(image)


def build_elf32_with_symbol(symbol_name, value):
    shstr = b"\0.rodata\0.dynsym\0.dynstr\0.shstrtab\0"
    dynstr = b"\0" + symbol_name.encode() + b"\0"
    rodata = value
    null_symbol = b"\0" * 16
    symbol = struct.pack("<IIIBBH", 1, 0x1000, len(value), 0x11, 0, 1)
    dynsym = null_symbol + symbol

    parts = []
    offset = 52
    for blob, alignment in ((rodata, 4), (dynsym, 4), (dynstr, 1), (shstr, 1)):
        offset = align(offset, alignment)
        parts.append((offset, blob))
        offset += len(blob)
    section_header_offset = align(offset, 4)

    header = bytearray(52)
    header[:16] = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIIIIIHHHHHH", header, 16, 3, 40, 1, 0, 0, section_header_offset, 0, 52, 0, 0, 40, 5, 4)
    image = bytearray(section_header_offset + 5 * 40)
    image[:52] = header
    for part_offset, blob in parts:
        image[part_offset : part_offset + len(blob)] = blob

    names = {name: shstr.index(name.encode()) for name in (".rodata", ".dynsym", ".dynstr", ".shstrtab")}
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (names[".rodata"], 1, 2, 0x1000, parts[0][0], len(rodata), 0, 0, 4, 0),
        (names[".dynsym"], 11, 2, 0, parts[1][0], len(dynsym), 3, 1, 4, 16),
        (names[".dynstr"], 3, 2, 0, parts[2][0], len(dynstr), 0, 0, 1, 0),
        (names[".shstrtab"], 3, 0, 0, parts[3][0], len(shstr), 0, 0, 1, 0),
    ]
    for index, section in enumerate(sections):
        struct.pack_into("<IIIIIIIIII", image, section_header_offset + index * 40, *section)
    return bytes(image)


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


if __name__ == "__main__":
    unittest.main()
