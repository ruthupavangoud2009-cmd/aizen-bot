#!/usr/bin/env bash
set -e

echo "================================================================="
echo "=== Building KYOKA Discord Bot & Embedded Lavalink Node ==="
echo "================================================================="

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAVALINK_DIR="${BASE_DIR}/lavalink-node"
PLUGINS_DIR="${LAVALINK_DIR}/plugins"
mkdir -p "${LAVALINK_DIR}" "${PLUGINS_DIR}" "${BASE_DIR}/data/music_cache"

# 1. System packages if running as root
if [ "$(id -u)" -eq 0 ] && command -v apt-get >/dev/null 2>&1; then
    echo "Installing voice/audio packages and system tools (root)..."
    apt-get update -y && apt-get install -y --no-install-recommends \
        curl ca-certificates libopus0 ffmpeg \
        && rm -rf /var/lib/apt/lists/* || true
fi

# 2. Check for Java runtime; download portable Eclipse Temurin 21 if missing
if command -v java >/dev/null 2>&1; then
    echo "Found system Java: $(java -version 2>&1 | head -n 1)"
elif [ -x "${BASE_DIR}/.jre/bin/java" ]; then
    echo "Found local JRE: $("${BASE_DIR}/.jre/bin/java" -version 2>&1 | head -n 1)"
else
    echo "No Java found in PATH. Downloading portable Eclipse Temurin 21 JRE..."
    mkdir -p "${BASE_DIR}/.jre"
    TEMURIN_URL="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.6%2B7/OpenJDK21U-jre_x64_linux_hotspot_21.0.6_7.tar.gz"
    if curl -fsSL "${TEMURIN_URL}" | tar -xz -C "${BASE_DIR}/.jre" --strip-components=1 2>/dev/null; then
        echo "Installed portable Eclipse Temurin 21 JRE into ${BASE_DIR}/.jre"
    else
        echo "Notice: Could not download JRE binary automatically (Docker runtime will supply JRE via multi-stage build)."
    fi
fi

# 3. Download Lavalink 4.2.2 binary if missing
LAVALINK_VERSION="4.2.2"
if [ ! -f "${LAVALINK_DIR}/Lavalink.jar" ] || [ $(wc -c < "${LAVALINK_DIR}/Lavalink.jar") -lt 1000000 ]; then
    echo "Downloading Lavalink ${LAVALINK_VERSION}..."
    curl -fsSL -o "${LAVALINK_DIR}/Lavalink.jar" \
        "https://github.com/lavalink-devs/Lavalink/releases/download/${LAVALINK_VERSION}/Lavalink.jar" || true
fi

# 4. Pre-download plugins from kyoka-lavalink
if [ ! -f "${PLUGINS_DIR}/youtube-plugin-1.18.2.jar" ]; then
    echo "Pre-downloading YouTube plugin 1.18.2..."
    curl -fsSL -o "${PLUGINS_DIR}/youtube-plugin-1.18.2.jar" \
        "https://maven.lavalink.dev/releases/dev/lavalink/youtube/youtube-plugin/1.18.2/youtube-plugin-1.18.2.jar" || true
fi

if [ ! -f "${PLUGINS_DIR}/lavasrc-plugin-4.8.3.jar" ]; then
    echo "Pre-downloading LavaSrc plugin 4.8.3..."
    curl -fsSL -o "${PLUGINS_DIR}/lavasrc-plugin-4.8.3.jar" \
        "https://maven.lavalink.dev/releases/com/github/topi314/lavasrc/lavasrc-plugin/4.8.3/lavasrc-plugin-4.8.3.jar" || true
fi

# 5. Upgrade pip and install Python requirements
echo "Installing Python dependencies..."
python -m pip install --no-cache-dir --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt

echo "=== Combined Build completed successfully ==="
