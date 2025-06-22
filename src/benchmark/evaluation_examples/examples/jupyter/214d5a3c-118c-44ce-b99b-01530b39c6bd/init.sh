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
cd $HOME/Desktop || {
    echo "Error: Could not change directory to ~/Desktop."
    exit 1
}

echo "🛠  Checking virtual environment at $VENV_PATH..."
if [ ! -d ".action-env/bin" ]; then
    echo "❌ Virtual environment '.action-env' not found! Please ensure 'action_server.sh' or manual setup created it first."
    exit 1
fi

echo "Activating virtual environment for package installation..."
source "$VENV_PATH/bin/activate"
if [ $? -ne 0 ]; then
    echo "❌ Failed to activate virtual environment."
    exit 1
fi
echo "✅ Virtual environment activated."

echo "📦 Installing Python packages with uv pip..."
uv pip install jupyter ipykernel numpy pandas matplotlib seaborn scipy scikit-learn

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install Python packages with uv pip."
    exit 1
fi
echo "✅ Python packages installed."

# Ensure the kernel is registered with Jupyter. Crucial for Jupyter Gateway.
echo "Registering ipykernel with Jupyter..."
python -m ipykernel install --user --name .action-env --display-name ".action-env"
if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to register ipykernel."
    exit 1
fi
echo "✅ ipykernel registered."

# ─── Launch VSCode in Background ───────────────────────────────────────────────
echo "🖥  Launching VSCode in the background from ~/Desktop..."

# --- Ensure DISPLAY is set for graphical applications ---
# This assumes your VM's main graphical session runs on :0
export DISPLAY=":0"
echo "✅ Hardcoded DISPLAY set to: $DISPLAY"

# 'code .' launches VSCode from the current directory (~/Desktop)
# 'nohup ... & ' runs the command in the background, detached from the SSH session,
# and redirects its stdout/stderr to the specified log file.
nohup code . Categorical-Data.ipynb >> "$VSCODE_LOG" 2>&1 &

# Give VSCode a brief moment to start up.
echo "Giving VSCode 5 seconds to initialize..."
sleep 5
echo "✅ Setup complete. VSCode should be running in the background."



