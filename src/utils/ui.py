"""
Kyoka Discord Bot — Sosuke Aizen Ultimate Design System & Modular UI Framework
Provides centralized color tokens, typography formatting, KyokaEmbed builders,
pagination controllers, and interactive modal dialogs across all bot modules.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Callable, Coroutine, List, Optional, Sequence, Union
import discord
from discord import ui
from discord.ext import commands

logger = logging.getLogger("Kyoka.UI")


# ─────────────────────────────────────────────────────────────────────────────
# 1. AIZEN DESIGN SYSTEM COLOR TOKENS
# ─────────────────────────────────────────────────────────────────────────────
class AizenPalette:
    """Standardized color palette for Kyoka x Sosuke Aizen supernatural cyber theme."""
    VOID_BLACK: int = 0x0A0A0F      # Pitch midnight abyss
    DEEP_PURPLE: int = 0x1A0933     # Midnight velvet
    ROYAL_VIOLET: int = 0x7C3AED    # Primary Aizen Reiatsu violet
    ELECTRIC_PURPLE: int = 0x9333EA # Vivid glow purple
    LAVENDER_GLOW: int = 0xDDD6FE   # Soft lavender accent
    CRIMSON: int = 0xFF3366         # Laser crimson / Kyoka blade
    BLOOD_MOON: int = 0xDC2626      # Deep danger crimson
    AMBER_WARN: int = 0xF59E0B      # Alert amber
    EMERALD_SUCCESS: int = 0x10B981 # Verified / success green
    CYBER_CYAN: int = 0x06B6D4      # Telemetry / info cyan
    INDIGO_INFO: int = 0x6366F1     # General info
    BLADE_SILVER: int = 0xE2E8F0    # Metallic white / silver
    MUTED_GRAY: int = 0x64748B      # Secondary footer text


# ─────────────────────────────────────────────────────────────────────────────
# 2. VISUAL SYMBOLS & TYPOGRAPHY
# ─────────────────────────────────────────────────────────────────────────────
class AizenSymbols:
    """Supernatural Aizen-themed symbols and indicators."""
    GATEWAY: str = "⛩️"
    BLADE: str = "⚔️"
    SHIELD: str = "🛡️"
    CROWN: str = "👑"
    DIAMOND: str = "💎"
    ORB: str = "🔮"
    SPARKLE: str = "✨"
    SCROLL: str = "📜"
    GEAR: str = "⚙️"
    WRENCH: str = "🔧"
    CHART: str = "📊"
    HEART: str = "💖"
    MUSIC: str = "🎵"
    TICKET: str = "🎫"
    GIFT: str = "🎉"
    SEARCH: str = "🔍"
    LOCK: str = "🔒"
    CHECK: str = "✅"
    CROSS: str = "❌"
    WARN: str = "⚠️"
    DOT: str = "•"
    ARROW: str = "»"
    STAR: str = "✦"
    BAR_FULL: str = "▰"
    BAR_EMPTY: str = "▱"


# ─────────────────────────────────────────────────────────────────────────────
# 3. MODULAR EMBED BUILDER (KyokaEmbed)
# ─────────────────────────────────────────────────────────────────────────────
class KyokaEmbed(discord.Embed):
    """
    Standardized Discord Embed builder implementing the Kyoka x Aizen Design System.
    Ensures consistent spacing, colors, footers, timestamps, and typography.
    """

    def __init__(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        color: int | None = None,
        url: str | None = None,
        timestamp: discord.datetime | None = None,
    ) -> None:
        super().__init__(
            title=title,
            description=description,
            color=color or AizenPalette.ROYAL_VIOLET,
            url=url,
            timestamp=timestamp or discord.utils.utcnow(),
        )

    # ── Factory Helpers ──────────────────────────────────────────────────────

    @classmethod
    def standard(
        cls,
        title: str,
        description: str,
        *,
        color: int = AizenPalette.ROYAL_VIOLET,
        icon: str = AizenSymbols.GATEWAY,
        thumbnail: str | None = None,
        image: str | None = None,
        footer: str | None = None,
        footer_icon: str | None = None,
    ) -> KyokaEmbed:
        """Create a standard Aizen-themed card."""
        embed = cls(
            title=f"{icon} {title}".strip() if icon else title,
            description=description,
            color=color,
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        embed.set_footer(
            text=footer or "Kyoka 3.0 • Aizen Control System",
            icon_url=footer_icon,
        )
        return embed

    @classmethod
    def success(
        cls,
        title: str,
        description: str,
        *,
        footer: str | None = None,
        footer_icon: str | None = None,
    ) -> KyokaEmbed:
        """Create a green-accented operation success embed."""
        embed = cls(
            title=f"{AizenSymbols.CHECK} {title}",
            description=f"> {description}",
            color=AizenPalette.EMERALD_SUCCESS,
        )
        embed.set_footer(
            text=footer or "Kyoka Security • Verified",
            icon_url=footer_icon,
        )
        return embed

    @classmethod
    def error(
        cls,
        title: str,
        description: str,
        *,
        suggestion: str | None = None,
        footer: str | None = None,
        footer_icon: str | None = None,
    ) -> KyokaEmbed:
        """Create a crimson-accented error embed."""
        desc = f"> {description}"
        if suggestion:
            desc += f"\n\n**Suggestion:**\n> {suggestion}"
        embed = cls(
            title=f"{AizenSymbols.CROSS} {title}",
            description=desc,
            color=AizenPalette.CRIMSON,
        )
        embed.set_footer(
            text=footer or "Kyoka Diagnostics • Error Resolved",
            icon_url=footer_icon,
        )
        return embed

    @classmethod
    def warning(
        cls,
        title: str,
        description: str,
        *,
        footer: str | None = None,
        footer_icon: str | None = None,
    ) -> KyokaEmbed:
        """Create an amber-accented warning embed."""
        embed = cls(
            title=f"{AizenSymbols.WARN} {title}",
            description=f"> {description}",
            color=AizenPalette.AMBER_WARN,
        )
        embed.set_footer(
            text=footer or "Kyoka Warning Protocol",
            icon_url=footer_icon,
        )
        return embed

    @classmethod
    def info(
        cls,
        title: str,
        description: str,
        *,
        thumbnail: str | None = None,
        footer: str | None = None,
        footer_icon: str | None = None,
    ) -> KyokaEmbed:
        """Create an indigo/cyan-accented informational embed."""
        embed = cls(
            title=f"{AizenSymbols.ORB} {title}",
            description=description,
            color=AizenPalette.INDIGO_INFO,
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(
            text=footer or "Kyoka Telemetry",
            icon_url=footer_icon,
        )
        return embed

    @classmethod
    def loading(
        cls,
        title: str = "Processing Command...",
        description: str = "Consulting the Hogyoku. Please hold...",
    ) -> KyokaEmbed:
        """Create a loading / waiting state embed."""
        return cls(
            title=f"{AizenSymbols.SPARKLE} {title}",
            description=f"> {description}",
            color=AizenPalette.ROYAL_VIOLET,
        )

    @classmethod
    def denied(
        cls,
        reason: str = "You lack the required authorization to execute this command.",
    ) -> KyokaEmbed:
        """Create an access denied embed."""
        embed = cls(
            title=f"{AizenSymbols.LOCK} Access Restricted",
            description=f"> {reason}\n\n*“Admiration is the furthest thing from understanding.”* — Sosuke Aizen",
            color=AizenPalette.BLOOD_MOON,
        )
        embed.set_footer(text="Kyoka Security Guard • Permission Denied")
        return embed

    @classmethod
    def moderation(
        cls,
        action: str,
        target: Any,
        moderator: Any,
        reason: str = "No reason provided",
        *,
        duration: str | None = None,
    ) -> KyokaEmbed:
        """Create a standardized dark-purple moderation audit embed."""
        t_name = getattr(target, "display_name", str(target))
        m_name = getattr(moderator, "display_name", str(moderator))
        desc = (
            f"**Action:** `{action.upper()}`\n"
            f"**Target:** {getattr(target, 'mention', t_name)} `「{getattr(target, 'id', '0')}」`\n"
            f"**Moderator:** {getattr(moderator, 'mention', m_name)}\n"
            f"**Reason:** `{reason}`"
        )
        if duration:
            desc += f"\n**Duration:** `{duration}`"
        embed = cls(
            title=f"{AizenSymbols.SHIELD} Moderation Action • {action.title()}",
            description=desc,
            color=AizenPalette.ROYAL_VIOLET,
        )
        t_avatar = getattr(getattr(target, "display_avatar", None), "url", None)
        if t_avatar:
            embed.set_thumbnail(url=str(t_avatar))
        embed.set_footer(text="KYOKA Moderation Protocol • Logged")
        return embed

    @classmethod
    def afk_notice(
        cls,
        member: Any,
        reason: str,
        *,
        duration_str: str | None = None,
    ) -> KyokaEmbed:
        """Create a standardized AFK notification embed."""
        m_name = getattr(member, "display_name", str(member))
        desc = f"**{m_name}** is currently AFK.\n> **Reason:** `{reason}`"
        if duration_str:
            desc += f"\n> **Since:** `{duration_str} ago`"
        embed = cls(
            title=f"💤 Member AFK",
            description=desc,
            color=AizenPalette.DEEP_PURPLE,
        )
        m_avatar = getattr(getattr(member, "display_avatar", None), "url", None)
        if m_avatar:
            embed.set_thumbnail(url=str(m_avatar))
        embed.set_footer(text="KYOKA • Presence System")
        return embed

    @classmethod
    def vouch_card(
        cls,
        recipient: Any,
        author: Any,
        comment: str,
        *,
        total_vouches: int = 1,
    ) -> KyokaEmbed:
        """Create a standardized member vouch card."""
        r_name = getattr(recipient, "display_name", str(recipient))
        a_name = getattr(author, "display_name", str(author))
        embed = cls(
            title=f"⭐ Vouch Recorded for {r_name}",
            description=(
                f"> “{comment}”\n\n"
                f"**Vouched by:** {getattr(author, 'mention', a_name)}\n"
                f"**Total Reputation:** **{total_vouches}** vouches"
            ),
            color=AizenPalette.ELECTRIC_PURPLE,
        )
        r_avatar = getattr(getattr(recipient, "display_avatar", None), "url", None)
        if r_avatar:
            embed.set_thumbnail(url=str(r_avatar))
        embed.set_footer(text="KYOKA Trust & Reputation Network")
        return embed

    @staticmethod
    def progress_bar(
        current: Union[int, float],
        total: Union[int, float],
        *,
        length: int = 12,
        fill_char: str = AizenSymbols.BAR_FULL,
        empty_char: str = AizenSymbols.BAR_EMPTY,
    ) -> str:
        """Generate a sleek Unicode progress bar."""
        if total <= 0:
            percentage = 100.0
            filled_length = length
        else:
            percentage = max(0.0, min(100.0, (float(current) / float(total)) * 100.0))
            filled_length = int(round((percentage / 100.0) * length))

        filled_length = max(0, min(length, filled_length))
        empty_length = length - filled_length
        bar = (fill_char * filled_length) + (empty_char * empty_length)
        return f"`{bar}` **{percentage:.1f}%**"


# ─────────────────────────────────────────────────────────────────────────────
# 4. REUSABLE PAGINATOR VIEW (KyokaPaginator)
# ─────────────────────────────────────────────────────────────────────────────
class KyokaPaginator(ui.View):
    """
    Production-grade paginator supporting Discord button navigation,
    first/prev/page/next/last controls, author isolation, and graceful timeout.
    """

    def __init__(
        self,
        pages: Sequence[Union[discord.Embed, KyokaEmbed]],
        author_id: int,
        *,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.pages: Sequence[Union[discord.Embed, KyokaEmbed]] = pages
        self.author_id: int = author_id
        self.current_page: int = 0
        self.total_pages: int = len(pages)
        self.message: Optional[discord.Message] = None

        self._update_buttons()

    def _update_buttons(self) -> None:
        """Enable or disable directional buttons based on current page index."""
        self.first_button.disabled = (self.current_page == 0)
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        self.last_button.disabled = (self.current_page >= self.total_pages - 1)
        self.indicator_button.label = f"{self.current_page + 1}/{self.total_pages}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"{AizenSymbols.CROSS} Only the user who executed this command can navigate this menu.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    @ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def first_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.current_page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(emoji="◀️", style=discord.ButtonStyle.primary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def indicator_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        pass

    @ui.button(emoji="▶️", style=discord.ButtonStyle.primary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def last_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.current_page = self.total_pages - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(emoji="🗑️", label="Dismiss", style=discord.ButtonStyle.danger, row=1)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                embed=KyokaEmbed.info("Session Closed", "> This interactive session has ended."),
                view=self,
            )
