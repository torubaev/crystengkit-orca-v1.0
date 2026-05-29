#!/usr/bin/env python3
"""
Installer/Checker Script for ORCA Input Builder and VisMap

This script checks the system configuration, installs required Python packages,
and verifies external software dependencies. It supports Windows and Linux.

Requirements checked/installed:
- Python 3.9+
- numpy, pyvista, matplotlib, periodictable, gemmi (optional), Pillow (recommended for MO surface images)
- External: ORCA, Gaussian, Multiwfn (checks only; user must install manually)

Run with: python install_checker.py
"""

import sys
import os
import subprocess
import platform
import json
from pathlib import Path

# Required Python packages
REQUIRED_PACKAGES = ['numpy', 'pyvista', 'matplotlib', 'periodictable']
OPTIONAL_PACKAGES = ['gemmi', 'Pillow']
PACKAGE_IMPORT_NAMES = {
    'Pillow': 'PIL',
}

# External software checks (commands to run for version check)
EXTERNAL_CHECKS = {
    'ORCA': [['orca', '--version'], ['orca.exe', '--version']],
    'Gaussian': [['g16', '--version'], ['g09', '--version'], ['g16.exe', '--version'], ['g09.exe', '--version']],
    'Multiwfn': [['Multiwfn', '--version'], ['multiwfn', '--version'], ['Multiwfn.exe', '--version']]
}

def check_python_version():
    """Check Python version >= 3.9"""
    if sys.version_info < (3, 9):
        print(f"ERROR: Python {sys.version_info.major}.{sys.version_info.minor} detected. Need Python 3.9+")
        return False
    print(f"✓ Python {sys.version} OK")
    return True

def check_package(package):
    """Check if package is installed"""
    try:
        __import__(PACKAGE_IMPORT_NAMES.get(package, package))
        return True
    except ImportError:
        return False

def install_package(package):
    """Install package via pip"""
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
        return True
    except subprocess.CalledProcessError:
        return False

def _legacy_check_external_software(name, command):
    """Check if external software is available"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✓ {name} found: {result.stdout.strip()[:100]}...")
            return True
        else:
            print(f"✗ {name} not found or not working")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"✗ {name} not found")
        return False

def check_external_software(name, commands):
    """Check if external software is available."""
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                output = (result.stdout or result.stderr or "").strip()
                print(f"{name} found via {command[0]}: {output[:100]}...")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    print(f"{name} not found or not working")
    return False


def main():
    print("=== ORCA Input Builder & VisMap Installer/Checker ===\n")

    # Check OS
    os_name = platform.system()
    print(f"Detected OS: {os_name}")

    # Check Python
    if not check_python_version():
        sys.exit(1)

    # Check/install Python packages
    print("\n--- Checking Python packages ---")
    for pkg in REQUIRED_PACKAGES:
        if check_package(pkg):
            print(f"✓ {pkg} installed")
        else:
            print(f"Installing {pkg}...")
            if install_package(pkg):
                print(f"✓ {pkg} installed")
            else:
                print(f"✗ Failed to install {pkg}")
                sys.exit(1)

    for pkg in OPTIONAL_PACKAGES:
        if check_package(pkg):
            print(f"✓ {pkg} installed (optional)")
        else:
            print(f"Optional package {pkg} not found. Installing...")
            if install_package(pkg):
                print(f"✓ {pkg} installed")
            else:
                print(f"⚠ Failed to install {pkg} (optional, continuing)")

    # Check external software
    print("\n--- Checking external software ---")
    print("Note: External software (ORCA, Gaussian, Multiwfn) must be installed manually.")
    print("Download from official websites if not found.\n")

    for name, cmd in EXTERNAL_CHECKS.items():
        check_external_software(name, cmd)

    # Create/update settings file if needed
    settings_file = Path(__file__).parent / "orca_gaussian_builder_settings.json"
    if not settings_file.exists():
        default_settings = {
            "homo_lumo_script": "HOMO_LUMO/HOMO_LUMO_v2.py",
            "esp_script": "VisMap_5.0/VisMap5.6_pyvista.py",
            "nci_script": "NCI_plot/nci_plotter.py",
            "qtaim_script": "qtaim-cp/qtaim.py",
            "python_executable": "",
            "esp_python_command": "",
            "nci_python_command": "",
            "qtaim_python_command": "",
        }
        with open(settings_file, 'w') as f:
            json.dump(default_settings, f, indent=2)
        print(f"\n✓ Created default settings file: {settings_file}")

    print("\n=== Installation check complete ===")
    print("Run the main scripts: python orca_input.py")

if __name__ == "__main__":
    main()
