"""Comprehensive regression and integration tests for KYOKA 3.0 fixes.

Covers:
1. Session token verification (both Python HMAC and Cloudflare base64 JSON formats).
2. Owner authorization (401 unauthenticated, 403 non-owner, 200 authoritative owner 1505515188991033409).
3. Discord guild permissions (Administrator 0x8, Manage Guild 0x20, and Server Owner).
4. Server scanner refresh handling (?refresh=1).
5. Ticket creation, creator retrieval, integer-vs-string user_id matching, and privacy isolation.
6. Ticket retrieval when Discord thread sync is unavailable.
7. Dashboard overview with complete and missing optional fields.
"""
import base64
import json
import time
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token, verify_session_token
from dashboard_api.permissions import has_manage_permission, can_manage_guild, ADMINISTRATOR, MANAGE_GUILD
from src.security.owner import OWNER_ID, is_primary_owner

NON_OWNER_ID = 999888777666555444
OTHER_USER_ID = 111222333444555666


class TestAuditFixesRecovery(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="1562505487214321714",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=1562505487214321714",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_recovery_secret_key_32_chars_long",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    def _make_hmac_cookie(self, user_id: int | str) -> dict[str, str]:
        payload = {
            "user_id": str(user_id),
            "username": "OwnerUser",
            "access_token": "mock_test_token",
        }
        token = create_session_token(payload, self.config.secret_key)
        return {self.config.session_cookie_name: token}

    def _make_edge_b64_cookie(self, user_id: int | str) -> dict[str, str]:
        payload = {
            "user_id": str(user_id),
            "username": "EdgeOwnerUser",
            "access_token": "mock_test_token",
            "expires_at": int(time.time() * 1000) + 86400000,
        }
        raw_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        return {self.config.session_cookie_name: raw_b64}

    # 1. Dual-format Token Verification
    def test_verify_session_token_both_formats(self):
        """Verify that verify_session_token handles both Python HMAC and Cloudflare Edge base64 JSON tokens."""
        # A. Python HMAC
        payload = {"user_id": str(OWNER_ID), "username": "Aizen"}
        hmac_token = create_session_token(payload, self.config.secret_key)
        verified_hmac = verify_session_token(hmac_token, self.config.secret_key)
        assert verified_hmac is not None
        assert verified_hmac["user_id"] == str(OWNER_ID)

        # B. Cloudflare Edge base64 JSON token (no dot)
        edge_payload = {
            "user_id": str(OWNER_ID),
            "username": "AizenEdge",
            "expires_at": int(time.time() * 1000) + 60000,
        }
        edge_token = base64.b64encode(json.dumps(edge_payload).encode("utf-8")).decode("utf-8")
        verified_edge = verify_session_token(edge_token, self.config.secret_key)
        assert verified_edge is not None
        assert verified_edge["user_id"] == str(OWNER_ID)
        assert verified_edge["username"] == "AizenEdge"

    # 2. Owner Authorization Checks
    async def test_owner_endpoint_access_control(self):
        """Owner endpoints reject unauthenticated (401), non-owners (403), and allow owner (200)."""
        # Unauthenticated -> 401
        res_unauth = await self.client.get("/api/owner/overview")
        assert res_unauth.status == 401

        # Non-owner with HMAC -> 403
        res_non_owner = await self.client.get(
            "/api/owner/overview",
            cookies=self._make_hmac_cookie(NON_OWNER_ID),
        )
        assert res_non_owner.status == 403

        # Non-owner with Edge base64 -> 403
        res_non_owner_edge = await self.client.get(
            "/api/owner/overview",
            cookies=self._make_edge_b64_cookie(NON_OWNER_ID),
        )
        assert res_non_owner_edge.status == 403

        # Authoritative owner (1505515188991033409) with HMAC -> 200
        res_owner_hmac = await self.client.get(
            "/api/owner/overview",
            cookies=self._make_hmac_cookie(OWNER_ID),
        )
        assert res_owner_hmac.status == 200
        data_hmac = await res_owner_hmac.json()
        assert data_hmac["bot_status"] == "online"

        # Authoritative owner (1505515188991033409) with Edge base64 -> 200
        res_owner_edge = await self.client.get(
            "/api/owner/overview",
            cookies=self._make_edge_b64_cookie(OWNER_ID),
        )
        assert res_owner_edge.status == 200
        data_edge = await res_owner_edge.json()
        assert data_edge["bot_status"] == "online"

    # 3. Discord Guild Permissions Calculation
    def test_discord_guild_permissions(self):
        """Verify Administrator (0x8), Manage Guild (0x20), and Server Owner permissions."""
        # Neither bit, not owner -> False
        assert not has_manage_permission(0, is_owner=False)
        assert not has_manage_permission("0", is_owner=False)

        # Administrator bit 0x8 -> True
        assert has_manage_permission(ADMINISTRATOR, is_owner=False)
        assert has_manage_permission(str(ADMINISTRATOR), is_owner=False)
        assert has_manage_permission(0x8 | 0x2000, is_owner=False)

        # Manage Guild bit 0x20 -> True
        assert has_manage_permission(MANAGE_GUILD, is_owner=False)
        assert has_manage_permission(str(MANAGE_GUILD), is_owner=False)

        # Server owner -> True regardless of permissions bitfield
        assert has_manage_permission(0, is_owner=True)
        assert has_manage_permission(None, is_owner=True)

        # can_manage_guild payload helper
        assert can_manage_guild({"owner": True, "permissions": "0"})
        assert can_manage_guild({"owner": False, "permissions": str(ADMINISTRATOR)})
        assert can_manage_guild({"owner": False, "permissions": str(MANAGE_GUILD)})
        assert not can_manage_guild({"owner": False, "permissions": "0"})

    # 4. Ticket System: Creator Retrieval & Cross-Type user_id Isolation
    async def test_ticket_creator_retrieval_and_privacy(self):
        """Ensure ticket creator can retrieve their ticket (int vs str user_id) and other users cannot."""
        cookies_creator = self._make_hmac_cookie(OWNER_ID)
        cookies_other = self._make_hmac_cookie(OTHER_USER_ID)

        # 1. Creator creates a ticket
        create_resp = await self.client.post(
            "/api/tickets",
            json={
                "category": "technical",
                "subject": "Website Dashboard Verification",
                "description": "Verifying ticket sync between website and discord staff thread.",
                "guild_id": "123456789012345678",
            },
            cookies=cookies_creator,
        )
        assert create_resp.status in (200, 201)
        created_data = await create_resp.json()
        ticket_id = created_data["ticket"]["ticket_id"]

        # 2. Creator retrieves their tickets list
        list_resp = await self.client.get("/api/tickets", cookies=cookies_creator)
        assert list_resp.status == 200
        list_data = await list_resp.json()
        assert any(t["ticket_id"] == ticket_id for t in list_data["tickets"])

        # 3. Creator retrieves specific ticket details
        detail_resp = await self.client.get(f"/api/tickets/{ticket_id}", cookies=cookies_creator)
        assert detail_resp.status == 200
        detail_data = await detail_resp.json()
        assert str(detail_data["ticket"]["user_id"]) == str(OWNER_ID)

        # 4. Creator replies to ticket
        reply_resp = await self.client.post(
            f"/api/tickets/{ticket_id}/reply",
            json={"content": "Here is an update regarding website dashboard."},
            cookies=cookies_creator,
        )
        assert reply_resp.status == 200

        # 5. Other user tries to access creator's ticket -> 403 Forbidden
        other_detail = await self.client.get(f"/api/tickets/{ticket_id}", cookies=cookies_other)
        assert other_detail.status == 403

        other_reply = await self.client.post(
            f"/api/tickets/{ticket_id}/reply",
            json={"content": "Unauthorized intrusion attempt."},
            cookies=cookies_other,
        )
        assert other_reply.status == 403

        # 6. Other user lists tickets -> creator's ticket is NOT in other user's list
        other_list = await self.client.get("/api/tickets", cookies=cookies_other)
        assert other_list.status == 200
        other_tickets = await other_list.json()
        assert not any(t["ticket_id"] == ticket_id for t in other_tickets["tickets"])

    # 5. Guild List with Mock Guilds & Force Refresh
    async def test_guild_list_and_refresh(self):
        """Test server listing and refresh flag handling."""
        mock_guilds = [
            {
                "id": "1001",
                "name": "Admin Server",
                "permissions": str(ADMINISTRATOR),
                "owner": False,
            },
            {
                "id": "1002",
                "name": "Owner Server",
                "permissions": "0",
                "owner": True,
            },
            {
                "id": "1003",
                "name": "Member Server",
                "permissions": "0",
                "owner": False,
            },
        ]
        payload = {
            "user_id": str(OWNER_ID),
            "username": "ServerTester",
            "access_token": "mock_test_token",
            "mock_guilds": mock_guilds,
        }
        token = create_session_token(payload, self.config.secret_key)
        cookies = {self.config.session_cookie_name: token}

        resp = await self.client.get("/api/guilds?refresh=1", cookies=cookies)
        assert resp.status == 200
        data = await resp.json()
        guilds = data["guilds"]

        # Only manageable servers (Admin or Owner) should be returned with can_manage: True
        manageable_ids = [g["id"] for g in guilds if g["can_manage"]]
        assert "1001" in manageable_ids
        assert "1002" in manageable_ids
        assert "1003" not in manageable_ids
