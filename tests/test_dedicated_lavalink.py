import asyncio
import pytest
from src.core.config import Config
from src.core.lavalink import candidates, create_lavalink_node, probe_node, connect_lavalink_node


def test_dedicated_lavalink_config():
    """Verify that user's exact Lavalink credentials and isolation settings are configured."""
    assert Config.LAVALINK_HOST == "kyoka-lavalink.onrender.com"
    assert Config.LAVALINK_PORT == 443
    assert Config.LAVALINK_SECURE is True
    assert Config.LAVALINK_IDENTIFIER == "kyoka-lavalink-v4"
    assert Config.LAVALINK_PASSWORD == "onlyforkyoka"
    assert Config.LAVALINK_AUTO_DISCOVER is False
    assert Config.LAVALINK_FALLBACK_URIS == ""
    assert Config.LAVALINK_URI == "https://kyoka-lavalink.onrender.com:443"


def test_candidates_isolation():
    """Verify candidates list contains only the primary dedicated node and no fallbacks."""
    node_candidates = candidates()
    assert len(node_candidates) == 1
    uri, pw = node_candidates[0]
    assert uri == "https://kyoka-lavalink.onrender.com:443"
    assert pw == "onlyforkyoka"


@pytest.mark.asyncio
async def test_node_smooth_streaming_parameters():
    """Verify create_lavalink_node sets heartbeat, retries, and resume timeout for 100% smooth playback."""
    node = create_lavalink_node(
        Config.LAVALINK_URI,
        Config.LAVALINK_PASSWORD,
        identifier=Config.LAVALINK_IDENTIFIER,
    )
    assert node.identifier == "kyoka-lavalink-v4"
    assert node.uri == "https://kyoka-lavalink.onrender.com:443"
    assert node.heartbeat == 15.0
    assert node._retries is None
    assert getattr(node, "_resume_timeout", getattr(node, "resume_timeout", None)) == 120
    if hasattr(node, "_session") and node._session and not node._session.closed:
        await node._session.close()


@pytest.mark.asyncio
async def test_live_lavalink_connectivity_and_probe():
    """Verify the live Render-hosted node responds to the REST health probe."""
    try:
        healthy = await probe_node(Config.LAVALINK_URI, Config.LAVALINK_PASSWORD, timeout=10.0)
        assert healthy is True, "Dedicated Lavalink node did not pass the health probe"
    except Exception as exc:
        pytest.fail(f"Failed to probe dedicated Lavalink node: {exc}")


@pytest.mark.asyncio
async def test_live_youtube_track_resolution():
    """Verify that YouTube search and track resolution works through the dedicated Lavalink node."""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": Config.LAVALINK_PASSWORD}
        url = f"{Config.LAVALINK_URI}/v4/loadtracks?identifier=ytsearch:test"
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15.0)) as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data.get("loadType") in ("search", "track", "playlist")
            assert len(data.get("data", [])) > 0


@pytest.mark.asyncio
async def test_music_commands_structure():
    """Verify play, previous, nowplaying, and stop command aliases."""
    from src.cogs.music.music import Music
    from unittest.mock import MagicMock
    mock_bot = MagicMock()
    cog = Music(mock_bot)
    cog.agent.cog_unload()

    play_cmd = cog.play
    assert "search" in play_cmd.aliases
    assert "p" in play_cmd.aliases

    stop_cmd = cog.stop
    assert "disconnect" in stop_cmd.aliases
    assert "leave" in stop_cmd.aliases

    np_cmd = cog.nowplaying
    assert "np" in np_cmd.aliases

    prev_cmd = cog.previous
    assert "prev" in prev_cmd.aliases
    assert "back" in prev_cmd.aliases

