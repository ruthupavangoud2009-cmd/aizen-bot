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


def test_select_best_playable_prioritizes_official_over_covers_and_loops():
    """Verify select_best_playable picks the official topic release over covers and 10-hour loops."""
    from src.cogs.music._extractor import select_best_playable
    t1 = MagicMock(title="Taare (Cover)", author="Cover Artist", length=180000, is_stream=False)
    t2 = MagicMock(title="Taare", author="Farak - Topic", length=155000, is_stream=False)
    t3 = MagicMock(title="Taare 10 Hours Loop", author="Meme Channel", length=36000000, is_stream=False)

    best = select_best_playable([t1, t2, t3], "Taare")
    assert best is t2


def test_youtube_and_spotify_url_handling():
    """Verify that is_playlist_url correctly distinguishes tracks vs playlists."""
    from src.cogs.music._extractor import is_playlist_url, YOUTUBE_URL_REGEX

    # Tracks must NOT be classified as playlists
    assert is_playlist_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is False
    assert is_playlist_url("https://open.spotify.com/intl-es/track/4cOdK2wGLETKBW3PvgPWqT") is False
    assert is_playlist_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT") is False
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert is_playlist_url("https://youtu.be/dQw4w9WgXcQ") is False
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ") is False

    # Actual playlists must be classified as playlists
    assert is_playlist_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
    assert is_playlist_url("https://open.spotify.com/album/4eLPsYPBmXABThSJ821sqY") is True
    assert is_playlist_url("https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj") is True

    # YouTube URL regex extraction
    m1 = YOUTUBE_URL_REGEX.search("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RD123")
    assert m1 is not None and m1.group(1) == "dQw4w9WgXcQ"

    m2 = YOUTUBE_URL_REGEX.search("https://youtu.be/dQw4w9WgXcQ?si=abc123xyz")
    assert m2 is not None and m2.group(1) == "dQw4w9WgXcQ"


def test_parse_time_to_seconds():
    """Verify parse_time_to_seconds handles mm:ss, hh:mm:ss, integer seconds, and human durations."""
    from src.cogs.music._commands.controls import parse_time_to_seconds

    assert parse_time_to_seconds("1:30") == 90
    assert parse_time_to_seconds("02:45") == 165
    assert parse_time_to_seconds("1:10:20") == 4220
    assert parse_time_to_seconds("90") == 90
    assert parse_time_to_seconds("90s") == 90
    assert parse_time_to_seconds("2m30s") == 150
    assert parse_time_to_seconds("1h5m") == 3900
    assert parse_time_to_seconds("invalid") is None
    assert parse_time_to_seconds("") is None


def test_wavelink_filters_integration():
    """Verify that Wavelink filter objects configure timescale, rotation, and equalizer payloads properly."""
    import wavelink

    # Nightcore
    f_nc = wavelink.Filters()
    f_nc.timescale.set(speed=1.25, pitch=1.25)
    assert f_nc.timescale.payload == {"speed": 1.25, "pitch": 1.25}

    # Vaporwave
    f_vw = wavelink.Filters()
    f_vw.timescale.set(speed=0.85, pitch=0.85)
    assert f_vw.timescale.payload == {"speed": 0.85, "pitch": 0.85}

    # 8D Spatial Audio
    f_8d = wavelink.Filters()
    f_8d.rotation.set(rotation_hz=0.2)
    assert f_8d.rotation.payload == {"rotationHz": 0.2}

    # Bass Boost
    f_bb = wavelink.Filters()
    f_bb.equalizer.set(bands=[{"band": 0, "gain": 0.35}, {"band": 1, "gain": 0.30}])
    eq_payload = f_bb.equalizer.payload
    assert eq_payload[0]["gain"] == 0.35
    assert eq_payload[1]["gain"] == 0.30


@pytest.mark.asyncio
async def test_lavalink_websocket_check_accepts_stats_and_ready_opcodes():
    """Verify check_websocket accepts both 'ready' and 'stats' opcodes without false-failing the node."""
    import aiohttp
    import json
    from src.core.lavalink import check_websocket

    class FakeWS:
        def __init__(self, op_name: str):
            self.op_name = op_name
            self.closed = False

        async def receive(self):
            class Msg:
                type = aiohttp.WSMsgType.TEXT
                data = json.dumps({"op": self.op_name, "players": 0})
            return Msg()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.closed = True

    class FakeSession:
        def __init__(self, op_name: str):
            self.op_name = op_name

        def ws_connect(self, *args, **kwargs):
            return FakeWS(self.op_name)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    # Op 'ready' must succeed
    with patch("aiohttp.ClientSession", return_value=FakeSession("ready")):
        ok, reason = await check_websocket("http://localhost:2333", "pass")
        assert ok is True, f"Ready op must be accepted: {reason}"

    # Op 'stats' must also succeed (does not falsely reject connected node)
    with patch("aiohttp.ClientSession", return_value=FakeSession("stats")):
        ok, reason = await check_websocket("http://localhost:2333", "pass")
        assert ok is True, f"Stats op must be accepted: {reason}"


@pytest.mark.asyncio
async def test_developer_no_prefix_cog_authorizes_staff_and_owner():
    """Verify developer no_prefix cog allows bot staff and owner to manage no-prefix access."""
    from src.cogs.developer.no_prefix import NoPrefix
    from src.security.owner import OWNER_ID, add_bot_staff, remove_bot_staff

    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.fetch_all = AsyncMock(return_value=[])
    cog = NoPrefix(bot)

    # 1. Standard user is blocked
    ctx_norm = MagicMock(author=MagicMock(id=12345), interaction=None)
    ctx_norm.send = AsyncMock()
    await cog.noprefix.callback(cog, ctx_norm, action="list")
    assert "Only the bot owner or authorized bot staff" in ctx_norm.send.call_args[0][0]

    # 2. Hardcoded Primary Owner is permitted
    ctx_owner = MagicMock(author=MagicMock(id=OWNER_ID), interaction=None)
    ctx_owner.send = AsyncMock()
    await cog.noprefix.callback(cog, ctx_owner, action="list")
    assert "No-Prefix Access Allowlist" in ctx_owner.send.call_args[0][0]

    # 3. Authorized Bot Staff is permitted
    staff_id = 888888888
    add_bot_staff(staff_id)
    try:
        ctx_staff = MagicMock(author=MagicMock(id=staff_id), interaction=None)
        ctx_staff.send = AsyncMock()
        await cog.noprefix.callback(cog, ctx_staff, action="list")
        assert "No-Prefix Access Allowlist" in ctx_staff.send.call_args[0][0]
    finally:
        remove_bot_staff(staff_id)
