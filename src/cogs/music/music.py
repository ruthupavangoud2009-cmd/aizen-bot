from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.music._controller import MusicController
from src.cogs.music._views import MusicControlView
from src.cogs.music._analytics import MusicAnalytics
from src.cogs.music._agent import MusicAgent
from src.cogs.music._commands.play import execute_play
from src.cogs.music._commands.pause import execute_pause, execute_resume
from src.cogs.music._commands.skip import execute_skip
from src.cogs.music._commands.stop import execute_stop
from src.cogs.music._commands.queue import execute_queue
from src.cogs.music._commands.nowplaying import execute_nowplaying
from src.cogs.music._commands.autoplay import execute_autoplay
from src.cogs.music._commands.controls import (
    execute_loop,
    execute_shuffle,
    execute_clear,
    execute_volume,
    execute_remove,
    execute_jump,
    execute_stay,
)
from src.cogs.music._commands.playlist import handle_playlist, handle_like, handle_unlike

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music")


class Music(commands.Cog):
    """High-Performance Native Discord Audio & Studio Music Engine."""
    category: str = "Music"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Preserve active controller and players across hot-reloads
        if hasattr(bot, "_music_controller") and bot._music_controller:
            self.controller = bot._music_controller
        else:
            self.controller = MusicController(bot)
            bot._music_controller = self.controller

        self.analytics = MusicAnalytics(bot)
        self.agent = MusicAgent(bot, self)
        bot._music_agent = self.agent
        # Register persistent view for button interactions
        self.bot.add_view(MusicControlView(bot, None))

    async def _connect_lavalink(self) -> None:
        """Wait for bot login and connect to Lavalink node."""
        while not self.bot.is_ready():
            await asyncio.sleep(1)
        from src.core.lavalink import connect_lavalink_node
        try:
            node = await connect_lavalink_node(self.bot, inactive_player_timeout=300)
            logger.info(f"Connected to Lavalink Node at {node.uri} (status={node.status})")
        except Exception as e:
            logger.error(f"Failed to connect to Lavalink node: {e}")

    async def _load_247_cache(self) -> None:
        """Load persistent 24/7 guild state from database."""
        while not self.bot.is_ready():
            await asyncio.sleep(1)
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                rows = await self.bot.db.fetch_all("SELECT guild_id FROM guild_music_247 WHERE is_247 = TRUE;")
                self.controller._247_cache = {int(r["guild_id"]) for r in rows}
                logger.info(f"Loaded {len(self.controller._247_cache)} 24/7 music guild(s) into memory.")
            except Exception as e:
                logger.debug(f"Notice loading 24/7 music state: {e}")

    async def cog_load(self) -> None:
        """Schedule Lavalink connection upon bot readiness if not already connected."""
        import wavelink
        has_nodes = False
        try:
            # `Pool.nodes` is the public accessor. The internal mapping is name
            # mangled (`_Pool__nodes`), so the previous `Pool._nodes` check never
            # matched and a duplicate node was created on every cog load.
            for node in wavelink.Pool.nodes.values():
                if node.status == wavelink.NodeStatus.CONNECTED:
                    has_nodes = True
                    break
        except Exception:
            pass

        if not has_nodes:
            asyncio.create_task(self._connect_lavalink())
        asyncio.create_task(self._load_247_cache())

    async def cog_unload(self) -> None:
        """Close Lavalink node pool only on bot shutdown, preserving active streams during hot-reload."""
        if hasattr(self, "agent") and self.agent:
            self.agent.cog_unload()
        if getattr(self.bot, "_is_shutting_down", False):
            import wavelink
            try:
                await wavelink.Pool.close()
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: Any) -> None:
        """Invoked when Lavalink successfully begins streaming audio to Discord VC."""
        player_obj = getattr(payload, "player", None)
        title = None
        if player_obj and player_obj.guild:
            player = self.controller.get_player(player_obj.guild.id)
            if player and player.current:
                title = player.current.title
        if not title or title.lower() in ("unknown", "unknown title"):
            track = getattr(payload, "track", None)
            title = getattr(track, "title", "Unknown")
        logger.info(f"Lavalink started streaming: '{title}'")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: Any) -> None:
        """Invoked when Lavalink encounters an exception during audio playback."""
        track = getattr(payload, "track", None)
        title = getattr(track, "title", "Unknown")
        exception = getattr(payload, "exception", None)
        logger.error(f"Lavalink Track Exception for '{title}': {exception}")
        player_obj = getattr(payload, "player", None)
        guild_id = player_obj.guild.id if player_obj and player_obj.guild else None
        if hasattr(self.bot, "sentinel") and self.bot.sentinel:
            from src.sentinel.models import SubsystemType, IncidentSeverity
            self.bot.sentinel.record_incident(
                SubsystemType.MUSIC,
                IncidentSeverity.WARNING,
                "Lavalink Track Exception",
                f"Track '{title}': {exception}",
                action_taken="Advanced queue to next available stream",
                resolved=True,
                guild_id=guild_id,
            )
        if player_obj and player_obj.guild:
            player = self.controller.get_player(player_obj.guild.id)
            if player and hasattr(player, "on_track_end"):
                await player.on_track_end(reason="loadFailed")

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: Any) -> None:
        """Invoked when Lavalink player is stuck."""
        track = getattr(payload, "track", None)
        title = getattr(track, "title", "Unknown")
        logger.warning(f"Lavalink Track Stuck for '{title}'")
        player_obj = getattr(payload, "player", None)
        guild_id = player_obj.guild.id if player_obj and player_obj.guild else None
        if hasattr(self.bot, "sentinel") and self.bot.sentinel:
            from src.sentinel.models import SubsystemType, IncidentSeverity
            self.bot.sentinel.record_incident(
                SubsystemType.MUSIC,
                IncidentSeverity.WARNING,
                "Lavalink Track Stuck",
                f"Playback buffer stalled for '{title}'",
                action_taken="Force terminated stuck track to unblock queue",
                resolved=True,
                guild_id=guild_id,
            )
        if player_obj and player_obj.guild:
            player = self.controller.get_player(player_obj.guild.id)
            if player and hasattr(player, "on_track_end"):
                await player.on_track_end(reason="loadFailed")

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, node: Any, disconnected: Any) -> None:
        """Invoked when Lavalink node drops connection."""
        node_id = getattr(node, "identifier", "default")
        logger.warning(f"Lavalink node closed: {node_id}")
        if hasattr(self, "agent") and self.agent:
            asyncio.create_task(self.agent.heal_node())

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: Any) -> None:
        """Handle track completion: loop modes, queue popping, and smart autoplay."""
        player_obj = getattr(payload, "player", None)
        if not player_obj or not player_obj.guild:
            return
        reason = getattr(payload, "reason", "finished")
        if str(reason).lower() in ("replaced", "cleanup"):
            return
        player = self.controller.get_player(player_obj.guild.id)
        if player and hasattr(player, "on_track_end"):
            await player.on_track_end(reason=str(reason))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice channel disconnects, empty VC timeouts, and 24/7 pause/resume."""
        # ignore state updates where channel did not change (mute/unmute/deafen/stream)
        if before.channel == after.channel:
            return

        # Resolve bot user ID safely without raising NoneType error
        bot_user_id = self.bot.user.id if (self.bot and self.bot.user) else getattr(self.bot, "application_id", None)

        # bot itself was disconnected from voice
        if bot_user_id and member.id == bot_user_id and after.channel is None:
            player = self.controller.get_player(member.guild.id)
            if player:
                # A null voice state is ALSO the delayed answer to a disconnect Kyro
                # initiated itself (reconnect / stop / self-heal). Discord can deliver
                # it after the new session is already live — tearing down here would
                # make the bot join a channel and immediately disconnect itself.
                if time.monotonic() < player._disconnect_expected_until:
                    player._disconnect_expected_until = 0.0
                    logger.debug(
                        f"Guild {member.guild.id}: ignoring self-initiated voice disconnect event."
                    )
                    return

                player.cancel_empty_vc_timer(auto_resume=False)
                # Only announce disconnect if not already announced by empty timer or user command
                if not getattr(player, "_disconnect_announced", False):
                    if player.home_channel and before.channel:
                        try:
                            container = KyroContainer(accent_color=None)
                            container.add_section(
                                content=(
                                    "**Voice Disconnected**\n"
                                    f"> Kyro has disconnected from {before.channel.mention}."
                                )
                            )
                            await send_container_response(player.home_channel, container)
                        except Exception:
                            pass
                player._disconnect_announced = False
                player._was_paused_for_empty_vc = False
                # A self-heal disconnect (MusicAgent) must NOT wipe the playlist —
                # otherwise one transient error invalidates the whole music session.
                if getattr(player, "preserve_queue_on_disconnect", False):
                    player.preserve_queue_on_disconnect = False
                    player.current = None
                    logger.info(
                        f"Guild {member.guild.id}: Self-heal voice disconnect — "
                        f"queue preserved ({len(player.queue)} track(s))."
                    )
                else:
                    player.queue.clear()
                    player.current = None
                if player.voice_client:
                    try:
                        player.voice_client.cleanup()
                    except Exception:
                        pass
                player.voice_client = None
            return

        # bot itself was moved INTO a voice channel (added by a user, no ?join used)
        if bot_user_id and member.id == bot_user_id and after.channel is not None:
            guild = after.channel.guild

            # Meeting Safety: Never hijack voice or auto-connect music if a Meeting is active or connecting
            meeting_cog = self.bot.get_cog("Meeting")
            if meeting_cog and (
                guild.id in getattr(meeting_cog, "_sessions", {})
                or guild.id in getattr(meeting_cog, "_connecting_guilds", set())
            ):
                return

            vc = guild.voice_client
            is_connected = False
            if vc is not None:
                if hasattr(vc, "is_connected"):
                    is_connected = vc.is_connected()
                else:
                    is_connected = getattr(vc, "connected", False)

            if not is_connected:
                # discord.py only opens a voice connection when connect() is called,
                # so a bot that gets dragged into a channel would otherwise sit there
                # silently forever. Establish the connection ourselves.
                asyncio.create_task(self._auto_connect_voice(after.channel))
            return

        # non-bot member joined or moved into bot's voice channel
        if after.channel and not member.bot:
            player = self.controller.get_player(after.channel.guild.id)
            if player and player.voice_client and player.voice_client.channel == after.channel:
                was_auto_paused = player._was_paused_for_empty_vc
                # Cancel pending empty VC disconnect timer and auto-resume if it was paused for empty VC
                player.cancel_empty_vc_timer(auto_resume=True)
                if was_auto_paused:
                    if player.home_channel:
                        try:
                            container = KyroContainer(accent_color=None)
                            container.add_section(
                                content=(
                                    "**Playback Resumed**\n"
                                    f"> Listener joined {after.channel.mention}. Resuming music playback."
                                )
                            )
                            await send_container_response(player.home_channel, container)
                        except Exception:
                            pass
                    await player.update_controller_message(force=True)

        # non-bot member left or moved out of bot's voice channel
        if before.channel and not member.bot:
            player = self.controller.get_player(before.channel.guild.id)
            if player and player.voice_client and player.voice_client.channel == before.channel:
                human_listeners = [m for m in before.channel.members if not m.bot]
                if len(human_listeners) == 0:
                    # Auto-pause playback if playing
                    if player.is_playing:
                        player.pause()
                        player._was_paused_for_empty_vc = True
                        await player.update_controller_message(force=True)

                    # Check 24/7 mode
                    if getattr(player, "is_247", False):
                        logger.info(f"Voice channel #{before.channel.name} empty, but 24/7 active. Paused and staying connected.")
                        return

                    # 24/7 is OFF: start 2-minute countdown timer silently (no spam in chat)
                    logger.info(f"Voice channel #{before.channel.name} empty. Starting 2-minute disconnect countdown.")
                    player.cancel_empty_vc_timer(auto_resume=False)
                    player._was_paused_for_empty_vc = True

                    player._empty_vc_task = asyncio.create_task(
                        self._empty_vc_timeout_worker(player, before.channel, timeout=120)
                    )

    async def _auto_connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        """Connect to a voice channel the bot was added to without a ?join command."""
        guild = channel.guild

        # Meeting Safety: Do not connect music if a Meeting is active or in-flight
        meeting_cog = self.bot.get_cog("Meeting")
        if meeting_cog and (
            guild.id in getattr(meeting_cog, "_sessions", {})
            or guild.id in getattr(meeting_cog, "_connecting_guilds", set())
        ):
            logger.debug(f"Guild {guild.id}: Skipping auto_connect_voice because Meeting is active/connecting.")
            return

        # Voice Client Collision Safety: Do not connect music if AI voice is using voice
        ai_voice_cog = self.bot.get_cog("AIVoice")
        if ai_voice_cog:
            vc = guild.voice_client
            if vc and isinstance(vc, discord.VoiceClient) and not isinstance(vc, wavelink.Player):
                logger.debug(f"Guild {guild.id}: Skipping auto_connect_voice because non-music VoiceClient is active.")
                return

        # Check if a Lavalink node is online before auto-connecting
        import wavelink
        has_node = False
        try:
            for n in wavelink.Pool.nodes.values():
                if n.status == wavelink.NodeStatus.CONNECTED:
                    has_node = True
                    break
        except Exception:
            pass

        if not has_node:
            logger.debug(f"Guild {guild.id}: Skipping auto_connect_voice because no Lavalink node is currently online.")
            return

        try:
            player = self.controller.get_or_create_player(guild)
            if player.voice_client and getattr(player.voice_client, "connected", False):
                return
            player.cancel_empty_vc_timer(auto_resume=False)
            await player.connect_voice(channel)
            logger.info(
                f"Guild {guild.id}: Kyro joined {channel.name} (added by a user)."
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                f"Guild {guild.id}: auto-connect to {getattr(channel, 'name', '?')} failed: "
                f"{type(e).__name__}: {e}"
            )

    async def _empty_vc_timeout_worker(
        self, player: Any, channel: discord.VoiceChannel, timeout: int = 120
    ) -> None:
        """Disconnects player silently after specified inactivity timeout if channel remains empty."""
        try:
            await asyncio.sleep(timeout)
            if not player.voice_client or player.voice_client.channel != channel:
                return

            human_listeners = [m for m in channel.members if not m.bot]
            if len(human_listeners) > 0:
                return

            if getattr(player, "is_247", False):
                return

            logger.info(f"Empty VC timer expired for #{channel.name} in guild {player.guild.id}. Disconnecting silently.")
            player._disconnect_announced = True
            await player.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Empty VC timeout worker error: {e}", exc_info=True)

    # ==========================================
    # Prefix & Slash Commands
    # ==========================================

    @commands.hybrid_command(
        name="join",
        aliases=["connect", "j"],
        description="Connect Kyro to your current voice channel.",
    )
    async def join(self, ctx: CustomContext) -> None:
        """Connect to voice channel with smart moving support."""
        if not ctx.guild or not getattr(ctx.guild, "id", None):
            container = KyroContainer(accent_color=None)
            container.add_text("**This command can only be used in a server.**")
            await send_container_response(ctx, container)
            return

        member = ctx.author if isinstance(ctx.author, discord.Member) else (ctx.guild.get_member(ctx.author.id) if (ctx.author and getattr(ctx.author, "id", None)) else None)
        voice_state = getattr(member, "voice", None)
        target_channel = getattr(voice_state, "channel", None) if voice_state else None
        if not member or not voice_state or not target_channel or not getattr(target_channel, "id", None):
            container = KyroContainer(accent_color=None)
            container.add_text("**Join a voice channel first, then try again.**")
            await send_container_response(ctx, container)
            return

        # Mutual exclusion: check if Voice Meeting Intelligence is actively recording
        meeting_cog = self.bot.get_cog("Meeting")
        if meeting_cog and (
            ctx.guild.id in getattr(meeting_cog, "_sessions", {})
            or ctx.guild.id in getattr(meeting_cog, "_connecting_guilds", set())
        ):
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Voice Session Conflict**\n"
                    "> An active Voice Meeting session is currently recording in this server.\n"
                    "> Please stop the meeting with `,meeting stop` before connecting music."
                )
            )
            await send_container_response(ctx, container)
            return

        player = self.controller.get_or_create_player(ctx.guild)
        player.home_channel = ctx.channel

        bot_member = ctx.guild.me or (ctx.guild.get_member(self.bot.user.id) if (self.bot and self.bot.user) else None)
        bot_voice_state = getattr(bot_member, "voice", None) if bot_member else None
        bot_vc = getattr(bot_voice_state, "channel", None) if bot_voice_state else None
        if bot_vc and getattr(bot_vc, "id", None) and target_channel and getattr(target_channel, "id", None):
            if bot_vc.id == target_channel.id:
                container = KyroContainer(accent_color=None)
                container.add_text(f"**Already connected to** {target_channel.mention}.")
                await send_container_response(ctx, container)
                return

            current_listeners = [m for m in bot_vc.members if not m.bot]
            # Only block moving if actively playing AND has active human listeners
            if player.is_playing and len(current_listeners) > 0:
                container = KyroContainer(accent_color=None)
                container.add_section(
                    content=(
                        "**Voice Channel Conflict**\n"
                        f"> I am currently streaming music for {len(current_listeners)} listener(s) in {bot_vc.mention}.\n"
                        "> Please join that channel or stop playback first."
                    )
                )
                await send_container_response(ctx, container)
                return

        try:
            player.cancel_empty_vc_timer(auto_resume=False)
            await player.connect_voice(target_channel)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Voice Channel Connected**\n"
                    f"> Connected to {target_channel.mention}. Ready to play music!"
                )
            )
            await send_container_response(ctx, container)
        except (RuntimeError, ValueError) as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Voice Connection Error:** {e}")
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to connect to voice channel:** `{e}`")
            await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Play high-fidelity music tracks directly in your voice channel.",
    )
    @app_commands.describe(query="Song title, artist name, Spotify or YouTube URL")
    async def play(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Play high-fidelity music tracks in your voice channel."""
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer()
            except Exception:
                pass
        await execute_play(self, ctx, query)

    @commands.hybrid_command(
        name="autoplay",
        aliases=["ap"],
        description="Toggle Smart Autoplay to play continuous radio based on played songs.",
    )
    @app_commands.describe(state="Action: on, off, or toggle")
    async def autoplay(self, ctx: CustomContext, state: Optional[str] = "") -> None:
        """Toggle Autoplay mode."""
        await execute_autoplay(self, ctx, state or "")

    @commands.hybrid_command(
        name="pause",
        description="Pause the currently playing music stream.",
    )
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        await execute_pause(self, ctx)

    @commands.hybrid_command(
        name="resume",
        aliases=["unpause"],
        description="Resume paused music stream.",
    )
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        await execute_resume(self, ctx)

    @commands.hybrid_command(
        name="skip",
        aliases=["s", "next"],
        description="Skip the current track to the next song in queue.",
    )
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        await execute_skip(self, ctx)

    @commands.hybrid_command(
        name="stop",
        aliases=["disconnect", "dc"],
        description="Stop playback, clear queue, and disconnect from voice.",
    )
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        await execute_stop(self, ctx)

    @commands.hybrid_command(
        name="queue",
        aliases=["q"],
        description="Display the upcoming server music playlist or clear it.",
    )
    @app_commands.describe(page="Queue page number (e.g. 1) or 'clear' to empty upcoming tracks")
    async def queue(self, ctx: CustomContext, page: Optional[str] = "1") -> None:
        """Show current song queue or clear it with 'queue clear'."""
        await execute_queue(self, ctx, page or "1")

    @commands.hybrid_command(
        name="nowplaying",
        aliases=["now", "playing"],
        description="Display the currently playing song with interactive controls.",
    )
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Show currently playing song details."""
        await execute_nowplaying(self, ctx)

    @commands.command(
        name="loop",
        description="Toggle loop mode between off, track, and entire queue.",
    )
    async def loop(self, ctx: CustomContext, mode: Optional[str] = None) -> None:
        """Toggle loop mode."""
        await execute_loop(self, ctx, mode)

    @commands.command(
        name="shuffle",
        description="Randomize the order of upcoming songs in queue.",
    )
    async def shuffle(self, ctx: CustomContext) -> None:
        """Shuffle queue."""
        await execute_shuffle(self, ctx)

    @commands.command(
        name="clear",
        aliases=["clearqueue", "cq", "queueclear", "qc"],
        description="Clear all upcoming tracks from the queue.",
    )
    async def clear(self, ctx: CustomContext) -> None:
        """Clear queue."""
        await execute_clear(self, ctx)

    @commands.hybrid_command(
        name="volume",
        aliases=["vol"],
        description="Adjust playback volume (0 to 200 percent).",
    )
    @app_commands.describe(volume="Volume percentage from 0 to 200")
    async def volume(self, ctx: CustomContext, volume: int = 100) -> None:
        """Adjust playback volume."""
        await execute_volume(self, ctx, volume)

    @commands.command(
        name="like",
        aliases=["fav", "favorite"],
        description="Save the currently playing song into your personal Favorites playlist.",
    )
    async def like(self, ctx: CustomContext) -> None:
        """Save current song to Favorites playlist."""
        await handle_like(ctx, self)

    @commands.command(
        name="unlike",
        aliases=["unfav", "dislike"],
        description="Remove a song from your personal Favorites playlist by title or playing track.",
    )
    async def unlike(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Remove a song from Favorites playlist."""
        await handle_unlike(ctx, self, query=query)

    @commands.command(
        name="playlist",
        aliases=["pl"],
        description="Manage, play, view, and save custom song playlists.",
    )
    async def playlist(
        self,
        ctx: CustomContext,
        action: Optional[str] = None,
        name: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> None:
        """Manage custom user playlists."""
        await handle_playlist(ctx, self, action, name, query=query)


    @commands.command(
        name="remove",
        description="Remove a specific track from the upcoming queue by its number.",
    )
    async def remove(self, ctx: CustomContext, index: int) -> None:
        """Remove a track from queue."""
        await execute_remove(self, ctx, index)

    @commands.command(
        name="jump",
        aliases=["skipto"],
        description="Skip directly to a specific track number in the queue.",
    )
    async def jump(self, ctx: CustomContext, index: int) -> None:
        """Skip directly to a track in queue."""
        await execute_jump(self, ctx, index)

    @commands.command(
        name="247",
        aliases=["stay"],
        description="Toggle 24/7 mode to keep Kyro connected in voice even when empty.",
    )
    @commands.has_permissions(manage_guild=True)
    async def stay_247(self, ctx: CustomContext) -> None:
        """Toggle 24/7 voice stay mode."""
        await execute_stay(self, ctx)

    @commands.hybrid_command(
        name="musicdiag",
        aliases=["audiodiag", "mudiag"],
        description="Run real-time diagnostics on the music audio engine, Lavalink nodes, and voice gateway.",
    )
    async def musicdiag(self, ctx: CustomContext) -> None:
        """Inspect real-time health of Lavalink nodes, voice gateway, and Opus engine."""
        import wavelink
        from src.core.lavalink import candidates, probe_node

        node_info = "None"
        node_status = "Disconnected"
        rest_status = "Unknown"
        try:
            node = wavelink.Pool.get_node()
            if node:
                node_info = getattr(node, "uri", "Unknown")
                node_status = getattr(node.status, "name", str(node.status))
                rest_ok = await probe_node(node, timeout=3.0)
                rest_status = "Responsive (HTTP 200)" if rest_ok else "Unresponsive"
        except Exception as e:
            node_status = f"Error: {e}"

        configured_nodes = candidates()
        opus_loaded = discord.opus.is_loaded()
        vc = ctx.guild.voice_client if ctx.guild else None
        vc_type = type(vc).__name__ if vc else "None"
        vc_connected = getattr(vc, "is_connected", lambda: getattr(vc, "connected", False))() if vc else False
        vc_channel = vc.channel.name if (vc and getattr(vc, "channel", None)) else "None"

        player = self.controller.get_player(ctx.guild.id) if ctx.guild else None
        player_playing = player.is_playing if player else False
        player_queue_len = len(player.queue) if player else 0

        container = KyroContainer(accent_color=0x7C3AED)
        container.add_section(
            content=(
                "**🎵 KYOKA Audio Engine & Voice Diagnostics**\n\n"
                f"**Active Lavalink Node:** `{node_info}`\n"
                f"**Node WebSocket State:** `{node_status}`\n"
                f"**Node REST API:** `{rest_status}`\n"
                f"**Configured Cluster Nodes:** `{len(configured_nodes)} configured`\n\n"
                f"**Discord Opus Engine:** `{'Loaded & Active' if opus_loaded else 'Not Loaded'}`\n"
                f"**Voice Client Type:** `{vc_type}`\n"
                f"**Voice Channel:** `{vc_channel}` (Connected: `{vc_connected}`)\n"
                f"**Playback State:** `{'Streaming' if player_playing else 'Idle'}`\n"
                f"**Queue Depth:** `{player_queue_len} track(s)`"
            )
        )
        await send_container_response(ctx, container)

    # ── Universal Music Cog Error Shield ──

    async def cog_command_error(self, ctx: CustomContext, error: Exception) -> None:
        """Universal shield for all prefix & hybrid music commands across all servers."""
        orig_err = getattr(error, "original", error)
        # Skip standard checks/cooldowns so global error handler formats them normally
        if isinstance(orig_err, (commands.CommandOnCooldown, commands.MissingPermissions, commands.MissingRequiredArgument, commands.CheckFailure)):
            raise error
        # User input errors are NOT subsystem faults — let the global handler
        # render the proper usage message instead of a maintenance card.
        if isinstance(orig_err, commands.UserInputError):
            raise error

        handled = False
        if hasattr(self, "agent") and self.agent:
            handled = await self.agent.handle_command_error(ctx, orig_err)
        if not handled:
            raise error

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Universal shield for all slash music commands across all servers."""
        orig_err = getattr(error, "original", error)
        if isinstance(orig_err, (app_commands.CommandOnCooldown, app_commands.MissingPermissions, app_commands.CheckFailure)):
            raise error
        # Bad/missing parameter input is not a subsystem fault.
        if isinstance(orig_err, (app_commands.TransformerError, app_commands.MissingRole, app_commands.MissingAnyRole)):
            raise error

        handled = False
        if hasattr(self, "agent") and self.agent:
            handled = await self.agent.handle_command_error(interaction, orig_err)
        if not handled:
            raise error


async def setup(bot: KyroBot) -> None:
    """Load the Music Cog into KyroBot."""
    await bot.add_cog(Music(bot))
