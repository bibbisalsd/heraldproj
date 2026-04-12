#!/bin/bash
# Install CUDA and system dependencies for Jarvis on Pop!_OS / Linux

set -e

echo "Updating package lists..."
sudo apt-get update

echo "Installing system dependencies for Voice and Tools..."
# xdotool and wmctrl for app_ops.py
# scrot and imagemagick for screen_capture.py
# portaudio19-dev for sounddevice/pyaudio
sudo apt-get install -y \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    portaudio19-dev \
    libavformat-dev \
    libavcodec-dev \
    libswresample-dev \
    libavutil-dev \
    python3-dev \
    build-essential

echo "Checking for NVIDIA drivers..."
if nvidia-smi &> /dev/null; then
    echo "NVIDIA driver detected. Installing CUDA and cuDNN libraries..."
    # Pop!_OS uses system76-cuda-latest for easy CUDA setup
    sudo apt-get install -y system76-cuda-latest
    
    # Also need the specific libraries for faster-whisper (cudnn)
    # We'll install via pip if possible, but system libraries are more stable
    sudo apt-get install -y libcudnn8 libcudnn8-dev
else
    echo "NVIDIA driver not found or nvidia-smi failed. Skipping CUDA-specific system packages."
fi

echo "Installing/Updating Python dependencies..."
# Ensure we are in the right venv if possible, but we'll assume the user runs this in their venv
pip install --upgrade pip
pip install \
    faster-whisper \
    mss \
    Pillow \
    sounddevice \
    soundfile \
    numpy

echo "Setup complete. Please restart your shell or re-activate your virtual environment."
