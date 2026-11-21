from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.ui.response import KyokaResponse, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class SlowmodeCog(commands.Cog):
    """Channel slowmode rate limiting tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="slowmode",
        description="Set slowmode delay for a channel (0 to disable, max 21600s).",
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to 21600)",
        channel="Channel to adjust (defaults to current)",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(
        self,
        ctx: CustomContext,
        seconds: int = 0,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Set channel slowmode delay."""
        if seconds < 0 or seconds > 21600:
            resp = KyokaResponse.warning(
                title="Invalid Seconds",
                description="Slowmode seconds must be between `0` and `21600` (6 hours).",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            resp = KyokaResponse.warning(
                title="Error",
                description="Slowmode only applies to text channels.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        await target_channel.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author}")

        title = "Slowmode Disabled" if seconds == 0 else "Slowmode Updated"
        desc = (
            f"Slowmode has been disabled for {target_channel.mention}."
            if seconds == 0
            else f"Slowmode set to `{seconds}` seconds in {target_channel.mention}."
        )
        resp = KyokaResponse.success(
            title=title,
            description=desc,
            fields=[
                ("Channel", target_channel.mention, True),
                ("Delay", f"`{seconds}s`" if seconds > 0 else "`Disabled`", True),
                ("Moderator", f"**{ctx.author.display_name}**", True),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the SlowmodeCog into KyokaBot."""
    await bot.add_cog(SlowmodeCog(bot))
