"""
Kyoka Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by native discord.py UI Views with Category Select
and Navigation Buttons (Prev/Home/Next/Close) plus Link actions.
Organized into 14 clean, intuitive command categories with dark purple Aizen styling.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import time
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response
from src.utils.ui import KyokaEmbed, AizenPalette, AizenSymbols
from src.security.owner import is_primary_owner, is_owner_or_staff
from src.security.adult_guard import is_adult_authorized
from src.ui.cards.hero_banner import generate_kyoka_hero_banner
from src.ui.cards.hca_banner import generate_hca_banner
from src.ui.categories import (
    CATEGORIES,
    CATEGORY_BY_ID,
    CATEGORY_BY_TAG,
    CATEGORY_SEARCH_ALIASES,
    resolve_command_category,
    get_category_by_query,
)
from src.ui.asset_manager import AssetManager
from src.ui.help_renderer import KyokaHelpEmbed

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Help")

HELP_COMMANDS_PER_PAGE: int = 10

UNICODE_CATEGORY_EMOJIS: dict[str, str] = {
    "home": "🏠",
    "🏠・GETTING STARTED": "🏠",
    "🏠・GENERAL & UTILITY": "🏠",
    "🛡️・MODERATION": "🛡️",
    "🔒・AUTOMOD & SECURITY": "🔒",
    "👋・WELCOME & AUTOMOD": "👋",
    "👋・WELCOME & GOODBYE": "👋",
    "🛡️・VERIFICATION": "🛡️",
    "🎫・TICKETS & SUPPORT": "🎫",
    "🎭・REACTION ROLES": "🎭",
    "🎉・GIVEAWAYS & EVENTS": "🎉",
    "⭐・LEVELS & COMMUNITY": "⭐",
    "🎵・MUSIC": "🎵",
    "💤・AFK": "💤",
    "⭐・VOUCHES & REPUTATION": "⭐",
    "🧾・BLOX FRUITS SERVICE BILLS": "🧾",
    "🍎・BLOX FRUITS AI": "🍎",
    "🎙️・AI VOICE": "🎙️",
    "📊・LEVELING & LEADERBOARDS": "📊",
    "🤖・ARTIFICIAL INTELLIGENCE": "🤖",
    "🖼️・IMAGES & AVATARS": "🖼️",
    "💬・SOCIAL & FUN": "💬",
    "💎・PREMIUM": "💎",
    "⚙️・SERVER ADMINISTRATION": "⚙️",
    "⚙️・SERVER CONFIGURATION": "⚙️",
    "🔧・UTILITIES": "🔧",
    "📝・STAFF APPLICATIONS": "📝",
    "👑・OWNER & DEVELOPER": "👑",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "🏠・GETTING STARTED": "Server onboarding, quickstart guide, bot setup & essential info",
    "🏠・GENERAL & UTILITY": "General utilities, calculators, reminders, info lookups & essential tools",
    "🛡️・MODERATION": "Punishments, audit logs, purges, timeouts, channel locks & cases",
    "🔒・AUTOMOD & SECURITY": "Anti-spam, anti-flood, invite protection, bad words & antinuke",
    "👋・WELCOME & AUTOMOD": "Greeting cards, farewell departures, autoroles & join settings",
    "👋・WELCOME & GOODBYE": "Greeting cards, farewell departures, autoroles & join settings",
    "🛡️・VERIFICATION": "Gatekeep channels with role isolation, button & challenge verification",
    "🎫・TICKETS & SUPPORT": "Interactive support ticket panels, claims & automated transcripts",
    "🎭・REACTION ROLES": "Self-service role menus, reaction assignment & interactive panels",
    "🎉・GIVEAWAYS & EVENTS": "Giveaway creation, requirement validation, timers & winner rerolls",
    "⭐・LEVELS & COMMUNITY": "Optional XP progression (disabled by default), custom rank cards & leaderboards",
    "🎵・MUSIC": "High-fidelity audio playback, queues, volume, filters & 24/7 radio",
    "💤・AFK": "Status notices, AFK reason tracking, mentions & return alerts",
    "⭐・VOUCHES & REPUTATION": "Verified member vouches, Blox Fruits trust profiles & leaderboards",
    "🧾・BLOX FRUITS SERVICE BILLS": "Blox Fruits service invoices, itemized receipts, fruits & Robux payment",
    "🍎・BLOX FRUITS AI": "Specialized Blox Fruits AI, fruit guides, trade calculator & builds",
    "🎙️・AI VOICE": "Neural Text-To-Speech, voice channel interaction, AI speech responses & diagnostics",
    "📊・LEVELING & LEADERBOARDS": "Optional XP progression (disabled by default), rank cards & leaderboards",
    "🤖・ARTIFICIAL INTELLIGENCE": "Aizen Gemini AI engine, 10 personalities & auto channels",
    "🖼️・IMAGES & AVATARS": "Anime reaction GIFs, avatar grabbers, banners & memes",
    "💬・SOCIAL & FUN": "Mini-games, truth-or-dare, relationship stats & trivia",
    "💎・PREMIUM": "Kyoka Prime licenses, high-resolution AI & premium perks",
    "⚙️・SERVER ADMINISTRATION": "Prefix management, server wizards, custom help & diagnostics",
    "⚙️・SERVER CONFIGURATION": "Prefix management, server wizards, custom help & diagnostics",
    "🔧・UTILITIES": "Handy server utilities, calculators, reminders & diagnostics",
    "📝・STAFF APPLICATIONS": "Appy-style staff recruitment panels, applicant submissions & reviewer dashboard",
    "👑・OWNER & DEVELOPER": "Core bot diagnostics, database status, extension reload & maintenance",
}



class HelpCategorySelect(discord.ui.Select):
    """Interactive category select menu for switching between command categories."""

    def __init__(
        self,
        help_view: HelpView,
        visible_categories: dict[str, list[commands.Command]],
        current_selection: str = "home",
    ) -> None:
        self.help_view = help_view

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Home",
                value="home",
                description="Kyoka overview, quickstart & navigation guide",
                emoji="🏠",
                default=(current_selection == "home"),
            )
        ]

        for cat_name, cmds in visible_categories.items():
            # Clean display label matching Screenshot 2
            raw_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            clean_label = raw_title.title() if raw_title.isupper() else raw_title
            clean_label = clean_label.strip()

            # Short module-specific description
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{len(cmds)} accessible commands")[:100]
            emoji_str = UNICODE_CATEGORY_EMOJIS.get(cat_name, "📁")

            options.append(
                discord.SelectOption(
                    label=clean_label[:100],
                    value=cat_name.lower(),
                    description=desc,
                    emoji=emoji_str,
                    default=(current_selection.lower() == cat_name.lower()),
                )
            )

        selected_label = "🏠 Home"
        if current_selection.lower() != "home":
            for cat_name in visible_categories.keys():
                if cat_name.lower() == current_selection.lower():
                    raw_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
                    clean_title = raw_title.title() if raw_title.isupper() else raw_title
                    emoji_str = UNICODE_CATEGORY_EMOJIS.get(cat_name, "📁")
                    selected_label = f"{emoji_str} {clean_title}"
                    break

        super().__init__(
            placeholder=selected_label,
            min_values=1,
            max_values=1,
            options=options[:25],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        await self.help_view.switch_category(interaction, selected)


class HelpSearchModal(discord.ui.Modal, title="⛩️ Search Kyoka Commands"):
    """Interactive modal allowing instant search across all registered commands."""
    query_input = discord.ui.TextInput(
        label="Command Name or Keyword",
        placeholder="e.g. ban, ai, ticket, rank, music, remind...",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, help_view: HelpView) -> None:
        super().__init__()
        self.help_view = help_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = self.query_input.value.strip().lower()
        embed = self.help_view.cog.build_search_results_embed(
            self.help_view.ctx,
            self.help_view.visible_categories,
            query,
        )
        await interaction.response.edit_message(embed=embed, view=self.help_view)


class HelpView(discord.ui.View):
    """Enterprise UI View providing category selection, pagination, search, and quick links."""

    def __init__(
        self,
        cog: Help,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        current_category: str = "home",
        current_page: int = 1,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.visible_categories = visible_categories
        self.category_keys = list(visible_categories.keys())
        self.current_category = current_category
        self.current_page = current_page
        self.message: discord.Message | None = None

        self._build_components()

    def _build_components(self) -> None:
        """Construct the view buttons and select menu matching Kyro clean layout."""
        self.clear_items()

        # Row 0: Dropdown
        self.add_item(
            HelpCategorySelect(
                self,
                self.visible_categories,
                current_selection=self.current_category,
            )
        )

        bot_name = "Kyoka"
        branding = None
        if hasattr(self.cog.bot, "branding_mgr"):
            mgr = getattr(self.cog.bot, "branding_mgr", None)
            if hasattr(mgr, "_cache") and isinstance(mgr._cache, dict):
                branding = mgr._cache.get(self.ctx.guild.id if self.ctx.guild else None)
        raw_display = branding.get("display_name") if isinstance(branding, dict) else None
        if isinstance(raw_display, str) and raw_display.strip():
            bot_name = raw_display.strip()

        invite_url = (
            Config.INVITE_URL
            or (
                f"https://discord.com/oauth2/authorize?client_id={self.cog.bot.application_id or self.cog.bot.user.id}&permissions=8&scope=bot%20applications.commands"
                if (hasattr(self.cog.bot, "user") and self.cog.bot.user)
                else "https://discord.com"
            )
        )
        support_url = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"

        if self.current_category == "home":
            btn_search = discord.ui.Button(
                label="Search",
                emoji="🔍",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)

            self.add_item(
                discord.ui.Button(
                    label=f"Invite {bot_name}",
                    url=invite_url,
                    style=discord.ButtonStyle.link,
                    row=1,
                )
            )
            self.add_item(
                discord.ui.Button(
                    label="Support Server",
                    url=support_url,
                    style=discord.ButtonStyle.link,
                    row=1,
                )
            )
        else:
            # On Category: Clean Navigation Buttons + Link Buttons
            btn_back = discord.ui.Button(
                label="Back",
                emoji="◀️",
                style=discord.ButtonStyle.secondary,
                disabled=(self.current_page <= 1),
                row=1,
            )
            btn_back.callback = self.btn_back_callback
            self.add_item(btn_back)

            btn_home = discord.ui.Button(
                label="Home",
                emoji="🏠",
                style=discord.ButtonStyle.primary,
                row=1,
            )
            btn_home.callback = self.btn_home_callback
            self.add_item(btn_home)

            btn_next = discord.ui.Button(
                label="Next",
                emoji="▶️",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_next.callback = self.btn_next_callback
            self.add_item(btn_next)

            btn_search = discord.ui.Button(
                label="Search",
                emoji="🔍",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)

            self.add_item(
                discord.ui.Button(
                    label=f"Invite {bot_name}",
                    url=invite_url,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )
            self.add_item(
                discord.ui.Button(
                    label="Support Server",
                    url=support_url,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command requester can control this session."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the user who requested this help menu can interact with it. Type `+help` or `/help` to open your own!",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable interactive buttons and dropdown on session expiration."""
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)) and getattr(item, "style", None) != discord.ButtonStyle.link:
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
            elif self.ctx and getattr(self.ctx, "interaction", None):
                await self.ctx.interaction.edit_original_response(view=self)
        except Exception:
            pass

    async def switch_category(self, interaction: discord.Interaction, selected_val: str) -> None:
        """Switch current view page and refresh UI components with category artwork."""
        self.current_category = selected_val
        self.current_page = 1
        self._build_components()
        embed, banner_file = self.cog.build_embed_for_selection(self.ctx, self.visible_categories, selected_val, page=1)
        if banner_file:
            await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        """Navigate to the previous page or previous category."""
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match and self.current_page > 1:
                self.current_page -= 1
                embed, banner_file = self.cog.build_embed_for_selection(
                    self.ctx, self.visible_categories, self.current_category, page=self.current_page
                )
                if banner_file:
                    await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                else:
                    await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                return

        if not self.category_keys:
            await self.switch_category(interaction, "home")
            return
        if self.current_category == "home":
            new_cat = self.category_keys[-1]
        else:
            curr_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if curr_match and curr_match in self.category_keys:
                idx = self.category_keys.index(curr_match)
                new_cat = self.category_keys[(idx - 1) % len(self.category_keys)]
            else:
                new_cat = self.category_keys[0]
        await self.switch_category(interaction, new_cat)

    async def btn_home_callback(self, interaction: discord.Interaction) -> None:
        """Navigate directly to the Home Overview."""
        await self.switch_category(interaction, "home")

    async def btn_next_callback(self, interaction: discord.Interaction) -> None:
        """Navigate to the next page or next category."""
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match:
                cmds = self.visible_categories.get(cat_match, [])
                total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))
                if self.current_page < total_pages:
                    self.current_page += 1
                    embed, banner_file = self.cog.build_embed_for_selection(
                        self.ctx, self.visible_categories, self.current_category, page=self.current_page
                    )
                    if banner_file:
                        await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                    else:
                        await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                    return

        if not self.category_keys:
            await self.switch_category(interaction, "home")
            return
        if self.current_category == "home":
            new_cat = self.category_keys[0]
        else:
            curr_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if curr_match and curr_match in self.category_keys:
                idx = self.category_keys.index(curr_match)
                new_cat = self.category_keys[(idx + 1) % len(self.category_keys)]
            else:
                new_cat = self.category_keys[0]
        await self.switch_category(interaction, new_cat)

    async def btn_search_callback(self, interaction: discord.Interaction) -> None:
        """Prompt command search modal."""
        await interaction.response.send_modal(HelpSearchModal(self))

    async def btn_close_callback(self, interaction: discord.Interaction) -> None:
        """Close the help session gracefully."""
        self.stop()
        embed = discord.Embed(
            title="🔒 Help Session Closed",
            description="> This help menu has been closed.\n> Type `+help` or `/help` whenever you need guidance.",
            color=0x2B0938,
        )
        for item in self.children:
            if getattr(item, "style", None) != discord.ButtonStyle.link:
                item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class HCACategorySelect(discord.ui.Select):
    """Category select menu for the Public Help Command Archive."""

    def __init__(
        self,
        hca_view: HCAView,
        categories: dict[str, list[commands.Command]],
        current_selection: str = "home",
    ) -> None:
        self.hca_view = hca_view
        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Archive Index",
                value="home",
                description="Complete directory index of all categories",
                emoji="📚",
                default=(current_selection == "home"),
            )
        ]
        for cat_name, cmds in categories.items():
            raw_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            clean_label = raw_title.title() if raw_title.isupper() else raw_title
            clean_label = clean_label.strip()[:100]
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{len(cmds)} archived commands")[:100]
            emoji_str = UNICODE_CATEGORY_EMOJIS.get(cat_name, "📁")
            options.append(
                discord.SelectOption(
                    label=clean_label,
                    value=cat_name.lower(),
                    description=desc,
                    emoji=emoji_str,
                    default=(current_selection.lower() == cat_name.lower()),
                )
            )

        super().__init__(
            placeholder="Select a category to view all commands...",
            min_values=1,
            max_values=1,
            options=options[:25],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        await self.hca_view.switch_category(interaction, selected)


class HCASearchModal(discord.ui.Modal, title="📚 Search Command Archive"):
    query_input = discord.ui.TextInput(
        label="Command Name or Keyword",
        placeholder="e.g. play, ban, fruitvalues, aivoice, bill, ticket...",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, hca_view: HCAView) -> None:
        super().__init__()
        self.hca_view = hca_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = self.query_input.value.strip().lower()
        embed = self.hca_view.cog.build_hca_search_embed(
            self.hca_view.ctx,
            self.hca_view.all_categories,
            query,
        )
        await interaction.response.edit_message(embed=embed, view=self.hca_view)


class HCAView(discord.ui.View):
    """Interactive navigation view for the public Help Command Archive directory."""

    def __init__(
        self,
        cog: Help,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
        current_category: str = "home",
        current_page: int = 1,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.all_categories = all_categories
        self.category_keys = list(all_categories.keys())
        self.current_category = current_category
        self.current_page = current_page
        self.message: discord.Message | None = None
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        self.add_item(HCACategorySelect(self, self.all_categories, current_selection=self.current_category))

        btn_back = discord.ui.Button(label="Back", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        btn_back.callback = self.btn_back_callback
        self.add_item(btn_back)

        btn_home = discord.ui.Button(label="Index", emoji="📚", style=discord.ButtonStyle.primary, row=1)
        btn_home.callback = self.btn_home_callback
        self.add_item(btn_home)

        btn_next = discord.ui.Button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
        btn_next.callback = self.btn_next_callback
        self.add_item(btn_next)

        btn_search = discord.ui.Button(label="Search", emoji="🔍", style=discord.ButtonStyle.secondary, row=1)
        btn_search.callback = self.btn_search_callback
        self.add_item(btn_search)

        btn_close = discord.ui.Button(label="Close", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
        btn_close.callback = self.btn_close_callback
        self.add_item(btn_close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the command requester can control this session. Type `+hca` to open your own!",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)) and getattr(item, "style", None) != discord.ButtonStyle.link:
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
            elif self.ctx and getattr(self.ctx, "interaction", None):
                await self.ctx.interaction.edit_original_response(view=self)
        except Exception:
            pass

    async def switch_category(self, interaction: discord.Interaction, selected_val: str) -> None:
        self.current_category = selected_val
        self.current_page = 1
        self._build_components()
        embed, banner_file = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, selected_val, page=1)
        if banner_file:
            await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match and self.current_page > 1:
                self.current_page -= 1
                embed, banner_file = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, self.current_category, page=self.current_page)
                if banner_file:
                    await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                else:
                    await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                return

        if not self.category_keys:
            await self.switch_category(interaction, "home")
            return
        if self.current_category == "home":
            new_cat = self.category_keys[-1]
        else:
            curr_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if curr_match and curr_match in self.category_keys:
                idx = self.category_keys.index(curr_match)
                new_cat = self.category_keys[(idx - 1) % len(self.category_keys)]
            else:
                new_cat = self.category_keys[0]
        await self.switch_category(interaction, new_cat)

    async def btn_home_callback(self, interaction: discord.Interaction) -> None:
        await self.switch_category(interaction, "home")

    async def btn_next_callback(self, interaction: discord.Interaction) -> None:
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match:
                cmds = self.all_categories.get(cat_match, [])
                total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))
                if self.current_page < total_pages:
                    self.current_page += 1
                    embed, banner_file = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, self.current_category, page=self.current_page)
                    if banner_file:
                        await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                    else:
                        await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                    return

        if not self.category_keys:
            await self.switch_category(interaction, "home")
            return
        if self.current_category == "home":
            new_cat = self.category_keys[0]
        else:
            curr_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if curr_match and curr_match in self.category_keys:
                idx = self.category_keys.index(curr_match)
                new_cat = self.category_keys[(idx + 1) % len(self.category_keys)]
            else:
                new_cat = self.category_keys[0]
        await self.switch_category(interaction, new_cat)

    async def btn_search_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(HCASearchModal(self))

    async def btn_close_callback(self, interaction: discord.Interaction) -> None:
        self.stop()
        embed = discord.Embed(
            title="🔒 Command Archive Closed",
            description="> Use `+hca` or `/hca` whenever you need to explore commands.",
            color=0x2B0938,
        )
        for item in self.children:
            if getattr(item, "style", None) != discord.ButtonStyle.link:
                item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class Help(commands.Cog):
    """Enterprise SaaS Help & Module Console with dynamic 14-category permission filtering."""
    category: str = "General"

    CATEGORY_ORDER = [
        "🏠・GETTING STARTED",
        "🤖・ARTIFICIAL INTELLIGENCE",
        "🛡️・MODERATION",
        "👋・WELCOME & AUTOMOD",
        "🎫・TICKETS & SUPPORT",
        "🎉・GIVEAWAYS & EVENTS",
        "⭐・LEVELS & COMMUNITY",
        "🖼️・IMAGES & AVATARS",
        "🎵・MUSIC",
        "💬・SOCIAL & FUN",
        "💎・PREMIUM",
        "⚙️・SERVER ADMINISTRATION",
        "🔧・UTILITIES",
        "👑・OWNER & DEVELOPER",
    ]
    ALL_CATEGORY_TAGS = [c.tag for c in CATEGORIES]
    CATEGORY_ALIASES = CATEGORY_SEARCH_ALIASES

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _get_latency_ms(self) -> int:
        """Safely compute websocket ping in milliseconds, handling NaN, inf, or None."""
        try:
            lat = getattr(self.bot, "latency", None)
            if lat is not None and not math.isnan(lat) and not math.isinf(lat):
                return max(0, round(lat * 1000))
        except Exception:
            pass
        return 0

    def _resolve_category(self, cmd: commands.Command) -> str:
        """Resolve a command into one of the clean, modular help categories using the centralized registry."""
        meta = resolve_command_category(cmd)
        return meta.tag

    @staticmethod
    def _can_run_command(cmd: Any, ctx: CustomContext | None = None) -> bool:
        """Hide hidden commands, owner-restricted commands, and adult-restricted commands from unauthorized users."""
        if getattr(cmd, "hidden", False):
            return False

        cog = getattr(cmd, "cog", None)
        cog_cat = str(getattr(cog, "category", "")).strip().lower()
        author_id = getattr(ctx.author, "id", None) if ctx else None

        # Owner/developer internals check
        if cog_cat in {"owner", "developer"}:
            if not is_primary_owner(author_id):
                return False

        cmd_name = str(getattr(cmd, "name", "")).strip().lower()
        if cmd_name in {"spam", "spamcancel"}:
            if not is_owner_or_staff(author_id):
                return False
        else:
            owner_only = {
                "guesshostadd", "guesshostremove", "guesshosts",
                "eval", "exec", "restart", "shutdown", "sync", "leaveserver", "blacklist",
                "whitelistuser", "errors", "validateconfig", "maintenance", "systemstatus",
                "dbstatus", "extstatus",
            }
            if cmd_name in owner_only and not is_primary_owner(author_id):
                return False

        # Adult-humor allowlist restriction check
        if cog_cat in ("adult humor — restricted", "adult humor - restricted", "adulthumor"):
            if not is_adult_authorized(author_id):
                return False

        return True

    def _get_badge(self, cmd: commands.Command) -> str:
        """Return a visual permission/status tag for a command."""
        name = cmd.qualified_name.lower()
        resolved_cat = self._resolve_category(cmd)

        if resolved_cat == "Adult Humor — Restricted":
            return " `[Restricted]`"
        if resolved_cat == "👑・OWNER & DEVELOPER" or name in (
            "spam", "spamcancel", "guesshostadd", "guesshostremove", "guesshosts",
            "eval", "exec", "restart", "shutdown", "sync"
        ):
            return " `[Owner]`"
        if resolved_cat == "🛡️・MODERATION" or name in (
            "ban", "unban", "kick", "timeout", "mute", "unmute", "warn", "delwarn",
            "lock", "unlock", "slowmode", "purge", "clear", "modlog", "softban",
            "nick", "hide", "unhide", "case", "unwarn", "clearwarnings"
        ):
            return " `[Mod]`"
        if resolved_cat == "⚙️・SERVER ADMINISTRATION" or name in ("prefix", "setprefix", "resetprefix", "setup"):
            return " `[Admin]`"
        if resolved_cat == "💎・PREMIUM" or name in ("imagine", "tier", "license", "prime", "setbotavatar", "botavatar", "resetbotavatar", "247", "halloween", "premium", "plan"):
            return " `[Premium]`"
        return ""

    def _get_base_categories(self) -> dict[str, list[commands.Command]]:
        """Index all commands across cogs and bot commands once."""
        categories: dict[str, list[commands.Command]] = {cat: [] for cat in self.CATEGORY_ORDER}
        seen_cmd_names: set[str] = set()

        def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
            cmd_list = [cmd_obj]
            if isinstance(cmd_obj, commands.Group):
                for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                    cmd_list.extend(_collect_all(sub_cmd))
            return cmd_list

        all_root_cmds: list[commands.Command] = list(self.bot.commands)
        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue
            for cmd in cog.get_commands():
                if cmd not in all_root_cmds:
                    all_root_cmds.append(cmd)

        for cmd in all_root_cmds:
            cog = getattr(cmd, "cog", None)
            if cog and getattr(cog, "qualified_name", "").lower() in ["errorhandler"]:
                continue
            for c in _collect_all(cmd):
                target_cat = self._resolve_category(c)
                if target_cat not in categories:
                    categories[target_cat] = []
                if c not in categories[target_cat] and c.qualified_name not in seen_cmd_names:
                    categories[target_cat].append(c)
                    seen_cmd_names.add(c.qualified_name)

        return categories

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to view and execute into categories with high-speed caching."""
        # Use cached command index if command count has not changed
        if not hasattr(self, "_cached_base_categories") or getattr(self, "_cached_cmd_count", -1) != len(self.bot.commands):
            self._cached_base_categories = self._get_base_categories()
            self._cached_cmd_count = len(self.bot.commands)

        base_categories = self._cached_base_categories
        categories: dict[str, list[commands.Command]] = {}

        for cat, cmds in base_categories.items():
            permitted = [c for c in cmds if self._can_run_command(c, ctx)]
            if permitted:
                categories[cat] = permitted

        # Retain only non-empty categories following exact priority order
        ordered_categories: dict[str, list[commands.Command]] = {}
        for cat in self.CATEGORY_ORDER:
            if cat in categories and categories[cat]:
                ordered_categories[cat] = categories[cat]

        for cat, cmds in categories.items():
            if cat not in ordered_categories and cmds:
                ordered_categories[cat] = cmds

        # Integrate guild custom categories if configured
        if ctx.guild and hasattr(self.bot, "custom_help_mgr") and self.bot.custom_help_mgr:
            try:
                custom_cats = await self.bot.custom_help_mgr.get_guild_categories(ctx.guild.id)
                for c_cat in custom_cats:
                    if c_cat.get("is_hidden"):
                        author_perms = getattr(ctx.author, "guild_permissions", None)
                        is_admin = bool(author_perms and author_perms.administrator) or is_primary_owner(getattr(ctx.author, "id", None))
                        if not is_admin:
                            continue
                    c_name = c_cat["category_name"]
                    c_emoji = c_cat.get("emoji") or "📁"
                    cat_header = f"{c_emoji}・{c_name.upper()}"
                    matched_cmds: list[commands.Command] = []
                    for c_cmd_name in c_cat.get("commands", []):
                        cmd_obj = self.bot.get_command(c_cmd_name)
                        if cmd_obj and self._can_run_command(cmd_obj, ctx):
                            if cmd_obj not in matched_cmds:
                                matched_cmds.append(cmd_obj)
                    if matched_cmds:
                        ordered_categories[cat_header] = matched_cmds
                        if c_cat.get("description"):
                            CATEGORY_DESCRIPTIONS[cat_header] = c_cat["description"]
                        UNICODE_CATEGORY_EMOJIS[cat_header] = c_emoji
            except Exception as e:
                logger.debug(f"Error loading custom categories: {e}")

        return ordered_categories

    async def _get_all_registered_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Collect all registered prefix and slash commands for the public Help Command Archive (HCA)."""
        categories: dict[str, list[commands.Command]] = {cat: [] for cat in self.CATEGORY_ORDER}

        def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
            cmd_list = [cmd_obj]
            if isinstance(cmd_obj, commands.Group):
                for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                    cmd_list.extend(_collect_all(sub_cmd))
            return cmd_list

        author_id = getattr(ctx.author, "id", None) if ctx else None
        is_owner = is_primary_owner(author_id)

        # Collect from all cogs + freestanding commands in self.bot.commands
        for cmd in self.bot.commands:
            for c in _collect_all(cmd):
                # Never expose hidden internal debug commands unless primary owner
                if getattr(c, "hidden", False) and not is_owner:
                    continue
                target_cat = self._resolve_category(c)
                if target_cat not in categories:
                    categories[target_cat] = []
                if c not in categories[target_cat]:
                    categories[target_cat].append(c)

        ordered_categories: dict[str, list[commands.Command]] = {}
        for cat in self.CATEGORY_ORDER:
            if cat in categories and categories[cat]:
                ordered_categories[cat] = categories[cat]

        for cat, cmds in categories.items():
            if cat not in ordered_categories and cmds:
                ordered_categories[cat] = cmds

        return ordered_categories

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji or unicode fallback for category header."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return UNICODE_CATEGORY_EMOJIS.get(cat_name, "•")
        mapping = {
            "🏠・GENERAL & UTILITY": e_reg.get("icon_home", "🏠"),
            "🛡️・MODERATION": e_reg.get("icon_moderation", "🛡️"),
            "🔒・AUTOMOD & SECURITY": e_reg.get("icon_shield", "🔒"),
            "👋・WELCOME & GOODBYE": e_reg.get("icon_shield", "👋"),
            "🛡️・VERIFICATION": e_reg.get("icon_shield", "🛡️"),
            "🎫・TICKETS & SUPPORT": e_reg.get("icon_ticket", "🎫"),
            "🎭・REACTION ROLES": e_reg.get("icon_settings", "🎭"),
            "🎉・GIVEAWAYS & EVENTS": e_reg.get("discord_giveaway", "🎉"),
            "🎵・MUSIC": e_reg.get("music", e_reg.get("icon_music", "🎵")),
            "💤・AFK": "💤",
            "⭐・VOUCHES & REPUTATION": e_reg.get("icon_chart", "⭐"),
            "🧾・BLOX FRUITS SERVICE BILLS": "🧾",
            "🍎・BLOX FRUITS AI": e_reg.get("icon_sparkles", "🍎"),
            "🎙️・AI VOICE": "🎙️",
            "📊・LEVELING & LEADERBOARDS": e_reg.get("icon_chart", "📊"),
            "🤖・ARTIFICIAL INTELLIGENCE": e_reg.get("icon_sparkles", "🤖"),
            "🖼️・IMAGES & AVATARS": e_reg.get("icon_image", "🖼️"),
            "💬・SOCIAL & FUN": e_reg.get("icon_heart", "💬"),
            "💎・PREMIUM": e_reg.get("verified_premium", "💎"),
            "⚙️・SERVER CONFIGURATION": e_reg.get("icon_settings", "⚙️"),
            "👑・OWNER & DEVELOPER": e_reg.get("icon_crown", "👑"),
        }
        return mapping.get(cat_name, UNICODE_CATEGORY_EMOJIS.get(cat_name, "•"))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return None
        mapping = {
            "🏠・GENERAL & UTILITY": "icon_home",
            "🛡️・MODERATION": "icon_moderation",
            "🔒・AUTOMOD & SECURITY": "icon_shield",
            "👋・WELCOME & GOODBYE": "icon_shield",
            "🛡️・VERIFICATION": "icon_shield",
            "🎫・TICKETS & SUPPORT": "icon_ticket",
            "🎭・REACTION ROLES": "icon_settings",
            "🎉・GIVEAWAYS & EVENTS": "discord_giveaway",
            "🎵・MUSIC": "music",
            "⭐・VOUCHES & REPUTATION": "icon_chart",
            "📊・LEVELING & LEADERBOARDS": "icon_chart",
            "🤖・ARTIFICIAL INTELLIGENCE": "icon_sparkles",
            "🍎・BLOX FRUITS AI": "icon_sparkles",
            "🖼️・IMAGES & AVATARS": "icon_image",
            "💬・SOCIAL & FUN": "icon_heart",
            "💎・PREMIUM": "verified_premium",
            "⚙️・SERVER CONFIGURATION": "icon_settings",
            "👑・OWNER & DEVELOPER": "icon_crown",
        }
        emoji_name = mapping.get(cat_name, "icon_moderation")
        return e_reg.get_select_emoji(emoji_name, fallback_unicode=None)

    def _build_home_container(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
        selected_val: str = "home",
    ) -> KyokaContainer:
        """Construct the Signature Kyoka Overview Container Card."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        e_reg = getattr(self.bot, "custom_emojis", None)

        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•")) if e_reg else "•"

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Hey, I'm Kyoka 3.0**\n"
                f"> Built for our community — keeping your server safe, active, and effortlessly connected."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Latency:** `{ws_ping}ms`\n"
            f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
            f"{dot} **Available Commands:** `{total_commands}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {author.display_name} • Type {current_prefix}help <command> for details**")
        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> KyokaContainer:
        """Construct category command container with permission badges and clean layout."""
        cat_icon = self._get_category_emoji(cat_name)
        cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        container = KyokaContainer(accent_color=None)

        if cat_name in ("🤖・ARTIFICIAL INTELLIGENCE", "⛩️・AIZEN AI SYSTEM"):
            container.add_section(
                content=(
                    f"**{cat_icon_prefix}AIZEN AI SYSTEM MODULE**\n"
                    f"> High-performance conversational AI engine powered by Google Gemini.\n"
                    f"> Fast async execution (~800ms) with 10 distinct personalities, natural automatic channel conversations, and real-time reachability diagnostics."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"**Available Personalities (10 Total):**\n"
                f"> 🌸 `girlfriend` • 💅 `baddie` • 😈 `special` (Restricted) • 🤝 `friendly` • 🎭 `funny`\n"
                f"> 🔥 `savage` • ⚡ `anime` • ⛩️ `aizen` • 🌟 `friend` • ⚙️ `custom`\n\n"
                f"**Core AI Commands & Syntax:**\n"
                f"• `{p}ai <message>` — Direct conversation with active personality\n"
                f"• `{p}ai personalities` — Browse all 10 personalities with interactive selector\n"
                f"• `{p}ai persona <name>` — Switch active personality for channel/server\n"
                f"• `{p}ai setup [#channel]` — (Admin) Enable automatic natural chat in channel\n"
                f"• `{p}ai status` — View active AI channel configuration\n"
                f"• `{p}ai disable` / `{p}ai remove` — Pause or delete channel configuration\n"
                f"• `{p}ai reset` — Clear your personal conversation memory\n"
                f"• `{p}ai settings` — (Admin) Configure mention_only, gifs, and cooldowns\n"
                f"• `{p}aidiag` — Real-time performance & provider latency diagnostics\n"
                f"• `{p}aigf`, `{p}aibaddie`, `{p}aispecial` — Direct shortcuts\n\n"
                f"**Cooldown & Rate Controls:**\n"
                f"> Direct AI: `3s` per user | Automatic Channel: `2s` throttle | Provider: Semaphored"
            )
            container.add_separator(divider=True)

        elif cat_name == "🏠・GETTING STARTED":
            container.add_section(
                content=(
                    f"**{cat_icon_prefix}GETTING STARTED & ONBOARDING**\n"
                    f"> Beginner-friendly setup tools designed to make server configuration instant and effortless."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"**Essential Setup Commands:**\n"
                f"• `{p}start` — Interactive beginner introduction and next steps guide\n"
                f"• `{p}quickstart` — 5-minute setup checklist for new server administrators\n"
                f"• `{p}setup` — Master interactive server configuration wizard\n"
                f"• `{p}setup status` — Audit which features are currently configured vs unconfigured\n"
                f"• `{p}setup welcome #channel` — Set automatic welcome cards and greeting messages\n"
                f"• `{p}setup goodbye #channel` — Set member departure farewell channel\n"
                f"• `{p}setup logs #channel` — Set moderation audit logging\n"
                f"• `{p}setup suggestions #channel` — Enable member suggestions with voting buttons\n"
                f"• `{p}setup autorole @role` — Assign role automatically upon member join\n"
                f"• `{p}setup tickets #channel` — Dispatch interactive support ticket panel\n"
                f"• `{p}setup levels #channel` — Set level-up celebration alert channel\n"
                f"• `{p}setup ai #channel` — Enable natural hands-free AI conversations\n"
                f"• `{p}setup reset` — Reset specific configuration modules safely with confirmation"
            )
            container.add_separator(divider=True)

        else:
            container.add_section(
                content=(
                    f"**{cat_icon_prefix}{cat_name} Commands**\n"
                    f"> Listing `{len(commands_list)}` accessible command(s) for your role in this server."
                )
            )
            container.add_separator(divider=True)

        sorted_cmds = sorted(commands_list, key=lambda c: c.qualified_name.lower())

        # Render rich command cards with syntax, descriptions, and permission badges
        cmd_blocks: list[str] = []
        for cmd in sorted_cmds[:16]:
            sig = f" {cmd.signature}" if cmd.signature else ""
            desc = (cmd.description or cmd.help or "No detailed description provided.").strip().split("\n")[0][:110]
            badge = self._get_badge(cmd)
            aliases = f" • Aliases: {', '.join([f'`{a}`' for a in cmd.aliases[:3]])}" if cmd.aliases else ""
            access = f" • Access: {badge}" if badge else ""

            cmd_blocks.append(
                f"`{cmd.name}` — {desc}\n"
                f"Usage: `{p}{cmd.qualified_name}{sig}`{aliases}{access}"
            )

        formatted_text = "\n\n".join(cmd_blocks)
        if len(sorted_cmds) > 16:
            remaining = sorted_cmds[16:]
            formatted_text += f"\n\n**Additional Accessible Commands ({len(remaining)}):**\n" + ", ".join([f"`{c.qualified_name}`" for c in remaining])

        container.add_text(formatted_text)
        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name} • Type {p}help <command> for syntax & examples**")
        return container

    def build_home_embed(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
    ) -> discord.Embed:
        """Construct compact, clean Default Help Embed matching Kyro specification."""
        guild = ctx.guild
        author = ctx.author
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())

        branding = None
        if hasattr(self.bot, "branding_mgr"):
            mgr = getattr(self.bot, "branding_mgr", None)
            if hasattr(mgr, "_cache") and isinstance(mgr._cache, dict):
                branding = mgr._cache.get(guild.id if guild else None)
            if not isinstance(branding, dict) and hasattr(mgr, "get_default_branding") and callable(mgr.get_default_branding):
                branding = mgr.get_default_branding()
        if not isinstance(branding, dict):
            assets = getattr(Config, "ASSETS", None)
            branding = {
                "display_name": "Kyoka 3.0",
                "bio": "Built for our community — keeping your server safe, active, and effortlessly connected.",
                "avatar_url": getattr(assets, "AIZEN_AVATAR_URL", "") or (self.bot.user.display_avatar.url if getattr(self.bot, "user", None) else ""),
                "banner_url": "",
            }

        raw_display = branding.get("display_name") if isinstance(branding, dict) else None
        display_name = raw_display if isinstance(raw_display, str) and raw_display.strip() else "Kyoka 3.0"
        raw_bio = branding.get("bio") if isinstance(branding, dict) else None
        bio = raw_bio if isinstance(raw_bio, str) and raw_bio.strip() else "Built for our community — keeping your server safe, active, and effortlessly connected."

        # Compact category directory
        cat_labels = []
        for cat_name in visible_categories.keys():
            clean = cat_name.split("・", 1)[-1].strip().title() if "・" in cat_name else cat_name.strip().title()
            cat_labels.append(f"`{clean}`")
        categories_line = " · ".join(cat_labels)

        desc = (
            f"> {bio}\n\n"
            f"• **Latency:** `{ws_ping}ms`\n"
            f"• **Prefix:** `{p}` | **Slash:** `/`\n"
            f"• **Available Commands:** `{total_commands}`\n\n"
            f"📁 **Command Modules ({len(visible_categories)}):**\n"
            f"{categories_line}\n\n"
            f"⚡ **Essential Commands:**\n"
            f"`{p}help` · `{p}play` · `{p}ai` · `{p}ticket` · `{p}setup` · `{p}botedit`"
        )

        embed = KyokaHelpEmbed(
            title=f"Hey, I'm {display_name}",
            description=desc,
            color=0x2B0938,
        )

        avatar_url = branding.get("avatar_url") if isinstance(branding, dict) else None
        if avatar_url and str(avatar_url).strip():
            embed.set_thumbnail(url=str(avatar_url).strip())

        banner_url = branding.get("banner_url") if isinstance(branding, dict) else None
        if banner_url and str(banner_url).strip():
            embed.set_image(url=str(banner_url).strip())

        embed.set_footer(
            text=f"Requested by {author.display_name}",
            icon_url=author.display_avatar.url if author and author.display_avatar else None,
        )
        embed.banner_file = None
        return embed

    def build_search_results_embed(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        query: str,
    ) -> discord.Embed:
        """Construct interactive search results embed matching commands against user query."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        clean_query = query.lower().strip()

        matched: list[tuple[commands.Command, str]] = []
        for cat_name, cmd_list in visible_categories.items():
            for cmd in cmd_list:
                cname = cmd.qualified_name.lower()
                desc = (cmd.description or cmd.help or "").lower()
                aliases = [a.lower() for a in getattr(cmd, "aliases", [])]
                if clean_query == cname or clean_query in cname or any(clean_query in a for a in aliases) or clean_query in desc:
                    matched.append((cmd, cat_name))

        embed = discord.Embed(
            title=f"🔍 Search Results for: `{clean_query}`",
            color=0x2B0938,
        )

        if not matched:
            embed.description = (
                f"> No accessible commands matching **`{clean_query}`** were found.\n\n"
                f"**Suggestions:**\n"
                f"• Try a broader search term (e.g., `mod`, `role`, `ai`, `music`, `level`)\n"
                f"• Use the dropdown category menu below to browse all available commands\n"
                f"• Click **🏠 Home** to return to the main console overview"
            )
            embed.color = 0xED4245
        else:
            embed.description = f"Found **{len(matched)}** accessible command(s) matching `{clean_query}`:\n\n"
            matched.sort(
                key=lambda item: (
                    0 if item[0].qualified_name.lower() == clean_query else (
                        1 if item[0].qualified_name.lower().startswith(clean_query) else 2
                    ),
                    item[0].qualified_name.lower(),
                )
            )

            for cmd, cat in matched[:10]:
                badge = self._get_badge(cmd)
                desc = (cmd.description or cmd.help or "No detailed description provided.").strip().split("\n")[0][:110]
                sig = f" {cmd.signature}" if cmd.signature else ""
                embed.add_field(
                    name=f"`{p}{cmd.qualified_name}{sig}`{badge}",
                    value=f"> {desc}\n> *Category: {cat}*",
                    inline=False,
                )

            if len(matched) > 10:
                embed.description += f"*(Showing top 10 of {len(matched)} matches. Refine your query for more precise results.)*\n\n"

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Type {p}help <command> for full manual",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

    def build_category_embed(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        page: int = 1,
    ) -> discord.Embed:
        """Construct compact, clean category embed (10 commands per page, single line descriptions)."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)

        clean_cat_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"Accessible commands for {clean_cat_title}.")

        # Retrieve guild branding for avatar
        branding = None
        if hasattr(self.bot, "branding_mgr"):
            branding = self.bot.branding_mgr._cache.get(guild.id if guild else None)
        avatar_url = branding.get("avatar_url") if branding else None
        if not avatar_url and hasattr(self.bot, "user") and self.bot.user:
            avatar_url = self.bot.user.display_avatar.url

        # Collect unique command names
        seen: set[str] = set()
        unique_cmds: list[commands.Command] = []
        for c in commands_list:
            if c.qualified_name not in seen:
                seen.add(c.qualified_name)
                unique_cmds.append(c)
        unique_cmds.sort(key=lambda c: c.qualified_name)

        per_page = 10
        total_pages = max(1, math.ceil(len(unique_cmds) / per_page))
        safe_page = max(1, min(page, total_pages))
        start_idx = (safe_page - 1) * per_page
        page_cmds = unique_cmds[start_idx : start_idx + per_page]

        desc_lines = [
            f"> *{cat_desc}*\n",
            f"**Page {safe_page}/{total_pages}** • **{len(unique_cmds)}** commands\n",
        ]
        for c in page_cmds:
            desc_text = (c.description or getattr(c, "help", None) or "No description provided.").strip().split("\n")[0][:90]
            c_name = c.qualified_name if isinstance(getattr(c, "qualified_name", None), str) else (c.name if isinstance(getattr(c, "name", None), str) else str(c))
            desc_lines.append(f"• **`{c_name}`** — {desc_text}")

        desc_lines.append(f"\n`{p}help <command>` — View details for one command.")

        embed = KyokaHelpEmbed(
            title=f"{self._get_category_emoji(cat_name)} {cat_name}",
            description="\n".join(desc_lines),
            color=0x2B0938,
        )

        embed.banner_file = None

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        banner_url = branding.get("banner_url") if branding else None
        if banner_url and str(banner_url).strip():
            embed.set_image(url=str(banner_url).strip())

        embed.set_footer(
            text=f"Page {safe_page}/{total_pages} • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author and ctx.author.display_avatar else None,
        )
        return embed

    def build_command_embed(self, ctx: CustomContext, cmd: commands.Command) -> discord.Embed:
        """Construct compact, clean single-command manual embed."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        cat = self._resolve_category(cmd)
        cat_icon = self._get_category_emoji(cat)
        desc = (cmd.description or cmd.help or "No detailed description provided.").strip()
        aliases = ", ".join([f"`{a}`" for a in cmd.aliases]) if cmd.aliases else "`None`"
        sig = f" {cmd.signature}" if cmd.signature else ""
        usage = f"`{p}{cmd.qualified_name}{sig}`"
        example = f"`{p}{cmd.qualified_name}`"

        badge = self._get_badge(cmd)
        status_str = badge.strip(" `[]") if badge else "Public"

        is_hybrid = isinstance(cmd, commands.HybridCommand) or getattr(cmd, "app_command", None) is not None
        slash_syntax = f"`/{cmd.qualified_name}`" if is_hybrid else "N/A"

        embed = discord.Embed(
            title=f"{cat_icon} Command: `{cmd.qualified_name}`",
            description=f"> {desc}",
            color=0x2B0938,
        )

        embed.add_field(
            name="📝 Usage & Example",
            value=(
                f"• **Usage:** {usage}\n"
                f"• **Prefix Example:** {example}\n"
                + (f"• **Slash Example:** {slash_syntax}\n" if is_hybrid else "")
            ),
            inline=False,
        )

        embed.add_field(
            name="📋 Command Details",
            value=(
                f"• **Category:** `{cat}`\n"
                f"• **Aliases:** {aliases}\n"
                f"• **Required Permissions:** `{status_str}`"
            ),
            inline=False,
        )

        if isinstance(cmd, commands.Group) and cmd.commands:
            subcmds = ", ".join([f"`{sc.name}`" for sc in sorted(cmd.commands, key=lambda s: s.name)])
            embed.add_field(
                name="📂 Subcommands",
                value=subcmds,
                inline=False,
            )

        branding = None
        if hasattr(self.bot, "branding_mgr"):
            branding = self.bot.branding_mgr._cache.get(guild.id if guild else None)
        avatar_url = branding.get("avatar_url") if branding else None
        if not avatar_url and hasattr(self.bot, "user") and self.bot.user:
            avatar_url = self.bot.user.display_avatar.url
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        banner_url = branding.get("banner_url") if branding else None
        if banner_url and str(banner_url).strip():
            embed.set_image(url=str(banner_url).strip())

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Type {p}help to return",
            icon_url=ctx.author.display_avatar.url if ctx.author and ctx.author.display_avatar else None,
        )
        return embed

    def build_embed_for_selection(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        selected_val: str,
        page: int = 1,
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Route selection value to corresponding category or home embed with artwork."""
        if selected_val == "home":
            embed = self.build_home_embed(ctx, visible_categories)
            return embed, getattr(embed, "banner_file", None)
        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            embed = self.build_category_embed(
                ctx, matched_cat, visible_categories[matched_cat], visible_categories, page=page
            )
            return embed, getattr(embed, "banner_file", None)
        embed = self.build_home_embed(ctx, visible_categories)
        return embed, getattr(embed, "banner_file", None)

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules", "h"],
        description="Display the Kyoka command directory tailored to your permissions.",
    )
    async def help_command(self, ctx: CustomContext, *, command_or_module: str | None = None) -> None:
        """Interactive help menu filtered by user permissions and organized into categories."""
        t_start = time.perf_counter()
        if hasattr(self.bot, "branding_mgr"):
            await self.bot.branding_mgr.get_branding(ctx.guild.id if ctx.guild else None)
        visible_categories = await self._get_visible_categories(ctx)
        t_categories = time.perf_counter()

        # Direct command or module lookup
        if command_or_module:
            query = command_or_module.lower().strip()

            target_cmd = self.bot.get_command(query)
            if target_cmd and self._can_run_command(target_cmd, ctx):
                embed = self.build_command_embed(ctx, target_cmd)
                await ctx.send(embed=embed)
                return

            # Direct module / category lookup
            target_cat_name = self.CATEGORY_ALIASES.get(query)
            if not target_cat_name:
                cat_meta = get_category_by_query(query)
                if cat_meta and cat_meta.tag in visible_categories:
                    target_cat_name = cat_meta.tag
                else:
                    target_cat_name = next(
                        (c for c in visible_categories.keys() if c.lower() == query or query in c.lower()),
                        None,
                    )

            if target_cat_name:
                matched_cat = next((c for c in visible_categories.keys() if c.lower() == target_cat_name.lower()), None)
                if matched_cat:
                    view = HelpView(
                        cog=self,
                        ctx=ctx,
                        visible_categories=visible_categories,
                        current_category=matched_cat,
                    )
                    embed = self.build_category_embed(ctx, matched_cat, visible_categories[matched_cat], visible_categories)
                    banner_file = getattr(embed, "banner_file", None)
                    if banner_file:
                        msg = await ctx.send(embed=embed, file=banner_file, view=view)
                    else:
                        msg = await ctx.send(embed=embed, view=view)
                    if getattr(ctx, "interaction", None):
                        try:
                            view.message = await ctx.interaction.original_response()
                        except Exception:
                            pass
                    else:
                        view.message = msg
                    return

            # Command or category not found — return clear error and attach HelpView
            p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
            embed = discord.Embed(
                title="❌ Command or Category Not Found",
                description=(
                    f"No command or category matching **`{command_or_module}`** was found.\n\n"
                    f"**Suggestions:**\n"
                    f"• Browse all categories using the dropdown menu below\n"
                    f"• Type `{p}help` to view the main console overview\n"
                    f"• Type `{p}hca` for the complete public command archive"
                ),
                color=0xED4245,
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.display_name} • Kyoka 3.0",
                icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
            )
            view = HelpView(
                cog=self,
                ctx=ctx,
                visible_categories=visible_categories,
                current_category="home",
            )
            msg = await ctx.send(embed=embed, view=view)
            if getattr(ctx, "interaction", None):
                try:
                    view.message = await ctx.interaction.original_response()
                except Exception:
                    pass
            else:
                view.message = msg
            return

        # Main Help Console (Home Overview)
        view = HelpView(
            cog=self,
            ctx=ctx,
            visible_categories=visible_categories,
            current_category="home",
        )
        embed = self.build_home_embed(ctx, visible_categories)
        t_embed = time.perf_counter()
        banner_file = getattr(embed, "banner_file", None)
        if banner_file:
            msg = await ctx.send(embed=embed, file=banner_file, view=view)
        else:
            msg = await ctx.send(embed=embed, view=view)
        t_send = time.perf_counter()

        logger.info(
            f"⚡ [Help Timing] Total: {(t_send - t_start)*1000:.1f}ms | "
            f"Categories: {(t_categories - t_start)*1000:.1f}ms | "
            f"Embed: {(t_embed - t_categories)*1000:.1f}ms | "
            f"Send: {(t_send - t_embed)*1000:.1f}ms"
        )

        if getattr(ctx, "interaction", None):
            try:
                view.message = await ctx.interaction.original_response()
            except Exception:
                pass
        else:
            view.message = msg

    @commands.command(
        name="premium",
        aliases=["plan", "tier", "subscription", "perks"],
        description="View this server's subscription plan, expiry, and Free vs Premium feature matrix.",
    )
    async def view_plan(self, ctx: CustomContext) -> None:
        """Display this server's current tier and the comprehensive Free vs Premium feature matrix."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)

        is_prem = False
        expiry_str = "N/A (Standard Free)"
        tier_title = "Standard Free Tier"
        if guild and hasattr(self.bot, "premium_mgr") and self.bot.premium_mgr:
            is_prem = self.bot.premium_mgr.is_guild_premium(guild.id)
            if is_prem:
                info = self.bot.premium_mgr.get_guild_info(guild.id)
                tier_title = f"💎 Kyoka {info.get('tier', 'Premium')}"
                expiry_str = info.get("remaining_str", "Active")

        embed = discord.Embed(
            title="⛩️ KYOKA 3.0 • PLAN & FEATURE ACCESS MATRIX",
            description=(
                f"**Current Server:** `{guild.name if guild else 'Direct Message'}`\n"
                f"**Active Entitlement:** `{tier_title}`\n"
                f"**Status / Expiry:** `{expiry_str}`\n\n"
                f"> Kyoka separates core server stability features (free to all servers) from advanced visual and enterprise customization (premium)."
            ),
            color=0x7C3AED,
        )

        embed.add_field(
            name="🛡️ FREE TIER (Available to Every Server)",
            value=(
                "• **Core Moderation:** `ban`, `kick`, `timeout`, `warn`, `purge`, `lock`, `unlock`, `slowmode`\n"
                "• **Utility & Info:** `calc`, `remind`, `avatar`, `banner`, `userinfo`, `serverinfo`, `ping`\n"
                "• **Welcome & Departures:** Standard welcome cards, leave announcements, autoroles\n"
                "• **Gatekeeper Security:** Button and captcha verification gate\n"
                "• **Support Tickets:** Standard ticket panel, claims, and closures\n"
                "• **Giveaways:** Timers, automatic roll, and winner rerolls\n"
                "• **Audio Playback:** High-fidelity Lavalink v4 music player\n"
                "• **Community & Fun:** AFK notices, anime actions, 8ball, trivia, truth-or-dare\n"
                "• **Server Administration:** Isolated single prefix (`setprefix`, `resetprefix`)"
            ),
            inline=False,
        )

        embed.add_field(
            name="💎 PREMIUM TIER (Requires Server Subscription)",
            value=(
                "• **Custom Bot Avatar:** Upload custom server-specific avatar (`setbotavatar`)\n"
                "• **24/7 Music Radio:** Continuous voice stay mode that never disconnects (`247`, `halloween`)\n"
                "• **Aizen Visual Palette:** Custom hex embed colors and server author icons\n"
                "• **Animated Welcome Cards:** Cyber Sakura, Celestial Nebula & Hueco Mundo themes\n"
                "• **Multi-Panel Tickets:** Multi-department routing and HTML transcripts\n"
                "• **Role-Gated Giveaways:** Bonus entries, bypass roles, and multi-winner raffles\n"
                "• **Priority Gemini AI:** ~600ms latency, all 10 AI personas simultaneously\n"
                "• **Extended Leveling:** Custom rank card backgrounds and XP multipliers\n"
                "• **Modular Logging:** Anti-ghostping tracking and dedicated channel routing"
            ),
            inline=False,
        )

        assets = getattr(Config, "ASSETS", None)
        thumb = getattr(assets, "AIZEN_AVATAR_URL", "")
        if thumb and thumb.strip():
            embed.set_thumbnail(url=thumb.strip())

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • KYOKA 3.0 — Aizen Edition",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )

        view = discord.ui.View(timeout=180.0)
        view.add_item(
            discord.ui.Button(
                label="Upgrade to Premium",
                style=discord.ButtonStyle.link,
                url="https://aizen-bot.pages.dev/premium",
                emoji="💎",
            )
        )
        if Config.SUPPORT_URL:
            view.add_item(
                discord.ui.Button(
                    label="Join Support Server",
                    style=discord.ButtonStyle.link,
                    url=Config.SUPPORT_URL,
                    emoji="💜",
                )
            )
        view.add_item(
            discord.ui.Button(
                label="Web Dashboard",
                style=discord.ButtonStyle.link,
                url="https://aizen-bot.pages.dev/dashboard",
                emoji="⚡",
            )
        )

        await ctx.send(embed=embed, view=view)

    # ─── HELP COMMAND ARCHIVE (HCA) PUBLIC DIRECTORY ─────────────────────────
    def build_hca_index_embed(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Construct the master Help Command Archive (HCA) index directory embed with Aizen artwork."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        total_commands = sum(len(cmds) for cmds in all_categories.values())

        embed = discord.Embed(
            title="📚 KYOKA 3.0 — Help Command Archive (HCA)",
            description=(
                "> **Complete Public Command Directory & Architecture Index**\n"
                "> Accessible to every server member. Explore all loaded features, aliases, and syntax.\n\n"
                f"• **Global Prefix:** `{p}<command>` · **Slash Support:** `/<command>`\n"
                f"• **Total Commands:** `{total_commands}` across `{len(all_categories)}` active modules\n"
                f"• **Legend:** `[+]` Prefix · `[/]` Slash · `[Public]` Everyone · `[Mod]` Staff · `[Admin]` Admin · `[Owner]` Dev\n\n"
                f"💡 *Select a module from the dropdown or click **Search** to find any command.*"
            ),
            color=0x2B0938,
        )

        for cat_name, cmds in list(all_categories.items())[:12]:
            clean_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            cat_icon = self._get_category_emoji(cat_name)
            preview_names = [f"`{c.name}`" for c in cmds[:4]]
            preview_str = ", ".join(preview_names)
            if len(cmds) > 4:
                preview_str += f", +{len(cmds) - 4} more"
            embed.add_field(
                name=f"{cat_icon} {clean_title} ({len(cmds)})",
                value=f"> {preview_str}",
                inline=True,
            )

        banner_file = AssetManager.attach_help_banner(embed, "home")
        embed.set_footer(
            text=f"Help Command Archive (HCA) • Requested by {ctx.author.display_name} • Type {p}hca <module>",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed, banner_file

    def build_hca_category_embed(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        all_categories: dict[str, list[commands.Command]],
        page: int = 1,
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Construct a paginated category archive card for HCA with distinct feature artwork."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        clean_cat_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"All registered commands for {clean_cat_title}.")
        cat_icon = self._get_category_emoji(cat_name)
        cat_meta = CATEGORY_BY_TAG.get(cat_name) or get_category_by_query(clean_cat_title)

        seen: set[str] = set()
        unique_cmds: list[commands.Command] = []
        for c in commands_list:
            if c.qualified_name not in seen:
                seen.add(c.qualified_name)
                unique_cmds.append(c)
        unique_cmds.sort(key=lambda c: c.qualified_name)

        per_page = 10
        total_pages = max(1, math.ceil(len(unique_cmds) / per_page))
        safe_page = max(1, min(page, total_pages))
        start_idx = (safe_page - 1) * per_page
        page_cmds = unique_cmds[start_idx : start_idx + per_page]

        desc_lines = [
            f"> {cat_desc}\n",
            f"**Category:** `{cat_name}` • **Page {safe_page}/{total_pages}** • **{len(unique_cmds)}** total commands\n",
        ]

        for c in page_cmds:
            badge = self._get_badge(c) or " `[Public]`"
            is_slash = getattr(c, "app_command", None) is not None or hasattr(c, "app_command")
            type_tag = "`[+ /]`" if is_slash else "`[+]`"
            sig = f" {c.signature}" if c.signature else ""
            desc = (c.description or getattr(c, "help", None) or "No detailed description provided.").strip().split("\n")[0][:90]
            alias_str = f" · *Aliases:* {', '.join(f'`{a}`' for a in c.aliases)}" if c.aliases else ""
            desc_lines.append(f"**`{p}{c.qualified_name}{sig}`** {type_tag}{badge}")
            desc_lines.append(f"> {desc}{alias_str}\n")

        embed = discord.Embed(
            title=f"{cat_icon} Archive — {cat_name}",
            description="\n".join(desc_lines),
            color=0x2B0938,
        )
        image_key = cat_meta.image_key if cat_meta else "general"
        banner_file = AssetManager.attach_help_banner(embed, image_key)
        embed.set_footer(
            text=f"Page {safe_page}/{total_pages} • {len(unique_cmds)} Commands • Public Archive • KYOKA 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed, banner_file

    def build_hca_search_embed(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
        query: str,
    ) -> discord.Embed:
        """Construct search results embed for the Help Command Archive."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        clean_query = query.lower().strip()

        matched: list[tuple[commands.Command, str]] = []
        for cat_name, cmd_list in all_categories.items():
            for cmd in cmd_list:
                cname = cmd.qualified_name.lower()
                desc = (cmd.description or cmd.help or "").lower()
                aliases = [a.lower() for a in getattr(cmd, "aliases", [])]
                if clean_query == cname or clean_query in cname or any(clean_query in a for a in aliases) or clean_query in desc:
                    if (cmd, cat_name) not in matched:
                        matched.append((cmd, cat_name))

        embed = discord.Embed(
            title=f"🔍 Archive Search Results: `{clean_query}`",
            color=0x2B0938,
        )

        if not matched:
            embed.description = (
                f"> No registered commands matching **`{clean_query}`** were found in the archive.\n\n"
                f"**Suggestions:**\n"
                f"• Try keywords: `music`, `ban`, `ticket`, `fruit`, `voice`, `bill`, `level`\n"
                f"• Use the dropdown category selector to browse the entire directory\n"
                f"• Type `{p}hca` to view the master index"
            )
            embed.color = 0xED4245
        else:
            embed.description = f"Found **{len(matched)}** command(s) matching `{clean_query}`:\n\n"
            matched.sort(
                key=lambda item: (
                    0 if item[0].qualified_name.lower() == clean_query else (
                        1 if item[0].qualified_name.lower().startswith(clean_query) else 2
                    ),
                    item[0].qualified_name.lower(),
                )
            )

            for cmd, cat in matched[:10]:
                badge = self._get_badge(cmd) or " `[Public]`"
                is_slash = getattr(cmd, "app_command", None) is not None or hasattr(cmd, "app_command")
                type_tag = "`[+ /]`" if is_slash else "`[+]`"
                desc = (cmd.description or cmd.help or "No description.").strip().split("\n")[0][:100]
                sig = f" {cmd.signature}" if cmd.signature else ""
                embed.add_field(
                    name=f"`{p}{cmd.qualified_name}{sig}` {type_tag}{badge}",
                    value=f"> {desc}\n> *Module:* {cat}",
                    inline=False,
                )

            if len(matched) > 10:
                embed.description += f"*(Showing top 10 of {len(matched)} matches.)*\n\n"

        AssetManager.attach_help_banner(embed, "home")
        embed.set_footer(
            text=f"Archive Search • Requested by {ctx.author.display_name} • KYOKA 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

    def build_hca_embed_for_selection(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
        selected_val: str,
        page: int = 1,
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Route HCA selection to index or category embed with artwork."""
        if selected_val == "home":
            return self.build_hca_index_embed(ctx, all_categories)
        matched_cat = next((c for c in all_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            return self.build_hca_category_embed(
                ctx, matched_cat, all_categories[matched_cat], all_categories, page=page
            )
        return self.build_hca_index_embed(ctx, all_categories)

    @commands.command(
        name="hca",
        aliases=["archive", "allcommands", "directory", "cmds"],
        description="Public all-commands directory and architecture archive for Kyoka 3.0.",
    )
    async def hca_command(self, ctx: CustomContext, *, category: str | None = None) -> None:
        """Browse all registered prefix and slash commands across all bot modules. Open to everyone."""
        all_categories = await self._get_all_registered_categories(ctx)
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        if category:
            query = category.lower().strip()
            cat_meta = get_category_by_query(query)
            target_cat = None
            if cat_meta and cat_meta.tag in all_categories:
                target_cat = cat_meta.tag
            else:
                target_cat = next(
                    (c for c in all_categories.keys() if query in c.lower() or c.lower().endswith(query)),
                    None,
                )

            if target_cat and target_cat in all_categories:
                view = HCAView(
                    cog=self,
                    ctx=ctx,
                    all_categories=all_categories,
                    current_category=target_cat,
                    current_page=1,
                )
                embed, banner_file = self.build_hca_category_embed(
                    ctx, target_cat, all_categories[target_cat], all_categories, page=1
                )
                if banner_file:
                    msg = await ctx.send(embed=embed, file=banner_file, view=view)
                else:
                    msg = await ctx.send(embed=embed, view=view)
                if getattr(ctx, "interaction", None):
                    try:
                        view.message = await ctx.interaction.original_response()
                    except Exception:
                        pass
                else:
                    view.message = msg
                return

            # Category not found - show error and list available categories
            available_list = [f"`{c.split('・', 1)[-1].lower().strip()}`" for c in all_categories.keys()]
            embed = discord.Embed(
                title="❌ Archive Category Not Found",
                description=(
                    f"No category matching **`{category}`** was found in the archive.\n\n"
                    f"**Available Categories:**\n"
                    f"> {', '.join(available_list)}\n\n"
                    f"**Usage Examples:**\n"
                    f"• `{p}hca music` — View all Music commands\n"
                    f"• `{p}hca tickets` — View all Ticket & Support commands\n"
                    f"• `{p}hca bloxai` — View Blox Fruits AI & Web commands\n"
                    f"• `{p}hca ai` — View AI and Voice commands\n"
                    f"• `{p}hca` — Open the master Archive Index"
                ),
                color=0xED4245,
            )
            view = HCAView(
                cog=self,
                ctx=ctx,
                all_categories=all_categories,
                current_category="home",
                current_page=1,
            )
            msg = await ctx.send(embed=embed, view=view)
            if getattr(ctx, "interaction", None):
                try:
                    view.message = await ctx.interaction.original_response()
                except Exception:
                    pass
            else:
                view.message = msg
            return

        # Main HCA Index
        view = HCAView(
            cog=self,
            ctx=ctx,
            all_categories=all_categories,
            current_category="home",
            current_page=1,
        )
        embed, banner_file = self.build_hca_index_embed(ctx, all_categories)
        if banner_file:
            msg = await ctx.send(embed=embed, file=banner_file, view=view)
        else:
            msg = await ctx.send(embed=embed, view=view)
        if getattr(ctx, "interaction", None):
            try:
                view.message = await ctx.interaction.original_response()
            except Exception:
                pass
        else:
            view.message = msg

    @commands.command(
        name="helpdiag",
        aliases=["categorydiag", "cmdstatus"],
        description="Run comprehensive category classification & command tree diagnostics.",
    )
    async def help_diagnostics(self, ctx: CustomContext) -> None:
        """Run diagnostic audit across all registered prefix and slash commands."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        all_categories = await self._get_all_registered_categories(ctx)

        total_cmds = sum(len(c) for c in all_categories.values())
        missing_desc: list[str] = []
        music_cmds = [c.name for c in all_categories.get("🎵・MUSIC", [])]
        ai_cmds = [c.name for c in all_categories.get("🤖・ARTIFICIAL INTELLIGENCE", [])]

        for cat, cmds in all_categories.items():
            for cmd in cmds:
                desc = cmd.description or getattr(cmd, "help", None)
                if not desc:
                    missing_desc.append(cmd.qualified_name)

        # Audit AI vs Music leak
        ai_in_music = [c for c in music_cmds if c in ("aivoice", "voicespeak", "voiceask", "speak", "voicejoin")]

        embed = discord.Embed(
            title="🔬 Kyoka 3.0 — Help & Category Diagnostics",
            description=(
                f"> **System Health:** Category Classification Engine active\n"
                f"> **Total Registered Commands:** `{total_cmds}` across `{len(all_categories)}` categories\n"
                f"> **AI Leaks in Music:** `{len(ai_in_music)}` {'(CLEAN ✅)' if not ai_in_music else '(LEAK ❌)'}\n"
                f"> **Missing Descriptions:** `{len(missing_desc)}`"
            ),
            color=0x10B981 if not ai_in_music else 0xEF4444,
        )

        embed.add_field(
            name="🎵 Music Module Commands",
            value=", ".join(f"`{c}`" for c in music_cmds[:15]) + (f" +{len(music_cmds)-15} more" if len(music_cmds) > 15 else ""),
            inline=False,
        )
        embed.add_field(
            name="🤖 AI Module Commands",
            value=", ".join(f"`{c}`" for c in ai_cmds[:15]) + (f" +{len(ai_cmds)-15} more" if len(ai_cmds) > 15 else ""),
            inline=False,
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name} • KYOKA 3.0 Diagnostics")
        await ctx.send(embed=embed)

    # ─── CUSTOM HELP CATEGORIES ADMINISTRATION ────────────────────────────────
    @commands.group(
        name="customhelp",
        aliases=["chelp"],
        invoke_without_command=True,
        description="Manage custom help categories for your server without code changes.",
    )
    @commands.has_permissions(administrator=True)
    async def customhelp(self, ctx: CustomContext) -> None:
        """Overview of custom help category management commands."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        embed = discord.Embed(
            title="⚙️ Custom Help Categories Manager",
            description=(
                "Customize your server's help menu and categories dynamically.\n\n"
                f"• `{p}customhelp create <name> [emoji] [description]` — Create a new category\n"
                f"• `{p}customhelp rename <old_name> <new_name>` — Rename an existing category\n"
                f"• `{p}customhelp emoji <name> <emoji>` — Update the icon/emoji\n"
                f"• `{p}customhelp add <category> <command>` — Add a registered command to category\n"
                f"• `{p}customhelp remove <category> <command>` — Remove a command from category\n"
                f"• `{p}customhelp hide <category>` — Hide category from help menu\n"
                f"• `{p}customhelp show <category>` — Show category in help menu\n"
                f"• `{p}customhelp delete <category>` — Delete a custom category\n"
                f"• `{p}customhelp list` — List all custom categories and their commands\n"
                f"• `{p}customhelp reset` — Reset custom categories to defaults"
            ),
            color=0x2B0938,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Administrator Only")
        await ctx.send(embed=embed)

    @customhelp.command(name="create", description="Create a new custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_create(
        self, ctx: CustomContext, name: str, emoji: str = "📁", *, description: str = "Custom server commands"
    ) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.create_category(
            ctx.guild.id, name, emoji=emoji, description=description
        )
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="rename", description="Rename an existing custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_rename(self, ctx: CustomContext, old_name: str, new_name: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.rename_category(ctx.guild.id, old_name, new_name)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="emoji", description="Set icon or emoji for a custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_emoji(self, ctx: CustomContext, name: str, emoji: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.set_emoji(ctx.guild.id, name, emoji)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="add", description="Add a registered command to a custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_add(self, ctx: CustomContext, category_name: str, command_name: str) -> None:
        if not ctx.guild:
            return
        all_cmds = {c.qualified_name.lower() for c in self.bot.commands}
        owner_cmds = {
            "spam", "spamcancel", "guesshostadd", "guesshostremove", "guesshosts",
            "eval", "exec", "restart", "shutdown", "sync", "leaveserver", "blacklist",
            "whitelistuser", "errors", "validateconfig", "maintenance", "systemstatus",
            "dbstatus", "extstatus",
        }
        success, msg = await self.bot.custom_help_mgr.add_command(
            ctx.guild.id, category_name, command_name, all_cmds, owner_cmds
        )
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="remove", description="Remove a command from a custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_remove(self, ctx: CustomContext, category_name: str, command_name: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.remove_command(ctx.guild.id, category_name, command_name)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="hide", description="Hide a custom category from the help menu.")
    @commands.has_permissions(administrator=True)
    async def customhelp_hide(self, ctx: CustomContext, category_name: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.set_hidden(ctx.guild.id, category_name, True)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="show", description="Show a custom category in the help menu.")
    @commands.has_permissions(administrator=True)
    async def customhelp_show(self, ctx: CustomContext, category_name: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.set_hidden(ctx.guild.id, category_name, False)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="delete", description="Delete a custom help category.")
    @commands.has_permissions(administrator=True)
    async def customhelp_delete(self, ctx: CustomContext, category_name: str) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.delete_category(ctx.guild.id, category_name)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Category", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    @customhelp.command(name="list", description="List all custom help categories for this server.")
    @commands.has_permissions(administrator=True)
    async def customhelp_list(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        categories = await self.bot.custom_help_mgr.get_guild_categories(ctx.guild.id)
        if not categories:
            embed = discord.Embed(
                title="⚙️ Custom Help Categories",
                description="> No custom categories configured for this server. Use `customhelp create` to make one!",
                color=0x2B0938,
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="⚙️ Custom Help Categories",
            description=f"Found **{len(categories)}** custom category/categories for this server:\n",
            color=0x2B0938,
        )
        for cat in categories:
            cmds = cat.get("commands", [])
            cmd_preview = ", ".join(f"`{c}`" for c in cmds[:10]) if cmds else "*No commands added*"
            if len(cmds) > 10:
                cmd_preview += f" *(+{len(cmds)-10} more)*"
            status = "🔒 Hidden" if cat.get("is_hidden") else "👁️ Visible"
            embed.add_field(
                name=f"{cat.get('emoji', '📁')} {cat['category_name']} [{status}]",
                value=f"> {cat.get('description', '')}\n> **Commands ({len(cmds)}):** {cmd_preview}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @customhelp.command(name="reset", description="Reset all custom help categories to defaults.")
    @commands.has_permissions(administrator=True)
    async def customhelp_reset(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        success, msg = await self.bot.custom_help_mgr.reset_categories(ctx.guild.id)
        color = 0x2B0938 if success else 0xED4245
        embed = discord.Embed(title="Custom Help Categories Reset", description=f"> {msg}", color=color)
        await ctx.send(embed=embed)

    def audit_command_tree(self) -> dict[str, Any]:
        """
        Audit the bot's registered command tree against the centralized category registry.
        Detects:
        - Total registered commands
        - Registered commands missing from help categorization
        - Vouch commands in ⭐・VOUCHES & REPUTATION
        - Bill commands in 🧾・BLOX FRUITS SERVICE BILLS
        - Cross-contamination (e.g. AI commands in Music)
        - Commands without descriptions or usage signatures
        - Category command counts
        """
        def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
            cmd_list = [cmd_obj]
            if isinstance(cmd_obj, commands.Group):
                for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                    cmd_list.extend(_collect_all(sub_cmd))
            return cmd_list

        all_cmds: list[commands.Command] = []
        for cmd in self.bot.commands:
            for c in _collect_all(cmd):
                if c not in all_cmds:
                    all_cmds.append(c)

        for cog in self.bot.cogs.values():
            if getattr(cog, "qualified_name", "").lower() in ["errorhandler"]:
                continue
            for cmd in cog.get_commands():
                for c in _collect_all(cmd):
                    if c not in all_cmds:
                        all_cmds.append(c)

        category_distribution: dict[str, list[str]] = {}
        missing_from_help: list[str] = []
        missing_descriptions: list[str] = []
        music_contamination: list[str] = []
        vouch_commands: list[str] = []
        bill_commands: list[str] = []

        for c in all_cmds:
            tag = self._resolve_category(c)
            if not tag:
                missing_from_help.append(c.qualified_name)
                continue
            if tag not in category_distribution:
                category_distribution[tag] = []
            category_distribution[tag].append(c.qualified_name)

            if not (c.description or c.help):
                missing_descriptions.append(c.qualified_name)

            # Check cross contamination
            if tag == "🎵・MUSIC":
                qname = c.qualified_name.lower()
                cog_name = getattr(getattr(c, "cog", None), "qualified_name", "").lower()
                if "ai" in qname or "gemini" in qname or cog_name not in ("music", ""):
                    music_contamination.append(c.qualified_name)

            if tag == "⭐・VOUCHES & REPUTATION":
                vouch_commands.append(c.qualified_name)

            if tag == "🧾・BLOX FRUITS SERVICE BILLS":
                bill_commands.append(c.qualified_name)

        return {
            "total_registered": len(all_cmds),
            "total_categorized": sum(len(cmds) for cmds in category_distribution.values()),
            "missing_from_help": missing_from_help,
            "category_distribution": category_distribution,
            "missing_descriptions": missing_descriptions,
            "music_contamination": music_contamination,
            "vouch_commands": vouch_commands,
            "bill_commands": bill_commands,
            "is_complete": len(missing_from_help) == 0 and len(music_contamination) == 0,
        }


async def setup(bot: KyokaBot) -> None:
    cog = Help(bot)
    await bot.add_cog(cog)
    logger.info("⛩️ [KYOKA CONTROL] Aizen Premium Help Dashboard loaded successfully (Hybrid Prefix & Slash).")

