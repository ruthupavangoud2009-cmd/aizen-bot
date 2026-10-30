from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cogs.fun.ai_interactions import AIInteractions


def make_message(channel_id: int = 123):
    message = MagicMock()
    message.author.bot = False
    message.author.id = 456
    message.guild.id = 789
    message.guild.name = "Test Guild"
    message.channel.id = channel_id
    message.channel.typing.return_value.__aenter__ = AsyncMock()
    message.channel.typing.return_value.__aexit__ = AsyncMock()
    message.content = "Hello Kyoka"
    message.mentions = []
    message.reply = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_auto_chat_stays_silent_until_channel_is_configured():
    bot = MagicMock()
    bot.user = MagicMock(id=999)
    bot.db.fetch_one = AsyncMock(return_value=None)
    bot.get_context = AsyncMock(return_value=SimpleNamespace(valid=False))
    bot.get_cog.return_value = None
    cog = AIInteractions(bot)
    cog._ask_ai = AsyncMock(return_value="Hello!")
    message = make_message()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        await cog.on_message(message)

    message.reply.assert_not_awaited()
    cog._ask_ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_chat_only_replies_in_the_configured_channel():
    bot = MagicMock()
    bot.user = MagicMock(id=999)
    bot.db.fetch_one = AsyncMock(return_value={"channel_id": 123})
    bot.get_context = AsyncMock(return_value=SimpleNamespace(valid=False))
    bot.get_cog.return_value = None
    cog = AIInteractions(bot)
    cog._ask_ai = AsyncMock(return_value="Hello!")
    message = make_message(channel_id=124)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        await cog.on_message(message)

    message.reply.assert_not_awaited()
    cog._ask_ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_chat_replies_when_configured_channel_matches():
    bot = MagicMock()
    bot.user = MagicMock(id=999)
    bot.db.fetch_one = AsyncMock(return_value={"channel_id": 123})
    bot.get_context = AsyncMock(return_value=SimpleNamespace(valid=False))
    bot.get_cog.return_value = None
    cog = AIInteractions(bot)
    cog._ask_ai = AsyncMock(return_value="Hello!")
    message = make_message(channel_id=123)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        await cog.on_message(message)

    cog._ask_ai.assert_awaited_once_with(789, 123, 456, "Hello Kyoka")
    message.reply.assert_awaited_once()
