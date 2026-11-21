from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, parse_duration, dispatch_mod_log
from src.ui.response import KyokaResponse, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class TimeoutCog(commands.Cog):
    """Server timeout and unmute moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="timeout",
        aliases=["mute"],
        description="Timeout a member for a specified duration (e.g., 10m, 1h, 1d).",
    )
    @app_commands.describe(
        member="Member to timeout",
        duration="Duration (e.g. 10m, 1h, 1d, max 28d)",
        reason="Reason for timeout",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: CustomContext,
        member: discord.Member,
        duration: str = "10m",
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Timeout/mute a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        delta = parse_duration(duration)
        if not delta:
            resp = KyokaResponse.warning(
                title="Invalid Duration Format",
                description="Please use format: `10s`, `15m`, `2h`, or `7d` (Max: `28d`).",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        if delta > datetime.timedelta(days=28):
            resp = KyokaResponse.warning(
                title="Duration Exceeded",
                description="Discord maximum timeout duration is 28 days.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        until = discord.utils.utcnow() + delta
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Timeout", member, ctx.author, reason, extra=f"Duration: {duration}")

        resp = KyokaResponse.moderation(
            action="timeout",
            target=member,
            moderator=ctx.author,
            reason=reason,
            extra_fields=[("Duration", f"`{duration}` (Expires: <t:{int(until.timestamp())}:R>)", False)],
        )
        await send_response(ctx, resp)

    @commands.hybrid_command(
        name="unmute",
        aliases=["untimeout"],
        description="Remove timeout from a member.",
    )
    @app_commands.describe(member="Member to remove timeout from", reason="Reason for removing timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def unmute(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Remove timeout/unmute a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Timeout Removed", member, ctx.author, reason)

        resp = KyokaResponse.moderation(
            action="untimeout",
            target=member,
            moderator=ctx.author,
            reason=reason,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the TimeoutCog into KyokaBot."""
    await bot.add_cog(TimeoutCog(bot))
