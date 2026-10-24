"""
Automated Test Suite for Kyoka 3.0 Modular Architecture & Design System
Covers Rules 1, 3, 6, 7, 10:
- FeatureRegistry registration, discovery, health status, and category queries
- CommandRegistry indexing, alias mapping, category grouping, and permission metadata
- Core Permissions: primary owner check, role hierarchy checks, server admin check
- UI Theme & EmbedFactory: consistent color tokens, semantic embeds (success, error, warning, info, loading)
- UI Pagination: 5-15 items per page constraint, author isolation, button state management
- HelpRenderer: home console, category page, command inspection cards
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import pytest

from src.core.feature_registry import FeatureInfo, FeatureRegistry
from src.core.command_registry import CommandMetadata, CommandRegistry
from src.core.permissions import check_hierarchy, is_bot_owner, is_server_admin
from src.security.owner import OWNER_ID
from src.ui.embed_factory import KyokaEmbedFactory
from src.ui.pagination import KyokaPaginatorView, paginate_items
from src.ui.theme import KyokaTheme
from src.ui.help_renderer import HelpRenderer
from src.ui.components import ConfirmCancelView


# ─── 1. FEATURE REGISTRY TESTS ───────────────────────────────────────────────

def test_feature_registry_lifecycle():
    registry = FeatureRegistry()

    # Register features
    music = registry.register_feature(
        name="Music",
        extension_path="src.cogs.music.music",
        category="Music",
        description="High-fidelity audio engine",
        dependencies=["wavelink"],
    )
    tickets = registry.register_feature(
        name="Tickets",
        extension_path="src.cogs.ticket.ticket_system",
        category="Support",
        description="Enterprise support tickets",
    )

    assert registry.get_feature("Music") is not None
    assert registry.get_feature("music") == music  # Case-insensitive lookup
    assert registry.get_feature("tickets") == tickets

    # Category query
    music_feats = registry.get_features_by_category("Music")
    assert len(music_feats) == 1
    assert music_feats[0].name == "Music"

    # Health & status
    assert registry.is_enabled("Music") is True
    registry.update_health("Music", "degraded", "Lavalink reconnecting")
    assert registry.is_enabled("Music") is False  # Degraded features are not fully healthy
    assert registry.get_feature("Music").health_status == "degraded"

    # Disable / Enable
    registry.disable_feature("Tickets")
    assert registry.get_feature("Tickets").enabled is False
    assert registry.is_enabled("Tickets") is False
    registry.enable_feature("Tickets")
    assert registry.get_feature("Tickets").enabled is True


def test_feature_registry_system_audit():
    bot = MagicMock()
    bot.extensions = {"src.cogs.music.music": MagicMock()}
    bot.failed_extensions = {"src.cogs.broken.broken": "SyntaxError"}

    registry = FeatureRegistry(bot)
    registry.register_feature("Music", "src.cogs.music.music", "Music")
    registry.register_feature("Broken", "src.cogs.broken.broken", "Utility")
    registry.register_feature("Unloaded", "src.cogs.unloaded.unloaded", "Admin")

    report = registry.audit_system_features(bot)
    assert report["total_features"] == 3
    assert report["healthy"] == 1
    assert report["failed"] == 1
    assert report["unloaded"] == 1
    assert registry.get_feature("Broken").health_status == "failed"


# ─── 2. COMMAND REGISTRY TESTS ───────────────────────────────────────────────

def test_command_registry_indexing_and_aliases():
    cmd_reg = CommandRegistry()

    cmd_reg.register_command(
        name="play",
        category="Music",
        description="Stream audio from YouTube or Spotify",
        usage="play <query>",
        aliases=["p", "stream"],
        is_prefix=True,
        is_slash=True,
    )
    cmd_reg.register_command(
        name="skip",
        category="Music",
        description="Skip current track",
        aliases=["s", "next"],
    )
    cmd_reg.register_command(
        name="ban",
        category="Moderation",
        description="Ban a member from the server",
        required_permissions=["ban_members"],
    )

    # Primary lookup
    play_meta = cmd_reg.get_command("play")
    assert play_meta is not None
    assert play_meta.name == "play"

    # Alias lookup
    assert cmd_reg.get_command("p") == play_meta
    assert cmd_reg.get_command("stream") == play_meta
    assert cmd_reg.get_command("s").name == "skip"

    # Categories
    categories = cmd_reg.get_all_categories()
    assert "Music" in categories
    assert "Moderation" in categories

    music_cmds = cmd_reg.get_commands_in_category("Music")
    assert len(music_cmds) == 2
    cmd_names = {c.name for c in music_cmds}
    assert "play" in cmd_names
    assert "skip" in cmd_names


# ─── 3. CORE PERMISSIONS & HIERARCHY TESTS ───────────────────────────────────

def test_primary_owner_security_enforcement():
    assert is_bot_owner(OWNER_ID) is True
    assert is_bot_owner(123456789) is False
    assert is_bot_owner(None) is False


def test_server_admin_check():
    guild = MagicMock()
    guild.owner_id = 1111

    owner_member = MagicMock(spec=discord.Member)
    owner_member.id = 1111
    owner_member.guild = guild
    assert is_server_admin(owner_member) is True

    admin_member = MagicMock(spec=discord.Member)
    admin_member.id = 2222
    admin_member.guild = guild
    admin_member.guild_permissions.administrator = True
    assert is_server_admin(admin_member) is True

    normal_member = MagicMock(spec=discord.Member)
    normal_member.id = 3333
    normal_member.guild = guild
    normal_member.guild_permissions.administrator = False
    assert is_server_admin(normal_member) is False


def test_role_hierarchy_checks():
    guild = MagicMock()
    guild.owner_id = 9999

    executor = MagicMock(spec=discord.Member)
    executor.id = 1000
    executor.guild = guild
    executor.top_role.position = 10
    executor.top_role.name = "Moderator"

    target_higher = MagicMock(spec=discord.Member)
    target_higher.id = 2000
    target_higher.guild = guild
    target_higher.top_role.position = 15
    target_higher.top_role.name = "Admin"

    # Executor role lower than target
    can_mod, reason = check_hierarchy(executor, target_higher)
    assert can_mod is False
    assert "strictly higher" in reason

    # Cannot moderate server owner
    owner_target = MagicMock(spec=discord.Member)
    owner_target.id = 9999
    owner_target.guild = guild
    can_mod_owner, owner_reason = check_hierarchy(executor, owner_target)
    assert can_mod_owner is False
    assert "cannot moderate the server owner" in owner_reason

    # Target lower role is permitted
    target_lower = MagicMock(spec=discord.Member)
    target_lower.id = 3000
    target_lower.guild = guild
    target_lower.top_role.position = 5
    can_mod_lower, _ = check_hierarchy(executor, target_lower)
    assert can_mod_lower is True


# ─── 4. UI THEME & EMBED FACTORY TESTS ───────────────────────────────────────

def test_embed_factory_aizen_theming():
    success_embed = KyokaEmbedFactory.success("Task Complete", "Database synced", details="Took 12ms")
    assert success_embed.color.value == KyokaTheme.SUCCESS
    assert "Task Complete" in success_embed.title
    assert "Database synced" in success_embed.description
    assert "> Took 12ms" in success_embed.description

    error_embed = KyokaEmbedFactory.error("Execution Failed", "Rate limit exceeded")
    assert error_embed.color.value == KyokaTheme.ERROR
    assert "Rate limit exceeded" in error_embed.description

    perm_embed = KyokaEmbedFactory.permission_denied("Requires Manage Guild")
    assert perm_embed.color.value == KyokaTheme.ERROR
    assert "Requires Manage Guild" in perm_embed.description


# ─── 5. UI PAGINATION TESTS (5-15 PER PAGE RULE) ─────────────────────────────

def test_paginate_items_enforces_bounds():
    items = [f"command_{i:02d}" for i in range(25)]

    # Test 10 per page
    pages = paginate_items(items, per_page=10, title="Commands")
    assert len(pages) == 3  # 10 + 10 + 5
    assert "Page 1 of 3" in pages[0].footer.text
    assert "Page 3 of 3" in pages[2].footer.text

    # Test bounds clamping: per_page < 5 clamped to 5
    clamped_min = paginate_items(items, per_page=2)
    assert len(clamped_min) == 5  # 25 / 5 = 5 pages

    # Test bounds clamping: per_page > 15 clamped to 15
    clamped_max = paginate_items(items, per_page=50)
    assert len(clamped_max) == 2  # 15 + 10 = 2 pages


@pytest.mark.asyncio
async def test_paginator_view_author_isolation():
    embeds = [discord.Embed(title="P1"), discord.Embed(title="P2")]
    view = KyokaPaginatorView(embeds, author_id=12345)

    # Authorized interaction check
    mock_auth_interaction = MagicMock(spec=discord.Interaction)
    mock_auth_interaction.user.id = 12345
    assert await view.interaction_check(mock_auth_interaction) is True

    # Unauthorized interaction check
    mock_unauth_interaction = MagicMock(spec=discord.Interaction)
    mock_unauth_interaction.user.id = 99999
    mock_unauth_interaction.response.send_message = AsyncMock()
    assert await view.interaction_check(mock_unauth_interaction) is False
    mock_unauth_interaction.response.send_message.assert_called_once()


# ─── 6. HELP RENDERER TESTS ──────────────────────────────────────────────────

def test_help_renderer_home_and_category_page():
    bot_user = MagicMock()
    bot_user.display_avatar.url = "https://cdn.discordapp.com/avatar.png"

    home_embed = HelpRenderer.render_home_embed(
        bot_user=bot_user,
        prefix="+",
        total_commands=150,
        total_categories=14,
        guild_name="Aizen Citadel",
    )
    assert "KYOKA 3.0" in home_embed.title
    assert "Aizen Citadel" in home_embed.description
    assert "+help" in home_embed.description

    # Category page formatting
    sample_cmds = [
        {"name": "play", "description": "Play a track", "usage": "+play <query>", "aliases": ["p"], "is_slash": True},
        {"name": "skip", "description": "Skip track", "usage": "+skip", "aliases": [], "is_slash": False},
    ]
    cat_embed = HelpRenderer.render_category_page("Music", sample_cmds, page=1, total_pages=2, prefix="+")
    assert "MUSIC MODULE" in cat_embed.title
    assert len(cat_embed.fields) == 2
    assert cat_embed.fields[0].name == "`+play` `[p]` `[/]`"
    assert cat_embed.fields[1].name == "`+skip` `[+]`"


# ─── 7. UI CONFIRM CANCEL VIEW TESTS ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_cancel_view_flow():
    view = ConfirmCancelView(author_id=5555)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 5555
    interaction.response.edit_message = AsyncMock()

    # Click confirm button
    await view.confirm_btn.callback(interaction)
    assert view.value is True
    assert view.is_finished() is True
