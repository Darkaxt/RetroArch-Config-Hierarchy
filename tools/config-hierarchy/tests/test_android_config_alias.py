import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLATFORM_UNIX = ROOT / "frontend/drivers/platform_unix.c"


class AndroidConfigAliasWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLATFORM_UNIX.read_text(encoding="utf-8")

    def test_config_extra_is_selected_after_storage_paths_are_derived(self):
        env = self.source[
            self.source.index("static void frontend_unix_get_env") :
            self.source.index("static void frontend_unix_deinit")
        ]

        self.assertIn("requested_config_path", env)
        self.assertIn("android_env_select_config_path", env)
        self.assertLess(
            env.index("android_env_derive_storage"),
            env.index("android_env_select_config_path")
        )

    def test_selector_has_exact_legacy_alias_and_custom_override_branches(self):
        selector = self.source[
            self.source.index("static void android_env_select_config_path") :
            self.source.index("bool test_permissions_android")
        ]

        self.assertIn("android_env_config_path_is_legacy_default", selector)
        self.assertIn("requested_config_path", selector)
        self.assertIn("is_play_store_build", selector)
        self.assertIn("RetroArch", selector)
        self.assertIn("retroarch.cfg", selector)

    def test_legacy_identity_uses_canonical_parent_and_exact_filename(self):
        identity = self.source[
            self.source.index("static bool android_env_config_path_is_legacy_default") :
            self.source.index("static void android_env_select_config_path")
        ]

        self.assertIn("path_resolve_realpath", identity)
        self.assertIn("path_basename", identity)
        self.assertIn('string_is_equal(path_basename(requested), "retroarch.cfg")', identity)


if __name__ == "__main__":
    unittest.main()
