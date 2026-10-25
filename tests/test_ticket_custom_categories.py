import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.managers.ticket_manager import TicketManager

@pytest.mark.asyncio
async def test_ticket_custom_categories():
    # Mock bot and database
    bot_mock = MagicMock()
    db_mock = MagicMock()
    bot_mock.db = db_mock

    # Store in-memory records
    stored_categories = []

    async def mock_execute(query, *args):
        nonlocal stored_categories
        q = query.strip().upper()
        if "CREATE TABLE" in q:
            return
        if "INSERT OR REPLACE INTO TICKET_CATEGORIES" in q or "INSERT INTO TICKET_CATEGORIES" in q:
            guild_id, panel_name, name, desc, emoji, img, c_chan, s_role, w_msg, order_idx = args
            # check if exists
            for idx, c in enumerate(stored_categories):
                if c["guild_id"] == guild_id and c["name"].lower() == name.lower():
                    stored_categories[idx] = {
                        "guild_id": guild_id,
                        "panel_name": panel_name,
                        "name": name,
                        "description": desc,
                        "emoji": emoji,
                        "image_url": img,
                        "category_channel_id": c_chan,
                        "staff_role_id": s_role,
                        "welcome_message": w_msg,
                        "display_order": order_idx,
                        "is_active": 1,
                    }
                    return
            stored_categories.append({
                "guild_id": guild_id,
                "panel_name": panel_name,
                "name": name,
                "description": desc,
                "emoji": emoji,
                "image_url": img,
                "category_channel_id": c_chan,
                "staff_role_id": s_role,
                "welcome_message": w_msg,
                "display_order": order_idx,
                "is_active": 1,
            })
            return
        if "DELETE FROM TICKET_CATEGORIES" in q:
            guild_id, name = args
            stored_categories = [c for c in stored_categories if not (c["guild_id"] == guild_id and c["name"].lower() == name.lower())]
            return

    async def mock_fetch_all(query, *args):
        nonlocal stored_categories
        if "FROM TICKET_CATEGORIES" in query.upper():
            guild_id = args[0]
            return [c for c in stored_categories if c["guild_id"] == guild_id]
        return []

    async def mock_fetch_one(query, *args):
        res = await mock_fetch_all(query, *args)
        return res[0] if res else None

    db_mock.execute = AsyncMock(side_effect=mock_execute)
    db_mock.fetch_all = AsyncMock(side_effect=mock_fetch_all)
    db_mock.fetch_one = AsyncMock(side_effect=mock_fetch_one)

    mgr = TicketManager(bot_mock)

    # 1. Without any custom categories in DB, list_categories returns DEFAULT_TICKET_CATEGORIES
    cats = await mgr.list_categories(guild_id=123)
    assert len(cats) >= 5
    cat_names = [c["name"] for c in cats]
    assert "Support" in cat_names
    assert "Trials" in cat_names
    assert "Raids" in cat_names
    assert "Bosses" in cat_names

    # 2. Add custom Blox Fruits category
    new_cat = await mgr.add_category(
        guild_id=123,
        name="Mirage Island",
        description="Assistance with finding Mirage Island and gear",
        emoji="🏝️",
        welcome_message="Mirage Island ticket opened. Staff will assist shortly."
    )
    assert new_cat["name"] == "Mirage Island"
    assert new_cat["emoji"] == "🏝️"

    # Verify category is now listed
    cats_after = await mgr.list_categories(guild_id=123)
    after_names = [c["name"] for c in cats_after]
    assert "Mirage Island" in after_names

    # 3. Edit category
    edited = await mgr.edit_category(
        guild_id=123,
        name="Mirage Island",
        description="Updated Mirage Island hunt and gear services"
    )
    assert edited["description"] == "Updated Mirage Island hunt and gear services"

    # 4. Delete category
    deleted = await mgr.delete_category(guild_id=123, name="Mirage Island")
    assert deleted is True

    # Confirm removed
    cats_final = await mgr.list_categories(guild_id=123)
    final_names = [c["name"] for c in cats_final]
    assert "Mirage Island" not in final_names
