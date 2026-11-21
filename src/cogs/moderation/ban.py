from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.ui.response import KyokaResponse, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class BanCog(commands.Cog):
    """Server ban and unban moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="ban",
        description="Ban a member from the server.",
    )
    @app_commands.describe(member="Member to ban", reason="Reason for the ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Ban a member from the server."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        # Attempt DM notification
        try:
            dm_resp = KyokaResponse.moderation(
                action="banned",
                target=member,
                moderator=ctx.author,
                reason=reason,
                extra_fields=[("Server", ctx.guild.name, True)],
            )
            await send_response(member, dm_resp)
        except Exception:
            pass

        await ctx.guild.ban(member, reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_days=0)
        await dispatch_mod_log(self.bot, ctx.guild, "Member Ban", member, ctx.author, reason)

        resp = KyokaResponse.moderation("ban", member, ctx.author, reason)
        await send_response(ctx, resp)

    @commands.hybrid_command(
        name="unban",
        description="Unban a user by their user ID or tag.",
    )
    @app_commands.describe(user="User ID or mention to unban", reason="Reason for unbanning")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: CustomContext, user: discord.User, *, reason: str = "No reason provided") -> None:
        """Unban a previously banned user."""
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            resp = KyokaResponse.warning(
                title="Not Found",
                description="This user is not currently banned in this server.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        await dispatch_mod_log(self.bot, ctx.guild, "Member Unban", user, ctx.author, reason)

        resp = KyokaResponse.moderation("unban", user, ctx.author, reason)
        await send_response(ctx, resp)

    @commands.command(
        name="softban",
        description="Softban a member: kick them and purge their recent messages.",
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def softban(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Softban a member (ban and instantly unban to purge messages)."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        try:
            dm_resp = KyokaResponse.moderation(
                action="softbanned",
                target=member,
                moderator=ctx.author,
                reason=reason,
                extra_fields=[("Server", ctx.guild.name, True)],
            )
            await send_response(member, dm_resp)
        except Exception:
            pass

        await ctx.guild.ban(member, reason=f"{ctx.author} ({ctx.author.id}) [Softban]: {reason}", delete_message_days=1)
        await ctx.guild.unban(member, reason="Softban message purge unban")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Softban", member, ctx.author, reason)

        resp = KyokaResponse.moderation(
            action="softban",
            target=member,
            moderator=ctx.author,
            reason=reason,
            extra_fields=[("Messages Purged", "Last 24 Hours", True)],
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the BanCog into KyokaBot."""
    await bot.add_cog(BanCog(bot))
