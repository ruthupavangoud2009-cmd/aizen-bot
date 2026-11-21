"""
KYOKA — Aizen Ultimate Edition
Global Premium Response System (Unified UI & Response Framework)

Provides a standardized, dark, premium visual response style inspired by the
signature AFK system layout. All systems across KYOKA use this framework
for consistent embeds, custom animated emojis, clean typography, mobile-first formatting,
and zero cluttered text outside embeds.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Sequence
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class ResponseType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    LOADING = "loading"
    PERMISSION = "permission"
    CONFIRMATION = "confirmation"
    SYSTEM = "system"
    PREMIUM = "premium"
    AI = "ai"
    MODERATION = "moderation"
    MUSIC = "music"
    TICKET = "ticket"
    VERIFICATION = "verification"


class KyokaPalette:
    """Aizen Eclipse Theme Colors for consistent premium responses."""
    PRIMARY: int = 0x2B0938       # Aizen signature deep violet
    SURFACE_DARK: int = 0x120C1F  # Charcoal violet backdrop
    SUCCESS: int = 0x10B981       # Emerald green confirmed actions
    ERROR: int = 0xEF4444         # Crimson rose errors
    WARNING: int = 0xF59E0B       # Amber gold alerts
    INFO: int = 0x38BDF8          # Sky cyan telemetry
    LOADING: int = 0x7C3AED       # Vivid spiritual purple
    PERMISSION: int = 0xDC2626    # Deep danger red
    CONFIRMATION: int = 0x10B981  # Confirm green
    SYSTEM: int = 0x1E1B4B        # Dark obsidian console
    PREMIUM: int = 0xA855F7       # Kyoka Prime purple
    AI: int = 0x6366F1            # Neural Indigo
    MODERATION: int = 0x8B5CF6    # Sentry Violet
    MUSIC: int = 0xEC4899         # Melody Pink
    TICKET: int = 0x06B6D4        # Support Cyan
    VERIFICATION: int = 0x10B981  # Verified Emerald

    @classmethod
    def get_color(cls, rtype: ResponseType | str) -> int:
        name = rtype.value.upper() if isinstance(rtype, ResponseType) else str(rtype).upper()
        return getattr(cls, name, cls.PRIMARY)


class KyokaResponse:
    """
    Unified KYOKA Premium Response Model.
    Generates single clean embeds adhering to Aizen visual guidelines.
    Mobile-friendly, no text overflow, consistent iconography and footers.
    """

    def __init__(
        self,
        response_type: ResponseType = ResponseType.INFO,
        title: str = "",
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
        author_name: Optional[str] = None,
        author_icon_url: Optional[str] = None,
        footer_text: Optional[str] = None,
        footer_icon_url: Optional[str] = None,
        custom_emoji: Optional[str] = None,
        color: Optional[int] = None,
        timestamp: Optional[datetime.datetime] = None,
    ) -> None:
        self.response_type = response_type
        self.title = title
        self.description = description
        self.fields = list(fields or [])
        self.thumbnail_url = thumbnail_url
        self.image_url = image_url
        self.author_name = author_name
        self.author_icon_url = author_icon_url
        self.footer_text = footer_text or "KYOKA — Aizen Edition"
        self.footer_icon_url = footer_icon_url
        self.custom_emoji = custom_emoji
        self.color = color if color is not None else KyokaPalette.get_color(response_type)
        self.timestamp = timestamp or discord.utils.utcnow()

    def add_field(self, name: str, value: Any, inline: bool = False) -> KyokaResponse:
        self.fields.append((str(name), value, inline))
        return self

    def build_embed(self, bot: Optional[KyokaBot] = None) -> discord.Embed:
        """Construct the unified mobile-optimized discord.Embed."""
        emoji_prefix = ""
        bullet_icon = "•"

        # Resolve custom animated or static emoji from registry
        if bot and hasattr(bot, "custom_emojis"):
            reg = bot.custom_emojis
            cat_name = self.response_type.value.upper()
            if self.custom_emoji:
                emoji_prefix = self.custom_emoji
            else:
                emoji_prefix = reg.get_category(cat_name, fallback="")
            bullet_icon = reg.get("heart_dot", reg.get("icons_rightarrow", "•"))

        # Clean title with custom emoji
        formatted_title = f"{emoji_prefix} {self.title}".strip() if emoji_prefix else self.title

        embed = discord.Embed(
            title=formatted_title[:256] if formatted_title else None,
            description=self.description[:4000] if self.description else None,
            color=self.color,
            timestamp=self.timestamp,
        )

        if self.author_name:
            embed.set_author(name=self.author_name[:256], icon_url=self.author_icon_url)

        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)

        if self.image_url:
            embed.set_image(url=self.image_url)

        for name, value, inline in self.fields[:25]:
            field_name = str(name)[:256]
            # Format value with bullet if multiline key-value without bullet
            field_val = str(value)[:1024]
            embed.add_field(name=field_name, value=field_val, inline=inline)

        footer_text = self.footer_text
        embed.set_footer(
            text=footer_text[:2048] if footer_text else "KYOKA — Aizen Edition",
            icon_url=self.footer_icon_url,
        )

        return embed

    # ── Factory Constructors ─────────────────────────────────────────────────

    @classmethod
    def success(
        cls,
        title: str = "Action Confirmed",
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.SUCCESS,
            title=title,
            description=description,
            fields=fields,
            footer_text=f"-# Requested by {author.display_name}" if author else "KYOKA — Action Confirmed",
            thumbnail_url=author.display_avatar.url if author else None,
        )

    @classmethod
    def error(
        cls,
        title: str = "Command Error",
        description: str = "",
        incident_id: Optional[str] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        desc = description
        if incident_id:
            desc = f"{description}\n\n**Incident ID:** `{incident_id}`\n*Report this ID to administrators if this continues.*"
        return cls(
            response_type=ResponseType.ERROR,
            title=title,
            description=desc,
            footer_text=f"-# Requested by {author.display_name}" if author else "KYOKA — Error Diagnostic",
        )

    @classmethod
    def warning(
        cls,
        title: str = "Attention Required",
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.WARNING,
            title=title,
            description=description,
            fields=fields,
            footer_text=f"-# Requested by {author.display_name}" if author else "KYOKA — Warning",
        )

    @classmethod
    def info(
        cls,
        title: str = "Information",
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        author: Optional[discord.User | discord.Member] = None,
        thumbnail_url: Optional[str] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.INFO,
            title=title,
            description=description,
            fields=fields,
            thumbnail_url=thumbnail_url or (author.display_avatar.url if author else None),
            footer_text=f"-# Requested by {author.display_name}" if author else "KYOKA — Aizen Edition",
        )

    @classmethod
    def loading(
        cls,
        title: str = "Processing Request...",
        description: str = "Please wait while Kyoka synchronizes state...",
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.LOADING,
            title=title,
            description=description,
            footer_text="KYOKA — Synchronizing State",
        )

    @classmethod
    def permission(
        cls,
        title: str = "Permission Denied",
        description: str = "You do not have the required permissions to execute this action.",
        missing_perms: Optional[list[str]] = None,
    ) -> KyokaResponse:
        desc = description
        if missing_perms:
            perms_str = ", ".join(f"`{p}`" for p in missing_perms)
            desc = f"{description}\n\n**Required:** {perms_str}"
        return cls(
            response_type=ResponseType.PERMISSION,
            title=title,
            description=desc,
            footer_text="KYOKA — Access Control",
        )

    @classmethod
    def moderation(
        cls,
        action: str,
        target: discord.User | discord.Member,
        moderator: discord.User | discord.Member,
        reason: str = "No reason provided",
        extra_fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
    ) -> KyokaResponse:
        fields = [
            ("Target", f"**{target}** `「{target.id}」`", True),
            ("Moderator", f"**{moderator}**", True),
            ("Reason", f"`{reason}`", False),
        ]
        if extra_fields:
            fields.extend(extra_fields)
        return cls(
            response_type=ResponseType.MODERATION,
            title=f"Member {action.title()}",
            description=f"Action **{action.upper()}** executed successfully.",
            fields=fields,
            thumbnail_url=target.display_avatar.url if hasattr(target, "display_avatar") else None,
            footer_text=f"-# Moderator: {moderator.display_name} • KYOKA Moderation",
        )

    @classmethod
    def music(
        cls,
        title: str,
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        thumbnail_url: Optional[str] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.MUSIC,
            title=title,
            description=description,
            fields=fields,
            thumbnail_url=thumbnail_url,
            footer_text=f"-# Queued by {author.display_name}" if author else "KYOKA Audio Engine • kasawa-v4",
        )

    @classmethod
    def ticket(
        cls,
        title: str,
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.TICKET,
            title=title,
            description=description,
            fields=fields,
            footer_text=f"-# Creator: {author.display_name}" if author else "KYOKA Ticket Security Portal",
        )

    @classmethod
    def verification(
        cls,
        title: str = "Server Verification",
        description: str = "",
        fields: Optional[Sequence[tuple[str, Any, bool]]] = None,
    ) -> KyokaResponse:
        return cls(
            response_type=ResponseType.VERIFICATION,
            title=title,
            description=description,
            fields=fields,
            footer_text="KYOKA Verification Engine",
        )

    @classmethod
    def ai(
        cls,
        persona_name: str,
        answer: str,
        latency_ms: Optional[float] = None,
        author: Optional[discord.User | discord.Member] = None,
    ) -> KyokaResponse:
        footer = f"-# Prompted by {author.display_name}" if author else "KYOKA Aizen AI Engine"
        if latency_ms is not None:
            footer += f" • {latency_ms:.0f}ms"
        return cls(
            response_type=ResponseType.AI,
            title=persona_name,
            description=answer,
            footer_text=footer,
            thumbnail_url=author.display_avatar.url if author else None,
        )

    @classmethod
    def premium(
        cls,
        title: str = "Kyoka Prime Feature",
        description: str = "This feature requires an active KYOKA Prime subscription.",
        tier_info: str = "PRO ($4.99/mo) or ULTIMATE ($9.99/mo)",
    ) -> KyokaResponse:
        fields = [
            ("Supported Tiers", tier_info, False),
            ("Unlock", "Use `+license activate <key>` or visit the dashboard.", False),
        ]
        return cls(
            response_type=ResponseType.PREMIUM,
            title=title,
            description=description,
            fields=fields,
            footer_text="KYOKA Prime • Unlimited Access",
        )


async def send_response(
    target: discord.Interaction | commands.Context | discord.abc.Messageable | discord.User | discord.Member,
    response: KyokaResponse,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = False,
    file: Optional[discord.File] = None,
    files: Optional[list[discord.File]] = None,
) -> Any:
    """
    Unified response sender for KYOKA.
    Handles Interactions, Contexts, Channels, and DMs consistently with zero clutter.
    """
    # Resolve bot instance defensively
    bot = getattr(target, "bot", getattr(target, "client", None))
    if not bot and hasattr(target, "_state"):
        bot = getattr(target._state, "_parent", getattr(target._state, "bot", None))

    embed = response.build_embed(bot=bot)
    file_list = [file] if file else (files or None)

    # 1. Interaction or Context wrapping an Interaction
    interaction = getattr(target, "interaction", target if isinstance(target, discord.Interaction) else None)
    if isinstance(interaction, discord.Interaction):
        try:
            if interaction.response.is_done():
                return await interaction.followup.send(
                    embed=embed,
                    view=view or discord.utils.MISSING,
                    ephemeral=ephemeral,
                    files=file_list or discord.utils.MISSING,
                )
            else:
                return await interaction.response.send_message(
                    embed=embed,
                    view=view or discord.utils.MISSING,
                    ephemeral=ephemeral,
                    files=file_list or discord.utils.MISSING,
                )
        except (discord.NotFound, discord.HTTPException):
            # Interaction expired (3s limit reached before dispatch): fallback to channel send
            channel = getattr(interaction, "channel", None)
            if channel and hasattr(channel, "send"):
                return await channel.send(embed=embed, view=view or discord.utils.MISSING, files=file_list or discord.utils.MISSING)
            raise

    # 2. Text Command Context or Direct Channel
    send_callable = getattr(target, "send", None)
    if callable(send_callable):
        try:
            return await send_callable(
                embed=embed,
                view=view or discord.utils.MISSING,
                files=file_list or discord.utils.MISSING,
            )
        except discord.Forbidden:
            raise
        except Exception:
            # Fallback if channel send encounters parameter error
            return await send_callable(embed=embed)

    # 3. User / Member DM
    if isinstance(target, (discord.User, discord.Member)):
        dm_channel = await target.create_dm()
        return await dm_channel.send(
            embed=embed,
            view=view or discord.utils.MISSING,
            files=file_list or discord.utils.MISSING,
        )
