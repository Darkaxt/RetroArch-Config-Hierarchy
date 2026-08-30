# RetroArch Config Hierarchy Design

> **Implementation architecture update (2026-08-21):** Upstream removed the Java launcher and moved Android config derivation into `frontend/drivers/platform_unix.c`. The maintained fork now implements the public master and exact legacy-default alias there, with no runtime migration or copying. The current behavior contract is `2026-08-21-retroarch-legacy-config-alias-design.md`; Java launcher and automatic-migration sections below are retained as historical design context.

| Field | Decision |
| --- | --- |
| Project | RetroArch-Config-Hierarchy |
| Upstream | `libretro/RetroArch` |
| Platform | Android non-Play builds |
| Published variants | `normal` and `aarch64` |
| Distribution | GitHub prereleases consumed by Obtainium or ObtainX |
| Master configuration root | `/storage/emulated/0/RetroArch/` |
| Upstream alignment | Exact APK revision when public; otherwise a disclosed `upstream/master` fallback |

## Purpose

RetroArch-Config-Hierarchy is a minimal Android-focused overlay on upstream RetroArch. It makes the public Android configuration tree authoritative for ordinary user launches while preserving explicit `CONFIGFILE` overrides for launchers, companion applications, and other intentional integrations.

The fork follows upstream Android nightlies. It does not become an independently evolving RetroArch distribution. Each release is built from the exact RetroArch source revision identified in a completed upstream Android nightly when that revision is public. If the APK-reported revision is not public, or if every ABI in both APKs consistently omits the revision, the release uses the current full `upstream/master` revision and discloses the reported revision or `unavailable` plus the non-exact relationship. A small reviewed patch implements the public configuration hierarchy in either case.

## User Contract

For direct human interaction, the active master configuration is:

```text
/storage/emulated/0/RetroArch/retroarch.cfg
```

An explicit config argument remains stronger than the default policy:

```text
Explicit CONFIGFILE supplied
    -> use the supplied file unchanged

No explicit CONFIGFILE supplied
    -> public config exists: use it unchanged
    -> public config missing and legacy config exists:
         copy legacy config to public storage
         use the public copy
    -> neither exists:
         initialize the public config
         use it
```

After successful initialization, ordinary UI changes, Save Current Configuration, save-on-exit, Android-specific Java reads, and subsequent launches use the same public master file.

## Goals

- Make the public master `retroarch.cfg` authoritative for normal Android interaction.
- Preserve caller-supplied `CONFIGFILE` behavior.
- Migrate an existing default app-specific config without overwriting public user data.
- Keep Android Java-side config reads aligned with the active native config.
- Preserve upstream package identities and Android behavior outside this policy.
- Build and sign normal and AArch64 APKs with one permanent fork signer.
- Publish a fork release only after upstream has completed the corresponding Android nightly.
- Bind each fork nightly to its APK-reported revision, official APK hashes, selected public build revision, and exact/non-exact status.
- Fail without publishing when provenance, patch application, building, signing, or verification is uncertain.

## Non-Goals

- Reimplementing RetroArch's native configuration parser.
- Changing the semantics of native `-c` or Android `CONFIGFILE` overrides.
- Mirroring all private app data into shared storage.
- Migrating cores, assets, caches, databases, playlists, saves, states, thumbnails, or temporary files.
- Automatically merging arbitrary custom configuration directories.
- Changing core/game/directory override semantics.
- Changing `.opt` or `.rmp` path semantics.
- Supporting Google Play flavors with public-path behavior.
- Adding a self-updater to RetroArch.
- Automating the one-time rooted migration on the AYN Thor.
- Repairing or working around the historical Network Commands persistence bug already fixed upstream.

## Current Upstream Behavior

The Android launcher resolves its default config through `UserPreferences.getDefaultConfigPath()`. With external storage mounted, the resolver normally selects the application-specific external file returned beneath `Context.getExternalFilesDir(null)`. It does not consult the established public `RetroArch/retroarch.cfg` file.

The launcher passes that result to the native activity through `CONFIGFILE`. Native Android handling converts the value into RetroArch's config argument, which becomes the active `RARCH_PATH_CONFIG`. Android-side code also calls the default resolver directly for settings including display-cutout and automatic mouse-grab behavior.

Native Android defaults already place core/game/directory overrides under the public configuration tree for normal non-Play builds. Remaps default beneath its `remaps` subdirectory. The principal demonstrated inconsistency is therefore the master config resolver, not a universal private mirror of subordinate configuration files.

## Configuration Selection Architecture

### Explicit override

A non-empty `CONFIGFILE` supplied by the initiating caller is authoritative. The fork must not copy, redirect, normalize, replace, or rewrite that path as part of default resolution.

Code that already has access to the active Android intent must read this explicit value first. Android Java-side consumers must use the same active value as native RetroArch. They call the default resolver only when the intent does not contain a non-empty config path.

An explicit config may be public, app-specific, private, removable, or otherwise user-selected. Access failure is reported as a failure of that explicit selection; it does not trigger silent substitution with the public default.

### Ordinary launch

When no initiating caller supplies `CONFIGFILE`, the launcher resolves the default public config and passes the resolved path to native RetroArch. Passing this synthesized value through the intent is an implementation detail and does not turn it into an external override.

The policy applies to normal icon/menu launches and core-sideload launches. Existing per-core behavior associated with the legacy `global_config_enable` preference must not gain stronger precedence than an explicit caller argument. If retained, its derived filename follows the same public-first, non-destructive policy inside the public configuration directory.

### Public precedence

If the target public config exists, it is returned immediately and remains byte-for-byte untouched by migration. The presence of any legacy app-specific or private copy cannot replace it.

The resolver must distinguish these outcomes:

- public file selected successfully;
- legacy file migrated successfully;
- new public file initialized successfully;
- storage permission not yet available;
- public directory or file cannot be created;
- migration source cannot be read;
- migration destination cannot be published.

Once public initialization has been attempted with the required permission available, failure must be visible. The application must not continue using a newly created private config while presenting the public file as authoritative.

### Legacy source order

When the public file is missing, migration examines only known legacy locations for the same config filename:

1. alternate public `RetroArch/config/` directory;
2. application-specific external files directory;
3. internal files directory;
4. an existing platform fallback used by the current resolver, if still reachable and relevant at implementation time.

The first valid source is copied exactly. Migration does not parse the source through Android's `ConfigFile` map because doing so could discard comments, ordering, duplicate entries, quoting, or unknown syntax.

### Atomic migration

Migration creates the public parent directory, writes a uniquely named temporary file in that directory, flushes and closes it, verifies the copied length and content digest, and publishes it without overwriting an existing destination. A concurrent public-file creation wins; the migration discards its temporary candidate and selects the existing public file.

Temporary migration files are removed after success or handled failure. Existing public files are never renamed aside, replaced, or rewritten.

### Fresh initialization

When neither public nor legacy config exists, the launcher creates the public parent directory and initializes the same Android-specific values currently produced by `UserPreferences.updateConfigFile()`. Native compiled defaults continue to supply normal RetroArch defaults.

The initialization ordering must ensure that non-Play shared-storage access has been granted before the public file is created or updated. Returning from the Android all-files-access screen must resume initialization exactly once without launching native RetroArch against an uninitialized path.

### Play builds

Google Play flavors remove broad shared-storage permission and retain their current application-specific config behavior. Common code must choose the policy by build flavor rather than making the public path unconditional. Both Play flavors must continue to compile even though this fork does not publish them.

## Native and Subordinate Configuration Boundaries

The native configuration parser and `RARCH_PATH_CONFIG` saving behavior remain unchanged. Once the launcher passes the public path, existing native behavior naturally makes Save Current Configuration and save-on-exit target that file.

The setting exposed as Configuration Files is serialized as `rgui_config_directory`. Existing behavior remains:

- core/game/directory `.cfg` overrides derive from the configured application config directory;
- per-core/game/folder `.opt` files derive from that directory;
- global core options may use `core_options_path` or a file beside the active master config;
- `.rmp` files use the independent `input_remapping_directory`;
- bundled resources and controller autoconfig defaults may remain application-specific.

The fork does not invent a generic internal-to-public fallback for these categories. A later change requires evidence of a specific private-path leak and a separately reviewed migration rule.

## Expected Patch Boundary

The implementation should remain within the modern Android launcher and common preference code unless tests prove another call path is required. The expected functional surface is:

- `UserPreferences.java`: default-path policy, migration and initialization result;
- modern `MainMenuActivity.java`: permission-aware initialization and preservation of an incoming explicit config;
- modern `RetroActivityFuture.java`: active-intent config for Java-side reads;
- focused tests and test fixtures;
- GitHub Actions and small release/provenance helpers.

Legacy and Jelly Bean source trees are changed only if the maintained build actually compiles them or a shared-code change would otherwise leave them inconsistent. Native C configuration code is excluded unless source-level evidence invalidates the Java-only design.

## One-Time Rooted Thor Migration

The initial transition from the official signer to the fork signer is performed manually when the first release candidate is ready. It is not implemented as a reusable script or CI stage.

The manual operation must satisfy this gate before uninstalling the official APK:

1. Identify the installed RetroArch package and signer on the Thor.
2. Let RetroArch quit normally so save-on-exit completes.
3. Use root access to identify the actual active master config rather than selecting a candidate by modification time.
4. If the public destination already exists, preserve it and review the difference manually.
5. Otherwise copy the active config byte-for-byte to the canonical public destination.
6. Verify source and destination size and SHA-256.
7. Inspect `rgui_config_directory`, `input_remapping_directory`, and `core_options_path`; migrate subordinate files only if a proven active path is private and only after a separate manual review.
8. Uninstall the official APK only after the public copy passes verification.
9. Confirm the public config and its hash survived uninstall.
10. Install the fork release and verify its package, signer and version.
11. Launch normally and confirm the runtime log names the public config as active.
12. Change and save a harmless setting, restart, and confirm the public file is the effective persistent config.

No extra backup tree is created merely for caution. The verified public copy is the migration artifact. If any pre-uninstall check fails, deployment stops without removing the official application.

After this one-time signer transition, Obtainium or ObtainX performs normal in-place updates. Later nightly installations do not repeat private-data migration.

## Upstream Nightly Monitor

GitHub Actions cannot receive a completion webhook from the Libretro buildbot, so a scheduled monitoring heartbeat inspects the upstream Android nightly archive. The heartbeat does not initiate builds merely because a date changed or `master` advanced.

For each unprocessed upstream date, readiness requires both dated files:

```text
YYYY-MM-DD-RetroArch.apk
YYYY-MM-DD-RetroArch_aarch64.apk
```

The monitor handles delayed and missed dates by considering completed dates newer than the last processed upstream nightly, not only the current calendar date. A partial pair is left pending for a later heartbeat.

A full, structurally valid download is the completion check. Truncated or changing upstream files fail the current heartbeat and are retried later; they do not create a failed release record.

## Upstream Provenance and Public-Source Fallback

Both upstream APKs are inspected for their embedded RetroArch Git revision. The pipeline requires:

- both APKs and all their native ABIs either report the same revision or consistently omit it;
- mixed revision availability or divergent reported revisions fail closed;
- the revision is not older than the previously released upstream baseline unless manually approved;
- the upstream APK filenames match the nightly date being processed.

If the reported revision resolves unambiguously in `libretro/RetroArch`, that exact full commit is the required build base. If it does not resolve publicly, or both APKs consistently omit it, the only permitted fallback is the current full `upstream/master` commit. The pipeline embeds and publishes the APK-reported revision or `unavailable`, official APK hashes, selected full build revision, and `upstream_revision_exact: false`; it never presents the fallback as an exact reconstruction of the official APK source.

If extraction becomes incompatible with upstream packaging in any other way, the pipeline stops before patching or publishing. Repairing provenance extraction is a reviewed maintenance change.

## Patch Stack and Branch Model

The maintained branch is a short patch stack over the last released upstream nightly revision:

```text
upstream nightly source commit
+ Android public config hierarchy patch
+ fork automation and documentation
```

For a new nightly, automation rebases or reapplies the maintained commits onto the proven upstream revision in an isolated checkout. Semantic conflicts are never resolved automatically. The maintained branch advances only after patch application, tests, both release builds and all artifact checks succeed.

The released tag identifies the exact patched commit. Historical release tags remain immutable even though the maintained branch is rebased for later upstream revisions.

## Build and Signing

The workflow builds `normalRelease` and `aarch64Release` in one Gradle invocation so both artifacts share the same configured timestamp-derived version code. It reuses upstream Android Gradle and NDK configuration.

One permanent fork-owned release key signs both package identities:

```text
normal  -> com.retroarch
aarch64 -> com.retroarch.aarch64
```

The keystore and credentials are supplied through encrypted GitHub secrets. A recoverable offline copy is mandatory. The public certificate SHA-256 is committed to the repository and is not secret.

The workflow must fail before Gradle if any release-signing input is absent. It must not permit upstream's debug-signing fallback for release builds.

## Artifact Verification

Both APKs must pass before either is published. Verification requires:

- expected application ID;
- expected flavor and upstream-defined ABI set;
- identical version name and version code across the pair;
- version code greater than the previous fork release;
- valid APK signing block and certificate chain;
- certificate SHA-256 equal to the pinned fork signer;
- no debug certificate;
- successful zip-alignment verification;
- expected embedded fork release Git revision;
- release provenance identifies the selected full upstream build revision, APK-reported revision, official APK hashes, and exact/non-exact status;
- expected fork patch identity;
- successful archive integrity test;
- successful Android build and relevant automated tests.

The pipeline records SHA-256 for every published asset. Verification reads the final release APKs, not unsigned intermediates.

## GitHub Release Contract

Each successful upstream nightly creates one immutable GitHub prerelease with a dated fork tag. The release contains:

```text
RetroArch.apk
RetroArch_aarch64.apk
```

The two stable asset names provide predictable Obtainium and ObtainX filters. The dated release tag and release notes preserve correspondence with upstream without uploading byte-identical dated duplicates.

The release is assembled as a GitHub draft. Both assets are uploaded, downloaded again, and checked against the final hashes before the draft is published as a prerelease. An incomplete draft is not user-visible and is removed or retained privately for diagnosis rather than promoted.

Release notes record:

- upstream nightly date;
- selected upstream full Git revision and APK-reported revision;
- whether the APK/source match is exact;
- fork release commit;
- public-config patch revision;
- fork signer fingerprint;
- package IDs, versions and ABI sets;
- SHA-256 for all assets;
- build and verification results;
- a concise description of the fork's configuration behavior;
- the one-time signer-transition warning.

Obtainium and ObtainX must be configured to include prereleases and select exactly one stable alias appropriate for the device.

An upstream date/revision pair already released is idempotently ignored. If upstream replaces an already processed dated APK with different content, automation does not overwrite the existing release; it stops for manual provenance review.

## Failure Semantics

The pipeline publishes nothing and leaves the maintained branch and last good release unchanged when any of these occur:

- incomplete upstream artifact pair;
- invalid upstream APK;
- mixed, invalid, or divergent embedded Git revision evidence;
- upstream revision rollback;
- patch conflict;
- source or dependency build failure;
- unit or integration test failure;
- missing signing secret;
- debug or unexpected signer;
- mismatched package, version, ABI or provenance;
- only one fork variant succeeds;
- GitHub release upload is incomplete.

The workflow exposes the failing stage in GitHub Actions. It does not silently switch source revisions or auto-resolve semantic conflicts. If both upstream APKs agree on an embedded revision that is not public, it may build from the current full `upstream/master` commit only when the APK-reported revision, selected build revision, non-exact status, and official APK hashes are embedded and published in the release provenance.

## Test Strategy

### Resolver tests

- Explicit non-empty `CONFIGFILE` wins over public and legacy files.
- Empty or absent explicit value invokes default resolution.
- Existing public config wins and remains byte-identical.
- Missing public plus legacy external config copies and selects public.
- Missing public and external plus legacy internal config copies and selects public.
- No existing config initializes public storage.
- Concurrent public creation never gets overwritten.
- Copy or publication failure is visible and leaves no authoritative partial file.
- A stale temporary migration file cannot replace public data.
- `getExternalFilesDir(null)` returning null is handled.
- Play flavor retains app-specific behavior.

### Android integration tests

- Fresh non-Play installation requests storage access before public initialization.
- Permission grant resumes initialization and launches successfully.
- Permission denial does not create a misleading private authority.
- Normal launcher passes the public config.
- Core sideload without explicit config passes the public config.
- Explicit external launch uses the caller path.
- Java notch and mouse-grab reads follow the explicit active path.
- Save Current Configuration changes the active public master file.
- Save-on-exit persists to the active public master file.
- External modification while stopped is observed after restart.
- Public data is not overwritten by an application version or asset update.
- Play variants compile and retain existing storage behavior.

### Configuration-boundary tests

- Existing `rgui_config_directory` remains honored.
- Existing `input_remapping_directory` remains honored.
- Existing `core_options_path` remains honored.
- Core/game/directory overrides continue to load and save normally.
- Core options and remaps continue to load and save normally.
- Bundled asset extraction remains private and completes after an application update.
- Network Commands persist on a source revision containing upstream's `HAVE_COMMAND` fix.

### Pipeline tests

- Partial upstream nightly does not trigger a build.
- Completed normal and AArch64 pair triggers once.
- Missed completed dates are discovered on a later heartbeat.
- Divergent embedded upstream revisions block publication.
- Consistent revision omission across both APKs selects the disclosed public fallback.
- Mixed embedded-revision availability blocks publication.
- Repeated heartbeat for a released date is a no-op.
- Patch conflict blocks branch advancement.
- Missing signing inputs fail before build publication.
- Deliberately wrong signer, package, ABI or version blocks publication.
- The release manifest contains exactly the two stable APK names.
- Obtainium/ObtainX can identify a newer version code and install over the prior fork build.

## Acceptance Criteria

The project is ready for its first public prerelease when all of the following are true:

1. A normal human launch uses the public master config.
2. A caller-supplied `CONFIGFILE` remains fully functional in native and Android Java behavior.
3. Existing public config always wins and is never overwritten by migration or update.
4. A legacy default config migrates byte-for-byte when public config is absent.
5. Fresh initialization succeeds only after required storage access is available.
6. Save Current Configuration and save-on-exit update the proven active public file.
7. Existing override, core-option and remap behavior remains functional.
8. Play variants retain their current app-specific policy and compile successfully.
9. The workflow waits for both upstream Android nightly variants.
10. The build base equals the revision embedded in both upstream APKs when it is public; otherwise the release uses the current full `upstream/master` revision and discloses the reported revision or `unavailable`, official APK hashes, and non-exact status.
11. Both fork variants are built in one release run and pass all signer, package, ABI, version, alignment, integrity and provenance checks.
12. The GitHub prerelease contains exactly `RetroArch.apk` and `RetroArch_aarch64.apk`; the tag and notes carry the upstream date.
13. The manually migrated Thor config survives official-app uninstall and becomes the proven active config in the first fork installation.
14. The next fork nightly installs in place through Obtainium or ObtainX without another migration or uninstall.

## Maintenance Policy

Upstream changes are accepted automatically only when the patch applies cleanly and every test and artifact gate passes. A conflict is evidence that the affected Android behavior must be reviewed, not an inconvenience to bypass.

The fork should remain small enough that its behavior can be described as current RetroArch Android nightly plus a public-first default configuration hierarchy. Any feature outside that description requires a separate design decision.

## Primary References

- [RetroArch Android default config resolver](https://github.com/libretro/RetroArch/blob/master/pkg/android/phoenix-common/src/com/retroarch/browser/preferences/util/UserPreferences.java)
- [RetroArch modern Android launcher](https://github.com/libretro/RetroArch/blob/master/pkg/android/phoenix/src/com/retroarch/browser/mainmenu/MainMenuActivity.java)
- [RetroArch Android Java-side config reads](https://github.com/libretro/RetroArch/blob/master/pkg/android/phoenix/src/com/retroarch/browser/retroactivity/RetroActivityFuture.java)
- [RetroArch Android Gradle build and signing configuration](https://github.com/libretro/RetroArch/blob/master/pkg/android/phoenix/build.gradle)
- [RetroArch Android nightly archive](https://buildbot.libretro.com/nightly/android/)
- [Android all-files access](https://developer.android.com/training/data-storage/manage-all-files)
- [Android app-specific storage lifecycle](https://developer.android.com/training/data-storage/app-specific)
