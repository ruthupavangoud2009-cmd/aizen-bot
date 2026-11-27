from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import (
    OWNER_ID,
    add_bot_staff,
    audit,
    get_all_bot_staff,
    is_bot_staff,
    is_primary_owner,
    remove_bot_staff,
)
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import em

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Developer.BotStaff")


class BotStaffCog(commands.Cog, name="Developer-BotStaff"):
    """Bot Staff management cog granting full bot permissions across all servers (except spam)."""
    category: str = "Developer"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.group(
        name="botstaff",
        aliases=["bstaff", "staffbot"],
        invoke_without_command=True,
        description="Manage Bot Staff who hold all bot permissions (except spam).",
    )
    async def botstaff(self, ctx: CustomContext) -> None:
        """Overview of Bot Staff management commands."""
        if not is_primary_owner(ctx.author.id):
            return await ctx.send(f"{em(self.bot, 'LOCK')} You are not authorized to view bot staff management.", delete_after=6)

        prefix = ctx.prefix or "+"
        e_shield = em(self.bot, "ANTINUKE", animated=True)
        e_arrow = em(self.bot, "ARROW")
        container = KyokaContainer(accent_color=0x7C3AED)
        container.add_section(
            content=(
                f"**{e_shield} Kyoka 3.0 — Bot Staff System**\n"
                f"> Bot staff can use server commands and moderation across servers, and manage premium.\n"
                f"> *(Global owner controls and Bot Staff management stay owner-only; spam is capped at 20 and cannot target the owner.)*\n\n"
                f"**Commands:**\n"
                f"> {e_arrow} `{prefix}botstaff list` — List all active bot staff members\n"
                f"> {e_arrow} `{prefix}botstaff add <@user | id>` — Grant bot staff permissions *(Owner only)*\n"
                f"> {e_arrow} `{prefix}botstaff remove <@user | id>` — Revoke bot staff permissions *(Owner only)*"
            )
        )
        staff_ids = get_all_bot_staff()
        container.add_separator(divider=True)
        container.add_text(f"-# Active Bot Staff: {len(staff_ids)} member(s) | Primary Owner: <@{OWNER_ID}>")
        await send_container_response(ctx, container)

    @botstaff.command(name="list", description="List all active Bot Staff members.")
    async def staff_list(self, ctx: CustomContext) -> None:
        """List all active bot staff members."""
        if not is_primary_owner(ctx.author.id):
            return await ctx.send(f"{em(self.bot, 'LOCK')} You are not authorized to view bot staff.", delete_after=6)

        e_shield = em(self.bot, "ANTINUKE", animated=True)
        e_crown = em(self.bot, "CROWN")
        e_arrow = em(self.bot, "ARROW")
        staff_ids = get_all_bot_staff()
        embed = discord.Embed(
            title=f"{e_shield} Kyoka 3.0 — Active Bot Staff Directory",
            description=(
                "Bot staff can use server commands and moderation across servers, and manage premium. "
                "Spam is limited to 20 messages and cannot target the primary owner. "
                "Global owner controls and Bot Staff management remain owner-only."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name=f"{e_crown} Primary Bot Owner",
            value=f"<@{OWNER_ID}> (`{OWNER_ID}`)",
            inline=False,
        )

        if staff_ids:
            staff_entries = []
            for uid in staff_ids:
                u = self.bot.get_user(uid)
                tag = f"{u.name}" if u else "Unknown User"
                staff_entries.append(f"{e_arrow} <@{uid}> (`{uid}`) — **{tag}**")
            embed.add_field(
                name=f"{e_shield} Bot Staff Members ({len(staff_ids)})",
                value="\n".join(staff_entries),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"{e_shield} Bot Staff Members (0)",
                value="*No additional bot staff currently registered.*",
                inline=False,
            )

        embed.set_footer(text="Kyoka Staff System • High Privilege Security Tier")
        await ctx.send(embed=embed)

    @botstaff.command(name="add", description="Add a user as Bot Staff (Primary Owner only).")
    @app_commands.describe(user="The user or user ID to grant bot staff permissions")
    async def staff_add(self, ctx: CustomContext, *, user: str) -> None:
        """Grant bot staff permissions to a user."""
        if not is_primary_owner(ctx.author.id):
            return await ctx.send(f"{em(self.bot, 'LOCK')} Only the primary bot owner can appoint bot staff.", delete_after=6)

        clean = user.strip("<@!> ")
        target_id: int | None = None
        target_user: discord.User | None = None

        if clean.isdigit():
            target_id = int(clean)
            target_user = self.bot.get_user(target_id)
            if not target_user:
                try:
                    target_user = await self.bot.fetch_user(target_id)
                except Exception:
                    pass
        elif ctx.message.mentions:
            target_user = ctx.message.mentions[0]
            target_id = target_user.id

        if not target_id:
            return await ctx.send(f"{em(self.bot, 'ERROR')} Could not resolve user. Provide a valid mention or ID.")

        if target_id == OWNER_ID:
            return await ctx.send(f"{em(self.bot, 'CROWN')} This user is already the primary bot owner.")

        if is_bot_staff(target_id):
            return await ctx.send(f"{em(self.bot, 'WARNING')} <@{target_id}> is already registered as Bot Staff.")

        add_bot_staff(target_id)
        if hasattr(self.bot, "no_prefix_users"):
            self.bot.no_prefix_users.add(target_id)
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    "INSERT INTO system_bot_staff (user_id, added_by) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING;",
                    target_id,
                    ctx.author.id,
                )
            except Exception as e:
                logger.debug("Notice persisting bot staff to DB: %s", e)

        await audit(self.bot, ctx.author.id, "botstaff-add", target_id, "success")
        display = target_user.name if target_user else str(target_id)
        await ctx.send(
            f"{em(self.bot, 'SUCCESS', animated=True)} Successfully granted **Bot Staff** permissions to <@{target_id}> (`{display}`).\n"
            f"> They can use server commands and moderation across servers and manage premium. "
            f"Spam is limited to 20 messages and cannot target the primary owner."
        )

    @botstaff.command(name="remove", description="Remove a user from Bot Staff (Primary Owner only).")
    @app_commands.describe(user="The user or user ID to remove from bot staff")
    async def staff_remove(self, ctx: CustomContext, *, user: str) -> None:
        """Revoke bot staff permissions from a user."""
        if not is_primary_owner(ctx.author.id):
            return await ctx.send(f"{em(self.bot, 'LOCK')} Only the primary bot owner can remove bot staff.", delete_after=6)

        clean = user.strip("<@!> ")
        target_id: int | None = None
        if clean.isdigit():
            target_id = int(clean)
        elif ctx.message.mentions:
            target_id = ctx.message.mentions[0].id

        if not target_id:
            return await ctx.send(f"{em(self.bot, 'ERROR')} Could not resolve user. Provide a valid mention or ID.")

        if target_id == OWNER_ID:
            return await ctx.send(f"{em(self.bot, 'ERROR')} Cannot remove the primary bot owner.")

        if not is_bot_staff(target_id) or target_id not in get_all_bot_staff():
            return await ctx.send(f"{em(self.bot, 'WARNING')} <@{target_id}> is not in the Bot Staff registry.")

        remove_bot_staff(target_id)
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute("DELETE FROM system_bot_staff WHERE user_id = $1;", target_id)
            except Exception as e:
                logger.debug("Notice removing bot staff from DB: %s", e)
        await audit(self.bot, ctx.author.id, "botstaff-remove", target_id, "success")
        await ctx.send(f"{em(self.bot, 'DELETE')} Successfully removed <@{target_id}> (`{target_id}`) from Bot Staff.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(BotStaffCog(bot))
