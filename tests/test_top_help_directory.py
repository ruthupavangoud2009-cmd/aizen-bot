import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.cogs.general.top_ai_manager import TopAIManager
from src.cogs.general.help import Help
from src.security.adult_guard import add_adult_user, remove_adult_user, is_adult_authorized

@pytest.mark.asyncio
async def test_top_help_command_registration():
    bot_mock = MagicMock()
    cog = TopAIManager(bot_mock)
    
    # Check that 'help' subcommand is registered on top_group
    help_cmd = cog.top_group.get_command("help")
    assert help_cmd is not None
    assert help_cmd.name == "help"

    # Mock context and help cog
    ctx_mock = MagicMock()
    ctx_mock.reply = AsyncMock()
    
    help_cog_mock = MagicMock()
    help_cog_mock.help_command = AsyncMock()
    bot_mock.get_cog.return_value = help_cog_mock

    # Invoke top_help_subcmd callback
    await cog.top_help_subcmd.callback(cog, ctx_mock, command_or_module=None)
    help_cog_mock.help_command.assert_called_once_with(ctx_mock, command_or_module=None)

@pytest.mark.asyncio
async def test_help_category_permission_filtering():
    bot_mock = MagicMock()
    bot_mock.commands = []
    bot_mock.cogs = {}
    bot_mock.guild_mgr = MagicMock()
    bot_mock.guild_mgr.get_prefix.return_value = "?"
    bot_mock.perm_mgr = MagicMock()
    bot_mock.perm_mgr.is_developer_sync.return_value = False

    help_cog = Help(bot_mock)

    # Test normal user vs primary owner (1505515188991033409)
    normal_ctx = MagicMock()
    normal_ctx.author.id = 999999999
    normal_ctx.guild = MagicMock()
    normal_ctx.guild.id = 12345
    normal_ctx.guild.owner_id = 111111111

    owner_ctx = MagicMock()
    owner_ctx.author.id = 1505515188991033409
    owner_ctx.guild = normal_ctx.guild

    # Check adult permission check
    dummy_adult_cmd = MagicMock()
    dummy_adult_cmd.hidden = False
    dummy_adult_cmd.name = "adulthumor"
    dummy_adult_cmd.qualified_name = "adulthumor"
    dummy_adult_cmd.cog = MagicMock()
    dummy_adult_cmd.cog.category = "Adult Humor — Restricted"
    dummy_adult_cmd.cog.qualified_name = "AdultHumor"

    # Normal user is not authorized
    assert help_cog._can_run_command(dummy_adult_cmd, normal_ctx) is False

    # Primary owner is authorized
    assert help_cog._can_run_command(dummy_adult_cmd, owner_ctx) is True
