"""Shortcut command for creating fully configured ticket panels."""

from __future__ import annotations

import discord
from discord.ext import commands

from src.core.bot import KyokaBot
from src.core.context import CustomContext
from src.cogs.ticket.ticket_system import TicketSetupWizard
from src.utils.containers import send_container_response


class TicketPanelShortcut(commands.Cog):
    """Expose the ticket-panel wizard under the requested easy-to-remember command."""

    category = "Ticket"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="newticketpannel",
        aliases=["newticketpanel"],
        description="Create and customize a new interactive ticket panel.",
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def newticketpannel(self, ctx: CustomContext) -> None:
        """Launch the existing multi-step ticket panel builder."""
        if ctx.guild is None:
            return await ctx.send_error("This command can only be used inside a server.")

        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer()

        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        wizard = TicketSetupWizard(self.bot.get_cog("TicketSystem"), ctx.author, templates=templates)
        panel = wizard.get_dashboard_container(ctx.guild)
        await send_container_response(ctx, panel, view=wizard)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(TicketPanelShortcut(bot))
