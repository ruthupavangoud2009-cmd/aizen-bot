import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.core.bot import KyokaBot


def test_calculate_presence_stats_multi_guild():
    """Verify calculate_presence_stats sums valid guilds and managed members accurately."""
    bot = KyokaBot()

    # Create mock guilds
    g1 = MagicMock()
    g1.unavailable = False
    g1.member_count = 101  # 100 managed (excluding bot)

    g2 = MagicMock()
    g2.unavailable = False
    g2.member_count = 501  # 500 managed

    bot._connection._guilds = {1: g1, 2: g2}

    servers, members = bot.calculate_presence_stats()
    assert servers == 2
    assert members == 600


def test_calculate_presence_stats_handles_unavailable_and_missing_counts():
    """Verify unavailable guilds and None/invalid member counts are handled safely without crashing."""
    bot = KyokaBot()

    g1 = MagicMock()
    g1.unavailable = False
    g1.member_count = 50

    g2 = MagicMock()
    g2.unavailable = True  # Unavailable during outage/shard split
    g2.member_count = 1000

    g3 = MagicMock()
    g3.unavailable = False
    g3.member_count = None  # Missing member count

    g4 = MagicMock()
    g4.unavailable = False
    g4.member_count = 0  # 0 count

    bot._connection._guilds = {1: g1, 2: g2, 3: g3, 4: g4}

    servers, members = bot.calculate_presence_stats()
    # Only g1, g3, g4 are available = 3 servers
    assert servers == 3
    # Only g1 has valid count > 0: max(0, 50 - 1) = 49
    assert members == 49


def test_format_presence_activity_text_plural():
    """Verify formatting with comma separators for multiple servers and members."""
    bot = KyokaBot()
    text = bot.format_presence_activity_text(125, 45680)
    assert text == "over 125 servers | 45,680 members"


def test_format_presence_activity_text_singular():
    """Verify singular grammar for 1 server and 1 member."""
    bot = KyokaBot()
    text = bot.format_presence_activity_text(1, 1)
    assert text == "over 1 server | 1 member"


def test_format_presence_activity_text_zero_members():
    """Verify fallback when members is 0."""
    bot = KyokaBot()
    text = bot.format_presence_activity_text(5, 0)
    assert text == "over 5 servers"


def test_format_presence_activity_text_length_limit():
    """Verify text never exceeds Discord 128 character limit."""
    bot = KyokaBot()
    text = bot.format_presence_activity_text(10**15, 10**25)
    assert len(text) <= 128


@pytest.mark.asyncio
async def test_update_dynamic_presence_calls_change_presence():
    """Verify update_dynamic_presence sets Watching activity and Online status."""
    bot = KyokaBot()
    bot.change_presence = AsyncMock()

    g = MagicMock()
    g.unavailable = False
    g.member_count = 1001
    bot._connection._guilds = {1: g}

    await bot.update_dynamic_presence()

    assert bot.change_presence.called
    kwargs = bot.change_presence.call_args[1]
    assert kwargs.get("status") == discord.Status.online
    activity = kwargs.get("activity")
    assert activity.type == discord.ActivityType.watching
    assert activity.name == "over 1 server | 1,000 members"


@pytest.mark.asyncio
async def test_guild_join_and_remove_trigger_presence_refresh():
    """Verify on_guild_join and on_guild_remove refresh dynamic presence."""
    bot = KyokaBot()
    bot.update_dynamic_presence = AsyncMock()

    guild = MagicMock(id=999, name="Test Guild")

    # on_guild_join
    with patch("src.core.greetings.send_guild_welcome_card", new=AsyncMock()):
        await bot.on_guild_join(guild)
        assert bot.update_dynamic_presence.called

    bot.update_dynamic_presence.reset_mock()

    # on_guild_remove
    await bot.on_guild_remove(guild)
    assert bot.update_dynamic_presence.called
