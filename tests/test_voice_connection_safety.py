"""
Regression tests for Voice Connection Safety and NoneType Fixes:
1. Exact NoneType regression: when guild.me is None, connect_voice does NOT crash with 'NoneType' object has no attribute 'id'
2. When channel is None or missing id: raises ValueError cleanly without crashing
3. When guild is None or missing id: raises ValueError cleanly without crashing
4. Missing Connect/Speak permissions: raises descriptive RuntimeError
5. User not in voice channel: responds clearly with "Join a voice channel first, then try again."
6. User in voice channel: proceeds safely to connect_voice
7. Voice welcome while music is playing: defers greeting without disconnecting or interrupting music
8. UI controls and views: safely handle missing voice state / channels without .id attribute errors
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest
import wavelink

from src.cogs.music._player import GuildPlayer
from src.cogs.music._commands.play import execute_play
from src.cogs.music._commands.controls import check_voice_channel
from src.cogs.music._views import MusicControlView
from src.managers.voice_welcome_manager import VoiceWelcomeManager


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 1505515188991033409
    bot._connection = MagicMock()
    bot._connection._remove_voice_client = MagicMock()
    return bot


@pytest.fixture
def mock_guild():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1122334455
    guild.name = "Test Guild"
    guild.voice_client = None
    guild.me = MagicMock(spec=discord.Member)
    guild.me.id = 1505515188991033409
    guild.me.voice = None
    return guild


@pytest.fixture
def mock_channel(mock_guild):
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 99887766
    channel.name = "General Voice"
    channel.guild = mock_guild
    channel.user_limit = 0
    channel.members = []
    
    perms = MagicMock()
    perms.connect = True
    perms.speak = True
    perms.move_members = True
    channel.permissions_for.return_value = perms
    channel.connect = AsyncMock()
    return channel


@pytest.mark.asyncio
async def test_connect_voice_when_guild_me_is_none(mock_bot, mock_guild, mock_channel):
    """REGRESSION: If guild.me is None, connect_voice must NOT crash with 'NoneType' object has no attribute 'id'."""
    mock_guild.me = None
    mock_guild.get_member.return_value = None

    player = GuildPlayer(mock_bot, mock_guild)
    
    # Mock wavelink pool and node
    mock_node = MagicMock()
    mock_node.status = wavelink.NodeStatus.CONNECTED
    with patch("wavelink.Pool.get_node", return_value=mock_node), \
         patch.object(player, "_probe_lavalink_node", AsyncMock(return_value=True)):
        mock_vc = MagicMock(spec=wavelink.Player)
        mock_channel.connect.return_value = mock_vc

        await player.connect_voice(mock_channel)
        assert player.voice_client == mock_vc


@pytest.mark.asyncio
async def test_connect_voice_with_none_channel(mock_bot, mock_guild):
    """Passing None channel must raise ValueError without accessing .id on None."""
    player = GuildPlayer(mock_bot, mock_guild)
    with pytest.raises(ValueError, match="Invalid voice channel"):
        await player.connect_voice(None)


@pytest.mark.asyncio
async def test_connect_voice_with_none_guild(mock_bot, mock_channel):
    """Player with None guild must raise ValueError without accessing .id on None."""
    player = GuildPlayer(mock_bot, None)
    with pytest.raises(ValueError, match="Invalid guild"):
        await player.connect_voice(mock_channel)


@pytest.mark.asyncio
async def test_connect_voice_missing_connect_permission(mock_bot, mock_guild, mock_channel):
    """Missing Connect permission must raise RuntimeError with channel name."""
    perms = MagicMock()
    perms.connect = False
    perms.speak = True
    mock_channel.permissions_for.return_value = perms

    player = GuildPlayer(mock_bot, mock_guild)
    with pytest.raises(RuntimeError, match="lacks 'Connect' permission"):
        await player.connect_voice(mock_channel)


@pytest.mark.asyncio
async def test_connect_voice_missing_speak_permission(mock_bot, mock_guild, mock_channel):
    """Missing Speak permission must raise RuntimeError with channel name."""
    perms = MagicMock()
    perms.connect = True
    perms.speak = False
    mock_channel.permissions_for.return_value = perms

    player = GuildPlayer(mock_bot, mock_guild)
    with pytest.raises(RuntimeError, match="lacks 'Speak' permission"):
        await player.connect_voice(mock_channel)


@pytest.mark.asyncio
async def test_play_command_when_user_not_in_voice(mock_bot, mock_guild):
    """When user is not in a voice channel, respond with 'Join a voice channel first, then try again.'"""
    ctx = MagicMock()
    ctx.guild = mock_guild
    ctx.interaction = None
    author = MagicMock(spec=discord.Member)
    author.voice = None
    ctx.author = author

    cog = MagicMock()
    cog.bot = mock_bot

    with patch("src.cogs.music._commands.play.send_container_response", new_callable=AsyncMock) as mock_send:
        await execute_play(cog, ctx, "song query")
        mock_send.assert_called_once()
        container = mock_send.call_args[0][1]
        assert any("Join a voice channel first, then try again." in str(c) for c in container.components)


@pytest.mark.asyncio
async def test_play_command_when_user_in_voice(mock_bot, mock_guild, mock_channel):
    """When user is in a voice channel, proceed to connect_voice."""
    ctx = MagicMock()
    ctx.guild = mock_guild
    ctx.interaction = None
    author = MagicMock(spec=discord.Member)
    author.voice = MagicMock()
    author.voice.channel = mock_channel
    ctx.author = author
    ctx.channel = MagicMock()

    player = MagicMock()
    player.connect_voice = AsyncMock()
    player.is_paused = False
    player.queue = []
    player.is_playing = False

    cog = MagicMock()
    cog.bot = mock_bot
    cog.controller.get_or_create_player.return_value = player
    cog.controller.get_player.return_value = player

    with patch("src.cogs.music._commands.play.send_container_response", new_callable=AsyncMock):
        # Empty query triggers empty query handler after connect_voice
        await execute_play(cog, ctx, "")
        player.connect_voice.assert_called_once_with(mock_channel)


@pytest.mark.asyncio
async def test_voice_welcome_deferred_while_music_active(mock_bot, mock_guild, mock_channel):
    """Voice welcome greeting must defer safely without disconnecting or interrupting active music."""
    mgr = VoiceWelcomeManager(mock_bot, MagicMock())
    
    # Active wavelink player
    active_player = MagicMock(spec=wavelink.Player)
    active_player.connected = True
    mock_guild.voice_client = active_player

    member = MagicMock(spec=discord.Member)
    member.id = 554433
    member.guild = mock_guild
    member.display_name = "NewPlayer"
    member.voice = MagicMock()
    member.voice.channel = mock_channel

    config = {
        "enabled": True,
        "channel_id": mock_channel.id,
        "trigger": "voice_join",
        "greeting_text": "Welcome {member}!",
        "defer_if_music_active": True,
        "cooldown_seconds": 0,
        "allow_bots": True,
    }

    with patch.object(mgr, "get_config", AsyncMock(return_value=config)), \
         patch.object(mgr, "is_music_active", return_value=True), \
         patch.object(mgr, "play_greeting", AsyncMock()) as mock_play:
        await mgr.handle_member_event(member, "voice_join")
        mock_play.assert_not_called()
        assert mock_guild.id in mgr._queues
        assert len(mgr._queues[mock_guild.id]) == 1


def test_check_voice_channel_safety(mock_guild):
    """check_voice_channel must safely handle missing voice states without AttributeError."""
    ctx = MagicMock()
    ctx.guild = mock_guild
    
    # Author voice is None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.voice = None
    allowed, msg = check_voice_channel(ctx)
    assert allowed is False
    assert "Join a voice channel first, then try again." in msg

    # Author voice channel is None
    ctx.author.voice = MagicMock()
    ctx.author.voice.channel = None
    allowed, msg = check_voice_channel(ctx)
    assert allowed is False
    assert "Join a voice channel first, then try again." in msg


def test_music_view_check_voice_safety(mock_bot):
    """MusicControlView._check_voice must safely handle missing bot_vc or user_vc without crashing on .id."""
    mock_player = MagicMock()
    mock_player.is_connected = True
    mock_player.voice_client = MagicMock()
    mock_player.voice_client.channel = MagicMock()
    mock_player.guild.id = 1122334455

    view = MusicControlView(bot=mock_bot, player=mock_player, guild_id=1122334455)
    
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    member.roles = []
    member.voice = None

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member
    interaction.guild_id = 1122334455

    # Member has no voice
    err = view._check_voice(interaction, mock_player)
    assert err == "Join a voice channel first, then try again."

    # Member has voice, but bot is not connected
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 111
    
    mock_player.voice_client = None
    err = view._check_voice(interaction, mock_player)
    assert "not connected" in err.lower()
