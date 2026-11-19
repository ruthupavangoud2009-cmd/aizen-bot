"""
KYOKA official Discord AutoMod integration.

AutoMod is opt-in per guild. Rules are created through Discord's native Auto
Moderation API and are only changed/deleted when their names carry KYOKA's prefix.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Cogs.AutoMod")
RULE_PREFIX = "KYOKA • "


class AutoModCog(commands.Cog, name="AutoMod"):
    """Opt-in management commands for Discord's native AutoMod rules."""

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _manager(self):
        return getattr(self.bot, "automod_mgr", None)

    async def _send_status(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing. Please try again shortly.")
            return
        try:
            rules = await manager.fetch_native_rules(ctx.guild)
        except discord.Forbidden:
            await ctx.send_error("KYOKA cannot view AutoMod rules. Please check its **Manage Server** permission.")
            return
        enabled = [rule for rule in rules if rule.enabled]
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="🛡️ KYOKA • Official Discord AutoMod",
            description=(
                f"**Status:** {'🟢 Enabled' if enabled else '⚪ Not enabled'}\n"
                f"**KYOKA rules:** {len(rules)} total • {len(enabled)} active\n\n"
                "**Protection installed by setup**\n"
                "• Discord spam detection\n"
                "• Mention-spam and raid protection\n"
                "• Discord harmful-link detection\n"
                "• Profanity, sexual-content and slur presets\n\n"
                "**Commands**\n"
                f"• `{prefix}automod setup` — install protection\n"
                f"• `{prefix}automod enable` / `disable`\n"
                f"• `{prefix}automod config` — show native rules\n"
                f"• `{prefix}automod reset` — remove KYOKA rules only"
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text=f"{ctx.guild.name} • Discord-native AutoMod")
        await ctx.send(embed=embed)

    @commands.hybrid_group(
        name="automod",
        aliases=["am"],
        invoke_without_command=True,
        description="Configure official Discord AutoMod protection for this server.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_group(self, ctx: CustomContext) -> None:
        await self._send_status(ctx)

    @automod_group.command(name="setup", description="Install KYOKA's official Discord AutoMod rules.")
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_setup(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing.")
            return
        bot_member = ctx.guild.me
        if not bot_member or not bot_member.guild_permissions.manage_guild:
            await ctx.send_error("KYOKA needs the **Manage Server** permission to create official Discord AutoMod rules.")
            return
        try:
            result = await manager.setup_native_rules(ctx.guild)
        except PermissionError as exc:
            await ctx.send_error(str(exc))
            return
        except discord.Forbidden:
            await ctx.send_error("Discord denied AutoMod setup. Confirm KYOKA has **Manage Server** permission.")
            return
        except discord.HTTPException as exc:
            logger.exception("Native AutoMod setup failed in guild %s", ctx.guild.id)
            await ctx.send_error(f"Discord could not complete AutoMod setup: {getattr(exc, 'text', None) or 'API error'}.")
            return

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        lines = []
        if result["created"]:
            lines.append("**Created:** " + ", ".join(result["created"]))
        if result["skipped"]:
            lines.append("**Already installed:** " + ", ".join(result["skipped"]))
        if result["errors"]:
            lines.append("**Could not install:** " + "; ".join(result["errors"]))
        if not lines:
            lines.append("No rules were changed.")
        embed = discord.Embed(
            title="🛡️ KYOKA AutoMod setup",
            description=(
                "KYOKA has configured genuine rules using Discord's official Auto Moderation API.\n\n"
                + "\n".join(lines)
                + f"\n\n**KYOKA rules in this server:** {result['total']}\n"
                f"Rules are server-specific. Other servers are untouched. Use `{prefix}automod config` to review them."
            ),
            color=0x7C3AED,
        )
        await ctx.send(embed=embed)

    @automod_group.command(name="enable", description="Enable KYOKA's Discord AutoMod rules.")
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_enable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing.")
            return
        try:
            rules = await manager.fetch_native_rules(ctx.guild)
            if not rules:
                await ctx.send_warning("No KYOKA rules are installed. Run `?automod setup` first.")
                return
            changed = await manager.set_native_rules_enabled(ctx.guild, True)
            await ctx.send_success(f"Official Discord AutoMod is enabled. Updated **{changed}** rule(s).")
        except discord.Forbidden:
            await ctx.send_error("KYOKA needs **Manage Server** permission to manage its AutoMod rules.")
        except discord.HTTPException as exc:
            await ctx.send_error(f"Discord could not enable AutoMod: {getattr(exc, 'text', None) or 'API error'}.")

    @automod_group.command(name="disable", description="Disable KYOKA's Discord AutoMod rules.")
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_disable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing.")
            return
        try:
            changed = await manager.set_native_rules_enabled(ctx.guild, False)
            await ctx.send_warning(f"KYOKA's official AutoMod rules are disabled. Updated **{changed}** rule(s).")
        except discord.Forbidden:
            await ctx.send_error("KYOKA needs **Manage Server** permission to manage its AutoMod rules.")
        except discord.HTTPException as exc:
            await ctx.send_error(f"Discord could not disable AutoMod: {getattr(exc, 'text', None) or 'API error'}.")

    @automod_group.command(name="config", description="View KYOKA's official Discord AutoMod rules.")
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_config(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing.")
            return
        try:
            rules = await manager.fetch_native_rules(ctx.guild)
        except discord.Forbidden:
            await ctx.send_error("KYOKA cannot view AutoMod rules. Check **Manage Server** permission.")
            return
        if not rules:
            await ctx.send_warning("No KYOKA AutoMod rules are installed. Run `?automod setup` to opt in.")
            return
        embed = discord.Embed(title="⚙️ KYOKA AutoMod configuration", color=0x7C3AED)
        for rule in rules:
            embed.add_field(
                name=rule.name.removeprefix(RULE_PREFIX),
                value=f"{'🟢 Enabled' if rule.enabled else '⚪ Disabled'} • Discord rule ID: `{rule.id}`",
                inline=False,
            )
        await ctx.send(embed=embed)

    @automod_group.command(name="reset", description="Delete only AutoMod rules created by KYOKA.")
    @commands.has_guild_permissions(manage_guild=True)
    async def automod_reset(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        manager = self._manager()
        if not manager:
            await ctx.send_error("AutoMod is still initializing.")
            return
        try:
            deleted = await manager.delete_native_rules(ctx.guild)
            await ctx.send_success(
                f"Removed **{deleted}** KYOKA AutoMod rule(s). Other server AutoMod rules were left untouched."
            )
        except discord.Forbidden:
            await ctx.send_error("KYOKA needs **Manage Server** permission to remove its AutoMod rules.")
        except discord.HTTPException as exc:
            await ctx.send_error(f"Discord could not reset AutoMod: {getattr(exc, 'text', None) or 'API error'}.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(AutoModCog(bot))
