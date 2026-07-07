from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


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
