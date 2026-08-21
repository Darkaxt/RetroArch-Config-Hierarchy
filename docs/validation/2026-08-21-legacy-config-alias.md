# Legacy Config Compatibility Alias Validation

**Date:** 2026-08-21

**Specification:** `docs/superpowers/specs/2026-08-21-retroarch-legacy-config-alias-design.md`

**Stage:** Settings behavior and upstream rebase complete; publication pending

## Result

Stage 1 satisfies the approved behavior on upstream's current native-launcher architecture. Non-Play Android builds select the public master config for both an argument-free icon launch and the historical app-specific default supplied by a stock-oriented launcher. Every other explicit `CONFIGFILE` remains authoritative. Play behavior is retained, and no file copying or synchronization was introduced.

## Upstream Architecture Change and Pipeline Failure

Upstream commit `8075cbe77c` removed `MainMenuActivity` and its Java config resolver on 2026-08-21. Commits `69e002d27d` through `d67a52655e` moved absent-argument environment derivation, permission gating, config parsing, and direct launcher behavior into the native Android startup path.

The previous maintained patch edited the deleted launcher. Every scheduled run for the completed 2026-08-21 upstream pair therefore failed deterministically while rebasing commit `8f2b3cb325`, with a modify/delete conflict for `MainMenuActivity.java` and content conflicts in `UserPreferences.java` and `RetroActivityFuture.java`. The patch stack was rebased onto upstream `8a275f147d0f65888fd6cd1ebee622e0d0c0d99b` and translated to `frontend/drivers/platform_unix.c`; obsolete Java resolver code and tests were not resurrected.

## Selection Contract

| Input | Build | Result |
| --- | --- | --- |
| Absent or empty `CONFIGFILE` | Non-Play | `<shared storage>/RetroArch/retroarch.cfg` |
| Exact app-specific external default | Non-Play | Public master |
| `/sdcard` or another canonically equivalent parent spelling | Non-Play | Public master |
| Custom sibling config | Non-Play | Explicit path |
| Same filename in any other directory | Non-Play | Explicit path |
| Public path explicitly supplied | Non-Play | Explicit public path |
| Canonical parent resolution fails | Non-Play | Explicit path |
| App-specific external directory is unavailable | Non-Play | Explicit path |
| Any explicit path | Play | Explicit path |
| Absent `CONFIGFILE` | Play | Upstream app-specific probe order |

`android_env_config_path_is_legacy_default()` requires the exact `retroarch.cfg` basename and compares canonical parent directories. Because it resolves the parent, the legacy file itself need not exist. `android_env_select_config_path()` preserves a requested path unless the build is non-Play and that exact identity test succeeds.

## Native Startup Boundary

`frontend_unix_get_env()` stores the raw Intent extra in `requested_config_path` without assigning `args->config_path`. It first derives application and storage paths, then calls `android_env_select_config_path()`, logs the selected path, and assigns it to `args->config_path`. This one boundary covers direct icon launches, CocoonShell launches, both published package IDs, and other external launchers.

The Play boolean is the value already obtained from `RetroActivityCommon.isPlayStoreBuild()`. Play's existing external/internal probe order is preserved inside the selector. Native command-line `-c`, desktop behavior, overrides, remaps, core options, and subordinate directories were not changed.

## Prohibited Mechanisms Audit

- No timestamp comparison was added.
- No public-to-private or private-to-public copy was added.
- No legacy file is created, rewritten, deleted, or used as a fallback after alias selection.
- No RetroAchievements or credential-specific key appears in the patch.
- No symlink, merge rule, or background synchronization was added.
- Canonicalization failure and a null app-specific external directory both preserve the explicit argument.

## Verification Evidence

- Red phase: three native source-boundary regressions failed before the translated selector existed.
- Green phase: all 3 native alias regressions passed.
- Complete config-hierarchy suite: 43 tests passed.
- Gradle `test`, both Play release Java compilations, and `assembleNormalDebug`: successful in one invocation.
- Native compilation succeeded for `arm64-v8a`, `armeabi-v7a`, `x86`, and `x86_64`.
- Gradle result: 155 tasks, 126 executed, 29 up-to-date, `BUILD SUCCESSFUL`.
- Existing upstream warnings were limited to Android plugin/manifest deprecations and mbedTLS macro redefinitions.

The signed `assembleNormalRelease` and `assembleAarch64Release` builds, signer/provenance checks, actionlint, final diff checks, and public two-asset verification remain Stage 2 gates in the existing nightly workflow.
