import pytest
from unittest.mock import AsyncMock, MagicMock
import discord

from src.managers.ticket_manager import TicketManager
from src.cogs.ticket.ticket_system import TicketSetupWizard, ManageTopicsView, AddTopicModal
from src.cogs.fun.games import Games, GamesHubView
from src.cogs.games.multiplayer import MultiplayerGames


@pytest.mark.asyncio
async def test_ticket_categories_default_to_nothing():
    """Verify that ticket categories default to empty [] so server owners have a clean slate to customize."""
    db_mock = MagicMock()
    db_mock.fetch_all = AsyncMock(return_value=[])
    mgr = TicketManager(db_mock)

    cats = await mgr.list_categories(guild_id=999, panel_name="support")
    assert cats == [], "Default categories must be empty so users can customize whatever they want"


@pytest.mark.asyncio
async def test_wizard_starts_with_zero_default_topics():
    """Verify that TicketSetupWizard starts with 0 topics (no hardcoded defaults)."""
    cog_mock = MagicMock()
    bot_mock = MagicMock()
    cog_mock.bot = bot_mock
    bot_mock.custom_emojis = {}
    author = MagicMock(spec=discord.Member)
    author.id = 12345
    author.display_name = "ServerAdmin"

    wizard = TicketSetupWizard(cog=cog_mock, author=author)
    assert wizard.custom_topics == [], "Wizard must start with 0 custom topics by default"

    # Verify Clear All Topics button in ManageTopicsView
    manage_view = ManageTopicsView(wizard)
    custom_ids = [item.custom_id for item in manage_view.children if hasattr(item, "custom_id")]
    assert "manage_topic_btn_clear" in custom_ids
    assert "manage_topic_btn_add" in custom_ids

    # Adding a custom topic
    wizard.custom_topics.append({
        "name": "Custom VIP Support",
        "emoji": "💎",
        "description": "Exclusive high-tier member assistance",
    })
    assert len(wizard.custom_topics) == 1

    # Clearing all topics
    interaction_mock = MagicMock(spec=discord.Interaction)
    interaction_mock.data = {}
    interaction_mock.response.edit_message = AsyncMock()
    await manage_view._on_clear_clicked(interaction_mock)
    assert wizard.custom_topics == [], "Clear All Topics must reset topics to an empty clean slate"


@pytest.mark.asyncio
async def test_games_cog_has_all_games_and_hub():
    """Verify that Games cog contains games command, reactionrace, hideandseek, twotruths, tod, bloxfruits, etc."""
    bot = MagicMock()
    cog = Games(bot)

    # Check key commands exist on the cog
    commands_dict = {cmd.name: cmd for cmd in cog.get_commands()}
    assert "games" in commands_dict
    assert "reactionrace" in commands_dict
    assert "hideandseek" in commands_dict
    assert "twotruths" in commands_dict
    assert "tod" in commands_dict
    assert "bloxfruits" in commands_dict
    assert "wordguess" in commands_dict
    assert "poll" in commands_dict
    assert "legit" in commands_dict
    assert "dailychallenge" in commands_dict

    # Check GamesHubView attaches GamesDropdown with all categories
    view = GamesHubView("?")
    assert len(view.children) == 1
    dropdown = view.children[0]
    option_values = [opt.value for opt in dropdown.options]
    assert "overview" in option_values
    assert "casino" in option_values
    assert "multiplayer" in option_values
    assert "puzzles" in option_values
    assert "number" in option_values
    assert "social" in option_values


@pytest.mark.asyncio
async def test_rps_direct_choice_and_solo():
    """Verify rps supports direct choice (e.g. ?rps rock) and interactive buttons."""
    bot = MagicMock()
    bot.db = MagicMock()
    multi = MultiplayerGames(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=500)
    ctx.author = MagicMock(id=100)
    ctx.author.bot = False
    ctx.send = AsyncMock()

    # Direct choice: ?rps rock
    await multi.rps.callback(multi, ctx, target_or_choice="rock")
    ctx.send.assert_called_once()
    sent_text = ctx.send.call_args[0][0]
    assert "You chose **rock**" in sent_text

    # Interactive choice: ?rps
    ctx.send.reset_mock()
    await multi.rps.callback(multi, ctx, target_or_choice=None)
    ctx.send.assert_called_once()
    call_kwargs = ctx.send.call_args[1]
    assert "view" in call_kwargs
    button_labels = [btn.label for btn in call_kwargs["view"].children]
    assert "Rock" in button_labels
    assert "Paper" in button_labels
    assert "Scissors" in button_labels
