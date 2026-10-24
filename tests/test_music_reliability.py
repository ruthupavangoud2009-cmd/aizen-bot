"""
Tests for Kyoka 3.0 Music Subsystem Reliability & Error Recovery.
Verifies:
- yt-dlp timeout & multi-client configuration to prevent buffer freezing
- Stuck and loadFailed error unblocking and queue advancement
- Event listeners registration on Music cog
- Clean audio source & player lifecycle handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.cogs.music._extractor import YDL_OPTIONS
from src.cogs.music._models import Track
from src.cogs.music._player import GuildPlayer
from src.cogs.music.music import Music


def test_ydl_options_resilience_configuration():
    """Verify YDL_OPTIONS contains increased socket timeout and resilient player clients."""
    assert YDL_OPTIONS["socket_timeout"] >= 10, "Socket timeout should be >= 10s to prevent stream buffering stalls"
    extractor_args = YDL_OPTIONS.get("extractor_args", {}).get("youtube", {})
    clients = extractor_args.get("player_client", [])
    assert "android" in clients
    assert "web" in clients
    assert YDL_OPTIONS.get("ignoreerrors") is True


@pytest.mark.asyncio
async def test_music_cog_listeners_registered():
    """Verify the Music Cog defines all necessary Wavelink listeners."""
    bot = MagicMock()
    with patch("src.cogs.music._agent.tasks.loop"):
        cog = Music(bot)
        listeners = [name for name, _ in cog.get_listeners()]
        assert "on_wavelink_track_start" in listeners
        assert "on_wavelink_track_exception" in listeners
        assert "on_wavelink_track_stuck" in listeners
        assert "on_wavelink_track_end" in listeners


@pytest.mark.asyncio
async def test_stuck_track_unblocks_queue_and_calls_skip():
    """Verify on_track_end(reason='stuck') cleans voice_client and advances to next track."""
    bot = MagicMock()
    guild = MagicMock(id=123456789)
    
    player = GuildPlayer(bot, guild)
    player.voice_client = AsyncMock()
    player.voice_client.skip = AsyncMock()
    
    track1 = Track(title="Stuck Song", url="https://example.com/1", author="Artist 1", duration=180)
    track2 = Track(title="Next Good Song", url="https://example.com/2", author="Artist 2", duration=200)
    
    player.current = track1
    await player.add_track(track2)
    
    with patch.object(player, "play_track", new_callable=AsyncMock) as mock_play:
        await player.on_track_end(reason="stuck")
        
        # Verify skip was called to clean Lavalink buffer
        player.voice_client.skip.assert_awaited_once_with(force=True)
        # Verify next track popped and played
        mock_play.assert_awaited_once_with(track2)


@pytest.mark.asyncio
async def test_loadfailed_track_ends_queue_cleanly_if_empty():
    """Verify on_track_end(reason='loadFailed') cleans up state when queue is empty."""
    bot = MagicMock()
    guild = MagicMock(id=123456789)
    
    player = GuildPlayer(bot, guild)
    player.voice_client = AsyncMock()
    player.voice_client.skip = AsyncMock()
    
    track1 = Track(title="Failed Track", url="https://example.com/fail", author="Artist", duration=120)
    player.current = track1
    
    with patch.object(player, "send_queue_ended_card", new_callable=AsyncMock) as mock_ended:
        with patch.object(player, "schedule_empty_vc_timer") as mock_timer:
            await player.on_track_end(reason="loadFailed")
            
            assert player.current is None
            mock_ended.assert_awaited_once()
            mock_timer.assert_called_once()
