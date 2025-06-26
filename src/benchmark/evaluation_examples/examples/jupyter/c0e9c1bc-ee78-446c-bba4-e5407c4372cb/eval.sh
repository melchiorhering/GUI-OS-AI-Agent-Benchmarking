#!/bin/bash
# Evaluation script for checking the Agents jupyter kernel setup
set -euo pipefail

# ─── Load user profile if present ──────────────────────────────────────────────
# Crucial for picking up DISPLAY and other global settings from ~/.profile
if [ -f "${HOME}/.profile" ]; then source "${HOME}/.profile"; fi


# ─── Virtual Environment Setup and Package Installation ────────────────────────
VENV_PATH="$HOME/Desktop/.action-env"

echo "🛠 Navigating to ~/Desktop..."
cd "$HOME/Desktop" || {
    echo "❌ Error: Could not change directory to $HOME/Desktop. Aborting."
    exit 1
}

echo "🛠 Checking for virtual environment at $VENV_PATH..."
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

# ─── Evaluation and Log Output ──────────────────────────────────────────────
# Define the log file path on the VM.
# IMPORTANT: This must match the 'vm_eval_logs' argument in your Python code.
EVAL_LOG="$HOME/eval.log"

# Clear the log file and then redirect ONLY the jupyter kernelspec list output to it.
# This ensures that "$HOME/eval.log" will contain nothing but the output
# of 'jupyter kernelspec list'.
jupyter kernelspec list > "$EVAL_LOG" 2>&1
