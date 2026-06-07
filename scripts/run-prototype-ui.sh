#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PSEC_VENV_DIR:-"$BASE_DIR/.venv"}"
PYTHON_BIN="${PYTHON:-python3}"
REQUIREMENTS_FILE="$BASE_DIR/requirements.txt"

echo "pySecretary prototype UI launcher"
echo "Project: $BASE_DIR"
echo "Venv:    $VENV_DIR"

APP_ARGS=("$@")
REQUESTED_HOST="${PSEC_PROTOTYPE_HOST:-127.0.0.1}"
REQUESTED_PORT="${PSEC_PROTOTYPE_PORT:-8765}"
HOST_EXPLICIT=0
PORT_EXPLICIT=0
SHOW_HELP=0

for ((i = 0; i < ${#APP_ARGS[@]}; i++)); do
  case "${APP_ARGS[$i]}" in
    -h|--help)
      SHOW_HELP=1
      ;;
    --host)
      HOST_EXPLICIT=1
      if ((i + 1 < ${#APP_ARGS[@]})); then
        REQUESTED_HOST="${APP_ARGS[$((i + 1))]}"
      fi
      ;;
    --host=*)
      HOST_EXPLICIT=1
      REQUESTED_HOST="${APP_ARGS[$i]#--host=}"
      ;;
    --port)
      PORT_EXPLICIT=1
      if ((i + 1 < ${#APP_ARGS[@]})); then
        REQUESTED_PORT="${APP_ARGS[$((i + 1))]}"
      fi
      ;;
    --port=*)
      PORT_EXPLICIT=1
      REQUESTED_PORT="${APP_ARGS[$i]#--port=}"
      ;;
  esac
done

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
elif [[ -f "$REQUIREMENTS_FILE" ]]; then
  echo "Dependencies are up to date for this virtual environment using $INSTALLER."
fi

cd "$BASE_DIR"

port_available() {
  local host="$1"
  local port="$2"
  python -c 'import socket, sys
host = sys.argv[1]
port = int(sys.argv[2])
sock = None
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
except PermissionError:
    sys.exit(2)
except OSError:
    sys.exit(1)
finally:
    if sock is not None:
        sock.close()
' "$host" "$port"
}

if [[ "$SHOW_HELP" == "0" && "$PORT_EXPLICIT" == "1" ]]; then
  set +e
  port_available "$REQUESTED_HOST" "$REQUESTED_PORT"
  PORT_STATUS="$?"
  set -e
  if [[ "$PORT_STATUS" == "1" ]]; then
    echo "Port $REQUESTED_PORT is already in use on $REQUESTED_HOST."
    echo "Choose another port, for example: scripts/run-prototype-ui.sh --port $((REQUESTED_PORT + 1))"
    exit 1
  elif [[ "$PORT_STATUS" == "2" ]]; then
    echo "Port probe is unavailable in this shell; starting server without preflight port check."
  fi
elif [[ "$SHOW_HELP" == "0" ]]; then
  SELECTED_PORT="$REQUESTED_PORT"
  set +e
  port_available "$REQUESTED_HOST" "$SELECTED_PORT"
  PORT_STATUS="$?"
  set -e
  if [[ "$PORT_STATUS" == "1" ]]; then
    echo "Port $SELECTED_PORT is already in use on $REQUESTED_HOST; searching for a free port..."
    FOUND_PORT=""
    for ((candidate = REQUESTED_PORT + 1; candidate <= REQUESTED_PORT + 50; candidate++)); do
      set +e
      port_available "$REQUESTED_HOST" "$candidate"
      CANDIDATE_STATUS="$?"
      set -e
      if [[ "$CANDIDATE_STATUS" == "0" ]]; then
        FOUND_PORT="$candidate"
        break
      elif [[ "$CANDIDATE_STATUS" == "2" ]]; then
        echo "Port probe is unavailable in this shell; starting server without preflight port check."
        FOUND_PORT="$REQUESTED_PORT"
        break
      fi
    done

    if [[ -z "$FOUND_PORT" ]]; then
      echo "No free port found from $REQUESTED_PORT to $((REQUESTED_PORT + 50))."
      exit 1
    fi
    SELECTED_PORT="$FOUND_PORT"
  elif [[ "$PORT_STATUS" == "2" ]]; then
    echo "Port probe is unavailable in this shell; starting server without preflight port check."
  fi
  APP_ARGS+=(--port "$SELECTED_PORT")
fi

if [[ "$SHOW_HELP" == "0" && "$HOST_EXPLICIT" == "0" ]]; then
  APP_ARGS+=(--host "$REQUESTED_HOST")
fi

if [[ "$SHOW_HELP" == "1" ]]; then
  echo "Showing prototype UI help..."
else
  echo "Starting prototype UI server on $REQUESTED_HOST:${SELECTED_PORT:-$REQUESTED_PORT}..."
  echo "Pass --mock for scripted demo mode, for example: scripts/run-prototype-ui.sh --mock"
fi
python -m pysecretary prototype-ui "${APP_ARGS[@]}"
