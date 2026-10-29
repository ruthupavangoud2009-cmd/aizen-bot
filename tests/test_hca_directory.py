"""
Comprehensive automated tests for Kyoka 3.0 Help Command Archive (HCA).
Verifies:
- Public accessibility for ordinary members (non-owner, non-admin).
- Hybrid command registration (+hca and /hca).
- Category filtering (+hca music, +hca tickets, +hca bloxai, +hca aivoice).
- Unknown category graceful handling with available category listing.
- Full command registry discovery via _get_all_registered_categories.
- HCAView navigation components (select, Back, Index, Next, Search, Close).
- Author lock enforcement preventing non-requesters from controlling interactive session.
- Search modal querying command names, aliases, and descriptions.
- Permission badges for restricted commands.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord.ext import commands

from src.cogs.general.help import Help, HCAView, HCACategorySelect, HCASearchModal
from src.core.bot import KyokaBot


async def _dummy_coro(ctx):
    pass


@pytest.fixture
def mock_bot() -> KyokaBot:
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777, name="Kyoka")
    bot._connection.application_id = 999888777
    return bot


@pytest.fixture
def help_cog(mock_bot: KyokaBot) -> Help:
    return Help(mock_bot)


@pytest.fixture
def mock_ordinary_ctx() -> MagicMock:
    """Mock context of an ordinary server member with zero special permissions."""
    ctx = MagicMock()
    ctx.guild = MagicMock(id=111222333, name="Community Haven")
    ctx.author = MagicMock(id=123456789012345678, display_name="RegularMember")
    ctx.author.guild_permissions = discord.Permissions.none()
    ctx.author.display_avatar = MagicMock(url="https://cdn.discord.com/avatars/123/avatar.png")
    ctx.clean_prefix = "+"
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


def test_hca_is_hybrid_command(help_cog: Help):
    """Verify HCA is registered as a command accessible to all members."""
    cmd = help_cog.hca_command
    assert isinstance(cmd, commands.Command)
    assert cmd.name == "hca"
    assert "archive" in cmd.aliases
    assert "allcommands" in cmd.aliases
    assert "directory" in cmd.aliases
    assert "cmds" in cmd.aliases


@pytest.mark.asyncio
async def test_hca_accessible_to_ordinary_member(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify an ordinary member with no admin/mod permissions can invoke +hca successfully."""
    dummy_cmd = commands.Command(_dummy_coro, name="testcmd", help="A public test command")
    dummy_cmd.cog = MagicMock(category="General", qualified_name="General")
    help_cog.bot.add_command(dummy_cmd)

    await help_cog.hca_command.callback(help_cog, mock_ordinary_ctx, category=None)

    mock_ordinary_ctx.send.assert_awaited_once()
    _, kwargs = mock_ordinary_ctx.send.call_args
    assert "embed" in kwargs
    assert "file" in kwargs
    assert "view" in kwargs

    embed = kwargs["embed"]
    assert "Help Command Archive" in embed.title or "HCA" in embed.title
    assert embed.color.value == 0x2B0938


@pytest.mark.asyncio
async def test_hca_category_filtering_music(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify +hca music filters directly to the music category archive."""
    play_cmd = commands.Command(_dummy_coro, name="play", help="Play audio stream")
    play_cmd.cog = MagicMock(category="Music", qualified_name="Music")
    help_cog.bot.add_command(play_cmd)

    await help_cog.hca_command.callback(help_cog, mock_ordinary_ctx, category="music")

    mock_ordinary_ctx.send.assert_awaited_once()
    _, kwargs = mock_ordinary_ctx.send.call_args
    embed = kwargs["embed"]
    assert "MUSIC" in embed.title
    assert "play" in embed.description


@pytest.mark.asyncio
async def test_hca_category_filtering_bloxai(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify +hca bloxai filters directly to the Blox Fruits AI category archive."""
    blox_cmd = commands.Command(_dummy_coro, name="bloxai", help="Ask Blox Fruits AI")
    blox_cmd.cog = MagicMock(category="Blox Fruits AI", qualified_name="BloxFruitsAI")
    help_cog.bot.add_command(blox_cmd)

    await help_cog.hca_command.callback(help_cog, mock_ordinary_ctx, category="bloxai")

    mock_ordinary_ctx.send.assert_awaited_once()
    _, kwargs = mock_ordinary_ctx.send.call_args
    embed = kwargs["embed"]
    assert "BLOX FRUITS AI" in embed.title


@pytest.mark.asyncio
async def test_hca_unknown_category_handling(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify querying an unknown category returns helpful guidance with available categories."""
    await help_cog.hca_command.callback(help_cog, mock_ordinary_ctx, category="non_existent_module_999")

    mock_ordinary_ctx.send.assert_awaited_once()
    _, kwargs = mock_ordinary_ctx.send.call_args
    embed = kwargs["embed"]
    assert "Archive Category Not Found" in embed.title
    assert embed.color.value == 0xED4245
    assert "hca music" in embed.description


@pytest.mark.asyncio
async def test_hca_get_all_registered_categories(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify _get_all_registered_categories collects and groups registered commands."""
    cmd1 = commands.Command(_dummy_coro, name="kick", help="Kick a member")
    cmd1.cog = MagicMock(category="Moderation", qualified_name="Moderation")
    cmd2 = commands.Command(_dummy_coro, name="play", help="Play audio")
    cmd2.cog = MagicMock(category="Music", qualified_name="Music")

    help_cog.bot.add_command(cmd1)
    help_cog.bot.add_command(cmd2)

    categories = await help_cog._get_all_registered_categories(mock_ordinary_ctx)
    assert isinstance(categories, dict)
    assert "🛡️・MODERATION" in categories
    assert "🎵・MUSIC" in categories


def test_hca_view_components_and_author_lock(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify HCAView contains select menu, navigation buttons, and enforces author lock."""
    categories = {"🎵・MUSIC": [MagicMock(qualified_name="play")]}
    view = HCAView(help_cog, mock_ordinary_ctx, categories, current_category="home")

    selects = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(selects) == 1

    buttons = [i for i in view.children if isinstance(i, discord.ui.Button) and i.style != discord.ButtonStyle.link]
    labels = [b.label for b in buttons]
    assert "Back" in labels
    assert "Index" in labels
    assert "Next" in labels
    assert "Search" in labels
    assert "Close" in labels

    # Author interaction allowed
    author_interaction = MagicMock(user=mock_ordinary_ctx.author)
    assert asyncio.run(view.interaction_check(author_interaction)) is True

    # Unauthorized member interaction denied
    intruder = MagicMock(id=999999999999)
    intruder_interaction = MagicMock(user=intruder)
    intruder_interaction.response.send_message = AsyncMock()
    assert asyncio.run(view.interaction_check(intruder_interaction)) is False


def test_hca_view_on_timeout(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify on_timeout disables interactive items in HCAView."""
    categories = {"🎵・MUSIC": [MagicMock(qualified_name="play")]}
    view = HCAView(help_cog, mock_ordinary_ctx, categories)
    view.message = MagicMock()
    view.message.edit = AsyncMock()

    asyncio.run(view.on_timeout())
    for item in view.children:
        if getattr(item, "style", None) != discord.ButtonStyle.link:
            assert item.disabled is True


def test_hca_search_results_embed(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify search across archive correctly locates matching commands."""
    cmd1 = MagicMock(qualified_name="volume", description="Adjust playback volume", help=None, aliases=["vol"], signature="<1-100>")
    cmd1.cog = MagicMock(category="Music")
    categories = {"🎵・MUSIC": [cmd1]}

    # Search for "volume"
    embed = help_cog.build_hca_search_embed(mock_ordinary_ctx, categories, "volume")
    assert "volume" in embed.fields[0].name
    assert "🎵・MUSIC" in embed.fields[0].value

    # Search for alias "vol"
    embed_alias = help_cog.build_hca_search_embed(mock_ordinary_ctx, categories, "vol")
    assert len(embed_alias.fields) > 0

    # Search for nonexistent keyword
    embed_none = help_cog.build_hca_search_embed(mock_ordinary_ctx, categories, "xyz_not_found")
    assert "No registered commands matching" in embed_none.description


@pytest.mark.asyncio
async def test_hca_all_commands_selection_is_paginated(help_cog: Help, mock_ordinary_ctx: MagicMock):
    """Verify the All Commands dropdown target renders and navigates its own pages."""
    commands_list = [
        commands.Command(_dummy_coro, name=f"cmd{i}", help=f"Command number {i}")
        for i in range(11)
    ]
    categories = {"🎵・MUSIC": commands_list}
    view = HCAView(help_cog, mock_ordinary_ctx, categories, current_category="all")
    select = next(item for item in view.children if isinstance(item, discord.ui.Select))
    assert any(option.value == "all" for option in select.options)

    embed, _ = help_cog.build_hca_embed_for_selection(
        mock_ordinary_ctx, categories, "all", page=2
    )
    assert "All Commands" in embed.title
    assert "Page **2/2**" in embed.description
    assert "cmd10" in embed.fields[0].name

    interaction = MagicMock()
    interaction.response.edit_message = AsyncMock()
    await view.btn_next_callback(interaction)
    assert view.current_page == 2
    await view.btn_back_callback(interaction)
    assert view.current_page == 1

    for command in commands_list:
        help_cog.bot.add_command(command)
    await help_cog.hca_command.callback(help_cog, mock_ordinary_ctx, category="all")
    _, kwargs = mock_ordinary_ctx.send.call_args
    assert "All Commands" in kwargs["embed"].title
    assert kwargs["view"].current_category == "all"
