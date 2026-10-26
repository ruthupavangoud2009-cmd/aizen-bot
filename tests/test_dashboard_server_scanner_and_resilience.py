"""Regression test suite for KYOKA 3.0 server scanner, music studio resilience, and settings verification."""
from __future__ import annotations

import time
import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from dashboard_api.auth import (
    create_session_token,
    clear_guild_caches,
    fetch_user_guilds,
    fetch_bot_guilds,
    _USER_GUILDS_CACHE,
    _BOT_GUILDS_CACHE,
)
from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.routes.music_routes import parse_timestamp_seconds


class TestServerScannerAndResilience(AioHTTPTestCase):
    """Test suite covering server scanner classification, rate limit resilience, and music studio robustness."""

    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="1562505487214321714",
            client_secret="test_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            secret_key="test_super_secret_signing_key_32_bytes_long",
        )
        self.db = MockDatabaseAdapter()
        # Preconfigure bot presence in guild 1001 and 1002
        self.db.known_bot_guilds = {1001, 1002}
        return create_app(config=self.config, db=self.db, serve_website=False)

    def setUp(self):
        super().setUp()
        clear_guild_caches()

    def tearDown(self):
        super().tearDown()
        clear_guild_caches()

    def _create_user_session(self, user_id: int, guilds: list[dict], access_token: str = "mock_test_token") -> str:
        payload = {
            "user_id": user_id,
            "username": "TestUser",
            "avatar": None,
            "is_owner": user_id == 1505515188991033409,
            "access_token": access_token,
            "mock_guilds": guilds,
        }
        return create_session_token(payload, self.config.secret_key)

    @unittest_run_loop
    async def test_server_scanner_bot_installed_multiple_servers(self):
        """Verify bot is correctly detected as installed when guild ID matches bot memberships."""
        mock_guilds = [
            {"id": "1001", "name": "Active Server 1", "permissions": 8, "owner": True},
            {"id": "1002", "name": "Active Server 2", "permissions": 0x20, "owner": False},
            {"id": "2001", "name": "Bot Absent Server", "permissions": 8, "owner": True},
        ]
        session_token = self._create_user_session(100, mock_guilds)

        resp = await self.client.get(
            "/api/guilds",
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert "guilds" in data
        guilds = data["guilds"]
        assert len(guilds) == 3

        # Guild 1001: Bot Added (installed)
        g1 = next(g for g in guilds if g["id"] == "1001")
        assert g1["bot_installed"] is True
        assert g1["status"] == "installed"

        # Guild 1002: Bot Added (installed)
        g2 = next(g for g in guilds if g["id"] == "1002")
        assert g2["bot_installed"] is True
        assert g2["status"] == "installed"

        # Guild 2001: Add KYOKA (not_installed)
        g3 = next(g for g in guilds if g["id"] == "2001")
        assert g3["bot_installed"] is False
        assert g3["status"] == "not_installed"
        assert "client_id=1562505487214321714" in g3["invite_url"]

    @unittest_run_loop
    async def test_server_scanner_permission_required(self):
        """User without manage rights gets permission_required state."""
        mock_guilds = [
            {"id": "3001", "name": "No Permissions Server", "permissions": 0, "owner": False},
        ]
        session_token = self._create_user_session(200, mock_guilds)

        resp = await self.client.get(
            "/api/guilds",
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert resp.status == 200
        data = await resp.json()
        g = data["guilds"][0]
        assert g["can_manage"] is False
        assert g["status"] == "permission_required"
        assert g["bot_installed"] is False

    @unittest_run_loop
    async def test_server_scanner_unauthorized_expired_session(self):
        """Expired or tampered token must be rejected with 401."""
        resp = await self.client.get(
            "/api/guilds",
            headers={"Authorization": "Bearer invalid.expired.token"}
        )
        assert resp.status == 401

    @unittest_run_loop
    async def test_user_guilds_ttl_cache_avoids_repeated_discord_calls(self):
        """In-memory TTL cache prevents Discord 429 rate-limiting on rapid repeated calls."""
        token = "test_discord_user_oauth_token"
        mock_data = [{"id": "999", "name": "Cached Guild", "permissions": 8}]

        # Inject into cache directly
        import hashlib
        cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        _USER_GUILDS_CACHE[cache_key] = (time.time(), mock_data)

        # Calling fetch_user_guilds returns immediately from cache without HTTP request
        http_session = self.app["http_session"]
        result = await fetch_user_guilds(token, http_session)
        assert result == mock_data
        assert result[0]["name"] == "Cached Guild"

    @unittest_run_loop
    async def test_music_studio_playback_and_never_502(self):
        """Music Studio playback route returns 200 with structured playback data and never 502."""
        mock_guilds = [{"id": "1001", "name": "Audio Server", "permissions": 8}]
        session_token = self._create_user_session(100, mock_guilds)

        resp = await self.client.get(
            "/api/guilds/1001/music/playback",
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["guild_id"] == "1001"
        assert "status" in data
        assert "is_connected" in data
        assert "volume" in data

    @unittest_run_loop
    async def test_music_timestamp_parser(self):
        """Timestamp parser correctly handles MM:SS, HH:MM:SS, and integer seconds."""
        assert parse_timestamp_seconds("95") == 95
        assert parse_timestamp_seconds("1:35") == 95
        assert parse_timestamp_seconds("01:35") == 95
        assert parse_timestamp_seconds("0:45") == 45
        assert parse_timestamp_seconds("1:00:00") == 3600
        assert parse_timestamp_seconds("01:15:30") == 4530
        assert parse_timestamp_seconds("invalid") is None

    @unittest_run_loop
    async def test_music_studio_seek_and_volume(self):
        """Seek and volume controls update playback state reliably."""
        mock_guilds = [{"id": "1001", "name": "Audio Server", "permissions": 8}]
        session_token = self._create_user_session(100, mock_guilds)

        # Test seek with 1:35
        resp = await self.client.post(
            "/api/guilds/1001/music/control",
            json={"action": "seek", "value": "1:35"},
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["action"] == "seek"
        assert data["formatted"] == "1:35"

        # Test volume set to 85%
        v_resp = await self.client.post(
            "/api/guilds/1001/music/control",
            json={"action": "volume", "value": 85},
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert v_resp.status == 200
        v_data = await v_resp.json()
        assert v_data["success"] is True
        assert v_data["playback"]["volume"] == 85

    @unittest_run_loop
    async def test_guild_settings_all_modules_present(self):
        """Ensure all 19 advertised module keys exist in default guild settings."""
        mock_guilds = [{"id": "1001", "name": "Settings Server", "permissions": 8}]
        session_token = self._create_user_session(100, mock_guilds)

        resp = await self.client.get(
            "/api/guilds/1001/settings",
            headers={"Authorization": f"Bearer {session_token}"}
        )
        assert resp.status == 200
        settings = await resp.json()

        expected_modules = [
            "general", "welcome_leave", "verification", "moderation",
            "antinuke", "logs", "tickets", "leveling", "giveaways",
            "reaction_roles", "music", "ai", "prefix_commands",
            "utilities", "premium", "embeds", "roles_channels",
            "roles_utilities", "diagnostics"
        ]
        for mod in expected_modules:
            assert mod in settings, f"Missing expected settings module '{mod}'"
