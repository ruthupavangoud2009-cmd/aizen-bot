import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord.ext import commands

import wavelink
from src.core.config import Config
from src.core.lavalink import candidates, LavalinkUnavailable
from src.cogs.music._player import GuildPlayer
from src.cogs.music.music import Music
from src.cogs.fun.ai_voice import AIVoice
from src.managers.voice_welcome_manager import VoiceWelcomeManager


def test_candidates_parsing_with_custom_passwords():
    """Verify that candidates() parses both standard and uri|password formatted fallback URIs."""
    with patch.object(Config, "LAVALINK_URI", "http://primary.local:2334"), \
         patch.object(Config, "LAVALINK_PASSWORD", "mainpass"), \
         patch.object(Config, "LAVALINK_FALLBACK_URIS", "https://fallback1.local:443|custompass,http://fallback2.local:2334"):
        c = candidates()
        assert len(c) == 3
        assert c[0] == ("http://primary.local:2334", "mainpass")
        assert c[1] == ("https://fallback1.local:443", "custompass")
        assert c[2] == ("http://fallback2.local:2334", "mainpass")


@pytest.mark.asyncio
async def test_connect_voice_aborts_without_node_preventing_ghost_join():
    """
    Regression Test:
    When Lavalink node is offline, connect_voice MUST raise LavalinkUnavailable
    WITHOUT calling channel.connect(cls=wavelink.Player). Calling channel.connect
    without Lavalink is the exact cause of the orange [!] warning indicator.
    """
    bot = MagicMock()
    bot.get_cog.return_value = None
    bot._connection._remove_voice_client = MagicMock()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.voice_client = None
    guild.me = MagicMock()

    channel = MagicMock(spec=discord.VoiceChannel)
    channel.name = "Music"
    channel.id = 99999
    channel.user_limit = 0
    perms = MagicMock()
    perms.connect = True
    channel.permissions_for.return_value = perms
    channel.connect = AsyncMock()

    player = GuildPlayer(bot, guild)

    with patch("wavelink.Pool.get_node", side_effect=Exception("No node in pool")), \
         patch("src.cogs.music._player.connect_lavalink_node", side_effect=LavalinkUnavailable("Node unreachable")), \
         patch("src.cogs.music._player.close_pool_nodes", new_callable=AsyncMock):
        with pytest.raises(LavalinkUnavailable):
            await player.connect_voice(channel)

    # CRITICAL: channel.connect must NEVER be called if the node could not connect
    assert channel.connect.call_count == 0
    assert player.voice_client is None


@pytest.mark.asyncio
async def test_ai_voice_does_not_disconnect_or_override_music_player():
    """
    Regression Test:
    AIVoice commands must detect wavelink.Player and refuse to disconnect,
    hijack, or play FFmpeg audio over it.
    """
    bot = MagicMock(spec=commands.Bot)
    ai_cog = AIVoice(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345

    # Mock voice client as a wavelink.Player
    music_vc = MagicMock(spec=wavelink.Player)
    music_vc.connected = True
    music_vc.disconnect = AsyncMock()
    music_vc.stop = MagicMock()
    guild.voice_client = music_vc

    ctx = MagicMock()
    ctx.guild = guild
    ctx.prefix = "+"
    ctx.send_error = AsyncMock()
    ctx.send_success = AsyncMock()

    # 1. Test voice_leave does not disconnect wavelink.Player
    await ai_cog.voice_leave.callback(ai_cog, ctx)
    music_vc.disconnect.assert_not_called()
    music_vc.stop.assert_not_called()
    ctx.send_error.assert_called_once()
    assert "Music" in ctx.send_error.call_args[0][0]

    # 2. Test voice_join detects active music
    ctx.send_error.reset_mock()
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    ctx.author.voice = author_voice
    await ai_cog.voice_join.callback(ai_cog, ctx)
    ctx.send_error.assert_called_once()
    assert "Music session is currently active" in ctx.send_error.call_args[0][0]

    # 3. Test voice_speak refuses to speak over wavelink.Player
    ctx.send_error.reset_mock()
    await ai_cog.voice_speak.callback(ai_cog, ctx, text="Hello world")
    ctx.send_error.assert_called_once()
    assert "Music" in ctx.send_error.call_args[0][0]


@pytest.mark.asyncio
async def test_voice_welcome_manager_recognizes_wavelink_player():
    """
    Regression Test:
    VoiceWelcomeManager must treat any wavelink.Player as active music
    and defer greetings to prevent voice conflicts.
    """
    bot = MagicMock()
    db = MagicMock()
    mgr = VoiceWelcomeManager(bot, db)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345

    music_vc = MagicMock(spec=wavelink.Player)
    music_vc.connected = True
    guild.voice_client = music_vc

    # Verify is_music_active returns True for wavelink.Player
    assert mgr.is_music_active(guild) is True

    # Verify play_greeting aborts when wavelink.Player is attached
    channel = MagicMock(spec=discord.VoiceChannel)
    member = MagicMock(spec=discord.Member)
    member.guild = guild
    config = {"greeting_text": "Welcome {member}!", "language": "en"}

    result = await mgr.play_greeting(guild, channel, member, config)
    assert result is False


@pytest.mark.asyncio
async def test_all_music_commands_registered():
    """Verify all music commands are registered properly on the Music Cog without naming conflicts."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 1562505487214321714
    cog = Music(bot)

    command_names = {c.name for c in cog.get_commands()}
    expected_commands = {
        "join", "play", "autoplay", "pause", "resume", "skip",
        "stop", "queue", "nowplaying", "loop", "shuffle", "clear",
        "volume", "like", "unlike", "playlist", "remove", "jump",
        "247", "musicdiag"
    }

    for exp in expected_commands:
        assert exp in command_names, f"Expected music command '{exp}' not found in registered commands: {command_names}"
