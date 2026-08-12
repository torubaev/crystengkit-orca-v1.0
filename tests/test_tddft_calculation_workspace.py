import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from TD_DFT.orca_calculation_workspace import orca_stage, output_summary, subprocess_environment


class TDDFTCalculationWorkspaceTests(unittest.TestCase):
    def test_stage_detection_uses_orca_markers(self):
        self.assertEqual(orca_stage("TD-DFT/TDA EXCITED STATES"), "TD-DFT excited states")
        self.assertEqual(orca_stage("ORCA TERMINATED NORMALLY"), "Finished normally")
        self.assertEqual(orca_stage("unrelated output"), "")

    def test_summary_reports_completion_energy_and_runtime(self):
        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as directory:
            output = Path(directory) / "job.out"
            output.write_text(
                "FINAL SINGLE POINT ENERGY     -123.456\n"
                "TOTAL RUN TIME: 0 days 0 hours 1 minutes 2 seconds\n"
                "ORCA TERMINATED NORMALLY\n",
                encoding="utf-8",
            )
            summary = output_summary(output)
        self.assertIn("Status: Normal termination", summary)
        self.assertIn("Final energy: -123.456", summary)
        self.assertIn("Runtime: 0 days 0 hours 1 minutes 2 seconds", summary)

    def test_subprocess_environment_prepends_orca_directory(self):
        executable = str(ROOT / "vendor" / "orca" / ("orca.exe" if os.name == "nt" else "orca"))
        environment = subprocess_environment(executable)
        self.assertEqual(Path(environment["PATH"].split(os.pathsep)[0]), Path(executable).resolve().parent)


if __name__ == "__main__":
    unittest.main()
