#!/usr/bin/env bash
set -e

echo "=== Installing dependencies for KYOKA Discord Bot (low-disk mode) ==="

# Install system dependencies only when the host permits it.
if command -v apt-get >/dev/null 2>&1; then
    echo "Installing optional voice/audio system packages..."
    apt-get update -y && apt-get install -y --no-install-recommends libopus0 ffmpeg         && rm -rf /var/lib/apt/lists/* || true
fi

# Disable pip's download cache to reduce disk usage on constrained hosts.
python -m pip install --no-cache-dir --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt

echo "=== Build completed successfully ==="
