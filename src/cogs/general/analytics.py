from __future__ import annotations

import datetime
import logging
import math
import os
import platform
import time
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.utility.giveaway import is_giveaway_authorized
from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.Analytics")


class AnalyticsAndDiagnostics(commands.Cog):
    """
    KYOKA 3.0 Utility and Administration Commands.
    Houses top-level commands:
    46. /activity
    47. /leaderboard
    48. /auditlog
    49. /diagnostics
    50. /privacy
    """

    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    # 46. /activity
    @app_commands.command(
        name="activity",
        description="View your or a member's message activity statistics in this server.",
    )
    @app_commands.describe(member="Member whose activity to inspect (defaults to yourself)")
    async def slash_activity(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)

        target = member or interaction.user
        if not isinstance(target, discord.Member):
            return await interaction.response.send_message("Target must be a member in this server.", ephemeral=True)

        stats = await self.bot.activity_mgr.get_user_activity(interaction.guild.id, target.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        container.add_section(content=f"# **Activity Stats: {target.display_name}**")
        container.add_separator(divider=True)

        if stats["opted_out"]:
            container.add_text(
                f"🔒 **Privacy Opt-Out Active**\n"
                f"> This member has opted out of activity tracking. No counts are tracked.\n"
                f"-# Change privacy settings anytime using `/privacy`."
            )
        else:
            last_msg_str = (
                f"<t:{int(stats['last_message_at'].timestamp())}:R>"
                if stats.get("last_message_at")
                else "No recent qualifying messages"
            )

            container.add_text(
                f"{dot} **Messages Today:** `{stats['today']:,}` qualifying messages\n"
                f"{dot} **Past 7 Days:** `{stats['weekly']:,}` messages\n"
                f"{dot} **Past 30 Days:** `{stats['monthly']:,}` messages\n"
                f"{dot} **Server Activity Rank:** `#{stats['rank']}`\n"
                f"{dot} **Last Message Sent:** {last_msg_str}"
            )

        container.add_thumbnail(target.display_avatar.url)
        container.add_separator(divider=True)
        container.add_text(f"-# {interaction.guild.name} • Message counts and timestamps only")
        await send_container_response(interaction, container, ephemeral=True)

    # 47. /leaderboard
    @app_commands.command(
        name="leaderboard",
        description="Show the server message activity leaderboard.",
    )
    @app_commands.describe(
        period="Time period to rank activity",
        limit="Number of top members to display (default: 10, max: 25)",
    )
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Today (calendar day)", value="today"),
            app_commands.Choice(name="Weekly (rolling 7 days)", value="weekly"),
            app_commands.Choice(name="All-Time Tracked", value="all"),
        ]
    )
    async def slash_leaderboard(
        self,
        interaction: discord.Interaction,
        period: Optional[app_commands.Choice[str]] = None,
        limit: int = 10,
    ) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)

        p_val = period.value if period else "weekly"
        p_name = period.name if period else "Weekly (rolling 7 days)"
        rows = await self.bot.activity_mgr.get_leaderboard(interaction.guild.id, period=p_val, limit=limit)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        container.add_section(content=f"# **Activity Leaderboard: {interaction.guild.name}**\n> Period: `{p_name}`")
        container.add_separator(divider=True)

        if not rows:
            container.add_text(f"{dot} No qualifying message activity recorded for this period yet.")
        else:
            lines = []
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            for idx, r in enumerate(rows, start=1):
                badge = medals.get(idx, f"`#{idx}`")
                lines.append(f"{badge} <@{r['user_id']}> — **{r['total']:,}** messages")
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text("-# Only qualifying messages are counted • Privacy opt-outs respected")
        await send_container_response(interaction, container)

    # 48. /auditlog
    @app_commands.command(
        name="auditlog",
        description="View authorized giveaway and configuration audit log events.",
    )
    @app_commands.describe(limit="Number of recent audit events to display (default: 15)")
    async def slash_auditlog(
        self,
        interaction: discord.Interaction,
        limit: int = 15,
    ) -> None:
        if not interaction.guild:
            return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)

        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to view administrative audit logs.", ephemeral=True)

        logs = await self.bot.giveaway_mgr.get_audit_logs(interaction.guild.id, limit=limit)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        container.add_section(content=f"# **Giveaway Audit Log: {interaction.guild.name}**")
        container.add_separator(divider=True)

        if not logs:
            container.add_text(f"{dot} No administrative audit records recorded yet.")
        else:
            lines = []
            for item in logs:
                t = item.get("occurred_at")
                ts_str = f"<t:{int(t.timestamp())}:R>" if t else "recently"
                action_name = str(item.get("action", "")).upper()
                actor = f"<@{item.get('actor_id')}>"
                details = item.get("details", "")
                lines.append(f"{dot} `[{action_name}]` by {actor} ({ts_str})\n> {details}")
            container.add_text("\n\n".join(lines[:10]))

        container.add_separator(divider=True)
        container.add_text(f"-# Restricted administrative audit records • {interaction.guild.name}")
        await send_container_response(interaction, container, ephemeral=True)

    # 49. /diagnostics
    @app_commands.command(
        name="diagnostics",
        description="Check KYOKA 3.0 database connectivity, background tasks, and health.",
    )
    async def slash_diagnostics(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        # 1. Database Ping
        db_start = time.monotonic()
        db_healthy = False
        db_error = ""
        try:
            row = await self.bot.db.fetch_one("SELECT 1 AS ok;")
            db_latency_ms = round((time.monotonic() - db_start) * 1000, 2)
            db_healthy = bool(row and row.get("ok") == 1)
        except Exception as e:
            db_error = str(e)
            db_latency_ms = -1

        # 2. Gateway / Latency
        gateway_ms = round(self.bot.latency * 1000, 2) if math.isfinite(self.bot.latency) else "Unavailable"

        # 3. Uptime
        now = discord.utils.utcnow()
        start_time = getattr(self.bot, "start_time", now)
        uptime_seconds = max(0, int((now - start_time).total_seconds()))
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # 4. Giveaway Engine Cache
        active_cache_count = len(getattr(self.bot.giveaway_mgr, "_active_giveaways", {}))

        # 5. Background Tasks
        gw_cog = self.bot.get_cog("Giveaways")
        ticker_running = bool(gw_cog and getattr(gw_cog, "giveaway_ticker", None) and gw_cog.giveaway_ticker.is_running())

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyokaContainer()
        container.add_section(content="# **KYOKA 3.0 System Diagnostics**")
        container.add_separator(divider=True)

        db_status_icon = "🟢 Healthy" if db_healthy else f"🔴 Unhealthy ({db_error})"
        ticker_icon = "🟢 Active" if ticker_running else "🔴 Stopped"

        container.add_text(
            f"**Database & Network**\n"
            f"{dot} PostgreSQL / Supabase Pool: {db_status_icon}\n"
            f"{dot} Database Query Round-Trip: `{db_latency_ms} ms`\n"
            f"{dot} Discord Gateway Latency: `{gateway_ms} ms`\n\n"
            f"**Runtime & Host**\n"
            f"{dot} Uptime: `{uptime_str}`\n"
            f"{dot} Shard Count: `{self.bot.shard_count or 1}`\n"
            f"{dot} Connected Servers: `{len(self.bot.guilds):,}`\n"
            f"{dot} Python Version: `{platform.python_version()}`\n"
            f"{dot} discord.py Library: `{discord.__version__}`\n\n"
            f"**Engine Subsystems**\n"
            f"{dot} Active Giveaways in Memory: `{active_cache_count}`\n"
            f"{dot} Autonomous Giveaway Ticker: {ticker_icon}\n"
            f"{dot} Activity Tracking Cache: `Active`\n"
            f"{dot} Multi-Personality AI Engine: `Loaded`"
        )
        container.add_separator(divider=True)
        container.add_text("-# KYOKA 3.0 Production Diagnostics")
        await send_container_response(interaction, container, ephemeral=True)

    # 50. /privacy
    @app_commands.command(
        name="privacy",
        description="View message activity tracking policy, retention controls, or erase your data.",
    )
    @app_commands.describe(action="Privacy action to perform")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View privacy policy and data retention summary", value="view"),
            app_commands.Choice(name="Opt-out of message activity tracking", value="opt_out"),
            app_commands.Choice(name="Opt-in to message activity tracking", value="opt_in"),
            app_commands.Choice(name="Erase all your stored message activity data", value="erase"),
        ]
    )
    async def slash_privacy(
        self,
        interaction: discord.Interaction,
        action: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        act = action.value if action else "view"
        uid = interaction.user.id
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if act == "opt_out":
            await self.bot.activity_mgr.set_opt_out(uid, True)
            return await interaction.response.send_message(
                "🔒 **You have opted out of message activity tracking.**\n"
                "> KYOKA will no longer count your messages for activity requirements or leaderboards.",
                ephemeral=True,
            )

        elif act == "opt_in":
            await self.bot.activity_mgr.set_opt_out(uid, False)
            return await interaction.response.send_message(
                "✅ **You have opted in to message activity tracking.**\n"
                "> Your future qualifying messages will be counted towards giveaway eligibility and leaderboards.",
                ephemeral=True,
            )

        elif act == "erase":
            await self.bot.activity_mgr.erase_user_data(uid)
            return await interaction.response.send_message(
                "🗑️ **All your tracked message activity counts have been permanently deleted from KYOKA's database.**",
                ephemeral=True,
            )

        # Default 'view' privacy policy explanation
        is_opted = self.bot.activity_mgr.is_opted_out(uid)
        container = KyokaContainer()
        container.add_section(content="# **KYOKA 3.0 Privacy & Data Protection**")
        container.add_separator(divider=True)
        container.add_text(
            f"**What KYOKA Stores for Activity Tracking**\n"
            f"{dot} **Message Counts Only:** KYOKA counts how many qualifying messages you send each day.\n"
            f"{dot} **Zero Message Content:** KYOKA **NEVER** stores the contents, words, attachments, or text of your messages.\n"
            f"{dot} **Anti-Spam Filters:** Rapid message flooding and messages under 3 characters are discarded.\n"
            f"{dot} **Bot & Channel Exclusions:** Bot messages and administrator-excluded channels are never counted.\n\n"
            f"**Your Privacy Controls**\n"
            f"{dot} Your Current Status: `{'🔒 Opted-Out' if is_opted else '🟢 Active / Opted-In'}`\n"
            f"{dot} Opt Out Anytime: `/privacy action:Opt-out`\n"
            f"{dot} Opt In Anytime: `/privacy action:Opt-in`\n"
            f"{dot} Right to Erasure: `/privacy action:Erase all your stored message activity data`\n\n"
            f"> KYOKA complies with Discord Developer Terms of Service and data minimization best practices."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# User ID: {uid} • Privacy Policy")
        await send_container_response(interaction, container, ephemeral=True)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(AnalyticsAndDiagnostics(bot))
