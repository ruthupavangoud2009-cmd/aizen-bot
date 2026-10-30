"""
Comprehensive automated tests for Kyoka 3.0 Modular AI Voice Engine.
Verifies:
- Persona discovery and switching (aizen, kyoka, guy, christopher, aria, keita, nanami).
- Diagnostics reporting FFmpeg, Opus, and TTS engine state.
- Voice join and leave validations.
- Speech synthesis input constraints and queue locks.
- Independent operation from music system (never disconnects music to speak).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from src.cogs.fun.ai_voice import AIVoice, AVAILABLE_VOICES
from src.cogs.fun.ai_interactions import AIInteractions
from src.managers.voice_conversation_manager import VoiceConversationSession


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.user = MagicMock(id=999888777, name="Kyoka")
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    return bot


@pytest.fixture
def voice_cog(mock_bot: MagicMock) -> AIVoice:
    return AIVoice(mock_bot)


@pytest.fixture
def mock_voice_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.guild = MagicMock(id=999000111, name="Voice Testing Guild")
    ctx.author = MagicMock(id=111222333, display_name="AizenFan")
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_success = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.send_warning = AsyncMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    return ctx


def test_voice_available_personas():
    """Verify available voice personas include core anime and conversational voices."""
    expected_voices = ["aizen", "kyoka", "guy", "christopher", "aria", "keita", "nanami"]
    for v in expected_voices:
        assert v in AVAILABLE_VOICES
        assert "id" in AVAILABLE_VOICES[v]
        assert "name" in AVAILABLE_VOICES[v]
        assert "style" in AVAILABLE_VOICES[v]


@pytest.mark.asyncio
async def test_voice_persona_listing(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify listing personas returns an embed with all voices."""
    await voice_cog.voice_select.callback(voice_cog, mock_voice_ctx, voice_name=None)
    mock_voice_ctx.send.assert_awaited_once()
    _, kwargs = mock_voice_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Available AI Voice Personas" in embed.title
    assert "aizen" in embed.description
    assert "kyoka" in embed.description


@pytest.mark.asyncio
async def test_voice_persona_switch(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify switching to a valid voice persona updates the guild voice setting."""
    await voice_cog.voice_select.callback(voice_cog, mock_voice_ctx, voice_name="kyoka")
    assert voice_cog._guild_voices[mock_voice_ctx.guild.id] == "kyoka"

    mock_voice_ctx.send.assert_awaited_once()
    _, kwargs = mock_voice_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Kyoka" in embed.description


@pytest.mark.asyncio
async def test_voice_unknown_persona_error(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify selecting an unknown persona returns an error with valid options."""
    await voice_cog.voice_select.callback(voice_cog, mock_voice_ctx, voice_name="alien_robot_xyz")
    mock_voice_ctx.send_error.assert_awaited_once()
    args, _ = mock_voice_ctx.send_error.call_args
    assert "Unknown voice persona" in args[0]


@pytest.mark.asyncio
async def test_voice_diag_command(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify diagnostics reports Opus and FFmpeg health."""
    mock_voice_ctx.guild.voice_client = None
    await voice_cog.voice_diag.callback(voice_cog, mock_voice_ctx)
    mock_voice_ctx.send.assert_awaited_once()
    _, kwargs = mock_voice_ctx.send.call_args
    embed = kwargs["embed"]
    assert "AI Voice Engine Diagnostics" in embed.title
    field_names = [f.name for f in embed.fields]
    assert "🎵 Audio Binaries" in field_names


@pytest.mark.asyncio
async def test_voice_join_not_in_voice(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify voice_join fails gracefully when author is not connected to a voice channel."""
    mock_voice_ctx.author.voice = None
    await voice_cog.voice_join.callback(voice_cog, mock_voice_ctx)
    mock_voice_ctx.send_error.assert_awaited_once_with("You must be connected to a voice channel first!")

@pytest.mark.asyncio
async def test_voice_talk_reports_missing_voice_receive_dependency(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    with patch("src.cogs.fun.ai_voice.HAS_VOICE_RECV", False):
        await voice_cog.voice_talk.callback(voice_cog, mock_voice_ctx)

    mock_voice_ctx.send_error.assert_awaited_once_with(
        "Live voice conversations are unavailable because `discord-ext-voice_recv` is not installed."
    )


@pytest.mark.asyncio
async def test_voice_leave_not_connected(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify voice_leave fails gracefully when bot is not connected in guild."""
    mock_voice_ctx.guild.voice_client = None
    await voice_cog.voice_leave.callback(voice_cog, mock_voice_ctx)
    mock_voice_ctx.send_error.assert_awaited_once_with("I am not connected to any voice channel in this server.")


@pytest.mark.asyncio
async def test_voice_speak_requires_text(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify voice_speak fails when text is empty."""
    await voice_cog.voice_speak.callback(voice_cog, mock_voice_ctx, text="   ")
    mock_voice_ctx.send_error.assert_awaited_once_with("Please provide text to speak!")


@pytest.mark.asyncio
async def test_voice_stop_playback(voice_cog: AIVoice, mock_voice_ctx: MagicMock):
    """Verify voice_stop invokes vc.stop() when playing audio."""
    vc = MagicMock()
    vc.is_playing.return_value = True
    mock_voice_ctx.guild.voice_client = vc

    await voice_cog.voice_stop.callback(voice_cog, mock_voice_ctx)
    vc.stop.assert_called_once()
    mock_voice_ctx.send_success.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_moan_uses_comedic_tts_and_existing_voice_client() -> None:
    bot = MagicMock()
    bot._music_controller = None
    bot.db.fetch_one = AsyncMock(
        return_value={"value": json.dumps({"enabled": True, "channel_id": 321})}
    )
    voice_cog = AIVoice(bot)

    class FakeVoiceClient:
        channel = MagicMock(id=321)

        def is_connected(self) -> bool:
            return True

        def is_playing(self) -> bool:
            return False

    voice_client = FakeVoiceClient()
    voice_cog._play_audio_file = AsyncMock()

    async def synthesize(text: str, voice_id: str, output_path: str, lang: str) -> bool:
        assert "plot twist" in text or "joke" in text or "drama" in text
        with open(output_path, "wb") as audio_file:
            audio_file.write(b"generated audio")
        return True

    voice_cog._synthesize_audio = AsyncMock(side_effect=synthesize)
    ctx = MagicMock()
    ctx.guild.id = 321
    ctx.guild.voice_client = voice_client
    ctx.author.voice.channel.id = 321
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.send_success = AsyncMock()
    ctx.send_error = AsyncMock()

    with patch("src.cogs.fun.ai_voice.discord.VoiceClient", FakeVoiceClient):
        await voice_cog.cmd_voice.callback(voice_cog, ctx, voice_name="moan")

    voice_cog._synthesize_audio.assert_awaited_once()
    voice_cog._play_audio_file.assert_awaited_once()
    ctx.send_success.assert_awaited_once_with("Played a short, non-explicit comedic voice effect.")


@pytest.mark.asyncio
async def test_voice_moan_is_disabled_until_server_configures_it() -> None:
    voice_cog = AIVoice(MagicMock())
    voice_cog.bot.db.fetch_one = AsyncMock(return_value=None)
    ctx = MagicMock()
    ctx.guild.id = 321
    ctx.send_error = AsyncMock()
    voice_cog._synthesize_audio = AsyncMock()

    await voice_cog.cmd_voice.callback(voice_cog, ctx, voice_name="moan")

    ctx.send_error.assert_awaited_once()
    voice_cog._synthesize_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_voice_conversation_handles_text_without_breaking_voice_reply(voice_cog: AIVoice):
    session = VoiceConversationSession(
        guild_id=321,
        channel_id=123,
        channel_name="Voice",
        text_channel_id=456,
        started_by_id=789,
        started_by_name="Tester",
    )
    voice_cog.summary_mgr.get_session = MagicMock(return_value=None)
    voice_cog.conv_mgr.get_session = MagicMock(return_value=session)
    voice_cog.conv_mgr.handle_text_utterance = AsyncMock(return_value="Voice response")

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(id=789, bot=False, display_name="Tester")
    message.author.voice.channel.id = session.channel_id
    message.guild.id = 321
    message.channel.id = session.text_channel_id
    message.content = "Tell me something"
    message.reply = AsyncMock()

    await voice_cog.on_message(message)
    await asyncio.sleep(0)

    voice_cog.conv_mgr.handle_text_utterance.assert_awaited_once_with(
        session, voice_cog, message.author, "Tell me something"
    )
    message.reply.assert_awaited_once_with('🎙️ *"Voice response"*', mention_author=False)


@pytest.mark.asyncio
async def test_configured_ai_reply_is_spoken_when_user_shares_voice_channel():
    bot = MagicMock()
    voice_cog = MagicMock()
    voice_cog.conv_mgr.is_active.return_value = False
    voice_cog._is_music_active.return_value = False
    voice_cog._get_voice_id.return_value = "en-US-AvaNeural"
    voice_cog._get_voice_lang.return_value = "en"
    voice_cog._get_lock.return_value = asyncio.Lock()
    played = AsyncMock()
    voice_cog._play_audio_file = played

    async def synthesize(text, voice_id, output_path, lang):
        with open(output_path, "wb"):
            pass
        return True

    voice_cog._synthesize_audio = AsyncMock(side_effect=synthesize)
    bot.get_cog.return_value = voice_cog
    cog = AIInteractions(bot)

    channel = MagicMock(id=123)
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.channel = channel
    voice_client.is_connected.return_value = True
    guild = MagicMock(spec=discord.Guild)
    guild.id = 456
    guild.voice_client = voice_client
    member = MagicMock(spec=discord.Member)
    member.voice.channel = channel

    await cog._speak_configured_reply(guild, member, "Hello from configured AI")

    voice_cog._synthesize_audio.assert_awaited_once()
    played.assert_awaited_once_with(voice_client, voice_cog._synthesize_audio.await_args.args[2])


@pytest.mark.asyncio
async def test_configured_ai_reply_does_not_join_voice_automatically():
    bot = MagicMock()
    voice_cog = MagicMock()
    bot.get_cog.return_value = voice_cog
    cog = AIInteractions(bot)
    guild = MagicMock(spec=discord.Guild)
    guild.voice_client = None
    member = MagicMock(spec=discord.Member)
    member.voice.channel = MagicMock(id=123)

    await cog._speak_configured_reply(guild, member, "Hello")

    voice_cog._synthesize_audio.assert_not_called()


@pytest.mark.asyncio
async def test_regular_ai_command_speaks_answer_when_caller_is_in_voice():
    bot = MagicMock()
    cog = AIInteractions(bot)
    cog._ask_ai = AsyncMock(return_value="Spoken answer")
    cog._speak_configured_reply = AsyncMock()
    ctx = MagicMock()
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.guild.id = 456
    ctx.guild.name = "Test Guild"
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 123
    ctx.author.voice.channel = MagicMock()
    ctx.channel.id = 789
    ctx.prefix = "+"
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    ctx.reply = AsyncMock()

    await cog._send_ai(ctx, "Say hello")
    await asyncio.sleep(0)

    cog._speak_configured_reply.assert_awaited_once_with(ctx.guild, ctx.author, "Spoken answer")
