#!/usr/bin/env sh
# Installs everything TurboTranscribe needs on macOS / Linux. Safe to run again at any time.
#   ./setup.sh          one-time setup
#   ./setup.sh --auto   used by start.sh when dependencies are missing or changed
# Missing tools are installed with Homebrew (macOS) or apt (Debian/Ubuntu, asks for your password).
set -e
cd "$(dirname "$0")"

install_pkg() {  # install_pkg <brew name> <apt name> <human name> <url>
  if command -v brew >/dev/null 2>&1; then
    echo "      $3 is missing: installing it with Homebrew..."
    brew install "$1"
  elif command -v apt-get >/dev/null 2>&1 && [ -n "$2" ]; then
    echo "      $3 is missing: installing it with apt..."
    sudo apt-get update && sudo apt-get install -y $2
  else
    echo "[!] $3 is missing. Install it from $4 and run ./setup.sh again."
    exit 1
  fi
}

find_python() {  # prints a Python 3.10-3.13 command (the tested versions), or nothing
  for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" >/dev/null 2>&1 &&
       "$cmd" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" 2>/dev/null; then
      echo "$cmd"; return
    fi
  done
}

node_ok() {
  command -v node >/dev/null 2>&1 &&
    node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
}

echo "=== TurboTranscribe setup ==="
echo "[1/4] System tools"
if [ -x backend/venv/bin/python ] && ! backend/venv/bin/python -c "import sys" 2>/dev/null; then
  echo "      The Python environment is broken; recreating it."
  rm -rf backend/venv
fi
if [ ! -x backend/venv/bin/python ]; then
  PY=$(find_python)
  [ -n "$PY" ] || { install_pkg python@3.12 "python3 python3-venv" "Python 3.10-3.13" https://www.python.org/downloads/; PY=$(find_python); }
  [ -n "$PY" ] || { echo "[!] No Python 3.10-3.13 found. Install one and run ./setup.sh again."; exit 1; }
  echo "      Python: $PY"
fi
node_ok || install_pkg node "" "Node.js 20+" https://nodejs.org/   # distro Node.js is often too old
node_ok || { echo "[!] Node.js 20 or newer is required: https://nodejs.org/"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || install_pkg ffmpeg ffmpeg "ffmpeg" https://ffmpeg.org/download.html
echo "      Node.js $(node --version), ffmpeg found"

echo "[2/4] Python packages (about 1.2 GB the first time)"
[ -x backend/venv/bin/python ] || "$PY" -m venv backend/venv
backend/venv/bin/python -m pip install --upgrade pip >/dev/null
backend/venv/bin/python -m pip install -r backend/requirements.txt
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "      NVIDIA GPU detected: installing the CUDA libraries (about 2 GB the first time)"
  backend/venv/bin/python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
fi
cp backend/requirements.txt backend/venv/requirements.installed  # start.sh compares against this

echo "[3/4] Frontend packages"
(cd frontend && npm install --no-audit --no-fund)  # not "npm ci": it deletes node_modules first
cp frontend/package-lock.json frontend/node_modules/.turbotranscribe-lock

echo "[4/4] Settings"
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "      Created backend/.env - add OPENROUTER_API_KEY there to enable the notes assistant."
fi
echo "Setup complete. The speech model (up to 1.6 GB) downloads automatically on the first start."
[ "$1" = "--auto" ] || echo "Start with ./start.sh"
