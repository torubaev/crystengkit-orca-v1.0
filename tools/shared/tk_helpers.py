"""Small Tk behaviors shared by the standalone tool windows."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Any, Optional


def executable_filetypes(label: str = "Executable") -> list[tuple[str, str]]:
    """Return a native executable filter without hiding Unix executables."""
    if os.name == "nt":
        return [(label, "*.exe"), ("All files", "*.*")]
    return [(label, "*"), ("All files", "*")]


def configure_builder_ui_style(widget: tk.Misc) -> None:
    """Apply the common CrystEngKit control-panel theme."""
    install_edit_context_menu(widget)
    style = ttk.Style(widget)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    try:
        widget.configure(background="#f4f6f9")
    except tk.TclError:
        pass

    style.configure("TFrame", background="#f4f6f9")
    style.configure("Panel.TFrame", background="#f4f6f9")
    style.configure("Header.TFrame", background="#1e3a5f")
    style.configure("HeaderTitle.TLabel", background="#1e3a5f", foreground="#f8fafc", font=("Segoe UI", 15, "bold"))
    style.configure("HeaderSub.TLabel", background="#1e3a5f", foreground="#d7e1ee", font=("Segoe UI", 10, "bold"))
    style.configure("HeaderAction.TLabel", background="#1e3a5f", foreground="#d7e1ee", font=("Segoe UI", 9, "bold"))
    style.configure("HeaderLink.TLabel", background="#1e3a5f", foreground="#ffffff", font=("Segoe UI", 11, "bold"))
    style.configure("TLabelframe", background="#f8fafc", bordercolor="#d8dee8", relief="solid", padding=8)
    style.configure("TLabelframe.Label", background="#f8fafc", foreground="#172033", font=("Segoe UI", 10, "bold"))
    style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
    style.configure("Primary.TButton", padding=(14, 8), font=("Segoe UI", 10, "bold"))
    style.configure(
        "HeaderCTA.TButton",
        background="#2f80c8",
        foreground="#ffffff",
        bordercolor="#61a5e8",
        lightcolor="#2f80c8",
        darkcolor="#2f80c8",
        focusthickness=0,
        padding=(14, 7),
        relief="flat",
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "HeaderCTA.TButton",
        background=[("active", "#3b94df"), ("pressed", "#1f68a8")],
        foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        bordercolor=[("active", "#8ac4f4"), ("pressed", "#1f68a8")],
    )
    style.configure("Info.TButton", padding=(3, 1), font=("Segoe UI", 9, "bold"))
    style.configure("TCheckbutton", background="#f8fafc", padding=(1, 2), font=("Segoe UI", 9))
    style.configure("TLabel", background="#f8fafc", foreground="#263348", padding=(1, 1), font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background="#f4f6f9", foreground="#53627a", font=("Segoe UI", 9))
    style.configure(
        "Blue.Horizontal.TProgressbar",
        troughcolor="#dbeafe",
        background="#2563eb",
        lightcolor="#3b82f6",
        darkcolor="#1d4ed8",
        bordercolor="#93c5fd",
        thickness=14,
    )


def install_edit_context_menu(widget: tk.Misc) -> None:
    """Install one standard Cut/Copy/Paste menu for editable Tk widgets.

    The binding is attached once per Tk interpreter and therefore also covers
    entries and text areas created later in child tool windows.
    """
    root = widget._root()
    marker = "_crystengkit_edit_context_menu_installed"
    if getattr(root, marker, False):
        return
    setattr(root, marker, True)

    menu = tk.Menu(root, tearoff=False)
    current: dict[str, Optional[tk.Misc]] = {"widget": None}

    def target_widget() -> Optional[tk.Misc]:
        return current["widget"]

    def send(sequence: str) -> None:
        target = target_widget()
        if target is not None:
            try:
                target.event_generate(sequence)
            except tk.TclError:
                pass

    def select_all() -> None:
        target = target_widget()
        if target is None:
            return
        try:
            if isinstance(target, tk.Text):
                target.tag_add("sel", "1.0", "end-1c")
                target.mark_set("insert", "1.0")
                target.see("insert")
            else:
                target.selection_range(0, "end")
                target.icursor("end")
        except (tk.TclError, AttributeError):
            pass

    menu.add_command(label="Cut", accelerator="Ctrl+X", command=lambda: send("<<Cut>>"))
    menu.add_command(label="Copy", accelerator="Ctrl+C", command=lambda: send("<<Copy>>"))
    menu.add_command(label="Paste", accelerator="Ctrl+V", command=lambda: send("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", accelerator="Ctrl+A", command=select_all)

    def has_selection(target: tk.Misc) -> bool:
        try:
            if isinstance(target, tk.Text):
                return bool(target.tag_ranges("sel"))
            return bool(target.selection_present())
        except (tk.TclError, AttributeError):
            return False

    def is_editable(target: tk.Misc) -> bool:
        try:
            return str(target.cget("state")) == "normal"
        except tk.TclError:
            return True

    def show(event):
        target = event.widget
        supported = isinstance(target, (tk.Text, tk.Entry, tk.Spinbox, ttk.Entry, ttk.Combobox, ttk.Spinbox))
        if not supported:
            return None
        current["widget"] = target
        try:
            target.focus_set()
        except tk.TclError:
            pass
        selected = has_selection(target)
        editable = is_editable(target)
        try:
            target.clipboard_get()
            can_paste = editable
        except tk.TclError:
            can_paste = False
        menu.entryconfigure("Cut", state="normal" if selected and editable else "disabled")
        menu.entryconfigure("Copy", state="normal" if selected else "disabled")
        menu.entryconfigure("Paste", state="normal" if can_paste else "disabled")
        menu.entryconfigure("Select All", state="normal")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    root.bind_all("<Button-3>", show, add="+")


def load_header_icon(path: Any, max_size: int = 56) -> Optional[tk.PhotoImage]:
    """Load and integer-downsample a Tk header icon if it exists."""
    if not path.is_file():
        return None
    image = tk.PhotoImage(file=str(path))
    factor = max(1, int(max(image.width() / max_size, image.height() / max_size) + 0.999))
    return image.subsample(factor, factor) if factor > 1 else image


def keep_entry_end_visible(entry: tk.Entry, variable: Optional[tk.Variable] = None) -> tk.Entry:
    """Keep the end of a long entry value visible after layout and edits."""

    def show_end(*_args) -> None:
        try:
            entry.icursor("end")
            entry.xview_moveto(1.0)
        except tk.TclError:
            pass

    entry.bind("<Configure>", lambda _event: entry.after_idle(show_end), add="+")
    entry.bind("<FocusOut>", lambda _event: entry.after_idle(show_end), add="+")
    if variable is not None:
        variable.trace_add("write", lambda *_args: entry.after_idle(show_end))
    entry.after_idle(show_end)
    return entry


def bind_mousewheel_to_canvas(canvas: tk.Canvas, *_hover_widgets: tk.Misc) -> None:
    """Scroll a canvas only while the pointer is over a scrollable region."""

    def pointer_is_over_canvas() -> bool:
        try:
            x = canvas.winfo_pointerx()
            y = canvas.winfo_pointery()
            left = canvas.winfo_rootx()
            top = canvas.winfo_rooty()
            return left <= x < left + canvas.winfo_width() and top <= y < top + canvas.winfo_height()
        except tk.TclError:
            return False

    def can_scroll() -> bool:
        try:
            first, last = canvas.yview()
            return first > 0.0 or last < 1.0
        except tk.TclError:
            return False

    def wheel_units(event) -> int:
        if getattr(event, "num", None) == 4:
            return -5
        if getattr(event, "num", None) == 5:
            return 5
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return 0
        if abs(delta) >= 120:
            return int(-delta / 120) * 5
        return -5 if delta > 0 else 5

    def on_mousewheel(event):
        if not pointer_is_over_canvas() or not can_scroll():
            return None
        units = wheel_units(event)
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

    canvas.bind_all("<MouseWheel>", on_mousewheel, add="+")
    canvas.bind_all("<Button-4>", on_mousewheel, add="+")
    canvas.bind_all("<Button-5>", on_mousewheel, add="+")
