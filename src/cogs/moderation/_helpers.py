from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import resolve_emoji

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Moderation.Helpers")


def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """Parse duration string like '10s', '15m', '2h', '7d' into timedelta."""
    match = re.match(r"^(\d+)([smhd])$", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return datetime.timedelta(seconds=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    return None


def resolve_role(guild: discord.Guild, query: str) -> Optional[discord.Role]:
    """
    Resolve a role in the guild from:
    1. Role mention (<@&123456789>)
    2. Role ID (123456789)
    3. Exact role name (case-insensitive)
    4. Role name starting with query (case-insensitive)
    5. Substring match on role name (case-insensitive, ignoring @everyone)
    """
    clean_query = query.strip()
    if not clean_query:
        return None

    # 1. Mention check: <@&123456789>
    mention_match = re.match(r"^<@&(\d+)>$", clean_query)
    if mention_match:
        role_id = int(mention_match.group(1))
        return guild.get_role(role_id)

    # 2. Raw Digits (Role ID): 123456789
    if clean_query.isdigit():
        role = guild.get_role(int(clean_query))
        if role:
            return role

    clean_lower = clean_query.lower()

    # 3. Exact name match (case-insensitive)
    for r in guild.roles:
        if r.name.lower() == clean_lower:
            return r

    # 4. Starts with match (case-insensitive)
    for r in guild.roles:
        if r.name.lower().startswith(clean_lower):
            return r

    # 5. Substring match (case-insensitive, ignoring @everyone)
    for r in guild.roles:
        if not r.is_default() and clean_lower in r.name.lower():
            return r

    return None


from src.security.owner import OWNER_ID

def check_hierarchy(bot: KyokaBot, ctx: CustomContext, target: discord.Member) -> tuple[bool, str | None]:
    """Verify role hierarchy rules between author, bot, target, server owner, and primary bot owner."""
    if target.id == OWNER_ID:
        return False, "You cannot execute moderation actions against the bot owner."
    if target.id == ctx.author.id:
        return False, "You cannot execute moderation actions on yourself."
    if bot.user and target.id == bot.user.id:
        return False, "I cannot execute moderation actions on myself."
    if target.id == ctx.guild.owner_id:
        return False, "You cannot moderate the server owner."

    # Check author hierarchy (server owner bypasses)
    if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
        return False, "You cannot moderate this member because their highest role is equal to or higher than yours."

    # Check bot hierarchy
    if target.top_role >= ctx.guild.me.top_role:
        return False, "I cannot moderate this member because their highest role is equal to or higher than mine."

    return True, None


async def dispatch_mod_log(
    bot: KyokaBot,
    guild: discord.Guild,
    action: str,
    target: discord.User | discord.Member | None = None,
    moderator: discord.User | discord.Member | None = None,
    reason: Optional[str] = None,
    extra: Optional[str] = None,
    channel: Optional[discord.TextChannel | discord.Thread | discord.abc.GuildChannel] = None,
    duration: Optional[str] = None,
) -> Optional[int]:
    """Record a persistent moderation case and post an audit log card to the configured mod-log channel."""
    case_id: Optional[int] = None
    case_mgr = getattr(bot, "case_mgr", None)
    if case_mgr is not None and target is not None and moderator is not None:
        normalized_action = action.lower().replace("member ", "").replace("timeout removed", "untimeout").strip()
        try:
            case_id = await case_mgr.create_case(
                guild_id=guild.id,
                action=normalized_action,
                user_id=target.id,
                moderator_id=moderator.id,
                reason=reason or "No reason provided",
                duration=duration,
                notes=extra,
            )
        except Exception as case_err:
            logger.debug("Notice recording moderation case: %s", case_err)

    log_mgr = getattr(bot, "log_mgr", None)
    log_channel = log_mgr.get_log_channel(guild, "mod") if log_mgr else None
    if not log_channel:
        return case_id

    dot = resolve_emoji(bot, "ARROW", fallback="-")
    badge = resolve_emoji(bot, "MODERATION")
    badge_str = f"{badge} " if badge else ""
    case_suffix = f" (Case #{case_id})" if case_id is not None else ""

    container = KyokaContainer(accent_color=None)
    container.add_section(content=f"**{badge_str}Moderation Log — {action}{case_suffix}**")
    container.add_separator(divider=True)

    items = []
    if target is not None:
        target_name = getattr(target, "display_name", str(target))
        items.append(f"{dot} **Target:** **{target_name}** `「{target.id}」`")

    if channel is not None:
        items.append(f"{dot} **Channel:** {channel.mention}")

    if moderator is not None:
        mod_name = getattr(moderator, "display_name", str(moderator))
        items.append(f"{dot} **Moderator:** **{mod_name}** `「{moderator.id}」`")

    if extra and str(extra).strip():
        items.append(f"{dot} **Details:** `{str(extra).strip()}`")

    if reason and str(reason).strip() and str(reason).strip().lower() != "no reason provided":
        items.append(f"{dot} **Reason:** `{str(reason).strip()}`")

    container.add_text("\n".join(items) if items else f"{dot} Action completed successfully.")
    container.add_separator(divider=True)
    container.add_text(f"-# Timestamp: <t:{int(discord.utils.utcnow().timestamp())}:f>")

    try:
        await send_container_response(log_channel, container)
    except Exception as e:
        logger.warning(f"Failed to dispatch mod log in {guild.name}: {e}")
    return case_id
