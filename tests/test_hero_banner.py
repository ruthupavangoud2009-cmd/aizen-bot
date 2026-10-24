"""
Unit tests for Kyoka 3.0 Pillow Canvas Banner Generators.
Verifies:
- generate_kyoka_hero_banner returns valid PNG bytes with correct dimensions.
- generate_hca_banner returns valid PNG bytes with category customization.
- Banner generation handles long guild names and extreme latency without crashing.
"""

from __future__ import annotations

import io
import pytest
from PIL import Image

from src.ui.cards.hero_banner import generate_kyoka_hero_banner
from src.ui.cards.hca_banner import generate_hca_banner

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def test_generate_kyoka_hero_banner_valid_png():
    """Verify hero banner generates valid PNG image bytes with expected dimensions."""
    raw_fp = generate_kyoka_hero_banner(
        bot_name="KYOKA 3.0",
        guild_name="Aizen Central",
        total_commands=148,
        latency_ms=42,
        prefix="+",
    )
    raw_bytes = raw_fp.getvalue()
    assert raw_bytes.startswith(PNG_HEADER)
    assert len(raw_bytes) > 5000

    raw_fp.seek(0)
    image = Image.open(raw_fp)
    assert image.format == "PNG"
    assert image.size == (900, 260)


def test_generate_kyoka_hero_banner_resilience():
    """Verify hero banner handles extreme inputs without exception."""
    raw_fp = generate_kyoka_hero_banner(
        bot_name="A" * 100,
        guild_name="Super Long Server Name That Exceeds Normal Margins " * 5,
        total_commands=9999,
        latency_ms=99999,
        prefix="superlongprefix+",
    )
    raw_bytes = raw_fp.getvalue()
    assert raw_bytes.startswith(PNG_HEADER)
    raw_fp.seek(0)
    image = Image.open(raw_fp)
    assert image.size == (900, 260)


def test_generate_hca_banner_valid_png():
    """Verify HCA directory banner generates valid PNG with custom category name."""
    raw_fp = generate_hca_banner(
        category_name="🎵・MUSIC",
        total_commands=18,
        prefix="+",
    )
    raw_bytes = raw_fp.getvalue()
    assert raw_bytes.startswith(PNG_HEADER)
    assert len(raw_bytes) > 5000

    raw_fp.seek(0)
    image = Image.open(raw_fp)
    assert image.format == "PNG"
    assert image.size == (900, 260)


def test_generate_hca_banner_master_index():
    """Verify HCA directory banner for master archive index."""
    raw_fp = generate_hca_banner(
        category_name="Archive Index",
        total_commands=150,
        prefix="+",
    )
    raw_bytes = raw_fp.getvalue()
    assert raw_bytes.startswith(PNG_HEADER)
    raw_fp.seek(0)
    image = Image.open(raw_fp)
    assert image.size == (900, 260)
