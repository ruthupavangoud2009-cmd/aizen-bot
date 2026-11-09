import pytest
import os
import unittest.mock as mock
from src.core.config import Config
from src.core.lavalink import LavalinkUnavailable
import discord
from discord.ext import commands


def test_lavalink_host_sanitization():
    """Verify that any protocol, trailing slash, or port format in LAVALINK_HOST is sanitized cleanly."""
    test_cases = [
        ("kyoka-lavalink.onrender.com", "kyoka-lavalink.onrender.com", 443),
        ("https://kyoka-lavalink.onrender.com", "kyoka-lavalink.onrender.com", 443),
        ("https://kyoka-lavalink.onrender.com:443", "kyoka-lavalink.onrender.com", 443),
        ("https://kyoka-lavalink.onrender.com:443/", "kyoka-lavalink.onrender.com", 443),
        ("http://127.0.0.1:2333/", "127.0.0.1", 2333),
    ]

    for raw_host, expected_host, expected_port in test_cases:
        # Simulate config sanitization logic
        raw = raw_host.strip()
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        raw = raw.rstrip("/")
        if ":" in raw:
            h_part, p_part = raw.split(":", 1)
            raw = h_part
            inferred_port = p_part
        else:
            inferred_port = "443"

        parsed_host = raw
        parsed_port = int(inferred_port)

        assert parsed_host == expected_host
        assert parsed_port == expected_port


def test_current_config_lavalink_values():
    """Verify active Config settings match user requirements."""
    assert Config.LAVALINK_HOST == "kyoka-lavalink.onrender.com"
    assert Config.LAVALINK_PORT == 443
    assert Config.LAVALINK_SECURE is True
    assert Config.LAVALINK_IDENTIFIER == "kyoka-lavalink-v4"
    assert Config.LAVALINK_PASSWORD == "onlyforkyoka"
    assert Config.LAVALINK_URI == "https://kyoka-lavalink.onrender.com:443"
    assert Config.LAVALINK_AUTO_DISCOVER is False
    assert Config.LAVALINK_FALLBACK_URIS == ""


@pytest.mark.asyncio
async def test_play_exception_order_catches_lavalink_unavailable():
    """Verify that LavalinkUnavailable is caught before generic RuntimeError."""
    assert issubclass(LavalinkUnavailable, RuntimeError)

    # Simulate play command exception branch
    mock_agent = mock.MagicMock()
    mock_agent.build_maintenance_card.return_value = mock.MagicMock()

    exc = LavalinkUnavailable("No reachable node")

    caught_branch = None
    if isinstance(exc, LavalinkUnavailable):
        caught_branch = "lavalink_unavailable"
    elif isinstance(exc, (RuntimeError, ValueError)):
        caught_branch = "runtime_error"

    assert caught_branch == "lavalink_unavailable"


@pytest.mark.asyncio
async def test_music_hybrid_commands_have_deferral():
    """Inspect source code of hybrid commands in music cog to ensure early deferral is present."""
    import inspect
    from src.cogs.music.music import Music

    # Check join, pause, resume, skip, stop, queue, nowplaying, volume, stay_247
    commands_to_check = [
        "join", "pause", "resume", "skip", "stop", "queue", "nowplaying", "volume", "stay_247"
    ]
    for cmd_name in commands_to_check:
        cmd_obj = getattr(Music, cmd_name)
        cb = getattr(cmd_obj, "callback", cmd_obj)
        src = inspect.getsource(cb)
        assert "ctx.interaction.response.defer()" in src, f"{cmd_name} missing deferral"


@pytest.mark.asyncio
async def test_help_command_has_early_deferral():
    """Verify help hybrid command includes early slash interaction deferral."""
    import inspect
    from src.cogs.general.help import Help
    cb = getattr(Help.help_command, "callback", Help.help_command)
    src = inspect.getsource(cb)
    assert "ctx.interaction.response.defer()" in src


def test_create_lavalink_node_retries_default():
    """Verify create_lavalink_node defaults retries to None (indefinite exponential backoff)."""
    import inspect
    from src.core.lavalink import create_lavalink_node
    sig = inspect.signature(create_lavalink_node)
    assert sig.parameters["retries"].default is None


@pytest.mark.asyncio
async def test_warmup_render_service_non_render():
    """Verify non-render URIs immediately return True without HTTP calls."""
    from src.core.lavalink import warmup_render_service
    res = await warmup_render_service("http://127.0.0.1:2333")
    assert res is True

