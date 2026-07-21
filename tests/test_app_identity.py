import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import app_identity


class FakeWindow:
    def __init__(self):
        self.bindings = {}
        self.destroyed = False
        self.bell_count = 0

    def bind_all(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def after_idle(self, callback):
        callback()

    def destroy(self):
        self.destroyed = True

    def bell(self):
        self.bell_count += 1


class DevReloadShortcutTests(unittest.TestCase):
    def test_ctrl_r_relaunches_same_script_and_arguments_then_closes(self):
        window = FakeWindow()
        script = ROOT / "tools" / "example.py"
        app_identity.install_dev_reload_shortcut(window, script, argv=["--output", "job.out"])

        with mock.patch.object(app_identity.subprocess, "Popen") as popen:
            result = window.bindings["<Control-r>"]()

        self.assertEqual(result, "break")
        self.assertTrue(window.destroyed)
        command = popen.call_args.args[0]
        self.assertEqual(command, [sys.executable, str(script.resolve()), "--output", "job.out"])

    def test_ctrl_r_is_blocked_while_tool_reports_active_work(self):
        window = FakeWindow()
        app_identity.install_dev_reload_shortcut(window, ROOT / "tool.py", can_restart=lambda: False)

        with mock.patch.object(app_identity.subprocess, "Popen") as popen:
            result = window.bindings["<Control-r>"]()

        self.assertEqual(result, "break")
        self.assertFalse(window.destroyed)
        self.assertEqual(window.bell_count, 1)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
