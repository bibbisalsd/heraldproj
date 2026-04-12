#!/bin/bash

# Jarvis Unified Virtual Environment Script
# Combines .venv, myvenv, and .audit_venv into a single .venv

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "Creating new unified .venv..."

# Create a clean .venv
python3 -m venv .venv_new
source .venv_new/bin/activate

# Install all requirements
echo "Installing requirements from all files..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-voice.txt
pip install -r requirements-dev.txt

# Verify the environment
echo "Verifying environment..."
python3 -c "import jarvis; print('Jarvis package import: SUCCESS')"

# Switch the environment
deactivate
echo "Switching old .venv with new one..."

# Move the current .venv if it exists
if [ -d ".venv" ]; then
    mv .venv .venv_old
fi

# Move the new one in place
mv .venv_new .venv

echo "SUCCESS: Unified .venv created and active."
echo "You can now safely delete .venv_old, myvenv, and .audit_venv."
