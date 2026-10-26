"""Configuration and environment management for the KYOKA 3.0 Dashboard API.

Reads environment variables safely and provides validation defaults.
Never exposes sensitive tokens or connection strings to clients.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

try:
    from dotenv import load_dotenv
    # Find .env in project root directory (one level up from dashboard_api)
    _root_dir = Path(__file__).resolve().parent.parent
    _env_path = _root_dir / ".env"
    if _env_path.is_file():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

logger = logging.getLogger("Kyoka.Dashboard.Config")


@dataclass(frozen=True)
class DashboardConfig:
    # Discord OAuth2
    client_id: str
    client_secret: str
    bot_token: str
    redirect_uri: str
    secret_key: str

    bot_invite_url: str = ""
    support_server_url: str = "https://discord.gg/7q4tn6dA6V"
    session_cookie_name: str = "kyoka_session"
    session_max_age_seconds: int = 86400 * 7  # 7 days
    state_max_age_seconds: int = 600  # 10 minutes
    is_production: bool = False
    frontend_origin: str = "*"

    # Database
    database_url: str = ""

    # Server binding
    host: str = "0.0.0.0"
    port: int = 8080

    # Rate Limiting
    rate_limit_per_minute: int = 60

    @property
    def allowed_origins(self) -> List[str]:
        """Return list of allowed frontend origins for CORS and OAuth redirects."""
        origins = [
            "https://aizen-bot.pages.dev",
            "https://kyoka-dashboard-website.onrender.com",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://localhost:5173",
        ]
        if self.frontend_origin and self.frontend_origin != "*":
            for part in self.frontend_origin.split(","):
                p = part.strip().rstrip("/")
                if p and p not in origins:
                    origins.append(p)
        return origins

    def is_origin_allowed(self, origin: str) -> bool:
        """Check if an incoming origin header is authorized for CORS credentials."""
        if not origin:
            return False
        if not self.is_production or self.frontend_origin == "*":
            return True
        norm = origin.strip().rstrip("/")
        if norm in self.allowed_origins:
            return True
        # Allow Cloudflare Pages deployments like https://*.aizen-bot.pages.dev or *.pages.dev
        if norm.endswith(".pages.dev") or norm.endswith(".onrender.com"):
            return True
        return False

    @property
    def primary_frontend_url(self) -> str:
        """Return primary frontend root URL to redirect users after OAuth authorization."""
        if self.is_production:
            return "https://aizen-bot.pages.dev"
        if self.frontend_origin and self.frontend_origin != "*":
            first = self.frontend_origin.split(",")[0].strip().rstrip("/")
            if first and not first.endswith(".onrender.com"):
                return first
        return "https://aizen-bot.pages.dev" if self.is_production else "http://localhost:8080"

    def get_missing_oauth_vars(self) -> List[str]:
        """Return list of missing required environment variable names for Discord OAuth2."""
        missing = []
        if not self.client_id:
            missing.append("DISCORD_CLIENT_ID")
        if not self.client_secret:
            missing.append("DISCORD_CLIENT_SECRET")
        return missing

    @property
    def is_oauth_configured(self) -> bool:
        """True if both client_id and client_secret are non-empty."""
        return bool(self.client_id and self.client_secret)

    @classmethod
    def from_env(cls) -> DashboardConfig:
        env = os.environ.get("ENVIRONMENT", "development").lower()
        is_prod = env == "production"

        # Secret key: canonical DASHBOARD_SECRET_KEY, fallback SECRET_KEY
        secret_key = os.environ.get("DASHBOARD_SECRET_KEY") or os.environ.get("SECRET_KEY")
        if not secret_key:
            # Deterministic development fallback or DISCORD_TOKEN
            secret_key = os.environ.get("DISCORD_TOKEN", "kyoka_default_dev_secret_key_32_bytes_long_minimum")

        # Canonical DISCORD_CLIENT_ID, fallback CLIENT_ID
        client_id = (os.environ.get("DISCORD_CLIENT_ID") or os.environ.get("CLIENT_ID") or "1562505487214321714").strip()
        # Canonical DISCORD_CLIENT_SECRET, fallback CLIENT_SECRET
        client_secret = (os.environ.get("DISCORD_CLIENT_SECRET") or os.environ.get("CLIENT_SECRET") or "").strip()
        raw_bot_token = (
            os.environ.get("DISCORD_TOKEN")
            or os.environ.get("BOT_TOKEN")
            or os.environ.get("TOKEN")
            or ""
        ).strip()
        bot_token = raw_bot_token[4:].strip() if raw_bot_token.lower().startswith("bot ") else raw_bot_token

        # Canonical DISCORD_REDIRECT_URI, fallback REDIRECT_URI
        default_redirect = "https://aizen-bot.pages.dev/api/auth/callback" if is_prod else "http://localhost:8080/api/auth/callback"
        redirect_uri = (
            os.environ.get("DISCORD_REDIRECT_URI")
            or os.environ.get("REDIRECT_URI")
            or default_redirect
        ).strip()

        invite_url = os.environ.get(
            "INVITE_URL",
            f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&scope=bot%20applications.commands" if client_id else ""
        )
        support_url = os.environ.get("SUPPORT_URL", "https://discord.gg/7q4tn6dA6V")

        frontend_origin = os.environ.get("FRONTEND_ORIGIN", "https://aizen-bot.pages.dev,https://kyoka-dashboard-website.onrender.com" if is_prod else "*")
        database_url = os.environ.get("DATABASE_URL", "").strip()

        host = os.environ.get("HOST", "0.0.0.0")
        try:
            port = int(os.environ.get("PORT", "8080"))
        except ValueError:
            port = 8080

        cfg = cls(
            client_id=client_id,
            client_secret=client_secret,
            bot_token=bot_token,
            redirect_uri=redirect_uri,
            bot_invite_url=invite_url,
            support_server_url=support_url,
            secret_key=secret_key,
            is_production=is_prod,
            frontend_origin=frontend_origin,
            database_url=database_url,
            host=host,
            port=port,
        )

        missing_oauth = cfg.get_missing_oauth_vars()
        if missing_oauth:
            logger.warning(
                f"Discord OAuth2 credentials not fully configured. Missing: {', '.join(missing_oauth)}. "
                "Discord login will return an informative error until configured in .env."
            )
        else:
            logger.info("Discord OAuth2 configuration validated successfully.")

        return cfg
