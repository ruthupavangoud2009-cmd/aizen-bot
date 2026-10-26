from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import TYPE_CHECKING, Callable
import discord
from aiohttp import web

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Server")


class HealthServer:
    """Async web server for hosting health checks and real-time telemetry APIs."""

    def __init__(
        self,
        bot: KyokaBot | None = None,
        bot_getter: Callable[[], KyokaBot | None] | None = None,
    ) -> None:
        self._bot = bot
        self._bot_getter = bot_getter
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._setup_routes()

    @property
    def bot(self) -> KyokaBot | None:
        if self._bot_getter:
            return self._bot_getter()
        return self._bot

    @bot.setter
    def bot(self, value: KyokaBot | None) -> None:
        self._bot = value

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self._handle_home)
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/api/health", self._handle_health)
        self.app.router.add_get("/api/stats", self._handle_api_stats)
        self.app.router.add_get("/api/guilds", self._handle_api_guilds)
        self.app.router.add_get("/api/guilds/{id}", self._handle_api_guild)
        self.app.router.add_get("/api/guilds/{id}/antinuke", self._handle_api_antinuke_get)
        self.app.router.add_patch("/api/guilds/{id}/antinuke", self._handle_api_antinuke_patch)
        self.app.router.add_post("/api/guilds/{id}/test-event", self._handle_api_test_event)
        self.app.router.add_get("/api/commands", self._handle_api_commands)
        self.app.router.add_get("/api/music/{id}", self._handle_api_music)
        self.app.router.add_post("/api/music/{id}/control", self._handle_api_music_control)
        self.app.router.add_post("/api/music/{id}/play", self._handle_api_music_play)
        # CORS preflight for website (localhost + prod)
        self.app.router.add_options("/api/{tail:.*}", self._handle_options)
        self.app.router.add_options("/health", self._handle_options)

    async def _handle_options(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers=self._cors_headers())

    @staticmethod
    def _cors_headers() -> dict:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

    def _check_dashboard_auth(self, request: web.Request) -> bool:
        """Bearer-token guard for write endpoints (empty token = local dev, allow)."""
        expected = os.getenv("DASHBOARD_TOKEN", "").strip() or os.getenv("INTERNAL_API_SECRET", "").strip()
        if not expected:
            return True
        auth = request.headers.get("Authorization", "")
        return auth == f"Bearer {expected}"

    async def _handle_home(self, request: web.Request) -> web.Response:
        """Root endpoint returning basic status."""
        return web.Response(
            text="Kyoka Discord Bot is Online & Running 24/7!",
            content_type="text/plain",
            status=200,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Lightweight health check distinguishing process, DB pool, and Discord gateway."""
        bot = self.bot
        ws_ping = round(bot.latency * 1000) if (bot and bot.latency and not math.isnan(bot.latency)) else 0

        # Check DB pool connectivity safely without blocking
        db_connected = False
        if bot and hasattr(bot, "db") and getattr(bot.db, "pool", None):
            try:
                db_connected = not bot.db.pool._closed
            except Exception:
                db_connected = False

        # Lightweight process stats
        ram_mb = 0.0
        try:
            import psutil
            process = psutil.Process(os.getpid())
            ram_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass

        gateway_status = "connected" if (bot and bot.is_ready()) else ("connecting" if bot else "offline")
        overall_status = "healthy" if (gateway_status == "connected" and db_connected) else "degraded"

        data = {
            "status": overall_status,
            "bot": getattr(Config, "BOT_NAME", "Kyoka"),
            "service": "kyoka-discord-bot",
            "process": {
                "status": "online",
                "uptime_seconds": int((discord.utils.utcnow() - bot.start_time).total_seconds()) if (bot and hasattr(bot, "start_time")) else 0,
                "memory_mb": ram_mb,
            },
            "database": {
                "connected": db_connected,
                "engine": "PostgreSQL / Supabase",
            },
            "discord_gateway": {
                "status": gateway_status,
                "ping_ms": ws_ping,
                "guilds": len(bot.guilds) if bot else 0,
            },
            "guilds": len(bot.guilds) if bot else 0,
            "ping_ms": ws_ping,
        }
        return web.json_response(data, status=200, headers=self._cors_headers())

    async def _handle_api_stats(self, request: web.Request) -> web.Response:
        """Real-time bot telemetry metrics JSON API."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway not initialized"}, status=503)

        ws_ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
        total_members = sum(getattr(g, "member_count", 0) for g in bot.guilds)

        active_players = 0
        music_cog = bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            active_players = sum(1 for p in music_cog.controller.players.values() if p and p.is_connected)

        ram_mb = 0.0
        try:
            import os
            import psutil
            process = psutil.Process(os.getpid())
            ram_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass

        data = {
            "status": "online",
            "bot_name": Config.BOT_NAME,
            "version": getattr(Config, "VERSION", "2.4.0"),
            "latency_ms": ws_ping,
            "guilds": len(bot.guilds),
            "total_users": total_members,
            "active_audio_players": active_players,
            "ram_usage_mb": ram_mb,
            "loaded_cogs": list(bot.cogs.keys()),
            "total_commands": len(bot.commands),
            "uptime_seconds": int((discord.utils.utcnow() - bot.start_time).total_seconds()) if hasattr(bot, "start_time") else 0,
        }
        return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})

    async def _handle_api_guild(self, request: web.Request) -> web.Response:
        """Real-time guild telemetry and configuration."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)

        guild = bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found"}, status=404)

        prefix = bot.guild_mgr.get_prefix(guild.id)
        modlog_ch = bot.log_mgr.get_log_channel(guild, "mod")

        data = {
            "id": str(guild.id),
            "name": guild.name,
            "member_count": getattr(guild, "member_count", 0),
            "prefix": prefix,
            "modlog_channel_id": str(modlog_ch.id) if modlog_ch else None,
            "icon_url": str(guild.icon.url) if guild.icon else None,
        }
        return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})

    async def _handle_api_guilds(self, request: web.Request) -> web.Response:
        """Real guild list — every server the bot is actually in."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)
        guilds = [
            {
                "id": str(g.id),
                "name": g.name,
                "member_count": getattr(g, "member_count", 0) or 0,
                "icon_url": str(g.icon.url) if g.icon else None,
            }
            for g in bot.guilds
        ]
        return web.json_response({"guilds": guilds}, headers=self._cors_headers())

    async def _handle_api_antinuke_get(self, request: web.Request) -> web.Response:
        """Real antinuke state for a guild, straight from AntinukeManager memory."""
        bot = self.bot
        try:
            guild_id = int(request.match_info.get("id"))
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)
        if not bot.get_guild(guild_id):
            return web.json_response({"error": "Guild not found"}, status=404)

        from src.managers.antinuke_manager import PROTECTION_MODULES
        cfg = bot.antinuke_mgr.get_settings(guild_id)
        data = {
            "guild_id": str(guild_id),
            "enabled": bool(cfg.get("enabled", False)),
            "punishment": cfg.get("punishment", "ban"),
            "log_channel_id": str(cfg["log_channel_id"]) if cfg.get("log_channel_id") else None,
            "modules": {m: bool(cfg.get(f"{m}_protection", True)) for m in PROTECTION_MODULES},
        }
        return web.json_response(data, headers=self._cors_headers())

    async def _handle_api_antinuke_patch(self, request: web.Request) -> web.Response:
        """Apply antinuke changes for real — master switch, punishment, modules."""
        bot = self.bot
        try:
            guild_id = int(request.match_info.get("id"))
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)
        if not bot.get_guild(guild_id):
            return web.json_response({"error": "Guild not found"}, status=404)
        if not self._check_dashboard_auth(request):
            return web.json_response(
                {"error": "Unauthorized — Discord login required"}, status=401,
                headers=self._cors_headers(),
            )
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400,
                                     headers=self._cors_headers())

        from src.managers.antinuke_manager import PROTECTION_MODULES
        updates: dict = {}
        if "enabled" in body:
            updates["enabled"] = bool(body["enabled"])
        if "punishment" in body and str(body["punishment"]).lower() in ("ban", "kick", "quarantine", "strip_roles"):
            updates["punishment"] = str(body["punishment"]).lower()
        if isinstance(body.get("modules"), dict):
            for m in PROTECTION_MODULES:
                if m in body["modules"]:
                    updates[f"{m}_protection"] = bool(body["modules"][m])
        if not updates:
            return web.json_response({"error": "Nothing to update"}, status=400,
                                     headers=self._cors_headers())

        await bot.antinuke_mgr.update_settings(guild_id, **updates)
        return await self._handle_api_antinuke_get(request)

    async def _handle_api_commands(self, request: web.Request) -> web.Response:
        """Real command registry — every loaded prefix command with its help text."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)
        cmds = []
        for cmd in sorted(bot.commands, key=lambda c: c.qualified_name):
            if getattr(cmd, "hidden", False):
                continue
            cmds.append({
                "name": cmd.qualified_name,
                "help": (cmd.help or cmd.description or "No description yet.").strip().split("\n")[0][:160],
                "cog": cmd.cog_name or "General",
            })
        return web.json_response({"count": len(cmds), "commands": cmds}, headers=self._cors_headers())

    async def _handle_api_music(self, request: web.Request) -> web.Response:
        """Real-time audio streaming telemetry and queue state per guild."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers())

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers())

        music_cog = bot.get_cog("Music")
        if not music_cog or not hasattr(music_cog, "controller"):
            return web.json_response({
                "connected": False,
                "is_connected": False,
                "is_playing": False,
                "is_paused": False,
                "status": "idle",
                "current": None,
                "current_track": None,
                "queue": [],
                "queue_length": 0,
                "volume": 100,
                "loop_mode": "off",
            }, headers=self._cors_headers())

        player = music_cog.controller.get_player(guild_id)
        if not player or not player.is_connected:
            return web.json_response({
                "connected": False,
                "is_connected": False,
                "is_playing": False,
                "is_paused": False,
                "status": "idle",
                "current": None,
                "current_track": None,
                "queue": [],
                "queue_length": 0,
                "volume": 100,
                "loop_mode": "off",
            }, headers=self._cors_headers())

        current_track = None
        pos_sec = 0
        if player.current:
            if player.voice_client and hasattr(player.voice_client, "position"):
                pos_sec = max(0, int(player.voice_client.position / 1000))
            raw_dur = getattr(player.current, "duration", 0)
            dur_sec = int(raw_dur / 1000) if raw_dur > 1000 else int(raw_dur)
            current_track = {
                "title": player.current.title,
                "author": player.current.author or "Artist",
                "artist": player.current.author or "Artist",
                "duration": dur_sec,
                "position": pos_sec,
                "url": getattr(player.current, "uri", None) or player.current.url,
                "uri": getattr(player.current, "uri", None) or player.current.url,
                "requester": getattr(player.current, "requester", "Server Member"),
            }

        queue_tracks = []
        for idx, trk in enumerate(list(player.queue)[:30]):
            raw_d = getattr(trk, "duration", 0)
            d_sec = int(raw_d / 1000) if raw_d > 1000 else int(raw_d)
            queue_tracks.append({
                "id": f"trk_{idx}",
                "title": getattr(trk, "title", "Track"),
                "artist": getattr(trk, "author", "Artist"),
                "author": getattr(trk, "author", "Artist"),
                "duration": d_sec,
                "url": getattr(trk, "uri", "") or getattr(trk, "url", ""),
                "uri": getattr(trk, "uri", "") or getattr(trk, "url", ""),
                "requester": getattr(trk, "requester", None),
            })

        status = "playing" if player.is_playing else ("paused" if player.is_paused else "idle")
        vc_channel = getattr(player.voice_client, "channel", None) if player.voice_client else None

        data = {
            "connected": True,
            "is_connected": True,
            "is_playing": player.is_playing,
            "is_paused": player.is_paused,
            "status": status,
            "volume": int(player.volume * 100) if player.volume <= 1.5 else int(player.volume),
            "loop_mode": player.loop_mode,
            "is_247": getattr(player, "is_247", False),
            "queue_length": len(player.queue),
            "queue": queue_tracks,
            "current": current_track,
            "current_track": current_track,
            "voice_channel": {"id": str(vc_channel.id), "name": vc_channel.name} if vc_channel else None,
        }
        return web.json_response(data, headers=self._cors_headers())

    async def _handle_api_music_control(self, request: web.Request) -> web.Response:
        """Execute playback action on the live player (requires Bearer DASHBOARD_TOKEN)."""
        if not self._check_dashboard_auth(request):
            return web.json_response({"error": "Unauthorized — valid DASHBOARD_TOKEN required"}, status=401, headers=self._cors_headers())

        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers())

        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers())

        music_cog = bot.get_cog("Music")
        if not music_cog or not hasattr(music_cog, "controller"):
            return web.json_response({"error": "Music subsystem unavailable"}, status=503, headers=self._cors_headers())

        try:
            body = await request.json()
        except Exception:
            body = {}

        action = str(body.get("action", "")).lower().strip()
        value = body.get("value")
        player = music_cog.controller.get_player(guild_id)

        if not player or not player.is_connected:
            return web.json_response({"error": "No active audio player connected for this guild. Join a voice channel and start playback with +play first."}, status=404, headers=self._cors_headers())

        try:
            if action == "pause":
                player.pause()
            elif action == "resume":
                player.resume()
            elif action == "skip":
                await player.skip()
            elif action == "stop":
                await player.stop()
            elif action == "volume":
                vol = max(0, min(150, int(value or 100)))
                player.set_volume(vol)
            elif action == "loop":
                mode = str(value).lower().strip() if value else ("track" if player.loop_mode == "off" else ("queue" if player.loop_mode == "track" else "off"))
                player.set_loop_mode(mode)
            elif action == "shuffle":
                await player.shuffle_queue()
            elif action == "seek":
                seek_ms = int(value or 0) * 1000
                if player.voice_client and hasattr(player.voice_client, "seek"):
                    await player.voice_client.seek(seek_ms)
            elif action == "leave":
                await player.stop()
                if player.voice_client:
                    await player.voice_client.disconnect(force=True)
            else:
                return web.json_response({"error": f"Unknown music control action: '{action}'"}, status=400, headers=self._cors_headers())

            return await self._handle_api_music(request)
        except Exception as e:
            logger.error(f"Error executing music action '{action}' for guild {guild_id}: {e}", exc_info=e)
            return web.json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def _handle_api_music_play(self, request: web.Request) -> web.Response:
        """Enqueue or play a track from dashboard (requires Bearer DASHBOARD_TOKEN)."""
        if not self._check_dashboard_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401, headers=self._cors_headers())

        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers())

        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers())

        music_cog = bot.get_cog("Music")
        if not music_cog or not hasattr(music_cog, "controller"):
            return web.json_response({"error": "Music subsystem unavailable"}, status=503, headers=self._cors_headers())

        try:
            body = await request.json()
        except Exception:
            body = {}

        query = str(body.get("query", "")).strip()
        if not query:
            return web.json_response({"error": "Track query or URL required"}, status=400, headers=self._cors_headers())

        player = music_cog.controller.get_player(guild_id)
        if not player or not player.is_connected:
            return web.json_response({"error": "Bot is not connected to a voice channel in this server."}, status=400, headers=self._cors_headers())

        # Search track via Wavelink / Lavalink
        try:
            import wavelink
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                return web.json_response({"error": f"No tracks found matching '{query}'"}, status=404, headers=self._cors_headers())

            track = tracks[0]
            track.requester = str(body.get("requester", "Dashboard User"))
            if not player.is_playing:
                await player.play_track(track)
                msg = f"Started playing '{track.title}'."
            else:
                player.queue.append(track)
                msg = f"Enqueued '{track.title}' (#{len(player.queue)} in queue)."

            return web.json_response({"success": True, "message": msg, "track": {"title": track.title, "author": track.author}}, headers=self._cors_headers())
        except Exception as e:
            logger.error(f"Failed to play track for guild {guild_id}: {e}", exc_info=e)
            return web.json_response({"error": str(e)}, status=500, headers=self._cors_headers())

    async def _handle_api_test_event(self, request: web.Request) -> web.Response:
        """Trigger test welcome/leave event simulation or real dispatch to Discord channel."""
        if not self._check_dashboard_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401, headers=self._cors_headers())

        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers())

        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers())

        guild = bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found on this bot instance"}, status=404, headers=self._cors_headers())

        try:
            body = await request.json()
        except Exception:
            body = {}

        event_type = str(body.get("event_type", "welcome")).lower().strip()
        channel_id = body.get("channel_id")
        send_to_discord = bool(body.get("send_to_discord", False))

        target_ch = None
        if channel_id:
            try:
                target_ch = guild.get_channel(int(channel_id))
            except Exception:
                target_ch = None

        events_cog = bot.get_cog("Events")
        if not events_cog or not hasattr(events_cog, "_send_event_card"):
            return web.json_response({"error": "Events cog not available"}, status=503, headers=self._cors_headers())

        # Invalidate event manager cache so latest DB changes apply immediately
        if hasattr(bot, "event_mgr"):
            bot.event_mgr.invalidate_cache(guild_id, event_type)

        test_member = guild.me
        if send_to_discord and target_ch:
            success, err = await events_cog._send_event_card(event_type, guild, test_member, test_channel=target_ch)
            return web.json_response({
                "success": success,
                "sent_to_channel": bool(target_ch),
                "channel_id": str(target_ch.id) if target_ch else None,
                "channel_name": target_ch.name if target_ch else None,
                "error": err,
                "message": f"Test {event_type} card dispatched to #{target_ch.name}." if success else f"Failed to send: {err}"
            }, headers=self._cors_headers())
        else:
            return web.json_response({
                "success": True,
                "preview_only": True,
                "event_type": event_type,
                "guild_name": guild.name,
                "member_count": getattr(guild, "member_count", 0),
                "target_channel": target_ch.name if target_ch else None,
            }, headers=self._cors_headers())

    async def _keepalive_loop(self, port: int) -> None:
        """Self-ping loop every 8 minutes to prevent Render Free tier spin-down."""
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url and "cicada-3301" in render_url:
            render_url = None

        target_url = f"{render_url.rstrip('/')}/health" if render_url else f"http://127.0.0.1:{port}/health"
        logger.info(f"Initialized 24/7 keep-alive pinger for: {target_url}")

        await asyncio.sleep(60)

        while True:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        logger.debug(f"Render keep-alive ping status: {resp.status}")
            except Exception as e:
                logger.debug(f"Render keep-alive notice: {e}")
            await asyncio.sleep(480)

    async def start(self) -> None:
        """Start the async HTTP server with automatic port fallback."""
        base_port = int(os.getenv("PORT", 8080))
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        for port in [base_port, base_port + 1, base_port + 2, 0]:
            try:
                site = web.TCPSite(self.runner, "0.0.0.0", port)
                await site.start()
                actual_port = port if port != 0 else getattr(site._server.sockets[0], "getsockname", lambda: (0, 0))()[1]
                logger.info(f"Keep-Alive Health Server listening on http://0.0.0.0:{actual_port}")
                self._keepalive_task = asyncio.create_task(self._keepalive_loop(actual_port))
                return
            except OSError as e:
                logger.warning(f"Port {port} is in use ({e}). Trying next port...")
        logger.error("Could not bind HealthServer to any open port.")

    async def stop(self) -> None:
        """Gracefully stop the web server."""
        if hasattr(self, "_keepalive_task") and self._keepalive_task:
            self._keepalive_task.cancel()
        if self.runner:
            await self.runner.cleanup()
            logger.info("Keep-Alive Health Server stopped.")
