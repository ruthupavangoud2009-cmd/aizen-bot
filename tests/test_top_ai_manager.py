"""
Kyoka 3.0 - Comprehensive Test Suite for Top AI Manager, Pricing, Bills & Staff Applications.
Verifies all 18 official price categories, trial package math, decimal-safe tax arithmetic,
natural-language intent parsing, persistent billing ledger, message ID payment confirmation,
financial accounting boundaries, price management, and Appy-style staff recruitment workflows.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
import pytest

from src.managers.top_manager import TopManager, CalculationResult


@pytest.fixture
def temp_top_mgr():
    """Create an isolated temporary TopManager instance with clean test database."""
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test_billing.sqlite3"
    mgr = TopManager(db_path=db_file)
    yield mgr
    shutil.rmtree(temp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. TEST EVERY OFFICIAL PRICE CATEGORY AND LISTED PRICES
# ─────────────────────────────────────────────────────────────────────────────

def test_price_catalogue_initial_seed_integrity(temp_top_mgr: TopManager):
    """Verify all 18 price categories exist with official amounts in catalogue."""
    prices = temp_top_mgr.get_all_prices()
    assert len(prices) >= 80, f"Expected at least 80 seeded prices, got {len(prices)}"

    # Check key categories are present
    categories = {p.category for p in prices}
    expected_categories = {
        "Trials", "Normal Raids", "Advance Raids", "Order Raids", "Races",
        "Draco", "Sea Events", "Bosses", "Fighting Styles", "Swords", "Guns",
        "Beli Farming", "Levels", "Admin Panel", "Titles", "Accessories",
        "Mastery", "Gun Mastery"
    }
    assert expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}"


def test_trials_pricing_and_packages(temp_top_mgr: TopManager):
    """Verify Trials: 1 trial (20M), 2 (40M), 3 (60M), Max trial (100M; training not included),
    Each training (+10M), Max Race Package (150M; training included), Draco trials (100M each).
    """
    assert temp_top_mgr.calculate_service_price("1 trial").total == 20.0
    assert temp_top_mgr.calculate_service_price("2 trials").total == 40.0
    assert temp_top_mgr.calculate_service_price("3 trials").total == 60.0

    max_trial = temp_top_mgr.calculate_service_price("max trial")
    assert max_trial.total == 100.0
    assert "training not included" in max_trial.condition_note.lower()

    training = temp_top_mgr.calculate_service_price("training")
    assert training.total == 10.0

    max_pkg = temp_top_mgr.calculate_service_price("max race package")
    assert max_pkg.total == 150.0
    assert "training included" in max_pkg.condition_note.lower()

    draco_trial = temp_top_mgr.calculate_service_price("draco trials")
    assert draco_trial.total == 100.0


def test_normal_raids_ranges_and_custom_boundary(temp_top_mgr: TopManager):
    """Verify Normal Raids: 1-5 (10M), 6-10 (20M), 11-15 (30M), 16-20 (50M), 20-25 (60M), 25+ (custom)."""
    assert temp_top_mgr.calculate_service_price("normal raids", quantity=3).total == 10.0
    assert temp_top_mgr.calculate_service_price("normal raids", quantity=8).total == 20.0
    assert temp_top_mgr.calculate_service_price("normal raids", quantity=14).total == 30.0
    assert temp_top_mgr.calculate_service_price("normal raids", quantity=18).total == 50.0
    assert temp_top_mgr.calculate_service_price("normal raids", quantity=23).total == 60.0

    # Overlap at 20 is flagged with boundary note
    res_20 = temp_top_mgr.calculate_service_price("normal raids", quantity=20)
    assert res_20.total in (50.0, 60.0)
    assert res_20.ambiguity_note != "", "Expected overlap note at boundary 20"

    # 25+ requires custom quote
    res_26 = temp_top_mgr.calculate_service_price("normal raids", quantity=30)
    assert res_26.custom_quote is True
    assert res_26.total_display == "Custom Quote"


def test_advance_raids_and_order_raids(temp_top_mgr: TopManager):
    """Verify Advance Raids (1-2: 10M, 3-4: 20M, 5: 30M, 6-8: 60M) and
    Order Raids (1: 10M, 2: 20M, 3-5: 60M, 6-8: 120M, 8-10: 150M, 10+: custom).
    """
    # Advance Raids
    assert temp_top_mgr.calculate_service_price("advance raid", quantity=2).total == 10.0
    assert temp_top_mgr.calculate_service_price("advance raid", quantity=4).total == 20.0
    assert temp_top_mgr.calculate_service_price("advance raid", quantity=5).total == 30.0
    assert temp_top_mgr.calculate_service_price("advance raid", quantity=7).total == 60.0

    # Order Raids
    assert temp_top_mgr.calculate_service_price("order raid", quantity=1).total == 10.0
    assert temp_top_mgr.calculate_service_price("order raid", quantity=2).total == 20.0
    assert temp_top_mgr.calculate_service_price("order raid", quantity=4).total == 60.0
    assert temp_top_mgr.calculate_service_price("order raid", quantity=7).total == 120.0
    assert temp_top_mgr.calculate_service_price("order raid", quantity=9).total == 150.0
    assert temp_top_mgr.calculate_service_price("order raid", quantity=15).custom_quote is True


def test_races_and_ghoul_dough_condition(temp_top_mgr: TopManager):
    """Verify Races: V1 Cyborg (100M), V1 Ghoul (100M), V2 Every race (20M),
    V3 Every race (10M), Ghoul V3 condition (Dough fruit required).
    """
    assert temp_top_mgr.calculate_service_price("cyborg v1").total == 100.0
    assert temp_top_mgr.calculate_service_price("ghoul v1").total == 100.0
    assert temp_top_mgr.calculate_service_price("every race v2").total == 20.0
    assert temp_top_mgr.calculate_service_price("every race v3").total == 10.0

    ghoul_v3 = temp_top_mgr.calculate_service_price("ghoul v3")
    assert "dough" in ghoul_v3.condition_note.lower()


def test_draco_and_sea_events(temp_top_mgr: TopManager):
    """Verify Draco: V1 (150M), V2 (20M), V3 (30M), V4 (600M), Max V4 (1.2B).
    Verify Sea Events: Mirage (60M), Mirage+Gear (100M), Prehistoric (30M/60M),
    Levi to Tiki (300M), Levi to Hydra (350M), Kitsune Shrine (30M).
    """
    assert temp_top_mgr.calculate_service_price("draco v1").total == 150.0
    assert temp_top_mgr.calculate_service_price("draco v2").total == 20.0
    assert temp_top_mgr.calculate_service_price("draco v3").total == 30.0
    assert temp_top_mgr.calculate_service_price("draco v4").total == 600.0
    assert temp_top_mgr.calculate_service_price("max draco v4").total == 1200.0
    assert temp_top_mgr.calculate_service_price("max draco v4").total_display == "1.2B"

    # Sea Events
    assert temp_top_mgr.calculate_service_price("mirage island").total == 60.0
    assert temp_top_mgr.calculate_service_price("mirage + blue gear").total == 100.0
    assert temp_top_mgr.calculate_service_price("prehistoric island not carry").total == 30.0
    assert temp_top_mgr.calculate_service_price("prehistoric island carry").total == 60.0
    assert temp_top_mgr.calculate_service_price("leviathan to tiki").total == 300.0
    assert temp_top_mgr.calculate_service_price("leviathan to hydra").total == 350.0
    assert temp_top_mgr.calculate_service_price("kitsune shrine").total == 30.0


def test_bosses_with_and_without_chalice(temp_top_mgr: TopManager):
    """Verify Bosses: Dough King (120M), Cake Prince (60M), Soul Reaper (40M),
    Rip_Indra (60M normally, 30M with customer chalice), Dark Beard (60M).
    """
    assert temp_top_mgr.calculate_service_price("dough king").total == 120.0
    assert temp_top_mgr.calculate_service_price("cake prince").total == 60.0
    assert temp_top_mgr.calculate_service_price("soul reaper").total == 40.0
    assert temp_top_mgr.calculate_service_price("dark beard").total == 60.0

    # Normal Rip Indra
    assert temp_top_mgr.calculate_service_price("rip indra").total == 60.0

    # Rip Indra with customer chalice
    assert temp_top_mgr.calculate_service_price("rip indra", with_chalice=True).total == 30.0
    assert temp_top_mgr.calculate_service_price("rip indra with chalice").total == 30.0


def test_fighting_styles_swords_guns(temp_top_mgr: TopManager):
    """Verify Fighting Styles, Swords, and Guns."""
    # Fighting styles
    assert temp_top_mgr.calculate_service_price("sanguine art").total == 600.0
    assert temp_top_mgr.calculate_service_price("godhuman").total == 600.0
    assert temp_top_mgr.calculate_service_price("dragon talon").total == 90.0
    assert temp_top_mgr.calculate_service_price("electric claw").total == 60.0
    assert temp_top_mgr.calculate_service_price("death step").total == 60.0

    # Swords
    assert temp_top_mgr.calculate_service_price("cdk").total == 600.0
    assert temp_top_mgr.calculate_service_price("ttk").total == 30.0
    assert temp_top_mgr.calculate_service_price("dragonheart").total == 150.0
    assert temp_top_mgr.calculate_service_price("shark anchor").total == 60.0
    assert temp_top_mgr.calculate_service_price("hollow scythe").total == 150.0
    assert temp_top_mgr.calculate_service_price("dark dagger").total == 600.0
    assert temp_top_mgr.calculate_service_price("fox lamp").total == 150.0
    assert temp_top_mgr.calculate_service_price("tushita").total == 90.0
    assert temp_top_mgr.calculate_service_price("yama").total == 30.0
    assert temp_top_mgr.calculate_service_price("tushita scroll").total == 20.0
    assert temp_top_mgr.calculate_service_price("yama scroll").total == 30.0

    # Guns
    assert temp_top_mgr.calculate_service_price("dragonstorm").total == 150.0
    assert temp_top_mgr.calculate_service_price("skull guitar").total == 60.0


def test_beli_farming_distinction_2x_money(temp_top_mgr: TopManager):
    """Verify Beli Farming without 2x vs with 2x money and missing 25M tier in 2x."""
    # Without 2x Money
    assert temp_top_mgr.calculate_service_price("5m beli without 2x").total == 30.0
    assert temp_top_mgr.calculate_service_price("10m beli without 2x").total == 50.0
    assert temp_top_mgr.calculate_service_price("15m beli without 2x").total == 80.0
    assert temp_top_mgr.calculate_service_price("20m beli without 2x").total == 150.0
    assert temp_top_mgr.calculate_service_price("25m beli without 2x").total == 350.0
    assert temp_top_mgr.calculate_service_price("30m+ beli without 2x").custom_quote is True

    # With 2x Money
    assert temp_top_mgr.calculate_service_price("5m beli with 2x").total == 20.0
    assert temp_top_mgr.calculate_service_price("10m beli with 2x").total == 30.0
    assert temp_top_mgr.calculate_service_price("15m beli with 2x").total == 40.0
    assert temp_top_mgr.calculate_service_price("20m beli with 2x").total == 80.0
    assert temp_top_mgr.calculate_service_price("30m beli with 2x").total == 150.0
    assert temp_top_mgr.calculate_service_price("30m+ beli with 2x").custom_quote is True


def test_levels_admin_panel_titles_accessories_mastery(temp_top_mgr: TopManager):
    """Verify Levels, Admin Panel, Titles, Accessories, and Mastery tiers."""
    # Levels
    assert temp_top_mgr.calculate_service_price("level 100").total == 30.0
    assert temp_top_mgr.calculate_service_price("level 500").total == 120.0
    assert temp_top_mgr.calculate_service_price("level 1000").total == 400.0
    assert temp_top_mgr.calculate_service_price("max level").total == 1300.0

    # Admin Panel
    assert temp_top_mgr.calculate_service_price("gravity").total == 500.0
    assert temp_top_mgr.calculate_service_price("lightning").total == 600.0
    assert temp_top_mgr.calculate_service_price("control").total == 1200.0

    # Titles & Accessories
    assert temp_top_mgr.calculate_service_price("custom titles").custom_quote is True
    assert temp_top_mgr.calculate_service_price("raging demon").total == 300.0
    assert temp_top_mgr.calculate_service_price("levi shield").total == 1200.0
    assert temp_top_mgr.calculate_service_price("kit mask").total == 100.0
    assert temp_top_mgr.calculate_service_price("bandana").total == 20.0

    # Mastery
    assert temp_top_mgr.calculate_service_price("till 600 mastery without 2x").total == 120.0
    assert temp_top_mgr.calculate_service_price("till 600 mastery with 2x").total == 60.0
    assert temp_top_mgr.calculate_service_price("till 600 gun mastery without 2x").total == 150.0
    assert temp_top_mgr.calculate_service_price("till 600 gun mastery with 2x").total == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. TEST TAX CALCULATOR AND DECIMAL PRECISION
# ─────────────────────────────────────────────────────────────────────────────

def test_decimal_safe_tax_calculation(temp_top_mgr: TopManager):
    """Verify exact formula: Tax = subtotal * tax% / 100, Total = subtotal + tax."""
    # 2 trials: subtotal 40M, 5% tax -> tax 2M, total 42M
    tax_amt, total = temp_top_mgr.calculate_tax(subtotal=40.0, tax_percentage=5.0)
    assert tax_amt == 2.0
    assert total == 42.0

    # 3 trials: subtotal 60M, 10% tax -> tax 6M, total 66M
    tax_amt, total = temp_top_mgr.calculate_tax(subtotal=60.0, tax_percentage=10.0)
    assert tax_amt == 6.0
    assert total == 66.0

    # Fractional tax rate (7.5% on 40M) -> tax 3M, total 43M
    tax_amt, total = temp_top_mgr.calculate_tax(subtotal=40.0, tax_percentage=7.5)
    assert tax_amt == 3.0
    assert total == 43.0

    # Fractional subtotal with rounding: 35.5M with 7.5% tax -> tax 2.66M, total 38.16M
    tax_amt, total = temp_top_mgr.calculate_tax(subtotal=35.5, tax_percentage=7.5)
    assert tax_amt == 2.66
    assert total == 38.16

    # 0% tax produces zero tax
    tax_amt, total = temp_top_mgr.calculate_tax(subtotal=50.0, tax_percentage=0.0)
    assert tax_amt == 0.0
    assert total == 50.0

    # Validation: reject negative tax and excessive >100%
    with pytest.raises(ValueError):
        temp_top_mgr.calculate_tax(subtotal=50.0, tax_percentage=-5.0)
    with pytest.raises(ValueError):
        temp_top_mgr.calculate_tax(subtotal=50.0, tax_percentage=105.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. TEST NATURAL LANGUAGE INTENT PARSING
# ─────────────────────────────────────────────────────────────────────────────

def test_natural_language_queries(temp_top_mgr: TopManager):
    """Verify natural-language queries from prompt specifications."""
    # 1. "what's the price of 1 trial?"
    r1 = temp_top_mgr.parse_top_query("what's the price of 1 trial?")
    assert r1["intent"] == "price_lookup"
    assert r1["calculation"].total == 20.0

    # 2. "price of 2 trials"
    r2 = temp_top_mgr.parse_top_query("price of 2 trials")
    assert r2["calculation"].total == 40.0

    # 3. "what is the cost of 5 normal raids?"
    r3 = temp_top_mgr.parse_top_query("what is the cost of 5 normal raids?")
    assert r3["calculation"].total == 10.0

    # 4. "price of Draco V2"
    r4 = temp_top_mgr.parse_top_query("price of Draco V2")
    assert r4["calculation"].total == 20.0

    # 5. "how much is Dough King?"
    r5 = temp_top_mgr.parse_top_query("how much is Dough King?")
    assert r5["calculation"].total == 120.0

    # 6. "what's the price of 2 trials with 5% tax?"
    r6 = temp_top_mgr.parse_top_query("what's the price of 2 trials with 5% tax?")
    assert r6["calculation"].subtotal == 40.0
    assert r6["calculation"].tax_amount == 2.0
    assert r6["calculation"].total == 42.0

    # 7. "calculate 3 trials with 10% tax"
    r7 = temp_top_mgr.parse_top_query("calculate 3 trials with 10% tax")
    assert r7["calculation"].subtotal == 60.0
    assert r7["calculation"].tax_amount == 6.0
    assert r7["calculation"].total == 66.0

    # 8. "make a bill for 2 trials with 5% tax unpaid"
    r8 = temp_top_mgr.parse_top_query("make a bill for 2 trials with 5% tax unpaid")
    assert r8["intent"] == "make_bill"
    assert r8["calculation"].total == 42.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. TEST PERSISTENT BILLING LEDGER, STATUSES & AUDIT LOGS
# ─────────────────────────────────────────────────────────────────────────────

def test_bill_creation_and_persistence(temp_top_mgr: TopManager):
    """Verify bill creation generates unique ID, saves UNPAID status, and logs audit."""
    bill = temp_top_mgr.create_bill(
        guild_id=12345,
        creator_id=999,
        creator_name="StaffMember",
        service_name="2 trials",
        quantity=1,
        tax_rate=5.0,
        customer_id=111,
        customer_name="ClientUser",
    )

    assert bill["id"].startswith("TOP-")
    assert bill["status"] == "UNPAID"
    assert bill["subtotal"] == 40.0
    assert bill["tax_amount"] == 2.0
    assert bill["total"] == 42.0

    # Retrieve from DB
    retrieved = temp_top_mgr.get_bill(bill["id"])
    assert retrieved is not None
    assert retrieved["id"] == bill["id"]
    assert retrieved["status"] == "UNPAID"


def test_mark_bill_paid_with_discord_message_id(temp_top_mgr: TopManager):
    """Verify marking bill paid requires valid message ID, sets paid_at, and prevents double-pay."""
    bill = temp_top_mgr.create_bill(
        guild_id=12345,
        creator_id=999,
        creator_name="StaffMember",
        service_name="1 trial",
    )

    # Valid Discord message ID snowflake (18 digits)
    proof_msg_id = "123456789012345678"

    paid_bill = temp_top_mgr.mark_bill_paid(
        bill_id=bill["id"],
        staff_id=888,
        staff_name="SeniorStaff",
        message_id=proof_msg_id,
    )

    assert paid_bill["status"] == "PAID"
    assert paid_bill["paid_at"] is not None
    assert paid_bill["paid_by_id"] == 888
    assert paid_bill["payment_message_id"] == proof_msg_id

    # Searching by message ID locates this bill
    matches = temp_top_mgr.find_bill_by_message_id(proof_msg_id)
    assert len(matches) == 1
    assert matches[0]["id"] == bill["id"]

    # Prevents marking paid twice
    with pytest.raises(ValueError, match="already been marked as PAID"):
        temp_top_mgr.mark_bill_paid(
            bill_id=bill["id"],
            staff_id=888,
            staff_name="SeniorStaff",
            message_id="999999999999999999",
        )


def test_invalid_message_id_rejected(temp_top_mgr: TopManager):
    """Verify non-numeric or malformed message IDs are strictly rejected."""
    bill = temp_top_mgr.create_bill(
        guild_id=12345,
        creator_id=999,
        creator_name="StaffMember",
        service_name="1 trial",
    )

    with pytest.raises(ValueError, match="not a valid Discord message ID"):
        temp_top_mgr.mark_bill_paid(bill["id"], staff_id=888, staff_name="Staff", message_id="invalid_abc")

    with pytest.raises(ValueError, match="not a valid Discord message ID"):
        temp_top_mgr.mark_bill_paid(bill["id"], staff_id=888, staff_name="Staff", message_id="12345")  # Too short


def test_bill_cancellation_and_refund_lifecycle(temp_top_mgr: TopManager):
    """Verify cancellation of unpaid bills, refunding of paid bills, and state protections."""
    # 1. Cancellation of unpaid bill
    bill1 = temp_top_mgr.create_bill(guild_id=1, creator_id=1, creator_name="Staff", service_name="1 trial")
    cancelled = temp_top_mgr.cancel_bill(bill1["id"], staff_id=1, reason="Client changed mind")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancel_reason"] == "Client changed mind"

    # Cannot pay a cancelled bill
    with pytest.raises(ValueError, match="currently CANCELLED"):
        temp_top_mgr.mark_bill_paid(bill1["id"], staff_id=1, staff_name="Staff", message_id="123456789012345678")

    # 2. Refund of paid bill
    bill2 = temp_top_mgr.create_bill(guild_id=1, creator_id=1, creator_name="Staff", service_name="1 trial")
    temp_top_mgr.mark_bill_paid(bill2["id"], staff_id=1, staff_name="Staff", message_id="123456789012345678")

    refunded = temp_top_mgr.refund_bill(bill2["id"], staff_id=1, reason="Customer disconnected during raid")
    assert refunded["status"] == "REFUNDED"
    assert refunded["refund_reason"] == "Customer disconnected during raid"


# ─────────────────────────────────────────────────────────────────────────────
# 5. TEST FINANCIAL REPORTING & ACCOUNTING BOUNDARIES
# ─────────────────────────────────────────────────────────────────────────────

def test_financial_reporting_boundaries_and_net_revenue(temp_top_mgr: TopManager):
    """Verify that:
    1. Unpaid bills are excluded from received revenue.
    2. Cancelled bills are excluded from outstanding balance.
    3. Net revenue = received revenue - refunds.
    4. Payments count on paid_at date, not created_at date.
    """
    now = time.time()
    guild_id = 9999

    # Bill A: Created and PAID (40M)
    b_a = temp_top_mgr.create_bill(guild_id, creator_id=10, creator_name="Staff1", service_name="2 trials")
    temp_top_mgr.mark_bill_paid(b_a["id"], staff_id=10, staff_name="Staff1", message_id="111111111111111111")

    # Bill B: Created and UNPAID (20M)
    b_b = temp_top_mgr.create_bill(guild_id, creator_id=10, creator_name="Staff1", service_name="1 trial")

    # Bill C: Created and CANCELLED (60M)
    b_c = temp_top_mgr.create_bill(guild_id, creator_id=20, creator_name="Staff2", service_name="3 trials")
    temp_top_mgr.cancel_bill(b_c["id"], staff_id=20, reason="Client cancel")

    # Bill D: Created, PAID (20M), then REFUNDED
    b_d = temp_top_mgr.create_bill(guild_id, creator_id=20, creator_name="Staff2", service_name="1 trial")
    temp_top_mgr.mark_bill_paid(b_d["id"], staff_id=20, staff_name="Staff2", message_id="222222222222222222")
    temp_top_mgr.refund_bill(b_d["id"], staff_id=20, reason="Service dispute")

    report = temp_top_mgr.get_today_report(guild_id=guild_id)

    # 4 bills created
    assert report["created_count"] == 4
    assert report["created_total_value"] == 40.0 + 20.0 + 60.0 + 20.0  # 140M

    # 2 paid in period (Bill A 40M + Bill D 20M) = 60M received
    assert report["paid_count"] == 2
    assert report["received_revenue"] == 60.0

    # 1 refunded (Bill D 20M)
    assert report["refunded_count"] == 1
    assert report["refund_total"] == 20.0

    # Net revenue = 60M - 20M = 40M
    assert report["net_revenue"] == 40.0

    # Unpaid count = 1 (Bill B only, 20M). Cancelled bill C is NOT in unpaid!
    assert report["unpaid_count"] == 1
    assert report["outstanding_amount"] == 20.0


# ─────────────────────────────────────────────────────────────────────────────
# 6. TEST PRICE CATALOGUE MANAGEMENT (IMMUTABILITY OF PAST BILLS)
# ─────────────────────────────────────────────────────────────────────────────

def test_price_update_does_not_retroactively_change_past_bills(temp_top_mgr: TopManager):
    """Verify updating a catalogue price does not alter historical bills."""
    # 1. Create a bill at original price (1 trial = 20M)
    bill = temp_top_mgr.create_bill(guild_id=1, creator_id=1, creator_name="Staff", service_name="1 trial")
    assert bill["total"] == 20.0

    # 2. Update catalogue price for 1 trial from 20M to 25M
    temp_top_mgr.update_price("trial_1", new_price=25.0, staff_id=999, reason="Market adjustment")
    updated_item = temp_top_mgr.get_price("trial_1")
    assert updated_item.price_amount == 25.0
    assert updated_item.price_display == "25M"

    # 3. Verify old bill still retains original 20M price
    persisted_bill = temp_top_mgr.get_bill(bill["id"])
    assert persisted_bill["total"] == 20.0
    assert persisted_bill["subtotal"] == 20.0

    # 4. Verify audit history was recorded
    history = temp_top_mgr.get_price_history("trial_1")
    assert len(history) == 1
    assert history[0]["old_price"] == 20.0
    assert history[0]["new_price"] == 25.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. TEST APPY-STYLE STAFF APPLICATION SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def test_staff_application_submission_and_cooldown(temp_top_mgr: TopManager):
    """Verify application submission, duplicate blocking, and cooldown enforcement."""
    guild_id = 555
    applicant_id = 777

    answers = {
        "Timezone": "EST",
        "Experience": "2 years moderation",
        "Motivation": "Passionate about Kyoka",
    }

    # 1. Submit valid application
    app = temp_top_mgr.submit_application(
        guild_id=guild_id,
        applicant_id=applicant_id,
        applicant_name="Applicant#0001",
        position="Community Moderator",
        answers=answers,
    )
    assert app["id"].startswith("APP-")
    assert app["status"] == "PENDING"
    assert app["position"] == "Community Moderator"

    # 2. Duplicate submission blocked while pending
    with pytest.raises(ValueError, match="already have an active application"):
        temp_top_mgr.submit_application(
            guild_id=guild_id,
            applicant_id=applicant_id,
            applicant_name="Applicant#0001",
            position="Trial Staff",
            answers=answers,
        )


def test_staff_application_review_workflow(temp_top_mgr: TopManager):
    """Verify application review transitions: UNDER_REVIEW, ACCEPTED, and notes."""
    guild_id = 555
    applicant_id = 888

    app = temp_top_mgr.submit_application(
        guild_id=guild_id,
        applicant_id=applicant_id,
        applicant_name="Applicant#0002",
        position="Support & Billing Staff",
        answers={"Timezone": "PST"},
    )

    # 1. Mark under review
    under_review = temp_top_mgr.review_application(app["id"], reviewer_id=1, reviewer_name="Admin", new_status="UNDER_REVIEW")
    assert under_review["status"] == "UNDER_REVIEW"

    # 2. Add private staff note
    noted = temp_top_mgr.add_application_note(app["id"], staff_id=1, note="Good answers, scheduled interview.")
    assert "Good answers" in noted["staff_notes"]

    # 3. Accept application
    accepted = temp_top_mgr.review_application(app["id"], reviewer_id=1, reviewer_name="Admin", new_status="ACCEPTED", reason="Passed interview")
    assert accepted["status"] == "ACCEPTED"
    assert accepted["decision_reason"] == "Passed interview"
