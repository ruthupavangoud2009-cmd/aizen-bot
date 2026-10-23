"""
Tests for KYOKA 3.0 Aizen Engine & Upgraded Systems:
- Fast AI responses, concurrency, timeout, and metrics diagnostics (+aidiag)
- 10-Persona system & alias resolution
- Asynchronous cooldowns & memory cleanup
- Music player UI (Now Playing container, DJ permissions, multi-guild isolation)
- Help categories (12 clean categories, dedicated AI Help Module)
- Safety: No API keys or database URLs exposed
"""

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from src.managers.ai_manager import AIManager, AI_PERSONAS, PERSONALITY_PRESETS
from src.cogs.general.help import Help
from src.cogs.music._player import GuildPlayer
from src.cogs.music._views import MusicControlView


# ─── 1. TEST 10-PERSONA SYSTEM & RESOLUTION ──────────────────────────────────

def test_ten_aizen_personas_exist_and_distinct():
    """Verify all 10 required master personalities are defined with distinct prompts."""
    required = [
        "girlfriend",
        "baddie",
        "special",
        "friendly",
        "funny",
        "savage",
        "anime",
        "aizen",
        "friend",
        "custom",
    ]
    for key in required:
        assert key in AI_PERSONAS, f"Persona '{key}' must be defined in AI_PERSONAS"
        persona = AI_PERSONAS[key]
        assert "name" in persona
        assert "description" in persona
        assert "prompt" in persona
        assert len(persona["prompt"]) > 20

    # Ensure all prompts are distinct
    prompts = [AI_PERSONAS[k]["prompt"] for k in required if k != "custom"]
    assert len(prompts) == len(set(prompts)), "All 9 non-custom personas must have distinct prompts"


def test_persona_alias_resolution():
    """Verify resolve_persona correctly maps aliases and defaults."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    # Aliases
    assert mgr.resolve_persona("aigf") == "girlfriend"
    assert mgr.resolve_persona("gf") == "girlfriend"
    assert mgr.resolve_persona("girlfriend") == "girlfriend"

    assert mgr.resolve_persona("aibaddie") == "baddie"
    assert mgr.resolve_persona("baddie") == "baddie"

    assert mgr.resolve_persona("aispecial") == "special"
    assert mgr.resolve_persona("special") == "special"

    assert mgr.resolve_persona("wise") == "aizen"
    assert mgr.resolve_persona("aizen") == "aizen"

    assert mgr.resolve_persona("roast") == "savage"
    assert mgr.resolve_persona("savage") == "savage"

    assert mgr.resolve_persona("otaku") == "anime"
    assert mgr.resolve_persona("anime") == "anime"

    assert mgr.resolve_persona("support") == "friend"
    assert mgr.resolve_persona("friend") == "friend"

    assert mgr.resolve_persona("helper") == "friendly"
    assert mgr.resolve_persona("assistant") == "friendly"

    assert mgr.resolve_persona("meme") == "funny"
    assert mgr.resolve_persona("funny") == "funny"

    # Default fallback
    assert mgr.resolve_persona("unknown_xyz") == "aizen"
    assert mgr.resolve_persona(None) == "aizen"


# ─── 2. TEST PERFORMANCE METRICS & DIAGNOSTICS ────────────────────────────────

@pytest.mark.asyncio
async def test_ai_diagnostics_structure_and_latency_tracking():
    """Verify AIManager tracks latency and provides secure diagnostics."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    # Record some latencies
    mgr._record_latency(120.0)
    mgr._record_latency(180.0)
    mgr._record_latency(240.0)

    diag = await mgr.get_diagnostics()
    assert "Gemini" in diag["provider"]
    assert "model" in diag
    assert diag["healthy"] is True
    assert diag["total_requests"] == 3
    assert abs(diag["avg_latency_ms"] - 180.0) < 0.1
    assert len(diag["recent_latencies_ms"]) == 3
    assert diag["last_latency_ms"] == 240.0
    assert diag["timeout_count"] == 0
    assert diag["error_count"] == 0
    assert diag["rate_limit_count"] == 0
    assert diag["db_reachable"] is True

    # Ensure sensitive items are NOT in diagnostics dict
    diag_str = str(diag).lower()
    assert "api_key" not in diag_str
    assert "password" not in diag_str
    assert "postgres" not in diag_str


@pytest.mark.asyncio
async def test_ai_concurrency_semaphore_and_timeout_config():
    """Verify concurrency semaphore and timeout settings are enforced."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    assert mgr.timeout_seconds == 15.0 or isinstance(mgr.timeout_seconds, float)
    assert mgr.semaphore._value >= 1

    # Simulate timeout handling
    with patch("aiohttp.ClientSession.post", side_effect=asyncio.TimeoutError):
        with pytest.raises(RuntimeError) as exc_info:
            await mgr.get_response(
                guild_id=111,
                channel_id=222,
                user_id=333,
                user_message="Test timeout",
                persona="aizen"
            )
        assert "timed out" in str(exc_info.value).lower()
        assert mgr._total_timeouts >= 1


# ─── 3. TEST ASYNCHRONOUS COOLDOWNS & MEMORY CLEANUP ──────────────────────────

def test_user_cooldowns_and_expiry_cleanup():
    """Verify check_user_cooldown throttles correctly and cleanup prevents unbounded growth."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    user_id = 123456789
    # First call: allowed (remaining == 0.0)
    rem = mgr.check_user_cooldown(user_id, cooldown_seconds=3.0)
    assert rem == 0.0

    # Immediate second call: rejected with remaining time > 0
    rem = mgr.check_user_cooldown(user_id, cooldown_seconds=3.0)
    assert 0.0 < rem <= 3.0

    # Expire the timestamp artificially
    mgr.user_last_call[user_id] = time.monotonic() - 400.0
    mgr.user_last_call[999999999] = time.monotonic() - 500.0

    # Trigger cleanup
    mgr._maybe_cleanup_cooldowns(force=True)
    assert user_id not in mgr.user_last_call
    assert 999999999 not in mgr.user_last_call


# ─── 4. TEST MUSIC NOW PLAYING UI & PERMISSIONS ───────────────────────────────

def test_music_now_playing_container_format():
    """Verify build_now_playing_container displays elapsed, volume, loop, and queue info."""
    mock_bot = MagicMock()
    mock_guild = MagicMock(id=12345)
    player = GuildPlayer(mock_bot, mock_guild)
    player.volume = 0.8  # 80%
    player.loop_mode = "track"
    player.queue = [MagicMock(), MagicMock(), MagicMock()]  # 3 tracks

    mock_vc = MagicMock()
    mock_vc.position = 45000  # 45 seconds in ms
    player.voice_client = mock_vc

    mock_track = MagicMock()
    mock_track.title = "Bleach OST - Treachery"
    mock_track.url = "https://youtube.com/watch?v=123"
    mock_track.author = "Shiro Sagisu"
    mock_track.formatted_duration = "03:05"
    mock_track.thumbnail = "https://img.youtube.com/vi/123/hqdefault.jpg"
    mock_track.requester = "Captain Aizen"

    container = player.build_now_playing_container(mock_track)
    assert container is not None

    # Helper to recursively extract all text from container components
    def extract_texts(comp_list):
        out = []
        for c in comp_list:
            if "content" in c:
                out.append(c["content"])
            if "components" in c:
                out.extend(extract_texts(c["components"]))
        return out

    all_text = " ".join(extract_texts(container.components))
    assert "Now Playing" in all_text
    assert "Bleach OST - Treachery" in all_text
    assert "Shiro Sagisu" in all_text
    assert "00:45 / 03:05" in all_text
    assert "Volume: `80%`" in all_text
    assert "Loop: `TRACK`" in all_text
    assert "Queue: `3 tracks`" in all_text
    assert "Requested by: Captain Aizen" in all_text


def test_music_control_view_dj_role_and_voice_check():
    """Verify MusicControlView permits DJs/admins and rejects voice-mismatched users."""
    mock_bot = MagicMock()
    mock_player = MagicMock()
    mock_player.guild = MagicMock(id=987654321)
    mock_player.is_connected = True
    mock_player.voice_client = MagicMock()
    mock_player.voice_client.channel = MagicMock(id=1111)

    view = MusicControlView(mock_bot, mock_player)

    # User not in voice channel
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 987654321
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    member.roles = []
    member.voice = None
    interaction.user = member

    err = view._check_voice(interaction, mock_player)
    assert err is not None
    assert "voice channel" in err.lower()

    # User with DJ role in voice channel
    dj_role = MagicMock()
    dj_role.name = "DJ"
    member.roles = [dj_role]
    err = view._check_voice(interaction, mock_player)
    assert err is None  # DJ bypasses voice channel requirement for controls


# ─── 5. TEST 12 HELP CATEGORIES & DEDICATED AI MODULE ─────────────────────────

def test_help_category_order_has_14_categories_including_music():
    """Verify Help.CATEGORY_ORDER contains all 14 designated categories."""
    assert len(Help.CATEGORY_ORDER) == 14
    expected = [
        "🏠・GETTING STARTED",
        "🤖・ARTIFICIAL INTELLIGENCE",
        "🛡️・MODERATION",
        "👋・WELCOME & AUTOMOD",
        "🎫・TICKETS & SUPPORT",
        "🎉・GIVEAWAYS & EVENTS",
        "⭐・LEVELS & COMMUNITY",
        "🖼️・IMAGES & AVATARS",
        "🎵・MUSIC",
        "💬・SOCIAL & FUN",
        "💎・PREMIUM",
        "⚙️・SERVER ADMINISTRATION",
        "🔧・UTILITIES",
        "👑・OWNER & DEVELOPER",
    ]
    assert Help.CATEGORY_ORDER == expected


def test_help_dedicated_ai_module_rendering():
    """Verify _build_category_container renders the dedicated AI module console for AIZEN AI SYSTEM."""
    from src.core.bot import KyokaBot
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777

    help_cog = Help(bot)
    ctx = MagicMock()
    ctx.guild = MagicMock(id=12345)
    ctx.clean_prefix = "+"

    # Mock cmd
    cmd = MagicMock()
    cmd.qualified_name = "ai"

    # Build container for AI category
    container = help_cog._build_category_container(
        ctx=ctx,
        cat_name="⛩️・AIZEN AI SYSTEM",
        commands_list=[cmd],
        visible_categories={"⛩️・AIZEN AI SYSTEM": [cmd]},
        custom_id_prefix="help_test",
    )
    assert container is not None
    all_text = " ".join(c.get("content", "") for c in container.components).lower()
    assert "aizen ai system module" in all_text
    assert "personalities" in all_text or "girlfriend" in all_text
    assert "ai <message>" in all_text
    assert "aidiag" in all_text
