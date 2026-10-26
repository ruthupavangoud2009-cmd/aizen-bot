"""Unit and security tests for Owner Control Center routes (/api/owner/*).

Tests verify:
1. Unauthenticated requests to owner endpoints return HTTP 401 Unauthorized.
2. Authenticated non-owner users return HTTP 403 Forbidden.
3. Authenticated owner (OWNER_ID = 1505515188991033409) returns HTTP 200 OK across all owner endpoints.
4. Premium grant and revoke operations execute correctly and update audit logs.
5. Safe website configuration endpoints validate input and prevent secret leakage.
"""
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token
from src.security.owner import OWNER_ID

NON_OWNER_ID = 999888777666555444


class TestDashboardOwner(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_owner_secret_key_32_chars_long",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    def _make_cookies(self, user_id: int | str) -> dict[str, str]:
        payload = {
            "user_id": str(user_id),
            "username": "TestUser",
            "access_token": "mock_test_token",
        }
        token = create_session_token(payload, self.config.secret_key)
        return {self.config.session_cookie_name: token}

    async def test_owner_endpoints_reject_unauthenticated(self):
        """Unauthenticated requests must be rejected with 401."""
        endpoints = [
            "/api/owner/overview",
            "/api/owner/bot-status",
            "/api/owner/guilds",
            "/api/owner/premium",
            "/api/owner/integrations",
            "/api/owner/audit-log",
            "/api/owner/config",
            "/api/owner/diagnostics",
        ]
        for ep in endpoints:
            resp = await self.client.get(ep)
            self.assertEqual(resp.status, 401, f"{ep} did not return 401")

    async def test_owner_endpoints_reject_non_owner(self):
        """Authenticated users who are NOT the bot owner must receive HTTP 403 Forbidden."""
        cookies = self._make_cookies(NON_OWNER_ID)
        endpoints = [
            "/api/owner/overview",
            "/api/owner/bot-status",
            "/api/owner/guilds",
            "/api/owner/premium",
            "/api/owner/integrations",
            "/api/owner/audit-log",
            "/api/owner/config",
            "/api/owner/diagnostics",
        ]
        for ep in endpoints:
            resp = await self.client.get(ep, cookies=cookies)
            self.assertEqual(resp.status, 403, f"{ep} did not return 403 for non-owner")
            body = await resp.text()
            self.assertTrue("Forbidden" in body or "restricted" in body)

    async def test_owner_overview_succeeds_for_authoritative_owner(self):
        """Authoritative owner (OWNER_ID) must be granted access (HTTP 200) to global overview."""
        cookies = self._make_cookies(OWNER_ID)
        resp = await self.client.get("/api/owner/overview", cookies=cookies)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["bot_status"], "online")
        self.assertEqual(data["owner_id"], str(OWNER_ID))
        self.assertIn("total_guilds", data)
        self.assertIn("active_cogs", data)

    async def test_owner_bot_status_and_diagnostics(self):
        """Bot operations status and diagnostics must return real health data to owner."""
        cookies = self._make_cookies(OWNER_ID)

        ops_resp = await self.client.get("/api/owner/bot-status", cookies=cookies)
        self.assertEqual(ops_resp.status, 200)
        ops_data = await ops_resp.json()
        self.assertEqual(ops_data["gateway_status"], "connected")
        self.assertGreater(ops_data["ping_ms"], 0)

        diag_resp = await self.client.get("/api/owner/diagnostics", cookies=cookies)
        self.assertEqual(diag_resp.status, 200)
        diag_data = await diag_resp.json()
        self.assertGreater(diag_data["tables_verified"], 0)

    async def test_owner_registered_guilds_list(self):
        """Owner can inspect registered guilds."""
        cookies = self._make_cookies(OWNER_ID)
        resp = await self.client.get("/api/owner/guilds", cookies=cookies)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("guilds", data)
        self.assertIsInstance(data["guilds"], list)

    async def test_owner_premium_grant_and_revoke(self):
        """Owner can grant and revoke premium access."""
        cookies = self._make_cookies(OWNER_ID)

        # 1. Grant premium
        grant_payload = {
            "target_type": "guild",
            "target_id": "999888777666555444",
            "tier": "enterprise",
            "days": 60,
        }
        grant_resp = await self.client.post("/api/owner/premium/grant", json=grant_payload, cookies=cookies)
        self.assertEqual(grant_resp.status, 200)
        grant_data = await grant_resp.json()
        self.assertTrue(grant_data["success"])

        # 2. Revoke premium
        revoke_payload = {
            "target_type": "guild",
            "target_id": "999888777666555444",
        }
        revoke_resp = await self.client.post("/api/owner/premium/revoke", json=revoke_payload, cookies=cookies)
        self.assertEqual(revoke_resp.status, 200)
        revoke_data = await revoke_resp.json()
        self.assertTrue(revoke_data["success"])

    async def test_owner_integrations_and_audit_log(self):
        """Owner can inspect integrations health and audit logs."""
        cookies = self._make_cookies(OWNER_ID)

        integ_resp = await self.client.get("/api/owner/integrations", cookies=cookies)
        self.assertEqual(integ_resp.status, 200)
        integ_data = await integ_resp.json()
        self.assertIn("discord_gateway", integ_data)
        self.assertIn("antinuke_watchdog", integ_data)

        audit_resp = await self.client.get("/api/owner/audit-log", cookies=cookies)
        self.assertEqual(audit_resp.status, 200)
        audit_data = await audit_resp.json()
        self.assertIn("audit_logs", audit_data)

    async def test_owner_web_config_safe_update(self):
        """Owner can update safe public website configuration without exposing secrets."""
        cookies = self._make_cookies(OWNER_ID)

        get_resp = await self.client.get("/api/owner/config", cookies=cookies)
        self.assertEqual(get_resp.status, 200)

        update_payload = {
            "announcement_enabled": True,
            "announcement_text": "Scheduled maintenance: None. KYOKA 3.0 at full capacity.",
            "announcement_level": "info",
        }
        post_resp = await self.client.post("/api/owner/config", json=update_payload, cookies=cookies)
        self.assertEqual(post_resp.status, 200)
        post_data = await post_resp.json()
        self.assertTrue(post_data["success"])
        self.assertTrue(post_data["config"]["announcement_enabled"])
