from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence


TOOLS_ROOT = Path(__file__).resolve().parent
DEFAULT_APP_ICON = TOOLS_ROOT / "images" / "orca_builder.ico"
DEFAULT_APPUSERMODELID = "Torubaev.CrystEngKitORCA"


def set_windows_app_id(suffix: str = "") -> None:
    if os.name != "nt":
        return
    app_id = DEFAULT_APPUSERMODELID
    if suffix:
        clean = "".join(ch for ch in str(suffix) if ch.isalnum() or ch in "._-")
        if clean:
            app_id = f"{app_id}.{clean}"
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def apply_tk_icon(window, icon_path: Optional[Path] = None) -> None:
    path = Path(icon_path or DEFAULT_APP_ICON)
    if os.name == "nt" and path.is_file():
        try:
            window.iconbitmap(default=str(path))
        except Exception:
            pass


def configure_tk_window_identity(window, suffix: str = "", icon_path: Optional[Path] = None) -> None:
    set_windows_app_id(suffix)
    apply_tk_icon(window, icon_path)


def install_dev_reload_shortcut(
    window,
    script_path: Path,
    *,
    can_restart: Optional[Callable[[], bool]] = None,
    argv: Optional[Sequence[str]] = None,
) -> None:
    """Install the hidden Ctrl+R developer shortcut on a primary Tk window."""
    script = Path(script_path).resolve()
    launch_args = list(sys.argv[1:] if argv is None else argv)

    def restart_tool(_event=None):
        if can_restart is not None and not can_restart():
            try:
                window.bell()
            except Exception:
                pass
            return "break"
        command = [sys.executable, str(script), *launch_args]
        kwargs = {"cwd": os.getcwd()}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(command, **kwargs)
        except Exception:
            try:
                window.bell()
            except Exception:
                pass
            return "break"
        try:
            window.after_idle(window.destroy)
        except Exception:
            window.destroy()
        return "break"

    window.bind_all("<Control-r>", restart_tool, add="+")
