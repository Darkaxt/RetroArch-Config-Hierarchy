# Stage 1 Validation: Settings Behavior

Validated against `docs/superpowers/specs/2026-08-10-retroarch-config-hierarchy-design.md` on 2026-08-10.

## Automated evidence

- `gradlew.bat testNormalDebugUnitTest`: passed 13 tests, 0 failures, 0 errors.
- `gradlew.bat compilePlayStoreNormalReleaseJavaWithJavac compilePlayStorePlusReleaseJavaWithJavac`: passed.
- `gradlew.bat assembleNormalRelease assembleAarch64Release`: passed in one invocation (107 tasks) and produced both APKs.
- Normal release APK: 26,277,059 bytes.
- AArch64 release APK: 13,494,022 bytes.

The initial TDD run failed at `compileNormalDebugUnitTestJavaWithJavac` because `ActiveConfigPath` and `ConfigPathPolicy` did not exist. The same focused task passed after implementation.

## Specification trace

| Design requirement | Implementation and evidence | Status |
| --- | --- | --- |
| Ordinary non-Play launch selects `/storage/emulated/0/RetroArch/config/<config>` | `UserPreferences.resolveDefaultConfig()` selects the public policy and `MainMenuActivity.finalStartup()` passes the result as `CONFIGFILE`. | Code and build validated |
| Explicit non-empty `CONFIGFILE` remains authoritative | `ActiveConfigPath.select()` bypasses its default provider; `MainMenuActivity` preserves an incoming value and `RetroActivityFuture` uses the active intent for Java-side reads. Three focused tests cover present, empty, and absent values. | Automated |
| Existing public config wins and migration never replaces it | `ConfigPathPolicy` checks the destination before source selection and again inside its publication lock. The public-precedence and concurrent-publisher tests pass. | Automated |
| Legacy migration is byte-for-byte, ordered external then internal then fallback | Migration copies raw bytes, flushes and syncs, verifies size and SHA-256, and publishes a same-directory temporary file. Binary and source-order tests pass. | Automated |
| Fresh initialization occurs only after storage permission | The eager `onCreate()` update was removed. Non-Play initialization now occurs only in `finalStartup()`, reached after permission; a duplicate-start guard prevents a second launch. | Code and build validated; device permission UI pending |
| Failures are visible, with no misleading private fallback | Resolver/write failures throw; `MainMenuActivity` logs and displays a blocking configuration error instead of launching. Publication-failure test passes. | Automated/code validated |
| `getExternalFilesDir(null)` may be null | The resolver accepts null legacy locations; the null-external test proves internal migration still works. | Automated |
| Play flavors retain app-specific storage | `BuildConfig.PLAY_STORE_BUILD` selects `APP_SPECIFIC`; the policy test and both Play release Java compilations pass. | Automated |
| Per-core filenames follow the same hierarchy | Existing `global_config_enable` and core-name derivation remain, with only the destination policy changed. | Code validated |
| Native config, override, core-option, and remap semantics remain unchanged | No native C/C++ files or subordinate config-directory logic changed. | Diff validated |
| No reusable Thor migration script | None was added; the design's manual checklist remains authoritative. | Diff validated |

## Deferred device gates

The following acceptance checks require the first manually prepared Thor deployment and are intentionally not claimed by this source/build validation:

- runtime log proves the public master path is active;
- Save Current Configuration and save-on-exit modify that active public file;
- external edits are observed after restart;
- active override, core-option, and remap paths work with the migrated real configuration;
- the verified public config survives official-signer uninstall and the fork-signer install.

These gates belong immediately before the first public prerelease, after the manual rooted migration described in the specification.
