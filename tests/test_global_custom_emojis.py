"""
Tests for KYOKA Global Custom Emoji Integration & `emojis_gpt/` Catalog.
Verifies:
1. Central emoji configuration & placeholder validation (no invalid markup emitted).
2. `emojis_gpt/extra_emoji_manifest.json` 60-icon catalog loading and fallbacks.
3. Static and animated custom emoji resolution + animated -> static -> Unicode fallback.
4. Safety against dict/None/MagicMock `bot.custom_emojis` in tests.
5. Cross-module integration (Response, Help, Moderation, Tickets, Music, Verification).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import discord
import pytest

from src.utils.emoji_config import (
    ANIMATED_EMOJI_KEYS,
    KYOKA_CUSTOM_EMOJI_IDS,
    get_gpt_manifest_entry,
    get_unconfigured_emoji_keys,
    load_gpt_emoji_manifest,
    parse_configured_emoji,
)
from src.utils.emojis import (
    CATEGORY_CANDIDATES,
    CATEGORY_FALLBACK_EMOJIS,
    EmojiRegistry,
    em,
    resolve_emoji,
    resolve_select_emoji,
    sanitize_emoji_string,
    unconfigured_emoji_report,
)


def test_gpt_manifest_loaded_all_60_entries():
    manifest = load_gpt_emoji_manifest()
    assert len(manifest) == 60
    for expected in ("admin", "staff", "owner", "developer", "firewall", "scan", "webhook", "api", "sync", "date"):
        entry = get_gpt_manifest_entry(expected)
        assert entry is not None
        assert entry.fallback


def test_placeholder_ids_never_emitted():
    assert parse_configured_emoji("<:kyoka_success:EMOJI_ID>") is None
    assert parse_configured_emoji("<a:kyoka_loading:EMOJI_ID>") is None
    assert parse_configured_emoji("<:kyoka_success:0>") is None
    assert parse_configured_emoji("invalid") is None
    assert parse_configured_emoji("<:kyoka_success:123456789012345678>") == "<:kyoka_success:123456789012345678>"
    assert parse_configured_emoji("<a:kyoka_loading:123456789012345678>") == "<a:kyoka_loading:123456789012345678>"

    for key in KYOKA_CUSTOM_EMOJI_IDS:
        val = resolve_emoji(None, key)
        assert val
        assert "EMOJI_ID" not in val

    cleaned = sanitize_emoji_string("<:kyoka_success:EMOJI_ID> Saved! <a:kyoka_loading:EMOJI_ID>")
    assert "EMOJI_ID" not in cleaned
    assert "✅" in cleaned
    assert "⏳" in cleaned


def test_configured_static_and_animated_resolution_with_fallback():
    bot = MagicMock()
    bot.emojis = []
    reg = EmojiRegistry(bot)
    bot.custom_emojis = reg

    with patch.dict(
        KYOKA_CUSTOM_EMOJI_IDS,
        {
            "LOADING": "<a:kyoka_loading:111222333444555666>",
            "REFRESH": "<:kyoka_refresh:111222333444555667>",
            "SUCCESS": "<:kyoka_success:111222333444555668>",
        },
    ):
        assert resolve_emoji(bot, "LOADING", animated=True) == "<a:kyoka_loading:111222333444555666>"
        # When animations disabled, falls back cleanly to static equivalent REFRESH
        assert resolve_emoji(bot, "LOADING", prefer_animated=False) == "<:kyoka_refresh:111222333444555667>"
        assert em(bot, "SUCCESS") == "<:kyoka_success:111222333444555668>"

        sel_obj = resolve_select_emoji(bot, "SUCCESS")
        assert isinstance(sel_obj, discord.PartialEmoji)
        assert sel_obj.id == 111222333444555668


def test_safe_fallback_across_dict_none_and_simplenamespace():
    assert resolve_emoji(None, "MODERATION") == CATEGORY_FALLBACK_EMOJIS["MODERATION"]
    assert resolve_emoji(SimpleNamespace(custom_emojis={}), "TICKET") == CATEGORY_FALLBACK_EMOJIS["TICKET"]
    assert resolve_emoji(SimpleNamespace(custom_emojis={"heart_dot": "•"}), "heart_dot") == "•"
    assert resolve_emoji(SimpleNamespace(custom_emojis=None), "MUSIC") == CATEGORY_FALLBACK_EMOJIS["MUSIC"]

    sel_fallback = resolve_select_emoji(SimpleNamespace(custom_emojis={}), "BACK", fallback="◀️")
    assert sel_fallback == "◀️"


def test_required_categories_and_report_populated():
    required_keys = (
        "KYOKA", "HOME", "BACK", "NEXT", "SEARCH", "HELP", "BOOK", "MODULES",
        "MODERATION", "BAN", "KICK", "MUTE", "UNMUTE", "WARN", "PURGE", "LOCK", "UNLOCK",
        "ANTI_NUKE", "SECURITY", "VERIFICATION",
        "TICKET", "TICKET_OPEN", "TICKET_CLOSE", "TICKET_CLAIM", "TRANSCRIPT", "STAFF",
        "MUSIC", "PLAY", "PAUSE", "RESUME", "STOP", "SKIP", "PREVIOUS", "QUEUE", "VOLUME", "LYRICS", "LOOP", "SHUFFLE",
        "ECONOMY", "BALANCE", "WALLET", "COINS", "SHOP", "INVENTORY", "REWARDS", "DAILY", "LEADERBOARD",
        "LEVEL", "XP", "RANK", "PROFILE", "VOUCH", "REPUTATION",
        "AI", "AI_LOADING", "AI_VOICE", "AI_PERSONALITY",
        "ROLE", "CHANNEL", "ADMIN", "SERVER", "SETTINGS", "LOGGING", "WELCOMER",
        "AFK", "REMINDER", "INFO", "STATS", "API", "DATABASE", "WEBHOOK",
        "OWNER", "DEVELOPER", "DIAGNOSTICS", "MAINTENANCE", "BUG", "PREMIUM",
        "SUCCESS", "ERROR", "WARNING", "LOADING",
    )
    for k in required_keys:
        assert k in CATEGORY_CANDIDATES, f"Missing CATEGORY_CANDIDATES entry: {k}"
        assert k in CATEGORY_FALLBACK_EMOJIS, f"Missing CATEGORY_FALLBACK_EMOJIS entry: {k}"
        assert k in KYOKA_CUSTOM_EMOJI_IDS, f"Missing KYOKA_CUSTOM_EMOJI_IDS entry: {k}"

    report = unconfigured_emoji_report()
    assert report["manifest_entries"] == 60
    assert report["total_config_keys"] >= len(required_keys)
    assert "LOADING" in report["animated_keys"]


def test_ui_views_and_responses_render_without_emoji_crashes():
    from src.ui.response import KyokaResponse
    from src.utils.ui import KyokaEmbed

    bot = MagicMock()
    bot.emojis = []
    bot.custom_emojis = EmojiRegistry(bot)

    target = MagicMock(display_name="Member", id=123, mention="<@123>")
    target.display_avatar.url = "https://example.com/a.png"
    mod = MagicMock(display_name="Mod", id=456, mention="<@456>")
    mod.display_avatar.url = "https://example.com/b.png"

    mod_resp = KyokaResponse.moderation("ban", target, mod, "Spam")
    assert mod_resp.emoji_key == "BAN"
    with patch.dict(KYOKA_CUSTOM_EMOJI_IDS, {"BAN": "<:kyoka_ban:999888777666555444>"}):
        emb = mod_resp.build_embed(bot=bot)
        assert "<:kyoka_ban:999888777666555444>" in (emb.title or "")
    emb_fb = mod_resp.build_embed(bot=bot)
    assert emb_fb.title and "EMOJI_ID" not in emb_fb.title
    assert "EMOJI_ID" not in (emb_fb.description or "")

    ui_emb = KyokaEmbed.success("Done", "Saved settings", bot=bot)
    assert "✅" in ui_emb.title or "<" in ui_emb.title
    assert "EMOJI_ID" not in ui_emb.title
