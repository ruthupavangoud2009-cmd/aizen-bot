"""
KYOKA — Playback Watchdog & Health Supervision Engine
=====================================================

Monitors active players in real time:
- Detects stalled playback (position not advancing while marked playing)
- Automatically recovers lost voice connections
- Manages empty voice channel timeouts to conserve server resources
- Purges inactive zombie players to prevent memory leaks
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from discord.ext import tasks

if TYPE_CHECKING:
    from src.core.bot import KyokaBot
    from src.cogs.music._controller import MusicController
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyoka.Music.Watchdog")


class PlaybackWatchdog:
    """
    Autonomous Watchdog & Quality-of-Service Monitor for Kyoka Music.
    Runs every 10 seconds to detect stalls, network blips, and zombie players.
    """

    def __init__(self, bot: KyokaBot, controller: MusicController) -> None:
        self.bot = bot
        self.controller = controller

        # Position tracking: guild_id -> (last_position_ms, timestamp)
        self._last_positions: Dict[int, tuple[float, float]] = {}
        self._empty_vc_deadlines: Dict[int, float] = {}  # guild_id -> deadline
        self._idle_timestamps: Dict[int, float] = {}     # guild_id -> stopped_time

        # Telemetry
        self.stalls_detected: int = 0
        self.stalls_recovered: int = 0
        self.voice_reconnects: int = 0
        self.empty_vc_timeouts: int = 0

        self.watchdog_loop.start()

    def stop(self) -> None:
        """Cancel watchdog on cog unload."""
        if self.watchdog_loop.is_running():
            self.watchdog_loop.cancel()

    @tasks.loop(seconds=10.0)
    async def watchdog_loop(self) -> None:
        """Periodic health check across all active guild players."""
        if not self.bot.is_ready():
            return

        now = time.time()
        players_snapshot = list(self.controller.players.items())

        for guild_id, player in players_snapshot:
            try:
                await self._inspect_player(guild_id, player, now)
            except Exception as e:
                logger.debug(f"Watchdog inspection notice for guild {guild_id}: {e}")

    async def _inspect_player(self, guild_id: int, player: GuildPlayer, now: float) -> None:
        guild = player.guild
        if not guild:
            return

        vc = player.voice_client or guild.voice_client

        # ── 1. Zombie / Idle Cleanup ──
        if not player.is_playing and not player.is_paused and len(player.queue) == 0:
            if not getattr(player, "is_247", False):
                idle_since = self._idle_timestamps.setdefault(guild_id, now)
                if now - idle_since > 900.0:  # 15 minutes idle
                    logger.info(f"Guild {guild_id}: Purging idle player to free hosting memory.")
                    await self.controller.remove_player(guild_id)
                    self._idle_timestamps.pop(guild_id, None)
                    self._last_positions.pop(guild_id, None)
                    return
            else:
                self._idle_timestamps.pop(guild_id, None)
        else:
            self._idle_timestamps.pop(guild_id, None)

        # ── 2. Empty Voice Channel Timeout ──
        if vc and getattr(vc, "channel", None):
            members = [m for m in vc.channel.members if not m.bot]
            if len(members) == 0 and not getattr(player, "is_247", False):
                # Channel is empty of human listeners
                if guild_id not in self._empty_vc_deadlines:
                    self._empty_vc_deadlines[guild_id] = now + 180.0  # 3 minutes
                    logger.debug(f"Guild {guild_id}: Voice channel empty, scheduled disconnect in 3m.")
                elif now >= self._empty_vc_deadlines[guild_id]:
                    logger.info(f"Guild {guild_id}: Empty voice channel timeout expired. Stopping player.")
                    self.empty_vc_timeouts += 1
                    self._empty_vc_deadlines.pop(guild_id, None)
                    await player.stop(force_disconnect=True)
                    return
            else:
                self._empty_vc_deadlines.pop(guild_id, None)

        # ── 3. Voice Gateway Desync Recovery ──
        if (player.is_playing or getattr(player, "is_247", False)) and not player.is_connected:
            # Voice client dropped unexpectedly
            logger.warning(f"Guild {guild_id}: Voice connection lost while active. Attempting self-heal...")
            self.voice_reconnects += 1
            agent = getattr(self.bot, "_music_agent", None)
            if agent:
                try:
                    await agent.heal_voice_session(guild, reason="Watchdog voice drop")
                except Exception as e:
                    logger.debug(f"Guild {guild_id}: Voice heal error: {e}")
            return

        # ── 4. Stalled Playback Detection ──
        if player.is_playing and not player.is_paused and player.current:
            pos = getattr(vc, "position", 0.0) if vc else 0.0
            last_entry = self._last_positions.get(guild_id)

            if last_entry:
                last_pos, last_time = last_entry
                elapsed = now - last_time
                if elapsed >= 15.0:
                    # If position has not moved at all over 15 seconds while marked playing
                    if abs(pos - last_pos) < 100.0:  # less than 100ms advancement in 15s
                        self.stalls_detected += 1
                        logger.warning(
                            f"Guild {guild_id}: Audio playback stall detected on '{player.current.title}' "
                            f"(pos={pos}ms unchanged for {elapsed:.1f}s). Triggering auto-recovery..."
                        )
                        self._last_positions[guild_id] = (pos, now)
                        await self._recover_stalled_player(guild_id, player)
                        return

            self._last_positions[guild_id] = (pos, now)
        else:
            self._last_positions.pop(guild_id, None)

    async def _recover_stalled_player(self, guild_id: int, player: GuildPlayer) -> None:
        """Attempt surgical alternative source recovery or clean skip on stall."""
        self.stalls_recovered += 1
        current_track = player.current
        if not current_track:
            return

        # Invoke player on_track_end with stuck reason to trigger alternative source cascade
        try:
            await player.on_track_end(reason="stuck")
        except Exception as e:
            logger.error(f"Guild {guild_id}: Error recovering stalled track: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Return watchdog metrics."""
        return {
            "stalls_detected": self.stalls_detected,
            "stalls_recovered": self.stalls_recovered,
            "voice_reconnects": self.voice_reconnects,
            "empty_vc_timeouts": self.empty_vc_timeouts,
            "monitored_guilds": len(self.controller.players),
        }
