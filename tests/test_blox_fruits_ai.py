"""
Unit tests for Blox Fruits AI cog:
1. Fruit specifications lookup (+fruitinfo).
2. Leveling & grinding navigation (+grindhelp).
3. Trade evaluation calculator (+tradehelp).
4. Meta build advisor (+buildhelp).
5. Conversational AI fallback matching (+bloxai).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import pytest

from src.cogs.general.blox_fruits_ai import BloxFruitsAI, FRUITS_DATABASE, GRINDING_GUIDE, META_BUILDS


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 99887766
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 11223344
    ctx.author.display_name = "BloxMaster"
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def cog():
    c = BloxFruitsAI(MagicMock())
    for attr in dir(c):
        val = getattr(c, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = c
    return c


@pytest.mark.asyncio
async def test_fruitinfo_known_fruits(cog, mock_ctx):
    # Kitsune
    await cog.fruitinfo(mock_ctx, fruit="Kitsune")
    mock_ctx.reply.assert_called_once()
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Kitsune Fruit" in embed.title
    assert "SSS" in str(embed.to_dict())

    # Dough
    mock_ctx.reply.reset_mock()
    await cog.fruitinfo(mock_ctx, fruit="Dough")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Dough Fruit" in embed.title
    assert "Piercing Clothesline" in str(embed.to_dict())


@pytest.mark.asyncio
async def test_fruitinfo_unknown_fruit(cog, mock_ctx):
    await cog.fruitinfo(mock_ctx, fruit="BananaFruitNonExistent")
    assert "not found" in mock_ctx.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_grindhelp_level_ranges(cog, mock_ctx):
    # Sea 1 check (Lv 50 -> Pirate Village)
    await cog.grindhelp(mock_ctx, level=50)
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "First Sea" in str(embed.to_dict())
    assert "Pirate Village" in str(embed.to_dict())

    # Sea 2 check (Lv 1050 -> Hot and Cold)
    mock_ctx.reply.reset_mock()
    await cog.grindhelp(mock_ctx, level=1050)
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Second Sea" in str(embed.to_dict())
    assert "Hot and Cold" in str(embed.to_dict())

    # Sea 3 check (Lv 2500 -> Tiki Outpost)
    mock_ctx.reply.reset_mock()
    await cog.grindhelp(mock_ctx, level=2500)
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Third Sea" in str(embed.to_dict())
    assert "Tiki Outpost" in str(embed.to_dict())


@pytest.mark.asyncio
async def test_tradehelp_evaluator(cog, mock_ctx):
    # Offering Dough (25M) for Kitsune (115M) -> Massive Win for offerer
    await cog.tradehelp(mock_ctx, offer="Dough", target="Kitsune")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "MASSIVE WIN" in embed.description

    # Offering Kitsune (115M) for Ice (500k) -> Massive L
    mock_ctx.reply.reset_mock()
    await cog.tradehelp(mock_ctx, offer="Kitsune", target="Ice")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "MASSIVE L" in embed.description


@pytest.mark.asyncio
async def test_buildhelp_goals(cog, mock_ctx):
    # PvP build
    await cog.buildhelp(mock_ctx, goal="pvp")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Bounty Hunter" in embed.title
    assert "Godhuman" in str(embed.to_dict())

    # Grinding build
    mock_ctx.reply.reset_mock()
    await cog.buildhelp(mock_ctx, goal="grinding")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Buddha" in str(embed.to_dict())

    # Sea beast build
    mock_ctx.reply.reset_mock()
    await cog.buildhelp(mock_ctx, goal="seabeast")
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "Magma V2" in str(embed.to_dict())


@pytest.mark.asyncio
async def test_bloxai_offline_fallback(cog, mock_ctx):
    await cog.bloxai(mock_ctx, question="How do I awaken my Dough fruit in raids?")
    mock_ctx.reply.assert_called_once()
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "BLOX FRUITS AI ASSISTANT" in embed.title
    assert "Raid" in embed.description or "Dough" in embed.description
