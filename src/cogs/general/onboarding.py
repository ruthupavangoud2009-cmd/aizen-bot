"""
KYOKA 3.0 — Beginner-Friendly Onboarding & Server Configuration Hub.
Provides +start, +quickstart, and an interactive +setup wizard for easy server configuration.
Supports direct subcommands:
+setup status
+setup welcome #channel
+setup goodbye #channel
+setup logs #channel
+setup suggestions #channel
+setup autorole @role
+setup tickets #channel
+setup levels #channel
+setup ai #channel [persona]
+setup reset [feature]
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Any
import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_owner_or_staff
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.Onboarding")


class SetupResetConfirmView(discord.ui.View):
    """Confirmation view for resetting server configurations."""

    def __init__(self, bot: KyokaBot, guild_id: int, user_id: int, scope: str = "all") -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.scope = scope.lower().strip()

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if (
            interaction.user.id != self.user_id
            and not interaction.user.guild_permissions.administrator
            and not is_owner_or_staff(interaction.user.id)
        ):
            return await interaction.response.send_message("Only the command author or a server administrator can confirm this.", ephemeral=True)

        gid = self.guild_id
        reset_msgs = []

        if self.scope in ("all", "welcome"):
            await self.bot.db.execute("DELETE FROM server_events WHERE guild_id = ? AND event_type = 'welcome';", gid)
            reset_msgs.append("Welcome Messages")

        if self.scope in ("all", "goodbye", "leave"):
            await self.bot.db.execute("DELETE FROM server_events WHERE guild_id = ? AND event_type = 'leave';", gid)
            reset_msgs.append("Goodbye Messages")

        if self.scope in ("all", "logs", "modlog"):
            await self.bot.db.execute("UPDATE guild_logs SET mod_channel_id = NULL, all_channel_id = NULL WHERE guild_id = ?;", gid)
            reset_msgs.append("Moderation Logs")

        if self.scope in ("all", "suggestions"):
            await self.bot.db.execute("DELETE FROM guild_suggestions_settings WHERE guild_id = ?;", gid)
            reset_msgs.append("Community Suggestions")

        if self.scope in ("all", "autorole"):
            await self.bot.db.execute("DELETE FROM guild_autoroles WHERE guild_id = ?;", gid)
            reset_msgs.append("Join Autoroles")

        if self.scope in ("all", "tickets"):
            await self.bot.db.execute("DELETE FROM ticket_panels WHERE guild_id = ?;", gid)
            reset_msgs.append("Support Tickets")

        if self.scope in ("all", "levels"):
            await self.bot.db.execute("UPDATE leveling_settings SET channel_id = NULL WHERE guild_id = ?;", gid)
            reset_msgs.append("Leveling Announcements")

        if self.scope in ("all", "ai"):
            await self.bot.db.execute("DELETE FROM ai_channel_configs WHERE guild_id = ?;", gid)
            await self.bot.ai_mgr.reset_server_config(gid)
            reset_msgs.append("AI Channels & Personas")

        for child in self.children:
            child.disabled = True
        self.stop()

        summary = ", ".join(reset_msgs) if reset_msgs else self.scope
        await interaction.response.edit_message(
            content=f"✅ **Reset Complete:** `{summary}` have been restored to factory defaults.",
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the command author can cancel this.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        self.stop()
        await interaction.response.edit_message(content="❌ **Reset cancelled.**", view=self)


class SetupWizardSelect(discord.ui.Select):
    """Dropdown selector to view and configure specific server systems."""

    def __init__(self, cog: Onboarding, prefix: str) -> None:
        self.cog = cog
        self.prefix = prefix
        options = [
            discord.SelectOption(
                label="Welcome Messages",
                value="welcome",
                description="Greet new members automatically when they join",
                emoji="👋",
            ),
            discord.SelectOption(
                label="Goodbye Messages",
                value="goodbye",
                description="Farewell announcement when members leave",
                emoji="🚪",
            ),
            discord.SelectOption(
                label="Moderation Logs",
                value="logs",
                description="Track bans, kicks, mutes, warnings, and locks",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Community Suggestions",
                value="suggestions",
                description="Member ideas channel with upvote/downvote buttons",
                emoji="💡",
            ),
            discord.SelectOption(
                label="Join Autorole",
                value="autorole",
                description="Automatically give a role to newly joined members",
                emoji="🏷️",
            ),
            discord.SelectOption(
                label="Support Tickets",
                value="tickets",
                description="Interactive ticket panel for private member support",
                emoji="🎫",
            ),
            discord.SelectOption(
                label="Level-up Announcements",
                value="levels",
                description="Broadcast XP rank advancements in a designated channel",
                emoji="⭐",
            ),
            discord.SelectOption(
                label="AI Companion Chat",
                value="ai",
                description="Conversational AI channel with 10 customizable personas",
                emoji="🤖",
            ),
        ]
        super().__init__(
            placeholder="Select a system to inspect or configure...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        prefix = self.prefix

        guides = {
            "welcome": (
                "👋 **Welcome Messages**\n"
                "> Automatically greet newly joined members with custom cards and messages.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages` and `Embed Links` in target channel.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup welcome #channel` — Sets and enables the welcome channel.\n"
                f"`{prefix}welcome test` — Send a test welcome greeting.\n"
                f"`{prefix}welcome message <text>` — Customize the greeting message."
            ),
            "goodbye": (
                "🚪 **Goodbye / Leave Messages**\n"
                "> Send an announcement whenever a member departs or leaves the server.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages` and `Embed Links` in target channel.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup goodbye #channel` — Sets and enables the leave channel.\n"
                f"`{prefix}leave test` — Preview the departure message."
            ),
            "logs": (
                "🛡️ **Moderation Logs**\n"
                "> Audit trail for bans, kicks, timeouts, warnings, unbans, and channel locks.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages`, `Embed Links`, and `View Audit Log`.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup logs #channel` — Sets the moderation audit channel.\n"
                f"`{prefix}modlog` — Check current audit log channel."
            ),
            "suggestions": (
                "💡 **Community Suggestions**\n"
                "> Collect member feedback with interactive 👍 Upvote and 👎 Downvote voting buttons.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages` and `Embed Links` in target channel.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup suggestions #channel` — Sets the suggestions channel.\n"
                f"`{prefix}suggest <idea>` — Submit a community idea with voting."
            ),
            "autorole": (
                "🏷️ **Join Autorole**\n"
                "> Automatically grants a base member role to users when they join.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Manage Roles` permission.\n"
                "• Kyoka's bot role must be positioned higher than the assigned role in Server Settings.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup autorole @Role` — Set auto-assigned role.\n"
                f"`{prefix}autorole config` — Inspect current autorole settings."
            ),
            "tickets": (
                "🎫 **Support Tickets**\n"
                "> Private channels for member inquiries, support requests, and billing.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Manage Channels`, `Send Messages`, and `Manage Roles`.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup tickets #channel` — Deploy a support ticket panel.\n"
                f"`{prefix}ticket close` — Close an active ticket channel."
            ),
            "levels": (
                "⭐ **Level-up Announcements**\n"
                "> Reward member activity with XP progression, levels, and rank cards.\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages` and `Embed Links`.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup levels #channel` — Set the level-up celebration channel.\n"
                f"`{prefix}rank` — View your personal level card.\n"
                f"`{prefix}leaderboard` — View the top server members."
            ),
            "ai": (
                "🤖 **AI Companion Chat**\n"
                "> Enable natural, prefix-free conversational AI powered by Google Gemini.\n"
                "> Choose between 10 distinct personalities (Girlfriend, Baddie, Wise Aizen, etc.).\n\n"
                "**Required Permissions:**\n"
                "• Bot needs `Send Messages` and `Embed Links`.\n\n"
                f"**How to Configure:**\n"
                f"`{prefix}setup ai #channel [persona]` — Enable natural chat in channel.\n"
                f"`{prefix}ai personalities` — Browse and select from all 10 personalities.\n"
                f"`{prefix}aidiag` — Test AI provider latency and reachability."
            ),
        }

        embed = discord.Embed(
            title=f"⚙️ Setup Guide: {selected.title()}",
            description=guides.get(selected, "No guide available."),
            color=0x7C3AED,
        )
        embed.set_footer(text=f"Run the command shown above to save your settings.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class SetupWizardView(discord.ui.View):
    """Interactive Hub View for the +setup command."""

    def __init__(self, cog: Onboarding, prefix: str) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.prefix = prefix
        self.add_item(SetupWizardSelect(cog, prefix))

    @discord.ui.button(label="Full Status", style=discord.ButtonStyle.primary, emoji="📊", row=1)
    async def btn_status(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild:
            return
        status_embed = await self.cog._build_status_embed(interaction.guild, self.prefix)
        await interaction.response.send_message(embed=status_embed, ephemeral=True)

    @discord.ui.button(label="Quickstart Guide", style=discord.ButtonStyle.secondary, emoji="🚀", row=1)
    async def btn_quickstart(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        qs_embed = self.cog._build_quickstart_embed(self.prefix)
        await interaction.response.send_message(embed=qs_embed, ephemeral=True)


class Onboarding(commands.Cog):
    """
    KYOKA 3.0 Beginner Onboarding & Server Setup Wizard.
    Makes configuring the bot effortless for community owners and administrators.
    """

    category = "🏠・GETTING STARTED"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _build_quickstart_embed(self, p: str) -> discord.Embed:
        embed = discord.Embed(
            title="🚀 KYOKA 3.0 — Server Owner Quickstart Guide",
            description=(
                "Welcome to **KYOKA 3.0**! Follow these three simple steps to prepare your server in less than 2 minutes.\n\n"
                "**Step 1: Set Up Essential Channels**\n"
                f"• `{p}setup welcome #welcome` — Greet new members automatically\n"
                f"• `{p}setup logs #mod-logs` — Track bans, kicks, timeouts, and warning cases\n\n"
                "**Step 2: Assign Join Roles & Command Prefix**\n"
                f"• `{p}setup autorole @Member` — Automatically give a base role to new members\n"
                f"• `{p}prefix +` — Change or customize the bot prefix (default is `+`)\n\n"
                "**Step 3: Enable Community Features**\n"
                f"• `{p}setup ai #ai-chat girlfriend` — Enable natural conversational AI chat\n"
                f"• `{p}setup suggestions #suggestions` — Collect community feedback with voting\n"
                f"• `{p}setup tickets #tickets` — Deploy an interactive support ticket panel\n"
                f"• `{p}setup levels #level-ups` — Celebrate member chat activity and XP progression\n\n"
                "**Helpful Next Commands:**\n"
                f"• `{p}setup status` — Verify your configured features\n"
                f"• `{p}help` — Interactive command directory"
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text="Aizen Edition • Designed for seamless beginner setup")
        return embed

    async def _build_status_embed(self, guild: discord.Guild, p: str) -> discord.Embed:
        gid = guild.id
        db = self.bot.db

        # 1. Welcome
        welcome_row = await db.fetch_one("SELECT channel_id, is_enabled FROM server_events WHERE guild_id = ? AND event_type = 'welcome';", gid)
        w_chan = f"<#{welcome_row['channel_id']}>" if welcome_row and welcome_row.get("channel_id") else "`Not Configured`"
        w_status = "🟢 Enabled" if welcome_row and welcome_row.get("is_enabled", True) and welcome_row.get("channel_id") else "🔴 Disabled"

        # 2. Goodbye
        leave_row = await db.fetch_one("SELECT channel_id, is_enabled FROM server_events WHERE guild_id = ? AND event_type = 'leave';", gid)
        l_chan = f"<#{leave_row['channel_id']}>" if leave_row and leave_row.get("channel_id") else "`Not Configured`"
        l_status = "🟢 Enabled" if leave_row and leave_row.get("is_enabled", True) and leave_row.get("channel_id") else "🔴 Disabled"

        # 3. Mod Logs
        log_row = await db.fetch_one("SELECT mod_channel_id FROM guild_logs WHERE guild_id = ?;", gid)
        log_chan = f"<#{log_row['mod_channel_id']}>" if log_row and log_row.get("mod_channel_id") else "`Not Configured`"

        # 4. Suggestions
        sug_row = await db.fetch_one("SELECT channel_id, is_enabled FROM guild_suggestions_settings WHERE guild_id = ?;", gid)
        sug_chan = f"<#{sug_row['channel_id']}>" if sug_row and sug_row.get("channel_id") else "`Not Configured`"

        # 5. Autorole
        ar_row = await db.fetch_one("SELECT human_role_id, role_id FROM guild_autoroles WHERE guild_id = ?;", gid)
        ar_id = ar_row.get("human_role_id") or ar_row.get("role_id") if ar_row else None
        ar_role = f"<@&{ar_id}>" if ar_id else "`Not Configured`"

        # 6. Tickets
        ticket_row = await db.fetch_one("SELECT channel_id FROM ticket_panels WHERE guild_id = ? LIMIT 1;", gid)
        ticket_chan = f"<#{ticket_row['channel_id']}>" if ticket_row and ticket_row.get("channel_id") else "`Not Configured`"

        # 7. Leveling
        lvl_row = await db.fetch_one("SELECT channel_id, enabled FROM leveling_settings WHERE guild_id = ?;", gid)
        lvl_chan = f"<#{lvl_row['channel_id']}>" if lvl_row and lvl_row.get("channel_id") else "`Current Channel`"

        # 8. AI Channel
        ai_row = await db.fetch_one("SELECT channel_id, persona, enabled FROM ai_channel_configs WHERE guild_id = ? LIMIT 1;", gid)
        ai_chan = f"<#{ai_row['channel_id']}> (`{ai_row['persona']}`)" if ai_row and ai_row.get("channel_id") else "`Not Configured`"

        embed = discord.Embed(
            title=f"📊 Server Setup Status — {guild.name}",
            description="Overview of configured features in this server:",
            color=0x7C3AED,
        )
        embed.add_field(name="👋 Welcome Messages", value=f"{w_status} | {w_chan}", inline=False)
        embed.add_field(name="🚪 Goodbye Messages", value=f"{l_status} | {l_chan}", inline=False)
        embed.add_field(name="🛡️ Moderation Logs", value=log_chan, inline=True)
        embed.add_field(name="💡 Suggestions", value=sug_chan, inline=True)
        embed.add_field(name="🏷️ Join Autorole", value=ar_role, inline=True)
        embed.add_field(name="🎫 Support Tickets", value=ticket_chan, inline=True)
        embed.add_field(name="⭐ Level Announcements", value=lvl_chan, inline=True)
        embed.add_field(name="🤖 AI Chat Channel", value=ai_chan, inline=True)
        embed.set_footer(text=f"Use {p}setup <feature> to configure missing systems.")
        return embed

    # ─── 1. +start ───────────────────────────────────────────────────────────

    @commands.command(
        name="start",
        description="Introduction to KYOKA 3.0 and recommended setup steps.",
    )
    async def start(self, ctx: CustomContext) -> None:
        """Beginner introduction to the bot."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 — The Ultimate All-in-One Discord Bot",
            description=(
                "Thank you for choosing **KYOKA**! Built for speed, elegance, and reliability.\n\n"
                "**Core Systems Included:**\n"
                "• 🤖 **Conversational AI** — 10 personalities, automatic chat channels (~800ms latency)\n"
                "• 🛡️ **Moderation & Logs** — Bans, timeouts, warnings, purge, channel locks\n"
                "• 🎫 **Tickets & Support** — Private ticket channels with HTML transcripts\n"
                "• 🎉 **Giveaways** — Requirements, bonus roles, rerolls, activity tracking\n"
                "• 🎵 **Music Player** — High-performance audio playback with interactive controls\n"
                "• ⭐ **Community & XP** — Levels, rankings, suggestions with voting, polls\n\n"
                f"**Immediate Next Steps for Admins:**\n"
                f"1. Run `{p}quickstart` for a 2-minute walkthrough.\n"
                f"2. Run `{p}setup` to open the interactive configuration wizard.\n"
                f"3. Run `{p}help` to browse all categorized commands."
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text=f"Type {p}help for full command directory • Aizen Edition")

        view = discord.ui.View(timeout=120)
        qs_btn = discord.ui.Button(label="Quickstart Guide", style=discord.ButtonStyle.primary, emoji="🚀")
        setup_btn = discord.ui.Button(label="Setup Wizard", style=discord.ButtonStyle.secondary, emoji="⚙️")
        help_btn = discord.ui.Button(label="Command Help", style=discord.ButtonStyle.secondary, emoji="📖")

        async def qs_callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_message(embed=self._build_quickstart_embed(p), ephemeral=True)

        async def setup_callback(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                return await interaction.response.send_message("Setup is only available inside servers.", ephemeral=True)
            status_embed = await self._build_status_embed(interaction.guild, p)
            w_view = SetupWizardView(self, p)
            await interaction.response.send_message(embed=status_embed, view=w_view, ephemeral=True)

        async def help_callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_message(f"Type `{p}help` in chat to browse the interactive command directory!", ephemeral=True)

        qs_btn.callback = qs_callback
        setup_btn.callback = setup_callback
        help_btn.callback = help_callback

        view.add_item(qs_btn)
        view.add_item(setup_btn)
        view.add_item(help_btn)

        await ctx.send(embed=embed, view=view)

    # ─── 2. +quickstart ──────────────────────────────────────────────────────

    @commands.command(
        name="quickstart",
        description="Step-by-step setup guide for server owners and administrators.",
    )
    async def quickstart(self, ctx: CustomContext) -> None:
        """Interactive quickstart guide."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        embed = self._build_quickstart_embed(p)

        view = discord.ui.View(timeout=120)
        launch_btn = discord.ui.Button(label="Launch Setup Wizard", style=discord.ButtonStyle.success, emoji="⚙️")

        async def launch_cb(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                return await interaction.response.send_message("Only available in a server.", ephemeral=True)
            status_embed = await self._build_status_embed(interaction.guild, p)
            w_view = SetupWizardView(self, p)
            await interaction.response.send_message(embed=status_embed, view=w_view, ephemeral=True)

        launch_btn.callback = launch_cb
        view.add_item(launch_btn)

        await ctx.send(embed=embed, view=view)

    # ─── 3. +setup (Master Command & Group) ──────────────────────────────────

    @commands.group(
        name="setup",
        invoke_without_command=True,
        description="Interactive server configuration wizard for all core features.",
    )
    @commands.guild_only()
    async def setup_cmd(self, ctx: CustomContext) -> None:
        """Server configuration wizard hub."""
        if not ctx.guild:
            return

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        status_embed = await self._build_status_embed(ctx.guild, p)
        view = SetupWizardView(self, p)
        await ctx.send(embed=status_embed, view=view)

    # Subcommand: +setup status
    @setup_cmd.command(name="status", description="Show which features are configured and what is missing.")
    @commands.guild_only()
    async def setup_status(self, ctx: CustomContext) -> None:
        """Display configuration status."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        embed = await self._build_status_embed(ctx.guild, p)
        await ctx.send(embed=embed)

    # Subcommand: +setup welcome #channel
    @setup_cmd.command(name="welcome", description="Configure automated welcome messages in a channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_welcome(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set welcome channel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await ctx.send(f"⚠️ I need `Send Messages` and `Embed Links` permissions in {channel.mention}.")

        await self.bot.db.execute(
            """
            INSERT INTO server_events (guild_id, event_type, channel_id, is_enabled, updated_at)
            VALUES (?, 'welcome', ?, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, event_type) DO UPDATE SET
                channel_id = ?, is_enabled = TRUE, updated_at = CURRENT_TIMESTAMP;
            """,
            ctx.guild.id,
            channel.id,
            channel.id,
        )
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="✅ Welcome Channel Configured",
            description=(
                f"Welcome messages are now active in {channel.mention}!\n\n"
                f"**Next Steps:**\n"
                f"• Test greeting: `{p}welcome test`\n"
                f"• Customize message: `{p}welcome message Welcome to {{server}}, {{user}}!`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup goodbye #channel
    @setup_cmd.command(name="goodbye", aliases=["leave"], description="Configure member leave announcements in a channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_goodbye(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set goodbye channel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await ctx.send(f"⚠️ I need `Send Messages` and `Embed Links` permissions in {channel.mention}.")

        await self.bot.db.execute(
            """
            INSERT INTO server_events (guild_id, event_type, channel_id, is_enabled, updated_at)
            VALUES (?, 'leave', ?, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, event_type) DO UPDATE SET
                channel_id = ?, is_enabled = TRUE, updated_at = CURRENT_TIMESTAMP;
            """,
            ctx.guild.id,
            channel.id,
            channel.id,
        )
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="✅ Goodbye Channel Configured",
            description=(
                f"Departure messages are now active in {channel.mention}!\n\n"
                f"**Next Steps:**\n"
                f"• Test message: `{p}leave test`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup logs #channel
    @setup_cmd.command(name="logs", aliases=["modlogs"], description="Configure the moderation audit log channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_logs(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set moderation log channel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await ctx.send(f"⚠️ I need `Send Messages` and `Embed Links` permissions in {channel.mention}.")

        await self.bot.log_mgr.set_log_channel(ctx.guild.id, "mod", channel.id)
        embed = discord.Embed(
            title="✅ Moderation Logs Configured",
            description=(
                f"Moderation audit logs will now be dispatched to {channel.mention}!\n"
                "> All bans, kicks, mutes, warnings, and locks will be documented here."
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup suggestions #channel
    @setup_cmd.command(name="suggestions", aliases=["suggestion"], description="Configure the community suggestions channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_suggestions(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set community suggestions channel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await ctx.send(f"⚠️ I need `Send Messages` and `Embed Links` permissions in {channel.mention}.")

        await self.bot.db.execute(
            """
            INSERT INTO guild_suggestions_settings (guild_id, channel_id, is_enabled)
            VALUES (?, ?, TRUE)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = ?, is_enabled = TRUE;
            """,
            ctx.guild.id,
            channel.id,
            channel.id,
        )
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="✅ Suggestions Channel Configured",
            description=(
                f"Community suggestions will now appear in {channel.mention} with interactive voting buttons!\n\n"
                f"**How to Use:**\n"
                f"• Submit an idea: `{p}suggest <your idea>`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup autorole @role
    @setup_cmd.command(name="autorole", description="Configure a join role automatically given to new members.")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def setup_autorole(self, ctx: CustomContext, role: discord.Role) -> None:
        """Set join autorole."""
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send("❌ I need the `Manage Roles` permission to assign roles.")
        if role >= ctx.guild.me.top_role:
            return await ctx.send(
                f"❌ The role {role.mention} is higher than or equal to my highest role. "
                "Move my bot role higher in **Server Settings -> Roles**."
            )

        await self.bot.db.execute(
            """
            INSERT INTO guild_autoroles (guild_id, human_role_id, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET human_role_id = ?, role_id = ?;
            """,
            ctx.guild.id,
            role.id,
            role.id,
            role.id,
            role.id,
        )
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="✅ Join Autorole Configured",
            description=(
                f"Newly joined members will automatically receive {role.mention}!\n\n"
                f"**Verify Settings:**\n"
                f"• `{p}autorole config`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup tickets #channel
    @setup_cmd.command(name="tickets", description="Configure the support ticket panel in a channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_tickets(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Deploy support ticket panel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links or not perms.manage_channels:
            return await ctx.send(f"⚠️ I need `Manage Channels`, `Send Messages`, and `Embed Links` in {channel.mention}.")

        # Deploy ticket panel message
        embed = discord.Embed(
            title="🎫 Server Support Desk",
            description="Need help, support, or have a billing inquiry?\nClick the button below to open a private ticket channel with our team.",
            color=0x7C3AED,
        )
        embed.set_footer(text=f"{ctx.guild.name} • Support Department")

        # Interactive Create Ticket Button
        view = discord.ui.View(timeout=None)
        ticket_btn = discord.ui.Button(
            label="Open Support Ticket",
            style=discord.ButtonStyle.primary,
            emoji="🎫",
            custom_id="ticket:create_default",
        )

        async def ticket_cb(interaction: discord.Interaction) -> None:
            ticket_cog = self.bot.get_cog("TicketSystem")
            if ticket_cog and hasattr(ticket_cog, "create_ticket_channel"):
                await ticket_cog.create_ticket_channel(interaction, panel_name="Support")
            else:
                await interaction.response.send_message("Creating your private support channel...", ephemeral=True)

        ticket_btn.callback = ticket_cb
        view.add_item(ticket_btn)

        msg = await channel.send(embed=embed, view=view)
        await self.bot.db.execute(
            """
            INSERT INTO ticket_panels (guild_id, panel_name, embed_name, channel_id, message_id)
            VALUES (?, 'Support', 'Default', ?, ?)
            ON CONFLICT DO NOTHING;
            """,
            ctx.guild.id,
            channel.id,
            msg.id,
        )

        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        conf_embed = discord.Embed(
            title="✅ Ticket Panel Deployed",
            description=(
                f"Support ticket panel deployed in {channel.mention}!\n\n"
                f"**How to Manage Tickets:**\n"
                f"• Close ticket: `{p}ticket close`\n"
                f"• Claim ticket: `{p}ticket claim`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=conf_embed)

    # Subcommand: +setup levels #channel
    @setup_cmd.command(name="levels", description="Configure the channel for level-up celebrations.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_levels(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set level-up announcements channel."""
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await ctx.send(f"⚠️ I need `Send Messages` and `Embed Links` in {channel.mention}.")

        await self.bot.db.execute(
            """
            INSERT INTO leveling_settings (guild_id, channel_id, enabled, announce_level_up, updated_at)
            VALUES (?, ?, TRUE, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = ?, enabled = TRUE, announce_level_up = TRUE, updated_at = CURRENT_TIMESTAMP;
            """,
            ctx.guild.id,
            channel.id,
            channel.id,
        )
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        embed = discord.Embed(
            title="✅ Level-up Announcements Configured",
            description=(
                f"Member rank advancements will now be celebrated in {channel.mention}!\n\n"
                f"**Commands:**\n"
                f"• Check rank: `{p}rank`\n"
                f"• Server leaderboard: `{p}leaderboard`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    # Subcommand: +setup ai #channel [persona]
    @setup_cmd.command(name="ai", description="Configure an automatic natural AI conversation channel.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_ai(self, ctx: CustomContext, channel: discord.TextChannel, persona: str = "girlfriend") -> None:
        """Set automatic conversational AI channel."""
        companion_cog = self.bot.get_cog("CompanionAI")
        if companion_cog and hasattr(companion_cog, "_setup_channel"):
            embed = await companion_cog._setup_channel(
                guild=ctx.guild,
                channel=channel,
                persona=persona,
                user_id=ctx.author.id,
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ CompanionAI cog is not currently loaded.")

    # Subcommand: +setup reset [feature]
    @setup_cmd.command(name="reset", description="Reset a configured feature to defaults after confirmation.")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_reset(self, ctx: CustomContext, feature: str = "all") -> None:
        """Reset configured features."""
        view = SetupResetConfirmView(self.bot, ctx.guild.id, ctx.author.id, scope=feature)
        await ctx.send(
            f"⚠️ **Are you sure you want to reset settings for `{feature}`?**\n"
            "> Click below to confirm or cancel.",
            view=view,
        )


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Onboarding(bot))
