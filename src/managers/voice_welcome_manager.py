"""
Kyoka Discord Bot - Per-Server Voice Welcome Manager
Handles automated, customizable Text-To-Speech (TTS) voice greetings when members join
the server or connect to designated voice channels.
Architected to co-exist with Music sessions: never disconnects, moves, or interrupts active music.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from gtts import gTTS

if TYPE_CHECKING:
    from src.core.bot import KyokaBot
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyoka.Managers.VoiceWelcome")


class VoiceWelcomeManager:
    """Manages voice welcome configuration, greetings queue, and audio playback."""

    def __init__(self, bot: KyokaBot, db: PostgresDatabase) -> None:
        self.bot = bot
        self.db = db
        self._cache: dict[int, dict[str, Any]] = {}
        self._queues: dict[int, list[dict[str, Any]]] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    def invalidate_cache(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        """Fetch voice welcome settings for a guild with caching."""
        if guild_id in self._cache:
            return self._cache[guild_id]

        query = """
        SELECT guild_id, enabled, channel_id, trigger, greeting_text, tts_provider,
               language, cooldown_seconds, queue_expiration_seconds, allow_bots, defer_if_music_active
        FROM guild_voice_welcome_config
        WHERE guild_id = $1;
        """
        try:
            row = await self.db.fetch_one(query, guild_id)
            if row:
                config = dict(row)
            else:
                config = {
                    "guild_id": guild_id,
                    "enabled": False,
                    "channel_id": None,
                    "trigger": "both",
                    "greeting_text": "Hi {member}! Thanks for joining {server}. Welcome to our community!",
                    "tts_provider": "gtts",
                    "language": "en",
                    "cooldown_seconds": 30,
                    "queue_expiration_seconds": 120,
                    "allow_bots": False,
                    "defer_if_music_active": True,
                }
            self._cache[guild_id] = config
            return config
        except Exception as e:
            logger.debug(f"Error fetching voice welcome config for guild {guild_id}: {e}")
            return {
                "guild_id": guild_id,
                "enabled": False,
                "channel_id": None,
                "trigger": "both",
                "greeting_text": "Hi {member}! Thanks for joining {server}. Welcome to our community!",
                "tts_provider": "gtts",
                "language": "en",
                "cooldown_seconds": 30,
                "queue_expiration_seconds": 120,
                "allow_bots": False,
                "defer_if_music_active": True,
            }

    async def update_config(self, guild_id: int, **kwargs: Any) -> bool:
        """Update voice welcome settings in database and invalidate cache."""
        current = await self.get_config(guild_id)
        current.update(kwargs)

        query = """
        INSERT INTO guild_voice_welcome_config (
            guild_id, enabled, channel_id, trigger, greeting_text, tts_provider,
            language, cooldown_seconds, queue_expiration_seconds, allow_bots, defer_if_music_active, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            channel_id = EXCLUDED.channel_id,
            trigger = EXCLUDED.trigger,
            greeting_text = EXCLUDED.greeting_text,
            tts_provider = EXCLUDED.tts_provider,
            language = EXCLUDED.language,
            cooldown_seconds = EXCLUDED.cooldown_seconds,
            queue_expiration_seconds = EXCLUDED.queue_expiration_seconds,
            allow_bots = EXCLUDED.allow_bots,
            defer_if_music_active = EXCLUDED.defer_if_music_active,
            updated_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.db.execute(
                query,
                guild_id,
                current.get("enabled", False),
                current.get("channel_id"),
                current.get("trigger", "both"),
                current.get("greeting_text", "Hi {member}! Thanks for joining {server}. Welcome to our community!"),
                current.get("tts_provider", "gtts"),
                current.get("language", "en"),
                current.get("cooldown_seconds", 30),
                current.get("queue_expiration_seconds", 120),
                current.get("allow_bots", False),
                current.get("defer_if_music_active", True),
            )
            self.invalidate_cache(guild_id)
            return True
        except Exception as e:
            logger.error(f"Error saving voice welcome config: {e}")
            return False

    async def reset_config(self, guild_id: int) -> bool:
        """Reset configuration for guild to factory defaults."""
        query = "DELETE FROM guild_voice_welcome_config WHERE guild_id = $1;"
        try:
            await self.db.execute(query, guild_id)
            self.invalidate_cache(guild_id)
            self._queues.pop(guild_id, None)
            return True
        except Exception as e:
            logger.error(f"Error resetting voice welcome config: {e}")
            return False

    def is_music_active(self, guild: discord.Guild) -> bool:
        """Check if music is currently active or playing in the guild."""
        if not guild.voice_client or not guild.voice_client.is_connected():
            return False

        # Check if voice client itself is currently transmitting audio
        if guild.voice_client.is_playing():
            return True

        # Check music controller player state if available
        music_ctrl = getattr(self.bot, "_music_controller", None)
        if music_ctrl and hasattr(music_ctrl, "get_player"):
            player = music_ctrl.get_player(guild.id)
            if player:
                if getattr(player, "is_playing", False) or getattr(player, "current_track", None) is not None:
                    return True
                if getattr(player, "is_247", False):
                    return True

        return False

    def format_greeting(self, template: str, member: discord.Member) -> str:
        """Format dynamic greeting variables with member and guild attributes."""
        guild = getattr(member, "guild", None)
        member_name = str(getattr(member, "name", "member"))
        display_name = str(getattr(member, "display_name", member_name))
        guild_name = str(getattr(guild, "name", "the server")) if guild else "the server"
        member_count = str(getattr(guild, "member_count", 1)) if guild else "1"

        return (
            template.replace("{member}", display_name)
            .replace("{username}", member_name)
            .replace("{server}", guild_name)
            .replace("{guild}", guild_name)
            .replace("{count}", member_count)
        )

    def generate_tts_file(self, text: str, lang: str = "en") -> str:
        """Generate mp3 file via gTTS and return temporary file path."""
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="kyoka_voice_welcome_")
        os.close(fd)
        tts = gTTS(text=text, lang=lang or "en", slow=False)
        tts.save(path)
        return path

    def is_on_cooldown(self, guild_id: int, user_id: int, cooldown_sec: int) -> bool:
        """Verify if greeting is on cooldown for this user."""
        now = time.time()
        last = self._cooldowns.get((guild_id, user_id), 0.0)
        if now - last < cooldown_sec:
            return True
        self._cooldowns[(guild_id, user_id)] = now
        return False

    async def handle_member_event(self, member: discord.Member, trigger_type: str) -> None:
        """Process member join or voice state change event."""
        if not member.guild:
            return

        guild_id = member.guild.id
        config = await self.get_config(guild_id)

        if not config.get("enabled"):
            return

        if member.bot and not config.get("allow_bots"):
            return

        allowed_trigger = config.get("trigger", "both")
        if allowed_trigger != "both" and allowed_trigger != trigger_type:
            return

        cooldown = int(config.get("cooldown_seconds") or 30)
        if self.is_on_cooldown(guild_id, member.id, cooldown):
            logger.debug(f"[VoiceWelcome] User {member.id} is on cooldown in guild {guild_id}.")
            return

        channel_id = config.get("channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) and not hasattr(channel, "connect"):
            return

        # If user joined voice, verify they are in the target channel or permitted channel
        if trigger_type == "voice_join":
            if not member.voice or not member.voice.channel or member.voice.channel.id != channel_id:
                return

        # Check music coexistence
        if self.is_music_active(member.guild):
            if config.get("defer_if_music_active", True):
                # Queue greeting safely without interrupting music session
                self._enqueue_greeting(guild_id, member, config)
                logger.info(
                    f"[VoiceWelcome] Music session active in guild {guild_id}. Deferring greeting for {member.display_name}."
                )
                return

        # Execute speech playback
        asyncio.create_task(self.play_greeting(member.guild, channel, member, config))

    def _enqueue_greeting(self, guild_id: int, member: discord.Member, config: dict[str, Any]) -> None:
        """Enqueue deferred greeting with expiration timestamp."""
        if guild_id not in self._queues:
            self._queues[guild_id] = []

        now = time.time()
        ttl = int(config.get("queue_expiration_seconds") or 120)

        # Remove expired queue items
        self._queues[guild_id] = [item for item in self._queues[guild_id] if now - item["timestamp"] < ttl]

        # Prevent duplicate entries for the same member
        if any(item["member_id"] == member.id for item in self._queues[guild_id]):
            return

        self._queues[guild_id].append({
            "member_id": member.id,
            "member": member,
            "timestamp": now,
            "ttl": ttl,
        })

    async def on_music_idle(self, guild: discord.Guild) -> None:
        """Called when a music session finishes to drain eligible non-expired greetings."""
        guild_id = guild.id
        if guild_id not in self._queues or not self._queues[guild_id]:
            return

        config = await self.get_config(guild_id)
        if not config.get("enabled"):
            self._queues[guild_id].clear()
            return

        channel_id = config.get("channel_id")
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return

        now = time.time()
        queue = self._queues.pop(guild_id, [])
        valid_items = [i for i in queue if now - i["timestamp"] < i["ttl"]]

        for item in valid_items:
            member = item["member"]
            # Verify member is still in guild
            if guild.get_member(member.id):
                await self.play_greeting(guild, channel, member, config)
                break  # Process sequentially

    async def play_greeting(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel | discord.StageChannel,
        member: discord.Member,
        config: dict[str, Any],
    ) -> bool:
        """Connect to voice channel, play generated TTS speech, and cleanly disconnect."""
        lock = self._get_lock(guild.id)
        if lock.locked():
            logger.debug(f"[VoiceWelcome] Playback locked for guild {guild.id}, skipping overlapping greeting.")
            return False

        async with lock:
            # Re-verify music has not started in the meantime
            if self.is_music_active(guild):
                logger.info(f"[VoiceWelcome] Music started in guild {guild.id}, aborting greeting.")
                return False

            greeting_template = config.get("greeting_text") or "Welcome {member} to {server}!"
            spoken_text = self.format_greeting(greeting_template, member)
            lang = config.get("language") or "en"

            temp_path: str | None = None
            voice_client: discord.VoiceClient | None = None
            we_connected = False

            try:
                # Run TTS generation in executor to avoid blocking event loop
                temp_path = await asyncio.to_thread(self.generate_tts_file, spoken_text, lang)

                # Connect or reuse voice client if not used by music
                if guild.voice_client:
                    if guild.voice_client.channel.id != channel.id:
                        # Connected to different channel; check if music is using it
                        if self.is_music_active(guild):
                            return False
                        await guild.voice_client.move_to(channel)
                    voice_client = guild.voice_client
                else:
                    voice_client = await channel.connect(timeout=10.0, reconnect=False)
                    we_connected = True

                if not voice_client or not voice_client.is_connected():
                    return False

                # Play audio asynchronously
                play_done = asyncio.Event()

                def _after_play(error: Exception | None) -> None:
                    if error:
                        logger.warning(f"[VoiceWelcome] Playback error: {error}")
                    play_done.set()

                audio_source = discord.FFmpegPCMAudio(temp_path)
                voice_client.play(audio_source, after=_after_play)

                # Wait for playback completion with timeout
                try:
                    await asyncio.wait_for(play_done.wait(), timeout=20.0)
                except asyncio.TimeoutError:
                    if voice_client.is_playing():
                        voice_client.stop()

                logger.info(f"[VoiceWelcome] Successfully greeted {member.display_name} in {guild.name}.")
                return True

            except Exception as e:
                logger.error(f"[VoiceWelcome] Failed to play greeting for {member.display_name}: {e}")
                return False
            finally:
                # Clean up temporary audio file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

                # Disconnect only if we established the connection and music didn't claim it
                if we_connected and voice_client and voice_client.is_connected():
                    if not self.is_music_active(guild):
                        try:
                            await voice_client.disconnect(force=True)
                        except Exception:
                            pass
