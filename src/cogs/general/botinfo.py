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

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

SUPPORT_URL = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"
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
                url=SUPPORT_URL,
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
    premium_manager = getattr(bot, "premium_mgr", None)
    premium_info = premium_manager.get_guild_info(guild_id) if premium_manager and guild_id else None
    premium_status = (
        f"{premium_info['tier']} (expires {premium_info['remaining_str']})"
        if premium_info and premium_info.get("is_premium")
        else "Manual access; ask in the support server"
    )

    container = KyokaContainer()
    container.add_text(
        f"### {bot_name} Information\n"
        f"> **Creator:** Aizen\n"
        f"> **Owner ID:** `{OWNER_ID}`\n"
        f"> **Bot ID:** `{bot_id if bot_id is not None else 'Unavailable'}`"
    )
    if avatar_url:
        container.add_media(avatar_url)
    container.add_separator(divider=True)
    container.add_text(
        f"**Status**\n"
        f"> **Uptime:** `{uptime}`\n"
        f"> **API latency:** `{gateway_ping}` • **Gateway ping:** `{gateway_ping}`\n"
        f"> **Servers:** `{len(guilds):,}` • **Members across servers:** `{total_members:,}` • **Members:** {total_members:,} Members\n\n"
        f"**Runtime**\n"
        f"> **Library:** `discord.py {discord.__version__}`\n"
        f"> **Python:** `{platform.python_version()}`\n\n"
        f"**Commands & Premium**\n"
        f"> **Prefix:** `{prefix}` • **Help:** `{prefix}help` or `/help`\n"
        f"> **Web Dashboard:** [aizen-bot.pages.dev](https://aizen-bot.pages.dev/)\n"
        f"> **Premium:** {premium_status}\n\n"
        f"-# Made by Aizen • [Official Website](https://aizen-bot.pages.dev/) • [Support Server]({SUPPORT_URL})"
    )
    return container


class BotInfo(commands.Cog):
    """Public bot identity, runtime, and performance information."""

    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="botinfo",
        aliases=["bi", "about", "info"],
        description="View KYOKA's identity, runtime, latency, and support information.",
    )
    async def botinfo(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else None
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
