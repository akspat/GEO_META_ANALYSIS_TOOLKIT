#!/usr/bin/env bash
# scripts/setup_ubuntu.sh
#
# Verifies and sets up the environment for the Gene Expression Standardization Tool on:
#   Native Ubuntu 24 | 8 GB VRAM GPU
#
# Run with:
#   chmod +x scripts/setup_ubuntu.sh
#   ./scripts/setup_ubuntu.sh
#
# IMPORTANT:
#   Make sure you have installed the proprietary NVIDIA driver on your Ubuntu system
#   before running this script. You can do this via 'Software & Updates' -> 'Additional Drivers'
#   or via command line: sudo ubuntu-drivers autoinstall

set -e

echo "======================================================================"
echo " Gene Expression Standardization Tool — Ubuntu / 8 GB VRAM GPU Environment Check"
echo "======================================================================"

# ── 1. Check GPU visibility ────────────────────────────────────────────────────
echo ""
echo "[1/5] Checking GPU visibility..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    echo "  [OK] GPU detected."
else
    echo "  [FAIL] nvidia-smi not found."
    echo "  Fix: install the NVIDIA driver on your Ubuntu system:"
    echo "       sudo ubuntu-drivers autoinstall"
    echo "  Then reboot your system."
    exit 1
fi

# ── 2. Python version ──────────────────────────────────────────────────────────
echo ""
echo "[2/5] Checking Python version..."
PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "  Found Python $PY_VERSION"
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "  WARNING: Python 3.10+ recommended. Consider: sudo apt install python3.11"
fi

# ── 3. Virtual environment ─────────────────────────────────────────────────────
echo ""
echo "[3/5] Setting up virtual environment..."
cd "$(dirname "$0")/.."   # move to project root
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  [OK] Created venv/"
else
    echo "  [OK] venv/ already exists"
fi
source venv/bin/activate

# ── 4. PyTorch with CUDA ───────────────────────────────────────────────────────
echo ""
echo "[4/5] Installing PyTorch with CUDA support..."
pip install --upgrade pip --quiet
pip install torch --index-url https://download.pytorch.org/whl/cu121 --quiet
python3 -c "
import torch
print(f'  PyTorch version : {torch.__version__}')
print(f'  CUDA available  : {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'  GPU name        : {torch.cuda.get_device_name(0)}')
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f'  VRAM            : {vram:.1f} GB')
else:
    print('  WARNING: CUDA not available to PyTorch. Embeddings will run on CPU')
    print('           (still works, just ~5-10x slower for index building).')
"

# ── 5. Project dependencies ────────────────────────────────────────────────────
echo ""
echo "[5/5] Installing project dependencies..."
pip install -r requirements.txt --quiet
echo "  [OK] Dependencies installed"

# ── 6. Ollama check ─────────────────────────────────────────────────────────────
echo ""
echo "[6/6] Checking Ollama..."
if command -v ollama &> /dev/null; then
    echo "  [OK] Ollama is installed."
    if curl -s http://localhost:11434/api/tags &> /dev/null; then
        echo "  [OK] Ollama service is running."
    else
        echo "  Ollama installed but not running. Start it with: ollama serve &"
    fi
else
    echo "  Ollama not found. Install with:"
    echo "       curl -fsSL https://ollama.com/install.sh | sh"
    echo "  Then pull the model:"
    echo "       ollama pull medgemma:4b"
fi

echo ""
echo "======================================================================"
echo " Setup check complete."
echo ""
echo " Next steps:"
echo "   1. cp .env.example .env   (then edit NCBI_EMAIL at minimum)"
echo "   2. ollama pull medgemma:4b      (~3.5GB download, one-time)"
echo "   3. python scripts/build_index.py  (~15-20 min, one-time)"
echo "   4. ./venv/bin/python -m streamlit run app.py"
echo "======================================================================"
