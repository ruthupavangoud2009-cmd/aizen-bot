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
    "🧾・BLOX FRUITS SERVICE BILLS": "Blox Fruits service invoices, itemized receipts, fruits & Robux payment",
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
            if not emoji_registry:
                return None
            if not cat_name or cat_name == "home":
                return emoji_registry.get_category_obj("HOME")
            raw_category = cat_name.split("・", 1)[-1].strip().upper()
            mapping = {
                "GETTING STARTED": "HOME",
                "MODERATION": "MODERATION",
                "AUTOMOD & SECURITY": "SECURITY",
                "WELCOME & AUTOMOD": "SERVER",
                "VERIFICATION": "VERIFICATION",
                "TICKETS & SUPPORT": "TICKET",
                "REACTION ROLES": "SETTINGS",
                "GIVEAWAYS & EVENTS": "PREMIUM",
                "MUSIC": "MUSIC",
                "AFK": "AFK",
                "VOUCHES & REPUTATION": "LEVEL",
                "BLOX FRUITS SERVICE BILLS": "SAVE",
                "BLOX FRUITS AI": "AI",
                "ARTIFICIAL INTELLIGENCE": "AI",
                "LEVELS & COMMUNITY": "LEVEL",
                "IMAGES & AVATARS": "PROFILE",
                "SOCIAL & FUN": "MEMBERS",
                "PREMIUM": "PREMIUM",
                "SERVER ADMINISTRATION": "ADMIN",
                "UTILITIES": "SETTINGS",
                "OWNER & DEVELOPER": "OWNER",
            }
            cat_key = mapping.get(raw_category, "SETTINGS")
            return emoji_registry.get_category_obj(cat_key)

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
            placeholder="Select a category to view commands...",
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
        self.add_item(
            HelpCategorySelect(
                self,
                self.visible_categories,
                current_selection=self.current_category,
            )
        )

        invite_url = (
            Config.INVITE_URL
            or (
                f"https://discord.com/oauth2/authorize?client_id={self.cog.bot.application_id or self.cog.bot.user.id}&permissions=8&scope=bot%20applications.commands"
                if (hasattr(self.cog.bot, "user") and self.cog.bot.user)
                else "https://discord.com"
            )
        )
        support_url = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"

        # Row 1: Navigation Buttons
        if self.current_category == "home":
            btn_search = discord.ui.Button(
                label="Search",
                emoji=btn_emoji("SEARCH"),
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)

            self.add_item(
                discord.ui.Button(
                    label="Invite KYOKA",
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

            btn_search = discord.ui.Button(
                label="Search",
                emoji=btn_emoji("SEARCH"),
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_search.callback = self.btn_search_callback
            self.add_item(btn_search)

            self.add_item(
                discord.ui.Button(
                    label="Invite",
                    url=invite_url,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )
            self.add_item(
                discord.ui.Button(
                    label="Support",
                    url=support_url,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )

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
        embed = self.cog.build_home_embed(self.ctx, self.visible_categories)
        await interaction.response.edit_message(embed=embed, view=self)

    async def switch_to_category(self, interaction: discord.Interaction, cat_name: str, page: int = 1) -> None:
        self.current_category = cat_name
        self.current_page = page
        self._build_components()
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
        "🧾・BLOX FRUITS SERVICE BILLS",
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

    def build_home_embed(self, ctx: CustomContext, visible_categories: dict[str, list[commands.Command]]) -> discord.Embed:
        """Construct the signature KYOKA Aizen Edition Help Homepage."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(category_name: str) -> str:
            if not reg:
                return ""
            return reg.get_category(category_name, fallback="")

        home_icon = get_em("HOME")
        ping_icon = get_em("PING")
        time_icon = get_em("TIME")
        server_icon = get_em("SERVER")
        members_icon = get_em("MEMBERS")
        creator_icon = get_em("OWNER")
        premium_icon = get_em("PREMIUM")
        arrow_icon = get_em("ARROW")

        bullet = arrow_icon if arrow_icon else "•"

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        ws_ping = self._get_latency_ms()
        guilds = list(getattr(self.bot, "guilds", ()) or ())
        total_servers = len(guilds)
        total_members = sum(int(getattr(g, "member_count", 0) or 0) for g in guilds)

        # Uptime
        start_time = getattr(self.bot, "start_time", None) or discord.utils.utcnow()
        uptime_timestamp = int(start_time.timestamp())

        title_str = f"{home_icon} KYOKA — AIZEN ULTIMATE EDITION".strip()
        embed = discord.Embed(
            title=title_str,
            description=(
                "**Welcome to KYOKA** — The premier Aizen-themed Discord experience.\n"
                "> Powerful server protection, high-fidelity music streaming, autonomous AI companions, "
                "automated ticket panels, and next-generation moderation."
            ),
            color=0x2B0938,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name=f"{ping_icon} System Telemetry",
            value=(
                f"{bullet} **WebSocket Ping:** `{ws_ping}ms`\n"
                f"{bullet} **Online Since:** <t:{uptime_timestamp}:R>\n"
                f"{bullet} **Default Prefix:** `{prefix}` | **Slash:** `/`"
            ),
            inline=True,
        )

        embed.add_field(
            name=f"{server_icon} Global Scale",
            value=(
                f"{bullet} **Active Servers:** `{total_servers:,}`\n"
                f"{bullet} **Total Members:** `{total_members:,}`\n"
                f"{bullet} **Accessible Modules:** `{len(visible_categories)}`"
            ),
            inline=True,
        )

        embed.add_field(
            name=f"{creator_icon} Identity & Support",
            value=(
                f"{bullet} **Creator:** `made by aizen (ruthupavan)`\n"
                f"{bullet} **Primary Owner:** <@{OWNER_ID}>\n"
                f"{bullet} **Support Server:** [Join Here](https://discord.gg/7q4tn6dA6V)"
            ),
            inline=False,
        )

        embed.add_field(
            name=f"{premium_icon} Premium Status",
            value=f"{bullet} **Tier:** `KYOKA Supreme (Active)` — All enterprise features unlocked.",
            inline=False,
        )

        if getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        banner_url = Config.ASSETS.HELP_BANNER_URL or Config.ASSETS.BANNER_URL
        if banner_url and banner_url.startswith("http"):
            embed.set_image(url=banner_url)

        embed.set_footer(
            text=f"-# Select a category from the dropdown below • Type {prefix}help <command> for syntax",
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
        """Construct a paginated category command viewer showing syntax, description, and permissions."""
        reg = getattr(self.bot, "custom_emojis", None)

        def get_em(category_name: str) -> str:
            if not reg:
                return ""
            return reg.get_category(category_name, fallback="")

        arrow_icon = get_em("ARROW")
        bullet = arrow_icon if arrow_icon else "•"

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

        cat_icon = get_em(raw_title) or get_em("SETTINGS")
        embed = discord.Embed(
            title=f"{cat_icon} {raw_title} Module (Page {curr_page}/{total_pages})".strip(),
            description=f"> {CATEGORY_DESCRIPTIONS.get(cat_name, 'Commands in this system.')}\n\n**Total Commands:** `{len(unique_cmds)}`",
            color=0x2B0938,
            timestamp=discord.utils.utcnow(),
        )

        for cmd in page_cmds:
            badge = self._get_badge(cmd)
            desc = (cmd.description or cmd.help or "No description provided.").strip().split("\n")[0][:100]
            sig = f" {cmd.signature}" if cmd.signature else ""
            aliases_str = f" | Aliases: `{'`, `'.join(cmd.aliases[:3])}`" if getattr(cmd, "aliases", None) else ""
            
            field_name = f"{bullet} `{prefix}{cmd.qualified_name}{sig}`{badge}"
            field_val = f"> {desc}{aliases_str}"
            embed.add_field(name=field_name[:256], value=field_val[:1024], inline=False)

        if getattr(self.bot, "user", None):
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.set_footer(
            text=f"-# Use buttons below to paginate • {prefix}help <command> for deep details",
            icon_url=ctx.author.display_avatar.url if ctx.author else None,
        )

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
                embed = self.build_category_embed(ctx, matched_cat, cmds, page=1)
                view = HelpView(self, ctx, visible_categories, current_category=matched_cat, current_page=1)
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
        embed = self.build_home_embed(ctx, visible_categories)
        view = HelpView(self, ctx, visible_categories, current_category="home", current_page=1)
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
