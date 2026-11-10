import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.cogs.ticket.ticket_system import (
    TicketSetupWizard,
    AddTopicModal,
    ManageTopicsView,
    TicketAIReplyView,
    TicketAISolvedPromptView,
    TicketSystem,
)

@pytest.mark.asyncio
async def test_ticket_setup_wizard_topics():
    cog_mock = MagicMock()
    bot_mock = MagicMock()
    cog_mock.bot = bot_mock
    bot_mock.custom_emojis = {}
    author_mock = MagicMock(spec=discord.Member)
    author_mock.id = 12345
    author_mock.display_name = "ServerAdmin"

    wizard = TicketSetupWizard(cog=cog_mock, author=author_mock)

    # Initial topics should be empty (clean slate) so admins can customize whatever they want
    assert len(wizard.custom_topics) == 0

    # Switch to slide 2 ("roles")
    wizard.current_slide_idx = 1
    wizard._build_components_for_slide()

    # Check that custom topic buttons exist
    custom_ids = [item.custom_id for item in wizard.children if hasattr(item, "custom_id")]
    assert "wiz_btn_topics" in custom_ids

    # Add a custom topic via Modal logic
    modal = AddTopicModal(wizard)
    modal.topic_name._value = "Blox Fruits Mirage Island"
    modal.topic_emoji._value = "🏝️"
    modal.topic_description._value = "Carry & assistance for Mirage"
    modal.topic_welcome._value = "Welcome to Mirage Island support!"

    interaction_mock = MagicMock(spec=discord.Interaction)
    interaction_mock.guild = MagicMock()
    interaction_mock.response = MagicMock()
    interaction_mock.response.edit_message = AsyncMock()

    with patch("src.cogs.ticket.ticket_system.edit_container_response", new=AsyncMock()):
        await modal.on_submit(interaction_mock)

    # Verify custom topic was added
    new_names = [t["name"] for t in wizard.custom_topics]
    assert "Blox Fruits Mirage Island" in new_names

    # Check dashboard container includes topics
    container = wizard.get_dashboard_container(interaction_mock.guild)
    assert container is not None
    container_text = "\n".join([item.get("content", "") for item in container.components if isinstance(item, dict)])
    assert "Blox Fruits Mirage Island" in container_text or "Ticket Topics" in container_text


@pytest.mark.asyncio
async def test_ticket_ai_reply_view_actions():
    cog_mock = MagicMock(spec=TicketSystem)
    cog_mock.execute_ticket_close = AsyncMock()
    cog_mock.summon_ticket_staff = AsyncMock()

    ticket_data = {
        "id": 99,
        "channel_id": 55555,
        "user_id": 11111,
        "ticket_number": 42,
        "category": "Bug Report",
    }

    view = TicketAIReplyView(cog=cog_mock, ticket_data=ticket_data)
    assert view.btn_solved.custom_id == "ticket_ai_solved_99"
    assert view.btn_staff.custom_id == "ticket_ai_staff_99"

    # Test staff escalation click
    interaction_mock = MagicMock(spec=discord.Interaction)
    interaction_mock.user = MagicMock(spec=discord.Member)
    interaction_mock.user.id = 11111
    interaction_mock.channel = MagicMock()
    interaction_mock.response = MagicMock()
    interaction_mock.response.edit_message = AsyncMock()

    await view.btn_staff.callback(interaction_mock)
    cog_mock.summon_ticket_staff.assert_awaited_once()


@pytest.mark.asyncio
async def test_ticket_solution_generation():
    bot_mock = MagicMock()
    bot_mock.ai_mgr = None
    bot_mock.add_view = MagicMock()
    ticket_cog = TicketSystem(bot_mock)

    guild_mock = MagicMock()
    guild_mock.name = "Kyoka Empire"
    user_mock = MagicMock()
    user_mock.display_name = "PlayerOne"

    # Test bug solution
    sol_bug = await ticket_cog.generate_ticket_solution("I have a bug with loading", "Bug Report", guild_mock, user_mock)
    assert "troubleshooting" in sol_bug.lower() or "restart" in sol_bug.lower()

    # Test billing solution
    sol_buy = await ticket_cog.generate_ticket_solution("I want to purchase coins", "Billing / Orders", guild_mock, user_mock)
    assert "purchases" in sol_buy.lower() or "payment" in sol_buy.lower()

    # Test trials solution
    sol_trial = await ticket_cog.generate_ticket_solution("Help with race v4 trials", "Trials", guild_mock, user_mock)
    assert "trials" in sol_trial.lower() or "moon" in sol_trial.lower()


@pytest.mark.asyncio
async def test_ticket_ai_solved_prompt_view():
    cog_mock = MagicMock(spec=TicketSystem)
    cog_mock.execute_ticket_close = AsyncMock()
    cog_mock.summon_ticket_staff = AsyncMock()

    ticket_data = {
        "id": 105,
        "channel_id": 99999,
        "user_id": 22222,
        "ticket_number": 55,
        "category": "General Support",
    }

    view = TicketAISolvedPromptView(cog=cog_mock, ticket_data=ticket_data)
    assert view.btn_close.custom_id == "ticket_ai_solved_close_105"
    assert view.btn_more.custom_id == "ticket_ai_solved_more_105"
    assert view.btn_staff.custom_id == "ticket_ai_solved_staff_105"

    interaction_mock = MagicMock(spec=discord.Interaction)
    interaction_mock.user = MagicMock(spec=discord.Member)
    interaction_mock.user.id = 22222
    interaction_mock.channel = MagicMock()
    interaction_mock.response = MagicMock()
    interaction_mock.response.edit_message = AsyncMock()

    # Test "I Have Another Question" button
    with patch("src.cogs.ticket.ticket_system.send_container_response", new=AsyncMock()) as mock_send:
        await view.btn_more.callback(interaction_mock)
        mock_send.assert_awaited_once()

    # Test "Need Staff Help" button
    await view.btn_staff.callback(interaction_mock)
    cog_mock.summon_ticket_staff.assert_awaited_once()
