#!/bin/bash
# --- 5. FastAPI Observation Server Startup Script ---
# This script is designed to be run as a systemd service at startup.
# It installs project dependencies using 'uv' and launches the FastAPI server.

# Exit on any error, treat unset variables as an error, and prevent errors in pipelines from being masked.
set -euo pipefail

# --- Configuration ───────────────────────────────────────────────────────────
# Network settings for the FastAPI application.
readonly FASTAPI_HOST="0.0.0.0"
readonly FASTAPI_PORT="8765"

# The root directory of your FastAPI project.
readonly PROJECT_PATH="${HOME}/observation-server"
# The virtual environment path, managed by 'uv'.
readonly VENV_PATH="${PROJECT_PATH}/.venv"
# The requirements file for 'uv sync'. Assumes pyproject.toml but can be changed.
readonly REQ_FILE="pyproject.toml"

# Log directory and file names.
readonly LOG_DIR="/mnt/container/fastapi-observation-logs"
readonly SCRIPT_LOG_FILE="startup.log"
readonly SERVER_LOG_FILE="fastapi_server_output.log"

# XServer configuration required for GUI automation (e.g., screenshots).
# These are typically provided by the systemd unit file.
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"

# --- [1/7] Prepare Logging Environment ───────────────────────────────────────
mkdir -p "${LOG_DIR}"
if [ ! -w "${LOG_DIR}" ]; then
    echo "FATAL ERROR: Log directory ${LOG_DIR} is not writable. Exiting." >&2
    exit 1
fi

readonly SCRIPT_LOG_PATH="${LOG_DIR}/${SCRIPT_LOG_FILE}"
readonly SERVER_LOG_PATH="${LOG_DIR}/${SERVER_LOG_FILE}"

# Redirect all of this script's output (stdout and stderr) to its log file.
exec >"${SCRIPT_LOG_PATH}" 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 FastAPI Observation Server Startup Script"
echo "Timestamp:           $(date)"
echo "User:                $(whoami)"
echo "──────────────────────────────────────────────────"
echo "Project Path:        ${PROJECT_PATH}"
echo "Virtual Env (uv):    ${VENV_PATH}"
echo "Script Log File:     ${SCRIPT_LOG_PATH}"
echo "Server Output Log:   ${SERVER_LOG_PATH}"
echo "API Host:            ${FASTAPI_HOST}"
echo "API Port:            ${FASTAPI_PORT}"
echo "DISPLAY:             ${DISPLAY}"
echo "XAUTHORITY:          ${XAUTHORITY}"
echo "──────────────────────────────────────────────────"

# --- [2/7] Change Directory & Validate Environment ───────────────────────────
echo "[2/7] Validating environment..."
if ! cd "${PROJECT_PATH}"; then
    echo "❌ FATAL: Project directory not found at '${PROJECT_PATH}'! Cannot continue."
    exit 1
fi
echo "--> Changed directory to ${PROJECT_PATH}"

if [ ! -f "main.py" ]; then
    echo "❌ FATAL: main.py not found in project directory '${PROJECT_PATH}'!"
    exit 1
fi
if [ ! -f "${REQ_FILE}" ]; then
    echo "❌ FATAL: Requirements file '${REQ_FILE}' not found for 'uv sync'!"
    exit 1
fi
if [ ! -r "${XAUTHORITY}" ]; then
    echo "❌ FATAL: XAUTHORITY file not found or not readable at '${XAUTHORITY}'!"
    exit 1
fi
if ! command -v uv &>/dev/null; then
    echo "❌ FATAL: 'uv' command not found. Please ensure it is installed."
    exit 1
fi
echo "✅ Environment validation passed."

# --- [3/7] Install/Sync Dependencies with UV ─────────────────────────────────
echo "[3/7] Installing/syncing dependencies with 'uv'..."
# This command creates the .venv if it doesn't exist and syncs dependencies
# from pyproject.toml (or requirements.txt)
uv sync --no-cache
echo "✅ Dependencies are in sync."

# --- [4/7] Configure X Server Permissions for GUI ────────────────────────────
echo "[4/7] Configuring X server permissions for GUI automation..."
# This allows the server to connect to the X display for screenshots.
if [ -n "${DISPLAY}" ] && command -v xhost &>/dev/null; then
    # The '+SI:localuser:...' grants access only to the specified local user.
    xhost +SI:localuser:"$(whoami)" || echo "ℹ️  xhost command finished (non-critical errors are common)."
    echo "✅ X server permissions updated."
else
    echo "⚠️  xhost command not found or DISPLAY is not set. Screenshots will likely fail."
fi

# --- [5/7] Clean Up Stale Processes ───────────────────────────────────────────
echo "[5/7] Killing any stale processes on port ${FASTAPI_PORT}..."
# `fuser` finds and kills processes using a specific network port.
# The `|| true` prevents the script from exiting if no process is found.
fuser -k -n tcp "${FASTAPI_PORT}" || true
echo "✅ Stale process cleanup finished."

# --- [6/7] Start FastAPI Server ───────────────────────────────────────────────
echo "[6/7] Starting FastAPI server..."
echo "--> Server executable: '${VENV_PATH}/bin/fastapi'"
echo "--> Server output will be redirected to: ${SERVER_LOG_PATH}"

# Use 'exec' to replace this script's process with the FastAPI server process.
# We use the full path to the 'fastapi' executable created by 'uv'.
# The server's output is redirected to its own log file.
exec "${VENV_PATH}/bin/fastapi" run main.py \
    --host "${FASTAPI_HOST}" \
    --port "${FASTAPI_PORT}" \
    --workers 1 > "${SERVER_LOG_PATH}" 2>&1

# --- [7/7] Fallback Error Message ─────────────────────────────────────────────
# This final section will only be reached if the `exec` command itself fails.
echo "❌ FATAL: The 'exec fastapi run' command failed to launch."
echo "   This indicates a problem with the virtual environment or the 'fastapi' installation."
exit 1
