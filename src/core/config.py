from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _parse_application_id(value: str | int | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if len(value) > 20 or not value.isascii() or not value.isdecimal():
            return None
        value = int(value)
    if not isinstance(value, int) or not 0 < value <= 0xFFFFFFFFFFFFFFFF:
        return None
    return value


@dataclass(frozen=True)
class ThemeColors:
    """Standardized color palette for Kyoka cryptographic cyber theme."""
    PRIMARY: int = 0x7C3AED      # Aizen violet
    SUCCESS: int = 0xA78BFA      # Violet glow
    ERROR: int = 0xFF3366        # Laser Crimson
    WARNING: int = 0xFFB300      # Cyber Amber
    INFO: int = 0xC4B5FD         # Pale violet
    DARK: int = 0x0A0E14         # Deep Cyber Void
    SECONDARY: int = 0x5B21B6    # Deep violet
    ACCENT: int = 0xDDD6FE       # Aizen lavender


@dataclass(frozen=True)
class ThemeEmojis:
    """Standardized system emojis for Kyoka embeds."""
    SUCCESS: str = ""
    ERROR: str = ""
    WARNING: str = ""
    INFO: str = ""
    LOADING: str = ""
    SHIELD: str = ""
    SPARKLES: str = ""
    SETTINGS: str = ""
    PING: str = ""
    DATABASE: str = ""
    BOT: str = ""
    KYOKA: str = ""


class Config:
    """Bot global configuration."""
    
    # Discord Bot Token
    TOKEN: str = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TOKEN")
        or ""
    ).strip()
    CLIENT_ID: int | None = _parse_application_id(os.getenv("CLIENT_ID", "").strip())
    
    # Prefixes & Identity
    BOT_NAME: str = os.getenv("BOT_NAME", "KYOKA 3.0")
    DEFAULT_PREFIX: str = os.getenv("BOT_PREFIX", "?")
    
    # Environment & Dev Settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    DEV_GUILD_ID: int | None = (
        int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None
    )
    SYNC_COMMANDS_ON_STARTUP: bool = (
        os.getenv("SYNC_COMMANDS_ON_STARTUP", "false").lower() in ("true", "1", "yes")
    )
    
    # PostgreSQL / Supabase Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # Lavalink / Audio Settings
    LAVALINK_URI: str = os.getenv("LAVALINK_URI", "http://lava2.kasawa.pro:2334").strip()
    LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "youshallnotpass").strip()
    LAVALINK_FALLBACK_URIS: str = os.getenv("LAVALINK_FALLBACK_URIS", "").strip()
    LAVALINK_AUTO_DISCOVER: bool = os.getenv("LAVALINK_AUTO_DISCOVER", "1").lower() in ("1", "true", "yes")
    LAVALINK_PUBLIC_LIST_URL: str = os.getenv(
        "LAVALINK_PUBLIC_LIST_URL",
        "https://lavalink-list.ajieblogs.eu.org/All"
    ).strip()

    # Aesthetics
    COLORS: ThemeColors = ThemeColors()
    EMOJIS: ThemeEmojis = ThemeEmojis()
    
    # Bot Branding & Official Links
    VERSION: str = "3.0.0"
    FOOTER_TEXT: str = "Made by Aizen"
    INVITE_URL: str = os.getenv("INVITE_URL", "").strip()
    SUPPORT_URL: str = os.getenv("SUPPORT_URL", "https://discord.gg/5DBQTQJa9").strip()

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration values."""
        if not cls.TOKEN:
            raise ValueError(
                "DISCORD_TOKEN is missing! Please set your bot token in the .env file."
            )
        if not cls.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL is missing! Please set your Supabase connection string in the .env file."
            )


def get_invite_url(runtime_application_id: int | None = None) -> str | None:
    if Config.INVITE_URL:
        return Config.INVITE_URL

    application_id = _parse_application_id(runtime_application_id) or Config.CLIENT_ID
    if application_id is None:
        return None

    return (
        f"https://discord.com/oauth2/authorize?client_id={application_id}"
        "&permissions=8&integration_type=0&scope=applications.commands+bot"
    )
