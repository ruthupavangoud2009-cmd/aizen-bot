"""
Automated Test Suite for Kyoka 3.0 Spam Upgrade:
- Roles, @everyone, and @here mass mentions enabled
- Bot staff authorized to use spam command (with 20 count limit)
- Bot staff strictly prevented from targeting/pinging the bot owner
- Primary owner limit is 10,000 count
- Interval / delay between messages is strictly 0.4 seconds
- Bot staff can cancel channel spam tasks, but emergency global cancel is owner-only
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from src.cogs.fun.fun import Fun
from src.core.task_manager import TaskManager
from src.security.owner import OWNER_ID, add_bot_staff, remove_bot_staff


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user.id = 999999999
    bot.owner_id = OWNER_ID
    bot.owner_ids = {OWNER_ID}
    bot.task_mgr = TaskManager(bot)
    return bot


@pytest.fixture
def bot_staff_user():
    staff_id = 888877776666
    add_bot_staff(staff_id)
    yield staff_id
    remove_bot_staff(staff_id)


@pytest.mark.asyncio
async def test_bot_staff_authorized_within_20_limit(mock_bot, bot_staff_user):
    """Bot staff members can run spam up to 20 count with 0.4s interval."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101010
    ctx.guild.id = 202020
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await cog.spam.callback(cog, ctx, count=20, message="Staff spamming safely")

        assert ctx.channel.id in cog._spam_tasks
        await cog._spam_tasks[ctx.channel.id]

        # 1 start message + 20 spam messages = 21 sends
        assert ctx.send.call_count == 21
        # Check start message text contains 0.4s interval
        start_msg = ctx.send.call_args_list[0][0][0]
        assert "20" in start_msg
        assert "0.4s" in start_msg
        assert "enabled" in start_msg

        # Verify interval sleep called with 0.4s
        sleep_args = [call[0][0] for call in mock_sleep.call_args_list if call[0]]
        assert 0.4 in sleep_args


@pytest.mark.asyncio
async def test_bot_staff_count_over_20_rejected(mock_bot, bot_staff_user):
    """Bot staff members attempting count > 20 are rejected."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101011
    ctx.guild.id = 202021
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, count=21, message="Exceeding limit")

    ctx.send.assert_called_once()
    msg = ctx.send.call_args[0][0]
    assert "Choose a count from **1 to 20**" in msg
    assert len(cog._spam_tasks) == 0


@pytest.mark.asyncio
async def test_owner_limit_up_to_10000(mock_bot):
    """Primary owner can spam with count > 20 up to 10,000."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 101012
    ctx.guild.id = 202022
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await cog.spam.callback(cog, ctx, count=100, message="Owner 100 spam")
        assert ctx.channel.id in cog._spam_tasks
        await cog._spam_tasks[ctx.channel.id]

        assert ctx.send.call_count == 101
        start_msg = ctx.send.call_args_list[0][0][0]
        assert "100" in start_msg
        assert "0.4s" in start_msg


@pytest.mark.asyncio
async def test_owner_count_over_10000_rejected(mock_bot):
    """Primary owner attempting count > 10,000 is rejected."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 101013
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, count=10001, message="Too many")

    ctx.send.assert_called_once()
    msg = ctx.send.call_args[0][0]
    assert "Choose a count from **1 to 10,000**" in msg
    assert len(cog._spam_tasks) == 0


@pytest.mark.asyncio
async def test_bot_staff_cannot_target_owner_via_mention_in_message(mock_bot, bot_staff_user):
    """Bot staff cannot spam when OWNER_ID is mentioned in message text."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101014
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    # Try mentioning owner ID in text
    await cog.spam.callback(cog, ctx, count=5, message=f"Wake up <@{OWNER_ID}>!")

    ctx.send.assert_called_once()
    msg = ctx.send.call_args[0][0]
    assert "cannot target or ping the bot owner" in msg
    assert len(cog._spam_tasks) == 0


@pytest.mark.asyncio
async def test_bot_staff_cannot_target_owner_via_ctx_mentions(mock_bot, bot_staff_user):
    """Bot staff cannot spam when OWNER_ID is in ctx.message.mentions."""
    cog = Fun(mock_bot)

    owner_user = MagicMock()
    owner_user.id = OWNER_ID

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101015
    ctx.message.mentions = [owner_user]
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, count=5, message="Hey owner wake up")

    ctx.send.assert_called_once()
    msg = ctx.send.call_args[0][0]
    assert "cannot target or ping the bot owner" in msg
    assert len(cog._spam_tasks) == 0


@pytest.mark.asyncio
async def test_bot_staff_cannot_spam_in_owner_dms(mock_bot, bot_staff_user):
    """Bot staff cannot execute spam in owner's DM channel."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101016
    ctx.channel.recipient = MagicMock(id=OWNER_ID)
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, count=5, message="DM spam")

    ctx.send.assert_called_once()
    msg = ctx.send.call_args[0][0]
    assert "cannot use the spam command on the bot owner" in msg
    assert len(cog._spam_tasks) == 0


@pytest.mark.asyncio
async def test_spam_allows_roles_everyone_here(mock_bot, bot_staff_user):
    """Spam allows @everyone, @here, and roles with proper AllowedMentions."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101017
    ctx.guild.id = 202023
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await cog.spam.callback(cog, ctx, count=3, message="@everyone @here <@&11223344> Raid alert!")
        assert ctx.channel.id in cog._spam_tasks
        await cog._spam_tasks[ctx.channel.id]

        # First send is the control message, next 3 are the spam messages
        assert ctx.send.call_count == 4

        # Check allowed_mentions on spam messages
        spam_call_kwargs = ctx.send.call_args_list[1][1]
        allowed_mentions = spam_call_kwargs.get("allowed_mentions")
        assert allowed_mentions is not None
        assert allowed_mentions.everyone is True
        assert allowed_mentions.roles is True
        assert allowed_mentions.users is True


@pytest.mark.asyncio
async def test_bot_staff_channel_cancel_allowed(mock_bot, bot_staff_user):
    """Bot staff can cancel an active spam task in the channel."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101018
    ctx.guild.id = 202024
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    # Create dummy running task
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    cog._spam_tasks[ctx.channel.id] = dummy_task

    await cog.spamcancel.callback(cog, ctx)

    try:
        await dummy_task
    except asyncio.CancelledError:
        pass

    assert dummy_task.cancelled()
    msg = ctx.send.call_args[0][0]
    assert "cancelled" in msg.lower()


@pytest.mark.asyncio
async def test_bot_staff_cannot_emergency_stop_all(mock_bot, bot_staff_user):
    """Bot staff cannot execute global emergency stop (primary owner only)."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = bot_staff_user
    ctx.channel.id = 101019
    ctx.send = AsyncMock()

    await cog.spamcancel.callback(cog, ctx, target="all")

    msg = ctx.send.call_args[0][0]
    assert "Only the primary bot owner can execute an emergency stop" in msg
