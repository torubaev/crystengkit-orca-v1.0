import os
import sys
import tempfile
import unittest
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from TD_DFT.orca_calculation_workspace import orca_stage, output_summary, subprocess_environment


class TDDFTCalculationWorkspaceTests(unittest.TestCase):
    def test_builder_exposes_current_and_regenerated_input_providers(self):
        source = (ROOT / "tools" / "Orca_input" / "orca_input.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "get_tddft_global_context"
        )
        rendered = ast.unparse(method)
        self.assertIn("'current_input_provider': self.get_preview_text", rendered)
        self.assertIn("'input_provider': self.refresh_full_orca_input", rendered)
        self.assertIn("'active_job_provider': self.get_active_orca_job_status", rendered)

    def test_tddft_has_separate_setup_calculation_and_post_modes(self):
        source = (ROOT / "tools" / "TD_DFT" / "td_dft_module.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_set_ui_mode"
        )
        rendered = ast.unparse(method)
        self.assertIn("'calculation'", rendered)
        self.assertIn("getattr(self, 'calculation_sections', ())", rendered)

    def test_monitor_attaches_to_builder_active_job_provider(self):
        source = (ROOT / "tools" / "TD_DFT" / "orca_calculation_workspace.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "show_monitor"
        )
        rendered = ast.unparse(method)
        self.assertIn("self.active_job_provider()", rendered)
        self.assertIn("self.external_monitor = True", rendered)
        self.assertIn("self._poll()", rendered)

    def test_single_input_and_multi_job_actions_are_named_by_scope(self):
        workspace = (ROOT / "tools" / "TD_DFT" / "orca_calculation_workspace.py").read_text(encoding="utf-8")
        panel = (ROOT / "tools" / "TD_DFT" / "td_dft_module.py").read_text(encoding="utf-8")
        self.assertIn('text="Run this input"', workspace)
        self.assertIn('text="Start automated sequence..."', panel)
        self.assertNotIn('text="Run ORCA"', workspace)
        self.assertNotIn('text="Run complete workflow..."', panel)

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
