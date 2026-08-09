#!/usr/bin/env python3
"""Render the immutable metadata recorded in each fork prerelease."""


def render(metadata):
    assets = "\n".join(
        f"- `{name}`: `{digest}`" for name, digest in sorted(metadata["assets"].items())
    )
    return f"""# RetroArch Config Hierarchy nightly {metadata['nightly_date']}

This fork keeps an explicit caller-supplied `CONFIGFILE` authoritative. Ordinary non-Play launches use `/storage/emulated/0/RetroArch/retroarch.cfg`, with public-first, non-destructive migration from the alternate `RetroArch/config` path or app-specific storage.

- Upstream nightly: `{metadata['nightly_date']}`
- Exact upstream revision: `{metadata['upstream_revision']}`
- Fork release revision: `{metadata['fork_revision']}`
- Public-config patch revision: `{metadata['patch_revision']}`
- Fork signer SHA-256: `{metadata['signer_sha256']}`
- Version: `{metadata['version_name']}` (`{metadata['version_code']}`)
- Packages: `com.retroarch` and `com.retroarch.aarch64`
- ABIs: normal = `armeabi-v7a, arm64-v8a, x86, x86_64`; AArch64 = `arm64-v8a, x86_64`

## Asset SHA-256

{assets}

## One-time signer transition

The official RetroArch APK must be uninstalled before the first fork-signed installation. On the rooted AYN Thor, perform the manual configuration migration and hash verification from the repository design before uninstalling. Later releases update in place through Obtainium or ObtainX.
"""
