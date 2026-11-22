import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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
    assert module.CRYSTAL_HABIT_ICON_PATH.name == "tr_crystal_habit_icon.png"


def test_crystal_habit_exposes_standard_about_content():
    module = load_crystal_habit_module()

    assert callable(module.CrystalHabitApp.open_about_window)
    assert module.GITHUB_URL in module.CITATION_REFERENCE
    assert "CrystalClear" in module.ABOUT_PURPOSE
    assert "CrystalGrower" in module.ABOUT_PURPOSE
    assert module.DOCUMENTATION_URL.endswith("tools/crystal_habit/README.md")
    assert "CrystalClear" in module.CRYSTALCLEAR_REFERENCE
    assert "CrystalGrower/CrystoGen" in module.CRYSTALGROWER_REFERENCE


def test_crystal_habit_accepts_an_initial_cif_path():
    module = load_crystal_habit_module()

    with tempfile.TemporaryDirectory() as directory:
        cif = Path(directory) / "opened structure.cif"
        cif.write_text("data_test\n", encoding="utf-8")

        assert module.normalize_initial_cif(str(cif)) == str(cif.resolve())
        assert module.default_results_folder(str(cif)) == cif.resolve().parent
        assert module.normalize_initial_cif(cif.with_suffix(".xyz")) == ""
        assert module.default_results_folder(None) == module.DEFAULT_OUTPUT


def test_builder_passes_its_open_cif_to_crystal_habit():
    builder = load_builder_module()
    builder_source = inspect.getsource(builder.App._build)

    assert builder.CRYSTAL_HABIT_ICON_PATH.name == "tr_crystal_habit_icon.png"
    assert "_add_header_image_action" in builder_source
    assert "CRYSTAL_HABIT_ICON_PATH" in builder_source
    assert "icon_max_size=88" in builder_source

    class FakePanel:
        def __init__(self, _parent, *, embedded, initial_cif):
            self.embedded = embedded
            self.initial_cif = initial_cif
            self.packed = False
            self.synced_cif = None

        def pack(self, **_kwargs):
            self.packed = True

        def winfo_exists(self):
            return True

        def set_cif_path(self, value):
            self.synced_cif = value

    with tempfile.TemporaryDirectory() as directory:
        cif = Path(directory) / "builder structure.cif"
        cif.write_text("data_builder\n", encoding="utf-8")
        app = object.__new__(builder.App)
        app.structure_source_path = str(cif)
        app.embedded_tool_controllers = {}
        app._embedded_tool_page = lambda key: key
        app._load_embedded_tool_module = lambda *_args: type("Module", (), {"CrystalHabitApp": FakePanel})
        app._restore_workspace_state = lambda: None
        shown = []
        app._show_embedded_workspace = lambda key, title: shown.append((key, title))

        app.launch_crystal_habit()

        panel = app.embedded_tool_controllers["crystal_habit"]
        assert panel.embedded is True
        assert panel.initial_cif == str(cif.resolve())
        assert panel.packed is True
        assert shown == [("crystal_habit", "Crystal Habit Builder")]


def test_builder_reuses_embedded_crystal_habit_panel():
    builder = load_builder_module()

    class ExistingPanel:
        def __init__(self):
            self.synced_cif = "not-called"

        def winfo_exists(self):
            return True

        def set_cif_path(self, value):
            self.synced_cif = value

    app = object.__new__(builder.App)
    panel = ExistingPanel()
    app.structure_source_path = ""
    app.embedded_tool_controllers = {"crystal_habit": panel}
    app._embedded_tool_page = lambda key: key
    app._show_embedded_workspace = lambda *_args: None

    app.launch_crystal_habit()

    assert panel.synced_cif is None


def test_crystal_habit_workspace_action_is_advanced_only():
    builder = load_builder_module()
    source = inspect.getsource(builder.App._set_builder_ui_level)

    assert '("TD-DFT", "Crystal Habit")' in source
    assert "grid_remove" in source


def test_builder_about_dispatches_to_active_embedded_tool():
    builder = load_builder_module()
    calls = []
    module = SimpleNamespace(
        ESP_ICON_PATH=Path("esp.png"),
        ABOUT_PURPOSE="ESP-specific description",
        open_about_dialog=lambda *args: calls.append(args),
    )
    app = object.__new__(builder.App)
    app.active_workspace_key = "esp"
    app.embedded_tool_controllers = {"esp": object()}
    app._embedded_tool_modules = {"esp": module}
    app._open_builder_about_window = lambda: calls.append(("builder",))

    app.open_about_window()

    assert len(calls) == 1
    assert calls[0][1:] == ("VisMap", module.ESP_ICON_PATH, module.ABOUT_PURPOSE)


def test_builder_about_uses_crystal_habit_panel_dialog():
    builder = load_builder_module()
    calls = []
    panel = SimpleNamespace(open_about_window=lambda: calls.append("crystal"))
    app = object.__new__(builder.App)
    app.active_workspace_key = "crystal_habit"
    app.embedded_tool_controllers = {"crystal_habit": panel}
    app._embedded_tool_modules = {}
    app._open_builder_about_window = lambda: calls.append("builder")

    app.open_about_window()

    assert calls == ["crystal"]


def test_external_about_links_use_windows_shell_opener():
    module = load_crystal_habit_module()
    helper_module = sys.modules[module.open_external_url.__module__]

    with mock.patch.object(helper_module.os, "name", "nt"), mock.patch.object(
        helper_module.os, "startfile", create=True
    ) as startfile:
        assert module.open_external_url(module.DOCUMENTATION_URL) is True

    startfile.assert_called_once_with(module.DOCUMENTATION_URL)
