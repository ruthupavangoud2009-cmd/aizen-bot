import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.cogs.music._models import Track
from src.cogs.music._player import GuildPlayer
from src.cogs.music._commands.nowplaying import execute_nowplaying


@pytest.mark.asyncio
async def test_now_playing_does_not_send_unprompted_message():
    """Verify that automatic song transitions never send unprompted messages to chat."""
    bot = MagicMock()
    guild = MagicMock(id=112233)
    player = GuildPlayer(bot, guild)
    player.home_channel = MagicMock(spec=discord.TextChannel)
    player.controller_message = None

    track = Track(
        title="Chill Track",
        author="Lo-Fi Beats",
        url="https://youtube.com/watch?v=12345",
        duration=180,
    )

    with patch("src.cogs.music._player.send_container_response", new_callable=AsyncMock) as mock_send:
        # Automatic transition has message_to_edit=None
        await player.send_now_playing_card(track, message_to_edit=None)

        # MUST NOT post a new message to chat
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_now_playing_updates_existing_controller_message_in_place():
    """Verify that if a controller message already exists from ?nowplaying, it edits in place without new messages."""
    bot = MagicMock()
    guild = MagicMock(id=112233)
    player = GuildPlayer(bot, guild)
    player.home_channel = MagicMock(spec=discord.TextChannel)
    
    mock_msg = MagicMock(spec=discord.Message)
    player.controller_message = mock_msg

    track = Track(
        title="Next Song",
        author="Artist",
        url="https://youtube.com/watch?v=67890",
        duration=200,
    )

    with patch("src.cogs.music._player.send_container_response", new_callable=AsyncMock) as mock_send:
        with patch("src.cogs.music._player.edit_container_response", new_callable=AsyncMock) as mock_edit:
            await player.send_now_playing_card(track, message_to_edit=None)

            # Did not post any new message
            mock_send.assert_not_awaited()
            # Edited existing message in place
            mock_edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_now_playing_appears_on_explicit_command():
    """Verify that Now Playing card is sent when someone explicitly runs the ?nowplaying command."""
    bot = MagicMock()
    cog = MagicMock()
    cog.bot = bot
    guild = MagicMock(id=112233)
    player = GuildPlayer(bot, guild)
    player.voice_client = MagicMock(connected=True)
    cog.controller.get_player.return_value = player

    track = Track(
        title="Current Jam",
        author="Superstar",
        url="https://youtube.com/watch?v=99999",
        duration=240,
    )
    player.current = track

    ctx = MagicMock()
    ctx.guild = guild
    ctx.channel = MagicMock(spec=discord.TextChannel)

    with patch("src.cogs.music._commands.nowplaying.send_container_response", new_callable=AsyncMock) as mock_send:
        mock_msg = MagicMock(spec=discord.Message)
        mock_send.return_value = mock_msg

        await execute_nowplaying(cog, ctx)

        # Must send now playing response to user command
        mock_send.assert_awaited_once()
        assert player.controller_message == mock_msg
