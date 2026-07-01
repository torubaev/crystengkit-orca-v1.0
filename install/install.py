#!/usr/bin/env python3
"""
Short HTML + terminal Installation Checker for ORCA Input Builder / VisMap

For common users:
- Checks Python version.
- Checks required/recommended Python packages.
- If Python packages are missing, asks permission:
      Install missing Python packages now? [Y/n]
  Press Enter = Yes.
- Installs approved Python packages; on Linux, pip progress is shown in the terminal.
- Checks whether ORCA, Multiwfn, and Gaussian are visible from the command line.
- If ORCA or Multiwfn are not visible from PATH, searches likely local folders.
- Creates installation_report.html and opens it in the default web browser.
- Also prints a concise report in the command prompt / terminal.

Report design:
- The first visible HTML report is intentionally very short.
- It shows only components that are truly missing, meaning not detected in PATH
  and not found locally by the bounded local search.
- Components found locally but not in PATH are placed under "Details...".
- Full status, links, and notes are available under the collapsible "Details..." section.

Run:
    python install.py

Optional:
    python install.py --no-open
"""

from __future__ import annotations

import datetime as _dt
import html
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Union


REQUIRED_PACKAGES = ["numpy", "pyvista", "matplotlib", "periodictable"]
RECOMMENDED_PACKAGES = ["gemmi", "Pillow"]
PACKAGE_IMPORT_NAMES = {
    "Pillow": "PIL",
}

SETTINGS_FILENAME = "orca_gaussian_builder_settings.json"
VENV_DIR_NAME = ".venv"
PROJECT_MAIN_SCRIPT = Path("tools") / "Orca_input" / "orca_input.py"
PROJECT_ICON = Path("tools") / "images" / "orca_builder.ico"
DESKTOP_SHORTCUT_NAME = "ORCA input builder.lnk"
EXPECTED_PROJECT_ITEMS = [
    PROJECT_MAIN_SCRIPT,
    Path("tools") / "HOMO_LUMO" / "HOMO_LUMO_v2.py",
    Path("tools") / "VisMap_5.0" / "VisMap5.6_pyvista.py",
    Path("tools") / "NCI_plot" / "nci_plotter.py",
    Path("tools") / "NCI_QTAIM_overlay" / "nci_qtaim_overlay.py",
    Path("tools") / "qtaim-cp" / "qtaim.py",
]

OFFICIAL_LINKS = {
    "ORCA": [
        ("ORCA official page", "https://www.faccts.de/orca/"),
        ("ORCA official installation guide", "https://www.faccts.de/docs/orca/6.0/tutorials/first_steps/install.html"),
        ("ORCA downloads / forum", "https://orcaforum.kofo.mpg.de/app.php/dlext/"),
    ],
    "Multiwfn": [
        ("Multiwfn official page", "https://sobereva.com/multiwfn/"),
        ("Multiwfn official download page", "https://sobereva.com/multiwfn/download.html"),
    ],
}

MULTIWFN_SECURITY_NOTE = """
Some browsers or antivirus programs may flag the Multiwfn website or downloaded archive as unsafe.
Do not switch off antivirus protection just to force the download. First check that the address is the
official Multiwfn/Sobereva page, download only from the official page, scan the downloaded archive,
and ask local IT support if this is a work/institutional computer. If the warning looks serious or the
source is uncertain, stop and do not install it.
"""

EXTERNAL_SOFTWARE = {
    "ORCA": {
        "executables": ["orca", "orca.exe"],
        "required": True,
        "message": "ORCA was not detected from the command line.",
    },
    "Multiwfn": {
        "executables": ["Multiwfn", "Multiwfn.exe", "multiwfn"],
        "required": True,
        "message": "Multiwfn was not detected from the command line.",
    },
    "Gaussian": {
        "executables": ["g16", "g16.exe", "g09", "g09.exe"],
        "required": False,
        "message": "Gaussian was not detected. This matters only if you plan to use Gaussian-related features.",
    },
}

LOCAL_SEARCH_PROGRAMS = {"ORCA", "Multiwfn"}

LOCAL_SEARCH_SKIP_DIRS = {
    "$Recycle.Bin",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    "System Volume Information",
    "Windows",
    "WinSxS",
    "Microsoft",
    "Packages",
    "Temp",
    "tmp",
}

GNOME_ORCA_REJECTION_MARKERS = (
    "EVENT MANAGER",
    "PYATSPI",
    "DIST-PACKAGES/ORCA",
    "DIST-PACKAGES\\ORCA",
    "GNOME ORCA",
    "SCREEN READER",
    "ACCESSIBILITY",
)
ORCA_QM_IDENTITY_MARKERS = (
    "PROGRAM ORCA",
    "O   R   C   A",
    "ORCA VERSION",
    "ORCA TERMINATED",
    "FACCTS",
    "FRANK NEESE",
    "MAX-PLANCK",
)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def ask_yes_no_default_yes(question: str) -> bool:
    while True:
        answer = input(f"{question} [Y/n]: ").strip().lower()
        if answer == "":
            return True
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please type Y or N. Press Enter for Yes.")


def has_arg(name: str) -> bool:
    return name in sys.argv[1:]


def arg_value(prefix: str) -> str:
    needle = prefix + "="
    for arg in sys.argv[1:]:
        if arg.startswith(needle):
            return arg[len(needle):]
    return ""


def venv_python_path(base_dir: Path) -> Path:
    if platform.system() == "Windows":
        return base_dir / VENV_DIR_NAME / "Scripts" / "python.exe"
    return base_dir / VENV_DIR_NAME / "bin" / "python"


def create_venv_and_reexec(base_dir: Path) -> Dict[str, object]:
    venv_dir = base_dir / VENV_DIR_NAME
    venv_python = venv_python_path(base_dir)
    info: Dict[str, object] = {
        "requested": True,
        "ok": False,
        "created": False,
        "path": str(venv_dir),
        "python": str(venv_python),
        "message": "",
    }

    if not venv_python.is_file():
        print()
        print(f"Creating local Python environment: {venv_dir}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                timeout=300,
                errors="replace",
            )
        except Exception as exc:
            info["message"] = f"Could not create virtual environment: {type(exc).__name__}: {exc}"
            return info
        if result.returncode != 0:
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            info["message"] = f"Could not create virtual environment. {output[-1200:]}"
            return info
        info["created"] = True

    if not venv_python.is_file():
        info["message"] = f"Virtual environment Python was not found: {venv_python}"
        return info

    command = [
        str(venv_python),
        str(Path(__file__).resolve()),
        "--using-venv",
        f"--project-root={base_dir}",
    ]
    if has_arg("--no-open"):
        command.append("--no-open")

    print(f"Continuing setup inside local environment: {venv_python}")
    result = subprocess.run(command)
    raise SystemExit(result.returncode)


def is_project_root(path: Path) -> bool:
    return all((path / item).exists() for item in EXPECTED_PROJECT_ITEMS)


def browse_for_installation_location(default_root: Path) -> Path:
    """
    Ask the user to choose the CrystEngKit installation folder.

    The folder is where this checker writes local settings and where the main
    app scripts are expected to live.
    """
    default_root = default_root.resolve()
    print()
    print("Choose the CrystEngKit installation folder.")
    print(f"Suggested folder: {default_root}")

    selected = ""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askdirectory(
            title="Select CrystEngKit installation folder",
            initialdir=str(default_root if default_root.exists() else Path.home()),
            mustexist=True,
        )
        root.destroy()
    except Exception as exc:
        print(f"Folder browser could not be opened: {type(exc).__name__}: {exc}")

    if not selected:
        typed = input("Folder path (press Enter to use the suggested folder): ").strip().strip('"')
        selected = typed or str(default_root)

    chosen = Path(selected).expanduser().resolve()
    if not is_project_root(chosen):
        print()
        print("WARNING: The selected folder does not look like a complete CrystEngKit folder.")
        print("Expected to find:")
        for item in EXPECTED_PROJECT_ITEMS:
            print(f"  - {item}")
        if not ask_yes_no_default_yes("Continue with this folder anyway?"):
            return browse_for_installation_location(default_root)

    return chosen


def package_found(package: str) -> bool:
    import_name = PACKAGE_IMPORT_NAMES.get(package, package)
    return importlib.util.find_spec(import_name) is not None


def package_version(package: str) -> str:
    try:
        import importlib.metadata as importlib_metadata
        return importlib_metadata.version(package)
    except Exception:
        return ""


def tkinter_install_hint() -> str:
    system = platform.system().lower()
    if system == "linux":
        return (
            "Tkinter is missing. Install the Linux Tk package for your Python, for example: "
            "sudo apt install python3-tk  |  sudo dnf install python3-tkinter  |  "
            "sudo pacman -S tk  |  sudo zypper install python3-tk"
        )
    if system == "darwin":
        return (
            "Tkinter is missing. Install a Python build that includes Tcl/Tk, for example from python.org, "
            "or install tkinter support through your Python distribution."
        )
    return "Tkinter is missing. Reinstall Python with Tcl/Tk support enabled."


def check_tkinter() -> Dict[str, object]:
    try:
        import tkinter  # noqa: F401
        return {"ok": True, "message": "Tkinter is available."}
    except Exception as exc:
        return {
            "ok": False,
            "message": tkinter_install_hint(),
            "error": f"{type(exc).__name__}: {exc}",
        }


def install_package(package: str, show_progress: bool = False) -> Dict[str, object]:
    command = [sys.executable, "-m", "pip", "install", package]
    try:
        if show_progress:
            result = subprocess.run(
                command,
                timeout=600,
                errors="replace",
            )
            return {
                "package": package,
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "output": "",
            }

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            errors="replace",
        )
        return {
            "package": package,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "output": ((result.stdout or "") + "\n" + (result.stderr or "")).strip()[-2000:],
        }
    except Exception as exc:
        return {
            "package": package,
            "ok": False,
            "returncode": -1,
            "output": f"{type(exc).__name__}: {exc}",
        }


def check_and_optionally_install_python_packages() -> Dict[str, object]:
    all_known_packages = REQUIRED_PACKAGES + RECOMMENDED_PACKAGES

    initially_missing_required = [pkg for pkg in REQUIRED_PACKAGES if not package_found(pkg)]
    initially_missing_recommended = [pkg for pkg in RECOMMENDED_PACKAGES if not package_found(pkg)]
    initially_missing_all = initially_missing_required + initially_missing_recommended

    installed_now: List[str] = []
    install_failures: List[Dict[str, object]] = []
    user_declined = False

    if initially_missing_all:
        print()
        print("Missing Python packages:")
        for pkg in initially_missing_required:
            print(f"  - {pkg}  (required)")
        for pkg in initially_missing_recommended:
            print(f"  - {pkg}  (recommended)")

        if ask_yes_no_default_yes("Install missing Python packages now?"):
            show_progress = platform.system().lower() == "linux"
            if show_progress:
                print("Installing missing Python packages. Progress will be shown below.")
            else:
                print("Installing missing Python packages. Details are hidden unless something fails.")
            for pkg in initially_missing_all:
                result = install_package(pkg, show_progress=show_progress)
                if result["ok"]:
                    installed_now.append(pkg)
                    print(f"  OK: {pkg}")
                else:
                    install_failures.append(result)
                    print(f"  FAILED: {pkg}")
        else:
            user_declined = True
            print("Installation skipped by user.")

    final_missing_required = [pkg for pkg in REQUIRED_PACKAGES if not package_found(pkg)]
    final_missing_recommended = [pkg for pkg in RECOMMENDED_PACKAGES if not package_found(pkg)]

    final_installed = {
        pkg: package_version(pkg)
        for pkg in all_known_packages
        if package_found(pkg)
    }

    return {
        "initially_missing_required": initially_missing_required,
        "initially_missing_recommended": initially_missing_recommended,
        "installed_now": installed_now,
        "install_failures": install_failures,
        "user_declined": user_declined,
        "final_missing_required": final_missing_required,
        "final_missing_recommended": final_missing_recommended,
        "final_installed": final_installed,
    }


def detect_external_program(executables: List[str]) -> Optional[str]:
    for exe in executables:
        resolved = shutil.which(exe)
        if resolved:
            return resolved
    return None


def _looks_like_gnome_orca(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in GNOME_ORCA_REJECTION_MARKERS)


def subprocess_env_with_executable_dir(executable_path: str) -> Dict[str, str]:
    env = os.environ.copy()
    exe_dir = str(Path(executable_path).expanduser().resolve().parent)
    current_path = env.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    if exe_dir and exe_dir not in path_parts:
        env["PATH"] = exe_dir + (os.pathsep + current_path if current_path else "")
    return env


def validate_orca_qm_executable(path: str, timeout: float = 5.0) -> Dict[str, object]:
    candidate = Path(str(path).strip().strip('"')).expanduser()
    if not candidate.is_file():
        return {"ok": False, "reason": "file does not exist"}
    if candidate.name.lower() not in {"orca", "orca.exe"}:
        return {"ok": False, "reason": "executable name is not orca/orca.exe"}
    identity_text = f"{candidate}\n{candidate.resolve()}"
    if _looks_like_gnome_orca(identity_text):
        return {"ok": False, "reason": "this appears to be Ubuntu GNOME Orca screen reader, not ORCA quantum chemistry"}

    outputs: List[str] = []
    for args in ([str(candidate), "--version"], [str(candidate), "-v"], [str(candidate), "-h"], [str(candidate)]):
        try:
            result = subprocess.run(
                args,
                cwd=str(candidate.parent),
                env=subprocess_env_with_executable_dir(str(candidate)),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                errors="replace",
            )
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if output:
                outputs.append(output[:4000])
        except subprocess.TimeoutExpired:
            continue
        except Exception as exc:
            outputs.append(f"{type(exc).__name__}: {exc}")

    combined = "\n".join(outputs)
    if _looks_like_gnome_orca(combined):
        return {"ok": False, "reason": "this appears to be Ubuntu GNOME Orca screen reader, not ORCA quantum chemistry"}
    upper = combined.upper()
    if any(marker in upper for marker in ORCA_QM_IDENTITY_MARKERS):
        return {"ok": True, "reason": "valid ORCA QM executable"}
    return {"ok": False, "reason": "could not verify ORCA quantum-chemistry identity"}


def add_if_existing(roots: List[Path], item: Path) -> None:
    try:
        if item.exists() and item.is_dir():
            roots.append(item)
    except OSError:
        pass


def add_glob_matches(roots: List[Path], parent: Path, pattern: str) -> None:
    try:
        if parent.exists() and parent.is_dir():
            for item in parent.glob(pattern):
                add_if_existing(roots, item)
    except OSError:
        pass


def likely_local_search_roots(program_name: str, project_root: Optional[Path] = None) -> List[Path]:
    """Return likely local folders plus bounded system roots for executable search."""
    roots: List[Path] = []
    base_dir = Path(__file__).resolve().parent
    home = Path.home()

    for item in [
        base_dir,
        base_dir.parent,
        project_root or base_dir.parent,
        Path.cwd(),
        home / "Desktop",
        home / "Downloads",
        home / "Documents",
        home / "Applications",
        home / "bin",
        home / ".local" / "bin",
    ]:
        add_if_existing(roots, item)

    for env_name in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
        env_value = os.environ.get(env_name)
        if env_value:
            env_path = Path(env_value)
            if program_name == "ORCA":
                add_glob_matches(roots, env_path, "*ORCA*")
                add_glob_matches(roots, env_path, "*orca*")
                add_glob_matches(roots, env_path, "*FACCT*")
                add_glob_matches(roots, env_path, "*facct*")
            elif program_name == "Multiwfn":
                add_glob_matches(roots, env_path, "*Multiwfn*")
                add_glob_matches(roots, env_path, "*multiwfn*")

    if platform.system() == "Windows":
        c_drive = Path("C:/")
        add_if_existing(roots, c_drive)
        if program_name == "ORCA":
            patterns = ["ORCA*", "orca*", "FACCT*", "facct*"]
        elif program_name == "Multiwfn":
            patterns = ["Multiwfn*", "multiwfn*"]
        else:
            patterns = []

        for pattern in patterns:
            add_glob_matches(roots, c_drive, pattern)

    else:
        for item in [
            Path("/"),
            Path("/opt"),
            Path("/usr/local"),
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/Applications"),
            home / "bin",
            home / ".local" / "bin",
        ]:
            add_if_existing(roots, item)

    unique_roots: List[Path] = []
    seen = set()
    for root in roots:
        try:
            resolved = str(root.resolve())
        except OSError:
            resolved = str(root)
        if resolved not in seen:
            seen.add(resolved)
            unique_roots.append(root)

    return unique_roots


def search_local_executables(
    program_name: str,
    executable_names: List[str],
    project_root: Optional[Path] = None,
    max_seconds: float = 20.0,
    max_matches: int = 8,
    max_visited: int = 80000,
    max_depth: int = 6,
) -> List[str]:
    """
    Search likely local folders for executable files.

    This search is deliberately bounded by time, depth, and visited entries.
    """
    target_names = {name.lower() for name in executable_names}
    roots = likely_local_search_roots(program_name, project_root=project_root)
    started = time.monotonic()
    visited = 0
    found: List[str] = []
    found_seen = set()

    def timed_out() -> bool:
        return (time.monotonic() - started) > max_seconds

    def maybe_record(path: Path) -> None:
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        if resolved not in found_seen:
            found_seen.add(resolved)
            found.append(resolved)

    def scan_dir(folder: Path, depth: int) -> None:
        nonlocal visited

        if timed_out() or len(found) >= max_matches or visited >= max_visited:
            return
        if depth > max_depth:
            return

        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except (OSError, PermissionError):
            return

        for entry in entries:
            if timed_out() or len(found) >= max_matches or visited >= max_visited:
                return

            visited += 1

            try:
                entry_name_lower = entry.name.lower()
                if entry.is_file(follow_symlinks=False) and entry_name_lower in target_names:
                    maybe_record(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in LOCAL_SEARCH_SKIP_DIRS:
                        continue
                    scan_dir(Path(entry.path), depth + 1)
            except (OSError, PermissionError):
                continue

    for root in roots:
        if timed_out() or len(found) >= max_matches or visited >= max_visited:
            break
        scan_dir(root, 0)

    return found


def check_external_software(project_root: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for name, config in EXTERNAL_SOFTWARE.items():
        path_in_path = detect_external_program(config["executables"])
        local_paths: List[str] = []
        rejected_paths: List[Dict[str, str]] = []

        if name == "ORCA" and path_in_path:
            validation = validate_orca_qm_executable(path_in_path)
            if not validation["ok"]:
                rejected_paths.append({"path": path_in_path, "reason": str(validation["reason"])})
                path_in_path = None

        if path_in_path is None and name in LOCAL_SEARCH_PROGRAMS:
            print(f"Searching likely local folders for {name} executable...")
            found_paths = search_local_executables(name, config["executables"], project_root=project_root)
            if name == "ORCA":
                for found_path in found_paths:
                    validation = validate_orca_qm_executable(found_path)
                    if validation["ok"]:
                        local_paths.append(found_path)
                    else:
                        rejected_paths.append({"path": found_path, "reason": str(validation["reason"])})
            else:
                local_paths = found_paths
            if local_paths:
                print(f"  Found locally: {local_paths[0]}")
            else:
                print("  Not found locally.")
            if rejected_paths:
                for rejected in rejected_paths[:5]:
                    print(f"  Rejected: {rejected['path']} ({rejected['reason']})")

        rows.append(
            {
                "name": name,
                "detected": path_in_path is not None,
                "path": path_in_path or "",
                "found_local_not_path": bool(local_paths),
                "local_paths": local_paths,
                "rejected_paths": rejected_paths,
                "required": bool(config["required"]),
                "message": config["message"],
            }
        )

    return rows


def ensure_settings_file(base_dir: Path) -> Dict[str, object]:
    settings_file = base_dir / "tools" / "Orca_input" / SETTINGS_FILENAME
    legacy_settings_file = base_dir / SETTINGS_FILENAME

    default_settings = {
        "homo_lumo_script": "tools/HOMO_LUMO/HOMO_LUMO_v2.py",
        "esp_script": "tools/VisMap_5.0/VisMap5.6_pyvista.py",
        "nci_script": "tools/NCI_plot/nci_plotter.py",
        "qtaim_script": "tools/qtaim-cp/qtaim.py",
        "python_executable": sys.executable,
        "esp_python_command": sys.executable,
        "nci_python_command": sys.executable,
        "qtaim_python_command": sys.executable,
    }

    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        created = not settings_file.exists()
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
                if not isinstance(settings, dict):
                    settings = {}
            except Exception:
                settings = {}
            for key, value in default_settings.items():
                if not str(settings.get(key, "")).strip():
                    settings[key] = value
        else:
            settings = default_settings

        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        if legacy_settings_file.exists():
            legacy_settings_file.unlink()
        return {
            "ok": True,
            "created": created,
            "path": str(settings_file),
            "message": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "created": False,
            "path": str(settings_file),
            "message": f"Could not create settings file: {type(exc).__name__}: {exc}",
        }


def powershell_quote(value: Union[Path, str]) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def desktop_shortcut_path() -> Optional[Path]:
    if platform.system() != "Windows":
        return None
    try:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Environment]::GetFolderPath('Desktop')",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        desktop = (result.stdout or "").strip()
        if desktop:
            return Path(desktop) / DESKTOP_SHORTCUT_NAME
    except Exception:
        pass
    fallback = Path.home() / "Desktop"
    return fallback / DESKTOP_SHORTCUT_NAME if fallback.exists() else None


def shortcut_python_executable() -> Path:
    python_exe = Path(sys.executable).resolve()
    if platform.system() == "Windows" and python_exe.name.lower() == "python.exe":
        pythonw = python_exe.with_name("pythonw.exe")
        if pythonw.is_file():
            return pythonw
    return python_exe


def create_desktop_shortcut(base_dir: Path) -> Dict[str, object]:
    shortcut = desktop_shortcut_path()
    if platform.system() != "Windows":
        return {
            "ok": True,
            "created": False,
            "path": "",
            "message": "Desktop shortcut creation is implemented for Windows only.",
        }
    if shortcut is None:
        return {
            "ok": False,
            "created": False,
            "path": "",
            "message": "Could not locate the Windows Desktop folder.",
        }

    script_path = (base_dir / PROJECT_MAIN_SCRIPT).resolve()
    icon_path = (base_dir / PROJECT_ICON).resolve()
    if not script_path.is_file():
        return {
            "ok": False,
            "created": False,
            "path": str(shortcut),
            "message": f"Main script was not found: {script_path}",
        }
    if not icon_path.is_file():
        return {
            "ok": False,
            "created": False,
            "path": str(shortcut),
            "message": f"Shortcut icon was not found: {icon_path}",
        }

    target = shortcut_python_executable()
    ps_script = "\n".join(
        [
            "$shell = New-Object -ComObject WScript.Shell",
            f"$shortcut = $shell.CreateShortcut({powershell_quote(shortcut)})",
            f"$shortcut.TargetPath = {powershell_quote(target)}",
            f"$shortcut.Arguments = {powershell_quote(str(script_path))}",
            f"$shortcut.WorkingDirectory = {powershell_quote(base_dir.resolve())}",
            f"$shortcut.IconLocation = {powershell_quote(str(icon_path) + ',0')}",
            "$shortcut.Description = 'Launch ORCA Input Builder'",
            "$shortcut.Save()",
        ]
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            message = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
            return {
                "ok": False,
                "created": False,
                "path": str(shortcut),
                "target": str(script_path),
                "icon": str(icon_path),
                "message": message or f"PowerShell returned exit code {result.returncode}.",
            }
        return {
            "ok": True,
            "created": True,
            "path": str(shortcut),
            "target": str(script_path),
            "icon": str(icon_path),
            "message": "Created desktop shortcut for ORCA Input Builder with the bundled ORCA icon.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "created": False,
            "path": str(shortcut),
            "target": str(script_path),
            "icon": str(icon_path),
            "message": f"Could not create desktop shortcut: {type(exc).__name__}: {exc}",
        }


def link_list_for(program_name: str) -> str:
    links = OFFICIAL_LINKS.get(program_name, [])
    if not links:
        return ""

    items = "\n".join(
        f'<li><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a></li>'
        for label, url in links
    )
    return f"<ul>{items}</ul>"


def external_status_label(row: Dict[str, object]) -> str:
    if row["detected"]:
        return "Valid ORCA QM found" if row["name"] == "ORCA" else "Detected in PATH"
    if row["found_local_not_path"]:
        return "Valid ORCA QM found locally, but not in PATH" if row["name"] == "ORCA" else "Found locally, but not in PATH"
    if row.get("rejected_paths"):
        return "Executable named orca found but rejected"
    return "Not found"


def get_top_missing_items(
    package_info: Dict[str, object],
    external_info: List[Dict[str, object]],
) -> List[str]:
    python_ok = sys.version_info >= (3, 9)
    top_missing_items: List[str] = []

    if not python_ok:
        top_missing_items.append("Python 3.9 or newer is required.")

    for pkg in package_info["final_missing_required"]:
        top_missing_items.append(f"Required Python package is missing: {pkg}")

    tkinter_info = package_info.get("tkinter_info", {})
    if tkinter_info and not tkinter_info.get("ok", False):
        top_missing_items.append("Tkinter is missing. It is required for the graphical interface.")

    for row in external_info:
        if not row["required"] or row["detected"]:
            continue
        if row["found_local_not_path"]:
            local_paths = row.get("local_paths", [])
            local_path = str(local_paths[0] if local_paths else "")
            top_missing_items.append(
                f"{row['name']} was found locally but is not available from PATH. "
                f"Use this path in Settings or add its folder to PATH: {local_path}"
            )
            continue
        if row["name"] == "ORCA" and row.get("rejected_paths"):
            rejected = row["rejected_paths"][0]
            top_missing_items.append(
                f"ORCA QM: not found. Rejected {rejected['path']}: {rejected['reason']}."
            )
            continue
        top_missing_items.append(
            f"{row['name']} was not detected in PATH and was not found locally by this checker."
        )

    return top_missing_items


def print_terminal_report(
    package_info: Dict[str, object],
    external_info: List[Dict[str, object]],
    settings_info: Dict[str, object],
    shortcut_info: Dict[str, object],
    output_path: Path,
) -> None:
    """Print a concise report in cmd/terminal."""
    top_missing_items = get_top_missing_items(package_info, external_info)

    print()
    print("=" * 64)
    print("Installation status")
    print("=" * 64)

    if top_missing_items:
        print("Missing components found:")
        for item in top_missing_items:
            print(f"  - {item}")
    else:
        print("No missing components")

    local_not_path = [
        row for row in external_info
        if row["required"] and (not row["detected"]) and row["found_local_not_path"]
    ]
    if local_not_path:
        print()
        print("Found locally but not in PATH:")
        for row in local_not_path:
            print(f"  - {row['name']}:")
            for path in row["local_paths"]:
                print(f"      {path}")
            print("    Add the executable folder to PATH or select it manually in the program settings.")

    rejected_external = [row for row in external_info if row.get("rejected_paths")]
    if rejected_external:
        print()
        print("Rejected executable candidates:")
        for row in rejected_external:
            for rejected in row["rejected_paths"]:
                print(f"  - {row['name']}: {rejected['path']}")
                print(f"    {rejected['reason']}")

    if package_info["installed_now"]:
        print()
        print("Python packages installed now:")
        for pkg in package_info["installed_now"]:
            print(f"  - {pkg}")

    venv_info = package_info.get("venv_info", {})
    if venv_info.get("requested"):
        print()
        print("Python environment:")
        print(f"  - Path: {venv_info.get('path', '-')}")
        print(f"  - Python: {venv_info.get('python', '-')}")
        print(f"  - Status: {'OK' if venv_info.get('ok') else 'Problem'}")
        if venv_info.get("message"):
            print(f"  - Note: {venv_info['message']}")

    if package_info["install_failures"]:
        print()
        print("Failed Python package installation:")
        for item in package_info["install_failures"]:
            print(f"  - {item['package']}")

    tkinter_info = package_info.get("tkinter_info", {})
    if tkinter_info and not tkinter_info.get("ok", False):
        print()
        print("Tkinter problem:")
        print(f"  - {tkinter_info.get('message', 'Tkinter is missing.')}")
        if tkinter_info.get("error"):
            print(f"  - Import error: {tkinter_info['error']}")

    if package_info["final_missing_recommended"]:
        print()
        print("Recommended package still missing:")
        for pkg in package_info["final_missing_recommended"]:
            print(f"  - {pkg}")

    optional_missing = [
        row for row in external_info
        if (not row["required"]) and not row["detected"]
    ]
    if optional_missing:
        print()
        print("Optional / feature-specific components not detected:")
        for row in optional_missing:
            print(f"  - {row['name']}: {row['message']}")

    if not settings_info["ok"]:
        print()
        print("Settings file problem:")
        print(f"  - {settings_info['message']}")

    print()
    if shortcut_info.get("ok"):
        if shortcut_info.get("created"):
            print(f"Desktop shortcut: {shortcut_info['path']}")
        else:
            print(f"Desktop shortcut: {shortcut_info.get('message', 'not created')}")
    else:
        print("Desktop shortcut problem:")
        print(f"  - {shortcut_info.get('message', 'Shortcut was not created.')}")

    print()
    print(f"HTML report: {output_path}")
    print("=" * 64)


def render_short_report(
    package_info: Dict[str, object],
    external_info: List[Dict[str, object]],
    settings_info: Dict[str, object],
    shortcut_info: Dict[str, object],
    output_path: Path,
) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    truly_missing_required_external = [
        row for row in external_info
        if row["required"] and not row["detected"] and not row["found_local_not_path"]
    ]

    found_local_not_path_external = [
        row for row in external_info
        if row["required"] and not row["detected"] and row["found_local_not_path"]
    ]

    missing_optional_external = [
        row for row in external_info
        if (not row["required"]) and not row["detected"]
    ]

    top_missing_items = get_top_missing_items(package_info, external_info)

    if top_missing_items:
        main_status = "Missing components found"
        main_message = "These components need attention before the full workflow is ready."
        status_class = "bad"
    else:
        main_status = "No missing components"
        main_message = ""
        status_class = "ok"

    top_missing_html = ""
    if top_missing_items:
        top_missing_html += "<ul class='toplist'>"
        for item in top_missing_items:
            top_missing_html += f"<li>{esc(item)}</li>"
        top_missing_html += "</ul>"

    # Top links only for components truly missing, not for local-but-not-PATH cases.
    top_links_html = ""
    missing_program_names = [
        row["name"] for row in truly_missing_required_external
        if row["name"] in OFFICIAL_LINKS
    ]
    if missing_program_names:
        top_links_html += "<h2>Official download links</h2>"
        for name in missing_program_names:
            top_links_html += f"<h3>{esc(name)}</h3>"
            top_links_html += link_list_for(name)
            if name == "Multiwfn":
                top_links_html += (
                    "<div class='smallbox warnbox'>"
                    "<b>Browser / antivirus warning:</b><br>"
                    + esc(" ".join(MULTIWFN_SECURITY_NOTE.split()))
                    + "</div>"
                )

    # Details section: full report.
    installed_now = package_info["installed_now"]
    installed_now_html = ""
    if installed_now:
        installed_now_html = (
            "<div class='smallbox okbox'><b>Installed now:</b> "
            + esc(", ".join(installed_now))
            + "</div>"
        )

    declined_html = ""
    if package_info["user_declined"]:
        declined_html = (
            "<div class='smallbox warnbox'><b>Python package installation was skipped by user.</b></div>"
        )

    python_failures_html = ""
    install_failures = package_info["install_failures"]
    if install_failures:
        failure_items = "\n".join(
            f"<li><b>{esc(item['package'])}</b>: installation failed.</li>"
            for item in install_failures
        )
        python_failures_html = (
            "<div class='smallbox badbox'><b>Failed Python package installation:</b>"
            f"<ul>{failure_items}</ul></div>"
        )

    tkinter_info = package_info.get("tkinter_info", {})
    tkinter_html = ""
    if tkinter_info:
        if tkinter_info.get("ok", False):
            tkinter_html = "<div class='smallbox okbox'><b>Tkinter:</b> available for graphical windows.</div>"
        else:
            tkinter_html = (
                "<div class='smallbox badbox'><b>Tkinter is missing.</b><br>"
                + esc(tkinter_info.get("message", "Install Tkinter for your operating system."))
                + "<br><b>Import error:</b> "
                + esc(tkinter_info.get("error", ""))
                + "</div>"
            )

    venv_info = package_info.get("venv_info", {})
    venv_html = ""
    if venv_info.get("requested"):
        venv_class = "okbox" if venv_info.get("ok") else "badbox"
        venv_html = f"""
        <h3>Python environment</h3>
        <div class='smallbox {venv_class}'>
            <b>Status:</b> {esc("OK" if venv_info.get("ok") else "Problem")}<br>
            <b>Path:</b> <code>{esc(venv_info.get("path", "") or "-")}</code><br>
            <b>Python:</b> <code>{esc(venv_info.get("python", "") or "-")}</code><br>
            <b>Note:</b> {esc(venv_info.get("message", "") or "-")}
        </div>
        """

    local_paths_html = ""
    if found_local_not_path_external:
        local_paths_html += "<h3>Found locally but not in PATH</h3>"
        local_paths_html += "<p>These programs appear to be installed, but the command line cannot find them.</p>"
        for row in found_local_not_path_external:
            local_paths_html += f"<h4>{esc(row['name'])}</h4><ul>"
            for path in row["local_paths"]:
                local_paths_html += f"<li><code>{esc(path)}</code></li>"
            local_paths_html += "</ul>"
            local_paths_html += "<p>Add the executable folder to PATH or select this executable manually in the program settings.</p>"

    rejected_paths_html = ""
    rejected_external = [row for row in external_info if row.get("rejected_paths")]
    if rejected_external:
        rejected_paths_html += "<h3>Rejected executable candidates</h3>"
        rejected_paths_html += "<p>These files matched an executable name but failed program identity validation.</p>"
        for row in rejected_external:
            rejected_paths_html += f"<h4>{esc(row['name'])}</h4><ul>"
            for rejected in row["rejected_paths"]:
                rejected_paths_html += f"<li><code>{esc(rejected['path'])}</code>: {esc(rejected['reason'])}</li>"
            rejected_paths_html += "</ul>"

    external_table_rows = ""
    for row in external_info:
        path_text = row["path"] or ""
        if not path_text and row["local_paths"]:
            path_text = row["local_paths"][0]
        external_table_rows += f"""
        <tr>
            <td>{esc(row["name"])}</td>
            <td>{esc("Required" if row["required"] else "Optional")}</td>
            <td>{esc(external_status_label(row))}</td>
            <td><code>{esc(path_text or "-")}</code></td>
        </tr>
        """

    external_table_html = f"""
    <h3>External program status</h3>
    <table>
        <tr><th>Program</th><th>Type</th><th>Status</th><th>Path found</th></tr>
        {external_table_rows}
    </table>
    """

    package_rows = ""
    for name in REQUIRED_PACKAGES + RECOMMENDED_PACKAGES:
        installed = name in package_info["final_installed"]
        version = package_info["final_installed"].get(name, "")
        ptype = "Required" if name in REQUIRED_PACKAGES else "Recommended"
        status = "Installed" if installed else "Missing"
        package_rows += f"""
        <tr>
            <td>{esc(name)}</td>
            <td>{esc(ptype)}</td>
            <td>{esc(status)}</td>
            <td>{esc(version or "-")}</td>
        </tr>
        """

    package_table_html = f"""
    <h3>Python package status</h3>
    <table>
        <tr><th>Package</th><th>Type</th><th>Status</th><th>Version</th></tr>
        {package_rows}
    </table>
    """

    warnings_html = ""
    detail_warnings: List[str] = []

    if package_info["final_missing_recommended"]:
        detail_warnings.append(
            "Recommended Python package not installed: " + ", ".join(package_info["final_missing_recommended"])
        )

    for row in missing_optional_external:
        detail_warnings.append(row["message"])

    if not settings_info["ok"]:
        detail_warnings.append(settings_info["message"])
    if not shortcut_info["ok"]:
        detail_warnings.append(shortcut_info["message"])

    if detail_warnings:
        warnings_html += "<h3>Other notes</h3><ul>"
        for item in detail_warnings:
            warnings_html += f"<li>{esc(item)}</li>"
        warnings_html += "</ul>"

    all_links_html = ""
    all_program_names_for_links = []
    for row in external_info:
        if not row["detected"] and row["name"] in OFFICIAL_LINKS:
            all_program_names_for_links.append(row["name"])

    if all_program_names_for_links:
        all_links_html += "<h3>Official links</h3>"
        for name in all_program_names_for_links:
            all_links_html += f"<h4>{esc(name)}</h4>"
            all_links_html += link_list_for(name)
            if name == "Multiwfn":
                all_links_html += (
                    "<div class='smallbox warnbox'>"
                    "<b>Browser / antivirus warning:</b><br>"
                    + esc(" ".join(MULTIWFN_SECURITY_NOTE.split()))
                    + "</div>"
                )

    settings_html = f"""
    <h3>Settings file</h3>
    <table>
        <tr><th>Status</th><td>{esc("OK" if settings_info["ok"] else "Problem")}</td></tr>
        <tr><th>Path</th><td><code>{esc(settings_info["path"])}</code></td></tr>
    </table>
    """

    shortcut_html = f"""
    <h3>Desktop shortcut</h3>
    <table>
        <tr><th>Status</th><td>{esc("OK" if shortcut_info["ok"] else "Problem")}</td></tr>
        <tr><th>Path</th><td><code>{esc(shortcut_info.get("path", "") or "-")}</code></td></tr>
        <tr><th>Target</th><td><code>{esc(shortcut_info.get("target", "") or "-")}</code></td></tr>
        <tr><th>Icon</th><td><code>{esc(shortcut_info.get("icon", "") or "-")}</code></td></tr>
        <tr><th>Note</th><td>{esc(shortcut_info.get("message", "") or ("Created with ORCA builder icon." if shortcut_info.get("created") else ""))}</td></tr>
    </table>
    """

    details_html = f"""
    <details>
        <summary>Details...</summary>

        {installed_now_html}
        {declined_html}
        {python_failures_html}
        {tkinter_html}
        {venv_html}

        {local_paths_html}
        {rejected_paths_html}
        {package_table_html}
        {external_table_html}
        {warnings_html}
        {all_links_html}
        {settings_html}
        {shortcut_html}

        <h3>Run main program</h3>
        <p><code>"{esc(sys.executable)}" {esc(output_path.parent / PROJECT_MAIN_SCRIPT)}</code></p>
    </details>
    """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Installation status</title>
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 32px;
    color: #222;
    background: #f7f7f7;
    line-height: 1.45;
}}
.main {{
    max-width: 850px;
    background: #fff;
    border-radius: 10px;
    padding: 24px 30px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}}
h1 {{
    margin-top: 0;
}}
h2 {{
    margin-top: 24px;
}}
h3 {{
    margin-top: 18px;
    margin-bottom: 6px;
}}
h4 {{
    margin-bottom: 4px;
}}
.status {{
    font-size: 20px;
    font-weight: bold;
    padding: 10px 14px;
    border-radius: 6px;
    display: inline-block;
}}
.ok {{
    color: #1b5e20;
}}
.warn {{
    color: #8a5a00;
}}
.bad {{
    color: #b00020;
}}
.status.ok {{
    background: #e8f5e9;
}}
.status.warn {{
    background: #fff8e1;
}}
.status.bad {{
    background: #ffebee;
}}
.meta {{
    color: #666;
    font-size: 13px;
}}
.smallbox {{
    padding: 10px 12px;
    border-radius: 6px;
    margin: 10px 0;
}}
.okbox {{
    background: #e8f5e9;
}}
.warnbox {{
    background: #fff8e1;
}}
.badbox {{
    background: #ffebee;
}}
code {{
    background: #eee;
    padding: 2px 5px;
    border-radius: 4px;
}}
a {{
    color: #0645ad;
}}
li {{
    margin-bottom: 6px;
}}
.toplist {{
    font-size: 16px;
}}
details {{
    margin-top: 24px;
    border-top: 1px solid #ddd;
    padding-top: 16px;
}}
summary {{
    cursor: pointer;
    font-weight: bold;
    font-size: 17px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0 18px 0;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 7px 9px;
    vertical-align: top;
    text-align: left;
}}
th {{
    background: #f0f0f0;
}}
</style>
</head>
<body>
<div class="main">

<h1>Installation status</h1>
<p class="meta">
Generated: {esc(now)}<br>
System: {esc(platform.system())} {esc(platform.release())}<br>
Python: {esc(sys.version.split()[0])}
</p>

<p><span class="status {status_class}">{esc(main_status)}</span></p>
{f"<p>{esc(main_message)}</p>" if main_message else ""}

{top_missing_html}

{top_links_html}

{details_html}

</div>
</body>
</html>
"""


def main() -> None:
    launcher_dir = Path(__file__).resolve().parent
    project_root_arg = arg_value("--project-root")
    default_project_root = Path(project_root_arg).expanduser().resolve() if project_root_arg else launcher_dir.parent
    if project_root_arg and is_project_root(default_project_root):
        base_dir = default_project_root
    else:
        base_dir = browse_for_installation_location(default_project_root)

    venv_info: Dict[str, object] = {"requested": has_arg("--setup-venv"), "ok": False, "created": False, "path": "", "python": "", "message": "Virtual environment was not requested."}
    if has_arg("--using-venv"):
        venv_dir = Path(sys.executable).resolve().parent.parent
        venv_info = {
            "requested": True,
            "ok": True,
            "created": False,
            "path": str(venv_dir),
            "python": sys.executable,
            "message": "Running inside the local CrystEngKit Python environment.",
        }
    elif has_arg("--setup-venv"):
        venv_info = create_venv_and_reexec(base_dir)
        print()
        print("ERROR: Local Python environment setup failed.")
        print(venv_info.get("message", "Unknown virtual environment error."))
        raise SystemExit(1)

    output_path = base_dir / "installation_report.html"

    package_info = check_and_optionally_install_python_packages()
    package_info["tkinter_info"] = check_tkinter()
    package_info["venv_info"] = venv_info
    external_info = check_external_software(base_dir)
    settings_info = ensure_settings_file(base_dir)
    shortcut_info = create_desktop_shortcut(base_dir)

    report = render_short_report(
        package_info=package_info,
        external_info=external_info,
        settings_info=settings_info,
        shortcut_info=shortcut_info,
        output_path=output_path,
    )

    output_path.write_text(report, encoding="utf-8")

    print_terminal_report(
        package_info=package_info,
        external_info=external_info,
        settings_info=settings_info,
        shortcut_info=shortcut_info,
        output_path=output_path,
    )

    if "--no-open" not in sys.argv:
        opened = webbrowser.open(output_path.as_uri())
        if opened:
            print("Report opened in the default web browser.")
        else:
            print("The report was created, but the browser did not open automatically.")
            print(f"Open this file manually: {output_path}")


if __name__ == "__main__":
    main()
