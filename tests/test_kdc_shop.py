"""
Test Suite for KDC Shop, Stock Catalogue, Billing & Bot Auto-Delivery Engine.
Validates exact user pricing, currency conversions, invoice creation,
bot archive packaging, payment verification, and staff permissions.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
import pytest
import discord
from discord.ext import commands

from src.managers.kdc_shop_manager import KDCShopManager, ShopItem, ShopBill
from src.cogs.general.kdc_shop import KDCShop, is_kdc_staff, PRIMARY_OWNER_ID


@pytest.fixture
def temp_shop():
    """Create a temporary isolated KDCShopManager for testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "kdc_shop_test.sqlite3"
        bots_dir = tmp_path / "kdc_bots_test"
        mgr = KDCShopManager(db_path=db_path, bots_dir=bots_dir)
        yield mgr


def test_kdc_shop_exact_pricing_seed(temp_shop: KDCShopManager):
    """Verify that all products specified by the user are seeded with exact prices."""
    items = temp_shop.get_all_items(active_only=True)
    item_map = {it.id: it for it in items}

    # 1. Server Boosts
    assert "boost_2" in item_map
    assert item_map["boost_2"].price_inr == 200.0
    assert item_map["boost_2"].price_usd == 2.0

    assert "boost_4" in item_map
    assert item_map["boost_4"].price_inr == 380.0
    assert item_map["boost_4"].price_usd == 3.8

    assert "boost_8" in item_map
    assert item_map["boost_8"].price_inr == 720.0
    assert item_map["boost_8"].price_usd == 7.2

    assert "boost_10" in item_map
    assert item_map["boost_10"].price_inr == 850.0
    assert item_map["boost_10"].price_usd == 8.5

    assert "boost_14" in item_map
    assert item_map["boost_14"].price_inr == 1150.0
    assert item_map["boost_14"].price_usd == 11.5

    # 2. Discord Nitro Subscriptions
    assert "nitro_1m_2b" in item_map
    assert item_map["nitro_1m_2b"].price_inr == 250.0
    assert item_map["nitro_1m_2b"].price_usd == 2.5

    assert "nitro_3m" in item_map
    assert item_map["nitro_3m"].price_inr == 350.0
    assert item_map["nitro_3m"].price_usd == 3.5

    assert "nitro_1y" in item_map
    assert item_map["nitro_1y"].price_inr == 2200.0
    assert item_map["nitro_1y"].price_usd == 22.0

    # 3. Auto-Delivery Pre-Built Bots
    assert "bot_music" in item_map
    assert item_map["bot_music"].price_inr == 50.0
    assert item_map["bot_music"].price_usd == 0.5
    assert item_map["bot_music"].is_auto_deliver is True

    assert "bot_chat" in item_map
    assert item_map["bot_chat"].price_inr == 50.0
    assert item_map["bot_chat"].price_usd == 0.5
    assert item_map["bot_chat"].is_auto_deliver is True

    assert "bot_allinone" in item_map
    assert item_map["bot_allinone"].price_inr == 300.0
    assert item_map["bot_allinone"].price_usd == 3.0
    assert item_map["bot_allinone"].is_auto_deliver is True

    assert "bot_tickets" in item_map
    assert item_map["bot_tickets"].price_inr == 120.0
    assert item_map["bot_tickets"].price_usd == 1.2
    assert item_map["bot_tickets"].is_auto_deliver is True

    assert "bot_antinuke" in item_map
    assert item_map["bot_antinuke"].price_inr == 150.0
    assert item_map["bot_antinuke"].price_usd == 1.5
    assert item_map["bot_antinuke"].is_auto_deliver is True


def test_bot_zip_archives_generated_on_disk(temp_shop: KDCShopManager):
    """Verify that ready-to-run bot zip packages are physically generated in warehouse."""
    for bot_id in ["bot_music", "bot_chat", "bot_allinone", "bot_tickets", "bot_antinuke"]:
        file_path = temp_shop.get_bot_file_path(bot_id)
        assert file_path is not None, f"Bot archive for {bot_id} should exist"
        assert file_path.exists(), f"File {file_path} must exist on disk"
        assert file_path.stat().st_size > 50, f"Zip file {file_path} must have content"


def test_bill_invoice_creation_inr_and_usd(temp_shop: KDCShopManager):
    """Verify bill invoice creation, calculations, and status transitions."""
    # INR Invoice
    bill_inr = temp_shop.create_bill(
        guild_id=1515995663903752213,
        customer_id=123456789,
        customer_name="TestBuyer",
        item_id="boost_4",
        currency="INR",
        quantity=2,
    )
    assert bill_inr.id.startswith("KDC-")
    assert bill_inr.total == 380.0 * 2  # 760.0
    assert bill_inr.currency == "INR"
    assert bill_inr.status == "PENDING"

    # USD Invoice
    bill_usd = temp_shop.create_bill(
        guild_id=1515995663903752213,
        customer_id=123456789,
        customer_name="TestBuyer",
        item_id="bot_music",
        currency="USD",
        quantity=1,
    )
    assert bill_usd.total == 0.50
    assert bill_usd.currency == "USD"

    # Update status to PAID & verify
    updated = temp_shop.update_bill_status(
        bill_usd.id,
        status="PAID",
        transaction_id="TXN12345678",
        staff_id=PRIMARY_OWNER_ID,
        staff_notes="Auto-verified via scanner",
    )
    assert updated is not None
    assert updated.status == "PAID"
    assert updated.transaction_id == "TXN12345678"
    assert updated.staff_id == PRIMARY_OWNER_ID


def test_is_kdc_staff_recognizes_authoritative_owner():
    """Verify primary owner has instant elevated staff permissions."""
    assert is_kdc_staff(PRIMARY_OWNER_ID) is True
    # Random ID is not staff by default
    assert is_kdc_staff(999999999999) is False


@pytest.mark.asyncio
async def test_kdc_shop_cog_registration():
    """Verify KDCShop cog registers command and subcommands properly."""
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="+", intents=intents)
    cog = KDCShop(bot)
    await bot.add_cog(cog)

    cmd = bot.get_command("stock")
    assert cmd is not None
    assert "kdc" in cmd.aliases
    assert "shop" in cmd.aliases
    assert "store" in cmd.aliases
    assert "kdcshop" in cmd.aliases

    subcmds = [c.name for c in cmd.commands]
    assert "add" in subcmds
    assert "update" in subcmds
    assert "upload" in subcmds
    assert "deliver" in subcmds
    assert "verify" in subcmds
    assert "bills" in subcmds

    # Verify review commands
    review_cmd = bot.get_command("review")
    assert review_cmd is not None
    assert "addreview" in review_cmd.aliases

    reviews_cmd = bot.get_command("reviews")
    assert reviews_cmd is not None
    assert "ratings" in reviews_cmd.aliases


def test_kdc_shop_review_crud_and_rating_summary(temp_shop: KDCShopManager):
    """Verify customer review submission, aggregation, and rating statistics."""
    # 1. Verify default seed reviews are loaded
    seed_revs = temp_shop.get_reviews(limit=10)
    assert len(seed_revs) >= 5

    # 2. Add a new customer review
    new_rev = temp_shop.add_review(
        user_id=88888888,
        username="happy_customer",
        rating=5,
        comment="Incredible bot zip! Set up in under 60 seconds.",
        product="Basic Music Only Bot",
    )
    assert new_rev["id"].startswith("REV-")
    assert new_rev["rating"] == 5
    assert new_rev["username"] == "happy_customer"

    # 3. Verify it appears at the top of get_reviews
    latest = temp_shop.get_reviews(limit=1)[0]
    assert latest["id"] == new_rev["id"]
    assert latest["comment"] == "Incredible bot zip! Set up in under 60 seconds."

    # 4. Check rating summary
    summary = temp_shop.get_rating_summary()
    assert summary["total"] >= 6
    assert summary["average"] >= 4.5
    assert summary["stars_str"] == "⭐⭐⭐⭐⭐"

    # 5. Delete review
    deleted = temp_shop.delete_review(new_rev["id"])
    assert deleted is True
    # Verify removed
    rev_ids = [r["id"] for r in temp_shop.get_reviews(limit=20)]
    assert new_rev["id"] not in rev_ids

