#!/usr/bin/env sh
set -eu

APP_NAME="CrystEngKit ORCA"
REPO_REF="${REPO_REF:-}"
REPO_SHA256="${REPO_SHA256:-}"
REPO_ZIP_URL="${REPO_ZIP_URL:-}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/CrystEngKit-ORCA}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
LAUNCHER="$BIN_DIR/crystengkit-orca"
DESKTOP_FILE="$DESKTOP_DIR/crystengkit-orca.desktop"

yes_no() {
    question="$1"
    default="${2:-y}"
    while :; do
        if [ "$default" = "y" ]; then
            printf "%s [Y/n]: " "$question"
        else
            printf "%s [y/N]: " "$question"
        fi
        read -r answer || answer=""
        answer="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]')"
        if [ -z "$answer" ]; then
            [ "$default" = "y" ]
            return $?
        fi
        case "$answer" in
            y|yes) return 0 ;;
            n|no) return 1 ;;
            *) echo "Please type y or n." ;;
        esac
    done
}

find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            if "$cmd" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
                command -v "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

install_system_python_components() {
    reason="$1"
    echo "$reason"
    echo
    if command -v apt-get >/dev/null 2>&1; then
        echo "Suggested command:"
        echo "  sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-tk curl"
        if yes_no "Run this command now?" "n"; then
            sudo apt-get update
            sudo apt-get install -y python3 python3-venv python3-tk curl
            return 0
        fi
    elif command -v dnf >/dev/null 2>&1; then
        echo "Suggested command:"
        echo "  sudo dnf install -y python3 python3-tkinter curl"
        if yes_no "Run this command now?" "n"; then
            sudo dnf install -y python3 python3-tkinter curl
            return 0
        fi
    elif command -v pacman >/dev/null 2>&1; then
        echo "Suggested command:"
        echo "  sudo pacman -S --needed python tk curl"
        if yes_no "Run this command now?" "n"; then
            sudo pacman -S --needed python tk curl
            return 0
        fi
    elif command -v zypper >/dev/null 2>&1; then
        echo "Suggested command:"
        echo "  sudo zypper install python3 python3-venv python3-tk curl"
        if yes_no "Run this command now?" "n"; then
            sudo zypper install python3 python3-venv python3-tk curl
            return 0
        fi
    else
        echo "Install Python 3.9+, venv support, Tkinter, and curl with your distribution package manager."
    fi
    return 1
}

check_venv_support() {
    probe_dir="$(mktemp -d)"
    if "$PYTHON_CMD" -m venv "$probe_dir/venv" >/dev/null 2>&1; then
        rm -rf "$probe_dir"
        return 0
    fi
    rm -rf "$probe_dir"
    return 1
}

download_file() {
    url="$1"
    output="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail "$url" -o "$output"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$output" "$url"
    else
        "$PYTHON_CMD" - "$url" "$output" <<'PY'
import sys
import urllib.request

url, output = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(url) as response:
    data = response.read()
with open(output, "wb") as handle:
    handle.write(data)
PY
    fi
}

verify_download() {
    zip_path="$1"
    "$PYTHON_CMD" - "$zip_path" "$REPO_SHA256" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2].strip().lower()
actual = hashlib.sha256(path.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"Repository archive checksum mismatch. Expected {expected}, got {actual}.")
PY
}

extract_zip() {
    zip_path="$1"
    extract_dir="$2"
    "$PYTHON_CMD" - "$zip_path" "$extract_dir" "$INSTALL_DIR" <<'PY'
import os
import shutil
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
extract_dir = Path(sys.argv[2])
install_dir = Path(sys.argv[3])

extract_root = extract_dir.resolve()
with zipfile.ZipFile(zip_path) as archive:
    for member in archive.infolist():
        target = (extract_root / member.filename).resolve()
        if target != extract_root and extract_root not in target.parents:
            raise SystemExit(f"Unsafe path in repository archive: {member.filename}")
    archive.extractall(extract_root)

roots = [p for p in extract_dir.iterdir() if p.is_dir()]
if not roots:
    raise SystemExit("Downloaded archive did not contain a repository folder.")

source_root = roots[0]
install_dir.mkdir(parents=True, exist_ok=True)
for item in source_root.iterdir():
    target = install_dir / item.name
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    if item.is_dir():
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)
PY
}

create_launchers() {
    mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env sh
cd "$INSTALL_DIR" || exit 1
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/tools/Orca_input/orca_input.py" "\$@"
EOF
    chmod +x "$LAUNCHER"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Launch ORCA Input Builder
Exec=$LAUNCHER
Path=$INSTALL_DIR
Icon=$INSTALL_DIR/tools/images/orca_builder.ico
Terminal=false
Categories=Science;Education;
EOF
}

echo "$APP_NAME Linux web installer"
echo
echo "Install folder: $INSTALL_DIR"
if [ -z "$REPO_REF" ] || [ -z "$REPO_SHA256" ]; then
    echo "ERROR: REPO_REF and REPO_SHA256 are required for a verified web install."
    echo "Use the release-specific command published with the installer."
    exit 2
fi
if [ -z "$REPO_ZIP_URL" ]; then
    REPO_ZIP_URL="https://github.com/torubaev/crystengkit-orca-v1.0/archive/$REPO_REF.zip"
fi
echo "Repository commit: $REPO_REF"
echo "Repository ZIP SHA-256: $REPO_SHA256"
echo

PYTHON_CMD="$(find_python || true)"
if [ -z "$PYTHON_CMD" ]; then
    install_system_python_components "Python 3.9+ was not found." || {
        echo
        echo "Python setup was not completed. Install Python 3.9+ and run this installer again."
        exit 1
    }
    PYTHON_CMD="$(find_python || true)"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "Python 3.9+ is still not available."
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
if ! check_venv_support; then
    install_system_python_components "Python venv support was not found." || {
        echo
        echo "Python venv setup was not completed. Install the venv package for your distribution and run again."
        exit 1
    }
    if ! check_venv_support; then
        echo "Python venv support is still unavailable."
        exit 1
    fi
fi

if ! "$PYTHON_CMD" -c "import tkinter" >/dev/null 2>&1; then
    echo
    echo "WARNING: Tkinter was not detected. The graphical tools need Tkinter."
    echo "Install python3-tk / python3-tkinter / tk for your distribution if the checker reports a problem."
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ZIP_PATH="$TMP_DIR/repo.zip"
EXTRACT_DIR="$TMP_DIR/extract"
mkdir -p "$EXTRACT_DIR"

echo
echo "Downloading repository..."
download_file "$REPO_ZIP_URL" "$ZIP_PATH"
verify_download "$ZIP_PATH"

echo "Installing repository files..."
extract_zip "$ZIP_PATH" "$EXTRACT_DIR"

echo "Running CrystEngKit checker and environment setup..."
cd "$INSTALL_DIR"
"$PYTHON_CMD" "$INSTALL_DIR/install/install.py" --setup-venv --project-root="$INSTALL_DIR"

if [ -x "$INSTALL_DIR/.venv/bin/python" ]; then
    create_launchers
    echo
    echo "Launcher created:"
    echo "  $LAUNCHER"
    echo "Desktop entry:"
    echo "  $DESKTOP_FILE"
else
    echo
    echo "WARNING: .venv was not created, so the launcher was not written."
fi

echo
echo "Done."
