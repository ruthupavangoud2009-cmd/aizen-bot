from __future__ import annotations

import math
import platform
from urllib.parse import urlsplit
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import resolve_emoji

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

OWNER_ID = 1505515188991033409


def _valid_http_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class BotInfoView(discord.ui.View):
    """Link buttons for configured invite and official support pages."""

    def __init__(self, invite_url: str | None = None) -> None:
        super().__init__(timeout=None)
        if _valid_http_url(invite_url):
            self.add_item(
                discord.ui.Button(
                    label="Invite KYOKA",
                    style=discord.ButtonStyle.link,
                    url=invite_url,
                )
            )
        self.add_item(
            discord.ui.Button(
                label="Join Support Server",
                style=discord.ButtonStyle.link,
                url=Config.SUPPORT_URL,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Official Website",
                style=discord.ButtonStyle.link,
                url="https://aizen-bot.pages.dev/",
            )
        )


def build_botinfo_container(bot: KyokaBot, guild_id: int | None = None) -> KyokaContainer:
    """Build public bot information without depending on optional Discord state."""
    now = discord.utils.utcnow()
    start_time = getattr(bot, "start_time", now)
    uptime_seconds = max(0, int((now - start_time).total_seconds()))
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    uptime = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

    gateway_latency = getattr(bot, "latency", float("nan"))
    gateway_ping = (
        f"{round(gateway_latency * 1000)} ms"
        if isinstance(gateway_latency, (int, float)) and math.isfinite(gateway_latency)
        else "Unavailable"
    )
    guilds = getattr(bot, "guilds", ())
    total_members = sum(guild.member_count or 0 for guild in guilds)
    user = getattr(bot, "user", None)
    bot_name = getattr(user, "name", None) or Config.BOT_NAME
    bot_id = getattr(user, "id", None) or getattr(bot, "application_id", None)
    avatar_url = getattr(getattr(user, "display_avatar", None), "url", None)

    guild_manager = getattr(bot, "guild_mgr", None)
    prefix = guild_manager.get_prefix(guild_id) if guild_manager else Config.DEFAULT_PREFIX

    # Server-specific branding integration with strict isolation & fallback
    branding = None
    if hasattr(bot, "branding_mgr"):
        if guild_id:
            branding = bot.branding_mgr._cache.get(guild_id)
        if not branding:
            branding = bot.branding_mgr.get_default_branding()
    if branding:
        bot_name = branding.get("display_name") or bot_name
        avatar_url = branding.get("avatar_url") or avatar_url

    premium_manager = getattr(bot, "premium_mgr", None)
    premium_info = premium_manager.get_guild_info(guild_id) if premium_manager and guild_id else None
    premium_status = (
        f"{premium_info['tier']} (expires {premium_info['remaining_str']})"
        if premium_info and premium_info.get("is_premium")
        else "Manual access; ask in the support server"
    )
    support_url = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"

    brand_em = resolve_emoji(bot, "KYOKA")
    status_em = resolve_emoji(bot, "BOT_STATUS", prefer_animated=True)
    stats_em = resolve_emoji(bot, "STATS")
    prem_em = resolve_emoji(bot, "PREMIUM", prefer_animated=True)

    container = KyokaContainer()
    bio_text = branding.get("bio") if branding else "Power isn't given. It's taken. — Sosuke Aizen"
    bio_line = f"\n> **Bio:** {bio_text}" if bio_text else ""
    container.add_text(
        f"### {brand_em} {bot_name} Information\n"
        f"> **Creator:** Aizen\n"
        f"> **Owner ID:** `{OWNER_ID}`\n"
        f"> **Bot ID:** `{bot_id if bot_id is not None else 'Unavailable'}`{bio_line}"
    )
    if avatar_url:
        container.add_media(avatar_url)
    container.add_separator(divider=True)
    container.add_text(
        f"**{status_em} Status**\n"
        f"> **Uptime:** `{uptime}`\n"
        f"> **API latency:** `{gateway_ping}` • **Gateway ping:** `{gateway_ping}`\n"
        f"> **Servers:** `{len(guilds):,}` • **Members across servers:** `{total_members:,}` • **Members:** {total_members:,} Members\n\n"
        f"**{stats_em} Runtime**\n"
        f"> **Library:** `discord.py {discord.__version__}`\n"
        f"> **Python:** `{platform.python_version()}`\n\n"
        f"**{prem_em} Commands & Premium**\n"
        f"> **Prefix:** `{prefix}` • **Help:** `{prefix}help` or `/help`\n"
        f"> **Web Dashboard:** [aizen-bot.pages.dev](https://aizen-bot.pages.dev/)\n"
        f"> **Premium:** {premium_status}\n\n"
        f"-# Made by Aizen • [Official Website](https://aizen-bot.pages.dev/) • [Support Server]({support_url})"
    )
    return container


class BotInfo(commands.Cog):
    """Public bot identity, runtime, and performance information."""

    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.command(
        name="botemojis",
        aliases=["botemoji", "addbotemoji"],
        description="Upload a custom emoji to KYOKA's application emoji collection (owner only).",
    )
    async def botemojis(self, ctx: CustomContext, emoji_source: str | None = None, *, emoji_name: str | None = None) -> None:
        """Upload an attached image or server emoji into KYOKA's application emoji collection."""
        import re
        if ctx.author.id != OWNER_ID:
            await ctx.reply("Only the bot creator can manage KYOKA's application emojis.", delete_after=8)
            return
        if not self.bot.application_id:
            await ctx.reply("Application ID is not ready yet.", delete_after=8)
            return
        cached = getattr(getattr(self.bot, "custom_emojis", None), "_emojis", {})
        emoji_count = len({getattr(emoji, "id", id(emoji)) for emoji in cached.values()})
        if emoji_count >= 2000:
            await ctx.reply("KYOKA has reached Discord's application emoji limit (2,000/2,000). Delete an application emoji in the Developer Portal before adding another.", delete_after=10)
            return
        attachment = ctx.message.attachments[0] if getattr(ctx, "message", None) and ctx.message.attachments else None
        source_url = attachment.url if attachment else None
        default_name = attachment.filename.rsplit(".", 1)[0] if attachment else None
        if not source_url and emoji_source:
            match = re.fullmatch(r"<(a?):([A-Za-z0-9_]{2,32}):(\d{15,22})>", emoji_source.strip())
            if match:
                default_name = match.group(2)
                ext = "gif" if match.group(1) == "a" else "png"
                source_url = f"https://cdn.discordapp.com/emojis/{match.group(3)}.{ext}?quality=lossless"
        if not source_url:
            await ctx.reply("Attach a PNG/JPG/GIF image or provide a custom emoji mention. Example: `?botemojis <:name:123456789012345678>`.", delete_after=12)
            return
        requested_name = emoji_name or (emoji_source.strip().strip(":") if attachment and emoji_source else None) or default_name or "kyoka_emoji"
        name = requested_name.lower()
        name = re.sub(r"[^a-z0-9_]", "_", name)[:32].strip("_") or "kyoka_emoji"
        try:
            if attachment:
                image_bytes = await attachment.read()
            else:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(source_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status != 200:
                            await ctx.reply(f"Emoji source download failed (HTTP {response.status}).", delete_after=10)
                            return
                        image_bytes = await response.read()
            if len(image_bytes) > 256 * 1024:
                await ctx.reply("Emoji file must be 256 KB or smaller.", delete_after=10)
                return
            uploaded = await self.bot.create_application_emoji(name=name, image=image_bytes)
            cached[name] = uploaded
            await ctx.reply(f"Added {uploaded} as **{name}** to KYOKA's application emojis.")
        except discord.HTTPException as exc:
            await ctx.reply(f"Discord rejected this emoji upload: {exc}", delete_after=12)
        except Exception:
            await ctx.reply("Emoji upload failed. Check the file, permissions, and Discord's application emoji limits.", delete_after=12)

    @commands.hybrid_command(
        name="botinfo",
        aliases=["bi", "about", "info"],
        description="View KYOKA's identity, runtime, latency, and support information.",
    )
    async def botinfo(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else None
        if hasattr(self.bot, "branding_mgr") and guild_id:
            await self.bot.branding_mgr.get_branding(guild_id)
        invite_url = Config.INVITE_URL
        if not invite_url:
            invite_url = discord.utils.oauth_url(self.bot.application_id) if self.bot.application_id else None
        await send_container_response(
            ctx,
            build_botinfo_container(self.bot, guild_id),
            view=BotInfoView(invite_url),
        )


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(BotInfo(bot))
