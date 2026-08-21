from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LinuxPackagingTests(unittest.TestCase):
    def test_installer_includes_application_metadata(self):
        source = (ROOT / "packaging/linux/install_crystengkit_orca.sh").read_text(encoding="utf-8")
        self.assertNotIn('if item.name == "app_metadata"', source)

    def test_git_attributes_enforce_unix_line_endings(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertRegex(attributes, r"(?m)^\*\.sh\s+text eol=lf$")
        self.assertRegex(attributes, r"(?m)^\*\.command\s+text eol=lf$")


if __name__ == "__main__":
    unittest.main()
