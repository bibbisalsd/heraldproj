#!/bin/bash

# Jarvis VRAM Monitor
# Specifically for 6GB RTX 4050 tracking during BG1 tasks

echo "Monitoring NVIDIA GPU VRAM usage. Press Ctrl+C to stop."
echo "Target: 6GB Limit (Jarvis Budget)"

# Run nvidia-smi every 1 second and clear the screen
watch -n 1 nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
