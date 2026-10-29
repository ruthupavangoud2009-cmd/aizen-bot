"""
Comprehensive automated tests for Kyoka's Ultimate Voice Agent & Conversational AI.
Verifies:
- VoiceAgentSpeakModal dialog and text-to-voice interaction.
- VoiceConversationControlView controls (Speak Modal button, SFX triggers, Vibe dropdown).
- VoiceConversationManager text utterance handler (contextual responses, soundboard triggers, session transcripts).
- Top-level prefix commands: +voiceagent, +vcask, +vc20q, +vcstory, +vcleave.
- Automatic voice state listeners: member welcome greetings & auto-disconnect on empty VC.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

from src.cogs.fun.ai_voice import AIVoice
from src.managers.voice_conversation_manager import (
    VoiceConversationManager,
    VoiceConversationSession,
    VoiceAgentSpeakModal,
    VoiceConversationControlView,
    CONVERSATIONAL_VIBES,
)


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
def mock_voice_channel() -> MagicMock:
    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 123456789
    vc.name = "General Voice"
    vc.guild = MagicMock(id=999000111, name="Voice Guild")
    vc.members = []
    return vc


@pytest.fixture
def mock_member(mock_voice_channel: MagicMock) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.name = "Pavan"
    member.display_name = "Pavan"
    member.bot = False
    member.guild = mock_voice_channel.guild
    member.voice = MagicMock()
    member.voice.channel = mock_voice_channel
    return member


@pytest.fixture
def mock_voice_client() -> MagicMock:
    client = MagicMock()
    client.is_connected.return_value = True
    client.is_playing.return_value = False
    client.play = MagicMock()
    client.stop = MagicMock()
    client.disconnect = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# 1. VoiceAgentSpeakModal & Control View Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_agent_speak_modal_init_and_submit():
    """Verify VoiceAgentSpeakModal initializes with correct fields and handles submission."""
    manager = VoiceConversationManager()
    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="TestUser",
    )
    cog = MagicMock()

    modal = VoiceAgentSpeakModal(manager, session, cog)
    assert modal.title == "🎙️ Speak to Voice Agent"
    assert modal.prompt is not None

    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.response = MagicMock()
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup = MagicMock()
    mock_interaction.followup.send = AsyncMock()
    mock_interaction.user = MagicMock(id=111, display_name="TestUser")

    modal.prompt._value = "Tell us a joke!"

    with patch.object(manager, "handle_text_utterance", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = "Why did the chicken cross the road? To rule Hueco Mundo!"
        await modal.on_submit(mock_interaction)

        mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_handle.assert_awaited_once_with(
            session,
            cog,
            mock_interaction.user,
            "Tell us a joke!",
        )
        mock_interaction.followup.send.assert_awaited_once()
        msg = mock_interaction.followup.send.call_args[0][0]
        assert "Why did the chicken cross the road" in msg


def test_voice_conversation_control_view_structure(mock_bot: MagicMock):
    """Verify VoiceConversationControlView includes speak modal button and valid soundboard buttons."""
    manager = VoiceConversationManager()
    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="TestUser",
    )
    view = VoiceConversationControlView(manager, session, mock_bot)

    custom_ids = [item.custom_id for item in view.children if hasattr(item, "custom_id")]
    assert "kyoka:vctalk:speak_modal" in custom_ids
    assert "kyoka:vctalk:sfx_boom" in custom_ids
    assert "kyoka:vctalk:sfx_airhorn" in custom_ids
    assert "kyoka:vctalk:leave" in custom_ids

    speak_btn = next((b for b in view.children if getattr(b, "custom_id", None) == "kyoka:vctalk:speak_modal"), None)
    assert speak_btn is not None
    assert "Speak" in speak_btn.label


# ---------------------------------------------------------------------------
# 2. VoiceConversationManager Utterance & SFX Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_text_utterance_with_soundboard_trigger():
    """Verify handle_text_utterance triggers soundboard effects when keywords are detected."""
    manager = VoiceConversationManager()
    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = False

    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="DJ_Aizen",
    )
    session.voice_client = mock_vc

    cog = MagicMock()
    cog._get_lock.return_value = asyncio.Lock()
    cog._play_audio_file = AsyncMock()
    cog._synthesize_audio = AsyncMock(return_value=False)

    mock_user = MagicMock(display_name="DJ_Aizen")

    with patch.object(manager.sfx_engine, "get_sfx_path", return_value="tests/dummy.mp3"), \
         patch("os.path.exists", return_value=True):
        reply = await manager.handle_text_utterance(
            session,
            cog,
            mock_user,
            "drop the airhorn right now!",
        )

        assert session.total_sfx_played >= 1


@pytest.mark.asyncio
async def test_handle_text_utterance_generates_vibe_reply():
    """Verify handle_text_utterance generates contextual spoken reply for mastermind vibe."""
    manager = VoiceConversationManager()
    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = False

    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="Ichigo",
        vibe="mastermind",
    )
    session.voice_client = mock_vc

    cog = MagicMock()
    cog._get_lock.return_value = asyncio.Lock()
    cog._play_audio_file = AsyncMock()
    cog._synthesize_audio = AsyncMock(return_value=False)

    mock_user = MagicMock(display_name="Ichigo")

    reply = await manager.handle_text_utterance(
        session,
        cog,
        mock_user,
        "What is your plan for the Soul Society?",
    )

    assert isinstance(reply, str)
    assert len(reply) > 0
    assert len(session.full_transcript) == 1
    assert session.turn_count == 1


@pytest.mark.asyncio
async def test_handle_text_utterance_generates_normal_human_reply():
    """Verify handle_text_utterance generates natural, warm human conversation for normal vibe."""
    manager = VoiceConversationManager()
    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="Chill Hangout",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="Pavan",
        vibe="normal",
    )
    assert session.vibe == "normal"
    assert session.get_voice_meta()["name"] == "Ava"

    cog = MagicMock()
    cog._get_lock.return_value = asyncio.Lock()
    cog._play_audio_file = AsyncMock()
    cog._synthesize_audio = AsyncMock(return_value=False)

    mock_user = MagicMock(display_name="Pavan")

    reply = await manager.handle_text_utterance(
        session,
        cog,
        mock_user,
        "Hey how's your day going?",
    )

    assert isinstance(reply, str)
    assert len(reply) > 0
    assert any(term in reply for term in ("Hey", "doing", "good", "nice", "hang", "Pavan"))
    assert session.turn_count == 1


def test_voice_session_defaults_to_normal_human_vibe():
    """Verify VoiceConversationSession defaults to normal human persona with Ava voice."""
    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="Pavan",
    )
    assert session.vibe == "normal"
    assert session.voice_key == "ava"
    meta = session.get_vibe_meta()
    assert meta["id"] == "normal"
    assert "Natural Human" in meta["name"]


# ---------------------------------------------------------------------------
# 3. Top-Level Prefix Commands Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voiceagent_prefix_command_joins_and_starts_hud(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify +voiceagent joins the caller's voice channel and initiates conversation."""
    ctx = MagicMock()
    ctx.guild = mock_voice_channel.guild
    ctx.guild.voice_client = None
    ctx.channel = MagicMock(id=888, spec=discord.TextChannel)
    ctx.author = mock_member
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.send_warning = AsyncMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()

    mock_voice_channel.connect = AsyncMock(return_value=mock_voice_client)

    with patch.object(voice_cog, "voice_talk", new_callable=AsyncMock) as mock_talk:
        await voice_cog.cmd_voiceagent.callback(voice_cog, ctx, vibe="chill")
        mock_talk.assert_awaited_once_with(ctx, mode="chill")


@pytest.mark.asyncio
async def test_vcask_command_calls_voice_ask(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
):
    """Verify +vcask asks a question and routes to voice_ask."""
    ctx = MagicMock()
    ctx.guild = mock_voice_channel.guild
    ctx.channel = MagicMock(id=888)
    ctx.author = mock_member
    ctx.clean_prefix = "+"

    with patch.object(voice_cog, "voice_ask", new_callable=AsyncMock) as mock_ask:
        await voice_cog.cmd_vcask.callback(voice_cog, ctx, question="Who is Kyoka?")
        mock_ask.assert_awaited_once_with(ctx, question="Who is Kyoka?")


@pytest.mark.asyncio
async def test_vc20q_starts_game_session(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify +vc20q starts the 20 questions spoken challenge."""
    ctx = MagicMock()
    ctx.guild = mock_voice_channel.guild
    ctx.guild.voice_client = mock_voice_client
    ctx.channel = MagicMock(id=888)
    ctx.author = mock_member
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()

    with patch.object(voice_cog, "_synthesize_audio", new_callable=AsyncMock) as mock_synth, \
         patch.object(voice_cog, "_play_audio_file", new_callable=AsyncMock) as mock_play, \
         patch.object(voice_cog.conv_mgr.sfx_engine, "get_sfx_path", return_value=None):
        mock_synth.return_value = True

        await voice_cog.cmd_vc20q.callback(voice_cog, ctx)

        mock_synth.assert_awaited_once()
        mock_play.assert_awaited()
        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Voice 20 Questions" in embed.title


@pytest.mark.asyncio
async def test_vcstory_narrates_spoken_story(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify +vcstory synthesizes and speaks interactive adventure narration."""
    ctx = MagicMock()
    ctx.guild = mock_voice_channel.guild
    ctx.guild.voice_client = mock_voice_client
    ctx.channel = MagicMock(id=888)
    ctx.author = mock_member
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()

    with patch.object(voice_cog, "_synthesize_audio", new_callable=AsyncMock) as mock_synth, \
         patch.object(voice_cog, "_play_audio_file", new_callable=AsyncMock) as mock_play, \
         patch.object(voice_cog.conv_mgr.sfx_engine, "get_sfx_path", return_value=None):
        mock_synth.return_value = True

        await voice_cog.cmd_vcstory.callback(voice_cog, ctx)

        mock_synth.assert_awaited_once()
        mock_play.assert_awaited()
        ctx.send.assert_awaited_once()
        embed = ctx.send.call_args[1]["embed"]
        assert "Interactive Voice Story" in embed.title


@pytest.mark.asyncio
async def test_vcleave_concludes_session(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify +vcleave concludes session and cleans up."""
    ctx = MagicMock()
    ctx.guild = mock_voice_channel.guild
    ctx.channel = MagicMock(id=888)
    ctx.author = mock_member
    ctx.clean_prefix = "+"

    session = VoiceConversationSession(
        guild_id=ctx.guild.id,
        channel_id=mock_voice_channel.id,
        channel_name="General Voice",
        text_channel_id=888,
        started_by_id=mock_member.id,
        started_by_name="Pavan",
    )
    voice_cog.conv_mgr.sessions[ctx.guild.id] = session

    with patch.object(voice_cog, "end_conversation_session", new_callable=AsyncMock) as mock_end:
        await voice_cog.cmd_vcleave.callback(voice_cog, ctx)
        mock_end.assert_awaited_once_with(ctx.guild, ctx.channel, trigger_user=mock_member, summarize=True)


# ---------------------------------------------------------------------------
# 4. Listener Tests: Member Welcome & Empty VC Auto-Disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_voice_state_update_welcomes_new_member(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify on_voice_state_update speaks a welcome message when someone joins."""
    mock_voice_client.channel = mock_voice_channel
    mock_voice_channel.members = [mock_member]

    session = VoiceConversationSession(
        guild_id=mock_voice_channel.guild.id,
        channel_id=mock_voice_channel.id,
        channel_name="General Voice",
        text_channel_id=888,
        started_by_id=999,
        started_by_name="Host",
        vibe="mastermind",
    )
    session.voice_client = mock_voice_client
    voice_cog.conv_mgr.sessions[mock_voice_channel.guild.id] = session

    before = MagicMock(channel=None)
    after = MagicMock(channel=mock_voice_channel)

    with patch.object(voice_cog.conv_mgr, "play_custom_announcement", new_callable=AsyncMock) as mock_announce:
        await voice_cog.on_voice_state_update(mock_member, before, after)
        # Yield to let the created background task run
        await asyncio.sleep(0.01)
        mock_announce.assert_awaited_once()
        announcement_text = mock_announce.call_args[0][2]
        assert "Welcome, Pavan" in announcement_text


@pytest.mark.asyncio
async def test_on_voice_state_update_auto_disconnects_when_vc_empty(
    voice_cog: AIVoice,
    mock_member: MagicMock,
    mock_voice_channel: MagicMock,
    mock_voice_client: MagicMock,
):
    """Verify on_voice_state_update disconnects bot when only bots remain in channel."""
    mock_voice_client.channel = mock_voice_channel
    bot_member = MagicMock(bot=True)
    mock_voice_channel.members = [bot_member]

    session = VoiceConversationSession(
        guild_id=mock_voice_channel.guild.id,
        channel_id=mock_voice_channel.id,
        channel_name="General Voice",
        text_channel_id=888,
        started_by_id=999,
        started_by_name="Host",
    )
    session.voice_client = mock_voice_client
    voice_cog.conv_mgr.sessions[mock_voice_channel.guild.id] = session

    mock_text_channel = MagicMock()
    mock_voice_channel.guild.get_channel.return_value = mock_text_channel

    before = MagicMock(channel=mock_voice_channel)
    after = MagicMock(channel=None)

    with patch.object(voice_cog, "end_conversation_session", new_callable=AsyncMock) as mock_end:
        await voice_cog.on_voice_state_update(mock_member, before, after)
        mock_end.assert_awaited_once_with(mock_voice_channel.guild, mock_text_channel, trigger_user=None, summarize=True)


# ---------------------------------------------------------------------------
# 5. Expanded Personalities Tests
# ---------------------------------------------------------------------------

def test_conversational_vibes_structure_and_completeness():
    """Verify all 17 voice personalities have valid metadata and valid Discord UI constraints."""
    expected_personalities = [
        "mastermind", "gamer", "chill", "tsundere", "podcast",
        "cyberpunk", "comedian", "pirate", "butler", "sensei",
        "chef", "detective", "therapist", "drillsergeant", "knight",
        "supervillain", "crypto",
    ]
    assert len(CONVERSATIONAL_VIBES) >= 17

    for p_id in expected_personalities:
        assert p_id in CONVERSATIONAL_VIBES
        meta = CONVERSATIONAL_VIBES[p_id]
        assert "name" in meta
        assert "emoji" in meta
        assert "color" in meta
        assert "voice" in meta
        assert "description" in meta
        assert len(meta["description"]) <= 100, f"Description for {p_id} exceeds Discord select limit"
        assert "prompt" in meta
        assert "greeting" in meta
        assert "welcome" in meta


@pytest.mark.asyncio
async def test_personality_vibe_switching_and_local_responses(voice_cog: AIVoice):
    """Verify switching between diverse personalities produces valid fallback responses and greetings."""
    manager = VoiceConversationManager()
    session = VoiceConversationSession(
        guild_id=999,
        channel_id=123,
        channel_name="General Voice",
        text_channel_id=456,
        started_by_id=111,
        started_by_name="Pavan",
        vibe="pirate",
    )

    test_personalities = ["pirate", "butler", "sensei", "chef", "detective", "therapist", "drillsergeant", "knight", "supervillain", "crypto"]
    for p in test_personalities:
        session.vibe = p
        _, fallback_reply = manager._generate_intelligent_local_turn(session, "Pavan")
        assert isinstance(fallback_reply, str)
        assert len(fallback_reply) > 0
        assert "Pavan" in fallback_reply

        welcome = session.get_vibe_meta()["welcome"].format(user="Pavan")
        assert "Pavan" in welcome


@pytest.mark.asyncio
async def test_vcvibe_command_lists_all_personalities(voice_cog: AIVoice, mock_member: MagicMock):
    """Verify +vcvibe with no arguments lists all available personalities."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=999)
    ctx.channel = MagicMock()
    ctx.author = mock_member
    ctx.prefix = "+"
    ctx.send = AsyncMock()

    await voice_cog.cmd_vcvibe.callback(voice_cog, ctx, vibe_name=None)
    ctx.send.assert_awaited_once()
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Conversational Voice Vibes" in embed.title
    for key in ["pirate", "butler", "sensei", "chef", "crypto"]:
        assert key in embed.description


@pytest.mark.asyncio
async def test_voice_sessions_command_handles_empty_and_records(voice_cog: AIVoice, mock_member: MagicMock):
    """Verify +aivoice sessions handles both empty history and populated session logs cleanly without crashing."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=999, name="Audio HQ")
    ctx.channel = MagicMock()
    ctx.author = mock_member
    ctx.prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_info = AsyncMock()

    # 1. Empty history
    voice_cog.summary_mgr._history_cache.clear()
    await voice_cog.voice_sessions(ctx)
    ctx.send_info.assert_awaited_once()

    # 2. Populated history
    voice_cog.summary_mgr._history_cache[999] = [{
        "id": 1,
        "guild_id": 999,
        "channel_id": 123,
        "channel_name": "General Voice",
        "started_by": "Pavan",
        "duration": "12m 30s",
        "speaker_count": 3,
        "summary": "Meeting discussion notes",
        "created_at": "2026-10-29 02:00 UTC",
    }]
    ctx.send_info.reset_mock()
    await voice_cog.voice_sessions(ctx)
    ctx.send.assert_awaited_once()
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Voice Meeting History" in embed.title
    assert "Session `#1`" in embed.description


def test_resolve_voice_key_aliases():
    """Verify resolve_voice_key maps friendly aliases and defaults correctly."""
    from src.cogs.fun.ai_voice import resolve_voice_key

    assert resolve_voice_key("ava") == "ava"
    assert resolve_voice_key("female") == "ava"
    assert resolve_voice_key("girl") == "ava"

    assert resolve_voice_key("andrew") == "andrew"
    assert resolve_voice_key("male") == "andrew"
    assert resolve_voice_key("boy") == "andrew"

    assert resolve_voice_key("kyoka") == "kyoka"
    assert resolve_voice_key("waifu") == "kyoka"

    assert resolve_voice_key("aizen") == "aizen"
    assert resolve_voice_key("villain") == "aizen"

    # Default fallback
    assert resolve_voice_key(None) == "ava"
    assert resolve_voice_key("nonexistent_random_voice") == "ava"


@pytest.mark.asyncio
async def test_cmd_setvoice_updates_and_persists_voice(voice_cog: AIVoice):
    """Verify +setvoice switches guild voice, updates cache, and persists to DB."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=12345, name="Test Guild")
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()

    voice_cog.bot.db = AsyncMock()

    # Call +setvoice with alias 'male' -> resolves to 'andrew'
    await voice_cog.cmd_setvoice.callback(voice_cog, ctx, voice_name="male")

    assert voice_cog._guild_voices[12345] == "andrew"
    voice_cog.bot.db.execute.assert_awaited_once()
    ctx.send.assert_awaited_once()
    embed = ctx.send.call_args[1]["embed"]
    assert "Andrew" in embed.description
    assert "Updated" in embed.title

