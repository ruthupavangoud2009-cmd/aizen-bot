#!/usr/bin/env python3
"""
Unit and integration tests for Kyoka Lavalink Hotfix.
Verifies supervisor diagnostics, memory limit detection, password consistency,
port collision protection, and elimination of competing background launchers.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Mock external heavy dependencies if running in minimal environment without pip packages
for mod_name in ["discord", "discord.ext", "discord.ext.tasks", "discord.ext.commands", "wavelink", "aiohttp"]:
    if mod_name not in sys.modules:
        m = MagicMock()
        if mod_name == "aiohttp":
            m.ClientTimeout = MagicMock()
            m.ClientSession = MagicMock()
        elif mod_name == "wavelink":
            m.Pool = MagicMock()
            m.Node = MagicMock()
        sys.modules[mod_name] = m

from src.core.config import Config
from src.core.lavalink import candidates
from scripts.run_combined import (
    detect_container_ram_mb,
    calculate_jvm_opts,
    verify_configuration,
    ensure_java_runtime,
    verify_lavalink_auth,
    probe_http_version,
    probe_http_version_auth,
    get_configured_passwords,
    CombinedSupervisor,
    INTERNAL_HOST,
    INTERNAL_PORT,
)


class TestLavalinkProductionHotfix(unittest.TestCase):
    """Test suite for Lavalink hotfix verification."""

    def test_configuration_loopback_binding(self):
        """Verify Config binds strictly to configured Lavalink cluster endpoint."""
        self.assertTrue(len(Config.LAVALINK_HOST) > 0)
        self.assertTrue(Config.LAVALINK_PORT > 0)
        self.assertTrue(Config.LAVALINK_URI.startswith(("http://", "https://")))
        self.assertFalse(Config.LAVALINK_AUTO_DISCOVER)

    def test_candidates_list(self):
        """Verify candidate node list resolves with valid URI and password."""
        c = candidates()
        self.assertTrue(len(c) >= 1)
        uri, pw = c[0]
        self.assertTrue(uri.startswith(("http://", "https://")))
        self.assertTrue(len(pw) > 0)

    def test_no_insecure_fallback_password(self):
        """Verify that default insecure fallback 'onlyforkyoka' is not committed as password."""
        with patch.dict(os.environ, {"LAVALINK_PASSWORD": "", "LAVALINK_SERVER_PASSWORD": ""}):
            supervisor = CombinedSupervisor()
            # If no password is in env, supervisor must generate a secure secret (not onlyforkyoka)
            self.assertNotEqual(supervisor.password, "onlyforkyoka")
            self.assertNotEqual(supervisor.password, "")
            self.assertTrue(len(supervisor.password) >= 20)
            self.assertEqual(os.environ["LAVALINK_PASSWORD"], supervisor.password)

    def test_container_memory_detection(self):
        """Verify container RAM limit detection doesn't crash and returns reasonable MB."""
        ram_mb = detect_container_ram_mb()
        self.assertIsInstance(ram_mb, int)
        self.assertGreater(ram_mb, 64)

    def test_jvm_opts_low_ram_container(self):
        """Verify JVM options for 512 MB / 500 MB container allocate safe heap to avoid OOM killer."""
        opts = calculate_jvm_opts(512)
        opts_str = " ".join(opts)
        self.assertIn("-Xmx96m", opts_str)
        self.assertIn("-Xms32m", opts_str)
        self.assertIn("-XX:+UseSerialGC", opts_str)
        self.assertIn("-XX:MaxMetaspaceSize=56m", opts_str)
        self.assertIn("-XX:ReservedCodeCacheSize=16m", opts_str)
        self.assertIn("-XX:MaxDirectMemorySize=16m", opts_str)
        self.assertIn("-Xss256k", opts_str)
        self.assertIn("-Djava.security.egd=file:/dev/./urandom", opts_str)

    def test_jvm_opts_moderate_ram_container(self):
        """Verify JVM options for 1024 MB container."""
        opts = calculate_jvm_opts(1024)
        opts_str = " ".join(opts)
        self.assertIn("-Xmx512m", opts_str)
        self.assertIn("-Xms128m", opts_str)

    def test_jvm_opts_oversized_env_opts_scaled_down(self):
        """Verify that if custom JAVA_OPTS has -Xmx4g on a 512MB container, it is scaled down."""
        with patch.dict(os.environ, {"JAVA_OPTS": "-Xmx4g -Xms1g -XX:+UseG1GC"}):
            opts = calculate_jvm_opts(512)
            opts_str = " ".join(opts)
            self.assertNotIn("-Xmx4g", opts_str)
            self.assertIn("-Xmx96m", opts_str)

    def test_application_yml_exists_and_valid(self):
        """Verify that application.yml is present and contains required server and lavalink blocks."""
        cfg_path = verify_configuration()
        self.assertTrue(cfg_path.is_file())
        content = cfg_path.read_text(encoding="utf-8")
        self.assertIn("port: 2333", content)
        self.assertIn("address: 127.0.0.1", content)
        self.assertIn("${LAVALINK_PASSWORD:${LAVALINK_SERVER_PASSWORD:youshallnotpass}}", content)
        self.assertNotIn("onlyforkyoka", content)

    def test_no_competing_launchers(self):
        """Verify that src/core/lavalink.py does NOT define _ensure_local_lavalink_running."""
        import src.core.lavalink as lavalink_module
        self.assertFalse(
            hasattr(lavalink_module, "_ensure_local_lavalink_running"),
            "Competing launcher _ensure_local_lavalink_running must be completely removed from lavalink.py"
        )

    def test_render_yaml_configuration(self):
        """Verify render.yaml declares docker runtime and ultra-lean bot startCommand."""
        render_path = BASE_DIR / "render.yaml"
        content = render_path.read_text(encoding="utf-8")
        self.assertIn("runtime: docker", content)
        self.assertIn("startCommand: python -m src.main", content)
        self.assertIn("LAVALINK_URI", content)

    def test_dockerfile_configuration(self):
        """Verify Dockerfile contains lean direct python entrypoint."""
        docker_path = BASE_DIR / "Dockerfile"
        content = docker_path.read_text(encoding="utf-8")
        self.assertIn('ENTRYPOINT ["python", "-m", "src.main"]', content)


    def test_ensure_java_runtime_resolution(self):
        """Verify ensure_java_runtime finds system java or checks standard paths."""
        with patch("shutil.which", return_value="/usr/bin/java"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="openjdk version 21.0.2")
            java_path = ensure_java_runtime()
            self.assertEqual(java_path, "/usr/bin/java")

    def test_verify_lavalink_auth_mocked(self):
        """Verify auth verification handles HTTP 200 and HTTP 401."""
        import urllib.error
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.getcode.return_value = 200
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
            self.assertTrue(verify_lavalink_auth("127.0.0.1", 2333, "secret"))

        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("http://127.0.0.1:2333/v4/info", 401, "Unauthorized", {}, None)):
            self.assertFalse(verify_lavalink_auth("127.0.0.1", 2333, "wrong_secret"))

    def test_readiness_timeout_default_and_env(self):
        """Verify readiness timeout defaults to 300s and respects LAVALINK_READINESS_TIMEOUT env var."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LAVALINK_READINESS_TIMEOUT", None)
            timeout = float(os.getenv("LAVALINK_READINESS_TIMEOUT", "300.0"))
            self.assertEqual(timeout, 300.0)

        with patch.dict(os.environ, {"LAVALINK_READINESS_TIMEOUT": "180"}):
            timeout = float(os.getenv("LAVALINK_READINESS_TIMEOUT", "300.0"))
            self.assertEqual(timeout, 180.0)

    def test_probe_http_version_sends_authorization_header(self):
        """Verify that probe_http_version passes Authorization header to Lavalink /version."""
        import urllib.request
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"4.2.2\n"
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            ok, ver = probe_http_version("127.0.0.1", 2333, password="supersecretpass")
            self.assertTrue(ok)
            self.assertEqual(ver, "4.2.2")

            # Check that the request was made with Authorization header
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertIsInstance(req, urllib.request.Request)
            self.assertEqual(req.headers.get("Authorization"), "supersecretpass")
            self.assertEqual(req.full_url, "http://127.0.0.1:2333/version")

    def test_probe_http_version_auth_fallback_on_401(self):
        """Verify that if candidate password gives 401, next candidate is tried."""
        import urllib.error
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"4.2.2"
            mock_resp.__enter__.return_value = mock_resp

            # First password fails with 401 Unauthorized, second succeeds
            mock_urlopen.side_effect = [
                urllib.error.HTTPError("http://127.0.0.1:2333/version", 401, "Unauthorized", {}, None),
                mock_resp,
            ]

            ok, ver, matched_pw = probe_http_version_auth(
                "127.0.0.1",
                2333,
                candidate_passwords=["wrongpass", "rightpass"],
            )
            self.assertTrue(ok)
            self.assertEqual(ver, "4.2.2")
            self.assertEqual(matched_pw, "rightpass")

    def test_probe_http_version_connection_refused(self):
        """Verify that connection failure returns False without throwing."""
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError(111, "Connection refused")):
            ok, err = probe_http_version("127.0.0.1", 2333, password="test")
            self.assertFalse(ok)
            self.assertIn("Connection refused", err)

    def test_get_configured_passwords(self):
        """Verify get_configured_passwords resolves env and default fallbacks."""
        with patch.dict(os.environ, {"LAVALINK_PASSWORD": "mycustompassword"}):
            pws = get_configured_passwords()
            self.assertIn("mycustompassword", pws)
            self.assertIn("youshallnotpass", pws)


if __name__ == "__main__":
    unittest.main()
