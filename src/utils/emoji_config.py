"""
KYOKA — Global Custom Emoji Configuration & `emojis_gpt/` Catalog Loader.

Single source of truth for:
1. Uploaded Discord custom emoji IDs (static and animated).
   Replace placeholder ``EMOJI_ID`` values below once the PNG/GIF assets in
   ``emojis_gpt/`` are uploaded to Discord. Placeholder strings are NEVER emitted;
   unconfigured entries automatically fall back to runtime Application/Guild emojis,
   static equivalents, or clean Unicode/manifest fallbacks.
2. The 60 extra concept entries from ``emojis_gpt/extra_emoji_manifest.json``.
3. Category organization, candidate names, and Discord-safe fallbacks.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("Kyoka.EmojiConfig")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MANIFEST_PATH = _REPO_ROOT / "emojis_gpt" / "extra_emoji_manifest.json"

# Strict Discord custom emoji format: <:name:12345678901234567> or <a:name:12345678901234567>
_VALID_CUSTOM_EMOJI_RE = re.compile(r"^<(a?):([a-zA-Z0-9_]{2,32}):(\d{15,22})>$")
_PLACEHOLDER_MARKERS = ("EMOJI_ID", "YOUR_EMOJI_ID", "PLACEHOLDER", "<ID>")


# ─────────────────────────────────────────────────────────────────────────────
# 1. CENTRAL DISCORD CUSTOM EMOJI ID CONFIGURATION (INSERT YOUR UPLOADED IDS HERE)
# ─────────────────────────────────────────────────────────────────────────────
# Keep placeholder format `<:kyoka_<name>:EMOJI_ID>` or `<a:kyoka_<name>:EMOJI_ID>`
# until you upload each asset to Discord. Simply replace `EMOJI_ID` with the real
# snowflake ID (e.g. "1234567890123456789") — no cog edits needed.

KYOKA_CUSTOM_EMOJI_IDS: dict[str, str] = {
    # ── Branding & Identity ──
    "KYOKA": "<:kyoka_brand:EMOJI_ID>",
    "BRAND": "<:kyoka_brand:EMOJI_ID>",
    "SPARKLE": "<a:kyoka_sparkle:EMOJI_ID>",
    "HEART": "<a:kyoka_heart:EMOJI_ID>",
    "ARROW": "<:kyoka_arrow:EMOJI_ID>",

    # ── Status & Feedback (Animated reserved subtly for loading & key feedback) ──
    "SUCCESS": "<:kyoka_success:EMOJI_ID>",
    "SUCCESS_ANIM": "<a:kyoka_success_glow:EMOJI_ID>",
    "APPROVE": "<:kyoka_approve:EMOJI_ID>",
    "ERROR": "<:kyoka_error:EMOJI_ID>",
    "DENY": "<:kyoka_deny:EMOJI_ID>",
    "WARNING": "<:kyoka_warning:EMOJI_ID>",
    "WARNING_ALT": "<:kyoka_warning_alt:EMOJI_ID>",
    "LOADING": "<a:kyoka_loading:EMOJI_ID>",
    "PROGRESS": "<a:kyoka_progress:EMOJI_ID>",
    "SYNC": "<a:kyoka_sync:EMOJI_ID>",
    "REFRESH": "<:kyoka_refresh:EMOJI_ID>",
    "ONLINE": "<:kyoka_online:EMOJI_ID>",
    "OFFLINE": "<:kyoka_offline:EMOJI_ID>",
    "IDLE": "<:kyoka_idle:EMOJI_ID>",
    "BOT_STATUS": "<a:kyoka_bot_status:EMOJI_ID>",

    # ── Navigation & Help UI ──
    "HOME": "<:kyoka_home:EMOJI_ID>",
    "BACK": "<:kyoka_back:EMOJI_ID>",
    "NEXT": "<:kyoka_next:EMOJI_ID>",
    "SEARCH": "<:kyoka_search:EMOJI_ID>",
    "HELP": "<:kyoka_help:EMOJI_ID>",
    "BOOK": "<:kyoka_book:EMOJI_ID>",
    "MODULES": "<:kyoka_modules:EMOJI_ID>",
    "TERMINAL": "<:kyoka_terminal:EMOJI_ID>",
    "BRACKETS": "<:kyoka_brackets:EMOJI_ID>",
    "STACK": "<:kyoka_stack:EMOJI_ID>",
    "PIN": "<:kyoka_pin:EMOJI_ID>",
    "LOCATION": "<:kyoka_location:EMOJI_ID>",
    "FILTER": "<:kyoka_filter:EMOJI_ID>",
    "SORT": "<:kyoka_sort:EMOJI_ID>",

    # ── Moderation & Security / Anti-Nuke ──
    "MODERATION": "<:kyoka_moderation:EMOJI_ID>",
    "BAN": "<:kyoka_ban:EMOJI_ID>",
    "KICK": "<:kyoka_kick:EMOJI_ID>",
    "MUTE": "<:kyoka_mute:EMOJI_ID>",
    "MUTE_ALT": "<:kyoka_mute_alt:EMOJI_ID>",
    "UNMUTE": "<:kyoka_unmute:EMOJI_ID>",
    "WARN": "<:kyoka_warn:EMOJI_ID>",
    "PURGE": "<:kyoka_purge:EMOJI_ID>",
    "DELETE": "<:kyoka_delete:EMOJI_ID>",
    "EDIT": "<:kyoka_edit:EMOJI_ID>",
    "LOCK": "<:kyoka_lock:EMOJI_ID>",
    "UNLOCK": "<:kyoka_unlock:EMOJI_ID>",
    "SECURITY": "<:kyoka_security:EMOJI_ID>",
    "ANTI_NUKE": "<a:kyoka_antinuke:EMOJI_ID>",
    "SHIELD_ALT": "<:kyoka_shield_alt:EMOJI_ID>",
    "FIREWALL": "<:kyoka_firewall:EMOJI_ID>",
    "SCAN": "<:kyoka_scan:EMOJI_ID>",
    "VERIFICATION": "<:kyoka_verification:EMOJI_ID>",
    "VERIFIED_ALT": "<:kyoka_verified_alt:EMOJI_ID>",
    "APPEAL": "<:kyoka_appeal:EMOJI_ID>",
    "REPORT": "<:kyoka_report:EMOJI_ID>",
    "BACKUP": "<:kyoka_backup:EMOJI_ID>",
    "RESTORE": "<:kyoka_restore:EMOJI_ID>",

    # ── Tickets & Support ──
    "TICKET": "<:kyoka_ticket:EMOJI_ID>",
    "TICKET_OPEN": "<:kyoka_ticket_open:EMOJI_ID>",
    "TICKET_CLOSE": "<:kyoka_ticket_close:EMOJI_ID>",
    "TICKET_CLAIM": "<:kyoka_ticket_claim:EMOJI_ID>",
    "TICKET_UNCLAIM": "<:kyoka_ticket_unclaim:EMOJI_ID>",
    "TRANSCRIPT": "<:kyoka_transcript:EMOJI_ID>",
    "STAFF": "<:kyoka_staff:EMOJI_ID>",

    # ── Music & Voice ──
    "MUSIC": "<a:kyoka_music:EMOJI_ID>",
    "PLAY": "<:kyoka_play:EMOJI_ID>",
    "PAUSE": "<:kyoka_pause:EMOJI_ID>",
    "RESUME": "<:kyoka_resume:EMOJI_ID>",
    "STOP": "<:kyoka_stop:EMOJI_ID>",
    "SKIP": "<:kyoka_skip:EMOJI_ID>",
    "PREVIOUS": "<:kyoka_previous:EMOJI_ID>",
    "QUEUE": "<:kyoka_queue:EMOJI_ID>",
    "VOLUME": "<:kyoka_volume:EMOJI_ID>",
    "VOLUME_UP": "<:kyoka_volume_up:EMOJI_ID>",
    "VOLUME_DOWN": "<:kyoka_volume_down:EMOJI_ID>",
    "LYRICS": "<:kyoka_lyrics:EMOJI_ID>",
    "LOOP": "<:kyoka_loop:EMOJI_ID>",
    "SHUFFLE": "<:kyoka_shuffle:EMOJI_ID>",
    "SOUND": "<:kyoka_sound:EMOJI_ID>",
    "RECORD": "<:kyoka_record:EMOJI_ID>",
    "VOICE": "<:kyoka_voice:EMOJI_ID>",
    "STAGE": "<:kyoka_stage:EMOJI_ID>",
    "VOICE_JOIN": "<:kyoka_voice_join:EMOJI_ID>",
    "VOICE_LEAVE": "<:kyoka_voice_leave:EMOJI_ID>",

    # ── Economy, Casino & Commerce ──
    "ECONOMY": "<:kyoka_economy:EMOJI_ID>",
    "BALANCE": "<:kyoka_balance:EMOJI_ID>",
    "WALLET": "<:kyoka_wallet:EMOJI_ID>",
    "COINS": "<a:kyoka_coins:EMOJI_ID>",
    "SHOP": "<:kyoka_shop:EMOJI_ID>",
    "INVENTORY": "<:kyoka_inventory:EMOJI_ID>",
    "REWARDS": "<:kyoka_rewards:EMOJI_ID>",
    "DAILY": "<:kyoka_daily:EMOJI_ID>",
    "LEADERBOARD": "<:kyoka_leaderboard:EMOJI_ID>",
    "TRANSACTIONS": "<:kyoka_transactions:EMOJI_ID>",
    "PURCHASES": "<:kyoka_purchases:EMOJI_ID>",
    "CASINO": "<:kyoka_casino:EMOJI_ID>",
    "GAMES": "<:kyoka_games:EMOJI_ID>",

    # ── Levels, XP, Reputation & Social ──
    "LEVEL": "<:kyoka_level:EMOJI_ID>",
    "XP": "<:kyoka_xp:EMOJI_ID>",
    "RANK": "<:kyoka_rank:EMOJI_ID>",
    "MEDAL": "<:kyoka_medal:EMOJI_ID>",
    "PROFILE": "<:kyoka_profile:EMOJI_ID>",
    "VOUCH": "<:kyoka_vouch:EMOJI_ID>",
    "REPUTATION": "<:kyoka_reputation:EMOJI_ID>",
    "SOCIAL": "<:kyoka_social:EMOJI_ID>",
    "STARRED": "<:kyoka_starred:EMOJI_ID>",
    "FAVORITE": "<:kyoka_favorite:EMOJI_ID>",
    "PARTY": "<:kyoka_party:EMOJI_ID>",
    "GIFTBOX": "<:kyoka_giftbox:EMOJI_ID>",
    "GIVEAWAY": "<:kyoka_giveaway:EMOJI_ID>",
    "TARGET": "<:kyoka_target:EMOJI_ID>",

    # ── Artificial Intelligence ──
    "AI": "<:kyoka_ai:EMOJI_ID>",
    "AI_LOADING": "<a:kyoka_ai_loading:EMOJI_ID>",
    "AI_VOICE": "<:kyoka_ai_voice:EMOJI_ID>",
    "AI_PERSONALITY": "<:kyoka_ai_personality:EMOJI_ID>",

    # ── Server Management & Administration ──
    "ADMIN": "<:kyoka_admin:EMOJI_ID>",
    "SERVER": "<:kyoka_server:EMOJI_ID>",
    "MEMBER": "<:kyoka_member:EMOJI_ID>",
    "MEMBERS": "<:kyoka_members:EMOJI_ID>",
    "ROLE": "<:kyoka_role:EMOJI_ID>",
    "CHANNEL": "<:kyoka_channel:EMOJI_ID>",
    "SETTINGS": "<:kyoka_settings:EMOJI_ID>",
    "LOGGING": "<:kyoka_logging:EMOJI_ID>",
    "WELCOMER": "<:kyoka_welcomer:EMOJI_ID>",
    "BOOST": "<:kyoka_boost:EMOJI_ID>",
    "BROADCAST": "<:kyoka_broadcast:EMOJI_ID>",
    "BELL_ALT": "<:kyoka_bell_alt:EMOJI_ID>",
    "MESSAGE_ALT": "<:kyoka_message_alt:EMOJI_ID>",

    # ── Utilities & Diagnostics ──
    "UTILITY": "<:kyoka_utility:EMOJI_ID>",
    "AFK": "<:kyoka_afk:EMOJI_ID>",
    "REMINDER": "<:kyoka_reminder:EMOJI_ID>",
    "TIME": "<:kyoka_time:EMOJI_ID>",
    "TIMER": "<:kyoka_timer:EMOJI_ID>",
    "DATE": "<:kyoka_date:EMOJI_ID>",
    "INFO": "<:kyoka_info:EMOJI_ID>",
    "STATS": "<:kyoka_stats:EMOJI_ID>",
    "PING": "<:kyoka_ping:EMOJI_ID>",
    "API": "<:kyoka_api:EMOJI_ID>",
    "DATABASE": "<:kyoka_database:EMOJI_ID>",
    "WEBHOOK": "<:kyoka_webhook:EMOJI_ID>",
    "CLOUD": "<:kyoka_cloud:EMOJI_ID>",
    "NETWORK": "<:kyoka_network:EMOJI_ID>",
    "STORAGE": "<:kyoka_storage:EMOJI_ID>",
    "SAVE": "<:kyoka_save:EMOJI_ID>",
    "MEDIA": "<:kyoka_media:EMOJI_ID>",

    # ── Owner, Developer & Premium ──
    "OWNER": "<:kyoka_owner:EMOJI_ID>",
    "DEVELOPER": "<:kyoka_developer:EMOJI_ID>",
    "DIAGNOSTICS": "<:kyoka_diagnostics:EMOJI_ID>",
    "MAINTENANCE": "<:kyoka_maintenance:EMOJI_ID>",
    "BUG": "<:kyoka_bug:EMOJI_ID>",
    "RELOAD": "<:kyoka_reload:EMOJI_ID>",
    "PREMIUM": "<a:kyoka_premium:EMOJI_ID>",
    "BADGE_ALT": "<:kyoka_badge_alt:EMOJI_ID>",
}

# Animated keys (subtly reserved for loading, music activity, premium, AI processing, key indicators)
ANIMATED_EMOJI_KEYS: frozenset[str] = frozenset({
    "LOADING",
    "PROGRESS",
    "SYNC",
    "MUSIC",
    "PREMIUM",
    "AI_LOADING",
    "SUCCESS_ANIM",
    "BOT_STATUS",
    "COINS",
    "ANTI_NUKE",
    "HEART",
    "SPARKLE",
})

# Static equivalent key when an animated icon is unavailable or animation is disabled
STATIC_EQUIVALENT_KEYS: dict[str, str] = {
    "LOADING": "REFRESH",
    "PROGRESS": "TIME",
    "SYNC": "REFRESH",
    "MUSIC": "SOUND",
    "PREMIUM": "BADGE_ALT",
    "AI_LOADING": "AI",
    "SUCCESS_ANIM": "SUCCESS",
    "BOT_STATUS": "ONLINE",
    "COINS": "BALANCE",
    "ANTI_NUKE": "SECURITY",
    "HEART": "FAVORITE",
    "SPARKLE": "STARRED",
}


def parse_configured_emoji(raw: str | None) -> Optional[str]:
    """
    Validate a configured custom emoji string.
    Returns the valid Discord `<:name:id>` or `<a:name:id>` markup,
    or None if empty / still containing placeholder text (e.g. `EMOJI_ID`).
    """
    if not raw or not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if any(marker in stripped for marker in _PLACEHOLDER_MARKERS):
        return None
    if _VALID_CUSTOM_EMOJI_RE.match(stripped):
        return stripped
    return None


def get_unconfigured_emoji_keys() -> list[str]:
    """Return sorted list of configured keys still using placeholder IDs."""
    return sorted(
        k for k, v in KYOKA_CUSTOM_EMOJI_IDS.items()
        if parse_configured_emoji(v) is None
    )


@dataclass(frozen=True)
class GptEmojiEntry:
    """Normalized catalog entry from emojis_gpt/extra_emoji_manifest.json."""
    name: str
    category: str
    glyph: str
    fallback: str
    usage: str
    animated: bool
    source: str


@lru_cache(maxsize=1)
def load_gpt_emoji_manifest() -> dict[str, GptEmojiEntry]:
    """Load and cache all entries from emojis_gpt/extra_emoji_manifest.json."""
    entries: dict[str, GptEmojiEntry] = {}
    if not _MANIFEST_PATH.exists():
        logger.debug(f"emojis_gpt manifest not found at {_MANIFEST_PATH}")
        return entries
    try:
        raw_list = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw_list, list):
            return entries
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().lower()
            if not name:
                continue
            entries[name] = GptEmojiEntry(
                name=name,
                category=str(item.get("category", "extras")).strip().lower(),
                glyph=str(item.get("glyph", "")),
                fallback=str(item.get("fallback", item.get("glyph", "•"))),
                usage=str(item.get("usage", name.title())),
                animated=bool(item.get("animated", False)),
                source=str(item.get("source", "extra_emoji_sheet.svg")),
            )
    except Exception as exc:
        logger.warning(f"Failed to load emojis_gpt manifest: {exc}")
    return entries


def get_gpt_manifest_entry(name: str) -> Optional[GptEmojiEntry]:
    """Look up a single entry from the emojis_gpt manifest by name (case-insensitive)."""
    clean = name.lower().strip().lstrip(":")
    manifest = load_gpt_emoji_manifest()
    if clean in manifest:
        return manifest[clean]
    if clean.endswith("_alt") and clean[:-4] in manifest:
        return manifest[clean[:-4]]
    alt_key = f"{clean}_alt"
    if alt_key in manifest:
        return manifest[alt_key]
    return None
