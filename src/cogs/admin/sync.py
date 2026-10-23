from __future__ import annotations

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer, is_owner
from src.utils.containers import KyokaContainer, send_container_response


class Sync(commands.Cog):
    """Developer and Admin command synchronization tools."""
    category: str = "Developer"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="sync",
        description="Sync application commands globally or to the current guild.",
        hidden=True,
    )
    @is_owner()
    async def sync_tree(
        self, ctx: CustomContext, scope: str = "global"
    ) -> None:
        """
        Clean & Sync slash commands.
        Usage:
          +sync         -> Syncs all slash commands globally across Discord.
          +sync guild   -> Forces instant guild-only copy to this server for immediate testing.
          +sync clear   -> Clears guild-specific commands in this server.
        """
        scope_clean = scope.lower().strip()
        guild = ctx.guild

        if scope_clean in ["guild", "local"]:
            if guild:
                self.bot.tree.copy_global_to(guild=guild)
                synced_guild = await self.bot.tree.sync(guild=guild)
                msg = (
                    f"Successfully synced `{len(synced_guild)}` slash commands to **{guild.name}**.\n"
                    f"> (Instant propagation: visible in this server immediately!)"
                )
            else:
                msg = "Guild not found. Cannot perform guild sync in DM."
        elif scope_clean == "clear":
            if guild:
                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)
                msg = f"Cleared guild-specific commands in **{guild.name}**."
            else:
                msg = "Guild not found."
        else:
            # Default +sync: Global command sync
            synced_global = await self.bot.tree.sync()
            msg = (
                f"Successfully synced `{len(synced_global)}` slash commands globally.\n"
                f"> (Note: Global Discord updates take 10-60 minutes to appear in client caches. Use `+sync guild` for instant testing in this server.)"
            )

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Slash Commands Synchronized**\n"
                f"> {msg}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.command(
        name="syncemojis",
        aliases=["emojisync", "uploademojis"],
        description="Scan assets folders and sync custom application emojis to Discord.",
        hidden=True,
    )
    @is_developer()
    async def sync_emojis(self, ctx: CustomContext) -> None:
        load_card = KyokaContainer()
        load_card.add_section(content="**Emoji Synchronization**\n> Scanning assets and uploading application emojis...")
        status_msg = await send_container_response(ctx, load_card)
        uploaded, total = await self.bot.custom_emojis.sync_from_assets()

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Application Emojis Synchronized**\n"
                f"> Successfully uploaded `{uploaded}` new emoji(s).\n"
                f"> Total cached custom emojis: `{total}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sync(bot))
