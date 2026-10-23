"""
Kyoka Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by native discord.py UI Views with Category Select
and Navigation Buttons (Prev/Home/Next/Close) plus Link actions.
Organized into 14 clean, intuitive command categories with dark purple Aizen styling.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response
from src.utils.ui import KyokaEmbed, AizenPalette, AizenSymbols
from src.security.owner import is_primary_owner
from src.security.adult_guard import is_adult_authorized

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Help")

UNICODE_CATEGORY_EMOJIS: dict[str, str] = {
    "home": "🏠",
    "🏠・GETTING STARTED": "🏠",
    "🤖・ARTIFICIAL INTELLIGENCE": "🤖",
    "⛩️・AIZEN AI SYSTEM": "⛩️",
    "🛡️・MODERATION": "🛡️",
    "👋・WELCOME & AUTOMOD": "👋",
    "🎫・TICKETS & SUPPORT": "🎫",
    "🎉・GIVEAWAYS & EVENTS": "🎉",
    "⭐・LEVELS & COMMUNITY": "⭐",
    "🖼️・IMAGES & AVATARS": "🖼️",
    "🎵・MUSIC": "🎵",
    "💬・SOCIAL & FUN": "💬",
    "💎・PREMIUM": "💎",
    "⚙️・SERVER ADMINISTRATION": "⚙️",
    "🔧・UTILITIES": "🔧",
    "👑・OWNER & DEVELOPER": "👑",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "🏠・GETTING STARTED": "Onboarding wizards, initial setup, bot ping & system stats",
    "🤖・ARTIFICIAL INTELLIGENCE": "Aizen Gemini AI engine, 10 personalities & auto channels",
    "🛡️・MODERATION": "Punishments, audit logs, purges, timeouts & channel locks",
    "👋・WELCOME & AUTOMOD": "Greeting cards, farewell messages, autoroles & anti-spam",
    "🎫・TICKETS & SUPPORT": "Support panels, ticket management & automated transcripts",
    "🎉・GIVEAWAYS & EVENTS": "Giveaway creation, requirement validation & winner rerolls",
    "⭐・LEVELS & COMMUNITY": "XP system, rank cards, leaderboards & member suggestions",
    "🖼️・IMAGES & AVATARS": "Anime reaction GIFs, avatar grabbers, banners & memes",
    "🎵・MUSIC": "High-fidelity audio playback, queues, volume & filters",
    "💬・SOCIAL & FUN": "Mini-games, truth-or-dare, relationship stats & trivia",
    "💎・PREMIUM": "Kyoka Prime licenses, high-resolution AI & premium perks",
    "⚙️・SERVER ADMINISTRATION": "Prefix management, logging setups & custom permissions",
    "🔧・UTILITIES": "Calculators, reminders, timestamps & info lookups",
    "👑・OWNER & DEVELOPER": "Core bot diagnostics, database status & maintenance tools",
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
                label="Home Overview",
                value="home",
                description="Kyoka overview, quickstart & navigation guide",
                emoji="🏠",
                default=(current_selection == "home"),
            )
        ]

        for cat_name, cmds in visible_categories.items():
            clean_label = cat_name.split("・", 1)[1] if "・" in cat_name else cat_name
            opt_label = f"{clean_label} ({len(cmds)})"[:100]
            desc = CATEGORY_DESCRIPTIONS.get(cat_name, f"{len(cmds)} accessible commands")[:100]
            emoji_str = UNICODE_CATEGORY_EMOJIS.get(cat_name, "📁")

            options.append(
                discord.SelectOption(
                    label=opt_label,
                    value=cat_name.lower(),
                    description=desc,
                    emoji=emoji_str,
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
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.visible_categories = visible_categories
        self.category_keys = list(visible_categories.keys())
        self.current_category = current_category
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

        # Row 2: Link Buttons
        if Config.INVITE_URL:
            self.add_item(
                discord.ui.Button(
                    label="Invite",
                    url=Config.INVITE_URL,
                    style=discord.ButtonStyle.link,
                    row=2,
                )
            )
        if Config.SUPPORT_URL:
            self.add_item(
                discord.ui.Button(
                    label="Support",
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
        self._build_components()
        embed = self.cog.build_embed_for_selection(self.ctx, self.visible_categories, selected_val)
        await interaction.response.edit_message(embed=embed, view=self)

    async def btn_back_callback(self, interaction: discord.Interaction) -> None:
        """Navigate to the previous category."""
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
        """Navigate to the next category."""
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
        "getting started": "🏠・GETTING STARTED",
        "onboarding": "🏠・GETTING STARTED",
        "ai": "🤖・ARTIFICIAL INTELLIGENCE",
        "artificial intelligence": "🤖・ARTIFICIAL INTELLIGENCE",
        "aizen": "🤖・ARTIFICIAL INTELLIGENCE",
        "mod": "🛡️・MODERATION",
        "moderation": "🛡️・MODERATION",
        "welcome": "👋・WELCOME & AUTOMOD",
        "automod": "👋・WELCOME & AUTOMOD",
        "ticket": "🎫・TICKETS & SUPPORT",
        "tickets": "🎫・TICKETS & SUPPORT",
        "support": "🎫・TICKETS & SUPPORT",
        "giveaway": "🎉・GIVEAWAYS & EVENTS",
        "giveaways": "🎉・GIVEAWAYS & EVENTS",
        "events": "🎉・GIVEAWAYS & EVENTS",
        "levels": "⭐・LEVELS & COMMUNITY",
        "community": "⭐・LEVELS & COMMUNITY",
        "xp": "⭐・LEVELS & COMMUNITY",
        "images": "🖼️・IMAGES & AVATARS",
        "image": "🖼️・IMAGES & AVATARS",
        "gifs": "🖼️・IMAGES & AVATARS",
        "gif": "🖼️・IMAGES & AVATARS",
        "avatars": "🖼️・IMAGES & AVATARS",
        "music": "🎵・MUSIC",
        "audio": "🎵・MUSIC",
        "social": "💬・SOCIAL & FUN",
        "fun": "💬・SOCIAL & FUN",
        "games": "💬・SOCIAL & FUN",
        "premium": "💎・PREMIUM",
        "prime": "💎・PREMIUM",
        "admin": "⚙️・SERVER ADMINISTRATION",
        "administration": "⚙️・SERVER ADMINISTRATION",
        "utility": "🔧・UTILITIES",
        "utilities": "🔧・UTILITIES",
        "owner": "👑・OWNER & DEVELOPER",
        "developer": "👑・OWNER & DEVELOPER",
        "dev": "👑・OWNER & DEVELOPER",
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
        """Resolve a command into one of the 14 clean help categories."""
        name = cmd.name.lower()
        cog_cat = getattr(cmd.cog, "category", "").strip()
        cog_name = getattr(cmd.cog, "qualified_name", "").lower()

        # 14. 👑・OWNER & DEVELOPER
        if cog_cat.lower() in ("owner", "developer") or cog_name in ("owner", "ownersystem", "developer") or name in (
            "owner", "dev", "health", "dbstatus", "extstatus", "eval", "exec", "restart",
            "shutdown", "sync", "leaveserver", "blacklist", "whitelistuser", "errors",
            "validateconfig", "maintenance", "spam", "spamcancel", "guesshostadd",
            "guesshostremove", "guesshosts", "reload", "load", "unload", "cogs", "systemstatus",
        ):
            return "👑・OWNER & DEVELOPER"

        # 1. 🏠・GETTING STARTED
        if cog_cat.lower() in ("onboarding", "getting started") or name in (
            "help", "start", "quickstart", "setup", "ping", "invite", "support",
            "botinfo", "serverinfo", "userinfo", "roleinfo", "channelinfo",
            "about", "uptime", "links", "invitebot",
        ):
            return "🏠・GETTING STARTED"

        # 2. 🤖・ARTIFICIAL INTELLIGENCE
        if cog_cat in ("AI Companions", "AI & Chat", "AIInteractions", "🤖・ARTIFICIAL INTELLIGENCE", "⛩️・AIZEN AI SYSTEM") or name in (
            "aigf", "aibaddie", "aispecial", "aiclearcompanion", "aichannel", "aidiag", "aistatus",
            "ai", "chat", "askai", "aizenai", "aisetup", "aipersonality", "aiconfig", "aitest",
            "aiclear", "aimodel", "aidebug", "girlfriend", "baddie", "specialai", "clearcompanion",
            "setaichannel", "setcompanionchannel", "aichatsetup", "aihelp", "companion",
        ):
            return "🤖・ARTIFICIAL INTELLIGENCE"

        # 3. 🛡️・MODERATION
        if cog_cat.lower() in ("moderation", "mod") or name in (
            "warn", "warnings", "timeout", "untimeout", "kick", "ban", "unban", "softban",
            "purge", "slowmode", "lock", "unlock", "hide", "unhide", "nick", "modlogs", "modlog",
            "case", "unwarn", "clearwarnings", "delwarn", "mute", "unmute", "snipe", "snipeall",
            "clearsnipe", "clearsnipeall", "nuke", "admins", "mods", "bots",
        ):
            return "🛡️・MODERATION"

        # 4. 👋・WELCOME & AUTOMOD
        if cog_cat.lower() in ("automod", "welcome", "antinuke", "security") or name in (
            "welcome", "goodbye", "autorole", "antispam", "antiflood", "invites", "badwords",
            "mentionspam", "automod", "antinuke", "whitelist", "extraowner", "boost",
        ):
            return "👋・WELCOME & AUTOMOD"

        # 5. 🎫・TICKETS & SUPPORT
        if cog_cat.lower() in ("ticket", "tickets", "support") or name.startswith("ticket") or name in (
            "panel", "claim", "close", "reopen", "transcript", "ticketstats", "ticketsetup",
            "addmember", "removemember",
        ):
            return "🎫・TICKETS & SUPPORT"

        # 6. 🎉・GIVEAWAYS & EVENTS
        if cog_cat.lower() in ("giveaway", "giveaways", "events") or name in (
            "giveaway", "gstart", "gend", "greroll", "glist", "requirements", "reroll", "event", "events",
        ):
            return "🎉・GIVEAWAYS & EVENTS"

        # 7. ⭐・LEVELS & COMMUNITY
        if cog_cat in ("Community & XP", "Intelligence", "Levels", "Suggestions") or name in (
            "levels", "rank", "levelconfig", "activity", "leaderboard", "xp", "xpmultiplier",
            "multiplier", "daily", "streak", "rep", "reputation", "suggest", "suggestions",
            "poll", "polls", "serverstats", "privacy", "diagnostics", "tech", "devpulse", "cve", "news",
        ):
            return "⭐・LEVELS & COMMUNITY"

        # 8. 🖼️・IMAGES & AVATARS
        if cog_cat in ("Images & GIFs", "Anime Actions") or name in (
            "gif", "meme", "randomgif", "imagine", "steal", "emojis", "expressions",
            "stickers", "delemoji", "filter", "trigger", "hug", "kiss", "pat", "slap",
            "cuddle", "wave", "dance", "smile", "cry", "blush", "banner", "serveravatar",
            "serverbanner", "avatar", "punch", "blast", "animekick", "bonk", "poke", "bite", "yeet",
            "highfive", "stare", "scare", "laugh", "wink", "shy", "facepalm",
        ):
            return "🖼️・IMAGES & AVATARS"

        # 9. 🎵・MUSIC
        if cog_cat.lower() in ("music", "audio") or name in (
            "play", "pause", "resume", "skip", "stop", "queue", "nowplaying", "np",
            "volume", "vol", "loop", "repeat", "shuffle", "clear", "remove", "seek",
            "autoplay", "lyrics", "jump", "stay", "247", "playlist", "like", "unlike",
            "disconnect", "dc",
        ):
            return "🎵・MUSIC"

        # 10. 💬・SOCIAL & FUN
        if cog_cat in ("Romance & Relationships", "Social & Profiles", "Games", "Fun", "Adult Humor — Restricted") or name in (
            "propose", "marry", "divorce", "breakup", "relationship", "couple", "marriage",
            "love", "crush", "date", "jealous", "flirt", "pickup", "compliment", "romance",
            "heartbreak", "reject", "confess", "rizz", "ship", "compatibility", "soulmate",
            "loveletter", "profile", "bio", "coinflip", "flip", "dice", "roll", "8ball",
            "eightball", "choose", "rate", "joke", "fact", "quote", "wyr", "truth", "dare",
            "roast", "rps", "trivia", "wordguess", "wordgame", "bloxfruits", "bf", "bloxtrivia",
            "tod", "truthordare", "guess", "membercount",
            "goon", "goonreaction", "fuck", "smash", "thirst", "downbad", "downbadcheck",
            "hornybonk", "seduce", "spank", "wildreaction", "adultreaction", "simp",
            "obsessed", "fantasize", "tease", "bedroomeyes", "caughtlacking", "rateattraction",
        ):
            return "💬・SOCIAL & FUN"

        # 11. 💎・PREMIUM
        if cog_cat.lower() in ("premium", "prime") or name in (
            "premium", "redeem", "tier", "license", "prime", "perks",
        ):
            return "💎・PREMIUM"

        # 12. ⚙️・SERVER ADMINISTRATION
        if cog_cat.lower() in ("admin", "administration", "config", "settings") or name in (
            "prefix", "setprefix", "resetprefix", "media", "sticky", "logs", "config",
            "disablecmd", "enablecmd", "channelsettings", "rolesettings",
        ):
            return "⚙️・SERVER ADMINISTRATION"

        # 13. 🔧・UTILITIES
        if cog_cat.lower() in ("utility", "utilities", "reminders", "calculator") or name in (
            "calc", "calculator", "math", "remind", "reminder", "reminders", "timer",
            "time", "timestamp", "format", "userlookup", "rolelookup", "channellookup",
            "apistatus", "botlatency",
        ):
            return "🔧・UTILITIES"

        # Fallback
        return "🔧・UTILITIES"

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

        return ordered_categories

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji or unicode fallback for category header."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return UNICODE_CATEGORY_EMOJIS.get(cat_name, "•")
        mapping = {
            "🏠・GETTING STARTED": e_reg.get("icon_home", "🏠"),
            "🤖・ARTIFICIAL INTELLIGENCE": e_reg.get("icon_sparkles", "🤖"),
            "⛩️・AIZEN AI SYSTEM": e_reg.get("icon_sparkles", "⛩️"),
            "🛡️・MODERATION": e_reg.get("icon_moderation", "🛡️"),
            "👋・WELCOME & AUTOMOD": e_reg.get("icon_shield", "👋"),
            "🎫・TICKETS & SUPPORT": e_reg.get("icon_ticket", "🎫"),
            "🎉・GIVEAWAYS & EVENTS": e_reg.get("discord_giveaway", "🎉"),
            "⭐・LEVELS & COMMUNITY": e_reg.get("icon_chart", "⭐"),
            "🖼️・IMAGES & AVATARS": e_reg.get("icon_image", "🖼️"),
            "🎵・MUSIC": e_reg.get("music", e_reg.get("icon_music", "🎵")),
            "💬・SOCIAL & FUN": e_reg.get("icon_heart", "💬"),
            "💎・PREMIUM": e_reg.get("verified_premium", "💎"),
            "⚙️・SERVER ADMINISTRATION": e_reg.get("icon_settings", "⚙️"),
            "🔧・UTILITIES": e_reg.get("icon_wrench", "🔧"),
            "👑・OWNER & DEVELOPER": e_reg.get("icon_crown", "👑"),
        }
        return mapping.get(cat_name, UNICODE_CATEGORY_EMOJIS.get(cat_name, "•"))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return None
        mapping = {
            "🏠・GETTING STARTED": "icon_home",
            "🤖・ARTIFICIAL INTELLIGENCE": "icon_sparkles",
            "⛩️・AIZEN AI SYSTEM": "icon_sparkles",
            "🛡️・MODERATION": "icon_moderation",
            "👋・WELCOME & AUTOMOD": "icon_shield",
            "🎫・TICKETS & SUPPORT": "icon_ticket",
            "🎉・GIVEAWAYS & EVENTS": "discord_giveaway",
            "⭐・LEVELS & COMMUNITY": "icon_chart",
            "🖼️・IMAGES & AVATARS": "icon_image",
            "🎵・MUSIC": "music",
            "💬・SOCIAL & FUN": "icon_heart",
            "💎・PREMIUM": "verified_premium",
            "⚙️・SERVER ADMINISTRATION": "icon_settings",
            "🔧・UTILITIES": "icon_wrench",
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
        formatted_cmds = ", ".join([f"`{cmd.qualified_name}`{self._get_badge(cmd)}" for cmd in sorted_cmds])
        container.add_text(f"**Accessible Commands ({len(sorted_cmds)}):**\n" + formatted_cmds)
        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name} • Type {p}help <command> for details**")
        return container

    def build_home_embed(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
    ) -> discord.Embed:
        """Construct the Signature Kyoka Home Overview Discord Embed."""
        guild = ctx.guild
        author = ctx.author
        p = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = self._get_latency_ms()
        total_commands = sum(len(cmds) for cmds in visible_categories.values())

        embed = discord.Embed(
            title="⛩️ Kyoka 3.0 — The Perfect Control System",
            description=(
                "*“Control the chaos. Command the impossible.”*\n\n"
                "Welcome to **Kyoka 3.0**, high-performance Discord automation powered by "
                "Google Gemini AI, real-time moderation, community progression, and entertainment.\n\n"
                "### 🚀 Getting Started & Quick Setup\n"
                f"• `{p}quickstart` — 5-minute setup checklist for server administrators\n"
                f"• `{p}setup` — Interactive multi-module server configuration wizard\n"
                f"• `{p}setup status` — Audit active vs unconfigured features\n"
                f"• `{p}setprefix <prefix>` — Set custom server command prefix\n\n"
                "### 🧭 Navigation & Command Types\n"
                f"• **Prefix Commands:** Use `{p}<command>` (e.g., `{p}ping`, `{p}ai hello`, `{p}help`)\n"
                f"• **Slash Commands:** Type `/<command>` for Discord autocomplete and modal wizards\n"
                f"• **Browse Categories:** Select any category from the dropdown below or use **◀️ Back / ▶️ Next**\n"
                f"• **Instant Search:** Click **🔍 Search** below or type `{p}help <query>` to search all commands\n"
                f"• **Command Manual:** Type `{p}help <command>` (e.g., `{p}help ban`, `{p}help ai`) for detailed syntax\n\n"
                "### 🔒 Permission System\n"
                "`[Public]` Available to all members • `[Mod]` Requires Kick/Ban/Timeout\n"
                "`[Admin]` Requires Administrator permission • `[Prime]` Kyoka Premium perks"
            ),
            color=0x2B0938,
        )

        embed.add_field(
            name="📊 System Status",
            value=(
                f"• **Prefix:** `{p}` | **Slash:** `/`\n"
                f"• **Latency:** `{ws_ping}ms` | **Status:** `Operational`\n"
                f"• **Commands:** `{total_commands}` accessible across `{len(visible_categories)}` categories"
            ),
            inline=True,
        )

        embed.add_field(
            name="✨ Key Features",
            value=(
                f"• **AI Engine:** `{p}ai`, `{p}aigf`, `{p}aidiag`\n"
                f"• **Moderation:** `{p}warn`, `{p}kick`, `{p}ban`, `{p}purge`\n"
                f"• **Utilities:** `{p}calc`, `{p}remind`, `{p}suggest`\n"
                f"• **Community:** `{p}rank`, `{p}play`, `{p}giveaway`"
            ),
            inline=True,
        )

        # Apply configurable Aizen artwork if available
        assets = getattr(Config, "ASSETS", None)
        banner_url = getattr(assets, "BANNER_URL", None) or getattr(Config, "AIZEN_IMAGE_URL", "")
        if banner_url and banner_url.strip():
            embed.set_image(url=banner_url.strip())

        thumbnail_url = getattr(assets, "DEFAULT_THUMBNAIL_URL", "")
        if thumbnail_url and thumbnail_url.strip():
            embed.set_thumbnail(url=thumbnail_url.strip())

        embed.set_footer(
            text=f"Requested by {author.display_name} • Type {p}help <command> for syntax & examples",
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
            # Sort: exact name match first, then prefix match, then others
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
    ) -> discord.Embed:
        """Construct a formatted Discord Embed for a specific command category."""
        cat_keys = list(visible_categories.keys())
        page_idx = (cat_keys.index(cat_name) + 1) if cat_name in cat_keys else 1
        total_pages = len(cat_keys)
        p = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        container = self._build_category_container(
            ctx=ctx,
            cat_name=cat_name,
            commands_list=commands_list,
            visible_categories=visible_categories,
            custom_id_prefix="help_ui",
        )
        embed = container.to_embed()
        embed.title = f"{self._get_category_emoji(cat_name)} {cat_name}"
        embed.color = 0x2B0938
        embed.set_footer(
            text=f"Category {page_idx}/{total_pages} • Requested by {ctx.author.display_name} • Type {p}help <command> for details",
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
    ) -> discord.Embed:
        """Route selection value to corresponding category or home embed."""
        if selected_val == "home":
            return self.build_home_embed(ctx, visible_categories)
        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected_val.lower()), None)
        if matched_cat:
            return self.build_category_embed(ctx, matched_cat, visible_categories[matched_cat], visible_categories)
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
        msg = await ctx.send(embed=embed, view=view)
        if getattr(ctx, "interaction", None):
            try:
                view.message = await ctx.interaction.original_response()
            except Exception:
                pass
        else:
            view.message = msg


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
