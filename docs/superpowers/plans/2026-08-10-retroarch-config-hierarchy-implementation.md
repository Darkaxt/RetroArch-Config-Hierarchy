# RetroArch Config Hierarchy Implementation Plan

> **For Codex:** Execute this plan with the executing-plans skill. Apply test-driven development to behavioral code and verify every completion claim with fresh command output.

**Goal:** Make ordinary non-Play Android launches use the persistent public RetroArch master config while preserving an explicit `CONFIGFILE`, then publish exact-source replicas of completed upstream Android nightlies under the fork signer.

**Architecture:** A small, testable Java resolver owns public-first selection and byte-preserving migration; the Android activities provide flavor, storage, and intent context. A scheduled GitHub Actions monitor delegates discovery, provenance extraction, patch rebasing, signing, artifact verification, and draft-prerelease publication to repository scripts that have offline tests.

**Tech Stack:** Java/Android Gradle, JUnit 4, Python 3 standard library, PowerShell/Bash, GitHub Actions, Android SDK build-tools, GitHub CLI.

---

## Stage 1: Settings behavior

### Task 1: Specify resolver behavior with failing unit tests

**Files:**
- Modify: `pkg/android/phoenix/build.gradle`
- Create: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ConfigPathPolicyTest.java`
- Create: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ActiveConfigPathTest.java`

1. Add the JUnit 4 unit-test dependency and test source support without changing production behavior.
2. Write focused tests for explicit-path precedence, empty explicit fallback, public-file precedence, external/internal legacy order, byte-exact migration, fresh initialization selection, stale temporary files, publication failure, null legacy locations, concurrent destination creation, and app-specific Play policy.
3. Run `gradlew.bat :phoenix:testNormalDebugUnitTest` and record the expected compilation/test failure because the policy classes do not exist.

### Task 2: Implement the resolver and active-path policy

**Files:**
- Create: `pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/ConfigPathPolicy.java`
- Create: `pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/ActiveConfigPath.java`
- Modify: `pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/UserPreferences.java`

1. Implement a pure-Java public-first resolver with exact legacy-source ordering, unique destination-directory temporary files, flush/sync, length and SHA-256 verification, no-replace publication, cleanup, and visible exceptions.
2. Preserve the Play/app-specific policy and safely handle a null external-files directory.
3. Implement explicit non-empty `CONFIGFILE` selection as a small reusable policy.
4. Run the focused unit test task until green, then run the complete Phoenix unit-test suite.

### Task 3: Wire permission-aware launch and Java consumers

**Files:**
- Modify: `pkg/android/phoenix/src/com/retroarch/browser/mainmenu/MainMenuActivity.java`
- Modify: `pkg/android/phoenix/src/com/retroarch/browser/retroactivity/RetroActivityFuture.java`
- Modify: `pkg/android/phoenix/src/com/retroarch/browser/preferences/util/UserPreferences.java` only if flavor wiring requires it

1. Preserve an incoming non-empty `CONFIGFILE`; otherwise resolve/update only after required shared-storage permission is available.
2. Ensure initialization and native launch happen once per activity start and surface resolver failure instead of silently falling back private.
3. Make notch and mouse-grab reads use the same active intent path as native.
4. Run focused unit tests, assemble `normalRelease`, `aarch64Release`, and compile both Play release variants.

### Task 4: Validate Stage 1 against the design specification

**Files:**
- Create: `docs/validation/2026-08-10-stage-1-settings-behavior.md`

1. Trace every Stage 1 acceptance criterion to code and automated evidence; mark device-only checks explicitly pending first Thor deployment rather than claiming them.
2. Inspect the diff to confirm native configuration and subordinate override/remap/core-option behavior were not broadened.
3. Run the final Stage 1 unit and build commands fresh, record exact results, and commit Stage 1.

## Stage 2: Publication pipeline

### Task 5: Specify nightly discovery and provenance behavior with failing tests

**Files:**
- Create: `tools/config-hierarchy/tests/test_nightly_pipeline.py`
- Create: `tools/config-hierarchy/nightly_pipeline.py`

1. Write standard-library tests for complete-pair detection, partial-pair deferral, missed-date discovery, released-pair idempotence, changed-upstream detection, divergent/unknown revisions, rollback rejection, and asset-alias identity.
2. Run `python -m unittest discover -s tools/config-hierarchy/tests -v` and record the expected failures before implementation.
3. Implement the smallest reusable functions required for discovery, state comparison, provenance resolution, and hash manifests, then rerun until green.

### Task 6: Implement exact-source build, signer, and artifact gates

**Files:**
- Create: `tools/config-hierarchy/extract_apk_revision.py`
- Create: `tools/config-hierarchy/verify_release.py`
- Create: `tools/config-hierarchy/release_notes.py`
- Create: `config-hierarchy/signer-certificate-sha256.txt`
- Modify: `pkg/android/phoenix/build.gradle`
- Modify tests under `tools/config-hierarchy/tests/`

1. Add failing tests for embedded-revision extraction fixtures, missing signer inputs, wrong package/signer/ABI/version/provenance, and release-note/manifest contents.
2. Implement exact revision extraction from both upstream APKs and require the same full Git commit.
3. Remove release debug-signing fallback for CI release builds and validate the pinned signer before Gradle.
4. Verify final APK archive integrity, alignment, package IDs, ABIs, versions, signer, embedded fork revision, upstream-base provenance, aliases, and hashes.
5. Exercise revision extraction against a live completed upstream nightly pair before accepting the gate.

### Task 7: Implement the scheduled transactional release workflow

**Files:**
- Create: `.github/workflows/config-hierarchy-nightly.yml`
- Create: `tools/config-hierarchy/run_release.py`
- Create: `docs/release-operations.md`
- Modify: `README.md`
- Modify pipeline tests as required

1. Add a scheduled monitoring heartbeat plus manual dispatch; require both dated upstream APK variants before doing work.
2. In an isolated checkout, resolve the embedded upstream commit, reject rollback/replacement, rebase the maintained patch stack without automatic conflict resolution, and build both releases in one Gradle invocation.
3. Fail before build when signing secrets are absent; assemble a draft release, upload four assets, download and re-hash them, then publish it as a prerelease.
4. Advance the maintained branch and immutable release tag only after all tests, builds, and remote asset checks pass.
5. Document required secrets, the permanent-key recovery requirement, Obtainium/ObtainX filters, and the manual Thor signer-transition checklist; do not create a migration script.

### Task 8: Validate Stage 2 and complete the branch

**Files:**
- Create: `docs/validation/2026-08-10-stage-2-publication-pipeline.md`

1. Trace every Stage 2 acceptance criterion and failure semantic to workflow/script code and test evidence.
2. Run all Java and Python tests, both release assemblies, both Play compile checks, workflow syntax validation, script syntax validation, and repository diff/status checks fresh.
3. Create or connect the public GitHub fork repository, configure its permanent signer secrets and pinned certificate, push the maintained branch, and manually dispatch the first pipeline only if the live upstream pair and all credentials are valid.
4. Publish only after the draft assets pass remote re-download verification; otherwise leave no public release and report the precise external blocker.
5. Commit and push the verified implementation, preserving immutable release history.
