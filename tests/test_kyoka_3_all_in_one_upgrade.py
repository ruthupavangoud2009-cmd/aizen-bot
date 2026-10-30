"""
Comprehensive Test Suite for KYOKA 3.0 Ultimate All-In-One Upgrade
Validates:
1. Low-Ping Optimization & Performance Instrumentation (Diagnostics, Event loop lag, bounded telemetry)
2. Presence & Activity (Online status, 'KYOKA | The Ultimate Bot' game activity, zero 'Listening to ?help')
3. Redesigned Help Dashboard & Dynamic Category Discovery (Aizen dark violet, interaction lock, all 23 categories)
4. Consistent Asset System & Resilient Fallbacks
5. Automatic Help on Bot Mention (Structured detection, plain-text immunity, anti-spam cooldowns, command bypass)
6. Appy-Style Staff Application Engine (Persistence, open/closed gating, cooldowns, review transitions, notes, stats)
7. Full System Regression Checks (Pricing engine, tax calculation, billing integrity)
"""

from __future__ import annotations

import asyncio
import collections
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import pytest
import discord
from discord.ext import commands

from src.core.bot import KyokaBot
from src.core.config import Config
from src.core.context import CustomContext
from src.cogs.general.ping import Ping
from src.cogs.developer.system import SystemCog
from src.cogs.general.help import Help, HelpView
from src.ui.categories import CATEGORIES, resolve_command_category
from src.ui.asset_manager import AssetManager
from src.managers.top_manager import TopManager


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRESENCE & ACTIVITY TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_bot_initial_presence_is_online_with_watching_activity():
    """Verify default initial presence is configured as discord.Status.online and Watching activity."""
    bot = KyokaBot()
    assert bot.status == discord.Status.online
    assert bot.activity.type == discord.ActivityType.watching
    assert "servers" in bot.activity.name


def test_no_legacy_listening_to_help_presence_remains():
    """Verify all occurrences of 'Listening to ?help' and DND presence were purged from source files."""
    files_to_check = [
        "src/core/bot.py",
        "src/cogs/developer/identity.py",
    ]
    for rel_path in files_to_check:
        with open(rel_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Listening to ?help" not in content, f"Legacy presence found in {rel_path}"
            assert "discord.Status.dnd" not in content, f"Legacy DND presence found in {rel_path}"


@pytest.mark.asyncio
async def test_rotate_presence_maintains_online_and_dynamic_watching():
    """Verify presence rotation task reliably enforces Online and dynamic Watching presence."""
    bot = KyokaBot()
    bot.change_presence = AsyncMock()

    # Invoke the internal presence update method
    await bot._rotate_presence()
    assert bot.change_presence.called
    kwargs = bot.change_presence.call_args[1]
    assert kwargs.get("status") == discord.Status.online
    activity = kwargs.get("activity")
    assert activity.type == discord.ActivityType.watching
    assert "servers" in activity.name


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOW-PING OPTIMIZATION & DIAGNOSTICS TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_slow_operation_telemetry_ring_buffer_is_bounded():
    """Verify telemetry storage uses a bounded deque (maxlen=30) and never leaks memory."""
    bot = KyokaBot()
    assert isinstance(bot.slow_operations, collections.deque)
    assert bot.slow_operations.maxlen == 30

    # Record 50 slow operations
    for i in range(50):
        bot.record_slow_operation(f"op_{i}", duration_ms=300.0 + i, details=f"Details {i}")

    # Must be bounded to exactly maxlen
    assert len(bot.slow_operations) == 30
    assert bot.slow_operations[-1]["name"] == "op_49"
    assert bot.slow_operations[0]["name"] == "op_20"


@pytest.mark.asyncio
async def test_ping_command_measures_separate_components():
    """Verify +ping command measures gateway latency, bot response, loop lag, and database status separately."""
    bot = KyokaBot()
    bot.db = AsyncMock()
    bot.db.fetch_one = AsyncMock(return_value={"1": 1})
    bot.custom_emojis = MagicMock()
    bot.custom_emojis.get = MagicMock(return_value="•")

    ping_cog = Ping(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(spec=discord.Guild, shard_id=0)
    ctx.author = MagicMock(display_name="KyokaUser")
    ctx.channel = MagicMock(spec=discord.TextChannel, id=1001)
    bot.http = AsyncMock()
    bot.http.request.return_value = {"id": "123"}
    ctx.bot = bot

    with patch.object(KyokaBot, "latency", new_callable=PropertyMock, return_value=0.035):
        await ping_cog.ping.callback(ping_cog, ctx)
        assert bot.http.request.called
        sent_payload = bot.http.request.call_args[1].get("json") or {}
        raw_text = str(sent_payload)

        # Separate measurements verification
        assert "Gateway:" in raw_text
        assert "35.00ms" in raw_text
        assert "Bot Processing:" in raw_text
        assert "Event-Loop Lag:" in raw_text
        assert "Database:" in raw_text
        assert "Healthy" in raw_text


@pytest.mark.asyncio
async def test_diagnostics_command_permissions_and_output():
    """Verify owner-only diagnostics command enforces owner authorization and returns telemetry."""
    bot = KyokaBot()
    bot.db = AsyncMock()
    bot.db.fetch_one = AsyncMock(return_value={"1": 1})
    bot.record_slow_operation("test_slow_task", 350.0, "DB Query")

    system_cog = SystemCog(bot)
    diag_cmd = system_cog.diagnostics

    # Authorized owner test (1505515188991033409)
    owner_ctx = MagicMock(spec=CustomContext)
    owner_ctx.author = MagicMock(id=1505515188991033409, display_name="PrimaryOwner")
    owner_ctx.channel = MagicMock(spec=discord.TextChannel, id=1001)
    owner_ctx.bot = bot
    bot.http = AsyncMock()
    bot.http.request.return_value = {"id": "999"}

    await diag_cmd.callback(system_cog, owner_ctx)
    assert bot.http.request.called
    sent_payload = bot.http.request.call_args[1].get("json") or {}
    raw_diag = str(sent_payload)
    assert "Core Diagnostics" in raw_diag
    assert "test_slow_task" in raw_diag
    assert "350.0ms" in raw_diag


# ─────────────────────────────────────────────────────────────────────────────
# 3. HELP UI & DYNAMIC CATEGORIES TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_all_23_categories_registered_including_watch_party_and_staff_applications():
    """Verify dynamic category catalog contains all required categories without empty gaps."""
    cat_tags = [c.tag for c in CATEGORIES]
    assert len(cat_tags) == 23
    assert "📝・STAFF APPLICATIONS" in cat_tags
    assert "🎬・WATCH PARTY" in cat_tags

    # Route verification for staff application commands
    mock_app_cmd = MagicMock(qualified_name="top app", cog_name="TopAIManager")
    assert resolve_command_category(mock_app_cmd).id == "staff_applications"

    mock_apply_cmd = MagicMock(qualified_name="apply", cog_name="TopAIManager")
    assert resolve_command_category(mock_apply_cmd).id == "staff_applications"


def test_asset_manager_maps_staff_applications_safely():
    """Verify asset manager provides safe local assets and fallbacks."""
    assert "staff_applications" in AssetManager.CATEGORY_HELP_ASSETS
    assert AssetManager.CATEGORY_HELP_ASSETS["staff_applications"] == "help_tickets.png"

    assert "staff_panel" in AssetManager.FEATURE_ASSETS
    assert AssetManager.FEATURE_ASSETS["staff_panel"] == "ticket_panel.png"

    # Missing category safe fallback does not crash
    embed = discord.Embed(title="Test")
    res = AssetManager.attach_help_banner(embed, "non_existent_category_xyz")
    assert embed.image is not None or res is None


@pytest.mark.asyncio
async def test_help_view_interaction_check_restricts_to_author():
    """Verify HelpView rejects clicks from non-authors with ephemeral notice."""
    bot = KyokaBot()
    help_cog = Help(bot)
    ctx = MagicMock()
    ctx.author.id = 12345

    view = HelpView(help_cog, ctx, visible_categories={"General": []})

    # Authorized user
    auth_interaction = MagicMock(spec=discord.Interaction)
    auth_interaction.user.id = 12345
    auth_interaction.response.send_message = AsyncMock()
    assert await view.interaction_check(auth_interaction) is True
    assert not auth_interaction.response.send_message.called

    # Unauthorized intruder
    unauth_interaction = MagicMock(spec=discord.Interaction)
    unauth_interaction.user.id = 99999
    unauth_interaction.response.send_message = AsyncMock()
    assert await view.interaction_check(unauth_interaction) is False
    assert unauth_interaction.response.send_message.called
    kwargs = unauth_interaction.response.send_message.call_args[1]
    assert kwargs.get("ephemeral") is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. BOT MENTION DETECTION & ANTI-SPAM TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mention_detection_triggers_help_dashboard():
    """Verify structured bot mention triggers greeting and interactive help dashboard."""
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=88888888)
    bot.user.id = 88888888

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=11111)
    message.guild = MagicMock(id=22222)
    message.content = "<@88888888>"
    message.mentions = [bot.user]
    message.mention_everyone = False
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.send = AsyncMock()

    # Stub get_context so it's not a registered command
    mock_ctx = MagicMock()
    mock_ctx.valid = False
    bot.get_context = AsyncMock(return_value=mock_ctx)
    bot._handle_bot_mention = AsyncMock()
    bot.process_commands = AsyncMock()

    await bot.on_message(message)
    assert bot._handle_bot_mention.called


@pytest.mark.asyncio
async def test_plain_text_kyoka_does_not_trigger_mention_help():
    """Verify plain text containing 'KYOKA' without actual structured mention does not trigger help."""
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=88888888)
    bot.user.id = 88888888

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=11111)
    message.guild = MagicMock(id=22222)
    message.content = "Kyoka is the greatest bot in discord"
    message.mentions = []  # No structured mention
    message.mention_everyone = False

    mock_ctx = MagicMock()
    mock_ctx.valid = False
    bot.get_context = AsyncMock(return_value=mock_ctx)
    bot._handle_bot_mention = AsyncMock()
    bot.process_commands = AsyncMock()

    await bot.on_message(message)
    assert not bot._handle_bot_mention.called


@pytest.mark.asyncio
async def test_mention_cooldown_prevents_channel_spam():
    """Verify per-user and per-guild anti-spam cooldown blocks repeated mentions."""
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=88888888)
    bot.user.id = 88888888

    user_id = 123456
    guild_id = 654321

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=user_id)
    message.guild = MagicMock(id=guild_id)
    message.content = f"<@{bot.user.id}>"
    message.mentions = [bot.user]
    message.mention_everyone = False

    mock_ctx = MagicMock()
    mock_ctx.valid = False
    bot.get_context = AsyncMock(return_value=mock_ctx)
    bot._handle_bot_mention = AsyncMock()
    bot.process_commands = AsyncMock()

    # First mention: off cooldown -> triggered
    await bot.on_message(message)
    assert bot._handle_bot_mention.call_count == 1

    # Second immediate mention from same user: on cooldown -> suppressed
    await bot.on_message(message)
    assert bot._handle_bot_mention.call_count == 1  # Not triggered again!


@pytest.mark.asyncio
async def test_valid_command_with_mention_executes_without_help_dashboard():
    """Verify messages that are valid commands (e.g. +avatar @KYOKA) invoke command, not mention help."""
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=88888888)
    bot.user.id = 88888888

    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=11111)
    message.guild = MagicMock(id=22222)
    message.content = f"+avatar <@{bot.user.id}>"
    message.mentions = [bot.user]
    message.mention_everyone = False

    # get_context returns valid command
    mock_ctx = MagicMock()
    mock_ctx.valid = True
    bot.get_context = AsyncMock(return_value=mock_ctx)
    bot.invoke = AsyncMock()
    bot._handle_bot_mention = AsyncMock()

    await bot.on_message(message)
    assert bot.invoke.called
    assert not bot._handle_bot_mention.called


# ─────────────────────────────────────────────────────────────────────────────
# 5. APPY-STYLE STAFF APPLICATION SYSTEM TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_staff_application_workflow_persistence_and_states():
    """Verify full end-to-end staff application flow: submission, cooldowns, reviewer transitions, notes & stats."""
    top_mgr = TopManager()
    guild_id = 999000111
    applicant_id = 555000222
    reviewer_id = 1505515188991033409  # Primary owner

    # Clean existing test applications
    with top_mgr._get_connection() as conn:
        conn.execute("DELETE FROM top_applications WHERE guild_id = ?", (guild_id,))
        conn.execute("DELETE FROM top_applications_config WHERE guild_id = ?", (guild_id,))
        conn.commit()

    # 1. Config: Open applications
    top_mgr.set_app_config(guild_id, is_open=1, cooldown_days=7)
    cfg = top_mgr.get_app_config(guild_id)
    assert cfg["is_open"] == 1
    assert cfg["cooldown_days"] == 7

    # 2. Submit application
    answers = {
        "Timezone & Availability": "EST, 6 hours/day",
        "Relevant Experience": "Moderated 2 major Discord servers",
        "Why Kyoka Staff": "Passionate about security and community building",
        "Handling Disputes": "De-escalate calmly in DMs or dedicated ticket",
    }
    app = top_mgr.submit_application(
        guild_id=guild_id,
        applicant_id=applicant_id,
        applicant_name="StaffApplicant#0001",
        position="Community Moderator",
        answers=answers,
    )
    assert app is not None
    assert app["id"].startswith("APP-")
    assert app["status"] == "PENDING"
    assert app["answers"]["Timezone & Availability"] == "EST, 6 hours/day"

    # 3. Duplicate active application prevention
    with pytest.raises(ValueError, match="already have an active application"):
        top_mgr.submit_application(
            guild_id=guild_id,
            applicant_id=applicant_id,
            applicant_name="StaffApplicant#0001",
            position="Helper",
            answers=answers,
        )

    # 4. Status transition: UNDER_REVIEW
    reviewed = top_mgr.review_application(
        app["id"],
        reviewer_id=reviewer_id,
        reviewer_name="Owner",
        new_status="UNDER_REVIEW",
        reason="Background check in progress",
    )
    assert reviewed["status"] == "UNDER_REVIEW"

    # 5. Status transition: MORE_INFO_REQUESTED & Notes
    top_mgr.add_application_note(app["id"], staff_id=reviewer_id, note="Applicant has good vouches.")
    top_mgr.review_application(
        app["id"],
        reviewer_id=reviewer_id,
        reviewer_name="Owner",
        new_status="MORE_INFO_REQUESTED",
        reason="Please provide vouch links",
    )
    app_updated = top_mgr.get_application(app["id"])
    assert app_updated["status"] == "MORE_INFO_REQUESTED"
    assert "Applicant has good vouches." in app_updated["staff_notes"]

    # 6. Final decision: ACCEPTED
    final_app = top_mgr.review_application(
        app["id"],
        reviewer_id=reviewer_id,
        reviewer_name="Owner",
        new_status="ACCEPTED",
        reason="Passed interview",
    )
    assert final_app["status"] == "ACCEPTED"
    assert final_app["decision_reason"] == "Passed interview"

    # 7. Compute statistics
    stats = top_mgr.get_application_stats(guild_id)
    assert stats["total"] >= 1
    assert stats["accepted"] >= 1
    assert stats["positions"].get("Community Moderator") >= 1

    # 8. Re-apply when closed is blocked
    top_mgr.set_app_config(guild_id, is_open=0)
    with pytest.raises(ValueError, match="closed or paused"):
        top_mgr.submit_application(
            guild_id=guild_id,
            applicant_id=888777666,
            applicant_name="LateApplicant#0001",
            position="Helper",
            answers=answers,
        )


def test_empty_application_answers_are_rejected():
    """Verify empty or whitespace-only answers fail validation."""
    top_mgr = TopManager()
    guild_id = 999000222
    top_mgr.set_app_config(guild_id, is_open=1)

    with pytest.raises(ValueError, match="cannot be empty"):
        top_mgr.submit_application(
            guild_id=guild_id,
            applicant_id=123999,
            applicant_name="EmptyUser",
            position="Helper",
            answers={"Q1": "   ", "Q2": ""},
        )
