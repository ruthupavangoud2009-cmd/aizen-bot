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
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response
from src.utils.ui import KyokaEmbed, AizenPalette, AizenSymbols
from src.security.owner import is_primary_owner
from src.security.adult_guard import is_adult_authorized
from src.ui.cards.hero_banner import generate_kyoka_hero_banner
from src.ui.cards.hca_banner import generate_hca_banner

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Help")

HELP_COMMANDS_PER_PAGE: int = 15

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
    "⭐・LEVELS & COMMUNITY": "XP rewards, rank cards, level-up announcements & leaderboards",
    "🎵・MUSIC": "High-fidelity audio playback, queues, volume, filters & 24/7 radio",
    "💤・AFK": "Status notices, AFK reason tracking, mentions & return alerts",
    "⭐・VOUCHES & REPUTATION": "Verified member vouches, Blox Fruits trust profiles & leaderboards",
    "🧾・BLOX FRUITS SERVICE BILLS": "Blox Fruits service invoices, itemized receipts, fruits & Robux payment",
    "🍎・BLOX FRUITS AI": "Specialized Blox Fruits AI, fruit guides, trade calculator & builds",
    "🎙️・AI VOICE": "Neural Text-To-Speech, voice channel interaction, AI speech responses & diagnostics",
    "📊・LEVELING & LEADERBOARDS": "XP rewards, rank cards, level-up announcements & leaderboards",
    "🤖・ARTIFICIAL INTELLIGENCE": "Aizen Gemini AI engine, 10 personalities & auto channels",
    "🖼️・IMAGES & AVATARS": "Anime reaction GIFs, avatar grabbers, banners & memes",
    "💬・SOCIAL & FUN": "Mini-games, truth-or-dare, relationship stats & trivia",
    "💎・PREMIUM": "Kyoka Prime licenses, high-resolution AI & premium perks",
    "⚙️・SERVER ADMINISTRATION": "Prefix management, server wizards, custom help & diagnostics",
    "⚙️・SERVER CONFIGURATION": "Prefix management, server wizards, custom help & diagnostics",
    "🔧・UTILITIES": "Handy server utilities, calculators, reminders & diagnostics",
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

        super().__init__(
            placeholder="Select a module to view commands...",
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
        """Construct the view buttons and select menu."""
        self.clear_items()

        # Row 0: Dropdown
        self.add_item(
            HelpCategorySelect(
                self,
                self.visible_categories,
                current_selection=self.current_category,
            )
        )

        # Row 1: Back, Home, Next, Search, Close
        btn_back = discord.ui.Button(
            label="Back",
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
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

        btn_close = discord.ui.Button(
            label="Close",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        btn_close.callback = self.btn_close_callback
        self.add_item(btn_close)

        # Row 2: Link Buttons matching Screenshot 1
        bot_name = self.cog.bot.user.name if hasattr(self.cog.bot, "user") and self.cog.bot.user else "Kyoka"
        if Config.INVITE_URL:
            self.add_item(
                discord.ui.Button(
                    label=f"Invite {bot_name}",
                    url=Config.INVITE_URL,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )
        if Config.SUPPORT_URL:
            self.add_item(
                discord.ui.Button(
                    label="Support Server",
                    url=Config.SUPPORT_URL,
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
        """Switch current view page and refresh UI components."""
        self.current_category = selected_val
        self.current_page = 1
        self._build_components()
        embed = self.cog.build_embed_for_selection(self.ctx, self.visible_categories, selected_val, page=1)
        await interaction.response.edit_message(embed=embed, view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        """Navigate to the previous page or previous category."""
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match and self.current_page > 1:
                self.current_page -= 1
                embed = self.cog.build_embed_for_selection(
                    self.ctx, self.visible_categories, self.current_category, page=self.current_page
                )
                await interaction.response.edit_message(embed=embed, view=self)
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
                    embed = self.cog.build_embed_for_selection(
                        self.ctx, self.visible_categories, self.current_category, page=self.current_page
                    )
                    await interaction.response.edit_message(embed=embed, view=self)
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
        embed = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, selected_val, page=1)
        await interaction.response.edit_message(embed=embed, view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        if self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match and self.current_page > 1:
                self.current_page -= 1
                embed = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, self.current_category, page=self.current_page)
                await interaction.response.edit_message(embed=embed, view=self)
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
                    embed = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, self.current_category, page=self.current_page)
                    await interaction.response.edit_message(embed=embed, view=self)
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

    CATEGORY_ALIASES = {
        "start": "🏠・GETTING STARTED",
        "quickstart": "🏠・GETTING STARTED",
        "getting started": "🏠・GETTING STARTED",
        "general": "🏠・GETTING STARTED",
        "ai": "🤖・ARTIFICIAL INTELLIGENCE",
        "aizen": "🤖・ARTIFICIAL INTELLIGENCE",
        "mod": "🛡️・MODERATION",
        "moderation": "🛡️・MODERATION",
        "welcome": "👋・WELCOME & AUTOMOD",
        "goodbye": "👋・WELCOME & AUTOMOD",
        "automod": "🔒・AUTOMOD & SECURITY",
        "security": "🔒・AUTOMOD & SECURITY",
        "verify": "🛡️・VERIFICATION",
        "verification": "🛡️・VERIFICATION",
        "ticket": "🎫・TICKETS & SUPPORT",
        "tickets": "🎫・TICKETS & SUPPORT",
        "support": "🎫・TICKETS & SUPPORT",
        "giveaway": "🎉・GIVEAWAYS & EVENTS",
        "giveaways": "🎉・GIVEAWAYS & EVENTS",
        "events": "🎉・GIVEAWAYS & EVENTS",
        "levels": "⭐・LEVELS & COMMUNITY",
        "leveling": "⭐・LEVELS & COMMUNITY",
        "rank": "⭐・LEVELS & COMMUNITY",
        "xp": "⭐・LEVELS & COMMUNITY",
        "images": "🖼️・IMAGES & AVATARS",
        "music": "🎵・MUSIC",
        "audio": "🎵・MUSIC",
        "social": "💬・SOCIAL & FUN",
        "fun": "💬・SOCIAL & FUN",
        "premium": "💎・PREMIUM",
        "prime": "💎・PREMIUM",
        "admin": "⚙️・SERVER ADMINISTRATION",
        "administration": "⚙️・SERVER ADMINISTRATION",
        "config": "⚙️・SERVER ADMINISTRATION",
        "settings": "⚙️・SERVER ADMINISTRATION",
        "utility": "🔧・UTILITIES",
        "utilities": "🔧・UTILITIES",
        "vouch": "⭐・VOUCHES & REPUTATION",
        "vouches": "⭐・VOUCHES & REPUTATION",
        "rep": "⭐・VOUCHES & REPUTATION",
        "reputation": "⭐・VOUCHES & REPUTATION",
        "bill": "🧾・BLOX FRUITS SERVICE BILLS",
        "bills": "🧾・BLOX FRUITS SERVICE BILLS",
        "invoice": "🧾・BLOX FRUITS SERVICE BILLS",
        "invoices": "🧾・BLOX FRUITS SERVICE BILLS",
        "bloxfruits": "🍎・BLOX FRUITS AI",
        "bloxai": "🍎・BLOX FRUITS AI",
        "bf": "🍎・BLOX FRUITS AI",
        "fruit": "🍎・BLOX FRUITS AI",
        "afk": "💤・AFK",
        "reactionrole": "🎭・REACTION ROLES",
        "reactionroles": "🎭・REACTION ROLES",
        "rr": "🎭・REACTION ROLES",
        "roles": "🎭・REACTION ROLES",
        "owner": "👑・OWNER & DEVELOPER",
        "developer": "👑・OWNER & DEVELOPER",
        "dev": "👑・OWNER & DEVELOPER",
        "voice": "🎙️・AI VOICE",
        "aivoice": "🎙️・AI VOICE",
        "tts": "🎙️・AI VOICE",
        "fruitvalues": "🍎・BLOX FRUITS AI",
        "fruitnotifier": "🍎・BLOX FRUITS AI",
        "stock": "🍎・BLOX FRUITS AI",
    }

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
        """Resolve a command into one of the clean, modular help categories."""
        name = cmd.name.lower()
        cog_cat = getattr(cmd.cog, "category", "").strip().lower()
        cog_name = getattr(cmd.cog, "qualified_name", "").lower()

        # 1. 👑・OWNER & DEVELOPER
        if cog_cat in ("owner", "developer") or cog_name in ("owner", "ownersystem", "developer") or name in (
            "owner", "dev", "health", "dbstatus", "extstatus", "eval", "exec", "restart",
            "shutdown", "sync", "leaveserver", "blacklist", "whitelistuser", "errors",
            "validateconfig", "maintenance", "spam", "spamcancel", "guesshostadd",
            "guesshostremove", "guesshosts", "reload", "load", "unload", "cogs", "systemstatus",
        ):
            return "👑・OWNER & DEVELOPER"

        # 2. 🎙️・AI VOICE
        if cog_cat in ("ai voice", "aivoice", "voice tts", "voice") or cog_name in ("aivoice", "voiceai", "aivoicecog") or name in (
            "aivoice", "voicespeak", "voiceask", "voicepersona", "voicestop", "voicediag", "speak", "voicejoin", "voiceleave"
        ) or (name.startswith("voice") and name not in ("voicelog", "voicerole")):
            return "🎙️・AI VOICE"

        # 3. 🧾・BLOX FRUITS SERVICE BILLS
        if cog_cat in ("bills", "billing") or cog_name in ("bills", "billing") or name.startswith("bill"):
            return "🧾・BLOX FRUITS SERVICE BILLS"

        # 4. 🍎・BLOX FRUITS AI
        if cog_cat in ("blox fruits ai", "bloxfruitsai", "bloxfruits", "blox fruits notifier", "fruitnotifier") or cog_name in ("bloxfruitsai", "bloxfruits", "bloxfruitsnotifier") or name in (
            "bloxai", "fruitinfo", "grindhelp", "tradehelp", "buildhelp", "bfai", "finfo", "bfbuild", "tradecalc", "levelhelp", "grindguide", "fruitvalues", "fruitnotifier"
        ):
            return "🍎・BLOX FRUITS AI"

        # 5. ⭐・VOUCHES & REPUTATION
        if cog_cat in ("vouches", "vouch", "reputation") or cog_name in ("vouches", "vouch") or name in (
            "vouch", "vouches", "vouchprofile", "vouchleaderboard", "vouchchannel", "heldvouches", "vouchremove", "botstaff", "repcheck", "vouchlb", "topvouches", "repleaderboard"
        ):
            return "⭐・VOUCHES & REPUTATION"

        # 6. 🛡️・VERIFICATION
        if cog_cat in ("verification", "verify") or cog_name in ("verification", "verify") or name.startswith("verify") or name in ("verification", "verify"):
            return "🛡️・VERIFICATION"

        # 6. 👋・WELCOME & AUTOMOD
        if cog_name in ("welcome", "goodbye") or name in (
            "welcome", "goodbye", "autorole", "welcometest", "goodbyetest", "welcomecard", "goodbyecard", "welcomesetup"
        ):
            return "👋・WELCOME & AUTOMOD"

        # 7. 🔒・AUTOMOD & SECURITY
        if cog_cat in ("automod", "security", "antinuke") or name in (
            "antispam", "antiflood", "invites", "badwords", "mentionspam", "automod", "antinuke", "whitelist", "extraowner", "boost", "security"
        ):
            return "🔒・AUTOMOD & SECURITY"

        # 8. 🛡️・MODERATION
        if cog_cat in ("moderation", "mod") or name in (
            "warn", "warnings", "timeout", "untimeout", "kick", "ban", "unban", "softban",
            "purge", "slowmode", "lock", "unlock", "hide", "unhide", "nick", "modlogs", "modlog",
            "case", "unwarn", "clearwarnings", "delwarn", "mute", "unmute", "snipe", "snipeall",
            "clearsnipe", "clearsnipeall", "nuke", "admins", "mods", "bots",
        ):
            return "🛡️・MODERATION"

        # 9. 🎫・TICKETS & SUPPORT
        if cog_cat in ("ticket", "tickets", "support") or name.startswith("ticket") or name in (
            "panel", "claim", "close", "reopen", "transcript", "ticketstats", "ticketsetup",
            "addmember", "removemember",
        ):
            return "🎫・TICKETS & SUPPORT"

        # 10. 🎭・REACTION ROLES
        if cog_cat in ("reaction roles", "reactionrole", "roles") or name in (
            "reactionrole", "rr", "rolemenu", "addreactionrole", "removereactionrole", "reactionroles"
        ):
            return "🎭・REACTION ROLES"

        # 11. 🎉・GIVEAWAYS & EVENTS
        if cog_cat in ("giveaway", "giveaways", "events") or name in (
            "giveaway", "gstart", "gend", "greroll", "glist", "requirements", "reroll", "event", "events",
        ):
            return "🎉・GIVEAWAYS & EVENTS"

        # 12. 🎵・MUSIC
        if cog_cat in ("music", "audio") or name in (
            "play", "pause", "resume", "skip", "stop", "queue", "nowplaying", "np",
            "volume", "vol", "loop", "repeat", "shuffle", "clear", "remove", "seek",
            "autoplay", "lyrics", "jump", "stay", "247", "playlist", "like", "unlike",
            "disconnect", "dc",
        ):
            return "🎵・MUSIC"

        # 13. 💤・AFK
        if cog_cat == "afk" or name == "afk":
            return "💤・AFK"

        # 14. ⭐・LEVELS & COMMUNITY
        if cog_cat in ("community & xp", "levels", "leveling") or name in (
            "levels", "rank", "levelconfig", "activity", "leaderboard", "xp", "xpmultiplier",
            "multiplier", "daily", "streak",
        ):
            return "⭐・LEVELS & COMMUNITY"

        # 15. 🤖・ARTIFICIAL INTELLIGENCE
        if cog_cat in ("ai companions", "ai & chat", "aiinteractions", "🤖・artificial intelligence", "⛩️・aizen ai system") or name in (
            "aigf", "aibaddie", "aispecial", "aiclearcompanion", "aichannel", "aidiag", "aistatus",
            "ai", "chat", "askai", "aizenai", "aisetup", "aipersonality", "aiconfig", "aitest",
            "aiclear", "aimodel", "aidebug", "girlfriend", "baddie", "specialai", "clearcompanion",
            "setaichannel", "setcompanionchannel", "aichatsetup", "aihelp", "companion",
        ):
            return "🤖・ARTIFICIAL INTELLIGENCE"

        # 16. 💎・PREMIUM
        if cog_cat in ("premium", "prime") or name in (
            "premium", "redeem", "tier", "license", "prime", "perks",
        ):
            return "💎・PREMIUM"

        # 17. ⚙️・SERVER ADMINISTRATION
        if cog_cat in ("admin", "administration", "config", "settings") or name in (
            "prefix", "setprefix", "resetprefix", "media", "sticky", "logs", "config",
            "disablecmd", "enablecmd", "channelsettings", "rolesettings", "customhelp", "chelp", "setup",
        ):
            return "⚙️・SERVER ADMINISTRATION"

        # 18. 🔧・UTILITIES
        if cog_cat in ("utilities", "utility", "tools") or name in (
            "calc", "calculate", "remind", "remindme", "reminders", "time", "timestamp", "avatar", "serveravatar",
        ):
            return "🔧・UTILITIES"

        # 19. 🖼️・IMAGES & AVATARS
        if cog_cat in ("images & gifs", "anime actions") or name in (
            "gif", "meme", "randomgif", "imagine", "steal", "emojis", "expressions",
            "stickers", "delemoji", "filter", "trigger", "hug", "kiss", "pat", "slap",
            "cuddle", "wave", "dance", "smile", "cry", "blush", "punch", "blast",
            "animekick", "bonk", "poke", "bite", "yeet", "highfive", "stare", "scare", "laugh", "wink", "shy", "facepalm",
        ):
            return "🖼️・IMAGES & AVATARS"

        # 20. 💬・SOCIAL & FUN
        if cog_cat in ("romance & relationships", "social & profiles", "games", "fun", "adult humor — restricted") or name in (
            "propose", "marry", "divorce", "breakup", "relationship", "couple", "marriage",
            "love", "crush", "date", "jealous", "flirt", "pickup", "compliment", "romance",
            "heartbreak", "reject", "confess", "rizz", "ship", "compatibility", "soulmate",
            "loveletter", "bio", "coinflip", "flip", "dice", "roll", "8ball",
            "eightball", "choose", "rate", "joke", "fact", "quote", "wyr", "truth", "dare",
            "roast", "rps", "trivia", "wordguess", "wordgame", "tod", "truthordare", "guess",
        ):
            return "💬・SOCIAL & FUN"

        # 21. 🏠・GETTING STARTED (Default)
        return "🏠・GETTING STARTED"

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
        owner_only = {
            "spam", "spamcancel", "guesshostadd", "guesshostremove", "guesshosts",
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
        if resolved_cat == "💎・PREMIUM" or name in ("imagine", "tier", "license", "prime"):
            return " `[Prime]`"
        return ""

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to view and execute into the 14 categories."""
        categories: dict[str, list[commands.Command]] = {cat: [] for cat in self.CATEGORY_ORDER}

        def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
            cmd_list = [cmd_obj]
            if isinstance(cmd_obj, commands.Group):
                for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                    cmd_list.extend(_collect_all(sub_cmd))
            return cmd_list

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue

            for cmd in cog.get_commands():
                for c in _collect_all(cmd):
                    if self._can_run_command(c, ctx):
                        target_cat = self._resolve_category(c)
                        if target_cat not in categories:
                            categories[target_cat] = []
                        if c not in categories[target_cat]:
                            categories[target_cat].append(c)

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
                f"**⛩️ Kyoka 3.0 — Ultimate All-In-One Discord Bot**\n"
                f"> Clean onboarding, automatic AI companions, robust moderation, and community entertainment."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Latency:** `{ws_ping}ms`\n"
            f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
            f"{dot} **Categories:** `{len(visible_categories)}` | **Available Commands:** `{total_commands}`\n"
            f"{dot} **Quick Start:** Type `{current_prefix}quickstart` or `{current_prefix}setup` to configure your server in minutes!"
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
        """Construct the Signature Kyoka Home Overview Discord Embed matching reference design."""
        guild = ctx.guild
        author = ctx.author
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        bot_name = self.bot.user.name if hasattr(self.bot, "user") and self.bot.user else "Kyoka"

        embed = discord.Embed(
            title=f"Hey, I'm {bot_name} — Kyoka 3.0",
            description=(
                "> Built for our community — keeping your server safe, active, and effortlessly connected.\n\n"
                f"• **Prefix Commands:** `{p}<command>` · **Slash Commands:** `/<command>`\n"
                f"• **Quickstart Guide:** `{p}quickstart` · `{p}setup`\n"
                f"• **Permission System:** `[Public]` Everyone · `[Mod]` Staff · `[Admin]` Administrators · `[Prime]` Kyoka Premium"
            ),
            color=0x2B0938,
        )

        embed.add_field(
            name="📊 System Status",
            value=(
                f"• **Latency:** `{ws_ping}ms`\n"
                f"• **Prefix:** `{p}` | **Slash:** `/`\n"
                f"• **Available Commands:** `{total_commands}` across `{len(visible_categories)}` categories"
            ),
            inline=False,
        )

        embed.add_field(
            name="✨ Key Features",
            value=(
                "• Select a module from the dropdown below to explore accessible commands.\n"
                "• Use pagination buttons to browse between pages (max 15 commands/page).\n"
                "• Use `🔍 Search` to find any specific command instantly."
            ),
            inline=False,
        )

        # Render high-res custom Kyoka Hero Banner
        embed.set_image(url="attachment://kyoka_hero.png")

        assets = getattr(Config, "ASSETS", None)
        thumbnail_url = getattr(assets, "AIZEN_AVATAR_URL", "") or getattr(assets, "DEFAULT_THUMBNAIL_URL", "")
        if not thumbnail_url and hasattr(self.bot, "user") and self.bot.user:
            thumbnail_url = self.bot.user.display_avatar.url
        if thumbnail_url and thumbnail_url.strip():
            embed.set_thumbnail(url=thumbnail_url.strip())

        embed.set_footer(
            text=f"Requested by {author.display_name} • KYOKA 3.0",
            icon_url=author.display_avatar.url if author.display_avatar else None,
        )
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
        """Construct a formatted Discord Embed for a specific command category with strict 15 cmd limit."""
        cat_keys = list(visible_categories.keys())
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        clean_cat_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"Accessible commands for {clean_cat_title}.")

        # Collect unique command names
        seen: set[str] = set()
        unique_cmds: list[commands.Command] = []
        for c in commands_list:
            if c.qualified_name not in seen:
                seen.add(c.qualified_name)
                unique_cmds.append(c)
        unique_cmds.sort(key=lambda c: c.qualified_name)

        per_page = HELP_COMMANDS_PER_PAGE
        total_pages = max(1, math.ceil(len(unique_cmds) / per_page))
        safe_page = max(1, min(page, total_pages))
        start_idx = (safe_page - 1) * per_page
        page_cmds = unique_cmds[start_idx : start_idx + per_page]

        desc_lines = [
            f"> {cat_desc}\n",
            f"**Page {safe_page}/{total_pages}** • **{len(unique_cmds)}** accessible command(s)\n",
        ]
        for c in page_cmds:
            badge = self._get_badge(c)
            desc_text = (c.description or getattr(c, "help", None) or "No detailed description provided.").strip().split("\n")[0][:80]
            desc_lines.append(f"• `{c.qualified_name}`{badge} — *{desc_text}*")
        desc_lines.append(f"\n*Use ◀️ / ▶️ buttons to paginate • Type `{p}help <command>` for full manual.*")

        embed = discord.Embed(
            title=f"{self._get_category_emoji(cat_name)} {cat_name}",
            description="\n".join(desc_lines),
            color=0x2B0938,
        )

        assets = getattr(Config, "ASSETS", None)
        gif_url = (
            getattr(assets, "HELP_GIF_URL", None)
            or os.getenv("KYOKA_HELP_GIF_URL")
            or "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif"
        )
        if gif_url and str(gif_url).strip():
            embed.set_image(url=str(gif_url).strip())

        thumb = getattr(assets, "AIZEN_AVATAR_URL", "") or getattr(assets, "DEFAULT_THUMBNAIL_URL", "")
        if thumb and thumb.strip():
            embed.set_thumbnail(url=thumb.strip())

        embed.set_footer(
            text=f"Page {safe_page}/{total_pages} • {len(unique_cmds)} Commands • Requested by {ctx.author.display_name} • KYOKA 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

    def build_command_embed(self, ctx: CustomContext, cmd: commands.Command) -> discord.Embed:
        """Construct detailed single-command manual embed."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        cat = self._resolve_category(cmd)
        cat_icon = self._get_category_emoji(cat)
        desc = cmd.description or cmd.help or "No detailed description provided."
        aliases = ", ".join([f"`{a}`" for a in cmd.aliases]) if cmd.aliases else "`None`"
        sig = f" {cmd.signature}" if cmd.signature else ""
        usage = f"`{p}{cmd.qualified_name}{sig}`"
        example = f"`{p}{cmd.qualified_name}`"

        badge = self._get_badge(cmd)
        status_str = badge.strip(" `[]") if badge else "Public"

        slash_info = f"`/{cmd.name}`" if getattr(cmd, "app_command", None) else "Prefix command only"
        if cat == "🤖・ARTIFICIAL INTELLIGENCE":
            slash_info = f"`/ai` or `{p}{cmd.name}`"

        embed = discord.Embed(
            title=f"{cat_icon} Command: `{cmd.qualified_name}`",
            description=f"> {desc}",
            color=0x2B0938,
        )

        embed.add_field(
            name="📌 Usage & Execution",
            value=(
                f"• **Syntax:** {usage}\n"
                f"• **Example:** {example}\n"
                f"• **Slash Command:** {slash_info}"
            ),
            inline=False,
        )

        embed.add_field(
            name="⚙️ Metadata & Permissions",
            value=(
                f"• **Category:** `{cat}`\n"
                f"• **Required Access:** `{status_str}`\n"
                f"• **Aliases:** {aliases}"
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

        assets = getattr(Config, "ASSETS", None)
        thumb = getattr(assets, "AIZEN_AVATAR_URL", "") or getattr(assets, "DEFAULT_THUMBNAIL_URL", "")
        if thumb and thumb.strip():
            embed.set_thumbnail(url=thumb.strip())

        embed.set_footer(
            text=f"Requested by {ctx.author.display_name} • Kyoka 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed


    def build_embed_for_selection(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        selected_val: str,
        page: int = 1,
    ) -> discord.Embed:
        """Route selection value to corresponding category or home embed."""
        if selected_val == "home":
            return self.build_home_embed(ctx, visible_categories)
        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            return self.build_category_embed(
                ctx, matched_cat, visible_categories[matched_cat], visible_categories, page=page
            )
        return self.build_home_embed(ctx, visible_categories)

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules", "h"],
        description="Display the Kyoka command directory tailored to your permissions.",
    )
    async def help_command(self, ctx: CustomContext, *, command_or_module: str | None = None) -> None:
        """Interactive help menu filtered by user permissions and organized into 14 categories."""
        visible_categories = await self._get_visible_categories(ctx)

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
                    f"• Type `{p}quickstart` for initial server onboarding"
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
        ws_ping = self._get_latency_ms()
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        bot_user_name = self.bot.user.name if hasattr(self.bot, "user") and self.bot.user else "KYOKA 3.0"
        banner_fp = generate_kyoka_hero_banner(
            bot_name=bot_user_name,
            guild_name=ctx.guild.name if ctx.guild else "Direct Messages",
            total_commands=total_commands,
            latency_ms=ws_ping,
            prefix=p,
        )
        banner_fp.seek(0)
        banner_file = discord.File(banner_fp, filename="kyoka_hero.png")
        msg = await ctx.send(embed=embed, file=banner_file, view=view)
        if getattr(ctx, "interaction", None):
            try:
                view.message = await ctx.interaction.original_response()
            except Exception:
                pass
        else:
            view.message = msg

    # ─── HELP COMMAND ARCHIVE (HCA) PUBLIC DIRECTORY ─────────────────────────
    def build_hca_index_embed(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
    ) -> discord.Embed:
        """Construct the master Help Command Archive (HCA) index directory embed."""
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

        embed.set_image(url="attachment://hca_banner.png")
        embed.set_footer(
            text=f"Help Command Archive (HCA) • Requested by {ctx.author.display_name} • Type {p}hca <module>",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

    def build_hca_category_embed(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        all_categories: dict[str, list[commands.Command]],
        page: int = 1,
    ) -> discord.Embed:
        """Construct a paginated category archive card for HCA."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        clean_cat_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"All registered commands for {clean_cat_title}.")
        cat_icon = self._get_category_emoji(cat_name)

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
        embed.set_image(url="attachment://hca_banner.png")
        embed.set_footer(
            text=f"Page {safe_page}/{total_pages} • {len(unique_cmds)} Commands • Public Archive • KYOKA 3.0",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

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

        embed.set_image(url="attachment://hca_banner.png")
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
    ) -> discord.Embed:
        """Route HCA selection to index or category embed."""
        if selected_val == "home":
            return self.build_hca_index_embed(ctx, all_categories)
        matched_cat = next((c for c in all_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            return self.build_hca_category_embed(
                ctx, matched_cat, all_categories[matched_cat], all_categories, page=page
            )
        return self.build_hca_index_embed(ctx, all_categories)

    @commands.hybrid_command(
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
            target_cat = self.CATEGORY_ALIASES.get(query)
            if not target_cat:
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
                embed = self.build_hca_category_embed(ctx, target_cat, all_categories[target_cat], all_categories, page=1)
                banner_fp = generate_hca_banner(
                    category_name=target_cat,
                    total_commands=len(all_categories[target_cat]),
                    prefix=p,
                )
                banner_fp.seek(0)
                banner_file = discord.File(banner_fp, filename="hca_banner.png")
                msg = await ctx.send(embed=embed, file=banner_file, view=view)
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
                    f"• `{p}hca aivoice` — View AI Voice & TTS commands\n"
                    f"• `{p}hca` — Open the master Archive Index"
                ),
                color=0xED4245,
            )
            banner_fp = generate_hca_banner(category_name="Unknown Category", total_commands=sum(len(c) for c in all_categories.values()), prefix=p)
            banner_fp.seek(0)
            banner_file = discord.File(banner_fp, filename="hca_banner.png")
            view = HCAView(
                cog=self,
                ctx=ctx,
                all_categories=all_categories,
                current_category="home",
                current_page=1,
            )
            msg = await ctx.send(embed=embed, file=banner_file, view=view)
            if getattr(ctx, "interaction", None):
                try:
                    view.message = await ctx.interaction.original_response()
                except Exception:
                    pass
            else:
                view.message = msg
            return

        # Master Archive Index
        view = HCAView(
            cog=self,
            ctx=ctx,
            all_categories=all_categories,
            current_category="home",
            current_page=1,
        )
        embed = self.build_hca_index_embed(ctx, all_categories)
        total_cmds = sum(len(c) for c in all_categories.values())
        banner_fp = generate_hca_banner(category_name="Archive Index", total_commands=total_cmds, prefix=p)
        banner_fp.seek(0)
        banner_file = discord.File(banner_fp, filename="hca_banner.png")
        msg = await ctx.send(embed=embed, file=banner_file, view=view)
        if getattr(ctx, "interaction", None):
            try:
                view.message = await ctx.interaction.original_response()
            except Exception:
                pass
        else:
            view.message = msg

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


async def setup(bot: KyokaBot) -> None:
    cog = Help(bot)
    await bot.add_cog(cog)
    logger.info("⛩️ [KYOKA CONTROL] Aizen Premium Help Dashboard loaded successfully (Hybrid Prefix & Slash).")

