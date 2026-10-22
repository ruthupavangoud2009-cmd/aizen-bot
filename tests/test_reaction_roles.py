import pytest
from unittest.mock import AsyncMock
from src.cogs.utility.reaction_roles import normalize_emoji, format_emoji_display
from src.managers.reaction_role_manager import ReactionRoleManager


def test_normalize_emoji():
    assert normalize_emoji("🎮") == "🎮"
    assert normalize_emoji("<:aizen:1234567890>") == "aizen:1234567890"
    assert normalize_emoji("<a:pepe_dance:9876543210>") == "pepe_dance:9876543210"
    assert format_emoji_display("🎮") == "🎮"
    assert format_emoji_display("aizen:1234567890") == "<:aizen:1234567890>"


@pytest.mark.asyncio
async def test_reaction_role_manager_lifecycle():
    mock_db = AsyncMock()
    mgr = ReactionRoleManager(mock_db)

    # 1. Add binding
    binding = await mgr.add_binding(
        guild_id=111,
        channel_id=222,
        message_id=333,
        emoji="🎮",
        role_id=444,
        mode="normal",
    )
    assert binding["emoji"] == "🎮"
    assert binding["role_id"] == 444
    assert binding["mode"] == "normal"

    # 2. Get binding
    fetched = mgr.get_binding(333, "🎮")
    assert fetched is not None
    assert fetched["role_id"] == 444

    # 3. Message bindings
    msg_bindings = mgr.get_message_bindings(333)
    assert len(msg_bindings) == 1

    # 4. Remove binding
    removed = await mgr.remove_binding(333, "🎮")
    assert removed is True
    assert mgr.get_binding(333, "🎮") is None
