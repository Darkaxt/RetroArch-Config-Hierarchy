# RetroArch Legacy Config Alias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the historical app-specific Android default config path a compatibility alias for the public RetroArch config while preserving every genuine caller-supplied custom path.

**Architecture:** Upstream removed the Java launcher during implementation, so the final patch centralizes selection in `frontend/drivers/platform_unix.c`. It defers assignment of the Intent's `CONFIGFILE` until storage paths are known, aliases only the canonical historical app-specific default, and leaves every custom and Play path unchanged.

**Tech Stack:** C/JNI, Android intents and storage APIs, Gradle/NDK, Python `unittest`, GitHub Actions.

---

## Upstream architecture adaptation

Tasks 1-4 below record the test-first implementation completed against the pre-2026-08-21 Java launcher. During publication review, upstream commit `8075cbe77c` removed that launcher and made the Java files obsolete. The maintained stack was then rebased and translated test-first to the native environment resolver:

- [x] Reproduce the scheduled rebase failure on the completed upstream pair.
- [x] Trace the failure to upstream's Java-launcher removal and new native config derivation.
- [x] Add three failing native source-boundary regressions.
- [x] Implement public-default selection and the exact legacy alias in `platform_unix.c`.
- [x] Preserve custom explicit paths and Play's app-specific probe order.
- [x] Pass the 43-test config suite, all Gradle tests, both Play Java compilations, and a four-ABI normal native build.
- [x] Update the specification, validation, README, operations, and release disclosure to describe the final no-copy native architecture.

## Task 1: Specify the compatibility selector with failing unit tests

**Files:**

- Modify: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ActiveConfigPathTest.java`
- Test: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ActiveConfigPathTest.java`

- [x] Add tests proving that null and empty explicit paths resolve the public default.
- [x] Add tests proving that an exact legacy app-specific default, and a canonically equivalent spelling of it, resolve the public default.
- [x] Add tests proving that a custom sibling path, the same filename in another directory, and an explicit public path remain explicit without unnecessary default resolution.
- [x] Add tests proving that a null legacy path and canonicalization failure preserve the explicit path.
- [x] Run the focused `ActiveConfigPathTest` task and confirm the new tests fail because the compatibility selector API does not exist.
- [x] Commit the failing regression tests with message `test: cover legacy config compatibility alias`.

## Task 2: Implement the minimal path selector

**Files:**

- Modify: `pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/ActiveConfigPath.java`
- Test: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ActiveConfigPathTest.java`

- [x] Add a selector overload accepting the explicit path, nullable legacy default path, and lazy public-default provider.
- [x] Compare the explicit and legacy paths through `File.getCanonicalPath()` and redirect only when they are equivalent.
- [x] Preserve the explicit path when canonicalization throws, the legacy path is unavailable, or the explicit path is any genuine custom path.
- [x] Keep the existing two-argument selector as a compatibility overload that supplies no legacy alias.
- [x] Run the focused `ActiveConfigPathTest` and require all tests to pass.
- [x] Run `git diff --check` and commit with message `feat: alias legacy Android config default`.

## Task 3: Expose the exact legacy default and normalize all modern launch paths

**Files:**

- Modify: `pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/UserPreferences.java`
- Modify: `pkg/android/phoenix/src/com/retroarch/browser/mainmenu/MainMenuActivity.java`
- Modify: `pkg/android/phoenix/src/com/retroarch/browser/retroactivity/RetroActivityFuture.java`
- Modify: `pkg/android/phoenix/src/test/java/com/retroarch/browser/preferences/util/ActiveConfigPathTest.java`

- [x] Add the smallest failing test needed for any selector behavior discovered while wiring the Android call sites, then run it and confirm the expected failure before production edits.
- [x] Factor the active config filename calculation in `UserPreferences` so the public and legacy candidates always use the same filename.
- [x] Expose a nullable legacy app-specific config candidate only for non-Play builds; do not create, copy, or modify the legacy file.
- [x] Update `MainMenuActivity` to pass the legacy candidate into the shared selector while retaining `updateConfigFile()` when the public default is selected.
- [x] In `RetroActivityFuture.onCreate`, normalize `CONFIGFILE` on the existing Intent before `super.onCreate()` so native startup receives the canonical public selection.
- [x] Normalize incoming intents before `super.onNewIntent()` and before any restart or `setIntent()` path.
- [x] Make later Java-side config reads use the already normalized Intent, with the same safe fallback when the extra is absent.
- [x] Compile normal and Play Store Java variants.
- [x] Run the focused selector tests and the complete `testNormalDebugUnitTest` suite.
- [x] Commit with message `feat: normalize legacy config launch intents`.

## Task 4: Validate stage 1 against the design specification

**Files:**

- Create: `docs/validation/2026-08-21-legacy-config-alias.md`
- Review: `docs/superpowers/specs/2026-08-21-retroarch-legacy-config-alias-design.md`

- [x] Trace every current `ActiveConfigPath.select`, `CONFIGFILE`, and `getDefaultConfigPath` call site and record why the implemented boundary covers direct human launches without changing unrelated legacy/Play variants.
- [x] Confirm there is no timestamp comparison, copying, credential-specific logic, or mutation of a genuine custom config path.
- [x] Run `python -m unittest discover -s tools/config-hierarchy/tests -p 'test_*.py'` and require zero failures.
- [x] Run actionlint on `.github/workflows/config-hierarchy-nightly.yml` and require zero findings.
- [x] Run `git diff --check` and inspect the full diff against every acceptance case in the design specification.
- [x] Record commands, results, and the design-spec decision table in the validation document.
- [x] Commit with message `docs: validate legacy config compatibility alias`.

## Task 5: Publish through the existing nightly pipeline

**Files:**

- Verify: `.github/workflows/config-hierarchy-nightly.yml`
- Verify: `tools/config-hierarchy/release_state.json`

- [x] Fetch `origin` and `upstream`, rebase the maintained stack onto current upstream after the launcher-removal conflict, and rerun the native regression/build gates plus `git diff --check`.
- [ ] Push the verified branch tip to `origin/main` without force.
- [ ] Inspect the newest completed upstream Android nightly pair and the fork release state.
- [ ] Dispatch the existing `config-hierarchy-nightly.yml` workflow only when it can process a completed, unreleased upstream pair; otherwise remain attached until the next normal trigger can publish the code without creating a duplicate release.
- [ ] Follow the workflow through completion and verify the public release rather than trusting workflow status alone.
- [ ] Confirm the release is non-draft and has exactly `RetroArch.apk` and `RetroArch_aarch64.apk`.
- [ ] Re-download both APKs under `D:\Temp` and verify SHA-256 hashes, ZIP integrity/alignment, package IDs, expected ABIs, monotonic shared version code, signer fingerprint `BD8C473A9E1C8F3FB83EE4549AEDCFE43E77E6960118E75B7DB90A32F3640D12`, and embedded fork/patch/source provenance.
- [ ] Confirm no draft release or `config-hierarchy-staging` branch leaked.

## Task 6: Clean execution artifacts and hand off the device outcome

**Files:**

- Remove after verification: `D:\Temp\retroarch-legacy-alias-20260821`
- Remove after verification: `D:\Temp\retroarch-worktree-add.stdout.log`
- Remove after verification: `D:\Temp\retroarch-worktree-add.stderr.log`

- [ ] Remove downloaded verification APKs and other disposable files under `D:\Temp`.
- [ ] Remove the clean worktree through Git and delete the feature branch only after the commit is safely on `origin/main`.
- [ ] Confirm the retained checkout at `C:\Users\darka\Documents\Projects\Android\RetroArch-Config-Hierarchy` was not reset or modified.
- [ ] Report the published release and explain that after installing it, direct human/Cocoon launches treat the old app-specific default as an alias of the public config; genuine custom `CONFIGFILE` arguments still work.
