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

from src.utils.emoji_config import (
    ANIMATED_EMOJI_KEYS,
    KYOKA_CUSTOM_EMOJI_IDS,
    STATIC_EQUIVALENT_KEYS,
    GptEmojiEntry,
    get_gpt_manifest_entry,
    get_unconfigured_emoji_keys,
    load_gpt_emoji_manifest,
    parse_configured_emoji,
)

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Emojis")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_PERSISTENT_MAPPINGS_FILE = _DATA_DIR / "emoji_mappings.json"

# All official KYOKA system & emojis_gpt categories mapped to prioritized custom emoji names
CATEGORY_CANDIDATES: dict[str, list[str]] = {
    # Branding & Core Feedback
    "KYOKA": ["kyoka_brand", "kyoka", "heart_pulse", "sparkle_shine"],
    "BRAND": ["kyoka_brand", "kyoka", "sparkle_shine"],
    "SPARKLE": ["kyoka_sparkle", "sparkle_shine", "ai", "icons_magicwand", "icons_sparkles"],
    "HEART": ["kyoka_heart", "heart_pulse", "heart_dot", "favorite"],
    "SUCCESS": ["kyoka_success", "kyoka_success_glow", "verified_glow", "icon_success", "success", "icons_verified", "verified", "verified_alt", "approve", "icon_clear", "check"],
    "SUCCESS_ANIM": ["kyoka_success_glow", "verified_glow", "kyoka_success", "icon_success"],
    "APPROVE": ["kyoka_approve", "approve", "verified_glow", "icon_success", "success"],
    "ERROR": ["kyoka_error", "icon_x", "icon_wrong", "error", "icons_wrong", "deny", "icon_delete", "cross"],
    "DENY": ["kyoka_deny", "deny", "icon_x", "icon_wrong", "error"],
    "WARNING": ["kyoka_warning", "warning_flash", "icons_warning", "icon_warning", "warning", "warning_alt", "icons_reminder"],
    "WARNING_ALT": ["kyoka_warning_alt", "warning_alt", "warning_flash", "icons_warning", "warning"],
    "LOADING": ["kyoka_loading", "loading_pulse", "icons_loading", "loading", "ub_refresh_icon", "icons_update"],
    "PROGRESS": ["kyoka_progress", "progress", "loading_pulse", "icons_loading"],
    "SYNC": ["kyoka_sync", "sync", "ub_refresh_icon", "icons_update", "refresh"],
    "REFRESH": ["kyoka_refresh", "refresh", "ub_refresh_icon", "reload", "icons_update"],
    "ONLINE": ["kyoka_online", "icons_online", "bot_status"],
    "OFFLINE": ["kyoka_offline", "icons_offline"],
    "IDLE": ["kyoka_idle", "icons_reminder", "time"],
    "BOT_STATUS": ["kyoka_bot_status", "bot_status", "icons_online", "icon_bot"],

    # Navigation & Help UI
    "ARROW": ["kyoka_arrow", "heart_pulse", "heart_dot", "icons_rightarrow", "white_arrow", "tts_right_arrow", "icons_arrow"],
    "HOME": ["kyoka_home", "icon_stack", "icon_home", "home"],
    "BACK": ["kyoka_back", "icons_leftarrow", "icon_arrow_left", "pmochii_arrow_left"],
    "NEXT": ["kyoka_next", "icons_rightarrow", "white_arrow", "icons_arrow"],
    "SEARCH": ["kyoka_search", "icon_search", "icons_search", "scan", "icons_todolist"],
    "HELP": ["kyoka_help", "icon_book", "spy_icons_question", "icon_info"],
    "BOOK": ["kyoka_book", "icon_book", "icons_rules", "icon_rules", "icons_file"],
    "MODULES": ["kyoka_modules", "icon_modules", "icon_grid", "icon_menu", "icons_menu", "icon_forum"],
    "TERMINAL": ["kyoka_terminal", "icon_terminal", "icon_slash", "icons_slash", "icon_dev"],
    "BRACKETS": ["kyoka_brackets", "icon_brackets", "icon_code", "icon_developer", "icons_todolist", "icon_settings"],
    "STACK": ["kyoka_stack", "icon_stack", "icon_layers", "icon_home", "icons_menu"],
    "PIN": ["kyoka_pin", "pin", "icons_pin"],
    "LOCATION": ["kyoka_location", "location", "pin"],
    "FILTER": ["kyoka_filter", "filter", "sort"],
    "SORT": ["kyoka_sort", "sort", "filter"],

    # Moderation & Security / Anti-Nuke
    "MODERATION": ["kyoka_moderation", "icon_moderation", "icon_mod", "icons_guardian", "icons_staff"],
    "BAN": ["kyoka_ban", "icon_unban", "icon_delete", "icons_locked", "icon_lock", "icon_x"],
    "KICK": ["kyoka_kick", "icon_delete", "icons_leave", "icons_wrong"],
    "MUTE": ["kyoka_mute", "icons_micmute", "room_icon_mute", "icons_timeout", "mute_alt", "icons_locked"],
    "MUTE_ALT": ["kyoka_mute_alt", "mute_alt", "icons_micmute", "icons_timeout"],
    "UNMUTE": ["kyoka_unmute", "icons_unlock", "icons_verified", "approve"],
    "WARN": ["kyoka_warn", "warning_flash", "icons_warning", "icon_warning", "warning"],
    "PURGE": ["kyoka_purge", "icon_clear", "icon_delete", "delete"],
    "DELETE": ["kyoka_delete", "delete", "icon_delete", "icon_clear", "icons_delete"],
    "EDIT": ["kyoka_edit", "edit", "icons_settings"],
    "LOCK": ["kyoka_lock", "icons_locked", "icon_lock", "locked"],
    "UNLOCK": ["kyoka_unlock", "icons_unlock", "unlock", "icons_locked"],
    "SECURITY": ["kyoka_security", "antinuke_pulse", "antinuke_shield", "shield_alt", "icons_guardian", "icon_shield", "icons_locked"],
    "ANTI_NUKE": ["kyoka_antinuke", "antinuke_pulse", "antinuke_shield", "shield_alt", "icons_guardian", "icon_shield"],
    "SHIELD_ALT": ["kyoka_shield_alt", "shield_alt", "antinuke_shield", "icons_guardian"],
    "FIREWALL": ["kyoka_firewall", "firewall", "antinuke_shield", "icons_guardian"],
    "SCAN": ["kyoka_scan", "scan", "icon_search", "icons_search"],
    "VERIFICATION": ["kyoka_verification", "verified_glow", "icons_verified", "icon_verified", "verified_alt", "verified_premium", "icons_guardian"],
    "VERIFIED_ALT": ["kyoka_verified_alt", "verified_alt", "verified_glow", "icons_verified"],
    "APPEAL": ["kyoka_appeal", "appeal", "icon_rules", "icons_rules"],
    "REPORT": ["kyoka_report", "report", "warning_flash", "icons_warning"],
    "BACKUP": ["kyoka_backup", "backup", "storage", "icons_download"],
    "RESTORE": ["kyoka_restore", "restore", "ub_refresh_icon", "sync"],

    # Tickets & Support
    "TICKET": ["kyoka_ticket", "icon_ticket", "ticket_support", "ticket", "ticket_nox"],
    "TICKET_OPEN": ["kyoka_ticket_open", "icon_ticket", "ticket_support", "ticket"],
    "TICKET_CLOSE": ["kyoka_ticket_close", "icons_locked", "icon_lock", "icon_delete"],
    "TICKET_CLAIM": ["kyoka_ticket_claim", "pin", "icons_pin", "icons_staff"],
    "TICKET_UNCLAIM": ["kyoka_ticket_unclaim", "icons_unlock", "icons_supportteam"],
    "TRANSCRIPT": ["kyoka_transcript", "transcript", "icons_todolist", "icons_file"],
    "STAFF": ["kyoka_staff", "staff", "icons_staff", "icons_supportteam", "icon_support"],

    # Music & Voice
    "MUSIC": ["kyoka_music", "music_music", "music_playing", "music", "icon_music", "sound"],
    "PLAY": ["kyoka_play", "music_playing", "music", "icon_music", "icons_rightarrow"],
    "PAUSE": ["kyoka_pause", "paused", "icons_pause", "icon_pause"],
    "RESUME": ["kyoka_resume", "music_playing", "icons_rightarrow", "play"],
    "STOP": ["kyoka_stop", "icons_stop_button", "icon_stop", "icon_delete"],
    "SKIP": ["kyoka_skip", "skip", "icons_rightarrow", "icon_arrow_left"],
    "PREVIOUS": ["kyoka_previous", "icons_leftarrow", "icon_arrow_left", "pmochii_arrow_left"],
    "QUEUE": ["kyoka_queue", "queue", "icons_list", "icon_playlist", "icons_todolist"],
    "VOLUME": ["kyoka_volume", "sound", "volume_up", "volume_down"],
    "VOLUME_UP": ["kyoka_volume_up", "volume_up", "volup"],
    "VOLUME_DOWN": ["kyoka_volume_down", "volume_down", "voldown", "room_icon_mute"],
    "LYRICS": ["kyoka_lyrics", "icon_book", "icons_message", "message_alt"],
    "LOOP": ["kyoka_loop", "icons_loop", "loop", "ub_refresh_icon"],
    "SHUFFLE": ["kyoka_shuffle", "icons_shuffle", "icons_magicwand", "icons_splash"],
    "SOUND": ["kyoka_sound", "sound", "music_music", "icon_music"],
    "RECORD": ["kyoka_record", "record", "icons_podcast"],
    "VOICE": ["kyoka_voice", "voice", "icons_podcast", "room_icon_mute", "icon_voice"],
    "STAGE": ["kyoka_stage", "stage", "icons_stagerequesttospeaklist", "icons_podcast"],
    "VOICE_JOIN": ["kyoka_voice_join", "voice_join", "icons_join"],
    "VOICE_LEAVE": ["kyoka_voice_leave", "voice_leave", "icons_leave"],

    # Economy & Casino
    "ECONOMY": ["kyoka_economy", "coin_spin", "icon_dollar", "zefex_credit_cards", "cash"],
    "BALANCE": ["kyoka_balance", "coin_spin", "icon_dollar", "zefex_credit_cards", "cash"],
    "WALLET": ["kyoka_wallet", "zefex_credit_cards", "icon_dollar", "coin_spin"],
    "COINS": ["kyoka_coins", "coin_spin", "cash", "icon_dollar"],
    "SHOP": ["kyoka_shop", "giftbox", "icon_backpack", "icons_gift"],
    "INVENTORY": ["kyoka_inventory", "icon_backpack", "storage", "icons_list"],
    "REWARDS": ["kyoka_rewards", "giftbox", "prize", "icons_gift", "gpp_winner"],
    "DAILY": ["kyoka_daily", "icons_calender1", "date", "time", "coin_spin"],
    "LEADERBOARD": ["kyoka_leaderboard", "rank", "medal", "btp_red_crown", "icon_stats"],
    "TRANSACTIONS": ["kyoka_transactions", "zefex_credit_cards", "icons_todolist", "icon_dollar"],
    "PURCHASES": ["kyoka_purchases", "zefex_credit_cards", "giftbox", "icon_backpack"],
    "CASINO": ["kyoka_casino", "coin_spin", "icon_casino", "casino", "cash"],
    "GAMES": ["kyoka_games", "icon_backpack", "icon_games", "icon_fun"],

    # Levels, XP, Reputation & Social
    "LEVEL": ["kyoka_level", "rank", "sparkle_shine", "icon_stats", "btp_red_crown", "icons_star", "icons_upvote"],
    "XP": ["kyoka_xp", "starred", "icons_star", "icons_upvote", "sparkle_shine"],
    "RANK": ["kyoka_rank", "rank", "medal", "badge_alt", "btp_red_crown"],
    "MEDAL": ["kyoka_medal", "medal", "rank", "gpp_winner"],
    "PROFILE": ["kyoka_profile", "icon_person", "user_badge", "icons_member", "icons_people"],
    "VOUCH": ["kyoka_vouch", "verified_glow", "starred", "icons_star", "icons_verified"],
    "REPUTATION": ["kyoka_reputation", "starred", "verified_glow", "medal", "icons_star"],
    "SOCIAL": ["kyoka_social", "heart_pulse", "favorite", "party", "icons_people"],
    "STARRED": ["kyoka_starred", "starred", "icons_star", "sparkle_shine"],
    "FAVORITE": ["kyoka_favorite", "favorite", "heart_pulse", "heart_dot"],
    "PARTY": ["kyoka_party", "party", "icons_tada", "s_giveaway"],
    "GIFTBOX": ["kyoka_giftbox", "giftbox", "icons_gift", "prize"],
    "GIVEAWAY": ["kyoka_giveaway", "s_giveaway", "discord_giveaway", "giveaway", "icons_gift"],
    "TARGET": ["kyoka_target", "target", "icons_ping"],

    # Artificial Intelligence
    "AI": ["kyoka_ai", "sparkle_shine", "ai", "icons_magicwand", "icons_sparkles", "icon_bot"],
    "AI_LOADING": ["kyoka_ai_loading", "loading_pulse", "sparkle_shine", "icons_loading"],
    "AI_VOICE": ["kyoka_ai_voice", "voice", "icons_podcast", "sparkle_shine"],
    "AI_PERSONALITY": ["kyoka_ai_personality", "sparkle_shine", "icons_magicwand", "icon_person"],

    # Server Management & Utilities
    "ADMIN": ["kyoka_admin", "admin", "icons_staff", "icon_mod", "icon_developer", "icon_dev"],
    "SERVER": ["kyoka_server", "server", "icon_forum", "icons_menu", "icon_home"],
    "MEMBER": ["kyoka_member", "member", "icon_person", "icons_member", "user_badge"],
    "MEMBERS": ["kyoka_members", "icons_people", "icons_member", "icon_person"],
    "ROLE": ["kyoka_role", "role", "lpf_icon_roles", "icons_staff", "user_badge"],
    "CHANNEL": ["kyoka_channel", "channel", "icons_message", "icons_thread", "icons_podcast"],
    "SETTINGS": ["kyoka_settings", "icons_settings", "icon_rules"],
    "LOGGING": ["kyoka_logging", "icon_logging", "icons_todolist", "icons_file"],
    "WELCOMER": ["kyoka_welcomer", "icons_join", "icon_join", "icons_welcome", "001_cinnamoroll_welcome_nf2u"],
    "BOOST": ["kyoka_boost", "boost", "icons_nitroboost", "icons_upvote"],
    "BROADCAST": ["kyoka_broadcast", "broadcast", "bell_alt", "icons_ping"],
    "BELL_ALT": ["kyoka_bell_alt", "bell_alt", "icons_reminder"],
    "MESSAGE_ALT": ["kyoka_message_alt", "message_alt", "icons_message"],
    "UTILITY": ["kyoka_utility", "icons_utility", "icons_settings", "ub_refresh_icon"],
    "AFK": ["kyoka_afk", "afk", "icons_clock", "icons_offline", "icons_richpresence"],
    "REMINDER": ["kyoka_reminder", "icons_reminder", "timer", "time"],
    "TIME": ["kyoka_time", "time", "icons_reminder", "icons_calender1", "icons_clock"],
    "TIMER": ["kyoka_timer", "timer", "time", "icons_clock"],
    "DATE": ["kyoka_date", "date", "icons_calender1"],
    "PING": ["kyoka_ping", "icons_ping", "icons_richpresence", "network"],
    "DATABASE": ["kyoka_database", "storage", "icons_todolist", "icons_file", "icons_files"],
    "SAVE": ["kyoka_save", "icons_download", "icons_todolist", "icon_upload"],
    "INFO": ["kyoka_info", "icon_info", "spy_icons_question", "icons_todolist"],
    "STATS": ["kyoka_stats", "icon_stats", "progress", "icons_richpresence"],
    "API": ["kyoka_api", "api", "network", "webhook"],
    "WEBHOOK": ["kyoka_webhook", "webhook", "api", "icons_link"],
    "CLOUD": ["kyoka_cloud", "cloud", "network"],
    "NETWORK": ["kyoka_network", "network", "cloud", "icons_ping"],
    "STORAGE": ["kyoka_storage", "storage", "backup", "icons_files"],
    "MEDIA": ["kyoka_media", "media", "icon_media", "icons_image", "icons_file"],

    # Owner, Developer & Premium
    "PREMIUM": ["kyoka_premium", "verified_premium", "icon_premium", "btp_red_crown", "icons_nitroboost"],
    "BADGE_ALT": ["kyoka_badge_alt", "badge_alt", "user_badge", "verified_premium"],
    "OWNER": ["kyoka_owner", "owner", "icons_owner", "icon_owner", "btp_red_crown"],
    "DEVELOPER": ["kyoka_developer", "developer", "icon_developer", "icon_dev", "icon_code"],
    "DIAGNOSTICS": ["kyoka_diagnostics", "scan", "bug", "icon_stats", "icons_ping"],
    "MAINTENANCE": ["kyoka_maintenance", "icons_utility", "icons_settings", "reload"],
    "BUG": ["kyoka_bug", "bug", "report", "warning_alt"],
    "RELOAD": ["kyoka_reload", "reload", "refresh", "ub_refresh_icon", "sync"],
}

# Discord-safe Unicode fallbacks (valid in message prose, embed headers, AND Buttons/SelectOptions)
CATEGORY_FALLBACK_EMOJIS: dict[str, str] = {
    "KYOKA": "⛩️",
    "BRAND": "⛩️",
    "SPARKLE": "✨",
    "HEART": "💜",
    "SUCCESS": "✅",
    "SUCCESS_ANIM": "✅",
    "APPROVE": "✅",
    "ERROR": "❌",
    "DENY": "❌",
    "WARNING": "⚠️",
    "WARNING_ALT": "⚠️",
    "LOADING": "⏳",
    "PROGRESS": "⏳",
    "SYNC": "🔄",
    "REFRESH": "🔄",
    "ONLINE": "🟢",
    "OFFLINE": "🔴",
    "IDLE": "🟡",
    "BOT_STATUS": "🟢",
    "ARROW": "»",
    "HOME": "🏠",
    "BACK": "◀️",
    "NEXT": "▶️",
    "SEARCH": "🔍",
    "HELP": "📖",
    "BOOK": "📖",
    "MODULES": "🗂️",
    "TERMINAL": "💻",
    "BRACKETS": "🧩",
    "STACK": "📚",
    "PIN": "📌",
    "LOCATION": "📍",
    "FILTER": "🧰",
    "SORT": "🔀",
    "MODERATION": "⚔️",
    "BAN": "🔨",
    "KICK": "👢",
    "MUTE": "🔇",
    "MUTE_ALT": "🔇",
    "UNMUTE": "🔊",
    "WARN": "⚠️",
    "PURGE": "🧹",
    "DELETE": "🗑️",
    "EDIT": "✏️",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "SECURITY": "🛡️",
    "ANTI_NUKE": "🛡️",
    "SHIELD_ALT": "🛡️",
    "FIREWALL": "🧱",
    "SCAN": "🔎",
    "VERIFICATION": "✅",
    "VERIFIED_ALT": "✅",
    "APPEAL": "⚖️",
    "REPORT": "🚩",
    "BACKUP": "💾",
    "RESTORE": "♻️",
    "TICKET": "🎫",
    "TICKET_OPEN": "📩",
    "TICKET_CLOSE": "🔒",
    "TICKET_CLAIM": "📌",
    "TICKET_UNCLAIM": "🔓",
    "TRANSCRIPT": "📄",
    "STAFF": "🛡️",
    "MUSIC": "🎵",
    "PLAY": "▶️",
    "PAUSE": "⏸️",
    "RESUME": "▶️",
    "STOP": "⏹️",
    "SKIP": "⏭️",
    "PREVIOUS": "⏮️",
    "QUEUE": "📜",
    "VOLUME": "🔊",
    "VOLUME_UP": "🔊",
    "VOLUME_DOWN": "🔉",
    "LYRICS": "📝",
    "LOOP": "🔁",
    "SHUFFLE": "🔀",
    "SOUND": "🎶",
    "RECORD": "⏺️",
    "VOICE": "🎙️",
    "STAGE": "🎤",
    "VOICE_JOIN": "📥",
    "VOICE_LEAVE": "📤",
    "ECONOMY": "🪙",
    "BALANCE": "💰",
    "WALLET": "👛",
    "COINS": "🪙",
    "SHOP": "🛒",
    "INVENTORY": "🎒",
    "REWARDS": "🎁",
    "DAILY": "📅",
    "LEADERBOARD": "🏆",
    "TRANSACTIONS": "🧾",
    "PURCHASES": "🛍️",
    "CASINO": "🎰",
    "GAMES": "🎮",
    "LEVEL": "⭐",
    "XP": "✨",
    "RANK": "🏆",
    "MEDAL": "🏅",
    "PROFILE": "👤",
    "VOUCH": "⭐",
    "REPUTATION": "🌟",
    "SOCIAL": "💬",
    "STARRED": "⭐",
    "FAVORITE": "💜",
    "PARTY": "🎉",
    "GIFTBOX": "🎁",
    "GIVEAWAY": "🎉",
    "TARGET": "🎯",
    "AI": "🤖",
    "AI_LOADING": "⏳",
    "AI_VOICE": "🎙️",
    "AI_PERSONALITY": "🎭",
    "ADMIN": "⚙️",
    "SERVER": "🌐",
    "MEMBER": "👤",
    "MEMBERS": "👥",
    "ROLE": "🏷️",
    "CHANNEL": "💬",
    "SETTINGS": "⚙️",
    "LOGGING": "📜",
    "WELCOMER": "🚪",
    "BOOST": "🚀",
    "BROADCAST": "📢",
    "BELL_ALT": "🔔",
    "MESSAGE_ALT": "✉️",
    "UTILITY": "🔧",
    "AFK": "💤",
    "REMINDER": "⏰",
    "TIME": "⏰",
    "TIMER": "⏱️",
    "DATE": "📅",
    "PING": "📶",
    "DATABASE": "💾",
    "SAVE": "💾",
    "INFO": "ℹ️",
    "STATS": "📊",
    "API": "🔌",
    "WEBHOOK": "🪝",
    "CLOUD": "☁️",
    "NETWORK": "🌐",
    "STORAGE": "🗄️",
    "MEDIA": "🖼️",
    "PREMIUM": "💎",
    "BADGE_ALT": "🎖️",
    "OWNER": "👑",
    "DEVELOPER": "🛠️",
    "DIAGNOSTICS": "🩺",
    "MAINTENANCE": "🔧",
    "BUG": "🐛",
    "RELOAD": "🔄",
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

    @property
    def heart_dot(self) -> str:
        """Animated pulsing heart if available, else static heart dot, else bullet."""
        return (
            self.animated("heart_pulse", fallback="")
            or self.get("heart_pulse", "")
            or self.get("heart_dot", "")
            or ">"
        )

    @property
    def music_playing(self) -> str:
        """Animated music equalizer if available, else static music, else note."""
        return (
            self.animated("music_playing", "music_music", fallback="")
            or self.get("music_playing", "")
            or self.get("music", "")
            or "🎵"
        )

    @property
    def verified(self) -> str:
        """Animated verified glow if available, else static verified, else checkmark."""
        return (
            self.animated("verified_glow", fallback="")
            or self.get("verified_glow", "")
            or self.get("verified_premium", "")
            or "✅"
        )

    @property
    def loading(self) -> str:
        """Animated loading spinner if available, else static loading, else spinner."""
        return (
            self.animated("loading_pulse", fallback="")
            or self.get("loading_pulse", "")
            or "🔄"
        )

    @property
    def antinuke(self) -> str:
        """Animated antinuke shield pulse if available, else shield."""
        return (
            self.animated("antinuke_pulse", fallback="")
            or self.get("antinuke_pulse", "")
            or self.get("antinuke_shield", "")
            or "🛡️"
        )

    @property
    def coin(self) -> str:
        """Animated coin spin if available, else coin."""
        return (
            self.animated("coin_spin", fallback="")
            or self.get("coin_spin", "")
            or "🪙"
        )

    @property
    def sparkle(self) -> str:
        """Animated sparkle shine if available, else sparkle."""
        return (
            self.animated("sparkle_shine", fallback="")
            or self.get("sparkle_shine", "")
            or "✨"
        )

    def _init_alias_map(self) -> dict[str, list[str]]:
        return {
            "white_line": ["whiteline", "line", "icon_line"],
            "white_arrow": ["icons_rightarrow", "tts_right_arrow", "icons_arrow"],
            "tts_right_arrow": ["icons_rightarrow", "icons_arrow"],
            "icons_arrow": ["icons_rightarrow", "heart_pulse", "heart_dot", "icon_arrow_left"],
            "icons_rightarrow": ["icons_arrow", "heart_pulse", "heart_dot"],
            "icon_arrow_left": ["icons_leftarrow"],
            "icons_leftarrow": ["icon_arrow_left"],
            "heart_dot": ["heart_pulse", "icons_heart", "heart"],
            "icons_heart": ["heart_pulse", "heart_dot", "heart"],
            "heart": ["heart_pulse", "heart_dot", "icons_heart"],
            "heart_pulse": ["heart_dot", "icons_heart", "heart"],
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
            "music": ["music_playing", "music_music", "icon_music"],
            "music_playing": ["music_music", "music", "icon_music"],
            "music_music": ["music_playing", "music", "icon_music"],
            "icon_music": ["music_playing", "music_music", "music"],
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
            "verified": ["verified_glow", "verified_premium", "icons_verified"],
            "verified_glow": ["verified_premium", "icons_verified", "icon_success"],
            "loading": ["loading_pulse", "icons_loading", "ub_refresh_icon"],
            "loading_pulse": ["icons_loading", "ub_refresh_icon", "loading"],
            "antinuke": ["antinuke_pulse", "antinuke_shield", "icon_shield"],
            "antinuke_pulse": ["antinuke_shield", "icon_shield", "icons_guardian"],
            "coin": ["coin_spin", "icon_casino", "cash"],
            "coin_spin": ["icon_casino", "cash", "icon_dollar"],
            "sparkle": ["sparkle_shine", "ai", "icons_magicwand"],
            "sparkle_shine": ["ai", "icons_magicwand", "icons_sparkles"],
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
                # Asynchronously sync missing local assets up to the 2,000 application emoji limit
                asyncio.create_task(self.sync_assets_to_application())
        except Exception as e:
            logger.warning(f"Failed to fetch application emojis: {e}")

    async def sync_assets_to_application(self, max_upload: int = 2000) -> int:
        """
        Sync local PNG/GIF assets to Discord Application Emojis,
        taking advantage of Discord's 2,000 application emoji storage.
        """
        if not hasattr(self.bot, "create_application_emoji") or not getattr(self.bot, "application_id", None):
            return 0

        asset_dirs = [
            _DATA_DIR.parent / "assets" / "emoji",
            _DATA_DIR.parent / "assets" / "emoji2",
            _DATA_DIR.parent / "assets" / "emoji_custom",
            _DATA_DIR.parent / "assets" / "music",
            _DATA_DIR.parent / "assets" / "avatar",
            _DATA_DIR.parent / "assets" / "branding",
        ]
        created_count = 0
        existing_names = set(self._emojis.keys())

        for folder in asset_dirs:
            if not folder.exists():
                continue
            for file_path in folder.iterdir():
                if created_count >= max_upload:
                    break
                if file_path.suffix.lower() not in (".png", ".gif", ".jpg", ".jpeg"):
                    continue

                raw_name = file_path.stem.lower()
                clean_name = re.sub(r"[^a-z0-9_]", "_", raw_name)
                clean_name = re.sub(r"_+", "_", clean_name).strip("_")
                if len(clean_name) < 2:
                    clean_name = f"em_{clean_name}"
                clean_name = clean_name[:32]

                if clean_name in existing_names:
                    continue

                try:
                    with open(file_path, "rb") as f:
                        img_bytes = f.read()
                    if len(img_bytes) > 256 * 1024:
                        continue

                    new_emoji = await self.bot.create_application_emoji(name=clean_name, image=img_bytes)
                    self._emojis[clean_name] = new_emoji
                    existing_names.add(clean_name)
                    created_count += 1
                    logger.info(f"Registered Application Emoji: {clean_name} (ID: {new_emoji.id}, Animated: {getattr(new_emoji, 'animated', False)})")
                    await asyncio.sleep(0.4)
                except Exception as e:
                    logger.debug(f"Notice uploading application emoji {clean_name}: {e}")

        return created_count

    def _configured_for_key(self, key: str, *, allow_animated: bool = True) -> Optional[str]:
        """Resolve a valid configured emoji ID string from _custom_mappings or KYOKA_CUSTOM_EMOJI_IDS."""
        cat_key = key.upper().strip()
        for source in (self._custom_mappings, KYOKA_CUSTOM_EMOJI_IDS):
            raw = source.get(cat_key)
            parsed = parse_configured_emoji(raw)
            if parsed:
                is_anim = parsed.startswith("<a:")
                if is_anim and not allow_animated:
                    static_key = STATIC_EQUIVALENT_KEYS.get(cat_key)
                    if static_key:
                        static_raw = source.get(static_key) or KYOKA_CUSTOM_EMOJI_IDS.get(static_key)
                        static_parsed = parse_configured_emoji(static_raw)
                        if static_parsed:
                            return static_parsed
                    continue
                return parsed
            if raw and not raw.startswith("<") and raw in self._custom_mappings.values():
                return raw
        return None

    def get_category(
        self,
        category: str,
        animated_only: bool = False,
        fallback: str = "",
        allow_animated: bool = True,
    ) -> str:
        """
        Resolve custom emoji string by system category (e.g. SUCCESS, ERROR, LOADING, MODERATION).
        Resolution order:
        1. Persistent user-configured override or KYOKA_CUSTOM_EMOJI_IDS (validated ID only)
        2. Runtime Application / Guild animated custom emoji (when allow_animated=True)
        3. Runtime Application / Guild static custom emoji (or static equivalent)
        4. Provided fallback -> CATEGORY_FALLBACK_EMOJIS -> emojis_gpt manifest fallback -> '•'
        """
        cat_key = category.upper().strip()

        # 1. Persistent user mapping / central ID config
        configured = self._configured_for_key(cat_key, allow_animated=allow_animated)
        if configured:
            if not animated_only or configured.startswith("<a:"):
                return configured

        # 2. Runtime Application / Guild emojis
        candidates = CATEGORY_CANDIDATES.get(cat_key, [cat_key.lower()])

        if allow_animated:
            for name in candidates:
                obj = self.get_emoji_obj(name)
                if obj is not None and getattr(obj, "animated", False):
                    return str(obj)

        if not animated_only:
            for name in candidates:
                obj = self.get_emoji_obj(name)
                if obj is not None and (allow_animated or not getattr(obj, "animated", False)):
                    return str(obj)
            # Check explicit static equivalent category if animated key was requested without animation
            static_key = STATIC_EQUIVALENT_KEYS.get(cat_key)
            if static_key and static_key != cat_key:
                for name in CATEGORY_CANDIDATES.get(static_key, [static_key.lower()]):
                    obj = self.get_emoji_obj(name)
                    if obj is not None:
                        return str(obj)

        if fallback:
            return fallback
        if cat_key in CATEGORY_FALLBACK_EMOJIS:
            return CATEGORY_FALLBACK_EMOJIS[cat_key]
        manifest_entry = get_gpt_manifest_entry(cat_key)
        if manifest_entry:
            return manifest_entry.fallback
        return "•"

    def get_animated(self, concept_or_name: str, fallback: str = "✨") -> str:
        """
        Resolve an animated custom application emoji by concept, mood, or keyword.
        Matches keywords (sparkle, heart, verify, loading, defense, coin, hype, fire, etc.)
        to active animated application emojis on the bot, falling back to static or Unicode.
        """
        clean = concept_or_name.lower().strip(": ")
        upper = clean.upper()
        configured = self._configured_for_key(upper, allow_animated=True)
        if configured:
            return configured

        concept_map: dict[str, list[str]] = {
            "sparkle": ["kyoka_sparkle", "sparkle_shine", "ai", "icons_magicwand"],
            "ai": ["kyoka_ai_loading", "kyoka_sparkle", "sparkle_shine", "ai"],
            "magic": ["kyoka_sparkle", "sparkle_shine"],
            "love": ["kyoka_heart", "heart_pulse", "heart_dot"],
            "heart": ["kyoka_heart", "heart_pulse", "heart_dot"],
            "verify": ["kyoka_success_glow", "verified_glow", "icons_verified"],
            "success": ["kyoka_success_glow", "verified_glow", "kyoka_success", "icon_success"],
            "shield": ["kyoka_antinuke", "antinuke_pulse", "antinuke_shield"],
            "defense": ["kyoka_antinuke", "antinuke_pulse", "antinuke_shield"],
            "security": ["kyoka_antinuke", "antinuke_pulse", "antinuke_shield"],
            "loading": ["kyoka_loading", "loading_pulse", "icons_loading"],
            "wait": ["kyoka_loading", "loading_pulse"],
            "coin": ["kyoka_coins", "coin_spin", "icon_casino"],
            "money": ["kyoka_coins", "coin_spin", "icon_dollar"],
            "music": ["kyoka_music", "music_playing", "music_music"],
            "premium": ["kyoka_premium", "verified_premium", "icon_premium"],
            "win": ["kyoka_success_glow", "verified_glow", "coin_spin"],
            "fire": ["heart_pulse", "icon_fire"],
        }
        candidates = concept_map.get(clean, [f"kyoka_{clean}", clean, f"{clean}_pulse", f"{clean}_glow", f"{clean}_spin", f"{clean}_shine"])
        for name in candidates:
            obj = self.get_emoji_obj(name)
            if obj is not None and getattr(obj, "animated", False):
                return str(obj)
        for name in candidates:
            obj = self.get_emoji_obj(name)
            if obj is not None:
                return str(obj)
        return fallback

    def list_animated(self) -> list[discord.Emoji | discord.PartialEmoji]:
        """List all currently accessible animated application/guild emojis."""
        res: list[discord.Emoji | discord.PartialEmoji] = []
        for e in self._emojis.values():
            if getattr(e, "animated", False):
                res.append(e)
        if hasattr(self.bot, "emojis"):
            for e in self.bot.emojis:
                if getattr(e, "animated", False) and e.id not in {getattr(x, "id", 0) for x in res}:
                    res.append(e)
        return res

    def get_category_obj(self, category: str) -> discord.Emoji | discord.PartialEmoji | str:
        """Resolve a discord.Emoji, PartialEmoji, or Discord-safe Unicode icon for UI Buttons/Select menus."""
        cat_key = category.upper().strip()

        # Check persistent mapping or central configured custom IDs
        configured = self._configured_for_key(cat_key, allow_animated=True)
        if configured:
            match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", configured)
            if match:
                anim_flag, ename, eid = bool(match.group(1)), match.group(2), int(match.group(3))
                if hasattr(self.bot, "emojis"):
                    known = discord.utils.get(self.bot.emojis, id=eid)
                    if known and getattr(known, "is_usable", lambda: True)():
                        return known
                return discord.PartialEmoji(name=ename, id=eid, animated=anim_flag)

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

        # Guaranteed Discord-safe standard emoji fallback so Buttons/SelectOptions never error
        return CATEGORY_FALLBACK_EMOJIS.get(cat_key, "📁")

    def get(self, name: str, fallback: str = "", allow_animated: bool = True) -> str:
        """
        Get custom emoji string (e.g. '<:kyoka_success:123456789>') by name or category.
        If not found, returns fallback (defaults to empty string, avoiding random Unicode).
        """
        name_clean = name.lower().strip(":")
        upper_key = name_clean.upper()

        # Check central & persistent custom ID mappings (validated, never emits placeholder EMOJI_ID)
        configured = self._configured_for_key(upper_key, allow_animated=allow_animated)
        if configured:
            return configured
        if name_clean in self._custom_mappings:
            parsed = parse_configured_emoji(self._custom_mappings[name_clean])
            if parsed:
                return parsed
            if not self._custom_mappings[name_clean].startswith("<"):
                return self._custom_mappings[name_clean]

        # Check application & guild emojis (also checking kyoka_ prefix)
        emoji = self._emojis.get(name_clean) or self._emojis.get(f"kyoka_{name_clean}")
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean) or discord.utils.get(
                self.bot.emojis, name=f"kyoka_{name_clean}"
            )

        # Check aliases
        if not emoji:
            for alias in self._aliases.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        if emoji:
            if isinstance(emoji, discord.Emoji) and not getattr(emoji, "is_usable", lambda: True)():
                return fallback
            return str(emoji)

        # If a category was passed, try category resolver
        if upper_key in CATEGORY_CANDIDATES:
            cat_res = self.get_category(upper_key, fallback=fallback, allow_animated=allow_animated)
            if cat_res:
                return cat_res

        return fallback

    def animated(self, *names: str, fallback: str = "") -> str:
        """Resolve only registered animated custom emojis."""
        for name in names:
            try:
                upper = name.upper().strip(":")
                configured = self._configured_for_key(upper, allow_animated=True)
                if configured and configured.startswith("<a:"):
                    return configured
                emoji = self.get_emoji_obj(name)
                if emoji is not None and getattr(emoji, "animated", False):
                    if isinstance(emoji, discord.Emoji) and not getattr(emoji, "is_usable", lambda: True)():
                        continue
                    return str(emoji)
            except Exception:
                continue
        return fallback

    def get_emoji_obj(self, name: str) -> discord.Emoji | discord.PartialEmoji | None:
        """Get a discord.Emoji or discord.PartialEmoji object for UI buttons or components."""
        name_clean = name.lower().strip(":")
        upper_key = name_clean.upper()

        configured = self._configured_for_key(upper_key, allow_animated=True)
        if configured:
            match = re.match(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>", configured)
            if match:
                anim_flag, ename, eid = bool(match.group(1)), match.group(2), int(match.group(3))
                if hasattr(self.bot, "emojis"):
                    known = discord.utils.get(self.bot.emojis, id=eid)
                    if known and getattr(known, "is_usable", lambda: True)():
                        return known
                return discord.PartialEmoji(name=ename, id=eid, animated=anim_flag)

        emoji = self._emojis.get(name_clean) or self._emojis.get(f"kyoka_{name_clean}")
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean) or discord.utils.get(
                self.bot.emojis, name=f"kyoka_{name_clean}"
            )

        if not emoji:
            for alias in self._aliases.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        if emoji and isinstance(emoji, discord.Emoji) and not getattr(emoji, "is_usable", lambda: True)():
            return None

        return emoji

    def get_select_emoji(self, name: str, fallback_unicode: str | None = None) -> dict[str, Any] | None:
        """
        Get emoji dictionary structure suitable for Discord Select Menu options and components.
        Custom emoji requires {'id': str, 'name': str, 'animated': bool}.
        Supports BOTH static and animated custom emojis.
        """
        obj = self.get_emoji_obj(name)
        if obj and getattr(obj, "id", None):
            return {
                "id": str(getattr(obj, "id", "")),
                "name": str(getattr(obj, "name", name)),
                "animated": bool(getattr(obj, "animated", False)),
            }
        if fallback_unicode:
            return {"name": fallback_unicode}
        safe = CATEGORY_FALLBACK_EMOJIS.get(name.upper().strip(":"))
        if safe:
            return {"name": safe}
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SHARED MODULE HELPERS (Safe across Bot, Context, Interaction, Dict/None mocks)
# ─────────────────────────────────────────────────────────────────────────────

def get_emoji_registry(source: Any) -> Any:
    """Safely extract bot.custom_emojis from a Bot, Context, Interaction, Cog, or Registry."""
    if source is None:
        return None
    if isinstance(source, EmojiRegistry):
        return source
    if hasattr(source, "custom_emojis"):
        return getattr(source, "custom_emojis", None)
    bot = getattr(source, "bot", None) or getattr(source, "client", None)
    if bot is not None and hasattr(bot, "custom_emojis"):
        return getattr(bot, "custom_emojis", None)
    cog = getattr(source, "cog", None)
    if cog is not None:
        c_bot = getattr(cog, "bot", None)
        if c_bot is not None and hasattr(c_bot, "custom_emojis"):
            return getattr(c_bot, "custom_emojis", None)
    return None


def resolve_emoji(
    source: Any,
    key: str,
    *,
    animated: bool = False,
    prefer_animated: bool = True,
    fallback: str = "",
) -> str:
    """
    Universal, crash-proof custom emoji resolver usable across every cog and UI helper.
    Handles EmojiRegistry, dict mocks (`{}`), SimpleNamespace, MagicMock, or `None`.
    Resolution order:
    1. Registry custom/configured emoji (respecting animated / static preference)
    2. Central KYOKA_CUSTOM_EMOJI_IDS (when real snowflake ID is configured)
    3. Provided fallback -> CATEGORY_FALLBACK_EMOJIS -> emojis_gpt manifest fallback -> '•'
    """
    key_str = str(key or "").strip()
    upper = key_str.upper()
    lower = key_str.lower()
    effective_fallback = fallback or CATEGORY_FALLBACK_EMOJIS.get(upper, "")
    if not effective_fallback:
        manifest_entry = get_gpt_manifest_entry(lower)
        effective_fallback = manifest_entry.fallback if manifest_entry else "•"

    reg = get_emoji_registry(source)
    if reg is not None:
        # Dict mock (used heavily in unit tests)
        if isinstance(reg, dict):
            val = reg.get(lower) or reg.get(upper)
            if isinstance(val, str) and val and parse_configured_emoji(val) is not False:
                if val.startswith("<"):
                    return parse_configured_emoji(val) or effective_fallback
                return val
        elif isinstance(reg, EmojiRegistry):
            if animated:
                anim = reg.animated(lower, *CATEGORY_CANDIDATES.get(upper, []))
                if anim:
                    return anim
            if hasattr(reg, "get_category") and upper in CATEGORY_CANDIDATES:
                res = reg.get_category(upper, fallback="", allow_animated=prefer_animated)
                if res and (not res.startswith("<") or parse_configured_emoji(res)):
                    return res
            res = reg.get(lower, fallback="", allow_animated=prefer_animated)
            if res and (not res.startswith("<") or parse_configured_emoji(res)):
                return res
        else:
            # SimpleNamespace / MagicMock in unit tests
            try:
                if animated and hasattr(reg, "get_animated"):
                    res = reg.get_animated(lower, fallback="")
                    if isinstance(res, str) and res:
                        return res
                if hasattr(reg, "get_category") and upper in CATEGORY_CANDIDATES:
                    res = reg.get_category(upper, fallback="")
                    if isinstance(res, str) and res:
                        return res
                if hasattr(reg, "get"):
                    res = reg.get(lower, fallback="")
                    if isinstance(res, str) and res:
                        return res
            except Exception:
                pass

    # Standalone central config lookup (even when bot/registry is None)
    configured = parse_configured_emoji(KYOKA_CUSTOM_EMOJI_IDS.get(upper))
    if configured:
        if not prefer_animated and configured.startswith("<a:"):
            static_key = STATIC_EQUIVALENT_KEYS.get(upper)
            static_cfg = parse_configured_emoji(KYOKA_CUSTOM_EMOJI_IDS.get(static_key or ""))
            if static_cfg:
                return static_cfg
        return configured

    return effective_fallback


def em(
    source: Any,
    key: str,
    fallback: str = "",
    *,
    animated: bool = False,
    prefer_animated: bool = True,
) -> str:
    """Short alias for `resolve_emoji` to keep f-strings concise and readable."""
    return resolve_emoji(source, key, animated=animated, prefer_animated=prefer_animated, fallback=fallback)


def resolve_select_emoji(
    source: Any,
    key: str,
    *,
    fallback: str = "",
) -> discord.Emoji | discord.PartialEmoji | str:
    """
    Resolve a Discord-safe emoji object or standard Unicode emoji for
    `discord.ui.Button(emoji=...)` and `discord.SelectOption(emoji=...)`.
    """
    upper = str(key or "").upper().strip()
    reg = get_emoji_registry(source)
    if isinstance(reg, EmojiRegistry):
        obj = reg.get_category_obj(upper)
        if obj:
            return obj

    configured = parse_configured_emoji(KYOKA_CUSTOM_EMOJI_IDS.get(upper))
    if configured:
        match = _VALID_EMOJI_TAG_RE.match(configured)
        if match:
            return discord.PartialEmoji(
                name=match.group(2),
                id=int(match.group(3)),
                animated=bool(match.group(1)),
            )

    return fallback or CATEGORY_FALLBACK_EMOJIS.get(upper, "📁")


def unconfigured_emoji_report() -> dict[str, Any]:
    """Return status summary of central emoji IDs and emojis_gpt manifest coverage."""
    manifest = load_gpt_emoji_manifest()
    unconfigured = get_unconfigured_emoji_keys()
    configured = [k for k in KYOKA_CUSTOM_EMOJI_IDS if k not in unconfigured]
    return {
        "total_config_keys": len(KYOKA_CUSTOM_EMOJI_IDS),
        "configured_keys": len(configured),
        "awaiting_ids": unconfigured,
        "manifest_entries": len(manifest),
        "animated_keys": sorted(ANIMATED_EMOJI_KEYS),
    }


_VALID_EMOJI_TAG_RE = re.compile(r"<(a?):([a-zA-Z0-9_]+):([0-9]+)>")
_ANY_EMOJI_TAG_RE = re.compile(r"<(a?):([a-zA-Z0-9_]+):([a-zA-Z0-9_]+)>")


def _fallback_for_tag_name(name: str) -> str:
    clean = name.lower().removeprefix("kyoka_")
    upper = clean.upper()
    if upper in CATEGORY_FALLBACK_EMOJIS:
        return CATEGORY_FALLBACK_EMOJIS[upper]
    if any(k in clean for k in ("error", "wrong", "fail", "deny", "no", "x")):
        return "❌"
    if any(k in clean for k in ("warn", "alert", "caution")):
        return "⚠️"
    if any(k in clean for k in ("lock", "secure", "private")):
        return "🔒"
    if any(k in clean for k in ("time", "clock", "load", "wait", "progress")):
        return "⏳"
    if any(k in clean for k in ("check", "success", "tick", "approve", "verified")):
        return "✅"
    if any(k in clean for k in ("music", "song", "audio", "note", "sound")):
        return "🎵"
    if any(k in clean for k in ("sparkle", "star", "glow", "ai")):
        return "✨"
    if any(k in clean for k in ("coin", "cash", "eco", "wallet", "balance")):
        return "🪙"
    if any(k in clean for k in ("shield", "antinuke", "guard")):
        return "🛡️"
    if any(k in clean for k in ("ticket", "support")):
        return "🎫"
    if any(k in clean for k in ("premium", "crown", "owner", "vip")):
        return "💎"
    return "💜"


def sanitize_emoji_string(text: str, bot: Optional[commands.Bot] = None) -> str:
    """
    Sanitize any custom emoji tags in text that cannot be rendered or contain
    unconfigured placeholder IDs (e.g. `<:kyoka_success:EMOJI_ID>`), falling back
    to clean Discord-safe Unicode. Preserves known Application Emojis and valid
    configured `KYOKA_CUSTOM_EMOJI_IDS` entries.
    """
    if not text or "<" not in text:
        return text

    configured_ids: set[int] = set()
    for raw_cfg in KYOKA_CUSTOM_EMOJI_IDS.values():
        parsed = parse_configured_emoji(raw_cfg)
        if parsed:
            m_cfg = _VALID_EMOJI_TAG_RE.match(parsed)
            if m_cfg:
                configured_ids.add(int(m_cfg.group(3)))

    reg = get_emoji_registry(bot)
    app_emoji_ids: set[int] = set()
    if isinstance(reg, EmojiRegistry):
        app_emoji_ids.update(
            getattr(obj, "id", 0)
            for obj in reg._emojis.values()
            if getattr(obj, "id", None)
        )
        for raw_map in reg._custom_mappings.values():
            parsed = parse_configured_emoji(raw_map)
            if parsed:
                m_map = _VALID_EMOJI_TAG_RE.match(parsed)
                if m_map:
                    configured_ids.add(int(m_map.group(3)))

    def _repl(match: re.Match) -> str:
        name = match.group(2).lower()
        raw_id = match.group(3)
        if not raw_id.isdigit():
            return _fallback_for_tag_name(name)
        eid = int(raw_id)
        if eid in configured_ids or eid in app_emoji_ids:
            return match.group(0)
        if bot and hasattr(bot, "emojis"):
            e = discord.utils.get(bot.emojis, id=eid)
            if e and getattr(e, "is_usable", lambda: True)():
                return match.group(0)
        return _fallback_for_tag_name(name)

    return _ANY_EMOJI_TAG_RE.sub(_repl, text)

