"""
Kyoka Discord Bot - Lavalink Guild Audio Player
Streamlined, zero-lag, zero-stutter audio streaming powered by NexCloud Lavalink v4.
Offloads all heavy audio processing, buffering, and encoding from Render/PC to the Lavalink node.
Maintains full compatibility with Kyoka Components V2 interactive cards and commands.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, List, Optional, Set
import discord
import wavelink

from src.cogs.music._models import Track
from src.cogs.music._autoplay import NativeSmartAutoplay
from src.core.lavalink import (
    LAVALINK_OP_TIMEOUT,
    LAVALINK_PLAY_TIMEOUT,
    LAVALINK_RESOLVE_TIMEOUT,
    LavalinkUnavailable,
    close_pool_nodes,
    connect_lavalink_node,
    err_text,
    probe_node,
)
from src.utils.containers import KyokaContainer, KyroContainer, send_container_response, edit_container_response
from src.cogs.music._views import MusicControlView

if TYPE_CHECKING:
    from src.core.bot import KyokaBot, KyroBot

logger = logging.getLogger("Kyoka.Music.Player")


class KyokaWavelinkPlayer(wavelink.Player):
    """
    Hardened Wavelink 3.x Player for Kyoka.

    Eliminates the Discord voice gateway packet-ordering race condition where
    VOICE_SERVER_UPDATE lands before VOICE_STATE_UPDATE. Standard Wavelink only
    dispatches on server update; if state update lands later, Wavelink never
    dispatches the credentials to Lavalink, causing channel.connect() to hang
    for 20 seconds and disconnect itself.

    Also guards against stale null-channel VOICE_STATE_UPDATE packets tearing
    down active voice sessions when the bot is still present in the channel.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not getattr(self, "_guild", None) and getattr(self, "channel", None):
            self._guild = getattr(self.channel, "guild", None)

    async def on_voice_state_update(self, data: Any, /) -> None:
        if not getattr(self, "_guild", None) and getattr(self, "channel", None):
            self._guild = getattr(self.channel, "guild", None)

        channel_id = data.get("channel_id")
        if not channel_id:
            # If Discord delivers a stale null-channel packet from a prior connection,
            # but the bot is still in a voice channel according to guild.me.voice,
            # do not destroy the active session!
            if self.guild and getattr(getattr(self.guild, "me", None), "voice", None):
                if getattr(self.guild.me.voice, "channel", None) is not None:
                    logger.debug(
                        f"Guild {self.guild.id}: ignoring stale null-channel voice state update."
                    )
                    return
            await self._destroy()
            return

        self._connected = True
        if "voice" not in self._voice_state or not isinstance(self._voice_state["voice"], dict):
            self._voice_state["voice"] = {}

        self._voice_state["voice"]["session_id"] = data["session_id"]
        self._voice_state["channel_id"] = str(channel_id)
        if self.client and hasattr(self.client, "get_channel"):
            self.channel = self.client.get_channel(int(channel_id))

        # Bidirectional dispatch: if VOICE_SERVER_UPDATE arrived first, dispatch now!
        if (
            self._voice_state["voice"].get("token")
            and self._voice_state["voice"].get("endpoint")
        ):
            await self._dispatch_voice_update()


def shorten_artist(artist: str, max_len: int = 30) -> str:
    """Safely truncate artist string for embeds."""
    if not artist:
        return "Unknown"
    return artist if len(artist) <= max_len else artist[:max_len - 3] + "..."


class GuildPlayer:
    """
    High-Performance Lavalink Guild Player for Kyoka Bot.
    Replaces local FFmpeg subprocesses with dedicated Lavalink node streaming.
    """

    def __init__(self, bot: KyokaBot | KyroBot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[KyokaWavelinkPlayer | wavelink.Player] = None

        # Playback state
        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.volume: float = 1.0  # Normalized (1.0 = 100%)
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.smart_autoplay: bool = False
        self.autoplay_history: Set[str] = set()
        self.is_247: bool = False

        # UI & Communication
        self.home_channel: Optional[discord.TextChannel | discord.Thread] = None
        self.controller_message: Optional[discord.Message] = None
        self._disconnect_announced: bool = False
        self._empty_vc_task: Optional[asyncio.Task] = None
        self._advance_lock: asyncio.Lock = asyncio.Lock()
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._queue_lock: asyncio.Lock = asyncio.Lock()
        self._last_advance_time: float = 0.0
        self._last_manual_advance: float = 0.0
        self._advance_gen: int = 0
        self._is_prefetching: bool = False
        self._is_connecting: bool = False
        # Set by the MusicAgent before a self-heal disconnect so the queue survives.
        self.preserve_queue_on_disconnect: bool = False
        # Monotonic deadline until which a VOICE_STATE_UPDATE(channel=None) is treated as
        # the delayed answer to a disconnect Kyoka initiated itself (reconnect / stop /
        # self-heal) instead of an external disconnect that must end the session.
        self._disconnect_expected_until: float = 0.0

    # ── State Properties ──

    @property
    def is_connected(self) -> bool:
        """Check if connected to a valid Discord voice channel."""
        vc = self.guild.voice_client
        return vc is not None and getattr(vc, "connected", False)

    @property
    def is_playing(self) -> bool:
        """Check if actively playing audio."""
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return vc.playing and not vc.paused
        return False

    @property
    def is_paused(self) -> bool:
        """Check if playback is currently paused."""
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return vc.paused
        return False

    # ── Thread-Safe Queue Operations ──

    async def add_track(self, track: Track) -> None:
        """Thread-safely append a single track to the queue."""
        async with self._queue_lock:
            self.queue.append(track)
        asyncio.create_task(self._prefetch_next_track())

    async def add_tracks(self, tracks: list[Track]) -> None:
        """Thread-safely append multiple tracks to the queue."""
        async with self._queue_lock:
            self.queue.extend(tracks)
        asyncio.create_task(self._prefetch_next_track())

    async def pop_next_track(self) -> Optional[Track]:
        """Thread-safely pop the next track from the front of the queue."""
        async with self._queue_lock:
            if self.queue:
                return self.queue.pop(0)
            return None

    async def clear_queue(self) -> int:
        """Thread-safely clear all tracks from the queue and return count."""
        async with self._queue_lock:
            cnt = len(self.queue)
            self.queue.clear()
            return cnt

    async def remove_track_at(self, index: int) -> Optional[Track]:
        """Thread-safely remove a track at index (0-based) from queue."""
        async with self._queue_lock:
            if 0 <= index < len(self.queue):
                return self.queue.pop(index)
            return None

    async def shuffle_queue(self) -> int:
        """Thread-safely shuffle the upcoming queue."""
        async with self._queue_lock:
            import random
            random.shuffle(self.queue)
            return len(self.queue)

    # ── Voice Connection ──

    async def connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        """Connect or move to the specified voice channel using Wavelink with race-condition locking."""
        if not channel or not getattr(channel, "id", None):
            raise ValueError("Invalid voice channel: channel does not exist or is not specified.")

        if not self.guild or not getattr(self.guild, "id", None):
            raise ValueError("Invalid guild: music player guild is missing.")

        channel_name = getattr(channel, "name", "voice channel")

        async with self._connect_lock:
            self._is_connecting = True
            try:
                # Check if this guild has an active or in-flight Voice Meeting session
                meeting_cog = self.bot.get_cog("Meeting")
                if meeting_cog and (
                    self.guild.id in getattr(meeting_cog, "_sessions", {})
                    or self.guild.id in getattr(meeting_cog, "_connecting_guilds", set())
                ):
                    raise RuntimeError(
                        f"Cannot connect music player: Guild {self.guild.id} is currently running an active Voice Meeting."
                    )

                # 1. Pre-flight permission and capacity verification
                me = self.guild.me or (self.guild.get_member(self.bot.user.id) if (self.bot and self.bot.user) else None)
                if me is not None:
                    perms = channel.permissions_for(me)
                    if not perms.connect:
                        raise RuntimeError(f"Kyoka lacks 'Connect' permission to join {channel_name}.")
                    if not perms.speak:
                        raise RuntimeError(f"Kyoka lacks 'Speak' permission in {channel_name}.")
                    if channel.user_limit and channel.user_limit > 0:
                        if len(channel.members) >= channel.user_limit and not perms.move_members:
                            raise RuntimeError(f"Voice channel {channel_name} is full ({len(channel.members)}/{channel.user_limit} members).")
                else:
                    logger.warning(f"Guild {self.guild.id}: could not resolve bot member for voice permission check.")

                vc = self.guild.voice_client
                if vc and isinstance(vc, wavelink.Player) and vc.connected:
                    vc_channel = getattr(vc, "channel", None)
                    if vc_channel and getattr(vc_channel, "id", None) != channel.id:
                        try:
                            # Bounded: move_to talks to the Lavalink REST API.
                            await asyncio.wait_for(
                                vc.move_to(channel),
                                timeout=LAVALINK_OP_TIMEOUT,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Guild {self.guild.id}: move_to {channel_name} failed: "
                                f"{type(e).__name__}: {e}"
                            )
                    self.voice_client = vc
                    return

                # If connected to an invalid, disconnected, or non-wavelink player, clean it up first
                if vc:
                    # Never disconnect an active Meeting VoiceRecvClient!
                    if meeting_cog and (
                        self.guild.id in getattr(meeting_cog, "_sessions", {})
                        or self.guild.id in getattr(meeting_cog, "_connecting_guilds", set())
                    ):
                        return

                    # Flag the disconnect as self-initiated so the VOICE_STATE_UPDATE that
                    # Discord sends back for it cannot tear down the session we are about
                    # to establish.
                    self._disconnect_expected_until = time.monotonic() + 10.0
                    try:
                        # Bounded: this talks to the Lavalink REST API.
                        await asyncio.wait_for(
                            vc.disconnect(force=True),
                            timeout=LAVALINK_OP_TIMEOUT,
                        )
                    except Exception:
                        pass
                    try:
                        vc.cleanup()
                    except Exception:
                        pass
                    self.voice_client = None

                # Purge any lingering voice client cache so the next handshake starts clean.
                try:
                    self.bot._connection._remove_voice_client(self.guild.id)
                except Exception:
                    pass

                # Ensure Wavelink node is alive and connected before connecting player
                node = None
                try:
                    node = wavelink.Pool.get_node()
                except Exception:
                    pass

                if not node or node.status != wavelink.NodeStatus.CONNECTED:
                    logger.info("Wavelink node disconnected or missing. Re-establishing connection...")
                    try:
                        await close_pool_nodes()
                        node = await connect_lavalink_node(
                            self.bot,
                            inactive_player_timeout=300,
                        )
                    except Exception as e:
                        logger.error(f"On-demand Lavalink node connect error: {err_text(e)}")
                        node = None

                # ── Node REST health probe ──
                if node is not None and not await self._probe_lavalink_node(node):
                    logger.warning(
                        f"Guild {self.guild.id}: Lavalink REST API is not responsive, "
                        "re-establishing the node before connecting."
                    )
                    agent = getattr(self.bot, "_music_agent", None)
                    if agent is not None:
                        try:
                            await agent.heal_node(force=True)
                        except Exception as heal_err:
                            logger.error(f"Guild {self.guild.id}: Lavalink node heal failed: {heal_err}")
                    try:
                        node = wavelink.Pool.get_node()
                    except Exception:
                        node = None

                # Critical validation before touching Discord voice gateway:
                if not node or node.status != wavelink.NodeStatus.CONNECTED:
                    stale_vc = self.guild.voice_client
                    if stale_vc:
                        self._disconnect_expected_until = time.monotonic() + 10.0
                        try:
                            await asyncio.wait_for(stale_vc.disconnect(force=True), timeout=LAVALINK_OP_TIMEOUT)
                        except Exception:
                            pass
                    try:
                        self.bot._connection._remove_voice_client(self.guild.id)
                    except Exception:
                        pass
                    self.voice_client = None
                    raise LavalinkUnavailable(
                        "Audio streaming engine (Lavalink) is currently unreachable. "
                        "Cannot establish voice audio connection without an active node."
                    )

                # Connect as hardened Kyoka Wavelink Player with automatic retry on temporary Discord gateway blip
                last_error: Optional[BaseException] = None
                for attempt in range(3):
                    try:
                        self.voice_client = await channel.connect(cls=KyokaWavelinkPlayer, self_deaf=True, timeout=20.0)
                        if self.voice_client:
                            self.voice_client.autoplay = wavelink.AutoPlayMode.disabled
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"Guild {self.guild.id}: Voice connect attempt {attempt + 1}/3 failed "
                            f"({type(e).__name__}: {e}), clearing voice state and retrying..."
                        )
                        stale_vc = self.guild.voice_client
                        if stale_vc:
                            self._disconnect_expected_until = time.monotonic() + 10.0
                            try:
                                # Bounded: this talks to the Lavalink REST API.
                                await asyncio.wait_for(
                                    stale_vc.disconnect(force=True),
                                    timeout=LAVALINK_OP_TIMEOUT,
                                )
                            except Exception:
                                pass
                            try:
                                stale_vc.cleanup()
                            except Exception:
                                pass
                        try:
                            self.bot._connection._remove_voice_client(self.guild.id)
                        except Exception:
                            pass
                        try:
                            self._disconnect_expected_until = time.monotonic() + 10.0
                            await self.guild.change_voice_state(channel=None)
                        except Exception:
                            pass
                        self.voice_client = None

                        if attempt == 0:
                            agent = getattr(self.bot, "_music_agent", None)
                            if agent is not None:
                                try:
                                    await agent.heal_node(force=True)
                                except Exception as heal_err:
                                    logger.error(f"Guild {self.guild.id}: Lavalink node heal failed: {heal_err}")
                        await asyncio.sleep(1.5 * (attempt + 1))

                if last_error is not None:
                    logger.error(f"Guild {self.guild.id}: Wavelink connect error: {last_error}")
                    try:
                        ghost_vc = self.guild.voice_client
                        if ghost_vc:
                            self._disconnect_expected_until = time.monotonic() + 10.0
                            await asyncio.wait_for(ghost_vc.disconnect(force=True), timeout=LAVALINK_OP_TIMEOUT)
                    except Exception:
                        pass
                    try:
                        self.bot._connection._remove_voice_client(self.guild.id)
                    except Exception:
                        pass
                    self.voice_client = None
                    if hasattr(self.bot, "sentinel") and self.bot.sentinel:
                        from src.sentinel.models import SubsystemType, IncidentSeverity
                        self.bot.sentinel.record_incident(
                            SubsystemType.VOICE,
                            IncidentSeverity.WARNING,
                            "Voice Gateway Connect Failure",
                            f"Failed connecting to channel {channel.name} ({channel.id}): "
                            f"{type(last_error).__name__}: {last_error}",
                            action_taken="Purged stale voice client & gateway state (queue preserved)",
                            resolved=True,
                            guild_id=self.guild.id,
                        )
                    raise last_error
            finally:
                self._is_connecting = False

    async def _probe_lavalink_node(self, node: Any, timeout: float = 4.0) -> bool:
        """
        Verify the Lavalink node REST API is actually responsive.

        The websocket can be alive while the REST API is slow or unreachable -
        and the Wavelink voice handshake only completes after a successful REST
        call, so a dead REST API silently turns into a voice connect timeout.
        """
        return await probe_node(node, timeout=timeout)

    # ── Playback Engine ──

    async def play_track(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Stream a track via the dedicated Lavalink node with 0% stutter."""
        # 1. Verify voice connection or attempt fast recovery
        if not self.voice_client or not self.voice_client.connected:
            vc = self.guild.voice_client
            if vc and isinstance(vc, wavelink.Player) and vc.connected:
                self.voice_client = vc

        if not self.voice_client or not self.voice_client.connected:
            target_ch = getattr(self.guild.me.voice, "channel", None)
            if target_ch:
                try:
                    await self.connect_voice(target_ch)
                except Exception:
                    pass

        if not self.voice_client or not self.voice_client.connected:
            logger.warning(f"Guild {self.guild.id}: Cannot play, voice client not connected.")
            if message_to_edit and isinstance(message_to_edit, discord.Message):
                err_c = KyokaContainer(accent_color=None)
                err_c.add_text("**Voice Disconnected**\n> Kyoka is not connected to a voice channel. Please join a voice channel and use `?play` to start.")
                try:
                    await edit_container_response(message_to_edit, err_c)
                except Exception:
                    pass
            return

        # 2. Direct playable if already attached, otherwise resolve via Lavalink with strict timeout
        playable = getattr(track, "_playable", None)
        if not playable:
            try:
                playable = await self._resolve_playable(track)
            except Exception as e:
                logger.error(f"Error resolving playable for '{track.title}': {e}")
                playable = None

        if not playable:
            logger.warning(f"Guild {self.guild.id}: Lavalink could not resolve playable for '{track.title}'")
            if self.home_channel:
                try:
                    warn_c = KyokaContainer(accent_color=None)
                    warn_c.add_text(f"⚠️ **Could not stream track:** `{track.title}`\n> Audio stream was unavailable on YouTube. Advancing to next track in queue...")
                    await send_container_response(self.home_channel, warn_c)
                except Exception:
                    pass
            next_t = await self.pop_next_track()
            if next_t:
                await self.play_track(next_t, message_to_edit=message_to_edit)
            else:
                self.current = None
                if message_to_edit and isinstance(message_to_edit, discord.Message):
                    err_c = KyokaContainer(accent_color=None)
                    err_c.add_text(f"**Failed to Stream Track:** `{track.title}`\n> The audio source could not be loaded. Please try another song.")
                    try:
                        await edit_container_response(message_to_edit, err_c)
                    except Exception:
                        pass
                else:
                    await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        self.current = track
        self.autoplay_history.add(track.title.lower())
        self._was_paused_for_empty_vc = False
        self.cancel_empty_vc_timer(auto_resume=False)

        # 3. Start playback on Lavalink node with volume (explicitly unpaused)
        vol_int = int(self.volume * 100)
        try:
            # Bounded: this call talks to the Lavalink REST API. Without a bound it
            # could block for the session's 300s default timeout and freeze the
            # command (and any lock it holds) for five minutes.
            await asyncio.wait_for(
                self.voice_client.play(playable, volume=vol_int, paused=False),
                timeout=LAVALINK_PLAY_TIMEOUT,
            )
        except Exception as play_err:
            logger.warning(f"Guild {self.guild.id}: voice_client.play error for '{track.title}': {play_err}. Attempting node recovery...")
            recovered = False
            try:
                agent = getattr(self.bot, "_music_agent", None)
                if agent:
                    await agent.heal_node(force=True)
                await asyncio.sleep(0.5)
                await asyncio.wait_for(
                    self.voice_client.play(playable, volume=vol_int, paused=False),
                    timeout=LAVALINK_PLAY_TIMEOUT,
                )
                recovered = True
                logger.info(f"Guild {self.guild.id}: Re-stream recovered successfully for '{track.title}'")
            except Exception as retry_err:
                logger.error(f"Guild {self.guild.id}: Re-stream retry failed: {retry_err}")

            if not recovered:
                if message_to_edit:
                    err_c = KyokaContainer(accent_color=None)
                    err_c.add_text(f"**Failed to Stream Track:** `{track.title}`\n> Playback dispatch error: `{play_err}`")
                    try:
                        await edit_container_response(message_to_edit, err_c)
                    except Exception:
                        pass
                raise

        # 4. Send or edit sleek Now Playing card with buttons
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)
        asyncio.create_task(self._prefetch_next_track())

    # Domains that are NOT direct audio streams — Lavalink can't play their page URLs
    _NON_STREAM_DOMAINS = (
        "spotify.com",
        "open.spotify.com",
        "music.youtube.com",
        "youtube.com/watch",
        "youtu.be",
    )

    def _is_direct_stream_url(self, url: str) -> bool:
        """Return True only if url is a raw audio stream Lavalink can play via HTTP."""
        if not url or not url.startswith(("http://", "https://")):
            return False
        u_low = url.lower()
        if any(cdn in u_low for cdn in ("saavncdn.com", "googlevideo.com", "sndcdn.com", "stream.zeno.fm", "icecast", "shoutcast")):
            return True
        if any(u_low.endswith(ext) or f"{ext}?" in u_low for ext in (".mp4", ".m4a", ".mp3", ".aac", ".ogg", ".flac", ".opus", "videoplayback")):
            return True
        return False

    async def _prefetch_next_track(self) -> None:
        """Background pre-resolver: resolves upcoming track's Playable before current track ends."""
        if getattr(self, "_is_prefetching", False):
            return
        self._is_prefetching = True
        try:
            target_track: Optional[Track] = None
            async with self._queue_lock:
                for t in self.queue[:2]:
                    if not getattr(t, "_playable", None):
                        target_track = t
                        break
            if target_track:
                p = await self._resolve_playable(target_track)
                if p:
                    target_track._playable = p
                    logger.debug(f"Pre-fetched playable for upcoming track '{target_track.title}'")
        except Exception as e:
            logger.debug(f"Background prefetch notice: {e}")
        finally:
            self._is_prefetching = False

    async def _resolve_playable(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve a Lavalink Playable for a track with a hard overall deadline.

        The inner cascade can try up to five strategies twice each, so without an
        overall budget a single unresolvable track could keep the caller waiting
        for well over a minute. The whole resolution is capped here instead.
        """
        try:
            return await asyncio.wait_for(
                self._resolve_playable_cascade(track),
                timeout=LAVALINK_RESOLVE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Guild {self.guild.id}: playable resolution timed out after "
                f"{LAVALINK_RESOLVE_TIMEOUT:.0f}s for '{track.title}'."
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Guild {self.guild.id}: playable resolution failed for '{track.title}': "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def _resolve_playable_cascade(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve Lavalink Playable via attached playable, direct YouTube/Spotify URL, or resilient search cascade.

        Each search strategy is retried once on TimeoutError with a short backoff.
        Timeouts are set to 10s to survive transient Lavalink / YouTube 429 slowness.
        """
        # ── Priority 1: Attached Playable (already resolved) ──
        playable = getattr(track, "_playable", None)
        if playable:
            return playable

        # ── Node Health Pre-check: Ensure Lavalink node is alive ──
        try:
            node = wavelink.Pool.get_node()
            if not node or node.status != wavelink.NodeStatus.CONNECTED:
                if hasattr(self.bot, "_music_agent") and self.bot._music_agent:
                    await self.bot._music_agent.heal_node()
                await asyncio.sleep(0.4)
        except Exception:
            pass

        url = track.url or ""

        # ── Priority 1.5: Direct Audio Stream URL (JioSaavn 320kbps / CDN / HTTP stream) ──
        stream_url = getattr(track, "stream_url", None)
        if stream_url and self._is_direct_stream_url(stream_url):
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(stream_url), timeout=8.0)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Direct stream URL resolve notice for '{track.title}': {e}")

        # ── Priority 2: Direct URL (YouTube or Spotify track) ──
        if url.startswith(("http://", "https://")):
            is_yt = any(yt in url for yt in ("youtube.com/watch", "youtu.be/", "music.youtube.com/watch"))
            is_sp = "open.spotify.com/track/" in url
            if is_yt or is_sp:
                for attempt in range(2):
                    try:
                        results = await asyncio.wait_for(
                            wavelink.Playable.search(url), timeout=10.0
                        )
                        if results:
                            return results[0] if isinstance(results, list) else results.tracks[0]
                        break  # got empty response, no point retrying
                    except asyncio.TimeoutError:
                        logger.debug(f"Direct URL resolve timeout for '{url}' (attempt {attempt + 1})")
                        if attempt == 0:
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Direct URL resolve notice for '{url}': {e}")
                        break

        # ── Priority 3: Multi-strategy search cascade with retry ──
        from src.cogs.music._extractor import clean_track_title
        clean_title = clean_track_title(track.title) if track.title else ""
        raw_author = track.author if (track.author and "spotify" not in track.author.lower() and "unknown" not in track.author.lower() and "artist" != track.author.lower()) else ""
        full_query = f"{clean_title} {raw_author}".strip() or track.query or track.title or ""

        # Build ordered search strategies: (query, source)
        strategies: list[tuple[str, object]] = []
        if full_query:
            strategies.append((full_query, wavelink.TrackSource.YouTubeMusic))
            strategies.append((full_query, wavelink.TrackSource.YouTube))
            strategies.append((full_query, None))
            strategies.append((full_query, wavelink.TrackSource.SoundCloud))
            strategies.append((full_query, "spsearch"))
        if clean_title and clean_title != full_query:
            strategies.append((clean_title, wavelink.TrackSource.YouTubeMusic))
            strategies.append((clean_title, wavelink.TrackSource.YouTube))
            strategies.append((clean_title, None))
            strategies.append((clean_title, wavelink.TrackSource.SoundCloud))
        if track.query and track.query not in (full_query, clean_title) and not track.query.startswith(("http://", "https://")):
            strategies.append((track.query, wavelink.TrackSource.YouTubeMusic))
            strategies.append((track.query, wavelink.TrackSource.YouTube))
            strategies.append((track.query, None))
            strategies.append((track.query, wavelink.TrackSource.SoundCloud))
        if track.title and track.title not in (full_query, clean_title):
            strategies.append((track.title, wavelink.TrackSource.YouTube))
            strategies.append((track.title, None))
            strategies.append((track.title, wavelink.TrackSource.SoundCloud))

        for query, source in strategies:
            if not query:
                continue
            for attempt in range(2):  # retry once per strategy on timeout
                try:
                    results = await asyncio.wait_for(
                        wavelink.Playable.search(query, source=source),
                        timeout=10.0,
                    )
                    if results:
                        p = results[0] if isinstance(results, list) else results.tracks[0]
                        logger.debug(
                            f"Resolved '{track.title}' via strategy ({source}, query='{query}', attempt={attempt + 1})"
                        )
                        return p
                    break  # empty result — no point retrying this strategy
                except asyncio.TimeoutError:
                    logger.debug(
                        f"Search timeout for '{query}' source={source} (attempt {attempt + 1})"
                    )
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Search error for '{query}' source={source}: {e}")
                    break  # non-timeout error — skip retry, try next strategy

        # ── Priority 4: JioSaavn HD Audio Engine Fallback ──
        if not url.startswith(("http://", "https://")):
            try:
                from src.cogs.music._extractor import NativeExtractor
                saavn_t = await asyncio.wait_for(
                    NativeExtractor._extract_jiosaavn(full_query or track.title, requester=track.requester, is_autoplay=track.is_autoplay),
                    timeout=5.0
                )
                if saavn_t and saavn_t.stream_url:
                    s_res = await asyncio.wait_for(wavelink.Playable.search(saavn_t.stream_url), timeout=6.0)
                    if s_res:
                        return s_res[0] if isinstance(s_res, list) else s_res.tracks[0]
            except Exception as e:
                logger.debug(f"JioSaavn playable cascade fallback notice: {e}")

        logger.warning(f"All resolution strategies exhausted for '{track.title}' (queries tried: {[s[0] for s in strategies]})")
        return None


    # ── Controls ──

    @staticmethod
    async def _bounded_node_call(coro: Any, timeout: float = LAVALINK_OP_TIMEOUT) -> None:
        """
        Run a Lavalink REST call with a hard deadline.

        Wavelink's aiohttp session uses the library default timeout of 300s, so a
        single unreachable node can keep a background task alive for five minutes.
        """
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"Bounded Lavalink call failed: {type(e).__name__}: {e}")

    def pause(self) -> bool:
        """Pause playback."""
        if self.voice_client and self.voice_client.playing and not self.voice_client.paused:
            try:
                self.voice_client._paused = True
            except Exception:
                pass
            asyncio.create_task(self._bounded_node_call(self.voice_client.pause(True)))
            return True
        return False

    def resume(self) -> bool:
        """Resume playback."""
        if self.voice_client and self.voice_client.paused:
            try:
                self.voice_client._paused = False
            except Exception:
                pass
            asyncio.create_task(self._bounded_node_call(self.voice_client.pause(False)))
            self._was_paused_for_empty_vc = False
            return True
        return False

    async def skip(self) -> None:
        """
        Skip the currently playing track.
        Directly pops the next queued track and plays it via Lavalink's native replacement.
        """
        if self.loop_mode == "track":
            self.loop_mode = "off"

        target = await self.pop_next_track()
        if target is not None:
            await self.play_track(target)
        else:
            self.current = None
            if self.voice_client:
                try:
                    await asyncio.wait_for(
                        self.voice_client.skip(force=True),
                        timeout=LAVALINK_OP_TIMEOUT,
                    )
                except Exception as e:
                    logger.debug(f"Guild {self.guild.id}: voice skip notice: {e}")
            await self.send_queue_ended_card()
            self.schedule_empty_vc_timer()


    async def stop(self) -> None:
        """Stop playback and disconnect."""
        self.cancel_empty_vc_timer(auto_resume=False)
        self.queue.clear()
        self.current = None
        self.autoplay_history.clear()
        self._was_paused_for_empty_vc = False

        if self.voice_client:
            # Mark this as a self-initiated disconnect so the matching
            # VOICE_STATE_UPDATE(channel=None) does not run the teardown twice.
            self._disconnect_expected_until = time.monotonic() + 5.0
            try:
                # Bounded: an unreachable node must not hang ?stop for minutes.
                await asyncio.wait_for(
                    self.voice_client.disconnect(force=True),
                    timeout=LAVALINK_OP_TIMEOUT,
                )
            except Exception as e:
                logger.warning(
                    f"Guild {self.guild.id}: voice disconnect failed: {type(e).__name__}: {e}"
                )
            self.voice_client = None

        # Clear reference without deleting card from chat
        self.controller_message = None

    def set_volume(self, volume_percent: int) -> int:
        """Adjust volume (0 - 150%)."""
        clamped = max(0, min(150, volume_percent))
        self.volume = clamped / 100.0
        if self.voice_client:
            asyncio.create_task(self._bounded_node_call(self.voice_client.set_volume(clamped)))
        return clamped

    def set_loop_mode(self, mode: Optional[str] = None) -> str:
        """
        Cycle loop mode or set specific mode ('off', 'track', 'queue').
        Accepts: 'off', 'track', 'queue', 'song', 'all', 'toggle', or None.
        """
        modes = ["off", "track", "queue"]
        m_str = (mode or "").strip().lower()

        if m_str in ("track", "song", "single", "1"):
            self.loop_mode = "track"
        elif m_str in ("queue", "all", "q"):
            self.loop_mode = "queue"
        elif m_str in ("off", "none", "disable", "stop", "0"):
            self.loop_mode = "off"
        else:
            cur_idx = modes.index(self.loop_mode) if self.loop_mode in modes else 0
            self.loop_mode = modes[(cur_idx + 1) % len(modes)]

        return self.loop_mode

    # ── Track End & Autoplay Transition ──

    async def on_track_end(
        self,
        reason: Optional[str] = None,
        *,
        manual: bool = False,
        expected_gen: Optional[int] = None,
    ) -> None:
        """
        Invoked when Lavalink finishes playing a track.

        `manual=True` is used by explicit user actions (skip/jump) which must
        ALWAYS advance, while event driven advances are debounced so a duplicate
        `TrackEndEvent` cannot skip two tracks at once.
        """
        if reason and str(reason).lower() in ("replaced", "cleanup"):
            return

        if reason and str(reason).lower() in ("loadfailed", "load_failed", "stuck", "error"):
            logger.warning(f"Guild {self.guild.id}: Lavalink reported track {reason}.")
            failed_title = self.current.title if self.current else "track"
            if self.voice_client and hasattr(self.voice_client, "skip"):
                try:
                    await asyncio.wait_for(
                        self.voice_client.skip(force=True),
                        timeout=LAVALINK_OP_TIMEOUT,
                    )
                except Exception as e:
                    logger.debug(f"Guild {self.guild.id}: voice skip cleanup notice: {e}")
            if self.home_channel:
                try:
                    warn_c = KyokaContainer(accent_color=None)
                    warn_c.add_text(f"⚠️ **Could not stream track:** `{failed_title}` (audio source error). Advancing queue...")
                    await send_container_response(self.home_channel, warn_c)
                except Exception:
                    pass
            next_track = await self.pop_next_track()
            if next_track:
                await self.play_track(next_track)
            else:
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        async with self._advance_lock:
            now = time.time()

            if manual:
                # A TrackEnd event already advanced the queue for this skip.
                if expected_gen is not None and self._advance_gen != expected_gen:
                    logger.debug(
                        f"Guild {self.guild.id}: skip advance skipped, "
                        "queue was already advanced by a TrackEnd event."
                    )
                    return
            else:
                # Debounce duplicate TrackEnd events (Lavalink emits one per skip).
                if now - self._last_advance_time < 0.8:
                    logger.debug(f"Guild {self.guild.id}: Duplicate on_track_end call debounced")
                    return
                # A locally advanced skip may still be followed by the node's own
                # TrackEnd event — ignore it within a short window to avoid double-skip.
                # Window reduced to 1.5s (was 2.0s) so rapid legitimate user skips
                # are not incorrectly blocked.
                if self._last_manual_advance and (now - self._last_manual_advance) < 1.5:
                    logger.debug(
                        f"Guild {self.guild.id}: Redundant TrackEnd event after a manually "
                        "advanced skip ignored (within 1.5s window)"
                    )
                    self._last_advance_time = now
                    return

            self._last_advance_time = now
            self._advance_gen += 1
            if manual:
                self._last_manual_advance = now

            # ── Critical section: only in-memory state decisions ──
            # The lock must NOT be held while a track is resolved or dispatched:
            # both talk to the Lavalink node and can take many seconds. Holding it
            # here meant one slow advance blocked every later ?skip / ?jump /
            # track-end for the whole duration.
            if self.loop_mode == "track" and self.current:
                target: Optional[Track] = self.current
            else:
                if self.loop_mode == "queue" and self.current:
                    await self.add_track(self.current)
                target = await self.pop_next_track()

        # ── Slow work happens OUTSIDE the advance lock ──
        if target is not None:
            await self.play_track(target)
            return

        if self.smart_autoplay and self.current:
            # Smart Autoplay AI recommendation
            try:
                rec = await NativeSmartAutoplay.get_next_recommendation(
                    self.current, self.autoplay_history, self.bot.db
                )
                if rec:
                    rec.requester = "⚡ Smart Autoplay"
                    await self.play_track(rec)
                else:
                    self.current = None
                    await self.send_queue_ended_card()
                    self.schedule_empty_vc_timer()
            except Exception as e:
                logger.error(f"Guild {self.guild.id}: Smart autoplay error: {e}", exc_info=True)
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
        else:
            self.current = None
            await self.send_queue_ended_card()
            self.schedule_empty_vc_timer()

    # ── Components V2 Controller Card ──

    def build_now_playing_container(self, track: Track) -> KyokaContainer:
        """Construct the Components V2 Now Playing card matching custom layout."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        heart_e = ""
        if e_reg:
            heart_e = (
                e_reg.get("heart_dot", "")
                or e_reg.get("icons_heart", "")
                or e_reg.get("heart", "")
            )
        link_emoji = e_reg.get("link", "") if e_reg else ""

        container = KyokaContainer(accent_color=None)

        # 1. Title: Now Playing (ZERO emoji on title)
        container.add_text("## Now Playing")

        # 2. 1 Divider line directly beneath Now Playing
        container.add_separator(divider=True)

        # 3. Song, Artist, and Duration with heart emoji in front (NO normal/unicode emojis, no source)
        safe_title = track.title.replace("[", "(").replace("]", ")")
        song_display = f"[{safe_title}]({track.url})" if track.url else safe_title
        artist_display = track.author or "Unknown Artist"
        duration_display = track.formatted_duration or "00:00"

        # Calculate elapsed position if available
        pos_ms = getattr(self.voice_client, "position", 0) if self.voice_client else 0
        if pos_ms > 0:
            e_mins, e_secs = divmod(int(pos_ms / 1000), 60)
            time_display = f"`{e_mins:02d}:{e_secs:02d} / {duration_display}`"
        else:
            time_display = f"`{duration_display}`"

        vol_pct = int(self.volume * 100)
        loop_status = self.loop_mode.upper() if self.loop_mode != "off" else "Off"
        queue_count = len(self.queue)
        q_label = f"{queue_count} track{'s' if queue_count != 1 else ''}" if queue_count > 0 else "Empty"

        dot_prefix = f"> {heart_e} " if heart_e else "> "
        link_prefix = f"{link_emoji} " if link_emoji else ""

        body_lines = [
            f"{dot_prefix}**Song:** {song_display}",
            f"{dot_prefix}**Artist:** `{artist_display}`",
            f"{dot_prefix}**Duration:** {time_display}",
            f"{dot_prefix}**Status:** Volume: `{vol_pct}%` • Loop: `{loop_status}` • Queue: `{q_label}`",
        ]

        container.add_section(content="\n".join(body_lines))

        # Resolve thumbnail (fallback to YouTube thumbnail if missing)
        thumb = track.thumbnail
        if not thumb and track.url and ("youtube.com" in track.url or "youtu.be" in track.url):
            import re
            m = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", track.url)
            if m:
                thumb = f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"
                track.thumbnail = thumb

        if thumb:
            container.add_thumbnail(thumb)

        # 4. Divider line before footer
        container.add_separator(divider=True)

        # 5. Footer: Requested by ONLY
        container.add_text(f"-# Requested by: {track.requester}")

        # 6. Divider line after footer before action row buttons
        container.add_separator(divider=True)
        return container

    async def send_now_playing_card(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Post or edit the interactive Now Playing card in home channel."""
        if not self.home_channel:
            return

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.bot, player=self, track_url=track.url)

        # For every song starting from queue, skip, autoplay, or fresh play: send a brand-new clean Now Playing card!
        try:
            msg = await send_container_response(
                self.home_channel, container, view=view, content=None
            )
            if isinstance(msg, discord.Message):
                self.controller_message = msg
                # Clean up initial temporary searching message if present
                if message_to_edit and isinstance(message_to_edit, discord.Message) and message_to_edit.id != msg.id:
                    try:
                        await message_to_edit.delete()
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Failed to send now playing card: {e}")

    async def update_controller_message(self, force: bool = False) -> None:
        """Refresh active controller card."""
        if not self.controller_message or not self.current:
            return

        container = self.build_now_playing_container(self.current)
        view = MusicControlView(self.bot, player=self, track_url=self.current.url)
        try:
            await edit_container_response(self.controller_message, container, view=view, content=None)
        except Exception as e:
            logger.debug(f"Failed to edit controller message: {e}")

    async def send_queue_ended_card(self) -> None:
        """Post or edit the Queue Ended card in home channel."""
        if not self.home_channel:
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "") if hasattr(e_reg, "get") else ""
        bullet = f"{dot} " if dot else "> "

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"# **Queue Concluded**\n"
                f"{bullet}All queued songs have finished playing.\n"
                f"> Add more tracks using `?play <song>` or enable autoplay with `?autoplay on`!"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Disconnecting in 3 minutes if no new songs are added.")
        container.add_separator(divider=True)

        if self.controller_message and isinstance(self.controller_message, discord.Message):
            try:
                await edit_container_response(
                    self.controller_message,
                    container,
                    view=None,
                    content=None,
                )
                self.controller_message = None
                return
            except Exception:
                pass

        try:
            await send_container_response(
                self.home_channel,
                container,
                content=None,
            )
        except Exception:
            pass

    # ── Inactivity Timers ──

    def cancel_empty_vc_timer(self, auto_resume: bool = False) -> None:
        """Cancel idle disconnect timer."""
        if self._empty_vc_task and not self._empty_vc_task.done():
            self._empty_vc_task.cancel()
            self._empty_vc_task = None

    def schedule_empty_vc_timer(self) -> None:
        """Schedule disconnect after 3 minutes of idle queue."""
        if getattr(self, "is_247", False):
            return
        self.cancel_empty_vc_timer()
        self._empty_vc_task = asyncio.create_task(self._empty_vc_timeout(180))

    async def _empty_vc_timeout(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            if getattr(self, "is_247", False):
                return
            if not self.is_playing and not self.queue:
                logger.info(f"Guild {self.guild.id}: Idle timeout reached, disconnecting silently.")
                await self.stop()
        except asyncio.CancelledError:
            pass
