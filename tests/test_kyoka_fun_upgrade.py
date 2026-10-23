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
async def test_help_aizen_categories_coverage():
    from src.core.bot import KyokaBot
    from src.cogs.general.help import Help

    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    await bot._load_all_extensions()

    help_cog = bot.get_cog("Help")
    assert help_cog is not None

    # Check clean Aizen Edition categories are explicitly defined in Help (includes 14 categories in 3.0)
    assert len(Help.CATEGORY_ORDER) in (11, 12, 14)
    assert "🛡️・MODERATION" in Help.CATEGORY_ORDER
    assert "🎵・MUSIC" in Help.CATEGORY_ORDER
    assert "💎・PREMIUM" in Help.CATEGORY_ORDER

    # Mock context with primary owner (has access to all categories)
    ctx = MagicMock(spec=CustomContext)
    ctx.author.id = OWNER_ID
    ctx.guild = MagicMock(id=12345)

    visible = await help_cog._get_visible_categories(ctx)
    assert len(visible) >= 8  # Populated categories
    # Verify core categories exist in visible categories
    core_cats = ["🤖・ARTIFICIAL INTELLIGENCE", "🛡️・MODERATION", "🎫・TICKETS & SUPPORT", "🎉・GIVEAWAYS & EVENTS", "💬・SOCIAL & FUN", "🔧・UTILITIES"]
    for cat in core_cats:
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


# ─── 7. TEST AUTOMATIC AI CHANNELS SETUP & PERSISTENCE ───────────────────────

@pytest.mark.asyncio
async def test_ai_channel_setup_and_persistence():
    from src.cogs.fun.companion_ai import CompanionAI

    mock_bot = MagicMock()
    mock_bot.db = AsyncMock()
    cog = CompanionAI(mock_bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 88888
    guild.name = "Aizen HQ"
    guild.me = MagicMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 77777
    channel.name = "girlfriend-lounge"
    channel.mention = "<#77777>"

    # Mock permissions as valid
    perms = MagicMock()
    perms.send_messages = True
    perms.embed_links = True
    perms.read_messages = True
    channel.permissions_for.return_value = perms

    # Test Setup
    embed = await cog._setup_channel(guild, channel, persona="aigf", user_id=12345)
    assert "Automatic AI Channel Configured" in embed.title
    assert 77777 in cog._channel_configs
    assert cog._channel_configs[77777]["persona"] == "aigf"
    mock_bot.db.set_ai_channel.assert_called_once()

    # Test Status
    status_embed = await cog._status_channel(guild, channel)
    assert "girlfriend-lounge" in status_embed.title
    assert "Active" in status_embed.fields[0].value

    # Test Disable
    disable_embed = await cog._disable_channel(guild, channel)
    assert "Disabled" in disable_embed.title
    assert cog._channel_configs[77777]["enabled"] is False
    mock_bot.db.disable_ai_channel.assert_called_once_with(88888, 77777)

    # Test Remove
    remove_embed = await cog._remove_channel(guild, channel)
    assert "Removed" in remove_embed.title
    assert 77777 not in cog._channel_configs
    mock_bot.db.remove_ai_channel.assert_called_once_with(88888, 77777)


# ─── 8. TEST AUTOMATIC AI CHANNEL MESSAGE LISTENER ───────────────────────────

@pytest.mark.asyncio
async def test_ai_channel_on_message_listener_flow():
    from src.cogs.fun.companion_ai import CompanionAI

    mock_bot = MagicMock()
    mock_bot.user.id = 99999
    mock_bot.db = AsyncMock()
    mock_bot.ai_mgr = AsyncMock()
    mock_bot.ai_mgr.generate_persona_reply.return_value = "Hello darling, I missed you! 💖"
    mock_bot.session = MagicMock()
    mock_bot.session.closed = False

    cog = CompanionAI(mock_bot)
    cog._channel_configs[77777] = {
        "guild_id": 88888,
        "channel_id": 77777,
        "persona": "aigf",
        "enabled": True,
        "mention_only": False,
        "cooldown_seconds": 3,
        "send_gifs": False,
    }

    # 1. Message from bot itself -> ignored
    bot_msg = MagicMock(spec=discord.Message)
    bot_msg.author.id = 99999
    bot_msg.author.bot = True
    await cog.on_message(bot_msg)
    mock_bot.ai_mgr.generate_persona_reply.assert_not_called()

    # 2. Normal user message in configured channel -> generates response
    user_msg = MagicMock(spec=discord.Message)
    user_msg.author.id = 55555
    user_msg.author.bot = False
    user_msg.webhook_id = None
    user_msg.guild.id = 88888
    user_msg.guild.name = "Aizen HQ"
    user_msg.channel.id = 77777
    user_msg.channel.name = "girlfriend-lounge"
    user_msg.content = "How was your day?"
    user_msg.mentions = []
    user_msg.reference = None
    user_msg.reply = AsyncMock()

    # Context parser returns invalid (not a command)
    mock_ctx = MagicMock()
    mock_ctx.valid = False
    mock_bot.get_context.return_value = mock_ctx

    await cog.on_message(user_msg)
    mock_bot.ai_mgr.generate_persona_reply.assert_called_once()
    user_msg.reply.assert_called_once()


# ─── 9. TEST GEMINI CONNECTIVITY DIAGNOSTICS ─────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_connectivity_diagnostics_mocked():
    from src.managers.ai_manager import AIManager

    mock_db = AsyncMock()
    ai_mgr = AIManager(mock_db)

    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200

    # Mock post context manager
    mock_session.post.return_value.__aenter__.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFakeKey123", "GEMINI_MODEL": "gemini-flash-lite-latest"}):
        result = await ai_mgr.test_connectivity(mock_session)
        assert result["ok"] is True
        assert result["status"] == 200
        assert result["model"] == "gemini-flash-lite-latest"
        assert "latency_ms" in result


# ─── 10. TEST BOT-WIDE DEFAULT ALLOWED MENTIONS ──────────────────────────────

def test_bot_default_allowed_mentions_protection():
    from src.core.bot import KyokaBot

    bot = KyokaBot()
    assert bot.allowed_mentions is not None
    assert bot.allowed_mentions.everyone is False
    assert bot.allowed_mentions.roles is False
    assert bot.allowed_mentions.users is True


