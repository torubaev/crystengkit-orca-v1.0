import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "crystal_habit" / "crystal_habit_gui.py"
BUILDER_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"


def load_crystal_habit_module():
    name = "crystal_habit_ui_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_builder_module():
    name = "crystal_habit_builder_handoff_test"
    for directory in (str(ROOT / "tools"), str(BUILDER_PATH.parent)):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    spec = importlib.util.spec_from_file_location(name, BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_crystal_habit_uses_repository_relative_shared_tools():
    module = load_crystal_habit_module()

    assert module.ORCA_TOOLS == ROOT / "tools"
    assert module.CRYSTAL_HABIT_ICON_PATH.is_file()


def test_crystal_habit_exposes_standard_about_content():
    module = load_crystal_habit_module()

    assert callable(module.CrystalHabitApp.open_about_window)
    assert module.GITHUB_URL in module.CITATION_REFERENCE
    assert "CrystalClear" in module.ABOUT_PURPOSE
    assert "CrystalGrower" in module.ABOUT_PURPOSE
    assert module.DOCUMENTATION_URL.endswith("tools/crystal_habit/README.md")


def test_crystal_habit_accepts_an_initial_cif_path():
    module = load_crystal_habit_module()

    with tempfile.TemporaryDirectory() as directory:
        cif = Path(directory) / "opened structure.cif"
        cif.write_text("data_test\n", encoding="utf-8")

        assert module.normalize_initial_cif(str(cif)) == str(cif.resolve())
        assert module.normalize_initial_cif(cif.with_suffix(".xyz")) == ""


def test_builder_passes_its_open_cif_to_crystal_habit():
    builder = load_builder_module()

    with tempfile.TemporaryDirectory() as directory:
        cif = Path(directory) / "builder structure.cif"
        cif.write_text("data_builder\n", encoding="utf-8")
        app = object.__new__(builder.App)
        app.structure_source_path = str(cif)
        launched = []
        app._launch_python_tool = lambda script, input_path=None: launched.append((script, input_path))

        app.launch_crystal_habit()

        assert launched == [(str(builder.DEFAULT_CRYSTAL_HABIT_SCRIPT), str(cif.resolve()))]
