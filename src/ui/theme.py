"""
Kyoka 3.0 - UI Theme & Design Tokens
Aizen-inspired black, charcoal, and deep violet palette with refined iconography.
"""

from __future__ import annotations
import discord


class KyokaTheme:
    """KYOKA: Eclipse Interface visual styling constants, color tokens, and layout guidelines."""

    # Eclipse Interface Surface & Atmosphere Palette
    ECLIPSE_BLACK: int = 0x101116     # Pure obsidian surface
    SURFACE_DARK: int = 0x181A22      # Charcoal violet backdrop
    DEEP_VIOLET: int = 0x20212B       # Midnight violet container
    PRIMARY: int = 0x252735           # Aizen signature deep violet (primary embed color)
    SECONDARY: int = 0x20232D         # Charcoal violet secondary
    ACCENT: int = 0x8878C7            # Electric purple spiritual pressure
    HIGHLIGHT: int = 0xA99BDF         # Indigo / purple shimmer
    ELECTRIC_PURPLE: int = 0x8878C7   # Vivid spiritual pressure
    BLADE_SILVER: int = 0xE2E8F0      # Silver-white typography
    MUTED_SLATE: int = 0x9296A5       # Subtitle & footer muted text

    # Semantic Status & Accent Colors
    SUCCESS: int = 0x10B981           # Emerald green for confirmed actions
    WARNING: int = 0xF59E0B           # Amber gold for alerts and cautionary notices
    ERROR: int = 0xEF4444             # Crimson rose for errors
    CRIMSON: int = 0xFF3366           # Laser crimson for warnings & destructive actions
    DANGER: int = 0xDC2626            # Deep danger red
    INFO: int = 0x06B6D4              # Cyber cyan telemetry and informational cards
    MUTED: int = 0x27272A             # Zinc 800 dark border

    # Emojis & Iconography
    ICON_AIZEN: str = "⛩️"
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
    ICON_FIRE: str = "🔥"
    ICON_SPARKLE: str = "✨"
    ICON_CROWN: str = "👑"
    ICON_DIAMOND: str = "💎"

    # Default Branding Assets (safe fallback URLs)
    AIZEN_AVATAR_URL: str = "https://media.discordapp.net/attachments/1234567890/kyoka_aizen.png"
    AIZEN_BANNER_URL: str = "https://media.discordapp.net/attachments/1234567890/kyoka_banner.png"

    # Standard Footers
    FOOTER_TEXT: str = "KYŌKA 3.0  •  ECLIPSE INTERFACE"
    TICKET_FOOTER: str = "KYOKA Portal • Security & Transcripts Guaranteed"
    MUSIC_FOOTER: str = "KYOKA Audio Engine • Zero Loss Playback"

    @classmethod
    def get_color(cls, name: str = "primary") -> discord.Color:
        val = getattr(cls, name.upper(), cls.PRIMARY)
        return discord.Color(val)

    @staticmethod
    def progress_bar(current: float, total: float, length: int = 10, fill: str = "▰", empty: str = "▱") -> str:
        """Render a sleek ASCII progress bar for audio duration or XP progression."""
        if total <= 0:
            return empty * length
        ratio = max(0.0, min(1.0, current / total))
        filled_count = int(round(ratio * length))
        return (fill * filled_count) + (empty * (length - filled_count))

    @staticmethod
    def format_badge(label: str, style: str = "primary") -> str:
        """Format a clean markdown pill badge."""
        return f"`[{label}]`"
