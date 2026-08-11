# Stage 2 Validation: Publication Pipeline

Date: 2026-08-10; live publication validated 2026-08-12

Design under test: `docs/superpowers/specs/2026-08-10-retroarch-config-hierarchy-design.md`

## Automated evidence

- `python -m unittest discover -s tools/config-hierarchy/tests -p 'test_*.py'`: 36 tests passed.
- `actionlint .github/workflows/config-hierarchy-nightly.yml`: passed.
- Gradle release-signing preflight with missing signer inputs: failed during configuration as required; debug signing was not used.
- GitHub Actions run [`31536815901`](https://github.com/Darkaxt/RetroArch-Config-Hierarchy/actions/runs/31536815901) passed discovery, source selection, patch rebase, signing, the combined test/build matrix, final APK verification, draft creation, four-asset upload, four-asset re-download, hash verification, and public prerelease promotion.
- Public prerelease [`nightly-2026-08-10-fa7b68b`](https://github.com/Darkaxt/RetroArch-Config-Hierarchy/releases/tag/nightly-2026-08-10-fa7b68b) is non-draft and contains exactly the two dated APKs plus their byte-identical stable aliases.
- Final release verifier, normal APK: passed for package `com.retroarch`, ABIs `armeabi-v7a`, `arm64-v8a`, `x86`, and `x86_64`, version code `1786482848`, version name `1.22.2_GIT`, fork revision `efa81cf325d8`, and the pinned signer.
- Final release verifier, AArch64 APK: passed for package `com.retroarch.aarch64`, ABIs `arm64-v8a` and `x86_64`, the same version, fork revision, and pinned signer.
- Signer SHA-256 for both APKs: `BD8C473A9E1C8F3FB83EE4549AEDCFE43E77E6960118E75B7DB90A32F3640D12`.
- Normal APK SHA-256: `353c684f728504e322927552b8ea3ad9cca9d8e1addf7c7385844e4e208f2d83`.
- AArch64 APK SHA-256: `e90ca346d4543b388f8a88f95ba82cdfa9595fc10a1ac5eed027c63715cc49d7`.
- GitHub Actions run `31340444178`: passed the activated no-op path in 37 seconds and skipped download, build, signing, and publication because no complete pair was newer than the baseline.

The signed validation build used the full asset payload extracted from the validated upstream normal APK. Both final APKs passed ZIP integrity, `zipalign`, `aapt` package/version inspection, `apksigner` certificate inspection, ABI inspection, ELF revision extraction, and embedded provenance checks. After publication, all four assets were independently downloaded from GitHub and checked again; the stable aliases matched their dated counterparts byte-for-byte.

## Two-asset contract update

On 2026-08-12, the release contract was simplified for future nightlies. The dated tag and release notes retain upstream identity, while publication now uploads and re-downloads only `RetroArch.apk` and `RetroArch_aarch64.apk`. The inaugural four-asset release remains unchanged as historical evidence. The full suite passed 37 tests, actionlint passed, and regression coverage requires a two-entry manifest while rejecting dated upload paths in the workflow.

GitHub Actions run [`31540487454`](https://github.com/Darkaxt/RetroArch-Config-Hierarchy/actions/runs/31540487454) completed the full build, verification, transactional upload, remote re-download, and publication path in 9m26s. Public prerelease [`nightly-2026-08-11-0af3e17`](https://github.com/Darkaxt/RetroArch-Config-Hierarchy/releases/tag/nightly-2026-08-11-0af3e17) contains exactly the two stable assets. GitHub reports SHA-256 `7710b0694ca633444496748ff2da2759df50ec1ed77f987142a1d269d154f61c` for `RetroArch.apk` and `62cacfbbc287dffb022cf3a8b97b3fd0f28b0b36e4a3e85aa74fba37bb7632af` for `RetroArch_aarch64.apk`.

## Design acceptance mapping

| Design requirement | Evidence | Result |
| --- | --- | --- |
| Wait for both upstream variants | Discovery accepts only a complete normal/AArch64 date pair; partial-pair and missed-date tests pass. | Passed |
| Select and disclose the upstream build source | Every ABI is inspected; divergent, missing, and rollback revisions fail closed. The exact embedded revision is preferred; an unresolvable shared revision uses the current full `upstream/master` revision only with both revisions, official APK hashes, and non-exact status embedded and published. | Passed in tests and live fallback release |
| Maintain the fork patch without semantic auto-resolution | The workflow rebases the maintained commit stack on the proven source and stops on conflict. | Passed by inspection and orchestration coverage |
| Build both variants together | One signed Gradle invocation produced and tested both release variants. | Passed |
| Validate signer, package, ABI, version, alignment, integrity, and provenance | Independent verification passed for both signed outputs with the expected, matching version and permanent certificate. | Passed |
| Publish the verified stable assets without duplicates | The August 11 public prerelease contains exactly the two stable names; the workflow re-downloaded both and verified the complete name/hash manifest before promotion. | Passed live |
| Repeated heartbeat is idempotent | Released dates are a no-op; changed previously processed upstream artifacts are rejected. | Passed |
| Publication is transactional | Failed publication attempts removed their draft/staging state and restored `main`; the successful run advanced `main`, verified all remote assets, and then promoted the draft. | Passed live |
| Obtainium/ObtainX can update in place | Both package IDs use one pinned permanent signer and a shared deterministic monotonic version code. | Artifact contract passed; first/second device install remains a deployment gate |

## Live upstream provenance check

The completed official `2026-08-10` pair reports short revision `31c4e00` in both APKs. That revision does not resolve in the public `libretro/RetroArch` repository.

After GitHub activation, workflow-dispatch run `31340197569` exercised the monitor from its initially empty state. It downloaded and structurally validated the oldest archived complete pair (`2026-07-27`), found matching embedded revision `14b958d`, and failed at exact-source resolution because that revision is also absent from the public upstream repository. It created no release or staging ref and left `main` unchanged. The archive state is now seeded at `2026-08-09`, the activation baseline, so scheduled runs mirror future completed nightlies without trying to retroactively publish an unverifiable backlog.

The approved functional-first fallback selected full public revision `fa7b68b7050829206e87b29d6caa82cd7e4e4b80` from `upstream/master`. The release provenance and notes disclose the APK-reported revision, selected build revision, `Exact APK/source match: false`, and both official APK hashes. The release therefore remains reproducible from public source without claiming an exact source match that upstream has not published.

## Remaining device and recovery gates

These are intentionally not claimed by stage 2 automation:

- create and test the required offline recovery copy of the permanent signer;
- perform the one-time rooted Thor migration manually, then validate active-config saves/restarts and the first Obtainium/ObtainX in-place update.

The publication implementation and first public prerelease are complete. The remaining items are device-deployment and recovery gates, not blockers for the already validated GitHub publication.
