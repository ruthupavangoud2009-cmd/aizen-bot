"""
KYOKA — Aizen Ultimate Edition
Help System & Command Navigation Console

High-performance, mobile-optimized interactive help system.
Initial ?help displays the signature KYOKA Aizen Edition homepage with bot avatar,
banner, ping, uptime, creator credit, server/member metrics, premium info,
support server link, and category dropdown.
Category views display command syntax, descriptions, aliases, required permissions,
cooldowns, and examples using custom animated/static emojis.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner, is_owner_or_staff, OWNER_ID
from src.security.adult_guard import is_adult_authorized
from src.utils.containers import (
    KyokaContainer,
    send_container_response,
    edit_container_response,
)
from src.utils.emojis import resolve_emoji, resolve_select_emoji
from src.ui.categories import (
    CATEGORIES,
    CATEGORY_BY_TAG,
    resolve_command_category,
    get_category_by_query,
)
from src.ui.asset_manager import AssetManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Help")

HELP_COMMANDS_PER_PAGE: int = 8

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
    "🎬・WATCH PARTY": "🎬",
    "💤・AFK": "💤",
    "⭐・VOUCHES & REPUTATION": "⭐",
    "🧾・BLOX FRUITS SERVICE BILLS": "🧾",
    "🍎・BLOX FRUITS AI": "🍎",
    "🤖・ARTIFICIAL INTELLIGENCE": "🤖",
    "🖼️・IMAGES & AVATARS": "🖼️",
    "💬・SOCIAL & FUN": "💬",
    "💎・PREMIUM": "💎",
    "⚙️・SERVER ADMINISTRATION": "⚙️",
    "🔧・UTILITIES": "🔧",
    "📝・STAFF APPLICATIONS": "📝",
    "👑・OWNER & DEVELOPER": "👑",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "🏠・GETTING STARTED": "Server onboarding, quickstart guide, bot setup & essential info",
    "🛡️・MODERATION": "Punishments, audit logs, purges, timeouts, channel locks & cases",
    "🔒・AUTOMOD & SECURITY": "Anti-spam, anti-raid, invite defense, bad words & antinuke",
    "👋・WELCOME & AUTOMOD": "Greeting cards, farewell departures, autoroles & join settings",
    "🛡️・VERIFICATION": "Gatekeep channels with role isolation, challenge codes & button verification",
    "🎫・TICKETS & SUPPORT": "Interactive support ticket panels, staff claims & automated transcripts",
    "🎭・REACTION ROLES": "Self-service role menus, dropdown selectors & button role assignments",
    "🎉・GIVEAWAYS & EVENTS": "Giveaway creation, requirement validation, timers & winner rerolls",
    "🎵・MUSIC": "High-fidelity audio playback, queues, volume, filters, lyrics & 24/7 radio",
    "💤・AFK": "Status notices, AFK reason tracking, mentions & auto-return alerts",
    "⭐・VOUCHES & REPUTATION": "Verified member vouches, Blox Fruits trust profiles & leaderboards",
    "🍎・BLOX FRUITS AI": "Specialized Blox Fruits companion, fruit guides, trade calculator & builds",
    "🤖・ARTIFICIAL INTELLIGENCE": "Aizen Gemini AI engine, 10 personalities & auto chat channels",
    "⭐・LEVELS & COMMUNITY": "Optional XP progression (disabled by default), custom rank cards & leaderboards",
    "🖼️・IMAGES & AVATARS": "Anime reaction GIFs, avatar lookups, banners & visual tools",
    "💬・SOCIAL & FUN": "Mini-games, truth-or-dare, relationship stats & trivia",
    "💎・PREMIUM": "Kyoka Prime licenses, high-resolution AI & exclusive server perks",
    "⚙️・SERVER ADMINISTRATION": "Prefix management, server wizards, custom help & diagnostics",
    "🔧・UTILITIES": "Handy server utilities, calculators, reminders & everyday tools",
    "👑・OWNER & DEVELOPER": "Core bot diagnostics, database status, extension reload & maintenance",
}


async def _safe_help_send(
    ctx: CustomContext,
    *,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    content: Optional[str] = None,
) -> Optional[discord.Message]:
    """Guaranteed fail-safe sender for help command across prefix, slash, and hybrid invocations."""
    inter = getattr(ctx, "interaction", None)
    if inter:
        try:
            if inter.response.is_done():
                return await inter.followup.send(
                    embed=embed or discord.utils.MISSING,
                    view=view or discord.utils.MISSING,
                    content=content or discord.utils.MISSING,
                )
            else:
                await inter.response.send_message(
                    embed=embed or discord.utils.MISSING,
                    view=view or discord.utils.MISSING,
                    content=content or discord.utils.MISSING,
                )
                try:
                    return await inter.original_response()
                except Exception:
                    return None
        except Exception as e:
            logger.debug(f"Interaction send notice: {e}")

    try:
        return await ctx.reply(
            embed=embed or discord.utils.MISSING,
            view=view or discord.utils.MISSING,
            content=content or discord.utils.MISSING,
            mention_author=False,
        )
    except Exception:
        try:
            return await ctx.send(
                embed=embed or discord.utils.MISSING,
                view=view or discord.utils.MISSING,
                content=content or discord.utils.MISSING,
            )
        except Exception as e:
            logger.error(f"Failed to send help response: {e}")
            return None


class HelpCategorySelect(discord.ui.Select):
    """Interactive category select menu for switching between command categories."""

    def __init__(
        self,
        help_view: HelpView,
        visible_categories: dict[str, list[commands.Command]],
        current_selection: str = "home",
    ) -> None:
        self.help_view = help_view

        def resolve_menu_emoji(cat_name: Optional[str] = None) -> str:
            if not cat_name or cat_name.lower() == "home":
                return "🏠"

            raw = cat_name.split("・", 1)[-1].strip().upper()
            mapping = {
                "GETTING STARTED": "HOME",
                "MODERATION": "MODERATION",
                "AUTOMOD & SECURITY": "ANTI_NUKE",
                "ANTINUKE": "ANTI_NUKE",
                "WELCOME & AUTOMOD": "WELCOMER",
                "WELCOMER": "WELCOMER",
                "VERIFICATION": "VERIFICATION",
                "TICKETS & SUPPORT": "TICKET",
                "TICKET": "TICKET",
                "REACTION ROLES": "ROLE",
                "GIVEAWAYS & EVENTS": "GIVEAWAY",
                "GIVEAWAY": "GIVEAWAY",
                "MUSIC": "MUSIC",
                "AFK": "AFK",
                "VOUCHES & REPUTATION": "LEVEL",
                "BLOX FRUITS AI": "AI",
                "ARTIFICIAL INTELLIGENCE": "AI",
                "AI": "AI",
                "LEVELS & COMMUNITY": "LEVEL",
                "IMAGES & AVATARS": "MEDIA",
                "MEDIA": "MEDIA",
                "SOCIAL & FUN": "MEMBERS",
                "PREMIUM": "PREMIUM",
                "SERVER ADMINISTRATION": "ADMIN",
                "ADMIN": "ADMIN",
                "UTILITIES": "UTILITY",
                "UTILITY": "UTILITY",
                "OWNER & DEVELOPER": "OWNER",
                "OWNER": "OWNER",
                "MULTIPLAYER GAMES": "GAMES",
                "MINI-GAMES": "GAMES",
                "GAMES": "GAMES",
                "WATCH PARTY": "VOICE",
                "KYOKA CASINO": "CASINO",
                "CASINO": "CASINO",
                "HUNTING & ANIMALS": "GAMES",
                "JOIN TO CREATE": "VOICE",
                "MEETING": "VOICE",
                "LOGGING": "LOGGING",
            }
            cat_key = mapping.get(raw)
            if not cat_key:
                for k, v in mapping.items():
                    if k in raw or raw in k:
                        cat_key = v
                        break
            if not cat_key:
                cat_key = "SETTINGS"

            fallback_map = {
                "HOME": "🏠", "MODERATION": "⚔️", "ANTI_NUKE": "🛡️", "WELCOMER": "🚪",
                "VERIFICATION": "✅", "TICKET": "🎫", "ROLE": "🏷️", "GIVEAWAY": "🎉",
                "MUSIC": "🎵", "AFK": "💤", "AI": "🤖", "LEVEL": "⭐", "MEDIA": "🖼️",
                "MEMBERS": "👥", "PREMIUM": "💎", "ADMIN": "⚙️", "UTILITY": "🔧",
                "OWNER": "👑", "GAMES": "🎮", "VOICE": "🎙️", "CASINO": "🎰",
                "LOGGING": "📜", "SETTINGS": "⚙️",
            }
            bot_ref = getattr(getattr(help_view, "cog", None), "bot", None)
            return resolve_select_emoji(bot_ref, cat_key, fallback=fallback_map.get(cat_key, "📁"))

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Home",
                value="home",
                description="KYOKA overview, quickstart & system navigation",
                emoji=resolve_menu_emoji("home"),
                default=(current_selection == "home"),
            )
        ]

        for idx, (cat_name, cmds) in enumerate(visible_categories.items()):
            raw_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            clean_label = raw_title.title() if raw_title.isupper() else raw_title
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{len(cmds)} accessible commands")[:100]

            options.append(
                discord.SelectOption(
                    label=clean_label.strip()[:100],
                    value=f"cat_{idx}",
                    description=desc,
                    emoji=resolve_menu_emoji(cat_name),
                    default=(current_selection.lower() == cat_name.lower()),
                )
            )

        if current_selection == "home":
            placeholder_text = "🏠 Home — Select a module to view commands..."
        else:
            cur_clean = current_selection.split("・", 1)[-1].strip()
            placeholder_text = f"📁 {cur_clean.title() if cur_clean.isupper() else cur_clean} — Switch module..."

        super().__init__(
            placeholder=placeholder_text[:150],
            min_values=1,
            max_values=1,
            options=options[:25],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_val = self.values[0]
        if selected_val == "home":
            await self.help_view.switch_to_home(interaction)
            return

        idx = int(selected_val.replace("cat_", ""))
        cat_keys = list(self.help_view.visible_categories.keys())
        if 0 <= idx < len(cat_keys):
            target_cat = cat_keys[idx]
            await self.help_view.switch_to_category(interaction, target_cat, page=1)


class HelpSearchModal(discord.ui.Modal, title="Search KYOKA Commands"):
    """Search modal allowing users to find commands by name or keyword."""

    search_input = discord.ui.TextInput(
        label="Search Command or Keyword",
        placeholder="e.g. ban, play, afk, ticket, ai...",
        required=True,
        max_length=50,
    )

    def __init__(self, help_view: HelpView) -> None:
        super().__init__()
        self.help_view = help_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = str(self.search_input.value).strip()
        embed = self.help_view.cog.build_search_results_embed(
            self.help_view.ctx,
            self.help_view.visible_categories,
            query,
        )
        await interaction.response.edit_message(embed=embed, view=self.help_view)


class HelpView(discord.ui.View):
    """Interactive navigation view for KYOKA Help System."""

    def __init__(
        self,
        cog: Help,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        current_category: str = "home",
        current_page: int = 1,
    ) -> None:
        super().__init__(timeout=180.0)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.visible_categories = visible_categories
        self.current_category = current_category
        self.current_page = current_page
        self.category_keys = list(visible_categories.keys())
        self.message: Optional[discord.Message] = None

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        def btn_emoji(cat_name: str) -> Any:
            fb = {"BACK": "◀️", "HOME": "🏠", "NEXT": "▶️", "SEARCH": "🔍", "DELETE": "🗑️"}
            return resolve_select_emoji(self.cog.bot, cat_name, fallback=fb.get(cat_name, "•"))

        # Row 0: Dropdown
        self.category_select = HelpCategorySelect(
            self,
            self.visible_categories,
            current_selection=self.current_category,
        )
        self.add_item(self.category_select)

        # On Home: Keep ultra-clean Greed style (dropdown + link buttons in fallback view)
        if self.current_category == "home":
            invite_url = getattr(Config, "INVITE_URL", "")
            support_url = getattr(Config, "SUPPORT_URL", "") or "https://discord.gg/7q4tn6dA6V"
            pages_url = getattr(Config, "PAGES_ORIGIN", "") or "https://aizen-bot.pages.dev/"
            if invite_url and str(invite_url).startswith("http"):
                self.add_item(discord.ui.Button(label="Invite KYOKA", style=discord.ButtonStyle.link, url=invite_url, row=1))
            elif pages_url and str(pages_url).startswith("http"):
                self.add_item(discord.ui.Button(label="Web Dashboard", style=discord.ButtonStyle.link, url=pages_url, row=1))
            if support_url and str(support_url).startswith("http"):
                self.add_item(discord.ui.Button(label="Support Server", style=discord.ButtonStyle.link, url=support_url, row=1))
            btn_search = discord.ui.Button(
                label="Search",
                emoji=btn_emoji("SEARCH"),
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)
        else:
            cmds = self.visible_categories.get(self.current_category, [])
            total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))

            btn_back = discord.ui.Button(
                label="Back",
                emoji=btn_emoji("BACK"),
                style=discord.ButtonStyle.secondary,
                disabled=(not self.category_keys and self.current_page <= 1),
                row=1,
            )
            btn_back.callback = self.btn_back_callback
            self.add_item(btn_back)

            btn_home = discord.ui.Button(
                label="Home",
                emoji=btn_emoji("HOME"),
                style=discord.ButtonStyle.primary,
                row=1,
            )
            btn_home.callback = self.btn_home_callback
            self.add_item(btn_home)

            btn_next = discord.ui.Button(
                label="Next",
                emoji=btn_emoji("NEXT"),
                style=discord.ButtonStyle.secondary,
                disabled=(not self.category_keys and self.current_page >= total_pages),
                row=1,
            )
            btn_next.callback = self.btn_next_callback
            self.add_item(btn_next)

            btn_search = discord.ui.Button(
                label="Search",
                emoji=btn_emoji("SEARCH"),
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)

    @staticmethod
    def _serialize_item(item: Any) -> dict[str, Any]:
        if hasattr(item, "_underlying") and hasattr(item._underlying, "to_dict"):
            return item._underlying.to_dict()
        if hasattr(item, "to_dict"):
            return item.to_dict()
        return {}

    def to_container_components(self) -> list[dict[str, Any]]:
        """Pack select menu, pagination, and Greed-style footer inside Components V2 Container."""
        comps: list[dict[str, Any]] = []
        if hasattr(self, "category_select"):
            comps.append({"type": 1, "components": [self._serialize_item(self.category_select)]})

        if self.current_category != "home":
            btn_comps = []
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    btn_comps.append(self._serialize_item(item))
            if btn_comps:
                comps.append({"type": 1, "components": btn_comps[:5]})

        prefix = self.cog.bot.guild_mgr.get_prefix(self.ctx.guild.id if self.ctx.guild else None)
        book_em = resolve_emoji(self.cog.bot, "BOOK", fallback="📖")
        comps.append({
            "type": 10,
            "content": f"-# {book_em} Use `{prefix}help (command)` for details on a specific command",
        })
        return comps

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This help menu belongs to the user who requested it. Use `?help` to open your own!",
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

    async def switch_to_home(self, interaction: discord.Interaction) -> None:
        self.current_category = "home"
        self.current_page = 1
        self._build_components()
        container = self.cog.build_home_container(self.ctx, self.visible_categories)
        try:
            await edit_container_response(interaction, container, view=self)
        except Exception:
            embed = self.cog.build_home_embed(self.ctx, self.visible_categories)
            if interaction.response.is_done() is True:
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

    async def switch_to_category(self, interaction: discord.Interaction, cat_name: str, page: int = 1) -> None:
        self.current_category = cat_name
        self.current_page = page
        self._build_components()
        cmds = self.visible_categories.get(cat_name, [])
        container = self.cog.build_category_container(self.ctx, cat_name, cmds, page=page)
        try:
            await edit_container_response(interaction, container, view=self)
        except Exception:
            embed = self.cog.build_category_embed(self.ctx, cat_name, cmds, page=page)
            if interaction.response.is_done() is True:
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        if self.current_category != "home" and self.current_page > 1:
            await self.switch_to_category(interaction, self.current_category, page=self.current_page - 1)
            return
        if not self.category_keys:
            await self.switch_to_home(interaction)
            return
        if self.current_category == "home":
            target = self.category_keys[-1]
        elif self.current_category in self.category_keys:
            idx = self.category_keys.index(self.current_category)
            target = self.category_keys[(idx - 1) % len(self.category_keys)]
        else:
            target = self.category_keys[0]
        await self.switch_to_category(interaction, target, page=1)

    async def btn_home_callback(self, interaction: discord.Interaction) -> None:
        await self.switch_to_home(interaction)

    async def btn_next_callback(self, interaction: discord.Interaction) -> None:
        if self.current_category != "home":
            cmds = self.visible_categories.get(self.current_category, [])
            total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))
            if self.current_page < total_pages:
                await self.switch_to_category(interaction, self.current_category, page=self.current_page + 1)
                return
        if not self.category_keys:
            await self.switch_to_home(interaction)
            return
        if self.current_category == "home":
            target = self.category_keys[0]
        elif self.current_category in self.category_keys:
            idx = self.category_keys.index(self.current_category)
            target = self.category_keys[(idx + 1) % len(self.category_keys)]
        else:
            target = self.category_keys[0]
        await self.switch_to_category(interaction, target, page=1)

    async def btn_search_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(HelpSearchModal(self))


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
                emoji=None,
                default=(current_selection == "home"),
            ),
            discord.SelectOption(
                label="All Commands",
                value="all",
                description="Browse every registered command A-Z with pagination",
                emoji=None,
                default=(current_selection == "all"),
            ),
        ]
        for cat_name, cmds in categories.items():
            raw_title = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            clean_label = raw_title.title() if raw_title.isupper() else raw_title
            clean_label = clean_label.strip()[:100]
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{len(cmds)} archived commands")[:100]
            options.append(
                discord.SelectOption(
                    label=clean_label,
                    value=cat_name.lower(),
                    description=desc,
                    emoji=None,
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
        await self.hca_view.switch_category(interaction, self.values[0])


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
        bot_ref = getattr(self.cog, "bot", None)

        btn_back = discord.ui.Button(label="Back", emoji=resolve_select_emoji(bot_ref, "BACK", fallback="◀️"), style=discord.ButtonStyle.secondary, row=1)
        btn_back.callback = self.btn_back_callback
        self.add_item(btn_back)

        btn_home = discord.ui.Button(label="Index", emoji=resolve_select_emoji(bot_ref, "HOME", fallback="🏠"), style=discord.ButtonStyle.primary, row=1)
        btn_home.callback = self.btn_home_callback
        self.add_item(btn_home)

        btn_next = discord.ui.Button(label="Next", emoji=resolve_select_emoji(bot_ref, "NEXT", fallback="▶️"), style=discord.ButtonStyle.secondary, row=1)
        btn_next.callback = self.btn_next_callback
        self.add_item(btn_next)

        btn_search = discord.ui.Button(label="Search", emoji=resolve_select_emoji(bot_ref, "SEARCH", fallback="🔍"), style=discord.ButtonStyle.secondary, row=1)
        btn_search.callback = self.btn_search_callback
        self.add_item(btn_search)

        btn_close = discord.ui.Button(label="Close", emoji=resolve_select_emoji(bot_ref, "DELETE", fallback="🗑️"), style=discord.ButtonStyle.danger, row=1)
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
        if self.current_category == "all":
            if self.current_page > 1:
                self.current_page -= 1
                embed, banner_file = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, "all", page=self.current_page)
                if banner_file:
                    await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                else:
                    await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                return
        elif self.current_category != "home":
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
        if self.current_category == "all":
            total_all = len({c.qualified_name for cmds in self.all_categories.values() for c in cmds})
            total_pages = max(1, math.ceil(total_all / 10))
            if self.current_page < total_pages:
                self.current_page += 1
                embed, banner_file = self.cog.build_hca_embed_for_selection(self.ctx, self.all_categories, "all", page=self.current_page)
                if banner_file:
                    await interaction.response.edit_message(embed=embed, attachments=[banner_file], view=self)
                else:
                    await interaction.response.edit_message(embed=embed, attachments=[], view=self)
                return
        elif self.current_category != "home":
            cat_match = next((c for c in self.category_keys if c.lower() == self.current_category.lower()), None)
            if cat_match:
                cmds = self.all_categories.get(cat_match, [])
                total_pages = max(1, math.ceil(len(cmds) / 10))
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
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.edit_message(view=self)


class Help(commands.Cog, name="Help"):
    """Signature KYOKA Aizen Edition Help Console."""
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
        "🎬・WATCH PARTY",
        "💬・SOCIAL & FUN",
        "💎・PREMIUM",
        "⚙️・SERVER ADMINISTRATION",
        "🔧・UTILITIES",
        "👑・OWNER & DEVELOPER",
    ]

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    def _get_latency_ms(self) -> int:
        try:
            lat = getattr(self.bot, "latency", None)
            if lat is not None and not math.isnan(lat) and not math.isinf(lat):
                return max(0, round(lat * 1000))
        except Exception:
            pass
        return 0

    def _resolve_category(self, cmd: commands.Command) -> str:
        meta = resolve_command_category(cmd)
        return meta.tag

    @staticmethod
    def _can_run_command(cmd: Any, ctx: CustomContext | None = None) -> bool:
        if getattr(cmd, "hidden", False):
            return False

        cog = getattr(cmd, "cog", None)
        cog_cat = str(getattr(cog, "category", "")).strip().lower()
        author_id = getattr(ctx.author, "id", None) if ctx else None

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

        if cog_cat in ("adult humor — restricted", "adult humor - restricted", "adulthumor"):
            if not is_adult_authorized(author_id):
                return False

        return True

    def _get_badge(self, cmd: commands.Command) -> str:
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
        base_categories = self._get_base_categories()
        ordered: dict[str, list[commands.Command]] = {}

        for cat in self.CATEGORY_ORDER:
            cmds = base_categories.get(cat, [])
            permitted = [c for c in cmds if self._can_run_command(c, ctx)]
            if permitted:
                ordered[cat] = permitted

        for cat, cmds in base_categories.items():
            if cat not in ordered:
                permitted = [c for c in cmds if self._can_run_command(c, ctx)]
                if permitted:
                    ordered[cat] = permitted

        return ordered

    def audit_command_tree(self) -> dict[str, Any]:
        """Audit every registered command to confirm 100% category coverage and zero Music pollution."""
        missing_from_help: list[str] = []
        music_contamination: list[str] = []
        vouch_commands: list[str] = []
        bill_commands: list[str] = []
        category_distribution: dict[str, list[str]] = {}

        base_cats = self._get_base_categories()
        for cat_tag, cmds in base_cats.items():
            names = [c.qualified_name for c in cmds]
            category_distribution[cat_tag] = names
            if cat_tag == "⭐・VOUCHES & REPUTATION":
                vouch_commands.extend(names)
            elif cat_tag == "🧾・BLOX FRUITS SERVICE BILLS":
                bill_commands.extend(names)
            elif cat_tag == "🎵・MUSIC":
                for c in cmds:
                    cog_name = getattr(getattr(c, "cog", None), "qualified_name", "").lower()
                    if "ai" in cog_name or c.qualified_name.startswith("aivoice"):
                        music_contamination.append(c.qualified_name)

        all_mapped = {n for names in category_distribution.values() for n in names}
        for cmd in getattr(self.bot, "commands", set()):
            if cmd.qualified_name not in all_mapped:
                missing_from_help.append(cmd.qualified_name)

        return {
            "is_complete": len(missing_from_help) == 0 and len(music_contamination) == 0,
            "missing_from_help": missing_from_help,
            "music_contamination": music_contamination,
            "vouch_commands": vouch_commands,
            "bill_commands": bill_commands,
            "category_distribution": category_distribution,
        }

    def build_home_container(self, ctx: CustomContext, visible_categories: dict[str, list[commands.Command]]) -> KyokaContainer:
        """Construct the signature Greed-style KyokaContainer (Components V2)."""
        term_icon = resolve_emoji(self.bot, "TERMINAL", fallback=">_")
        cmd_icon = resolve_emoji(self.bot, "BRACKETS", fallback="{ }")
        mod_icon = resolve_emoji(self.bot, "MODULES", fallback="⊞")
        dot = resolve_emoji(self.bot, "ARROW", fallback="»")

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        latency_ms = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        modules_count = len(visible_categories)
        raw_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B0938)
        ui_color = raw_color if isinstance(raw_color, int) and not isinstance(raw_color, bool) else 0x2B0938

        container = KyokaContainer(accent_color=ui_color)

        # 1. Top banner image
        banner_url = Config.ASSETS.HELP_BANNER_URL or Config.ASSETS.BANNER_URL
        if not banner_url or not banner_url.startswith("http"):
            banner_url = "https://raw.githubusercontent.com/ruthupavangoud2009-cmd/aizen-bot/main/assets/branding/kyoka_banner.png"
        container.add_media(banner_url)

        # 2. Section with Title and Description + Avatar Thumbnail
        avatar_url = self.bot.user.display_avatar.url if getattr(self.bot, "user", None) else None
        section_text = (
            "### Hey, I'm KYOKA\n"
            "> Experience the ultimate Discord bot designed for seamless server management, "
            "bulletproof security, high-fidelity music, and community engagement."
        )
        if avatar_url:
            container.add_section(section_text, accessory={"type": 11, "media": {"url": avatar_url}})
        else:
            container.add_text(section_text)

        # 3. Clean Separator
        container.add_separator()

        # 4. Telemetry & Stats
        stats_text = (
            f"{dot} **Latency:** `{latency_ms}ms`\n"
            f"{term_icon} **Prefix:** `{prefix}` | **Slash:** `/`\n"
            f"{cmd_icon} **Available Commands:** `{total_commands:,}`\n"
            f"{mod_icon} **Modules:** `{modules_count}`"
        )
        container.add_text(stats_text)

        return container

    def resolve_command_emoji(self, cmd_name: str, cat_name: str = "") -> str:
        """
        Resolve a dedicated custom emoji for every single command in KYOKA.
        Prefers custom emojis (<:name:id> / <a:name:id>), falls back cleanly to category/manifest symbols.
        """
        clean = cmd_name.lower().strip()

        def em(key: str, fallback: str) -> str:
            return resolve_emoji(self.bot, key, fallback=fallback)

        # 1. Exact command lookup table
        EXACT_MAP: dict[str, tuple[str, str]] = {
            # Moderation
            "ban": ("icon_delete", "🔨"),
            "unban": ("icon_unlock", "🔓"),
            "softban": ("icon_delete", "🔨"),
            "tempban": ("icons_timeout", "⏳"),
            "kick": ("icons_leave", "👢"),
            "mute": ("icons_micmute", "🔇"),
            "unmute": ("icons_podcast", "🔊"),
            "tempmute": ("icons_timeout", "⏱️"),
            "timeout": ("icons_timeout", "⏳"),
            "warn": ("icons_warning", "⚠️"),
            "warnings": ("icons_todolist", "📋"),
            "warns": ("icons_todolist", "📋"),
            "clearwarns": ("icon_clear", "🧹"),
            "purge": ("icon_clear", "🧹"),
            "clean": ("icon_clear", "🧹"),
            "nuke": ("icon_fire", "💥"),
            "lock": ("icons_locked", "🔒"),
            "unlock": ("icons_unlock", "🔓"),
            "lockdown": ("icons_locked", "🔒"),
            "slowmode": ("icons_reminder", "⏱️"),
            "role": ("lpf_icon_roles", "🏷️"),
            "addrole": ("icons_plus", "🏷️"),
            "removerole": ("icon_delete", "🏷️"),
            "nick": ("icons_message", "✏️"),
            "setnick": ("icons_message", "✏️"),
            "hide": ("icons_offline", "👁️‍🗨️"),
            "unhide": ("icons_online", "👁️"),
            "case": ("icons_file", "📁"),
            "reason": ("icons_message", "📝"),
            "history": ("icons_todolist", "📜"),
            "modlogs": ("icon_logging", "📜"),
            "snipe": ("sparkle_shine", "🎯"),
            # Security / Antinuke
            "antinuke": ("antinuke_pulse", "🛡️"),
            "whitelist": ("icons_verified", "📜"),
            "unwhitelist": ("icon_delete", "❌"),
            "trust": ("verified_glow", "🤝"),
            "untrust": ("icon_delete", "❌"),
            "panic": ("warning_flash", "🚨"),
            "recovery": ("ub_refresh_icon", "🔄"),
            "automod": ("antinuke_pulse", "🤖"),
            "antiraid": ("antinuke_pulse", "🛡️"),
            "antispam": ("icons_micmute", "🚫"),
            "antilink": ("icons_link", "🔗"),
            "antiinvite": ("icons_invite", "🚫"),
            # Music
            "play": ("music_playing", "▶️"),
            "p": ("music_playing", "▶️"),
            "pause": ("paused", "⏸️"),
            "resume": ("music_playing", "⏯️"),
            "stop": ("icons_stop_button", "⏹️"),
            "skip": ("skip", "⏭️"),
            "s": ("skip", "⏭️"),
            "seek": ("icons_rightarrow", "⏩"),
            "queue": ("queue", "📑"),
            "q": ("queue", "📑"),
            "np": ("music_music", "🎵"),
            "nowplaying": ("music_music", "🎵"),
            "volume": ("volume_up", "🔊"),
            "vol": ("volume_up", "🔊"),
            "loop": ("icons_loop", "🔁"),
            "repeat": ("icons_loop", "🔂"),
            "shuffle": ("icons_shuffle", "🔀"),
            "lyrics": ("lyrics", "📜"),
            "disconnect": ("icons_leave", "🔌"),
            "dc": ("icons_leave", "🔌"),
            "join": ("icons_join", "📥"),
            "filters": ("icons_magicwand", "🎛️"),
            "bassboost": ("volume_up", "🔊"),
            "radio": ("icons_podcast", "📻"),
            "247": ("icons_richpresence", "♾️"),
            # AI & Chat
            "ai": ("sparkle_shine", "🤖"),
            "ask": ("sparkle_shine", "💡"),
            "chat": ("icon_chat", "💬"),
            "gemini": ("sparkle_shine", "✨"),
            "imagine": ("icons_image", "🎨"),
            "draw": ("icons_image", "🖌️"),
            "resetai": ("ub_refresh_icon", "🔄"),
            "persona": ("user_badge", "🎭"),
            # AFK
            "afk": ("afk", "💤"),
            "unafk": ("icons_online", "👋"),
            "afklist": ("icons_todolist", "📋"),
            # Blox Fruits & Trading
            "bfservice": ("icons_todolist", "🧾"),
            "bfbill": ("zefex_credit_cards", "🧾"),
            "bfprice": ("icon_dollar", "🍎"),
            "bftrade": ("coin_spin", "⚖️"),
            "bffruits": ("icon_gift", "🍇"),
            "bfstock": ("icons_list", "📦"),
            "vouch": ("sparkle_shine", "⭐"),
            "vouches": ("btp_red_crown", "🌟"),
            # Giveaways
            "giveaway": ("discord_giveaway", "🎉"),
            "gstart": ("discord_giveaway", "🎉"),
            "gend": ("icons_stop_button", "🏁"),
            "greroll": ("ub_refresh_icon", "🎲"),
            "glist": ("icons_list", "📋"),
            # Tickets
            "ticket": ("ticket_support", "🎫"),
            "tcreate": ("ticket_support", "🎫"),
            "tclose": ("icons_locked", "🔒"),
            "treopen": ("icons_unlock", "🔓"),
            "ttranscript": ("transcript", "📄"),
            "tclaim": ("icons_staff", "🙋"),
            "tadd": ("icons_plus", "➕"),
            "tremove": ("icon_delete", "➖"),
            # Economy & Casino
            "balance": ("coin_spin", "💰"),
            "bal": ("coin_spin", "💰"),
            "daily": ("icon_gift", "🎁"),
            "weekly": ("icon_gift", "📦"),
            "pay": ("zefex_credit_cards", "💸"),
            "rob": ("icons_leave", "🥷"),
            "work": ("icons_todolist", "💼"),
            "slots": ("coin_spin", "🎰"),
            "coinflip": ("coin_spin", "🪙"),
            "cf": ("coin_spin", "🪙"),
            "roulette": ("coin_spin", "🎡"),
            "blackjack": ("zefex_credit_cards", "🃏"),
            "shop": ("icon_shoppingcart", "🛒"),
            "buy": ("icon_shoppingcart", "🛍️"),
            "inventory": ("icon_backpack", "🎒"),
            "inv": ("icon_backpack", "🎒"),
            # Verification
            "verify": ("verified_glow", "✅"),
            "setverify": ("icons_settings", "⚙️"),
            "verifyrole": ("lpf_icon_roles", "🏷️"),
            # Welcomer
            "welcome": ("001_cinnamoroll_welcome_nf2u", "👋"),
            "setwelcome": ("icons_settings", "⚙️"),
            "autorole": ("lpf_icon_roles", "🏷️"),
            # Server & General Utility
            "ping": ("icons_ping", "📶"),
            "uptime": ("icons_reminder", "⏳"),
            "botinfo": ("icon_bot", "🤖"),
            "serverinfo": ("icon_forum", "🌐"),
            "userinfo": ("icon_person", "👤"),
            "avatar": ("icons_image", "🖼️"),
            "av": ("icons_image", "🖼️"),
            "banner": ("icons_image", "🖼️"),
            "uicolour": ("icons_settings", "🎨"),
            "uicolor": ("icons_settings", "🎨"),
            "prefix": ("icon_terminal", "⚙️"),
            "setprefix": ("icons_settings", "⚙️"),
            "invite": ("nt_icon_invite", "🔗"),
            "support": ("icons_supportteam", "💬"),
            "membercount": ("icons_people", "👥"),
            "help": ("icon_book", "📖"),
            "hca": ("icon_book", "📚"),
        }

        if clean in EXACT_MAP:
            key, fb = EXACT_MAP[clean]
            return em(key, fb)

        # 2. Semantic keyword matching
        KEYWORD_MAP: list[tuple[str, str, str]] = [
            ("ban", "icon_delete", "🔨"),
            ("kick", "icons_leave", "👢"),
            ("mute", "icons_micmute", "🔇"),
            ("warn", "icons_warning", "⚠️"),
            ("lock", "icons_locked", "🔒"),
            ("role", "lpf_icon_roles", "🏷️"),
            ("play", "music_playing", "▶️"),
            ("song", "music_music", "🎵"),
            ("music", "music_music", "🎵"),
            ("vol", "volume_up", "🔊"),
            ("ticket", "ticket_support", "🎫"),
            ("giveaway", "discord_giveaway", "🎉"),
            ("game", "icon_backpack", "🎮"),
            ("coin", "coin_spin", "🪙"),
            ("cash", "coin_spin", "💰"),
            ("money", "coin_spin", "💰"),
            ("user", "icon_person", "👤"),
            ("member", "icons_people", "👥"),
            ("server", "icon_forum", "🌐"),
            ("guild", "icon_forum", "🌐"),
            ("image", "icons_image", "🖼️"),
            ("pic", "icons_image", "🖼️"),
            ("voice", "icons_podcast", "🎙️"),
            ("log", "icon_logging", "📜"),
            ("set", "icons_settings", "⚙️"),
            ("config", "icons_settings", "⚙️"),
            ("find", "icon_search", "🔍"),
            ("search", "icon_search", "🔍"),
            ("add", "icons_plus", "➕"),
            ("del", "icon_delete", "🗑️"),
            ("rem", "icon_delete", "➖"),
            ("check", "verified_glow", "✅"),
        ]
        for kw, ek, fb in KEYWORD_MAP:
            if kw in clean:
                return em(ek, fb)

        # 3. Fallback to category icon
        if cat_name:
            cat_em = resolve_emoji(self.bot, cat_name, fallback="")
            if cat_em and cat_em != "•":
                return cat_em
        return em("heart_dot", "»")

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji or unicode fallback for category header."""
        raw = cat_name.split("・", 1)[-1].strip()
        fb = UNICODE_CATEGORY_EMOJIS.get(cat_name, "•")
        resolved = resolve_emoji(self.bot, raw, fallback="")
        if resolved and resolved != "•":
            return resolved
        return resolve_emoji(self.bot, cat_name, fallback=fb)

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

        for cmd in self.bot.commands:
            for c in _collect_all(cmd):
                if getattr(c, "hidden", False) and not is_owner:
                    continue
                target_cat = self._resolve_category(c)
                if target_cat not in categories:
                    categories[target_cat] = []
                if c not in categories[target_cat]:
                    categories[target_cat].append(c)

        ordered: dict[str, list[commands.Command]] = {}
        for cat in self.CATEGORY_ORDER:
            if cat in categories and categories[cat]:
                ordered[cat] = categories[cat]
        for cat, cmds in categories.items():
            if cat not in ordered and cmds:
                ordered[cat] = cmds
        return ordered

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]] | int | None = None,
        page: int = 1,
        custom_id_prefix: str = "",
    ) -> KyokaContainer:
        """Backward-compatible wrapper around build_category_container."""
        p = visible_categories if isinstance(visible_categories, int) else page
        return self.build_category_container(ctx, cat_name, commands_list, page=p)

    def build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        page: int = 1,
    ) -> KyokaContainer:
        """Construct a sleek category viewer container (Components V2)."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(name_or_cat: str, fallback: str = "") -> str:
            if not reg:
                return fallback
            res = reg.get_category(name_or_cat, fallback="")
            if not res:
                res = reg.get(name_or_cat, fallback=fallback)
            return res or fallback

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        raw_title = cat_name.split("・", 1)[-1].strip()

        unique_cmds: list[commands.Command] = []
        seen = set()
        for cmd in commands_list:
            if cmd.qualified_name not in seen:
                seen.add(cmd.qualified_name)
                unique_cmds.append(cmd)
        unique_cmds.sort(key=lambda c: c.qualified_name.lower())

        total_pages = max(1, math.ceil(len(unique_cmds) / HELP_COMMANDS_PER_PAGE))
        curr_page = max(1, min(page, total_pages))

        start_idx = (curr_page - 1) * HELP_COMMANDS_PER_PAGE
        end_idx = start_idx + HELP_COMMANDS_PER_PAGE
        page_cmds = unique_cmds[start_idx:end_idx]

        cat_icon = self._get_category_emoji(cat_name) or resolve_emoji(self.bot, "SETTINGS", fallback="⚔️")
        ui_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B2D31)

        cat_desc = (
            CATEGORY_DESCRIPTIONS.get(cat_name)
            or ("Aizen Gemini AI engine, 10 personalities & auto chat channels" if "AI" in raw_title.upper() else "Commands in this system.")
        )
        container = KyokaContainer(accent_color=ui_color)
        if cat_name in ("🤖・ARTIFICIAL INTELLIGENCE", "⛩️・AIZEN AI SYSTEM") or "AIZEN AI" in raw_title.upper():
            container.add_section(
                content=(
                    f"**{cat_icon} AIZEN AI SYSTEM MODULE**\n"
                    f"> High-performance conversational AI engine with 10 distinct personalities, natural automatic channel conversations, and real-time diagnostics."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"**Available Personalities (10 Total):**\n"
                f"> 🌸 `girlfriend` • 💅 `baddie` • 😈 `special` (Restricted) • 🤝 `friendly` • 🎭 `funny`\n"
                f"> 🔥 `savage` • ⚡ `anime` • ⛩️ `aizen` • 🌟 `friend` • ⚙️ `custom`\n\n"
                f"**Core AI Commands & Syntax:**\n"
                f"• `{prefix}ai <message>` — Direct conversation with active personality\n"
                f"• `{prefix}ai personalities` — Browse all 10 personalities with interactive selector\n"
                f"• `{prefix}ai setup [#channel]` — Enable automatic natural chat in a channel\n"
                f"• `{prefix}aidiag` — Real-time performance & provider latency diagnostics\n"
                f"• `{prefix}aigf`, `{prefix}aibaddie`, `{prefix}aispecial` — Direct persona shortcuts"
            )
            container.add_separator()
        else:
            container.add_text(f"### {cat_icon} {raw_title} Module (Page {curr_page}/{total_pages})")
            container.add_text(f"> {cat_desc}")
            container.add_separator()

        cmd_lines = [f"**Commands ({len(unique_cmds)}):**"]
        for cmd in page_cmds:
            badge = self._get_badge(cmd)
            raw_desc = cmd.description if isinstance(getattr(cmd, "description", None), str) and cmd.description else (
                cmd.help if isinstance(getattr(cmd, "help", None), str) else ""
            )
            desc = (raw_desc or "No description provided.").strip().split("\n")[0][:75]
            raw_sig = cmd.signature if isinstance(getattr(cmd, "signature", None), str) else ""
            sig = f" {raw_sig}" if raw_sig else ""
            cmd_emoji = self.resolve_command_emoji(cmd.qualified_name, raw_title)
            cmd_lines.append(f"> {cmd_emoji} **`{prefix}{cmd.qualified_name}{sig}`**{badge}\n> *{desc}*")

        container.add_text("\n".join(cmd_lines))
        return container

    def _get_cached_branding(self, guild_id: int | None) -> dict[str, Any]:
        """Synchronously read cached guild branding when configured."""
        branding_mgr = getattr(self.bot, "branding_mgr", None)
        cache = getattr(branding_mgr, "_cache", None) if branding_mgr else None
        if guild_id and isinstance(cache, dict):
            entry = cache.get(guild_id)
            if isinstance(entry, dict):
                return entry
        return {}

    def build_home_embed(self, ctx: CustomContext, visible_categories: dict[str, list[commands.Command]]) -> discord.Embed:
        """Construct the signature KYOKA Help Homepage (compact embed fallback)."""
        term_icon = resolve_emoji(self.bot, "TERMINAL", fallback=">_")
        cmd_icon = resolve_emoji(self.bot, "BRACKETS", fallback="{ }")
        mod_icon = resolve_emoji(self.bot, "MODULES", fallback="⊞")
        book_icon = resolve_emoji(self.bot, "BOOK", fallback="📖")
        dot = resolve_emoji(self.bot, "ARROW", fallback="»")

        gid = ctx.guild.id if ctx.guild else None
        branding = self._get_cached_branding(gid)
        is_custom = bool(branding.get("is_custom"))
        brand_name = str(branding.get("display_name") or "").strip() if is_custom and branding.get("display_name") else "KYOKA"
        bio_text = (
            str(branding.get("bio") or "").strip()
            if is_custom and branding.get("bio")
            else (
                "Experience the ultimate Discord bot designed for seamless server management, "
                "bulletproof security, high-fidelity music, and community engagement."
            )
        )

        prefix = self.bot.guild_mgr.get_prefix(gid)
        latency_ms = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        modules_count = len(visible_categories)

        raw_color = self.bot.guild_mgr.get_ui_color(gid, default=0x2B0938)
        embed_color = raw_color if isinstance(raw_color, int) and not isinstance(raw_color, bool) else 0x2B0938
        embed = discord.Embed(
            title=f"⛩️ Hey, I'm {brand_name}",
            description=(
                f"{bio_text}\n\n"
                f"{dot} **Latency:** `{latency_ms}ms`\n"
                f"{term_icon} **Prefix:** `{prefix}` | **Slash:** `/`\n"
                f"{cmd_icon} **Available Commands:** `{total_commands:,}`\n"
                f"{mod_icon} **Command Modules:** `{modules_count}`\n"
                f"{book_icon} **Essential Commands:** `{prefix}help`, `{prefix}ping`, `{prefix}play`, `{prefix}setup`"
            ),
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        custom_avatar = branding.get("avatar_url") if is_custom else None
        if isinstance(custom_avatar, str) and custom_avatar.startswith("http"):
            embed.set_thumbnail(url=custom_avatar)
        elif getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        custom_banner = branding.get("banner_url") if is_custom else None
        banner_url = (
            custom_banner
            if isinstance(custom_banner, str) and custom_banner.startswith("http")
            else (Config.ASSETS.HELP_BANNER_URL or Config.ASSETS.BANNER_URL)
        )
        if not banner_url or not str(banner_url).startswith("http"):
            banner_url = "https://raw.githubusercontent.com/ruthupavangoud2009-cmd/aizen-bot/main/assets/branding/kyoka_banner.png"
        embed.set_image(url=banner_url)

        embed.set_footer(
            text=f"{book_icon} Use {prefix}help <command> for details • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

        return embed

    def build_category_embed(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]] | int | None = None,
        page: int = 1,
    ) -> discord.Embed:
        """Construct a sleek, compact category command viewer matching KYOKA & Greed style."""
        if isinstance(visible_categories, int):
            page = visible_categories
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        raw_title = cat_name.split("・", 1)[-1].strip()

        # Deduplicate and sort commands
        unique_cmds: list[commands.Command] = []
        seen = set()
        for cmd in commands_list:
            if cmd.qualified_name not in seen:
                seen.add(cmd.qualified_name)
                unique_cmds.append(cmd)
        unique_cmds.sort(key=lambda c: c.qualified_name.lower())

        total_pages = max(1, math.ceil(len(unique_cmds) / HELP_COMMANDS_PER_PAGE))
        curr_page = max(1, min(page, total_pages))

        start_idx = (curr_page - 1) * HELP_COMMANDS_PER_PAGE
        end_idx = start_idx + HELP_COMMANDS_PER_PAGE
        page_cmds = unique_cmds[start_idx:end_idx]

        cat_icon = self._get_category_emoji(cat_name) or resolve_emoji(self.bot, "SETTINGS", fallback="⚔️")
        desc_lines = [
            f"> {CATEGORY_DESCRIPTIONS.get(cat_name, 'Commands in this system.')}\n",
            f"**Page {curr_page}/{total_pages} • Commands ({len(unique_cmds)}):**",
        ]

        for cmd in page_cmds:
            badge = self._get_badge(cmd)
            raw_desc = cmd.description if isinstance(getattr(cmd, "description", None), str) and cmd.description else (
                cmd.help if isinstance(getattr(cmd, "help", None), str) else ""
            )
            desc = (raw_desc or "No description provided.").strip().split("\n")[0][:75]
            raw_sig = cmd.signature if isinstance(getattr(cmd, "signature", None), str) else ""
            sig = f" {raw_sig}" if raw_sig else ""
            cmd_emoji = self.resolve_command_emoji(cmd.qualified_name, raw_title)
            desc_lines.append(f"> {cmd_emoji} **`{prefix}{cmd.qualified_name}{sig}`**{badge}\n> *{desc}*")

        raw_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B0938)
        embed_color = raw_color if isinstance(raw_color, int) and not isinstance(raw_color, bool) else 0x2B0938
        embed = discord.Embed(
            title=f"{cat_icon} {raw_title} Module (Page {curr_page}/{total_pages})".strip(),
            description="\n".join(desc_lines)[:4000],
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        gid = ctx.guild.id if ctx.guild else None
        branding = self._get_cached_branding(gid)
        is_custom = bool(branding.get("is_custom"))
        custom_avatar = branding.get("avatar_url") if is_custom else None
        if isinstance(custom_avatar, str) and custom_avatar.startswith("http"):
            embed.set_thumbnail(url=custom_avatar)
        elif getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        custom_banner = branding.get("banner_url") if is_custom else None
        if isinstance(custom_banner, str) and custom_banner.startswith("http"):
            embed.set_image(url=custom_banner)

        embed.set_footer(
            text=f"📖 Page {curr_page}/{total_pages} • Use {prefix}help <command> for syntax • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

        return embed

    def build_command_embed(self, ctx: CustomContext, cmd: commands.Command) -> discord.Embed:
        """Construct detailed single-command inspector card."""
        arrow_icon = resolve_emoji(self.bot, "ARROW", fallback="•")
        bullet = arrow_icon if arrow_icon else "•"

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        resolved_cat = self._resolve_category(cmd)
        badge = self._get_badge(cmd)

        embed = discord.Embed(
            title=f"Command Manual: `{cmd.qualified_name}` {badge}".strip(),
            description=f"> {cmd.description or cmd.help or 'No detailed description provided for this command.'}",
            color=0x2B0938,
            timestamp=discord.utils.utcnow(),
        )

        sig = f" {cmd.signature}" if cmd.signature else ""
        embed.add_field(
            name="Syntax & Usage",
            value=f"`{prefix}{cmd.qualified_name}{sig}`",
            inline=False,
        )

        if getattr(cmd, "aliases", None):
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{a}`" for a in cmd.aliases),
                inline=True,
            )

        embed.add_field(
            name="Category",
            value=f"`{resolved_cat}`",
            inline=True,
        )

        try:
            if getattr(cmd, "_buckets", None) and hasattr(cmd._buckets, "_cooldown") and cmd._buckets._cooldown:
                cd = cmd._buckets._cooldown.per
                embed.add_field(name="Cooldown", value=f"`{cd:.1f}s`", inline=True)
        except Exception:
            pass

        gid = ctx.guild.id if ctx.guild else None
        branding = self._get_cached_branding(gid)
        is_custom = bool(branding.get("is_custom"))
        custom_avatar = branding.get("avatar_url") if is_custom else None
        if isinstance(custom_avatar, str) and custom_avatar.startswith("http"):
            embed.set_thumbnail(url=custom_avatar)
        elif getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        custom_banner = branding.get("banner_url") if is_custom else None
        if isinstance(custom_banner, str) and custom_banner.startswith("http"):
            embed.set_image(url=custom_banner)

        embed.set_footer(
            text=f"-# Requested by {ctx.author.display_name} • KYOKA Aizen Edition",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

        return embed

    def build_search_results_embed(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        query: str,
    ) -> discord.Embed:
        """Construct search results matching commands against user query."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(category_name: str) -> str:
            if not reg:
                return ""
            return reg.get_category(category_name, fallback="")

        arrow_icon = get_em("ARROW")
        search_icon = get_em("SEARCH")
        bullet = arrow_icon if arrow_icon else "•"

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
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
            title=f"🔍 Search Results for: `{clean_query}`" if matched else "⚠️ Command or Category Not Found",
            color=0x2B0938,
            timestamp=discord.utils.utcnow(),
        )

        if not matched:
            embed.description = f"> No accessible commands matching **`{clean_query}`** were found in your accessible categories."
            embed.color = 0xED4245
        else:
            embed.description = f"Found **{len(matched)}** command(s) matching `{clean_query}`:\n"
            matched.sort(key=lambda it: it[0].qualified_name.lower())
            for cmd, cat in matched[:10]:
                badge = self._get_badge(cmd)
                desc = (cmd.description or cmd.help or "No description provided.").strip().split("\n")[0][:100]
                sig = f" {cmd.signature}" if cmd.signature else ""
                embed.add_field(
                    name=f"{bullet} `{prefix}{cmd.qualified_name}{sig}`{badge}",
                    value=f"> {desc}\n> *Module: {cat}*",
                    inline=False,
                )

        embed.set_footer(
            text=f"-# Requested by {ctx.author.display_name} • Type {prefix}help <command> for full manual",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )
        return embed

    def build_hca_index_embed(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Construct the master Help Command Archive (HCA) index directory embed."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        total_commands = sum(len(cmds) for cmds in all_categories.values())

        embed = discord.Embed(
            title="📚 KYOKA — Help Command Archive (HCA)",
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
        """Construct a paginated category archive card for HCA."""
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
            description="\n".join(desc_lines)[:4000],
            color=0x2B0938,
        )
        image_key = cat_meta.image_key if cat_meta else "general"
        banner_file = AssetManager.attach_help_banner(embed, image_key)
        embed.set_footer(
            text=f"Page {safe_page}/{total_pages} • {len(unique_cmds)} Commands • Public Archive • KYOKA",
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

        AssetManager.attach_help_banner(embed, "home")
        embed.set_footer(
            text=f"Archive Search • Requested by {ctx.author.display_name} • KYOKA",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed

    def build_hca_all_embed(
        self,
        ctx: CustomContext,
        all_categories: dict[str, list[commands.Command]],
        page: int = 1,
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        """Construct a paginated flat archive of all registered commands."""
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        all_items: list[tuple[commands.Command, str]] = []
        seen: set[str] = set()
        for cat_name, cmds in all_categories.items():
            for c in cmds:
                if c.qualified_name not in seen:
                    seen.add(c.qualified_name)
                    all_items.append((c, cat_name))
        import re as _re
        def _nat_key(item: tuple[commands.Command, str]) -> list[tuple[int, Any]]:
            parts = _re.split(r"(\d+)", item[0].qualified_name.lower())
            return [(0, int(p)) if p.isdigit() else (1, p) for p in parts if p]

        all_items.sort(key=_nat_key)

        per_page = 10
        total_pages = max(1, math.ceil(len(all_items) / per_page))
        safe_page = max(1, min(page, total_pages))
        start_idx = (safe_page - 1) * per_page
        page_items = all_items[start_idx : start_idx + per_page]

        embed = discord.Embed(
            title="📋 KYOKA — All Commands Archive",
            description=(
                f"> **Page **{safe_page}/{total_pages}** • `{len(all_items)}` total commands across all modules**\n"
                f"> Use `{p}help <command>` for detailed syntax and examples."
            ),
            color=0x2B0938,
        )
        for c, cat_name in page_items:
            desc = (c.description or getattr(c, "help", None) or "No description.").strip().split("\n")[0][:90]
            sig = f" {c.signature}" if c.signature else ""
            embed.add_field(
                name=f"`{p}{c.qualified_name}{sig}`",
                value=f"> {desc}\n> *{cat_name}*",
                inline=False,
            )

        banner_file = AssetManager.attach_help_banner(embed, "home")
        embed.set_footer(
            text=f"All Commands • Page {safe_page}/{total_pages} • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
        )
        return embed, banner_file

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
        if selected_val == "all":
            return self.build_hca_all_embed(ctx, all_categories, page=page)
        matched_cat = next((c for c in all_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            return self.build_hca_category_embed(
                ctx, matched_cat, all_categories[matched_cat], all_categories, page=page
            )
        return self.build_hca_index_embed(ctx, all_categories)

    # ── Help Commands (Prefix + Slash) ───────────────────────────────────────

    @commands.hybrid_command(
        name="help",
        aliases=["h", "commands", "menu", "modules"],
        description="Open the KYOKA Aizen Edition interactive help console.",
    )
    async def help_command(
        self,
        ctx: CustomContext,
        *,
        command_or_module: Optional[str] = None,
    ) -> None:
        """Interactive Help Console for KYOKA."""
        try:
            # Immediate deferral for slash commands to prevent Discord 3s interaction timeout
            if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
                try:
                    await ctx.interaction.response.defer()
                except Exception:
                    pass

            visible_categories = await self._get_visible_categories(ctx)

            # 1. Single Command or Direct Category Lookup
            if command_or_module:
                raw_arg = command_or_module.strip()
                tokens = raw_arg.split()
                req_page = 1
                clean_arg = raw_arg.lower()

                # Handle "music 2" or "mod 2" style arguments (page number as second word)
                if len(tokens) >= 2 and tokens[-1].isdigit():
                    req_page = max(1, int(tokens[-1]))
                    clean_arg = " ".join(tokens[:-1]).strip().lower()

                # Check if exact category match
                matched_cat = next(
                    (c for c in visible_categories if clean_arg in c.lower()),
                    None,
                )
                if matched_cat:
                    cmds = visible_categories[matched_cat]
                    container = self.build_category_container(ctx, matched_cat, cmds, page=req_page)
                    view = HelpView(self, ctx, visible_categories, current_category=matched_cat, current_page=req_page)
                    try:
                        msg = await send_container_response(ctx, container, view=view)
                        view.message = msg
                    except Exception:
                        try:
                            embed = self.build_category_embed(ctx, matched_cat, cmds, page=req_page)
                            msg = await _safe_help_send(ctx, embed=embed, view=view)
                            view.message = msg
                        except Exception:
                            embed = self.build_category_embed(ctx, matched_cat, cmds, page=req_page)
                            await _safe_help_send(ctx, embed=embed)
                    return

                # Check if command match
                cmd = self.bot.get_command(clean_arg)
                if cmd and self._can_run_command(cmd, ctx):
                    embed = self.build_command_embed(ctx, cmd)
                    await _safe_help_send(ctx, embed=embed)
                    return

                # Fallback to search query
                embed = self.build_search_results_embed(ctx, visible_categories, clean_arg)
                view = HelpView(self, ctx, visible_categories, current_category="home")
                try:
                    msg = await _safe_help_send(ctx, embed=embed, view=view)
                    view.message = msg
                except Exception:
                    await _safe_help_send(ctx, embed=embed)
                return

            # 2. Default Homepage View
            container = self.build_home_container(ctx, visible_categories)
            view = HelpView(self, ctx, visible_categories, current_category="home", current_page=1)
            try:
                msg = await send_container_response(ctx, container, view=view)
                view.message = msg
            except Exception:
                try:
                    embed = self.build_home_embed(ctx, visible_categories)
                    msg = await _safe_help_send(ctx, embed=embed, view=view)
                    view.message = msg
                except Exception:
                    embed = self.build_home_embed(ctx, visible_categories)
                    await _safe_help_send(ctx, embed=embed)
        except Exception as exc:
            logger.exception(f"Unhandled notice in help_command: {exc}")
            try:
                prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
            except Exception:
                prefix = "+"
            try:
                emb = discord.Embed(
                    title="📖 KYOKA Help Menu",
                    description=(
                        f"Welcome to **KYOKA**.\n\n"
                        f"• Use `{prefix}help <command>` to inspect a command manual.\n"
                        f"• Use `{prefix}ping` for latency and system diagnostics.\n"
                        f"• Use `{prefix}hca` for the complete command archive."
                    ),
                    color=0x7C3AED,
                )
                await _safe_help_send(ctx, embed=emb)
            except Exception:
                await _safe_help_send(
                    ctx,
                    content=f"📖 **KYOKA Help:** Use `{prefix}help <command>` or `{prefix}ping` to test system speed.",
                )

    @commands.command(
        name="hca",
        aliases=["archive", "allcommands", "directory", "cmds"],
        description="Public all-commands directory and architecture archive for KYOKA.",
    )
    async def hca_command(self, ctx: CustomContext, *, category: Optional[str] = None) -> None:
        """Browse all registered prefix and slash commands across all bot modules."""
        all_categories = await self._get_all_registered_categories(ctx)
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        if category:
            query = category.lower().strip()
            if query in ("all", "allcommands"):
                view = HCAView(cog=self, ctx=ctx, all_categories=all_categories, current_category="all", current_page=1)
                embed, banner_file = self.build_hca_all_embed(ctx, all_categories, page=1)
                msg = await ctx.send(embed=embed, file=banner_file, view=view) if banner_file else await ctx.send(embed=embed, view=view)
                view.message = msg
                return
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
                msg = await ctx.send(embed=embed, file=banner_file, view=view) if banner_file else await ctx.send(embed=embed, view=view)
                view.message = msg
                return

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
                    f"• `{p}hca bloxai` — View Blox Fruits AI commands\n"
                    f"• `{p}hca ai` — View AI and Voice commands\n"
                    f"• `{p}hca` — Open the master Archive Index"
                ),
                color=0xED4245,
            )
            view = HCAView(cog=self, ctx=ctx, all_categories=all_categories, current_category="home", current_page=1)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            return

        view = HCAView(cog=self, ctx=ctx, all_categories=all_categories, current_category="home", current_page=1)
        embed, banner_file = self.build_hca_index_embed(ctx, all_categories)
        msg = await ctx.send(embed=embed, file=banner_file, view=view) if banner_file else await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(
        name="premium",
        aliases=["plan", "tier", "perks"],
        description="Display this server's current tier and KYOKA feature matrix.",
    )
    async def view_plan(self, ctx: CustomContext) -> None:
        """Display this server's current tier and KYOKA feature access matrix."""
        guild = ctx.guild
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        tier_title = "👑 Supreme Premium (All Features Unlocked)"
        expiry_str = "Lifetime / Active"
        if guild and hasattr(self.bot, "premium_mgr") and self.bot.premium_mgr:
            try:
                if self.bot.premium_mgr.is_guild_premium(guild.id):
                    info = self.bot.premium_mgr.get_guild_info(guild.id)
                    tier_title = f"💎 Kyoka {info.get('tier', 'Premium')}"
                    expiry_str = info.get("remaining_str", "Active")
            except Exception:
                pass

        embed = discord.Embed(
            title="⛩️ KYOKA • PLAN & FEATURE ACCESS MATRIX",
            description=(
                f"**Current Server:** `{guild.name if guild else 'Direct Message'}`\n"
                f"**Active Entitlement:** `{tier_title}`\n"
                f"**Status / Expiry:** `{expiry_str}`\n\n"
                f"Use `{p}help` to explore every enabled module in this server."
            ),
            color=0x7C3AED,
        )
        await _safe_help_send(ctx, embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
