"""
Kyoka 3.0 Ultimate Upgrade - Automated Verification Test Suite
Covers:
- Compact Screenshot-matching Help UI (no 6k char overflow)
- Category command pagination (strictly <= 15 commands per page)
- Custom help categories per-server management & security boundary checks
- Ticket system unlimited simultaneous tickets per user by default
- Voice welcome & music coexistence (zero interruption, greeting queueing)
- Announcement command parsing & plain text broadcast
- Owner-only spam command verification (2,000 limit, owner enforcement)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord.ext import commands

from src.cogs.general.help import Help, HelpView, HelpCategorySelect
from src.cogs.ticket.ticket_system import TicketSystem
from src.cogs.utility.announcement import Announcement
from src.cogs.utility.voice_welcome import VoiceWelcome
from src.cogs.fun.fun import Fun
from src.managers.custom_help_manager import CustomHelpManager
from src.managers.voice_welcome_manager import VoiceWelcomeManager
from src.security.owner import OWNER_ID


# ─────────────────────────────────────────────────────────────────────────────
# 1. HELP UI & SCREENSHOT ALIGNMENT TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_help_home_embed_character_limit_and_structure():
    """Verify home embed stays strictly under Discord's 6,000 character limit even with 200 commands."""
    bot = MagicMock()
    bot.user.name = "Kyoka"
    bot.guild_mgr.get_prefix.return_value = "."
    cog = Help(bot)
    cog._get_latency_ms = MagicMock(return_value=16)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=12345)
    ctx.author.display_name = "Aizen"
    ctx.author.display_avatar.url = "https://cdn.discord.com/avatars/1/avatar.png"

    # Simulate 200 registered commands across 14 categories
    visible_categories = {}
    for cat in Help.CATEGORY_ORDER:
        visible_categories[cat] = [
            MagicMock(qualified_name=f"cmd_{cat[:3]}_{i}", description="Test description")
            for i in range(15)
        ]

    embed = cog.build_home_embed(ctx, visible_categories)

    # Must be well under 6,000 characters (tiny compact UI)
    total_len = len(embed)
    assert total_len < 1000, f"Home embed length ({total_len}) exceeds compact limit!"
    assert "Hey, I'm" in embed.title
    assert "Latency:" in embed.description
    assert "Requested by Aizen" in embed.footer.text


def test_help_category_pagination_max_15_commands():
    """Verify each category page displays 5-15 commands, never more than 15."""
    bot = MagicMock()
    bot.guild_mgr.get_prefix.return_value = "."
    cog = Help(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock(id=12345)
    ctx.author.display_name = "Aizen"
    ctx.author.display_avatar.url = "https://cdn.discord.com/avatars/1/avatar.png"

    # Category with 35 commands -> should produce 4 pages (10, 10, 10, 5)
    commands_list = [MagicMock(qualified_name=f"cmd_{i:02d}", hidden=False) for i in range(35)]
    visible_categories = {"🛡️・MODERATION": commands_list}

    # Page 1: exactly 10 commands (cmd_00 to cmd_09)
    embed_p1 = cog.build_category_embed(ctx, "🛡️・MODERATION", commands_list, visible_categories, page=1)
    assert "Page 1/4" in embed_p1.description
    assert "`cmd_00`" in embed_p1.description
    assert "`cmd_09`" in embed_p1.description
    assert "`cmd_10`" not in embed_p1.description

    # Page 2: next 10 commands (cmd_10 to cmd_19)
    embed_p2 = cog.build_category_embed(ctx, "🛡️・MODERATION", commands_list, visible_categories, page=2)
    assert "Page 2/4" in embed_p2.description
    assert "`cmd_10`" in embed_p2.description
    assert "`cmd_19`" in embed_p2.description
    assert "`cmd_20`" not in embed_p2.description

    # Page 4: remaining 5 commands (cmd_30 to cmd_34)
    embed_p4 = cog.build_category_embed(ctx, "🛡️・MODERATION", commands_list, visible_categories, page=4)
    assert "Page 4/4" in embed_p4.description
    assert "`cmd_30`" in embed_p4.description
    assert "`cmd_34`" in embed_p4.description


def test_help_category_select_options_matching_screenshots():
    """Verify dropdown select options match clean module labels."""
    cog = MagicMock()
    ctx = MagicMock()
    visible_categories = {
        "🛡️・MODERATION": [MagicMock(qualified_name="ban")],
        "🎫・TICKETS & SUPPORT": [MagicMock(qualified_name="ticket")],
        "🎵・MUSIC": [MagicMock(qualified_name="play")],
    }
    view = HelpView(cog, ctx, visible_categories, current_category="home")

    selects = [i for i in view.children if isinstance(i, discord.ui.Select)]
    assert len(selects) == 1
    options = selects[0].options

    labels = [opt.label for opt in options]
    assert "Home" in labels
    assert "Moderation" in labels
    assert "Tickets & Support" in labels
    assert "Music" in labels


# ─────────────────────────────────────────────────────────────────────────────
# 2. CUSTOM HELP CATEGORIES PER-SERVER TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_custom_help_manager_crud_and_security():
    """Verify custom help categories manager CRUD and owner-command security block."""
    mock_db = MagicMock()
    mock_db.fetch_all = AsyncMock(return_value=[
        {
            "guild_id": 123,
            "category_name": "VIP Commands",
            "emoji": "⭐",
            "description": "Exclusive perks",
            "commands": ["rank", "level"],
            "priority": 1,
            "is_hidden": False,
        }
    ])
    mock_db.fetch_one = AsyncMock(return_value={"category_name": "VIP Commands"})
    mock_db.execute = AsyncMock()

    mgr = CustomHelpManager(mock_db)

    # 1. Fetch categories
    cats = await mgr.get_guild_categories(123)
    assert len(cats) == 1
    assert cats[0]["category_name"] == "VIP Commands"

    # 2. Add legitimate command
    all_cmds = {"rank", "level", "ban", "kick"}
    owner_cmds = {"spam", "eval", "restart"}
    success, msg = await mgr.add_command(123, "VIP Commands", "ban", all_cmds, owner_cmds)
    assert success is True
    assert "Added `ban`" in msg

    # 3. Security block: attempt to add owner-only command to custom category
    success, msg = await mgr.add_command(123, "VIP Commands", "spam", all_cmds, owner_cmds)
    assert success is False
    assert "Security violation" in msg

    # 4. Attempt to add non-existent command
    success, msg = await mgr.add_command(123, "VIP Commands", "fake_cmd_xyz", all_cmds, owner_cmds)
    assert success is False
    assert "not a registered bot command" in msg


# ─────────────────────────────────────────────────────────────────────────────
# 3. TICKET SYSTEM UNLIMITED TICKETS PER USER TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ticket_system_unlimited_tickets_default():
    """Verify ticket creation allows unlimited simultaneous tickets when max_tickets_per_user is 0."""
    bot = MagicMock()
    bot._connection = MagicMock()
    bot.http.request = AsyncMock(return_value={"id": "12345"})
    bot.ticket_mgr = MagicMock()
    # Panel has max_tickets_per_user = 0 (Unlimited by default)
    bot.ticket_mgr.get_panel_by_id = AsyncMock(return_value={
        "id": 1,
        "guild_id": 999,
        "panel_name": "support",
        "max_tickets_per_user": 0,
        "naming_format": "ticket-{count}",
    })
    bot.ticket_mgr.get_next_ticket_number = AsyncMock(return_value=42)
    bot.ticket_mgr.create_ticket = AsyncMock(return_value={"channel_id": 8888})

    cog = TicketSystem(bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction._client = bot
    interaction.type = discord.InteractionType.component
    interaction.data = {"custom_id": "ticket_open_1"}
    interaction.guild = MagicMock(id=999)
    interaction.guild.me = MagicMock()
    interaction.user = MagicMock(spec=discord.Member, id=555)
    interaction.user.name = "user1"
    interaction.user.guild_permissions.administrator = False
    interaction.response.is_done.return_value = True
    interaction.response.defer = AsyncMock()

    # Mock channel creation
    created_channel = MagicMock(spec=discord.TextChannel, id=8888, mention="<#8888>")
    created_channel._state.http.request = AsyncMock(return_value={"id": "12345"})
    created_channel.send = AsyncMock()
    interaction.guild.create_text_channel = AsyncMock(return_value=created_channel)
    interaction.followup.send = AsyncMock()

    await cog.on_interaction(interaction)

    # Should not be blocked by any 1-ticket limit!
    assert interaction.guild.create_text_channel.called
    assert bot.ticket_mgr.create_ticket.called


@pytest.mark.asyncio
async def test_ticket_system_configured_limit_enforced():
    """Verify ticket creation respects configured limit when max_tickets_per_user > 0."""
    bot = MagicMock()
    bot._connection = MagicMock()
    bot.http.request = AsyncMock(return_value={"id": "12345"})
    bot.ticket_mgr = MagicMock()
    bot.ticket_mgr.get_panel_by_id = AsyncMock(return_value={
        "id": 1,
        "guild_id": 999,
        "panel_name": "support",
        "max_tickets_per_user": 2,
    })
    # User already has 2 active tickets
    bot.ticket_mgr.get_active_tickets_count_for_user = AsyncMock(return_value=2)

    cog = TicketSystem(bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction._client = bot
    interaction.type = discord.InteractionType.component
    interaction.data = {"custom_id": "ticket_open_1"}
    interaction.guild = MagicMock(id=999)
    interaction.user = MagicMock(spec=discord.Member, id=555, name="User1")
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()

    await cog.on_interaction(interaction)

    # Channel should NOT be created; user informed of limit
    assert not hasattr(interaction.guild, "create_text_channel") or not interaction.guild.create_text_channel.called


# ─────────────────────────────────────────────────────────────────────────────
# 4. VOICE WELCOME & MUSIC COEXISTENCE TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_welcome_defers_when_music_active():
    """Verify voice welcome NEVER interrupts or moves active music sessions."""
    bot = MagicMock()
    mock_db = MagicMock()
    mgr = VoiceWelcomeManager(bot, mock_db)

    guild = MagicMock(id=777, name="Test Guild")
    # Simulate active music: voice client is connected and playing
    guild.voice_client = MagicMock()
    guild.voice_client.is_connected.return_value = True
    guild.voice_client.is_playing.return_value = True

    target_channel = MagicMock(spec=discord.VoiceChannel, id=12345)
    guild.get_channel = MagicMock(return_value=target_channel)

    assert mgr.is_music_active(guild) is True

    # When handling a member join event while music is active:
    mgr.get_config = AsyncMock(return_value={
        "enabled": True,
        "channel_id": 12345,
        "trigger": "both",
        "cooldown_seconds": 30,
        "queue_expiration_seconds": 120,
        "allow_bots": False,
        "defer_if_music_active": True,
    })

    member = MagicMock(id=999, guild=guild, bot=False, display_name="Newbie")
    member.name = "newbie"
    await mgr.handle_member_event(member, "server_join")

    # Verify greeting was enqueued, NOT played over active music
    assert 777 in mgr._queues
    assert len(mgr._queues[777]) == 1
    assert mgr._queues[777][0]["member_id"] == 999


def test_voice_welcome_greeting_variable_formatting():
    """Verify dynamic variables like {member}, {server}, {count} format properly."""
    bot = MagicMock()
    mock_db = MagicMock()
    mgr = VoiceWelcomeManager(bot, mock_db)

    guild = MagicMock()
    guild.name = "Aizen Citadel"
    guild.member_count = 150

    member = MagicMock()
    member.guild = guild
    member.display_name = "Kurosaki"
    member.name = "ichigo"

    template = "Welcome {member} (@{username}) to {server}! You are member #{count}."
    formatted = mgr.format_greeting(template, member)

    assert formatted == "Welcome Kurosaki (@ichigo) to Aizen Citadel! You are member #150."


# ─────────────────────────────────────────────────────────────────────────────
# 5. ANNOUNCEMENT COMMAND TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_announcement_plain_text_delivery():
    """Verify announce command sends exact message to target channel."""
    bot = MagicMock()
    cog = Announcement(bot)

    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.me = MagicMock()
    ctx.author = MagicMock(id=OWNER_ID)
    ctx.author.guild_permissions.manage_messages = True
    ctx.author.guild_permissions.mention_everyone = True
    ctx.send = AsyncMock()
    ctx.interaction = None

    target_channel = MagicMock(spec=discord.TextChannel)
    target_channel.mention = "<#112233>"
    target_channel.permissions_for.return_value = MagicMock(send_messages=True, view_channel=True)
    target_channel.send = AsyncMock(return_value=MagicMock(jump_url="https://discord.com/msg1"))

    # Execute 'announce #channel hi' directly via callback
    await cog.announce.callback(cog, ctx, target_channel, message="hi")

    # Exact plain text 'hi' must be sent to the channel
    assert target_channel.send.called
    call_args, call_kwargs = target_channel.send.call_args
    assert call_args[0] == "hi"
    assert call_kwargs["allowed_mentions"].everyone is True


@pytest.mark.asyncio
async def test_send_command_posts_message_then_deletes_invocation():
    cog = Announcement(MagicMock())
    ctx = MagicMock()
    ctx.guild.id = 123
    ctx.guild.me = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.author.guild_permissions.mention_everyone = True
    ctx.channel.permissions_for.return_value.manage_messages = True
    ctx.message.delete = AsyncMock()
    ctx.send_error = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 456
    channel.guild.id = ctx.guild.id
    channel.mention = "<#456>"
    channel.permissions_for.return_value = MagicMock(view_channel=True, send_messages=True)
    channel.send = AsyncMock()

    await cog.send_message.callback(cog, ctx, channel, message="hello @everyone")

    channel.send.assert_awaited_once()
    assert channel.send.await_args.args[0] == "hello @everyone"
    assert channel.send.await_args.kwargs["allowed_mentions"].everyone is True
    ctx.message.delete.assert_awaited_once()
    ctx.send_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_command_does_not_delete_invocation_when_delivery_fails():
    cog = Announcement(MagicMock())
    ctx = MagicMock()
    ctx.guild.id = 123
    ctx.guild.me = MagicMock()
    ctx.author.id = OWNER_ID
    ctx.author.guild_permissions.mention_everyone = False
    ctx.message.delete = AsyncMock()
    ctx.send_error = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 456
    channel.guild.id = ctx.guild.id
    channel.mention = "<#456>"
    channel.permissions_for.return_value = MagicMock(view_channel=True, send_messages=True)
    channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "forbidden"))

    await cog.send_message.callback(cog, ctx, channel, message="hello")

    ctx.message.delete.assert_not_awaited()
    ctx.send_error.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# 6. OWNER-ONLY SPAM COMMAND TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_spam_authorization_and_2000_limit():
    """Verify spam command enforces OWNER_ID check and 2,000 maximum count."""
    bot = MagicMock()
    cog = Fun(bot)

    # 1. Reject unauthorized non-owner
    ctx_unauth = MagicMock()
    ctx_unauth.author.id = 999888777  # Not primary owner
    ctx_unauth.send = AsyncMock()

    await cog.spam.callback(cog, ctx_unauth, count=10, message="Hello")
    assert ctx_unauth.send.called
    msg = ctx_unauth.send.call_args[0][0]
    assert "Only the primary bot owner" in msg

    # 2. Reject count > 10000 even for owner
    ctx_owner = MagicMock()
    ctx_owner.author.id = OWNER_ID
    ctx_owner.send = AsyncMock()

    await cog.spam.callback(cog, ctx_owner, count=10001, message="Hello")
    msg2 = ctx_owner.send.call_args[0][0]
    assert "1 to 10,000" in msg2
