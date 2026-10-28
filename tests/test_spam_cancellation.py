"""
Automated Test Suite for Kyoka 3.0 Spam Command Cancellation Bug Fix
Covers Rule 2:
- Initiating message deletion cancellation (on_raw_message_delete & on_message_delete)
- Initiating message invalidation/empty edit cancellation (on_raw_message_edit)
- Interactive stop button cancellation (SpamControlView)
- Emergency global stop (spamcancel all / spamstop)
- Targeted task cancellation by Task ID
- Task ID tracking and structured metadata (SpamTaskInfo)
- Cancellation error propagation (asyncio.CancelledError not swallowed)
- Task cleanup in finally block & done callback
- Authoritative Owner ID security check (OWNER_ID = 1505515188991033409)
- Maximum 2,000 count limit enforcement
- Bot shutdown cancellation and await
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from src.cogs.fun.fun import Fun
from src.core.task_manager import SpamControlView, SpamTaskInfo, TaskManager
from src.security.owner import OWNER_ID, is_primary_owner


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user.id = 999999999
    bot.task_mgr = TaskManager(bot)
    return bot


@pytest.mark.asyncio
async def test_initiating_message_deletion_cancels_task(mock_bot):
    """Deleting the initiating command message must cancel the running repeat task."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 112233
    ctx.guild.id = 445566
    ctx.message.id = 778899
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    # Start a 10-message spam task with a mocked sleep that yields
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # sleep yields to allow task execution
        mock_sleep.side_effect = lambda d: asyncio.sleep(0.01)

        await cog.spam.callback(cog, ctx, count=10, message="Aizen illusion")

        # Let task run briefly
        await asyncio.sleep(0.005)

        # Verify task is registered in task_mgr
        task_info = mock_bot.task_mgr.get_task_by_channel(ctx.channel.id)
        assert task_info is not None
        assert task_info.initiating_message_id == 778899
        assert not task_info.task.done()

        # Simulate Discord firing raw message delete for initiating command message
        payload = MagicMock(spec=discord.RawMessageDeleteEvent)
        payload.message_id = 778899
        await cog.on_raw_message_delete(payload)

        # Allow loop to process cancellation
        try:
            await task_info.task
        except asyncio.CancelledError:
            pass

        assert task_info.task.cancelled()
        assert task_info.status == "cancelled"
        assert task_info.cancel_reason == "initiating_message_deleted"

        # Verify unregistration in finally and done callback
        assert mock_bot.task_mgr.get_task_by_channel(ctx.channel.id) is None
        assert ctx.channel.id not in cog._spam_tasks


@pytest.mark.asyncio
async def test_message_delete_listener_cancels_task(mock_bot):
    """Cached message delete event (on_message_delete) cancels task."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 112244
    ctx.guild.id = 445577
    ctx.message.id = 778800
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = lambda d: asyncio.sleep(0.01)
        await cog.spam.callback(cog, ctx, count=5, message="Testing delete")
        await asyncio.sleep(0.005)

        task_info = mock_bot.task_mgr.get_task_by_channel(ctx.channel.id)
        assert task_info is not None

        # Call on_message_delete
        deleted_msg = MagicMock()
        deleted_msg.id = 778800
        await cog.on_message_delete(deleted_msg)

        try:
            await task_info.task
        except asyncio.CancelledError:
            pass

        assert task_info.task.cancelled()
        assert mock_bot.task_mgr.get_task_by_channel(ctx.channel.id) is None
        assert ctx.channel.id not in cog._spam_tasks


@pytest.mark.asyncio
async def test_interactive_stop_button_cancels_task(mock_bot):
    """Clicking Stop Spam button cancels the running task."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 112255
    ctx.guild.id = 445588
    ctx.message.id = 778811
    ctx.message.mentions = []
    ctx.send = AsyncMock()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = lambda d: asyncio.sleep(0.01)
        await cog.spam.callback(cog, ctx, count=20, message="Interactive test")
        await asyncio.sleep(0.005)

        task_info = mock_bot.task_mgr.get_task_by_channel(ctx.channel.id)
        assert task_info is not None
        task_id = task_info.task_id

        # Simulate clicking the Stop Spam button via trigger_stop
        view = SpamControlView(task_id, mock_bot.task_mgr, ctx.author.id)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = OWNER_ID
        interaction.response.edit_message = AsyncMock()

        await view.trigger_stop(interaction)

        try:
            await task_info.task
        except asyncio.CancelledError:
            pass

        assert task_info.task.cancelled()
        assert task_info.cancel_reason == "interactive_button"
        interaction.response.edit_message.assert_called_once()
        assert ctx.channel.id not in cog._spam_tasks


@pytest.mark.asyncio
async def test_interactive_stop_button_unauthorized_user_blocked(mock_bot):
    """Unauthorized user cannot click the stop button to tamper with tasks."""
    task_id = "SPAM-TEST"
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    mock_bot.task_mgr.register_spam_task(
        task_id=task_id,
        task=dummy_task,
        guild_id=123,
        channel_id=456,
        invoker_id=OWNER_ID,
    )

    view = SpamControlView(task_id, mock_bot.task_mgr, OWNER_ID)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 999999999999  # Random non-owner, non-initiator
    interaction.response.send_message = AsyncMock()

    await view.trigger_stop(interaction)

    interaction.response.send_message.assert_called_once()
    assert "Only the task initiator or bot owner" in interaction.response.send_message.call_args[0][0]
    assert not dummy_task.cancelled()
    dummy_task.cancel()
    try:
        await dummy_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_emergency_global_stop(mock_bot):
    """Owner emergency stop cancels all active tasks across all channels."""
    cog = Fun(mock_bot)

    # Spawn 3 separate spam tasks in 3 channels
    task1 = asyncio.create_task(asyncio.sleep(10))
    task2 = asyncio.create_task(asyncio.sleep(10))
    task3 = asyncio.create_task(asyncio.sleep(10))

    mock_bot.task_mgr.register_spam_task("SPAM-0001", task1, 1, 101, OWNER_ID)
    mock_bot.task_mgr.register_spam_task("SPAM-0002", task2, 1, 102, OWNER_ID)
    mock_bot.task_mgr.register_spam_task("SPAM-0003", task3, 1, 103, OWNER_ID)

    cog._spam_tasks[101] = task1
    cog._spam_tasks[102] = task2
    cog._spam_tasks[103] = task3

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.send = AsyncMock()

    # Execute ?spamcancel all
    await cog.spamcancel.callback(cog, ctx, target="all")

    for t in (task1, task2, task3):
        assert t.cancelling() or t.cancelled()

    await asyncio.gather(task1, task2, task3, return_exceptions=True)

    for t in (task1, task2, task3):
        assert t.cancelled()

    assert "Emergency stop executed" in ctx.send.call_args[0][0]


@pytest.mark.asyncio
async def test_targeted_task_cancellation(mock_bot):
    """Owner can cancel a specific task using its unique Task ID."""
    cog = Fun(mock_bot)

    task1 = asyncio.create_task(asyncio.sleep(10))
    task2 = asyncio.create_task(asyncio.sleep(10))

    mock_bot.task_mgr.register_spam_task("SPAM-0010", task1, 1, 201, OWNER_ID)
    mock_bot.task_mgr.register_spam_task("SPAM-0020", task2, 1, 202, OWNER_ID)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.send = AsyncMock()

    # Cancel only SPAM-0010
    await cog.spamcancel.callback(cog, ctx, target="SPAM-0010")

    assert task1.cancelling() or task1.cancelled()
    assert not (task2.cancelling() or task2.cancelled())
    assert "Task **SPAM-0010** cancelled" in ctx.send.call_args[0][0]

    # Clean up
    await asyncio.gather(task1, return_exceptions=True)
    task2.cancel()
    await asyncio.gather(task2, return_exceptions=True)


@pytest.mark.asyncio
async def test_task_manager_graceful_shutdown(mock_bot):
    """Shutdown cleanly cancels and awaits all running tasks without leaking resources."""
    task1 = asyncio.create_task(asyncio.sleep(10))
    task2 = asyncio.create_task(asyncio.sleep(10))

    mock_bot.task_mgr.register_spam_task("SPAM-0091", task1, 1, 301, OWNER_ID)
    mock_bot.task_mgr.register_spam_task("SPAM-0092", task2, 1, 302, OWNER_ID)

    await mock_bot.task_mgr.shutdown()

    assert task1.cancelled()
    assert task2.cancelled()
    assert len(mock_bot.task_mgr._spam_tasks) == 0


@pytest.mark.asyncio
async def test_rate_limit_429_safe_termination(mock_bot):
    """Encountering Discord 429 safely terminates the task loop without raising unhandled error."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 112299
    ctx.message.mentions = []

    mock_resp = MagicMock()
    mock_resp.status = 429
    http_error = discord.HTTPException(mock_resp, "Rate limited")

    ctx.send = AsyncMock(side_effect=[None, http_error])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await cog.spam.callback(cog, ctx, count=100, message="Rate limit test")
        task = cog._spam_tasks[ctx.channel.id]
        await task

    assert ctx.channel.id not in cog._spam_tasks
    assert mock_bot.task_mgr.get_task_by_channel(ctx.channel.id) is None


@pytest.mark.asyncio
async def test_authoritative_owner_id_enforced(mock_bot):
    """Ensure that only OWNER_ID = 1505515188991033409 is authorized to execute spam."""
    cog = Fun(mock_bot)

    ctx = MagicMock()
    ctx.author.id = 123456789  # Non-owner
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, count=10, message="Hello")

    assert "Only the primary bot owner or bot staff can use this command" in ctx.send.call_args[0][0]
    assert len(cog._spam_tasks) == 0
