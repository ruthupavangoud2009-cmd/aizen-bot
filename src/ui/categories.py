"""
Kyoka 3.0 - Centralized Command Category Registry & Classification Engine
Provides bulletproof classification of prefix, slash, hybrid, and subcommands.
Ensures zero category pollution (e.g. AI subcommands like 'stop' or 'leave' never leak into Music).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import discord
from discord.ext import commands


@dataclass(frozen=True)
class CategoryMeta:
    """Metadata describing a single Kyoka command category."""
    id: str
    name: str
    tag: str
    emoji: str
    description: str
    image_key: str
    priority: int


# Standard 18+ Categories matching the Kyoka Infographic & Architecture
CATEGORIES: list[CategoryMeta] = [
    CategoryMeta(
        id="general",
        name="General & Getting Started",
        tag="🏠・GETTING STARTED",
        emoji="🏠",
        description="Everyday utility commands, bot statistics, info lookups, and beginner guide",
        image_key="general",
        priority=1,
    ),
    CategoryMeta(
        id="moderation",
        name="Moderation",
        tag="🛡️・MODERATION",
        emoji="🛡️",
        description="High-precision server protection, punishments, lockups, and moderation logs",
        image_key="moderation",
        priority=2,
    ),
    CategoryMeta(
        id="automod",
        name="Automod & Security",
        tag="🔒・AUTOMOD & SECURITY",
        emoji="🔒",
        description="Anti-spam, anti-raid, invite defense, and server antinuke protection",
        image_key="automod",
        priority=3,
    ),
    CategoryMeta(
        id="welcome",
        name="Welcome & Goodbye",
        tag="👋・WELCOME & AUTOMOD",
        emoji="👋",
        description="Greeting cards, farewell departures, autoroles, and join settings",
        image_key="welcome",
        priority=4,
    ),
    CategoryMeta(
        id="verification",
        name="Verification",
        tag="🛡️・VERIFICATION",
        emoji="🛡️",
        description="Gatekeep channels with role isolation, challenge codes, and button verification",
        image_key="verification",
        priority=5,
    ),
    CategoryMeta(
        id="tickets",
        name="Tickets & Support",
        tag="🎫・TICKETS & SUPPORT",
        emoji="🎫",
        description="Interactive support ticket panels, staff claiming, and HTML transcripts",
        image_key="tickets",
        priority=6,
    ),
    CategoryMeta(
        id="reaction_roles",
        name="Reaction Roles",
        tag="🎭・REACTION ROLES",
        emoji="🎭",
        description="Self-service role menus, dropdown selectors, and button assignments",
        image_key="reaction_roles",
        priority=7,
    ),
    CategoryMeta(
        id="giveaways",
        name="Giveaways & Events",
        tag="🎉・GIVEAWAYS & EVENTS",
        emoji="🎉",
        description="Automated giveaways, requirement checks, countdown timers, and rerolls",
        image_key="giveaways",
        priority=8,
    ),
    CategoryMeta(
        id="music",
        name="Music",
        tag="🎵・MUSIC",
        emoji="🎵",
        description="High-fidelity audio playback, queues, volume, filters, lyrics, and 24/7 radio",
        image_key="music",
        priority=9,
    ),
    CategoryMeta(
        id="afk",
        name="AFK",
        tag="💤・AFK",
        emoji="💤",
        description="Away from keyboard notices, mention triggers, and auto-return logs",
        image_key="afk",
        priority=10,
    ),
    CategoryMeta(
        id="vouches",
        name="Vouches & Reputation",
        tag="⭐・VOUCHES & REPUTATION",
        emoji="⭐",
        description="Verified member trust profiles, Blox Fruits transaction vouches, and leaderboards",
        image_key="vouches",
        priority=11,
    ),
    CategoryMeta(
        id="service_bills",
        name="Blox Fruits Service Bills",
        tag="🧾・BLOX FRUITS SERVICE BILLS",
        emoji="🧾",
        description="Blox Fruits service receipts, itemized invoices, proof verification, and payments",
        image_key="service_bills",
        priority=12,
    ),
    CategoryMeta(
        id="blox_fruits",
        name="Blox Fruits AI",
        tag="🍎・BLOX FRUITS AI",
        emoji="🍎",
        description="Specialized Blox Fruits companion, fruit values, trade calculation, builds & notifier",
        image_key="blox_fruits",
        priority=13,
    ),
    CategoryMeta(
        id="ai",
        name="Artificial Intelligence",
        tag="🤖・ARTIFICIAL INTELLIGENCE",
        emoji="🤖",
        description="Aizen Gemini AI engine, chat companions, neural TTS, and voice channel interaction",
        image_key="ai",
        priority=14,
    ),
    CategoryMeta(
        id="leveling",
        name="Levels & Community",
        tag="⭐・LEVELS & COMMUNITY",
        emoji="⭐",
        description="Optional member XP progression (disabled by default), custom rank cards & leaderboards",
        image_key="leveling",
        priority=15,
    ),
    CategoryMeta(
        id="images",
        name="Images & Avatars",
        tag="🖼️・IMAGES & AVATARS",
        emoji="🖼️",
        description="Anime actions, expressions, avatar lookups, and visual tools",
        image_key="reaction_roles",
        priority=16,
    ),
    CategoryMeta(
        id="premium",
        name="Premium",
        tag="💎・PREMIUM",
        emoji="💎",
        description="Kyoka Prime licenses, high-resolution AI, and exclusive server perks",
        image_key="premium",
        priority=17,
    ),
    CategoryMeta(
        id="config",
        name="Server Administration",
        tag="⚙️・SERVER ADMINISTRATION",
        emoji="⚙️",
        description="Custom prefixes, logging channels, module toggles, and server administration",
        image_key="config",
        priority=18,
    ),
    CategoryMeta(
        id="utility",
        name="Utilities",
        tag="🔧・UTILITIES",
        emoji="🔧",
        description="Calculators, reminders, server stats, translator, and everyday tools",
        image_key="general",
        priority=19,
    ),
    CategoryMeta(
        id="social",
        name="Social & Fun",
        tag="💬・SOCIAL & FUN",
        emoji="💬",
        description="Mini-games, truth-or-dare, relationship stats, reaction GIFs, and fun",
        image_key="general",
        priority=20,
    ),
    CategoryMeta(
        id="staff_applications",
        name="Staff Applications",
        tag="📝・STAFF APPLICATIONS",
        emoji="📝",
        description="Appy-style staff recruitment panels, applicant submissions & reviewer dashboard",
        image_key="staff_applications",
        priority=21,
    ),
    CategoryMeta(
        id="owner",
        name="Owner & Developer",
        tag="👑・OWNER & DEVELOPER",
        emoji="👑",
        description="Core bot diagnostics, database status, extension reloading & maintenance",
        image_key="owner",
        priority=22,
    ),
]

CATEGORY_BY_ID: dict[str, CategoryMeta] = {c.id: c for c in CATEGORIES}
CATEGORY_BY_TAG: dict[str, CategoryMeta] = {c.tag: c for c in CATEGORIES}

# Fast lookup aliases for user queries e.g. `+hca music`, `+help tickets`, `+hca bloxai`
CATEGORY_SEARCH_ALIASES: dict[str, str] = {
    # General & Getting Started
    "general": "general", "gen": "general", "start": "general", "quickstart": "general", "getting started": "general", "gettingstarted": "general",
    # Utilities
    "util": "utility", "utility": "utility", "utilities": "utility", "tools": "utility", "tool": "utility",
    # Moderation
    "mod": "moderation", "moderation": "moderation", "punish": "moderation",
    # Automod
    "automod": "automod", "security": "automod", "antinuke": "automod", "antiraid": "automod",
    # Welcome
    "welcome": "welcome", "goodbye": "welcome", "autorole": "welcome", "greet": "welcome",
    # Verification
    "verify": "verification", "verification": "verification", "captcha": "verification",
    # Tickets
    "ticket": "tickets", "tickets": "tickets", "support": "tickets", "transcripts": "tickets",
    # Reaction Roles
    "rr": "reaction_roles", "reactionrole": "reaction_roles", "reactionroles": "reaction_roles", "roles": "reaction_roles",
    # Giveaways
    "giveaway": "giveaways", "giveaways": "giveaways", "gstart": "giveaways", "events": "giveaways",
    # Music
    "music": "music", "song": "music", "audio": "music", "radio": "music", "player": "music",
    # AFK
    "afk": "afk", "away": "afk",
    # Vouches
    "vouch": "vouches", "vouches": "vouches", "rep": "vouches", "reputation": "vouches", "trust": "vouches",
    "vlb": "vouches", "vouchinfo": "vouches", "vouchhistory": "vouches", "vouchimport": "vouches",
    # Service Bills
    "bill": "service_bills", "bills": "service_bills", "invoice": "service_bills", "service": "service_bills", "billing": "service_bills",
    "top": "service_bills", "topai": "service_bills", "topmanager": "service_bills", "toptiers": "service_bills", "aihelp": "service_bills",
    # Staff Applications
    "staff": "staff_applications", "apply": "staff_applications", "apps": "staff_applications",
    "application": "staff_applications", "applications": "staff_applications", "staffapp": "staff_applications",
    # Blox Fruits AI
    "bloxai": "blox_fruits", "bfai": "blox_fruits", "bloxfruits": "blox_fruits", "bf": "blox_fruits", "fruit": "blox_fruits", "fruitnotifier": "blox_fruits",
    # AI System & Voice
    "ai": "ai", "aizen": "ai", "ask": "ai", "aivoice": "ai", "voice": "ai", "voiceai": "ai", "tts": "ai", "gemini": "ai",
    # Leveling
    "rank": "leveling", "levels": "leveling", "leveling": "leveling", "xp": "leveling", "leaderboard": "leveling", "lb": "leveling", "community": "leveling",
    # Images & Avatars
    "images": "images", "avatars": "images", "avatar": "images", "image": "images",
    # Premium
    "premium": "premium", "prime": "premium", "tier": "premium", "license": "premium",
    # Server Config
    "config": "config", "setup": "config", "settings": "config", "prefix": "config", "logs": "config", "admin": "config", "administration": "config",
    # Social & Fun
    "social": "social", "fun": "social", "games": "social", "romance": "social", "anime": "social",
    # KDC Shop & Stock & Reviews
    "stock": "service_bills", "kdc": "service_bills", "shop": "service_bills", "store": "service_bills", "kdcshop": "service_bills", "review": "service_bills", "reviews": "service_bills",
    # Owner & Developer
    "owner": "owner", "dev": "owner", "developer": "owner", "system": "owner", "eval": "owner",
}


# Cog class names / qualified names strongly mapped to categories
COG_MAPPINGS: dict[str, str] = {
    "kdcshop": "service_bills",
    # Music (STRICT: only the real music cog)
    "music": "music",

    # AI & Voice (STRICT)
    "aivoice": "ai",
    "aiinteractions": "ai",
    "companionai": "ai",

    # Blox Fruits AI
    "bloxfruitsai": "blox_fruits",
    "bloxfruitsnotifier": "blox_fruits",

    # Service Bills
    "bills": "service_bills",
    "topaimanager": "service_bills",
    "top": "service_bills",

    # Vouches
    "vouches": "vouches",

    # Tickets
    "ticketsystem": "tickets",

    # Verification
    "verification": "verification",

    # Reaction Roles
    "reactionroles": "reaction_roles",
    "reaction roles": "reaction_roles",

    # Giveaways
    "giveaways": "giveaways",

    # AFK
    "afk": "afk",
    "afkcog": "afk",

    # Leveling
    "leveling": "leveling",
    "general-leveling": "leveling",

    # Welcome
    "voicewelcome": "welcome",
    "onboarding": "welcome",

    # Server Configuration & Administration
    "serverconfig": "config",
    "prefix": "config",
    "serverlogscog": "config",

    # Automod & Antinuke
    "antiautomodcog": "automod",
    "antibancog": "automod",
    "antibotcog": "automod",
    "antichannelcog": "automod",
    "antieveryonecog": "automod",
    "antikickcog": "automod",
    "antiprunecog": "automod",
    "antirolecog": "automod",
    "antiservercog": "automod",
    "antivanitycog": "automod",
    "antiwebhookcog": "automod",
    "antinukeextraownercog": "automod",
    "antinukepanelcog": "automod",
    "antinukewhitelistcog": "automod",

    # Moderation
    "bancog": "moderation",
    "kickcog": "moderation",
    "lockcog": "moderation",
    "purgecog": "moderation",
    "slowmodecog": "moderation",
    "timeoutcog": "moderation",
    "warncog": "moderation",
    "moderation-admins": "moderation",
    "moderation-mods": "moderation",
    "moderation-bots": "moderation",
    "moderation-listroles": "moderation",
    "moderation-role": "moderation",
    "moderation-roleall": "moderation",
    "moderation-roleinfo": "moderation",
    "moderation-emojis": "moderation",
    "modlogcog": "moderation",
    "mediachannels": "moderation",

    # Developer & Owner
    "ownersystem": "owner",
    "developer-blacklist": "owner",
    "developer-dm": "owner",
    "developer-eval": "owner",
    "developer-git": "owner",
    "developer-guilds": "owner",
    "developer-identity": "owner",
    "developer-monitor": "owner",
    "developer-noprefix": "owner",
    "developer-portal": "owner",
    "developer-reload": "owner",
    "developer-shell": "owner",
    "developer-source": "owner",
    "developer-sql": "owner",
    "developer-system": "owner",
    "sync": "owner",

    # Fun & Social
    "fun": "social",
    "games": "social",
    "romance": "social",
    "adulthumor": "social",

    # Images & Avatars
    "animeactions": "images",
    "general-avatar": "images",
    "general-banner": "images",
    "general-serveravatar": "images",
    "general-imagine": "images",

    # Utilities
    "calculator": "utility",
    "reminders": "utility",
    "translator": "utility",
    "stats": "utility",
    "profile": "utility",
    "analyticsanddiagnostics": "utility",
    "utility-snipe": "utility",
    "utility-snipeall": "utility",

    # General & Getting Started
    "ping": "general",
    "botinfo": "general",
    "general-channelinfo": "general",
    "general-serverinfo": "general",
    "general-userinfo": "general",
    "general-membercount": "general",
    "invite": "general",
    "suggestions": "general",
    "tempvoice": "general",
    "embedbuilder": "general",
    "devfeedcog": "general",
    "techfeedcog": "general",
    "autoevents": "general",
    "requirements": "general",
    "steal": "general",
    "sticky": "general",
}


def resolve_command_category(cmd: Any) -> CategoryMeta:
    """
    Bulletproof category resolver for prefix, slash, and hybrid commands.
    Ensures subcommands inherit parent group category and cog mapping is respected.
    """
    # 1. Check parent command group first (e.g. `aivoice stop` -> parent is `aivoice`)
    parent = getattr(cmd, "root_parent", None) or getattr(cmd, "parent", None)
    if parent:
        parent_name = getattr(parent, "name", "").lower()
        if parent_name in ("app", "apply", "staffapp", "applications"):
            return CATEGORY_BY_ID["staff_applications"]
        if parent_name in ("aivoice", "voiceai", "aiv"):
            return CATEGORY_BY_ID["ai"]
        if parent_name in ("bill", "bills", "invoice"):
            return CATEGORY_BY_ID["service_bills"]
        if parent_name in ("ticket", "tickets"):
            return CATEGORY_BY_ID["tickets"]
        if parent_name in ("vouch", "vouches"):
            return CATEGORY_BY_ID["vouches"]
        if parent_name in ("bloxai", "bfai"):
            return CATEGORY_BY_ID["blox_fruits"]
        if parent_name in ("music", "queue", "player"):
            return CATEGORY_BY_ID["music"]
        if parent_name in ("config", "setup", "serverconfig"):
            return CATEGORY_BY_ID["config"]
        if parent_name in ("rr", "reactionrole"):
            return CATEGORY_BY_ID["reaction_roles"]
        if parent_name in ("giveaway", "gstart"):
            return CATEGORY_BY_ID["giveaways"]
        if parent_name in ("verify", "verification"):
            return CATEGORY_BY_ID["verification"]
        if parent_name in ("mod", "warn", "lock"):
            return CATEGORY_BY_ID["moderation"]

    # 2. Check Cog ownership via COG_MAPPINGS
    cog = getattr(cmd, "cog", None)
    if cog:
        cog_name = getattr(cog, "qualified_name", "").lower()
        if cog_name in COG_MAPPINGS:
            cat_id = COG_MAPPINGS[cog_name]
            if cat_id in CATEGORY_BY_ID:
                return CATEGORY_BY_ID[cat_id]

        # Check explicit cog.category attribute
        cog_cat = str(getattr(cog, "category", "")).strip().lower()
        for cat in CATEGORIES:
            if cat.tag.lower() == cog_cat or cat.name.lower() == cog_cat or cat.id == cog_cat:
                return cat

    # 3. Check explicit command name
    name = getattr(cmd, "name", "").lower()
    root_name = getattr(cmd, "qualified_name", name).lower().split()[0]

    # AI Commands (Strict check)
    if root_name in (
        "ai", "chat", "askai", "aizenai", "aivoice", "voicespeak", "voiceask",
        "voicepersona", "voicestop", "voicediag", "speak", "voicejoin", "voiceleave",
        "aigf", "aibaddie", "aispecial", "aiclearcompanion", "aichannel", "aidiag",
        "aistatus", "aisetup", "aipersonality", "aiconfig", "aitest", "aiclear",
        "aimodel", "aidebug", "companion", "setaichannel", "setcompanionchannel",
    ) or root_name.startswith("aivoice"):
        return CATEGORY_BY_ID["ai"]

    # Blox Fruits AI (Strict check)
    if root_name in (
        "bloxai", "fruitinfo", "grindhelp", "tradehelp", "buildhelp", "bfai",
        "finfo", "bfbuild", "tradecalc", "levelhelp", "grindguide", "fruitvalues",
        "fruitnotifier", "fruitstock", "devilfruit", "bloxfruits",
    ):
        return CATEGORY_BY_ID["blox_fruits"]

    # Music Commands (Strict check - verified against Lavalink Player)
    if root_name in (
        "play", "pause", "resume", "skip", "stop", "queue", "nowplaying", "np",
        "volume", "vol", "loop", "repeat", "shuffle", "clear", "remove", "seek",
        "autoplay", "lyrics", "jump", "stay", "247", "playlist", "like", "unlike",
        "disconnect", "dc", "musicdiag", "skipto", "replay", "fwd", "rwd",
    ) and getattr(cog, "qualified_name", "").lower() in ("music", ""):
        return CATEGORY_BY_ID["music"]

    # Tickets & Support
    if root_name in (
        "ticket", "tickets", "close", "reopen", "transcript", "ticketstats",
        "ticketsetup", "ticketpanel", "addmember", "removemember", "claim", "unclaim",
    ):
        return CATEGORY_BY_ID["tickets"]

    # Vouches & Reputation
    if root_name in (
        "vouch", "vouches", "vouchprofile", "vouchleaderboard", "vouchchannel",
        "heldvouches", "vouchremove", "repcheck", "vouchlb", "topvouches", "repleaderboard",
        "vlb", "vouchinfo", "vouchhistory", "vouchimport", "rep", "reputation", "botstaff",
    ):
        return CATEGORY_BY_ID["vouches"]

    # Staff Applications
    if root_name in ("app", "apply", "staffapp", "applications", "staffapplication") or (
        root_name == "top" and any(part in ("app", "apply", "applications") for part in getattr(cmd, "qualified_name", "").lower().split())
    ):
        return CATEGORY_BY_ID["staff_applications"]

    # KDC Shop & Stock & Reviews
    if root_name in ("stock", "kdc", "kdcshop", "shop", "store", "review", "reviews"):
        return CATEGORY_BY_ID["service_bills"]

    # Blox Fruits Service Bills
    if root_name in (
        "bill", "bills", "paid", "cancelbill", "refund", "services", "billconfig",
        "billexport", "servicebill",
    ) or root_name.startswith("bill"):
        return CATEGORY_BY_ID["service_bills"]

    # Verification
    if root_name in (
        "verify", "unverify", "verifysetup", "verifyrole", "verifylog", "verifystatus",
    ) or root_name.startswith("verify"):
        return CATEGORY_BY_ID["verification"]

    # Welcome & Goodbye
    if root_name in (
        "welcome", "goodbye", "autorole", "welcometest", "goodbyetest",
        "welcomecard", "goodbyecard", "welcomesetup",
    ):
        return CATEGORY_BY_ID["welcome"]

    # AFK
    if root_name in ("afk", "setafk", "resetafk", "viewafk", "back"):
        return CATEGORY_BY_ID["afk"]

    # Moderation
    if root_name in (
        "ban", "unban", "kick", "mute", "unmute", "warn", "unwarn", "warnings",
        "clearwarnings", "delwarn", "purge", "lock", "unlock", "hide", "unhide",
        "slowmode", "timeout", "untimeout", "softban", "modlogs", "modlog", "case",
        "admins", "mods", "bots", "listroles",
    ):
        return CATEGORY_BY_ID["moderation"]

    # Automod & Antinuke
    if root_name in (
        "antispam", "antiflood", "invites", "badwords", "mentionspam", "automod",
        "antinuke", "whitelist", "extraowner", "antiraid", "scamcheck", "inviteblock",
    ):
        return CATEGORY_BY_ID["automod"]

    # Giveaways
    if root_name in ("giveaway", "gstart", "gend", "greroll", "glist", "reroll"):
        return CATEGORY_BY_ID["giveaways"]

    # Reaction Roles
    if root_name in ("reactionrole", "rr", "rolemenu", "addreactionrole", "removereactionrole"):
        return CATEGORY_BY_ID["reaction_roles"]

    # Leveling
    if root_name in ("rank", "level", "levels", "levelconfig", "leaderboard", "xp", "setxp", "resetxp"):
        return CATEGORY_BY_ID["leveling"]

    # Premium
    if root_name in ("premium", "redeem", "tier", "license", "prime", "perks"):
        return CATEGORY_BY_ID["premium"]

    # Server Configuration
    if root_name in ("config", "setup", "setprefix", "prefix", "resetprefix", "logs", "modlogs"):
        return CATEGORY_BY_ID["config"]

    # Owner & Developer
    if root_name in (
        "eval", "exec", "restart", "shutdown", "sync", "leaveserver", "blacklist",
        "whitelistuser", "errors", "validateconfig", "maintenance", "reload", "load",
        "unload", "cogs", "systemstatus", "sql", "shell", "git", "portal",
    ):
        return CATEGORY_BY_ID["owner"]

    # Default to General & Utility
    return CATEGORY_BY_ID["general"]


def get_category_by_query(query: str) -> Optional[CategoryMeta]:
    """Look up a category by ID, alias, tag, or partial name."""
    clean = query.strip().lower()
    if clean in CATEGORY_BY_ID:
        return CATEGORY_BY_ID[clean]
    if clean in CATEGORY_SEARCH_ALIASES:
        return CATEGORY_BY_ID[CATEGORY_SEARCH_ALIASES[clean]]
    for cat in CATEGORIES:
        if clean in cat.name.lower() or clean in cat.tag.lower() or cat.id in clean:
            return cat
    return None
