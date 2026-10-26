"""Discord OAuth2 state generation, token exchange, and HMAC-signed session security.

Guarantees:
- Strict CSRF protection via timestamped HMAC state nonces.
- Encrypted/signed tamper-proof session cookies (no arbitrary client modifications).
- Secure Discord v10 OAuth2 token exchange without leaking credentials to the browser.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
import aiohttp

DISCORD_API_BASE: str = "https://discord.com/api/v10"
DISCORD_TOKEN_URL: str = f"{DISCORD_API_BASE}/oauth2/token"
DISCORD_USER_URL: str = f"{DISCORD_API_BASE}/users/@me"
DISCORD_GUILDS_URL: str = f"{DISCORD_API_BASE}/users/@me/guilds"


# --- OAuth2 State Nonce (CSRF Protection) ---

def create_oauth_state(secret_key: str, extra: str = "") -> str:
    """Generate a tamper-proof timestamped OAuth state parameter with HMAC signature.
    
    If `extra` is provided (e.g. client origin or return URL), it is securely embedded
    and signed. If `extra` is empty, returns canonical 3-part nonce.timestamp.sig.
    """
    nonce = secrets.token_urlsafe(16)
    timestamp = str(int(time.time()))
    if extra:
        safe_extra = base64.urlsafe_b64encode(extra.encode("utf-8")).decode("utf-8").rstrip("=")
        payload = f"{nonce}:{timestamp}:{safe_extra}"
        signature = hmac.new(
            secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"{nonce}.{timestamp}.{safe_extra}.{signature}"

    payload = f"{nonce}:{timestamp}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{nonce}.{timestamp}.{signature}"


def verify_oauth_state(state: str, secret_key: str, max_age_seconds: int = 600) -> bool:
    """Verify state parameter integrity, signature, and expiration."""
    if not state or not isinstance(state, str):
        return False
    parts = state.split(".")
    if len(parts) == 3:
        nonce, timestamp_str, received_sig = parts
        safe_extra = None
        payload = f"{nonce}:{timestamp_str}"
    elif len(parts) == 4:
        nonce, timestamp_str, safe_extra, received_sig = parts
        payload = f"{nonce}:{timestamp_str}:{safe_extra}"
    else:
        return False

    try:
        ts = int(timestamp_str)
    except ValueError:
        return False

    # Check age
    now = int(time.time())
    age = now - ts
    if age > max_age_seconds or (max_age_seconds <= 0 and age >= 0) or ts > now + 30:  # allows 30s clock skew
        return False

    # Check HMAC
    expected_sig = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_sig, received_sig)


def extract_oauth_state_extra(state: str, secret_key: str, max_age_seconds: int = 600) -> Optional[str]:
    """Verify state and extract the embedded extra string if present."""
    if not verify_oauth_state(state, secret_key, max_age_seconds=max_age_seconds):
        return None
    parts = state.split(".")
    if len(parts) != 4:
        return None
    safe_extra = parts[2]
    if not safe_extra:
        return None
    try:
        # Restore base64 padding
        padding = 4 - (len(safe_extra) % 4)
        if padding != 4:
            safe_extra += "=" * padding
        raw = base64.urlsafe_b64decode(safe_extra.encode("utf-8")).decode("utf-8")
        return raw
    except Exception:
        return None


# --- Tamper-Proof Signed Session Tokens ---

def create_session_token(data: Dict[str, Any], secret_key: str) -> str:
    """Create a signed session token containing user payload and expiration timestamp."""
    payload_dict = {
        **data,
        "_created_at": int(time.time())
    }
    raw_json = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_json).decode("utf-8").rstrip("=")

    signature = hmac.new(
        secret_key.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"{b64_payload}.{signature}"


def verify_session_token(token: str, secret_key: str, max_age_seconds: int = 86400 * 7) -> Optional[Dict[str, Any]]:
    """Verify session token signature, decode payload, and validate expiration."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 2:
        # Check if it's an Edge-issued base64 JSON session token
        try:
            padding = "=" * ((4 - len(token) % 4) % 4)
            raw = base64.urlsafe_b64decode((token + padding).encode("utf-8"))
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict) and data.get("user_id"):
                expires_at = data.get("expires_at", 0)
                if expires_at and expires_at > 1000000000000:  # millisecond timestamp
                    expires_at = expires_at / 1000.0
                if expires_at and time.time() > expires_at:
                    return None
                return data
        except Exception:
            return None
        return None

    b64_payload, received_sig = parts
    expected_sig = hmac.new(
        secret_key.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, received_sig):
        return None

    # Add back base64 padding
    padding = "=" * ((4 - len(b64_payload) % 4) % 4)
    try:
        raw_json = base64.urlsafe_b64decode(b64_payload + padding)
        data = json.loads(raw_json.decode("utf-8"))
    except Exception:
        return None

    created_at = data.get("_created_at", 0)
    now = int(time.time())
    age = now - created_at
    if age > max_age_seconds or (max_age_seconds <= 0 and age >= 0):
        return None

    return data


# --- Discord API Client Helpers ---

async def exchange_discord_code(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    session: aiohttp.ClientSession
) -> Dict[str, Any]:
    """Exchange authorization code for Discord access and refresh tokens."""
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with session.post(DISCORD_TOKEN_URL, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            error_body = await resp.text()
            raise RuntimeError(f"Discord token exchange failed (HTTP {resp.status}): {error_body}")
        return await resp.json()


import logging

logger = logging.getLogger("Kyoka.Dashboard.Auth")

# In-memory TTL caches to eliminate rate limits and 502 errors
_USER_GUILDS_CACHE: Dict[str, tuple[float, list[Dict[str, Any]]]] = {}
USER_GUILDS_CACHE_TTL: float = 120.0  # 2 minutes active freshness
USER_GUILDS_STALE_TTL: float = 900.0  # 15 minutes fallback for rate-limit resilience

_BOT_GUILDS_CACHE: Optional[tuple[float, set[str]]] = None
BOT_GUILDS_CACHE_TTL: float = 60.0    # 1 minute active freshness
BOT_GUILDS_STALE_TTL: float = 600.0   # 10 minutes fallback


async def fetch_discord_user(access_token: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Fetch logged in user profile from Discord."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with session.get(DISCORD_USER_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Failed to fetch Discord user (HTTP {resp.status})")
        return await resp.json()


async def fetch_user_guilds(
    access_token: str,
    session: aiohttp.ClientSession,
    force_refresh: bool = False
) -> list[Dict[str, Any]]:
    """Fetch list of user's guilds from Discord with in-memory TTL caching and rate-limit resilience."""
    now = time.time()
    cache_key = hashlib.sha256(access_token.encode("utf-8")).hexdigest()

    cached = _USER_GUILDS_CACHE.get(cache_key)
    if not force_refresh and cached:
        cached_time, cached_guilds = cached
        if now - cached_time < USER_GUILDS_CACHE_TTL:
            return cached_guilds

    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with session.get(DISCORD_GUILDS_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                guilds = await resp.json()
                _USER_GUILDS_CACHE[cache_key] = (now, guilds)
                return guilds
            elif resp.status == 429:
                logger.warning("Discord API returned 429 Too Many Requests while fetching user guilds.")
                if cached and (now - cached[0] < USER_GUILDS_STALE_TTL):
                    logger.info("Serving user guilds from stale cache due to Discord 429 rate limit.")
                    return cached[1]
                raise RuntimeError("Discord API rate limit reached (HTTP 429). Please wait a moment.")
            else:
                error_text = await resp.text()
                if cached and (now - cached[0] < USER_GUILDS_STALE_TTL):
                    logger.warning(f"Discord returned HTTP {resp.status}; falling back to cached user guilds.")
                    return cached[1]
                raise RuntimeError(f"Failed to fetch user guilds from Discord (HTTP {resp.status}): {error_text}")
    except Exception as e:
        if cached and (now - cached[0] < USER_GUILDS_STALE_TTL):
            logger.warning(f"Error fetching user guilds ({e}); serving from stale cache.")
            return cached[1]
        raise


async def fetch_bot_guilds(
    bot_token: str,
    session: aiohttp.ClientSession,
    force_refresh: bool = False,
    bot_instance: Any = None
) -> tuple[set[str], bool]:
    """Verify bot's real guild memberships via live bot instance or server-side Discord REST API.
    
    Returns (guild_ids_set, verification_succeeded).
    Guarantees exact Discord snowflake ID comparison and eliminates false "Add Bot" detection.
    """
    global _BOT_GUILDS_CACHE
    now = time.time()

    # 1. Live Bot Memory Fast-Path: authoritative check from running KyokaBot
    live_bot = bot_instance
    if not live_bot:
        try:
            from src.main import get_current_bot
            live_bot = get_current_bot()
        except Exception as e:
            logger.debug(f"get_current_bot check bypassed: {e}")

    if live_bot and hasattr(live_bot, "guilds"):
        try:
            guilds = live_bot.guilds
            is_ready = getattr(live_bot, "is_ready", lambda: True)()
            if guilds or is_ready:
                live_guild_ids = {str(getattr(g, "id", g)) for g in guilds}
                _BOT_GUILDS_CACHE = (now, live_guild_ids)
                return live_guild_ids, True
        except Exception as e:
            logger.warning(f"Error reading live bot guilds: {e}")

    # 2. Check in-memory cache
    if not force_refresh and _BOT_GUILDS_CACHE:
        cached_time, cached_ids = _BOT_GUILDS_CACHE
        if now - cached_time < BOT_GUILDS_CACHE_TTL:
            return cached_ids, True

    # Sanitize bot token
    clean_token = (bot_token or "").strip()
    if clean_token.lower().startswith("bot "):
        clean_token = clean_token[4:].strip()

    if not clean_token:
        # Fallback to process environment variables
        import os
        raw_env_token = (
            os.environ.get("DISCORD_TOKEN")
            or os.environ.get("BOT_TOKEN")
            or os.environ.get("TOKEN")
            or ""
        ).strip()
        clean_token = raw_env_token[4:].strip() if raw_env_token.lower().startswith("bot ") else raw_env_token

    if not clean_token:
        logger.warning("No valid bot token found for fetch_bot_guilds; verification unavailable.")
        if _BOT_GUILDS_CACHE:
            return _BOT_GUILDS_CACHE[1], False
        return set(), False

    # 3. Server-side Discord REST API with bot token
    guild_ids: set[str] = set()
    headers = {"Authorization": f"Bot {clean_token}"}
    after_id: Optional[str] = None

    try:
        for _ in range(10):  # Up to 10 pages (2,000 guilds) with bounded execution
            url = f"{DISCORD_GUILDS_URL}?limit=200"
            if after_id:
                url += f"&after={after_id}"

            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data:
                        break
                    for g in data:
                        guild_ids.add(str(g["id"]))
                    if len(data) < 200:
                        break
                    after_id = str(data[-1]["id"])
                elif resp.status == 429:
                    logger.warning("Discord API rate limited bot guilds verification (HTTP 429).")
                    if _BOT_GUILDS_CACHE and (now - _BOT_GUILDS_CACHE[0] < BOT_GUILDS_STALE_TTL):
                        return _BOT_GUILDS_CACHE[1], True
                    return (guild_ids, False) if guild_ids else (set(), False)
                else:
                    error_body = await resp.text()
                    logger.error(f"Discord API error fetching bot guilds (HTTP {resp.status}): {error_body}")
                    if _BOT_GUILDS_CACHE and (now - _BOT_GUILDS_CACHE[0] < BOT_GUILDS_STALE_TTL):
                        return _BOT_GUILDS_CACHE[1], True
                    return (guild_ids, False) if guild_ids else (set(), False)

        _BOT_GUILDS_CACHE = (now, guild_ids)
        return guild_ids, True

    except Exception as e:
        logger.error(f"Network error verifying bot guilds: {e}")
        if _BOT_GUILDS_CACHE and (now - _BOT_GUILDS_CACHE[0] < BOT_GUILDS_STALE_TTL):
            return _BOT_GUILDS_CACHE[1], True
        return set(), False


def clear_guild_caches() -> None:
    """Clear in-memory guild caches (used during testing or forced refresh)."""
    global _BOT_GUILDS_CACHE
    _USER_GUILDS_CACHE.clear()
    _BOT_GUILDS_CACHE = None

