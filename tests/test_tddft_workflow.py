import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from TD_DFT.workflow.config import (  # noqa: E402
    ExcitedStatesConfig, FrequencyConfig, MethodConfig, OrcaConfig,
    SystemConfig, WorkflowConfig, load_config, save_config, write_example_config,
)
from TD_DFT.workflow.engine import WorkflowEngine, WorkflowError  # noqa: E402
from TD_DFT.workflow.models import method_signature  # noqa: E402
from TD_DFT.workflow.orca import (  # noqa: E402
    generate_input, geometry_converged, imaginary_frequencies,
    normal_termination, validate_output,
)
from TD_DFT.workflow.scheduler import build_dependency_submit_script, dependency_order  # noqa: E402
from TD_DFT.workflow.importer import inspect_external_workflow_source  # noqa: E402


XYZ = """2
test
H 0 0 0
H 0 0 0.7
"""

OPT_OUT = """FINAL SINGLE POINT ENERGY -1.234
THE OPTIMIZATION HAS CONVERGED
CARTESIAN COORDINATES (ANGSTROEM)
---------------------------------
H 0.0 0.0 0.0
H 0.0 0.0 0.8

ORCA TERMINATED NORMALLY
"""

TD_OUT = """STATE 1: E= 0.100 au 2.5000 eV 495.94 nm f=0.4
ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
1 20163.9 495.94 0.4000
ORCA TERMINATED NORMALLY
"""


def config(initial):
    return WorkflowConfig(
        system=SystemConfig("mol", 0, 1, str(initial)),
        orca=OrcaConfig("orca", "6.0.1"),
        method=MethodConfig("CAM-B3LYP", "def2-SVP", "def2/J", "D3BJ"),
        excited_states=ExcitedStatesConfig(use_tda=True, nroots=5, target_root=1),
        frequency=FrequencyConfig(enabled=False),
    )


class StrictTDDFTWorkflowTests(unittest.TestCase):
    def test_external_s0_optimization_is_detected_and_can_be_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "old_s0.out"; inp = root / "old_s0.inp"; gbw = root / "old_s0.gbw"
            out.write_text("Program Version 6.0.1\n" + OPT_OUT, encoding="utf-8")
            inp.write_text("! CAM-B3LYP def2-SVP def2/J RIJCOSX D3BJ TightSCF DefGrid2 Opt\n* xyz 0 1\nH 0 0 0\nH 0 0 .8\n*\n", encoding="utf-8")
            gbw.write_bytes(b"gbw")
            source = inspect_external_workflow_source(str(out), orca_executable="orca", frequency_enabled=False)
            self.assertEqual(source.stage, "s0_opt")
            initial = root / "project" / "input" / "initial_geometry.xyz"
            initial.parent.mkdir(parents=True); initial.write_text(XYZ)
            source.config.system.initial_xyz = str(initial)
            engine = WorkflowEngine(source.config, str(root / "project"))
            record = engine.import_completed_stage(source.stage, source.output_path, source.input_path, source.gbw_path)
            self.assertEqual(record.status.value, "COMPLETED")
            self.assertEqual(engine.next_stage_after("s0_opt"), "absorption")
            self.assertTrue(Path(record.geometry_file).is_file())

    def test_external_absorption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "abs.out"; inp = root / "abs.inp"; gbw = root / "abs.gbw"
            out.write_text("CARTESIAN COORDINATES (ANGSTROEM)\n---------------------------------\nH 0 0 0\nH 0 0 .8\n\n" + TD_OUT, encoding="utf-8")
            inp.write_text("! CAM-B3LYP def2-SVP def2/J RIJCOSX TightSCF SP\n%tddft\n NRoots 5\n TDA true\n MaxDim 10\n MaxIter 300\nend\n* xyz 0 1\nH 0 0 0\nH 0 0 .8\n*\n", encoding="utf-8")
            gbw.write_bytes(b"gbw")
            source = inspect_external_workflow_source(str(out), orca_executable="orca")
            self.assertEqual(source.stage, "absorption")
            self.assertTrue(source.config.excited_states.use_tda)
            self.assertEqual(source.config.excited_states.nroots, 5)

    def test_external_excited_state_optimization_preserves_its_iroot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "s2opt.out"; inp = root / "s2opt.inp"; gbw = root / "s2opt.gbw"
            out.write_text(OPT_OUT, encoding="utf-8")
            inp.write_text(
                "! CAM-B3LYP def2-SVP TightSCF Opt\n%tddft\n NRoots 5\n TDA true\n IRoot 2\n IRootMult singlet\nend\n* xyz 0 1\nH 0 0 0\nH 0 0 .8\n*\n",
                encoding="utf-8",
            )
            gbw.write_bytes(b"gbw")
            source = inspect_external_workflow_source(str(out), orca_executable="orca", target_root=1)
            self.assertEqual(source.stage, "es_opt")
            self.assertEqual(source.config.excited_states.target_root, 2)

    def test_method_signature_is_canonical_and_contains_excited_method(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory) / "x.xyz")
            self.assertEqual(method_signature(cfg), method_signature(cfg))
            self.assertTrue(method_signature(cfg).endswith("|tda"))
            self.assertNotIn("|tda", method_signature(cfg, include_excited_state=False))

    def test_inputs_use_correct_geometry_and_wavefunction_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            engine = WorkflowEngine(config(initial), str(root / "project")); engine.prepare()
            absorption = engine.stage_input("absorption").read_text()
            esopt = engine.stage_input("es_opt").read_text()
            emission = engine.stage_input("emission").read_text()
            self.assertIn("mol_S0_opt.xyz", absorption)
            self.assertIn(engine.stage_gbw("s0_opt").name, absorption)
            self.assertIn(engine.stage_gbw("absorption").name, esopt)
            self.assertIn("mol_S1_opt.xyz", emission)
            self.assertIn(engine.stage_gbw("es_opt").name, emission)
            self.assertNotIn(" Opt", absorption)
            self.assertNotIn(" Opt", emission)

    def test_validation_requires_normal_termination_and_optimization(self):
        self.assertTrue(normal_termination(OPT_OUT))
        self.assertTrue(geometry_converged(OPT_OUT))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.out"; path.write_text("optimization stopped")
            with self.assertRaises(ValueError): validate_output(path, "s0_opt")

    def test_imaginary_frequency_parser(self):
        text = "  6:   -45.20 cm**-1\n  7: 10.0 cm**-1\n"
        self.assertEqual(imaginary_frequencies(text), [-45.2])

    def test_large_imaginary_frequency_blocks_downstream_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            cfg = config(initial); cfg.frequency.enabled = True
            engine = WorkflowEngine(cfg, str(root / "project")); engine.prepare()
            engine.stage_output("s0_freq").write_text(
                "  6: -45.2 cm**-1\nORCA TERMINATED NORMALLY\n", encoding="utf-8"
            )
            engine.validate_stage("s0_freq")
            self.assertEqual(engine.records["s0_freq"].status.value, "NEEDS_REVIEW")
            with self.assertRaises(WorkflowError): engine._check_dependency("absorption")

    def test_method_signature_tampering_blocks_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            engine = WorkflowEngine(config(initial), str(root / "project")); engine.prepare()
            inp = engine.stage_input("s0_opt")
            inp.write_text(inp.read_text().replace("cam-b3lyp", "pbe0"))
            with self.assertRaisesRegex(WorkflowError, "Method inconsistency"):
                engine._check_dependency("s0_opt")

    def test_keyword_tampering_with_unchanged_signature_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            engine = WorkflowEngine(config(initial), str(root / "project")); engine.prepare()
            inp = engine.stage_input("s0_opt")
            inp.write_text(inp.read_text().replace("CAM-B3LYP", "PBE0"))
            with self.assertRaisesRegex(WorkflowError, "Input consistency"):
                engine._check_dependency("s0_opt")

    def test_dependency_order_and_slurm_afterok_chain(self):
        self.assertEqual(dependency_order(False), ["s0_opt", "absorption", "es_opt", "emission"])
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory) / "x.xyz")
            script = build_dependency_submit_script(cfg)
            self.assertEqual(script.count("--dependency=afterok"), 3)
            self.assertNotIn("S0_freq", script)

    def test_example_yaml_loads_without_path_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_example_config(str(root / "config.yaml"))
            cfg = load_config(str(root / "config.yaml"))
            self.assertEqual(cfg.system.name, "molecule")
            self.assertEqual(Path(cfg.system.initial_xyz), root / "input" / "initial_geometry.xyz")

    def test_saved_gui_configuration_round_trips_without_pyyaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            source = config(initial)
            save_config(source, str(root / "config.yaml"))
            loaded = load_config(str(root / "config.yaml"))
            self.assertEqual(method_signature(loaded), method_signature(source))
            self.assertEqual(loaded.excited_states.target_root, 1)

    def test_failure_status_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            engine = WorkflowEngine(config(initial), str(root / "project")); engine.prepare()
            engine.stage_output("s0_opt").write_text("ORCA failed")
            with self.assertRaises(WorkflowError): engine.validate_stage("s0_opt", 1)
            payload = json.loads(engine.status_path.read_text())
            self.assertEqual(payload["stages"]["s0_opt"]["status"], "FAILED")

    def test_optimization_without_required_gbw_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); initial = root / "start.xyz"; initial.write_text(XYZ)
            engine = WorkflowEngine(config(initial), str(root / "project")); engine.prepare()
            engine.stage_output("s0_opt").write_text(OPT_OUT, encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, "wavefunction"):
                engine.validate_stage("s0_opt", 0)


if __name__ == "__main__":
    unittest.main()
