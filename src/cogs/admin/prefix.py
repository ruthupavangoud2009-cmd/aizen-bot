"""
Kyoka Discord Bot - Prefix Management Cog
Enforces exactly ONE active command prefix per server with zero-latency L1 memory caching,
strict input validation, role permissions, and complete cross-server isolation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner, is_owner_or_staff

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Admin.Prefix")


class Prefix(commands.Cog, name="Admin-Prefix"):
    """Server administration and isolated prefix configuration."""
    category: str = "Configuration"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _can_manage_prefix(self, ctx: CustomContext) -> bool:
        """Check if author has Manage Server permission or is Bot Primary Owner / Staff."""
        if is_owner_or_staff(ctx.author.id):
            return True
        if ctx.guild and ctx.author.guild_permissions.manage_guild:
            return True
        if ctx.guild and ctx.author.id == ctx.guild.owner_id:
            return True
        return False

    @staticmethod
    def _validate_prefix(prefix: str) -> tuple[bool, str]:
        """Validate candidate prefix. Returns (is_valid, error_message)."""
        clean_prefix = prefix.strip()
        if not clean_prefix:
            return False, "Prefix cannot be empty or whitespace-only."
        if len(clean_prefix) > 5:
            return False, f"Prefix length cannot exceed 5 characters (received {len(clean_prefix)} characters)."
        if " " in clean_prefix:
            return False, "Prefix cannot contain internal whitespace or spaces."
        if any(c in clean_prefix for c in ("@", "#", "/", "\\", "`", "\n", "\t")):
            return False, "Prefix cannot contain mentions (@), channel tags (#), slash (/), backticks, or control characters."
        return True, ""

    @commands.hybrid_command(
        name="setprefix",
        description="Change the single active command prefix for this server.",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def set_prefix(self, ctx: CustomContext, *, new_prefix: str) -> None:
        """
        Configure a custom prefix for this server.
        Usage: +setprefix ! or +setprefix k!
        
        Subsequent commands in this server must use the new prefix.
        Old prefixes (such as +, ?, etc.) will no longer be accepted.
        """
        if not self._can_manage_prefix(ctx):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to change the bot prefix.")
            return

        valid, err = self._validate_prefix(new_prefix)
        if not valid:
            await ctx.send_warning(f"❌ {err}")
            return

        clean_prefix = new_prefix.strip()

        # 5. Persist prefix to L1 Microsecond Cache & Database
        old_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        await self.bot.guild_mgr.set_prefix(ctx.guild.id, clean_prefix)

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • PREFIX CONFIGURED",
            description=(
                f"✅ **Command prefix for `{ctx.guild.name}` has been successfully updated!**\n\n"
                f"• **New Active Prefix:** `{clean_prefix}`\n"
                f"• **Previous Prefix:** `{old_prefix}` *(No longer recognized)*\n"
                f"• **Slash Commands:** `/` *(Always available)*\n\n"
                f"⚠️ **Single Active Prefix Enforced:**\n"
                f"> All subsequent text commands in this server must now begin with `{clean_prefix}`.\n"
                f"> Try running: `{clean_prefix}help` or `{clean_prefix}prefix`."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )

        assets = getattr(Config, "ASSETS", None)
        thumb = getattr(assets, "AIZEN_AVATAR_URL", "")
        if thumb and thumb.strip():
            embed.set_thumbnail(url=thumb.strip())

        embed.set_footer(
            text=f"Configured by {ctx.author.display_name} • Single Prefix System Active",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )

        await ctx.send(embed=embed)
        logger.info(
            f"Guild {ctx.guild.id} prefix changed from '{old_prefix}' to '{clean_prefix}' by {ctx.author} ({ctx.author.id})"
        )

    @commands.hybrid_command(
        name="resetprefix",
        description="Reset this server's command prefix to default ('+').",
    )
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def reset_prefix(self, ctx: CustomContext) -> None:
        """
        Reset this server's custom prefix back to default '+'.
        Usage: +resetprefix or !resetprefix
        """
        if not self._can_manage_prefix(ctx):
            await ctx.send_warning("❌ You need **Manage Server** permission or Server Ownership to reset the bot prefix.")
            return

        old_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        default_p = Config.DEFAULT_PREFIX

        if old_prefix == default_p:
            await ctx.send_info(f"ℹ️ This server is already using the default prefix (`{default_p}`).")
            return

        await self.bot.guild_mgr.reset_prefix(ctx.guild.id)

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • PREFIX RESTORED",
            description=(
                f"✅ **Command prefix for `{ctx.guild.name}` has been reset to default.**\n\n"
                f"• **Active Prefix:** `{default_p}`\n"
                f"• **Previous Prefix:** `{old_prefix}` *(Revoked)*\n"
                f"• **Example Command:** `{default_p}help`\n\n"
                f"> Use `{default_p}setprefix <new_prefix>` anytime to customize it again."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Reset by {ctx.author.display_name} • KYOKA 3.0")
        await ctx.send(embed=embed)
        logger.info(f"Guild {ctx.guild.id} prefix reset to '{default_p}' by {ctx.author} ({ctx.author.id})")

    @commands.hybrid_command(
        name="prefix",
        description="View the single active command prefix for this server.",
    )
    @commands.guild_only()
    async def view_prefix(self, ctx: CustomContext) -> None:
        """
        Display the current active command prefix for this server.
        Usage: +prefix or !prefix
        """
        current_p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        default_p = Config.DEFAULT_PREFIX
        is_custom = current_p != default_p

        embed = discord.Embed(
            title=f"⛩️ Command Prefix • {ctx.guild.name}",
            description=(
                f"• **Active Text Prefix:** `{current_p}`\n"
                f"• **Prefix Status:** `{'Custom Guild Prefix' if is_custom else 'Default Global Prefix'}`\n"
                f"• **Slash Commands:** `/<command>` *(Prefix-independent)*\n"
                f"• **Mention Invocation:** `<@{self.bot.user.id}> <command>`\n\n"
                f"**Quick Usage Examples:**\n"
                f"• `{current_p}help` — Browse all accessible commands\n"
                f"• `{current_p}setprefix <symbol>` — (Admin) Set a custom prefix\n"
                f"• `{current_p}resetprefix` — (Admin) Reset to default `{default_p}`"
            ),
            color=0x7C3AED,
        )

        assets = getattr(Config, "ASSETS", None)
        thumb = getattr(assets, "AIZEN_AVATAR_URL", "")
        if thumb and thumb.strip():
            embed.set_thumbnail(url=thumb.strip())

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Single Active Prefix Enforced",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Prefix(bot))
