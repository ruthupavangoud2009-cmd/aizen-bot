"""A polished Aizen-inspired introduction card for newly joined servers."""
from __future__ import annotations
import logging
import os
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit
import discord
from src.core.config import Config
if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Greetings")
AIZEN_ART = os.getenv("AIZEN_IMAGE_URL", "").strip()


def _valid_http_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

async def send_bot_mention_card(bot: KyokaBot, message: discord.Message) -> None:
    """Show bot prefix and quick links when a user mentions Kyoka."""
    prefix = bot.guild_mgr.get_prefix(message.guild.id if message.guild else None)
    latency = round(bot.latency * 1000) if bot.latency and bot.latency == bot.latency else 0
    embed = discord.Embed(
        title=f"⟡  {Config.BOT_NAME} • Aizen Edition",
        description=(
            f"**Greetings, {message.author.mention}.**\n"
            f"> A smarter, safer, and more connected Blox Fruits community experience.\n\n"
            f"• **Current Prefix:** `{prefix}`\n"
            f"• **Slash Commands:** `/`\n"
            f"• **Command Directory:** `{prefix}help`\n"
            f"• **WebSocket Latency:** `{latency} ms`"
        ),
        color=discord.Color.from_rgb(124, 58, 237),
    )
    if bot.user and hasattr(bot.user, "display_avatar"):
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Requested by {message.author.display_name} • KYOKA 3.0")
    view = discord.ui.View(timeout=None)
    if Config.INVITE_URL:
        view.add_item(discord.ui.Button(label="Invite KYOKA", style=discord.ButtonStyle.link, url=Config.INVITE_URL, emoji="✦"))
    view.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url=Config.SUPPORT_URL, emoji="💜"))
    try:
        await message.reply(embed=embed, view=view, mention_author=False)
    except (discord.HTTPException, discord.Forbidden):
        try:
            await message.channel.send(embed=embed, view=view)
        except Exception:
            pass


async def send_guild_welcome_card(bot: KyokaBot, guild: discord.Guild) -> None:
    """Thank the server for inviting KYOKA, using a standard Discord embed for compatibility."""
    logger.info("Joined new guild: %s (%s)", guild.name, guild.id)
    me = guild.me
    if me is None and bot.user:
        me = guild.get_member(bot.user.id)
    if me is None:
        logger.warning("Cannot resolve bot member in newly joined guild %s", guild.id)
        return
    target: Optional[discord.TextChannel] = None
    candidates = ([guild.system_channel] if guild.system_channel else []) + list(guild.text_channels)
    seen: set[int] = set()
    for channel in candidates:
        if channel is None or channel.id in seen:
            continue
        seen.add(channel.id)
        perms = channel.permissions_for(me)
        if perms.view_channel and perms.send_messages and perms.embed_links:
            target = channel
            break
    if target is None:
        logger.warning("No writable channel for join welcome in %s (%s)", guild.name, guild.id)
        return
    prefix = bot.guild_mgr.get_prefix(guild.id)
    embed = discord.Embed(
        title="⟡  Thanks for inviting KYOKA!",
        description=(
            f"**Welcome to {guild.name}.**\n"
            "The illusion begins now. Thanks for bringing **KYOKA**, crafted by **Aizen**, into your server.\n\n"
            "╭・**Get started**\n"
            f"├・Prefix commands: `{prefix}help`\n"
            "├・Slash commands: `/`\n"
            "╰・Use the support button below if you need help.\n\n"
            "**Tip:** Make sure KYOKA has permission to view and send messages in your chosen channel."
        ), color=discord.Color.from_rgb(100, 55, 180)
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    if _valid_http_url(AIZEN_ART):
        embed.set_image(url=AIZEN_ART)
    embed.set_footer(text="Made by Aizen • KYOKA Community")
    view = discord.ui.View(timeout=None)
    if Config.INVITE_URL:
        view.add_item(discord.ui.Button(label="Invite KYOKA", style=discord.ButtonStyle.link, url=Config.INVITE_URL, emoji="✦"))
    view.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url=Config.SUPPORT_URL, emoji="💜"))
    try:
        await target.send(embed=embed, view=view)
    except discord.Forbidden:
        logger.warning("Missing send/embed permission in %s (%s)", target.name, guild.id)
    except Exception:
        logger.exception("Failed to send guild join welcome in %s", guild.id)
