"""Cross-platform window handling shared by PyVista-based tools."""

from __future__ import annotations

import os
import threading
import time
from typing import Any


def save_pyvista_screenshot(plotter: Any, path: str, background: str, **kwargs: Any) -> Any:
    """Save white-background PNGs with alpha, with support for older PyVista."""
    transparent = str(path).lower().endswith(".png") and str(background or "").strip().lower() == "white"
    if transparent:
        try:
            return plotter.screenshot(path, transparent_background=True, **kwargs)
        except TypeError:
            pass
    return plotter.screenshot(path, **kwargs)


def bring_pyvista_window_to_front(plotter: Any, delay_s: float = 0.25) -> None:
    """Best-effort foreground activation for a PyVista render window."""

    def worker() -> None:
        try:
            if delay_s > 0:
                time.sleep(delay_s)
            render_window = getattr(plotter, "ren_win", None) or getattr(plotter, "render_window", None)
            if render_window is None:
                return
            handle = None
            for attr in ("GetGenericWindowId", "GetWindowId"):
                getter = getattr(render_window, attr, None)
                if callable(getter):
                    handle = getter()
                    if handle:
                        break
            if not handle or os.name != "nt":
                return
            hwnd = int(handle)
            import ctypes

            user32 = ctypes.windll.user32
            flags = 0x0001 | 0x0002 | 0x0040
            user32.ShowWindow(hwnd, 5)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()
