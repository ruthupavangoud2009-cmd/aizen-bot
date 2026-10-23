"""
Kyoka Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by Discord Components V2 Container Cards.
Organized into 14 clean, intuitive command categories with interactive dropdown and button navigation.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response
from src.security.owner import is_primary_owner
from src.security.adult_guard import is_adult_authorized

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


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

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

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
        """Resolve custom application emoji for category header."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return "•"
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
        return mapping.get(cat_name, e_reg.get("icon_moderation", "•"))

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
        """Construct the Signature Kyoka Overview Card."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        e_reg = self.bot.custom_emojis

        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

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
            f"{dot} **Quick Start:** Type `{current_prefix}start` or `{current_prefix}setup` to configure your server in minutes!"
        )
        container.add_separator(divider=True)

        # Dropdown Options
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": selected_val == "home",
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for cat_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": f"{cat_name} ({len(cmds)})",
                "value": cat_name.lower(),
                "default": selected_val == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(cat_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a category to view commands...",
                "options": options[:25],
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {author.display_name} • Type {current_prefix}help <command> for details**")
        container.add_separator(divider=True)

        quick_buttons: list[dict[str, Any]] = [
            {
                "type": 2,
                "style": 1,
                "label": "Quickstart Guide",
                "emoji": {"name": "🚀"},
                "custom_id": f"{custom_id_prefix}:start_guide",
            },
            {
                "type": 2,
                "style": 4,
                "label": "Close",
                "emoji": {"name": "🗑️"},
                "custom_id": f"{custom_id_prefix}:close_help",
            },
        ]
        if Config.INVITE_URL:
            quick_buttons.append({
                "type": 2,
                "style": 5,
                "label": "Invite",
                "url": Config.INVITE_URL,
            })
        if Config.SUPPORT_URL:
            quick_buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support",
                "url": Config.SUPPORT_URL,
            })
        container.add_action_row(quick_buttons)

        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> KyokaContainer:
        """Construct category command card with permission badges and clean layout."""
        cat_icon = self._get_category_emoji(cat_name)
        cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
        e_reg = self.bot.custom_emojis
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

        # Sort commands alphabetically
        sorted_cmds = sorted(commands_list, key=lambda c: c.qualified_name.lower())
        formatted_cmds = ", ".join([f"`{cmd.qualified_name}`{self._get_badge(cmd)}" for cmd in sorted_cmds])
        container.add_text(f"**Accessible Commands ({len(sorted_cmds)}):**\n" + formatted_cmds)
        container.add_separator(divider=True)

        # Dropdown options
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": False,
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for c_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": f"{c_name} ({len(cmds)})",
                "value": c_name.lower(),
                "default": c_name.lower() == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(c_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a category to view commands...",
                "options": options[:25],
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name} • Type {p}help <command> for details**")
        container.add_separator(divider=True)

        # Navigation row: Prev, Home, Next, Close
        nav_buttons: list[dict[str, Any]] = [
            {
                "type": 2,
                "style": 2,
                "label": "Back",
                "emoji": {"name": "◀️"},
                "custom_id": f"{custom_id_prefix}:{cat_name}:prev_category",
            },
            {
                "type": 2,
                "style": 1,
                "label": "Home",
                "emoji": {"name": "🏠"},
                "custom_id": f"{custom_id_prefix}:nav_home",
            },
            {
                "type": 2,
                "style": 2,
                "label": "Next",
                "emoji": {"name": "▶️"},
                "custom_id": f"{custom_id_prefix}:{cat_name}:next_category",
            },
            {
                "type": 2,
                "style": 4,
                "label": "Close",
                "emoji": {"name": "🗑️"},
                "custom_id": f"{custom_id_prefix}:close_help",
            },
        ]
        container.add_action_row(nav_buttons)

        return container

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
                current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
                cat = self._resolve_category(target_cmd)
                cat_icon = self._get_category_emoji(cat)
                desc = target_cmd.description or target_cmd.help or "No detailed description available."
                aliases = ", ".join([f"`{a}`" for a in target_cmd.aliases]) if target_cmd.aliases else "`None`"
                sig = f" {target_cmd.signature}" if target_cmd.signature else ""
                usage = f"`{current_prefix}{target_cmd.qualified_name}{sig}`"
                example = f"`{current_prefix}{target_cmd.qualified_name}`"

                badge = self._get_badge(target_cmd)
                status_str = badge.strip(" `[]") if badge else "Public"

                # Check slash command support
                slash_info = f"`/{target_cmd.name}`" if getattr(target_cmd, "app_command", None) else "Prefix command"
                if cat == "🤖・ARTIFICIAL INTELLIGENCE":
                    slash_info = f"`/ai` or `{current_prefix}{target_cmd.name}`"

                e_reg = self.bot.custom_emojis
                dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

                container = KyokaContainer(accent_color=None)
                cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
                container.add_section(
                    content=(
                        f"**{cat_icon_prefix}Command: `{target_cmd.name}`**\n"
                        f"> {desc}"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"{dot} **Usage:** {usage}\n"
                    f"{dot} **Example:** {example} | **Slash:** {slash_info}\n"
                    f"{dot} **Category:** `{cat}` | **Access:** `{status_str}`\n"
                    f"{dot} **Aliases:** {aliases}"
                )
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

            # Direct module / category lookup
            category_aliases = {
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
            target_cat_name = category_aliases.get(query)
            if not target_cat_name:
                target_cat_name = next((c for c in visible_categories.keys() if c.lower() == query), None)

            if target_cat_name:
                matched_cat = next((c for c in visible_categories.keys() if c.lower() == target_cat_name.lower()), None)
                if matched_cat:
                    custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
                    container = self._build_category_container(
                        ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                    )
                    await send_container_response(ctx, container)
                    return

        # Main Help Console (Home Overview)
        custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
        container = self._build_home_container(ctx, visible_categories, custom_id_prefix)
        await send_container_response(ctx, container)

        def check(interaction: discord.Interaction) -> bool:
            if not interaction.data:
                return False
            custom_id = interaction.data.get("custom_id", "")
            return custom_id.startswith(f"{custom_id_prefix}:")

        while True:
            try:
                interaction: discord.Interaction = await self.bot.wait_for(
                    "interaction", check=check, timeout=120.0
                )
                if not interaction.data:
                    continue

                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message(
                        "❌ Only the command author can interact with this menu. Type `+help` to open your own!",
                        ephemeral=True
                    )
                    continue

                custom_id = interaction.data.get("custom_id", "")
                parts = custom_id.split(":")
                action = parts[-1]

                # Select Menu Navigation
                if action == "select_category":
                    selected = interaction.data.get("values", ["home"])[0]
                    if selected == "home":
                        new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    else:
                        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected), None)
                        if matched_cat:
                            new_container = self._build_category_container(
                                ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                            )
                        else:
                            new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    await edit_container_response(interaction, new_container)

                elif action == "nav_home":
                    new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    await edit_container_response(interaction, new_container)

                elif action == "start_guide":
                    guide_cat = "🏠・GETTING STARTED"
                    if guide_cat in visible_categories:
                        new_container = self._build_category_container(
                            ctx, guide_cat, visible_categories[guide_cat], visible_categories, custom_id_prefix
                        )
                    else:
                        new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    await edit_container_response(interaction, new_container)

                elif action == "prev_category":
                    curr_cat = parts[-2] if len(parts) >= 2 else ""
                    cat_keys = list(visible_categories.keys())
                    if curr_cat in cat_keys:
                        curr_idx = cat_keys.index(curr_cat)
                        new_cat = cat_keys[(curr_idx - 1) % len(cat_keys)]
                    else:
                        new_cat = cat_keys[0] if cat_keys else "home"
                    new_container = self._build_category_container(
                        ctx, new_cat, visible_categories[new_cat], visible_categories, custom_id_prefix
                    )
                    await edit_container_response(interaction, new_container)

                elif action == "next_category":
                    curr_cat = parts[-2] if len(parts) >= 2 else ""
                    cat_keys = list(visible_categories.keys())
                    if curr_cat in cat_keys:
                        curr_idx = cat_keys.index(curr_cat)
                        new_cat = cat_keys[(curr_idx + 1) % len(cat_keys)]
                    else:
                        new_cat = cat_keys[0] if cat_keys else "home"
                    new_container = self._build_category_container(
                        ctx, new_cat, visible_categories[new_cat], visible_categories, custom_id_prefix
                    )
                    await edit_container_response(interaction, new_container)

                elif action == "close_help":
                    close_container = KyokaContainer()
                    close_container.add_section("🔒 **Help Menu Closed**\n> Use `+help` whenever you need guidance.")
                    await edit_container_response(interaction, close_container)
                    break

            except asyncio.TimeoutError:
                break


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
