"""
KYOKA — Interactive Music Search Command
========================================

Executes multi-result music searches and presents interactive selection cards.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, List
import discord
from discord.ext import commands

from src.cogs.music._commands.controls import check_voice_channel
from src.cogs.music._models import Track
from src.cogs.music._views import MusicSearchView
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyoka.Music.Search")


async def execute_search(cog: Music, ctx: commands.Context, query: Optional[str] = None) -> None:
    """Execute interactive /search command."""
    if ctx.interaction and not ctx.interaction.response.is_done():
        try:
            await ctx.interaction.response.defer()
        except Exception:
            pass

    if not ctx.guild:
        c = KyokaContainer()
        c.add_text("**This command can only be used in a server.**")
        await send_container_response(ctx, c)
        return

    member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
    if not member or not getattr(member, "voice", None) or not getattr(member.voice, "channel", None):
        c = KyokaContainer()
        c.add_text("**Join a voice channel first, then try again.**")
        await send_container_response(ctx, c)
        return

    if not query or not query.strip():
        c = KyokaContainer()
        c.add_text("**Please specify a song title or artist to search.**\n> Usage: `/search <query>` or `?search <query>`")
        await send_container_response(ctx, c)
        return

    search_term = query.strip()
    c = KyokaContainer()
    c.add_text(f"**Searching for:** `{search_term}`...")
    status_msg = await send_container_response(ctx, c)

    tracks: List[Track] = []

    # 1. Check SearchCache
    search_cache = getattr(cog.bot, "_music_search_cache", None)
    if search_cache:
        cached_list = await search_cache.get(search_term)
        if cached_list:
            tracks = cached_list[:5]

    # 2. Search via Wavelink / Dedicated Lavalink node
    if not tracks:
        import wavelink
        try:
            results = await asyncio.wait_for(
                wavelink.Playable.search(search_term, source=wavelink.TrackSource.YouTubeMusic),
                timeout=8.0,
            )
            raw_tracks = results if isinstance(results, list) else getattr(results, "tracks", [])
            for p in raw_tracks[:5]:
                t = Track(
                    title=p.title or "Unknown Track",
                    author=p.author or "Unknown Artist",
                    url=p.uri or f"https://youtube.com/watch?v={getattr(p, 'identifier', '')}",
                    duration=int((getattr(p, "length", 0) or 0) / 1000),
                    thumbnail=getattr(p, "artwork", None),
                    requester=ctx.author.display_name,
                    requester_id=ctx.author.id,
                    query=search_term,
                    source_name="YouTube Music",
                )
                t._playable = p
                tracks.append(t)
        except Exception as e:
            logger.debug(f"Search YTM notice: {e}")

    # 3. Fallback to standard YouTube search if needed
    if not tracks:
        import wavelink
        try:
            results = await asyncio.wait_for(
                wavelink.Playable.search(search_term, source=wavelink.TrackSource.YouTube),
                timeout=8.0,
            )
            raw_tracks = results if isinstance(results, list) else getattr(results, "tracks", [])
            for p in raw_tracks[:5]:
                t = Track(
                    title=p.title or "Unknown Track",
                    author=p.author or "Unknown Artist",
                    url=p.uri or f"https://youtube.com/watch?v={getattr(p, 'identifier', '')}",
                    duration=int((getattr(p, "length", 0) or 0) / 1000),
                    thumbnail=getattr(p, "artwork", None),
                    requester=ctx.author.display_name,
                    requester_id=ctx.author.id,
                    query=search_term,
                    source_name="YouTube",
                )
                t._playable = p
                tracks.append(t)
        except Exception as e:
            logger.debug(f"Search YT notice: {e}")

    # 4. Fallback to SoundCloud
    if not tracks:
        import wavelink
        try:
            results = await asyncio.wait_for(
                wavelink.Playable.search(search_term, source=wavelink.TrackSource.SoundCloud),
                timeout=8.0,
            )
            raw_tracks = results if isinstance(results, list) else getattr(results, "tracks", [])
            for p in raw_tracks[:5]:
                t = Track(
                    title=p.title or "Unknown Track",
                    author=p.author or "Unknown Artist",
                    url=p.uri or "",
                    duration=int((getattr(p, "length", 0) or 0) / 1000),
                    thumbnail=getattr(p, "artwork", None),
                    requester=ctx.author.display_name,
                    requester_id=ctx.author.id,
                    query=search_term,
                    source_name="SoundCloud",
                )
                t._playable = p
                tracks.append(t)
        except Exception as e:
            logger.debug(f"Search SC notice: {e}")

    if not tracks:
        c = KyokaContainer()
        c.add_section(
            content=f"**No Results Found**\n> No tracks found matching `{search_term}`.\n> Try searching with a different song name or artist."
        )
        if status_msg:
            try:
                await edit_container_response(status_msg, c)
                return
            except Exception:
                pass
        await send_container_response(ctx, c)
        return

    # Cache results in search cache
    if search_cache:
        await search_cache.set(search_term, tracks)

    # Build sleek search card
    c = KyokaContainer()
    c.add_text(f"## Search Results for `{search_term}`")
    c.add_separator(divider=True)

    lines = []
    for i, t in enumerate(tracks[:5], 1):
        safe_title = t.title.replace("[", "(").replace("]", ")")
        link = f"[{safe_title}]({t.url})" if t.url else f"**{safe_title}**"
        lines.append(f"`{i}.` {link}\n> 👤 `{t.author}` • ⏱️ `{t.formatted_duration}` • `{t.source_name}`")

    c.add_section(content="\n\n".join(lines))
    c.add_separator(divider=True)
    c.add_text("-# Select a track from the menu below to start playback. (Expires in 60s)")

    view = MusicSearchView(cog.bot, tracks, ctx.author.id)
    if status_msg:
        try:
            view.message = status_msg
            await edit_container_response(status_msg, c, view=view)
            return
        except Exception:
            pass

    msg = await send_container_response(ctx, c, view=view)
    if msg:
        view.message = msg
