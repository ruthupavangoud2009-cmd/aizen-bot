"""Unit and integration tests for dashboard health checks, public stats, and command inventory."""
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app


class TestDashboardHealth(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_health_secret_key_32_chars_long",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    async def test_health_check(self):
        resp = await self.client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "kyoka-dashboard-api"
        assert data["database_connected"] is True

    async def test_public_stats(self):
        resp = await self.client.get("/api/stats")
        assert resp.status == 200
        data = await resp.json()
        assert "guilds" in data
        assert "users" in data
        assert data["commands_available"] == 50
        assert data["status"] == "online"

    async def test_official_commands_inventory(self):
        resp = await self.client.get("/api/commands")
        assert resp.status == 200
        data = await resp.json()
        commands = data["commands"]
        assert len(commands) >= 50
        # Check command structure
        cmd = commands[0]
        assert "name" in cmd
        assert "description" in cmd
        assert "category" in cmd


class TestWebsiteStaticServing(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_health_secret_key_32_chars_long",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        # Serve website enabled
        app = create_app(config=self.config, db=self.db, serve_website=True)
        return app

    async def test_homepage_serves_html_not_directory_index(self):
        resp = await self.client.get("/")
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        text = await resp.text()
        assert "Index of /" not in text
        assert "KYOKA 3.0" in text

    async def test_clean_named_page_routes(self):
        for route in ["/features", "/commands", "/premium", "/dashboard", "/owner"]:
            resp = await self.client.get(route)
            assert resp.status == 200, f"Route {route} failed with {resp.status}"
            assert "text/html" in resp.headers.get("Content-Type", "")

    async def test_directory_browsing_disabled(self):
        resp = await self.client.get("/css/")
        assert resp.status == 403
