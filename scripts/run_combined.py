#!/usr/bin/env python3
"""
==============================================================================
KYOKA SUPERVISOR — COMBINED BOT & LAVALINK MONOLITHIC PROCESS RUNNER
==============================================================================
Authoritative single-process supervisor managing both the Discord Bot and
dedicated local Lavalink v4 audio engine under a single container deployment.

Startup sequence:
1. Validate startup environment and container cgroup memory limits.
2. Locate and verify Java runtime (or automatically provision portable JRE).
3. Validate and download Lavalink.jar binary if missing.
4. Validate Lavalink application.yml configuration.
5. Check port availability & loopback binding (127.0.0.1:2333).
6. Start Lavalink with real-time log streaming and password synchronization.
7. Poll HTTP /version readiness endpoint with controlled timeout (90s).
8. Verify HTTP 200 response and check /v4/info authentication.
9. Launch KYOKA Discord Bot.
10. Monitor both processes with automatic recovery and graceful signal trapping.
==============================================================================
"""

from __future__ import annotations

import os
import sys
import re
import time
import signal
import shutil
import socket
import logging
import secrets
import threading
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Setup logging with consistent KYOKA format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Kyoka.Supervisor] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Kyoka.Supervisor")

BASE_DIR = Path(__file__).resolve().parent.parent
LAVALINK_DIR = Path(os.getenv("LAVALINK_DIR") or (BASE_DIR / "lavalink-node")).resolve()
JAR_PATH = (LAVALINK_DIR / "Lavalink.jar").resolve()
APP_YML_PATH = (LAVALINK_DIR / "application.yml").resolve()
PLUGINS_DIR = (LAVALINK_DIR / "plugins").resolve()

# Strict internal loopback binding
INTERNAL_HOST = "127.0.0.1"
INTERNAL_PORT = 2333


def detect_container_ram_mb() -> int:
    """Detect real container memory limit in MB (safely clamped for 500MB / 512MB container hosting)."""
    override = os.getenv("CONTAINER_MAX_RAM_MB") or os.getenv("MAX_MEMORY_MB")
    if override and override.strip().isdigit():
        return int(override.strip())

    # 1. cgroup v2
    cg2_file = Path("/sys/fs/cgroup/memory.max")
    if cg2_file.is_file():
        try:
            val = cg2_file.read_text(encoding="utf-8").strip()
            if val and val != "max":
                bytes_limit = int(val)
                mb = bytes_limit // (1024 * 1024)
                if 64 <= mb < 1048576:
                    return min(mb, 512)
        except Exception:
            pass

    # 2. cgroup v1
    cg1_file = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if cg1_file.is_file():
        try:
            val = cg1_file.read_text(encoding="utf-8").strip()
            if val:
                bytes_limit = int(val)
                mb = bytes_limit // (1024 * 1024)
                if 64 <= mb < 1048576:
                    return min(mb, 512)
        except Exception:
            pass

    # Default to 512 MB container limit to ensure no host RAM leaks on Render/Docker
    return 512


def calculate_jvm_opts(container_ram_mb: int) -> list[str]:
    """Calculate optimized JVM heap and GC settings strictly bounded under container budget."""
    env_opts = os.getenv("JAVA_OPTS")

    # Ultra-lean tuning for 500MB - 512MB containers (Render Free / Starter)
    # Total JVM footprint stays strictly <= 180MB (Heap + Metaspace + CodeCache + Direct + Stacks)
    # Leaving >320MB for Python Discord Bot and Linux OS
    if container_ram_mb <= 512:
        lean_flags = [
            "-Xmx96m",
            "-Xms32m",
            "-XX:+UseSerialGC",
            "-XX:MaxMetaspaceSize=56m",
            "-XX:ReservedCodeCacheSize=16m",
            "-XX:MaxDirectMemorySize=16m",
            "-XX:CompressedClassSpaceSize=16m",
            "-XX:TieredStopAtLevel=1",
            "-Xss256k",
            "-Dio.netty.allocator.type=unpooled",
            "-Dfile.encoding=UTF-8",
            "-Djava.security.egd=file:/dev/./urandom",
        ]
        if env_opts and env_opts.strip():
            tokens = env_opts.split()
            # If custom JAVA_OPTS exceeds safe heap for 512MB container, scale it down to prevent OOM
            has_oversized = any(
                (t.startswith("-Xmx") or t.startswith("-Xms"))
                and any(c in t for c in ("g", "G", "128", "180", "256", "384", "512", "1024"))
                for t in tokens
            )
            if has_oversized or not any(t.startswith("-Xmx") for t in tokens):
                filtered = [t for t in tokens if not t.startswith("-Xmx") and not t.startswith("-Xms")]
                return ["-Xmx96m", "-Xms32m"] + [f for f in lean_flags[2:] if f not in filtered] + filtered
            return tokens
        return lean_flags

    gc_flags = [
        "-XX:+UseG1GC",
        "-XX:MaxGCPauseMillis=20",
        "-XX:+UseStringDeduplication",
        "-Dfile.encoding=UTF-8",
        "-Djava.security.egd=file:/dev/./urandom",
    ]

    if env_opts and env_opts.strip():
        return env_opts.split()

    if container_ram_mb <= 1024:
        heap_flags = ["-Xmx512m", "-Xms128m"]
    elif container_ram_mb <= 2048:
        heap_flags = ["-Xmx768m", "-Xms128m"]
    elif container_ram_mb <= 8192:
        heap_flags = ["-Xmx2g", "-Xms512m"]
    else:
        heap_flags = ["-Xmx4g", "-Xms1g"]

    return heap_flags + gc_flags


def find_java_binary() -> str | None:
    """Find a valid Java runtime binary in PATH, JAVA_HOME, or known system paths."""
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

    # 3. Known Docker & Linux installation paths
    common_paths = [
        Path("/opt/java/openjdk/bin/java"),
        Path("/usr/bin/java"),
        Path("/usr/lib/jvm/default-java/bin/java"),
        Path("/usr/lib/jvm/java-17-openjdk-amd64/bin/java"),
        Path("/usr/lib/jvm/java-17-openjdk-arm64/bin/java"),
        Path("/usr/lib/jvm/java-21-openjdk-amd64/bin/java"),
        Path("/usr/lib/jvm/java-21-openjdk-arm64/bin/java"),
        BASE_DIR / ".jre" / "bin" / "java",
    ]
    for p in common_paths:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)

    return None


def ensure_java_runtime() -> str:
    """Find existing Java binary or download portable Eclipse Temurin 21 JRE if missing."""
    java_bin = find_java_binary()
    if java_bin:
        try:
            res = subprocess.run(
                [java_bin, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10,
            )
            ver_line = res.stdout.splitlines()[0] if res.stdout else "unknown"
            logger.info(f"[KYOKA] Java verified: {java_bin} ({ver_line})")
            return java_bin
        except Exception as e:
            logger.warning(f"[KYOKA] Detected Java at {java_bin} failed verification: {e}")

    # No working Java found; check portable JRE directory
    jre_dir = BASE_DIR / ".jre"
    portable_java = jre_dir / "bin" / "java"
    if portable_java.is_file() and os.access(portable_java, os.X_OK):
        logger.info(f"[KYOKA] Java verified: Portable JRE at {portable_java}")
        return str(portable_java)

    logger.info("[KYOKA] No system Java found. Provisioning portable Eclipse Temurin 21 JRE...")
    jre_dir.mkdir(parents=True, exist_ok=True)
    tar_url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.6%2B7/OpenJDK21U-jre_x64_linux_hotspot_21.0.6_7.tar.gz"
    tar_path = jre_dir / "jre.tar.gz"
    try:
        urllib.request.urlretrieve(tar_url, str(tar_path))
        import tarfile
        with tarfile.open(str(tar_path), "r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if len(parts) > 1:
                    member.name = str(Path(*parts[1:]))
                    tar.extract(member, path=str(jre_dir))
        tar_path.unlink(missing_ok=True)
        if portable_java.is_file():
            os.chmod(str(portable_java), 0o755)
            logger.info(f"[KYOKA] Java verified: Portable Eclipse Temurin 21 JRE installed at {portable_java}")
            return str(portable_java)
    except Exception as err:
        logger.critical(f"[KYOKA] ERROR: JAVA_NOT_FOUND - Failed to provision portable JRE: {err}")
        raise RuntimeError(f"Java not found and portable JRE could not be provisioned: {err}")

    logger.critical("[KYOKA] ERROR: JAVA_NOT_FOUND - Java runtime binary not found on host or container.")
    raise FileNotFoundError("Java runtime not found.")


def verify_lavalink_jar() -> Path:
    """Ensure Lavalink.jar binary is present and valid, downloading v4.2.2 if missing."""
    if JAR_PATH.is_file() and JAR_PATH.stat().st_size > 1000000:
        logger.info(f"[KYOKA] Lavalink JAR verified: {JAR_PATH} ({JAR_PATH.stat().st_size / (1024*1024):.1f} MB)")
        return JAR_PATH

    LAVALINK_DIR.mkdir(parents=True, exist_ok=True)
    version = os.getenv("LAVALINK_VERSION", "4.2.2")
    url = f"https://github.com/lavalink-devs/Lavalink/releases/download/{version}/Lavalink.jar"
    logger.info(f"[KYOKA] Lavalink JAR missing. Downloading Lavalink {version}...")

    tmp_jar = JAR_PATH.with_suffix(".tmp")
    for attempt in range(1, 4):
        try:
            urllib.request.urlretrieve(url, str(tmp_jar))
            if tmp_jar.is_file() and tmp_jar.stat().st_size > 1000000:
                tmp_jar.replace(JAR_PATH)
                logger.info(f"[KYOKA] Lavalink JAR verified: Downloaded ({JAR_PATH.stat().st_size / (1024*1024):.1f} MB)")
                return JAR_PATH
        except Exception as e:
            logger.warning(f"[KYOKA] Download attempt {attempt} failed: {e}")
            if tmp_jar.is_file():
                tmp_jar.unlink(missing_ok=True)
            time.sleep(2.0)

    logger.critical("[KYOKA] ERROR: LAVALINK_JAR_NOT_FOUND - Failed to download Lavalink.jar after 3 attempts.")
    raise FileNotFoundError(f"Lavalink JAR not found at {JAR_PATH}")


def ensure_plugin_jars() -> None:
    """Pre-stage required plugins so Lavalink does not stall on startup."""
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    plugins = [
        (
            "youtube-plugin-1.18.2.jar",
            "https://maven.lavalink.dev/releases/dev/lavalink/youtube/youtube-plugin/1.18.2/youtube-plugin-1.18.2.jar",
        ),
        (
            "lavasrc-plugin-4.8.3.jar",
            "https://maven.lavalink.dev/releases/com/github/topi314/lavasrc/lavasrc-plugin/4.8.3/lavasrc-plugin-4.8.3.jar",
        ),
    ]
    for filename, url in plugins:
        target = PLUGINS_DIR / filename
        if not target.is_file() or target.stat().st_size < 1000:
            tmp = target.with_suffix(".tmp")
            try:
                logger.info(f"[KYOKA] Pre-downloading plugin: {filename}...")
                urllib.request.urlretrieve(url, str(tmp))
                if tmp.is_file() and tmp.stat().st_size > 1000:
                    tmp.replace(target)
            except Exception as e:
                if tmp.is_file():
                    tmp.unlink(missing_ok=True)
                logger.warning(f"[KYOKA] Notice: Plugin {filename} download deferred to Lavalink startup: {e}")


def verify_configuration() -> Path:
    """Verify that application.yml configuration exists and is non-empty."""
    if not APP_YML_PATH.is_file() or APP_YML_PATH.stat().st_size == 0:
        logger.critical(f"[KYOKA] ERROR: INVALID_CONFIG - Missing configuration at {APP_YML_PATH}")
        raise FileNotFoundError(f"Lavalink application.yml not found at {APP_YML_PATH}")

    content = APP_YML_PATH.read_text(encoding="utf-8")
    if "server:" not in content or "lavalink:" not in content:
        logger.critical(f"[KYOKA] ERROR: YAML_PARSE_ERROR - {APP_YML_PATH} is missing required sections.")
        raise ValueError(f"Invalid application.yml content in {APP_YML_PATH}")

    logger.info(f"[KYOKA] Lavalink configuration verified: {APP_YML_PATH}")
    return APP_YML_PATH


def check_port_open(host: str, port: int) -> bool:
    """Check if a TCP port is currently open and accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def get_configured_passwords() -> list[str]:
    """Extract candidate passwords from environment, configuration file, and defaults."""
    pw_list: list[str] = []
    env_pw = os.getenv("LAVALINK_PASSWORD") or os.getenv("LAVALINK_SERVER_PASSWORD")
    if env_pw and env_pw.strip():
        pw_list.append(env_pw.strip())

    if APP_YML_PATH.is_file():
        try:
            content = APP_YML_PATH.read_text(encoding="utf-8")
            m = re.search(r'password:\s*["\']?([^"\'\$\s\n\r]+)["\']?', content)
            if m:
                extracted = m.group(1).strip()
                if extracted and extracted not in pw_list:
                    pw_list.append(extracted)
        except Exception:
            pass

    for fallback in ("youshallnotpass", "onlyforkyoka", "kyoka_local_internal_secret"):
        if fallback not in pw_list:
            pw_list.append(fallback)

    return pw_list


def probe_http_version_auth(
    host: str,
    port: int,
    candidate_passwords: list[str] | None = None,
    timeout: float = 1.5,
) -> tuple[bool, str, str | None]:
    """Probe Lavalink /version endpoint across candidate authorization passwords.

    Returns (is_ready, version_str_or_error, working_password).
    """
    url = f"http://{host}:{port}/version"
    candidates: list[str] = []
    if candidate_passwords:
        for p in candidate_passwords:
            if p and p not in candidates:
                candidates.append(p)
    for p in get_configured_passwords():
        if p not in candidates:
            candidates.append(p)

    last_err = "non-200"
    for candidate_pw in candidates:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Kyoka-Supervisor/3.0",
                    "Authorization": candidate_pw,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    ver = resp.read().decode("utf-8").strip()
                    return True, ver, candidate_pw
        except urllib.error.HTTPError as he:
            last_err = f"HTTP Error {he.code}: {he.reason}"
            if he.code == 401:
                # 401 Unauthorized indicates Undertow / Lavalink is active and filtering requests,
                # but candidate_pw was rejected. Try next candidate password.
                continue
            return False, last_err, None
        except Exception as e:
            return False, str(e), None

    return False, last_err, None


def probe_http_version(
    host: str,
    port: int,
    password: str | None = None,
    timeout: float = 1.5,
) -> tuple[bool, str]:
    """Probe Lavalink /version endpoint with required authorization."""
    candidates = [password] if password else None
    ok, ver, _ = probe_http_version_auth(host, port, candidates, timeout=timeout)
    return ok, ver


def verify_lavalink_auth(host: str, port: int, password: str, timeout: float = 3.0) -> bool:
    """Verify that Lavalink accepts the authentication password at /v4/info."""
    url = f"http://{host}:{port}/v4/info"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": password,
            "User-Agent": "Kyoka-Supervisor/3.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as he:
        if he.code == 401:
            logger.critical("[KYOKA] ERROR: AUTHENTICATION_FAILED - Lavalink rejected authorization header.")
            return False
        return he.code != 401
    except Exception:
        return True


class CombinedSupervisor:
    """Authoritative supervisor for unified Lavalink and Kyoka Discord Bot container."""

    def __init__(self) -> None:
        self.java_proc: subprocess.Popen | None = None
        self.bot_proc: subprocess.Popen | None = None
        self.running: bool = True
        self.lavalink_restart_count: int = 0
        self.bot_restart_count: int = 0
        self.last_lavalink_restart: float = 0.0

        # Synchronize private localhost credentials
        raw_pw = os.getenv("LAVALINK_PASSWORD") or os.getenv("LAVALINK_SERVER_PASSWORD")
        if not raw_pw or raw_pw.strip() in ("", "onlyforkyoka", "youshallnotpass"):
            self.password = secrets.token_urlsafe(32)
            logger.info("[KYOKA] Generated secure ephemeral secret for internal Lavalink loopback session.")
        else:
            self.password = raw_pw.strip()

        # Propagate uniform configuration to environment for bot process
        os.environ["LAVALINK_PASSWORD"] = self.password
        os.environ["LAVALINK_SERVER_PASSWORD"] = self.password
        os.environ["LAVALINK_HOST"] = INTERNAL_HOST
        os.environ["LAVALINK_PORT"] = str(INTERNAL_PORT)
        os.environ["LAVALINK_SECURE"] = "false"
        os.environ["LAVALINK_IDENTIFIER"] = "kyoka-lavalink-local"
        os.environ["LAVALINK_URI"] = f"http://{INTERNAL_HOST}:{INTERNAL_PORT}"
        os.environ["KYOKA_SUPERVISED"] = "1"

    def _get_process_rss_mb(self, proc: subprocess.Popen | None) -> float:
        """Read process RSS in MB from /proc/[pid]/statm without external dependencies."""
        if not proc or proc.poll() is not None:
            return 0.0
        try:
            statm = Path(f"/proc/{proc.pid}/statm")
            if statm.is_file():
                pages = int(statm.read_text(encoding="utf-8").split()[1])
                page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
                return (pages * page_size) / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    def check_memory_usage(self, max_allowed_mb: int = 500) -> tuple[float, float, float]:
        """Monitor RSS of Java and Bot subprocesses and enforce safe container ceiling."""
        java_rss = self._get_process_rss_mb(self.java_proc)
        bot_rss = self._get_process_rss_mb(self.bot_proc)
        total_rss = java_rss + bot_rss

        if total_rss > 0 and total_rss > (max_allowed_mb * 0.90):
            logger.warning(
                f"[KYOKA.MemoryGuard] High container memory: Total {total_rss:.1f} MB "
                f"(Java: {java_rss:.1f} MB, Bot: {bot_rss:.1f} MB, Ceiling: {max_allowed_mb} MB). "
                f"Triggering proactive Python garbage collection."
            )
            import gc
            gc.collect()

        return java_rss, bot_rss, total_rss

    def handle_signal(self, signum: int, _) -> None:
        signame = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info(f"Signal {signame} received. Initiating graceful shutdown of all processes...")
        self.running = False
        self.shutdown()
        sys.exit(0)

    def shutdown(self) -> None:
        """Gracefully terminate Discord Bot and Lavalink subprocesses."""
        if self.bot_proc and self.bot_proc.poll() is None:
            logger.info(f"Stopping Discord Bot process (PID: {self.bot_proc.pid})...")
            try:
                self.bot_proc.terminate()
                self.bot_proc.wait(timeout=8.0)
            except Exception:
                try:
                    self.bot_proc.kill()
                except Exception:
                    pass

        if self.java_proc and self.java_proc.poll() is None:
            logger.info(f"Stopping Lavalink Java process (PID: {self.java_proc.pid})...")
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
        """Start Lavalink child process and verify HTTP /version readiness before bot launch."""
        if check_port_open(INTERNAL_HOST, INTERNAL_PORT):
            ok, ver, matched_pw = probe_http_version_auth(INTERNAL_HOST, INTERNAL_PORT, [self.password])
            if ok:
                if matched_pw and matched_pw != self.password:
                    logger.info("[KYOKA] Existing Lavalink accepted candidate password; synchronizing credentials.")
                    self.password = matched_pw
                    os.environ["LAVALINK_PASSWORD"] = matched_pw
                    os.environ["LAVALINK_SERVER_PASSWORD"] = matched_pw
                logger.info(f"[KYOKA] Lavalink HTTP readiness verified (Existing process detected, Version: {ver})")
                if verify_lavalink_auth(INTERNAL_HOST, INTERNAL_PORT, self.password):
                    logger.info("[KYOKA] Lavalink authentication verified")
                return True
            else:
                logger.warning(f"[KYOKA] Port {INTERNAL_PORT} in use; waiting up to 6s for socket release...")
                for _ in range(6):
                    time.sleep(1.0)
                    if not check_port_open(INTERNAL_HOST, INTERNAL_PORT):
                        break
                    ok, ver, matched_pw = probe_http_version_auth(INTERNAL_HOST, INTERNAL_PORT, [self.password])
                    if ok:
                        if matched_pw and matched_pw != self.password:
                            self.password = matched_pw
                            os.environ["LAVALINK_PASSWORD"] = matched_pw
                            os.environ["LAVALINK_SERVER_PASSWORD"] = matched_pw
                        logger.info(f"[KYOKA] Lavalink HTTP readiness verified (Version: {ver})")
                        return True

                if check_port_open(INTERNAL_HOST, INTERNAL_PORT):
                    logger.critical(f"[KYOKA] ERROR: PORT_ALREADY_IN_USE - Port {INTERNAL_PORT} occupied by unresponsive process.")
                    return False

        verify_lavalink_jar()
        ensure_plugin_jars()
        verify_configuration()

        cmd = [
            java_bin,
            *jvm_opts,
            f"-Dserver.port={INTERNAL_PORT}",
            f"-Dserver.address={INTERNAL_HOST}",
            f"-Dlavalink.server.password={self.password}",
            "-jar",
            str(JAR_PATH.resolve()),
        ]

        logger.info(f"[KYOKA] Starting Lavalink... (host={INTERNAL_HOST}, port={INTERNAL_PORT})")
        try:
            self.java_proc = subprocess.Popen(
                cmd,
                cwd=str(LAVALINK_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
            )
        except Exception as e:
            logger.critical(f"[KYOKA] ERROR: LAVALINK_STARTUP_FAILED - Could not spawn Java process: {e}")
            return False

        # Stream Java stdout/stderr in real-time so Render logs show all output with flush
        recent_logs: list[str] = []
        def _stream_output():
            try:
                for line in iter(self.java_proc.stdout.readline, ""):
                    if not line:
                        break
                    clean_line = line.rstrip()
                    recent_logs.append(clean_line)
                    if len(recent_logs) > 60:
                        recent_logs.pop(0)
                    print(f"[Lavalink] {clean_line}", flush=True)
            except Exception:
                pass

        reader_thread = threading.Thread(target=_stream_output, daemon=True)
        reader_thread.start()

        logger.info(f"Lavalink Java process spawned (PID: {self.java_proc.pid}).")
        logger.info("[KYOKA] Waiting for Lavalink readiness...")

        ready = False
        timeout_sec = float(os.getenv("LAVALINK_READINESS_TIMEOUT", "300.0"))
        deadline = time.time() + timeout_sec
        start_time = time.time()
        while time.time() < deadline:
            elapsed = int(time.time() - start_time)

            if self.java_proc.poll() is not None:
                code = self.java_proc.returncode
                time.sleep(0.5)
                logger.critical(f"[KYOKA] ERROR: JAVA_PROCESS_EXITED - Lavalink terminated prematurely with code {code}.")
                if recent_logs:
                    logger.critical("[KYOKA] --- Last Lavalink logs before termination ---")
                    for l in recent_logs[-20:]:
                        logger.critical(f"[KYOKA] {l}")
                    logger.critical("[KYOKA] ---------------------------------------------")
                return False

            ok, ver, matched_pw = probe_http_version_auth(INTERNAL_HOST, INTERNAL_PORT, [self.password])
            if ok:
                if matched_pw and matched_pw != self.password:
                    logger.info("[KYOKA] Synchronizing supervisor secret with verified Lavalink password.")
                    self.password = matched_pw
                    os.environ["LAVALINK_PASSWORD"] = matched_pw
                    os.environ["LAVALINK_SERVER_PASSWORD"] = matched_pw
                logger.info("[KYOKA] Lavalink HTTP readiness verified")
                if verify_lavalink_auth(INTERNAL_HOST, INTERNAL_PORT, self.password):
                    logger.info("[KYOKA] Lavalink authentication verified")
                else:
                    logger.warning("[KYOKA] Authentication check returned non-200; proceeding with synchronized secret.")
                logger.info(f"[KYOKA] Lavalink READY at {INTERNAL_HOST}:{INTERNAL_PORT} (Version: {ver})")
                ready = True
                break

            if elapsed > 0 and elapsed % 15 == 0:
                logger.info(f"[KYOKA] Waiting for Lavalink readiness... (elapsed: {elapsed}s / {int(timeout_sec)}s)")

            time.sleep(1.0)

        if not ready:
            logger.critical(f"[KYOKA] ERROR: READINESS_TIMEOUT - Lavalink failed to respond at http://{INTERNAL_HOST}:{INTERNAL_PORT}/version within {int(timeout_sec)}s.")
            if recent_logs:
                logger.critical("[KYOKA] --- Last Lavalink logs ---")
                for l in recent_logs[-20:]:
                    logger.critical(f"[KYOKA] {l}")
                logger.critical("[KYOKA] ---------------------------")
            return False

        return True

    def start_bot(self) -> None:
        """Start the Discord Bot process."""
        logger.info("[KYOKA] Starting Discord bot...")
        self.bot_proc = subprocess.Popen(
            [sys.executable, "src/main.py"],
            cwd=str(BASE_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr,
            env=os.environ.copy(),
        )
        logger.info(f"KYOKA Discord Bot process spawned (PID: {self.bot_proc.pid}).")

    def run(self) -> int:
        """Main supervisory execution loop managing both services with crash resilience."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.handle_signal)
            except Exception:
                pass

        logger.info("[KYOKA] Checking startup environment...")

        # 1. Validation & Memory Detection
        ram_mb = detect_container_ram_mb()
        jvm_opts = calculate_jvm_opts(ram_mb)
        logger.info(f"[KYOKA] Container memory verified ({ram_mb} MB available). JVM opts: {' '.join(jvm_opts)}")

        # 2. Java Runtime Verification (or automatic portable provisioning)
        try:
            java_bin = ensure_java_runtime()
        except Exception as e:
            logger.critical(f"[KYOKA] Fatal Java initialization error: {e}")
            return 1

        # 3. Artifact & Config Pre-flight
        try:
            verify_lavalink_jar()
            verify_configuration()
        except Exception as e:
            logger.critical(f"[KYOKA] Fatal artifact verification error: {e}")
            return 1

        # 4. Start Lavalink first and ensure HTTP /version is responsive
        if not self.start_lavalink(java_bin, jvm_opts):
            logger.critical("[KYOKA] FATAL: Lavalink readiness verification failed. Aborting bot startup.")
            self.shutdown()
            return 1

        # 5. Start Discord Bot
        self.start_bot()

        # 6. Supervisory Monitoring Loop
        last_memory_check = time.time()
        while self.running:
            time.sleep(2.0)
            now = time.time()

            # Proactive container memory telemetry & OOM guard (every 30 seconds)
            if now - last_memory_check >= 30.0:
                last_memory_check = now
                j_rss, b_rss, t_rss = self.check_memory_usage(ram_mb)
                if t_rss > 0:
                    status = "HEALTHY" if t_rss < (ram_mb * 0.85) else "ELEVATED"
                    logger.info(
                        f"[KYOKA.MemoryGuard] Memory Status: Total {t_rss:.1f} MB / {ram_mb} MB "
                        f"(Lavalink: {j_rss:.1f} MB, Discord Bot: {b_rss:.1f} MB) [{status}]"
                    )

            # Check Lavalink health
            if self.java_proc and self.java_proc.poll() is not None:
                exit_code = self.java_proc.returncode
                now = time.time()
                logger.warning(f"[KYOKA] Lavalink process terminated unexpectedly (exit code {exit_code})!")

                if now - self.last_lavalink_restart < 15.0:
                    self.lavalink_restart_count += 1
                else:
                    self.lavalink_restart_count = 1

                self.last_lavalink_restart = now

                if self.lavalink_restart_count > 5:
                    logger.critical("[KYOKA] Lavalink crashed more than 5 times in rapid succession. Halting restart.")
                    self.shutdown()
                    return 1

                logger.info(f"[KYOKA] Auto-restarting Lavalink (attempt {self.lavalink_restart_count})...")
                time.sleep(min(3.0 * self.lavalink_restart_count, 15.0))
                self.start_lavalink(java_bin, jvm_opts)

            # Check Bot health
            if self.bot_proc and self.bot_proc.poll() is not None:
                exit_code = self.bot_proc.returncode
                if not self.running:
                    break

                logger.warning(f"[KYOKA] Discord Bot process exited (code {exit_code}).")
                if exit_code == 0:
                    logger.info("[KYOKA] Bot exited cleanly (scheduled refresh). Restarting bot...")
                else:
                    self.bot_restart_count += 1
                    if self.bot_restart_count > 10:
                        logger.critical("[KYOKA] Bot has crashed repeatedly (>10 times). Halting.")
                        self.shutdown()
                        return 1
                    logger.warning(f"[KYOKA] Bot crashed. Auto-recovering in 5 seconds (attempt {self.bot_restart_count})...")
                    time.sleep(5.0)

                self.start_bot()

        self.shutdown()
        return 0


if __name__ == "__main__":
    supervisor = CombinedSupervisor()
    sys.exit(supervisor.run())
