from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.moderation.fakeban import FakeBan
from src.security.owner import OWNER_ID


class FakeDatabase:
    async def fetch_one(self, query: str, *args: object) -> None:
        return None

    async def execute(self, query: str, *args: object) -> None:
        return None


def _context(target_channel: object, author_id: int = 123) -> MagicMock:
    ctx = MagicMock()
    ctx.guild.id = 456
    ctx.guild.name = "Test Guild"
    ctx.guild.owner_id = 789
    ctx.guild.get_channel.return_value = None
    ctx.author.id = author_id
    ctx.author.name = "Moderator"
    ctx.author.display_name = "Moderator"
    ctx.author.guild_permissions.ban_members = True
    ctx.channel = target_channel
    ctx.prefix = "+"
    ctx.interaction = None
    ctx.send_success = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.send_warning = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


def test_fakeban_realistic_card_and_dm() -> None:
    async def run() -> None:
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 111
        channel.mention = "#general"
        channel.send = AsyncMock()
        target = MagicMock(spec=discord.Member)
        target.id = 234
        target.display_name = "TargetUser"
        target.name = "TargetUser"
        target.send = AsyncMock()

        bot = MagicMock()
        bot.user.id = 999
        bot.db = FakeDatabase()
        bot.custom_emojis = {}
        cog = FakeBan(bot)
        ctx = _context(channel)

        await cog._execute_fakeban(ctx, target, "Violating rules", send_dm=True)

        # Ensure no real ban was executed
        ctx.guild.ban.assert_not_called()
        ctx.guild.kick.assert_not_called()
        ctx.guild.timeout.assert_not_called()

        # Target should receive a realistic ban notice
        target.send.assert_awaited_once()

    asyncio.run(run())


def test_fakeban_protects_primary_owner() -> None:
    async def run() -> None:
        bot = MagicMock()
        bot.user.id = 999
        bot.db = FakeDatabase()
        cog = FakeBan(bot)
        ctx = _context(MagicMock(spec=discord.TextChannel))
        target = MagicMock(spec=discord.Member)
        target.id = OWNER_ID

        await cog._execute_fakeban(ctx, target, "testing")

        ctx.guild.ban.assert_not_called()

    asyncio.run(run())


def test_fakeban_state_uses_existing_system_state_storage() -> None:
    async def run() -> None:
        database = MagicMock()
        database.execute = AsyncMock()
        cog = FakeBan(SimpleNamespace(db=database, user=None))

        await cog._save_settings(456, {"enabled": False, "channel_id": 321, "send_dm": True})

        query, key, value = database.execute.await_args.args
        assert "system_state" in query
        assert key == "fakeban:456"
        assert json.loads(value) == {"enabled": False, "channel_id": 321, "send_dm": True}

    asyncio.run(run())


if __name__ == "__main__":
    test_fakeban_realistic_card_and_dm()
    test_fakeban_protects_primary_owner()
    test_fakeban_state_uses_existing_system_state_storage()
    print("All FakeBan tests passed successfully!")
