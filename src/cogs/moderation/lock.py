from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import dispatch_mod_log
from src.ui.response import KyokaResponse, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class LockCog(commands.Cog):
    """Channel lock and unlock moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="lock",
        description="Lock a channel to prevent regular members from sending messages.",
    )
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason for locking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Lock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            resp = KyokaResponse.warning("Error", "Lock command only applies to text channels.", author=ctx.author)
            await send_response(ctx, resp, ephemeral=True)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(
            self.bot,
            ctx.guild,
            "Channel Lock",
            target=None,
            moderator=ctx.author,
            reason=reason,
            channel=target_channel,
        )

        resp = KyokaResponse.success(
            title="Channel Locked",
            description=f"Successfully locked {target_channel.mention} for regular members.",
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", f"**{ctx.author.display_name}** `「{ctx.author.id}」`", True),
                ("Reason", f"`{reason}`", False),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.hybrid_command(
        name="unlock",
        description="Unlock a channel to allow members to send messages.",
    )
    @app_commands.describe(channel="Channel to unlock (defaults to current)", reason="Reason for unlocking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Unlock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            resp = KyokaResponse.warning("Error", "Unlock command only applies to text channels.", author=ctx.author)
            await send_response(ctx, resp, ephemeral=True)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        # Check if Fun cog has a recorded original overwrite from a Guess a Number event
        fun_cog = getattr(self.bot, "get_cog", lambda _: None)("Fun")
        if fun_cog and hasattr(fun_cog, "_locked_channels_original_overwrites"):
            original = fun_cog._locked_channels_original_overwrites.pop(target_channel.id, None)
            overwrite.send_messages = original
        else:
            overwrite.send_messages = None
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(
            self.bot,
            ctx.guild,
            "Channel Unlock",
            target=None,
            moderator=ctx.author,
            reason=reason,
            channel=target_channel,
        )

        resp = KyokaResponse.success(
            title="Channel Unlocked",
            description=f"Successfully unlocked {target_channel.mention} for regular members.",
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", f"**{ctx.author.display_name}** `「{ctx.author.id}」`", True),
                ("Reason", f"`{reason}`", False),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="hide",
        description="Hide a channel from regular members by disabling view permissions.",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def hide(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Hide a channel from @everyone."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            resp = KyokaResponse.warning("Error", "Hide command only applies to text channels.", author=ctx.author)
            return await send_response(ctx, resp, ephemeral=True)

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        overwrite.read_messages = False
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(
            self.bot,
            ctx.guild,
            "Channel Hide",
            target=None,
            moderator=ctx.author,
            reason=reason,
            channel=target_channel,
        )

        resp = KyokaResponse.success(
            title="Channel Hidden",
            description=f"Successfully hid {target_channel.mention} from regular members.",
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", f"**{ctx.author.display_name}** `「{ctx.author.id}」`", True),
                ("Reason", f"`{reason}`", False),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="unhide",
        description="Unhide a channel to make it visible to regular members again.",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unhide(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Unhide a channel for @everyone."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            resp = KyokaResponse.warning("Error", "Unhide command only applies to text channels.", author=ctx.author)
            return await send_response(ctx, resp, ephemeral=True)

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = None
        overwrite.read_messages = None
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(
            self.bot,
            ctx.guild,
            "Channel Unhide",
            target=None,
            moderator=ctx.author,
            reason=reason,
            channel=target_channel,
        )

        resp = KyokaResponse.success(
            title="Channel Unhidden",
            description=f"Successfully unhid {target_channel.mention} for regular members.",
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", f"**{ctx.author.display_name}** `「{ctx.author.id}」`", True),
                ("Reason", f"`{reason}`", False),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the LockCog into KyokaBot."""
    await bot.add_cog(LockCog(bot))
