"""
Kyoka Discord Bot - Core Task Manager
Structured background task execution, lifecycle management, and cancellation tracking.
Specialized for high-throughput utilities (e.g. owner repeat/spam tasks) with:
- Unique Task IDs
- Initiating message deletion listeners and automatic cancellation
- Channel-level and global concurrency boundaries
- Emergency global stop (cancel all)
- Graceful shutdown task cleanup
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Set
import discord

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Core.TaskManager")


@dataclass
class SpamTaskInfo:
    """Metadata tracking a running repeat-message spam utility task."""
    task_id: str
    task: asyncio.Task
    guild_id: Optional[int]
    channel_id: int
    invoker_id: int
    initiating_message_id: Optional[int]
    interaction_id: Optional[int]
    count: int
    sent_count: int = 0
    created_at: float = field(default_factory=time.time)
    status: str = "running"
    cancel_reason: Optional[str] = None


class SpamControlView(discord.ui.View):
    """Interactive stop button view attached to active repeat-message output."""

    def __init__(self, task_id: str, task_mgr: TaskManager, invoker_id: int) -> None:
        super().__init__(timeout=300.0)
        self.task_id = task_id
        self.task_mgr = task_mgr
        self.invoker_id = invoker_id

    @discord.ui.button(label="Stop Spam", style=discord.ButtonStyle.danger, emoji="🛑", custom_id="spam_stop_btn")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from src.security.owner import is_primary_owner

        if not (is_primary_owner(interaction.user.id) or interaction.user.id == self.invoker_id):
            await interaction.response.send_message("⛔ Only the task initiator or bot owner can halt this task.", ephemeral=True)
            return

        cancelled = self.task_mgr.cancel_task(self.task_id, reason="interactive_button")
        button.disabled = True
        button.label = "Stopped"
        if cancelled:
            await interaction.response.edit_message(content=f"🛑 Task **{self.task_id}** was stopped by user request.", view=self)
        else:
            await interaction.response.edit_message(content=f"ℹ️ Task **{self.task_id}** was already finished or stopped.", view=self)

    async def trigger_stop(self, interaction: discord.Interaction) -> None:
        """Helper to invoke the stop button handler directly."""
        await self.stop_button.callback(interaction)


class TaskManager:
    """Core manager tracking structured background tasks and handling cancellation events."""

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._spam_tasks: Dict[str, SpamTaskInfo] = {}
        self._msg_to_task_id: Dict[int, str] = {}
        self._channel_to_task_id: Dict[int, str] = {}
        self._task_counter: int = 0
        self._lock = asyncio.Lock()

    def get_next_task_id(self) -> str:
        """Generate a sequential unique task ID."""
        self._task_counter += 1
        return f"SPAM-{self._task_counter:04d}"

    def register_spam_task(
        self,
        task_id: str,
        task: asyncio.Task,
        guild_id: Optional[int],
        channel_id: int,
        invoker_id: int,
        initiating_message_id: Optional[int] = None,
        interaction_id: Optional[int] = None,
        count: int = 0,
    ) -> SpamTaskInfo:
        """Register a new active spam task."""
        task_info = SpamTaskInfo(
            task_id=task_id,
            task=task,
            guild_id=guild_id,
            channel_id=channel_id,
            invoker_id=invoker_id,
            initiating_message_id=initiating_message_id,
            interaction_id=interaction_id,
            count=count,
        )
        self._spam_tasks[task_id] = task_info
        self._channel_to_task_id[channel_id] = task_id
        if initiating_message_id:
            self._msg_to_task_id[initiating_message_id] = task_id
        logger.info(f"[TaskManager] Registered task {task_id} in channel {channel_id} (msg: {initiating_message_id}).")
        return task_info

    def get_task_by_channel(self, channel_id: int) -> Optional[SpamTaskInfo]:
        """Fetch active task for channel if one exists and is still running."""
        task_id = self._channel_to_task_id.get(channel_id)
        if task_id and task_id in self._spam_tasks:
            info = self._spam_tasks[task_id]
            if not info.task.done():
                return info
        return None

    def cancel_task(self, task_id: str, reason: str = "manual_cancel") -> bool:
        """Cancel a specific task by task ID."""
        info = self._spam_tasks.get(task_id)
        if not info or info.task.done():
            return False

        info.status = "cancelled"
        info.cancel_reason = reason
        info.task.cancel()
        logger.info(f"[TaskManager] Cancelled task {task_id} (reason: {reason}).")
        return True

    def cancel_by_message_id(self, message_id: int, reason: str = "message_deleted") -> bool:
        """Cancel the task whose initiating message was deleted or invalidated."""
        task_id = self._msg_to_task_id.get(message_id)
        if task_id:
            logger.info(f"[TaskManager] Initiating message {message_id} was deleted; cancelling task {task_id}.")
            return self.cancel_task(task_id, reason=reason)
        return False

    def cancel_by_channel(self, channel_id: int, reason: str = "channel_cancel") -> Optional[str]:
        """Cancel the active task running in a channel."""
        task_id = self._channel_to_task_id.get(channel_id)
        if task_id and self.cancel_task(task_id, reason=reason):
            return task_id
        return None

    def cancel_all(self, reason: str = "emergency_stop") -> int:
        """Cancel all active spam tasks across all channels."""
        cancelled_count = 0
        for task_id, info in list(self._spam_tasks.items()):
            if not info.task.done():
                info.status = "cancelled"
                info.cancel_reason = reason
                info.task.cancel()
                cancelled_count += 1
        logger.warning(f"[TaskManager] Emergency stop cancelled {cancelled_count} active spam tasks.")
        return cancelled_count

    def unregister_task(self, task_id: str) -> None:
        """Clean up mappings after a task finishes or is cancelled."""
        info = self._spam_tasks.pop(task_id, None)
        if info:
            if self._channel_to_task_id.get(info.channel_id) == task_id:
                self._channel_to_task_id.pop(info.channel_id, None)
            if info.initiating_message_id and self._msg_to_task_id.get(info.initiating_message_id) == task_id:
                self._msg_to_task_id.pop(info.initiating_message_id, None)

    async def shutdown(self) -> None:
        """Cancel and await all active tasks gracefully on bot shutdown."""
        tasks_to_await: list[asyncio.Task] = []
        for info in self._spam_tasks.values():
            if not info.task.done():
                info.task.cancel()
                tasks_to_await.append(info.task)

        if tasks_to_await:
            logger.info(f"[TaskManager] Awaiting shutdown of {len(tasks_to_await)} tasks...")
            await asyncio.gather(*tasks_to_await, return_exceptions=True)

        self._spam_tasks.clear()
        self._msg_to_task_id.clear()
        self._channel_to_task_id.clear()
