"""
Kyoka Discord Bot - Advanced Ticket System & Interactive Slide Dashboard
Seamlessly integrates with Embed Builder for custom visual panels and manages private ticket channels,
roles, permission overrides, live claiming, and HTML transcript logging.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any

import discord
from discord.ext import commands

from src.core.bot import KyokaBot
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response, build_container_payload
from src.utils.transcript import generate_html_transcript
from src.cogs.utility.embed_builder import ContainerDraft

logger = logging.getLogger("Kyoka.Cogs.Ticket")


# ─── INSIDE-TICKET CONTROLS VIEW ──────────────────────────────────────────────

class TicketCloseConfirmModal(discord.ui.Modal, title="Close Ticket"):
    reason_input = discord.ui.TextInput(
        label="Closing Reason (Optional)",
        placeholder="e.g. Issue resolved, inactive, answered",
        required=False,
        max_length=250,
    )

    def __init__(self, cog: TicketSystem, ticket_data: dict[str, Any]) -> None:
        super().__init__()
        self.cog = cog
        self.ticket_data = ticket_data

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = str(self.reason_input.value).strip() or "No reason provided."
        await self.cog.execute_ticket_close(interaction, self.ticket_data, reason=reason)


class TicketInsideControlsView(discord.ui.View):
    """Persistent controls attached inside the private ticket channel."""

    def __init__(self, cog: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        e_reg = getattr(cog.bot, "custom_emojis", None)
        if e_reg and hasattr(e_reg, "get_emoji_obj"):
            lock_em = e_reg.get_emoji_obj("icons_locked") or e_reg.get_emoji_obj("icon_lock")
            if isinstance(lock_em, (str, discord.Emoji, discord.PartialEmoji)):
                self.btn_close.emoji = lock_em

            staff_em = e_reg.get_emoji_obj("icons_staff") or e_reg.get_emoji_obj("icon_mod")
            if isinstance(staff_em, (str, discord.Emoji, discord.PartialEmoji)):
                self.btn_claim.emoji = staff_em

            file_em = e_reg.get_emoji_obj("icons_file") or e_reg.get_emoji_obj("icons_files")
            if isinstance(file_em, (str, discord.Emoji, discord.PartialEmoji)):
                self.btn_transcript.emoji = file_em

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_ctrl_close",
        row=0,
    )
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            container = KyokaContainer()
            container.add_section(content="**Ticket Error**\n> This channel is not registered as an active ticket.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0)) if ticket else None
        is_creator = bool(ticket and interaction.user.id == ticket.get("user_id"))
        is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
        if panel and panel.get("support_role_id"):
            s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
            if s_role and s_role in getattr(interaction.user, "roles", []):
                is_staff = True

        if not (is_creator or is_staff):
            container = KyokaContainer()
            container.add_section(content="**Permission Denied**\n> Only the ticket creator or authorized staff can close this ticket.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        # Open close confirmation modal
        await interaction.response.send_modal(TicketCloseConfirmModal(self.cog, ticket))

    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_ctrl_claim",
        row=0,
    )
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            container = KyokaContainer()
            container.add_section(content="**Ticket Error**\n> This channel is not registered as an active ticket.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        # Check if staff permissions or panel support role
        panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0))
        is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
        if panel and panel.get("support_role_id"):
            s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
            if s_role and s_role in getattr(interaction.user, "roles", []):
                is_staff = True

        if not is_staff:
            container = KyokaContainer()
            container.add_section(content="**Permission Denied**\n> Only staff members can claim tickets.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        claimed_by = ticket.get("claimed_by")
        if claimed_by and claimed_by == interaction.user.id:
            container = KyokaContainer()
            container.add_section(content="**Ticket Notice**\n> You have already claimed this ticket.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        await self.cog.bot.ticket_mgr.claim_ticket(interaction.channel_id, interaction.user.id)
        claim_card = KyokaContainer()
        claim_card.add_section(
            content=f"**Ticket Claimed**\n> This ticket has been claimed by {interaction.user.mention}."
        )
        await send_container_response(interaction, claim_card)

    @discord.ui.button(
        label="Save Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_ctrl_transcript",
        row=0,
    )
    async def btn_transcript(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            container = KyokaContainer()
            container.add_section(content="**Transcript Error**\n> Transcripts are only supported in text channels.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0)) if ticket else None
        is_creator = bool(ticket and interaction.user.id == ticket.get("user_id"))
        is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
        if panel and panel.get("support_role_id"):
            s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
            if s_role and s_role in getattr(interaction.user, "roles", []):
                is_staff = True

        if not (is_creator or is_staff):
            container = KyokaContainer()
            container.add_section(content="**Permission Denied**\n> Only the ticket creator or authorized staff can download transcripts.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        file = await generate_html_transcript(interaction.channel, ticket, bot=self.cog.bot)
        t_card = KyokaContainer()
        t_card.add_section(content="**Ticket Transcript**\n> Here is the live HTML transcript for this ticket:")
        await send_container_response(
            interaction,
            t_card,
            file=file,
            ephemeral=True,
        )


class TicketClosedControlsView(discord.ui.View):
    """
    Persistent Ticket King-style closed ticket controls.
    Offers staff and users Reopen, Transcript, and Permanent Delete actions.
    """

    def __init__(self, cog: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Reopen Ticket",
        style=discord.ButtonStyle.success,
        custom_id="ticket_ctrl_reopen",
        emoji="🔓",
        row=0,
    )
    async def btn_reopen(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            ticket = await self.cog.bot.db.fetch_one("SELECT * FROM active_tickets WHERE channel_id = $1;", interaction.channel_id)
        if ticket:
            panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0)) if ticket else None
            is_creator = bool(ticket and interaction.user.id == ticket.get("user_id"))
            is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
            if panel and panel.get("support_role_id"):
                s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
                if s_role and s_role in getattr(interaction.user, "roles", []):
                    is_staff = True
            if not (is_creator or is_staff):
                return await interaction.response.send_message("Only the ticket creator or authorized staff can reopen this ticket.", ephemeral=True)
        await self.cog.execute_ticket_reopen(interaction)

    @discord.ui.button(
        label="Transcript",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_ctrl_closed_transcript",
        emoji="📄",
        row=0,
    )
    async def btn_transcript(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            ticket = await self.cog.bot.db.fetch_one("SELECT * FROM active_tickets WHERE channel_id = $1;", interaction.channel_id)
        if ticket:
            panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0)) if ticket else None
            is_creator = bool(ticket and interaction.user.id == ticket.get("user_id"))
            is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
            if panel and panel.get("support_role_id"):
                s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
                if s_role and s_role in getattr(interaction.user, "roles", []):
                    is_staff = True
            if not (is_creator or is_staff):
                return await interaction.response.send_message("Only the ticket creator or authorized staff can view this transcript.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        file = await generate_html_transcript(interaction.channel, ticket, bot=self.cog.bot)
        t_card = KyokaContainer()
        t_card.add_section(content="**Ticket Transcript**\n> Here is the saved HTML transcript for this ticket:")
        await send_container_response(interaction, t_card, file=file, ephemeral=True)

    @discord.ui.button(
        label="Delete Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_ctrl_delete",
        emoji="🗑️",
        row=0,
    )
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not (interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("Only staff members with Manage Channels can delete tickets.", ephemeral=True)
        del_card = KyokaContainer(accent_color=15548997)
        del_card.add_section(content="**Deleting Ticket**\n> This ticket channel will be permanently deleted in 5 seconds...")
        await send_container_response(interaction, del_card)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception as e:
            logger.debug(f"Notice deleting channel: {e}")



# ─── SLIDE-BASED TICKET DASHBOARD SETUP WIZARD ───────────────────────────────

class TicketSetupWizard(discord.ui.View):
    """
    Slide-Based Wizard for ?ticket setup:
    Slide 1: Embed Select Template + Continue >
    Slide 2: Support Role & Target Category + < Back + Continue >
    Slide 3: Log Channel & Naming Format + < Back + Continue >
    Slide 4: Target Channel & Deploy Panel Action
    """

    SLIDES = [
        ("embed", "Step 1: Select Embed Template", "Choose a saved embed from the Embed Builder to use as the visual card for your ticket panel."),
        ("roles", "Step 2: Support Role & Category", "Select the support role allowed to manage tickets and the category where private channels are created."),
        ("logs", "Step 3: Logs & Settings", "Configure where transcripts and audit logs are sent, and set your ticket naming convention."),
        ("deploy", "Step 4: Target Channel & Deploy", "Choose which text channel to post this ticket panel to and deploy it live."),
    ]

    def __init__(
        self,
        cog: TicketSystem,
        author: discord.User | discord.Member,
        templates: list[dict[str, Any]] | None = None,
        initial_embed: str | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.bot = cog.bot
        self.author = author
        self.templates: list[dict[str, Any]] = templates or []
        self.current_slide_idx: int = 0

        # Wizard State
        self.selected_embed: str | None = initial_embed
        self.selected_role_id: int | None = None
        self.selected_category_id: int | None = None
        self.selected_log_channel_id: int | None = None
        self.selected_target_channel_id: int | None = None
        self.naming_format: str = "ticket-{count}"
        self.button_label: str = "Create Ticket"

        self._build_components_for_slide()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            container = KyokaContainer()
            container.add_section(
                content=f"**Access Denied**\n> Only {self.author.mention} can control this setup wizard session."
            )
            await send_container_response(interaction, container, ephemeral=True)
            return False
        return True

    def _build_components_for_slide(self) -> None:
        """Rebuild view items dynamically according to current slide index."""
        self.clear_items()
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "embed":
            # Slide 1: Embed Select Menu
            options = []
            if self.templates:
                for t in self.templates[:25]:
                    name = t.get("embed_name", "unknown")
                    options.append(discord.SelectOption(
                        label=name,
                        value=name,
                        description=f"Use '{name}' as the ticket panel embed"[:100],
                        default=(self.selected_embed == name),
                    ))
            if not options:
                options.append(discord.SelectOption(
                    label="Default Support Embed",
                    value="__default__",
                    description="Standard clean ticket support embed card",
                    default=True,
                ))
                if not self.selected_embed:
                    self.selected_embed = "__default__"

            select = discord.ui.Select(
                placeholder="Select an embed template...",
                options=options,
                custom_id="wiz_select_embed",
                row=0,
            )
            select.callback = self._on_embed_selected
            self.add_item(select)

            # Back button (disabled on Slide 1 for consistent layout)
            btn_back_disabled = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back_dis",
                disabled=True,
                row=1,
            )
            self.add_item(btn_back_disabled)

            # Continue button on right
            btn_continue = discord.ui.Button(
                label="Continue",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_continue",
                disabled=(self.selected_embed is None),
                row=1,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "roles":
            # Slide 2: Role Select & Category Select
            role_select = discord.ui.RoleSelect(
                placeholder="Select a Support Staff Role (Optional)...",
                custom_id="wiz_select_role",
                min_values=0,
                max_values=1,
                row=0,
            )
            role_select.callback = self._on_role_selected
            self.add_item(role_select)

            cat_select = discord.ui.ChannelSelect(
                placeholder="Select a Category for Ticket Channels (Optional)...",
                channel_types=[discord.ChannelType.category],
                custom_id="wiz_select_cat",
                min_values=0,
                max_values=1,
                row=1,
            )
            cat_select.callback = self._on_category_selected
            self.add_item(cat_select)

            btn_back = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=2,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = discord.ui.Button(
                label="Continue",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_continue",
                row=2,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "logs":
            # Slide 3: Log Channel Select
            log_select = discord.ui.ChannelSelect(
                placeholder="Select a Log Channel for Transcripts (Optional)...",
                channel_types=[discord.ChannelType.text],
                custom_id="wiz_select_log",
                min_values=0,
                max_values=1,
                row=0,
            )
            log_select.callback = self._on_log_channel_selected
            self.add_item(log_select)

            # Naming style toggle
            btn_name = discord.ui.Button(
                label=f"Naming: {self.naming_format}",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_naming",
                row=1,
            )
            btn_name.callback = self._on_toggle_naming
            self.add_item(btn_name)

            btn_back = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=2,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = discord.ui.Button(
                label="Continue",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_continue",
                row=2,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "deploy":
            # Slide 4: Target Channel & Deploy Action
            target_select = discord.ui.ChannelSelect(
                placeholder="Select Target Channel to post panel...",
                channel_types=[discord.ChannelType.text],
                custom_id="wiz_select_target",
                min_values=1,
                max_values=1,
                row=0,
            )
            target_select.callback = self._on_target_selected
            self.add_item(target_select)

            btn_back = discord.ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=1,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_deploy = discord.ui.Button(
                label="Deploy Panel",
                style=discord.ButtonStyle.success,
                custom_id="wiz_btn_deploy",
                disabled=(self.selected_target_channel_id is None),
                row=1,
            )
            btn_deploy.callback = self._on_deploy_clicked
            self.add_item(btn_deploy)

    def get_dashboard_container(self, guild: discord.Guild | None) -> KyokaContainer:
        """Render the single sleek Components V2 Ticket Dashboard Container."""
        container = KyokaContainer(accent_color=None)
        slide_key, slide_title, slide_desc = self.SLIDES[self.current_slide_idx]
        arrow = self.bot.custom_emojis.get("icons_rightarrow", self.bot.custom_emojis.get("icons_arrow", "›"))

        container.add_section(
            content=(
                "**Ticket Dashboard**\n"
                f"> **{slide_title}**\n"
                f"> {slide_desc}"
            )
        )
        container.add_separator(divider=True)

        e_disp = f"`{self.selected_embed}`" if self.selected_embed and self.selected_embed != "__default__" else "`Default Template`"
        r_disp = f"<@&{self.selected_role_id}>" if self.selected_role_id else "`Administrators (Default)`"
        c_disp = f"<#{self.selected_category_id}>" if self.selected_category_id else "`Auto-Create 'Tickets'`"
        l_disp = f"<#{self.selected_log_channel_id}>" if self.selected_log_channel_id else "`None (Direct DM)`"
        t_disp = f"<#{self.selected_target_channel_id}>" if self.selected_target_channel_id else "`Not Selected`"

        container.add_text(
            f"{arrow} **Selected Embed:** {e_disp}\n"
            f"{arrow} **Support Role:** {r_disp}\n"
            f"{arrow} **Target Category:** {c_disp}\n"
            f"{arrow} **Log Channel:** {l_disp}\n"
            f"{arrow} **Naming Format:** `{self.naming_format}`\n"
            f"{arrow} **Deploy Target:** {t_disp}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Step {self.current_slide_idx + 1}/4 • Setup Session for {self.author.display_name}")

        return container

    async def _on_embed_selected(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = interaction.data.get("values", [])  # type: ignore
        if select:
            self.selected_embed = select[0]
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_role_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        self.selected_role_id = int(values[0]) if values else None
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_category_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        self.selected_category_id = int(values[0]) if values else None
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_log_channel_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        self.selected_log_channel_id = int(values[0]) if values else None
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_target_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        self.selected_target_channel_id = int(values[0]) if values else None
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_toggle_naming(self, interaction: discord.Interaction) -> None:
        if self.naming_format == "ticket-{count}":
            self.naming_format = "support-{user}"
        elif self.naming_format == "support-{user}":
            self.naming_format = "ticket-{user}"
        else:
            self.naming_format = "ticket-{count}"
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_continue_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx < len(self.SLIDES) - 1:
            self.current_slide_idx += 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_back_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_deploy_clicked(self, interaction: discord.Interaction) -> None:
        if not self.selected_target_channel_id or not interaction.guild:
            container = KyokaContainer()
            container.add_section(content="**Deployment Error**\n> Please select a target channel to deploy.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        target_channel = interaction.guild.get_channel(self.selected_target_channel_id)
        if not isinstance(target_channel, discord.TextChannel):
            container = KyokaContainer()
            container.add_section(content="**Channel Error**\n> Invalid target text channel.")
            await send_container_response(interaction, container, ephemeral=True)
            return

        await interaction.response.defer()

        panel_name = self.selected_embed or "support"
        if panel_name == "__default__":
            panel_name = "support"

        # Generate panel container from template or clean default
        draft = ContainerDraft()
        if self.selected_embed and self.selected_embed != "__default__":
            tmpl = await self.bot.embed_mgr.get_template(interaction.guild.id, self.selected_embed)
            if tmpl:
                draft = ContainerDraft.from_dict(tmpl)
        else:
            draft.title = "🎫 Kyoka Support Portal"
            draft.description = (
                "**Need assistance?**\n"
                "> Select an inquiry category below or click **Create Ticket** to open a private channel with our staff team.\n"
                "> An authorized staff member will assist you shortly."
            )
            draft.accent_hex = "7C3AED"  # Aizen Royal Violet

        panel_container = draft.to_container(
            user=interaction.user,
            guild=interaction.guild,
            channel=target_channel,
            bot=self.bot,
        )

        # Create database panel entry to get panel_id
        temp_row = await self.bot.ticket_mgr.create_panel(
            guild_id=interaction.guild.id,
            panel_name=panel_name,
            embed_name=self.selected_embed or "support",
            channel_id=target_channel.id,
            message_id=0,
            category_id=self.selected_category_id,
            support_role_id=self.selected_role_id,
            log_channel_id=self.selected_log_channel_id,
            naming_format=self.naming_format,
            button_label=self.button_label,
            created_by=interaction.user.id,
        )
        panel_id = temp_row.get("id", 1)

        # Attach interactive category select dropdown
        custom_cats = await self.bot.ticket_mgr.list_categories(interaction.guild.id, panel_name=panel_name)
        cat_options = [
            {
                "label": cat["name"][:100],
                "value": cat["name"][:100],
                "description": (cat.get("description") or f"{cat['name']} inquiries")[:100],
                "emoji": {"name": cat.get("emoji", "🎫")},
            }
            for cat in custom_cats[:25]
        ]

        select_action_row: dict[str, Any] = {
            "type": 1,
            "components": [
                {
                    "type": 3,
                    "custom_id": f"ticket_select_{panel_id}",
                    "placeholder": "Select an inquiry or service category...",
                    "min_values": 1,
                    "max_values": 1,
                    "options": cat_options,
                }
            ],
        }

        # Attach interactive persistent button inside panel container
        ticket_emoji = (
            self.bot.custom_emojis.get_select_emoji("ticket_nox")
            or self.bot.custom_emojis.get_select_emoji("ticket_support")
            or self.bot.custom_emojis.get_select_emoji("icon_ticket")
        )
        btn_action_row: dict[str, Any] = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary Blurple/Violet
                    "label": self.button_label or "Create Ticket",
                    "custom_id": f"ticket_open_{panel_id}",
                }
            ],
        }
        if ticket_emoji:
            btn_action_row["components"][0]["emoji"] = ticket_emoji

        panel_container.components.append(select_action_row)
        panel_container.components.append(btn_action_row)

        msg_data = await send_container_response(target_channel, panel_container)
        msg_id = 0
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)

        # Update message_id in database
        if msg_id:
            await self.bot.ticket_mgr.create_panel(
                guild_id=interaction.guild.id,
                panel_name=panel_name,
                embed_name=self.selected_embed or "support",
                channel_id=target_channel.id,
                message_id=msg_id,
                category_id=self.selected_category_id,
                support_role_id=self.selected_role_id,
                log_channel_id=self.selected_log_channel_id,
                naming_format=self.naming_format,
                button_label=self.button_label,
                created_by=interaction.user.id,
            )

        # Success confirmation on dashboard
        arrow = self.bot.custom_emojis.get("icons_rightarrow", self.bot.custom_emojis.get("icons_arrow", "›"))
        conf_container = KyokaContainer(accent_color=5763719)  # Green
        conf_container.add_section(
            content=(
                "**Ticket Panel Deployed Successfully**\n"
                f"> Panel **{panel_name}** is now live in {target_channel.mention}.\n\n"
                f"{arrow} **Category:** {f'<#{self.selected_category_id}>' if self.selected_category_id else '`Auto-Create`'}\n"
                f"{arrow} **Support Role:** {f'<@&{self.selected_role_id}>' if self.selected_role_id else '`Administrators`'}\n"
                f"{arrow} **Logs Channel:** {f'<#{self.selected_log_channel_id}>' if self.selected_log_channel_id else '`None`'}"
            )
        )
        conf_container.add_separator(divider=True)
        conf_container.add_text(f"-# Configured by {interaction.user.display_name}")

        self.clear_items()
        await edit_container_response(interaction, conf_container, view=self)


# ─── MAIN TICKET SYSTEM COG ───────────────────────────────────────────────────

class TicketSystem(commands.Cog):
    """Enterprise Ticket System with Components V2 container panels and slide setup wizard."""
    category: str = "Ticket"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        # Concurrency protection tracking in-flight ticket creations per (guild_id, user_id)
        self._creating_tickets: set[tuple[int, int]] = set()
        # Register persistent inside-ticket views (active and closed controls)
        self.bot.add_view(TicketInsideControlsView(self))
        self.bot.add_view(TicketClosedControlsView(self))

    # ─── PERSISTENT BUTTON INTERACTION LISTENER ───────────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle ticket panel create button and category select clicks globally across all guilds."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not (custom_id.startswith("ticket_open_") or custom_id.startswith("ticket_select_")):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        # Concurrency & rapid repeated clicks protection
        lock_key = (interaction.guild.id, interaction.user.id)
        if lock_key in self._creating_tickets:
            container = KyokaContainer()
            container.add_section(
                content="**Ticket Creation In Progress**\n> Your support ticket is currently being created. Please wait a moment."
            )
            await send_container_response(interaction, container, ephemeral=True)
            return

        self._creating_tickets.add(lock_key)
        try:
            chosen_category = "General Support"
            if custom_id.startswith("ticket_select_"):
                raw_id = custom_id.replace("ticket_select_", "")
                if interaction.data.get("values"):
                    chosen_category = str(interaction.data["values"][0])
            else:
                raw_id = custom_id.replace("ticket_open_", "")
                if "_" in raw_id:
                    parts = raw_id.split("_", 1)
                    raw_id = parts[0]
                    chosen_category = parts[1].replace("-", " ").title()

            try:
                panel_id = int(raw_id)
            except ValueError:
                return

            panel = await self.bot.ticket_mgr.get_panel_by_id(panel_id)
            if not panel:
                container = KyokaContainer()
                container.add_section(content="**Configuration Error**\n> This ticket panel configuration was not found.")
                await send_container_response(interaction, container, ephemeral=True)
                return

            # Check configurable per-user ticket limit (0 = Unlimited simultaneous tickets by default)
            max_tickets = int(panel.get("max_tickets_per_user") or 0)
            if max_tickets > 0:
                active_count = await self.bot.ticket_mgr.get_active_tickets_count_for_user(
                    interaction.guild.id, interaction.user.id, panel_id=panel_id
                )
                if active_count >= max_tickets:
                    container = KyokaContainer()
                    container.add_section(
                        content=f"**Ticket Limit Reached**\n> You have reached the maximum limit of **{max_tickets}** open ticket(s) configured for this panel."
                    )
                    await send_container_response(interaction, container, ephemeral=True)
                    return

            await interaction.response.defer(ephemeral=True)

            # Increment sequential ticket number
            ticket_num = await self.bot.ticket_mgr.get_next_ticket_number(interaction.guild.id)
            ticket_str = f"{ticket_num:04d}"

            # Resolve channel name
            naming = panel.get("naming_format", "ticket-{count}")
            raw_user_name = str(getattr(interaction.user, "name", "user"))
            clean_user = re.sub(r"[^a-zA-Z0-9_-]", "", raw_user_name.lower()) or "user"
            channel_name = naming.replace("{count}", ticket_str).replace("{user}", clean_user)

            # Check for custom category definition overrides
            custom_cat_info: dict[str, Any] | None = None
            try:
                guild_cats = await self.bot.ticket_mgr.list_categories(interaction.guild.id, panel.get("panel_name", ""))
                for gc in guild_cats:
                    if gc.get("name", "").strip().lower() == chosen_category.strip().lower():
                        custom_cat_info = gc
                        break
            except Exception as e:
                logger.debug(f"Error fetching custom category info: {e}")

            # Resolve or auto-create target category
            cat_id = (custom_cat_info.get("category_channel_id") if custom_cat_info and custom_cat_info.get("category_channel_id") else None) or panel.get("category_id")
            category: discord.CategoryChannel | None = None
            if cat_id:
                cat_obj = interaction.guild.get_channel(cat_id)
                if isinstance(cat_obj, discord.CategoryChannel):
                    category = cat_obj

            if not category:
                category = discord.utils.get(interaction.guild.categories, name="Tickets")
                if not category:
                    try:
                        category = await interaction.guild.create_category(
                            name="Tickets",
                            reason="Kyoka Support Tickets Category",
                        )
                    except Exception as cat_err:
                        logger.warning(f"Could not auto-create Tickets category (fallback to root): {cat_err}")
                        category = None

            # Safely resolve bot member
            bot_member = interaction.guild.me
            if not bot_member and self.bot.user:
                bot_member = interaction.guild.get_member(self.bot.user.id)

            # Construct permission overrides
            overrides: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                ),
            }

            if bot_member:
                overrides[bot_member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                )

            support_role_id = panel.get("support_role_id")
            if support_role_id:
                s_role = interaction.guild.get_role(support_role_id)
                if s_role:
                    overrides[s_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True,
                    )

            # Apply category-specific staff role if configured
            if custom_cat_info and custom_cat_info.get("staff_role_id"):
                cat_staff_role = interaction.guild.get_role(custom_cat_info["staff_role_id"])
                if cat_staff_role:
                    overrides[cat_staff_role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True,
                    )

            # Atomic creation with rollback guarantee on database or initialization failure
            ticket_channel: discord.TextChannel | None = None
            try:
                try:
                    ticket_channel = await interaction.guild.create_text_channel(
                        name=channel_name,
                        category=category,
                        overwrites=overrides,
                        topic=f"Ticket #{ticket_str} | Category: {chosen_category} | Creator: {interaction.user} (ID: {interaction.user.id})",
                        reason=f"Ticket created by {interaction.user}",
                    )
                except Exception as cat_create_err:
                    logger.warning(f"Category creation fallback to root: {cat_create_err}")
                    ticket_channel = await interaction.guild.create_text_channel(
                        name=channel_name,
                        overwrites=overrides,
                        topic=f"Ticket #{ticket_str} | Category: {chosen_category} | Creator: {interaction.user} (ID: {interaction.user.id})",
                        reason=f"Ticket created by {interaction.user}",
                    )

                # Record ticket in database atomically
                await self.bot.ticket_mgr.create_ticket(
                    guild_id=interaction.guild.id,
                    panel_id=panel_id,
                    channel_id=ticket_channel.id,
                    user_id=interaction.user.id,
                    ticket_number=ticket_num,
                    category=chosen_category,
                )
            except Exception as atomic_err:
                logger.error(f"Atomic ticket creation failure: {atomic_err}", exc_info=atomic_err)
                if ticket_channel:
                    try:
                        await ticket_channel.delete(reason="Ticket creation rollback due to DB/setup failure")
                    except Exception:
                        pass
                err_card = KyokaContainer()
                err_card.add_section(
                    content=f"**Creation Failed**\n> Failed to initialize ticket channel: `{atomic_err}`.\n> Ensure the bot has **Manage Channels** and **Manage Roles** permissions."
                )
                await send_container_response(interaction, err_card, ephemeral=True)
                return

            # Send welcome card in ticket channel
            arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")
            welcome_msg_text = (
                custom_cat_info.get("welcome_message")
                if (custom_cat_info and custom_cat_info.get("welcome_message"))
                else (
                    f"**Ticket #{ticket_str} • {interaction.user.display_name}**\n"
                    f"> Welcome to your private support ticket, {interaction.user.mention}.\n"
                    f"> Please describe your inquiry in detail. Our staff team will assist you shortly."
                )
            )
            welcome_container = KyokaContainer(accent_color=None)
            welcome_container.add_section(content=welcome_msg_text)
            welcome_container.add_separator(divider=True)
            welcome_container.add_text(
                f"{arrow} **Ticket ID:** `#{ticket_str}`\n"
                f"{arrow} **Category:** `{chosen_category}`\n"
                f"{arrow} **Panel:** `{panel.get('panel_name', 'Support')}`\n"
                f"{arrow} **Status:** `Open` • **Claimed:** *Unclaimed*"
            )
            welcome_container.add_separator(divider=True)
            welcome_container.add_text("-# Use the buttons below to manage this ticket.")

            await send_container_response(
                ticket_channel,
                welcome_container,
                view=TicketInsideControlsView(self),
                content=f"{interaction.user.mention} {f'<@&{support_role_id}>' if support_role_id else ''}",
            )

            # Log ticket creation in log channel if configured
            log_channel_id = panel.get("log_channel_id")
            if log_channel_id:
                log_ch = interaction.guild.get_channel(log_channel_id)
                if isinstance(log_ch, discord.TextChannel):
                    try:
                        log_c = KyokaContainer(accent_color=5763719)  # Green
                        log_c.add_section(
                            content=(
                                f"**Ticket Opened • #{ticket_str}**\n"
                                f"> User: {interaction.user.mention} `「{interaction.user.id}」`\n"
                                f"> Category: `{chosen_category}`\n"
                                f"> Channel: {ticket_channel.mention}\n"
                                f"> Panel: `{panel.get('panel_name')}`"
                            )
                        )
                        await send_container_response(log_ch, log_c)
                    except Exception as log_err:
                        logger.warning(f"Could not dispatch ticket log: {log_err}")

            # Ephemeral confirmation to user
            created_card = KyokaContainer()
            created_card.add_section(
                content=f"**Ticket Created**\n> Your support ticket is ready: {ticket_channel.mention}"
            )
            await send_container_response(
                interaction,
                created_card,
                ephemeral=True,
            )
        finally:
            self._creating_tickets.discard(lock_key)

    # ─── TICKET CLOSE EXECUTION ───────────────────────────────────────────────

    async def execute_ticket_close(
        self,
        interaction_or_ctx: discord.Interaction | CustomContext,
        ticket_data: dict[str, Any],
        reason: str = "Issue resolved",
    ) -> None:
        """Generate transcript, notify logs/user, and safely close the ticket channel."""
        guild = interaction_or_ctx.guild
        channel = interaction_or_ctx.channel
        closer = interaction_or_ctx.user if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author

        if not guild or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        panel = await self.bot.ticket_mgr.get_panel_by_id(ticket_data.get("panel_id", 0))
        permissions = getattr(closer, "guild_permissions", None)
        is_staff = bool(
            permissions
            and (
                permissions.administrator
                or permissions.manage_channels
                or permissions.manage_messages
            )
        )
        support_role_id = panel.get("support_role_id") if panel else None
        support_role = guild.get_role(support_role_id) if support_role_id else None
        if support_role and support_role in getattr(closer, "roles", []):
            is_staff = True
        is_creator = closer.id == ticket_data.get("user_id")
        if not (is_creator or is_staff):
            denied = KyokaContainer()
            denied.add_section(
                content="**Permission Denied**\n> Only the ticket creator or configured support staff can close this ticket."
            )
            if isinstance(interaction_or_ctx, discord.Interaction):
                await send_container_response(interaction_or_ctx, denied, ephemeral=True)
            else:
                await interaction_or_ctx.send_warning(
                    "Only the ticket creator or configured support staff can close this ticket."
                )
            return

        closing_card = KyokaContainer(accent_color=15548997)
        closing_card.add_section(
            content="**Closing Ticket**\n> Generating transcript, channel will be deleted in 5 seconds..."
        )
        await send_container_response(interaction_or_ctx, closing_card)

        ticket_num = ticket_data.get("ticket_number", channel.id)
        # Generate HTML transcript
        transcript_file = await generate_html_transcript(channel, ticket_data, bot=self.bot)

        # Send transcript to ticket owner DM
        user_id = ticket_data.get("user_id")
        if user_id:
            try:
                user = guild.get_member(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    t_num_int = int(ticket_num) if str(ticket_num).isdigit() else 1
                    dm_container = KyokaContainer(accent_color=15548997)  # Red
                    dm_container.add_section(
                        content=(
                            f"**Ticket #{t_num_int:04d} Closed**\n"
                            f"> Server: **{guild.name}**\n"
                            f"> Closed By: **{closer.display_name}**\n"
                            f"> Reason: `{reason}`"
                        )
                    )
                    await send_container_response(user, dm_container, file=transcript_file)
            except Exception as dm_e:
                logger.debug(f"Could not DM user close transcript: {dm_e}")

        # Send transcript to log channel if configured
        log_channel_id = panel.get("log_channel_id") if panel else None
        if log_channel_id:
            log_ch = guild.get_channel(log_channel_id)
            if isinstance(log_ch, discord.TextChannel):
                try:
                    # Re-generate transcript stream for log channel
                    t_file_2 = await generate_html_transcript(channel, ticket_data, bot=self.bot)
                    t_num_int = int(ticket_num) if str(ticket_num).isdigit() else 1
                    log_c = KyokaContainer(accent_color=15548997)  # Red
                    log_c.add_section(
                        content=(
                            f"**Ticket Closed • #{t_num_int:04d}**\n"
                            f"> Channel: `#{channel.name}`\n"
                            f"> Creator: <@{user_id}> `「{user_id}」`\n"
                            f"> Closed By: {closer.mention} `「{closer.id}」`\n"
                            f"> Reason: `{reason}`"
                        )
                    )
                    await send_container_response(log_ch, log_c, file=t_file_2)
                except Exception as log_err:
                    logger.warning(f"Could not send close log: {log_err}")

        # Update database record
        await self.bot.ticket_mgr.close_ticket(channel.id, closer.id)

        # Lock channel permissions so creator cannot send messages anymore
        if user_id:
            creator_member = guild.get_member(user_id)
            if creator_member:
                try:
                    await channel.set_permissions(
                        creator_member,
                        view_channel=True,
                        send_messages=False,
                        reason=f"Ticket closed by {closer}",
                    )
                except Exception as perm_err:
                    logger.debug(f"Could not lock permissions for creator: {perm_err}")

        # Display Ticket King-style closed control panel with Reopen, Transcript, and Delete buttons
        t_num_int = int(ticket_num) if str(ticket_num).isdigit() else 1
        closed_card = KyokaContainer(accent_color=15548997)  # Red
        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")
        closed_card.add_section(
            content=(
                f"**Ticket #{t_num_int:04d} Closed**\n"
                f"> Closed by {closer.mention} (`{reason}`).\n"
                f"> Staff can manage this ticket with the controls below or permanently delete it."
            )
        )
        closed_card.add_separator(divider=True)
        closed_card.add_text(
            f"{arrow} **Transcript:** Dispatched to creator DM and log channel.\n"
            f"{arrow} **Controls:** Click **Reopen** to reactivate or **Delete** to permanently purge."
        )
        await send_container_response(channel, closed_card, view=TicketClosedControlsView(self))

    async def execute_ticket_reopen(
        self,
        interaction_or_ctx: discord.Interaction | CustomContext,
    ) -> None:
        """Reopen a closed ticket channel and restore messaging permissions."""
        guild = interaction_or_ctx.guild
        channel = interaction_or_ctx.channel
        reopener = interaction_or_ctx.user if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author

        if not guild or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        ticket = await self.bot.ticket_mgr.get_ticket(channel.id)
        if not ticket:
            ticket = await self.bot.db.fetch_one("SELECT * FROM active_tickets WHERE channel_id = $1;", channel.id)

        if not ticket:
            err_card = KyokaContainer()
            err_card.add_section(content="**Ticket Error**\n> This channel is not a recognized ticket channel.")
            if isinstance(interaction_or_ctx, discord.Interaction):
                await send_container_response(interaction_or_ctx, err_card, ephemeral=True)
            else:
                await interaction_or_ctx.send_error("This channel is not a recognized ticket channel.")
            return

        if ticket.get("status") == "open":
            err_card = KyokaContainer()
            err_card.add_section(content="**Already Open**\n> This ticket is already active and open.")
            if isinstance(interaction_or_ctx, discord.Interaction):
                await send_container_response(interaction_or_ctx, err_card, ephemeral=True)
            else:
                await interaction_or_ctx.send_warning("This ticket is already open.")
            return

        # Restore permissions for ticket creator
        user_id = ticket.get("user_id")
        if user_id:
            user = guild.get_member(user_id)
            if user:
                try:
                    await channel.set_permissions(
                        user,
                        view_channel=True,
                        send_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True,
                        reason=f"Ticket reopened by {reopener}",
                    )
                except Exception as perm_err:
                    logger.debug(f"Could not restore permissions for creator: {perm_err}")

        await self.bot.ticket_mgr.reopen_ticket(channel.id)

        t_num = ticket.get("ticket_number", 1)
        t_num_int = int(t_num) if str(t_num).isdigit() else 1
        reopen_card = KyokaContainer(accent_color=5763719)  # Green
        reopen_card.add_section(
            content=(
                f"**Ticket Reopened • #{t_num_int:04d}**\n"
                f"> This ticket was reopened by {reopener.mention}.\n"
                f"> Creator access has been restored."
            )
        )
        await send_container_response(channel, reopen_card, view=TicketInsideControlsView(self))


    # ─── TICKET COMMANDS ──────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="ticket",
        aliases=["tickets", "ticketpanel"],
        description="Enterprise Ticket System management commands and interactive setup wizard.",
        fallback="hub",
    )
    async def ticket_group(self, ctx: CustomContext) -> None:
        """Ticket Hub Overview & Commands Guide."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        panels = await self.bot.ticket_mgr.list_panels(ctx.guild.id)

        hub_container = KyokaContainer(accent_color=None)
        hub_container.add_section(
            content=(
                "**Ticket System Hub**\n"
                f"> Manage, deploy, and configure custom ticket panels for **{ctx.guild.name}**.\n"
                f"> Integrated with the **Embed Builder** for custom visual cards."
            )
        )
        hub_container.add_separator(divider=True)

        if panels:
            p_names = [f"`{p.get('panel_name')}`" for p in panels[:25]]
            hub_container.add_text(
                f"**Configured Panels ({len(panels)}):** " + " , ".join(p_names)
            )
        else:
            hub_container.add_text(
                "**Configured Panels:** `None`"
            )

        hub_container.add_separator(divider=True)
        hub_container.add_text(
            f"`{prefix}ticket setup` , `{prefix}ticket list`\n"
            f"`{prefix}ticket close` , `{prefix}ticket claim`\n"
            f"`{prefix}ticket add <@user>` , `{prefix}ticket remove <@user>`\n"
            f"`{prefix}ticket transcript` , `{prefix}ticket delete <name>`"
        )
        hub_container.add_separator(divider=True)
        hub_container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, hub_container)

    @ticket_group.command(
        name="setup",
        description="Launch the interactive Slide Dashboard to configure and deploy a ticket panel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(self, ctx: CustomContext, embed_name: str | None = None) -> None:
        """Launch the 4-step Slide Wizard."""
        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        wizard = TicketSetupWizard(self, ctx.author, templates=templates, initial_embed=embed_name)
        dashboard_container = wizard.get_dashboard_container(ctx.guild)
        await send_container_response(ctx, dashboard_container, view=wizard)

    @ticket_group.command(
        name="close",
        description="Close the active ticket channel with optional reason.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_close_cmd(self, ctx: CustomContext, *, reason: str = "Issue resolved") -> None:
        """Command to close active ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send_error("This channel is not an active ticket channel.")
            return
        await self.execute_ticket_close(ctx, ticket, reason=reason)

    @ticket_group.command(
        name="claim",
        description="Claim the current active ticket.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_claim_cmd(self, ctx: CustomContext) -> None:
        """Command to claim active ticket."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send_error("This channel is not an active ticket channel.")
            return

        claimed_by = ticket.get("claimed_by")
        if claimed_by and claimed_by == ctx.author.id:
            await ctx.send_warning("You have already claimed this ticket.")
            return

        await self.bot.ticket_mgr.claim_ticket(ctx.channel.id, ctx.author.id)
        c = KyokaContainer()
        c.add_section(content=f"**Ticket Claimed**\n> {ctx.author.mention} is now handling this ticket.")
        await send_container_response(ctx, c)

    @ticket_group.command(
        name="add",
        description="Add a member to the current ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_add_user(self, ctx: CustomContext, member: discord.Member) -> None:
        """Add user to ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send_error("This channel is not an active ticket channel.")
            return

        await ctx.channel.set_permissions(
            member,
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
            reason=f"Added to ticket by {ctx.author}",
        )
        await ctx.send_success(f"Added {member.mention} to this ticket.", title="Member Added")

    @ticket_group.command(
        name="remove",
        description="Remove a member from the current ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_remove_user(self, ctx: CustomContext, member: discord.Member) -> None:
        """Remove user from ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send_error("This channel is not an active ticket channel.")
            return

        if member.id == ticket.get("user_id"):
            await ctx.send_error("You cannot remove the ticket creator from their own ticket.")
            return

        await ctx.channel.set_permissions(member, overwrite=None, reason=f"Removed from ticket by {ctx.author}")
        await ctx.send_success(f"Removed {member.mention} from this ticket.", title="Member Removed")

    @ticket_group.command(
        name="transcript",
        description="Generate and download the HTML transcript of this ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_transcript_cmd(self, ctx: CustomContext) -> None:
        """Generate and send transcript."""
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send_error("Transcripts are only supported in text channels.")
            return

        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        file = await generate_html_transcript(ctx.channel, ticket, bot=self.bot)
        t_card = KyokaContainer()
        t_card.add_section(content="**Ticket Transcript**\n> Here is the generated HTML transcript for this ticket channel.")
        await send_container_response(ctx, t_card, file=file)

    @ticket_group.command(
        name="list",
        description="List all active ticket panels configured in this server.",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_list_panels(self, ctx: CustomContext) -> None:
        """List configured panels."""
        panels = await self.bot.ticket_mgr.list_panels(ctx.guild.id)
        if not panels:
            await ctx.send_warning("No ticket panels configured yet. Use `?ticket setup` to create one.")
            return

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=f"**Configured Ticket Panels ({len(panels)})**\n> Server: **{ctx.guild.name}**"
        )
        container.add_separator(divider=True)

        lines = []
        for i, p in enumerate(panels[:15], 1):
            ch_m = f"<#{p.get('channel_id')}>"
            cat_m = f"<#{p.get('category_id')}>" if p.get("category_id") else "*Auto*"
            lines.append(f"**{i}. {p.get('panel_name')}** • Channel: {ch_m} • Category: {cat_m}")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)

    @ticket_group.command(
        name="reopen",
        description="Reopen a closed ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_reopen_cmd(self, ctx: CustomContext) -> None:
        """Command to reopen closed ticket channel."""
        await self.execute_ticket_reopen(ctx)

    @ticket_group.command(
        name="delete",
        description="Delete a configured panel or purge the current ticket channel. Usage: ?ticket delete [panel_name]",
    )
    @commands.has_permissions(manage_channels=True)
    async def ticket_delete_cmd(self, ctx: CustomContext, panel_name: str | None = None) -> None:
        """Delete a ticket panel or delete current ticket channel."""
        if panel_name:
            clean_name = panel_name.lower().strip()
            existing = await self.bot.ticket_mgr.get_panel(ctx.guild.id, clean_name)
            if not existing:
                await ctx.send_error(f"Panel `{clean_name}` not found. Use `?ticket list` to see configured panels.")
                return

            ch_id = existing.get("channel_id")
            msg_id = existing.get("message_id")
            if ch_id and msg_id:
                try:
                    ch = ctx.guild.get_channel(ch_id)
                    if isinstance(ch, discord.TextChannel):
                        msg = await ch.fetch_message(msg_id)
                        await msg.delete()
                except Exception:
                    pass

            await self.bot.ticket_mgr.delete_panel(ctx.guild.id, clean_name)
            await ctx.send_success(f"Ticket panel `{clean_name}` has been deleted.", title="Panel Deleted")
            return

        # No panel name passed: check if running inside a ticket channel to delete it
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            ticket = await self.bot.db.fetch_one("SELECT * FROM active_tickets WHERE channel_id = $1;", ctx.channel.id)

        if ticket:
            del_card = KyokaContainer(accent_color=15548997)
            del_card.add_section(content="**Deleting Ticket**\n> This ticket channel will be permanently deleted in 5 seconds...")
            await send_container_response(ctx, del_card)
            await asyncio.sleep(5)
            try:
                await ctx.channel.delete(reason=f"Ticket deleted by {ctx.author}")
            except Exception as e:
                logger.debug(f"Could not delete channel: {e}")
            return
        await ctx.send_warning("Specify a panel name (`?ticket delete <panel_name>`) or use this command inside a ticket channel.")


    @ticket_group.command(name="unclaim", description="Release claim on the current active ticket.")
    @commands.has_permissions(manage_messages=True)
    async def ticket_unclaim_cmd(self, ctx: CustomContext) -> None:
        """Command to release ticket claim."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.send_error("This channel is not an active ticket channel.")
        if not ticket.get("claimed_by"):
            return await ctx.send_warning("This ticket is not currently claimed.")
        await self.bot.db.execute("UPDATE active_tickets SET claimed_by = NULL WHERE channel_id = $1;", ctx.channel.id)
        ticket["claimed_by"] = None
        await ctx.send_success("Ticket claim released. Any staff member can now handle this ticket.")

    @ticket_group.command(name="transfer", description="Transfer ticket handling to another staff member.")
    @commands.has_permissions(manage_messages=True)
    async def ticket_transfer_cmd(self, ctx: CustomContext, staff: discord.Member) -> None:
        """Command to transfer ticket to another staff member."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.send_error("This channel is not an active ticket channel.")
        await self.bot.ticket_mgr.claim_ticket(ctx.channel.id, staff.id)
        await ctx.send_success(f"Ticket transferred to {staff.mention}!")

    @ticket_group.command(name="rename", description="Rename the current ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_rename_cmd(self, ctx: CustomContext, *, new_name: str) -> None:
        """Command to rename current ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket or not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.send_error("This channel is not an active ticket channel.")
        clean = new_name.lower().replace(" ", "-")[:100]
        await ctx.channel.edit(name=clean, reason=f"Ticket renamed by {ctx.author}")
        await ctx.send_success(f"Renamed ticket channel to `#{clean}`.")

    @ticket_group.command(name="priority", description="Set ticket priority: Low, Normal, High, Urgent.")
    @commands.has_permissions(manage_messages=True)
    async def ticket_priority_cmd(self, ctx: CustomContext, level: str) -> None:
        """Command to set ticket priority."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.send_error("This channel is not an active ticket channel.")
        clean = level.title()
        if clean not in ("Low", "Normal", "High", "Urgent"):
            return await ctx.send_error("Invalid priority. Choose: `Low`, `Normal`, `High`, or `Urgent`.")
        await self.bot.db.execute("UPDATE active_tickets SET priority = $2 WHERE channel_id = $1;", ctx.channel.id, clean)
        ticket["priority"] = clean
        await ctx.send_success(f"Ticket priority set to **{clean}**.")

    @ticket_group.command(name="note", description="Add an internal staff note to this ticket.")
    @commands.has_permissions(manage_messages=True)
    async def ticket_note_cmd(self, ctx: CustomContext, *, note: str) -> None:
        """Command to record internal staff note."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.send_error("This channel is not an active ticket channel.")
        await self.bot.db.execute(
            "INSERT INTO ticket_internal_notes (channel_id, author_id, note_text) VALUES ($1, $2, $3);",
            ctx.channel.id,
            ctx.author.id,
            note,
        )
        await ctx.send_success("Internal staff note recorded.", title="Staff Note Added")

    @ticket_group.command(name="stats", description="View server ticket statistics and resolution metrics.")
    @commands.has_guild_permissions(manage_guild=True)
    async def ticket_stats_cmd(self, ctx: CustomContext) -> None:
        """Show ticket metrics and analytics."""
        open_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM active_tickets WHERE guild_id = $1 AND status = 'open';",
            ctx.guild.id,
        )
        closed_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM active_tickets WHERE guild_id = $1 AND status = 'closed';",
            ctx.guild.id,
        )
        unclaimed_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM active_tickets WHERE guild_id = $1 AND status = 'open' AND claimed_by IS NULL;",
            ctx.guild.id,
        )
        open_cnt = int(open_row["cnt"]) if open_row else 0
        closed_cnt = int(closed_row["cnt"]) if closed_row else 0
        unclaimed_cnt = int(unclaimed_row["cnt"]) if unclaimed_row else 0
        tot = open_cnt + closed_cnt

        c = KyokaContainer()
        c.add_section(
            content=(
                f"📊 **Ticket System Analytics • {ctx.guild.name}**\n"
                f"> Total Tickets: `{tot}`\n"
                f"> Currently Open: `{open_cnt}`\n"
                f"> Unclaimed: `{unclaimed_cnt}`\n"
                f"> Successfully Closed: `{closed_cnt}`"
            )
        )
        await send_container_response(ctx, c)

    @ticket_group.command(name="limit", description="Configure the maximum simultaneous tickets per user for a panel (0 = unlimited).")
    @commands.has_permissions(administrator=True)
    async def ticket_limit_cmd(self, ctx: CustomContext, panel_name: str, limit: int = 0) -> None:
        """Set max simultaneous tickets per user on a panel (0 for unlimited)."""
        clean_name = panel_name.lower().strip()
        panel = await self.bot.ticket_mgr.get_panel(ctx.guild.id, clean_name)
        if not panel:
            return await ctx.send_error(f"Panel `{clean_name}` not found.")
        if limit < 0:
            limit = 0
        await self.bot.db.execute(
            "UPDATE ticket_panels SET max_tickets_per_user = $1 WHERE guild_id = $2 AND panel_name = $3;",
            limit, ctx.guild.id, clean_name
        )
        self.bot.ticket_mgr._panels_cache.pop(ctx.guild.id, None)
        status = "Unlimited" if limit == 0 else str(limit)
        await ctx.send_success(f"Ticket limit for panel `{clean_name}` set to **{status}** per user.")

    @ticket_group.group(name="category", aliases=["cat", "categories"], invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def ticket_category_group(self, ctx: CustomContext) -> None:
        """Manage custom ticket categories for this server."""
        await ctx.invoke(self.ticket_category_list_cmd)

    @ticket_category_group.command(name="list", description="List all configured ticket categories.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_category_list_cmd(self, ctx: CustomContext, panel_name: str = "") -> None:
        """List all ticket categories."""
        cats = await self.bot.ticket_mgr.list_categories(ctx.guild.id, panel_name=panel_name)
        if not cats:
            return await ctx.send_warning("No ticket categories configured.")
        lines = []
        for i, c in enumerate(cats, start=1):
            emoji = c.get("emoji") or "🎫"
            desc = c.get("description") or "No description"
            lines.append(f"**{i}. {emoji} {c['name']}** — {desc}")

        container = KyokaContainer()
        container.add_section(
            content=f"🎫 **Ticket Categories • {ctx.guild.name}**\n\n" + "\n".join(lines)
        )
        await send_container_response(ctx, container)

    @ticket_category_group.command(name="add", description="Add a new custom ticket category. Usage: ?ticket category add <name> [emoji] [description]")
    @commands.has_permissions(manage_channels=True)
    async def ticket_category_add_cmd(
        self,
        ctx: CustomContext,
        name: str,
        emoji: str = "🎫",
        *,
        description: str = "Inquiry & services",
    ) -> None:
        """Add a custom ticket category."""
        clean_name = name.strip()[:100]
        await self.bot.ticket_mgr.add_category(
            guild_id=ctx.guild.id,
            name=clean_name,
            description=description[:250],
            emoji=emoji,
        )
        await ctx.send_success(f"Ticket category **{emoji} {clean_name}** added successfully!")

    @ticket_category_group.command(name="delete", aliases=["remove"], description="Delete a ticket category.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_category_delete_cmd(self, ctx: CustomContext, *, name: str) -> None:
        """Delete a ticket category."""
        clean_name = name.strip()
        deleted = await self.bot.ticket_mgr.delete_category(ctx.guild.id, clean_name)
        if deleted:
            await ctx.send_success(f"Ticket category **{clean_name}** deleted.")
        else:
            await ctx.send_error(f"Category **{clean_name}** not found.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(TicketSystem(bot))
