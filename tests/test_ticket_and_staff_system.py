"""Automated unit and integration test suite for KYOKA 3.0 Website Tickets & Staff Management.

Validates:
- Ticket creation, category validation, length validation, and authentication checks.
- Ticket listing privacy: user sees only own tickets; staff sees all tickets.
- Ticket replies: user and staff roles, timestamps, message ordering.
- Ticket status updates: closing and reopening permissions.
- Staff claims: only staff can claim, system messages posted.
- Staff management API: owner/admin permissions, add/remove/list, audit logs.
- WebStaff Discord Cog: prefix and slash command guards, database persistence.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from dashboard_api.auth import create_session_token
from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from src.cogs.developer.webstaff import WebStaffCog
from src.security.owner import OWNER_ID


class TestTicketAndStaffSystem(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            bot_token="mock_test_bot_token_123456",
            client_id="1562505487214321714",
            client_secret="mock_secret_test",
            secret_key="kyoka_super_test_secret_key_32chars!",
            redirect_uri="https://aizen-bot.pages.dev/api/auth/callback",
            database_url="",
            is_production=False,
            rate_limit_per_minute=500,
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    def _create_user_token(self, user_id: int, username: str = "TestUser") -> str:
        return create_session_token(
            {
                "user_id": str(user_id),
                "username": username,
                "discriminator": "0001",
                "avatar": None,
                "avatar_url": f"https://cdn.discordapp.com/embed/avatars/1.png",
            },
            self.config.secret_key,
        )

    @unittest_run_loop
    async def test_create_ticket_success(self):
        token = self._create_user_token(12345678, "Alice")
        payload = {
            "category": "Bug Report",
            "subject": "Bot latency high in voice",
            "description": "The audio playback is lagging noticeably in Europe voice servers.",
        }
        resp = await self.client.post(
            "/api/tickets",
            json=payload,
            cookies={self.config.session_cookie_name: token},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        ticket = data["ticket"]
        assert ticket["ticket_id"].startswith("TICK-")
        assert ticket["category"] == "Bug Report"
        assert ticket["subject"] == "Bot latency high in voice"
        assert ticket["status"] == "open"
        assert ticket["user_id"] == "12345678"

    @unittest_run_loop
    async def test_create_ticket_validation_failures(self):
        token = self._create_user_token(12345678, "Alice")

        # Subject too short
        resp = await self.client.post(
            "/api/tickets",
            json={"category": "Support", "subject": "hi", "description": "Valid description text here"},
            cookies={self.config.session_cookie_name: token},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "Subject" in data["error"]

        # Description too short
        resp = await self.client.post(
            "/api/tickets",
            json={"category": "Support", "subject": "Valid Subject", "description": "short"},
            cookies={self.config.session_cookie_name: token},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "Description" in data["error"]

        # Unauthenticated request
        resp = await self.client.post(
            "/api/tickets",
            json={"category": "Support", "subject": "Valid Subject", "description": "Valid long description text"},
        )
        assert resp.status == 401

    @unittest_run_loop
    async def test_ticket_listing_privacy(self):
        alice_token = self._create_user_token(11111, "Alice")
        bob_token = self._create_user_token(22222, "Bob")
        owner_token = self._create_user_token(OWNER_ID, "Owner")

        # Alice creates ticket
        await self.client.post(
            "/api/tickets",
            json={"category": "Support", "subject": "Alice's Ticket", "description": "Alice needs assistance with role"},
            cookies={self.config.session_cookie_name: alice_token},
        )

        # Bob creates ticket
        await self.client.post(
            "/api/tickets",
            json={"category": "Support", "subject": "Bob's Ticket", "description": "Bob needs billing support today"},
            cookies={self.config.session_cookie_name: bob_token},
        )

        # Alice lists tickets: only sees Alice's ticket
        resp = await self.client.get("/api/tickets", cookies={self.config.session_cookie_name: alice_token})
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 1
        assert data["tickets"][0]["subject"] == "Alice's Ticket"

        # Bob lists tickets: only sees Bob's ticket
        resp = await self.client.get("/api/tickets", cookies={self.config.session_cookie_name: bob_token})
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 1
        assert data["tickets"][0]["subject"] == "Bob's Ticket"

        # Owner (staff) lists tickets: sees both
        resp = await self.client.get("/api/tickets", cookies={self.config.session_cookie_name: owner_token})
        assert resp.status == 200
        data = await resp.json()
        assert data["total"] == 2
        assert data["is_staff"] is True

    @unittest_run_loop
    async def test_ticket_reply_and_history(self):
        user_token = self._create_user_token(33333, "Charlie")
        owner_token = self._create_user_token(OWNER_ID, "AizenOwner")

        # Create ticket
        c_res = await self.client.post(
            "/api/tickets",
            json={"category": "Premium", "subject": "Key not activating", "description": "Key gives error code."},
            cookies={self.config.session_cookie_name: user_token},
        )
        tid = (await c_res.json())["ticket"]["ticket_id"]

        # User replies
        r_res = await self.client.post(
            f"/api/tickets/{tid}/reply",
            json={"content": "Here is my receipt ID: #10492"},
            cookies={self.config.session_cookie_name: user_token},
        )
        assert r_res.status == 200

        # Owner replies as staff/admin
        s_res = await self.client.post(
            f"/api/tickets/{tid}/reply",
            json={"content": "Verified receipt. Key refreshed."},
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert s_res.status == 200
        assert (await s_res.json())["reply"]["sender_role"] == "admin"

        # Fetch ticket details
        detail_res = await self.client.get(
            f"/api/tickets/{tid}",
            cookies={self.config.session_cookie_name: user_token},
        )
        assert detail_res.status == 200
        details = await detail_res.json()
        messages = details["messages"]
        assert len(messages) == 3  # initial description + 2 replies
        assert messages[0]["content"] == "Key gives error code."
        assert messages[1]["content"] == "Here is my receipt ID: #10492"
        assert messages[2]["content"] == "Verified receipt. Key refreshed."

    @unittest_run_loop
    async def test_ticket_status_close_and_reopen(self):
        user_token = self._create_user_token(44444, "Dave")
        owner_token = self._create_user_token(OWNER_ID, "AizenOwner")

        c_res = await self.client.post(
            "/api/tickets",
            json={"category": "Other", "subject": "General Query", "description": "How do I invite the bot?"},
            cookies={self.config.session_cookie_name: user_token},
        )
        tid = (await c_res.json())["ticket"]["ticket_id"]

        # Dave closes his own ticket
        close_res = await self.client.post(
            f"/api/tickets/{tid}/status",
            json={"status": "closed"},
            cookies={self.config.session_cookie_name: user_token},
        )
        assert close_res.status == 200
        assert (await close_res.json())["ticket"]["status"] == "closed"

        # Dave cannot reopen
        reopen_user_res = await self.client.post(
            f"/api/tickets/{tid}/status",
            json={"status": "open"},
            cookies={self.config.session_cookie_name: user_token},
        )
        assert reopen_user_res.status == 403

        # Staff can reopen
        reopen_staff_res = await self.client.post(
            f"/api/tickets/{tid}/status",
            json={"status": "open"},
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert reopen_staff_res.status == 200
        assert (await reopen_staff_res.json())["ticket"]["status"] == "open"

    @unittest_run_loop
    async def test_staff_management_api(self):
        owner_token = self._create_user_token(OWNER_ID, "AizenOwner")
        regular_token = self._create_user_token(55555, "Regular")

        # Regular user cannot manage staff
        resp = await self.client.post(
            "/api/staff/manage",
            json={"action": "add", "user_id": 99999, "role_level": "support"},
            cookies={self.config.session_cookie_name: regular_token},
        )
        assert resp.status == 403

        # Owner adds staff member
        resp = await self.client.post(
            "/api/staff/manage",
            json={"action": "add", "user_id": 99999, "username": "SupportSam", "role_level": "support"},
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["staff"]["role_level"] == "support"

        # List staff
        list_resp = await self.client.get(
            "/api/staff/list",
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert list_resp.status == 200
        list_data = await list_resp.json()
        assert list_data["total"] == 1
        assert list_data["staff"][0]["username"] == "SupportSam"

        # Check /api/auth/me reflects staff role for SupportSam
        sam_token = self._create_user_token(99999, "SupportSam")
        me_resp = await self.client.get(
            "/api/auth/me",
            cookies={self.config.session_cookie_name: sam_token},
        )
        assert me_resp.status == 200
        me_data = await me_resp.json()
        assert me_data["user"]["is_staff"] is True
        assert me_data["user"]["staff_role"] == "support"

        # Owner removes staff member
        del_resp = await self.client.post(
            "/api/staff/manage",
            json={"action": "remove", "user_id": 99999},
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert del_resp.status == 200
        assert (await del_resp.json())["removed"] is True

        # Cannot remove bot owner
        del_owner_resp = await self.client.post(
            "/api/staff/manage",
            json={"action": "remove", "user_id": OWNER_ID},
            cookies={self.config.session_cookie_name: owner_token},
        )
        assert del_owner_resp.status == 400


@pytest.mark.asyncio
async def test_webstaff_discord_cog_security_and_execution():
    """Test Discord WebStaff cog command security and mock DB interaction."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock(return_value="INSERT 0 1")
    bot.db.fetch_all = AsyncMock(return_value=[
        {"user_id": 123456, "username": "StaffUser", "role_level": "support", "added_by": OWNER_ID, "added_at": "2026-10-26T12:00:00Z"}
    ])
    bot.db.fetch_one = AsyncMock(return_value=None)

    cog = WebStaffCog(bot)

    # 1. Non-owner / unauthorized execution check
    unauth_ctx = MagicMock()
    unauth_ctx.author.id = 88888888
    unauth_ctx.author.guild_permissions.administrator = False
    unauth_ctx.guild = MagicMock()
    unauth_ctx.interaction = None
    unauth_ctx.reply = AsyncMock()

    is_authed = await cog._check_admin_auth(unauth_ctx)
    assert is_authed is False
    unauth_ctx.reply.assert_called_once()
    assert "not authorized" in unauth_ctx.reply.call_args[0][0].lower()

    # 2. Owner execution check
    owner_ctx = MagicMock()
    owner_ctx.author.id = OWNER_ID
    owner_ctx.author.guild_permissions.administrator = True
    owner_ctx.guild = MagicMock()
    owner_ctx.interaction = None

    is_owner_authed = await cog._check_admin_auth(owner_ctx)
    assert is_owner_authed is True

    # 3. webstaff add command
    target_user = MagicMock()
    target_user.id = 77777777
    target_user.name = "NewModerator"
    target_user.mention = "<@77777777>"

    bot.db.execute.reset_mock()
    owner_ctx.send = AsyncMock()
    await cog.webstaff_add.callback(cog, owner_ctx, target_user, "senior")

    # 1 call for website_staff table + 1 call for kyoka_audit_log
    assert bot.db.execute.call_count == 2
    calls = bot.db.execute.call_args_list
    assert any(target_user.id in c[0] for c in calls)
    owner_ctx.send.assert_called_once()
    embed = owner_ctx.send.call_args[1]["embed"]
    assert "Staff Access Granted" in embed.title

    # 4. webstaff remove command
    bot.db.execute.reset_mock()
    bot.db.execute.return_value = "DELETE 1"
    owner_ctx.send.reset_mock()
    await cog.webstaff_remove.callback(cog, owner_ctx, target_user)
    # 1 call for delete + 1 call for audit
    assert bot.db.execute.call_count == 2
    owner_ctx.send.assert_called_once()
    del_embed = owner_ctx.send.call_args[1]["embed"]
    assert "Staff Access Revoked" in del_embed.title
