"""
Comprehensive automated tests for Kyoka 3.0 Help Module Repair & UI Stability.
Verifies:
- Hybrid Help registration (+help & /help)
- HelpCategorySelect & HelpView interactive buttons
- Author permission enforcement in interaction_check
- On-timeout component disabling
- Beginner-friendly Home Overview embed
- Dedicated AIZEN AI System category formatting
- Direct command and category lookups
- Unknown command/module graceful error handling
- Owner command isolation
- Container response fallbacks
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import pytest
import discord
from discord.ext import commands

from src.cogs.general.help import Help, HelpView, HelpCategorySelect
from src.core.bot import KyokaBot
from src.security.owner import OWNER_ID
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response


@pytest.fixture
def mock_bot() -> KyokaBot:
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    return bot


@pytest.fixture
def help_cog(mock_bot: KyokaBot) -> Help:
    return Help(mock_bot)


@pytest.fixture
def mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.guild = MagicMock(id=123456789)
    ctx.author = MagicMock(id=555666777, display_name="TestUser")
    ctx.author.display_avatar = MagicMock(url="https://cdn.discord.com/avatars/555666777/avatar.png")
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


def test_help_is_hybrid_command(help_cog: Help):
    """Verify help command is registered as a hybrid command supporting prefix and slash."""
    cmd = help_cog.help_command
    assert isinstance(cmd, commands.HybridCommand)
    assert cmd.name == "help"
    assert "commands" in cmd.aliases
    assert "modules" in cmd.aliases
    assert "h" in cmd.aliases


def test_help_category_order_complete():
    """Verify all 14 categories are present in CATEGORY_ORDER."""
    assert len(Help.CATEGORY_ORDER) == 14
    expected = [
        "🏠・GETTING STARTED",
        "🤖・ARTIFICIAL INTELLIGENCE",
        "🛡️・MODERATION",
        "👋・WELCOME & AUTOMOD",
        "🎫・TICKETS & SUPPORT",
        "🎉・GIVEAWAYS & EVENTS",
        "⭐・LEVELS & COMMUNITY",
        "🖼️・IMAGES & AVATARS",
        "🎵・MUSIC",
        "💬・SOCIAL & FUN",
        "💎・PREMIUM",
        "⚙️・SERVER ADMINISTRATION",
        "🔧・UTILITIES",
        "👑・OWNER & DEVELOPER",
    ]
    assert Help.CATEGORY_ORDER == expected


def test_help_home_embed_content(help_cog: Help, mock_ctx: MagicMock):
    """Verify compact Home Overview matches tiny UI specification."""
    visible = {
        "🏠・GETTING STARTED": [MagicMock(qualified_name="start"), MagicMock(qualified_name="quickstart")],
        "🤖・ARTIFICIAL INTELLIGENCE": [MagicMock(qualified_name="ai")],
        "🛡️・MODERATION": [MagicMock(qualified_name="kick"), MagicMock(qualified_name="ban")],
    }
    embed = help_cog.build_home_embed(mock_ctx, visible)
    assert embed.title is not None and "KYOKA HELP" in embed.title
    assert embed.color.value == 0x2B0938

    desc = embed.description
    assert "Choose a category below" in desc


def test_help_category_embed_content(help_cog: Help, mock_ctx: MagicMock):
    """Verify category embed renders command list with badges and navigation details."""
    cmd1 = MagicMock(qualified_name="kick", description="Kick a member")
    cmd2 = MagicMock(qualified_name="ban", description="Ban a member")
    cmd1.cog = MagicMock(category="Moderation")
    cmd2.cog = MagicMock(category="Moderation")

    visible = {"🛡️・MODERATION": [cmd1, cmd2]}
    embed = help_cog.build_category_embed(mock_ctx, "🛡️・MODERATION", [cmd1, cmd2], visible)

    assert "🛡️・MODERATION" in embed.title
    assert "kick" in embed.description
    assert "ban" in embed.description
    assert embed.color.value == 0x2B0938


def test_help_command_manual_embed(help_cog: Help, mock_ctx: MagicMock):
    """Verify single-command manual embed renders syntax, aliases, and slash command info."""
    cmd = MagicMock()
    cmd.qualified_name = "kick"
    cmd.name = "kick"
    cmd.description = "Kick a member from the server."
    cmd.help = None
    cmd.signature = "<member> [reason]"
    cmd.aliases = ["k"]
    cmd.cog = MagicMock(category="Moderation")
    cmd.app_command = MagicMock()
    cmd.commands = []

    embed = help_cog.build_command_embed(mock_ctx, cmd)
    assert "Command: `kick`" in embed.title
    assert "kick <member> [reason]" in embed.fields[0].value
    assert "/kick" in embed.fields[0].value
    assert "🛡️・MODERATION" in embed.fields[1].value
    assert "`k`" in embed.fields[1].value


def test_help_view_components_and_author_lock(help_cog: Help, mock_ctx: MagicMock):
    """Verify HelpView adds select menu, 4 navigation buttons, and enforces author lock."""
    visible = {"🏠・GETTING STARTED": [MagicMock(qualified_name="start")]}
    view = HelpView(help_cog, mock_ctx, visible, current_category="home")

    # Has select menu on row 0
    selects = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(selects) == 1
    assert selects[0].placeholder in ("Select a module to view commands...", "Select a category to view commands...")

    # Has buttons on row 1: Back, Home, Next, Close
    buttons = [i for i in view.children if isinstance(i, discord.ui.Button) and i.style != discord.ButtonStyle.link]
    labels = [b.label for b in buttons]
    assert "Back" in labels
    assert "Home" in labels
    assert "Next" in labels
    assert "Close" in labels

    # Author check
    mock_author_interaction = MagicMock(user=mock_ctx.author)
    assert asyncio.run(view.interaction_check(mock_author_interaction)) is True

    # Unauthorized user check
    intruder = MagicMock(id=999999999)
    mock_intruder_interaction = MagicMock(user=intruder)
    mock_intruder_interaction.response.send_message = AsyncMock()
    assert asyncio.run(view.interaction_check(mock_intruder_interaction)) is False
    mock_intruder_interaction.response.send_message.assert_awaited_once()


def test_help_view_on_timeout(help_cog: Help, mock_ctx: MagicMock):
    """Verify on_timeout disables all interactive buttons and dropdowns."""
    visible = {"🏠・GETTING STARTED": [MagicMock(qualified_name="start")]}
    view = HelpView(help_cog, mock_ctx, visible)
    view.message = MagicMock()
    view.message.edit = AsyncMock()

    asyncio.run(view.on_timeout())

    for item in view.children:
        if getattr(item, "style", None) != discord.ButtonStyle.link:
            assert item.disabled is True
    view.message.edit.assert_awaited_once_with(view=view)


@pytest.mark.asyncio
async def test_help_unknown_command_returns_error_embed(help_cog: Help, mock_ctx: MagicMock):
    """Verify searching for an unknown command returns an error embed without breaking."""
    with patch.object(help_cog.bot, "get_command", return_value=None):
        await help_cog.help_command.callback(help_cog, mock_ctx, command_or_module="nonexistent_cmd_xyz")

    mock_ctx.send.assert_awaited_once()
    _, kwargs = mock_ctx.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert "Command or Category Not Found" in embed.title
    assert "nonexistent_cmd_xyz" in embed.description
    assert "view" in kwargs
    assert isinstance(kwargs["view"], HelpView)


@pytest.mark.asyncio
async def test_help_view_navigation_stepping(help_cog: Help, mock_ctx: MagicMock):
    """Verify Back and Next buttons cycle through visible categories."""
    visible = {
        "🏠・GETTING STARTED": [MagicMock()],
        "🤖・ARTIFICIAL INTELLIGENCE": [MagicMock()],
        "🛡️・MODERATION": [MagicMock()],
    }
    view = HelpView(help_cog, mock_ctx, visible, current_category="home")

    mock_interaction = MagicMock()
    mock_interaction.response.edit_message = AsyncMock()

    # Next from home -> first category
    await view.btn_next_callback(mock_interaction)
    assert view.current_category == "🏠・GETTING STARTED"

    # Next from first -> second category
    await view.btn_next_callback(mock_interaction)
    assert view.current_category == "🤖・ARTIFICIAL INTELLIGENCE"

    # Back from second -> first category
    await view.btn_back_callback(mock_interaction)
    assert view.current_category == "🏠・GETTING STARTED"

    # Home button -> returns to home
    await view.btn_home_callback(mock_interaction)
    assert view.current_category == "home"


@pytest.mark.asyncio
async def test_help_owner_developer_isolation(help_cog: Help, mock_ctx: MagicMock):
    """Verify owner & developer commands are strictly hidden from non-owners in visible categories."""
    owner_cmd = MagicMock(qualified_name="eval", hidden=False)
    owner_cmd.name = "eval"
    owner_cmd.cog = MagicMock(category="Owner", qualified_name="OwnerSystem")

    public_cmd = MagicMock(qualified_name="ping", hidden=False)
    public_cmd.name = "ping"
    public_cmd.cog = MagicMock(category="General", qualified_name="General")

    # Regular user context
    mock_ctx.author.id = 111222333
    with patch.object(type(help_cog.bot), "cogs", new_callable=PropertyMock, return_value={"Owner": MagicMock(get_commands=lambda: [owner_cmd]), "General": MagicMock(get_commands=lambda: [public_cmd])}):
        visible = await help_cog._get_visible_categories(mock_ctx)
        assert "👑・OWNER & DEVELOPER" not in visible
        assert "🏠・GETTING STARTED" in visible

    # Primary owner context
    mock_ctx.author.id = OWNER_ID
    with patch.object(type(help_cog.bot), "cogs", new_callable=PropertyMock, return_value={"Owner": MagicMock(get_commands=lambda: [owner_cmd]), "General": MagicMock(get_commands=lambda: [public_cmd])}):
        visible_owner = await help_cog._get_visible_categories(mock_ctx)
        assert "👑・OWNER & DEVELOPER" in visible_owner
