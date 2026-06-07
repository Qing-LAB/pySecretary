#!/usr/bin/env bash
# Run the pySecretary offline test suite inside the managed virtual environment.
#
# This mirrors scripts/run-prototype-ui.sh so the environment (uv preferred,
# pip fallback) is created and kept in sync the same way for tests and for the
# server. See docs/testing/strategy.md for the test layers this covers.
#
# Usage:
#   scripts/run-tests.sh                 # full suite + compile sanity check
#   scripts/run-tests.sh -k pattern      # forward args to unittest (e.g. filters)
#   scripts/run-tests.sh tests.test_app  # run a single module
#   PSEC_SKIP_COMPILEALL=1 scripts/run-tests.sh
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PSEC_VENV_DIR:-"$BASE_DIR/.venv"}"
PYTHON_BIN="${PYTHON:-python3}"
REQUIREMENTS_FILE="$BASE_DIR/requirements.txt"

echo "pySecretary test runner"
echo "Project: $BASE_DIR"
echo "Venv:    $VENV_DIR"

if command -v uv >/dev/null 2>&1; then
  INSTALLER="uv"
else
  INSTALLER="pip"
fi

REQUIREMENTS_STAMP="$VENV_DIR/.pysecretary-requirements.$INSTALLER.stamp"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if [[ "$INSTALLER" == "uv" ]]; then
    echo "Creating virtual environment with uv..."
    uv venv "$VENV_DIR" --python "$PYTHON_BIN"
  else
    echo "Creating virtual environment with Python venv..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

if [[ -f "$REQUIREMENTS_FILE" && ( ! -f "$REQUIREMENTS_STAMP" || "$REQUIREMENTS_FILE" -nt "$REQUIREMENTS_STAMP" ) ]]; then
  if [[ "$INSTALLER" == "uv" ]]; then
    echo "Installing project dependencies with uv..."
    uv pip install --python "$VENV_DIR/bin/python" -r "$REQUIREMENTS_FILE"
  else
    echo "Installing project dependencies with pip..."
    python -m pip install --upgrade pip
    python -m pip install -r "$REQUIREMENTS_FILE"
  fi
  touch "$REQUIREMENTS_STAMP"
else
  echo "Dependencies are up to date for this virtual environment using $INSTALLER."
fi

cd "$BASE_DIR"

echo "Running offline unittest suite..."
if (($# > 0)); then
  python -m unittest "$@"
else
  # -b buffers per-test stdout/stderr so passing tests stay quiet and only
  # failures show their captured output.
  python -m unittest discover -s tests -b
fi

if [[ "${PSEC_SKIP_COMPILEALL:-0}" != "1" ]]; then
  echo "Running compile sanity check..."
  python -m compileall -q pysecretary tests
  echo "compileall passed."
fi

echo "All checks passed."
