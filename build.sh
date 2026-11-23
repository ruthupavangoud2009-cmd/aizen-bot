#!/usr/bin/env bash
set -e

echo "================================================================="
echo "=== Building KYOKA Discord Bot (Ultra-Lean Mode) ==="
echo "================================================================="

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${BASE_DIR}/data/music_cache"
chmod +x "${BASE_DIR}/build.sh" 2>/dev/null || true

# 1. System packages if running as root
if [ "$(id -u)" -eq 0 ] && command -v apt-get >/dev/null 2>&1; then
    echo "Installing voice/audio packages and system tools (root)..."
    apt-get update -y && apt-get install -y --no-install-recommends \
        curl ca-certificates libopus0 ffmpeg procps \
        && rm -rf /var/lib/apt/lists/* || true
fi

# 2. Upgrade pip and install Python dependencies
echo "Installing Python dependencies..."
python -m pip install --no-cache-dir --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt

echo "=== Build completed successfully ==="
