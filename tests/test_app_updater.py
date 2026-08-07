from __future__ import annotations

import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ORCA_INPUT = ROOT / "tools" / "Orca_input"
import sys

if str(ORCA_INPUT) not in sys.path:
    sys.path.insert(0, str(ORCA_INPUT))

import app_updater


class ApplicationUpdaterTests(unittest.TestCase):
    def test_release_selector_requires_exact_versioned_web_installer_and_digest(self):
        payload = {
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/torubaev/crystengkit-orca-v1.0/releases/tag/v1.2.3",
            "assets": [
                {
                    "name": "CrystEngKit-ORCA-Setup-1.2.3-web.exe",
                    "browser_download_url": "https://github.com/torubaev/crystengkit-orca-v1.0/releases/download/v1.2.3/installer.exe",
                    "digest": "sha256:" + "a" * 64,
                }
            ],
        }
        selected = app_updater.select_release_installer(payload)
        self.assertEqual(selected.version, "1.2.3")
        self.assertEqual(selected.sha256, "a" * 64)

    def test_release_selector_accepts_named_checksum_asset(self):
        name = "CrystEngKit-ORCA-Setup-2.0.0-web.exe"
        selected = app_updater.select_release_installer(
            {
                "tag_name": "2.0.0",
                "assets": [
                    {"name": name, "browser_download_url": "https://github.com/x/y/installer.exe"},
                    {"name": name + ".sha256", "browser_download_url": "https://github.com/x/y/checksum"},
                ],
            }
        )
        self.assertTrue(selected.sha256.startswith("url:https://github.com/"))

    def test_release_selector_rejects_unverified_or_wrong_asset(self):
        with self.assertRaisesRegex(ValueError, "expected web installer"):
            app_updater.select_release_installer({"tag_name": "1.2.3", "assets": []})
        with self.assertRaisesRegex(ValueError, "no GitHub SHA-256"):
            app_updater.select_release_installer(
                {
                    "tag_name": "1.2.3",
                    "assets": [
                        {
                            "name": "CrystEngKit-ORCA-Setup-1.2.3-web.exe",
                            "browser_download_url": "https://github.com/x/y/installer.exe",
                        }
                    ],
                }
            )

    def test_development_checkout_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.assertFalse(app_updater.is_development_checkout(root))
            (root / ".git").mkdir()
            self.assertTrue(app_updater.is_development_checkout(root))

    def test_web_installer_is_a_verified_inno_bootstrapper(self):
        source = (ROOT / "packaging" / "windows" / "CrystEngKitInstaller.cs").read_text(encoding="utf-8")
        for required in (
            "FindExistingInstallation",
            "PackageUrl",
            "PackageSha256",
            "DownloadVerifiedPackage",
            "SHA256.Create()",
            "UseShellExecute = true",
        ):
            self.assertIn(required, source)
        self.assertNotIn("ExtractRepositoryToInstall", source)

        builder = (ROOT / "packaging" / "windows" / "build_web_installer.ps1").read_text(encoding="utf-8")
        self.assertIn("Build the full Inno installer first", builder)
        self.assertIn("$fullInstallerHash", builder)
        self.assertIn("__PACKAGE_SHA256__", builder)

    def test_windows_launcher_prefers_managed_environment(self):
        launcher = (ROOT / "packaging" / "windows" / "launch_orca_builder.cmd").read_text(encoding="utf-8")
        venv_position = launcher.find('.venv\\Scripts\\pythonw.exe')
        global_position = launcher.find('where pyw.exe')
        self.assertGreaterEqual(venv_position, 0)
        self.assertGreater(global_position, venv_position)


if __name__ == "__main__":
    unittest.main()
