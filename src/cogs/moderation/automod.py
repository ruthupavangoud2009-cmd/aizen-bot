"""
Kyoka Discord Bot - AutoMod Moderation Cog
Registers listeners and management commands for real-time chat protection.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Cogs.AutoMod")


class AutoModCog(commands.Cog, name="AutoMod"):
    """Server chat moderation and automated rule enforcement."""

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    # ─── MESSAGE LISTENER ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Inspect all messages against server AutoMod filters."""
        if not message.guild or message.author.bot:
            return

        # Ensure automod manager exists on bot
        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr:
            return

        cfg = await mgr.get_settings(message.guild.id)
        if not cfg.get("enabled"):
            return

        # Check exemptions
        member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if not member:
            return

        if mgr.is_exempt(member, message.channel, cfg):
            return

        mentions_count = len(message.mentions) + len(message.role_mentions)
        violation, filter_name, reason = mgr.check_content(
            message.content,
            user_id=member.id,
            guild_id=message.guild.id,
            cfg=cfg,
            mentions_count=mentions_count,
        )

        if violation and filter_name and reason:
            await mgr.execute_action(
                guild=message.guild,
                member=member,
                channel=message.channel,
                message=message,
                filter_name=filter_name,
                reason=reason,
                cfg=cfg,
            )

    # ─── AUTOMOD COMMANDS ─────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="automod",
        aliases=["am"],
        invoke_without_command=True,
        description="Inspect or configure server AutoMod rules.",
    )
    @commands.has_permissions(manage_guild=True)
    async def automod_group(self, ctx: CustomContext) -> None:
        """Show current AutoMod status and active protection filters."""
        if not ctx.guild:
            return

        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr:
            await ctx.send_error("AutoMod system is currently initializing.")
            return

        cfg = await mgr.get_settings(ctx.guild.id)
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        status_str = "🟢 **Enabled**" if cfg.get("enabled") else "🔴 **Disabled**"
        action_str = str(cfg.get("action", "delete")).upper()

        filters = [
            f"• **Anti-Spam:** {'✅' if cfg.get('anti_spam') else '❌'} (`{cfg.get('spam_threshold')} msgs/4s`)",
            f"• **Mass Mentions:** {'✅' if cfg.get('anti_mentions') else '❌'} (`threshold: {cfg.get('mention_threshold')}`)",
            f"• **Anti-Invites:** {'✅' if cfg.get('anti_invites') else '❌'}",
            f"• **Bad Words:** {'✅' if cfg.get('anti_badwords') else '❌'} (`{len(cfg.get('badwords_list', []))} words`)",
            f"• **Repeated Text:** {'✅' if cfg.get('anti_repeated') else '❌'}",
            f"• **Anti-Caps:** {'✅' if cfg.get('anti_caps') else '❌'} (`>{cfg.get('caps_threshold')}%`)",
        ]

        embed = discord.Embed(
            title="🛡️ Kyoka AutoMod Engine",
            description=(
                f"Status: {status_str}\n"
                f"Punishment Action: **{action_str}**\n\n"
                f"**Active Protection Modules:**\n" + "\n".join(filters) + "\n\n"
                f"**Management Commands:**\n"
                f"• `{p}automod enable` / `{p}automod disable`\n"
                f"• `{p}automod action <delete|warn|timeout>`\n"
                f"• `{p}automod test <message text>` — Diagnostic dry run"
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text=f"{ctx.guild.name} • Kyoka 3.0 AutoMod")
        await ctx.send(embed=embed)

    @automod_group.command(name="enable", description="Enable server AutoMod chat filtering.")
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: CustomContext) -> None:
        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr or not ctx.guild:
            return
        await mgr.update_settings(ctx.guild.id, enabled=True)
        await ctx.send_success("AutoMod protection has been **enabled** for this server.")

    @automod_group.command(name="disable", description="Disable server AutoMod chat filtering.")
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: CustomContext) -> None:
        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr or not ctx.guild:
            return
        await mgr.update_settings(ctx.guild.id, enabled=False)
        await ctx.send_warning("AutoMod protection has been **disabled** for this server.")

    @automod_group.command(name="action", description="Set the default AutoMod punishment action.")
    @app_commands.describe(action="Punishment to execute: delete, warn, or timeout")
    @commands.has_permissions(manage_guild=True)
    async def automod_action(self, ctx: CustomContext, action: str) -> None:
        action = action.lower().strip()
        if action not in ("delete", "warn", "timeout"):
            await ctx.send_error("Invalid action. Supported actions: `delete`, `warn`, `timeout`.")
            return

        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr or not ctx.guild:
            return

        await mgr.update_settings(ctx.guild.id, action=action)
        await ctx.send_success(f"Default AutoMod action updated to **{action.upper()}**.")

    @automod_group.command(name="test", description="Test a message string against AutoMod filters without punishing.")
    @app_commands.describe(message_text="Text content to simulate against filters")
    @commands.has_permissions(manage_guild=True)
    async def automod_test(self, ctx: CustomContext, *, message_text: str) -> None:
        mgr = getattr(self.bot, "automod_mgr", None)
        if not mgr or not ctx.guild:
            return

        cfg = await mgr.get_settings(ctx.guild.id)
        # Enable temporarily for test evaluation
        test_cfg = dict(cfg)
        test_cfg["enabled"] = True

        violation, filter_name, reason = mgr.check_content(
            message_text,
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            cfg=test_cfg,
            mentions_count=0,
        )

        if violation:
            await ctx.send_warning(
                f"⚠️ **Violation Triggered!**\n"
                f"• **Filter:** `{filter_name}`\n"
                f"• **Reason:** {reason}\n"
                f"• **Expected Action:** `{cfg.get('action', 'delete').upper()}`"
            )
        else:
            await ctx.send_success(
                f"✅ **Clean Message!** No active AutoMod filters were triggered by this text."
            )


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(AutoModCog(bot))
