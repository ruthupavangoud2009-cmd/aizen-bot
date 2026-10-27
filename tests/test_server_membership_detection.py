"""Authoritative tests for KYOKA 3.0 Server Membership Detection, Management Features & Regression.

Covers the 9 mandatory regression test scenarios:
1. Bot installed -> Manage Server appears (status: installed, bot_installed: True).
2. Bot absent -> Add Bot appears only for authorized managers (status: not_installed, unmanageable servers excluded).
3. Bot installed but database cache is stale -> membership is correctly refreshed with ?refresh=1.
4. Wrong bot identity or wrong server ID -> no false positive.
5. OAuth token expired -> clear reconnect flow (401/error response).
6. Discord API timeout, rate limit, or error -> no false claim that the bot is absent (status: unavailable).
7. User cannot manage a server -> protected management actions are rejected (HTTP 403 Forbidden).
8. Every management button reaches the correct backend operation (settings, test-event, automod).
9. Existing authentication and working website features continue to work.
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

    async def test_case_1_bot_installed_manage_server_appears(self):
        """1. Bot installed -> Manage Server appears with status: installed and bot_installed: True."""
        user_guilds = [
            {"id": "1001", "name": "Installed Admin Server", "permissions": 8, "owner": False},
            {"id": "2002", "name": "Installed Owner Server", "permissions": 0, "owner": True},
        ]
        self.db.known_bot_guilds = {1001, 2002}
        cookies = self._make_session_cookie("12345", user_guilds)

        resp = await self.client.get("/api/guilds", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        assert len(data["guilds"]) == 2
        for g in data["guilds"]:
            assert g["can_manage"] is True
            assert g["bot_installed"] is True
            assert g["status"] == "installed"

    async def test_case_2_bot_absent_add_bot_appears_only_for_authorized_managers(self):
        """2. Bot absent -> Add Bot appears only for authorized managers; unmanageable servers excluded with manageable_only."""
        user_guilds = [
            {"id": "1001", "name": "Installed Server", "permissions": 8, "owner": False},
            {"id": "7777", "name": "Manageable Absent Server", "permissions": 32, "owner": False},  # Manage Guild
            {"id": "8888", "name": "Unmanageable Server", "permissions": 0, "owner": False},      # No manage rights
        ]
        self.db.known_bot_guilds = {1001}
        cookies = self._make_session_cookie("12345", user_guilds)

        # 1. Query with manageable_only=1 (used by dashboard): unmanageable server 8888 is excluded
        resp = await self.client.get("/api/guilds?manageable_only=1", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        guild_map = {g["id"]: g for g in data["guilds"]}

        # Manageable absent server 7777 must appear with not_installed and valid invite_url
        assert "7777" in guild_map
        assert guild_map["7777"]["can_manage"] is True
        assert guild_map["7777"]["bot_installed"] is False
        assert guild_map["7777"]["status"] == "not_installed"
        assert "discord.com/oauth2/authorize" in guild_map["7777"]["invite_url"]

        # Installed server 1001 must appear with installed
        assert "1001" in guild_map
        assert guild_map["1001"]["status"] == "installed"
        assert guild_map["1001"]["bot_installed"] is True

        # Server without management rights 8888 must NOT appear when manageable_only=1
        assert "8888" not in guild_map

        # 2. Query without filter: unmanageable server 8888 has can_manage: False and status: permission_required
        resp_all = await self.client.get("/api/guilds", cookies=cookies)
        assert resp_all.status == 200
        all_guilds = {g["id"]: g for g in (await resp_all.json())["guilds"]}
        assert all_guilds["8888"]["can_manage"] is False
        assert all_guilds["8888"]["status"] == "permission_required"

    async def test_case_3_bot_installed_stale_cache_refreshed(self):
        """3. Bot installed but database cache is stale -> membership is refreshed with ?refresh=1."""
        user_guilds = [
            {"id": "1001", "name": "Server 1001", "permissions": 8, "owner": True},
            {"id": "5555", "name": "Newly Joined Server", "permissions": 8, "owner": True},
        ]
        self.db.known_bot_guilds = {1001}
        cookies = self._make_session_cookie("12345", user_guilds)

        # Before invite: 5555 is not_installed
        resp1 = await self.client.get("/api/guilds", cookies=cookies)
        data1 = await resp1.json()
        g5555_before = next(g for g in data1["guilds"] if g["id"] == "5555")
        assert g5555_before["status"] == "not_installed"
        assert g5555_before["bot_installed"] is False

        # Bot is added to server 5555
        self.db.known_bot_guilds.add(5555)

        # Scanner refresh with ?refresh=1 immediately updates status to installed
        resp2 = await self.client.get("/api/guilds?refresh=1", cookies=cookies)
        assert resp2.status == 200
        data2 = await resp2.json()
        g5555_after = next(g for g in data2["guilds"] if g["id"] == "5555")
        assert g5555_after["status"] == "installed"
        assert g5555_after["bot_installed"] is True

    async def test_case_4_wrong_bot_identity_or_wrong_server_id_no_false_positive(self):
        """4. Wrong bot identity or wrong server ID -> no false positive."""
        user_guilds = [
            {"id": "999999999999999999", "name": "Foreign Server", "permissions": 8, "owner": True},
        ]
        # Bot only knows guild 1001
        self.db.known_bot_guilds = {1001}
        cookies = self._make_session_cookie("12345", user_guilds)

        resp = await self.client.get("/api/guilds", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        assert len(data["guilds"]) == 1
        assert data["guilds"][0]["id"] == "999999999999999999"
        assert data["guilds"][0]["bot_installed"] is False
        assert data["guilds"][0]["status"] == "not_installed"

    async def test_case_5_oauth_token_expired_reconnect_flow(self):
        """5. OAuth token expired -> clear reconnect flow with HTTP 502/401."""
        from dashboard_api.routes import guild_routes
        original_fetch = guild_routes.fetch_user_guilds

        async def mock_expired_token(*args, **kwargs):
            raise RuntimeError("Failed to fetch user guilds from Discord (HTTP 401)")

        guild_routes.fetch_user_guilds = mock_expired_token
        try:
            token = create_session_token({
                "user_id": "12345",
                "username": "ExpiredUser",
                "access_token": "expired_access_token",
            }, self.config.secret_key)
            resp = await self.client.get("/api/guilds", cookies={self.config.session_cookie_name: token})
            assert resp.status in (401, 502)
        finally:
            guild_routes.fetch_user_guilds = original_fetch

    async def test_case_6_discord_api_error_or_rate_limit_returns_unavailable_not_absent(self):
        """6. Discord API timeout, rate limit, or error -> returns status: unavailable, never false absent."""
        user_guilds = [
            {"id": "1001", "name": "Server During Outage", "permissions": 8, "owner": True},
        ]
        from dashboard_api.routes import guild_routes
        original_bot_fetch = guild_routes.fetch_bot_guilds
        original_user_fetch = guild_routes.fetch_user_guilds

        async def mock_failed_bot_fetch(*args, **kwargs):
            return set(), False  # Verification failed (e.g. rate limit 429)

        async def mock_user_fetch(*args, **kwargs):
            return user_guilds

        guild_routes.fetch_bot_guilds = mock_failed_bot_fetch
        guild_routes.fetch_user_guilds = mock_user_fetch
        try:
            token = create_session_token({
                "user_id": "12345",
                "username": "TestUser",
                "access_token": "live_token",
            }, self.config.secret_key)
            self.db.known_bot_guilds = set()
            resp = await self.client.get("/api/guilds", cookies={self.config.session_cookie_name: token})
            assert resp.status == 200
            data = await resp.json()
            assert data["verification_status"] == "unavailable"
            assert len(data["guilds"]) == 1
            # Crucial: Must be unavailable, NEVER falsely reported as not_installed
            assert data["guilds"][0]["status"] == "unavailable"
            assert data["guilds"][0]["bot_installed"] is False
        finally:
            guild_routes.fetch_bot_guilds = original_bot_fetch
            guild_routes.fetch_user_guilds = original_user_fetch

    async def test_case_7_unauthorized_user_management_actions_rejected(self):
        """7. User cannot manage a server -> protected management actions are rejected with HTTP 403."""
        # User only manages server 1001, NOT server 2002
        user_guilds = [
            {"id": "1001", "name": "Managed Server", "permissions": 8, "owner": True},
        ]
        cookies = self._make_session_cookie("12345", user_guilds)

        # GET settings for unmanaged server 2002 -> 403
        resp_get = await self.client.get("/api/guilds/2002/settings", cookies=cookies)
        assert resp_get.status == 403

        # PATCH settings for unmanaged server 2002 -> 403
        resp_patch = await self.client.patch("/api/guilds/2002/settings", json={"general": {"prefix": "!"}}, cookies=cookies)
        assert resp_patch.status == 403

        # Test event simulation for unmanaged server 2002 -> 403
        resp_sim = await self.client.post("/api/guilds/2002/test-event", json={"event_type": "welcome"}, cookies=cookies)
        assert resp_sim.status == 403

    async def test_case_8_management_actions_reach_correct_backend(self):
        """8. Every management button reaches the correct backend operation."""
        user_guilds = [
            {"id": "1001", "name": "Managed Server", "permissions": 8, "owner": True},
        ]
        cookies = self._make_session_cookie("12345", user_guilds)

        # 1. Save settings (PATCH /api/guilds/{id}/settings)
        resp_settings = await self.client.patch("/api/guilds/1001/settings", json={
            "general": {"prefix": "?"},
            "welcome_leave": {"welcome_enabled": True, "welcome_message": "Hello {user}!"},
        }, cookies=cookies)
        assert resp_settings.status == 200
        data_settings = await resp_settings.json()
        assert data_settings["success"] is True
        assert data_settings["settings"]["general"]["prefix"] == "?"

        # 2. Test event simulation (POST /api/guilds/{id}/test-event)
        resp_sim = await self.client.post("/api/guilds/1001/test-event", json={"event_type": "welcome"}, cookies=cookies)
        assert resp_sim.status == 200
        data_sim = await resp_sim.json()
        assert data_sim["success"] is True
        assert "simulated_message" in data_sim

        # 3. AutoMod test simulation (POST /api/guilds/{id}/automod/test)
        resp_am = await self.client.post("/api/guilds/1001/automod/test", json={"message_text": "discord.gg/invitelink"}, cookies=cookies)
        assert resp_am.status == 200
        data_am = await resp_am.json()
        assert data_am["success"] is True
        assert "is_violation" in data_am

    async def test_case_9_existing_auth_and_session_token_verification(self):
        """9. Existing authentication and working website features continue to work."""
        session_data = {
            "user_id": "1505515188991033409",
            "username": "AizenOwner",
            "access_token": "mock_test_token",
            "mock_guilds": [{"id": "1001", "name": "Aizen Sanctuary", "permissions": 8, "owner": True}],
        }
        token = create_session_token(session_data, self.config.secret_key)
        assert isinstance(token, str) and "." in token

        # Verify normalized ID resolution on live bot instance
        session = self.app["http_session"]
        bot_inst = MockBotInstance([1562505487214321714])
        guild_ids, ok = await fetch_bot_guilds("token", session, force_refresh=True, bot_instance=bot_inst)
        assert ok is True
        assert "1562505487214321714" in guild_ids
