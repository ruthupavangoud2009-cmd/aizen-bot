"""
KYOKA — Aizen Ultimate Edition
Server-Wide UI Color & Theme Configuration Cog
Allows server administrators to set custom embed UI colors (e.g. ?uicolour grey).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import is_owner_or_staff, is_primary_owner
from src.ui.response import KyokaResponse, ResponseType, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Admin.UIColor")


class UIColor(commands.Cog, name="Admin-UIColor"):
    """Server-Wide UI Color & Embed Theme Customization."""

    category: str = "⚙️・SERVER ADMINISTRATION"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _can_manage_color(self, ctx: CustomContext) -> bool:
        """Check if author has Manage Server permission or is Bot Primary Owner / Staff."""
        if is_owner_or_staff(ctx.author.id) or is_primary_owner(ctx.author.id):
            return True
        if ctx.guild and (ctx.author.id == ctx.guild.owner_id):
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        if perms and (perms.manage_guild or perms.administrator):
            return True
        return False

    @commands.command(
        name="uicolour",
        aliases=["uicolor", "setcolour", "setcolor", "themecolor", "themecolour"],
        description="Change the server-wide embed UI color (e.g. ?uicolour grey or ?uicolour #2b2d31).",
    )
    @commands.guild_only()
    async def uicolour(self, ctx: CustomContext, *, color_input: Optional[str] = None) -> None:
        """Set, view, or reset the bot's embed UI color for this server."""
        if not ctx.guild:
            return

        current_color_val = self.bot.guild_mgr.get_ui_color(ctx.guild.id, default=0x2B0938)
        current_hex = f"#{current_color_val:06X}"

        # If no arguments passed: display current color and preset list
        if not color_input or not color_input.strip():
            preset_names = ", ".join(f"`{k}`" for k in sorted(list(self.bot.guild_mgr.COLOR_PRESETS.keys())[:16]))
            desc = (
                f"> **Current UI Color:** `{current_hex}`\n"
                f"> **Usage:** `{ctx.prefix}uicolour <color_name_or_hex>`\n"
                f"> **Reset:** `{ctx.prefix}uicolour reset`\n\n"
                f"**Popular Color Presets:**\n"
                f"> {preset_names}\n\n"
                f"**Custom Hex Codes:**\n"
                f"> You can also use any hex code, e.g. `{ctx.prefix}uicolour #2B2D31` or `{ctx.prefix}uicolour #808080`."
            )
            resp = KyokaResponse(
                response_type=ResponseType.INFO,
                title="Server UI Color Configuration",
                description=desc,
                color=current_color_val,
                footer_text=f"-# Requested by {ctx.author.display_name}",
            )
            return await send_response(ctx, resp)

        # Check permissions
        if not self._can_manage_color(ctx):
            resp = KyokaResponse.permission(
                title="Permission Denied",
                description="You need `Manage Server` or `Administrator` permission to change the bot UI color.",
            )
            return await send_response(ctx, resp, ephemeral=True)

        clean_input = color_input.strip().lower()

        # Handle reset
        if clean_input in ("reset", "default", "aizen", "clear"):
            await self.bot.guild_mgr.reset_ui_color(ctx.guild.id)
            resp = KyokaResponse(
                response_type=ResponseType.SUCCESS,
                title="UI Color Reset",
                description=(
                    f"> The server UI color has been reset to default **Aizen Eclipse** (`#2B0938`).\n"
                    f"> All bot embeds will now use the signature deep violet theme."
                ),
                color=0x2B0938,
                footer_text=f"-# Updated by {ctx.author.display_name}",
            )
            return await send_response(ctx, resp)

        color_val, display_name = self.bot.guild_mgr.parse_color(clean_input)
        if color_val is None:
            resp = KyokaResponse.warning(
                title="Invalid Color Format",
                description=(
                    f"> Could not recognize `{color_input}` as a valid color preset or hex code.\n\n"
                    f"**Examples:**\n"
                    f"> • `{ctx.prefix}uicolour grey`\n"
                    f"> • `{ctx.prefix}uicolour dark`\n"
                    f"> • `{ctx.prefix}uicolour purple`\n"
                    f"> • `{ctx.prefix}uicolour emerald`\n"
                    f"> • `{ctx.prefix}uicolour #2F3136`"
                ),
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        # Store in cache and database
        await self.bot.guild_mgr.set_ui_color(ctx.guild.id, color_val)
        new_hex = f"#{color_val:06X}"

        resp = KyokaResponse(
            response_type=ResponseType.SUCCESS,
            title="UI Color Updated",
            description=(
                f"> Server UI color successfully changed to **{display_name}** (`{new_hex}`).\n"
                f"> All bot embeds, help menus, and responses in this server will now use this color.\n\n"
                f"💜 Kyoka UI styling synchronized."
            ),
            color=color_val,
            thumbnail_url=ctx.guild.icon.url if ctx.guild.icon else None,
            footer_text=f"-# Updated by {ctx.author.display_name} • KYOKA Theme Engine",
        )
        await send_response(ctx, resp)

    @commands.command(
        name="syncemojis",
        aliases=["emojisync", "uploademojis"],
        description="Sync local custom and animated emoji assets directly to Discord Application Emojis (Bot Owner only).",
    )
    async def syncemojis(self, ctx: CustomContext) -> None:
        """Sync all local assets to the bot's application emojis (up to 2,000 capacity)."""
        if not (is_primary_owner(ctx.author.id) or is_owner_or_staff(ctx.author.id)):
            resp = KyokaResponse.permission(
                title="Bot Owner Only",
                description="Only the bot owner / creator can synchronize application emojis.",
            )
            return await send_response(ctx, resp, ephemeral=True)

        reg = getattr(self.bot, "custom_emojis", None)
        if not reg:
            resp = KyokaResponse.error(
                title="Emoji Registry Unavailable",
                description="The emoji registry is not initialized on this bot instance.",
            )
            return await send_response(ctx, resp)

        status_msg = await ctx.send("> 🔄 **Synchronizing Application Emojis...** Uploading PNG/GIF assets to Discord...")
        count = await reg.sync_assets_to_application()
        total = reg.emoji_count

        resp = KyokaResponse(
            response_type=ResponseType.SUCCESS,
            title="Application Emojis Synchronized",
            description=(
                f"> **Newly Uploaded Emojis:** `{count}`\n"
                f"> **Total Cached Application Emojis:** `{total}` / `2,000`\n\n"
                f"All bot modules, help menus, and commands now have access to custom animated & static icons."
            ),
            footer_text=f"-# Triggered by {ctx.author.display_name} • 2,000 Emoji Storage",
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the UIColor cog."""
    await bot.add_cog(UIColor(bot))
