"""
Automated tests for Kyoka 3.0 — Sosuke Aizen Ultimate UI & Design System.
Verifies:
- AizenPalette and AizenSymbols design system tokens
- KyokaEmbed standardized factory methods (standard, success, error, warning, info, loading, denied)
- KyokaEmbed.progress_bar formatting
- KyokaPaginator multi-page navigation and security isolation
- HelpSearchModal & command search matching algorithm
- Configurable AizenAssets registry and fallbacks
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
import pytest
import discord
from discord.ext import commands

from src.utils.ui import AizenPalette, AizenSymbols, KyokaEmbed, KyokaPaginator
from src.core.config import Config, AizenAssets
from src.cogs.general.help import Help, HelpView, HelpSearchModal
from src.core.bot import KyokaBot


def test_aizen_palette_tokens():
    """Verify Aizen theme color tokens are valid 24-bit RGB integers."""
    assert AizenPalette.ROYAL_VIOLET == 0x7C3AED
    assert AizenPalette.CRIMSON == 0xFF3366
    assert AizenPalette.EMERALD_SUCCESS == 0x10B981
    assert AizenPalette.AMBER_WARN == 0xF59E0B
    assert AizenPalette.DEEP_PURPLE == 0x1A0933
    assert AizenPalette.VOID_BLACK == 0x0A0A0F


def test_aizen_symbols():
    """Verify key Aizen atmospheric symbols exist."""
    assert AizenSymbols.GATEWAY == "⛩️"
    assert AizenSymbols.BLADE == "⚔️"
    assert AizenSymbols.CROWN == "👑"
    assert AizenSymbols.SEARCH == "🔍"
    assert AizenSymbols.BAR_FULL == "▰"
    assert AizenSymbols.BAR_EMPTY == "▱"


def test_kyoka_embed_factories():
    """Verify KyokaEmbed factory methods generate properly formatted Discord embeds."""
    # Standard
    std = KyokaEmbed.standard("Control", "Chaos into order")
    assert "⛩️ Control" in std.title
    assert "Chaos into order" in std.description
    assert std.color.value == AizenPalette.ROYAL_VIOLET

    # Success
    succ = KyokaEmbed.success("Operation Complete", "Server configured.")
    assert "✅ Operation Complete" in succ.title
    assert succ.color.value == AizenPalette.EMERALD_SUCCESS

    # Error
    err = KyokaEmbed.error("Command Failed", "Rate limit hit.", suggestion="Cool down for 10s")
    assert "❌ Command Failed" in err.title
    assert "Rate limit hit." in err.description
    assert "Cool down for 10s" in err.description
    assert err.color.value == AizenPalette.CRIMSON

    # Warning
    warn = KyokaEmbed.warning("Elevated Permissions", "Be careful.")
    assert "⚠️ Elevated Permissions" in warn.title
    assert warn.color.value == AizenPalette.AMBER_WARN

    # Info
    inf = KyokaEmbed.info("Cluster Telemetry", "Latency: 25ms")
    assert "🔮 Cluster Telemetry" in inf.title
    assert inf.color.value == AizenPalette.INDIGO_INFO

    # Loading
    load = KyokaEmbed.loading("Consulting Hogyoku")
    assert "✨ Consulting Hogyoku" in load.title

    # Denied
    den = KyokaEmbed.denied("You are not authorized.")
    assert "🔒 Access Restricted" in den.title
    assert "Admiration is the furthest thing from understanding" in den.description


def test_kyoka_embed_progress_bar():
    """Verify sleek Unicode progress bar calculations."""
    bar_50 = KyokaEmbed.progress_bar(50, 100, length=10)
    assert "▰▰▰▰▰▱▱▱▱▱" in bar_50
    assert "50.0%" in bar_50

    bar_100 = KyokaEmbed.progress_bar(100, 100, length=10)
    assert "▰▰▰▰▰▰▰▰▰▰" in bar_100
    assert "100.0%" in bar_100

    bar_0 = KyokaEmbed.progress_bar(0, 100, length=10)
    assert "▱▱▱▱▱▱▱▱▱▱" in bar_0
    assert "0.0%" in bar_0


@pytest.mark.asyncio
async def test_kyoka_paginator_navigation():
    """Verify KyokaPaginator cycles through embeds and enforces author checks."""
    embed1 = KyokaEmbed.standard("Page 1", "Content 1")
    embed2 = KyokaEmbed.standard("Page 2", "Content 2")
    embed3 = KyokaEmbed.standard("Page 3", "Content 3")

    author_id = 123456789
    paginator = KyokaPaginator([embed1, embed2, embed3], author_id)

    assert paginator.current_page == 0
    assert paginator.total_pages == 3
    assert paginator.first_button.disabled is True
    assert paginator.prev_button.disabled is True
    assert paginator.next_button.disabled is False

    mock_interaction = MagicMock()
    mock_interaction.response.edit_message = AsyncMock()

    # Next
    await paginator.next_button.callback(mock_interaction)
    assert paginator.current_page == 1
    assert paginator.prev_button.disabled is False

    # Last
    await paginator.last_button.callback(mock_interaction)
    assert paginator.current_page == 2
    assert paginator.next_button.disabled is True

    # Prev
    await paginator.prev_button.callback(mock_interaction)
    assert paginator.current_page == 1

    # First
    await paginator.first_button.callback(mock_interaction)
    assert paginator.current_page == 0

    # Interaction security check
    mock_author_interaction = MagicMock(user=MagicMock(id=author_id))
    assert await paginator.interaction_check(mock_author_interaction) is True

    mock_intruder_interaction = MagicMock(user=MagicMock(id=999999999))
    mock_intruder_interaction.response.send_message = AsyncMock()
    assert await paginator.interaction_check(mock_intruder_interaction) is False
    mock_intruder_interaction.response.send_message.assert_awaited_once()


def test_help_search_results_embed_matching():
    """Verify command search matches by name, alias, and description with ranking."""
    bot = KyokaBot()
    bot._connection.user = MagicMock(id=999888777)
    bot._connection.application_id = 999888777
    help_cog = Help(bot)

    mock_ctx = MagicMock()
    mock_ctx.guild = MagicMock(id=111)
    mock_ctx.author = MagicMock(display_name="Tester", id=222)
    mock_ctx.author.display_avatar = MagicMock(url="https://example.com/av.png")

    cmd_ban = MagicMock(qualified_name="ban", description="Ban a member permanently.", aliases=["b"])
    cmd_timeout = MagicMock(qualified_name="timeout", description="Mute a member temporarily.", aliases=["mute"])
    cmd_ai = MagicMock(qualified_name="ai", description="Talk to Sosuke Aizen AI companion.", aliases=["ask"])

    visible = {
        "🛡️・MODERATION": [cmd_ban, cmd_timeout],
        "🤖・ARTIFICIAL INTELLIGENCE": [cmd_ai],
    }

    # Match exact
    embed = help_cog.build_search_results_embed(mock_ctx, visible, "ban")
    assert "Search Results for: `ban`" in embed.title
    assert "Found **1**" in embed.description
    assert "ban" in embed.fields[0].name

    # Match alias
    embed_alias = help_cog.build_search_results_embed(mock_ctx, visible, "mute")
    assert "Found **1**" in embed_alias.description
    assert "timeout" in embed_alias.fields[0].name

    # Match description keyword
    embed_desc = help_cog.build_search_results_embed(mock_ctx, visible, "permanently")
    assert "Found **1**" in embed_desc.description
    assert "ban" in embed_desc.fields[0].name

    # No match
    embed_none = help_cog.build_search_results_embed(mock_ctx, visible, "nonexistent_xyz")
    assert "No accessible commands matching" in embed_none.description
    assert embed_none.color.value == 0xED4245


def test_aizen_assets_configuration():
    """Verify AizenAssets registry loads properly with safe defaults."""
    assets = Config.ASSETS
    assert isinstance(assets, AizenAssets)
    assert hasattr(assets, "BANNER_URL")
    assert hasattr(assets, "HELP_GIF_URL")
    assert hasattr(assets, "WELCOME_IMAGE_URL")
    assert hasattr(assets, "LEVELUP_IMAGE_URL")
    assert hasattr(assets, "DEFAULT_THUMBNAIL_URL")
    assert hasattr(assets, "AIZEN_AVATAR_URL")
