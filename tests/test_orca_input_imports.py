from pathlib import Path
import importlib.util
import inspect
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("orca_input", MODULE_PATH)
orca_input = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["orca_input"] = orca_input
spec.loader.exec_module(orca_input)

from gaussian_orca_converter import GaussianOrcaConverter
from orca_gaussian_converter import OrcaGaussianConverter
from input_format_converter import convert_input_text, detect_input_program


class ImportHelperTests(unittest.TestCase):
    def test_input_association_uses_only_same_basename_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            current_input = folder / "torsion.inp"
            current_output = folder / "torsion.out"
            previous_output = folder / "emission.out"
            current_input.write_text("! B3LYP\n", encoding="utf-8")
            previous_output.write_text("old", encoding="utf-8")
            self.assertEqual(orca_input.associated_output_path(str(current_input)), "")
            current_output.write_text("current", encoding="utf-8")
            self.assertEqual(
                Path(orca_input.associated_output_path(str(current_input))).resolve(),
                current_output.resolve(),
            )

    def test_workspace_rejects_output_owned_by_previous_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            current_input = folder / "torsion.inp"
            previous_output = folder / "emission.out"
            stale = {"ui_mode": "post", "output_path": str(previous_output), "scroll": 0.25}
            cleaned = orca_input.tool_state_for_current_input(stale, str(current_input))
            self.assertEqual(cleaned["output_path"], "")
            self.assertEqual(cleaned["ui_mode"], "input")
            self.assertEqual(stale["output_path"], str(previous_output))

    def test_workspace_keeps_same_job_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current_input = Path(tmpdir) / "torsion.inp"
            current_output = current_input.with_suffix(".out")
            state = {"output_path": str(current_output)}
            self.assertEqual(
                orca_input.tool_state_for_current_input(state, str(current_input))["output_path"],
                str(current_output),
            )

    def test_loaded_input_does_not_fall_back_to_unrelated_folder_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            current_input = folder / "torsion.inp"
            unrelated_output = folder / "emission.out"
            current_input.write_text("! B3LYP\n", encoding="utf-8")
            unrelated_output.write_text("ORCA TERMINATED NORMALLY\n", encoding="utf-8")
            app = object.__new__(orca_input.App)
            app.current_input_path = str(current_input)
            app.last_output_path = str(unrelated_output)
            app.path_var = SimpleNamespace(get=lambda: str(current_input))
            with self.assertRaisesRegex(ValueError, "No output file"):
                app._available_output_path()


    def test_tddft_builder_context_exposes_existing_method_and_geometry_controls(self):
        app = object.__new__(orca_input.App)
        value = lambda item: SimpleNamespace(get=lambda: item)
        app.functional_var = value("CAM-B3LYP")
        app.basis_var = value("def2-SVP")
        app.dispersion_var = value("D3BJ")
        app.grid_var = value("DefGrid2")
        app.ri_jcosx_var = value(True)
        app.tight_scf_var = value(True)
        app.solvent_var = value("Chloroform")
        app.charge_var = value(0); app.mult_var = value(1)
        app.multiwfn_path_var = value(""); app.orca_path_var = value("C:/ORCA/orca.exe")
        app.freeze_heavy_var = value(False); app.freeze_all_var = value(False)
        app.job_freq_var = value(True)
        app.structure_source_path = "molecule.xyz"
        app.structure = orca_input.Structure([("H", 0.0, 0.0, 0.0)], "molecule")
        app._available_output_path = lambda: ""
        context = app.get_tddft_global_context()
        self.assertEqual(context["dispersion"], "D3BJ")
        self.assertEqual(context["grid"], "DefGrid2")
        self.assertTrue(context["ri_jcosx"])
        self.assertEqual(context["atoms"][0][0], "H")
        self.assertTrue(context["job_freq"])
    class _Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    def test_new_extensions_are_case_insensitive(self):
        for ext in [".mol", ".SDF", ".sd", ".CML", ".cdxml", ".CDXM", ".CDX", ".ct", ".GJF", ".com", ".GAU", ".gjc"]:
            self.assertTrue(orca_input.structure_input_format("molecule" + ext))
        with self.assertRaises(ValueError):
            orca_input.structure_input_format("generic.inp2")

    def test_generic_inp_is_not_gaussian(self):
        self.assertEqual(orca_input.structure_input_format("job.inp"), "ORCA input")

    def test_standalone_input_converter_detects_and_dispatches_formats(self):
        self.assertEqual(detect_input_program("job.inp"), "ORCA")
        self.assertEqual(detect_input_program("job.GJF"), "Gaussian")
        gaussian = "#P B3LYP/6-31G(d) SP\n\nwater\n\n0 1\nO 0 0 0\nH 0 0 1\n\n"
        copied = convert_input_text(gaussian, "Gaussian", "Gaussian")
        self.assertFalse(copied.converted)
        self.assertEqual(copied.text, gaussian)
        converted = convert_input_text(gaussian, "Gaussian", "ORCA")
        self.assertTrue(converted.converted)
        self.assertIn("! B3LYP 6-31G(d) SP", converted.text)

    def test_loaded_gaussian_input_remains_verbatim_in_orca_preview(self):
        class Preview:
            def __init__(self): self.content = ""
            def delete(self, *_args): self.content = ""
            def insert(self, _index, text): self.content = text

        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            source = Path(tmpdir) / "water.gjf"
            source.write_text(
                "#P B3LYP/6-31G(d) Opt\n\nwater\n\n0 1\nO 0 0 0\nH 0 0 1\nH 0 1 0\n\n",
                encoding="utf-8",
            )
            app = object.__new__(orca_input.App)
            app.program_var = self._Var("ORCA")
            app.preview_text = Preview()
            app._show_output_mode = lambda _mode: None
            app.append_monitor = lambda _line: None
            app.status = SimpleNamespace(configure=lambda **_kwargs: None)
            self.assertTrue(app._show_loaded_engine_input(str(source)))
            self.assertEqual(app.preview_text.content, source.read_text(encoding="utf-8"))
            self.assertIn("#P B3LYP/6-31G(d) Opt", app.preview_text.content)
            self.assertNotIn("* xyz 0 1", app.preview_text.content)

    def test_loaded_orca_input_remains_verbatim_in_gaussian_preview(self):
        class Preview:
            def __init__(self): self.content = ""
            def delete(self, *_args): self.content = ""
            def insert(self, _index, text): self.content = text

        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            source = Path(tmpdir) / "water.inp"
            source.write_text(
                "! PBE0 def2-SVP Freq\n\n* xyz -1 2\nO 0 0 0\nH 0 0 1\n*\n",
                encoding="utf-8",
            )
            app = object.__new__(orca_input.App)
            app.program_var = self._Var("Gaussian")
            app.preview_text = Preview()
            app._show_output_mode = lambda _mode: None
            app.append_monitor = lambda _line: None
            app.status = SimpleNamespace(configure=lambda **_kwargs: None)
            self.assertTrue(app._show_loaded_engine_input(str(source)))
            self.assertEqual(app.preview_text.content, source.read_text(encoding="utf-8"))
            self.assertIn("! PBE0 def2-SVP Freq", app.preview_text.content)
            self.assertNotIn("#P", app.preview_text.content)

    def test_save_as_inp_converts_loaded_gaussian_only_when_saving(self):
        class Preview:
            def __init__(self, content): self.content = content
            def delete(self, *_args): self.content = ""
            def insert(self, _index, text): self.content = text

        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            source = Path(tmpdir) / "water.gjf"
            target = Path(tmpdir) / "water.inp"
            original = "#P B3LYP/6-31G(d) Opt\n\nwater\n\n0 1\nO 0 0 0\nH 0 0 1\n\n"
            source.write_text(original, encoding="utf-8")
            app = object.__new__(orca_input.App)
            app.path_var = self._Var(str(source))
            app.program_var = self._Var("ORCA")
            app.preview_text = Preview(original)
            app.get_preview_text = lambda: app.preview_text.content
            app._show_output_mode = lambda _mode: None
            app.append_monitor = lambda _line: None
            app.status = SimpleNamespace(configure=lambda **_kwargs: None)
            with mock.patch.object(orca_input.filedialog, "asksaveasfilename", return_value=str(target)):
                app.save_input()
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertIn("! B3LYP 6-31G(d) Opt", target.read_text(encoding="utf-8"))
            self.assertIn("* xyz 0 1", target.read_text(encoding="utf-8"))

    def test_save_as_gjf_converts_loaded_orca_only_when_saving(self):
        class Preview:
            def __init__(self, content): self.content = content
            def delete(self, *_args): self.content = ""
            def insert(self, _index, text): self.content = text

        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            source = Path(tmpdir) / "water.inp"
            target = Path(tmpdir) / "water.gjf"
            original = "! PBE0 def2-SVP Freq\n\n* xyz -1 2\nO 0 0 0\nH 0 0 1\n*\n"
            source.write_text(original, encoding="utf-8")
            app = object.__new__(orca_input.App)
            app.path_var = self._Var(str(source))
            app.program_var = self._Var("Gaussian")
            app.preview_text = Preview(original)
            app.get_preview_text = lambda: app.preview_text.content
            app._show_output_mode = lambda _mode: None
            app.append_monitor = lambda _line: None
            app.status = SimpleNamespace(configure=lambda **_kwargs: None)
            with mock.patch.object(orca_input.filedialog, "asksaveasfilename", return_value=str(target)):
                app.save_input()
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertIn("#P PBE1PBE/Def2SVP Freq", target.read_text(encoding="utf-8"))
            self.assertIn("-1 2", target.read_text(encoding="utf-8"))

    def test_save_as_gjf_converts_builder_orca_preview_from_xyz_source(self):
        class Preview:
            def __init__(self, content): self.content = content
            def delete(self, *_args): self.content = ""
            def insert(self, _index, text): self.content = text

        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            source = Path(tmpdir) / "water.xyz"
            target = Path(tmpdir) / "water.gjf"
            source.write_text("2\nwater\nO 0 0 0\nH 0 0 1\n", encoding="utf-8")
            orca_text = "! PBE0 def2-SVP SP\n\n* xyz 0 1\nO 0 0 0\nH 0 0 1\n*\n"
            app = object.__new__(orca_input.App)
            app.path_var = self._Var(str(source))
            app.program_var = self._Var("ORCA")
            app.preview_text = Preview(orca_text)
            app.get_preview_text = lambda: app.preview_text.content
            app.synchronize_input_preview = lambda: orca_text
            app.suggest_input_save_path = lambda: str(Path(tmpdir) / "water.inp")
            app._confirm_tddft_memory_risk = lambda: None
            app._show_output_mode = lambda _mode: None
            app.append_monitor = lambda _line: None
            app.status = SimpleNamespace(configure=lambda **_kwargs: None)
            with mock.patch.object(orca_input.filedialog, "asksaveasfilename", return_value=str(target)):
                app.save_input()
            saved = target.read_text(encoding="utf-8")
            self.assertIn("#P PBE1PBE/Def2SVP SP", saved)
            self.assertNotIn("! PBE0", saved)

    def test_orca_to_gaussian_maps_builder_controls_without_orca_keywords(self):
        converted = OrcaGaussianConverter().convert_text(
            "! B3LYP def2-SVP def2/J RIJCOSX TightSCF DefGrid2 SP\n"
            "%pal\n  nprocs 1\nend\n"
            "%output\n  Print[P_MOs] 1\nend\n"
            "* xyz 0 1\nO 0 0 0\nH 0 0 1\n*\n"
        )
        gaussian = converted.gaussian_input
        self.assertTrue(gaussian.startswith("%NProcShared=1\n"))
        self.assertIn("B3LYP/Def2SVP", gaussian)
        self.assertIn("SP", gaussian)
        self.assertIn("SCF=Tight", gaussian)
        self.assertIn("Integral=FineGrid", gaussian)
        for orca_only in ("def2/J", "RIJCOSX", "TightSCF", "DefGrid2"):
            self.assertNotIn(orca_only, gaussian)
        self.assertTrue(any("auxiliary basis" in warning for warning in converted.warnings))
        self.assertIn("Pop=Full", gaussian)

    def test_orca_to_gaussian_converts_blocks_resources_and_round_trips(self):
        orca = (
            "! CAM-B3LYP def2-TZVP D3BJ TightSCF DefGrid3 Opt Freq KeepDens\n"
            "# full semantic conversion\n"
            "%maxcore 1200\n%pal\n  nprocs 8\nend\n"
            "%base \"calculation\"\n"
            "%scf\n  MaxIter 300\nend\n"
            "%geom\n  MaxIter 75\n  Calc_Hess true\n  Constraints\n"
            "    { B 0 1 C }\n  end\nend\n"
            "%tddft\n  NRoots 12\n  IRoot 2\n  TDA true\nend\n"
            "%eprnmr\n  NMR true\nend\n"
            "%cpcm\n  smd true\n  SMDsolvent \"Acetonitrile\"\nend\n"
            "%output\n  Print[P_MOs] 1\n  Print[P_OrbEn] 2\nend\n"
            "* xyz -1 2\nO 0 0 0\nH 0 0 1\n*\n"
        )
        converted = OrcaGaussianConverter().convert_text(orca)
        gaussian = converted.gaussian_input
        for expected in (
            "%NProcShared=8", "%Mem=12800MB", "%Chk=calculation.chk",
            "CAM-B3LYP/Def2TZVP", "EmpiricalDispersion=GD3BJ",
            "Opt=(CalcFC,MaxCycles=75,ModRedundant)", "Freq", "Density=Current",
            "TDA=(NStates=12,Root=2)", "NMR", "SCRF=(SMD,Solvent=Acetonitrile)",
            "Pop=Full", "SCF=(Tight,MaxCycle=300)", "Integral=UltraFine",
            "B 1 2 F",
        ):
            self.assertIn(expected, gaussian)
        self.assertEqual(converted.title, "full semantic conversion")

        round_trip = GaussianOrcaConverter().convert_text(gaussian).orca_input
        for expected in (
            "CAM-B3LYP", "def2-TZVP", "D3BJ", "TightSCF", "DefGrid3",
            "Opt", "Freq", "KeepDens", "%maxcore 1200", "nprocs 8",
            "NRoots 12", "IRoot 2", "TDA true", 'SMDsolvent "Acetonitrile"',
            "Print[P_MOs] 1", "Print[P_OrbEn] 2",
        ):
            self.assertIn(expected, round_trip)

    def test_gaussian_converter_keeps_multiline_route_keywords(self):
        converted = GaussianOrcaConverter().convert_text(
            "#P CAM-B3LYP/def2-TZVP\n"
            "Opt Freq EmpiricalDispersion=GD3BJ\n\n"
            "multiline route\n\n0 1\nH 0 0 0\nH 0 0 1\n\n"
        )
        self.assertIn("CAM-B3LYP", converted.orca_input)
        self.assertIn("Opt", converted.orca_input)
        self.assertIn("Freq", converted.orca_input)
        self.assertIn("D3BJ", converted.orca_input)

    def test_gaussian_converter_maps_resources_and_compound_options(self):
        converted = GaussianOrcaConverter().convert_text(
            "%Mem=16GB\n%NProcShared=8\n%Chk=transition.chk\n"
            "#P CAM-B3LYP/def2-TZVP Opt=(TS,CalcFC,MaxCycles=120) "
            "SCF=(XQC,MaxCycle=300) TD=(NStates=12,Root=2) "
            "SCRF=(SMD,Solvent=Water) NoSymm\n\ntransition\n\n"
            "-1 2\nO 0 0 0\nH 0 0 1\n\n"
        )
        text = converted.orca_input
        self.assertIn("! CAM-B3LYP def2-TZVP OptTS SlowConv NoSym", text)
        self.assertNotIn(" Opt OptTS", text)
        self.assertIn("%maxcore 1536", text)
        self.assertIn("nprocs 8", text)
        self.assertIn('%base "transition"', text)
        self.assertIn("MaxIter 300", text)
        self.assertIn("MaxIter 120", text)
        self.assertIn("Calc_Hess true", text)
        self.assertIn("NRoots 12", text)
        self.assertIn("IRoot 2", text)
        self.assertIn('SMDsolvent "Water"', text)

    def test_gaussian_converter_comments_unknown_keywords_and_maps_frozen_coordinates(self):
        converted = GaussianOrcaConverter().convert_text(
            "#P B3LYP/6-31G(d) Opt=ModRedundant IOP(3/33=1) MadeUpKeyword\n\n"
            "constraints\n\n0 1\nO 0 0 0\nH 0 0 1\nH 1 0 0\n\n"
            "B 1 2 F\nA 2 1 3 F\n\n"
        )
        text = converted.orca_input
        self.assertIn("{ B 0 1 C }", text)
        self.assertIn("{ A 1 0 2 C }", text)
        self.assertIn("# Unmapped Gaussian route token: IOP(3/33=1)", text)
        self.assertIn("# Unmapped Gaussian route token: MadeUpKeyword", text)
        keyword_line = text.splitlines()[0]
        self.assertNotIn("IOP", keyword_line)
        self.assertNotIn("MadeUpKeyword", keyword_line)

    def test_gaussian_converter_reports_link1_instead_of_silently_dropping_it(self):
        converted = GaussianOrcaConverter().convert_text(
            "#P B3LYP/6-31G(d) Opt\n\nfirst\n\n0 1\nH 0 0 0\nH 0 0 1\n\n"
            "--Link1--\n%OldChk=first.chk\n#P B3LYP/6-31G(d) Freq Geom=AllCheck\n\n"
        )
        self.assertTrue(any("Link1" in warning for warning in converted.warnings))

    def test_gaussian_converter_preserves_genecp_data_without_activating_it(self):
        converted = GaussianOrcaConverter().convert_text(
            "#P B3LYP/GenECP SP\n\ngeneral basis\n\n0 1\nPd 0 0 0\nCl 0 0 2\n\n"
            "Pd 0\nSDD\n****\nCl 0\n6-31G(d)\n****\n\nPd 0\nSDD\n\n"
        )
        self.assertNotIn("GenECP", converted.orca_input.splitlines()[0])
        self.assertIn("#   Pd 0", converted.orca_input)
        self.assertIn("#   SDD", converted.orca_input)
        self.assertTrue(any("%basis" in warning for warning in converted.warnings))

    def test_user_selected_orca_executable_accepts_custom_filename(self):
        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            executable = Path(tmpdir) / "orca_6_custom_launcher.exe"
            executable.write_bytes(b"test executable placeholder")
            completed = SimpleNamespace(stdout="Program ORCA version 6.0", stderr="", returncode=0)
            with mock.patch.object(orca_input.subprocess, "run", return_value=completed) as run:
                ok, reason = orca_input.validate_orca_qm_executable(str(executable))
            self.assertTrue(ok, reason)
            self.assertTrue(run.called)
            self.assertEqual(run.call_args_list[0].args[0][0], str(executable))

    def test_orca_xyzfile_is_resolved_relative_to_input(self):
        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            folder = Path(tmpdir)
            (folder / "restart geometry.xyz").write_text(
                "2\nrestart\nH 0 0 0\nH 0 0 0.74\n", encoding="utf-8"
            )
            inp = folder / "restart.inp"
            inp.write_text(
                '! B3LYP\n* xyzfile 0 1 "restart geometry.xyz"\n', encoding="utf-8"
            )
            structure = orca_input.StructureParser.parse_orca_input(str(inp))
            self.assertEqual(len(structure.atoms), 2)
            self.assertIn("restart geometry.xyz", structure.title)

    def test_orca_xyzfile_reports_missing_reference(self):
        work_root = ROOT / "tmp" / "codex_work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work_root) as tmpdir:
            inp = Path(tmpdir) / "restart.inp"
            inp.write_text("! B3LYP\n* xyzfile 0 1 absent.xyz\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Referenced ORCA xyzfile was not found"):
                orca_input.StructureParser.parse_orca_input(str(inp))

    def test_valid_and_invalid_xyz_output(self):
        xyz = "2\nwater fragment\nO 0 0 0\nH 0 0 1\n"
        structure = orca_input.validate_xyz_text(xyz)
        self.assertEqual(len(structure.atoms), 2)
        with self.assertRaises(ValueError):
            orca_input.validate_xyz_text("2\nbad\nO 0 0 nan\nH 0 0 1\n")
        with self.assertRaises(ValueError):
            orca_input.validate_xyz_text("3\nbad\nO 0 0 0\n")

    def test_native_cdxml_reads_and_scales_complete_stored_3d(self):
        cdxml = """<?xml version="1.0"?>
<CDXML xmlns="http://www.cambridgesoft.com/xml/cdxml">
  <page><fragment id="10">
    <n id="1" Element="6" xyz="0 0 0"/>
    <n id="2" Element="8" xyz="14.4 0 3.0" Charge="-1"/>
    <b id="3" B="1" E="2" Order="1"/>
  </fragment></page>
</CDXML>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stored.cdxml"
            path.write_text(cdxml, encoding="utf-8")
            parsed = orca_input.parse_cdxml_stored_3d(str(path))
        self.assertIsNotNone(parsed)
        atoms, logs = parsed
        self.assertEqual([atom[0] for atom in atoms], ["C", "O"])
        distance = sum((atoms[0][axis] - atoms[1][axis]) ** 2 for axis in range(1, 4)) ** 0.5
        expected = orca_input.COVALENT_RADII["C"] + orca_input.COVALENT_RADII["O"]
        self.assertAlmostEqual(distance, expected, places=6)
        self.assertTrue(any("formal charges: -1" in line for line in logs))

    def test_native_cdxml_returns_none_for_2d_only_document(self):
        cdxml = "<CDXML><page><fragment><n id='1' Element='6' p='0 0'/></fragment></page></CDXML>"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "flat.cdxm"
            path.write_text(cdxml, encoding="utf-8")
            self.assertIsNone(orca_input.parse_cdxml_stored_3d(str(path)))

    def test_native_cdxml_rejects_partial_stored_3d(self):
        cdxml = """<CDXML><page><fragment>
<n id="1" Element="6" xyz="0 0 0"/><n id="2" Element="6" p="1 0"/>
<b B="1" E="2"/></fragment></page></CDXML>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "partial.cdxml"
            path.write_text(cdxml, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete stored 3D coordinates"):
                orca_input.parse_cdxml_stored_3d(str(path))

    @unittest.skipIf(orca_input.gemmi is None, "Gemmi is not installed")
    def test_cif_symmetry_completes_inversion_generated_molecule(self):
        cif = """data_inversion
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P -1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .45 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inversion.cif"
            path.write_text(cif, encoding="utf-8")
            structure = orca_input.StructureParser.parse(str(path))
        self.assertEqual([atom[0] for atom in structure.atoms], ["C", "C"])
        self.assertAlmostEqual(orca_input.distance(*structure.atoms), 1.0, places=6)

    @unittest.skipIf(orca_input.gemmi is None, "Gemmi is not installed")
    def test_cif_without_generated_symmetry_keeps_existing_coordinates(self):
        cif = """data_boundary
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P 1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .98 .5 .5
C2 C .08 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundary.cif"
            path.write_text(cif, encoding="utf-8")
            structure = orca_input.StructureParser.parse(str(path))
        self.assertEqual(len(structure.atoms), 2)
        self.assertAlmostEqual(orca_input.distance(*structure.atoms), 9.0, places=6)

    def test_cif_fallback_does_not_silently_return_asymmetric_unit(self):
        cif = """data_half
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_space_group_symop_operation_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .45 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "half.cif"
            path.write_text(cif, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Gemmi"):
                orca_input.StructureParser.parse_cif_fallback(str(path))

    def test_2d_detection(self):
        flat = orca_input.Structure([("C", 0.0, 0.0, 0.0), ("O", 1.2, 0.0, 0.0)])
        spatial = orca_input.Structure([("C", 0.0, 0.0, 0.0), ("O", 1.2, 0.0, 0.2)])
        self.assertTrue(orca_input.looks_like_2d_structure(flat))
        self.assertFalse(orca_input.looks_like_2d_structure(spatial))

    def test_gaussian_cartesian_charge_multiplicity_freeze_and_atomic_numbers(self):
        text = """%chk=test.chk
#p b3lyp/6-31g(d)

Title

-1 2
6 0 0.000000 0.000000 0.000000
O 0 1.200000 0.000000 0.000000
H(label) 0.000000 0.000000 1.000000

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertEqual(section.charge, -1)
        self.assertEqual(section.multiplicity, 2)
        self.assertEqual([atom[0] for atom in section.atoms], ["C", "O", "H"])
        self.assertTrue(any("freeze-code" in warning for warning in section.warnings))

    def test_gaussian_bohr_to_angstrom(self):
        text = """#p hf/sto-3g units=bohr

Bohr title

0 1
H 0 0 1.0

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertEqual(section.units, "bohr")
        self.assertAlmostEqual(section.atoms[0][3], orca_input.BOHR_TO_ANGSTROM)

    def test_gaussian_link1_selection_metadata_and_checkpoint_rejection(self):
        text = """#p hf/sto-3g

First

0 1
H 0 0 0

--Link1--
#p hf/sto-3g geom=check

Second

0 1

"""
        sections = orca_input.parse_gaussian_input_text(text)
        geometry = orca_input.gaussian_sections_with_geometry(sections)
        self.assertEqual([section.index for section in geometry], [1])
        self.assertTrue(sections[1].checkpoint_dependent)

    def test_gaussian_zmatrix_requires_openbabel(self):
        text = """#p hf/sto-3g

Zmat

0 1
O
H 1 0.96
H 1 0.96 2 104.5

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertTrue(section.requires_openbabel)
        self.assertEqual(section.coordinate_type, "Z-matrix")

    def test_sdf_record_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sdf = Path(tmpdir) / "multi.sdf"
            sdf.write_text(
                "one\n  test\n\n  2  1  0  0  0  0            999 V2000\n$$$$\n"
                "two\n  test\n\n  3  2  0  0  0  0            999 V2000\n$$$$\n",
                encoding="utf-8",
            )
            records = orca_input.count_sdf_records(str(sdf))
        self.assertEqual([record["atom_count"] for record in records], [2, 3])

    def test_native_mol_to_xyz(self):
        mol = """Water 3D
  CrystEngKit

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.7586    0.0000    0.5043 H   0  0  0  0  0  0  0  0  0  0  0  0
   -0.7586    0.0000    0.5043 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
"""
        atoms, title = orca_input.parse_mol_v2000_atoms(mol, "MOL")
        self.assertEqual(title, "Water 3D")
        self.assertEqual([atom[0] for atom in atoms], ["O", "H", "H"])
        self.assertAlmostEqual(atoms[1][3], 0.5043)

    def test_native_sdf_selects_record_to_xyz(self):
        sdf = """First
  CrystEngKit

  1  0  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
Second
  CrystEngKit

  2  1  0  0  0  0            999 V2000
    0.0000    0.0000    0.1000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.2000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
M  END
$$$$
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multi.sdf"
            path.write_text(sdf, encoding="utf-8")
            xyz, title, logs = orca_input.mol_sdf_to_xyz_text(str(path), record_index=2)
        structure = orca_input.validate_xyz_text(xyz, "SDF")
        self.assertEqual(title, "Second")
        self.assertEqual([atom[0] for atom in structure.atoms], ["N", "H"])
        self.assertTrue(any("Selected SDF record: 2" in line for line in logs))

    def test_openbabel_validation_failure(self):
        ok, reason = orca_input.validate_openbabel_executable(str(ROOT / "missing_obabel"))
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

    def test_show_active_run_input_prefers_running_job_input(self):
        class DummyText:
            def __init__(self):
                self.content = ""

            def delete(self, *_args, **_kwargs):
                self.content = ""

            def insert(self, *_args, **_kwargs):
                self.content = _args[1] if len(_args) > 1 else ""

        class DummyStatus:
            def __init__(self):
                self.messages = []

            def configure(self, **kwargs):
                self.messages.append(kwargs)

        app = orca_input.App.__new__(orca_input.App)
        app.run_process = type("Proc", (), {"poll": lambda self: None})()
        app.current_input_path = None
        app.preview_text = DummyText()
        app.status = DummyStatus()
        app.output_mode = "monitor"
        app.output_buffers = {"preview": "", "monitor": ""}
        app.output_wraps = {"preview": "none", "monitor": "none"}
        app.preview_mode_button = None
        app.monitor_mode_button = None
        app._show_output_mode = lambda mode: setattr(app, "output_mode", mode)
        app.preview = lambda: setattr(app, "preview_called", True)
        app.preview_called = False

        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "running.inp"
            inp_path.write_text("! Running input\n", encoding="utf-8")
            app.current_input_path = str(inp_path)
            app._show_running_job_input_preview()

        self.assertFalse(getattr(app, "preview_called", False))
        self.assertEqual(app.preview_text.content, "! Running input\n")
        self.assertEqual(app.output_mode, "preview")

    def test_orca_uses_synchronized_tddft_block_exactly_once(self):
        structure = orca_input.Structure([("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.74)])
        data = {
            "functional": "B3LYP", "basis": "def2-SVP", "dispersion": "", "ri_jcosx": False,
            "tight_scf": True, "grid": "DefGrid2", "job_opt": False, "job_freq": False,
            "job_density": False, "job_esp": False, "job_sp": False, "job_tddft": True,
            "job_nmr": False, "print_mos": False, "extra": "", "charge": 0, "multiplicity": 1,
            "freeze_all": False, "freeze_heavy": False,
            "tddft_block": "%tddft\n  NRoots 7\n  TDA true\nend",
        }
        text = orca_input.generate_orca(data, structure, None)
        self.assertEqual(text.lower().count("%tddft"), 1)
        self.assertIn("NRoots 7", text)

        data["tddft_block"] = "%tddft\n  NRoots 11\n  TDA false\nend"
        updated = orca_input.generate_orca(data, structure, None)
        self.assertEqual(updated.lower().count("%tddft"), 1)
        self.assertNotIn("NRoots 7", updated)
        self.assertIn("NRoots 11", updated)

        data["tddft_settings"] = {"excited_state_optimization": True, "excited_state_frequencies": True}
        excited_state_job = orca_input.generate_orca(data, structure, None)
        self.assertIn(" Opt", excited_state_job.splitlines()[0])
        self.assertIn(" Freq", excited_state_job.splitlines()[0])

        data["tddft_block"] = (
            '! MOREAD\n%moinp "C:/calc/absorption.gbw"\n\n'
            "%tddft\n  NRoots 11\n  TDA true\n  IRoot 1\nend"
        )
        reused_orbitals_job = orca_input.generate_orca(data, structure, None)
        self.assertIn(" MOREAD", reused_orbitals_job.splitlines()[0])
        self.assertEqual(reused_orbitals_job.upper().count("MOREAD"), 1)
        self.assertIn('%moinp "C:/calc/absorption.gbw"', reused_orbitals_job)
        self.assertEqual(reused_orbitals_job.lower().count("%tddft"), 1)

    def test_tddft_rpa_convergence_failure_is_reported_specifically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "failed.out"
            out_path.write_text(
                "ORCA finished by error termination in CIS\n"
                "[file orca_cis/cis_solve_rpa.cpp, line 248]: "
                "RPA/TD-DFT did not converge! You may try raising the number of iterations.\n",
                encoding="utf-8",
            )
            ok, reason = orca_input.validate_orca_output_file(str(out_path))
        self.assertFalse(ok)
        self.assertIn("TD-DFT/RPA did not converge", reason)

    def test_ai_progress_prompt_redacts_sensitive_details_and_requests_short_answer(self):
        output = (
            "INPUT FILE C:\\Users\\chemist\\secret\\private_job.inp\n"
            "C 0.000 1.000 2.000\nH 0.000 0.000 1.000\n"
            "SCF ITERATION 12 ENERGY -100.0\napi_key=do-not-send\n"
        )
        prompt = orca_input.build_orca_progress_prompt(output)
        self.assertTrue(prompt.startswith("ORCA Job progress report."))
        self.assertNotIn(r"C:\Users\chemist", prompt)
        self.assertNotIn("private_job", prompt)
        self.assertNotIn("do-not-send", prompt)
        self.assertNotIn("C 0.000 1.000 2.000", prompt)
        self.assertIn("SCF ITERATION 12", prompt)
        self.assertIn("at most 120 words", prompt)
        self.assertIn("intentionally bounded live extract", prompt)
        self.assertIn("Never describe the paste as truncated", prompt)
        self.assertTrue(prompt.endswith(orca_input.ORCA_PROMPT_END_MARKER))
        self.assertIn("never refuse analysis", prompt)
        self.assertIn("unfinished calculation", prompt)
        self.assertIn("likely sequence of remaining stages", prompt)
        self.assertIn("overall remaining time", prompt)
        self.assertNotIn("INPUT_COMPLETE: YES", prompt)

    def test_chatgpt_is_default_ai_web_model(self):
        self.assertEqual(orca_input.DEFAULT_AI_WEB_MODEL, "ChatGPT")
        self.assertEqual(next(iter(orca_input.AI_WEB_MODELS)), "ChatGPT")
        self.assertEqual(orca_input.AI_WEB_MODELS["ChatGPT"], orca_input.CHATGPT_ORCA_MONITOR_URL)
        self.assertIn("g-6a5f33b7e3b881918fa604bb19250b23", orca_input.CHATGPT_ORCA_MONITOR_URL)

    def test_ai_browser_opens_only_after_verified_clipboard_copy(self):
        app = object.__new__(orca_input.App)
        app.ai_web_model_var = SimpleNamespace(get=lambda: "ChatGPT")
        app._orca_output_for_ai = lambda: "SCF ITERATION 9"
        app.clipboard_clear = mock.Mock()
        app.clipboard_append = mock.Mock()
        app.update_idletasks = mock.Mock()
        app.clipboard_get = mock.Mock(return_value="wrong clipboard contents")

        with mock.patch.object(orca_input.webbrowser, "open") as open_browser, \
             mock.patch.object(orca_input.messagebox, "showerror") as show_error:
            app.open_ai_progress_prompt()

        open_browser.assert_not_called()
        show_error.assert_called_once()

    def test_ai_browser_opens_after_verified_clipboard_copy(self):
        app = object.__new__(orca_input.App)
        app.ai_web_model_var = SimpleNamespace(get=lambda: "ChatGPT")
        app._orca_output_for_ai = lambda: "SCF ITERATION 9"
        copied = {"value": ""}
        app.clipboard_clear = lambda: copied.update(value="")
        app.clipboard_append = lambda value: copied.update(value=value)
        app.update_idletasks = lambda: None
        app.clipboard_get = lambda: copied["value"]
        app.append_monitor = mock.Mock()

        with mock.patch.object(orca_input.webbrowser, "open", return_value=True) as open_browser:
            app.open_ai_progress_prompt()

        open_browser.assert_called_once_with(orca_input.CHATGPT_ORCA_MONITOR_URL, new=2)
        self.assertTrue(copied["value"].endswith(orca_input.ORCA_PROMPT_END_MARKER))

    def test_orca_monitor_agent_payload_contains_data_but_no_analysis_instructions(self):
        payload = orca_input.build_orca_agent_payload("SCF ITERATION 9\nC 0.0 1.0 2.0")
        self.assertTrue(payload.startswith("ORCA Job progress report."))
        self.assertTrue(payload.endswith(orca_input.ORCA_PROMPT_END_MARKER))
        self.assertIn("PAYLOAD STATUS: COMPLETE PRIVACY-REDACTED ORCA OUTPUT", payload)
        self.assertGreaterEqual(payload.count(orca_input.ORCA_PROMPT_END_MARKER), 2)
        self.assertIn("SCF ITERATION 9", payload)
        self.assertNotIn("C 0.0 1.0 2.0", payload)
        self.assertNotIn("Answer in at most", payload)
        self.assertNotIn("Act as an expert", payload)
        self.assertIn("COMPLETE PAYLOAD: FINAL MARKER FOLLOWS", payload)

    def test_large_agent_payload_is_first_turn_safe_progress_extract(self):
        source = (
            "Program Version 6.1.0\n! CAM-B3LYP def2-SVP OPT TIGHTSCF\n"
            + "routine data\n" * 12000
            + "SCF ITERATION 77 NOT CONVERGED\n" + "more routine data\n" * 12000
            + "GEOMETRY OPTIMIZATION CYCLE 12\nTOTAL RUN TIME: 1 hours 2 minutes\n"
        )
        payload = orca_input.build_orca_agent_payload(source)
        self.assertLess(len(payload), orca_input.ORCA_AGENT_OUTPUT_MAX_CHARS + 600)
        self.assertIn("Program Version 6.1.0", payload)
        self.assertIn("CAM-B3LYP def2-SVP OPT", payload)
        self.assertIn("SCF ITERATION 77 NOT CONVERGED", payload)
        self.assertIn("GEOMETRY OPTIMIZATION CYCLE 12", payload)
        self.assertIn("TOTAL RUN TIME", payload)
        self.assertIn("COMPLETE PROGRESS-FOCUSED EXTRACT FROM FULL ORCA OUTPUT", payload)
        self.assertIn("CRYSTENGKIT SEMANTIC EXTRACT", payload)
        self.assertNotIn("routine data", payload)
        self.assertTrue(payload.endswith(orca_input.ORCA_PROMPT_END_MARKER))

    def test_large_agent_payload_stays_below_conservative_inline_paste_limit(self):
        source = "GEOMETRY OPTIMIZATION CYCLE 1\n" + ("SCF ITERATION 12\n" * 5000)
        payload = orca_input.build_orca_agent_payload(source)
        self.assertLess(len(payload), 13000)
        self.assertIn("GEOMETRY OPTIMIZATION CYCLE", payload)
        self.assertTrue(payload.endswith(orca_input.ORCA_PROMPT_END_MARKER))

    def test_monitor_actions_have_unique_standard_icons_and_handlers(self):
        actions = orca_input.MONITOR_ACTION_BUTTONS
        self.assertEqual(len(actions), 7)
        self.assertEqual([item[1] for item in actions], [
            "Stop job", "Reconnect", "Open .out", "Open folder", "Show summary",
            "Ask AI about progress", "Clear monitor",
        ])
        self.assertEqual(len({item[0] for item in actions}), len(actions))
        for _icon, _label, handler in actions:
            self.assertTrue(callable(getattr(orca_input.App, handler)))

    def test_monitor_actions_use_balanced_two_row_grid(self):
        positions = [orca_input.monitor_action_grid_position(i) for i in range(7)]
        self.assertEqual(positions[:4], [
            (0, 0, 3), (0, 3, 3), (0, 6, 3), (0, 9, 3),
        ])
        self.assertEqual(positions[4:], [
            (1, 0, 4), (1, 4, 4), (1, 8, 4),
        ])

    def test_attached_process_recognizes_current_live_pid(self):
        executable = orca_input.process_executable_path(os.getpid())
        self.assertTrue(executable)
        attached = orca_input.AttachedOrcaProcess(os.getpid(), executable)
        self.assertIsNone(attached.poll())

    def test_active_job_state_uses_user_config_location(self):
        self.assertEqual(
            orca_input.ACTIVE_ORCA_JOB_STATE_PATH.parent,
            orca_input.startup_news_cache_dir(),
        )

    def test_completed_output_rerun_suggests_and_creates_safe_alternative(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("! B3LYP\n* xyz 0 1\n*\n", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel", return_value=True) as confirm, \
                    mock.patch.object(
                        orca_input.filedialog, "asksaveasfilename",
                        return_value=str(Path(tmpdir) / "finished_custom.inp"),
                    ) as save_as:
                selected = app._resolve_completed_job_rerun_path(str(inp_path))
            self.assertEqual(selected, str(Path(tmpdir) / "finished_custom.inp"))
            self.assertEqual(Path(selected).read_text(encoding="utf-8"), inp_path.read_text(encoding="utf-8"))
        self.assertEqual(confirm.call_args.kwargs["icon"], "warning")
        self.assertEqual(confirm.call_args.kwargs["default"], orca_input.messagebox.YES)
        self.assertIn("finished_01.inp", confirm.call_args.args[1])
        self.assertEqual(save_as.call_args.kwargs["initialfile"], "finished_01.inp")

    def test_rerun_alternative_suffix_skips_existing_job_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "job.inp"
            inp_path.write_text("input", encoding="utf-8")
            (Path(tmpdir) / "job_01.gbw").write_text("existing", encoding="utf-8")
            self.assertEqual(
                orca_input.App._suggest_rerun_input_path(str(inp_path)),
                str(Path(tmpdir) / "job_02.inp"),
            )

    def test_overwrite_choice_requires_second_attention_confirmation(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(
                orca_input.messagebox, "askyesnocancel", side_effect=[False, True]
            ) as confirm:
                self.assertEqual(app._resolve_completed_job_rerun_path(str(inp_path)), str(inp_path))
        self.assertEqual(confirm.call_count, 2)
        self.assertIn("ARE YOU SURE?", confirm.call_args_list[1].args[1])
        self.assertEqual(confirm.call_args_list[1].kwargs["default"], orca_input.messagebox.NO)

    def test_no_on_second_overwrite_warning_uses_safe_alternative(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(
                orca_input.messagebox, "askyesnocancel", side_effect=[False, False]
            ), mock.patch.object(
                orca_input.filedialog, "asksaveasfilename",
                return_value=str(Path(tmpdir) / "finished_01.inp"),
            ):
                selected = app._resolve_completed_job_rerun_path(str(inp_path))
            self.assertEqual(selected, str(Path(tmpdir) / "finished_01.inp"))
            self.assertTrue(Path(selected).is_file())

    def test_cancelling_rerun_save_as_cancels_run(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel", return_value=True), \
                    mock.patch.object(orca_input.filedialog, "asksaveasfilename", return_value=""):
                self.assertIsNone(app._resolve_completed_job_rerun_path(str(inp_path)))

    def test_incomplete_output_does_not_prompt_before_rerun(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "unfinished.out"
            out_path.write_text("Program ORCA\nSCF ITERATION 4\n", encoding="utf-8")
            inp_path = Path(tmpdir) / "unfinished.inp"
            inp_path.write_text("input", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel") as confirm:
                self.assertEqual(app._resolve_completed_job_rerun_path(str(inp_path)), str(inp_path))
                confirm.assert_not_called()

    def test_loading_path_does_not_invoke_recalculation_guard(self):
        app = object.__new__(orca_input.App)
        with mock.patch.object(app, "_resolve_completed_job_rerun_path") as guard:
            self.assertEqual(app._guard_recalculation_path("finished.inp", False), "finished.inp")
            guard.assert_not_called()

    def test_explicit_recalculation_invokes_completed_output_guard(self):
        app = object.__new__(orca_input.App)
        with mock.patch.object(
            app, "_resolve_completed_job_rerun_path", return_value="finished_01.inp"
        ) as guard:
            self.assertEqual(app._guard_recalculation_path("finished.inp", True), "finished_01.inp")
            guard.assert_called_once_with("finished.inp")

    def test_orca_completion_summary_is_minimal(self):
        self.assertEqual(
            orca_input.orca_completion_summary(r"C:\jobs\water_B3LYP_opt.out", True),
            ("water_B3LYP_opt", "Finished successfully"),
        )
        self.assertEqual(
            orca_input.orca_completion_summary("failed_job.out", False),
            ("failed_job", "Failed"),
        )

    def test_completion_dialog_cannot_hide_with_a_modal_grab(self):
        source = inspect.getsource(orca_input.App._show_orca_completion_dialog)
        self.assertNotIn("grab_set", source)
        self.assertNotIn("wait_window", source)
        self.assertIn('attributes("-topmost", True)', source)
        self.assertIn("self.deiconify()", source)

    def test_legacy_gemini_default_migrates_but_explicit_new_choice_remains(self):
        self.assertEqual(orca_input.resolve_saved_ai_web_model({"ai_web_model": "Gemini"}), "ChatGPT")
        self.assertEqual(
            orca_input.resolve_saved_ai_web_model({
                "ai_web_model": "Gemini",
                "ai_web_model_settings_version": orca_input.AI_WEB_MODEL_SETTINGS_VERSION,
            }),
            "Gemini",
        )

    def test_ai_progress_prompt_rejects_empty_output(self):
        with self.assertRaisesRegex(ValueError, "No ORCA output"):
            orca_input.build_orca_progress_prompt("  ")

    def test_ai_progress_reads_full_output_file(self):
        app = object.__new__(orca_input.App)
        app._sync_active_output_buffer = lambda: None
        app.output_buffers = {"monitor": "trimmed monitor"}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "running.out"
            path.write_text("complete output\nlast iteration", encoding="utf-8")
            app.last_output_path = str(path)
            self.assertEqual(app._orca_output_for_ai(), "complete output\nlast iteration")

    def test_tddft_maxcore_batch_failure_is_reported_specifically(self):
        text = (
            "ORCA TD-DFT CALCULATION\n"
            "ORCA finished by error termination in CIS\n"
            "Error (BatchOrganizer): Not a single batch is possible with the present MaxCore\n"
            "aborting the run\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "failed.out"
            out_path.write_text(text, encoding="utf-8")
            ok, reason = orca_input.validate_orca_output_file(str(out_path))
        self.assertFalse(ok)
        self.assertIn("TD-DFT memory failure", reason)
        classified = orca_input.classify_orca_failure_output(text)
        self.assertEqual(classified["category"], "tddft_memory")
        self.assertNotIn("configured executable is not ORCA QM", classified["message"])

    def test_builder_rejects_duplicate_tddft_fragments(self):
        app = object.__new__(orca_input.App)
        app.current_tddft_block = ""
        app.set_tddft_block("%tddft\n  NRoots 5\nend")
        self.assertEqual(app.current_tddft_block.count("%tddft"), 1)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            app.set_tddft_block("%tddft\nend\n%cis\nend")

    def test_tddft_input_save_suggestion_adds_td_dft_tag_when_block_present(self):
        app = object.__new__(orca_input.App)
        app.path_var = self._Var(r"C:\calc\water.xyz")
        app.program_var = self._Var("ORCA")
        app.freeze_all_var = self._Var(False)
        app.freeze_heavy_var = self._Var(False)
        app.job_opt_var = self._Var(False)
        app.job_tddft_var = self._Var(True)
        app.current_tddft_block = "%tddft\n  NRoots 10\nend"
        app.collect = lambda: {"functional": "B3LYP", "basis": "def2-SVP", "solvent_text": ""}

        suggested = Path(app.suggest_input_save_path()).name

        self.assertEqual(suggested, "water_B3LYP_def2-SVP_td-dft_absorption.inp")

        app.current_tddft_settings = {"td_method": "TDA", "excited_state_optimization": True}
        app.current_tddft_block = "%tddft\n  TDA true\nend"
        self.assertEqual(Path(app.suggest_input_save_path()).name, "water_B3LYP_def2-SVP_tda_excited-state-optimization.inp")

    def test_tddft_input_save_suggestion_skips_td_dft_tag_without_block(self):
        app = object.__new__(orca_input.App)
        app.path_var = self._Var(r"C:\calc\water.xyz")
        app.program_var = self._Var("ORCA")
        app.freeze_all_var = self._Var(False)
        app.freeze_heavy_var = self._Var(False)
        app.job_opt_var = self._Var(False)
        app.job_tddft_var = self._Var(True)
        app.current_tddft_block = ""
        app.collect = lambda: {"functional": "B3LYP", "basis": "def2-SVP", "solvent_text": ""}

        suggested = Path(app.suggest_input_save_path()).name

        self.assertEqual(suggested, "water_B3LYP_def2-SVP_sp.inp")

    @unittest.skipIf(os.name == "nt", "POSIX fake executable script")
    def test_openbabel_safe_command_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake = tmp / "obabel"
            log = tmp / "args.txt"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv), encoding='utf-8')\n"
                "print('1')\nprint('converted')\nprint('C 0 0 0')\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            source = tmp / "space unicode alpha.mol"
            source.write_text("fake mol", encoding="utf-8")
            xyz, logs = orca_input.run_openbabel_to_xyz(str(fake), str(source), generate_3d=True)
            self.assertIn("C 0 0 0", xyz)
            args = log.read_text(encoding="utf-8").splitlines()
            self.assertIn(str(source), args)
            self.assertIn("--gen3d", args)
            self.assertTrue(any("return code: 0" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
