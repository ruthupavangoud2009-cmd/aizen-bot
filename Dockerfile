# ==============================================================================
# KYOKA DISCORD BOT - ULTRA-LEAN PRODUCTION CONTAINER
# ==============================================================================
# Pure Python 3.11 Debian runtime with native Opus & FFmpeg support.
# Connects to resilient public Lavalink v4 cluster (no local Java process required).
# Typical memory footprint: ~65MB - 75MB RAM.
# ==============================================================================

FROM python:3.11-slim-bookworm

# Install audio and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates procps libopus0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements & install
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy complete application source
COPY . /app/

# Make scripts executable
RUN chmod +x /app/build.sh 2>/dev/null || true

# Default environment configuration for public Lavalink v4 cluster
ENV LAVALINK_URI="https://lavalinkv4.serenetia.com:443" \
    LAVALINK_PASSWORD="https://seretia.link/discord" \
    LAVALINK_SECURE="true" \
    LAVALINK_IDENTIFIER="kyoka-lavalink-v4" \
    LAVALINK_FALLBACK_URIS="http://lava-v4.ajieblogs.eu.org:80|https://dsc.gg/ajidevserver,https://lavalink.nazha.online:443|nazhafreelava" \
    PORT=10000 \
    PYTHONUNBUFFERED=1

# Expose HTTP port for Discord bot HealthServer & Dashboard
EXPOSE 10000

# Direct Bot Entrypoint
ENTRYPOINT ["python", "-m", "src.main"]
CMD []
