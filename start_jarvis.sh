#!/bin/bash

# Jarvis Core Linux Launcher
# Codename: Harold

# Get the directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Determine which virtual environment to use
if [ -d ".venv" ]; then
    VENV_PATH=".venv"
elif [ -d "myvenv" ]; then
    VENV_PATH="myvenv"
else
    echo "Error: No virtual environment found (.venv or myvenv)."
    exit 1
fi

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Check for mode argument
MODE=$1

if [ "$MODE" == "chat" ]; then
    echo "Starting Jarvis in Chat Mode..."
    python3 run_chat.py
elif [ "$MODE" == "voice" ]; then
    echo "Starting Jarvis in Voice Mode..."
    python3 run_voice.py
else
    echo "Usage: ./start_jarvis.sh [chat|voice]"
    echo "Defaulting to Chat Mode..."
    python3 run_chat.py
fi
