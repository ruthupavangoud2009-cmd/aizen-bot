"""Unit and integration tests for all 14 multi-section dashboard features and test event simulation."""
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token


class TestDashboardAllSections(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/7q4tn6dA6V",
            secret_key="test_sections_secret_key_32_chars_long",
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
                }
            ],
        }
        token = create_session_token(session_data, self.config.secret_key)
        return {"Authorization": f"Bearer {token}"}

    async def test_get_settings_contains_all_18_sections(self):
        """Verify that get_settings provides data for all 18 server feature sections."""
        headers = self._create_auth_headers("1001")
        resp = await self.client.get("/api/guilds/1001/settings", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        expected_sections = [
            "general",
            "welcome_leave",
            "verification",
            "moderation",
            "antinuke",
            "logs",
            "tickets",
            "leveling",
            "giveaways",
            "reaction_roles",
            "music",
            "ai",
            "prefix_commands",
            "utilities",
            "premium",
            "embeds",
            "roles_channels",
            "diagnostics",
            "roles_utilities",
        ]
        for section in expected_sections:
            self.assertIn(section, data, f"Section {section} missing in guild settings")

    async def test_update_welcome_leave_settings(self):
        """Verify welcome and leave event configuration saves and updates."""
        headers = self._create_auth_headers("1001")
        update_payload = {
            "welcome_leave": {
                "welcome_enabled": True,
                "welcome_channel_id": "123456789012345678",
                "welcome_message": "Welcome {user} to the sanctuary of {server}!",
                "leave_enabled": False,
                "dm_enabled": True,
            }
        }
        resp = await self.client.patch("/api/guilds/1001/settings", json=update_payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        wl = data["settings"]["welcome_leave"]
        self.assertEqual(wl["welcome_channel_id"], "123456789012345678")
        self.assertEqual(wl["welcome_message"], "Welcome {user} to the sanctuary of {server}!")
        self.assertFalse(wl["leave_enabled"])
        self.assertTrue(wl["dm_enabled"])

    async def test_update_tickets_settings(self):
        """Verify ticket panel configuration saves and updates."""
        headers = self._create_auth_headers("1001")
        update_payload = {
            "tickets": {
                "panel_name": "VIP Concierge",
                "channel_id": "123456789012345678",
                "button_label": "Open VIP Inquiry",
                "button_emoji": "💎",
                "naming_format": "vip-{count}",
            }
        }
        resp = await self.client.patch("/api/guilds/1001/settings", json=update_payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        tk = data["settings"]["tickets"]
        self.assertEqual(tk["panel_name"], "VIP Concierge")
        self.assertEqual(tk["button_label"], "Open VIP Inquiry")
        self.assertEqual(tk["button_emoji"], "💎")

    async def test_update_roles_utilities_settings(self):
        """Verify autoroles and utilities configuration saves."""
        headers = self._create_auth_headers("1001")
        update_payload = {
            "roles_utilities": {
                "role_id": "111222333444555666",
                "human_role_id": "222333444555666777",
                "bot_role_id": "333444555666777888",
                "ghostping_enabled": True,
                "ghostping_channel_id": "444555666777888999",
            }
        }
        resp = await self.client.patch("/api/guilds/1001/settings", json=update_payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        ru = data["settings"]["roles_utilities"]
        self.assertEqual(ru["role_id"], "111222333444555666")
        self.assertEqual(ru["human_role_id"], "222333444555666777")
        self.assertTrue(ru["ghostping_enabled"])

    async def test_safe_test_event_simulation(self):
        """Verify test event generates simulation without live broadcast."""
        headers = self._create_auth_headers("1001")
        payload = {"event_type": "welcome"}
        resp = await self.client.post("/api/guilds/1001/test-event", json=payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "welcome")
        self.assertIn("@KyokaMember", data["simulated_message"])
        self.assertIn("Safe preview", data["note"])

    async def test_update_verification_settings(self):
        """Verify verification gate settings validation and persistence."""
        headers = self._create_auth_headers("1001")
        payload = {
            "verification": {
                "enabled": True,
                "role_id": "999888777666555444",
                "unverified_role_id": "111222333444555666",
                "channel_id": "888777666555444333",
                "log_channel_id": "777666555444333222",
                "method": "captcha",
                "timeout_seconds": 600,
                "max_retries": 5,
                "min_account_age_days": 7,
            }
        }
        resp = await self.client.patch("/api/guilds/1001/settings", json=payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        v = data["settings"]["verification"]
        self.assertTrue(v["enabled"])
        self.assertEqual(v["role_id"], "999888777666555444")
        self.assertEqual(v["method"], "captcha")
        self.assertEqual(v["timeout_seconds"], 600)
        self.assertEqual(v["min_account_age_days"], 7)

    async def test_update_utilities_and_branding_settings(self):
        """Verify sticky messages, reminders, and custom embed branding updates."""
        headers = self._create_auth_headers("1001")
        payload = {
            "utilities": {
                "sticky_enabled": True,
                "sticky_channel_id": "555666777888999000",
                "sticky_message": "Rules reminder: Be respectful in all channels.",
                "afk_notify": False,
                "reminders_enabled": True,
            },
            "embeds": {
                "primary_color": "#8B5CF6",
                "footer_text": "Aizen Sanctuary • Kyoka 3.0",
                "thumbnail_url": "https://example.com/thumb.png",
            },
        }
        resp = await self.client.patch("/api/guilds/1001/settings", json=payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        ut = data["settings"]["utilities"]
        self.assertTrue(ut["sticky_enabled"])
        self.assertEqual(ut["sticky_channel_id"], "555666777888999000")
        self.assertFalse(ut["afk_notify"])
        em = data["settings"]["embeds"]
        self.assertEqual(em["primary_color"], "#8B5CF6")
        self.assertEqual(em["footer_text"], "Aizen Sanctuary • Kyoka 3.0")

    async def test_wizard_get_save_and_apply_flow(self):
        """Verify the setup wizard draft save, progress resume, and atomic apply lifecycle."""
        headers = self._create_auth_headers("1001")

        # 1. Fetch initial wizard state
        resp_get = await self.client.get("/api/guilds/1001/wizard", headers=headers)
        self.assertEqual(resp_get.status, 200)
        initial_data = await resp_get.json()
        self.assertEqual(initial_data["guild_id"], "1001")
        self.assertIn("wizard_state", initial_data)

        # 2. Save draft progress (e.g. step 4)
        draft_payload = {
            "current_step": 4,
            "draft": {
                "welcome": {
                    "enabled": True,
                    "channel_id": "123456789012345678",
                    "message": "Welcome {user} to the citadel!",
                },
                "verification": {
                    "enabled": True,
                    "channel_id": "234567890123456789",
                    "role_id": "345678901234567890",
                    "method": "button",
                },
                "security": {
                    "antinuke_enabled": True,
                    "punishment": "strip_roles",
                    "automod_spam": True,
                },
            },
        }
        resp_save = await self.client.post("/api/guilds/1001/wizard/save", json=draft_payload, headers=headers)
        self.assertEqual(resp_save.status, 200)
        save_data = await resp_save.json()
        self.assertTrue(save_data["success"])
        self.assertEqual(save_data["state"]["current_step"], 4)

        # Verify draft was persisted in state
        resp_check = await self.client.get("/api/guilds/1001/wizard", headers=headers)
        check_data = await resp_check.json()
        self.assertEqual(check_data["wizard_state"]["current_step"], 4)
        self.assertEqual(check_data["wizard_state"]["draft"]["welcome"]["channel_id"], "123456789012345678")

        # 3. Apply wizard configuration atomically to live bot tables
        resp_apply = await self.client.post("/api/guilds/1001/wizard/apply", json=draft_payload, headers=headers)
        self.assertEqual(resp_apply.status, 200)
        apply_data = await resp_apply.json()
        self.assertTrue(apply_data["success"])
        self.assertIn("welcome", apply_data["applied_sections"])
        self.assertIn("verification", apply_data["applied_sections"])
        self.assertTrue(apply_data["state"]["is_completed"])

        # 4. Verify live guild settings now reflect the applied wizard configurations
        resp_live = await self.client.get("/api/guilds/1001/settings", headers=headers)
        live_settings = await resp_live.json()
        self.assertEqual(live_settings["welcome_leave"]["welcome_channel_id"], "123456789012345678")
        self.assertEqual(live_settings["welcome_leave"]["welcome_message"], "Welcome {user} to the citadel!")
        self.assertTrue(live_settings["verification"]["enabled"])
        self.assertEqual(live_settings["verification"]["role_id"], "345678901234567890")
        self.assertTrue(live_settings["antinuke"]["enabled"])

    async def test_wizard_unauthorized_access_fails(self):
        """Verify unauthenticated or unauthorized users are blocked from wizard endpoints."""
        # No auth header -> 401
        resp = await self.client.get("/api/guilds/1001/wizard")
        self.assertEqual(resp.status, 401)

        # Auth for guild 1001 attempting to access guild 2002 -> 403
        headers = self._create_auth_headers("1001")
        resp_cross = await self.client.get("/api/guilds/2002/wizard", headers=headers)
        self.assertEqual(resp_cross.status, 403)

