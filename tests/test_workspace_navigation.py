import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1] / "tools" / "Orca_input"
sys.path.insert(0, str(MODULE_DIR))

from workspace_navigation import StackedPageController  # noqa: E402


class FakePage:
    def __init__(self):
        self.events = []

    def grid(self, **kwargs):
        self.events.append(("grid", kwargs))

    def tkraise(self):
        self.events.append(("raise", None))

    def on_show(self):
        self.events.append(("show", None))

    def on_hide(self):
        self.events.append(("hide", None))


class StackedPageControllerTests(unittest.TestCase):
    def test_pages_mount_once_and_switch_with_raise(self):
        changes = []
        controller = StackedPageController(lambda key, title: changes.append((key, title)))
        builder, esp = FakePage(), FakePage()
        controller.register("builder", "Builder", builder)
        controller.register("esp", "ESP", esp)
        controller.show("builder")
        controller.show("esp")
        self.assertEqual(controller.active_key, "esp")
        self.assertEqual(sum(event[0] == "grid" for event in builder.events), 1)
        self.assertEqual(sum(event[0] == "grid" for event in esp.events), 1)
        self.assertIn(("hide", None), builder.events)
        self.assertEqual(esp.events[-2:], [("raise", None), ("show", None)])
        self.assertEqual(changes, [("builder", "Builder"), ("esp", "ESP")])

    def test_duplicate_and_unknown_pages_are_rejected(self):
        controller = StackedPageController()
        controller.register("builder", "Builder", FakePage())
        with self.assertRaises(ValueError):
            controller.register("builder", "Again", FakePage())
        with self.assertRaises(KeyError):
            controller.show("missing")


if __name__ == "__main__":
    unittest.main()
