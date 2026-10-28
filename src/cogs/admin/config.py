from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.utility.giveaway import is_giveaway_authorized
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Admin.Config")


class ConfirmResetView(discord.ui.View):
    """Interactive confirmation view for resetting server configuration."""

    def __init__(self, bot: KyokaBot, guild_id: int, user_id: int, scope: str) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.scope = scope
        self.value: Optional[bool] = None

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger, custom_id="cfg:confirm_reset")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the command author can confirm this.", ephemeral=True)

        if self.scope == "all" or self.scope == "giveaways":
            await self.bot.db.execute("DELETE FROM server_giveaway_config WHERE guild_id = $1;", self.guild_id)
            await self.bot.db.execute("DELETE FROM giveaway_requirements WHERE guild_id = $1 AND giveaway_id IS NULL;", self.guild_id)
            await self.bot.db.execute("DELETE FROM giveaway_bonus_roles WHERE guild_id = $1 AND giveaway_id IS NULL;", self.guild_id)

        if self.scope == "all" or self.scope == "ai":
            await self.bot.ai_mgr.reset_server_config(self.guild_id)

        if self.scope == "all" or self.scope == "activity":
            self.bot.activity_mgr.update_guild_config_cache(self.guild_id, enabled=True, cooldown=5, min_length=3)

        self.value = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Server configuration for **{self.scope}** has been reset to factory defaults.",
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cfg:cancel_reset")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the command author can cancel this.", ephemeral=True)
        self.value = False
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Reset cancelled.", view=self)


class ServerConfig(commands.Cog):
    """
    KYOKA 3.0 Server Configuration Cog.
    Houses the `/config` slash command group with all 8 documented subcommands.
    """

    category: str = "Admin"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    config_group = app_commands.Group(
        name="config",
        description="KYOKA 3.0 Server and Giveaway Configuration Console",
    )

    # 27. /config view
    @config_group.command(name="view", description="View current server configuration and feature settings.")
    async def slash_view(self, interaction: discord.Interaction) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to view server configuration.", ephemeral=True)

        gid = interaction.guild.id
        row = await self.bot.db.fetch_one("SELECT * FROM server_giveaway_config WHERE guild_id = $1;", gid)
        ai_cfg = self.bot.ai_mgr.get_server_config(gid)
        act_cfg = self.bot.activity_mgr.get_guild_config(gid)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyokaContainer()
        container.add_section(content=f"# **Server Configuration: {interaction.guild.name}**")
        container.add_separator(divider=True)

        # Giveaways & Channels
        gw_chan = f"<#{row['giveaway_channel_id']}>" if row and row.get("giveaway_channel_id") else "None"
        log_chan = f"<#{row['log_channel_id']}>" if row and row.get("log_channel_id") else "None"
        mgr_role = f"<@&{row['manager_role_id']}>" if row and row.get("manager_role_id") else "Administrators Only"
        ping_role = f"<@&{row['ping_role_id']}>" if row and row.get("ping_role_id") else "None"
        color = row.get("embed_color") if row and row.get("embed_color") else "#7C3AED (Default Purple)"

        container.add_text(
            f"**Giveaway System**\n"
            f"{dot} Manager Role: {mgr_role}\n"
            f"{dot} Dedicated Channel: {gw_chan}\n"
            f"{dot} Audit Log Channel: {log_chan}\n"
            f"{dot} Ping Notification Role: {ping_role}\n"
            f"{dot} Branding Accent Color: `{color}`\n"
        )
        container.add_separator(divider=True)

        # Activity Tracking
        container.add_text(
            f"**Activity Tracking**\n"
            f"{dot} Enabled: `{'Yes' if act_cfg['enabled'] else 'No'}`\n"
            f"{dot} Cooldown: `{act_cfg['cooldown']}s` per user\n"
            f"{dot} Min Message Length: `{act_cfg['min_length']}` characters\n"
            f"{dot} Excluded Channels: `{len(act_cfg['excluded_channels'])}` channels\n"
        )
        container.add_separator(divider=True)

        # AI Configuration
        ai_chan = f"<#{ai_cfg['channel_id']}>" if ai_cfg.get("channel_id") else "All allowed channels"
        container.add_text(
            f"**AI Persona**\n"
            f"{dot} Enabled: `{'Yes' if ai_cfg['enabled'] else 'No'}`\n"
            f"{dot} Personality Preset: `{ai_cfg.get('personality', 'aizen')}`\n"
            f"{dot} Tone / Humor: `{ai_cfg.get('tone')}` / `{ai_cfg.get('humor')}`\n"
            f"{dot} Response Length: `{ai_cfg.get('response_length')}`\n"
            f"{dot} AI Dedicated Channel: {ai_chan}\n"
        )

        await send_container_response(interaction, container, ephemeral=True)

    # 28. /config channel
    @config_group.command(name="channel", description="Configure dedicated channels for giveaways and audit logs.")
    @app_commands.describe(
        channel_type="Which channel to set",
        channel="The target text channel",
    )
    @app_commands.choices(
        channel_type=[
            app_commands.Choice(name="Dedicated Giveaway Channel", value="giveaway"),
            app_commands.Choice(name="Giveaway Audit Logs Channel", value="log"),
        ]
    )
    async def slash_channel(
        self,
        interaction: discord.Interaction,
        channel_type: app_commands.Choice[str],
        channel: discord.TextChannel,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to configure channels.", ephemeral=True)

        gid = interaction.guild.id
        if channel_type.value == "giveaway":
            col = "giveaway_channel_id"
        else:
            col = "log_channel_id"

        await self.bot.db.execute(
            f"""
            INSERT INTO server_giveaway_config (guild_id, {col}, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET {col} = $2, updated_at = CURRENT_TIMESTAMP;
            """,
            gid,
            channel.id,
        )

        await interaction.response.send_message(
            f"✅ Configured {channel_type.name} to {channel.mention}.", ephemeral=True
        )

    # 29. /config roles
    @config_group.command(name="roles", description="Configure management and notification roles.")
    @app_commands.describe(
        role_type="Which role to assign",
        role="The target role",
    )
    @app_commands.choices(
        role_type=[
            app_commands.Choice(name="Giveaway Manager Role", value="manager"),
            app_commands.Choice(name="Giveaway Ping Notification Role", value="ping"),
            app_commands.Choice(name="Winner Role (awarded on winning)", value="winner"),
        ]
    )
    async def slash_roles(
        self,
        interaction: discord.Interaction,
        role_type: app_commands.Choice[str],
        role: discord.Role,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to configure roles.", ephemeral=True)

        col_map = {
            "manager": "manager_role_id",
            "ping": "ping_role_id",
            "winner": "winner_role_id",
        }
        col = col_map[role_type.value]

        await self.bot.db.execute(
            f"""
            INSERT INTO server_giveaway_config (guild_id, {col}, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET {col} = $2, updated_at = CURRENT_TIMESTAMP;
            """,
            interaction.guild.id,
            role.id,
        )

        await interaction.response.send_message(
            f"✅ Configured {role_type.name} to {role.mention}.", ephemeral=True
        )

    # 30. /config permissions
    @config_group.command(name="permissions", description="Configure who can create and manage giveaways.")
    @app_commands.describe(
        access_level="Who is permitted to host and manage giveaways",
    )
    @app_commands.choices(
        access_level=[
            app_commands.Choice(name="Server Administrators Only", value="admin_only"),
            app_commands.Choice(name="Server Admins + Configured Manager Role", value="manager_role"),
            app_commands.Choice(name="Anyone with Manage Messages permission", value="manage_messages"),
        ]
    )
    async def slash_permissions(
        self,
        interaction: discord.Interaction,
        access_level: app_commands.Choice[str],
    ) -> None:
        if not interaction.user.guild_permissions.administrator and not is_primary_owner(interaction.user.id):
            return await interaction.response.send_message("Only server administrators can modify access permissions.", ephemeral=True)

        # If admin_only is chosen, remove the manager role binding
        if access_level.value == "admin_only":
            await self.bot.db.execute(
                "UPDATE server_giveaway_config SET manager_role_id = NULL WHERE guild_id = $1;",
                interaction.guild.id,
            )

        await interaction.response.send_message(
            f"✅ Configured giveaway access policy to: **{access_level.name}**.", ephemeral=True
        )

    # 31. /config appearance
    @config_group.command(name="appearance", description="Configure embed colors and branding.")
    @app_commands.describe(
        embed_color="Hex color code for giveaway embeds (e.g. #7C3AED, #9B59B6, #E74C3C)",
    )
    async def slash_appearance(
        self,
        interaction: discord.Interaction,
        embed_color: str,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to customize appearance.", ephemeral=True)

        clean_color = embed_color.strip()
        if not clean_color.startswith("#"):
            clean_color = f"#{clean_color}"

        await self.bot.db.execute(
            """
            INSERT INTO server_giveaway_config (guild_id, embed_color, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET embed_color = $2, updated_at = CURRENT_TIMESTAMP;
            """,
            interaction.guild.id,
            clean_color,
        )

        await interaction.response.send_message(f"✅ Set default giveaway embed accent color to `{clean_color}`.", ephemeral=True)

    # 32. /config notifications
    @config_group.command(name="notifications", description="Configure giveaway start, end, and reminder notifications.")
    @app_commands.describe(
        notify_on_start="Ping notification role when a new giveaway begins",
        notify_on_end="Mention winners in channel when a giveaway ends",
        reminder_intervals="Comma-separated countdown reminder times (e.g. 1h,15m)",
    )
    async def slash_notifications(
        self,
        interaction: discord.Interaction,
        notify_on_start: bool = True,
        notify_on_end: bool = True,
        reminder_intervals: str = "1h,15m",
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to configure notifications.", ephemeral=True)

        await self.bot.db.execute(
            """
            INSERT INTO server_giveaway_config (
                guild_id, notify_on_start, notify_on_end, reminder_intervals, updated_at
            )
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET
                notify_on_start = $2,
                notify_on_end = $3,
                reminder_intervals = $4,
                updated_at = CURRENT_TIMESTAMP;
            """,
            interaction.guild.id,
            notify_on_start,
            notify_on_end,
            reminder_intervals,
        )

        await interaction.response.send_message(
            f"✅ Configured notifications:\n"
            f"• Ping on start: `{'Yes' if notify_on_start else 'No'}`\n"
            f"• Mention winners: `{'Yes' if notify_on_end else 'No'}`\n"
            f"• Reminder intervals: `{reminder_intervals}`",
            ephemeral=True,
        )

    # 33. /config activity
    @config_group.command(name="activity", description="Configure message activity tracking rules.")
    @app_commands.describe(
        enabled="Enable or disable message activity tracking for this server",
        cooldown_seconds="Minimum seconds between counted messages per user (default: 5)",
        min_length="Minimum message character length to qualify (default: 3)",
        exclude_channel="Channel to exclude from message tracking",
    )
    async def slash_activity_config(
        self,
        interaction: discord.Interaction,
        enabled: bool = True,
        cooldown_seconds: int = 5,
        min_length: int = 3,
        exclude_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to configure activity tracking.", ephemeral=True)

        gid = interaction.guild.id
        current = self.bot.activity_mgr.get_guild_config(gid)
        excluded = list(current.get("excluded_channels", []))
        if exclude_channel and exclude_channel.id not in excluded:
            excluded.append(exclude_channel.id)

        excluded_str = ",".join(str(c) for c in excluded)

        await self.bot.db.execute(
            """
            INSERT INTO server_giveaway_config (
                guild_id, activity_tracking_enabled, activity_cooldown_seconds,
                activity_min_length, activity_excluded_channels, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET
                activity_tracking_enabled = $2,
                activity_cooldown_seconds = $3,
                activity_min_length = $4,
                activity_excluded_channels = $5,
                updated_at = CURRENT_TIMESTAMP;
            """,
            gid,
            enabled,
            cooldown_seconds,
            min_length,
            excluded_str,
        )

        self.bot.activity_mgr.update_guild_config_cache(
            gid,
            enabled=enabled,
            cooldown=cooldown_seconds,
            excluded_channels=excluded,
            min_length=min_length,
        )

        await interaction.response.send_message(
            f"✅ Updated activity tracking settings:\n"
            f"• Enabled: `{'Yes' if enabled else 'No'}`\n"
            f"• Cooldown: `{cooldown_seconds}s`\n"
            f"• Min length: `{min_length}` chars\n"
            f"• Excluded channels: `{len(excluded)}`",
            ephemeral=True,
        )

    # 34. /config reset
    @config_group.command(name="reset", description="Reset server configurations to default settings.")
    @app_commands.describe(scope="Which settings scope to reset")
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="All Server Configurations", value="all"),
            app_commands.Choice(name="Giveaway Configurations", value="giveaways"),
            app_commands.Choice(name="AI Configuration", value="ai"),
            app_commands.Choice(name="Activity Tracking Settings", value="activity"),
        ]
    )
    async def slash_reset(
        self,
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
    ) -> None:
        if not interaction.user.guild_permissions.administrator and not is_primary_owner(interaction.user.id):
            return await interaction.response.send_message("Only server administrators can reset configurations.", ephemeral=True)

        view = ConfirmResetView(self.bot, interaction.guild.id, interaction.user.id, scope.value)
        await interaction.response.send_message(
            f"⚠️ **Are you sure you want to reset {scope.name}?**\n"
            "> This will restore default settings. Click below to confirm or cancel.",
            view=view,
            ephemeral=True,
        )

    # ─── PREFIX COMMAND GROUP ────────────────────────────────────────────────

    @commands.group(name="config", aliases=["cfg", "serverconfig"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def prefix_config(self, ctx: commands.Context) -> None:
        """KYOKA 3.0 Server and Giveaway Configuration Console via prefix."""
        p = ctx.prefix
        await ctx.send(
            f"**Server Configuration Console**\n"
            f"> `{p}config view` — Inspect current server giveaway and activity configurations\n"
            f"> `{p}config channel <channel_type> <#channel>` — Bind channels (giveaway/announcement)\n"
            f"> `{p}config roles <@role>` — Configure giveaway manager role\n"
            f"> `{p}config reset [scope]` — Reset configurations to defaults"
        )

    @prefix_config.command(name="view")
    @commands.has_permissions(manage_guild=True)
    async def prefix_config_view(self, ctx: commands.Context) -> None:
        gid = ctx.guild.id
        row = await self.bot.db.fetch_one("SELECT * FROM server_giveaway_config WHERE guild_id = $1;", gid)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyokaContainer()
        container.add_section(content=f"# **Server Configuration: {ctx.guild.name}**")
        container.add_separator(divider=True)
        gw_chan = f"<#{row['giveaway_channel_id']}>" if row and row.get("giveaway_channel_id") else "None"
        mgr_role = f"<@&{row['manager_role_id']}>" if row and row.get("manager_role_id") else "Default (Staff)"
        container.add_text(
            f"**Giveaway Defaults**\n"
            f"{dot} Default Channel: {gw_chan}\n"
            f"{dot} Manager Role: {mgr_role}\n"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# {ctx.guild.name} Configuration")
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ServerConfig(bot))
