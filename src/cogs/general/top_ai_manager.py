"""
Kyoka 3.0 - Top AI Manager, Service Billing & Staff Application System Cog
Integrates natural-language pricing queries, decimal-safe tax calculations,
persistent bill generation with Discord message ID verification, period financial reports,
and Appy-style staff recruitment workflows with persistent UI modals and review panels.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.managers.top_manager import TopManager, CalculationResult, MultiCalculationResult, PriceItem, PRIMARY_OWNER_ID, clean_service_display_name
from src.security.adult_guard import add_adult_user, remove_adult_user, list_adult_users
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.TopAIManager")

# Fallback Aizen avatar / thumbnail
AIZEN_THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif"


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD UI: APPY-STYLE STAFF APPLICATION MODALS & VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class StaffApplicationModal(discord.ui.Modal):
    """Discord Modal gathering staff application responses respecting Discord limits."""

    def __init__(self, top_mgr: TopManager, position: str):
        super().__init__(title=f"Kyoka Staff: {position[:20]}")
        self.top_mgr = top_mgr
        self.position = position

        self.availability_input = discord.ui.TextInput(
            label="Timezone & Daily Availability",
            placeholder="e.g. EST (UTC-5), 4-6 hours per day",
            required=True,
            max_length=150,
        )
        self.add_item(self.availability_input)

        self.experience_input = discord.ui.TextInput(
            label="Relevant Experience",
            style=discord.TextStyle.paragraph,
            placeholder="Detail your Discord moderation, Blox Fruits trading, or service experience...",
            required=True,
            max_length=500,
        )
        self.add_item(self.experience_input)

        self.motivation_input = discord.ui.TextInput(
            label="Why Kyoka Staff?",
            style=discord.TextStyle.paragraph,
            placeholder="Why do you want to join our staff team and what makes you reliable?",
            required=True,
            max_length=500,
        )
        self.add_item(self.motivation_input)

        self.scenario_input = discord.ui.TextInput(
            label="Handling Disputes / Difficult Clients",
            style=discord.TextStyle.paragraph,
            placeholder="How do you handle an unhappy client or suspected voucher fraud?",
            required=True,
            max_length=500,
        )
        self.add_item(self.scenario_input)

        self.comments_input = discord.ui.TextInput(
            label="Additional Notes / References",
            placeholder="Any vouches, portfolio links, or questions for management...",
            required=False,
            max_length=300,
        )
        self.add_item(self.comments_input)

    async def on_submit(self, interaction: discord.Interaction):
        answers = {
            "Timezone & Availability": self.availability_input.value.strip(),
            "Relevant Experience": self.experience_input.value.strip(),
            "Why Kyoka Staff": self.motivation_input.value.strip(),
            "Handling Disputes": self.scenario_input.value.strip(),
            "Additional Notes": self.comments_input.value.strip() or "None",
        }

        try:
            app = self.top_mgr.submit_application(
                guild_id=interaction.guild_id or 0,
                applicant_id=interaction.user.id,
                applicant_name=str(interaction.user),
                position=self.position,
                answers=answers,
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"⚠️ **Application Error:** {e}",
                ephemeral=True,
            )

        # Notify review channel if configured
        cfg = self.top_mgr.get_app_config(interaction.guild_id or 0)
        review_ch_id = cfg.get("review_channel_id")
        if review_ch_id and interaction.guild:
            review_ch = interaction.guild.get_channel(review_ch_id)
            if review_ch and isinstance(review_ch, discord.TextChannel):
                embed = discord.Embed(
                    title=f"📥 NEW STAFF APPLICATION • {app['id']}",
                    description=f"**Applicant:** {interaction.user.mention} (`{interaction.user.id}`)\n**Position:** `{self.position}`\n**Status:** 🟡 **PENDING REVIEW**",
                    color=KyokaTheme.PRIMARY,
                    timestamp=discord.utils.utcnow(),
                )
                for q, a in answers.items():
                    embed.add_field(name=f"❓ {q}", value=f"> {a[:900]}", inline=False)

                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                embed.set_footer(text=f"Kyoka Top AI Manager • Application ID: {app['id']}")

                view = StaffApplicationReviewView(self.top_mgr, app["id"], interaction.user.id)
                try:
                    await review_ch.send(embed=embed, view=view)
                except Exception as ex:
                    logger.warning(f"Failed to send staff application to review channel: {ex}")

        # Send private confirmation
        confirm_embed = discord.Embed(
            title="✅ Application Submitted Successfully",
            description=(
                f"Thank you, {interaction.user.mention}! Your application for **{self.position}** has been received.\n\n"
                f"• **Application ID:** `{app['id']}`\n"
                f"• **Status:** 🟡 **PENDING**\n"
                f"• Our senior staff will review your submission. You will receive an automated notification once a decision is made."
            ),
            color=KyokaTheme.SUCCESS,
        )
        confirm_embed.set_footer(text="Kyoka Staff Recruitment Engine")
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)


def is_app_reviewer(user: Any, guild: Optional[discord.Guild], top_mgr: TopManager) -> bool:
    """Check if member has authority to review applications."""
    if getattr(user, "id", 0) == 1505515188991033409:
        return True
    if hasattr(user, "guild_permissions"):
        if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
            return True
        if guild:
            cfg = top_mgr.get_app_config(guild.id)
            rev_role_id = cfg.get("reviewer_role_id")
            if rev_role_id and any(r.id == rev_role_id for r in getattr(user, "roles", [])):
                return True
    return False


def build_app_review_embed(app: dict[str, Any], applicant_user: Optional[Any] = None) -> discord.Embed:
    """Construct or refresh the staff application review embed."""
    status_emoji = {
        "PENDING": "🟡",
        "SUBMITTED": "🟡",
        "UNDER_REVIEW": "🟠",
        "MORE_INFO_REQUESTED": "💬",
        "ACCEPTED": "🟢",
        "REJECTED": "🔴",
        "CLOSED": "📁",
        "WITHDRAWN": "⚪",
    }.get(app.get("status", "PENDING"), "⚪")

    color = KyokaTheme.PRIMARY
    if app.get("status") == "ACCEPTED":
        color = KyokaTheme.SUCCESS
    elif app.get("status") in ("REJECTED", "CLOSED"):
        color = KyokaTheme.ERROR
    elif app.get("status") == "MORE_INFO_REQUESTED":
        color = KyokaTheme.WARNING

    embed = discord.Embed(
        title=f"📥 STAFF APPLICATION • {app['id']}",
        description=(
            f"**Applicant:** <@{app['applicant_id']}> (`{app.get('applicant_name', 'Unknown')}`)\n"
            f"**Position:** `{app.get('position', 'Staff Candidate')}`\n"
            f"**Status:** {status_emoji} **{app.get('status', 'PENDING')}**\n"
            f"**Submitted:** <t:{int(app.get('created_at', time.time()))}:R>"
        ),
        color=color,
        timestamp=discord.utils.utcnow(),
    )

    for q, a in app.get("answers", {}).items():
        embed.add_field(name=f"❓ {q}", value=f"> {str(a)[:900]}", inline=False)

    if app.get("decision_reason"):
        embed.add_field(name="⚖️ Decision Notes", value=f"> {app['decision_reason']}", inline=False)

    if app.get("staff_notes"):
        embed.add_field(name="📝 Private Staff Notes", value=f"> {app['staff_notes'][:900]}", inline=False)

    if applicant_user and getattr(applicant_user, "display_avatar", None):
        embed.set_thumbnail(url=applicant_user.display_avatar.url)

    reviewer_str = app.get("reviewer_name") or "Pending"
    embed.set_footer(text=f"Application ID: {app['id']} • Reviewer: {reviewer_str}")
    return embed


class StaffApplicationRejectModal(discord.ui.Modal, title="🔴 Reject Staff Application"):
    def __init__(self, top_mgr: TopManager, app_id: str, applicant_id: int):
        super().__init__()
        self.top_mgr = top_mgr
        self.app_id = app_id
        self.applicant_id = applicant_id
        self.reason_input = discord.ui.TextInput(
            label="Rejection Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Feedback for applicant (or leave default)...",
            required=False,
            default="Not accepted at this time",
            max_length=300,
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip() or "Not accepted at this time"
        try:
            app = self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="REJECTED",
                reason=reason,
            )
        except Exception as e:
            return await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        try:
            applicant = interaction.client.get_user(self.applicant_id)
            if applicant:
                dm = discord.Embed(
                    title="Notice Regarding Your Staff Application",
                    description=(
                        f"Thank you for your interest in joining our staff team. After review, your application "
                        f"(`{self.app_id}`) was **not accepted** at this time.\n\n"
                        f"> **Reason:** `{reason}`\n\n"
                        f"You are welcome to reapply after the cooldown period has elapsed."
                    ),
                    color=KyokaTheme.ERROR,
                )
                await applicant.send(embed=dm)
        except Exception:
            pass

        updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
        await interaction.response.send_message(f"🔴 Application **{self.app_id}** marked as **REJECTED**.", ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.edit(embed=updated_emb)
        except Exception:
            pass


class StaffApplicationReqInfoModal(discord.ui.Modal, title="💬 Request Additional Information"):
    def __init__(self, top_mgr: TopManager, app_id: str, applicant_id: int):
        super().__init__()
        self.top_mgr = top_mgr
        self.app_id = app_id
        self.applicant_id = applicant_id
        self.question_input = discord.ui.TextInput(
            label="Question for Applicant",
            style=discord.TextStyle.paragraph,
            placeholder="What additional information do you need from the applicant?",
            required=True,
            max_length=500,
        )
        self.add_item(self.question_input)

    async def on_submit(self, interaction: discord.Interaction):
        q = self.question_input.value.strip()
        try:
            app = self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="MORE_INFO_REQUESTED",
                reason=f"Info requested: {q}",
            )
            self.top_mgr.add_application_note(self.app_id, staff_id=interaction.user.id, note=f"[Info Requested] {q}")
        except Exception as e:
            return await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        try:
            applicant = interaction.client.get_user(self.applicant_id)
            if applicant:
                dm = discord.Embed(
                    title="💬 Staff Application — Information Requested",
                    description=(
                        f"The staff team has reviewed your application (`{self.app_id}`) and requested additional information:\n\n"
                        f"> **Question:** {q}\n\n"
                        f"Please reply or contact staff directly with your response."
                    ),
                    color=KyokaTheme.WARNING,
                )
                await applicant.send(embed=dm)
        except Exception:
            pass

        updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
        await interaction.response.send_message(f"💬 Information request sent to applicant for **{self.app_id}**.", ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.edit(embed=updated_emb)
        except Exception:
            pass


class StaffApplicationNoteModal(discord.ui.Modal, title="📝 Add Internal Staff Note"):
    def __init__(self, top_mgr: TopManager, app_id: str, applicant_id: int):
        super().__init__()
        self.top_mgr = top_mgr
        self.app_id = app_id
        self.applicant_id = applicant_id
        self.note_input = discord.ui.TextInput(
            label="Internal Staff Note",
            style=discord.TextStyle.paragraph,
            placeholder="Confidential staff comments, interview notes, or vouch verification...",
            required=True,
            max_length=500,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        note_text = self.note_input.value.strip()
        try:
            app = self.top_mgr.add_application_note(self.app_id, staff_id=interaction.user.id, note=note_text)
        except Exception as e:
            return await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
        await interaction.response.send_message(f"📝 Note added to application **{self.app_id}**.", ephemeral=True)
        try:
            if interaction.message:
                await interaction.message.edit(embed=updated_emb)
        except Exception:
            pass


class StaffPositionSelect(discord.ui.Select):
    """Position select menu before displaying the modal."""

    def __init__(self, top_mgr: TopManager):
        self.top_mgr = top_mgr
        options = [
            discord.SelectOption(
                label="Community Moderator",
                value="Community Moderator",
                description="Enforce server rules, moderate chat, and handle automod flags.",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Trial Staff / Helper",
                value="Trial Staff / Helper",
                description="Assist new members, answer general questions, and assist trials.",
                emoji="🌱",
            ),
            discord.SelectOption(
                label="Support & Billing Staff",
                value="Support & Billing Staff",
                description="Manage customer service tickets, generate bills, and verify payments.",
                emoji="🧾",
            ),
            discord.SelectOption(
                label="Blox Fruits Service Provider",
                value="Service Provider / Grinder",
                description="Carry raids, complete V4 trials, farm Beli, and grind masteries.",
                emoji="⚔️",
            ),
        ]
        super().__init__(
            placeholder="Select the staff role you are applying for...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="kyoka_staff_pos_select",
        )

    async def callback(self, interaction: discord.Interaction):
        cfg = self.top_mgr.get_app_config(interaction.guild_id or 0)
        if cfg.get("is_open", 1) == 0:
            return await interaction.response.send_message(
                "❌ **Staff applications are currently closed or paused.** Please check back later!",
                ephemeral=True,
            )
        chosen_position = self.values[0]
        modal = StaffApplicationModal(self.top_mgr, chosen_position)
        await interaction.response.send_modal(modal)


class StaffApplicationPanelView(discord.ui.View):
    """Persistent panel view allowing users to select role and apply."""

    def __init__(self, top_mgr: TopManager):
        super().__init__(timeout=None)
        self.top_mgr = top_mgr
        self.add_item(StaffPositionSelect(top_mgr))

    @discord.ui.button(
        label="Quick Apply",
        style=discord.ButtonStyle.primary,
        custom_id="kyoka_staff_apply_btn",
        emoji="📝",
    )
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.top_mgr.get_app_config(interaction.guild_id or 0)
        if cfg.get("is_open", 1) == 0:
            return await interaction.response.send_message(
                "❌ **Staff applications are currently closed or paused.** Please check back later!",
                ephemeral=True,
            )
        modal = StaffApplicationModal(self.top_mgr, "General Staff Candidate")
        await interaction.response.send_modal(modal)


class StaffApplicationReviewView(discord.ui.View):
    """Interactive action buttons for staff review channel."""

    def __init__(self, top_mgr: TopManager, app_id: str, applicant_id: int):
        super().__init__(timeout=None)
        self.top_mgr = top_mgr
        self.app_id = app_id
        self.applicant_id = applicant_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_app_reviewer(interaction.user, interaction.guild, self.top_mgr):
            await interaction.response.send_message("❌ Staff or reviewer permission required.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="app_btn_accept", row=0)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = self.top_mgr.get_application(self.app_id)
        if not app:
            return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
        if app["status"] in ("ACCEPTED", "REJECTED", "CLOSED"):
            return await interaction.response.send_message(f"⚠️ Application {self.app_id} has already been finalized as **{app['status']}**.", ephemeral=True)

        try:
            app = self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="ACCEPTED",
                reason=f"Approved by {interaction.user}",
            )
        except Exception as e:
            return await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        # Assign role if configured
        cfg = self.top_mgr.get_app_config(interaction.guild_id or 0)
        role_id = cfg.get("role_on_accept_id")
        role_msg = ""
        if role_id and interaction.guild:
            target_member = interaction.guild.get_member(self.applicant_id)
            role = interaction.guild.get_role(role_id)
            if target_member and role:
                try:
                    await target_member.add_roles(role, reason=f"Staff application {self.app_id} accepted")
                    role_msg = f"\n• Granted role: **{role.name}**"
                except Exception as ex:
                    role_msg = f"\n• Note: Failed to assign role automatically ({ex})"

        # DM applicant if possible
        try:
            applicant = interaction.client.get_user(self.applicant_id)
            if applicant:
                dm_embed = discord.Embed(
                    title="🎉 Congratulations! Staff Application Accepted",
                    description=(
                        f"Your application (`{self.app_id}`) has been **ACCEPTED** by {interaction.user.mention}!\n"
                        f"Welcome to the staff team.{role_msg}\nPlease contact senior management for your onboarding."
                    ),
                    color=KyokaTheme.SUCCESS,
                )
                await applicant.send(embed=dm_embed)
        except Exception:
            pass

        updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(embed=updated_emb, view=self)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌", custom_id="app_btn_reject", row=0)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = self.top_mgr.get_application(self.app_id)
        if not app:
            return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
        if app["status"] in ("ACCEPTED", "REJECTED", "CLOSED"):
            return await interaction.response.send_message(f"⚠️ Application {self.app_id} has already been finalized as **{app['status']}**.", ephemeral=True)

        modal = StaffApplicationRejectModal(self.top_mgr, self.app_id, self.applicant_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Under Review", style=discord.ButtonStyle.secondary, emoji="🟠", custom_id="app_btn_review", row=0)
    async def under_review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = self.top_mgr.get_application(self.app_id)
        if not app:
            return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
        if app["status"] in ("ACCEPTED", "REJECTED", "CLOSED"):
            return await interaction.response.send_message(f"⚠️ Application {self.app_id} has already been finalized as **{app['status']}**.", ephemeral=True)

        try:
            app = self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="UNDER_REVIEW",
                reason="Review in progress",
            )
            updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
            await interaction.response.edit_message(embed=updated_emb, view=self)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @discord.ui.button(label="Request Info", style=discord.ButtonStyle.primary, emoji="💬", custom_id="app_btn_req_info", row=1)
    async def request_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = StaffApplicationReqInfoModal(self.top_mgr, self.app_id, self.applicant_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="app_btn_add_note", row=1)
    async def add_note_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = StaffApplicationNoteModal(self.top_mgr, self.app_id, self.applicant_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Interview Ticket", style=discord.ButtonStyle.secondary, emoji="🎫", custom_id="app_btn_interview", row=1)
    async def interview_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ Guild context required.", ephemeral=True)

        applicant = guild.get_member(self.applicant_id)
        if not applicant:
            return await interaction.response.send_message("❌ Applicant is no longer in this server.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            applicant: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }

        ch_name = f"interview-{applicant.name.lower()[:12]}-{self.app_id.lower()[-4:]}"
        try:
            interview_ch = await guild.create_text_channel(
                name=ch_name,
                overwrites=overwrites,
                reason=f"Staff interview for application {self.app_id}",
            )
            welcome_emb = discord.Embed(
                title=f"⛩️ STAFF INTERVIEW • {self.app_id}",
                description=(
                    f"Welcome {applicant.mention}! This is your private interview channel with {interaction.user.mention}.\n\n"
                    f"• **Application ID:** `{self.app_id}`\n"
                    f"• Please await questions from management. Good luck!"
                ),
                color=KyokaTheme.PRIMARY,
            )
            await interview_ch.send(content=f"{applicant.mention} {interaction.user.mention}", embed=welcome_emb)
            await interaction.response.send_message(f"🎫 Interview channel created: {interview_ch.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to create interview channel: {e}", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, emoji="📁", custom_id="app_btn_close", row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = self.top_mgr.get_application(self.app_id)
        if not app:
            return await interaction.response.send_message("❌ Application not found.", ephemeral=True)

        try:
            app = self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="CLOSED",
                reason=f"Closed by {interaction.user}",
            )
            updated_emb = build_app_review_embed(app, interaction.client.get_user(self.applicant_id))
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await interaction.response.edit_message(embed=updated_emb, view=self)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


def format_single_price_embed(calc: CalculationResult) -> discord.Embed:
    """Format single-service price result strictly per Kyoka Top AI Manager specs.
    Returns only the requested service, quantity/tier, subtotal/price, conditions, and tax.
    """
    if calc.is_clarification:
        embed = discord.Embed(
            title=calc.clarification_title or "❓ TOP AI MANAGER • CLARIFICATION NEEDED",
            description="\n".join(calc.clarification_options),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_footer(text="Kyoka Top AI Manager")
        return embed

    category_upper = calc.category.upper()
    title = f"🏷️ {category_upper}"

    # Line 1: Requested service and price / tier
    if calc.custom_quote:
        desc_lines = [f"{calc.service_name}: **Custom price — please contact staff.**"]
    else:
        if calc.category == "Normal Raids":
            desc_lines = [f"{calc.quantity} Raids: **{calc.subtotal_display}**"]
        elif calc.category in ("Advance Raids", "Order Raids"):
            desc_lines = [f"{calc.quantity} Raids ({calc.service_name}): **{calc.subtotal_display}**"]
        elif calc.category == "Trials":
            desc_lines = [f"{calc.service_name}: **{calc.subtotal_display}**"]
        elif calc.category == "Beli Farming":
            desc_lines = [f"{calc.service_name}: **{calc.subtotal_display}**"]
        else:
            if calc.quantity > 1 and "per" in calc.unit_display.lower():
                desc_lines = [f"{calc.quantity}x {calc.service_name}: **{calc.subtotal_display}**"]
            else:
                desc_lines = [f"{calc.service_name}: **{calc.subtotal_display}**"]

    # Tax lines (only if requested, i.e. tax_rate > 0)
    if calc.tax_rate > 0:
        tax_str = f"{int(calc.tax_rate)}%" if calc.tax_rate % 1 == 0 else f"{calc.tax_rate}%"
        desc_lines.append(f"Tax ({tax_str}): **+{calc.tax_display}**")
        desc_lines.append(f"Total: **{calc.total_display}**")

    # Condition note (only if relevant and applicable)
    if calc.condition_note:
        desc_lines.append(f"*{calc.condition_note}*")

    embed = discord.Embed(
        title=title,
        description="\n".join(desc_lines),
        color=KyokaTheme.PRIMARY,
    )
    embed.set_footer(text="Kyoka Top AI Manager")
    return embed


def format_quote_embed(calc: Union[CalculationResult, MultiCalculationResult]) -> discord.Embed:
    """Format single-service or multi-service quote embed with itemized breakdown and smart pricing."""
    if isinstance(calc, MultiCalculationResult):
        if calc.comparison_mode:
            embed = discord.Embed(
                title="⚖️ SERVICE PRICE COMPARISON",
                description="Comparing requested services from the authoritative catalogue:\n",
                color=KyokaTheme.PRIMARY,
            )
            for item in calc.items:
                if item.is_clarification:
                    embed.add_field(
                        name=f"❓ {item.service_name}",
                        value="\n".join(item.clarification_options[:4]),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name=f"📦 {item.service_name}",
                        value=f"• **Category:** `{item.category}`\n• **Price:** **{item.subtotal_display}**\n• *{item.condition_note or 'Catalogue price'}*",
                        inline=True,
                    )
            embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            embed.set_footer(text="Kyoka Top AI Manager • Blox Fruits Comparison")
            return embed

        if calc.clarification_needed:
            desc_lines = ["**Your request contains multiple services. Some items require clarification:**\n"]
            for item in calc.items:
                if item.is_clarification:
                    desc_lines.append(f"**❓ {item.service_name}:**")
                    desc_lines.extend(item.clarification_options[:4])
                    desc_lines.append("")
                else:
                    desc_lines.append(f"• **{item.service_name}:** **{item.subtotal_display}** ({item.condition_note or 'Confirmed'})")
            embed = discord.Embed(
                title="❓ TOP AI MANAGER • ITEMIZE QUOTE & CLARIFICATION",
                description="\n".join(desc_lines),
                color=KyokaTheme.PRIMARY,
            )
            embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            embed.set_footer(text="Kyoka Top AI Manager")
            return embed

        # Standard Multi-Item Breakdown
        embed = discord.Embed(
            title="⛩️ TOP AI MANAGER • ITEMIZED QUOTE",
            description="Itemized quote for requested Blox Fruits services:\n",
            color=KyokaTheme.PRIMARY,
        )
        for idx, item in enumerate(calc.items, 1):
            prov_tag = " `[Provisional]`" if getattr(item, "is_provisional", False) else ""
            item_title = item.service_name
            if item.quantity > 1 and not item.service_name.lower().startswith(str(item.quantity)):
                item_title = f"{item.quantity} {item.service_name}"
            embed.add_field(
                name=f"{idx}. {item_title}{prov_tag}",
                value=(
                    f"• **Qty:** `{item.quantity}` | **Unit:** `{item.unit_display}`\n"
                    f"• **Subtotal:** **{item.subtotal_display}**\n"
                    f"• *{item.condition_note or 'Authoritative catalogue rate'}*"
                ),
                inline=False,
            )
        tax_str = f"Tax ({calc.tax_rate:g}%): **+{calc.tax_display}**\n" if calc.tax_rate > 0 else ""
        tot_text = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• **Subtotal:** `{calc.subtotal_display}`\n"
            f"{tax_str}"
            f"• **Final Quoted Value:** **{calc.total_display}**\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        if getattr(calc, "requires_staff_approval", False):
            tot_text += "\n⚠️ *Note: High-value quote or custom work requires staff confirmation.*"
        embed.add_field(name="💰 Pricing Summary", value=tot_text, inline=False)
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka Top AI Manager • Click [Create Bill] below to generate invoice")
        return embed

    # Single-item calculation
    if calc.is_clarification:
        return format_single_price_embed(calc)

    embed = format_single_price_embed(calc)
    if getattr(calc, "is_provisional", False):
        embed.title = f"🏷️ {calc.category.upper()} [Provisional Quote]"
        if getattr(calc, "pricing_explanation", ""):
            embed.add_field(
                name="💡 Pricing Explanation",
                value=f"> {calc.pricing_explanation}",
                inline=False,
            )
    return embed


class EditQuantityModal(discord.ui.Modal, title="✏️ Edit Quote Quantity"):
    quantity_input = discord.ui.TextInput(
        label="New Quantity",
        placeholder="Enter positive integer (e.g. 5, 10)",
        min_length=1,
        max_length=6,
        required=True,
    )

    def __init__(self, quote_view: InteractiveQuoteView):
        super().__init__()
        self.quote_view = quote_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_qty = int(self.quantity_input.value.strip())
            if new_qty < 1 or new_qty > 10000:
                return await interaction.response.send_message("❌ Quantity must be between 1 and 10,000.", ephemeral=True)
            await self.quote_view.update_quantity(interaction, new_qty)
        except ValueError:
            await interaction.response.send_message("❌ Invalid quantity. Please enter a valid number.", ephemeral=True)


class SetCustomerModal(discord.ui.Modal, title="👥 Set Customer"):
    customer_input = discord.ui.TextInput(
        label="Customer Mention or Discord ID",
        placeholder="e.g. @Member or 123456789012345678",
        min_length=2,
        max_length=40,
        required=True,
    )

    def __init__(self, quote_view: InteractiveQuoteView):
        super().__init__()
        self.quote_view = quote_view

    async def on_submit(self, interaction: discord.Interaction):
        val = self.customer_input.value.strip()
        m = re.search(r'\b(\d{17,20})\b', val)
        if m:
            cid = int(m.group(1))
            self.quote_view.customer_id = cid
            cuser = interaction.client.get_user(cid)
            self.quote_view.customer_name = str(cuser) if cuser else f"User {cid}"
            await interaction.response.send_message(f"✅ Customer set to <@{cid}>.", ephemeral=True)
        else:
            self.quote_view.customer_name = val
            await interaction.response.send_message(f"✅ Customer set to `{val}`.", ephemeral=True)
        await self.quote_view.refresh_display(interaction)


class InteractiveQuoteView(discord.ui.View):
    """Interactive Quote View with One-Click Bill Creation, Server-Side Revalidation, and Duplicate Protection."""

    def __init__(
        self,
        top_mgr: TopManager,
        quote: Union[CalculationResult, MultiCalculationResult],
        author_id: int,
        guild_id: int,
        customer_id: Optional[int] = None,
        customer_name: str = "",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.top_mgr = top_mgr
        self.quote = quote
        self.author_id = author_id
        self.guild_id = guild_id
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.is_created = False
        self._lock = asyncio.Lock()
        self.message: Optional[discord.Message] = None

    async def update_quantity(self, interaction: discord.Interaction, new_qty: int):
        """Recalculate quote on server with updated quantity."""
        if isinstance(self.quote, CalculationResult):
            recalculated = self.top_mgr.calculate_service_price(
                self.quote.service_name,
                quantity=new_qty,
                tax_rate=self.quote.tax_rate,
            )
            self.quote = recalculated
        embed = format_quote_embed(self.quote)
        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_display(self, interaction: discord.Interaction):
        """Refresh quote display embed."""
        embed = format_quote_embed(self.quote)
        try:
            if self.message:
                await self.message.edit(embed=embed, view=self)
            elif interaction.message:
                await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce author or staff access to quote controls."""
        if interaction.user.id == self.author_id or interaction.user.id == PRIMARY_OWNER_ID:
            return True
        member = interaction.user if isinstance(interaction.user, discord.Member) else (
            interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        )
        if member:
            perms = getattr(member, "guild_permissions", None)
            if getattr(perms, "administrator", False) is True or getattr(perms, "manage_guild", False) is True:
                return True
        await interaction.response.send_message(
            "❌ Only the quote requester or server staff can interact with this quote card.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Create Bill", emoji="🧾", style=discord.ButtonStyle.success, row=0)
    async def btn_create_bill(self, interaction: discord.Interaction, button: Optional[discord.ui.Button] = None):
        async with self._lock:
            if self.is_created:
                return await interaction.response.send_message("⚠️ A bill has already been created for this quote.", ephemeral=True)

            # Check staff permission
            member = interaction.user if isinstance(interaction.user, discord.Member) else (
                interaction.guild.get_member(interaction.user.id) if interaction.guild else None
            )
            is_staff = False
            if member:
                is_staff = (
                    member.id == PRIMARY_OWNER_ID
                    or (hasattr(member, "guild_permissions") and (
                        member.guild_permissions.administrator
                        or member.guild_permissions.manage_guild
                        or member.guild_permissions.manage_messages
                    ))
                    or any(r.name.lower() in ("staff", "admin", "moderator", "billing") for r in getattr(member, "roles", []))
                )
            elif interaction.user.id == PRIMARY_OWNER_ID:
                is_staff = True

            if not is_staff:
                return await interaction.response.send_message(
                    "❌ **Staff Authorization Required:** Only authorized staff or management can generate official server bills. Please contact a staff member to finalize this quote.",
                    ephemeral=True,
                )

            # Check approval threshold for custom/high-value quotes
            if getattr(self.quote, "requires_staff_approval", False) and member and getattr(member, "id", 0) != PRIMARY_OWNER_ID and not getattr(getattr(member, "guild_permissions", None), "administrator", False):
                policy = self.top_mgr.get_pricing_policy(self.guild_id)
                threshold = policy.get("approval_threshold_amount", 500.0)
                if self.quote.total >= threshold:
                    return await interaction.response.send_message(
                        f"⚠️ **High-Value Approval Required:** Quotes exceeding {threshold}M in service value require Administrator or Owner approval before bill generation.",
                        ephemeral=True,
                    )

            # Revalidate quote on server
            try:
                if isinstance(self.quote, MultiCalculationResult):
                    bill = self.top_mgr.create_multi_bill(
                        guild_id=self.guild_id,
                        creator_id=interaction.user.id,
                        creator_name=str(interaction.user),
                        multi_calc=self.quote,
                        customer_id=self.customer_id,
                        customer_name=self.customer_name,
                    )
                else:
                    bill = self.top_mgr.create_bill(
                        guild_id=self.guild_id,
                        creator_id=interaction.user.id,
                        creator_name=str(interaction.user),
                        service_name=self.quote.service_name,
                        quantity=self.quote.quantity,
                        tax_rate=self.quote.tax_rate,
                        customer_id=self.customer_id,
                        customer_name=self.customer_name,
                        condition_notes=self.quote.condition_note,
                        custom_price=self.quote.unit_price if self.quote.custom_quote else None,
                        custom_price_display=self.quote.unit_display if self.quote.custom_quote else None,
                    )

                self.is_created = True
                if button:
                    button.disabled = True
                    button.label = "Bill Created"
                for item in self.children:
                    if isinstance(item, discord.ui.Button) and item.style != discord.ButtonStyle.link:
                        item.disabled = True

                cust_mention = f"<@{self.customer_id}>" if self.customer_id else (f"`{self.customer_name}`" if self.customer_name else "*Not specified*")
                confirm_embed = discord.Embed(
                    title=f"🧾 OFFICIAL BILL GENERATED • {bill['id']}",
                    description=(
                        f"**Service:** `{bill['service_name']}`\n"
                        f"**Quantity:** `{bill['quantity']}`\n"
                        f"**Subtotal:** `{bill['subtotal_display']}`\n"
                        f"**Tax ({bill['tax_rate']}%):** `{bill['tax_display']}`\n"
                        f"**Final Total:** **{bill['total_display']}**\n\n"
                        f"• **Customer:** {cust_mention}\n"
                        f"• **Staff Creator:** {interaction.user.mention}\n"
                        f"• **Status:** 🟡 **UNPAID**\n"
                        f"• **Audit Trail:** Bill recorded in persistent ledger.\n"
                        f"• **Mark as Paid:** `?top paid {bill['id']} <payment_message_id>`"
                    ),
                    color=KyokaTheme.PRIMARY,
                    timestamp=discord.utils.utcnow(),
                )
                confirm_embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
                confirm_embed.set_footer(text=f"Bill ID: {bill['id']} • Kyoka Top AI Manager")
                await interaction.response.edit_message(embed=confirm_embed, view=self)
            except Exception as ex:
                logger.error(f"Error creating bill from interactive quote: {ex}", exc_info=True)
                await interaction.response.send_message(f"❌ Error creating bill: {ex}", ephemeral=True)

    @discord.ui.button(label="Set Customer", emoji="👥", style=discord.ButtonStyle.secondary, row=0)
    async def btn_set_customer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetCustomerModal(self))

    @discord.ui.button(label="Edit Quantity", emoji="✏️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_edit_quantity(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditQuantityModal(self))

    @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        self.stop()
        await interaction.response.edit_message(view=self)


def format_service_value(amount_m: float) -> str:
    """Format numeric in-game service value: 20.0 -> '20M', 150.0 -> '150M', 1200.0 -> '1.2B'."""
    if amount_m <= 0:
        return "0M"
    if amount_m >= 1_000_000:
        amount_m = amount_m / 1_000_000

    if amount_m >= 1000:
        val_b = amount_m / 1000
        return f"{val_b:g}B"
    return f"{amount_m:g}M"


format_beli_amount = format_service_value


def format_blox_fruits_bill_embed(
    bill: dict[str, Any],
    customer_user: Optional[Any] = None,
    creator_user: Optional[Any] = None,
    guild: Optional[discord.Guild] = None,
) -> discord.Embed:
    """Construct professional Blox Fruits service quote & bill embed without misleading Beli labels."""
    status = bill.get("status", "UNPAID").upper()
    is_paid = status == "PAID"
    color = KyokaTheme.SUCCESS if is_paid else (KyokaTheme.ERROR if status == "CANCELLED" else KyokaTheme.PRIMARY)
    status_label = "PAID" if is_paid else ("CANCELLED" if status == "CANCELLED" else "UNPAID")

    cust_id = bill.get("customer_id")
    customer_str = f"<@{cust_id}>" if cust_id else (bill.get("customer_name") or "Not Specified")

    creator_id = bill.get("creator_id")
    creator_str = f"<@{creator_id}>" if creator_id else (bill.get("creator_name") or "Staff")

    qty = bill.get("quantity", 1)
    subtotal = bill.get("subtotal", 0.0)
    tax_rate = bill.get("tax_rate", 0.0)
    tax_amount = bill.get("tax_amount", 0.0)
    total = bill.get("total", 0.0)
    fruit_details = bill.get("fruit_details", "")
    condition_notes = bill.get("condition_notes", "")

    # Parse itemized lines if available in fruit_details JSON
    item_lines: list[str] = []
    if fruit_details:
        try:
            items_data = json.loads(fruit_details)
            if isinstance(items_data, list):
                for it in items_data:
                    s_name = it.get("service_name") or "Service"
                    s_qty = it.get("quantity", 1)
                    s_price = it.get("subtotal_display") or format_service_value(it.get("subtotal", 0.0))
                    item_lines.append(f"  • {s_name} × {s_qty} — {s_price}")
        except Exception:
            item_lines.append(f"  • {clean_service_display_name(bill.get('service_name', 'Service'))} × {qty} — {fruit_details}")

    if not item_lines:
        clean_name = clean_service_display_name(bill.get("service_name", "Service"))
        sub_disp = bill.get("subtotal_display") or format_service_value(subtotal)
        item_lines.append(f"  • {clean_name} × {qty} — {sub_disp}")

    # Build description lines
    desc_lines = [
        f"• **Customer:** {customer_str}",
        "• **Agreed service value:**",
    ]
    desc_lines.extend(item_lines)
    desc_lines.append(f"• **Subtotal:** {format_service_value(subtotal)}")

    # Tax, only if explicitly requested (> 0)
    if tax_rate > 0:
        desc_lines.append(f"• **Service fee/tax ({tax_rate:g}%):** +{format_service_value(tax_amount)}")

    # Final quoted total
    is_estimated = "estimated" in str(bill.get("total_display", "")).lower() or "[estimated" in str(bill.get("subtotal_display", "")).lower()
    tot_label = "Estimated total" if is_estimated else "Total agreed value"
    desc_lines.append(f"• **{tot_label}:** **{bill.get('total_display') or format_service_value(total)}**")
    desc_lines.append(f"• **Payment status:** `{status_label}`")
    desc_lines.append(f"• **Bill ID:** `{bill['id']}`")
    desc_lines.append(f"• **Created by:** {creator_str}")

    created_ts = int(bill.get("created_at", time.time()))
    desc_lines.append(f"• **Created at:** <t:{created_ts}:F> (<t:{created_ts}:R>)")

    if condition_notes and not fruit_details:
        desc_lines.append(f"• **Notes:** *{condition_notes}*")

    embed = discord.Embed(
        title="KYOKA — SERVICE QUOTE" if not is_paid else "KYOKA — SERVICE QUOTE [PAID]",
        description="\n".join(desc_lines),
        color=color,
        timestamp=discord.utils.utcnow(),
    )

    if is_paid:
        paid_ts = int(bill.get("paid_at", time.time()))
        paid_by = bill.get("paid_by_name") or f"<@{bill.get('paid_by_id')}>"
        msg_id = bill.get("payment_message_id", "Verified")
        embed.add_field(
            name="🟢 Payment Verification",
            value=f"• **Confirmed By:** {paid_by}\n• **Verified At:** <t:{paid_ts}:R>\n• **Payment Message ID:** `{msg_id}`",
            inline=False,
        )
    elif status == "UNPAID":
        embed.set_footer(text=f"Mark as paid: ?top billpaid {bill.get('posted_message_id') or bill['id']} • Kyoka 3.0")
    else:
        embed.set_footer(text=f"Status: {status} • Kyoka 3.0")

    embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
    return embed


def check_is_staff(user: Any, guild: Optional[discord.Guild], top_mgr: TopManager, bot: Any = None) -> bool:
    """Helper to check if user has staff privileges for billing & application interactions."""
    if getattr(user, "id", 0) == 1505515188991033409:
        return True
    if guild and hasattr(user, "guild_permissions"):
        if user.guild_permissions.administrator or user.guild_permissions.manage_guild or user.guild_permissions.manage_messages:
            return True
        cfg = top_mgr.get_app_config(guild.id)
        rev_role = cfg.get("reviewer_role_id")
        if rev_role and hasattr(user, "roles") and any(r.id == rev_role for r in user.roles):
            return True
    if bot:
        perm_mgr = getattr(bot, "perm_mgr", None)
        if perm_mgr and hasattr(perm_mgr, "is_developer_sync"):
            try:
                if perm_mgr.is_developer_sync(user.id) is True:
                    return True
            except Exception:
                pass
    return False


class BillLauncherView(discord.ui.View):
    """Persistent view with [ 🧾 Create Bill ] button for staff."""

    def __init__(self, top_mgr: TopManager):
        super().__init__(timeout=None)
        self.top_mgr = top_mgr

    @discord.ui.button(
        label="Create Bill",
        style=discord.ButtonStyle.primary,
        emoji="🧾",
        custom_id="kyoka:bill:open_creator",
    )
    async def create_bill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_is_staff(interaction.user, interaction.guild, self.top_mgr, interaction.client):
            return await interaction.response.send_message(
                "❌ **Staff Access Only:** Only authorized Blox Fruits service staff or administrators can issue bills.",
                ephemeral=True,
            )
        cfg = self.top_mgr.get_billing_config(interaction.guild.id) if interaction.guild else {}
        def_tax = cfg.get("tax_rate", 5.0)
        modal = CreateBillModal(self.top_mgr, default_tax=def_tax)
        await interaction.response.send_modal(modal)


class CreateBillModal(discord.ui.Modal, title="🧾 Create Blox Fruits Service Bill"):
    """Guided modal for staff to create Blox Fruits service invoices."""

    def __init__(self, top_mgr: TopManager, default_tax: float = 5.0):
        super().__init__()
        self.top_mgr = top_mgr
        self.default_tax = default_tax

        self.customer_input = discord.ui.TextInput(
            label="Customer (@mention, User ID, or Name)",
            placeholder="e.g. @Customer or 123456789012345678",
            required=True,
            max_length=100,
        )
        self.service_input = discord.ui.TextInput(
            label="Service / Item",
            placeholder="e.g. 2 Trials, Dough Raid, Race V4, Leviathan",
            required=True,
            max_length=150,
        )
        self.quantity_input = discord.ui.TextInput(
            label="Quantity",
            placeholder="1",
            default="1",
            required=True,
            max_length=5,
        )
        self.price_input = discord.ui.TextInput(
            label="Price / Unit (Beli or Fruits, blank=catalogue)",
            placeholder="e.g. 30M, 30000000 Beli, or Kitsune Fruit",
            required=False,
            max_length=100,
        )
        self.tax_input = discord.ui.TextInput(
            label="Tax / Service Fee % (0 for none)",
            placeholder=f"{self.default_tax}",
            default=f"{self.default_tax}",
            required=False,
            max_length=10,
        )

        self.add_item(self.customer_input)
        self.add_item(self.service_input)
        self.add_item(self.quantity_input)
        self.add_item(self.price_input)
        self.add_item(self.tax_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = max(1, int(self.quantity_input.value.strip()))
        except ValueError:
            return await interaction.response.send_message("❌ Quantity must be a positive integer.", ephemeral=True)

        try:
            tax_rate = float(self.tax_input.value.strip() or "0")
            if tax_rate < 0 or tax_rate > 100:
                return await interaction.response.send_message("❌ Tax rate must be between 0% and 100%.", ephemeral=True)
        except ValueError:
            tax_rate = 0.0

        raw_cust = self.customer_input.value.strip()
        cust_id = None
        cust_name = raw_cust
        match_id = re.search(r"\d{17,20}", raw_cust)
        if match_id:
            cust_id = int(match_id.group())
            if interaction.guild:
                member = interaction.guild.get_member(cust_id)
                if member:
                    cust_name = str(member)

        service_str = self.service_input.value.strip()
        price_val_str = self.price_input.value.strip()

        is_fruit = False
        fruit_keywords = ["fruit", "kitsune", "dragon", "leopard", "dough", "mammoth", "t-rex", "portal", "spirit", "venom", "shadow", "buddha", "blizzard", "sound"]
        if any(k in price_val_str.lower() for k in fruit_keywords) or any(k in service_str.lower() and "fruit" in price_val_str.lower() for k in fruit_keywords):
            is_fruit = True

        custom_price = None
        custom_display = None
        payment_type = "Fruits" if is_fruit else "Beli"
        fruit_details = ""

        if is_fruit:
            fruit_details = price_val_str or "In-Game Fruits"
            custom_price = 0.0
            custom_display = fruit_details
            subtotal = 0.0
            tax_amt = 0.0
            total = 0.0
        elif price_val_str:
            cleaned = re.sub(r"[^\d.]", "", price_val_str.lower().replace("m", "000000").replace("k", "000"))
            try:
                num = float(cleaned)
                if num >= 100000:
                    unit_m = num / 1_000_000.0
                else:
                    unit_m = num
                custom_price = unit_m
                custom_display = format_beli_amount(unit_m)
                subtotal = unit_m * qty
                tax_amt, total = self.top_mgr.calculate_tax(subtotal, tax_rate)
            except Exception:
                custom_price = 0.0
                custom_display = price_val_str
                subtotal = 0.0
                tax_amt = 0.0
                total = 0.0
        else:
            try:
                calc = self.top_mgr.calculate_service_price(service_str, quantity=qty, tax_rate=tax_rate)
                service_str = calc.service_name
                subtotal = calc.subtotal
                tax_amt = calc.tax_amount
                total = calc.total
                custom_price = calc.unit_price
                custom_display = format_beli_amount(calc.unit_price)
            except Exception:
                subtotal = 0.0
                tax_amt = 0.0
                total = 0.0

        bill_data = {
            "guild_id": interaction.guild_id or 0,
            "creator_id": interaction.user.id,
            "creator_name": str(interaction.user),
            "customer_id": cust_id,
            "customer_name": cust_name,
            "service_name": service_str,
            "quantity": qty,
            "tax_rate": tax_rate,
            "payment_type": payment_type,
            "fruit_details": fruit_details,
            "custom_price": custom_price,
            "custom_price_display": custom_display,
            "unit_price": custom_price or 0.0,
            "subtotal": subtotal,
            "tax_amount": tax_amt,
            "total": total,
            "status": "UNPAID",
            "created_at": time.time(),
            "id": "PREVIEW",
        }

        preview_embed = format_blox_fruits_bill_embed(bill_data, guild=interaction.guild)
        preview_embed.title = "🔍 PREVIEW — BLOX FRUITS SERVICE BILL"
        preview_embed.description = "Review the bill details below before issuing to the customer:\n\n" + preview_embed.description

        view = BillConfirmationView(self.top_mgr, bill_data)
        await interaction.response.send_message(embed=preview_embed, view=view, ephemeral=True)


class BillConfirmationView(discord.ui.View):
    """Confirmation view to safely issue and post the bill without duplicates."""

    def __init__(self, top_mgr: TopManager, bill_data: dict[str, Any]):
        super().__init__(timeout=180)
        self.top_mgr = top_mgr
        self.bill_data = bill_data
        self.is_confirmed = False

    @discord.ui.button(label="Confirm & Issue Bill", style=discord.ButtonStyle.success, emoji="✅", custom_id="kyoka:bill:confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_confirmed:
            return await interaction.response.send_message("⚠️ This bill has already been created.", ephemeral=True)
        self.is_confirmed = True
        button.disabled = True

        guild = interaction.guild
        cfg = self.top_mgr.get_billing_config(guild.id) if guild else {}
        target_ch_id = cfg.get("billing_channel_id")
        target_ch = guild.get_channel(target_ch_id) if (guild and target_ch_id) else interaction.channel

        if not target_ch or not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            target_ch = interaction.channel

        bill = self.top_mgr.create_bill(
            guild_id=self.bill_data["guild_id"],
            creator_id=self.bill_data["creator_id"],
            creator_name=self.bill_data["creator_name"],
            service_name=self.bill_data["service_name"],
            quantity=self.bill_data["quantity"],
            tax_rate=self.bill_data["tax_rate"],
            customer_id=self.bill_data["customer_id"],
            customer_name=self.bill_data["customer_name"],
            payment_type=self.bill_data["payment_type"],
            fruit_details=self.bill_data["fruit_details"],
            custom_price=self.bill_data["custom_price"],
            custom_price_display=self.bill_data["custom_price_display"],
            posted_channel_id=target_ch.id if target_ch else 0,
        )

        bill_embed = format_blox_fruits_bill_embed(bill, guild=guild)

        try:
            posted_msg = await target_ch.send(
                content=f"🔔 <@{bill['customer_id']}> Your official Blox Fruits service bill has been issued by <@{bill['creator_id']}>:" if bill.get("customer_id") else "",
                embed=bill_embed,
            )
            self.top_mgr.set_bill_posted_message(bill["id"], target_ch.id, posted_msg.id)
            bill["posted_message_id"] = str(posted_msg.id)
            bill["posted_channel_id"] = target_ch.id
        except Exception as ex:
            logger.warning(f"Failed to post bill to channel: {ex}")
            posted_msg = None

        amt_display = format_beli_amount(bill['total']) if bill['payment_type'] == 'Beli' else bill.get('fruit_details')
        success_emb = discord.Embed(
            title="✅ Bill Issued Successfully",
            description=(
                f"• **Bill ID:** `{bill['id']}`\n"
                f"• **Service:** `{bill['service_name']}`\n"
                f"• **Total Amount:** **{amt_display}**\n"
                f"• **Channel:** {target_ch.mention if hasattr(target_ch, 'mention') else 'Current Channel'}\n"
                f"• **Posted Message ID:** `{posted_msg.id if posted_msg else 'N/A'}`\n\n"
                f"To mark as paid once payment is received:\n"
                f"> `?top billpaid {posted_msg.id if posted_msg else bill['id']}`"
            ),
            color=KyokaTheme.SUCCESS,
        )
        await interaction.response.edit_message(embed=success_emb, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌", custom_id="kyoka:bill:cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🚫 Bill creation cancelled.", embed=None, view=None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAIN TOP AI MANAGER COG
# ─────────────────────────────────────────────────────────────────────────────

class TopAIManager(commands.Cog, name="TopAIManager"):
    """Official Blox Fruits Pricing Engine, Service Billing & Staff Applications."""

    category = "Bills"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.top_mgr = TopManager()
        # Register persistent application and bill creator button views
        self.bot.add_view(StaffApplicationPanelView(self.top_mgr))
        self.bot.add_view(BillLauncherView(self.top_mgr))

    def is_bot_staff(self, ctx: commands.Context) -> bool:
        """Verify author has authoritative staff or administrator privileges."""
        if ctx.author.id == 1505515188991033409:
            return True
        if ctx.guild and getattr(ctx.author, "guild_permissions", None):
            if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
                return True
            cfg = self.top_mgr.get_app_config(ctx.guild.id)
            rev_role = cfg.get("reviewer_role_id")
            if rev_role and hasattr(ctx.author, "roles") and any(r.id == rev_role for r in ctx.author.roles):
                return True
        perm_mgr = getattr(self.bot, "perm_mgr", None)
        if perm_mgr and hasattr(perm_mgr, "is_developer_sync"):
            try:
                if perm_mgr.is_developer_sync(ctx.author.id) is True:
                    return True
            except Exception:
                pass
        return False

    # ── ROOT COMMAND GROUP: ?top ──────────────────────────────────────────────
    @commands.group(
        name="top",
        aliases=["topai", "topmanager", "toptiers"],
        invoke_without_command=True,
    )
    async def top_group(self, ctx: CustomContext, *, query: Optional[str] = None):
        """Top AI Manager - Natural Language Price Lookup, Bill Calculation, and Staff Console.
        
        Examples:
        • +top what's the price of 1 trial?
        • +top price of 2 trials
        • +top what is the cost of 5 normal raids?
        • +top price of Draco V2
        • +top how much is Dough King?
        • +top what's the price of 2 trials with 5% tax?
        • +top calculate 3 trials with 10% tax
        • +top make a bill for 2 trials with 5% tax unpaid
        """
        p = ctx.prefix or Config.DEFAULT_PREFIX

        if not query or not query.strip():
            embed = discord.Embed(
                title="⛩️ TOP AI MANAGER • BLOX FRUITS CONSOLE",
                description=(
                    "> **Intelligent pricing engine, service billing & staff management.**\n\n"
                    f"**💬 Natural Language Examples:**\n"
                    f"• `{p}top price of 2 trials`\n"
                    f"• `{p}top what is the cost of 5 normal raids?`\n"
                    f"• `{p}top how much is Dough King?`\n"
                    f"• `{p}top price of 2 trials with 5% tax`\n"
                    f"• `{p}top calculate 3 trials with 10% tax`\n"
                    f"• `{p}top make a bill for 2 trials with 5% tax unpaid`\n\n"
                    f"**🧾 Service Billing Commands:**\n"
                    f"• `{p}top bill <service> [qty] [tax] [@user]` — Create invoice\n"
                    f"• `{p}top bill view <bill_id>` — View itemized bill details\n"
                    f"• `{p}top bill list [status]` — List recent bills\n"
                    f"• `{p}top paid <bill_id> <message_id>` — Mark bill as paid\n"
                    f"• `{p}top paid <message_id>` — Auto-match payment proof\n\n"
                    f"**📊 Accounting Reports:**\n"
                    f"• `{p}top today bills` / `{p}top revenue today`\n"
                    f"• `{p}top weekly bills` / `{p}top revenue weekly`\n"
                    f"• `{p}top monthly bills` / `{p}top revenue monthly`\n"
                    f"• `{p}top unpaid` — Outstanding unpaid invoices\n\n"
                    f"**📝 Staff Applications:**\n"
                    f"• `{p}top app setup <#channel>` — Configure review channel\n"
                    f"• `{p}top app panel` — Post persistent recruitment panel"
                ),
                color=KyokaTheme.PRIMARY,
            )
            embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            embed.set_footer(text=f"Kyoka 3.0 • Authoritative Official Price List • Prefix: {p}")
            return await ctx.reply(embed=embed, mention_author=False)

        # Natural Language Query Handler
        try:
            parsed = self.top_mgr.parse_top_query(query)
        except KeyError as ke:
            # Check if Gemini AI can interpret free-form pricing questions or strategy inquiries
            ai_mgr = getattr(self.bot, "ai_mgr", None)
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if ai_mgr and api_key:
                try:
                    system_prompt = (
                        "You are Kyoka 3.0, the Aizen Edition Blox Fruits service assistant. "
                        "You advise clients and staff on Blox Fruits services, pricing rules, raids, trials, and builds. "
                        "All prices are in Millions (M) or Billions (B) of in-game Beli/currency or Fruits. "
                        "Never mention USD, dollars, or real-world money. "
                        "Keep answers concise, direct, helpful, and anime-styled."
                    )
                    ai_reply = await ai_mgr.get_response(
                        guild_id=ctx.guild.id if ctx.guild else 0,
                        channel_id=ctx.channel.id,
                        user_id=ctx.author.id,
                        user_message=f"{system_prompt}\n\nUser Question: {query}",
                        persona="aizen",
                    )
                    ai_emb = discord.Embed(
                        title="⛩️ KYOKA AI ASSISTANT",
                        description=ai_reply[:2000],
                        color=KyokaTheme.PRIMARY,
                    )
                    ai_emb.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
                    ai_emb.set_footer(text=f"Kyoka 3.0 AI • Query: {query[:50]}")
                    return await ctx.reply(embed=ai_emb, mention_author=False)
                except Exception as ai_ex:
                    logger.debug(f"AI fallback failed: {ai_ex}")

            err_emb = discord.Embed(
                title="⚠️ Service Not Found",
                description=f"{ke}\n\n*Type `{p}top prices` to view the complete price catalogue or contact staff.*",
                color=KyokaTheme.WARNING,
            )
            return await ctx.reply(embed=err_emb, mention_author=False)
        except Exception as e:
            return await ctx.reply(f"❌ Could not interpret query: {e}", mention_author=False)

        calc = parsed["calculation"]

        # If user intended to create a bill
        if parsed["intent"] == "make_bill":
            if not self.is_bot_staff(ctx):
                unauth_emb = format_quote_embed(calc)
                view = InteractiveQuoteView(
                    self.top_mgr, calc, ctx.author.id, ctx.guild.id if ctx.guild else 0
                )
                msg = await ctx.reply(
                    content="ℹ️ *Official bills must be generated by authorized staff. Here is your itemized quote:*",
                    embed=unauth_emb,
                    view=view,
                    mention_author=False,
                )
                view.message = msg
                return

            # Staff creating bill via natural language
            if isinstance(calc, MultiCalculationResult):
                bill = self.top_mgr.create_multi_bill(
                    guild_id=ctx.guild.id if ctx.guild else 0,
                    creator_id=ctx.author.id,
                    creator_name=str(ctx.author),
                    multi_calc=calc,
                )
            else:
                bill = self.top_mgr.create_bill(
                    guild_id=ctx.guild.id if ctx.guild else 0,
                    creator_id=ctx.author.id,
                    creator_name=str(ctx.author),
                    service_name=calc.service_name,
                    quantity=calc.quantity,
                    tax_rate=calc.tax_rate,
                    condition_notes=calc.condition_note,
                )

            bill_emb = format_blox_fruits_bill_embed(bill, customer_user=None, creator_user=ctx.author, guild=ctx.guild)
            msg = await ctx.reply(embed=bill_emb, mention_author=False)
            self.top_mgr.set_bill_posted_message(bill["id"], ctx.channel.id, msg.id)
            return

        # Standard Price Inquiry Response with Interactive Quote View
        embed = format_quote_embed(calc)
        if not getattr(calc, "is_clarification", False) and not getattr(calc, "clarification_needed", False):
            view = InteractiveQuoteView(
                self.top_mgr, calc, ctx.author.id, ctx.guild.id if ctx.guild else 0
            )
            msg = await ctx.reply(embed=embed, view=view, mention_author=False)
            view.message = msg
        else:
            await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top bill ──────────────────────────────────────────────────
    @top_group.group(name="bill", invoke_without_command=True)
    async def bill_cmd(
        self,
        ctx: CustomContext,
        *,
        raw_input: Optional[str] = None,
    ):
        """Create a new service bill or view billing console.
        
        Usage: +top bill <service> [quantity] [tax%] [@customer]
        Examples:
        • +top bill 10 normal raids and 1 max race @Customer
        • +top bill "2 trials" 1 5% @Customer
        • +top bill 2 trials @Customer
        • +top bill dough king
        """
        p = ctx.prefix or Config.DEFAULT_PREFIX
        if not raw_input or not raw_input.strip():
            embed = discord.Embed(
                title="🧾 BLOX FRUITS SERVICE BILLING CONSOLE",
                description=(
                    "> **Create and manage itemized in-game service bills.**\n\n"
                    f"**📌 Command Syntax:**\n"
                    f"• `{p}top bill <service> [quantity] [tax%] [@customer]`\n"
                    f"• `{p}top bill 10 normal raids and 1 max race @Customer`\n"
                    f"• `{p}top bill 2 trials 5% @Customer`\n\n"
                    f"**🔍 Bill Management:**\n"
                    f"• `{p}top bill view <bill_id>` — View itemized bill details\n"
                    f"• `{p}top bill list [status]` — List recent server bills\n"
                    f"• `{p}top paid <bill_id> <message_id>` — Confirm payment proof"
                ),
                color=KyokaTheme.PRIMARY,
            )
            embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            embed.set_footer(text="Kyoka Top AI Manager")
            return await ctx.reply(embed=embed, mention_author=False)

        customer = None
        cleaned_input = raw_input.strip()

        # Parse user mention, user ID, or plain @username safely
        mention_match = re.search(r'<@!?(\d{17,20})>', cleaned_input)
        if mention_match:
            uid = int(mention_match.group(1))
            if ctx.guild:
                customer = ctx.guild.get_member(uid)
            if not customer:
                try:
                    customer = await self.bot.fetch_user(uid)
                except Exception:
                    pass
            cleaned_input = cleaned_input.replace(mention_match.group(0), "").strip()
        else:
            id_match = re.search(r'\b(\d{17,20})\b', cleaned_input)
            if id_match:
                uid = int(id_match.group(1))
                if ctx.guild:
                    customer = ctx.guild.get_member(uid)
                if not customer:
                    try:
                        customer = await self.bot.fetch_user(uid)
                    except Exception:
                        pass
                cleaned_input = cleaned_input.replace(id_match.group(0), "").strip()
            else:
                plain_mention = re.search(r'@([a-zA-Z0-9_\-\.]+)', cleaned_input)
                if plain_mention:
                    c_name = plain_mention.group(1)
                    if ctx.guild:
                        customer = discord.utils.find(
                            lambda m: m.name.lower() == c_name.lower() or m.display_name.lower() == c_name.lower(),
                            ctx.guild.members,
                        )
                    if not customer:
                        class _PlaceholderCustomer:
                            def __init__(self, name: str):
                                self.id = None
                                self.name = name
                                self.display_name = name
                                self.mention = f"@{name}"
                            def __str__(self):
                                return f"@{self.name}"
                        customer = _PlaceholderCustomer(c_name)
                    cleaned_input = cleaned_input.replace(plain_mention.group(0), "").strip()

        # Parse tax percentage if present
        tax = 0.0
        tax_m = re.search(r'(\d+(?:\.\d+)?)\s*%', cleaned_input)
        if tax_m:
            try:
                tax = float(tax_m.group(1))
                cleaned_input = cleaned_input.replace(tax_m.group(0), "").strip()
            except ValueError:
                pass

        # Permission check
        if not self.is_bot_staff(ctx):
            try:
                parsed = self.top_mgr.parse_top_query(cleaned_input, tax_override=tax)
                calc = parsed["calculation"]
                embed = format_quote_embed(calc)
                view = InteractiveQuoteView(
                    self.top_mgr, calc, ctx.author.id, ctx.guild.id if ctx.guild else 0,
                    customer_id=customer.id if getattr(customer, "id", None) else None,
                    customer_name=str(customer) if customer else "",
                )
                msg = await ctx.reply(
                    content="ℹ️ *Official bills must be generated by authorized staff. Here is your itemized quote:*",
                    embed=embed,
                    view=view,
                    mention_author=False,
                )
                view.message = msg
                return
            except Exception as e:
                return await ctx.reply(f"❌ Staff permissions required to create official bills. (Could not calculate quote: {e})", mention_author=False)

        # Staff workflow: First try parsing as a natural multi-service or catalogue query
        try:
            parsed = self.top_mgr.parse_top_query(cleaned_input, tax_override=tax)
            calc = parsed["calculation"]
            if isinstance(calc, MultiCalculationResult):
                bill = self.top_mgr.create_multi_bill(
                    guild_id=ctx.guild.id if ctx.guild else 0,
                    creator_id=ctx.author.id,
                    creator_name=str(ctx.author),
                    multi_calc=calc,
                    customer_id=customer.id if getattr(customer, "id", None) else None,
                    customer_name=str(customer) if customer else "",
                )
            else:
                bill = self.top_mgr.create_bill(
                    guild_id=ctx.guild.id if ctx.guild else 0,
                    creator_id=ctx.author.id,
                    creator_name=str(ctx.author),
                    service_name=calc.service_name,
                    quantity=calc.quantity,
                    tax_rate=tax or calc.tax_rate,
                    customer_id=customer.id if getattr(customer, "id", None) else None,
                    customer_name=str(customer) if customer else "",
                    condition_notes=calc.condition_note,
                )
            embed = format_blox_fruits_bill_embed(bill, customer_user=customer, creator_user=ctx.author, guild=ctx.guild)
            msg = await ctx.reply(embed=embed, mention_author=False)
            self.top_mgr.set_bill_posted_message(bill["id"], ctx.channel.id, msg.id)
            return
        except Exception:
            pass

        # Fallback structured parsing: service_name and trailing quantity
        parts = cleaned_input.split()
        if not parts:
            return await ctx.reply(f"❌ Invalid bill parameters. Usage: `{p}top bill <service> [quantity] [tax%] [@customer]`", mention_author=False)

        qty = 1
        if len(parts) > 1 and parts[-1].isdigit():
            qty = int(parts.pop())
            if qty < 1 or qty > 10000:
                return await ctx.reply("❌ Quantity must be between 1 and 10,000.", mention_author=False)

        service_name = " ".join(parts).strip().strip('"\'')
        try:
            bill = self.top_mgr.create_bill(
                guild_id=ctx.guild.id if ctx.guild else 0,
                creator_id=ctx.author.id,
                creator_name=str(ctx.author),
                service_name=service_name,
                quantity=qty,
                tax_rate=tax,
                customer_id=customer.id if getattr(customer, "id", None) else None,
                customer_name=str(customer) if customer else "",
            )
            embed = format_blox_fruits_bill_embed(bill, customer_user=customer, creator_user=ctx.author, guild=ctx.guild)
            msg = await ctx.reply(embed=embed, mention_author=False)
            self.top_mgr.set_bill_posted_message(bill["id"], ctx.channel.id, msg.id)
        except Exception as e:
            return await ctx.reply(f"⚠️ **Error creating bill:** {e}", mention_author=False)


    @commands.hybrid_command(
        name="aihelp",
        aliases=["tophelp", "helpai"],
        description="Comprehensive guide to Blox Fruits pricing AI assistant, personalities, and voice TTS.",
    )
    async def aihelp_cmd(self, ctx: CustomContext):
        """Display dedicated AI Blox Fruits pricing and assistant guide."""
        p = ctx.prefix or Config.DEFAULT_PREFIX
        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • AI TOP ASSISTANT & PRICING MANUAL",
            description=(
                "> **Intelligent Natural Language Pricing Assistant & In-Game Service Billing**\n"
                "> Kyoka understands free-form queries, itemizes package deals, calculates decimal-safe taxes, "
                "and generates interactive official bills using the authoritative Throne of Pirate catalogue.\n\n"
                f"**💬 Natural Language Examples:**\n"
                f"• `{p}top price of 10 normal raids and 1 max race` — Itemized multi-service quote\n"
                f"• `{p}top how much for 5 normal raids?` — Instant tier calculation\n"
                f"• `{p}top price of max race with 3 extra trainings` — Package rules & training math\n"
                f"• `{p}top how much is Dough King?` — Boss bounty lookup\n"
                f"• `{p}top compare the price of 5 raids with 10 raids` — Interactive comparison\n"
                f"• `{p}top price of 2 trials with 5% tax` — Decimal-safe tax calculation\n"
                f"• `{p}top make a bill for 10 normal raids and 1 Max Race package` — Direct invoice quote\n\n"
                f"**🧾 One-Click Bill Generation:**\n"
                f"• Every quote provides an interactive **`[ 🧾 Create Bill ]`** button.\n"
                f"• Staff can set customer mentions, adjust quantities, and generate permanent audit bills.\n"
                f"• Duplicate clicks are automatically locked and prevented.\n\n"
                f"**⚙️ Currency & In-Game Values:**\n"
                f"• All prices are quoted in **Millions (M)** or **Billions (B)** of in-game Beli or Fruits.\n"
                f"• Never converts to or uses real-world USD currency.\n\n"
                f"• **Official Support:** [Join Support Server]({Config.SUPPORT_URL or 'https://discord.gg/msH67hUx6G'})"
            ),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text=f"Kyoka 3.0 • AI Top Assistant • Requested by {ctx.author.display_name}")
        view = discord.ui.View(timeout=None)
        support_url = Config.SUPPORT_URL or "https://discord.gg/msH67hUx6G"
        view.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url=support_url, emoji="💜"))
        if Config.INVITE_URL:
            view.add_item(discord.ui.Button(label="Invite KYOKA", style=discord.ButtonStyle.link, url=Config.INVITE_URL, emoji="✦"))
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @bill_cmd.command(name="view")
    async def bill_view_cmd(self, ctx: CustomContext, bill_id: str):
        """View full details and audit history of a bill.
        
        Usage: +top bill view <bill_id>
        """
        bill = self.top_mgr.get_bill(bill_id)
        if not bill:
            return await ctx.reply(f"❌ Bill **`{bill_id}`** not found.", mention_author=False)

        status_emoji = {"UNPAID": "🟡", "PAID": "🟢", "CANCELLED": "🔴", "REFUNDED": "🟣"}.get(bill["status"], "⚪")
        cust_id = bill.get("customer_id")
        customer_text = f"<@{cust_id}>" if cust_id else (bill.get("customer_name") or "None")

        embed = discord.Embed(
            title=f"🧾 BILL DETAILS • {bill['id']}",
            description=(
                f"**Status:** {status_emoji} **{bill['status']}**\n"
                f"**Service:** `{bill['service_name']}` (`{bill['category']}`)\n"
                f"**Quantity:** `{bill['quantity']}`\n"
                f"**Unit Price:** `{bill['unit_price_display']}`\n"
                f"**Subtotal:** `{bill['subtotal_display']}`\n"
                f"**Tax:** `{bill['tax_rate']}%` (`+{bill['tax_display']}`)\n"
                f"**Final Total:** **{bill['total_display']}**\n\n"
                f"• **Customer:** {customer_text}\n"
                f"• **Created:** <t:{int(bill['created_at'])}:F> by `{bill['creator_name']}`"
            ),
            color=KyokaTheme.SUCCESS if bill["status"] == "PAID" else (KyokaTheme.ERROR if bill["status"] == "CANCELLED" else KyokaTheme.PRIMARY),
            timestamp=discord.utils.utcnow(),
        )

        if bill["status"] == "PAID":
            embed.add_field(
                name="🟢 Payment Confirmation",
                value=(
                    f"• **Confirmed By:** `{bill['paid_by_name']}`\n"
                    f"• **Paid At:** <t:{int(bill['paid_at'])}:R>\n"
                    f"• **Payment Message ID:** `{bill['payment_message_id']}`"
                ),
                inline=False,
            )

        if bill["status"] == "CANCELLED":
            embed.add_field(name="🔴 Cancellation Reason", value=f"> {bill['cancel_reason'] or 'No reason specified'}", inline=False)

        if bill["status"] == "REFUNDED":
            embed.add_field(name="🟣 Refund Reason", value=f"> {bill['refund_reason'] or 'No reason specified'}", inline=False)

        if bill.get("notes"):
            embed.add_field(name="📝 Staff Notes", value=f"> {bill['notes'][:900]}", inline=False)

        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text=f"Kyoka Top Billing Ledger • Bill ID: {bill['id']}")
        await ctx.reply(embed=embed, mention_author=False)

    @bill_cmd.command(name="list")
    async def bill_list_cmd(self, ctx: CustomContext, status: Optional[str] = None):
        """List recent bills in this server.
        
        Usage: +top bill list [UNPAID/PAID/CANCELLED/REFUNDED]
        """
        bills = self.top_mgr.list_bills(guild_id=ctx.guild.id if ctx.guild else None, status=status, limit=15)
        if not bills:
            return await ctx.reply(f"ℹ️ No bills found{f' with status `{status.upper()}`' if status else ''}.", mention_author=False)

        lines = []
        for b in bills:
            emoji = {"UNPAID": "🟡", "PAID": "🟢", "CANCELLED": "🔴", "REFUNDED": "🟣"}.get(b["status"], "⚪")
            lines.append(f"`{b['id']}` • {emoji} **{b['total_display']}** — `{b['service_name']}` ({b['status']})")

        embed = discord.Embed(
            title=f"🧾 RECENT BILLS {f'• {status.upper()}' if status else ''}",
            description="\n".join(lines),
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Showing {len(bills)} bill(s) • Type +top bill view <ID> for details")
        await ctx.reply(embed=embed, mention_author=False)

    @bill_cmd.command(name="cancel")
    async def bill_cancel_cmd(self, ctx: CustomContext, bill_id: str, *, reason: str = "Cancelled by staff"):
        """Cancel an UNPAID bill.
        
        Usage: +top bill cancel <bill_id> <reason>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to cancel bills.", mention_author=False)

        try:
            self.top_mgr.cancel_bill(bill_id, staff_id=ctx.author.id, reason=reason)
            await ctx.reply(f"🔴 Bill **`{bill_id.upper()}`** has been **CANCELLED**.\n> Reason: `{reason}`", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @bill_cmd.command(name="refund")
    async def bill_refund_cmd(self, ctx: CustomContext, bill_id: str, *, reason: str = "Refunded to customer"):
        """Refund a PAID bill.
        
        Usage: +top bill refund <bill_id> <reason>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to refund bills.", mention_author=False)

        try:
            self.top_mgr.refund_bill(bill_id, staff_id=ctx.author.id, reason=reason)
            await ctx.reply(f"🟣 Bill **`{bill_id.upper()}`** has been marked as **REFUNDED**.\n> Reason: `{reason}`", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @bill_cmd.command(name="note")
    async def bill_note_cmd(self, ctx: CustomContext, bill_id: str, *, note: str):
        """Add a staff note to a bill.
        
        Usage: +top bill note <bill_id> <note>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to add notes.", mention_author=False)

        try:
            self.top_mgr.add_bill_note(bill_id, staff_id=ctx.author.id, note=note)
            await ctx.reply(f"📝 Note added to bill **`{bill_id.upper()}`**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @bill_cmd.command(name="paid")
    async def bill_sub_paid_cmd(self, ctx: CustomContext, message_id: str):
        """Mark bill as paid using Discord message ID: ?top bill paid <message_id>"""
        await self.billpaid_cmd(ctx, message_id)

    @bill_cmd.command(name="today")
    async def bill_today_subcmd(self, ctx: CustomContext):
        """View today's Blox Fruits revenue: ?top bill today"""
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_blox_fruits_revenue_embed(ctx, rep, "TODAY'S BLOX FRUITS REVENUE")

    @bill_cmd.command(name="month")
    async def bill_month_subcmd(self, ctx: CustomContext):
        """View monthly Blox Fruits revenue: ?top bill month"""
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_blox_fruits_revenue_embed(ctx, rep, "MONTHLY BLOX FRUITS REVENUE")

    # ── SUBCOMMAND: ?top billpaid <message_id> ────────────────────────────────
    @top_group.command(name="billpaid", aliases=["paidbill"])
    async def billpaid_cmd(self, ctx: CustomContext, message_id: str):
        """Find the bill associated with a Discord message ID and mark it as PAID.
        
        Usage: ?top billpaid <message_id>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to confirm bill payments.", mention_author=False)

        clean_mid = message_id.strip()
        matching_bills = self.top_mgr.find_bill_by_message_id(clean_mid)
        if not matching_bills:
            return await ctx.reply(
                f"❌ No service bill found matching message ID or bill ID: `{clean_mid}`.\n"
                f"Please verify the Discord message ID belongs to an official Kyoka bill.",
                mention_author=False,
            )

        bill_to_pay = matching_bills[0]
        if bill_to_pay.get("status") == "PAID":
            paid_ts = int(bill_to_pay.get("paid_at", time.time()))
            staff_str = bill_to_pay.get("paid_by_name") or f"<@{bill_to_pay.get('paid_by_id')}>"
            return await ctx.reply(
                f"ℹ️ Bill **`{bill_to_pay['id']}`** has **already been marked as PAID** on <t:{paid_ts}:f> by `{staff_str}`.\n"
                f"*(Duplicate revenue counting prevented)*",
                mention_author=False,
            )

        try:
            paid_bill = self.top_mgr.mark_bill_paid_by_message_id(
                clean_mid,
                staff_id=ctx.author.id,
                staff_name=str(ctx.author),
            )
        except Exception as ex:
            return await ctx.reply(f"⚠️ Error confirming payment: {ex}", mention_author=False)

        # Attempt to edit original message embed
        posted_ch_id = paid_bill.get("posted_channel_id") or (ctx.channel.id if ctx.channel else None)
        target_mid = int(clean_mid) if clean_mid.isdigit() else (int(paid_bill["posted_message_id"]) if str(paid_bill.get("posted_message_id", "")).isdigit() else None)

        if posted_ch_id and target_mid and ctx.guild:
            ch = ctx.guild.get_channel(posted_ch_id)
            if ch and isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    orig_msg = await ch.fetch_message(target_mid)
                    if orig_msg:
                        new_embed = format_blox_fruits_bill_embed(paid_bill, guild=ctx.guild)
                        await orig_msg.edit(embed=new_embed)
                except Exception as ex:
                    logger.debug(f"Could not edit original bill message: {ex}")

        amt_display = format_beli_amount(paid_bill['total']) if paid_bill['payment_type'] == 'Beli' else paid_bill.get('fruit_details')
        confirm_embed = discord.Embed(
            title=f"🟢 BILL MARKED AS PAID • {paid_bill['id']}",
            description=(
                f"• **Bill ID:** `{paid_bill['id']}`\n"
                f"• **Customer:** <@{paid_bill.get('customer_id')}>\n"
                f"• **Service:** `{paid_bill.get('service_name')}`\n"
                f"• **Amount Paid:** **{amt_display}**\n"
                f"• **Verified By:** {ctx.author.mention}\n"
                f"• **Payment Message ID:** `{clean_mid}`\n\n"
                f"✅ **Recorded in accounting ledger & duplicate revenue prevented.**"
            ),
            color=KyokaTheme.SUCCESS,
            timestamp=discord.utils.utcnow(),
        )
        confirm_embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        confirm_embed.set_footer(text="Kyoka 3.0 Blox Fruits Ledger • Status: PAID")
        await ctx.reply(embed=confirm_embed, mention_author=False)

    # ── SUBCOMMAND: ?top bills [today/month] ───────────────────────────────────
    @top_group.group(name="bills", aliases=["invoices"], invoke_without_command=True)
    async def bills_group(self, ctx: CustomContext, mode: Optional[str] = None):
        """Blox Fruits Billing and Revenue Directory.
        
        Usage:
        • ?top bills today - View today's Blox Fruits revenue
        • ?top bill month - View current month's Blox Fruits revenue
        """
        if mode and mode.lower() == "today":
            rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
            return await self._send_blox_fruits_revenue_embed(ctx, rep, "TODAY'S BLOX FRUITS REVENUE")
        if mode and mode.lower() in ("month", "monthly"):
            rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
            return await self._send_blox_fruits_revenue_embed(ctx, rep, "MONTHLY BLOX FRUITS REVENUE")

        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_blox_fruits_revenue_embed(ctx, rep, "TODAY'S BLOX FRUITS REVENUE")

    @bills_group.command(name="today")
    async def bills_today_cmd(self, ctx: CustomContext):
        """Calculate total revenue from bills paid today (?top bills today)."""
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_blox_fruits_revenue_embed(ctx, rep, "TODAY'S BLOX FRUITS REVENUE")

    @bills_group.command(name="month")
    async def bills_month_cmd(self, ctx: CustomContext):
        """Calculate total paid revenue for current month (?top bills month)."""
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_blox_fruits_revenue_embed(ctx, rep, "MONTHLY BLOX FRUITS REVENUE")

    # ── SUBCOMMAND: ?top billpanel ────────────────────────────────────────────
    @top_group.command(name="billpanel")
    async def billpanel_cmd(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None):
        """Deploy interactive Blox Fruits Bill Creator panel with [ 🧾 Create Bill ] button.
        
        Usage: ?top billpanel [#channel]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to deploy billing panel.", mention_author=False)

        target_ch = channel or ctx.channel
        embed = discord.Embed(
            title="⛩️ KYOKA — BLOX FRUITS SERVICE BILLING",
            description=(
                "Welcome to the official **Blox Fruits Service Billing Desk**.\n\n"
                "Staff members can issue professional, itemized service invoices for:\n"
                "• **Trials & Race V4 Services**\n"
                "• **Normal, Advance & Order Raids**\n"
                "• **Beli & Fragment Farming**\n"
                "• **Sea Events, Leviathan & Boss Grinds**\n"
                "• **Physical Fruit & In-Game Payment Trades**\n\n"
                "Click the button below to generate a new invoice."
            ),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka 3.0 • Aizen Billing Engine")

        view = BillLauncherView(self.top_mgr)
        await target_ch.send(embed=embed, view=view)
        if target_ch.id != ctx.channel.id:
            await ctx.reply(f"✅ Billing creator panel deployed to {target_ch.mention}.", mention_author=False)

    # ── SUBCOMMAND: ?top billsetup ────────────────────────────────────────────
    @top_group.command(name="billsetup")
    async def billsetup_cmd(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None, tax: Optional[float] = None):
        """Configure default Blox Fruits billing channel and tax rate.
        
        Usage: ?top billsetup [#billing-channel] [tax_rate%]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to configure billing settings.", mention_author=False)

        cfg = self.top_mgr.set_billing_config(
            guild_id=ctx.guild.id if ctx.guild else 0,
            billing_channel_id=channel.id if channel else None,
            tax_rate=tax if tax is not None else None,
        )

        ch_str = f"<#{cfg['billing_channel_id']}>" if cfg.get("billing_channel_id") else "*Current Channel*"
        embed = discord.Embed(
            title="⚙️ BLOX FRUITS BILLING CONFIGURATION",
            description=(
                f"• **Billing Channel:** {ch_str}\n"
                f"• **Default Service Tax:** `{cfg.get('tax_rate', 5.0)}%`\n"
                f"• **Currency Unit:** `{cfg.get('currency_unit', 'Beli')}`\n\n"
                f"Deploy creator panel anytime with: `?top billpanel`"
            ),
            color=KyokaTheme.PRIMARY,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top addadult <user> ──────────────────────────────────────
    @top_group.command(name="addadult")
    async def addadult_cmd(self, ctx: CustomContext, user: Union[discord.Member, discord.User, str], *, notes: str = ""):
        """Grant a user access to restricted adult commands (Owner Only).
        
        Usage: ?top addadult <@user/user_id> [reason]
        """
        if ctx.author.id != 1505515188991033409:
            return await ctx.reply("❌ **Access Denied:** Only the Primary Bot Owner can grant adult command permissions.", mention_author=False)

        uid = None
        if isinstance(user, (discord.Member, discord.User)):
            uid = user.id
        else:
            match = re.search(r"\d{17,20}", str(user))
            if match:
                uid = int(match.group())
            else:
                return await ctx.reply("❌ Invalid user provided. Please mention a user or provide a valid Discord user ID.", mention_author=False)

        success = add_adult_user(uid, added_by=ctx.author.id, notes=notes)
        if success:
            await ctx.reply(f"✅ User <@{uid}> (`{uid}`) has been **authorized** for restricted adult commands.\n*(Immediate effect persisted)*", mention_author=False)
        else:
            await ctx.reply("❌ Failed to add user to adult allowlist database.", mention_author=False)

    # ── SUBCOMMAND: ?top removeadult <user> ───────────────────────────────────
    @top_group.command(name="removeadult")
    async def removeadult_cmd(self, ctx: CustomContext, user: Union[discord.Member, discord.User, str], *, notes: str = ""):
        """Revoke a user's access to restricted adult commands (Owner Only).
        
        Usage: ?top removeadult <@user/user_id> [reason]
        """
        if ctx.author.id != 1505515188991033409:
            return await ctx.reply("❌ **Access Denied:** Only the Primary Bot Owner can revoke adult command permissions.", mention_author=False)

        uid = None
        if isinstance(user, (discord.Member, discord.User)):
            uid = user.id
        else:
            match = re.search(r"\d{17,20}", str(user))
            if match:
                uid = int(match.group())
            else:
                return await ctx.reply("❌ Invalid user provided.", mention_author=False)

        if uid == 1505515188991033409:
            return await ctx.reply("❌ Cannot revoke the Primary Bot Owner.", mention_author=False)

        success = remove_adult_user(uid, removed_by=ctx.author.id, notes=notes)
        if success:
            await ctx.reply(f"🚫 User <@{uid}> (`{uid}`) access has been **REVOKED** immediately.\n*(Zero-delay enforcement active)*", mention_author=False)
        else:
            await ctx.reply("❌ Failed to revoke user from adult allowlist.", mention_author=False)

    # ── SUBCOMMAND: ?top listadult ────────────────────────────────────────────
    @top_group.command(name="listadult")
    async def listadult_cmd(self, ctx: CustomContext):
        """List all accounts authorized for restricted adult commands (Owner Only).
        
        Usage: ?top listadult
        """
        if ctx.author.id != 1505515188991033409:
            return await ctx.reply("❌ **Access Denied:** Only the Primary Bot Owner can view the adult allowlist.", mention_author=False)

        users = list_adult_users()
        lines = [f"• <@{1505515188991033409}> (`1505515188991033409`) — **Primary Owner**"]
        for u in users:
            if u["user_id"] != 1505515188991033409:
                ts = int(u["added_at"])
                note_str = f" — *{u['notes']}*" if u.get("notes") else ""
                lines.append(f"• <@{u['user_id']}> (`{u['user_id']}`) — Added <t:{ts}:R>{note_str}")

        embed = discord.Embed(
            title="🔒 RESTRICTED ADULT COMMAND ALLOWLIST",
            description=f"Total Authorized Users: `{len(lines)}`\n\n" + "\n".join(lines),
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Confidential Owner Console • Never Exposed Publicly")

        try:
            if ctx.guild:
                await ctx.author.send(embed=embed)
                await ctx.reply("📬 The adult allowlist has been delivered confidentially to your DM.", mention_author=False)
            else:
                await ctx.reply(embed=embed, mention_author=False)
        except Exception:
            await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top vouchregister ────────────────────────────────────────
    @top_group.command(name="vouchregister", aliases=["vouchscan", "scanvouches"])
    async def top_vouchregister_cmd(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        limit: int = 150,
    ):
        """Scan historical messages in a vouch channel and register valid vouches.
        
        Usage: ?top vouchregister [#channel] [limit]
        """
        vouch_cog = self.bot.get_cog("Vouches")
        if not vouch_cog:
            return await ctx.reply("❌ Vouch subsystem is currently loading or unavailable.", mention_author=False)
        await vouch_cog.vouchregister(ctx, channel=channel, limit=limit)

    # ── SUBCOMMAND: ?top help ─────────────────────────────────────────────────
    @top_group.command(name="help")
    async def top_help_subcmd(self, ctx: CustomContext, *, command_or_module: Optional[str] = None):
        """Display the complete Kyoka command directory organized by category.
        
        Usage: ?top help [category/command]
        """
        help_cog = self.bot.get_cog("Help")
        if help_cog and hasattr(help_cog, "help_command"):
            await help_cog.help_command(ctx, command_or_module=command_or_module)
        else:
            view = discord.ui.View(timeout=None)
            support_url = Config.SUPPORT_URL or "https://discord.gg/msH67hUx6G"
            view.add_item(discord.ui.Button(label="Join Support Server", style=discord.ButtonStyle.link, url=support_url, emoji="💜"))
            await ctx.reply("ℹ️ Command directory is loading. Need assistance? Join our official support server below!", view=view, mention_author=False)

    async def _send_blox_fruits_revenue_embed(self, ctx: CustomContext, rep: dict[str, Any], title: str):
        """Send formatted Blox Fruits revenue report embed."""
        paid_rev_beli = rep.get("received_revenue_m", 0.0)
        formatted_paid_rev = format_beli_amount(paid_rev_beli)
        tax_collected_m = rep.get("tax_collected_m", 0.0)
        formatted_tax = format_beli_amount(tax_collected_m)

        lines = [
            f"• **Bills Created Today:** `{rep.get('created_count', 0)}`" if "TODAY" in title.upper() else f"• **Bills Created:** `{rep.get('created_count', 0)}`",
            f"• **Bills Paid:** `{rep.get('paid_count', 0)}`",
            f"• **Unpaid Bills Created:** `{rep.get('unpaid_created_in_period', rep.get('unpaid_count', 0))}`",
            f"• **Total Paid Revenue:** **{formatted_paid_rev}**",
            f"• **Total Tax/Fees Collected:** `{formatted_tax}`",
        ]

        embed = discord.Embed(
            title=f"📊 {title}",
            description="\n".join(lines),
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )

        rev_by_type = rep.get("revenue_by_payment_type", {})
        if rev_by_type:
            type_lines = []
            for p_type, val_m in rev_by_type.items():
                type_lines.append(f"• **{p_type}:** {format_beli_amount(val_m)}")
            embed.add_field(name="💰 Revenue by Payment Type", value="\n".join(type_lines), inline=False)

        fruit_sum = rep.get("fruit_summary", {})
        if fruit_sum:
            fruit_lines = [f"• **{f_name}:** `{cnt}x received`" for f_name, cnt in list(fruit_sum.items())[:10]]
            embed.add_field(name="🍎 Physical Fruit Payments", value="\n".join(fruit_lines), inline=False)

        if self.is_bot_staff(ctx) and rep.get("staff_payments"):
            staff_lines = [f"• **{st}:** {format_beli_amount(val)}" for st, val in rep["staff_payments"].items()]
            embed.add_field(name="👥 Collections by Staff", value="\n".join(staff_lines), inline=False)

        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka 3.0 Blox Fruits Ledger • 100% Audit Precision")
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top paid ─────────────────────────────────────────────────
    @top_group.command(name="paid")
    async def paid_cmd(self, ctx: CustomContext, arg1: str, arg2: Optional[str] = None):
        """Mark bill as PAID using Discord message ID of payment proof.
        
        Workflows supported:
        • +top paid <bill_id> <message_id>
        • +top paid <message_id> (auto-locates active unpaid bill)
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to confirm payments.", mention_author=False)

        p = ctx.prefix or Config.DEFAULT_PREFIX

        if arg2 is not None:
            bill_id = arg1
            message_id = arg2
        else:
            if arg1.isdigit():
                message_id = arg1
                return await self.billpaid_cmd(ctx, message_id)
            else:
                return await ctx.reply(f"❌ Please provide a payment proof Message ID:\n`{p}top paid {arg1} <message_id>`", mention_author=False)

        try:
            bill = self.top_mgr.mark_bill_paid(
                bill_id=bill_id,
                staff_id=ctx.author.id,
                staff_name=str(ctx.author),
                message_id=message_id,
            )
        except Exception as e:
            return await ctx.reply(f"⚠️ {e}", mention_author=False)

        embed = discord.Embed(
            title=f"🟢 PAYMENT CONFIRMED • {bill['id']}",
            description=(
                f"**Bill ID:** `{bill['id']}`\n"
                f"**Service:** `{bill['service_name']}`\n"
                f"**Amount Paid:** **{bill['total_display']}**\n"
                f"**Confirmed By:** {ctx.author.mention}\n"
                f"**Payment Message ID:** `{message_id}`\n\n"
                f"✅ **Revenue recorded in accounting ledger.**"
            ),
            color=KyokaTheme.SUCCESS,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text=f"Kyoka Top Billing • Status: PAID")
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMANDS: ?top today, ?top weekly, ?top monthly, ?top unpaid ───────
    @top_group.group(name="today", invoke_without_command=True)
    async def today_group(self, ctx: CustomContext, mode: Optional[str] = "bills"):
        """View today's financial performance and bill count.
        
        Usage: +top today [bills/revenue]
        """
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @today_group.command(name="bills")
    async def today_bills_cmd(self, ctx: CustomContext):
        """View today's bills created and collected."""
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @today_group.command(name="revenue")
    async def today_revenue_cmd(self, ctx: CustomContext):
        """View today's revenue and collection statistics."""
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @top_group.group(name="weekly", invoke_without_command=True)
    async def weekly_group(self, ctx: CustomContext, mode: Optional[str] = "bills"):
        """View weekly performance (last 7 days).
        
        Usage: +top weekly [bills/revenue]
        """
        rep = self.top_mgr.get_weekly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @weekly_group.command(name="bills")
    async def weekly_bills_cmd(self, ctx: CustomContext):
        """View weekly bills summary."""
        rep = self.top_mgr.get_weekly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @weekly_group.command(name="revenue")
    async def weekly_revenue_cmd(self, ctx: CustomContext):
        """View weekly revenue summary."""
        rep = self.top_mgr.get_weekly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @top_group.group(name="monthly", invoke_without_command=True)
    async def monthly_group(self, ctx: CustomContext, mode: Optional[str] = "bills"):
        """View monthly performance (last 30 days).
        
        Usage: +top monthly [bills/revenue]
        """
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @monthly_group.command(name="bills")
    async def monthly_bills_cmd(self, ctx: CustomContext):
        """View monthly bills summary."""
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @monthly_group.command(name="revenue")
    async def monthly_revenue_cmd(self, ctx: CustomContext):
        """View monthly revenue summary."""
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @top_group.group(name="revenue", invoke_without_command=True)
    async def revenue_group(self, ctx: CustomContext, period: Optional[str] = "today"):
        """View revenue summary for a period (today, weekly, monthly).
        
        Usage: +top revenue [today/weekly/monthly]
        """
        norm = (period or "today").lower().strip()
        if "week" in norm:
            rep = self.top_mgr.get_weekly_report(ctx.guild.id if ctx.guild else None)
        elif "month" in norm:
            rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        else:
            rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @revenue_group.command(name="today")
    async def revenue_today_cmd(self, ctx: CustomContext):
        """Today's revenue ledger."""
        rep = self.top_mgr.get_today_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @revenue_group.command(name="weekly")
    async def revenue_weekly_cmd(self, ctx: CustomContext):
        """Weekly revenue ledger."""
        rep = self.top_mgr.get_weekly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @revenue_group.command(name="monthly")
    async def revenue_monthly_cmd(self, ctx: CustomContext):
        """Monthly revenue ledger."""
        rep = self.top_mgr.get_monthly_report(ctx.guild.id if ctx.guild else None)
        await self._send_report_embed(ctx, rep)

    @top_group.command(name="unpaid")
    async def unpaid_cmd(self, ctx: CustomContext):
        """View total outstanding unpaid bills."""
        unpaid = self.top_mgr.list_bills(guild_id=ctx.guild.id if ctx.guild else None, status="UNPAID", limit=15)
        total_outstanding = sum(b["total"] for b in unpaid)

        if not unpaid:
            return await ctx.reply("🟢 All bills are paid! Zero outstanding balance.", mention_author=False)

        lines = [f"`{b['id']}` • 🟡 **{b['total_display']}** — `{b['service_name']}`" for b in unpaid]
        embed = discord.Embed(
            title="🟡 OUTSTANDING UNPAID INVOICES",
            description=(
                f"**Total Outstanding:** **{self.top_mgr.format_price(total_outstanding)}** across `{len(unpaid)}` bill(s)\n\n"
                + "\n".join(lines)
            ),
            color=KyokaTheme.WARNING,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Kyoka Top Accounting Ledger • Use +top paid <ID> <msg_id> to settle")
        await ctx.reply(embed=embed, mention_author=False)

    async def _send_report_embed(self, ctx: CustomContext, rep: dict[str, Any]):
        """Render financial report embed with accounting precision."""
        embed = discord.Embed(
            title=f"📊 FINANCIAL REPORT • {rep['period_name'].upper()}",
            description=(
                f"**Period Window:** <t:{int(rep['start_time'])}:d> — <t:{int(rep['end_time'])}:d>\n\n"
                f"• **Invoices Created:** `{rep['created_count']}` (Value: **{rep['created_total_display']}**)\n"
                f"• **Confirmed Paid:** `+{rep['paid_count']}` (Revenue: **{rep['received_revenue_display']}**)\n"
                f"• **Outstanding Unpaid:** `+{rep['unpaid_count']}` (Balance: **{rep['outstanding_display']}**)\n"
                f"• **Cancelled Invoices:** `{rep['cancelled_count']}`\n"
                f"• **Refunds Issued:** `{rep['refunded_count']}` (Total: **-{rep['refund_total_display']}**)\n"
                f"• **Net Received Revenue:** **{rep['net_revenue_display']}**"
            ),
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )

        if rep.get("category_breakdown"):
            cats = ", ".join([f"{k}: `{v}`" for k, v in rep["category_breakdown"].items()])
            embed.add_field(name="📂 Service Breakdown", value=cats, inline=False)

        # Staff breakdown visible only to staff
        if self.is_bot_staff(ctx) and rep.get("staff_payments"):
            staff_lines = [f"• **{st}:** **{self.top_mgr.format_price(val)}**" for st, val in rep["staff_payments"].items()]
            embed.add_field(name="👥 Staff Collections (Staff-Only)", value="\n".join(staff_lines), inline=False)

        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka Accounting Ledger • 100% Audit Precision")
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top price / ?top prices ──────────────────────────────────
    @top_group.group(name="price", aliases=["prices"], invoke_without_command=True)
    async def price_cmd(self, ctx: CustomContext, *, query: Optional[str] = None):
        """Universal Smart Price Search for ALL services.
        
        Usage:
        • +top price of 1 trial
        • +top price of 5 normal raids
        • +top price of Draco V2
        • +top price of 2 trials with 5% tax
        • +top prices [category] — Browse whole category
        """
        all_prices = self.top_mgr.get_all_prices()
        categories = sorted(list({p.category for p in all_prices}))

        if not query or not query.strip():
            # Group by categories
            desc = "**Authoritative Blox Fruits Price Catalogue:**\n\n"
            for c in categories:
                count = sum(1 for p in all_prices if p.category == c)
                desc += f"• **{c}:** `{count} services`\n"

            p = ctx.prefix or Config.DEFAULT_PREFIX
            desc += f"\n*Type `{p}top prices <category>` to view itemized tier prices for any category.*"

            embed = discord.Embed(
                title="🏷️ TOP AI MANAGER • PRICE CATALOGUE",
                description=desc,
                color=KyokaTheme.PRIMARY,
            )
            embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            embed.set_footer(text=f"Total Services: {len(all_prices)} • Kyoka Official Prices")
            return await ctx.reply(embed=embed, mention_author=False)

        q_clean = query.strip()
        # If user explicitly used "+top prices <category>" to view whole category
        if ctx.invoked_with == "prices" and any(q_clean.lower() == c.lower() for c in categories):
            matched_cat = next(c for c in categories if q_clean.lower() == c.lower())
            filtered = [p for p in all_prices if p.category.lower() == matched_cat.lower()]
            lines = []
            for p in filtered[:25]:
                note = f" *({p.condition_note})*" if p.condition_note else ""
                lines.append(f"• **{p.service_name}:** `{p.price_display}`{note}")

            embed = discord.Embed(
                title=f"🏷️ OFFICIAL PRICES • {matched_cat.upper()}",
                description="\n".join(lines),
                color=KyokaTheme.PRIMARY,
            )
            embed.set_footer(text="Kyoka Top AI Manager • Authoritative Price Catalogue")
            return await ctx.reply(embed=embed, mention_author=False)

        # Execute Universal Smart Price Search
        try:
            parsed = self.top_mgr.parse_top_query(q_clean)
            calc: CalculationResult = parsed["calculation"]
            embed = format_single_price_embed(calc)
            return await ctx.reply(embed=embed, mention_author=False)
        except KeyError as ke:
            p = ctx.prefix or Config.DEFAULT_PREFIX
            err_emb = discord.Embed(
                title="⚠️ Service Not Found",
                description=f"{ke}\n\n*Type `{p}top prices` to view the complete price catalogue or contact staff.*",
                color=KyokaTheme.WARNING,
            )
            return await ctx.reply(embed=err_emb, mention_author=False)
        except Exception as e:
            return await ctx.reply(f"❌ Could not interpret price query: {e}", mention_author=False)

    @price_cmd.command(name="set")
    async def price_set_cmd(self, ctx: CustomContext, service_key: str, new_price: float):
        """Update a service price without modifying past bills.
        
        Usage: +top price set <service_key> <new_price_amount>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to update prices.", mention_author=False)

        try:
            item = self.top_mgr.update_price(service_key, new_price, staff_id=ctx.author.id, reason=f"Updated by {ctx.author}")
            await ctx.reply(f"✅ Price for **{item.service_name}** (`{item.service_key}`) updated to **{item.price_display}**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @price_cmd.command(name="rename")
    async def price_rename_cmd(self, ctx: CustomContext, service_key: str, *, new_name: str):
        """Rename a service.
        
        Usage: +top price rename <service_key> <new_name>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to rename services.", mention_author=False)

        try:
            item = self.top_mgr.rename_service(service_key, new_name, staff_id=ctx.author.id)
            await ctx.reply(f"✅ Service `{item.service_key}` renamed to **{item.service_name}**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @price_cmd.command(name="custom")
    async def price_custom_cmd(self, ctx: CustomContext, service_key: str, on_off: str = "on"):
        """Toggle whether service requires custom quote from staff.
        
        Usage: +top price custom <service_key> [on/off]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        flag = on_off.lower() in ("on", "true", "1", "yes")
        try:
            item = self.top_mgr.toggle_custom_quote(service_key, staff_id=ctx.author.id, required=flag)
            status_text = "Custom Quote Required" if flag else "Fixed Standard Pricing"
            await ctx.reply(f"✅ Service **{item.service_name}** updated to: **{status_text}**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @price_cmd.command(name="history")
    async def price_history_cmd(self, ctx: CustomContext, service_key: str):
        """View historical price change audit log.
        
        Usage: +top price history <service_key>
        """
        hist = self.top_mgr.get_price_history(service_key)
        if not hist:
            return await ctx.reply(f"ℹ️ No price modifications recorded for `{service_key}` (still on original seeded price).", mention_author=False)

        lines = [f"• <t:{int(h['timestamp'])}:d>: `{h['old_display']}` → **{h['new_display']}** by <@{h['changed_by']}>" for h in hist]
        embed = discord.Embed(
            title=f"📜 PRICE AUDIT HISTORY • {service_key.upper()}",
            description="\n".join(lines),
            color=KyokaTheme.PRIMARY,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top app (STAFF APPLICATION SYSTEM) ───────────────────────
    @top_group.group(name="app", aliases=["apply", "applications"], invoke_without_command=True)
    async def app_group(self, ctx: CustomContext):
        """Staff Application System (Appy-Style).
        
        Commands:
        • +top app setup <#channel> — Configure review channel
        • +top app panel [#channel] — Post persistent recruitment panel
        • +top app view <app_id> — View application details
        • +top app list [status] — List pending/reviewed applications
        • +top app accept <app_id> [reason] — Accept applicant
        • +top app reject <app_id> [reason] — Reject applicant
        """
        p = ctx.prefix or Config.DEFAULT_PREFIX
        embed = discord.Embed(
            title="⛩️ KYOKA STAFF APPLICATIONS • APPY ENGINE",
            description=(
                "> **Enterprise staff recruitment & review workflow.**\n\n"
                f"• `{p}top app setup <#channel>` — Set application review channel\n"
                f"• `{p}top app panel [#channel]` — Post recruitment panel with 'Apply Now' button\n"
                f"• `{p}top app view <app_id>` — View submitted answers and notes\n"
                f"• `{p}top app list [status]` — List submissions (Pending, Accepted, Rejected)\n"
                f"• `{p}top app accept <app_id>` — Accept and optionally grant staff role\n"
                f"• `{p}top app reject <app_id>` — Reject application with reason\n"
                f"• `{p}top app note <app_id> <note>` — Add private staff note"
            ),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        await ctx.reply(embed=embed, mention_author=False)

    @app_group.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def app_setup_cmd(self, ctx: CustomContext, channel: discord.TextChannel):
        """Set the private channel where staff applications are sent for review.
        
        Usage: +top app setup <#channel>
        """
        self.top_mgr.set_app_config(ctx.guild.id, review_channel_id=channel.id)
        await ctx.reply(f"✅ Staff application review channel configured to: {channel.mention}", mention_author=False)

    @app_group.command(name="panel")
    @commands.has_permissions(administrator=True)
    async def app_panel_cmd(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None):
        """Send the persistent recruitment panel embed with interactive 'Apply' components.
        
        Usage: +top app panel [#channel]
        """
        target_ch = channel or ctx.channel
        embed = discord.Embed(
            title="⛩️ KYOKA STAFF RECRUITMENT • NOW ACCEPTING APPLICATIONS",
            description=(
                "> *\"True power lies in disciplined execution.\"* — **Aizen**\n\n"
                "We are actively recruiting passionate, dedicated, and trustworthy members to join our official staff team!\n\n"
                "**Open Positions:**\n"
                "• 🛡️ **Community Moderator:** Enforce server safety, chat rules, and raid defense.\n"
                "• 🌱 **Trial Staff / Helper:** Guide new members, assist general inquiries.\n"
                "• 🧾 **Support & Billing Staff:** Process service invoices, manage tickets, verify payments.\n"
                "• ⚔️ **Blox Fruits Service Provider:** Carry raids, V4 trials, Beli farming, and masteries.\n\n"
                "**Requirements:**\n"
                "• Active presence and respectful communication.\n"
                "• Genuine Blox Fruits / Discord experience.\n"
                "• Ability to handle client disputes calmly and professionally.\n\n"
                "👉 **Click 'Quick Apply' or select your desired position below to begin!**"
            ),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka Staff Recruitment Engine • Private & Confidential Submissions")

        view = StaffApplicationPanelView(self.top_mgr)
        msg = await target_ch.send(embed=embed, view=view)

        # Save panel message ID
        self.top_mgr.set_app_config(ctx.guild.id, panel_message_id=msg.id)
        if target_ch != ctx.channel:
            await ctx.reply(f"✅ Recruitment panel posted in {target_ch.mention}.", mention_author=False)

    @app_group.command(name="view")
    async def app_view_cmd(self, ctx: CustomContext, app_id: str):
        """View full application answers and review status.
        
        Usage: +top app view <app_id>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        app = self.top_mgr.get_application(app_id)
        if not app:
            return await ctx.reply(f"❌ Application **`{app_id}`** not found.", mention_author=False)

        status_emoji = {"PENDING": "🟡", "ACCEPTED": "🟢", "REJECTED": "🔴", "UNDER_REVIEW": "🟠"}.get(app["status"], "⚪")
        embed = discord.Embed(
            title=f"📥 STAFF APPLICATION • {app['id']}",
            description=(
                f"**Applicant:** <@{app['applicant_id']}> (`{app['applicant_name']}`)\n"
                f"**Position:** `{app['position']}`\n"
                f"**Status:** {status_emoji} **{app['status']}**\n"
                f"**Submitted:** <t:{int(app['created_at'])}:F>"
            ),
            color=KyokaTheme.PRIMARY,
        )

        for q, a in app.get("answers", {}).items():
            embed.add_field(name=f"❓ {q}", value=f"> {a[:900]}", inline=False)

        if app.get("decision_reason"):
            embed.add_field(name="⚖️ Decision Notes", value=f"> {app['decision_reason']}", inline=False)

        if app.get("staff_notes"):
            embed.add_field(name="📝 Private Staff Notes", value=f"> {app['staff_notes'][:900]}", inline=False)

        embed.set_footer(text=f"Application ID: {app['id']} • Reviewed By: {app.get('reviewer_name') or 'Pending'}")
        await ctx.reply(embed=embed, mention_author=False)

    @app_group.command(name="list")
    async def app_list_cmd(self, ctx: CustomContext, status: Optional[str] = None):
        """List recent staff applications.
        
        Usage: +top app list [PENDING/ACCEPTED/REJECTED/UNDER_REVIEW]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        apps = self.top_mgr.list_applications(guild_id=ctx.guild.id if ctx.guild else 0, status=status, limit=15)
        if not apps:
            return await ctx.reply(f"ℹ️ No applications found{f' with status `{status.upper()}`' if status else ''}.", mention_author=False)

        lines = []
        for a in apps:
            emoji = {"PENDING": "🟡", "ACCEPTED": "🟢", "REJECTED": "🔴", "UNDER_REVIEW": "🟠"}.get(a["status"], "⚪")
            lines.append(f"`{a['id']}` • {emoji} **{a['applicant_name']}** — `{a['position']}` ({a['status']})")

        embed = discord.Embed(
            title=f"📋 STAFF APPLICATIONS {f'• {status.upper()}' if status else ''}",
            description="\n".join(lines),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_footer(text="Type +top app view <ID> to inspect details")
        await ctx.reply(embed=embed, mention_author=False)

    @app_group.command(name="accept")
    async def app_accept_cmd(self, ctx: CustomContext, app_id: str, *, reason: str = "Accepted by staff"):
        """Accept a staff application, grant configured role, and notify the applicant.
        
        Usage: +top app accept <app_id> [reason]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="ACCEPTED",
                reason=reason,
            )
        except Exception as e:
            return await ctx.reply(f"⚠️ {e}", mention_author=False)

        role_msg = ""
        cfg = self.top_mgr.get_app_config(ctx.guild.id if ctx.guild else 0)
        auto_role_id = cfg.get("role_on_accept_id")
        if auto_role_id and ctx.guild:
            target_role = ctx.guild.get_role(auto_role_id)
            target_member = ctx.guild.get_member(app["applicant_id"])
            if target_role and target_member:
                try:
                    await target_member.add_roles(target_role, reason=f"Staff application {app_id.upper()} accepted")
                    role_msg = f" Granted **{target_role.name}**."
                except Exception as ex:
                    role_msg = f" (Role assignment note: {ex})"

        # DM applicant
        try:
            applicant_user = self.bot.get_user(app["applicant_id"])
            if applicant_user:
                dm = discord.Embed(
                    title="🎉 Congratulations! Staff Application Accepted",
                    description=(
                        f"Your application (`{app_id.upper()}`) has been **ACCEPTED** by {ctx.author.mention}!\n\n"
                        f"> **Note / Reason:** `{reason}`\n\n"
                        f"Welcome to the team! Please contact server management for your onboarding."
                    ),
                    color=KyokaTheme.SUCCESS,
                )
                await applicant_user.send(embed=dm)
        except Exception:
            pass

        # Audit channel logging
        aud_ch_id = cfg.get("audit_channel_id")
        if aud_ch_id and ctx.guild:
            aud_ch = ctx.guild.get_channel(aud_ch_id)
            if aud_ch and isinstance(aud_ch, discord.TextChannel):
                audit_emb = discord.Embed(
                    title="⚖️ AUDIT: Staff Application Accepted",
                    description=f"**Application:** `{app_id.upper()}`\n**Applicant:** <@{app['applicant_id']}>\n**Reviewer:** {ctx.author.mention}\n**Reason:** `{reason}`",
                    color=KyokaTheme.SUCCESS,
                    timestamp=discord.utils.utcnow(),
                )
                try:
                    await aud_ch.send(embed=audit_emb)
                except Exception:
                    pass

        await ctx.reply(f"✅ Application **`{app_id.upper()}`** for <@{app['applicant_id']}> marked as **ACCEPTED**.{role_msg}", mention_author=False)

    @app_group.command(name="reject")
    async def app_reject_cmd(self, ctx: CustomContext, app_id: str, *, reason: str = "Not accepted at this time"):
        """Reject a staff application and notify the applicant.
        
        Usage: +top app reject <app_id> [reason]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="REJECTED",
                reason=reason,
            )
        except Exception as e:
            return await ctx.reply(f"⚠️ {e}", mention_author=False)

        # DM applicant
        try:
            applicant_user = self.bot.get_user(app["applicant_id"])
            if applicant_user:
                dm = discord.Embed(
                    title="Notice Regarding Your Staff Application",
                    description=(
                        f"Thank you for your interest in joining our staff team. After review, your application "
                        f"(`{app_id.upper()}`) was **not accepted** at this time.\n\n"
                        f"> **Reason:** `{reason}`\n\n"
                        f"You are welcome to reapply once the cooldown period has elapsed."
                    ),
                    color=KyokaTheme.ERROR,
                )
                await applicant_user.send(embed=dm)
        except Exception:
            pass

        # Audit channel logging
        cfg = self.top_mgr.get_app_config(ctx.guild.id if ctx.guild else 0)
        aud_ch_id = cfg.get("audit_channel_id")
        if aud_ch_id and ctx.guild:
            aud_ch = ctx.guild.get_channel(aud_ch_id)
            if aud_ch and isinstance(aud_ch, discord.TextChannel):
                audit_emb = discord.Embed(
                    title="⚖️ AUDIT: Staff Application Rejected",
                    description=f"**Application:** `{app_id.upper()}`\n**Applicant:** <@{app['applicant_id']}>\n**Reviewer:** {ctx.author.mention}\n**Reason:** `{reason}`",
                    color=KyokaTheme.ERROR,
                    timestamp=discord.utils.utcnow(),
                )
                try:
                    await aud_ch.send(embed=audit_emb)
                except Exception:
                    pass

        await ctx.reply(f"🔴 Application **`{app_id.upper()}`** for <@{app['applicant_id']}> marked as **REJECTED**.", mention_author=False)

    @app_group.command(name="underreview", aliases=["review"])
    async def app_underreview_cmd(self, ctx: CustomContext, app_id: str):
        """Mark a staff application as UNDER REVIEW.
        
        Usage: +top app underreview <app_id>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="UNDER_REVIEW",
                reason="Review in progress",
            )
            await ctx.reply(f"🟠 Application **`{app_id.upper()}`** status updated to **UNDER REVIEW**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @app_group.command(name="requestinfo", aliases=["reqinfo"])
    async def app_requestinfo_cmd(self, ctx: CustomContext, app_id: str, *, question: str):
        """Request additional information from an applicant and log inquiry note.
        
        Usage: +top app requestinfo <app_id> <question>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="MORE_INFO_REQUESTED",
                reason=f"Info requested: {question}",
            )
            self.top_mgr.add_application_note(app_id, staff_id=ctx.author.id, note=f"[Info Requested] {question}")
        except Exception as e:
            return await ctx.reply(f"⚠️ {e}", mention_author=False)

        # DM applicant
        try:
            applicant_user = self.bot.get_user(app["applicant_id"])
            if applicant_user:
                dm = discord.Embed(
                    title="💬 Staff Application — Information Requested",
                    description=(
                        f"The staff team has reviewed your application (`{app_id.upper()}`) and requested additional information:\n\n"
                        f"> **Question:** {question}\n\n"
                        f"Please contact server staff directly with your response."
                    ),
                    color=KyokaTheme.WARNING,
                )
                await applicant_user.send(embed=dm)
        except Exception:
            pass

        await ctx.reply(f"💬 Information request sent for application **`{app_id.upper()}`**.", mention_author=False)

    @app_group.command(name="closeapp", aliases=["archive"])
    async def app_closeapp_cmd(self, ctx: CustomContext, app_id: str, *, reason: str = "Closed by staff"):
        """Close or archive a staff application.
        
        Usage: +top app closeapp <app_id> [reason]
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="CLOSED",
                reason=reason,
            )
            await ctx.reply(f"📁 Application **`{app_id.upper()}`** has been **CLOSED / ARCHIVED**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @app_group.command(name="reopen")
    async def app_reopen_cmd(self, ctx: CustomContext, app_id: str):
        """Reopen a previously closed or reviewed application back to PENDING.
        
        Usage: +top app reopen <app_id>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="PENDING",
                reason="Reopened by staff",
            )
            await ctx.reply(f"🔄 Application **`{app_id.upper()}`** reopened as **PENDING**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @app_group.command(name="open")
    @commands.has_permissions(manage_guild=True)
    async def app_open_cmd(self, ctx: CustomContext):
        """Open staff recruitment and accept new applications.
        
        Usage: +top app open
        """
        self.top_mgr.set_app_config(ctx.guild.id, is_open=1)
        await ctx.reply("✅ Staff applications are now **OPEN**. Members may submit applications.", mention_author=False)

    @app_group.command(name="close", aliases=["pause"])
    @commands.has_permissions(manage_guild=True)
    async def app_close_cmd(self, ctx: CustomContext):
        """Close or pause staff recruitment and reject new submissions.
        
        Usage: +top app close
        """
        self.top_mgr.set_app_config(ctx.guild.id, is_open=0)
        await ctx.reply("🛑 Staff applications are now **CLOSED / PAUSED**. New submissions are temporarily blocked.", mention_author=False)

    @app_group.command(name="status")
    async def app_status_cmd(self, ctx: CustomContext, app_id: str):
        """Check application status (Public & safe view, sensitive notes omitted).
        
        Usage: +top app status <app_id>
        """
        app = self.top_mgr.get_application(app_id)
        if not app:
            return await ctx.reply(f"❌ Application **`{app_id.upper()}`** not found.", mention_author=False)

        status_emoji = {
            "PENDING": "🟡",
            "SUBMITTED": "🟡",
            "UNDER_REVIEW": "🟠",
            "MORE_INFO_REQUESTED": "💬",
            "ACCEPTED": "🟢",
            "REJECTED": "🔴",
            "CLOSED": "📁",
            "WITHDRAWN": "⚪",
        }.get(app["status"], "⚪")

        color = KyokaTheme.PRIMARY
        if app["status"] == "ACCEPTED":
            color = KyokaTheme.SUCCESS
        elif app["status"] in ("REJECTED", "CLOSED"):
            color = KyokaTheme.ERROR
        elif app["status"] == "MORE_INFO_REQUESTED":
            color = KyokaTheme.WARNING

        embed = discord.Embed(
            title=f"📄 APPLICATION STATUS • {app['id']}",
            description=(
                f"**Applicant:** <@{app['applicant_id']}>\n"
                f"**Position:** `{app['position']}`\n"
                f"**Current Status:** {status_emoji} **{app['status']}**\n"
                f"**Submitted:** <t:{int(app['created_at'])}:R>"
            ),
            color=color,
        )
        if app.get("decision_reason"):
            embed.add_field(name="⚖️ Status Note", value=f"> {app['decision_reason']}", inline=False)

        embed.set_footer(text="Kyoka Staff Recruitment Engine")
        await ctx.reply(embed=embed, mention_author=False)

    @app_group.command(name="stats")
    async def app_stats_cmd(self, ctx: CustomContext):
        """View recruitment statistics and average review duration.
        
        Usage: +top app stats
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        stats = self.top_mgr.get_application_stats(ctx.guild.id if ctx.guild else 0)
        cfg = self.top_mgr.get_app_config(ctx.guild.id if ctx.guild else 0)
        open_status = "🟢 Open" if cfg.get("is_open", 1) != 0 else "🔴 Closed/Paused"

        pos_lines = [f"• **{pos}:** {cnt}" for pos, cnt in stats["positions"].items()] or ["• None recorded yet"]

        embed = discord.Embed(
            title="📊 STAFF RECRUITMENT METRICS & STATS",
            description=f"**Current Status:** {open_status}\n**Total Applications:** `{stats['total']}`",
            color=KyokaTheme.PRIMARY,
        )
        embed.add_field(
            name="📋 Status Breakdown",
            value=(
                f"🟡 Pending: **{stats['pending']}**\n"
                f"🟠 Under Review: **{stats['under_review']}**\n"
                f"💬 Info Requested: **{stats['more_info']}**\n"
                f"🟢 Accepted: **{stats['accepted']}**\n"
                f"🔴 Rejected: **{stats['rejected']}**\n"
                f"📁 Closed: **{stats['closed']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="⏱️ Efficiency",
            value=f"Average Review Time:\n**{stats['avg_review_hours']} hours**",
            inline=True,
        )
        embed.add_field(
            name="🛡️ Positions Breakdown",
            value="\n".join(pos_lines),
            inline=False,
        )
        embed.set_footer(text="Kyoka Staff Analytics")
        await ctx.reply(embed=embed, mention_author=False)

    @app_group.group(name="config", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def app_config_group(self, ctx: CustomContext):
        """Manage recruitment system configuration.
        
        Subcommands:
        • +top app config reviewer_role <@role>
        • +top app config role <@role>
        • +top app config audit_channel <#channel>
        • +top app config cooldown <days>
        • +top app config show
        """
        p = ctx.prefix or Config.DEFAULT_PREFIX
        cfg = self.top_mgr.get_app_config(ctx.guild.id)
        open_str = "🟢 Open" if cfg.get("is_open", 1) != 0 else "🔴 Closed"
        rev_ch = f"<#{cfg['review_channel_id']}>" if cfg.get("review_channel_id") else "*None configured*"
        rev_role = f"<@&{cfg['reviewer_role_id']}>" if cfg.get("reviewer_role_id") else "*Administrators only*"
        auto_role = f"<@&{cfg['role_on_accept_id']}>" if cfg.get("role_on_accept_id") else "*None*"
        aud_ch = f"<#{cfg['audit_channel_id']}>" if cfg.get("audit_channel_id") else "*None*"

        embed = discord.Embed(
            title="⚙️ STAFF RECRUITMENT CONFIGURATION",
            description=(
                f"**Recruitment Status:** {open_str}\n"
                f"**Review Channel:** {rev_ch}\n"
                f"**Reviewer Role:** {rev_role}\n"
                f"**Auto Role on Accept:** {auto_role}\n"
                f"**Audit Channel:** {aud_ch}\n"
                f"**Rejection Cooldown:** `{cfg.get('cooldown_days', 7)} days`\n\n"
                f"**Commands:**\n"
                f"• `{p}top app config reviewer_role <@role>`\n"
                f"• `{p}top app config role <@role>`\n"
                f"• `{p}top app config audit_channel <#channel>`\n"
                f"• `{p}top app config cooldown <days>`"
            ),
            color=KyokaTheme.PRIMARY,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @app_config_group.command(name="reviewer_role", aliases=["reviewerrole", "reviewers"])
    @commands.has_permissions(manage_guild=True)
    async def config_reviewer_role_cmd(self, ctx: CustomContext, role: discord.Role):
        """Set the designated role allowed to review applications."""
        self.top_mgr.set_app_config(ctx.guild.id, reviewer_role_id=role.id)
        await ctx.reply(f"✅ Staff reviewer role set to {role.mention}.", mention_author=False)

    @app_config_group.command(name="role", aliases=["autorole", "staffrole"])
    @commands.has_permissions(manage_guild=True)
    async def config_role_cmd(self, ctx: CustomContext, role: discord.Role):
        """Set role automatically granted when an application is accepted."""
        self.top_mgr.set_app_config(ctx.guild.id, role_on_accept_id=role.id)
        await ctx.reply(f"✅ Automatic role on accept set to {role.mention}.", mention_author=False)

    @app_config_group.command(name="audit_channel", aliases=["auditchannel", "audit"])
    @commands.has_permissions(manage_guild=True)
    async def config_audit_channel_cmd(self, ctx: CustomContext, channel: discord.TextChannel):
        """Set the channel where application decisions and audits are logged."""
        self.top_mgr.set_app_config(ctx.guild.id, audit_channel_id=channel.id)
        await ctx.reply(f"✅ Staff application audit channel set to {channel.mention}.", mention_author=False)

    @app_config_group.command(name="cooldown")
    @commands.has_permissions(manage_guild=True)
    async def config_cooldown_cmd(self, ctx: CustomContext, days: int):
        """Set rejection cooldown period in days before re-applying."""
        if days < 0 or days > 365:
            return await ctx.reply("❌ Cooldown days must be between 0 and 365.", mention_author=False)
        self.top_mgr.set_app_config(ctx.guild.id, cooldown_days=days)
        await ctx.reply(f"✅ Application rejection cooldown set to **{days} day(s)**.", mention_author=False)

    @app_group.command(name="note")
    async def app_note_cmd(self, ctx: CustomContext, app_id: str, *, note: str):
        """Add a private staff note to an application.
        
        Usage: +top app note <app_id> <note>
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required.", mention_author=False)

        try:
            self.top_mgr.add_application_note(app_id, staff_id=ctx.author.id, note=note)
            await ctx.reply(f"📝 Note appended to application **`{app_id.upper()}`**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    # ── TOP-LEVEL APPLY COMMAND GROUP ─────────────────────────────────────────
    @commands.group(name="apply", aliases=["staffapp"], invoke_without_command=True)
    async def apply_top_level_cmd(self, ctx: CustomContext):
        """Staff recruitment portal & application console.
        
        Usage:
        • +apply — Open interactive recruitment position selector
        • +apply status <app_id> — Check status of your application
        """
        p = ctx.prefix or Config.DEFAULT_PREFIX
        cfg = self.top_mgr.get_app_config(ctx.guild.id if ctx.guild else 0)
        if cfg.get("is_open", 1) == 0:
            return await ctx.reply(
                "🛑 **Staff applications are currently closed or paused.** Please check back later!",
                mention_author=False,
            )

        embed = discord.Embed(
            title="⛩️ KYOKA STAFF RECRUITMENT • APPLICATION PORTAL",
            description=(
                "> *\"True power lies in disciplined execution.\"* — **Aizen**\n\n"
                "Welcome to the Kyoka Staff Application Portal!\n"
                "Select a position below to launch your private application modal.\n\n"
                f"• Check existing application status: `{p}apply status <APP_ID>`"
            ),
            color=KyokaTheme.PRIMARY,
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text="Kyoka Staff Recruitment Engine • Confidential Submissions")
        view = StaffApplicationPanelView(self.top_mgr)
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @apply_top_level_cmd.command(name="status")
    async def apply_sub_status_cmd(self, ctx: CustomContext, app_id: str):
        """Check application status via +apply status <app_id>."""
        await self.app_status_cmd(ctx, app_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TopAIManager(bot))
