#!/bin/bash
# --- 3. Jupyter Kernel Gateway Startup Script ---
# This script is designed to be run as a systemd service at startup.
# It activates the correct Python environment and launches the Jupyter Kernel Gateway,
# redirecting all output to dedicated log files for easy debugging.

# Exit on any error, treat unset variables as an error, and prevent errors in pipelines from being masked.
set -euo pipefail

# --- Configuration ───────────────────────────────────────────────────────────
# Network settings for the Jupyter Kernel Gateway API.
readonly JUPYTER_KERNEL_GATEWAY_APP_HOST="0.0.0.0"
readonly JUPYTER_KERNEL_GATEWAY_APP_PORT="8888"

# Path to the Python virtual environment.
readonly VENV_PATH="${HOME}/Desktop/.action-env"

# Log directory and file names. Using a shared mount point is recommended.
readonly LOG_DIR="/mnt/container/jupyter-kg-logs"
readonly SCRIPT_LOG_FILE="startup.log"
readonly SERVER_LOG_FILE="jupyter_server_output.log"

# XServer configuration. These are critical for GUI automation.
# They are typically provided by the systemd unit file, but we set fallbacks.
# IMPORTANT: Verify the XAUTHORITY path in your VM with `echo $XAUTHORITY`.
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"

# --- [1/6] Prepare Logging Environment ───────────────────────────────────────
# Ensure the log directory exists.
mkdir -p "${LOG_DIR}"

# Verify that the log directory is writable.
if [ ! -w "${LOG_DIR}" ]; then
    echo "FATAL ERROR: Log directory ${LOG_DIR} is not writable. Exiting." >&2
    exit 1
fi

readonly SCRIPT_LOG_PATH="${LOG_DIR}/${SCRIPT_LOG_FILE}"
readonly SERVER_LOG_PATH="${LOG_DIR}/${SERVER_LOG_FILE}"

# Redirect all of this script's output (stdout & stderr) to the main log file.
# Clear the log file at the start of each run.
exec >"${SCRIPT_LOG_PATH}" 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 Jupyter Kernel Gateway Startup Script"
echo "Timestamp:             $(date)"
echo "User:                  $(whoami)"
echo "──────────────────────────────────────────────────"
echo "Script Log File:       ${SCRIPT_LOG_PATH}"
echo "Server Output Log:     ${SERVER_LOG_PATH}"
echo "API Host:              ${JUPYTER_KERNEL_GATEWAY_APP_HOST}"
echo "API Port:              ${JUPYTER_KERNEL_GATEWAY_APP_PORT}"
echo "DISPLAY:               ${DISPLAY}"
echo "XAUTHORITY:            ${XAUTHORITY}"
echo "Virtual Env:           ${VENV_PATH}"
echo "──────────────────────────────────────────────────"


# --- [2/6] Validate Environment ──────────────────────────────────────────────
echo "[2/6] Validating environment..."

# Check for the virtual environment directory.
if [ ! -d "${VENV_PATH}" ]; then
    echo "❌ FATAL: Virtual environment not found at '${VENV_PATH}'!"
    echo "   Please run the '2-python-configuration.sh' script first."
    exit 1
fi

# Check for the XAUTHORITY file, which is crucial for GUI access.
if [ ! -r "${XAUTHORITY}" ]; then
    echo "❌ FATAL: XAUTHORITY file not found or not readable at '${XAUTHORITY}'!"
    echo "   This is critical for GUI automation. Ensure the path is correct and the service has permissions."
    exit 1
fi

echo "✅ Environment validation passed."


# --- [3/6] Activate Virtual Environment ──────────────────────────────────────
echo "[3/6] Activating virtual environment..."
# shellcheck source=/dev/null
if ! source "${VENV_PATH}/bin/activate"; then
    echo "❌ FATAL: Failed to activate virtual environment at ${VENV_PATH}."
    exit 1
fi
echo "✅ Virtual environment activated. Using Python: $(which python)"


# --- [4/6] Clean Up Stale Processes ───────────────────────────────────────────
echo "[4/6] Killing any stale 'jupyter kernelgateway' processes..."

# Construct a specific pattern to avoid killing unrelated processes.
# This targets the jupyter command being run from our specific venv on our specific port.
PFPATTERN="${VENV_PATH}/bin/jupyter.*kernelgateway.*--KernelGatewayApp.port=${JUPYTER_KERNEL_GATEWAY_APP_PORT}"

# Use pkill to find and kill the process. The `|| true` prevents the script from
# exiting if no matching processes are found (which is the normal case).
pkill -f "${PFPATTERN}" || true
echo "✅ Stale process cleanup finished."


# --- [5/6] Start Jupyter Kernel Gateway ───────────────────────────────────────
# Change to the Desktop directory to provide a consistent working directory for kernels.
cd "${HOME}/Desktop"

echo "[5/6] Starting Jupyter Kernel Gateway..."
echo "--> Server output will be redirected to: ${SERVER_LOG_PATH}"

# Use `exec` to replace the current shell process with the Jupyter server.
# This is a standard practice for service startup scripts.
# All stdout/stderr from the server is logged to its own file.
exec "${VENV_PATH}/bin/jupyter" kernelgateway \
    --KernelGatewayApp.api='kernel_gateway.jupyter_websocket' \
    --KernelGatewayApp.allow_origin='*' \
    --KernelGatewayApp.ip="${JUPYTER_KERNEL_GATEWAY_APP_HOST}" \
    --KernelGatewayApp.port="${JUPYTER_KERNEL_GATEWAY_APP_PORT}" \
    --KernelGatewayApp.prespawn_count=1 \
    --JupyterWebsocketPersonality.list_kernels=True \
    --debug > "${SERVER_LOG_PATH}" 2>&1


# --- [6/6] Fallback Error Message ─────────────────────────────────────────────
# This final section will ONLY be reached if the `exec` command itself fails to launch.
# This can happen if the jupyter executable is not found or has incorrect permissions.
echo "❌ FATAL: The 'exec jupyter kernelgateway' command failed to launch."
echo "   This indicates a problem with the executable path or permissions."
echo "   Check the virtual environment and file permissions at '${VENV_PATH}/bin/jupyter'."
exit 1
