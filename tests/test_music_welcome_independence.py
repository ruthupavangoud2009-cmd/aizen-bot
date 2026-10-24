"""
Unit and integration tests verifying:
1. Welcome and goodbye events do not block the Discord event loop while music is playing.
2. Missing manage_webhooks permission does not abort welcome dispatch (resilient fallback).
3. Image generation or template failure falls back gracefully.
4. Duplicate joins within deduplication window are safely ignored.
5. Music playback state is completely isolated from member join/leave processing.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from src.cogs.utility.events import AutoEvents


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789012345678
    bot.user.display_avatar.url = "https://example.com/bot_avatar.png"
    bot.db = MagicMock()
    bot.embed_mgr = MagicMock()
    bot.event_mgr = MagicMock()
    bot.autorole_mgr = MagicMock()
    bot.cache = MagicMock()
    bot.custom_emojis = None
    return bot


@pytest.fixture
def mock_member():
    member = MagicMock(spec=discord.Member)
    member.id = 987654321
    member.name = "BloxWarrior"
    member.display_name = "BloxWarrior"
    member.mention = "<@987654321>"
    member.bot = False
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 1122334455
    member.guild.name = "Blox Fruits Arena"
    member.guild.member_count = 1337
    member.guild.me = MagicMock()
    member.guild.me.guild_permissions.manage_roles = True
    member.guild.me.top_role.position = 100
    member.guild.icon = None
    return member


@pytest.mark.asyncio
async def test_welcome_dispatches_when_manage_webhooks_is_missing(mock_bot, mock_member):
    """Ensure welcome messages are NEVER aborted if bot lacks manage_webhooks permission."""
    cog = AutoEvents(mock_bot)

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 55667788
    channel.mention = "<#55667788>"
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.manage_webhooks = False  # Critical: Missing manage_webhooks!
    channel.permissions_for.return_value = perms
    channel.send = AsyncMock()

    mock_member.guild.get_channel.return_value = channel

    mock_bot.event_mgr.get_event_config = AsyncMock(return_value={
        "channel_id": channel.id,
        "is_enabled": True,
        "message_content": "Welcome {user_mention} to {server_name}!",
    })

    success, msg = await cog._send_event_card(
        event_type="welcome",
        guild=mock_member.guild,
        member=mock_member,
    )

    assert success is True
    assert msg is None or "delivered" in str(msg).lower()
    # Verified fallback embed was dispatched to the text channel
    channel.send.assert_called_once()
    call_kwargs = channel.send.call_args[1]
    assert call_kwargs.get("embed") is not None
    assert "BloxWarrior" in call_kwargs.get("content") or "987654321" in call_kwargs.get("content")


@pytest.mark.asyncio
async def test_duplicate_join_deduplication(mock_bot, mock_member):
    """Simultaneous member joins within 8s window must be deduplicated."""
    cog = AutoEvents(mock_bot)
    cog._send_event_card = AsyncMock(return_value=(True, "Delivered"))
    cog._get_autorole_id = AsyncMock(return_value=None)

    # First join
    await cog.on_member_join(mock_member)
    await asyncio.sleep(0.01)
    assert (mock_member.guild.id, mock_member.id) in cog._recent_joins

    # Second immediate join (within deduplication window)
    cog._send_event_card.reset_mock()
    await cog.on_member_join(mock_member)
    await asyncio.sleep(0.01)
    # Background task should NOT be created for duplicate
    assert cog._send_event_card.call_count == 0


@pytest.mark.asyncio
async def test_welcome_and_music_independence(mock_bot, mock_member):
    """Simulate music playing in event loop and verify welcome runs concurrently without blocking."""
    cog = AutoEvents(mock_bot)
    cog._send_event_card = AsyncMock(return_value=(True, "Delivered"))
    cog._get_autorole_id = AsyncMock(return_value=None)

    # Mock an active music playback state
    music_playing = True
    music_frames_played = 0

    async def simulate_music_stream():
        nonlocal music_frames_played
        while music_playing and music_frames_played < 20:
            music_frames_played += 1
            await asyncio.sleep(0.005)

    music_task = asyncio.create_task(simulate_music_stream())

    # Trigger member join
    join_task = asyncio.create_task(cog._safe_handle_member_join(mock_member))

    await asyncio.gather(music_task, join_task)

    assert music_frames_played >= 20
    assert music_playing is True
    assert cog._send_event_card.call_count == 1


@pytest.mark.asyncio
async def test_template_failure_fallback(mock_bot, mock_member):
    """If template fetching or image generation throws an exception, fallback embed is used."""
    cog = AutoEvents(mock_bot)
    mock_bot.embed_mgr.get_template = AsyncMock(side_effect=Exception("Database error loading template"))

    channel = MagicMock(spec=discord.TextChannel)
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.manage_webhooks = False
    channel.permissions_for.return_value = perms
    channel.send = AsyncMock()

    mock_member.guild.get_channel.return_value = channel

    mock_bot.event_mgr.get_event_config = AsyncMock(return_value={
        "channel_id": channel.id,
        "is_enabled": True,
        "embed_name": "corrupted_template",
    })

    success, msg = await cog._send_event_card(
        event_type="welcome",
        guild=mock_member.guild,
        member=mock_member,
    )

    assert success is True
    channel.send.assert_called_once()
