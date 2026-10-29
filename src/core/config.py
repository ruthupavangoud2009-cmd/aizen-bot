from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root with override=True
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)


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


def _clean_proxy_url(value: str | None) -> str | None:
    """Sanitize proxy string even if pasted as a full curl command or quoted string."""
    if not value:
        return None
    val = value.strip()
    import re
    match = re.search(r'(https?://[^\s"\'<>]+)', val)
    if match:
        return match.group(1).rstrip('/')
    return val or None


def parse_proxy_pool(raw: str | None) -> list[str]:
    """Parse comma, semicolon, or newline-separated proxy URLs into unique clean URLs."""
    if not raw or raw.strip().lower() in ("none", "direct", "off", "disabled", "false"):
        return []
    import re
    tokens = re.split(r'[,;\n\r]+', raw.strip())
    results: list[str] = []
    for t in tokens:
        cleaned = _clean_proxy_url(t)
        if cleaned and cleaned not in results:
            results.append(cleaned)
    return results


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


@dataclass(frozen=True)
class AizenAssets:
    """Configurable asset registry for Kyoka x Aizen aesthetic visual elements."""
    BANNER_URL: str = os.getenv(
        "KYOKA_BANNER_URL",
        os.getenv("AIZEN_IMAGE_URL", "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif")
    ).strip()
    HELP_BANNER_URL: str = os.getenv(
        "KYOKA_HELP_BANNER_URL",
        os.getenv(
            "KYOKA_BANNER_URL",
            os.getenv("AIZEN_IMAGE_URL", "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif")
        )
    ).strip()
    HELP_GIF_URL: str = os.getenv("KYOKA_HELP_GIF_URL", "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif").strip()
    WELCOME_IMAGE_URL: str = os.getenv("KYOKA_WELCOME_IMAGE_URL", "").strip()
    LEVELUP_IMAGE_URL: str = os.getenv("KYOKA_LEVELUP_IMAGE_URL", "").strip()
    DEFAULT_THUMBNAIL_URL: str = os.getenv("KYOKA_DEFAULT_THUMBNAIL_URL", "").strip()
    AIZEN_AVATAR_URL: str = os.getenv("AIZEN_AVATAR_URL", os.getenv("AIZEN_IMAGE_URL", "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif")).strip()



class Config:
    """Bot global configuration."""
    
    # Visual Assets & Themes
    ASSETS: AizenAssets = AizenAssets()
    AIZEN_IMAGE_URL: str = os.getenv("AIZEN_IMAGE_URL", "").strip()
    
    # Discord Bot Token
    TOKEN: str = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TOKEN")
        or ""
    ).strip()
    CLIENT_ID: int | None = _parse_application_id(os.getenv("CLIENT_ID", "").strip())
    VOICE_WELCOME_BOT_TOKEN: str | None = os.getenv("VOICE_WELCOME_BOT_TOKEN", "").strip() or None
    
    # Prefixes & Identity
    BOT_NAME: str = os.getenv("BOT_NAME", "KYOKA 3.0")
    DEFAULT_PREFIX: str = os.getenv("BOT_PREFIX", "+")
    
    # Environment & Dev Settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    DEV_GUILD_ID: int | None = (
        int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None
    )
    SYNC_COMMANDS_ON_STARTUP: bool = (
        os.getenv("SYNC_COMMANDS_ON_STARTUP", "true").lower() in ("true", "1", "yes")
    )
    
    # PostgreSQL / Supabase Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # Default verified Webshare datacenter proxy for emergency 429 bypass only
    DEFAULT_BACKUP_PROXY: str = "http://wovozhfw:cfnxdvq5iyyi@64.137.10.153:5803"

    # Proxy Configuration (Direct connection is primary for 10-30ms ping; proxy is failover only)
    DISCORD_PROXY: str | None = _clean_proxy_url(os.getenv("DISCORD_PROXY"))
    DISCORD_PROXY_POOL: list[str] = parse_proxy_pool(
        os.getenv("DISCORD_PROXY_POOL") or os.getenv("DISCORD_PROXY") or ""
    )

    @classmethod
    def get_proxy_pool(cls) -> list[str]:
        """Return list of configured proxies for gateway failover & rotation."""
        pool = parse_proxy_pool(os.getenv("DISCORD_PROXY_POOL") or os.getenv("DISCORD_PROXY") or "")
        # Provide emergency backup proxy as failover route if direct connection gets blocked
        if not pool and cls.DEFAULT_BACKUP_PROXY:
            pool = [cls.DEFAULT_BACKUP_PROXY]
        return pool

    # Lavalink / Audio Settings
    LAVALINK_URI: str = os.getenv("LAVALINK_URI", "https://lavalink.nazha.online:443").strip()
    LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "nazhafreelava").strip()
    LAVALINK_FALLBACK_URIS: str = os.getenv(
        "LAVALINK_FALLBACK_URIS",
        "https://lavalink.jirayu.net:443|youshallnotpass,"
        "http://lavalink.jirayu.net:13592|youshallnotpass,"
        "https://lava-v4.millohost.my.id:443|https://discord.gg/mjS5J2K3ep,"
        "http://lava2.kasawa.pro:2334|youshallnotpass,"
        "https://lavalinkv4.serenetia.com:443|https://seretia.link/discord"
    ).strip()
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
    SUPPORT_URL: str = os.getenv("SUPPORT_URL", "https://discord.gg/7q4tn6dA6V").strip()

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
