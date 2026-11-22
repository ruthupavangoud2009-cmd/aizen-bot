#!/usr/bin/env python3
"""
==============================================================================
KYOKA SUPERVISOR — COMBINED BOT & LAVALINK MONOLITHIC PROCESS RUNNER
==============================================================================
Manages both the Discord Bot and dedicated local Lavalink v4 audio engine
under a single host deployment.

Key Responsibilities:
1. Dynamic host resource detection & JVM memory allocation (30 GB headroom).
2. Starts local Lavalink bound strictly to 127.0.0.1:2333 loopback.
3. Health-polls /version until Lavalink is 100% online before launching the bot.
4. Starts KYOKA Discord Bot with loopback connection parameters.
5. Bidirectional health monitoring & automatic crash recovery with backoff.
6. Graceful signal trapping (SIGTERM, SIGINT) preventing zombie/orphaned Java processes.
==============================================================================
"""

from __future__ import annotations

import os
import sys
import time
import signal
import shutil
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Kyoka.Supervisor] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Kyoka.Supervisor")

BASE_DIR = Path(__file__).resolve().parent.parent
LAVALINK_DIR = BASE_DIR / "lavalink-node"
JAR_PATH = LAVALINK_DIR / "Lavalink.jar"
APP_YML_PATH = LAVALINK_DIR / "application.yml"


def detect_host_ram_mb() -> int:
    """Detect total host RAM in Megabytes safely across Linux and Termux."""
    # 1. Try reading /proc/meminfo
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            with open(meminfo, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        parts = line.split()
                        return int(parts[1]) // 1024  # kB to MB
    except Exception:
        pass

    # 2. Try sysconf
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) // (1024 * 1024)
    except Exception:
        pass

    # Fallback assumption (8 GB)
    return 8192


def calculate_jvm_opts(host_ram_mb: int) -> list[str]:
    """Calculate optimized JVM heap and GC settings for host resource availability."""
    env_opts = os.getenv("JAVA_OPTS")
    if env_opts and env_opts.strip():
        logger.info(f"Using custom user JAVA_OPTS from environment: {env_opts}")
        return env_opts.split()

    # High-resource allocation (host has ~30 GB RAM)
    if host_ram_mb >= 16384:  # >= 16 GB
        logger.info(f"Host has {host_ram_mb / 1024:.1f} GB RAM: Allocating 4 GB max heap + G1GC for Lavalink.")
        return [
            "-Xmx4g",
            "-Xms1g",
            "-XX:MaxMetaspaceSize=512m",
            "-XX:ReservedCodeCacheSize=128m",
            "-XX:+UseG1GC",
            "-XX:MaxGCPauseMillis=20",
            "-XX:+UseStringDeduplication",
            "-Dfile.encoding=UTF-8",
        ]
    elif host_ram_mb >= 8192:  # >= 8 GB
        logger.info(f"Host has {host_ram_mb / 1024:.1f} GB RAM: Allocating 2 GB max heap + G1GC for Lavalink.")
        return [
            "-Xmx2g",
            "-Xms512m",
            "-XX:MaxMetaspaceSize=384m",
            "-XX:ReservedCodeCacheSize=96m",
            "-XX:+UseG1GC",
            "-XX:MaxGCPauseMillis=20",
            "-XX:+UseStringDeduplication",
            "-Dfile.encoding=UTF-8",
        ]
    else:  # < 8 GB
        logger.info(f"Host has {host_ram_mb / 1024:.1f} GB RAM: Allocating 1 GB max heap for Lavalink.")
        return [
            "-Xmx1g",
            "-Xms256m",
            "-XX:MaxMetaspaceSize=256m",
            "-XX:ReservedCodeCacheSize=64m",
            "-XX:+UseG1GC",
            "-XX:MaxGCPauseMillis=20",
            "-XX:+UseStringDeduplication",
            "-Dfile.encoding=UTF-8",
        ]


def find_java_binary() -> str | None:
    """Find a valid Java runtime binary in PATH, JAVA_HOME, or common installation paths."""
    # 1. Standard PATH
    java_in_path = shutil.which("java")
    if java_in_path:
        return java_in_path

    # 2. JAVA_HOME environment variable
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    # 3. Known Docker & local paths
    common_paths = [
        Path("/opt/java/openjdk/bin/java"),
        Path("/usr/lib/jvm/default-java/bin/java"),
        Path("/usr/lib/jvm/java-21-openjdk-amd64/bin/java"),
        Path("/usr/lib/jvm/java-17-openjdk-amd64/bin/java"),
        BASE_DIR / ".jre" / "bin" / "java",
    ]
    for p in common_paths:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)

    return None


def ensure_lavalink_jar() -> Path:
    """Ensure Lavalink.jar binary is present, downloading v4.2.2 if missing."""
    if JAR_PATH.is_file() and JAR_PATH.stat().st_size > 1000000:
        return JAR_PATH

    LAVALINK_DIR.mkdir(parents=True, exist_ok=True)
    version = os.getenv("LAVALINK_VERSION", "4.2.2")
    url = f"https://github.com/lavalink-devs/Lavalink/releases/download/{version}/Lavalink.jar"
    logger.info(f"Downloading Lavalink {version} binary to {JAR_PATH}...")

    try:
        urllib.request.urlretrieve(url, str(JAR_PATH))
        logger.info(f"Downloaded Lavalink.jar ({JAR_PATH.stat().st_size / (1024*1024):.1f} MB).")
    except Exception as e:
        logger.error(f"Failed to download Lavalink binary: {e}")
        if not JAR_PATH.is_file() or JAR_PATH.stat().st_size == 0:
            raise RuntimeError(f"Lavalink.jar is required but could not be downloaded: {e}")

    return JAR_PATH


class CombinedSupervisor:
    """Supervises Lavalink backend and Kyoka Discord Bot in a single deployment."""

    def __init__(self) -> None:
        self.java_proc: subprocess.Popen | None = None
        self.bot_proc: subprocess.Popen | None = None
        self.running: bool = True
        self.lavalink_restart_count: int = 0
        self.bot_restart_count: int = 0
        self.last_lavalink_restart: float = 0.0

        # Synchronize private localhost credentials
        self.password = (
            os.getenv("LAVALINK_PASSWORD")
            or os.getenv("LAVALINK_SERVER_PASSWORD")
            or "onlyforkyoka"
        )
        os.environ["LAVALINK_PASSWORD"] = self.password
        os.environ["LAVALINK_SERVER_PASSWORD"] = self.password
        os.environ["LAVALINK_HOST"] = "127.0.0.1"
        os.environ["LAVALINK_PORT"] = "2333"
        os.environ["LAVALINK_SECURE"] = "false"
        os.environ["LAVALINK_IDENTIFIER"] = "kyoka-lavalink-local"
        os.environ["LAVALINK_URI"] = "http://127.0.0.1:2333"

    def handle_signal(self, signum: int, _) -> None:
        signame = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info(f"Signal {signame} received. Initiating graceful shutdown of all services...")
        self.running = False
        self.shutdown()
        sys.exit(0)

    def shutdown(self) -> None:
        """Gracefully stop Discord bot and Lavalink subprocesses."""
        # 1. Stop Discord Bot first so voice sessions clean up
        if self.bot_proc and self.bot_proc.poll() is None:
            logger.info("Stopping Discord Bot process (PID: %s)...", self.bot_proc.pid)
            try:
                self.bot_proc.terminate()
                self.bot_proc.wait(timeout=8.0)
            except Exception:
                try:
                    self.bot_proc.kill()
                except Exception:
                    pass

        # 2. Stop Lavalink Java process
        if self.java_proc and self.java_proc.poll() is None:
            logger.info("Stopping Lavalink Java process (PID: %s)...", self.java_proc.pid)
            try:
                self.java_proc.terminate()
                self.java_proc.wait(timeout=8.0)
            except Exception:
                try:
                    self.java_proc.kill()
                except Exception:
                    pass

        logger.info("All child services stopped cleanly. No orphaned Java processes remaining.")

    def start_lavalink(self, java_bin: str, jvm_opts: list[str]) -> bool:
        """Start Lavalink child process and wait for HTTP /version readiness."""
        ensure_lavalink_jar()
        cmd = [java_bin] + jvm_opts + ["-jar", str(JAR_PATH)]

        masked_pw = self.password[:2] + "*" * max(0, len(self.password) - 4) + self.password[-2:] if len(self.password) >= 6 else "****"
        logger.info("Starting Lavalink V4 backend on 127.0.0.1:2333 (Password: %s)...", masked_pw)

        self.java_proc = subprocess.Popen(
            cmd,
            cwd=str(LAVALINK_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        logger.info(f"Lavalink Java process spawned (PID: {self.java_proc.pid}). Awaiting readiness probe...")

        # Poll loopback HTTP readiness endpoint
        ready = False
        deadline = time.time() + 60.0
        while time.time() < deadline:
            if self.java_proc.poll() is not None:
                logger.error(f"Lavalink process exited prematurely during startup with code {self.java_proc.returncode}!")
                return False

            try:
                req = urllib.request.Request("http://127.0.0.1:2333/version")
                with urllib.request.urlopen(req, timeout=1.5) as response:
                    if response.status == 200:
                        version_str = response.read().decode("utf-8").strip()
                        logger.info(f"✅ Lavalink V4 ready on http://127.0.0.1:2333 (Version: {version_str})")
                        ready = True
                        break
            except Exception:
                pass

            time.sleep(1.0)

        if not ready:
            logger.error("Lavalink failed to respond on http://127.0.0.1:2333 within 60s!")
            return False

        return True

    def start_bot(self) -> None:
        """Start the Discord Bot process."""
        logger.info("Starting KYOKA Discord Bot (src/main.py)...")
        self.bot_proc = subprocess.Popen(
            [sys.executable, "src/main.py"],
            cwd=str(BASE_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logger.info(f"KYOKA Discord Bot process spawned (PID: {self.bot_proc.pid}).")

    def run(self) -> int:
        """Main supervisory loop managing both processes with crash resilience."""
        # Register signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.handle_signal)
            except Exception:
                pass

        ram_mb = detect_host_ram_mb()
        jvm_opts = calculate_jvm_opts(ram_mb)

        java_bin = find_java_binary()
        if not java_bin:
            logger.critical("FATAL: Java runtime binary not found on host! Ensure Java 17 or 21 is installed.")
            return 1

        logger.info(f"Found Java runtime at: {java_bin}")

        # 1. Start Lavalink first and verify it is listening
        if not self.start_lavalink(java_bin, jvm_opts):
            logger.critical("FATAL: Lavalink failed to initialize. Aborting startup.")
            self.shutdown()
            return 1

        # 2. Start Discord Bot
        self.start_bot()

        # 3. Supervisory monitoring loop
        while self.running:
            time.sleep(2.0)

            # Check Lavalink health
            if self.java_proc and self.java_proc.poll() is not None:
                exit_code = self.java_proc.returncode
                now = time.time()
                logger.warning(f"⚠️ Lavalink process terminated unexpectedly (exit code {exit_code})!")

                # Cooldown / backoff protection against rapid crash loops
                if now - self.last_lavalink_restart < 15.0:
                    self.lavalink_restart_count += 1
                else:
                    self.lavalink_restart_count = 1

                self.last_lavalink_restart = now

                if self.lavalink_restart_count > 5:
                    logger.critical("Lavalink has crashed more than 5 times in rapid succession. Halting restart.")
                    self.shutdown()
                    return 1

                logger.info(f"Auto-restarting Lavalink (attempt {self.lavalink_restart_count})...")
                time.sleep(min(3.0 * self.lavalink_restart_count, 15.0))
                self.start_lavalink(java_bin, jvm_opts)

            # Check Bot health
            if self.bot_proc and self.bot_proc.poll() is not None:
                exit_code = self.bot_proc.returncode
                if not self.running:
                    break

                logger.warning(f"⚠️ Discord Bot process exited (code {exit_code}).")
                if exit_code == 0:
                    logger.info("Bot exited cleanly (scheduled restart or client refresh). Restarting bot...")
                else:
                    logger.warning("Bot crashed. Auto-recovering in 5 seconds...")
                    time.sleep(5.0)

                self.start_bot()

        self.shutdown()
        return 0


if __name__ == "__main__":
    supervisor = CombinedSupervisor()
    sys.exit(supervisor.run())
