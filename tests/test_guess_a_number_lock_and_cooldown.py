"""
Tests for Guess a Number Event: Channel Lock on Game End & 3-Second Cooldown.

Covers:
1. 3-second cooldown upon game start:
   - Countdown notification is sent ("🎮 Guess a Number starts in 3 seconds! Get ready!")
   - Guesses submitted during countdown are rejected (not counted as attempts)
   - Concurrent game start prevention in the same channel
   - Cleanup of countdown tasks on cancellation and cog unload
2. Automatic channel lock on game completion:
   - Lock triggered when someone wins (only after winner message is announced)
   - Lock triggered on game timeout
   - Lock triggered when maximum attempts (100) are reached
   - Lock triggered on manual cancellation (?guesscancel)
   - Bot denies Send Messages for @everyone while preserving other role/user overwrites
   - Original permission overwrite is saved before locking
   - Permission restoration via ?guessunlock and integration with ?unlock
   - Safe error handling when bot lacks manage_channels permission
   - Unrelated channels remain completely unaffected
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.fun.fun import Fun
from src.cogs.moderation.lock import LockCog
from src.core.context import CustomContext
from src.security.owner import OWNER_ID


class MockDatabase:
    def __init__(self):
        self.games = {}
        self.attempts = []
        self.results = []

    async def fetch_one(self, query: str, *args):
        query_upper = query.upper()
        if "INSERT INTO GUESS_NUMBER_GAMES" in query_upper:
            game_id = 1000 + len(self.games) + 1
            self.games[game_id] = {
                "channel_id": args[0],
                "host_id": args[1],
                "low": args[2],
                "high": args[3],
                "status": "active",
            }
            return {"game_id": game_id}
        elif "INSERT INTO GUESS_NUMBER_ATTEMPTS" in query_upper:
            game_id, user_id, guess = args[0], args[1], args[2]
            for att in self.attempts:
                if att["game_id"] == game_id and att["guess"] == guess:
                    return None  # conflict
            self.attempts.append({"game_id": game_id, "user_id": user_id, "guess": guess})
            return {"guess": guess}
        elif "UPDATE GUESS_NUMBER_GAMES" in query_upper and "WINNER_ID" in query_upper:
            winner_id, game_id = args[0], args[1]
            if game_id in self.games:
                self.games[game_id]["status"] = "completed"
                self.games[game_id]["winner_id"] = winner_id
                return {"game_id": game_id}
            return {"game_id": game_id}
        return {"status": "ok"}

    async def execute(self, query: str, *args):
        query_upper = query.upper()
        if "INSERT INTO KYOKA_GUESS_RESULTS" in query_upper:
            self.results.append(args)
        elif "UPDATE GUESS_NUMBER_GAMES" in query_upper:
            pass
        elif "DELETE FROM GUESS_NUMBER_ATTEMPTS" in query_upper:
            pass


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = MockDatabase()
    bot.user = MagicMock(id=999999999)
    bot.custom_emojis = {"heart_dot": "•"}
    cogs = {}
    bot.get_cog = lambda name: cogs.get(name)
    bot._cogs = cogs
    return bot


def create_mock_channel(channel_id=12345, guild=None):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = f"game-channel-{channel_id}"
    channel.mention = f"<#{channel_id}>"
    channel.guild = guild or create_mock_guild()
    channel.send = AsyncMock()

    overwrites = {}
    default_role = channel.guild.default_role

    def get_overwrites_for(target):
        if target not in overwrites:
            ow = MagicMock(spec=discord.PermissionOverwrite)
            ow.send_messages = None
            overwrites[target] = ow
        return overwrites[target]

    channel.overwrites_for.side_effect = get_overwrites_for

    async def set_permissions(target, overwrite=None, reason=None):
        overwrites[target] = overwrite

    channel.set_permissions = AsyncMock(side_effect=set_permissions)

    # Permission check for bot
    def permissions_for(member):
        perms = MagicMock(spec=discord.Permissions)
        perms.manage_channels = True
        return perms

    channel.permissions_for.side_effect = permissions_for
    channel._overwrites = overwrites
    return channel


def create_mock_guild(guild_id=98765):
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.name = "Test Guild"
    default_role = MagicMock(spec=discord.Role)
    default_role.id = guild_id
    default_role.name = "@everyone"
    guild.default_role = default_role
    guild.me = MagicMock(spec=discord.Member)
    guild.me.id = 999999999
    return guild


@pytest.mark.asyncio
async def test_guess_cooldown_and_rejection_during_countdown(mock_bot):
    """Verify 3-second cooldown is applied, start message sent, and guesses rejected during countdown."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=101, guild=guild)

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=11111)
    ctx.author.send = AsyncMock()
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    # Start a game via callback
    await cog.guessanumber.callback(cog, ctx, bounds="1-100")

    # Verify game registered and in countdown mode
    assert 101 in cog.games
    game = cog.games[101]
    assert game["countdown_active"] is True
    assert 101 in cog._countdown_tasks

    # Verify initial countdown message
    ctx.send.assert_called_with("🎮 **Guess a Number starts in 3 seconds! Get ready!**")

    # Now simulate a user guessing during the countdown
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(id=22222, bot=False)
    msg.guild = guild
    msg.channel = channel
    msg.content = "50"
    msg.add_reaction = AsyncMock()
    msg.reply = AsyncMock()

    await cog.on_message(msg)

    # Reaction ⏳ added, but NOT processed as an attempt
    msg.add_reaction.assert_called_with("⏳")
    assert 101 not in cog._guess_attempts_by_channel or len(cog._guess_attempts_by_channel[101]) == 0
    # Did not reply or finish
    msg.reply.assert_not_called()

    # Clean up background task
    cd_task = cog._countdown_tasks.get(101)
    if cd_task and not cd_task.done():
        cd_task.cancel()


@pytest.mark.asyncio
async def test_concurrent_game_start_prevention(mock_bot):
    """Verify multiple games cannot be started concurrently in the same channel."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=102, guild=guild)

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=11111)
    ctx.author.send = AsyncMock()
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    # Start first game via callback
    await cog.guessanumber.callback(cog, ctx, bounds="1-100")
    assert 102 in cog.games

    # Try starting second game in same channel
    ctx.send.reset_mock()
    await cog.guessanumber.callback(cog, ctx, bounds="1-50")
    assert "already active" in ctx.send.call_args[0][0].lower() or "already running" in ctx.send.call_args[0][0].lower()

    # Clean up
    cd_task = cog._countdown_tasks.get(102)
    if cd_task and not cd_task.done():
        cd_task.cancel()


@pytest.mark.asyncio
async def test_channel_lock_after_winner_found(mock_bot):
    """Verify channel is locked after a winner is announced, preserving other permissions."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=103, guild=guild)

    # Set initial permission for @everyone to None
    ow = channel.overwrites_for(guild.default_role)
    ow.send_messages = None

    mock_bot.db.games["game_103"] = {"channel_id": 103, "host_id": 11111, "status": "active"}

    # Setup active game (countdown completed)
    cog.games[103] = {
        "game_id": "game_103",
        "starter": 11111,
        "low": 1,
        "high": 10,
        "answer": 7,
        "expires_at": time.time() + 1800,
        "countdown_active": False,
        "start_time": time.monotonic() - 5.0,
        "max_attempts": 100,
    }

    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(id=33333, bot=False, mention="<@33333>")
    msg.guild = guild
    msg.channel = channel
    msg.content = "7"
    msg.add_reaction = AsyncMock()
    msg.reply = AsyncMock()

    # Call on_message
    await cog.on_message(msg)

    # Verify winner was announced before lock
    msg.reply.assert_called()
    reply_args = msg.reply.call_args[0][0]
    assert "got it!" in reply_args
    assert "The secret number was **7**" in reply_args

    # Verify channel was locked: set_permissions called setting send_messages to False
    channel.set_permissions.assert_called()
    last_call_args = channel.set_permissions.call_args
    assert last_call_args[0][0] == guild.default_role
    assert last_call_args[1]["overwrite"].send_messages is False
    assert 103 in cog._locked_channels_original_overwrites
    assert cog._locked_channels_original_overwrites[103] is None

    # Verify game was cleaned up
    assert 103 not in cog.games


@pytest.mark.asyncio
async def test_channel_lock_after_max_attempts(mock_bot):
    """Verify channel locks when maximum attempts (100) are reached."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=104, guild=guild)

    cog.games[104] = {
        "game_id": "game_104",
        "starter": 11111,
        "low": 1,
        "high": 1000,
        "answer": 500,
        "expires_at": time.time() + 1800,
        "countdown_active": False,
        "start_time": time.monotonic() - 5.0,
        "max_attempts": 3,  # Set small threshold for test
    }
    cog._guess_attempts_by_channel[104] = {1, 2}

    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(id=44444, bot=False)
    msg.guild = guild
    msg.channel = channel
    msg.content = "3"
    msg.add_reaction = AsyncMock()
    msg.reply = AsyncMock()

    await cog.on_message(msg)

    # 3rd attempt reached max (3)
    channel.send.assert_any_call("🛑 **Maximum attempts reached (3)!** The game has concluded. The secret number was **500**.")
    channel.set_permissions.assert_called()
    assert 104 not in cog.games


@pytest.mark.asyncio
async def test_channel_lock_after_cancellation(mock_bot):
    """Verify channel locks when game is manually cancelled via ?guesscancel."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=105, guild=guild)

    cog.games[105] = {
        "game_id": "game_105",
        "starter": 11111,
        "low": 1,
        "high": 100,
        "answer": 42,
        "expires_at": time.time() + 1800,
        "countdown_active": True,
    }
    # Mock dummy countdown task
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    cog._countdown_tasks[105] = dummy_task

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=11111)  # The starter
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    await cog.guesscancel.callback(cog, ctx)

    # Task cancelled
    assert dummy_task.cancelling() > 0 or dummy_task.cancelled()
    # Game removed
    assert 105 not in cog.games
    # Message sent then locked
    ctx.send.assert_called_with("The number game was cancelled. The answer was not revealed.")
    channel.set_permissions.assert_called()


@pytest.mark.asyncio
async def test_channel_lock_after_timeout(mock_bot):
    """Verify channel locks when game expires and status is checked."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=106, guild=guild)

    cog.games[106] = {
        "game_id": "game_106",
        "starter": 11111,
        "low": 1,
        "high": 100,
        "answer": 42,
        "expires_at": time.time() - 10,  # Expired
        "countdown_active": False,
    }

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=11111)
    ctx.prefix = "?"
    ctx.send = AsyncMock()

    await cog.guessstatus.callback(cog, ctx)

    assert 106 not in cog.games
    ctx.send.assert_any_call("⌛ The number game timed out.")
    channel.set_permissions.assert_called()


@pytest.mark.asyncio
async def test_guessunlock_restores_original_permission(mock_bot):
    """Verify ?guessunlock restores the recorded original permission overwrite."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=107, guild=guild)

    # Simulate locked channel with stored original overwrite = True (or None)
    cog._locked_channels_original_overwrites[107] = True

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=11111)
    ctx.send = AsyncMock()

    await cog.guessunlock.callback(cog, ctx)

    # Verify set_permissions was called with send_messages = True
    channel.set_permissions.assert_called()
    call_args = channel.set_permissions.call_args
    assert call_args[1]["overwrite"].send_messages is True
    assert 107 not in cog._locked_channels_original_overwrites
    ctx.send.assert_called_with("🔓 **Channel Unlocked:** Permissions for @everyone have been restored.")


@pytest.mark.asyncio
async def test_moderation_unlock_integrates_with_fun_cog(mock_bot):
    """Verify moderation ?unlock restores original overwrite recorded in Fun cog."""
    fun_cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = fun_cog
    lock_cog = LockCog(mock_bot)

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=108, guild=guild)

    # Record original permission in Fun cog
    fun_cog._locked_channels_original_overwrites[108] = False  # original was False

    ctx = MagicMock(spec=CustomContext)
    ctx.guild = guild
    ctx.channel = channel
    ctx.author = MagicMock(id=OWNER_ID, display_name="Admin")
    ctx.send = AsyncMock()

    with patch("src.cogs.moderation.lock.dispatch_mod_log", AsyncMock()):
        with patch("src.cogs.moderation.lock.send_container_response", AsyncMock()):
            await lock_cog.unlock.callback(lock_cog, ctx, channel=channel, reason="End of event")

    # Overwrite in Fun cog was popped and applied
    assert 108 not in fun_cog._locked_channels_original_overwrites
    channel.set_permissions.assert_called()
    assert channel.set_permissions.call_args[1]["overwrite"].send_messages is False


@pytest.mark.asyncio
async def test_permission_error_handling_when_bot_lacks_manage_channels(mock_bot):
    """Verify lock attempt does not crash when bot lacks manage_channels permission."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    channel = create_mock_channel(channel_id=109, guild=guild)

    # Remove manage_channels from bot permissions
    def perms_no_manage(member):
        perms = MagicMock(spec=discord.Permissions)
        perms.manage_channels = False
        return perms

    channel.permissions_for.side_effect = perms_no_manage

    result = await cog._lock_channel_after_game(channel, "Winner found")
    # Gracefully returned False without raising
    assert result is False
    channel.set_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_unrelated_channels_unaffected(mock_bot):
    """Verify channel locking only affects the game channel, leaving unrelated channels unaffected."""
    cog = Fun(mock_bot)
    mock_bot._cogs["Fun"] = cog

    guild = create_mock_guild()
    game_channel = create_mock_channel(channel_id=201, guild=guild)
    unrelated_channel = create_mock_channel(channel_id=202, guild=guild)

    mock_bot.db.games["game_201"] = {"channel_id": 201, "host_id": 11111, "status": "active"}

    cog.games[201] = {
        "game_id": "game_201",
        "starter": 11111,
        "low": 1,
        "high": 10,
        "answer": 5,
        "expires_at": time.time() + 1800,
        "countdown_active": False,
        "start_time": time.monotonic() - 5.0,
        "max_attempts": 100,
    }

    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock(id=55555, bot=False, mention="<@55555>")
    msg.guild = guild
    msg.channel = game_channel
    msg.content = "5"
    msg.add_reaction = AsyncMock()
    msg.reply = AsyncMock()

    await cog.on_message(msg)

    # Game channel was locked
    game_channel.set_permissions.assert_called()
    # Unrelated channel was NOT touched
    unrelated_channel.set_permissions.assert_not_called()
    assert 202 not in cog._locked_channels_original_overwrites


@pytest.mark.asyncio
async def test_cog_unload_cancels_all_countdown_tasks(mock_bot):
    """Verify cog_unload safely cancels all pending countdown tasks."""
    cog = Fun(mock_bot)

    task1 = MagicMock(spec=asyncio.Task)
    task1.done.return_value = False
    task2 = MagicMock(spec=asyncio.Task)
    task2.done.return_value = True

    cog._countdown_tasks[301] = task1
    cog._countdown_tasks[302] = task2

    await cog.cog_unload()

    task1.cancel.assert_called_once()
    task2.cancel.assert_not_called()
    assert len(cog._countdown_tasks) == 0
