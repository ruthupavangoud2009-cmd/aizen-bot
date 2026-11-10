from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyoka.Music.Controls")

# Per-guild 247 toggle debounce: prevents duplicate responses from hybrid
# commands firing twice (prefix + slash) or rapid double-clicks.
_247_last_toggle: dict[int, float] = {}
_247_DEBOUNCE_SECONDS: float = 3.0


def check_voice_channel(ctx: commands.Context) -> tuple[bool, str | None]:
    """Verify that author is in the same voice channel as the bot."""
    if not ctx.guild:
        return False, "This command can only be used in a server."

    member = ctx.author if isinstance(ctx.author, discord.Member) else (ctx.guild.get_member(ctx.author.id) if (ctx.author and getattr(ctx.author, "id", None)) else None)
    author_vs = getattr(member, "voice", None) if member else None
    author_vc = getattr(author_vs, "channel", None) if author_vs else None
    if not author_vc or not getattr(author_vc, "id", None):
        return False, "Join a voice channel first, then try again."

    bot_member = ctx.guild.me or (ctx.guild.get_member(ctx.bot.user.id) if (ctx.bot and ctx.bot.user) else None)
    bot_vs = getattr(bot_member, "voice", None) if bot_member else None
    bot_vc = getattr(bot_vs, "channel", None) if bot_vs else None
    if bot_vc and getattr(bot_vc, "id", None):
        if bot_vc.id != author_vc.id:
            return False, f"You must be in the same voice channel as Kyoka ({bot_vc.mention})."
    return True, None


async def execute_volume(cog: Music, ctx: commands.Context, volume: int) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyokaContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_vol = player.set_volume(volume)
    await player.update_controller_message(force=True)
    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Volume adjusted to:** `{new_vol}%`")
    await send_container_response(ctx, container)


async def execute_loop(cog: Music, ctx: commands.Context, mode: Optional[str] = None) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyokaContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_mode = player.set_loop_mode(mode)
    await player.update_controller_message(force=True)
    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Loop mode set to:** `{new_mode.upper()}`")
    await send_container_response(ctx, container)


async def execute_shuffle(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or len(player.queue) < 2:
        container = KyokaContainer(accent_color=None)
        container.add_text("**Queue needs at least 2 tracks to shuffle.**")
        await send_container_response(ctx, container)
        return

    shuffled_count = await player.shuffle_queue()
    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Shuffled {shuffled_count} tracks in queue.**")
    await send_container_response(ctx, container)


async def execute_clear(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyokaContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    if not player.queue:
        container = KyokaContainer(accent_color=None)
        container.add_text("**The queue is already empty.**")
        await send_container_response(ctx, container)
        return

    cleared_count = await player.clear_queue()
    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Cleared {cleared_count} track{'s' if cleared_count != 1 else ''} from the queue.**")
    await send_container_response(ctx, container)


async def execute_remove(cog: Music, ctx: commands.Context, index: int) -> None:
    """Remove a specific track at 1-based index from the upcoming queue."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.queue:
        container = KyokaContainer(accent_color=None)
        container.add_text("**The queue is currently empty.**")
        await send_container_response(ctx, container)
        return

    if index < 1 or index > len(player.queue):
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Invalid track index.** Please provide a number between `1` and `{len(player.queue)}`.")
        await send_container_response(ctx, container)
        return

    removed_track = await player.remove_track_at(index - 1)
    if not removed_track:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Invalid track index.**")
        await send_container_response(ctx, container)
        return

    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Removed #{index}:** `{removed_track.title}`")
    await send_container_response(ctx, container)


async def execute_jump(cog: Music, ctx: commands.Context, index: int) -> None:
    """Skip directly to a specific track in queue."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.queue:
        container = KyokaContainer(accent_color=None)
        container.add_text("**The queue is currently empty.**")
        await send_container_response(ctx, container)
        return

    if index < 1 or index > len(player.queue):
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Invalid track index.** Please provide a number between `1` and `{len(player.queue)}`.")
        await send_container_response(ctx, container)
        return

    # If single track loop is on, disable it so skip properly advances to the jumped track
    if player.loop_mode == "track":
        player.loop_mode = "off"

    # Thread-safely keep target track at index 0 and clear preceding tracks
    async with player._queue_lock:
        del player.queue[:index - 1]
        target_track = player.queue[0]

    try:
        await player.skip()
    except Exception as e:
        logger.warning(f"Guild {ctx.guild.id}: jump failed: {type(e).__name__}: {e}")
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Could not jump:** `{e}`\n> Please try again in a moment.")
        await send_container_response(ctx, container)
        return

    container = KyokaContainer(accent_color=None)
    container.add_text(f"**Jumping to:** `{target_track.title}`")
    await send_container_response(ctx, container)


async def execute_stay(cog: Music, ctx: commands.Context) -> None:
    """Toggle 24/7 stay mode in voice."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    # Debounce: hybrid commands can fire twice (prefix + slash invocation) or
    # users double-click the slash command. Ignore repeated calls within 3s.
    guild_id = ctx.guild.id
    now = time.monotonic()
    last = _247_last_toggle.get(guild_id, 0.0)
    if now - last < _247_DEBOUNCE_SECONDS:
        return
    _247_last_toggle[guild_id] = now

    player = cog.controller.get_or_create_player(ctx.guild)
    player.is_247 = not getattr(player, "is_247", False)

    if player.is_247:
        player.smart_autoplay = True
        player.autoplay = True
        player.user_247_id = ctx.author.id
        if hasattr(cog.controller, "_247_cache"):
            cog.controller._247_cache.add(ctx.guild.id)
        player.cancel_empty_vc_timer(auto_resume=False)
        # Connect immediately if not already connected
        if not player.is_connected and ctx.author.voice and ctx.author.voice.channel:
            try:
                await player.connect_voice(ctx.author.voice.channel)
            except Exception:
                pass

        # If not actively playing and queue is empty, auto-start 24/7 continuous music with liked/related tracks
        if not player.is_playing and not player.queue:
            try:
                if hasattr(player, "trigger_247_playback"):
                    asyncio.create_task(player.trigger_247_playback(ctx))
                else:
                    from src.cogs.music._commands.play import execute_play
                    asyncio.create_task(execute_play(cog, ctx, "lofi hip hop radio beats to relax study to"))
            except Exception as e:
                logger.warning(f"Could not auto-start 24/7 music: {e}")
    else:
        player.smart_autoplay = False
        player.autoplay = False
        if hasattr(cog.controller, "_247_cache"):
            cog.controller._247_cache.discard(ctx.guild.id)
        if not player.is_playing and not player.queue:
            player.schedule_empty_vc_timer()

    # Persist in database
    if hasattr(cog.bot, "db") and cog.bot.db and getattr(cog.bot.db, "pool", None):
        try:
            vc_id = (ctx.author.voice.channel.id if (ctx.author.voice and ctx.author.voice.channel) else None) if player.is_247 else None
            txt_id = ctx.channel.id if player.is_247 else None
            await cog.bot.db.execute(
                """
                INSERT INTO guild_music_247 (guild_id, is_247, voice_channel_id, text_channel_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(guild_id) DO UPDATE SET 
                    is_247 = EXCLUDED.is_247,
                    voice_channel_id = EXCLUDED.voice_channel_id,
                    text_channel_id = EXCLUDED.text_channel_id;
                """,
                ctx.guild.id,
                player.is_247,
                vc_id,
                txt_id,
            )
        except Exception as db_err:
            logger.debug(f"Could not persist 24/7 state to db: {db_err}")

    state_str = "ENABLED" if player.is_247 else "DISABLED"
    container = KyokaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**24/7 Voice & Continuous Music: {state_str}**\n"
            f"> Kyoka will {'remain in voice 24/7 playing continuous liked music & related tracks with Smart Autoplay active' if player.is_247 else 'automatically disconnect when the voice channel is empty or queue concludes'}."
        )
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Requested by {ctx.author.display_name} • 24/7 Liked & Related Music System")
    await send_container_response(ctx, container)


def parse_time_to_seconds(time_str: str) -> int | None:
    """Parse time string like 1:30, 02:45, 90, 90s, 2m30s into integer seconds."""
    time_str = time_str.strip().lower()
    if not time_str:
        return None
    import re
    if ":" in time_str:
        parts = time_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
    m_match = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$", time_str)
    if m_match and any(m_match.groups()):
        h = int(m_match.group(1) or 0)
        m = int(m_match.group(2) or 0)
        s = int(m_match.group(3) or 0)
        return h * 3600 + m * 60 + s
    if time_str.isdigit():
        return int(time_str)
    return None


async def execute_seek(cog: Music, ctx: commands.Context, position: str) -> None:
    """Seek to a specific timestamp in the current track."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.current or not player.voice_client:
        container = KyokaContainer(accent_color=None)
        container.add_text("**No track is currently playing.**")
        await send_container_response(ctx, container)
        return

    track = player.current
    if track.duration <= 0:
        container = KyokaContainer(accent_color=None)
        container.add_text("**Cannot seek in a live stream.**")
        await send_container_response(ctx, container)
        return

    seconds = parse_time_to_seconds(position)
    if seconds is None or seconds < 0:
        container = KyokaContainer(accent_color=None)
        container.add_text(
            "**Invalid timestamp format.**\n> Usage: `?seek 1:30`, `?seek 90`, or `?seek 2m15s`"
        )
        await send_container_response(ctx, container)
        return

    if seconds > track.duration:
        container = KyokaContainer(accent_color=None)
        container.add_text(
            f"**Timestamp exceeds track duration.**\n> Track duration: `{track.formatted_duration}`"
        )
        await send_container_response(ctx, container)
        return

    position_ms = seconds * 1000
    try:
        await player.voice_client.seek(position_ms)
        await player.update_controller_message(force=True)
    except Exception as e:
        logger.warning(f"Seek error in guild {ctx.guild.id}: {e}")
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Failed to seek:** `{e}`")
        await send_container_response(ctx, container)
        return

    # Formatted target position
    m = seconds // 60
    s = seconds % 60
    formatted_pos = f"{m:02d}:{s:02d}"

    container = KyokaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**⏩ Seeked to `{formatted_pos}` / `{track.formatted_duration}`**\n"
            f"> [{track.title}]({track.url}) by `{track.author}`"
        )
    )
    await send_container_response(ctx, container)


async def execute_filter(cog: Music, ctx: commands.Context, filter_name: str) -> None:
    """Apply audio filters (bassboost, nightcore, vaporwave, 8d, karaoke, tremolo, reset)."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.voice_client:
        container = KyokaContainer(accent_color=None)
        container.add_text("**No active music player found in this server.**")
        await send_container_response(ctx, container)
        return

    import wavelink
    mode = (filter_name or "help").strip().lower()

    filters = wavelink.Filters()
    filter_label = ""
    filter_desc = ""

    if mode in ("bassboost", "bb", "bass"):
        filters.equalizer.set(bands=[
            {"band": 0, "gain": 0.35},
            {"band": 1, "gain": 0.30},
            {"band": 2, "gain": 0.25},
            {"band": 3, "gain": 0.15},
            {"band": 4, "gain": 0.10},
        ])
        filter_label = "🔊 Bass Boost (High Output)"
        filter_desc = "Low-end frequencies boosted by +35% for deep sub-bass punch."
        player.active_filter = "bassboost"

    elif mode in ("nightcore", "nc"):
        filters.timescale.set(speed=1.25, pitch=1.25, rate=1.0)
        filter_label = "⚡ Nightcore"
        filter_desc = "Speed and pitch increased by 1.25x for energetic high-tempo playback."
        player.active_filter = "nightcore"

    elif mode in ("vaporwave", "slowed", "slowed+reverb", "vw"):
        filters.timescale.set(speed=0.85, pitch=0.85, rate=1.0)
        filter_label = "🌊 Vaporwave / Slowed"
        filter_desc = "Speed and pitch lowered by 0.85x for aesthetic, relaxed vibes."
        player.active_filter = "vaporwave"

    elif mode in ("8d", "3d", "spatial", "rotation"):
        filters.rotation.set(rotation_hz=0.2)
        filter_label = "🎧 8D Spatial Audio"
        filter_desc = "Surround sound rotating around your headphones at 0.2Hz."
        player.active_filter = "8d"

    elif mode in ("karaoke", "vocal"):
        filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
        filter_label = "🎤 Karaoke Mode"
        filter_desc = "Center vocal frequencies suppressed for sing-along audio."
        player.active_filter = "karaoke"

    elif mode in ("tremolo", "vibrato"):
        filters.tremolo.set(frequency=4.0, depth=0.75)
        filter_label = "〰️ Tremolo Pulse"
        filter_desc = "Pulsing audio amplitude modulation at 4Hz."
        player.active_filter = "tremolo"

    elif mode in ("reset", "off", "clear", "flat", "none"):
        filters.reset()
        filter_label = "✨ Studio Flat (Reset)"
        filter_desc = "All audio DSP effects cleared. Bit-perfect lossless playback restored."
        player.active_filter = None

    else:
        # Help card
        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                "**🎛️ Audio DSP Filters & Effects**\n"
                "> Select an audio preset to transform your sound stream:\n\n"
                "• `?filter bassboost` — Heavy deep bass boost\n"
                "• `?filter nightcore` — High-tempo 1.25x speed & pitch\n"
                "• `?filter vaporwave` — Slowed aesthetic 0.85x tempo\n"
                "• `?filter 8d` — Rotating 3D spatial surround sound\n"
                "• `?filter karaoke` — Center channel vocal suppression\n"
                "• `?filter tremolo` — Rapid amplitude pulsing effect\n"
                "• `?filter reset` — Clear all effects and restore flat studio sound"
            )
        )
        await send_container_response(ctx, container)
        return

    try:
        await player.voice_client.set_filters(filters)
    except Exception as e:
        logger.warning(f"Filter error in guild {ctx.guild.id}: {e}")
        container = KyokaContainer(accent_color=None)
        container.add_text(f"**Failed to apply filter:** `{e}`")
        await send_container_response(ctx, container)
        return

    container = KyokaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{filter_label}**\n"
            f"> {filter_desc}\n"
            f"> Applied to active player by `{ctx.author.display_name}`."
        )
    )
    await send_container_response(ctx, container)


async def execute_lyrics(cog: Music, ctx: commands.Context, query: Optional[str] = None) -> None:
    """Fetch and display synchronized or plain song lyrics."""
    player = cog.controller.get_player(ctx.guild.id) if ctx.guild else None

    search_title = (query or "").strip()
    search_artist = ""

    if not search_title:
        if player and player.current:
            search_title = player.current.title
            search_artist = player.current.author or ""
        else:
            container = KyokaContainer(accent_color=None)
            container.add_text(
                "**No song is currently playing.**\n> Usage: `?lyrics <song name>`"
            )
            await send_container_response(ctx, container)
            return

    # Clean title (remove brackets, ft., 8D audio noise)
    import html
    import urllib.parse
    import aiohttp
    import re
    from src.cogs.music._extractor import clean_track_title

    clean_target = clean_track_title(search_title)
    clean_target = re.sub(r"\b(?:official\s+video|lyrics?|audio)\b", "", clean_target, flags=re.IGNORECASE).strip()

    search_container = KyokaContainer(accent_color=None)
    search_container.add_text(f"**Searching lyrics for:** `{clean_target}`...")
    status_msg = await send_container_response(ctx, search_container)

    lyrics_text: Optional[str] = None
    track_name_found = clean_target
    artist_name_found = search_artist

    try:
        headers = {"User-Agent": "KyokaDiscordBot/3.0 (+https://github.com/ruthupavangoud2009-cmd/aizen-bot)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Try exact match if artist is known
            if search_artist and "topic" not in search_artist.lower() and "artist" != search_artist.lower():
                enc_t = urllib.parse.quote(clean_target)
                enc_a = urllib.parse.quote(search_artist)
                exact_url = f"https://lrclib.net/api/get?track_name={enc_t}&artist_name={enc_a}"
                try:
                    async with session.get(exact_url, timeout=aiohttp.ClientTimeout(total=4)) as r:
                        if r.status == 200:
                            data = await r.json()
                            raw_ly = data.get("plainLyrics") or data.get("syncedLyrics")
                            if raw_ly:
                                lyrics_text = raw_ly
                                track_name_found = data.get("trackName") or clean_target
                                artist_name_found = data.get("artistName") or search_artist
                except Exception:
                    pass

            # 2. General search query fallback
            if not lyrics_text:
                q_enc = urllib.parse.quote(clean_target)
                search_url = f"https://lrclib.net/api/search?q={q_enc}"
                try:
                    async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=5)) as r2:
                        if r2.status == 200:
                            results = await r2.json()
                            if results and isinstance(results, list):
                                for item in results[:5]:
                                    raw_ly = item.get("plainLyrics") or item.get("syncedLyrics")
                                    if raw_ly:
                                        lyrics_text = raw_ly
                                        track_name_found = item.get("trackName") or clean_target
                                        artist_name_found = item.get("artistName") or ""
                                        break
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Lyrics lookup error: {e}")

    if not lyrics_text:
        err_c = KyokaContainer(accent_color=None)
        err_c.add_section(
            content=(
                f"**Lyrics Not Found**\n"
                f"> Could not find lyrics for `{clean_target}`.\n"
                f"> Try searching with both title and artist: `?lyrics <title> <artist>`"
            )
        )
        if status_msg:
            try:
                from src.utils.containers import edit_container_response
                await edit_container_response(status_msg, err_c)
                return
            except Exception:
                pass
        await send_container_response(ctx, err_c)
        return

    # Strip synced timestamps if mostly synced [00:12.34]
    clean_lyrics = re.sub(r"\[\d{2}:\d{2}\.\d{2,3}\]", "", lyrics_text).strip()

    # Truncate to Discord embed limit (3800 chars)
    if len(clean_lyrics) > 3800:
        clean_lyrics = clean_lyrics[:3750] + "\n\n... *(lyrics truncated due to length)*"

    result_c = KyokaContainer(accent_color=None)
    header = f"**Lyrics: {track_name_found}**"
    if artist_name_found:
        header += f" — *{artist_name_found}*"
    result_c.add_section(
        content=(
            f"{header}\n\n"
            f"```text\n{clean_lyrics}\n```"
        )
    )
    result_c.add_separator(divider=True)
    result_c.add_text(f"-# Requested by {ctx.author.display_name}")

    if status_msg:
        try:
            from src.utils.containers import edit_container_response
            await edit_container_response(status_msg, result_c)
            return
        except Exception:
            pass
    await send_container_response(ctx, result_c)
