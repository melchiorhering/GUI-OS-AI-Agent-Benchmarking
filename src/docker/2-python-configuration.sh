#!/bin/bash
# --- 2. Python Environment and Package Setup ---
# This script installs the 'uv' package manager, creates a dedicated
# Python virtual environment, and installs all necessary packages for the
# Jupyter and FastAPI servers.

# --- CRITICAL: VERSION CONFIGURATION ---
# The Python and smolagents versions specified below MUST MATCH the versions
# used on your host machine to ensure full compatibility.
# Please edit these values before running the script.

REQUIRED_PYTHON_VERSION="3.11"
REQUIRED_SMOLAGENTS_VERSION="1.18.0" # <-- EDIT THIS to match your host's smolagents version.

# --- Script Start ---
set -e # Exit immediately if a command fails.

cat <<EOF

--- Starting Python Environment Configuration ---

    Required Python version:   ${REQUIRED_PYTHON_VERSION}
    Required smolagents version: ${REQUIRED_SMOLAGENTS_VERSION}

This setup MUST match your host environment.
-------------------------------------------------
EOF

# --- [1/4] Install UV (Fast Python Package Installer) ---
echo "[1/4] Checking and installing UV package manager..."

# Check if uv is already installed to avoid re-downloading.
if command -v uv &> /dev/null; then
    echo "--> UV is already installed. Skipping installation."
else
    echo "--> UV not found. Installing..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "ERROR: Failed to download and execute UV installation script." >&2
        exit 1
    fi
    echo "--> UV installed successfully."
fi

# The installer places 'uv' in ~/.local/bin. We must add this to the current
# session's PATH to make the 'uv' command available immediately.
export PATH="$HOME/.local/bin:$PATH"

# Final verification to ensure 'uv' is accessible.
if ! command -v uv &> /dev/null; then
    echo "ERROR: UV command not found in PATH even after installation. Critical failure. Exiting." >&2
    exit 1
fi
echo "UV installation verified."


# --- [2/4] Create Python Virtual Environment ---
VENV_PATH="$HOME/Desktop/.action-env"
echo "[2/4] Setting up Python virtual environment at: $VENV_PATH"

# Create a parent directory on the Desktop for better organization.
mkdir -p "$HOME/Desktop"

# Create the virtual environment using the specified Python version.
# The '--seed' flag ensures that pip and setuptools are pre-installed.
echo "--> Creating virtual environment with Python ${REQUIRED_PYTHON_VERSION}..."
if ! uv venv "$VENV_PATH" --python "$REQUIRED_PYTHON_VERSION" --seed; then
    echo "ERROR: Failed to create virtual environment. Ensure Python ${REQUIRED_PYTHON_VERSION} is installed and accessible." >&2
    exit 1
fi
echo "Virtual environment created."


# --- [3/4] Install Python Packages ---
echo "[3/4] Installing required Python packages into the virtual environment..."

# Activate the virtual environment for the subsequent pip install command.
# shellcheck source=/dev/null
if ! source "$VENV_PATH/bin/activate"; then
    echo "ERROR: Failed to activate virtual environment at $VENV_PATH." >&2
    exit 1
fi
echo "--> Virtual environment activated."

# Install all packages in a single command for efficiency.
# The smolagents version is pinned to ensure compatibility with the host.
if ! uv pip install \
    jupyter_kernel_gateway \
    fastapi \
    uvicorn \
    pyautogui \
    requests \
    numpy \
    pandas \
    ipywidgets \
    "smolagents==${REQUIRED_SMOLAGENTS_VERSION}" \
    ipykernel \
    opencv-python \
    torch \
    Pillow \
    pynput; then
    echo "ERROR: Failed to install one or more Python packages." >&2
    exit 1
fi
echo "All Python packages installed successfully."


# --- [4/4] Final Verification ---
echo "[4/4] Verifying Jupyter kernel installation..."

# This command confirms that the Python environment is recognized as a Jupyter kernel.
if ! jupyter kernelspec list; then
    echo "WARNING: 'jupyter kernelspec list' command failed. This may indicate an issue with the Jupyter installation."
fi

echo "---"
echo "Python environment configuration complete."
echo "Next, run the server startup script (3-startup-servers.sh)."
