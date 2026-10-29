from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.fun.companion_ai import CompanionAI
from src.cogs.fun.last_to_leave import EliminationRecord, LastToLeaveGame, LastToLeaveVC, format_duration
from src.managers.ai_manager import AI_PERSONAS, AIManager, resolve_persona


# ─── 1. AI CHAT LIKE NORMAL PEOPLE TESTS ─────────────────────────────────────

def test_ai_normal_persona_prompt_and_defaults():
    """Verify default server personality is set to 'normal' with authentic friendly conversational style."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    # Server defaults should be 'normal' with casual tone
    cfg = mgr.get_server_config(12345)
    assert cfg["personality"] == "normal"
    assert cfg["tone"] == "casual"
    assert cfg["humor"] == "witty"

    # Normal persona exists and is distinct
    norm = resolve_persona("normal")
    assert norm["key"] == "normal"
    assert "human" in norm["aliases"] or "chat" in norm["aliases"]
    assert "chill" in norm["prompt"].lower() or "natural" in norm["prompt"].lower()
    assert "fictional anime villain" in norm["prompt"].lower() or "corporate robot" in norm["prompt"].lower()


def test_ai_smart_fallback_talks_like_normal_person():
    """Verify smart fallback gives natural, conversational, friendly responses rather than villain dialogue."""
    mock_db = AsyncMock()
    mgr = AIManager(mock_db)

    # Greetings
    greet_reply = mgr.get_smart_fallback("hey", persona_key="normal")
    assert any(w in greet_reply.lower() for w in ("hey", "yo", "what's up", "good to see you", "how are things"))
    assert "perceptions" not in greet_reply.lower()

    # How are you
    hru_reply = mgr.get_smart_fallback("how are you doing today?", persona_key="normal")
    assert any(w in hru_reply.lower() for w in ("good", "great", "pretty solid", "vibing", "how about yourself", "how's your day"))

    # Identity
    id_reply = mgr.get_smart_fallback("who are you?", persona_key="normal")
    assert "kyoka" in id_reply.lower()
    assert "architect of perception" not in id_reply.lower()

    # Gratitude
    ty_reply = mgr.get_smart_fallback("thank you so much!", persona_key="normal")
    assert any(w in ty_reply.lower() for w in ("anytime", "no problem", "happy to help", "glad to help"))

    # Small talk
    wyd_reply = mgr.get_smart_fallback("what are you doing?", persona_key="normal")
    assert any(w in wyd_reply.lower() for w in ("hanging out", "chilling", "chatting"))


@pytest.mark.asyncio
async def test_ai_command_aliases_and_plain_text_chat():
    """Verify ai command has talk/chat aliases and normal persona chats naturally in plain text."""
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.ai_mgr = AIManager(bot.db)

    cog = CompanionAI(bot)
    ai_cmd = cog.ai
    assert "chat" in ai_cmd.aliases
    assert "talk" in ai_cmd.aliases
    assert "ask" in ai_cmd.aliases

    # Test direct response with normal persona sends plain text without heavy card
    ctx = MagicMock()
    ctx.guild = MagicMock(id=999, name="Test Guild")
    ctx.channel = MagicMock(id=888)
    ctx.author = MagicMock(id=777, display_name="Friend")
    ctx.prefix = "?"
    ctx.send = AsyncMock()
    ctx.typing = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

    # Mock persona reply
    bot.ai_mgr.generate_persona_reply = AsyncMock(return_value="Haha yeah, that's honestly so cool! What happened next?")

    await cog._handle_direct_response(ctx, persona_key="normal", prompt="tell me something cool")

    assert ctx.send.called
    sent_text = ctx.send.call_args[0][0]
    assert "Haha yeah" in sent_text
    # Should not send an embed for normal persona
    kwargs = ctx.send.call_args[1]
    assert "embed" not in kwargs or kwargs["embed"] is None


# ─── 2. LAST TO LEAVE VC (LTLVC) GAME TESTS ──────────────────────────────────

def test_format_duration_helper():
    """Verify format_duration formats seconds into clean, human-readable strings."""
    assert format_duration(45) == "45s"
    assert format_duration(65) == "1m 05s"
    assert format_duration(215) == "3m 35s"
    assert format_duration(3665) == "1h 01m 05s"
    assert format_duration(7325) == "2h 02m 05s"


@pytest.mark.asyncio
async def test_ltlvc_overview_when_no_game_active():
    """Verify ?ltlvc without active game displays tutorial and rules."""
    bot = MagicMock()
    cog = LastToLeaveVC(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=100)
    ctx.author = MagicMock(display_name="PlayerOne")
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    await cog.ltlvc.callback(cog, ctx)

    assert ctx.send.called
    embed = ctx.send.call_args[1]["embed"]
    assert "Last To Leave VC" in embed.title
    assert "How It Works" in embed.description
    assert "?ltlvc start" in embed.description


@pytest.mark.asyncio
async def test_ltlvc_start_and_status():
    """Verify ?ltlvc start joins voice, starts timer, snapshots members, and ?ltlvc reports status."""
    bot = MagicMock()
    cog = LastToLeaveVC(bot)

    gid = 200
    vc_id = 300
    host_id = 401
    member2_id = 402
    member3_id = 403

    m_host = MagicMock(id=host_id, display_name="HostPlayer", bot=False)
    m2 = MagicMock(id=member2_id, display_name="PlayerTwo", bot=False)
    m3 = MagicMock(id=member3_id, display_name="PlayerThree", bot=False)
    m_bot = MagicMock(id=999, display_name="MusicBot", bot=True)

    vc_channel = MagicMock(spec=discord.VoiceChannel)
    vc_channel.id = vc_id
    vc_channel.mention = "<#300>"
    vc_channel.members = [m_host, m2, m3, m_bot]
    vc_channel.connect = AsyncMock()

    ctx = MagicMock()
    ctx.guild = MagicMock(id=gid, voice_client=None)
    ctx.author = m_host
    ctx.author.voice = MagicMock(channel=vc_channel)
    ctx.channel = MagicMock(id=500)
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    # 1. Start the game
    await cog.ltlvc_start.callback(cog, ctx, channel=None)

    assert vc_channel.connect.called
    game = cog.get_game(gid)
    assert game is not None
    assert game.is_active is True
    assert game.voice_channel_id == vc_id
    assert game.host_id == host_id
    # Only 3 human contestants (bot excluded)
    assert len(game.contestants) == 3
    assert host_id in game.contestants
    assert member2_id in game.contestants
    assert member3_id in game.contestants
    assert 999 not in game.contestants
    assert len(game.remaining) == 3

    # Check start message
    assert ctx.send.called
    start_embed = ctx.send.call_args[1]["embed"]
    assert "Game Started" in start_embed.title
    assert "Contestants (3)" in start_embed.description

    # 2. Check ?ltlvc (status)
    ctx.send.reset_mock()
    await cog.ltlvc.callback(cog, ctx)

    assert ctx.send.called
    status_embed = ctx.send.call_args[1]["embed"]
    assert "Live Game Status" in status_embed.title
    # Fields: Timer, Voice Channel, Host, Remaining, People Who Left
    field_names = [f.name for f in status_embed.fields]
    assert any("Survival Timer" in name for name in field_names)
    assert any("Contestants Remaining" in name for name in field_names)
    assert any("People Who Left" in name for name in field_names)


@pytest.mark.asyncio
async def test_ltlvc_voice_state_elimination_and_winner():
    """Verify on_voice_state_update records eliminations and declares winner when 1 person remains."""
    bot = MagicMock()
    text_ch = MagicMock(spec=discord.TextChannel)
    text_ch.send = AsyncMock()
    bot.get_channel = MagicMock(return_value=text_ch)

    cog = LastToLeaveVC(bot)

    gid = 500
    vc_id = 600
    p1_id = 701
    p2_id = 702
    p3_id = 703

    game = LastToLeaveGame(
        guild_id=gid,
        voice_channel_id=vc_id,
        text_channel_id=800,
        host_id=p1_id,
        start_time=time.time() - 100,  # 100 seconds ago
        contestants={p1_id: "Player1", p2_id: "Player2", p3_id: "Player3"},
        remaining={p1_id, p2_id, p3_id},
        eliminated=[],
        is_active=True,
    )
    cog.active_games[gid] = game

    # Guild and mock members
    guild = MagicMock(id=gid)
    p1 = MagicMock(id=p1_id, display_name="Player1", mention="<@701>", bot=False, guild=guild)
    p2 = MagicMock(id=p2_id, display_name="Player2", mention="<@702>", bot=False, guild=guild)
    p3 = MagicMock(id=p3_id, display_name="Player3", mention="<@703>", bot=False, guild=guild)
    guild.get_member = MagicMock(side_effect=lambda uid: {p1_id: p1, p2_id: p2, p3_id: p3}.get(uid))
    guild.voice_client = MagicMock()
    guild.voice_client.disconnect = AsyncMock()

    # 1. Player3 leaves the VC
    before_state = MagicMock(channel=MagicMock(id=vc_id))
    after_state = MagicMock(channel=None)  # disconnected from voice

    await cog.on_voice_state_update(p3, before_state, after_state)

    assert p3_id not in game.remaining
    assert len(game.eliminated) == 1
    assert game.eliminated[0].user_id == p3_id
    assert game.eliminated[0].order == 1
    assert game.is_active is True  # 2 remaining, game still running

    # Check elimination announcement
    assert text_ch.send.called
    msg = text_ch.send.call_args[0][0]
    assert "Player3" in msg
    assert "left the voice channel" in msg
    assert "Eliminated `#{}`".format(1) in msg

    # 2. Player2 leaves the VC -> Only Player1 remains -> WINNER!
    text_ch.send.reset_mock()
    await cog.on_voice_state_update(p2, before_state, after_state)

    assert len(game.remaining) == 1
    assert p1_id in game.remaining
    assert len(game.eliminated) == 2
    assert game.eliminated[1].user_id == p2_id

    # Game should have ended and announced winner
    assert game.is_active is False
    assert gid not in cog.active_games
    assert text_ch.send.called
    winner_call_kwargs = text_ch.send.call_args[1]
    assert "embed" in winner_call_kwargs
    winner_embed = winner_call_kwargs["embed"]
    assert "WE HAVE A WINNER" in winner_embed.title
    assert "<@701>" in winner_embed.description
    assert "Leaderboard" in winner_embed.description

    # Bot should disconnect from voice
    assert guild.voice_client.disconnect.called


@pytest.mark.asyncio
async def test_ltlvc_stop_command():
    """Verify ?ltlvc stop ends the game and disconnects the bot."""
    bot = MagicMock()
    cog = LastToLeaveVC(bot)

    gid = 888
    vc_id = 999
    host_id = 111

    game = LastToLeaveGame(
        guild_id=gid,
        voice_channel_id=vc_id,
        text_channel_id=222,
        host_id=host_id,
        start_time=time.time() - 50,
        contestants={host_id: "Host", 222: "PlayerB"},
        remaining={host_id, 222},
        eliminated=[],
        is_active=True,
    )
    cog.active_games[gid] = game

    ctx = MagicMock()
    ctx.guild = MagicMock(id=gid)
    ctx.guild.voice_client = MagicMock()
    ctx.guild.voice_client.disconnect = AsyncMock()
    ctx.author = MagicMock(id=host_id, mention="<@111>")
    ctx.send = AsyncMock()

    await cog.ltlvc_stop.callback(cog, ctx)

    assert game.is_active is False
    assert gid not in cog.active_games
    assert ctx.guild.voice_client.disconnect.called
    assert ctx.send.called
    stop_embed = ctx.send.call_args[1]["embed"]
    assert "Game Ended" in stop_embed.title
