#!/bin/bash
# --- 1. OS Configuration Script ---
# This script automates OS-level setup for the QEMU/KVM Ubuntu VM.
# It handles system updates, package installation, user permissions,
# and critical bug fixes for the graphical environment.

# Exit immediately if a command exits with a non-zero status.
set -e

# Define the username for configuration
VM_USERNAME="user"
VM_USER_HOME="/home/$VM_USERNAME"

echo "--- Starting OS-level configuration for user: $VM_USERNAME ---"

# --- System Updates and Core Package Installation ---
echo "[1/7] Updating system and installing core packages..."
sudo apt-get update -y
sudo apt-get dist-upgrade -y

# Combine common packages for better readability and efficiency
sudo apt-get install -y \
    curl \
    wget \
    git \
    htop \
    net-tools \
    build-essential \
    software-properties-common \
    ca-certificates \
    gnome-screenshot \
    python3-tk \
    python3-dev \
    scrot

echo "Core packages installed."

# --- Create and Configure Shared Directory Mount Point ---
echo "[2/7] Creating shared directory mount point at /mnt/container..."

# Create the directory where the shared volume will be mounted inside the VM
sudo mkdir -p /mnt/container

# Change ownership to the VM_USERNAME so services running as that user can write to it
sudo chown -R ${VM_USERNAME}:${VM_USERNAME} /mnt/container

echo "Shared directory configured for user '${VM_USERNAME}'."


# --- Passwordless sudo for the '$VM_USERNAME' account ---
echo "[3/7] Configuring passwordless sudo for $VM_USERNAME..."
SUDOERS_FILE="/etc/sudoers.d/10-passwordless-$VM_USERNAME"
sudo mkdir -p /etc/sudoers.d/
echo "$VM_USERNAME ALL=(ALL) NOPASSWD:ALL" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
echo "Passwordless sudo configured."

# --- Configure GUI Environment (X11) ---
echo "[4/7] Configuring GUI environment..."

# --- Disable Wayland and Default to X11 ---
echo "--> Forcing X11 as the default display server..."
# This is necessary for compatibility with GUI automation tools like pyautogui.
GDM_CUSTOM_CONF="/etc/gdm3/custom.conf"
if sudo grep -q '^#.*WaylandEnable=false' "$GDM_CUSTOM_CONF"; then
    sudo sed -i 's/^#\(WaylandEnable=false\)/\1/' "$GDM_CUSTOM_CONF"
    echo "    - Successfully disabled Wayland in $GDM_CUSTOM_CONF."
else
    echo "    - Wayland already disabled or configuration line not found."
fi

# --- CRITICAL FIX: Prevent X11 Black Screen Bug ---
echo "--> Applying fix for X11 black screen bug..."
PAM_LOGIN_FILE="/etc/pam.d/login"
# This bug is caused by pam_lastlog.so. Commenting it out prevents the black screen issue.
# The `sed` command finds the line containing "pam_lastlog.so" that is not already commented out
# and adds a '#' at the beginning.
if sudo grep -q '^[[:space:]]*session[[:space:]]\+optional[[:space:]]\+pam_lastlog.so' "$PAM_LOGIN_FILE"; then
    sudo sed -i -E 's/^(session\s+optional\s+pam_lastlog.so)/# \1/' "$PAM_LOGIN_FILE"
    echo "    - Successfully patched $PAM_LOGIN_FILE to prevent X11 bug."
else
    echo "    - PAM login file already patched or line not found."
fi


# --- SSH Minimal Configuration ---
echo "[5/7] Configuring SSH server..."
SSHD_CONFIG_DIR="/etc/ssh/sshd_config.d"
SSHD_CUSTOM_CONF="$SSHD_CONFIG_DIR/10-sandbox.conf"
sudo mkdir -p "$SSHD_CONFIG_DIR"
# This config allows for easy access during development.
# WARNING: This is an insecure configuration and should not be used in production.
sudo tee "$SSHD_CUSTOM_CONF" > /dev/null <<EOF
Port 22
PermitRootLogin yes
PasswordAuthentication yes
X11Forwarding yes
PubkeyAuthentication no
AcceptEnv *
PermitUserEnvironment yes
EOF
sudo chmod 0644 "$SSHD_CUSTOM_CONF"
echo "SSH server configuration created."

# --- Enable and Restart SSH Service ---
echo "[6/7] Enabling and restarting SSH service..."
sudo systemctl enable ssh
sudo systemctl restart ssh
echo "SSH service enabled on boot and restarted."


echo "[7/7] OS-level configuration complete."
echo "---"
echo "A reboot is recommended for all changes to take effect."
echo "Next, run the Python configuration script (2-python-configuration.sh)."
