#!/bin/bash
set -euo pipefail

# ─── Load user profile if present ──────────────────────────────────────────────
# Crucial for picking up DISPLAY and other global settings from ~/.profile
if [ -f "${HOME}/.profile" ]; then source "${HOME}/.profile"; fi

# ─── ENV Defaults ─────────────────────────────────────────────────────────────
: "${TASK_SETUP_LOG:=task-setup.log}" # Log for this init.sh script
: "${VSCODE_LOG:=vscode_launch.log}"  # Separate log for VS Code launch output

export TASK_SETUP_LOG VSCODE_LOG

# ─── Prepare Logging for THIS SCRIPT (init.sh) ────────────────────────────────
LOG_PATH="/mnt/container/$TASK_SETUP_LOG"
VSCODE_LOG="/mnt/container/$VSCODE_LOG"
# Clear the log file on each run of the setup script
echo "" >"$LOG_PATH"
# Redirect all stdout/stderr of THIS SCRIPT to the log file and console
exec > >(tee -a "$LOG_PATH") 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 VM Setup Script (init.sh)"
echo "→ Init Script Log:     $LOG_PATH"
echo "→ VSCode Launch Log:   $VSCODE_LOG"
echo "──────────────────────────────────────────────────"

# ─── Virtual Environment Setup and Package Installation ────────────────────────
VENV_PATH="$HOME/Desktop/.action-env"

echo "🛠  Navigating to ~/Desktop..."
cd "$HOME/Desktop" || {
    echo "❌ Error: Could not change directory to $HOME/Desktop. Aborting."
    exit 1
}

echo "🛠  Checking for virtual environment at $VENV_PATH..."
if [ ! -d "$VENV_PATH/bin" ]; then # More specific check for activate script parent
    echo "❌ Virtual environment '$VENV_PATH' not found or incomplete! Please ensure it was created correctly."
    exit 1
fi

echo "⏳ Activating virtual environment..."
source "$VENV_PATH/bin/activate"
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to activate virtual environment at $VENV_PATH."
    exit 1
fi
echo "✅ Virtual environment activated."


echo "📦 Installing Python packages with uv pip..."
uv pip install jupyter

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install Python packages with uv pip."
    exit 1
fi
echo "✅ Python packages installed."

# Create the Jupyter kernel
python -m ipykernel install --user --name "jupyter-kernel" --display-name "jupyter-kernel"

# --- Ensure DISPLAY is set for graphical applications ---
# This assumes your VM's main graphical session runs on :0
export DISPLAY=":0"
echo "✅ Hardcoded DISPLAY set to: $DISPLAY"

# Open the terminal in the user's home directory
gnome-terminal --working-directory=/home/user
