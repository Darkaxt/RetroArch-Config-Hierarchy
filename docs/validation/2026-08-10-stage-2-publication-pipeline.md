# Stage 2 Validation: Publication Pipeline

Date: 2026-08-10

Design under test: `docs/superpowers/specs/2026-08-10-retroarch-config-hierarchy-design.md`

## Automated evidence

- `python -m unittest discover -s tools/config-hierarchy/tests -v`: 29 tests passed.
- `actionlint .github/workflows/config-hierarchy-nightly.yml`: passed.
- Gradle release-signing preflight with missing signer inputs: failed during configuration as required; debug signing was not used.
- Signed Gradle matrix (`test`, both Play release compile checks, `assembleNormalRelease`, and `assembleAarch64Release`): 245 tasks completed successfully in one invocation.
- Final release verifier, normal APK: passed for package `com.retroarch`, ABIs `armeabi-v7a`, `arm64-v8a`, `x86`, and `x86_64`, version code `1786313695`, version name `1.22.2_GIT`, fork revision `735bc8175a41`, and the pinned signer.
- Final release verifier, AArch64 APK: passed for package `com.retroarch.aarch64`, ABIs `arm64-v8a` and `x86_64`, the same version, fork revision, and pinned signer.
- Signer SHA-256 for both APKs: `BD8C473A9E1C8F3FB83EE4549AEDCFE43E77E6960118E75B7DB90A32F3640D12`.
- Normal APK SHA-256: `0395b61ca17dc4793e68c4f4d7f1e5df4ecd04ad53a62b17d7f9a6f70e38081a`.
- AArch64 APK SHA-256: `21da0632b56d23e3b85c4990f2b1ad35f0d2fa725221eeed7ff0e2e2035591c3`.
- GitHub Actions run `31340444178`: passed the activated no-op path in 37 seconds and skipped download, build, signing, and publication because no complete pair was newer than the baseline.

The signed validation build used the full asset payload extracted from the validated upstream normal APK. Both final APKs passed ZIP integrity, `zipalign`, `aapt` package/version inspection, `apksigner` certificate inspection, ABI inspection, ELF revision extraction, and embedded provenance checks.

## Design acceptance mapping

| Design requirement | Evidence | Result |
| --- | --- | --- |
| Wait for both upstream variants | Discovery accepts only a complete normal/AArch64 date pair; partial-pair and missed-date tests pass. | Passed |
| Build from the exact revision embedded in both APKs | Every ABI is inspected; divergent, missing, unknown, and rollback revisions fail closed. Exact commit resolution is required before rebase/build. | Passed in tests and live fail-closed check |
| Maintain the fork patch without semantic auto-resolution | The workflow rebases the maintained commit stack on the proven source and stops on conflict. | Passed by inspection and orchestration coverage |
| Build both variants together | One signed Gradle invocation produced and tested both release variants. | Passed |
| Validate signer, package, ABI, version, alignment, integrity, and provenance | Independent verification passed for both signed outputs with the expected, matching version and permanent certificate. | Passed |
| Publish dated assets and byte-identical stable aliases | Manifest and alias-identity tests pass; publication re-downloads all four GitHub assets and verifies their hashes before making the prerelease public. | Passed locally; live release intentionally pending a resolvable upstream pair |
| Repeated heartbeat is idempotent | Released dates are a no-op; changed previously processed upstream artifacts are rejected. | Passed |
| Publication is transactional | Draft/tag/staging cleanup and force-with-lease branch restoration are implemented; incomplete remote manifests block publication. | Passed by inspection and orchestration coverage |
| Obtainium/ObtainX can update in place | Both package IDs use one pinned permanent signer and a shared deterministic monotonic version code. | Artifact contract passed; first/second device install remains a deployment gate |

## Live upstream provenance check

Local validation of the latest completed official pair available at the time (`2026-08-09`) found that both APKs embed short revision `31c4e00`, which does not resolve in `libretro/RetroArch`.

After GitHub activation, workflow-dispatch run `31340197569` exercised the monitor from its initially empty state. It downloaded and structurally validated the oldest archived complete pair (`2026-07-27`), found matching embedded revision `14b958d`, and failed at exact-source resolution because that revision is also absent from the public upstream repository. It created no release or staging ref and left `main` unchanged. The archive state is now seeded at `2026-08-09`, the activation baseline, so scheduled runs mirror future completed nightlies without trying to retroactively publish an unverifiable backlog.

Both checks demonstrate the required failure behavior: the workflow stops before rebase, signing, branch advancement, or release creation rather than approximating an upstream nightly.

## Remaining first-release gates

These are intentionally not claimed by stage 2 automation:

- create and test the required offline recovery copy of the permanent signer;
- wait for an upstream nightly pair whose embedded revision resolves to an exact public commit;
- perform the one-time rooted Thor migration manually, then validate active-config saves/restarts and the first Obtainium/ObtainX in-place update.

The publication implementation is complete. A public prerelease must remain blocked until the external provenance and first-device gates above are satisfied.
