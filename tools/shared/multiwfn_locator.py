"""Multiwfn executable discovery shared by analysis tools."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional


def auto_detect_multiwfn_path(saved: str = "") -> str:
    """Resolve a saved, environment, conventional, or PATH Multiwfn location."""
    names = ("Multiwfn.exe", "Multiwfn", "multiwfn")
    candidates: list[Path] = []
    for value in (saved, os.environ.get("Multiwfnpath", "")):
        value = str(value or "").strip().strip('"')
        if not value:
            continue
        path = Path(value).expanduser()
        candidates.extend([path / name for name in names] if path.is_dir() else [path])
    for root in (
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
        "C:\\Multiwfn",
        "C:\\Program Files\\Multiwfn",
    ):
        if str(root).strip():
            base = Path(root).expanduser()
            candidates.extend(base / name for name in names)
            candidates.extend(base / "Multiwfn" / name for name in names)
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return str(resolved)
    return ""


def find_multiwfn() -> Optional[str]:
    candidates = [
        r"C:\Multiwfn_2026.2.2_bin_Win64\Multiwfn.exe",
        r"C:\Multiwfn\Multiwfn.exe",
        r"C:\Multiwfn_3.8_dev_bin_Win64\Multiwfn.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return shutil.which("Multiwfn") or shutil.which("Multiwfn.exe") or shutil.which("multiwfn")


def likely_multiwfn_search_roots() -> list[Path]:
    roots: list[Path] = []
    home = Path.home()

    def add(path: Path) -> None:
        try:
            if path.exists() and path.is_dir():
                roots.append(path)
        except OSError:
            pass

    for item in [
        Path.cwd(),
        Path(__file__).resolve().parents[1],
        home / "Desktop",
        home / "Downloads",
        home / "Documents",
        home / "Applications",
        home / "bin",
        home / ".local" / "bin",
    ]:
        add(item)

    if os.name == "nt":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            env_value = os.environ.get(env_name)
            if env_value:
                env_path = Path(env_value)
                add(env_path)
                try:
                    for item in env_path.glob("*Multiwfn*"):
                        add(item)
                    for item in env_path.glob("*multiwfn*"):
                        add(item)
                except OSError:
                    pass
        add(Path("C:/"))
    else:
        for item in [Path("/"), Path("/opt"), Path("/usr/local"), Path("/usr/local/bin"), Path("/usr/bin")]:
            add(item)

    unique: list[Path] = []
    seen = set()
    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except OSError:
            key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_multiwfn_deep(max_seconds: float = 18.0, max_visited: int = 70000, max_depth: int = 6) -> Optional[str]:
    quick = find_multiwfn()
    if quick:
        return quick

    target_names = {"multiwfn", "multiwfn.exe"}
    skip_dirs = {
        "$Recycle.Bin", ".git", ".hg", ".svn", "__pycache__", "node_modules",
        "System Volume Information", "Windows", "WinSxS", "Microsoft", "Packages", "Temp", "tmp",
    }
    started = time.monotonic()
    visited = 0

    def timed_out() -> bool:
        return (time.monotonic() - started) > max_seconds

    def scan(folder: Path, depth: int) -> Optional[str]:
        nonlocal visited
        if timed_out() or visited >= max_visited or depth > max_depth:
            return None
        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except (OSError, PermissionError):
            return None
        for entry in entries:
            if timed_out() or visited >= max_visited:
                return None
            visited += 1
            try:
                if entry.is_file(follow_symlinks=False) and entry.name.lower() in target_names:
                    return str(Path(entry.path).resolve())
                if entry.is_dir(follow_symlinks=False) and entry.name not in skip_dirs:
                    found = scan(Path(entry.path), depth + 1)
                    if found:
                        return found
            except (OSError, PermissionError):
                continue
        return None

    for root in likely_multiwfn_search_roots():
        found = scan(root, 0)
        if found:
            return found
        if timed_out():
            break
    return None
