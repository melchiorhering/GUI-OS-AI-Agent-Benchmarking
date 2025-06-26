#!/bin/bash
# --- 3. Systemd Service Setup and Startup Script ---
# This script creates, enables, and starts the systemd services required to
# run the Jupyter Kernel Gateway and the FastAPI Observation Server automatically
# on machine boot.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ───────────────────────────────────────────────────────────
readonly VM_USERNAME="user"
readonly VM_USER_HOME="/home/${VM_USERNAME}"

# --- Script Start ────────────────────────────────────────────────────────────
echo "--- Starting Systemd Service Configuration for user: ${VM_USERNAME} ---"

# --- [1/5] Define GUI Service Environment ────────────────────────────────────
echo "[1/5] Determining GUI environment variables for systemd services..."

# Dynamically find the user's UID to construct the correct XAUTHORITY path.
# This makes the script more robust than hardcoding '1000'.
VM_USER_UID=$(id -u "$VM_USERNAME")
if [ -z "$VM_USER_UID" ]; then
    echo "❌ FATAL: Could not determine UID for user '${VM_USERNAME}'." >&2
    exit 1
fi
readonly XAUTHORITY_PATH="/run/user/${VM_USER_UID}/gdm/Xauthority"
echo "--> XAUTHORITY path set to: ${XAUTHORITY_PATH}"


# --- [2/5] Validate Prerequisite Scripts ─────────────────────────────────────
echo "[2/5] Verifying that the required service scripts exist..."
readonly KG_SCRIPT_PATH="${VM_USER_HOME}/4-jupyter-kernel-gateway.sh"
readonly FASTAPI_SCRIPT_PATH="${VM_USER_HOME}/5-fastapi-observation-server.sh"

if [ ! -f "$KG_SCRIPT_PATH" ]; then
    echo "❌ FATAL: Jupyter startup script not found at '${KG_SCRIPT_PATH}'."
    echo "   Please ensure you have copied it to the VM's home directory."
    exit 1
fi

if [ ! -f "$FASTAPI_SCRIPT_PATH" ]; then
    echo "❌ FATAL: FastAPI startup script not found at '${FASTAPI_SCRIPT_PATH}'."
    echo "   Please ensure you have copied it to the VM's home directory."
    exit 1
fi
echo "✅ All service scripts found."


# --- [3/5] Create Systemd Service Unit Files ─────────────────────────────────
echo "[3/5] Creating systemd service unit files..."

# --- Jupyter Kernel Gateway Service ---
readonly KG_SERVICE_FILE="/etc/systemd/system/jupyter-kg.service"
echo "--> Writing Jupyter service file to ${KG_SERVICE_FILE}..."
sudo tee "$KG_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Jupyter Kernel Gateway Service
# This service should start after a graphical session is available.
Wants=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
User=${VM_USERNAME}
WorkingDirectory=${VM_USER_HOME}/Desktop
# Environment variables required for the service to interact with the GUI.
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${XAUTHORITY_PATH}"
ExecStart=/bin/bash ${KG_SCRIPT_PATH}
# Restart the service automatically if it fails.
Restart=on-failure
RestartSec=5s
TimeoutStartSec=120

[Install]
# This enables the service to be started with the graphical environment.
WantedBy=graphical.target
EOF

# --- FastAPI Observation Server Service ---
readonly FASTAPI_SERVICE_FILE="/etc/systemd/system/observation-server.service"
echo "--> Writing FastAPI service file to ${FASTAPI_SERVICE_FILE}..."
sudo tee "$FASTAPI_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=FastAPI Observation Server
# This service also depends on the graphical session.
Wants=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
User=${VM_USERNAME}
WorkingDirectory=${VM_USER_HOME}/observation-server
# The PATH must include the location of 'uv' for the server to work.
Environment="PATH=${VM_USER_HOME}/.local/bin:/usr/bin:/bin"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${XAUTHORITY_PATH}"
ExecStart=/bin/bash ${FASTAPI_SCRIPT_PATH}
# Restart the service automatically on any exit.
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
EOF

echo "✅ Systemd service files created successfully."


# --- [4/5] Reload, Enable, and Start Services ────────────────────────────────
echo "[4/5] Reloading systemd daemon and enabling services..."
# Set correct, secure permissions for the service files.
sudo chmod 0644 "$KG_SERVICE_FILE"
sudo chmod 0644 "$FASTAPI_SERVICE_FILE"
# Reload systemd to make it aware of the new/changed files.
sudo systemctl daemon-reload
# Enable the services to start automatically on boot.
sudo systemctl enable jupyter-kg.service
sudo systemctl enable observation-server.service
echo "✅ Services enabled."

echo "--> Attempting to start all services..."
sudo systemctl start jupyter-kg.service
sudo systemctl start observation-server.service
echo "✅ Start command issued for all services."


# --- [5/5] Verify Service Status ─────────────────────────────────────────────
echo "[5/5] Verifying initial service statuses..."
echo "--- (Services may take a few moments to fully initialize) ---"
sleep 5 # Give services a moment to start up before checking status.

echo -e "\n--- Jupyter Kernel Gateway Status ---"
systemctl status jupyter-kg.service --no-pager | cat

echo -e "\n--- FastAPI Observation Server Status ---"
systemctl status observation-server.service --no-pager | cat

echo -e "\n---"
echo "Service setup is complete."
echo "To monitor live logs, use: 'journalctl -u <service-name> -f'"
echo "Example: 'journalctl -u jupyter-kg.service -f'"
