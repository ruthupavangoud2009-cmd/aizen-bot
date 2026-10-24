"""
Kyoka 3.0 - UI Theme & Design Tokens
Aizen-inspired black, charcoal, and deep violet palette with refined iconography.
"""

from __future__ import annotations
import discord


class KyokaTheme:
    """Aizen Edition visual styling constants and color tokens."""

    # Primary Palette
    PRIMARY: int = 0x2B0938       # Aizen signature deep violet
    SECONDARY: int = 0x1A092A     # Charcoal violet
    ACCENT: int = 0x7C3AED        # Bright violet / psychic spiritual pressure
    HIGHLIGHT: int = 0x9333EA     # Indigo / purple shimmer

    # Semantic Status Colors
    SUCCESS: int = 0x10B981       # Emerald green
    WARNING: int = 0xF59E0B       # Amber gold
    ERROR: int = 0xEF4444         # Crimson / rose
    INFO: int = 0x6366F1          # Indigo blue
    MUTED: int = 0x27272A         # Zinc 800 dark border

    # Emojis & Iconography
    ICON_AIZEN: str = "🌀"
    ICON_SWORD: str = "🗡️"
    ICON_SUCCESS: str = "✅"
    ICON_ERROR: str = "❌"
    ICON_WARNING: str = "⚠️"
    ICON_INFO: str = "ℹ️"
    ICON_MUSIC: str = "🎵"
    ICON_TICKET: str = "🎫"
    ICON_SHIELD: str = "🛡️"
    ICON_SETTINGS: str = "⚙️"
    ICON_LOADING: str = "⏳"
    ICON_STAR: str = "⭐"
    ICON_ARROW_LEFT: str = "◀️"
    ICON_ARROW_RIGHT: str = "▶️"
    ICON_STOP: str = "🛑"

    # Default Branding Assets (safe fallback URLs)
    AIZEN_AVATAR_URL: str = "https://media.discordapp.net/attachments/1234567890/kyoka_aizen.png"
    AIZEN_BANNER_URL: str = "https://media.discordapp.net/attachments/1234567890/kyoka_banner.png"

    # Standard Footers
    FOOTER_TEXT: str = "KYOKA 3.0 • Aizen Edition"
    TICKET_FOOTER: str = "KYOKA Portal • Security & Transcripts Guaranteed"
    MUSIC_FOOTER: str = "KYOKA Audio Engine • Zero Loss Playback"

    @classmethod
    def get_color(cls, name: str = "primary") -> discord.Color:
        val = getattr(cls, name.upper(), cls.PRIMARY)
        return discord.Color(val)
