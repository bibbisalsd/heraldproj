#!/usr/bin/env bash
# =============================================================================
# Jarvis v0.2 - Full Auto Installer (Linux)
# Phase 6: Install-Pack Finalization
#
# Supports: Ubuntu/Debian (apt), Fedora/RHEL (dnf), Arch (pacman)
# Usage:    chmod +x full_auto_install.sh && ./full_auto_install.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_MIN_VERSION="3.11"

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

# ─────────────────────────────────────────────────────────────────────────────
# Step 0: Detect package manager
# ─────────────────────────────────────────────────────────────────────────────
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

PKG_MANAGER=$(detect_pkg_manager)
info "Detected package manager: $PKG_MANAGER"

install_system_deps() {
    info "Installing system dependencies..."
    case "$PKG_MANAGER" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y -qq \
                python3 python3-venv python3-pip python3-dev \
                portaudio19-dev ffmpeg curl wget git \
                xdotool wmctrl xclip scrot \
                libsndfile1 libffi-dev build-essential
            ;;
        dnf)
            sudo dnf install -y \
                python3 python3-devel python3-pip \
                portaudio-devel ffmpeg curl wget git \
                xdotool wmctrl xclip scrot \
                libsndfile-devel libffi-devel gcc
            ;;
        pacman)
            sudo pacman -Syu --noconfirm \
                python python-pip python-virtualenv \
                portaudio ffmpeg curl wget git \
                xdotool wmctrl xclip scrot \
                libsndfile libffi base-devel
            ;;
        *)
            warn "Unknown package manager. Please install dependencies manually:"
            warn "  python3, portaudio, ffmpeg, xdotool, wmctrl, xclip, scrot"
            return 1
            ;;
    esac
    ok "System dependencies installed"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Check Python version
# ─────────────────────────────────────────────────────────────────────────────
check_python() {
    local py_cmd=""
    for cmd in python3.12 python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            py_cmd="$cmd"
            break
        fi
    done

    if [ -z "$py_cmd" ]; then
        fail "Python 3.11+ not found. Install python3.11 or newer."
        exit 1
    fi

    local py_version
    py_version=$("$py_cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    info "Found Python: $py_cmd ($py_version)"

    # Ensure >= 3.11
    local major minor
    major=$("$py_cmd" -c "import sys; print(sys.version_info.major)")
    minor=$("$py_cmd" -c "import sys; print(sys.version_info.minor)")
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        fail "Python ${PYTHON_MIN_VERSION}+ required, found ${py_version}"
        exit 1
    fi

    echo "$py_cmd"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Create virtual environment
# ─────────────────────────────────────────────────────────────────────────────
setup_venv() {
    local py_cmd="$1"

    if [ -d "$VENV_DIR" ]; then
        info "Virtual environment already exists at $VENV_DIR"
    else
        info "Creating virtual environment..."
        "$py_cmd" -m venv "$VENV_DIR"
        ok "Virtual environment created at $VENV_DIR"
    fi

    # Activate
    source "$VENV_DIR/bin/activate"
    info "Activated venv: $(which python)"

    # Upgrade pip
    python -m pip install --upgrade pip setuptools wheel -q
    ok "pip/setuptools/wheel upgraded"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Install Python dependencies
# ─────────────────────────────────────────────────────────────────────────────
install_python_deps() {
    info "Installing Python requirements..."

    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements.txt" -q
        ok "Core requirements installed"
    fi

    if [ -f "$PROJECT_ROOT/requirements-voice.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements-voice.txt" -q
        ok "Voice requirements installed"
    fi

    if [ -f "$PROJECT_ROOT/requirements-dev.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements-dev.txt" -q
        ok "Dev requirements installed"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Check Ollama
# ─────────────────────────────────────────────────────────────────────────────
check_ollama() {
    if command -v ollama &>/dev/null; then
        ok "Ollama found: $(ollama --version 2>/dev/null || echo 'unknown version')"
    else
        warn "Ollama not found. Install from: https://ollama.ai/download"
        warn "Run: curl -fsSL https://ollama.ai/install.sh | sh"
        return 0
    fi

    # Check if ollama is running
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama service is running"
    else
        warn "Ollama is installed but not running. Start with: ollama serve"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Pull required models
# ─────────────────────────────────────────────────────────────────────────────
pull_models() {
    if ! command -v ollama &>/dev/null; then
        warn "Skipping model pull (ollama not installed)"
        return 0
    fi

    if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
        warn "Skipping model pull (ollama not running)"
        return 0
    fi

    local models=("llama3.2:3b" "deepcoder:14b" "nomic-embed-text-v2-moe")
    info "Pulling required models..."

    for model in "${models[@]}"; do
        if ollama list 2>/dev/null | grep -q "$model"; then
            ok "Model already present: $model"
        else
            info "Pulling $model (this may take a while)..."
            ollama pull "$model" || warn "Failed to pull $model"
        fi
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Verify GPU (optional)
# ─────────────────────────────────────────────────────────────────────────────
verify_gpu() {
    info "Checking GPU availability..."
    if [ -f "$SCRIPT_DIR/../scripts/verify_gpu.sh" ]; then
        bash "$SCRIPT_DIR/../scripts/verify_gpu.sh"
    else
        if command -v nvidia-smi &>/dev/null; then
            ok "NVIDIA GPU detected"
            nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true
        elif command -v rocm-smi &>/dev/null; then
            ok "AMD ROCm GPU detected"
            rocm-smi --showproductname 2>/dev/null || true
        else
            info "No GPU detected — CPU mode will be used"
        fi
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Create data directories
# ─────────────────────────────────────────────────────────────────────────────
create_dirs() {
    info "Creating data directories..."
    mkdir -p "$PROJECT_ROOT/.data"
    mkdir -p "$PROJECT_ROOT/logs"
    mkdir -p "$PROJECT_ROOT/backups"
    mkdir -p "$PROJECT_ROOT/artifacts"
    mkdir -p "$PROJECT_ROOT/.crsis/history"
    ok "Data directories ready"
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 8: Write .env if missing
# ─────────────────────────────────────────────────────────────────────────────
create_env() {
    local env_file="$PROJECT_ROOT/.env"
    if [ -f "$env_file" ]; then
        info ".env already exists, skipping"
        return 0
    fi

    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$env_file"
        ok "Created .env from .env.example"
    else
        cat > "$env_file" << 'ENVEOF'
JARVIS_MEMORY_DB_PATH=./.data/jarvis_memory.sqlite
JARVIS_LOG_DIR=./logs
JARVIS_KOKORO_PACK_DIR=./voice_packs
JARVIS_ENABLE_SEMANTIC_MEMORY_RETRIEVAL=true
ENVEOF
        ok "Created default .env"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║       Jarvis v0.2 — Linux Full Auto Installer              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    install_system_deps
    echo ""

    PY_CMD=$(check_python)
    setup_venv "$PY_CMD"
    echo ""

    install_python_deps
    echo ""

    check_ollama
    echo ""

    pull_models
    echo ""

    verify_gpu
    echo ""

    create_dirs
    create_env
    echo ""

    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                   Installation Complete                     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    ok "To activate the environment: source $VENV_DIR/bin/activate"
    ok "To start voice mode:         python run_voice.py"
    ok "To start chat mode:          python run_chat.py"
    echo ""
}

main "$@"
