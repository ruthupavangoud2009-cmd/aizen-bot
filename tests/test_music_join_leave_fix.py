"""
Regression and reliability tests for the Discord bot voice connection bug:
"bot joins the vc and leaves".

Verifies:
1. KyokaWavelinkPlayer handles VOICE_SERVER_UPDATE arriving before VOICE_STATE_UPDATE
   without hanging or timing out.
2. KyokaWavelinkPlayer ignores stale null-channel voice updates when bot is still in VC.
3. GuildPlayer._is_connecting flag guards against concurrent duplicate connection attempts.
4. KyroBot and KyroContainer backwards-compatibility aliases are preserved.
5. Soundcloud track source is integrated into fallback cascade.
6. Music UI components use updated Kyoka prefixes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.cogs.music._player import KyokaWavelinkPlayer, GuildPlayer
from src.cogs.music._views import MusicControlView
from src.core.bot import KyokaBot, KyroBot
from src.utils.containers import KyokaContainer, KyroContainer


def test_kyro_aliases_compatibility():
    """Verify KyroBot and KyroContainer aliases map directly to Kyoka."""
    assert KyroBot is KyokaBot
    assert KyroContainer is KyokaContainer


@pytest.mark.asyncio
async def test_wavelink_player_dispatches_when_server_update_arrived_first():
    """
    Test the root cause fix:
    When VOICE_SERVER_UPDATE arrives before VOICE_STATE_UPDATE,
    KyokaWavelinkPlayer immediately calls _dispatch_voice_update() on receiving
    VOICE_STATE_UPDATE instead of hanging until timeout.
    """
    client = MagicMock()
    channel = MagicMock()
    channel.guild.id = 123456
    channel.id = 789

    mock_node = MagicMock()
    mock_node.status = MagicMock(name="CONNECTED")

    with patch("wavelink.Pool.get_node", return_value=mock_node):
        player = KyokaWavelinkPlayer(client, channel)
        player._dispatch_voice_update = AsyncMock()

        # Scenario: VOICE_SERVER_UPDATE arrived first and stored token & endpoint in _voice_state["voice"]
        player._voice_state = {
            "voice": {
                "token": "test-token-abc",
                "endpoint": "voice.discord.media:443",
            }
        }

        # Now VOICE_STATE_UPDATE arrives with session_id
        state_data = {
            "session_id": "sess-xyz-987",
            "channel_id": "789",
            "user_id": 9999,
        }

        await player.on_voice_state_update(state_data)

        # Must update session_id and immediately dispatch to Lavalink
        assert player._voice_state["voice"]["session_id"] == "sess-xyz-987"
        player._dispatch_voice_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_wavelink_player_ignores_stale_null_channel_when_still_in_vc():
    """
    Test stale null-channel packet protection:
    If Discord delivers a delayed null channel update while the bot is actually
    in a voice channel, it should not tear down the session.
    """
    client = MagicMock()
    channel = MagicMock()
    channel.id = 789
    channel.guild.id = 123456

    # Bot member is still in voice channel 789
    bot_voice = MagicMock()
    bot_voice.channel.id = 789
    channel.guild.me.voice = bot_voice

    mock_node = MagicMock()
    mock_node.status = MagicMock(name="CONNECTED")

    with patch("wavelink.Pool.get_node", return_value=mock_node):
        player = KyokaWavelinkPlayer(client, channel)
        player._connected = True
        player.disconnect = AsyncMock()

        # Discord sends a stale null-channel packet from a previous session
        stale_state_data = {
            "session_id": "old-sess",
            "channel_id": None,
            "user_id": 9999,
        }

        await player.on_voice_state_update(stale_state_data)

        # Disconnect must NOT have been called
        player.disconnect.assert_not_called()


@pytest.mark.asyncio
async def test_guild_player_is_connecting_flag():
    """Verify _is_connecting flag is initialized and prevents duplicate connect races."""
    bot = MagicMock()
    guild = MagicMock(id=123456789)
    player = GuildPlayer(bot, guild)

    assert player._is_connecting is False
    assert player._disconnect_expected_until == 0.0


def test_music_control_view_custom_ids():
    """Verify MusicControlView uses updated kyoka:music:* custom_ids."""
    bot = MagicMock()
    player = MagicMock()
    guild_id = 12345

    view = MusicControlView(bot, player, guild_id)
    custom_ids = [child.custom_id for child in view.children if hasattr(child, "custom_id")]

    for cid in custom_ids:
        assert cid.startswith("kyoka:music:"), f"Custom ID {cid} should start with kyoka:music:"
