import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.cogs.utility.youtube_pinger import YouTubeLivePinger

@pytest.mark.asyncio
async def test_youtube_pinger_direct_channel_id():
    bot_mock = MagicMock()
    bot_mock.db = MagicMock()
    pinger = YouTubeLivePinger(bot_mock)
    pinger.live_monitor_loop.cancel()  # Don't run background task during test

    # Test direct UC channel ID regex resolution
    ch_id, name, handle = await pinger.resolve_channel_info("UC1234567890123456789012")
    assert ch_id == "UC1234567890123456789012"
    if pinger._session and not pinger._session.closed:
        await pinger._session.close()


@pytest.mark.asyncio
async def test_youtube_pinger_announcement_dispatch():
    bot_mock = MagicMock()
    bot_mock.db = MagicMock()
    bot_mock.custom_emojis = {}

    guild_mock = MagicMock(spec=discord.Guild)
    channel_mock = MagicMock(spec=discord.TextChannel)
    channel_mock.name = "announcements"
    role_mock = MagicMock(spec=discord.Role)
    role_mock.mention = "<@&99999>"

    guild_mock.get_channel.return_value = channel_mock
    guild_mock.get_role.return_value = role_mock
    bot_mock.get_guild.return_value = guild_mock

    pinger = YouTubeLivePinger(bot_mock)
    pinger.live_monitor_loop.cancel()

    sub_data = {
        "guild_id": 123,
        "discord_channel_id": 456,
        "ping_role_id": 99999,
        "yt_channel_name": "KyokaGaming",
        "custom_message": "{role} 🔴 **{channel}** went LIVE! {url}",
    }

    with patch("src.cogs.utility.youtube_pinger.send_container_response", new=AsyncMock()) as mock_send:
        await pinger.dispatch_live_announcement(
            sub=sub_data,
            video_id="dQw4w9WgXcQ",
            title="EPIC STREAM!",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        )
        mock_send.assert_awaited_once()
        args, kwargs = mock_send.call_args
        assert channel_mock == args[0]
        content_sent = kwargs.get("content", "")
        assert "<@&99999>" in content_sent
        assert "KyokaGaming" in content_sent
        assert "dQw4w9WgXcQ" in content_sent
