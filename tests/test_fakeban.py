from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

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
    ctx.guild.owner_id = 789
    ctx.guild.get_channel.return_value = None
    ctx.author.id = author_id
    ctx.author.name = "Moderator"
    ctx.channel = target_channel
    ctx.prefix = "+"
    ctx.send_success = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.send_warning = AsyncMock()
    ctx.send = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_fakeban_posts_unmistakable_simulation_and_never_bans_member(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "#mod-log"
    channel.send = AsyncMock()
    target = SimpleNamespace(id=234, mention="<@234>", send=AsyncMock())
    bot = MagicMock()
    bot.user.id = 999
    bot.db = FakeDatabase()
    cog = FakeBan(bot)
    ctx = _context(channel)

    await cog._simulate(ctx, target, "testing", send_dm=True)

    embed = channel.send.await_args.kwargs["embed"]
    assert "NOT A REAL BAN" in embed.title
    assert "No moderation action was taken" in embed.description
    target.send.assert_awaited_once()
    ctx.send_success.assert_awaited_once()
    ctx.guild.ban.assert_not_called()
    ctx.guild.kick.assert_not_called()
    ctx.guild.timeout.assert_not_called()


@pytest.mark.asyncio
async def test_fakeban_protects_primary_owner() -> None:
    bot = MagicMock()
    bot.user.id = 999
    bot.db = FakeDatabase()
    cog = FakeBan(bot)
    ctx = _context(MagicMock(spec=discord.TextChannel))
    target = SimpleNamespace(id=OWNER_ID, mention=f"<@{OWNER_ID}>", send=AsyncMock())

    await cog._simulate(ctx, target, "testing")

    ctx.send_error.assert_awaited_once()
    ctx.channel.send.assert_not_awaited()


def test_fakeban_state_uses_existing_system_state_storage() -> None:
    async def run() -> None:
        database = MagicMock()
        database.execute = AsyncMock()
        cog = FakeBan(SimpleNamespace(db=database, user=None))

        await cog._save_settings(456, {"enabled": False, "channel_id": 321})

        query, key, value = database.execute.await_args.args
        assert "system_state" in query
        assert key == "fakeban:456"
        assert json.loads(value) == {"enabled": False, "channel_id": 321}

    asyncio.run(run())
