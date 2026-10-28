"""
Kyoka 3.0 - Centralized Feature-Access Registry & Premium Entitlement Engine
Defines Free vs Premium feature tiers, enforces access control across prefix commands,
slash commands, interactions, and web dashboard APIs, and provides branded upgrade feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional
import discord
from discord.ext import commands

from src.core.config import Config
from src.security.owner import is_primary_owner, is_owner_or_staff

logger = logging.getLogger("Kyoka.Security.FeatureAccess")


class FeatureTier(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


@dataclass(frozen=True)
class FeatureDefinition:
    """Metadata describing a single Kyoka capability and its required tier."""
    id: str
    name: str
    tier: FeatureTier
    category: str
    description: str
    commands: list[str] = field(default_factory=list)


# ── Canonical Master Feature Catalog ──
FEATURE_CATALOG: list[FeatureDefinition] = [
    # ── FREE TIER (Available to every server) ──
    FeatureDefinition(
        id="basic_moderation",
        name="Core Moderation Tools",
        tier=FeatureTier.FREE,
        category="Moderation",
        description="High-precision moderation: ban, kick, timeout, warn, purge, lock/unlock, slowmode, and modlogs.",
        commands=["ban", "kick", "timeout", "warn", "delwarn", "purge", "lock", "unlock", "slowmode", "modlog"],
    ),
    FeatureDefinition(
        id="basic_utility",
        name="Utility & Information",
        tier=FeatureTier.FREE,
        category="Utility",
        description="Everyday utilities: calculators, reminders, avatar/banner lookups, serverinfo, userinfo, and ping.",
        commands=["ping", "uptime", "serverinfo", "userinfo", "avatar", "banner", "calc", "remind", "snipe"],
    ),
    FeatureDefinition(
        id="basic_welcome",
        name="Standard Welcome & Farewell",
        tier=FeatureTier.FREE,
        category="Welcome",
        description="Standard welcome cards, goodbye announcements, autoroles, and basic join logging.",
        commands=["setup", "autorole", "welcome", "goodbye"],
    ),
    FeatureDefinition(
        id="basic_verification",
        name="Verification Gatekeeper",
        tier=FeatureTier.FREE,
        category="Security",
        description="Interactive button and captcha verification gate with unverified role isolation.",
        commands=["verify", "verification"],
    ),
    FeatureDefinition(
        id="basic_tickets",
        name="Standard Support Tickets",
        tier=FeatureTier.FREE,
        category="Tickets",
        description="Single support panel creation, interactive ticket claims, and standard closing.",
        commands=["ticket", "tickets", "close", "claim"],
    ),
    FeatureDefinition(
        id="basic_giveaways",
        name="Giveaway System",
        tier=FeatureTier.FREE,
        category="Giveaways",
        description="Standard giveaways with countdown timers, automatic winner selection, and rerolls.",
        commands=["gstart", "gend", "greroll", "giveaway"],
    ),
    FeatureDefinition(
        id="basic_music",
        name="High-Fidelity Music Playback",
        tier=FeatureTier.FREE,
        category="Music",
        description="Lavalink v4 audio player: play, pause, resume, skip, stop, queue, volume, and lyrics.",
        commands=["play", "pause", "resume", "skip", "stop", "queue", "volume", "np", "nowplaying", "seek"],
    ),
    FeatureDefinition(
        id="basic_afk_fun",
        name="AFK, Community & Fun",
        tier=FeatureTier.FREE,
        category="Social",
        description="AFK status notices, anime reaction actions, truth-or-dare, trivia, 8ball, and social stats.",
        commands=["afk", "hug", "kiss", "pat", "slap", "8ball", "trivia", "tod", "ship"],
    ),
    FeatureDefinition(
        id="basic_server_config",
        name="Server Prefix & Configuration",
        tier=FeatureTier.FREE,
        category="Administration",
        description="Single active prefix configuration per server, module toggles, and server diagnostics.",
        commands=["prefix", "setprefix", "resetprefix"],
    ),
    FeatureDefinition(
        id="basic_help",
        name="Interactive Help Manual",
        tier=FeatureTier.FREE,
        category="General",
        description="Complete Nyxium-style directory, multi-page category browser, search modal, and command manual.",
        commands=["help", "commands", "modules", "hca"],
    ),

    # ── PREMIUM TIER (Requires Server Premium Subscription) ──
    FeatureDefinition(
        id="custom_bot_avatar",
        name="Server-Specific Bot Avatar",
        tier=FeatureTier.PREMIUM,
        category="Customization",
        description="Upload custom bot avatar for your server via Discord commands or Web Dashboard with persistent storage.",
        commands=["setbotavatar", "botavatar", "resetbotavatar"],
    ),
    FeatureDefinition(
        id="music_247",
        name="24/7 Music Radio Stay Mode",
        tier=FeatureTier.PREMIUM,
        category="Music",
        description="Uninterrupted 24/7 continuous radio playback that never disconnects when voice channels are empty.",
        commands=["247", "stay", "halloween", "halloween247"],
    ),
    FeatureDefinition(
        id="advanced_branding",
        name="Custom Aizen Visual Palette",
        tier=FeatureTier.PREMIUM,
        category="Branding",
        description="Full custom hex embed colors, server-specific author icons, and expanded Aizen artwork.",
        commands=["embed", "customembed"],
    ),
    FeatureDefinition(
        id="premium_welcome_cards",
        name="Animated & Theme Welcome Cards",
        tier=FeatureTier.PREMIUM,
        category="Welcome",
        description="High-resolution Cyber Sakura, Celestial Nebula, and Hueco Mundo animated welcome artworks.",
        commands=["welcometheme", "welcomestyle"],
    ),
    FeatureDefinition(
        id="advanced_tickets",
        name="Multi-Panel Enterprise Tickets",
        tier=FeatureTier.PREMIUM,
        category="Tickets",
        description="Unlimited ticket panels, custom embed descriptions, multi-department routing, and HTML transcripts.",
        commands=["ticketpanel", "transcript"],
    ),
    FeatureDefinition(
        id="advanced_giveaways",
        name="Role-Gated Giveaways & Multi-Winners",
        tier=FeatureTier.PREMIUM,
        category="Giveaways",
        description="Role requirements, bypass roles, bonus entry multipliers, and multi-winner raffles.",
        commands=["gcreate", "gsettings"],
    ),
    FeatureDefinition(
        id="premium_ai",
        name="Priority Gemini AI & All Personas",
        tier=FeatureTier.PREMIUM,
        category="AI",
        description="Priority Google Gemini AI execution (~600ms), access to all 10 AI personas, and higher token limits.",
        commands=["ai", "persona", "aipersona", "imagine"],
    ),
    FeatureDefinition(
        id="advanced_leveling",
        name="Custom Rank Cards & XP Multipliers",
        tier=FeatureTier.PREMIUM,
        category="Leveling",
        description="Custom rank card background themes, role XP multipliers, and channel XP exclusions.",
        commands=["rankcard", "xpmultiplier"],
    ),
    FeatureDefinition(
        id="advanced_logging",
        name="Modular Security & Audit Logging",
        tier=FeatureTier.PREMIUM,
        category="Logging",
        description="Dedicated channels per log category, anti-ghostping tracking, and extended security audit history.",
        commands=["logchannel", "ghostping"],
    ),
]

FEATURE_BY_ID: dict[str, FeatureDefinition] = {f.id: f for f in FEATURE_CATALOG}
FEATURE_BY_CMD: dict[str, FeatureDefinition] = {
    cmd.lower(): f for f in FEATURE_CATALOG for cmd in f.commands
}


def get_feature(feature_id: str) -> FeatureDefinition | None:
    """Retrieve feature definition by ID."""
    return FEATURE_BY_ID.get(feature_id)


def get_feature_by_command(command_name: str) -> FeatureDefinition | None:
    """Retrieve feature definition by command name."""
    return FEATURE_BY_CMD.get(command_name.lower())


def is_feature_premium(feature_id: str) -> bool:
    """Return True if feature requires a paid subscription."""
    feat = get_feature(feature_id)
    return feat is not None and feat.tier in (FeatureTier.PREMIUM, FeatureTier.PRO)


def get_free_features() -> list[FeatureDefinition]:
    """Return all features available on standard free tier."""
    return [f for f in FEATURE_CATALOG if f.tier == FeatureTier.FREE]


def get_premium_features() -> list[FeatureDefinition]:
    """Return all features that require paid server premium."""
    return [f for f in FEATURE_CATALOG if f.tier in (FeatureTier.PREMIUM, FeatureTier.PRO)]


# ── Guild Feature Access Check ──

async def check_guild_feature_access(
    bot: Any,
    guild_id: int | None,
    feature_id: str,
    user_id: int | None = None,
) -> tuple[bool, str, FeatureDefinition | None]:
    """
    Check if a guild (or user) has access to a specific feature.
    
    Returns:
        (has_access: bool, reason: str, feature_def: FeatureDefinition | None)
    """
    feat = get_feature(feature_id)
    if not feat:
        # Unknown feature defaults to permitted for safety
        return True, "Unknown feature", None

    # Free features are universally accessible
    if feat.tier == FeatureTier.FREE:
        return True, "Free feature", feat

    # Bot Primary Owner and Bot Staff bypass all restrictions
    if user_id and is_owner_or_staff(user_id):
        return True, "Bot Owner/Staff Override", feat

    if not guild_id:
        return False, "This command can only be executed within a Discord server.", feat

    # Check guild premium status from memory cache (<0.001ms) or premium service
    premium_mgr = getattr(bot, "premium_mgr", None)
    if premium_mgr and hasattr(premium_mgr, "is_guild_premium"):
        try:
            if premium_mgr.is_guild_premium(guild_id):
                return True, "Active Server Premium", feat
        except Exception:
            pass
    elif hasattr(bot, "premium_service") and bot.premium_service:
        try:
            if await bot.premium_service.has_premium(scope="server", target_id=guild_id):
                return True, "Active Server Premium", feat
        except Exception:
            pass

    # Check user personal VIP status as fallback
    if user_id:
        if premium_mgr and hasattr(premium_mgr, "is_user_premium"):
            try:
                if premium_mgr.is_user_premium(user_id):
                    return True, "Active User VIP Subscription", feat
            except Exception:
                pass
        elif hasattr(bot, "premium_service") and bot.premium_service:
            try:
                if await bot.premium_service.has_premium(scope="user", target_id=user_id):
                    return True, "Active User VIP Subscription", feat
            except Exception:
                pass

    return False, f"**{feat.name}** requires an active **Kyoka Premium** server subscription.", feat


# ── Premium Required Check Failure Exception ──

class PremiumRequiredError(commands.CheckFailure):
    """Raised when a command requires Kyoka Premium."""

    def __init__(self, feature_id: str, feature_name: str | None = None) -> None:
        self.feature_id = feature_id
        feat = get_feature(feature_id)
        self.feature_name = feature_name or (feat.name if feat else "This feature")
        super().__init__(f"Premium subscription required for: {self.feature_name}")


def build_premium_required_embed(
    ctx_or_interaction: Any,
    feature_id: str,
) -> tuple[discord.Embed, discord.ui.View]:
    """Construct a beautiful, dark-purple Aizen Premium Required card."""
    feat = get_feature(feature_id)
    feat_name = feat.name if feat else "Exclusive Feature"
    feat_desc = feat.description if feat else "This capability requires a Kyoka Premium server subscription."

    embed = discord.Embed(
        title="💎 KYOKA PREMIUM REQUIRED",
        description=(
            f"**{feat_name}** is an exclusive **Kyoka Premium** capability.\n\n"
            f"> *\"{feat_desc}\"*\n\n"
            f"• **Current Server Plan:** `Standard (Free)`\n"
            f"• **Unlocked with Premium:** Custom bot avatars, 24/7 radio stay mode, unlimited ticket panels, priority Gemini AI, and custom visual palette.\n"
            f"• **How to Upgrade:** Use the buttons below or visit the web dashboard to activate an instant license key."
        ),
        color=0x7C3AED,
    )

    assets = getattr(Config, "ASSETS", None)
    thumb = getattr(assets, "AIZEN_AVATAR_URL", "")
    if thumb and thumb.strip():
        embed.set_thumbnail(url=thumb.strip())

    author_name = "Server Admin"
    if hasattr(ctx_or_interaction, "author") and ctx_or_interaction.author:
        author_name = ctx_or_interaction.author.display_name
    elif hasattr(ctx_or_interaction, "user") and ctx_or_interaction.user:
        author_name = ctx_or_interaction.user.display_name

    embed.set_footer(
        text=f"Requested by {author_name} • KYOKA 3.0 — Aizen Edition",
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

    return embed, view


# ── Command Decorator: @require_premium ──

def require_premium(feature_id: str):
    """
    Decorator enforcing that the executing server has an active Premium subscription.
    Works seamlessly on standard prefix commands, hybrid commands, and slash commands.
    """
    async def predicate(ctx: commands.Context) -> bool:
        guild_id = ctx.guild.id if ctx.guild else None
        user_id = ctx.author.id if ctx.author else None

        has_access, reason, feat = await check_guild_feature_access(
            ctx.bot, guild_id, feature_id, user_id=user_id
        )

        if not has_access:
            embed, view = build_premium_required_embed(ctx, feature_id)
            try:
                await ctx.send(embed=embed, view=view)
            except Exception:
                pass
            raise PremiumRequiredError(feature_id)

        return True

    return commands.check(predicate)
