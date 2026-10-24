"""
Kyoka 3.0 - Image Assets Registry
Maintains centralized URLs and fallback assets for Aizen-themed embeds, tickets, and banners.
"""

from __future__ import annotations
import os


class ImageAssets:
    """Configured and safe fallback image asset URLs."""

    # Default URLs (can be overridden via environment variables)
    AIZEN_PORTRAIT: str = os.getenv(
        "KYOKA_ASSET_AIZEN_PORTRAIT",
        "https://cdn.discordapp.com/emojis/1045239561234120764.webp?size=128&quality=lossless",
    )

    AIZEN_BANNER: str = os.getenv(
        "KYOKA_ASSET_AIZEN_BANNER",
        "https://media.discordapp.net/attachments/1234567890/kyoka_aizen_banner.png",
    )

    TICKET_BANNER: str = os.getenv(
        "KYOKA_ASSET_TICKET_BANNER",
        "https://media.discordapp.net/attachments/1234567890/ticket_banner.png",
    )

    MUSIC_DISK_GIF: str = os.getenv(
        "KYOKA_ASSET_MUSIC_GIF",
        "https://cdn.discordapp.com/emojis/1045239561234120765.gif?size=64&quality=lossless",
    )

    SHIELD_ICON: str = os.getenv(
        "KYOKA_ASSET_SHIELD_ICON",
        "https://cdn.discordapp.com/emojis/1045239561234120766.webp?size=64&quality=lossless",
    )

    @classmethod
    def get_asset(cls, key: str, fallback: str = "") -> str:
        """Fetch asset by key or return fallback."""
        return getattr(cls, key.upper(), fallback)
