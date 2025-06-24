#!/bin/bash
set -euo pipefail

# This script starts the FastAPI observation server using the `fastapi run` command.
# It's designed to be run as a systemd service, relying on the unit file for
# DISPLAY and XAUTHORITY, which are essential for GUI operations.

# --- Configuration ---
FASTAPI_HOST="0.0.0.0"
FASTAPI_PORT="8765"
# The root directory of your FastAPI project.
PROJECT_PATH="${HOME}/observation-server"

# Log directory and file names
LOG_DIR="/mnt/container/fastapi-observation-logs" # Dedicated log directory
SCRIPT_LOG="startup.log"                          # Log for this script's execution
SERVER_LOG="server.log"                           # Log for the FastAPI/Uvicorn server's output

# XServer configuration - these should be set by the systemd unit file
DISPLAY="${DISPLAY:-:0}"
XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"

export DISPLAY XAUTHORITY

# --- Prepare Logging ---
# Exit if the log directory does not exist or we can't write to it.
if ! mkdir -p "${LOG_DIR}" || [ ! -w "${LOG_DIR}" ]; then
    echo "ERROR: Log directory ${LOG_DIR} is not accessible or writable. Exiting." >&2
    exit 1
fi

LOG_PATH="${LOG_DIR}/${SCRIPT_LOG}"
SERVER_LOG_PATH="${LOG_DIR}/${SERVER_LOG}"

# Redirect all script and server output to a log file AND systemd's journal.
# The server's output will be captured by this as well.
exec &> >(tee "${SERVER_LOG_PATH}")

echo "──────────────────────────────────────────────────"
echo "🚀 FastAPI Observation Server Startup Script"
echo "Timestamp: $(date)"
echo "User: $(whoami)"
echo "→ Project Path:      ${PROJECT_PATH}"
echo "→ Log Directory:     ${LOG_DIR}"
echo "→ API Host:          ${FASTAPI_HOST}"
echo "→ API Port:          ${FASTAPI_PORT}"
echo "→ DISPLAY:           ${DISPLAY}"
echo "→ XAUTHORITY:        ${XAUTHORITY}"
echo "──────────────────────────────────────────────────"

# --- Prerequisite Check ---
echo "🛠️  Checking for project directory at '${PROJECT_PATH}'..."
if [ ! -d "${PROJECT_PATH}" ]; then
    echo "❌ Project directory not found at '${PROJECT_PATH}'! Please ensure the path is correct."
    exit 1
fi

VENV_FASTAPI_EXEC="${PROJECT_PATH}/.venv/bin/fastapi"
echo "🛠️  Checking if 'fastapi' command is available at '${VENV_FASTAPI_EXEC}'..."
if ! [ -x "${VENV_FASTAPI_EXEC}" ]; then
    echo "❌ 'fastapi' command not found or not executable at '${VENV_FASTAPI_EXEC}'."
    echo "   Please ensure your dependencies (like fastapi-cli) are installed in the venv."
    exit 1
fi
echo "✅ 'fastapi' command is available: ${VENV_FASTAPI_EXEC}"

# --- Configure X Server Permissions for GUI Automation ---
# This is critical for allowing the FastAPI server to take screenshots.
if [ -n "${DISPLAY}" ] && command -v xhost &>/dev/null; then
    echo "🖼️  Attempting to grant local user access to the X server..."
    # Allow the user running this script to connect to the X server.
    xhost +SI:localuser:"$(whoami)" || echo "ℹ️  xhost command finished (non-critical errors are suppressed)."
    echo "✅ X server permissions updated."
else
    echo "⚠️  xhost command not found or DISPLAY is not set. Screenshots and GUI automation may fail."
fi

# --- Clean Up Stale Processes ---
echo "🧹 Killing any stale processes on port ${FASTAPI_PORT}..."
# Use fuser to reliably kill processes using the target TCP port. This is more
# robust than pkill, as it doesn't depend on the process name.
fuser -k -n tcp "${FASTAPI_PORT}" || true
echo "✅ Stale process cleanup attempt finished."

# --- Start FastAPI Server ---
echo "📍 Changing directory to project path: '${PROJECT_PATH}'..."
cd "${PROJECT_PATH}" || { echo "❌ Failed to change directory to ${PROJECT_PATH}"; exit 1; }
echo "✅ Current working directory: $(pwd)"

echo "🚀 Starting FastAPI server with the 'fastapi run' command..."
# 'exec' replaces the shell process with the server process, which is a best practice for systemd.
# The server's output (stdout/stderr) is already being redirected by the 'exec &>' at the top.
exec "${VENV_FASTAPI_EXEC}" run main.py \
    --host "${FASTAPI_HOST}" \
    --port "${FASTAPI_PORT}"

# This part of the script will only be reached if the `exec` command itself fails to launch.
echo "❌ FATAL: The 'exec' command failed to launch the server. This should not happen." >&2
exit 1
