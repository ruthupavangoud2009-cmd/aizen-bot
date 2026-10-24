from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from src.core.config import Config
from src.cogs.fun.fun import Fun
from src.cogs.general.help import Help, HelpView, HelpCategorySelect
from src.cogs.ticket.ticket_system import (
    TicketSystem,
    TicketInsideControlsView,
    TicketClosedControlsView,
)
from src.security.owner import OWNER_ID
from src.utils.ui import KyokaEmbed, AizenPalette
from src.errors.handler import ErrorHandler


# ─────────────────────────────────────────────────────────────────────────────
# 1. OWNER-ONLY SPAM COMMAND TESTS (LIMIT 2,000 & SECURITY)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spam_unauthorized_user_rejected():
    bot = MagicMock()
    cog = Fun(bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID + 999  # non-owner
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, 10, message="Hello world")

    # Verify rejected before executing
    ctx.send.assert_called_once()
    args, kwargs = ctx.send.call_args
    sent_text = args[0] if args else kwargs.get("content", "")
    assert "⛔" in sent_text
    assert "primary bot owner" in sent_text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_count", [0, -1, -500, 2001, 5000, 100000])
async def test_spam_invalid_counts_rejected(invalid_count):
    bot = MagicMock()
    cog = Fun(bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.send = AsyncMock()

    await cog.spam.callback(cog, ctx, invalid_count, message="Test")

    ctx.send.assert_called_once()
    args, kwargs = ctx.send.call_args
    sent_text = args[0] if args else kwargs.get("content", "")
    assert "1 to 2,000" in sent_text


@pytest.mark.asyncio
async def test_spam_valid_count_and_cancellation():
    bot = MagicMock()
    cog = Fun(bot)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.channel.id = 99887766
    ctx.send = AsyncMock()

    # Test spamcancel when no spam running
    await cog.spamcancel.callback(cog, ctx)
    args, kwargs = ctx.send.call_args
    sent_text = args[0] if args else kwargs.get("content", "")
    assert "no repeat-message task running" in sent_text.lower()

    # Test spam execution with mock sleep
    ctx.send.reset_mock()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await cog.spam.callback(cog, ctx, 5, message="Kyoka Premium")
        assert ctx.channel.id in cog._spam_tasks
        await cog._spam_tasks[ctx.channel.id]
        # 1 intro notification + 5 repeat messages = 6 sends
        assert ctx.send.call_count == 6

    # Test spamcancel on active task
    ctx.send.reset_mock()
    # Create an unresolved task
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    cog._spam_tasks[ctx.channel.id] = dummy_task
    await cog.spamcancel.callback(cog, ctx)
    try:
        await dummy_task
    except asyncio.CancelledError:
        pass
    assert dummy_task.cancelled()
    args, kwargs = ctx.send.call_args
    sent_text = args[0] if args else kwargs.get("content", "")
    assert "cancelled" in sent_text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 2. HELP UI COMPACT EMBED & GIF FOOTER TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_help_compact_embed_structure():
    bot = MagicMock()
    bot.guild_mgr = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "!"
    cog = Help(bot)
    cog._get_latency_ms = MagicMock(return_value=12)

    ctx = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.guild = MagicMock(id=123)

    cmd_ban = MagicMock()
    cmd_ban.qualified_name = "ban"
    cmd_ban.description = "Ban a member"
    cmd_ban.hidden = False

    cmd_ticket = MagicMock()
    cmd_ticket.qualified_name = "ticket"
    cmd_ticket.description = "Ticket panel"
    cmd_ticket.hidden = False

    categories = {
        "🛡️・MODERATION": [cmd_ban],
        "🎫・TICKETS & SUPPORT": [cmd_ticket],
    }

    embed = cog.build_home_embed(ctx, categories)

    assert "Kyoka 3.0" in embed.title
    assert embed.color.value == 0x2B0938  # Dark violet aesthetic
    # Verify embed length is strictly safe under 6,000 chars (prevents 6,939 HTTP 400 error)
    assert len(embed) < 6000
    # Verify fields contain system status and key features
    field_names = [f.name for f in embed.fields]
    assert "📊 System Status" in field_names
    assert "✨ Key Features" in field_names


# ─────────────────────────────────────────────────────────────────────────────
# 3. TICKET SYSTEM CONCURRENCY, ROLLBACK & PERMISSION TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ticket_creation_concurrency_lock():
    bot = MagicMock()
    bot.custom_emojis = None
    bot.ticket_mgr = MagicMock()
    cog = TicketSystem(bot)

    user_id = 111222333
    guild_id = 444555666
    lock_key = (guild_id, user_id)

    # Pre-acquire the lock to simulate an in-progress ticket creation
    cog._creating_tickets.add(lock_key)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.type = discord.InteractionType.component
    interaction.data = {"custom_id": "ticket_open_1", "values": ["general"]}
    interaction.guild.id = guild_id
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id

    sent_containers = []
    async def fake_send(target, container, **kwargs):
        sent_containers.append(container)

    import sys
    import src.cogs.ticket.ticket_system as ts_module
    active_ts = sys.modules.get("src.cogs.ticket.ticket_system", ts_module)

    with patch.object(ts_module, "send_container_response", fake_send), patch.object(active_ts, "send_container_response", fake_send):
        await cog.on_interaction(interaction)

    # Should reject duplicate request
    assert len(sent_containers) == 1
    content = sent_containers[0].components[0]["content"]
    assert "currently being created" in content


@pytest.mark.asyncio
async def test_ticket_creation_atomic_rollback_on_failure():
    bot = MagicMock()
    bot.custom_emojis = None
    bot.ticket_mgr = MagicMock()
    cog = TicketSystem(bot)

    user_id = 12345
    guild_id = 67890

    interaction = MagicMock(spec=discord.Interaction)
    interaction.type = discord.InteractionType.component
    interaction.data = {"custom_id": "ticket_open_1_general", "values": ["general"]}
    interaction.guild.id = guild_id
    interaction.guild.get_channel = MagicMock(return_value=None)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.name = "TestUser"
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()

    # Mock panel lookup
    bot.ticket_mgr.get_panel_by_id = AsyncMock(return_value={
        "id": 1,
        "category_id": None,
        "naming_format": "ticket-{count}",
        "support_role_id": None,
    })
    bot.ticket_mgr.get_active_ticket_for_user = AsyncMock(return_value=None)
    bot.ticket_mgr.get_next_ticket_number = AsyncMock(return_value=42)

    # Mock guild channel creation
    created_channel = AsyncMock(spec=discord.TextChannel)
    created_channel.id = 99887711
    created_channel.delete = AsyncMock()
    interaction.guild.create_text_channel = AsyncMock(return_value=created_channel)

    # Mock DB failure during ticket insert
    bot.ticket_mgr.create_ticket = AsyncMock(side_effect=RuntimeError("Database write error"))

    sent_containers = []
    async def fake_send(target, container, **kwargs):
        sent_containers.append(container)

    import sys
    import src.cogs.ticket.ticket_system as ts_module
    active_ts = sys.modules.get("src.cogs.ticket.ticket_system", ts_module)

    with patch.object(ts_module, "send_container_response", fake_send), patch.object(active_ts, "send_container_response", fake_send):
        await cog.on_interaction(interaction)

    # Verify channel was deleted to avoid orphaned channels
    created_channel.delete.assert_called_once()
    # Lock was released
    assert (guild_id, user_id) not in cog._creating_tickets
    # Error message sent to user
    assert len(sent_containers) == 1
    content = sent_containers[0].components[0]["content"]
    assert "Creation Failed" in content


@pytest.mark.asyncio
async def test_ticket_inside_controls_permissions():
    bot = MagicMock()
    bot.custom_emojis = None
    bot.ticket_mgr = MagicMock()
    bot.ticket_mgr.get_ticket = AsyncMock(return_value={"user_id": 12345, "panel_id": 1})
    bot.ticket_mgr.get_panel_by_id = AsyncMock(return_value={"support_role_id": None})
    cog = TicketSystem(bot)
    view = TicketInsideControlsView(cog)

    # Unauthorized outsider interaction
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel_id = 777888999
    interaction.user.id = 99999  # Not creator (12345)
    interaction.user.roles = []
    interaction.user.guild_permissions.administrator = False
    interaction.user.guild_permissions.manage_channels = False
    interaction.guild.get_role = MagicMock(return_value=None)

    sent_containers = []
    async def fake_send(target, container, **kwargs):
        sent_containers.append(container)

    import sys
    import src.cogs.ticket.ticket_system as ts_module
    active_ts = sys.modules.get("src.cogs.ticket.ticket_system", ts_module)

    with patch.object(ts_module, "send_container_response", fake_send), patch.object(active_ts, "send_container_response", fake_send):
        # Test unauthorized close attempt
        await view.btn_close.callback(interaction)

    assert len(sent_containers) == 1
    content = sent_containers[0].components[0]["content"]
    assert "Permission Denied" in content
    assert "Only the ticket creator or authorized staff" in content


@pytest.mark.asyncio
async def test_ticket_closed_controls_permissions():
    bot = MagicMock()
    bot.custom_emojis = None
    bot.ticket_mgr = MagicMock()
    bot.ticket_mgr.get_ticket = AsyncMock(return_value={"user_id": 12345, "panel_id": 1})
    bot.ticket_mgr.get_panel_by_id = AsyncMock(return_value={"support_role_id": None})
    cog = TicketSystem(bot)
    view = TicketClosedControlsView(cog)

    # Unauthorized outsider interaction
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel_id = 777888999
    interaction.user.id = 99999  # Not creator (12345)
    interaction.user.roles = []
    interaction.user.guild_permissions.administrator = False
    interaction.user.guild_permissions.manage_channels = False
    interaction.guild.get_role = MagicMock(return_value=None)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    # Test unauthorized reopen attempt
    await view.btn_reopen.callback(interaction)
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    sent_msg = (args[0] if args else kwargs.get("content", "")).lower()
    assert "only the ticket creator or authorized staff" in sent_msg
    assert kwargs.get("ephemeral") is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. SHARED UI UTILITIES & ERROR TRACEBACK MASKING TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_shared_ui_embed_helpers():
    target = MagicMock()
    target.display_name = "BadActor#0001"
    target.mention = "@BadActor"
    target.id = 11112222
    target.display_avatar.url = "https://example.com/target.png"

    moderator = MagicMock()
    moderator.display_name = "Admin#1234"
    moderator.mention = "@Admin"

    # Moderation embed
    mod_embed = KyokaEmbed.moderation(
        action="Ban",
        target=target,
        moderator=moderator,
        reason="Breaking rule 1",
    )
    assert "Moderation Action • Ban" in mod_embed.title
    assert mod_embed.color.value == AizenPalette.ROYAL_VIOLET

    # AFK notice embed
    member = MagicMock()
    member.display_name = "Aizen"
    member.mention = "@Aizen"
    member.display_avatar.url = "https://example.com/aizen.png"

    afk_embed = KyokaEmbed.afk_notice(
        member=member,
        reason="Studying the Hōgyoku",
        duration_str="10m",
    )
    assert "Member AFK" in afk_embed.title
    assert "Studying the Hōgyoku" in afk_embed.description

    # Vouch card embed
    recipient = MagicMock()
    recipient.display_name = "TrustedSeller"
    recipient.mention = "@TrustedSeller"
    recipient.display_avatar.url = "https://example.com/seller.png"

    vouch_embed = KyokaEmbed.vouch_card(
        recipient=recipient,
        author=moderator,
        comment="Fast and legit!",
        total_vouches=5,
    )
    assert "Vouch Recorded for TrustedSeller" in vouch_embed.title
    assert "Fast and legit!" in vouch_embed.description
    assert "5" in vouch_embed.description


@pytest.mark.asyncio
async def test_error_traceback_masked_from_users():
    bot = MagicMock()
    bot.custom_emojis = None
    cog = ErrorHandler(bot)

    ctx = MagicMock()
    ctx.command = MagicMock(spec=["qualified_name", "signature"])
    ctx.command.qualified_name = "testcmd"
    ctx.command.signature = ""
    ctx.prefix = "!"
    ctx.author.display_name = "RegularUser"

    sent_containers = []
    async def fake_send(target, container, **kwargs):
        sent_containers.append(container)

    with patch("src.errors.handler.send_container_response", side_effect=fake_send):
        secret_exc = ValueError("Secret database password db_pass_1234 in internal_method()")
        await cog.on_command_error(ctx, secret_exc)

    assert len(sent_containers) == 1
    content = sent_containers[0].components[0]["content"]
    assert "Traceback" not in content
    assert "db_pass_1234" not in content
    assert "Internal Error" in content
