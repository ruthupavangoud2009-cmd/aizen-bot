from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.utils.containers import KyokaContainer, send_container_response

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
            container = KyokaContainer(accent_color=None)
            container.add_section(content=f"**Cannot Moderate Member**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        try:
            dm_container = KyokaContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You were kicked from {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Kick", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Member Kicked**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{member.display_name}** `「{member.id}」`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

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
            container = KyokaContainer(accent_color=None)
            container.add_section(content=f"**Cannot Moderate Member**\n> {err_msg}")
            return await send_container_response(ctx, container)

        old_nick = member.display_name
        new_nick = nickname.strip() if nickname else None

        try:
            await member.edit(nick=new_nick, reason=f"{ctx.author} ({ctx.author.id}) changed nickname")
        except discord.Forbidden:
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> I lack the necessary permissions or role hierarchy to modify this user's nickname.")
            return await send_container_response(ctx, container)

        action_name = "Nickname Reset" if not new_nick else "Nickname Changed"
        await dispatch_mod_log(self.bot, ctx.guild, action_name, member, ctx.author, f"From '{old_nick}' to '{new_nick or member.name}'")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(content=f"**{action_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{member.mention}** `「{member.id}」`\n"
            f"{dot} **Previous Nick:** `{old_nick}`\n"
            f"{dot} **New Nick:** `{new_nick or member.name}`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    """Load the KickCog into KyokaBot."""
    await bot.add_cog(KickCog(bot))
