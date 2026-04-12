#!/usr/bin/env bash
# =============================================================================
# Jarvis v0.2 - GPU Validation Script (Linux)
# Phase 5: AMD Acceptance & GPU Readiness
#
# Probes nvidia-smi, rocm-smi, or intel_gpu_top to determine
# the GPU hardware platform and write a validation report.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="$PROJECT_ROOT/artifacts"
REPORT_FILE="$REPORT_DIR/gpu_validation.md"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

mkdir -p "$REPORT_DIR"

GPU_VENDOR="none"
GPU_NAME="unknown"
GPU_MEMORY="unknown"
GPU_DRIVER="unknown"
GPU_STATUS="cpu_only"
ROCM_AVAILABLE="false"
CUDA_AVAILABLE="false"

# ─────────────────────────────────────────────────────────────────────────────
# NVIDIA Detection
# ─────────────────────────────────────────────────────────────────────────────
check_nvidia() {
    if ! command -v nvidia-smi &>/dev/null; then
        return 1
    fi

    info "nvidia-smi found, querying GPU..."
    GPU_VENDOR="nvidia"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    GPU_DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")

    # Check CUDA availability
    if nvidia-smi --query-gpu=compute_cap --format=csv,noheader &>/dev/null; then
        CUDA_AVAILABLE="true"
    fi

    GPU_STATUS="nvidia_gpu"
    ok "NVIDIA GPU: $GPU_NAME ($GPU_MEMORY, driver $GPU_DRIVER)"
    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# AMD ROCm Detection
# ─────────────────────────────────────────────────────────────────────────────
check_amd_rocm() {
    if ! command -v rocm-smi &>/dev/null; then
        # Try the alternative path
        if [ -x /opt/rocm/bin/rocm-smi ]; then
            export PATH="/opt/rocm/bin:$PATH"
        else
            return 1
        fi
    fi

    info "rocm-smi found, querying GPU..."
    GPU_VENDOR="amd"

    # Extract GPU name
    GPU_NAME=$(rocm-smi --showproductname 2>/dev/null | grep -oP '(?:Card series:\s+)\K.*' | head -1 || echo "unknown")
    if [ "$GPU_NAME" = "unknown" ] || [ -z "$GPU_NAME" ]; then
        GPU_NAME=$(rocm-smi --showproductname 2>/dev/null | grep -i "card" | head -1 | sed 's/.*:\s*//' || echo "AMD GPU")
    fi

    # Extract VRAM
    GPU_MEMORY=$(rocm-smi --showmeminfo vram 2>/dev/null | grep -i "total" | head -1 | awk '{print $NF}' || echo "unknown")

    # ROCm version
    GPU_DRIVER=$(rocm-smi --showdriverversion 2>/dev/null | grep -oP '\d+\.\d+.*' | head -1 || echo "unknown")
    if [ "$GPU_DRIVER" = "unknown" ] && [ -f /opt/rocm/.info/version ]; then
        GPU_DRIVER=$(cat /opt/rocm/.info/version 2>/dev/null || echo "unknown")
    fi

    ROCM_AVAILABLE="true"
    GPU_STATUS="amd_rocm_gpu"
    ok "AMD ROCm GPU: $GPU_NAME (VRAM: $GPU_MEMORY, ROCm: $GPU_DRIVER)"

    # Check for common Ollama ROCm compatibility
    if command -v ollama &>/dev/null; then
        local ollama_gpu
        ollama_gpu=$(ollama ps 2>/dev/null | grep -i "gpu" || echo "")
        if [ -n "$ollama_gpu" ]; then
            ok "Ollama is using GPU acceleration"
        else
            warn "Ollama may not be using ROCm. Ensure HSA_OVERRIDE_GFX_VERSION is set if needed."
        fi
    fi

    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Intel GPU Detection
# ─────────────────────────────────────────────────────────────────────────────
check_intel() {
    if ! command -v intel_gpu_top &>/dev/null; then
        # Check for Intel iGPU via lspci
        if lspci 2>/dev/null | grep -qi "intel.*graphics"; then
            GPU_VENDOR="intel"
            GPU_NAME=$(lspci 2>/dev/null | grep -i "intel.*graphics" | head -1 | sed 's/.*: //')
            GPU_STATUS="intel_igpu"
            info "Intel iGPU detected: $GPU_NAME"
            warn "Intel GPU support for Ollama is limited. CPU mode recommended."
            return 0
        fi
        return 1
    fi

    GPU_VENDOR="intel"
    GPU_NAME="Intel GPU (intel_gpu_top available)"
    GPU_STATUS="intel_gpu"
    ok "Intel GPU tools available"
    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Check Ollama GPU usage
# ─────────────────────────────────────────────────────────────────────────────
check_ollama_gpu() {
    if ! command -v ollama &>/dev/null; then
        warn "Ollama not installed — skipping GPU integration check"
        return 0
    fi

    if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
        warn "Ollama not running — skipping GPU integration check"
        return 0
    fi

    info "Checking Ollama GPU utilization..."
    local models_loaded
    models_loaded=$(ollama ps 2>/dev/null || echo "")
    if [ -n "$models_loaded" ]; then
        echo "$models_loaded"
    else
        info "No models currently loaded in Ollama"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Write Report
# ─────────────────────────────────────────────────────────────────────────────
write_report() {
    cat > "$REPORT_FILE" << EOF
# GPU Validation Report

- **checked_at_utc**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- **status**: $GPU_STATUS
- **vendor**: $GPU_VENDOR
- **gpu_name**: $GPU_NAME
- **gpu_memory**: $GPU_MEMORY
- **driver_version**: $GPU_DRIVER
- **cuda_available**: $CUDA_AVAILABLE
- **rocm_available**: $ROCM_AVAILABLE
- **host**: $(hostname)
- **kernel**: $(uname -r)

## Summary

$(if [ "$GPU_STATUS" = "cpu_only" ]; then
    echo "No dedicated GPU detected. Jarvis will run in CPU mode."
    echo "This is fully supported — latency may be higher for large models."
elif [ "$GPU_STATUS" = "nvidia_gpu" ]; then
    echo "NVIDIA GPU detected with CUDA support. Ollama should automatically use GPU acceleration."
elif [ "$GPU_STATUS" = "amd_rocm_gpu" ]; then
    echo "AMD GPU with ROCm detected. Ensure Ollama is built with ROCm support."
    echo "If using an RDNA3 card (e.g., RX 7900/9070), you may need: HSA_OVERRIDE_GFX_VERSION=11.0.0"
elif [ "$GPU_STATUS" = "intel_gpu" ] || [ "$GPU_STATUS" = "intel_igpu" ]; then
    echo "Intel GPU detected. GPU acceleration for Ollama is limited on Intel."
    echo "CPU mode is recommended for best compatibility."
fi)
EOF

    ok "GPU validation report written to: $REPORT_FILE"
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Jarvis v0.2 — GPU Validation Script              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    if check_nvidia; then
        :
    elif check_amd_rocm; then
        :
    elif check_intel; then
        :
    else
        info "No GPU acceleration detected — CPU mode will be used"
        GPU_STATUS="cpu_only"
    fi

    echo ""
    check_ollama_gpu

    echo ""
    write_report

    echo ""
    echo "────────────────────────────────────────────────────────────────"
    echo "  Vendor:  $GPU_VENDOR"
    echo "  GPU:     $GPU_NAME"
    echo "  Memory:  $GPU_MEMORY"
    echo "  Driver:  $GPU_DRIVER"
    echo "  Status:  $GPU_STATUS"
    echo "────────────────────────────────────────────────────────────────"
    echo ""
}

main "$@"
