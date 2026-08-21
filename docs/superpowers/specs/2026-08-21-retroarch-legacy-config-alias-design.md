# RetroArch Legacy Default Config Alias Design

**Date:** 2026-08-21
**Status:** Implemented and source-validated; publication pending
**Repository:** `Darkaxt/RetroArch-Config-Hierarchy`

## Purpose

RetroArch Config Hierarchy makes `/storage/emulated/0/RetroArch/retroarch.cfg` the authoritative master configuration for ordinary non-Play Android launches. The original design also preserved every non-empty Android `CONFIGFILE` argument unchanged.

Live AYN Thor evidence exposed an interoperability gap. A stock-oriented external launcher can pass RetroArch's own legacy app-specific default path, `/storage/emulated/0/Android/data/<package>/files/retroarch.cfg`, as an explicit argument. RetroArch then maintains two independent master files. Settings and credentials saved through one launch path are invisible to the other.

The legacy app-specific default is not a meaningful user-selected override for this fork. It is a compatibility artifact. The fork will treat that one path as an alias of the public master while retaining genuine custom configuration arguments.

This design supplements and narrows the explicit-override rule in `2026-08-10-retroarch-config-hierarchy-design.md`.

## Goals

- Use one authoritative non-Play master configuration for ordinary launches and stock-oriented external launchers.
- Preserve caller-selected custom `CONFIGFILE` paths.
- Avoid copying, timestamps, bidirectional synchronization, merge rules, or credential-specific behavior.
- Keep Google Play flavor behavior unchanged.
- Keep the patch small enough to rebase over upstream Android nightlies.

## Non-Goals

- Removing support for arbitrary explicit configs.
- Redirecting per-core, per-game, directory, removable-storage, or user-created configs.
- Deleting or rewriting an existing legacy app-specific file.
- Synchronizing settings between unrelated configs.
- Changing native `-c`, desktop, command-line, override, remap, or core-option behavior.
- Adding RetroAchievements-specific logic.

## Selection Rule

For a non-Play Android build, resolve the active master config as follows:

1. Let the native Android environment resolver derive the shared storage root after startup permission handling.
2. If `CONFIGFILE` is absent or empty, use the public default.
3. If `CONFIGFILE` identifies the exact legacy app-specific default returned by `Context.getExternalFilesDir(null)/retroarch.cfg`, use the public default instead.
4. Otherwise, preserve the explicit path unchanged and do not invoke default migration or initialization.

Upstream removed the Java launcher on 2026-08-21 and moved its absent-argument config policy into `frontend/drivers/platform_unix.c`. That upstream resolver now defines `retroarch.cfg` as the Android master filename, so the maintained patch follows the native policy instead of resurrecting the removed Java preference layer.

Play Store builds do not apply the alias because their app-specific file remains their supported default.

## Path Identity

Path comparison must recognize equivalent Android spellings such as `/sdcard/...` and `/storage/emulated/0/...` when the platform resolves them to the same file. It must not use a substring, package-name-only, parent-directory-only, or filename-only match.

The resolver requires the exact `retroarch.cfg` basename and compares the requested parent with `Context.getExternalFilesDir(null)` after canonical symlink resolution. Canonicalizing the parent makes the identity check work even when the config file itself does not yet exist. If either parent cannot be canonicalized, the resolver fails safe by preserving the explicit argument.

No symbolic links are created or required.

## Data Flow

The native Android environment pass performs selection once, after storage derivation and before assigning `args->config_path`:

```text
incoming CONFIGFILE
        |
        +-- empty ------------------------------> public default
        |
        +-- exact legacy app-default (non-Play) -> public default
        |
        +-- every other explicit path ----------> explicit path
```

The selected path becomes `args->config_path` exactly once. Existing native save behavior then writes Save Current Configuration and save-on-exit changes to that selected file.

The inactive app-specific file is left untouched. It is neither a mirror nor a fallback after the public config exists.

## Failure Behavior

- Failure to initialize or access the public default remains visible under the existing configuration-error behavior.
- Failure to canonicalize a comparison path preserves the explicit config.
- A missing app-specific legacy file does not matter; identity is based on the known default location, not current file existence.
- A null app-specific external directory disables the compatibility alias and preserves explicit arguments.
- No copy or partial synchronization can occur, so there are no synchronization temporary files or conflict states.

## Tests

Regression tests and builds must prove:

1. absent and empty explicit paths select the public default;
2. the exact legacy app-specific default selects the public default on non-Play builds;
3. an equivalent canonical spelling of that legacy path selects the public default;
4. a custom config beside the legacy default remains explicit;
5. a same-named config elsewhere remains explicit;
6. the public path supplied explicitly remains public;
7. canonicalization failure preserves the explicit path;
8. a null legacy directory preserves explicit paths;
9. Play policy retains the app-specific default;
10. selection occurs after native storage derivation and before `args->config_path` assignment.

Source-boundary tests enforce native ordering, the exact basename/canonical-parent identity rule, and the custom/Play branches. Regression verification includes the complete config-hierarchy suite, Java compilation for published and Play variants, a native four-ABI normal build, `git diff --check`, actionlint, and both signed Android release APK builds through the existing publication workflow.

## Device Acceptance

After a fork nightly containing the change is installed on the Thor:

1. a direct icon launch uses `/storage/emulated/0/RetroArch/retroarch.cfg`;
2. a CocoonShell launch that supplies the legacy app-specific default also uses the public file;
3. a harmless saved setting persists across both launch routes;
4. a deliberately custom `CONFIGFILE` remains independent;
5. the legacy app-specific file remains byte-identical throughout the checks;
6. a fresh RetroAchievements login produces one token in the public master and remains valid across both launch routes.

## Release Integration

The change is part of the maintained Android patch stack. The next completed upstream nightly is rebuilt, signed with the permanent fork identity, verified under the existing two-asset contract, and published without creating a duplicate release solely for testing.
