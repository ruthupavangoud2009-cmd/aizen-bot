"""Unit and integration tests for dashboard security headers, rate limiting, and unauthenticated access."""
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app


class TestDashboardSecurity(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/kyoka",
            secret_key="test_security_secret_key_32_chars_long",
            is_production=True,
            database_url="",
            rate_limit_per_minute=5,  # Low limit for testing
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    async def test_security_headers_present(self):
        resp = await self.client.get("/api/health")
        assert resp.status == 200
        headers = resp.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert "default-src" in headers.get("Content-Security-Policy", "")

    async def test_unauthenticated_requests_rejected(self):
        # /api/auth/me without cookie/token
        resp_me = await self.client.get("/api/auth/me")
        assert resp_me.status == 401

        # /api/guilds without cookie/token
        resp_guilds = await self.client.get("/api/guilds")
        assert resp_guilds.status == 401

        # /api/guilds/1001/settings without cookie/token
        resp_settings = await self.client.get("/api/guilds/1001/settings")
        assert resp_settings.status == 401

    async def test_rate_limiting_triggers(self):
        # Rate limit is set to 5 per minute
        for i in range(5):
            resp = await self.client.get("/api/stats")
            assert resp.status == 200

        # 6th request should hit 429
        rate_limited_resp = await self.client.get("/api/stats")
        assert rate_limited_resp.status == 429
        assert "Retry-After" in rate_limited_resp.headers
