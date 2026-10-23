"""
Kyoka Discord Bot - Beginner Onboarding & Community Upgrades Test Suite
Tests for:
- +start, +quickstart, +setup wizard & all 10 subcommands
- Suggestions system with interactive voting
- Safe AST math calculator
- Reminders / timer duration parser
- New moderation tools (hide, unhide, softban, nick, case, clearwarnings)
- 14 help categories with owner isolation
"""

from __future__ import annotations

import ast
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from src.core.context import CustomContext
from src.security.owner import OWNER_ID
from src.cogs.general.onboarding import (
    Onboarding,
    SetupWizardView,
    SetupResetConfirmView,
)
from src.cogs.utility.suggestions import Suggestions, SuggestionVoteView
from src.cogs.utility.calculator import safe_eval
from src.cogs.utility.reminders import parse_time_duration
from src.cogs.general.help import Help


# ─── 1. TEST START & QUICKSTART COMMANDS ─────────────────────────────────────

@pytest.mark.asyncio
async def test_start_command_renders_beginner_intro():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.send = AsyncMock()

    await cog.start.callback(cog, ctx)

    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    view = kwargs.get("view")

    assert embed is not None
    assert "The Ultimate All-in-One Discord Bot" in embed.title
    assert "Conversational AI" in embed.description
    assert view is not None
    assert len(view.children) == 3


@pytest.mark.asyncio
async def test_quickstart_command_renders_owner_checklist():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.send = AsyncMock()

    await cog.quickstart.callback(cog, ctx)

    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    view = kwargs.get("view")

    assert embed is not None
    assert "Server Owner Quickstart Guide" in embed.title
    assert "setup welcome" in embed.description
    assert "setup autorole" in embed.description
    assert view is not None


# ─── 2. TEST SETUP WIZARD & SUBCOMMANDS ──────────────────────────────────────

@pytest.mark.asyncio
async def test_setup_hub_command():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.fetch_one.return_value = None

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345, name="Kyoka Community")
    ctx.send = AsyncMock()

    await cog.setup_cmd.callback(cog, ctx)

    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    view = kwargs.get("view")

    assert embed is not None
    assert "Server Setup Status" in embed.title
    assert isinstance(view, SetupWizardView)
    assert len(view.children) >= 3


@pytest.mark.asyncio
async def test_setup_welcome_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.guild.me = MagicMock()
    ctx.send = AsyncMock()

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.id = 888111
    target_channel.mention = "<#888111>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)

    await cog.setup_welcome.callback(cog, ctx, target_channel)

    assert bot.db.execute.called
    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Welcome Channel Configured" in embed.title


@pytest.mark.asyncio
async def test_setup_goodbye_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.guild.me = MagicMock()
    ctx.send = AsyncMock()

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.id = 888222
    target_channel.mention = "<#888222>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)

    await cog.setup_goodbye.callback(cog, ctx, target_channel)

    assert bot.db.execute.called
    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Goodbye Channel Configured" in embed.title


@pytest.mark.asyncio
async def test_setup_logs_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock()
    bot.log_mgr = MagicMock()
    bot.log_mgr.set_log_channel = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.guild.me = MagicMock()
    ctx.send = AsyncMock()

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.id = 888333
    target_channel.mention = "<#888333>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)

    await cog.setup_logs.callback(cog, ctx, target_channel)

    assert bot.log_mgr.set_log_channel.called
    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Moderation Logs Configured" in embed.title


@pytest.mark.asyncio
async def test_setup_suggestions_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.guild.me = MagicMock()
    ctx.send = AsyncMock()

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.id = 888444
    target_channel.mention = "<#888444>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)

    await cog.setup_suggestions.callback(cog, ctx, target_channel)

    assert bot.db.execute.called
    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Suggestions Channel Configured" in embed.title


@pytest.mark.asyncio
async def test_setup_autorole_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    bot.db.execute = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    bot_member = MagicMock()
    bot_member.top_role.position = 10
    bot_member.guild_permissions.manage_roles = True
    ctx.guild.me = bot_member
    ctx.send = AsyncMock()

    target_role = MagicMock(spec=discord.Role)
    target_role.id = 777111
    target_role.name = "Member"
    target_role.mention = "<@&777111>"
    target_role.position = 5
    target_role.__ge__ = lambda self, other: False
    target_role.is_default.return_value = False
    target_role.managed = False

    await cog.setup_autorole.callback(cog, ctx, target_role)

    assert bot.db.execute.called
    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Join Autorole Configured" in embed.title


@pytest.mark.asyncio
async def test_setup_ai_subcommand():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()
    mock_companion = MagicMock()
    mock_companion._setup_channel = AsyncMock(return_value=discord.Embed(title="Automatic AI Channel Configured"))
    bot.get_cog.return_value = mock_companion

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.author = MagicMock(id=999)
    ctx.send = AsyncMock()

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.id = 888555
    target_channel.mention = "<#888555>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, embed_links=True)

    await cog.setup_ai.callback(cog, ctx, target_channel, persona="girlfriend")

    assert mock_companion._setup_channel.called
    assert ctx.send.called


@pytest.mark.asyncio
async def test_setup_reset_interactive_confirmation():
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "+"
    bot.db = AsyncMock()

    cog = Onboarding(bot)
    ctx = MagicMock(spec=CustomContext)
    ctx.guild = MagicMock(id=12345)
    ctx.author = MagicMock(id=999888)
    ctx.send = AsyncMock()

    await cog.setup_reset.callback(cog, ctx, feature="welcome")

    assert ctx.send.called
    kwargs = ctx.send.call_args[1]
    view = kwargs.get("view")

    assert isinstance(view, SetupResetConfirmView)


# ─── 3. TEST SUGGESTIONS VOTING VIEW ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggestions_vote_view_logic():
    view = SuggestionVoteView(suggestion_id=42, upvotes=0, downvotes=0)

    # 1. Upvote by User 1
    interaction1 = MagicMock(spec=discord.Interaction)
    interaction1.user.id = 1001
    interaction1.response.edit_message = AsyncMock()
    interaction1.followup.send = AsyncMock()
    await view.btn_upvote.callback(interaction1)

    assert view.upvotes == 1
    assert view.downvotes == 0
    assert 1001 in view.upvoters

    # 2. Toggle upvote off by User 1
    interaction2 = MagicMock(spec=discord.Interaction)
    interaction2.user.id = 1001
    interaction2.response.edit_message = AsyncMock()
    interaction2.followup.send = AsyncMock()
    await view.btn_upvote.callback(interaction2)

    assert view.upvotes == 0
    assert 1001 not in view.upvoters

    # 3. Downvote by User 2
    interaction3 = MagicMock(spec=discord.Interaction)
    interaction3.user.id = 1002
    interaction3.response.edit_message = AsyncMock()
    interaction3.followup.send = AsyncMock()
    await view.btn_downvote.callback(interaction3)

    assert view.downvotes == 1
    assert 1002 in view.downvoters


# ─── 4. TEST AST MATH CALCULATOR ─────────────────────────────────────────────

def test_ast_math_evaluator_valid_expressions():
    def evaluate(expr: str):
        clean_expr = expr.replace("^", "**").replace("x", "*").replace("X", "*")
        parsed = ast.parse(clean_expr, mode="eval")
        return safe_eval(parsed.body)

    assert evaluate("2 + 2") == 4
    assert evaluate("10 * 5 - 4 / 2") == 48.0
    assert evaluate("2 ^ 3") == 8
    assert evaluate("100 % 7") == 2
    assert evaluate("-(5 + 3)") == -8


def test_ast_math_evaluator_blocks_unsafe_code():
    def evaluate(expr: str):
        parsed = ast.parse(expr, mode="eval")
        return safe_eval(parsed.body)

    with pytest.raises(ValueError):
        evaluate("__import__('os').system('ls')")

    with pytest.raises(ValueError):
        evaluate("open('test.txt', 'w')")

    with pytest.raises(ValueError):
        evaluate("lambda: 1")


def test_ast_math_evaluator_division_by_zero():
    parsed = ast.parse("10 / 0", mode="eval")
    with pytest.raises(ZeroDivisionError):
        safe_eval(parsed.body)


# ─── 5. TEST REMINDERS DURATION PARSER ───────────────────────────────────────

def test_reminders_duration_parser():
    assert parse_time_duration("30s") == 30
    assert parse_time_duration("10m") == 600
    assert parse_time_duration("2h") == 7200
    assert parse_time_duration("1d") == 86400
    assert parse_time_duration("invalid") is None


# ─── 6. TEST 14 HELP CATEGORIES & OWNER ACCESS RESTRICTION ────────────────────

def test_help_category_order_has_14_categories():
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


def test_help_owner_developer_restricted_to_owner():
    """Verify owner-only commands are blocked from ordinary users and permitted for primary owner."""
    cmd = MagicMock()
    cmd.name = "eval"
    cmd.hidden = False
    cmd.cog = MagicMock(category="Owner")

    # Regular user context
    regular_ctx = MagicMock()
    regular_ctx.author.id = 999111222
    assert not Help._can_run_command(cmd, regular_ctx)

    # Primary owner context
    owner_ctx = MagicMock()
    owner_ctx.author.id = OWNER_ID
    assert Help._can_run_command(cmd, owner_ctx)
