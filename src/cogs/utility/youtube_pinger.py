"""
Kyoka Discord Bot - YouTube Live Stream Pinger & Broadcast Announcement Engine
Automatically monitors configured YouTube channels and pings an announcement channel
with customizable roles and embeds when a streamer goes live.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import TYPE_CHECKING, Any, Optional
import xml.etree.ElementTree as ET

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.YouTubePinger")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class YouTubeLivePinger(commands.Cog):
    """Monitors YouTube channels and announces live streams in real-time."""
    category = "Utility"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self._checking_lock = asyncio.Lock()
        self.live_monitor_loop.start()

    async def cog_load(self) -> None:
        """Create database table for YouTube live subscriptions."""
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS youtube_live_subscriptions (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        yt_channel_id VARCHAR(64) NOT NULL,
                        yt_channel_name VARCHAR(128) NOT NULL,
                        yt_handle VARCHAR(128),
                        discord_channel_id BIGINT NOT NULL,
                        ping_role_id BIGINT,
                        custom_message TEXT,
                        last_live_video_id VARCHAR(64),
                        is_live BOOLEAN DEFAULT FALSE,
                        last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(guild_id, yt_channel_id)
                    );
                    """
                )
                logger.info("YouTube live subscriptions table verified.")
            except Exception as e:
                logger.error(f"Failed to initialize youtube_live_subscriptions table: {e}")

    def cog_unload(self) -> None:
        """Stop background task and close HTTP session."""
        if self.live_monitor_loop.is_running():
            self.live_monitor_loop.cancel()
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    # ─── CHANNEL RESOLUTION & LIVE DETECTION HELPERS ─────────────────────────

    async def resolve_channel_info(self, query: str) -> tuple[str | None, str | None, str | None]:
        """
        Resolve a YouTube Channel ID, Display Name, and Handle from a query.
        Accepts: Channel ID (UC...), @handle, or full YouTube channel / user URL.
        """
        clean = query.strip()
        session = self._get_session()

        # 1. Direct 24-character Channel ID starting with UC
        if re.match(r"^UC[a-zA-Z0-9_-]{22}$", clean):
            channel_id = clean
            # Fetch channel name via RSS feed
            try:
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        root = ET.fromstring(text)
                        author_elem = root.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
                        name = author_elem.text if author_elem is not None else channel_id
                        return channel_id, name, None
            except Exception as e:
                logger.debug(f"RSS fetch notice for channel {channel_id}: {e}")
            return channel_id, channel_id, None

        # 2. Extract handle or direct URL
        target_url = clean
        if clean.startswith("@"):
            target_url = f"https://www.youtube.com/{clean}"
        elif not clean.startswith(("http://", "https://")):
            target_url = f"https://www.youtube.com/@{clean}"

        try:
            async with session.get(target_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None, None, None
                html_text = await resp.text()

                # Extract Channel ID from canonical link or meta tags
                id_match = (
                    re.search(r'<meta itemprop="identifier" content="(UC[a-zA-Z0-9_-]{22})"', html_text)
                    or re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html_text)
                    or re.search(r'href="https://www\.youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})"', html_text)
                )
                if not id_match:
                    return None, None, None

                channel_id = id_match.group(1)

                # Extract Title / Name
                name_match = (
                    re.search(r'<meta property="og:title" content="([^"]+)"', html_text)
                    or re.search(r'<title>([^<]+) - YouTube</title>', html_text)
                )
                channel_name = html.unescape(name_match.group(1)) if name_match else channel_id

                # Extract Handle
                handle_match = re.search(r'"canonicalBaseUrl":"/(@[a-zA-Z0-9_.-]+)"', html_text)
                handle = handle_match.group(1) if handle_match else None

                return channel_id, channel_name, handle
        except Exception as e:
            logger.error(f"Error resolving YouTube channel '{query}': {e}")
            return None, None, None

    async def check_channel_live(self, channel_id: str) -> tuple[bool, str | None, str | None, str | None]:
        """
        Check if a YouTube channel is currently live streaming.
        Returns: (is_live, video_id, title, thumbnail_url)
        """
        session = self._get_session()
        live_url = f"https://www.youtube.com/channel/{channel_id}/live"

        try:
            async with session.get(live_url, allow_redirects=True) as resp:
                final_url = str(resp.url)
                html_text = await resp.text()

                # A: Detect redirection to watch?v=VIDEO_ID
                vid_match = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", final_url)
                if not vid_match:
                    vid_match = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"', html_text)

                if vid_match:
                    video_id = vid_match.group(1)
                    # Check if page indicates active live stream
                    is_live = bool(
                        '"isLive":true' in html_text
                        or '"isLiveContent":true' in html_text
                        or '"isLiveBroadcast":true' in html_text
                        or '"status":"LIVE"' in html_text
                        or 'badge-style-type-live-now' in html_text
                    )

                    if is_live:
                        # Extract stream title
                        t_match = re.search(r'<meta property="og:title" content="([^"]+)"', html_text)
                        title = html.unescape(t_match.group(1)) if t_match else "Live Stream"

                        # Extract thumbnail
                        thumb = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                        return True, video_id, title, thumb

                # B: Backup check via RSS feed for new video entries
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                async with session.get(rss_url) as rss_resp:
                    if rss_resp.status == 200:
                        rss_text = await rss_resp.text()
                        if "<yt:videoId>" in rss_text:
                            root = ET.fromstring(rss_text)
                            entries = root.findall("{http://www.w3.org/2005/Atom}entry")
                            if entries:
                                first_entry = entries[0]
                                v_id_elem = first_entry.find("{http://www.youtube.com/xml/schemas/2015}videoId")
                                title_elem = first_entry.find("{http://www.w3.org/2005/Atom}title")
                                if v_id_elem is not None and v_id_elem.text:
                                    v_id = v_id_elem.text
                                    v_title = title_elem.text if title_elem is not None else "New Stream"
                                    # Verify if this specific video is live
                                    v_url = f"https://www.youtube.com/watch?v={v_id}"
                                    async with session.get(v_url) as v_resp:
                                        if v_resp.status == 200:
                                            v_html = await v_resp.text()
                                            if '"isLive":true' in v_html or '"isLiveContent":true' in v_html:
                                                thumb = f"https://i.ytimg.com/vi/{v_id}/maxresdefault.jpg"
                                                return True, v_id, v_title, thumb
        except Exception as e:
            logger.debug(f"Notice checking live status for {channel_id}: {e}")

        return False, None, None, None

    # ─── DISPATCH NOTIFICATION ───────────────────────────────────────────────

    async def dispatch_live_announcement(
        self,
        sub: dict[str, Any],
        video_id: str,
        title: str,
        thumbnail_url: str,
    ) -> None:
        """Send live stream card into configured Discord text channel."""
        guild = self.bot.get_guild(int(sub["guild_id"]))
        if not guild:
            return

        channel = guild.get_channel(int(sub["discord_channel_id"]))
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return

        stream_url = f"https://www.youtube.com/watch?v={video_id}"
        ping_role_id = sub.get("ping_role_id")
        ping_role = guild.get_role(int(ping_role_id)) if ping_role_id else None

        # Build ping text
        if ping_role:
            mention_str = ping_role.mention
        elif ping_role_id == -1:  # -1 represents @everyone
            mention_str = "@everyone"
        elif ping_role_id == -2:  # -2 represents @here
            mention_str = "@here"
        else:
            mention_str = ""

        ch_name = sub.get("yt_channel_name") or "YouTube Creator"
        custom_msg = sub.get("custom_message")
        if custom_msg:
            lead_text = (
                custom_msg.replace("{channel}", ch_name)
                .replace("{title}", title)
                .replace("{url}", stream_url)
                .replace("{role}", mention_str)
            )
        else:
            lead_text = f"🔴 **{ch_name}** is now **LIVE** on YouTube! {mention_str}".strip()

        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")
        container = KyokaContainer(accent_color=15548997)  # Red for Live
        container.add_section(
            content=(
                f"🔴 **LIVE BROADCAST STARTED**\n"
                f"> **[{title}]({stream_url})**\n\n"
                f"{arrow} **Streamer:** `{ch_name}`\n"
                f"{arrow} **Watch Now:** [Click to open YouTube Stream]({stream_url})"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# YouTube Live Notification • Sent to #{channel.name}")

        # Add Watch Button Action Row
        btn_action_row: dict[str, Any] = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 5,  # Link button
                    "label": "Watch Live Stream 📺",
                    "url": stream_url,
                }
            ],
        }
        container.components.append(btn_action_row)

        try:
            await send_container_response(channel, container, content=lead_text)
            logger.info(f"Dispatched YouTube live notification for {ch_name} ({video_id}) to {guild.name} #{channel.name}.")
        except Exception as e:
            logger.error(f"Failed to send live notification in {guild.name}: {e}")

    # ─── BACKGROUND POLLING MONITOR LOOP ─────────────────────────────────────

    @tasks.loop(seconds=120.0)
    async def live_monitor_loop(self) -> None:
        """Polls monitored YouTube channels every 120 seconds to detect live broadcasts."""
        if not hasattr(self.bot, "db") or not self.bot.db:
            return

        async with self._checking_lock:
            try:
                subs = await self.bot.db.fetch_all("SELECT * FROM youtube_live_subscriptions;")
                if not subs:
                    return

                for sub in subs:
                    ch_id = sub["yt_channel_id"]
                    is_live, video_id, title, thumbnail = await self.check_channel_live(ch_id)

                    last_vid = sub.get("last_live_video_id")
                    was_live = bool(sub.get("is_live", False))

                    if is_live and video_id:
                        # New live stream detected!
                        if not was_live or last_vid != video_id:
                            await self.dispatch_live_announcement(sub, video_id, title or "Live Stream", thumbnail or "")
                            await self.bot.db.execute(
                                """
                                UPDATE youtube_live_subscriptions
                                SET is_live = TRUE, last_live_video_id = $1, last_checked = CURRENT_TIMESTAMP
                                WHERE id = $2;
                                """,
                                video_id,
                                sub["id"],
                            )
                    else:
                        # Stream has ended
                        if was_live:
                            await self.bot.db.execute(
                                """
                                UPDATE youtube_live_subscriptions
                                SET is_live = FALSE, last_checked = CURRENT_TIMESTAMP
                                WHERE id = $1;
                                """,
                                sub["id"],
                            )

                    # Yield to event loop between channel checks
                    await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"Error in YouTube live monitor loop: {e}", exc_info=e)

    @live_monitor_loop.before_loop
    async def before_live_monitor(self) -> None:
        await self.bot.wait_until_ready()

    # ─── USER COMMANDS ───────────────────────────────────────────────────────

    @commands.group(name="ytlive", aliases=["youtubelive", "ytpinger", "ytping"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def ytlive_group(self, ctx: CustomContext) -> None:
        """Manage YouTube live notification pinger."""
        await ctx.invoke(self.ytlive_list_cmd)

    @ytlive_group.command(name="add", description="Add a YouTube channel to monitor for live streams.")
    @commands.has_permissions(manage_guild=True)
    async def ytlive_add_cmd(
        self,
        ctx: CustomContext,
        channel_query: str,
        announcement_channel: Optional[discord.TextChannel] = None,
        ping_role: Optional[discord.Role] = None,
    ) -> None:
        """
        Add a YouTube channel to monitor.
        Usage: ?ytlive add <@handle_or_url> [#channel] [@role]
        """
        target_channel = announcement_channel or ctx.channel
        await ctx.defer()

        # Resolve YouTube Channel Details
        channel_id, channel_name, handle = await self.resolve_channel_info(channel_query)
        if not channel_id:
            return await ctx.send_error(
                f"Could not find YouTube channel for query: `{channel_query}`.\n"
                "Please provide a valid YouTube channel URL (e.g. `https://youtube.com/@ChannelHandle`) or Channel ID."
            )

        role_id = ping_role.id if ping_role else None

        # Persist to database
        await self.bot.db.execute(
            """
            INSERT INTO youtube_live_subscriptions (
                guild_id, yt_channel_id, yt_channel_name, yt_handle,
                discord_channel_id, ping_role_id
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (guild_id, yt_channel_id) DO UPDATE SET
                discord_channel_id = EXCLUDED.discord_channel_id,
                ping_role_id = EXCLUDED.ping_role_id,
                yt_channel_name = EXCLUDED.yt_channel_name;
            """,
            ctx.guild.id,
            channel_id,
            channel_name or channel_id,
            handle,
            target_channel.id,
            role_id,
        )

        role_desc = ping_role.mention if ping_role else "`None`"
        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")

        c = KyokaContainer(accent_color=5763719)  # Green
        c.add_section(
            content=(
                "🔴 **YouTube Live Pinger Configured**\n"
                f"> Now monitoring **{channel_name}** for live broadcasts!\n\n"
                f"{arrow} **Channel:** [{channel_name}](https://www.youtube.com/channel/{channel_id})\n"
                f"{arrow} **Announcement Channel:** {target_channel.mention}\n"
                f"{arrow} **Ping Role:** {role_desc}\n"
                f"> *When this creator goes live, a notification will be sent automatically.*"
            )
        )
        await send_container_response(ctx, c)

    @ytlive_group.command(name="remove", aliases=["delete"], description="Remove a YouTube channel from live monitoring.")
    @commands.has_permissions(manage_guild=True)
    async def ytlive_remove_cmd(self, ctx: CustomContext, *, channel_query: str) -> None:
        """Remove a YouTube channel from live monitoring."""
        subs = await self.bot.db.fetch_all(
            "SELECT * FROM youtube_live_subscriptions WHERE guild_id = $1;",
            ctx.guild.id,
        )
        if not subs:
            return await ctx.send_warning("No YouTube live channels are currently monitored in this server.")

        q_low = channel_query.strip().lower()
        matched = None
        for s in subs:
            if (
                s["yt_channel_id"].lower() == q_low
                or (s.get("yt_handle") and s["yt_handle"].lower() == q_low)
                or (s.get("yt_channel_name") and s["yt_channel_name"].lower() == q_low)
                or q_low in (s.get("yt_channel_name") or "").lower()
            ):
                matched = s
                break

        if not matched:
            return await ctx.send_error(f"Could not find a monitored channel matching `{channel_query}`.")

        await self.bot.db.execute(
            "DELETE FROM youtube_live_subscriptions WHERE id = $1;",
            matched["id"],
        )
        await ctx.send_success(f"Removed **{matched['yt_channel_name']}** from YouTube live monitoring.")

    @ytlive_group.command(name="list", description="List all monitored YouTube channels in this server.")
    @commands.has_permissions(manage_guild=True)
    async def ytlive_list_cmd(self, ctx: CustomContext) -> None:
        """List all YouTube channels configured for live announcements."""
        subs = await self.bot.db.fetch_all(
            "SELECT * FROM youtube_live_subscriptions WHERE guild_id = $1 ORDER BY id ASC;",
            ctx.guild.id,
        )
        if not subs:
            return await ctx.send_warning(
                "No YouTube channels are currently monitored.\n"
                "Use `?ytlive add <@handle_or_url> [#channel] [@role]` to add one!"
            )

        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")
        lines = []
        for i, s in enumerate(subs, start=1):
            ch_obj = ctx.guild.get_channel(int(s["discord_channel_id"]))
            ch_disp = ch_obj.mention if ch_obj else f"<#{s['discord_channel_id']}>"
            r_obj = ctx.guild.get_role(int(s["ping_role_id"])) if s.get("ping_role_id") else None
            r_disp = r_obj.mention if r_obj else "`None`"
            status = "🔴 **LIVE NOW**" if s.get("is_live") else "⚪ *Offline*"

            lines.append(
                f"**{i}. [{s['yt_channel_name']}](https://youtube.com/channel/{s['yt_channel_id']})** {status}\n"
                f"> {arrow} Post In: {ch_disp} • Ping: {r_disp}"
            )

        c = KyokaContainer()
        c.add_section(
            content=f"🔴 **Monitored YouTube Live Channels • {ctx.guild.name}**\n\n" + "\n\n".join(lines)
        )
        c.add_separator(divider=True)
        c.add_text("-# Polled every 2 minutes for zero-latency live notifications.")
        await send_container_response(ctx, c)

    @ytlive_group.command(name="check", description="Force an immediate check for all monitored channels.")
    @commands.has_permissions(manage_guild=True)
    async def ytlive_check_cmd(self, ctx: CustomContext) -> None:
        """Trigger an instant live stream check."""
        subs = await self.bot.db.fetch_all(
            "SELECT * FROM youtube_live_subscriptions WHERE guild_id = $1;",
            ctx.guild.id,
        )
        if not subs:
            return await ctx.send_warning("No YouTube live channels configured to check.")

        await ctx.defer()
        checked_count = 0
        live_count = 0

        for sub in subs:
            ch_id = sub["yt_channel_id"]
            is_live, video_id, title, thumbnail = await self.check_channel_live(ch_id)
            checked_count += 1
            if is_live and video_id:
                live_count += 1
                await self.dispatch_live_announcement(sub, video_id, title or "Live Stream", thumbnail or "")
                await self.bot.db.execute(
                    "UPDATE youtube_live_subscriptions SET is_live = TRUE, last_live_video_id = $1 WHERE id = $2;",
                    video_id, sub["id"],
                )

        await ctx.send_success(
            f"Checked **{checked_count}** channel(s). **{live_count}** channel(s) are currently streaming LIVE!"
        )

    @ytlive_group.command(name="message", description="Set custom ping message format.")
    @commands.has_permissions(manage_guild=True)
    async def ytlive_message_cmd(self, ctx: CustomContext, *, message_template: str) -> None:
        """
        Customize announcement message format.
        Variables: {channel}, {title}, {url}, {role}
        """
        clean = message_template.strip()
        await self.bot.db.execute(
            "UPDATE youtube_live_subscriptions SET custom_message = $1 WHERE guild_id = $2;",
            clean, ctx.guild.id,
        )
        await ctx.send_success(f"Custom live message updated for all channels in this server:\n> `{clean}`")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(YouTubeLivePinger(bot))

