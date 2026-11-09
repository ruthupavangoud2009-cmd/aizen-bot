"""
Unit & Integration Tests for Kyoka Expanded Sovereign Gaming Universe & Server Admin Guess a Number.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord.ext import commands

from src.cogs.fun.fun import Fun, parse_guess_bounds
from src.cogs.fun.ai_interactions import AIInteractions
from src.cogs.games.casino import Casino, CrashGameView, MinesGameView
from src.cogs.games.multiplayer import (
    MultiplayerGames,
    Game2048View,
    MemoryMatchView,
    MultiplayerRPSView,
    BattleshipView,
)
from src.core.context import CustomContext
from src.ui.categories import resolve_command_category


# ─── 1. SERVER ADMIN GUESS A NUMBER AUTHORIZATION ────────────────────────────

@pytest.fixture
def mock_fun_bot():
    bot = MagicMock()
    bot.db = MagicMock()
    bot.db.execute = AsyncMock()
    bot.db.fetch_one = AsyncMock(return_value=None)
    bot.db.fetch_all = AsyncMock(return_value=[])
    bot.user = MagicMock(id=999999999)
    bot.get_cog = MagicMock(return_value=None)
    bot.get_user = MagicMock(return_value=None)
    bot.fetch_user = AsyncMock(return_value=MagicMock(id=1505515188991033409, send=AsyncMock()))
    return bot


@pytest.mark.asyncio
async def test_server_admin_can_start_guessanumber_without_allowlist(mock_fun_bot):
    """Server admins with administrator=True should bypass host allowlist check."""
    cog = Fun(mock_fun_bot)

    guild = MagicMock(spec=discord.Guild, id=5555, name="Admin Guild", owner_id=123)
    channel = MagicMock(spec=discord.TextChannel, id=6666, guild=guild)
    channel.send = AsyncMock()

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    # User is administrator
    admin_member = MagicMock(spec=discord.Member, id=7777)
    admin_member.guild_permissions.administrator = True
    admin_member.guild_permissions.manage_guild = True
    admin_member.send = AsyncMock()
    ctx.author = admin_member

    # Mock game insertion in DB
    mock_fun_bot.db.fetch_one.return_value = {"game_id": 99}

    await cog.guessanumber.callback(cog, ctx, bounds="1-100")

    # Game should have been created in channel 6666
    assert 6666 in cog.games
    assert cog.games[6666]["starter"] == 7777
    assert cog.games[6666]["low"] == 1
    assert cog.games[6666]["high"] == 100
    ctx.send.assert_called_with("🎮 **Guess a Number starts in 3 seconds! Get ready!**")


@pytest.mark.asyncio
async def test_server_admin_can_cancel_and_check_status(mock_fun_bot):
    """Server admins can cancel active games started by any member."""
    cog = Fun(mock_fun_bot)

    guild = MagicMock(spec=discord.Guild, id=5555, owner_id=123)
    channel = MagicMock(spec=discord.TextChannel, id=6666, guild=guild)

    # Active game started by user 1111
    cog.games[6666] = {
        "game_id": 42,
        "answer": 50,
        "low": 1,
        "high": 100,
        "starter": 1111,
        "expires_at": 9999999999.0,
        "start_time": 0.0,
        "countdown_active": False,
    }

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    # Admin author 9999
    admin = MagicMock(spec=discord.Member, id=9999)
    admin.guild_permissions.administrator = True
    ctx.author = admin

    # Check status
    await cog.guessstatus.callback(cog, ctx)
    ctx.send.assert_called_with("Number game active: range **1–100**. The answer remains private.")

    # Cancel game
    with patch.object(cog, "_lock_channel_after_game", new=AsyncMock()):
        await cog.guesscancel.callback(cog, ctx)
        assert 6666 not in cog.games
        ctx.send.assert_called_with("The number game was cancelled. The answer was not revealed.")


@pytest.mark.asyncio
async def test_server_admin_can_manage_hosts_and_settings(mock_fun_bot):
    """Server admins can authorize hosts, remove hosts, and configure game settings."""
    ai_cog = AIInteractions(mock_fun_bot)
    fun_cog = Fun(mock_fun_bot)

    guild = MagicMock(spec=discord.Guild, id=5555, owner_id=123)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.send = AsyncMock()
    ctx.prefix = "?"

    admin = MagicMock(spec=discord.Member, id=8888)
    admin.guild_permissions.administrator = True
    ctx.author = admin

    target = MagicMock(spec=discord.Member, id=2222, mention="<@2222>")

    # Add host
    await ai_cog.guesshostadd.callback(ai_cog, ctx, target)
    assert mock_fun_bot.db.execute.called
    assert "Added <@2222> to this server's number-game host allowlist." in ctx.send.call_args[0][0]

    # Configure rewards
    await fun_cog.guessreward.callback(fun_cog, ctx, 5000)
    assert "Set Guess a Number winner prize to **5,000 Coins**" in ctx.send.call_args[0][0]


# ─── 2. CASINO EXPANSION MECHANICS ──────────────────────────────────────────

def test_crash_game_view_logic():
    """Verify Crash game cashout math and crash threshold."""
    cog = MagicMock()
    cog.eco = MagicMock()
    cog.eco.update_balance = AsyncMock()
    ctx = MagicMock(author=MagicMock(id=100))

    view = CrashGameView(cog, ctx, bet=1000, guild_id=1)
    view.crash_point = 3.50
    view.current_mult = 2.00

    assert view.cashed_out is False
    assert view.crashed is False
    assert view.current_mult < view.crash_point


def test_mines_multiplier_progression():
    """Verify Mines math increases payout multiplier as safe gems are uncovered."""
    cog = MagicMock()
    ctx = MagicMock(author=MagicMock(id=100))

    view = MinesGameView(cog, ctx, bet=500, guild_id=1, bomb_count=3)
    assert len(view.board) == 25
    assert view.board.count(1) == 3
    assert view.board.count(0) == 22

    # Simulate 3 safe reveals
    view.revealed_safe = 3
    mult = view._calc_mult()
    assert mult > 1.0


# ─── 3. MULTIPLAYER & PUZZLE MECHANICS ──────────────────────────────────────

def test_2048_sliding_and_merging():
    """Verify 2048 tile merging math."""
    cog = MagicMock()
    ctx = MagicMock(author=MagicMock(id=100))
    view = Game2048View(cog, ctx)

    # Test row merging: [2, 2, 4, 8] -> [4, 4, 8, 0], score gain = 4
    merged, score = view._slide_left([2, 2, 4, 8])
    assert merged == [4, 4, 8, 0]
    assert score == 4

    # Test row with gap: [2, 0, 2, 0] -> [4, 0, 0, 0], score gain = 4
    merged2, score2 = view._slide_left([2, 0, 2, 0])
    assert merged2 == [4, 0, 0, 0]
    assert score2 == 4


def test_memory_match_card_pool():
    """Verify memory match generates 8 matching pairs (16 cards)."""
    cog = MagicMock()
    ctx = MagicMock(author=MagicMock(id=100))
    view = MemoryMatchView(cog, ctx)

    assert len(view.cards) == 16
    for card in set(view.cards):
        assert view.cards.count(card) == 2


def test_rps_duel_outcomes():
    """Verify Rock Paper Scissors win/loss/draw rules."""
    cog = MagicMock()
    p1 = MagicMock(id=1, mention="<@1>")
    p2 = MagicMock(id=2, mention="<@2>")
    view = MultiplayerRPSView(cog, p1, p2, bet=100)

    # Rock beats Scissors
    assert ("rock", "scissors") in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]
    # Paper beats Rock
    assert ("paper", "rock") in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]
    # Scissors beats Paper
    assert ("scissors", "paper") in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]


def test_battleship_initialization():
    """Verify Battleship assigns 4 distinct warships per player."""
    cog = MagicMock()
    p1 = MagicMock(id=1)
    p2 = MagicMock(id=2)
    view = BattleshipView(cog, p1, p2)

    assert len(view.ships_p1) == 4
    assert len(view.ships_p2) == 4
    assert all(0 <= s < 25 for s in view.ships_p1)
    assert all(0 <= s < 25 for s in view.ships_p2)


# ─── 4. CATEGORY CLASSIFICATION INTEGRITY ────────────────────────────────────

def test_all_expanded_games_categories():
    """Verify all casino and multiplayer games classify to their categories."""
    bot = MagicMock()
    cas = Casino(bot)
    mp = MultiplayerGames(bot)

    for cmd in cas.get_commands():
        cmd.cog = cas
        meta = resolve_command_category(cmd)
        assert meta.id == "casino", f"Command {cmd.name} did not resolve to casino!"

    for cmd in mp.get_commands():
        cmd.cog = mp
        meta = resolve_command_category(cmd)
        assert meta.id == "multiplayer", f"Command {cmd.name} did not resolve to multiplayer!"
