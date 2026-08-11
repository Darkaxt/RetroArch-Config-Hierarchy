# Two-Asset Release Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish only the stable normal and AArch64 APK names in future nightly releases.

**Architecture:** Build and verify both APKs under their final stable names, generate a manifest containing exactly those two files, upload only those files, and re-download them before publishing the draft. The dated tag and release notes remain the upstream-nightly identity.

**Tech Stack:** GitHub Actions YAML, Python release helpers and `unittest`, actionlint, GitHub Releases.

---

### Task 1: Lock the two-asset contract with failing tests

**Files:**
- Modify: `tools/config-hierarchy/tests/test_nightly_pipeline.py`

- [ ] Add `test_release_manifest_contains_only_stable_assets`:

```python
def test_release_manifest_contains_only_stable_assets(self):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        (directory / "RetroArch.apk").write_bytes(b"normal")
        (directory / "RetroArch_aarch64.apk").write_bytes(b"aarch64")
        (directory / "2026-08-10-RetroArch.apk").write_bytes(b"noise")
        self.assertEqual(
            {"RetroArch.apk", "RetroArch_aarch64.apk"},
            set(run_release.prepare_release_assets(directory)),
        )
```

- [ ] Add workflow contract assertions:

```python
self.assertIn('"$release_dir/RetroArch.apk"', publication)
self.assertIn('"$release_dir/RetroArch_aarch64.apk"', publication)
self.assertNotIn('"$release_dir/${date}-RetroArch.apk"', publication)
self.assertNotIn('"$release_dir/${date}-RetroArch_aarch64.apk"', publication)
```
- [ ] Run `python -m unittest tools.config-hierarchy.tests.test_nightly_pipeline` and confirm failure because `prepare_release_assets` and the two-asset workflow do not exist yet.

### Task 2: Implement the stable-only manifest and workflow

**Files:**
- Modify: `tools/config-hierarchy/run_release.py`
- Modify: `tools/config-hierarchy/verify_release.py`
- Modify: `.github/workflows/config-hierarchy-nightly.yml`
- Modify: `tools/config-hierarchy/tests/test_nightly_pipeline.py`

- [ ] Replace alias creation with:

```python
def prepare_release_assets(directory):
    directory = Path(directory)
    assets = (directory / "RetroArch.apk", directory / "RetroArch_aarch64.apk")
    return {path.name: sha256(path) for path in assets}
```
- [ ] Replace the `aliases` CLI command with `release-assets --directory` and remove the now-unused alias verifier.
- [ ] Copy Gradle outputs directly to `RetroArch.apk` and `RetroArch_aarch64.apk`, verify those paths, run `release-assets --directory "$release_dir"`, and pass only these upload arguments:

```bash
"$release_dir/RetroArch.apk" \
"$release_dir/RetroArch_aarch64.apk"
```
- [ ] Re-run the focused tests and confirm they pass.

### Task 3: Align operations documentation and automation

**Files:**
- Modify: `docs/release-operations.md`
- Modify: `docs/validation/2026-08-10-stage-2-publication-pipeline.md`
- Update: Codex automation `retroarch-nightly-pipeline-health-review`

- [ ] State that future releases contain two stable APKs and that the inaugural four-asset release remains historical evidence.
- [ ] Update the weekly health task to expect exactly two stable assets.

### Task 4: Verify and deploy

**Files:**
- Verify all modified files.

- [ ] Run `python -m unittest discover -s tools/config-hierarchy/tests -p 'test_*.py'` and require zero failures.
- [ ] Run `D:\Tools\actionlint-1.7.12\actionlint.exe .github/workflows/config-hierarchy-nightly.yml` and `git diff --check`.
- [ ] Commit and push the change to `main`.
- [ ] Dispatch the workflow and verify either a clean no-op when no new upstream pair exists or a public two-asset release when one does.
- [ ] Remove the temporary worktree under `D:\Temp` after remote verification.
