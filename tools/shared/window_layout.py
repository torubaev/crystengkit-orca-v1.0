"""Predictable side-by-side placement for Tk controls and PyVista windows."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Tuple


@dataclass(frozen=True)
class VisualizationWindowLayout:
    control_geometry: Tuple[int, int, int, int]
    viewer_geometry: Tuple[int, int, int, int]

    @property
    def viewer_size(self) -> Tuple[int, int]:
        return self.viewer_geometry[2], self.viewer_geometry[3]


def _monitor_work_area(widget) -> Tuple[int, int, int, int]:
    """Return the usable monitor rectangle containing *widget*."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            widget.update_idletasks()
            hwnd = int(widget.winfo_id())
            user32 = ctypes.windll.user32
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.MonitorFromWindow.restype = ctypes.c_void_p
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            monitor = user32.MonitorFromWindow(hwnd, 2)  # nearest monitor
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                return int(work.left), int(work.top), int(work.right), int(work.bottom)
        except Exception:
            pass

    try:
        widget.update_idletasks()
        left = int(widget.winfo_vrootx())
        top = int(widget.winfo_vrooty())
        return (
            left,
            top,
            left + int(widget.winfo_vrootwidth()),
            top + int(widget.winfo_vrootheight()),
        )
    except Exception:
        return 0, 0, 1920, 1040


def compute_visualization_layout(
    parent,
    *,
    control_width: int,
    control_height: int,
    margin: int = 12,
    gap: int = 10,
    minimum_viewer_width: int = 560,
) -> VisualizationWindowLayout:
    """Tile a narrow control window left of a top-aligned PyVista viewer."""
    left, top, right, bottom = _monitor_work_area(parent)
    work_width = max(1, right - left)
    work_height = max(1, bottom - top)
    usable_height = max(320, work_height - 2 * margin)

    max_control_width = max(300, work_width - minimum_viewer_width - gap - 2 * margin)
    actual_control_width = min(max(300, int(control_width)), max_control_width)
    control_x = left + margin
    control_y = top + margin
    actual_control_height = min(max(320, int(control_height)), usable_height)

    viewer_x = control_x + actual_control_width + gap
    viewer_y = control_y
    viewer_width = max(minimum_viewer_width, right - margin - viewer_x)
    viewer_width = min(viewer_width, max(1, right - viewer_x))
    viewer_height = usable_height

    return VisualizationWindowLayout(
        control_geometry=(control_x, control_y, actual_control_width, actual_control_height),
        viewer_geometry=(viewer_x, viewer_y, viewer_width, viewer_height),
    )


def place_visualization_windows(control_window, plotter, layout: VisualizationWindowLayout) -> None:
    """Apply a computed layout without changing either window's visibility."""
    try:
        x, y, width, height = layout.control_geometry
        control_window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        pass

    try:
        x, y, width, height = layout.viewer_geometry
        render_window = getattr(plotter, "ren_win", None) or getattr(plotter, "render_window", None)
        if render_window is not None:
            render_window.SetSize(int(width), int(height))
            render_window.SetPosition(int(x), int(y))
    except Exception:
        pass
