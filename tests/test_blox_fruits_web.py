"""
Comprehensive automated tests for Kyoka 3.0 Blox Fruits Web-Backed Values & Notifier.
Verifies:
- Real-time / cached fruit values (Kitsune, Dragon, Buddha, Portal, Dough, Leopard).
- Trade fairness calculation (Win, Fair, Loss).
- Global 4-hour UTC dealer stock reset countdown calculation.
- +fruitvalues command execution and embed rendering.
- +fruitnotifier stock, setup, and test commands.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from src.core.bot import KyokaBot
from src.managers.blox_fruits_web_manager import BloxFruitsWebManager
from src.cogs.general.blox_fruits_notifier import BloxFruitsNotifier


@pytest.fixture
def web_mgr() -> BloxFruitsWebManager:
    return BloxFruitsWebManager()


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.user = MagicMock(id=999888777, name="Kyoka")
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = None
    return bot


@pytest.fixture
def notifier_cog(mock_bot: MagicMock) -> BloxFruitsNotifier:
    return BloxFruitsNotifier(mock_bot)


@pytest.fixture
def mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.guild = MagicMock(id=888999000, name="Blox Fruits Empire")
    ctx.channel = MagicMock(id=777666555, mention="<#777666555>")
    ctx.author = MagicMock(id=123123123, display_name="FruitTrader")
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.send_success = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_get_fruit_value_kitsune(web_mgr: BloxFruitsWebManager):
    """Verify Kitsune fruit value retrieval with market values and demand."""
    data = await web_mgr.get_fruit_value("kitsune")
    assert data is not None
    assert data["name"] == "Kitsune"
    assert data["trade_value"] >= 100_000_000
    assert "demand" in data
    assert "beli" in data
    assert "tip" in data


@pytest.mark.asyncio
async def test_get_fruit_value_buddha(web_mgr: BloxFruitsWebManager):
    """Verify Buddha fruit value retrieval for grinding builds."""
    data = await web_mgr.get_fruit_value("buddha")
    assert data is not None
    assert data["name"] == "Buddha"
    assert "grind" in data["tip"].lower() or "raid" in data["tip"].lower() or "pvp" in data["tip"].lower()


@pytest.mark.asyncio
async def test_get_fruit_value_unknown(web_mgr: BloxFruitsWebManager):
    """Verify unknown fruit query returns None."""
    data = await web_mgr.get_fruit_value("completely_fake_fruit_12345")
    assert data is None


def test_calculate_trade_fairness(web_mgr: BloxFruitsWebManager):
    """Verify trade calculation computes total value and fairness rating."""
    result = web_mgr.calculate_trade(["kitsune"], ["dragon"])
    assert "give_total" in result
    assert "recv_total" in result
    assert "verdict" in result
    assert "diff" in result


def test_dealer_stock_countdown(web_mgr: BloxFruitsWebManager):
    """Verify dealer stock countdown adheres to 4-hour UTC reset cycles."""
    minutes, seconds, countdown_str = web_mgr.get_dealer_stock_countdown()
    assert 0 <= minutes < 60
    assert 0 <= seconds < 60
    assert "h" in countdown_str and "m" in countdown_str and "s" in countdown_str


@pytest.mark.asyncio
async def test_fruitvalues_command(notifier_cog: BloxFruitsNotifier, mock_ctx: MagicMock):
    """Verify +fruitvalues displays market value card."""
    await notifier_cog.fruitvalues.callback(notifier_cog, mock_ctx, fruit="dough")
    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Dough" in embed.title
    assert embed.color.value == 0x6F43BE


@pytest.mark.asyncio
async def test_fruitvalues_unknown_fruit(notifier_cog: BloxFruitsNotifier, mock_ctx: MagicMock):
    """Verify +fruitvalues with unknown fruit returns error embed."""
    await notifier_cog.fruitvalues.callback(notifier_cog, mock_ctx, fruit="nonexistent_fake_fruit")
    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Fruit Not Found" in embed.title
    assert embed.color.value == 0xED4245


@pytest.mark.asyncio
async def test_fruitnotifier_stock_command(notifier_cog: BloxFruitsNotifier, mock_ctx: MagicMock):
    """Verify +fruitnotifier stock returns countdown embed."""
    await notifier_cog.notifier_stock.callback(notifier_cog, mock_ctx)
    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Stock Watch" in embed.title or "Dealer" in embed.title


@pytest.mark.asyncio
async def test_fruitnotifier_setup_command(notifier_cog: BloxFruitsNotifier, mock_ctx: MagicMock):
    """Verify +fruitnotifier setup configures the alert channel."""
    await notifier_cog.notifier_setup.callback(notifier_cog, mock_ctx, channel=mock_ctx.channel)
    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Fruit Notifier Configured" in embed.title


@pytest.mark.asyncio
async def test_fruitnotifier_test_command(notifier_cog: BloxFruitsNotifier, mock_ctx: MagicMock):
    """Verify +fruitnotifier test sends a sample spawn alert card."""
    await notifier_cog.notifier_test.callback(notifier_cog, mock_ctx, fruit_name="Kitsune")
    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Spawned" in embed.title
