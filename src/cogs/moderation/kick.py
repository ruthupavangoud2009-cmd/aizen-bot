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


class KickCog(commands.Cog):
    """Server kick moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="kick",
        description="Kick a member from the server.",
    )
    @app_commands.describe(member="Member to kick", reason="Reason for kicking")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Kick a member from the server."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        try:
            dm_resp = KyokaResponse.moderation(
                action="kicked",
                target=member,
                moderator=ctx.author,
                reason=reason,
                extra_fields=[("Server", ctx.guild.name, True)],
            )
            await send_response(member, dm_resp)
        except Exception:
            pass

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Kick", member, ctx.author, reason)

        resp = KyokaResponse.moderation("kick", member, ctx.author, reason)
        await send_response(ctx, resp)

    @commands.command(
        name="nick",
        aliases=["nickname", "setnick"],
        description="Change or reset a member's server nickname.",
    )
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @commands.guild_only()
    async def nick(self, ctx: CustomContext, member: discord.Member, *, nickname: str | None = None) -> None:
        """Change or reset a member's nickname."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            return await send_response(ctx, resp, ephemeral=True)

        old_nick = member.display_name
        new_nick = nickname.strip() if nickname else None

        try:
            await member.edit(nick=new_nick, reason=f"{ctx.author} ({ctx.author.id}) changed nickname")
        except discord.Forbidden:
            resp = KyokaResponse.permission(
                "Permission Denied",
                "I lack the necessary permissions or role hierarchy to modify this user's nickname.",
            )
            return await send_response(ctx, resp, ephemeral=True)

        action_name = "Nickname Reset" if not new_nick else "Nickname Changed"
        await dispatch_mod_log(self.bot, ctx.guild, action_name, member, ctx.author, f"From '{old_nick}' to '{new_nick or member.name}'")

        resp = KyokaResponse.success(
            title=action_name,
            description=f"Successfully updated nickname for {member.mention}.",
            fields=[
                ("Target", f"**{member}** `「{member.id}」`", True),
                ("Previous Nick", f"`{old_nick}`", True),
                ("New Nick", f"`{new_nick or member.name}`", True),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the KickCog into KyokaBot."""
    await bot.add_cog(KickCog(bot))
