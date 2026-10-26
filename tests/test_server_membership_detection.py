"""Authoritative tests for KYOKA 3.0 Server Membership Detection and False Add Bot prevention.

Validates:
1. KYOKA installed and user can manage the server -> visible with installed status & bot_installed: True.
2. KYOKA absent -> excluded when installed_only=1, never shown as active.
3. KYOKA installed but membership check fails -> returns 'unavailable' status & verification_status: unavailable.
4. Refresh after installation (?refresh=1) -> purges caches and returns updated guild status immediately.
5. Guild ID normalization -> int vs str vs large 64-bit snowflake IDs compare accurately.
6. Authoritative bot instance checking -> prioritizes live running KyokaBot instance.
"""
import time
from typing import Any
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token, fetch_bot_guilds, clear_guild_caches


class MockGuild:
    def __init__(self, guild_id: int | str, name: str = "Mock Guild"):
        self.id = int(guild_id)
        self.name = name


class MockBotInstance:
    def __init__(self, guild_ids: list[int | str]):
        self.guilds = [MockGuild(gid) for gid in guild_ids]

    def is_ready(self) -> bool:
        return True


class TestServerMembershipDetection(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="1562505487214321714",
            client_secret="test_secret",
            bot_token="test_token",
            redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=1562505487214321714",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="membership_secret_test_key_32_bytes_ok",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        self.mock_bot = MockBotInstance([1001, 2002, "3003"])
        app = create_app(
            config=self.config,
            db=self.db,
            serve_website=False,
            bot=self.mock_bot,
            bot_getter=lambda: self.mock_bot
        )
        return app

    def _make_session_cookie(self, user_id: str, guilds: list[dict[str, Any]]) -> dict[str, str]:
        token = create_session_token({
            "user_id": user_id,
            "username": "TestManager",
            "access_token": "mock_test_token",
            "mock_guilds": guilds,
        }, self.config.secret_key)
        return {self.config.session_cookie_name: token}

    async def test_case_1_installed_and_manageable_server_is_installed(self):
        """User can manage and KYOKA is installed -> status: installed, bot_installed: True."""
        user_guilds = [
            {"id": "1001", "name": "Installed Admin Server", "permissions": 8, "owner": False},
            {"id": "2002", "name": "Installed Owner Server", "permissions": 0, "owner": True},
        ]
        self.db.known_bot_guilds = {1001, 2002}
        cookies = self._make_session_cookie("12345", user_guilds)

        resp = await self.client.get("/api/guilds?installed_only=1", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        assert len(data["guilds"]) == 2
        for g in data["guilds"]:
            assert g["can_manage"] is True
            assert g["bot_installed"] is True
            assert g["status"] == "installed"

    async def test_case_2_absent_server_not_shown_when_installed_only(self):
        """User owns/manages server, but KYOKA is NOT installed -> excluded when installed_only=1."""
        user_guilds = [
            {"id": "1001", "name": "Present Server", "permissions": 8, "owner": True},
            {"id": "9999", "name": "Absent Server", "permissions": 8, "owner": True},
        ]
        self.db.known_bot_guilds = {1001}
        cookies = self._make_session_cookie("12345", user_guilds)

        resp = await self.client.get("/api/guilds?installed_only=1", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        guild_ids = [g["id"] for g in data["guilds"]]
        assert "1001" in guild_ids
        assert "9999" not in guild_ids

    async def test_case_3_unverified_membership_returns_unavailable_not_absent(self):
        """When membership check cannot be verified, return status: unavailable with verification error state."""
        user_guilds = [
            {"id": "1001", "name": "Server In Limbo", "permissions": 8, "owner": True},
        ]
        cookies = self._make_session_cookie("12345", user_guilds)

        # In standard flow, if bot_check_ok is False and bot_guild_ids is empty
        # simulate verification unavailable
        from dashboard_api.routes import guild_routes
        original_fetch = guild_routes.fetch_bot_guilds

        async def mock_failed_fetch(*args, **kwargs):
            return set(), False

        guild_routes.fetch_bot_guilds = mock_failed_fetch
        try:
            # Bypass mock_test_token by providing a different token to trigger live path
            token = create_session_token({
                "user_id": "12345",
                "username": "TestManager",
                "access_token": "non_mock_token",
            }, self.config.secret_key)

            # Mock fetch_user_guilds to return the manageable guild
            original_user_fetch = guild_routes.fetch_user_guilds
            async def mock_user_fetch(*args, **kwargs):
                return user_guilds
            guild_routes.fetch_user_guilds = mock_user_fetch

            try:
                # Clear auxiliary db ids so it isolates verification failure
                self.db.known_bot_guilds = set()
                resp = await self.client.get("/api/guilds?installed_only=1", cookies={self.config.session_cookie_name: token})
                assert resp.status == 200
                data = await resp.json()
                assert data["verification_status"] == "unavailable"
                assert len(data["guilds"]) == 1
                assert data["guilds"][0]["status"] == "unavailable"
                assert data["guilds"][0]["bot_installed"] is False
            finally:
                guild_routes.fetch_user_guilds = original_user_fetch
        finally:
            guild_routes.fetch_bot_guilds = original_fetch

    async def test_case_4_refresh_updates_list_and_purges_cache(self):
        """Refreshing with ?refresh=1 immediately reflects new installations."""
        user_guilds = [
            {"id": "1001", "name": "Server 1001", "permissions": 8, "owner": True},
            {"id": "5555", "name": "Newly Joined Server", "permissions": 8, "owner": True},
        ]
        self.db.known_bot_guilds = {1001}
        cookies = self._make_session_cookie("12345", user_guilds)

        # First query: 5555 is absent
        resp1 = await self.client.get("/api/guilds?installed_only=1", cookies=cookies)
        data1 = await resp1.json()
        assert not any(g["id"] == "5555" for g in data1["guilds"])

        # KYOKA is invited and added to 5555
        self.db.known_bot_guilds.add(5555)

        # Query with refresh=1
        resp2 = await self.client.get("/api/guilds?refresh=1&installed_only=1", cookies=cookies)
        assert resp2.status == 200
        data2 = await resp2.json()
        assert any(g["id"] == "5555" for g in data2["guilds"])

    async def test_case_5_guild_id_normalization_int_vs_str(self):
        """Verify integer vs string snowflake guild IDs match accurately without type mismatch."""
        user_guilds = [
            # Discord API delivers string snowflakes
            {"id": "1562505487214321714", "name": "Snowflake Server", "permissions": 8, "owner": True},
        ]
        # Bot instance or DB delivers integer snowflakes
        self.db.known_bot_guilds = {1562505487214321714}
        cookies = self._make_session_cookie("12345", user_guilds)

        resp = await self.client.get("/api/guilds?installed_only=1", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        assert len(data["guilds"]) == 1
        assert data["guilds"][0]["id"] == "1562505487214321714"
        assert data["guilds"][0]["bot_installed"] is True
        assert data["guilds"][0]["status"] == "installed"

    async def test_case_6_live_bot_instance_authoritative_resolution(self):
        """Authoritative KyokaBot instance guilds are used directly."""
        session = self.app["http_session"]
        bot_inst = MockBotInstance([8888, 9999])
        guild_ids, ok = await fetch_bot_guilds("bogus_token", session, force_refresh=True, bot_instance=bot_inst)
        assert ok is True
        assert "8888" in guild_ids
        assert "9999" in guild_ids
