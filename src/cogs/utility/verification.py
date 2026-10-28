"""
Kyoka Discord Bot - Discord-Style Server Member Verification System
Enforces Discord role and channel permission isolation for unverified members.
Supports Button, Rules Acknowledgment, and Simple Math/Code Challenges with anti-raid rate limits.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.Verification")
PURPLE = Config.COLORS.PRIMARY


class VerificationChallengeModal(discord.ui.Modal, title="Server Verification Challenge"):
    """Interactive modal challenge verifying human intent."""

    def __init__(self, cog: Verification, num1: int, num2: int) -> None:
        super().__init__()
        self.cog = cog
        self.num1 = num1
        self.num2 = num2
        self.answer = str(num1 + num2)

        self.answer_input = discord.ui.TextInput(
            label=f"What is {num1} + {num2}?",
            placeholder="Type your numeric answer here",
            required=True,
            max_length=5,
        )
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.answer_input.value).strip()
        if val != self.answer:
            await interaction.response.send_message(
                "❌ Incorrect answer. Please click the button and try again.",
                ephemeral=True,
            )
            return

        await self.cog.handle_member_verified(interaction, method="challenge")


class VerificationRulesView(discord.ui.View):
    """View presenting community rules acknowledgement."""

    def __init__(self, cog: Verification) -> None:
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="I Agree & Accept Rules", style=discord.ButtonStyle.success, emoji="✅")
    async def agree(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_member_verified(interaction, method="rules")
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass


class PersistentVerifyView(discord.ui.View):
    """Persistent interactive panel view for member verification."""

    def __init__(self, cog: Verification) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Verify Me",
        style=discord.ButtonStyle.success,
        emoji="🛡️",
        custom_id="kyoka:verify:member",
        row=0,
    )
    async def btn_verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Verification is only available in a server.", ephemeral=True)

        settings = await self.cog.get_settings(interaction.guild.id)
        if not settings or not settings.get("enabled", True):
            return await interaction.response.send_message("Verification is currently disabled on this server.", ephemeral=True)

        method = (settings.get("method") or "button").lower()
        if method == "challenge":
            n1 = random.randint(3, 9)
            n2 = random.randint(2, 8)
            return await interaction.response.send_modal(VerificationChallengeModal(self.cog, n1, n2))
        elif method == "rules":
            rules_view = VerificationRulesView(self.cog)
            return await interaction.response.send_message(
                "📋 **Community Rules Agreement**\n\n"
                "1. Treat everyone with respect.\n"
                "2. No spamming, advertising, or unsolicited DMs.\n"
                "3. Follow Discord's Terms of Service and Community Guidelines.\n\n"
                "Click the button below to accept and complete verification:",
                view=rules_view,
                ephemeral=True,
            )
        else:
            # Direct button verification
            await self.cog.handle_member_verified(interaction, method="button")

    @discord.ui.button(
        label="Help / Issues",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="kyoka:verify:help",
        row=0,
    )
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "ℹ️ **Having trouble verifying?**\n"
            "• Ensure your internet connection is stable.\n"
            "• Check that you do not have server direct messages blocked.\n"
            "• Contact server moderators if issues persist.",
            ephemeral=True,
        )


class Verification(commands.Cog):
    """
    KYOKA 3.0 Enterprise Member Verification System.
    Enforces real Discord role & channel isolation for unverified members.
    """
    category: str = "Verification"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._rate_limits: dict[int, float] = {}

    async def cog_load(self) -> None:
        """Register persistent view upon cog load."""
        self.bot.add_view(PersistentVerifyView(self))

    async def get_settings(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Retrieve server verification configuration."""
        try:
            row = await self.bot.db.fetch_one(
                "SELECT * FROM kyoka_verification_settings WHERE guild_id = $1;",
                guild_id,
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching verification settings for guild {guild_id}: {e}")
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Assign unverified role to new members when verification is active."""
        if member.bot:
            return

        guild = member.guild
        settings = await self.get_settings(guild.id)
        if not settings or not settings.get("enabled", True):
            return

        unverified_role_id = settings.get("unverified_role_id")
        if not unverified_role_id:
            return

        unverified_role = guild.get_role(int(unverified_role_id))
        if not unverified_role:
            return

        me = guild.me
        if not me or not me.guild_permissions.manage_roles or me.top_role <= unverified_role:
            logger.warning(f"Cannot assign unverified role in guild {guild.id}: bot lacks permissions or role hierarchy.")
            return

        # Check minimum account age requirement
        min_age = int(settings.get("min_account_age_days", 0) or 0)
        now = discord.utils.utcnow()
        account_age_days = (now - member.created_at).days

        if min_age > 0 and account_age_days < min_age:
            logger.info(f"Member {member.id} in {guild.id} has account age {account_age_days}d < required {min_age}d.")
            # Record failed verification
            await self.bot.db.execute(
                """
                INSERT INTO kyoka_verification_records (guild_id, user_id, joined_at, status, method, failure_count)
                VALUES ($1, $2, $3, 'failed_age', 'auto', 1);
                """,
                guild.id,
                member.id,
                now,
            )
            # Log to log channel
            log_ch_id = settings.get("log_channel_id")
            if log_ch_id:
                ch = guild.get_channel(int(log_ch_id))
                if isinstance(ch, discord.TextChannel):
                    try:
                        await ch.send(
                            f"⚠️ **Verification Blocked**: {member.mention} (`{member.id}`) account is {account_age_days} days old (minimum required: {min_age} days)."
                        )
                    except Exception:
                        pass
            return

        try:
            await member.add_roles(unverified_role, reason="KYOKA Verification: New member join")
            # Record pending record
            await self.bot.db.execute(
                """
                INSERT INTO kyoka_verification_records (guild_id, user_id, joined_at, status, method)
                VALUES ($1, $2, $3, 'pending', 'auto')
                ON CONFLICT DO NOTHING;
                """,
                guild.id,
                member.id,
                now,
            )
        except Exception as e:
            logger.error(f"Failed to assign unverified role to {member.id} in {guild.id}: {e}")

    async def handle_member_verified(self, interaction: discord.Interaction, method: str) -> None:
        """Process successful verification: remove unverified role, assign verified role, record stats."""
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        # Rate limit clicks
        now = time.monotonic()
        last_click = self._rate_limits.get(member.id, 0.0)
        if now - last_click < 3.0:
            return await interaction.response.send_message("Please wait a moment before trying again.", ephemeral=True)
        self._rate_limits[member.id] = now

        settings = await self.get_settings(guild.id)
        if not settings:
            return await interaction.response.send_message("Verification is not configured on this server.", ephemeral=True)

        verified_role_id = settings.get("role_id")
        verified_role = guild.get_role(int(verified_role_id)) if verified_role_id else None

        if not verified_role:
            return await interaction.response.send_message("The verified role no longer exists. Please alert an administrator.", ephemeral=True)

        if verified_role in member.roles:
            return await interaction.response.send_message("✅ You are already verified on this server!", ephemeral=True)

        me = guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ KYOKA lacks **Manage Roles** permission.", ephemeral=True)

        if me.top_role <= verified_role:
            return await interaction.response.send_message(
                f"❌ KYOKA's highest role must be above {verified_role.mention} in Server Settings -> Roles.",
                ephemeral=True,
            )

        unverified_role_id = settings.get("unverified_role_id")
        unverified_role = guild.get_role(int(unverified_role_id)) if unverified_role_id else None

        # Execute role assignments
        try:
            roles_to_add = [verified_role]
            roles_to_remove = []
            if unverified_role and unverified_role in member.roles:
                roles_to_remove.append(unverified_role)

            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="KYOKA Verification: Member verified")
            await member.add_roles(*roles_to_add, reason=f"KYOKA Verification: Completed via {method}")

            # Record in database
            await self.bot.db.execute(
                """
                INSERT INTO kyoka_verification_records (guild_id, user_id, joined_at, verified_at, method, status)
                VALUES ($1, $2, $3, $3, $4, 'verified');
                """,
                guild.id,
                member.id,
                discord.utils.utcnow(),
                method,
            )

            await interaction.response.send_message(
                f"✅ **Verification Complete!**\n> Welcome to **{guild.name}**, {member.mention}! You now have full access.",
                ephemeral=True,
            )

            # Log to verification log channel
            log_ch_id = settings.get("log_channel_id")
            if log_ch_id:
                log_ch = guild.get_channel(int(log_ch_id))
                if isinstance(log_ch, discord.TextChannel):
                    try:
                        container = KyokaContainer()
                        container.add_section(
                            content=(
                                f"🛡️ **Member Verified**\n"
                                f"> Member: {member.mention} `「{member.id}」`\n"
                                f"> Method: `{method.title()}`\n"
                                f"> Timestamp: <t:{int(time.time())}:R>"
                            )
                        )
                        await send_container_response(log_ch, container)
                    except Exception:
                        pass

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing permissions to assign or remove roles. Please contact server staff.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error executing verification for {member.id} in {guild.id}: {e}")
            await interaction.response.send_message(
                "❌ An error occurred during verification. Please try again later.",
                ephemeral=True,
            )

    # ─── VERIFICATION COMMANDS (PREFIX + SLASH) ──────────────────────────────

    @commands.group(
        name="verify",
        aliases=["verification"],
        description="Configure and manage the KYOKA Discord server verification system.",
        invoke_without_command=True,
    )
    async def verify_group(self, ctx: CustomContext) -> None:
        """Display verification status and commands overview."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        settings = await self.get_settings(ctx.guild.id)

        container = KyokaContainer()
        status_text = "🟢 Enabled" if (settings and settings.get("enabled", True)) else "🔴 Disabled"
        container.add_section(
            content=(
                f"🛡️ **KYOKA Server Verification Hub**\n"
                f"> Current Status: **{status_text}**\n"
                f"> Gatekeep channels and verify new members with actual Discord role permissions."
            )
        )
        container.add_separator(divider=True)

        if settings:
            v_role = f"<@&{settings['role_id']}>" if settings.get("role_id") else "`Not configured`"
            u_role = f"<@&{settings['unverified_role_id']}>" if settings.get("unverified_role_id") else "`None`"
            ch_m = f"<#{settings['channel_id']}>" if settings.get("channel_id") else "`Not set`"
            method_str = (settings.get("method") or "button").title()
            container.add_text(
                f"• **Verified Role:** {v_role}\n"
                f"• **Unverified Role:** {u_role}\n"
                f"• **Verification Channel:** {ch_m}\n"
                f"• **Method:** `{method_str}`"
            )
        else:
            container.add_text("No verification settings configured yet. Use `+verify setup` to begin.")

        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}verify setup <@role>` — Complete guided setup\n"
            f"`{prefix}verify panel` — Post verification card\n"
            f"`{prefix}verify method <button|rules|challenge>` — Switch verification method\n"
            f"`{prefix}verify stats` — View verification metrics\n"
            f"`{prefix}verify user <@member>` — Manually verify a member"
        )
        await send_container_response(ctx, container)

    @verify_group.command(
        name="setup",
        description="Configure verification with verified role, optional unverified role, and channel.",
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_setup(
        self,
        ctx: CustomContext,
        verified_role: discord.Role,
        unverified_role: Optional[discord.Role] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Full setup for server verification."""
        me = ctx.guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await ctx.send_error("KYOKA requires the **Manage Roles** permission to operate verification.")

        if verified_role >= me.top_role:
            return await ctx.send_error(f"Cannot manage {verified_role.mention}. Move KYOKA's highest role above it.")

        if unverified_role and unverified_role >= me.top_role:
            return await ctx.send_error(f"Cannot manage {unverified_role.mention}. Move KYOKA's highest role above it.")

        target_channel = channel or ctx.channel
        u_role_id = unverified_role.id if unverified_role else None

        await self.bot.db.execute(
            """
            INSERT INTO kyoka_verification_settings (
                guild_id, role_id, unverified_role_id, channel_id, enabled, updated_at
            )
            VALUES ($1, $2, $3, $4, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE SET
                role_id = EXCLUDED.role_id,
                unverified_role_id = EXCLUDED.unverified_role_id,
                channel_id = EXCLUDED.channel_id,
                enabled = TRUE,
                updated_at = CURRENT_TIMESTAMP;
            """,
            ctx.guild.id,
            verified_role.id,
            u_role_id,
            target_channel.id,
        )

        container = KyokaContainer()
        container.add_section(
            content=(
                f"✅ **Verification Configured Successfully!**\n"
                f"> **Verified Role:** {verified_role.mention}\n"
                f"> **Unverified Role:** {unverified_role.mention if unverified_role else '`None`'}\n"
                f"> **Channel:** {target_channel.mention}\n\n"
                f"💡 **Discord Channel Permission Reminder:**\n"
                f"> To complete channel isolation, ensure your private channels deny **View Channel** to `{unverified_role.name if unverified_role else '@everyone'}` "
                f"and allow **View Channel** to `{verified_role.name}`. Do not forget to keep {target_channel.mention} visible to unverified members!\n\n"
                f"Use `+verify panel` in {target_channel.mention} to post the interactive verification card."
            )
        )
        await send_container_response(ctx, container)

    @verify_group.command(name="panel", description="Deploy the interactive verification panel into the verification channel.")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_panel(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Deploy verification card and button view."""
        settings = await self.get_settings(ctx.guild.id)
        if not settings or not settings.get("role_id"):
            return await ctx.send_error("Please configure a verified role first using `+verify setup @Role`.")

        target_ch = channel or (ctx.guild.get_channel(settings["channel_id"]) if settings.get("channel_id") else ctx.channel)
        if not isinstance(target_ch, discord.TextChannel):
            target_ch = ctx.channel

        container = KyokaContainer()
        container.add_section(
            content=(
                f"🛡️ **Welcome to {ctx.guild.name} • Verification**\n"
                f"> To access server channels and participate in the community, click the **Verify Me** button below."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            "• Please read and adhere to our server rules.\n"
            "• Automated anti-spam protection is active.\n"
            "• Click the button below to complete verification."
        )

        view = PersistentVerifyView(self)
        msg = await send_container_response(target_ch, container, view=view)

        # Update saved message_id
        await self.bot.db.execute(
            "UPDATE kyoka_verification_settings SET panel_message_id = $2, channel_id = $3 WHERE guild_id = $1;",
            ctx.guild.id,
            msg.id,
            target_ch.id,
        )

        if target_ch.id != ctx.channel.id:
            await ctx.send_success(f"Verification panel published in {target_ch.mention}!")

    @verify_group.command(name="method", description="Set verification method: button, rules, or challenge.")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_method(self, ctx: CustomContext, method: str) -> None:
        """Switch verification mechanism."""
        clean = method.lower().strip()
        if clean not in ("button", "rules", "challenge"):
            return await ctx.send_error("Invalid method. Choose from: `button`, `rules`, or `challenge`.")

        await self.bot.db.execute(
            "UPDATE kyoka_verification_settings SET method = $2, updated_at = CURRENT_TIMESTAMP WHERE guild_id = $1;",
            ctx.guild.id,
            clean,
        )
        await ctx.send_success(f"Verification method set to **{clean.title()}**.")

    @verify_group.command(name="enable", description="Enable verification on this server.")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_enable(self, ctx: CustomContext) -> None:
        """Enable verification."""
        await self.bot.db.execute(
            "UPDATE kyoka_verification_settings SET enabled = TRUE, updated_at = CURRENT_TIMESTAMP WHERE guild_id = $1;",
            ctx.guild.id,
        )
        await ctx.send_success("Server verification has been **enabled**.")

    @verify_group.command(name="disable", description="Disable verification on this server.")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_disable(self, ctx: CustomContext) -> None:
        """Disable verification."""
        await self.bot.db.execute(
            "UPDATE kyoka_verification_settings SET enabled = FALSE, updated_at = CURRENT_TIMESTAMP WHERE guild_id = $1;",
            ctx.guild.id,
        )
        await ctx.send_warning("Server verification has been **disabled**.")

    @verify_group.command(name="stats", description="View server verification metrics and pass rates.")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_stats(self, ctx: CustomContext) -> None:
        """Show verification statistics."""
        row_tot = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM kyoka_verification_records WHERE guild_id = $1;",
            ctx.guild.id,
        )
        row_ver = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM kyoka_verification_records WHERE guild_id = $1 AND status = 'verified';",
            ctx.guild.id,
        )
        row_fail = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM kyoka_verification_records WHERE guild_id = $1 AND status LIKE 'fail%';",
            ctx.guild.id,
        )

        total = int(row_tot["cnt"]) if row_tot else 0
        verified = int(row_ver["cnt"]) if row_ver else 0
        failed = int(row_fail["cnt"]) if row_fail else 0
        rate = f"{(verified / max(1, total)) * 100:.1f}%" if total > 0 else "N/A"

        container = KyokaContainer()
        container.add_section(
            content=(
                f"📊 **Verification Metrics • {ctx.guild.name}**\n"
                f"> Total Join Attempts: `{total}`\n"
                f"> Verified Members: `{verified}`\n"
                f"> Failed Attempts: `{failed}`\n"
                f"> Completion Rate: **{rate}**"
            )
        )
        await send_container_response(ctx, container)

    @verify_group.command(name="user", description="Manually verify a member (staff override).")
    @commands.has_guild_permissions(manage_roles=True)
    async def verify_user(self, ctx: CustomContext, member: discord.Member) -> None:
        """Staff command to manually verify a member."""
        settings = await self.get_settings(ctx.guild.id)
        if not settings or not settings.get("role_id"):
            return await ctx.send_error("Verification is not configured on this server.")

        v_role = ctx.guild.get_role(int(settings["role_id"]))
        if not v_role:
            return await ctx.send_error("Verified role not found.")

        u_role_id = settings.get("unverified_role_id")
        u_role = ctx.guild.get_role(int(u_role_id)) if u_role_id else None

        if u_role and u_role in member.roles:
            await member.remove_roles(u_role, reason=f"Manual verification by {ctx.author}")
        if v_role not in member.roles:
            await member.add_roles(v_role, reason=f"Manual verification by {ctx.author}")

        await self.bot.db.execute(
            """
            INSERT INTO kyoka_verification_records (guild_id, user_id, joined_at, verified_at, method, status, moderator_id)
            VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'manual', 'verified', $3);
            """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
        )

        await ctx.send_success(f"Manually verified {member.mention}!")

    @verify_group.command(name="remove", description="Remove verification status and re-isolate a member.")
    @commands.has_guild_permissions(manage_roles=True)
    async def verify_remove(self, ctx: CustomContext, member: discord.Member) -> None:
        """Remove verified role and restore unverified role."""
        settings = await self.get_settings(ctx.guild.id)
        if not settings:
            return await ctx.send_error("Verification is not configured on this server.")

        v_role = ctx.guild.get_role(int(settings.get("role_id", 0)))
        u_role = ctx.guild.get_role(int(settings.get("unverified_role_id", 0))) if settings.get("unverified_role_id") else None

        if v_role and v_role in member.roles:
            await member.remove_roles(v_role, reason=f"Unverified by {ctx.author}")
        if u_role and u_role not in member.roles:
            await member.add_roles(u_role, reason=f"Unverified by {ctx.author}")

        await ctx.send_warning(f"Removed verification status from {member.mention}.")

    @verify_group.command(name="reset", description="Reset all server verification settings.")
    @commands.has_guild_permissions(administrator=True)
    async def verify_reset(self, ctx: CustomContext) -> None:
        """Reset verification configuration."""
        await self.bot.db.execute("DELETE FROM kyoka_verification_settings WHERE guild_id = $1;", ctx.guild.id)
        await ctx.send_success("Server verification configuration has been reset.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Verification(bot))
