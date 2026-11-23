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
from src.ui.categories import (
    CATEGORIES,
    CATEGORY_BY_TAG,
    resolve_command_category,
)

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Help")

HELP_COMMANDS_PER_PAGE: int = 8

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


class HelpCategorySelect(discord.ui.Select):
    """Interactive category select menu for switching between command categories."""

    def __init__(
        self,
        help_view: HelpView,
        visible_categories: dict[str, list[commands.Command]],
        current_selection: str = "home",
    ) -> None:
        self.help_view = help_view
        emoji_registry = getattr(help_view.cog.bot, "custom_emojis", None)

        def resolve_menu_emoji(cat_name: Optional[str] = None) -> Optional[discord.PartialEmoji | str]:
            if not cat_name or cat_name.lower() == "home":
                if emoji_registry:
                    obj = emoji_registry.get_category_obj("HOME")
                    if obj:
                        return obj
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

            if emoji_registry:
                obj = emoji_registry.get_category_obj(cat_key)
                if obj:
                    return obj
            fallback_map = {
                "HOME": "🏠", "MODERATION": "⚔️", "ANTI_NUKE": "🛡️", "WELCOMER": "🚪",
                "VERIFICATION": "✅", "TICKET": "🎫", "ROLE": "🏷️", "GIVEAWAY": "🎉",
                "MUSIC": "🎵", "AFK": "💤", "AI": "🤖", "LEVEL": "⭐", "MEDIA": "🖼️",
                "MEMBERS": "👥", "PREMIUM": "💎", "ADMIN": "⚙️", "UTILITY": "🔧",
                "OWNER": "👑", "GAMES": "🎮", "VOICE": "🎙️", "CASINO": "🎰",
                "LOGGING": "📜", "SETTINGS": "⚙️",
            }
            return fallback_map.get(cat_key, "📁")

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

        super().__init__(
            placeholder="Select a module to view commands...",
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
        reg = getattr(self.cog.bot, "custom_emojis", None)

        def btn_emoji(cat_name: str) -> Optional[discord.PartialEmoji | str]:
            if not reg:
                return None
            return reg.get_category_obj(cat_name)

        # Row 0: Dropdown
        self.category_select = HelpCategorySelect(
            self,
            self.visible_categories,
            current_selection=self.current_category,
        )
        self.add_item(self.category_select)

        # On Home: Keep ultra-clean Greed style (only dropdown inside container)
        if self.current_category != "home":
            cmds = self.visible_categories.get(self.current_category, [])
            total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))

            btn_back = discord.ui.Button(
                label="Back",
                emoji=btn_emoji("BACK"),
                style=discord.ButtonStyle.secondary,
                disabled=(self.current_page <= 1),
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
                disabled=(self.current_page >= total_pages),
                row=1,
            )
            btn_next.callback = self.btn_next_callback
            self.add_item(btn_next)

    def to_container_components(self) -> list[dict[str, Any]]:
        """Pack select menu, pagination, and Greed-style footer inside Components V2 Container."""
        comps: list[dict[str, Any]] = []
        if hasattr(self, "category_select"):
            comps.append({"type": 1, "components": [self.category_select.to_dict()]})

        if self.current_category != "home":
            btn_comps = []
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    btn_comps.append(item.to_dict())
            if btn_comps:
                comps.append({"type": 1, "components": btn_comps[:5]})

        prefix = self.cog.bot.guild_mgr.get_prefix(self.ctx.guild.id if self.ctx.guild else None)
        reg = getattr(self.cog.bot, "custom_emojis", None)
        book_em = reg.get("book", fallback="📖") if reg else "📖"
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
            await interaction.response.edit_message(embed=embed, view=self)
        cmds = self.visible_categories.get(cat_name, [])
        embed = self.cog.build_category_embed(self.ctx, cat_name, cmds, page=page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        if self.current_page > 1:
            await self.switch_to_category(interaction, self.current_category, page=self.current_page - 1)

    async def btn_home_callback(self, interaction: discord.Interaction) -> None:
        await self.switch_to_home(interaction)

    async def btn_next_callback(self, interaction: discord.Interaction) -> None:
        cmds = self.visible_categories.get(self.current_category, [])
        total_pages = max(1, math.ceil(len(cmds) / HELP_COMMANDS_PER_PAGE))
        if self.current_page < total_pages:
            await self.switch_to_category(interaction, self.current_category, page=self.current_page + 1)

    async def btn_search_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(HelpSearchModal(self))


class Help(commands.Cog, name="Help"):
    """Signature KYOKA Aizen Edition Help Console."""
    category: str = "General"

    CATEGORY_ORDER = [
        "🏠・GETTING STARTED",
        "🤖・ARTIFICIAL INTELLIGENCE",
        "🛡️・MODERATION",
        "🔒・AUTOMOD & SECURITY",
        "👋・WELCOME & AUTOMOD",
        "🛡️・VERIFICATION",
        "🎫・TICKETS & SUPPORT",
        "🎉・GIVEAWAYS & EVENTS",
        "🎵・MUSIC",
        "💤・AFK",
        "⭐・VOUCHES & REPUTATION",
        "🍎・BLOX FRUITS AI",
        "⭐・LEVELS & COMMUNITY",
        "🖼️・IMAGES & AVATARS",
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

    def build_home_container(self, ctx: CustomContext, visible_categories: dict[str, list[commands.Command]]) -> KyokaContainer:
        """Construct the signature Greed-style KyokaContainer (Components V2)."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(name_or_cat: str, fallback: str = "") -> str:
            if not reg:
                return fallback
            res = reg.get_category(name_or_cat, fallback="")
            if not res:
                res = reg.get(name_or_cat, fallback=fallback)
            return res or fallback

        term_icon = get_em("terminal", fallback=">_")
        cmd_icon = get_em("brackets", fallback="{ }")
        mod_icon = get_em("modules", fallback="⊞")

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        modules_count = len(visible_categories)
        ui_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B2D31)

        container = KyokaContainer(accent_color=ui_color)

        # 1. Top banner image (matching Greed top banner)
        banner_url = Config.ASSETS.HELP_BANNER_URL or Config.ASSETS.BANNER_URL
        if not banner_url or not banner_url.startswith("http"):
            banner_url = "https://raw.githubusercontent.com/ruthupavangoud2009-cmd/aizen-bot/main/assets/branding/kyoka_banner.png"
        container.add_media(banner_url)

        # 2. Section with Title and Description + Avatar Thumbnail
        avatar_url = self.bot.user.display_avatar.url if getattr(self.bot, "user", None) else None
        section_text = (
            "### kyoka help\n"
            "Experience the ultimate Discord bot designed for seamless server management, "
            "bulletproof security, high-fidelity music, and community engagement."
        )
        if avatar_url:
            container.add_section(section_text, accessory={"type": 11, "media": {"url": avatar_url}})
        else:
            container.add_text(section_text)

        # 3. Clean Separator
        container.add_separator()

        # 4. Stats formatted exactly like Greed
        stats_text = (
            f"{term_icon} **Prefix** `{prefix}`\n"
            f"{cmd_icon} **Commands** `{total_commands:,}`\n"
            f"{mod_icon} **Modules** `{modules_count}`"
        )
        container.add_text(stats_text)

        return container

    def resolve_command_emoji(self, cmd_name: str, cat_name: str = "") -> str:
        """
        Resolve a dedicated custom emoji for every single command in KYOKA.
        Prefers application emojis (<:name:id> / <a:name:id>), falls back to dedicated clean symbols.
        """
        reg = getattr(self.bot, "custom_emojis", None)
        clean = cmd_name.lower().strip()

        def em(key: str, fallback: str) -> str:
            if reg:
                val = reg.get(key)
                if val:
                    return val
                cat_val = reg.get_category(key, fallback="")
                if cat_val:
                    return cat_val
            return fallback

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
            cat_em = reg.get_category(cat_name, fallback="") if reg else ""
            if cat_em:
                return cat_em
        return em("heart_dot", "💜")

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

        cat_icon = get_em(raw_title) or get_em("SETTINGS") or "⚔️"
        ui_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B2D31)

        container = KyokaContainer(accent_color=ui_color)
        container.add_text(f"### {cat_icon} {raw_title} Module (Page {curr_page}/{total_pages})")
        container.add_text(f"> {CATEGORY_DESCRIPTIONS.get(cat_name, 'Commands in this system.')}")
        container.add_separator()

        cmd_lines = [f"**Commands ({len(unique_cmds)}):**"]
        for cmd in page_cmds:
            badge = self._get_badge(cmd)
            desc = (cmd.description or cmd.help or "No description provided.").strip().split("\n")[0][:75]
            sig = f" {cmd.signature}" if cmd.signature else ""
            cmd_emoji = self.resolve_command_emoji(cmd.qualified_name, raw_title)
            cmd_lines.append(f"> {cmd_emoji} **`{prefix}{cmd.qualified_name}{sig}`**{badge}\n> *{desc}*")

        container.add_text("\n".join(cmd_lines))
        return container

    def build_home_embed(self, ctx: CustomContext, visible_categories: dict[str, list[commands.Command]]) -> discord.Embed:
        """Construct the signature KYOKA Aizen Edition Help Homepage (Greed style fallback)."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(name_or_cat: str, fallback: str = "") -> str:
            if not reg:
                return fallback
            res = reg.get_category(name_or_cat, fallback="")
            if not res:
                res = reg.get(name_or_cat, fallback=fallback)
            return res or fallback

        term_icon = get_em("terminal", fallback=">_")
        cmd_icon = get_em("brackets", fallback="{ }")
        mod_icon = get_em("modules", fallback="⊞")
        book_icon = get_em("book", fallback="📖")

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        modules_count = len(visible_categories)

        embed_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B2D31)
        embed = discord.Embed(
            title="kyoka help",
            description=(
                "Experience the ultimate Discord bot designed for seamless server management, "
                "bulletproof security, high-fidelity music, and community engagement.\n\n"
                f"{term_icon} **Prefix** `{prefix}`\n"
                f"{cmd_icon} **Commands** `{total_commands:,}`\n"
                f"{mod_icon} **Modules** `{modules_count}`"
            ),
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        if getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        banner_url = Config.ASSETS.HELP_BANNER_URL or Config.ASSETS.BANNER_URL
        if not banner_url or not banner_url.startswith("http"):
            banner_url = "https://raw.githubusercontent.com/ruthupavangoud2009-cmd/aizen-bot/main/assets/branding/kyoka_banner.png"
        embed.set_image(url=banner_url)

        embed.set_footer(
            text=f"{book_icon} Use {prefix}help (command) for details on a specific command • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

        return embed

    def build_category_embed(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        page: int = 1,
    ) -> discord.Embed:
        """Construct a sleek, compact category command viewer matching Kyro & Greed style."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(category_name: str) -> str:
            if not reg:
                return ""
            return reg.get_category(category_name, fallback="")

        heart = reg.get("heart_dot", "💜") if reg else "💜"
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

        cat_icon = get_em(raw_title) or get_em("SETTINGS") or "⚔️"
        desc_lines = [
            f"> {CATEGORY_DESCRIPTIONS.get(cat_name, 'Commands in this system.')}\n",
            f"**Commands ({len(unique_cmds)}):**",
        ]

        for cmd in page_cmds:
            badge = self._get_badge(cmd)
            desc = (cmd.description or cmd.help or "No description provided.").strip().split("\n")[0][:75]
            sig = f" {cmd.signature}" if cmd.signature else ""
            cmd_emoji = self.resolve_command_emoji(cmd.qualified_name, raw_title)
            desc_lines.append(f"> {cmd_emoji} **`{prefix}{cmd.qualified_name}{sig}`**{badge}\n> *{desc}*")

        embed_color = self.bot.guild_mgr.get_ui_color(ctx.guild.id if ctx.guild else None, default=0x2B0938)
        embed = discord.Embed(
            title=f"{cat_icon} {raw_title} Module (Page {curr_page}/{total_pages})".strip(),
            description="\n".join(desc_lines)[:4000],
            color=embed_color,
            timestamp=discord.utils.utcnow(),
        )

        if getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.set_footer(
            text=f"📖 Page {curr_page}/{total_pages} • Use {prefix}help <command> for syntax • Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

        return embed

        return embed

    def build_command_embed(self, ctx: CustomContext, cmd: commands.Command) -> discord.Embed:
        """Construct detailed single-command inspector card."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(category_name: str) -> str:
            if not reg:
                return ""
            return reg.get_category(category_name, fallback="")

        arrow_icon = get_em("ARROW")
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

        if getattr(cmd, "_buckets", None) and hasattr(cmd._buckets, "_cooldown") and cmd._buckets._cooldown:
            cd = cmd._buckets._cooldown.per
            embed.add_field(name="Cooldown", value=f"`{cd:.1f}s`", inline=True)

        if getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

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
            title=f"{search_icon} Search Results: `{clean_query}`".strip(),
            color=0x2B0938,
            timestamp=discord.utils.utcnow(),
        )

        if not matched:
            embed.description = f"> No commands matching **`{clean_query}`** were found in your accessible categories."
            embed.color = 0xEF4444
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

    # ── Help Commands (Prefix + Slash) ───────────────────────────────────────

    @commands.hybrid_command(
        name="help",
        aliases=["h", "commands", "menu"],
        description="Open the KYOKA Aizen Edition interactive help console.",
    )
    async def help_command(
        self,
        ctx: CustomContext,
        *,
        command_or_category: Optional[str] = None,
    ) -> None:
        """Interactive Help Console for KYOKA."""
        # Immediate deferral for slash commands to prevent Discord 3s interaction timeout
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer()
            except Exception:
                pass

        visible_categories = await self._get_visible_categories(ctx)

        # 1. Single Command or Direct Category Lookup
        if command_or_category:
            clean_arg = command_or_category.strip().lower()

            # Check if exact category match
            matched_cat = next(
                (c for c in visible_categories if clean_arg in c.lower()),
                None,
            )
            if matched_cat:
                cmds = visible_categories[matched_cat]
                container = self.build_category_container(ctx, matched_cat, cmds, page=1)
                view = HelpView(self, ctx, visible_categories, current_category=matched_cat, current_page=1)
                try:
                    msg = await send_container_response(ctx, container, view=view)
                    view.message = msg
                except Exception:
                    embed = self.build_category_embed(ctx, matched_cat, cmds, page=1)
                    msg = await ctx.send(embed=embed, view=view)
                    view.message = msg
                return

            # Check if command match
            cmd = self.bot.get_command(clean_arg)
            if cmd and self._can_run_command(cmd, ctx):
                embed = self.build_command_embed(ctx, cmd)
                await ctx.send(embed=embed)
                return

            # Fallback to search query
            embed = self.build_search_results_embed(ctx, visible_categories, clean_arg)
            view = HelpView(self, ctx, visible_categories, current_category="home")
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            return

        # 2. Default Homepage View
        container = self.build_home_container(ctx, visible_categories)
        view = HelpView(self, ctx, visible_categories, current_category="home", current_page=1)
        try:
            msg = await send_container_response(ctx, container, view=view)
            view.message = msg
        except Exception:
            embed = self.build_home_embed(ctx, visible_categories)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

    @commands.command(
        name="hca",
        aliases=["archive", "allcommands"],
        description="Open the complete KYOKA Command Archive.",
    )
    async def hca_command(self, ctx: CustomContext) -> None:
        """Display all public commands in the archive."""
        await self.help_command(ctx)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
