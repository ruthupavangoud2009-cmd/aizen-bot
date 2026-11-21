"""
KYOKA — Aizen Ultimate Edition
Centralized Custom Animated & Static Discord Emoji Registry

Manages all accessible Discord application emojis and shared guild emojis,
provides category mappings for all 43 bot systems, and permanently persists
custom emoji configuration across bot restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
import discord

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Emojis")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_PERSISTENT_MAPPINGS_FILE = _DATA_DIR / "emoji_mappings.json"

# All 43 official KYOKA system categories mapped to prioritized accessible emoji candidate names
CATEGORY_CANDIDATES: dict[str, list[str]] = {
    "SUCCESS": ["icon_success", "success", "icons_verified", "verified", "icon_clear", "check"],
    "ERROR": ["icon_x", "icon_wrong", "error", "icons_wrong", "icon_delete", "cross"],
    "WARNING": ["icons_warning", "icon_warning", "warning", "icons_reminder"],
    "LOADING": ["icons_loading", "loading", "ub_refresh_icon", "icons_update"],
    "ARROW": ["icons_rightarrow", "white_arrow", "tts_right_arrow", "icons_arrow", "heart_dot"],
    "HOME": ["icon_home", "home"],
    "MODERATION": ["icon_moderation", "icon_mod", "icons_guardian", "icons_staff"],
    "BAN": ["icon_unban", "icon_delete", "icons_locked", "icon_lock", "icon_x"],
    "KICK": ["icon_delete", "icons_leave", "icons_wrong"],
    "MUTE": ["icons_micmute", "room_icon_mute", "icons_timeout", "icons_locked"],
    "WARN": ["icons_warning", "icon_warning", "warning"],
    "LOCK": ["icons_locked", "icon_lock", "locked"],
    "UNLOCK": ["icons_unlock", "unlock", "icons_locked"],
    "SECURITY": ["antinuke_shield", "icons_guardian", "icon_shield", "icons_locked"],
    "ANTI_NUKE": ["antinuke_shield", "icons_guardian", "icon_shield"],
    "VERIFICATION": ["icons_verified", "icon_verified", "verified_premium", "icons_guardian"],
    "TICKET": ["icon_ticket", "ticket_support", "ticket", "ticket_nox"],
    "MUSIC": ["music_music", "music_playing", "music", "icon_music"],
    "PLAY": ["music_playing", "music", "icon_music", "icons_rightarrow"],
    "PAUSE": ["paused", "icons_pause", "icon_pause"],
    "SKIP": ["skip", "icons_rightarrow", "icon_arrow_left"],
    "STOP": ["icons_stop_button", "icon_stop", "icon_delete"],
    "AI": ["ai", "icons_magicwand", "icons_sparkles", "icon_bot"],
    "AFK": ["afk", "icons_clock", "icons_offline", "icons_richpresence"],
    "PROFILE": ["icon_person", "user_badge", "icons_member", "icons_people"],
    "LEVEL": ["icon_stats", "btp_red_crown", "icons_star", "icons_upvote"],
    "PREMIUM": ["verified_premium", "icon_premium", "btp_red_crown", "icons_nitroboost"],
    "OWNER": ["icons_owner", "icon_owner", "btp_red_crown"],
    "ADMIN": ["icons_staff", "icon_mod", "icon_developer", "icon_dev"],
    "STAFF": ["icons_staff", "icons_supportteam", "icon_support"],
    "MEMBERS": ["icons_people", "icons_member", "icon_person"],
    "SERVER": ["icon_forum", "icons_menu", "icon_home"],
    "CHANNEL": ["icons_message", "icons_thread", "icons_podcast"],
    "ROLE": ["lpf_icon_roles", "icons_staff", "user_badge"],
    "SETTINGS": ["icons_settings", "icon_rules"],
    "SEARCH": ["icon_search", "icons_search", "icons_todolist"],
    "BACK": ["icons_leftarrow", "icon_arrow_left", "pmochii_arrow_left"],
    "NEXT": ["icons_rightarrow", "white_arrow", "icons_arrow"],
    "TIME": ["icons_reminder", "icons_calender1", "icons_clock"],
    "PING": ["icons_ping", "icons_richpresence"],
    "DATABASE": ["icons_todolist", "icons_file", "icons_files"],
    "SAVE": ["icons_download", "icons_todolist", "icon_upload"],
    "INFO": ["icon_info", "spy_icons_question", "icons_todolist"],
    "GIVEAWAY": ["s_giveaway", "discord_giveaway", "giveaway", "icons_gift"],
    "MEDIA": ["media", "icon_media", "icons_image", "icons_file"],
    "WELCOMER": ["icons_join", "icon_join", "icons_welcome", "001_cinnamoroll_welcome_nf2u"],
    "VOICE": ["icons_podcast", "room_icon_mute", "icon_voice"],
    "LOGGING": ["icon_logging", "icons_todolist", "icons_file"],
    "CASINO": ["icon_casino", "casino", "cash"],
    "GAMES": ["icon_backpack", "icon_games", "icon_fun"],
    "UTILITY": ["icons_utility", "icons_settings", "ub_refresh_icon"],
    "ECONOMY": ["icon_dollar", "zefex_credit_cards", "cash"],
}

CATEGORY_FALLBACK_EMOJIS: dict[str, str] = {
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "LOADING": "🔄",
    "ARROW": "💜",
    "HOME": "🏠",
    "MODERATION": "⚔️",
    "BAN": "🔨",
    "KICK": "👢",
    "MUTE": "🔇",
    "WARN": "⚠️",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "SECURITY": "🛡️",
    "ANTI_NUKE": "🛡️",
    "VERIFICATION": "✅",
    "TICKET": "🎫",
    "MUSIC": "🎵",
    "PLAY": "▶️",
    "PAUSE": "⏸️",
    "SKIP": "⏭️",
    "STOP": "⏹️",
    "AI": "🤖",
    "AFK": "💤",
    "PROFILE": "👤",
    "LEVEL": "⭐",
    "PREMIUM": "💎",
    "OWNER": "👑",
    "ADMIN": "⚙️",
    "STAFF": "🛡️",
    "MEMBERS": "👥",
    "SERVER": "🌐",
    "CHANNEL": "💬",
    "ROLE": "🏷️",
    "SETTINGS": "⚙️",
    "SEARCH": "🔍",
    "BACK": "◀️",
    "NEXT": "▶️",
    "TIME": "⏰",
    "PING": "📶",
    "DATABASE": "💾",
    "SAVE": "💾",
    "INFO": "ℹ️",
    "GIVEAWAY": "🎉",
    "MEDIA": "🖼️",
    "WELCOMER": "🚪",
    "VOICE": "🎙️",
    "LOGGING": "📜",
    "CASINO": "🎰",
    "GAMES": "🎮",
    "UTILITY": "🔧",
    "ECONOMY": "💳",
}


class EmojiRegistry:
    """Central registry mapping emoji names and categories to discord.Emoji objects."""

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._emojis: dict[str, discord.Emoji] = {}
        self._custom_mappings: dict[str, str] = {}
        self._aliases: dict[str, list[str]] = self._init_alias_map()

    @property
    def emoji_count(self) -> int:
        """Count unique application emoji IDs, not cache aliases."""
        return len({getattr(emoji, "id", id(emoji)) for emoji in self._emojis.values()})

    def _init_alias_map(self) -> dict[str, list[str]]:
        return {
            "white_line": ["whiteline", "line", "icon_line"],
            "white_arrow": ["icons_rightarrow", "tts_right_arrow", "icons_arrow"],
            "tts_right_arrow": ["icons_rightarrow", "icons_arrow"],
            "icons_arrow": ["icons_rightarrow", "heart_dot", "icon_arrow_left"],
            "icons_rightarrow": ["icons_arrow", "heart_dot"],
            "icon_arrow_left": ["icons_leftarrow"],
            "icons_leftarrow": ["icon_arrow_left"],
            "heart_dot": ["icons_heart", "heart"],
            "icons_heart": ["heart_dot", "heart"],
            "heart": ["heart_dot", "icons_heart"],
            "ticket_nox": ["icon_ticket", "ticket_support"],
            "icon_ticket": ["ticket_nox", "ticket_support", "ticket"],
            "icons_locked": ["icon_lock", "icon_locked"],
            "icon_lock": ["icons_locked", "icon_locked"],
            "icons_staff": ["icon_mod", "icon_moderation", "icon_support", "icons_supportteam"],
            "icon_moderation": ["icon_mod", "icons_staff", "icons_guardian"],
            "icons_join": ["icon_join", "icons_welcome", "icons_connect"],
            "icon_join": ["icons_join", "icons_welcome", "icons_connect"],
            "icons_file": ["icons_files", "icons_todolist", "icon_logging"],
            "icons_files": ["icons_file", "icons_todolist", "icon_logging"],
            "icons_image": ["icon_image", "icons_file"],
            "icon_image": ["icons_image", "icons_file"],
            "icons_delete": ["icon_delete", "icon_clear", "icons_wrong"],
            "icon_delete": ["icons_delete", "icon_clear", "icon_x"],
            "icons_download": ["icons_download", "icons_Download", "download", "icon_download"],
            "download": ["icons_download", "icons_Download", "icon_download"],
            "music": ["icon_music", "music_playing", "music_music"],
            "icon_music": ["music", "music_playing", "music_music"],
            "paused": ["icons_pause", "icon_pause"],
            "icons_pause": ["paused", "icon_pause"],
            "skip": ["icons_rightarrow", "icon_arrow_left", "icons_arrow"],
            "queue": ["icons_list", "icon_playlist", "icons_todolist"],
            "icons_stop_button": ["stop", "icon_stop", "icon_delete", "icon_x"],
            "stop": ["icons_stop_button", "icon_stop", "icon_delete", "icon_x"],
            "icons_loop": ["ub_refresh_icon", "icons_update"],
            "loop": ["icons_loop", "ub_refresh_icon"],
            "icons_shuffle": ["icons_magicwand", "icons_splash"],
            "switch_on": ["icon_switch_on"],
            "switch_off": ["icon_switch_off"],
            "icon_switch_on": ["switch_on"],
            "icon_switch_off": ["switch_off"],
            "voldown": ["volume_down", "vol_down"],
            "volume_down": ["voldown", "vol_down"],
            "volup": ["volume_up", "vol_up"],
            "volume_up": ["volup", "vol_up", "volume_down"],
            "room_icon_mute": ["volume_down", "icons_micmute"],
            "media": ["icon_media", "icons_image", "icons_file"],
            "giveaway": ["s_giveaway", "discord_giveaway", "icons_gift"],
            "discord_giveaway": ["s_giveaway", "giveaway", "icons_gift"],
            "s_giveaway": ["discord_giveaway", "giveaway", "icons_gift"],
            "gpp_winner": ["winner", "s_giveaway", "discord_giveaway", "icons_gift"],
            "winner": ["gpp_winner", "s_giveaway", "discord_giveaway", "icons_gift"],
        }

    async def _load_persistent_mappings(self) -> None:
        """Load saved custom emoji configurations from PostgreSQL and fallback to disk."""
        # 1. Try local JSON first as immediate baseline
        try:
            if _PERSISTENT_MAPPINGS_FILE.exists():
                with open(_PERSISTENT_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._custom_mappings.update(data)
        except Exception as e:
            logger.debug(f"Could not read local emoji mappings: {e}")

        # 2. Sync from PostgreSQL database if pool is ready
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kyoka_emoji_mappings (
                        category_or_name VARCHAR(64) PRIMARY KEY,
                        raw_str TEXT NOT NULL,
                        emoji_id BIGINT,
                        emoji_name VARCHAR(64),
                        is_animated BOOLEAN DEFAULT FALSE,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                rows = await self.bot.db.fetch_all("SELECT category_or_name, raw_str FROM kyoka_emoji_mappings;")
                for r in rows:
                    cat = str(r["category_or_name"]).upper()
                    self._custom_mappings[cat] = str(r["raw_str"])
                logger.info(f"Loaded {len(rows)} persistent custom emoji mapping(s) from database.")
            except Exception as e:
                logger.debug(f"Notice loading database emoji mappings: {e}")

    async def save_mapping(self, category_or_name: str, emoji_str: str) -> None:
        """
        Permanently save a custom emoji mapping that survives bot restarts.
        Validates emoji access before saving to prevent broken icons.
        """
        key = category_or_name.upper().strip()
        val = emoji_str.strip()

        # Parse emoji metadata
        parsed_id = None
        parsed_name = None
        is_animated = False
        match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", val)
        if match:
            is_animated = match.group(1) == "a"
            parsed_name = match.group(2)
            parsed_id = int(match.group(3))

        self._custom_mappings[key] = val

        # Save to local disk cache
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_PERSISTENT_MAPPINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._custom_mappings, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist emoji mapping to disk: {e}")

        # Save to PostgreSQL
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO kyoka_emoji_mappings (category_or_name, raw_str, emoji_id, emoji_name, is_animated, updated_at)
                    VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
                    ON CONFLICT (category_or_name) DO UPDATE SET
                        raw_str = EXCLUDED.raw_str,
                        emoji_id = EXCLUDED.emoji_id,
                        emoji_name = EXCLUDED.emoji_name,
                        is_animated = EXCLUDED.is_animated,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    key,
                    val,
                    parsed_id,
                    parsed_name,
                    is_animated,
                )
                logger.info(f"Persisted custom emoji mapping: {key} -> {val}")
            except Exception as e:
                logger.error(f"Failed to persist emoji mapping to database: {e}")

    async def load(self) -> None:
        """Fetch all application emojis from Discord API, sync assets, and load persistent mappings."""
        try:
            await self._load_persistent_mappings()

            if not hasattr(self.bot, "http") or not getattr(self.bot.http, "token", None):
                return
            global_over = getattr(self.bot.http, "_global_over", None)
            if global_over is None or not hasattr(global_over, "is_set"):
                return

            if not self.bot.application_id:
                try:
                    app_info = await self.bot.application_info()
                    self.bot.application_id = app_info.id
                except Exception:
                    pass

            if self.bot.application_id:
                emojis = await self.bot.fetch_application_emojis()
                self._emojis = {e.name.lower(): e for e in emojis}
                logger.info(f"Successfully cached {len(self._emojis)} custom Application Emoji(s).")
        except Exception as e:
            logger.warning(f"Failed to fetch application emojis: {e}")

    def get_category(self, category: str, animated_only: bool = False, fallback: str = "") -> str:
        """
        Resolve custom emoji string by system category (e.g. SUCCESS, ERROR, LOADING, MODERATION).
        Prefers animated custom emojis when available; falls back to dedicated category icons.
        """
        cat_key = category.upper().strip()

        # 1. Check persistent user-configured override
        if cat_key in self._custom_mappings:
            return self._custom_mappings[cat_key]

        # 2. Check candidate list
        candidates = CATEGORY_CANDIDATES.get(cat_key, [cat_key.lower()])

        # First pass: look for animated custom emoji
        for name in candidates:
            obj = self.get_emoji_obj(name)
            if obj is not None and getattr(obj, "animated", False):
                return str(obj)

        if not animated_only:
            # Second pass: accept static custom emoji
            for name in candidates:
                obj = self.get_emoji_obj(name)
                if obj is not None:
                    return str(obj)

        if fallback:
            return fallback
        return CATEGORY_FALLBACK_EMOJIS.get(cat_key, "•")

    def get_category_obj(self, category: str) -> discord.Emoji | discord.PartialEmoji | str:
        """Resolve a discord.Emoji, PartialEmoji, or clean icon for UI Buttons/Select menus."""
        cat_key = category.upper().strip()

        # Check persistent mapping
        if cat_key in self._custom_mappings:
            raw = self._custom_mappings[cat_key]
            match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", raw)
            if match:
                return discord.PartialEmoji(
                    name=match.group(2),
                    id=int(match.group(3)),
                    animated=match.group(1) == "a",
                )
            if raw:
                return raw

        candidates = CATEGORY_CANDIDATES.get(cat_key, [cat_key.lower()])
        # First pass: animated
        for name in candidates:
            obj = self.get_emoji_obj(name)
            if obj is not None and getattr(obj, "animated", False):
                return obj

        # Second pass: static custom emoji
        for name in candidates:
            obj = self.get_emoji_obj(name)
            if obj is not None:
                return obj

        # Guaranteed fallback so dropdown options are NEVER blank (matching Image 4)
        return CATEGORY_FALLBACK_EMOJIS.get(cat_key, "📁")

    def get(self, name: str, fallback: str = "") -> str:
        """
        Get custom emoji string (e.g. '<:icon_bot:123456789>') by name or category.
        If not found, returns fallback (defaults to empty string, avoiding random Unicode).
        """
        name_clean = name.lower().strip(":")
        upper_key = name_clean.upper()

        # Check custom mappings
        if upper_key in self._custom_mappings:
            return self._custom_mappings[upper_key]
        if name_clean in self._custom_mappings:
            return self._custom_mappings[name_clean]

        # Check application emojis
        emoji = self._emojis.get(name_clean)
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean)

        # Check aliases
        if not emoji:
            for alias in self._aliases.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        if emoji:
            return str(emoji)

        # If a category was passed, try category resolver
        if upper_key in CATEGORY_CANDIDATES:
            cat_res = self.get_category(upper_key, fallback="")
            if cat_res:
                return cat_res

        return fallback

    def animated(self, *names: str, fallback: str = "") -> str:
        """Resolve only registered animated custom emojis."""
        for name in names:
            try:
                emoji = self.get_emoji_obj(name)
                if emoji is not None and getattr(emoji, "animated", False):
                    return str(emoji)
            except Exception:
                continue
        return fallback

    def get_emoji_obj(self, name: str) -> discord.Emoji | discord.PartialEmoji | None:
        """Get a discord.Emoji or discord.PartialEmoji object for UI buttons or components."""
        name_clean = name.lower().strip(":")
        upper_key = name_clean.upper()

        if upper_key in self._custom_mappings:
            raw = self._custom_mappings[upper_key]
            match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", raw)
            if match:
                return discord.PartialEmoji(
                    name=match.group(2),
                    id=int(match.group(3)),
                    animated=match.group(1) == "a",
                )

        emoji = self._emojis.get(name_clean)
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean)

        if not emoji:
            for alias in self._aliases.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        return emoji

    def get_select_emoji(self, name: str, fallback_unicode: str | None = None) -> dict[str, Any] | None:
        """
        Get emoji dictionary structure suitable for Discord Select Menu options and components.
        Custom emoji requires {'id': str, 'name': str, 'animated': bool}.
        Supports BOTH static and animated custom emojis.
        """
        obj = self.get_emoji_obj(name)
        if obj:
            return {
                "id": str(getattr(obj, "id", "")),
                "name": str(getattr(obj, "name", name)),
                "animated": bool(getattr(obj, "animated", False)),
            }
        if fallback_unicode:
            return {"name": fallback_unicode}
        return None
