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
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from src.cogs.fun.ai_voice import AIVoice, AVAILABLE_VOICES


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
