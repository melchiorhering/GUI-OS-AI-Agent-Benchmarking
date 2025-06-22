#!/bin/bash
# --- 3. Systemd Service Setup and Startup Script ---

set -e

# Define the username for configuration
VM_USERNAME="user"
VM_USER_HOME="/home/$VM_USERNAME"

echo "Starting systemd service configuration for user: $VM_USERNAME"

# --- Define GUI Service Environment ---
# Determine the correct XAUTHORITY path for the user
VM_USER_UID=$(id -u "$VM_USERNAME")
XAUTHORITY_PATH="/run/user/${VM_USER_UID}/gdm/Xauthority"

# --- Configure Jupyter Kernel Gateway Systemd Service ---
echo "Setting up Jupyter Kernel Gateway systemd service..."

# The user must have already copied '4-jupyter-kernel-gateway.sh' to this path
KG_SCRIPT_PATH="${VM_USER_HOME}/4-jupyter-kernel-gateway.sh"
KG_SERVICE_FILE="/etc/systemd/system/jupyter-kg.service"

sudo tee "$KG_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Jupyter Kernel Gateway Service
Wants=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
User=${VM_USERNAME}
WorkingDirectory=${VM_USER_HOME}/Desktop
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${XAUTHORITY_PATH}"
ExecStart=${KG_SCRIPT_PATH}
Restart=on-failure
RestartSec=5s
TimeoutStartSec=120

[Install]
WantedBy=graphical.target
EOF

echo "Jupyter service file created."

# --- Configure FastAPI Observation Server Systemd Service ---
echo "Setting up FastAPI Observation Server systemd service..."

# The user must have already copied '5-fastapi-observation-server.sh' to this path
FASTAPI_SCRIPT_PATH="${VM_USER_HOME}/5-fastapi-observation-server.sh"
FASTAPI_SERVICE_FILE="/etc/systemd/system/observation-server.service"

sudo tee "$FASTAPI_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=FastAPI Observation Server
Wants=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
User=${VM_USERNAME}
WorkingDirectory=${VM_USER_HOME}/observation-server
# IMPORTANT: These DISPLAY/XAUTHORITY settings are crucial for screenshots.
Environment="DISPLAY=:0"
Environment="XAUTHORITY=${XAUTHORITY_PATH}"
# ADD THIS LINE to tell systemd where to find uv
Environment="PATH=${VM_USER_HOME}/.local/bin:/usr/bin:/bin"
ExecStart=${FASTAPI_SCRIPT_PATH}
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
EOF

echo "FastAPI service file created."

# --- Reload, Enable, and Start Services ---
echo "Reloading systemd, and enabling services..."
sudo chmod 0644 "$KG_SERVICE_FILE"
sudo chmod 0644 "$FASTAPI_SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable jupyter-kg.service
sudo systemctl enable observation-server.service

echo "Starting all configured application services..."
sudo systemctl start jupyter-kg.service
sudo systemctl start observation-server.service

# --- Verify Service Status ---
echo "Verifying service statuses (services may take a moment to fully start)..."
sleep 5
systemctl status jupyter-kg.service --no-pager | head -n 5
echo "---"
systemctl status observation-server.service --no-pager | head -n 5

echo "Service setup complete. Check 'journalctl -u <service-name>.service -f' for live logs."