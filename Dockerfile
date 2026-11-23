# ==============================================================================
# KYOKA BOT + EMBEDDED LAVALINK V4 - COMBINED PRODUCTION CONTAINER
# ==============================================================================
# Dual-stack runtime: Eclipse Temurin JRE 21 + Python 3.11 Debian
# Runs both Kyoka Discord Bot and dedicated local Lavalink node in ONE container.
# Optimized for 500MB / 512MB container hosting (Render Free / Starter tier).
# ==============================================================================

# Stage 1: Official Eclipse Temurin 21 JRE for Lavalink
FROM eclipse-temurin:21-jre-jammy AS jre-base

# Stage 2: Production Python 3.11 Runtime
FROM python:3.11-slim-bookworm

# Copy JRE 21 from Stage 1
ENV JAVA_HOME=/opt/java/openjdk
COPY --from=jre-base /opt/java/openjdk /opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Install audio, font, procps, and Java runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates fontconfig procps libopus0 ffmpeg default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python requirements & install
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy complete application source
COPY . /app/

# Pre-stage Lavalink V4.2.2 binary and plugins deterministically inside final image
ARG LAVALINK_VERSION=4.2.2
RUN mkdir -p /app/lavalink-node/plugins /app/lavalink-node/logs /app/data/music_cache && \
    curl -fsSL -o /app/lavalink-node/Lavalink.jar \
    "https://github.com/lavalink-devs/Lavalink/releases/download/${LAVALINK_VERSION}/Lavalink.jar" && \
    curl -fsSL -o /app/lavalink-node/plugins/youtube-plugin-1.18.2.jar \
    "https://maven.lavalink.dev/releases/dev/lavalink/youtube/youtube-plugin/1.18.2/youtube-plugin-1.18.2.jar" && \
    curl -fsSL -o /app/lavalink-node/plugins/lavasrc-plugin-4.8.3.jar \
    "https://maven.lavalink.dev/releases/com/github/topi314/lavasrc/lavasrc-plugin/4.8.3/lavasrc-plugin-4.8.3.jar"

# Make scripts executable
RUN chmod +x /app/build.sh /app/build-lavalink.sh /app/scripts/run_combined.py 2>/dev/null || true

# Default environment configuration for private local connection (strict 500MB container ceiling)
ENV LAVALINK_HOST=127.0.0.1 \
    LAVALINK_PORT=2333 \
    LAVALINK_SECURE=false \
    LAVALINK_IDENTIFIER=kyoka-lavalink-local \
    LAVALINK_URI=http://127.0.0.1:2333 \
    CONTAINER_MAX_RAM_MB=500 \
    JAVA_OPTS="-Xmx180m -Xms48m -XX:+UseSerialGC -XX:MaxMetaspaceSize=80m -XX:ReservedCodeCacheSize=24m -XX:MaxDirectMemorySize=24m -Xss256k -Dio.netty.allocator.type=unpooled -Dfile.encoding=UTF-8 -Djava.security.egd=file:/dev/./urandom" \
    PORT=10000 \
    PYTHONUNBUFFERED=1

# Expose HTTP port for Discord bot HealthServer & Dashboard (Lavalink port 2333 stays internal)
EXPOSE 10000

# Supervisor entrypoint manages both Lavalink V4 and Kyoka Discord Bot
ENTRYPOINT ["python", "scripts/run_combined.py"]
CMD []
