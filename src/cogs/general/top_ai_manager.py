"""
Kyoka 3.0 - Top AI Manager, Service Billing & Staff Application System Cog
Integrates natural-language pricing queries, decimal-safe tax calculations,
persistent bill generation with Discord message ID verification, period financial reports,
and Appy-style staff recruitment workflows with persistent UI modals and review panels.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.managers.top_manager import TopManager, CalculationResult, PriceItem
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
        modal = StaffApplicationModal(self.top_mgr, "General Staff Candidate")
        await interaction.response.send_modal(modal)


class StaffApplicationReviewView(discord.ui.View):
    """Interactive action buttons for staff review channel."""

    def __init__(self, top_mgr: TopManager, app_id: str, applicant_id: int):
        super().__init__(timeout=None)
        self.top_mgr = top_mgr
        self.app_id = app_id
        self.applicant_id = applicant_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅", custom_id="app_btn_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != 1505515188991033409:
            return await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)

        try:
            self.top_mgr.review_application(
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

        await interaction.response.send_message(
            f"✅ Application **{self.app_id}** marked as **ACCEPTED** by {interaction.user.mention}.{role_msg}",
            ephemeral=False,
        )

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌", custom_id="app_btn_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != 1505515188991033409:
            return await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)

        try:
            self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="REJECTED",
                reason=f"Declined by {interaction.user}",
            )
        except Exception as e:
            return await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        try:
            applicant = interaction.client.get_user(self.applicant_id)
            if applicant:
                dm_embed = discord.Embed(
                    title="Notice Regarding Your Staff Application",
                    description=(
                        f"Thank you for your interest in joining our staff team. After review, your application "
                        f"(`{self.app_id}`) was not approved at this time.\n\n"
                        f"You are welcome to reapply after the cooldown period has expired."
                    ),
                    color=KyokaTheme.ERROR,
                )
                await applicant.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message(
            f"🔴 Application **{self.app_id}** marked as **REJECTED** by {interaction.user.mention}.",
            ephemeral=False,
        )

    @discord.ui.button(label="Under Review", style=discord.ButtonStyle.secondary, emoji="🟡", custom_id="app_btn_review")
    async def under_review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.top_mgr.review_application(
                self.app_id,
                reviewer_id=interaction.user.id,
                reviewer_name=str(interaction.user),
                new_status="UNDER_REVIEW",
                reason="Review in progress",
            )
            await interaction.response.send_message(f"🟡 Application **{self.app_id}** status updated to **UNDER REVIEW**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @discord.ui.button(label="Interview Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="app_btn_interview")
    async def interview_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ Guild context required.", ephemeral=True)

        applicant = guild.get_member(self.applicant_id)
        if not applicant:
            return await interaction.response.send_message("❌ Applicant is no longer in this server.", ephemeral=True)

        # Create private interview channel
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


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAIN TOP AI MANAGER COG
# ─────────────────────────────────────────────────────────────────────────────

class TopAIManager(commands.Cog, name="TopAIManager"):
    """Official Blox Fruits Pricing Engine, Service Billing & Staff Applications."""

    category = "Bills"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.top_mgr = TopManager()
        # Register persistent application button view
        self.bot.add_view(StaffApplicationPanelView(self.top_mgr))

    def is_bot_staff(self, ctx: commands.Context) -> bool:
        """Verify author has authoritative staff or administrator privileges."""
        if ctx.author.id == 1505515188991033409:
            return True
        if ctx.guild and getattr(ctx.author, "guild_permissions", None) and ctx.author.guild_permissions.administrator:
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
            err_emb = discord.Embed(
                title="⚠️ Service Not Found",
                description=f"{ke}\n\n*Type `{p}top prices` to view the complete price catalogue or contact staff.*",
                color=KyokaTheme.WARNING,
            )
            return await ctx.reply(embed=err_emb, mention_author=False)
        except Exception as e:
            return await ctx.reply(f"❌ Could not interpret query: {e}", mention_author=False)

        calc: CalculationResult = parsed["calculation"]

        # If user intended to create a bill
        if parsed["intent"] == "make_bill":
            if not self.is_bot_staff(ctx):
                # Inform that only staff create official bills, but show the calculated pricing
                unauth_emb = discord.Embed(
                    title="⛩️ TOP AI MANAGER • PRICE CALCULATION",
                    description=(
                        f"**Note:** Official bills must be generated by authorized staff.\n"
                        f"Here is your exact calculated price:\n\n"
                        f"• **Service:** `{calc.service_name}`\n"
                        f"• **Quantity:** `{calc.quantity}`\n"
                        f"• **Unit Price:** `{calc.unit_display}`\n"
                        f"• **Subtotal:** `{calc.subtotal_display}`\n"
                        f"• **Tax:** `{calc.tax_rate}%` (`+{calc.tax_display}`)\n"
                        f"• **Final Total:** **{calc.total_display}**"
                    ),
                    color=KyokaTheme.PRIMARY,
                )
                if calc.condition_note:
                    unauth_emb.add_field(name="📌 Condition Note", value=f"> {calc.condition_note}", inline=False)
                return await ctx.reply(embed=unauth_emb, mention_author=False)

            # Staff creating bill via natural language
            bill = self.top_mgr.create_bill(
                guild_id=ctx.guild.id if ctx.guild else 0,
                creator_id=ctx.author.id,
                creator_name=str(ctx.author),
                service_name=calc.service_name,
                quantity=calc.quantity,
                tax_rate=calc.tax_rate,
                condition_notes=calc.condition_note,
            )

            bill_emb = discord.Embed(
                title=f"🧾 SERVICE BILL GENERATED • {bill['id']}",
                description=(
                    f"**Service:** `{bill['service_name']}`\n"
                    f"**Quantity:** `{bill['quantity']}`\n"
                    f"**Subtotal:** `{bill['subtotal_display']}`\n"
                    f"**Tax ({bill['tax_rate']}%):** `{bill['tax_display']}`\n"
                    f"**Amount Due:** **{bill['total_display']}**\n\n"
                    f"• **Status:** 🟡 **UNPAID**\n"
                    f"• **Staff Creator:** {ctx.author.mention}\n"
                    f"• **To Pay:** Send payment proof message ID: `{p}top paid {bill['id']} <message_id>`"
                ),
                color=KyokaTheme.PRIMARY,
                timestamp=discord.utils.utcnow(),
            )
            bill_emb.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
            bill_emb.set_footer(text=f"Bill ID: {bill['id']} • Kyoka Top AI Manager")
            return await ctx.reply(embed=bill_emb, mention_author=False)

        # Standard Price Inquiry Response
        embed = discord.Embed(
            title="⛩️ TOP AI MANAGER • PRICE INQUIRY",
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="🗡️ Service", value=f"`{calc.service_name}`", inline=True)
        embed.add_field(name="🔢 Quantity", value=f"`{calc.quantity}`", inline=True)
        embed.add_field(name="🏷️ Unit Price", value=f"`{calc.unit_display}`", inline=True)

        embed.add_field(name="💵 Subtotal", value=f"**{calc.subtotal_display}**", inline=True)
        if calc.tax_rate > 0:
            embed.add_field(name=f"🏛️ Tax ({calc.tax_rate}%)", value=f"`+{calc.tax_display}`", inline=True)
        embed.add_field(name="💰 Final Total", value=f"**{calc.total_display}**", inline=True)

        if calc.condition_note:
            embed.add_field(name="📌 Condition Note", value=f"> {calc.condition_note}", inline=False)

        if calc.ambiguity_note:
            embed.add_field(name="⚠️ Range Boundary Notice", value=f"> {calc.ambiguity_note}", inline=False)

        if calc.custom_quote:
            embed.add_field(name="💬 Custom Quote", value="> This service requires a custom quote. Please contact staff in a ticket.", inline=False)

        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Authoritative Official Price List")
        await ctx.reply(embed=embed, mention_author=False)

    # ── SUBCOMMAND: ?top bill ──────────────────────────────────────────────────
    @top_group.group(name="bill", invoke_without_command=True)
    async def bill_cmd(
        self,
        ctx: CustomContext,
        service: str,
        quantity: int = 1,
        tax: float = 0.0,
        customer: Optional[Union[discord.Member, discord.User]] = None,
    ):
        """Create a new service bill.
        
        Usage: +top bill <service> [quantity] [tax%] [@customer]
        Example: +top bill "2 trials" 1 5 @User
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply("❌ Staff permissions required to create official bills.", mention_author=False)

        try:
            bill = self.top_mgr.create_bill(
                guild_id=ctx.guild.id if ctx.guild else 0,
                creator_id=ctx.author.id,
                creator_name=str(ctx.author),
                service_name=service,
                quantity=quantity,
                tax_rate=tax,
                customer_id=customer.id if customer else None,
                customer_name=str(customer) if customer else "",
            )
        except Exception as e:
            return await ctx.reply(f"⚠️ **Error creating bill:** {e}", mention_author=False)

        p = ctx.prefix or Config.DEFAULT_PREFIX
        embed = discord.Embed(
            title=f"🧾 SERVICE BILL GENERATED • {bill['id']}",
            description=(
                f"**Customer:** {customer.mention if customer else 'Not specified'}\n"
                f"**Service:** `{bill['service_name']}`\n"
                f"**Quantity:** `{bill['quantity']}`\n"
                f"**Subtotal:** `{bill['subtotal_display']}`\n"
                f"**Tax ({bill['tax_rate']}%):** `{bill['tax_display']}`\n"
                f"**Total Amount Due:** **{bill['total_display']}**\n\n"
                f"• **Status:** 🟡 **UNPAID**\n"
                f"• **Creator:** {ctx.author.mention}\n"
                f"• **Mark as Paid:** `{p}top paid {bill['id']} <message_id>`"
            ),
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=AIZEN_THUMBNAIL_URL)
        embed.set_footer(text=f"Bill ID: {bill['id']} • Kyoka Top AI Manager")
        await ctx.reply(embed=embed, mention_author=False)

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

        # Workflow 1: +top paid <bill_id> <message_id>
        if arg2 is not None:
            bill_id = arg1
            message_id = arg2
        else:
            # Workflow 2: +top paid <message_id>
            # Check if arg1 is message_id (digits) or bill_id
            if arg1.isdigit():
                message_id = arg1
                # Find unpaid bills in this guild
                unpaid = self.top_mgr.list_bills(guild_id=ctx.guild.id if ctx.guild else None, status="UNPAID", limit=5)
                if not unpaid:
                    return await ctx.reply(
                        f"❌ No pending unpaid bills found in this server. Please provide the bill ID explicitly:\n"
                        f"> `{p}top paid <bill_id> {message_id}`",
                        mention_author=False,
                    )
                if len(unpaid) == 1:
                    bill_id = unpaid[0]["id"]
                else:
                    options = "\n".join([f"• `{b['id']}`: **{b['total_display']}** ({b['service_name']})" for b in unpaid])
                    return await ctx.reply(
                        f"⚠️ Multiple pending bills found. Please specify which bill this payment message belongs to:\n{options}\n\n"
                        f"Usage: `{p}top paid <bill_id> {message_id}`",
                        mention_author=False,
                    )
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

    # ── SUBCOMMAND: ?top prices ───────────────────────────────────────────────
    @top_group.group(name="prices", aliases=["price"], invoke_without_command=True)
    async def prices_cmd(self, ctx: CustomContext, category_or_query: Optional[str] = None):
        """View official price catalogue or search a category.
        
        Usage: +top prices [category]
        Categories: Trials, Normal Raids, Advance Raids, Order Raids, Races, Draco, Sea Events, Bosses, Fighting Styles, Swords, Guns, Beli Farming, Levels, Admin Panel, Titles, Accessories, Mastery, Gun Mastery
        """
        all_prices = self.top_mgr.get_all_prices()

        if category_or_query:
            query = category_or_query.lower().strip()
            filtered = [p for p in all_prices if query in p.category.lower() or query in p.service_name.lower()]
            if not filtered:
                return await ctx.reply(f"ℹ️ No services found matching **`{category_or_query}`**.", mention_author=False)
            
            lines = []
            for p in filtered[:20]:
                note = f" *({p.condition_note})*" if p.condition_note else ""
                lines.append(f"• **{p.service_name}:** `{p.price_display}`{note}")

            embed = discord.Embed(
                title=f"🏷️ OFFICIAL PRICES • {filtered[0].category.upper()}",
                description="\n".join(lines),
                color=KyokaTheme.PRIMARY,
            )
            embed.set_footer(text="Kyoka Top AI Manager • Authoritative Price Catalogue")
            return await ctx.reply(embed=embed, mention_author=False)

        # Group by categories
        cats = sorted(list({p.category for p in all_prices}))
        desc = "**Authoritative Blox Fruits Price Catalogue:**\n\n"
        for c in cats:
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
        await ctx.reply(embed=embed, mention_author=False)

    @prices_cmd.command(name="set")
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

    @prices_cmd.command(name="rename")
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

    @prices_cmd.command(name="custom")
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

    @prices_cmd.command(name="history")
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
    @commands.has_permissions(administrator=True)
    async def app_accept_cmd(self, ctx: CustomContext, app_id: str, *, reason: str = "Accepted by admin"):
        """Accept a staff application and notify the applicant.
        
        Usage: +top app accept <app_id> [reason]
        """
        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="ACCEPTED",
                reason=reason,
            )
            await ctx.reply(f"✅ Application **`{app_id.upper()}`** for <@{app['applicant_id']}> marked as **ACCEPTED**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

    @app_group.command(name="reject")
    @commands.has_permissions(administrator=True)
    async def app_reject_cmd(self, ctx: CustomContext, app_id: str, *, reason: str = "Not accepted at this time"):
        """Reject a staff application and notify the applicant.
        
        Usage: +top app reject <app_id> [reason]
        """
        try:
            app = self.top_mgr.review_application(
                app_id,
                reviewer_id=ctx.author.id,
                reviewer_name=str(ctx.author),
                new_status="REJECTED",
                reason=reason,
            )
            await ctx.reply(f"🔴 Application **`{app_id.upper()}`** for <@{app['applicant_id']}> marked as **REJECTED**.", mention_author=False)
        except Exception as e:
            await ctx.reply(f"⚠️ {e}", mention_author=False)

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TopAIManager(bot))
