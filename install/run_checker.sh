#!/usr/bin/env sh

cd "$(dirname "$0")" || exit 1

CHECKER="install.py"

if [ ! -f "$CHECKER" ]; then
    echo "ERROR: $CHECKER was not found in this folder."
    echo "Put this launcher in the same folder as $CHECKER."
    exit 1
fi

find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            "$cmd" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1
            if [ $? -eq 0 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

echo "Checking for Python..."
echo

PYTHON_CMD="$(find_python)"

if [ -n "$PYTHON_CMD" ]; then
    echo "Python found: $PYTHON_CMD"
    if ! "$PYTHON_CMD" -c "import tkinter" >/dev/null 2>&1; then
        echo
        echo "WARNING: Python Tkinter support was not detected."
        echo "The graphical CrystEngKit tools need Tkinter."
        if [ "$(uname -s)" = "Linux" ]; then
            echo "Install it with the command for your Linux distribution, for example:"
            echo "  sudo apt install python3-tk"
            echo "  sudo dnf install python3-tkinter"
            echo "  sudo pacman -S tk"
            echo "  sudo zypper install python3-tk"
        fi
        echo
    fi
    echo "Running $CHECKER..."
    echo
    "$PYTHON_CMD" "$CHECKER"
    exit $?
fi

echo "Python 3.9 or newer was not found."
echo "Please install Python 3.9 or newer, then run this launcher again."
echo

OS_NAME="$(uname -s)"

case "$OS_NAME" in
    Darwin)
        echo "Opening the official Python download page for macOS..."
        open "https://www.python.org/downloads/macos/"
        ;;
    Linux)
        echo "Opening the official Python download page..."
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "https://www.python.org/downloads/"
        else
            echo "Open this page manually:"
            echo "https://www.python.org/downloads/"
        fi
        ;;
    *)
        echo "Open this page manually:"
        echo "https://www.python.org/downloads/"
        ;;
esac

exit 1
