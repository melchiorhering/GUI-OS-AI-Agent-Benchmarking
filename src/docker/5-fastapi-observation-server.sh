#!/bin/bash
set -euo pipefail

# This script starts the FastAPI observation server and is designed to be run as a
# systemd service on startup. It relies on the systemd unit file to provide
# DISPLAY and XAUTHORITY, which are essential for GUI operations like taking screenshots.

# ─── Configuration ────────────────────────────────────────────────────────────
FASTAPI_HOST="0.0.0.0"
FASTAPI_PORT="8765"
# The root directory of your FastAPI project.
PROJECT_PATH="${HOME}/observation-server"

# Log directory and file names
LOG_DIR="/mnt/container/fastapi-observation-logs" # Dedicated log directory
SCRIPT_LOG="startup.log"         # Log for this script's execution
SERVER_OUT_LOG="server.log"      # Log for the Uvicorn server's output

# XServer configuration - these should be set by the systemd unit file
DISPLAY="${DISPLAY:-:0}"
XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"

export DISPLAY XAUTHORITY
export FASTAPI_HOST FASTAPI_PORT

# ─── Prepare Logging ──────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}" # Ensure the log directory exists

if [ ! -w "${LOG_DIR}" ]; then
    echo "ERROR: Log directory ${LOG_DIR} is not writable. Exiting." >&2
    exit 1
fi

LOG_PATH="${LOG_DIR}/${SCRIPT_LOG}"
SERVER_OUT_FULL_PATH="${LOG_DIR}/${SERVER_OUT_LOG}"

# Clear the main script log file at the start of each run.
: >"${LOG_PATH}"
# All subsequent output from this script will go to this log file.
exec >"${LOG_PATH}" 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 FastAPI Observation Server Startup Script"
echo "Timestamp: $(date)"
echo "User: $(whoami)"
echo "→ Project Path:           ${PROJECT_PATH}"
echo "→ Log Directory:          ${LOG_DIR}"
echo "→ Script Log File:        ${LOG_PATH}"
echo "→ Server Output Log:      ${SERVER_OUT_FULL_PATH}"
echo "→ API Host:               ${FASTAPI_HOST}"
echo "→ API Port:               ${FASTAPI_PORT}"
echo "→ DISPLAY:                ${DISPLAY}"
echo "→ XAUTHORITY:             ${XAUTHORITY}"
echo "──────────────────────────────────────────────────"

# ─── Prerequisite Check ───────────────────────────────────────────────────────
echo "🛠️  Checking for project directory at '${PROJECT_PATH}'..."
if [ ! -d "${PROJECT_PATH}" ]; then
    echo "❌ Project directory not found at '${PROJECT_PATH}'! Please ensure the path is correct."
    exit 1
fi

echo "🛠️  Checking if 'uv' command is available..."
if ! command -v uv &> /dev/null; then
    echo "❌ 'uv' command not found. Please ensure 'uv' is installed and in the system's PATH."
    exit 1
fi
echo "✅ 'uv' is available: $(command -v uv)"

# ─── Configure X Server Permissions for GUI Automation ────────────────────────
# This is critical for allowing the FastAPI server to take screenshots.
if [ -n "${DISPLAY}" ]; then
    echo "🖼️  Attempting to grant local user access to the X server..."
    if command -v xhost &> /dev/null; then
        xhost +SI:localuser:"$(whoami)" || echo "ℹ️  xhost command ran (may have non-critical errors)."
        echo "✅ X server permissions updated (or attempt made)."
    else
        echo "⚠️ WARNING: xhost command not found. Screenshots and GUI automation will likely fail."
    fi
else
    echo "ℹ️  DISPLAY environment variable not set, skipping X server permission configuration."
fi

# ─── Clean Up Stale Processes ──────────────────────────────────────────────────
echo "🧹 Killing any stale 'uvicorn' processes on port ${FASTAPI_PORT}..."
# This pattern is specific enough to target the server started by this script.
# The '|| true' prevents the script from exiting if no processes are found.
pkill -f "uvicorn main:app --host ${FASTAPI_HOST} --port ${FASTAPI_PORT}" || true
echo "✅ Stale processes cleanup attempt finished."

# ─── Start FastAPI Server ───────────────────────────────────────────────────────
echo "📍 Changing directory to project path: '${PROJECT_PATH}'..."
cd "${PROJECT_PATH}" || { echo "❌ Failed to change directory to ${PROJECT_PATH}"; exit 1; }
echo "✅ Current working directory: $(pwd)"

echo "🚀 Starting FastAPI server with 'uv run'..."
# 'uv run' will automatically use the project's virtual environment.
# 'exec' replaces the shell process with the server process, which is best practice for systemd.
# The server's output (stdout/stderr) is redirected to its own log file.
exec uv run uvicorn main:app \
    --host "${FASTAPI_HOST}" \
    --port "${FASTAPI_PORT}" \
    --log-level debug > "${SERVER_OUT_FULL_PATH}" 2>&1

# This part of the script will only be reached if the `exec` command itself fails.
echo "❌ ERROR: 'uv run' command failed to launch. Check ${SERVER_OUT_FULL_PATH} for details."
exit 1