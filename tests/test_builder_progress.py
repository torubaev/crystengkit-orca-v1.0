from pathlib import Path


BUILDER = Path(__file__).resolve().parents[1] / "tools" / "Orca_input" / "orca_input.py"


def test_running_orca_uses_activity_indicator_not_fake_percentage():
    source = BUILDER.read_text(encoding="utf-8")
    assert 'self._set_monitor_activity("ORCA is running; overall completion cannot be estimated")' in source
    assert "self._pulse_monitor_activity()" in source
    assert "self._set_monitor_progress(self._progress_for_orca_stage(stage))" not in source
