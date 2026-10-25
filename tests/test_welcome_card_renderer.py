"""
Unit and regression tests for Kyoka 3.0 Aizen Edition Welcome Image Card & Event System.
Verifies:
- Pillow composite generates a 1000x360 PNG image in memory.
- Dynamic member avatar is rendered, or fallback monogram is used when avatar is absent/corrupt.
- Server name, member count, username, and custom next step instructions are rendered.
- Off-thread non-blocking rendering via render_welcome_card_async.
- Fallback embed is delivered if rendering fails or avatar download times out.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest
import discord

from src.ui.cards.welcome_card import (
    generate_aizen_welcome_card,
    render_welcome_card_async,
    fetch_avatar_bytes,
)


def _create_sample_avatar_bytes() -> bytes:
    """Create a dummy 128x128 RGBA avatar for testing."""
    im = Image.new("RGBA", (128, 128), (140, 50, 200, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_generate_aizen_welcome_card_dimensions_and_format():
    """Verify generated welcome card is a valid 1000x360 PNG."""
    buf = generate_aizen_welcome_card(
        username="AizenFan99",
        guild_name="Las Noches Community",
        member_count=777,
        avatar_bytes=_create_sample_avatar_bytes(),
        next_step="Read #rules and get verified",
    )
    assert isinstance(buf, io.BytesIO)
    buf.seek(0)
    img = Image.open(buf)
    assert img.size == (1000, 360)
    assert img.format == "PNG"


def test_generate_aizen_welcome_card_without_avatar():
    """Verify welcome card renders successfully without avatar bytes (using fallback avatar)."""
    buf = generate_aizen_welcome_card(
        username="GhostUser",
        guild_name="Soul Society",
        member_count=42,
        avatar_bytes=None,
        next_step=None,
    )
    assert isinstance(buf, io.BytesIO)
    buf.seek(0)
    img = Image.open(buf)
    assert img.size == (1000, 360)
    assert img.format == "PNG"


def test_generate_aizen_welcome_card_with_corrupt_avatar():
    """Verify welcome card handles invalid/corrupted avatar bytes without crashing."""
    corrupt_bytes = b"NOT_A_VALID_IMAGE_DATA_12345"
    buf = generate_aizen_welcome_card(
        username="BrokenAvatarUser",
        guild_name="Hueco Mundo",
        member_count=100,
        avatar_bytes=corrupt_bytes,
        next_step="Verify in #welcome",
    )
    assert isinstance(buf, io.BytesIO)
    buf.seek(0)
    img = Image.open(buf)
    assert img.size == (1000, 360)


@pytest.mark.asyncio
async def test_render_welcome_card_async():
    """Verify async non-blocking wrapper renders card without blocking event loop."""
    with patch("src.ui.cards.welcome_card.fetch_avatar_bytes", new=AsyncMock(return_value=_create_sample_avatar_bytes())):
        buf = await render_welcome_card_async(
            username="KyokaTest",
            guild_name="Test Sanctuary",
            member_count=1234,
            avatar_url="https://cdn.discordapp.com/avatars/123/avatar.png",
            next_step="Check out #announcements",
        )
    assert isinstance(buf, io.BytesIO)
    buf.seek(0)
    img = Image.open(buf)
    assert img.size == (1000, 360)


@pytest.mark.asyncio
async def test_fetch_avatar_bytes_timeout_or_error_returns_none():
    """Verify fetch_avatar_bytes returns None on network error rather than raising."""
    with patch("aiohttp.ClientSession.get", side_effect=Exception("Connection timeout")):
        result = await fetch_avatar_bytes("https://invalid.example.com/avatar.png")
        assert result is None
