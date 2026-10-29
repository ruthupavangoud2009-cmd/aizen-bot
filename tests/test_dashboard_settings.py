"""Unit and integration tests for dashboard settings saving, loading, and validation."""
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token


class TestDashboardSettings(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_settings_secret_key_32_chars_long",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    def _create_auth_headers(self, guild_id: str = "1001") -> dict:
        session_data = {
            "user_id": "999888777",
            "username": "GuildAdmin",
            "access_token": "mock_test_token",
            "mock_guilds": [
                {
                    "id": guild_id,
                    "name": "Test Managed Server",
                    "permissions": "32",  # Manage Guild
                    "owner": False,
                },
                {
                    "id": "2002",
                    "name": "Unmanaged Server",
                    "permissions": "0",  # No permissions
                    "owner": False,
                }
            ]
        }
        token = create_session_token(session_data, self.config.secret_key)
        return {"Authorization": f"Bearer {token}"}

    async def test_get_settings_authorized(self):
        headers = self._create_auth_headers("1001")
        resp = await self.client.get("/api/guilds/1001/settings", headers=headers)
        assert resp.status == 200
        data = await resp.json()
        assert data["guild_id"] == "1001"
        assert "general" in data
        assert "antinuke" in data
        assert "verification" in data
        assert "music" in data
        assert "ai" in data

    async def test_cross_server_isolation_denies_unauthorized_guild(self):
        headers = self._create_auth_headers("1001")
        # Try to access guild 2002 (in list, but permissions=0)
        resp = await self.client.get("/api/guilds/2002/settings", headers=headers)
        assert resp.status == 403

        # Try to access completely foreign guild 9999
        resp2 = await self.client.get("/api/guilds/9999/settings", headers=headers)
        assert resp2.status == 403

    async def test_update_settings_valid(self):
        headers = self._create_auth_headers("1001")
        payload = {
            "general": {
                "prefix": "k!",
                "language": "es"
            },
            "music": {
                "default_volume": 85,
                "autoplay": True
            },
            "antinuke": {
                "enabled": True,
                "punishment": "kick"
            }
        }
        resp = await self.client.patch("/api/guilds/1001/settings", headers=headers, json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        settings = data["settings"]
        assert settings["general"]["prefix"] == "k!"
        assert settings["general"]["language"] == "es"
        assert settings["music"]["default_volume"] == 85
        assert settings["music"]["autoplay"] is True
        assert settings["antinuke"]["enabled"] is True
        assert settings["antinuke"]["punishment"] == "kick"

    async def test_update_settings_validation_errors(self):
        headers = self._create_auth_headers("1001")

        # Invalid prefix (>10 chars)
        bad_prefix_payload = {"general": {"prefix": "thisprefixiswaytoolong"}}
        resp = await self.client.patch("/api/guilds/1001/settings", headers=headers, json=bad_prefix_payload)
        assert resp.status == 400

        # Invalid volume (>150)
        bad_volume_payload = {"music": {"default_volume": 999}}
        resp = await self.client.patch("/api/guilds/1001/settings", headers=headers, json=bad_volume_payload)
        assert resp.status == 400

        # Invalid punishment enum
        bad_punish_payload = {"antinuke": {"punishment": "destroy_server"}}
        resp = await self.client.patch("/api/guilds/1001/settings", headers=headers, json=bad_punish_payload)
        assert resp.status == 400

    async def test_branding_endpoints_lifecycle(self):
        headers = self._create_auth_headers("1001")

        # 1. Fetch initial branding
        resp = await self.client.get("/api/guilds/1001/branding", headers=headers)
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "branding" in data
        assert data["branding"]["display_name"] == "KYOKA 3.0"

        # 2. Update bio
        resp_bio = await self.client.post("/api/guilds/1001/bio", headers=headers, json={"bio": "Testing server bio from dashboard"})
        assert resp_bio.status == 200
        bio_data = await resp_bio.json()
        assert bio_data["success"] is True
        assert bio_data["bio"] == "Testing server bio from dashboard"

        # 3. Update banner (guild 1001 has mock premium)
        resp_banner = await self.client.post("/api/guilds/1001/banner", headers=headers, json={"banner_url": "https://cdn.discordapp.com/attachments/123/banner.png"})
        assert resp_banner.status == 200
        banner_data = await resp_banner.json()
        assert banner_data["success"] is True
        assert banner_data["banner_url"] == "https://cdn.discordapp.com/attachments/123/banner.png"

        # 4. Reset branding
        resp_reset = await self.client.post("/api/guilds/1001/branding/reset", headers=headers)
        assert resp_reset.status == 200
        reset_data = await resp_reset.json()
        assert reset_data["success"] is True
        assert "reset" in reset_data["message"].lower()

