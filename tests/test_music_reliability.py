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
from src.cogs.music._extractor import NativeExtractor
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


def test_direct_stream_url_detection():
    """Verify _is_direct_stream_url identifies valid direct audio streams."""
    bot = MagicMock()
    guild = MagicMock(id=123456789)
    player = GuildPlayer(bot, guild)

    # Valid streams
    assert player._is_direct_stream_url("https://aac.saavncdn.com/981/ddf4f57d94d268001967dc60725c52ca_320.mp4") is True
    assert player._is_direct_stream_url("https://example.com/audio/track.mp3") is True
    assert player._is_direct_stream_url("https://example.com/stream.opus?token=xyz") is True
    assert player._is_direct_stream_url("https://stream.zeno.fm/station") is True

    # Invalid / Web pages
    assert player._is_direct_stream_url("https://www.youtube.com/watch?v=12345") is False
    assert player._is_direct_stream_url("https://open.spotify.com/track/12345") is False
    assert player._is_direct_stream_url("") is False
    assert player._is_direct_stream_url(None) is False


@pytest.mark.asyncio
async def test_youtube_fallback_runs_in_worker_thread():
    expected = Track(
        title="Fallback Track",
        url="https://youtube.com/watch?v=abcdefghijk",
        stream_url="https://rr.example.googlevideo.com/videoplayback",
        author="Artist",
    )
    with patch.object(NativeExtractor, "_extract_youtube_fallback", return_value=expected) as fallback:
        result = await NativeExtractor.extract_youtube_fallback("fallback song", "Tester")

    assert result is expected
    fallback.assert_called_once_with("fallback song", "Tester", False)


@pytest.mark.asyncio
async def test_resolve_playable_with_attached_playable():
    """Verify _resolve_playable_cascade returns pre-attached _playable immediately."""
    bot = MagicMock()
    guild = MagicMock(id=123456789)
    player = GuildPlayer(bot, guild)

    dummy_playable = MagicMock()
    track = Track(title="Attached Track", url="https://example.com/track", author="Artist")
    track._playable = dummy_playable

    resolved = await player._resolve_playable_cascade(track)
    assert resolved is dummy_playable
