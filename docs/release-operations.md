# Release Operations

## Release contract

`.github/workflows/config-hierarchy-nightly.yml` checks the official Libretro Android nightly archive every 30 minutes. It does nothing until both dated APKs exist. The first completed date newer than `config-hierarchy/release-state.json` is processed, so a delayed or missed date is not skipped.

The initial state is deliberately seeded at the last completed pair present when the fork monitor was activated (`2026-08-09`). This prevents a new fork from trying to retroactively publish the archive backlog. After activation, every completed pair newer than that baseline is processed oldest-first, so temporary workflow downtime does not skip releases.

Both upstream APKs are fully downloaded, ZIP-tested, and inspected for the `retroarch_git_version` ELF symbol in every packaged ABI. The short revisions must match. When that revision resolves in `libretro/RetroArch`, the fork builds from the exact commit. When Libretro's APK names an unpublished commit, the fork builds from the current public `upstream/master` instead and records both revisions plus the non-exact match in the embedded provenance and release notes. Divergent APK revisions, an invalid public fallback, or a source rollback still stop publication.

After the first published fork nightly, the saved URL, ETag, Last-Modified value, content length, and SHA-256 identify both processed upstream APKs. Each heartbeat performs inexpensive HEAD checks against the last processed pair before selecting a new one. Changed remote identity stops the workflow for manual provenance review; an existing fork release is never silently replaced.

The maintained commits are rebased onto that proven source without conflict resolution. Assets, autoconfig profiles, databases, core info, overlays, filters, and shaders are extracted directly from the validated upstream normal APK before the fork build; this avoids independently drifting those bundled payloads.

The workflow builds `normalRelease` and `aarch64Release` in the same Gradle invocation. A successful prerelease contains exactly:

```text
YYYY-MM-DD-RetroArch.apk
YYYY-MM-DD-RetroArch_aarch64.apk
RetroArch.apk
RetroArch_aarch64.apk
```

The stable aliases are byte-identical to their dated counterparts.

## Permanent signer

The public certificate is committed at `config-hierarchy/signer-certificate.pem`. Its pinned SHA-256 is:

```text
BD8C473A9E1C8F3FB83EE4549AEDCFE43E77E6960118E75B7DB90A32F3640D12
```

The local private key is outside the repository at:

```text
D:\Keys\RetroArch-Config-Hierarchy\retroarch-config-hierarchy-release.p12
```

Its credentials are stored for the current Windows account in the DPAPI-protected `credentials.clixml` beside it. Neither file may be committed. Before enabling public releases, make a tested offline copy of the keystore and its credentials on separate storage. Losing this signer permanently breaks in-place updates for both package IDs.

Configure these GitHub Actions secrets:

- `RELEASE_KEYSTORE_BASE64`: base64 of the PKCS#12 keystore;
- `RELEASE_STORE_PASSWORD`;
- `RELEASE_KEY_ALIAS`: `retroarch-config-hierarchy`;
- `RELEASE_KEY_PASSWORD`.

The workflow checks every value and the keystore certificate before Gradle. Gradle has no release-to-debug-signing fallback. Missing or incorrect inputs fail before compilation.

## Transactional publication

The pipeline verifies the final signed APKs for archive integrity, package ID, ABI set, matching version name/code, monotonic version code, signature, pinned certificate, alignment, embedded fork revision, exact upstream provenance, and patch identity.

It then:

1. pushes the verified commit to a temporary staging ref;
2. creates a draft prerelease and uploads all four assets;
3. downloads all assets from GitHub and checks the complete name/hash manifest;
4. advances the maintained branch with force-with-lease;
5. publishes the draft as a prerelease and removes the staging ref.

An error deletes the draft/tag and staging ref. If the maintained branch had already advanced, cleanup restores the prior revision with force-with-lease. Historical published tags are never changed.

## Obtainium / ObtainX

Enable prereleases and use exactly one stable asset filter per installed package:

- `^RetroArch\.apk$` for `com.retroarch`;
- `^RetroArch_aarch64\.apk$` for `com.retroarch.aarch64`.

Do not match both dated and stable names, or the updater may see duplicate candidates. Both APKs use the same permanent certificate and the same monotonically increasing version code for a release.

## First AYN Thor transition

There is intentionally no migration or deployment script. Perform this once, manually, when the first verified release candidate exists:

1. Identify the installed official package and signer.
2. Quit RetroArch normally so save-on-exit completes.
3. With root, identify the actual active master config.
4. If `/storage/emulated/0/RetroArch/retroarch.cfg` exists, preserve it and review the difference manually. Otherwise copy the active config there. The fork also accepts `/storage/emulated/0/RetroArch/config/retroarch.cfg` as a migration fallback when the primary file is absent.
5. Verify source/destination byte count and SHA-256.
6. Inspect `rgui_config_directory`, `input_remapping_directory`, and `core_options_path`; move subordinate files only when an active private path is proven and separately reviewed.
7. Uninstall the official APK only after verification, then confirm the public config and hash survived.
8. Install the matching fork APK and verify package, version, and the pinned signer.
9. Launch normally, verify the runtime log names the public config, change and save a harmless setting, restart, and prove the same public file is authoritative.

After that signer transition, Obtainium or ObtainX performs ordinary in-place updates. The manual migration is not repeated.

## Upstream provenance fallback

Libretro's 2026-08-10 Android pair reports revision `31c4e00`, which is not present in the public source repository. Functional publication takes priority over waiting indefinitely: the monitor uses the full public `upstream/master` revision as the build source, while preserving the official APK hashes and APK-reported revision for auditability. It never labels this fallback as an exact source match.
