#!/usr/bin/env bash
set -e

echo "=== Installing dependencies for KYOKA Discord Bot ==="

# Install system dependencies only if running as root with apt-get
if [ "$(id -u)" -eq 0 ] && command -v apt-get >/dev/null 2>&1; then
    echo "Installing optional voice/audio system packages (root)..."
    apt-get update -y && apt-get install -y --no-install-recommends libopus0 ffmpeg \
        && rm -rf /var/lib/apt/lists/* || true
fi

# Upgrade pip and install requirements
python -m pip install --no-cache-dir --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt

echo "=== Build completed successfully ==="
