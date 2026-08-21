import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parsed(relative: str):
    return ast.parse((ROOT / relative).read_text(encoding="utf-8"))


def class_bases(tree, name: str):
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name)
    return [ast.unparse(base) for base in node.bases]


def function_parameters(tree, name: str):
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return [argument.arg for argument in (*node.args.args, *node.args.kwonlyargs)]


class EmbeddedToolContractTests(unittest.TestCase):
    def test_class_based_tools_are_frames(self):
        cases = (
            ("tools/HOMO_LUMO/HOMO_LUMO_v2.py", "App"),
            ("tools/qtaim-cp/qtaim.py", "QTAIMGui"),
            ("tools/TD_DFT/td_dft_module.py", "TDDFTPanel"),
            ("tools/torsion_generator/torsion_generator_gui.py", "TorsionGeneratorPanel"),
        )
        for relative, class_name in cases:
            with self.subTest(tool=relative):
                self.assertIn("ttk.Frame", class_bases(parsed(relative), class_name))

    def test_procedural_esp_has_embedded_launcher_contract(self):
        parameters = function_parameters(parsed("tools/VisMap_5.0/VisMap5.6_pyvista.py"), "launch_gui")
        self.assertIn("parent", parameters)
        self.assertIn("embedded", parameters)
        self.assertIn("run_mainloop", parameters)

    def test_nci_controller_accepts_embedded_mode(self):
        tree = parsed("tools/NCI_plot/nci_plotter.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "NCIPlotterApp")
        init = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__")
        parameters = [argument.arg for argument in (*init.args.args, *init.args.kwonlyargs)]
        self.assertIn("embedded", parameters)

    def test_nci_opacity_updates_only_the_surface_actor(self):
        tree = parsed("tools/NCI_plot/nci_plotter.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "NCIPlotterApp")
        methods = {
            item.name: ast.unparse(item)
            for item in node.body
            if isinstance(item, ast.FunctionDef)
        }
        opacity_update = methods["_apply_surface_opacity"]
        self.assertIn("self.nci_surface_actor.GetProperty()", opacity_update)
        self.assertIn("prop.SetOpacity(opacity)", opacity_update)
        self.assertNotIn("self.update_plot", opacity_update)
        self.assertNotIn("self.plotter.clear", opacity_update)

    def test_nci_open_controls_repairs_the_viewer_pair_without_generation(self):
        tree = parsed("tools/NCI_plot/nci_plotter.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "NCIPlotterApp")
        method = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "open_viewer_and_controls"
        )
        source = ast.unparse(method)
        self.assertIn("self.is_plotter_alive()", source)
        self.assertIn("self.viewer_controls_are_visible()", source)
        self.assertIn("self.update_plot()", source)
        self.assertIn("self.load_cubes_and_plot()", source)
        self.assertIn("self.show_viewer_controls()", source)
        self.assertNotIn("self.start_generate_nci", source)

    def test_nci_plotter_liveness_checks_native_vtk_window_state(self):
        tree = parsed("tools/NCI_plot/nci_plotter.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "NCIPlotterApp")
        method = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "is_plotter_alive"
        )
        source = ast.unparse(method)
        self.assertIn("_closed", source)
        self.assertIn("GetDone", source)
        self.assertIn("GetInitialized", source)
        self.assertIn("GetMapped", source)

    def test_tool_panels_publish_explicit_state_contracts(self):
        cases = (
            ("tools/HOMO_LUMO/HOMO_LUMO_v2.py", "App"),
            ("tools/NCI_plot/nci_plotter.py", "NCIPlotterApp"),
            ("tools/qtaim-cp/qtaim.py", "QTAIMGui"),
        )
        for relative, class_name in cases:
            tree = parsed(relative)
            node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name)
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            self.assertIn("get_state", methods)
            self.assertIn("set_state", methods)

    def test_embedded_homo_lumo_does_not_consume_builder_process_arguments(self):
        tree = parsed("tools/HOMO_LUMO/HOMO_LUMO_v2.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "App")
        method = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "_load_startup_file"
        )
        source = ast.unparse(method)
        self.assertIn("not self.embedded and len(sys.argv) >= 2", source)

    def test_builder_uses_one_responsive_layout_on_all_platforms(self):
        source = (ROOT / "tools/Orca_input/orca_input.py").read_text(encoding="utf-8")
        self.assertNotIn("is_linux_desktop", source)
        self.assertIn("body.columnconfigure(0, weight=2, minsize=620)", source)
        self.assertIn("body.columnconfigure(1, weight=1, minsize=320)", source)

    def test_qtaim_overlay_uses_the_matching_nci_output_folder(self):
        tree = parsed("tools/qtaim-cp/qtaim.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "QTAIMGui")
        method = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "open_nci_qtaim_overlay"
        )
        source = ast.unparse(method)
        self.assertIn("{wavefunction_path.stem}_NCI", source)
        self.assertIn("func2.cub", source)
        self.assertIn("func1.cub", source)
        self.assertIn("--rdg", source)
        self.assertIn("--signrho", source)

    def test_qtaim_open_controls_repairs_the_viewer_pair_without_multiwfn(self):
        tree = parsed("tools/qtaim-cp/qtaim.py")
        node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "QTAIMGui")
        method = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "open_viewer_and_controls"
        )
        source = ast.unparse(method)
        self.assertIn("self.is_plotter_alive()", source)
        self.assertIn("self.viewer_controls_are_visible()", source)
        self.assertIn("self.update_plot()", source)
        self.assertIn("self.show_viewer_controls()", source)
        self.assertNotIn("run_multiwfn", source)

        alive = next(
            item for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name == "is_plotter_alive"
        )
        alive_source = ast.unparse(alive)
        self.assertIn("GetDone", alive_source)
        self.assertIn("GetMapped", alive_source)


if __name__ == "__main__":
    unittest.main()
