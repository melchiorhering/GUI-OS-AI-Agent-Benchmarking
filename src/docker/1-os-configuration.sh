#!/bin/bash
# --- 1. OS Configuration Script ---
# This script automates OS-level setup for the QEMU/KVM Ubuntu VM.

# Exit immediately if a command exits with a non-zero status.
set -e

# Define the username for configuration
VM_USERNAME="user"
VM_USER_HOME="/home/$VM_USERNAME"

echo "Starting OS-level configuration for user: $VM_USERNAME"

# --- System Updates and Core Package Installation ---
echo "Updating system and installing core packages..."
sudo apt update -y
sudo apt dist-upgrade -y

# Combine common packages for better readability and efficiency
sudo apt install -y \
    openssh-server \
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
echo "Creating shared directory mount point at /mnt/container..."

# Create the directory where the shared volume will be mounted inside the VM
sudo mkdir -p /mnt/container

# Change ownership to the VM_USERNAME so services running as that user can write to it
sudo chown -R ${VM_USERNAME}:${VM_USERNAME} /mnt/container

echo "Shared directory configured and permissions set for user '${VM_USERNAME}'."


# --- Passwordless sudo for the '$VM_USERNAME' account ---
echo "Configuring passwordless sudo for $VM_USERNAME..."
SUDOERS_FILE="/etc/sudoers.d/10-passwordless-$VM_USERNAME"
sudo mkdir -p /etc/sudoers.d/
echo "$VM_USERNAME ALL=(ALL) NOPASSWD:ALL" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
echo "Passwordless sudo configured for $VM_USERNAME."

# --- Disable Wayland and Default to X11 ---
echo "Disabling Wayland to default to X11 display server..."
# The GDM (GNOME Display Manager) configuration determines which display server to use.
# By uncommenting 'WaylandEnable=false', we force GDM to use X11.
# This is often necessary for compatibility with screen sharing, remote desktop apps, and certain drivers.
GDM_CUSTOM_CONF="/etc/gdm3/custom.conf"
if sudo grep -q '^#.*WaylandEnable=false' "$GDM_CUSTOM_CONF"; then
    sudo sed -i 's/^#\(WaylandEnable=false\)/\1/' "$GDM_CUSTOM_CONF"
    echo "Successfully set X11 as the default display server."
else
    echo "Wayland configuration line not found or already uncommented in $GDM_CUSTOM_CONF."
fi


# --- SSH Minimal Configuration ---
echo "Configuring SSH server..."
SSHD_CONFIG_DIR="/etc/ssh/sshd_config.d"
SSHD_CUSTOM_CONF="$SSHD_CONFIG_DIR/10-sandbox.conf"
sudo mkdir -p "$SSHD_CONFIG_DIR"
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
# Test the config file, then restart the 'ssh' service to apply changes
sudo sshd -t && sudo systemctl restart ssh # Changed 'reload' to 'restart'
echo "SSH server configured and restarted."

# --- Enable SSH at Boot ---
echo "Enabling SSH to start at boot..."
sudo systemctl enable ssh
echo "SSH enabled at boot."

echo "OS-level configuration complete. A reboot is required for the display server change to take effect."
echo "Next, run the Python configuration script."