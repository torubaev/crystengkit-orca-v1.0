"""Standard stacked-page navigation for the single-window Builder GUI."""
from __future__ import annotations

from typing import Callable, Dict, Optional


class StackedPageController:
    """Mount pages once in one grid cell and switch them with ``tkraise``."""

    def __init__(self, on_change: Optional[Callable[[str, str], None]] = None):
        self._pages: Dict[str, object] = {}
        self._titles: Dict[str, str] = {}
        self._active_key = ""
        self._on_change = on_change

    @property
    def active_key(self) -> str:
        return self._active_key

    def register(self, key: str, title: str, page):
        key, title = str(key).strip(), str(title).strip()
        if not key or not title:
            raise ValueError("Page key and title must be non-empty.")
        if key in self._pages:
            raise ValueError(f"Page is already registered: {key}")
        page.grid(row=0, column=0, sticky="nsew")
        self._pages[key] = page
        self._titles[key] = title
        if self._active_key:
            self._pages[self._active_key].tkraise()
        return page

    def page(self, key: str):
        return self._pages.get(key)

    def show(self, key: str):
        if key not in self._pages:
            raise KeyError(f"Unknown workspace page: {key}")
        if self._active_key and self._active_key != key:
            self._call(self._pages[self._active_key], "on_hide")
        page = self._pages[key]
        page.tkraise()
        self._call(page, "on_show")
        self._active_key = key
        if self._on_change is not None:
            self._on_change(key, self._titles[key])
        return page

    def keys(self) -> tuple[str, ...]:
        return tuple(self._pages)

    @staticmethod
    def _call(page, method_name: str) -> None:
        callback = getattr(page, method_name, None)
        if callable(callback):
            callback()
