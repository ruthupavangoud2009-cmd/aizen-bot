"""Unit and integration tests for Music Studio and Premium Entitlement system."""
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web
from dashboard_api.config import DashboardConfig
from dashboard_api.database import MockDatabaseAdapter
from dashboard_api.server import create_app
from dashboard_api.auth import create_session_token


class TestDashboardMusicAndPremium(AioHTTPTestCase):
    async def get_application(self) -> web.Application:
        self.config = DashboardConfig(
            client_id="test_client_id",
            client_secret="test_client_secret",
            bot_token="test_bot_token",
            redirect_uri="http://localhost:8080/api/auth/callback",
            bot_invite_url="https://discord.com/oauth2/authorize?client_id=123",
            support_server_url="https://discord.gg/kyoka",
            secret_key="test_music_premium_secret_key_32_chars_ok",
            is_production=False,
            database_url="",
        )
        self.db = MockDatabaseAdapter()
        app = create_app(config=self.config, db=self.db, serve_website=False)
        return app

    def _create_auth_headers(self, guild_id: str = "1001", user_id: str = "999888777") -> dict:
        session_data = {
            "user_id": user_id,
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

    # ==========================================
    # PHASE 5: MUSIC STUDIO TESTS
    # ==========================================

    async def test_music_playback_auth_and_isolation(self):
        """Verify unauthenticated and cross-server requests to Music Studio are blocked."""
        # 1. No auth -> 401
        resp = await self.client.get("/api/guilds/1001/music/playback")
        self.assertEqual(resp.status, 401)

        # 2. Auth for 1001 trying to access 2002 -> 403
        headers = self._create_auth_headers("1001")
        resp_cross = await self.client.get("/api/guilds/2002/music/playback", headers=headers)
        self.assertEqual(resp_cross.status, 403)

    async def test_music_playback_get_state(self):
        """Verify retrieval of current playback state."""
        headers = self._create_auth_headers("1001")
        resp = await self.client.get("/api/guilds/1001/music/playback", headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data["success"])
        playback = data["playback"]
        self.assertIn("state", playback)
        self.assertIn("volume", playback)
        self.assertIn("loop_mode", playback)
        self.assertIn("is_connected", playback)
        self.assertIn("track", playback)

    async def test_music_playback_controls(self):
        """Verify play, pause, volume, seek, loop, and shuffle controls."""
        headers = self._create_auth_headers("1001")

        # 1. Pause
        resp_pause = await self.client.post("/api/guilds/1001/music/playback", json={"action": "pause"}, headers=headers)
        self.assertEqual(resp_pause.status, 200)
        data_pause = await resp_pause.json()
        self.assertEqual(data_pause["playback"]["state"], "paused")

        # 2. Resume
        resp_resume = await self.client.post("/api/guilds/1001/music/playback", json={"action": "resume"}, headers=headers)
        self.assertEqual(resp_resume.status, 200)
        data_resume = await resp_resume.json()
        self.assertEqual(data_resume["playback"]["state"], "playing")

        # 3. Volume within bounds (0-150)
        resp_vol = await self.client.post("/api/guilds/1001/music/playback", json={"action": "volume", "volume": 65}, headers=headers)
        self.assertEqual(resp_vol.status, 200)
        data_vol = await resp_vol.json()
        self.assertEqual(data_vol["playback"]["volume"], 65)

        # 4. Volume out of bounds -> 400
        resp_bad_vol = await self.client.post("/api/guilds/1001/music/playback", json={"action": "volume", "volume": 250}, headers=headers)
        self.assertEqual(resp_bad_vol.status, 400)

        # 5. Seek with seconds
        resp_seek_sec = await self.client.post("/api/guilds/1001/music/playback", json={"action": "seek", "position_seconds": 45}, headers=headers)
        self.assertEqual(resp_seek_sec.status, 200)
        data_seek = await resp_seek_sec.json()
        self.assertEqual(data_seek["playback"]["position"], 45)

        # 6. Seek with formatted timestamp string (e.g. '1:35' -> 95 seconds)
        resp_seek_str = await self.client.post("/api/guilds/1001/music/playback", json={"action": "seek", "timestamp": "1:35"}, headers=headers)
        self.assertEqual(resp_seek_str.status, 200)
        data_seek_str = await resp_seek_str.json()
        self.assertEqual(data_seek_str["playback"]["position"], 95)

        # 7. Invalid timestamp -> 400
        resp_bad_ts = await self.client.post("/api/guilds/1001/music/playback", json={"action": "seek", "timestamp": "invalid:time:format"}, headers=headers)
        self.assertEqual(resp_bad_ts.status, 400)

        # 8. Loop mode (off / track / queue)
        resp_loop = await self.client.post("/api/guilds/1001/music/playback", json={"action": "loop", "mode": "track"}, headers=headers)
        self.assertEqual(resp_loop.status, 200)
        data_loop = await resp_loop.json()
        self.assertEqual(data_loop["playback"]["loop_mode"], "track")

        # 9. Shuffle
        resp_shuffle = await self.client.post("/api/guilds/1001/music/playback", json={"action": "shuffle"}, headers=headers)
        self.assertEqual(resp_shuffle.status, 200)

        # 10. Voice channel join and leave
        resp_join = await self.client.post("/api/guilds/1001/music/playback", json={"action": "join", "channel_id": "999888111"}, headers=headers)
        self.assertEqual(resp_join.status, 200)
        self.assertTrue((await resp_join.json())["playback"]["is_connected"])

        resp_leave = await self.client.post("/api/guilds/1001/music/playback", json={"action": "leave"}, headers=headers)
        self.assertEqual(resp_leave.status, 200)
        self.assertFalse((await resp_leave.json())["playback"]["is_connected"])

    async def test_music_queue_and_search(self):
        """Verify queue manipulation and search functionality."""
        headers = self._create_auth_headers("1001")

        # 1. Search tracks
        resp_search = await self.client.get("/api/guilds/1001/music/search?q=Aizen+Theme", headers=headers)
        self.assertEqual(resp_search.status, 200)
        search_data = await resp_search.json()
        self.assertTrue(search_data["success"])
        self.assertGreater(len(search_data["results"]), 0)
        track_to_add = search_data["results"][0]

        # 2. Add track to queue
        resp_add = await self.client.post("/api/guilds/1001/music/queue", json={
            "title": track_to_add["title"],
            "artist": track_to_add["artist"],
            "duration": track_to_add["duration"],
            "url": track_to_add.get("url", "https://youtube.com/watch?v=mock"),
        }, headers=headers)
        self.assertEqual(resp_add.status, 200)
        add_data = await resp_add.json()
        self.assertTrue(add_data["success"])

        # 3. Fetch queue
        resp_q = await self.client.get("/api/guilds/1001/music/queue", headers=headers)
        self.assertEqual(resp_q.status, 200)
        q_data = await resp_q.json()
        self.assertTrue(q_data["success"])
        self.assertGreater(q_data["total_tracks"], 0)

        # 4. Remove single track
        first_track_id = q_data["queue"][0]["id"]
        resp_del_track = await self.client.delete(f"/api/guilds/1001/music/queue?track_id={first_track_id}", headers=headers)
        self.assertEqual(resp_del_track.status, 200)

        # 5. Clear all queue
        resp_clear = await self.client.delete("/api/guilds/1001/music/queue?all=true", headers=headers)
        self.assertEqual(resp_clear.status, 200)
        clear_data = await resp_clear.json()
        self.assertEqual(clear_data["total_tracks"], 0)

    # ==========================================
    # PHASE 6: PREMIUM ENTITLEMENT TESTS
    # ==========================================

    async def test_premium_status_and_license_redemption(self):
        """Verify premium status check and license key activation."""
        headers_1001 = self._create_auth_headers("1001")
        headers_1002 = self._create_auth_headers("1002")

        # 1. Guild 1001 has default mock premium (pro)
        resp_prem_1 = await self.client.get("/api/guilds/1001/premium", headers=headers_1001)
        self.assertEqual(resp_prem_1.status, 200)
        prem_1_data = await resp_prem_1.json()
        self.assertTrue(prem_1_data["is_premium"])
        self.assertEqual(prem_1_data["tier"], "pro")

        # 2. Guild 1002 is on free tier initially
        resp_prem_2 = await self.client.get("/api/guilds/1002/premium", headers=headers_1002)
        self.assertEqual(resp_prem_2.status, 200)
        prem_2_data = await resp_prem_2.json()
        self.assertFalse(prem_2_data["is_premium"])
        self.assertEqual(prem_2_data["tier"], "free")

        # 3. Redeem invalid key -> failure
        resp_bad_key = await self.client.post("/api/guilds/1002/premium/redeem", json={"license_key": "BOGUS-KEY-XYZ"}, headers=headers_1002)
        self.assertEqual(resp_bad_key.status, 400)
        bad_data = await resp_bad_key.json()
        self.assertFalse(bad_data["success"])

        # 4. Redeem valid PRO license key on Guild 1002
        valid_key = "KYOKA-PRO-1002-LIFETIME"
        resp_redeem = await self.client.post("/api/guilds/1002/premium/redeem", json={"license_key": valid_key}, headers=headers_1002)
        self.assertEqual(resp_redeem.status, 200)
        redeem_data = await resp_redeem.json()
        self.assertTrue(redeem_data["success"])
        self.assertEqual(redeem_data["tier"], "pro")

        # 5. Check Guild 1002 status now
        resp_prem_2_after = await self.client.get("/api/guilds/1002/premium", headers=headers_1002)
        self.assertEqual(resp_prem_2_after.status, 200)
        prem_2_after_data = await resp_prem_2_after.json()
        self.assertTrue(prem_2_after_data["is_premium"])
        self.assertEqual(prem_2_after_data["tier"], "pro")

    async def test_premium_feature_enforcement_on_settings(self):
        """Verify server-side protection prevents non-premium guilds from enabling premium features."""
        # Guild 9999 is free tier
        headers_free = self._create_auth_headers("9999")

        # Attempt to activate 24/7 Music mode without premium
        lock_attempt = {
            "music": {
                "is_247": True,
            }
        }
        resp_lock = await self.client.patch("/api/guilds/9999/settings", json=lock_attempt, headers=headers_free)
        self.assertEqual(resp_lock.status, 403)
        lock_data = await resp_lock.json()
        self.assertIn("error", lock_data)
        self.assertIn("exclusive Kyoka Premium feature", lock_data["error"])

        # Redeem pro key for guild 9999
        await self.client.post("/api/guilds/9999/premium/redeem", json={"license_key": "KYOKA-PRO-9999"}, headers=headers_free)

        # Attempt to activate 24/7 Music mode again with premium active -> succeeds!
        resp_allow = await self.client.patch("/api/guilds/9999/settings", json=lock_attempt, headers=headers_free)
        self.assertEqual(resp_allow.status, 200)
        allow_data = await resp_allow.json()
        self.assertTrue(allow_data["success"])
        self.assertTrue(allow_data["settings"]["music"]["is_247"])
