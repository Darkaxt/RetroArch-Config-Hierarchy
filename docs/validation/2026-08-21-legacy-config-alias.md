# Legacy Config Compatibility Alias Validation

**Date:** 2026-08-21  
**Specification:** `docs/superpowers/specs/2026-08-21-retroarch-legacy-config-alias-design.md`  
**Stage:** Settings behavior complete; publication pending

## Result

Stage 1 satisfies the approved design. Non-Play modern Android builds treat only the historical app-specific default as an alias of the public master config. Arbitrary explicit `CONFIGFILE` paths remain authoritative, Play Store intent behavior is unchanged, and no file copying or synchronization was introduced.

## Selection Contract

| Input | Legacy candidate | Result | Evidence |
| --- | --- | --- | --- |
| Absent or empty `CONFIGFILE` | Any | Public default | `ActiveConfigPathTest.absentExplicitPathUsesDefaultResolver` and `emptyExplicitPathUsesDefaultResolver` |
| Exact legacy default | Available | Public default | `exactLegacyDefaultUsesPublicDefault` |
| Canonically equivalent legacy spelling | Available | Public default | `canonicallyEquivalentLegacyDefaultUsesPublicDefault` |
| Custom sibling path | Available | Explicit path | `customSiblingPathRemainsExplicitWithoutResolvingDefault` |
| Same filename elsewhere | Available | Explicit path | `sameFilenameElsewhereRemainsExplicit` |
| Public path explicitly supplied | Available | Explicit public path | `explicitPublicPathRemainsExplicitWithoutResolvingDefault` |
| Canonicalization fails | Available | Explicit path | `canonicalizationFailurePreservesExplicitPath` |
| Legacy external directory unavailable | Null | Explicit path | `absentLegacyDefaultPreservesExplicitPath` |
| Play Store direct launch | Disabled by build policy | Upstream Intent unchanged | `test_play_store_direct_launches_keep_upstream_intent_behavior` plus Play compilation |

The active filename is calculated once by `UserPreferences.getDefaultConfigFileName()` and reused for both public resolution and the legacy app-specific candidate. This retains the existing `global_config_enable` and per-core filename policy.

## Launch Boundary

The published `normal` and `aarch64` APKs share the modern `phoenix` sources. `MainMenuActivity` uses the shared selector before putting `CONFIGFILE` into the RetroActivity Intent. Direct external launches enter `RetroActivityFuture`, which rewrites that same Intent before `super.onCreate()`; native `platform_unix.c` therefore reads the selected path during startup. Incoming intents are likewise normalized before `super.onNewIntent()` and before restart or `setIntent()` handling.

Jelly Bean and legacy Android front ends are not built into the two published nightly APKs and retain their existing behavior. Core sideload, subordinate config directories, native command-line `-c`, overrides, remaps, and core options are outside this master-Intent boundary and were not changed.

## Prohibited Mechanisms Audit

- No timestamp comparison was added.
- No public-to-private or private-to-public copy was added.
- No legacy file is created, rewritten, deleted, or used as fallback after alias selection.
- No RetroAchievements or credential-specific key appears in the patch.
- No symlink, merge rule, or background synchronization was added.
- Canonicalization failure and a null legacy directory both preserve the explicit argument.

## Verification Evidence

- Red phase: the focused Java test compilation failed with seven missing-selector overload errors before production implementation.
- Focused Java selector suite: 10 tests, 0 failures, 0 errors.
- Complete `testNormalDebugUnitTest`: 22 tests, 0 failures, 0 errors.
- Android wiring regression: 4 tests passed, including startup/new-intent ordering and Play isolation.
- Complete config-hierarchy suite: 44 tests passed.
- `compileNormalDebugJavaWithJavac`, `compilePlayStoreNormalReleaseJavaWithJavac`, and `compilePlayStorePlusReleaseJavaWithJavac`: successful.
- `D:\Tools\actionlint-1.7.12\actionlint.exe .github/workflows/config-hierarchy-nightly.yml`: exit 0.
- `git diff --check`: exit 0.

Gradle emitted only existing Android plugin deprecation, manifest, and 32-bit flavor warnings. The signed `assembleNormalRelease` and `assembleAarch64Release` builds, signer/provenance checks, and public two-asset verification remain Stage 2 gates in the existing nightly workflow.
