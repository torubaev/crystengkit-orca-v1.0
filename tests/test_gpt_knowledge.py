import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs" / "build_gpt_knowledge.py"
SPEC = importlib.util.spec_from_file_location("build_gpt_knowledge", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GPTKnowledgeTests(unittest.TestCase):
    def test_generated_bundle_contains_upload_manifest_files(self):
        output = ROOT / "docs" / "gpt_knowledge"
        manifest = (output / "UPLOAD_MANIFEST.md").read_text(encoding="utf-8")
        for number in range(1, 10):
            matches = list(output.glob(f"{number:02d}_*"))
            self.assertEqual(len(matches), 1)
            self.assertIn(matches[0].name, manifest)

    def test_structured_knowledge_is_valid_and_contains_primary_features(self):
        output = ROOT / "docs" / "gpt_knowledge"
        settings = json.loads((output / "07_SETTINGS_AND_DEFAULTS.json").read_text(encoding="utf-8"))
        version = json.loads((output / "09_VERSION_AND_FEATURES.json").read_text(encoding="utf-8"))
        with (output / "08_FEATURE_CAPABILITY_MATRIX.csv").open(encoding="utf-8", newline="") as handle:
            features = {row["feature"] for row in csv.DictReader(handle)}
        self.assertTrue(settings["tddft"]["do_nto"])
        self.assertIn("TD-DFT", version["tools"])
        self.assertIn("Named job queues", features)
        self.assertIn("AI progress assistance", features)

    def test_builder_is_deterministic_and_uses_editorial_tmp_manual(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            with mock.patch.object(MODULE, "OUTPUT", output):
                MODULE.build()
            manual = (output / "01_USER_MANUAL.md").read_text(encoding="utf-8")
            self.assertIn("Job queues and AI progress assistance", manual)
            self.assertIn("Emission and NTO analysis", manual)
            self.assertNotIn("IMAGE PLACEHOLDER", manual)
            self.assertFalse(manual.startswith("---"))


if __name__ == "__main__":
    unittest.main()
