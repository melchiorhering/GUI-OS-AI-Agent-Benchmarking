#!/bin/bash
# --- 2. Python Environment and Package Setup ---

# --- CRITICAL VERSION CONFIGURATION ---
# The Python and smolagents versions specified here MUST MATCH the versions
# used on your host machine to ensure compatibility. Please edit the values
# below before running the script.

REQUIRED_PYTHON_VERSION="3.11"
REQUIRED_SMOLAGENTS_VERSION="1.18.0" # <-- EDIT THIS to match your host's smolagents version.

# --- Script Start ---
set -e
echo "Starting Python environment configuration."
echo "---"
echo "IMPORTANT: Using Python version ${REQUIRED_PYTHON_VERSION}"
echo "IMPORTANT: Using smolagents version ${REQUIRED_SMOLAGENTS_VERSION}"
echo "---"


# --- Install UV (Python package installer) ---
echo "Installing UV..."
if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
    echo "ERROR: Failed to download and execute UV installation script." >&2
    exit 1
fi

# Manually add the expected UV install directory to the current script's PATH
export PATH="$HOME/.local/bin:$PATH"

# Verify UV installation
if ! command -v uv &> /dev/null; then
    echo "ERROR: UV command not found in PATH after installation. This is critical. Exiting." >&2
    exit 1
fi
echo "UV installed and verified."


# --- Python Environment and Jupyter Kernel Setup ---
echo "Setting up Python virtual environment and installing packages..."
VENV_PATH="$HOME/Desktop/.action-env"
mkdir -p "$HOME/Desktop"

echo "Creating virtual environment at $VENV_PATH with Python ${REQUIRED_PYTHON_VERSION}..."
# This Python version MUST match the host environment.
if ! uv venv "$VENV_PATH" --python "$REQUIRED_PYTHON_VERSION" --seed; then
    echo "ERROR: Failed to create virtual environment with Python ${REQUIRED_PYTHON_VERSION}." >&2
    exit 1
fi

# Activate the virtual environment
echo "Activating virtual environment: $VENV_PATH"
# shellcheck source=/dev/null
if ! source "$VENV_PATH/bin/activate"; then
    echo "ERROR: Failed to activate virtual environment." >&2
    exit 1
fi

echo "Installing Python packages into the virtual environment..."
# The smolagents version MUST match the host environment.
if ! uv pip install \
    jupyter_kernel_gateway \
    pyautogui \
    requests \
    numpy \
    pandas \
    ipywidgets \
    smolagents=="${REQUIRED_SMOLAGENTS_VERSION}" \
    ipykernel \
    opencv-python \
    torch \
    Pillow \
    pynput; then
    echo "ERROR: Failed to install Python packages." >&2
    exit 1
fi

echo "Python packages installed."
echo "Verifying Jupyter kernelspec list:"
jupyter kernelspec list || echo "WARNING: jupyter kernelspec list command failed."

echo "Python environment configuration finished. Next, run the server startup script."