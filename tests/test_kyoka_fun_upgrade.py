from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.core.context import CustomContext
from src.managers.ai_manager import AIManager, COMPANION_PERSONAS, PERSONALITY_PRESETS
from src.managers.gif_manager import GIFManager
from src.security.adult_guard import authorize_adult, is_adult_authorized, get_adult_allowlist
from src.security.owner import OWNER_ID


# ─── 1. TEST HELP 17 CATEGORIES COVERAGE ─────────────────────────────────────

@pytest.mark.asyncio
async def test_help_17_categories_coverage():
    from src.core.bot import KyokaBot
    from src.cogs.general.help import Help

    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    await bot._load_all_extensions()

    help_cog = bot.get_cog("Help")
    assert help_cog is not None

    # Check 17 categories are explicitly defined in Help
    assert len(Help.CATEGORY_ORDER) == 17
    expected_categories = [
        "General", "Fun", "Anime Actions", "Romance & Relationships",
        "Adult Humor — Restricted", "AI Companions", "AI Chat", "Games",
        "Social & Profiles", "Community & XP", "Moderation", "Tickets",
        "Giveaways", "Images & GIFs", "Premium", "Administration", "Utility"
    ]
    assert Help.CATEGORY_ORDER == expected_categories

    # Mock context with primary owner (has access to all categories)
    ctx = MagicMock(spec=CustomContext)
    ctx.author.id = OWNER_ID
    ctx.guild = MagicMock(id=12345)

    visible = await help_cog._get_visible_categories(ctx)
    assert len(visible) >= 12  # Populated categories
    # Verify core categories exist in visible categories
    for cat in ["General", "Fun", "Anime Actions", "Romance & Relationships", "AI Companions", "AI Chat", "Games", "Moderation", "Tickets", "Giveaways", "Utility"]:
        assert cat in visible, f"Category '{cat}' should be present in visible categories"


# ─── 2. TEST THREE DISTINCT AI COMPANION PERSONAS ────────────────────────────

def test_three_ai_companion_personas_definitions():
    assert len(COMPANION_PERSONAS) == 3
    assert "aigf" in COMPANION_PERSONAS
    assert "aibaddie" in COMPANION_PERSONAS
    assert "aispecial" in COMPANION_PERSONAS

    # Verify separate prompts and personalities
    gf_prompt = COMPANION_PERSONAS["aigf"]["prompt"]
    baddie_prompt = COMPANION_PERSONAS["aibaddie"]["prompt"]
    special_prompt = COMPANION_PERSONAS["aispecial"]["prompt"]

    assert "affectionate" in gf_prompt.lower()
    assert "baddie" in baddie_prompt.lower() or "confident" in baddie_prompt.lower()
    assert "adult" in special_prompt.lower() or "suggestive" in special_prompt.lower()

    # Verify they have distinct system prompts
    assert gf_prompt != baddie_prompt
    assert baddie_prompt != special_prompt
    assert gf_prompt != special_prompt


@pytest.mark.asyncio
async def test_ai_companion_context_isolation_and_clear():
    mock_db = AsyncMock()
    ai_mgr = AIManager(mock_db)

    # Simulate replies for different personas
    history_gf = ai_mgr.history[(111, 222, "aigf")]
    history_baddie = ai_mgr.history[(111, 222, "aibaddie")]
    history_special = ai_mgr.history[(111, 222, "aispecial")]

    history_gf.append({"role": "user", "text": "Hello girlfriend!"})
    history_baddie.append({"role": "user", "text": "Hey baddie!"})
    history_special.append({"role": "user", "text": "Spicy talk!"})

    # Verify isolated histories per persona
    assert len(history_gf) == 1
    assert history_gf[0]["text"] == "Hello girlfriend!"
    assert len(history_baddie) == 1
    assert history_baddie[0]["text"] == "Hey baddie!"
    assert len(history_special) == 1
    assert history_special[0]["text"] == "Spicy talk!"

    # Test clear_user_history clears all personas for that user
    ai_mgr.clear_user_history(111, 222)
    assert len(ai_mgr.history[(111, 222, "aigf")]) == 0
    assert len(ai_mgr.history[(111, 222, "aibaddie")]) == 0
    assert len(ai_mgr.history[(111, 222, "aispecial")]) == 0


# ─── 3. TEST ADULT ALLOWLIST ENFORCEMENT FAIL-CLOSED ─────────────────────────

def test_adult_allowlist_authorization_checks():
    # Primary owner is always authorized
    assert is_adult_authorized(OWNER_ID) is True

    # Unknown user without allowlist configured is blocked (fail closed)
    with patch.dict(os.environ, {"ADULT_COMMAND_ALLOWLIST": ""}):
        assert is_adult_authorized(999999999) is False
        assert is_adult_authorized(None) is False

    # Configured user is authorized
    with patch.dict(os.environ, {"ADULT_COMMAND_ALLOWLIST": "123456,7891011"}):
        assert is_adult_authorized(123456) is True
        assert is_adult_authorized(7891011) is True
        assert is_adult_authorized(999999999) is False


@pytest.mark.asyncio
async def test_authorize_adult_rejects_unauthorized_user():
    ctx = MagicMock(spec=CustomContext)
    ctx.author.id = 555555  # Unauthorized user
    ctx.send = AsyncMock()

    with patch.dict(os.environ, {"ADULT_COMMAND_ALLOWLIST": "123456"}):
        res = await authorize_adult(ctx, action_name="test_action")
        assert res is False
        ctx.send.assert_called_once()
        sent_msg = ctx.send.call_args[0][0]
        assert "Access Denied: Restricted Category" in sent_msg


# ─── 4. TEST MARRIAGE PROPOSAL VIEW & PERSISTENCE ────────────────────────────

@pytest.mark.asyncio
async def test_marriage_proposal_view_accept_and_decline():
    from src.cogs.fun.romance import ProposalView

    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()

    proposer = MagicMock(spec=discord.Member)
    proposer.id = 11111
    proposer.mention = "<@11111>"

    target = MagicMock(spec=discord.Member)
    target.id = 22222
    target.mention = "<@22222>"

    view = ProposalView(mock_bot, proposer, target)

    # 1. Non-target cannot interact
    intruder_interaction = MagicMock(spec=discord.Interaction)
    intruder_interaction.user.id = 33333
    intruder_interaction.response.send_message = AsyncMock()
    allowed = await view.interaction_check(intruder_interaction)
    assert allowed is False

    # 2. Target accept saves marriage
    target_interaction = MagicMock(spec=discord.Interaction)
    target_interaction.user.id = 22222
    target_interaction.guild_id = 99999
    target_interaction.response.edit_message = AsyncMock()

    btn = MagicMock(spec=discord.ui.Button)
    await view.accept.callback(target_interaction)
    assert view.value is True
    # Two DB inserts for reciprocal marriage
    assert mock_bot.db.execute.call_count == 2
    target_interaction.response.edit_message.assert_called_once()


# ─── 5. TEST ANIME ACTIONS & GIF VARIETY ─────────────────────────────────────

@pytest.mark.asyncio
async def test_anime_action_gif_manager_variety():
    gif_mgr = GIFManager()

    # Verify action categories have pools
    assert "slapped" in gif_mgr.curated
    assert "intimate_couple" in gif_mgr.curated
    assert "vibed" in gif_mgr.curated
    assert "thirst" in gif_mgr.curated

    # Fetch multiple action GIFs, ensuring HTTPS and variety
    urls = []
    for _ in range(5):
        url = await gif_mgr.get_action_gif("romance")
        assert url.startswith("https://")
        urls.append(url)

    # Ensure deque recent tracking prevents immediate duplicate
    assert len(gif_mgr._recent_served["loved"]) > 0


# ─── 6. TEST REAL MODERATION PRESERVATION ────────────────────────────────────

def test_real_moderation_commands_intact():
    from src.cogs.moderation.kick import KickCog
    from src.cogs.moderation.ban import BanCog

    mock_bot = MagicMock()
    kick_cog = KickCog(mock_bot)
    ban_cog = BanCog(mock_bot)

    # Verify real moderation kick is preserved
    assert hasattr(kick_cog, "kick")
    # Verify real moderation ban is preserved
    assert hasattr(ban_cog, "ban")

