#!/bin/bash
set -euo pipefail

# This script is intended to be run as a systemd service at machine startup.
# It relies on the systemd unit file to provide DISPLAY and XAUTHORITY.
# Running this script manually (e.g., via SSH without X forwarding) might not
# work as expected for GUI-dependent operations.

# ─── Configuration ────────────────────────────────────────────────────────────
JUPYTER_KERNEL_GATEWAY_APP_HOST="0.0.0.0"
JUPYTER_KERNEL_GATEWAY_APP_PORT="8888"
# JUPYTER_KG_READY_TIMEOUT=60 # This variable is not used in the script, consider removing if truly unused.

# Log directory and file names
LOG_DIR="/mnt/container/jupyter-kg-logs" # Use a dedicated log directory for cleaner HOME
ACTION_LOG="action-server.log"
SERVER_OUT_LOG="action-server.log.server_out"

# XServer configuration - these defaults should be set by the systemd unit file
DISPLAY="${DISPLAY:-:0}"
XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}" # Confirm this path with 'echo $XAUTHORITY' in your VM's GUI terminal

export DISPLAY XAUTHORITY
export JUPYTER_KERNEL_GATEWAY_APP_HOST JUPYTER_KERNEL_GATEWAY_APP_PORT

# ─── Prepare Logging ──────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}" # Ensure the log directory exists

if [ ! -w "${LOG_DIR}" ]; then
    echo "ERROR: Log directory ${LOG_DIR} is not writable. Exiting." >&2
    exit 1
fi

LOG_PATH="${LOG_DIR}/${ACTION_LOG}" # Full path to the main log file
SERVER_OUT_FULL_PATH="${LOG_DIR}/${SERVER_OUT_LOG}" # Full path for Jupyter's stdout/stderr

# Clear the main log file content at the start of each run.
: >"${LOG_PATH}"
# All subsequent output from this script will go to this main log file.
exec >"${LOG_PATH}" 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 Jupyter Kernel Gateway Startup Script (3-jupyter-kernel-gateway.sh)"
echo "Timestamp: $(date)"
echo "User: $(whoami)"
echo "Current Directory: $(pwd)"
echo "→ Log Directory:                 ${LOG_DIR}"
echo "→ Main Log File:                 ${LOG_PATH}"
echo "→ Server Output Log:             ${SERVER_OUT_FULL_PATH}"
echo "→ API Host:                      ${JUPYTER_KERNEL_GATEWAY_APP_HOST}"
echo "→ API Port:                      ${JUPYTER_KERNEL_GATEWAY_APP_PORT}"
echo "→ DISPLAY:                       ${DISPLAY}"
echo "→ XAUTHORITY:                    ${XAUTHORITY}"
echo "──────────────────────────────────────────────────"

# ─── Virtual Environment Check & Activation ───────────────────────────────────
VENV_PATH="${HOME}/Desktop/.action-env"

echo "🛠️  Checking for virtual environment at '${VENV_PATH}'..."
if [ ! -d "${VENV_PATH}" ]; then
    echo "❌ Virtual environment not found at '${VENV_PATH}'!"
    echo "Please ensure the '.action-env' virtual environment exists and contains Jupyter Kernel Gateway."
    exit 1
fi

echo "🛠️  Activating virtual environment: ${VENV_PATH}"
# shellcheck source=/dev/null
if ! source "${VENV_PATH}/bin/activate"; then
    echo "❌ Failed to activate virtual environment at ${VENV_PATH}."
    exit 1
fi
echo "✅ Virtual environment activated. Python: $(which python)"

# ─── Clean Up Stale Processes ──────────────────────────────────────────────────
echo "🧹 Killing any stale 'jupyter kernelgateway' processes to ensure a clean start..."
# Use pkill with the full path from venv to be more specific.
# The `|| true` prevents the script from exiting if no processes are found.
# Use a more targeted pattern to avoid killing unrelated processes.
pkill -f "${VENV_PATH}/bin/jupyter.*kernelgateway.*--port=${JUPYTER_KERNEL_GATEWAY_APP_PORT}" || true
echo "✅ Stale processes cleanup attempt finished."

# ─── Start Jupyter Kernel Gateway ──────────────────────────────────────────────
# Change Directory In `Desktop` for consistent working directory for the kernel.
cd "$HOME/Desktop" # Use quotes for robust path handling

echo "🚀 Starting Jupyter Kernel Gateway..."
# Redirect stdout/stderr of the Jupyter process to a separate log file.
exec "${VENV_PATH}/bin/jupyter" kernelgateway \
    --KernelGatewayApp.api='kernel_gateway.jupyter_websocket' \
    --KernelGatewayApp.allow_origin='*' \
    --KernelGatewayApp.ip="${JUPYTER_KERNEL_GATEWAY_APP_HOST}" \
    --KernelGatewayApp.port="${JUPYTER_KERNEL_GATEWAY_APP_PORT}" \
    --KernelGatewayApp.prespawn_count=1 \
    --JupyterWebsocketPersonality.list_kernels=True \
    --debug > "${SERVER_OUT_FULL_PATH}" 2>&1

# This part of the script will only be reached if the `exec` command fails.
echo "❌ ERROR: Jupyter Kernel Gateway command failed to launch. Check ${SERVER_OUT_FULL_PATH} for details."
exit 1