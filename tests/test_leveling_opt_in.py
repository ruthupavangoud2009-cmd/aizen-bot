import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.core.bot import KyokaBot
from src.managers.leveling_manager import LevelingManager
from src.cogs.general.leveling import Leveling


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value="OK")
    return db


@pytest.fixture
def leveling_mgr(mock_db):
    return LevelingManager(mock_db)


@pytest.mark.asyncio
async def test_guild_default_state_is_disabled_off(leveling_mgr):
    """The default state for any new server must be OFF (disabled)."""
    assert leveling_mgr.is_enabled(123456789) is False
    settings = leveling_mgr.get_guild_settings(123456789)
    assert settings["enabled"] is False
    assert settings["announce"] is False


@pytest.mark.asyncio
async def test_award_xp_returns_false_and_zero_db_writes_when_disabled(leveling_mgr, mock_db):
    """When disabled, stop automatically awarding XP and generating rank-up events."""
    # Ensure guild is disabled
    assert leveling_mgr.is_enabled(999) is False

    awarded, new_xp, new_lvl, leveled_up = await leveling_mgr.award_message_xp(
        guild_id=999,
        user_id=888,
        is_opted_out=False,
    )

    assert awarded is False
    assert new_xp == 0
    assert new_lvl == 1
    assert leveled_up is False
    # No queries to fetch profile or insert/update XP should be made
    assert mock_db.fetch_one.call_count == 0
    assert mock_db.execute.call_count == 0


@pytest.mark.asyncio
async def test_server_setting_isolation(leveling_mgr, mock_db):
    """One server's choice to enable or disable leveling must never change another server's setting."""
    guild_a = 1111111111
    guild_b = 2222222222

    # Initially both are disabled
    assert leveling_mgr.is_enabled(guild_a) is False
    assert leveling_mgr.is_enabled(guild_b) is False

    # Enable on Guild A
    await leveling_mgr.set_guild_enabled(guild_a, True, announce=True)

    assert leveling_mgr.is_enabled(guild_a) is True
    assert leveling_mgr.get_guild_settings(guild_a)["announce"] is True

    # Guild B must remain completely disabled
    assert leveling_mgr.is_enabled(guild_b) is False
    assert leveling_mgr.get_guild_settings(guild_b)["enabled"] is False

    # Disabling Guild A leaves Guild B unchanged
    await leveling_mgr.set_guild_enabled(guild_a, False)
    assert leveling_mgr.is_enabled(guild_a) is False
    assert leveling_mgr.is_enabled(guild_b) is False


@pytest.mark.asyncio
async def test_existing_data_preserved_when_toggling_leveling(leveling_mgr, mock_db):
    """Preserve existing leveling data and database records; do not delete anyone's saved XP."""
    guild_id = 55555
    user_id = 44444

    # Enable and award XP
    await leveling_mgr.set_guild_enabled(guild_id, True)
    assert leveling_mgr.is_enabled(guild_id) is True

    mock_db.fetch_one.return_value = {"xp": 500, "level": 2}
    awarded, new_xp, new_lvl, leveled_up = await leveling_mgr.award_message_xp(guild_id, user_id)
    assert awarded is True
    assert new_xp > 500

    # Now disable leveling
    await leveling_mgr.set_guild_enabled(guild_id, False)
    assert leveling_mgr.is_enabled(guild_id) is False

    # Verify query for user rank still returns preserved data
    mock_db.fetch_one.return_value = {"xp": new_xp, "level": new_lvl}
    mock_db.fetch_val = AsyncMock(return_value=1)
    rank_data = await leveling_mgr.get_user_rank(guild_id, user_id)
    assert rank_data["total_xp"] == new_xp
    assert rank_data["level"] == new_lvl

    # Verify no DELETE FROM user_profiles was executed
    for call in mock_db.execute.call_args_list:
        query = call[0][0]
        assert "DELETE FROM user_profiles" not in query


@pytest.mark.asyncio
async def test_bot_on_message_skips_xp_task_when_disabled():
    """Bot on_message does not create background XP tasks when leveling is disabled."""
    bot = KyokaBot()
    bot.leveling_mgr = MagicMock()
    bot.leveling_mgr.is_enabled = MagicMock(return_value=False)

    message = MagicMock()
    message.author.bot = False
    message.mentions = []
    message.mention_everyone = False
    message.guild = MagicMock(id=777)
    message.content = "hello world"

    with patch("asyncio.create_task") as mock_task, \
         patch.object(bot, "process_commands", new=AsyncMock()):
        await bot.on_message(message)
        # Should NOT have spawned _process_message_xp task
        for call in mock_task.call_args_list:
            coro = call[0][0]
            assert "_process_message_xp" not in getattr(coro, "__name__", "")


@pytest.mark.asyncio
async def test_levelenable_and_leveldisable_commands():
    """Verify levelenable and leveldisable commands update configuration correctly."""
    bot = KyokaBot()
    bot.leveling_mgr = MagicMock()
    bot.leveling_mgr.is_enabled = MagicMock(return_value=False)
    bot.leveling_mgr.set_guild_enabled = AsyncMock()

    cog = Leveling(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=888, name="Test Guild")
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.send = AsyncMock()
    ctx.interaction = None
    ctx.send_warning = AsyncMock()
    ctx.send_error = AsyncMock()
    ctx.send_success = AsyncMock()

    # Test levelenable
    with patch("src.utils.containers.send_container_response", new=AsyncMock()) as mock_send, \
         patch("src.cogs.general.leveling.send_container_response", new=AsyncMock()):
        await cog.level_enable.callback(cog, ctx, announce=True)
        bot.leveling_mgr.set_guild_enabled.assert_called_with(888, True, announce=True)

    # Test leveldisable
    with patch("src.utils.containers.send_container_response", new=AsyncMock()) as mock_send, \
         patch("src.cogs.general.leveling.send_container_response", new=AsyncMock()):
        await cog.level_disable.callback(cog, ctx)
        bot.leveling_mgr.set_guild_enabled.assert_called_with(888, False)
