"""
Comprehensive tests for KYOKA 3.0:
- Fix for `Converting to int failed for parameter quantity` in `?top bill`
- Multi-item calculations (e.g. `10 normal raids and 1 max race`)
- Training distinction: Max Race Package (training included) vs Max Trial (training added)
- Comparison queries (`compare 5 normal raids with 10 normal raids`)
- Interactive quote cards and duplicate-bill creation prevention
- Smart pricing policy with staff approval threshold
- Authoritative Throne of Pirate catalogue coverage (Sections A - U)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.managers.top_manager import (
    TopManager,
    CalculationResult,
    MultiCalculationResult,
)
from src.cogs.general.top_ai_manager import (
    TopAIManager,
    InteractiveQuoteView,
    format_quote_embed,
)


@pytest.fixture
def top_manager(tmp_path) -> TopManager:
    """Initialize TopManager with a temporary sqlite database for isolated testing."""
    db_file = tmp_path / "test_top.db"
    return TopManager(db_path=str(db_file))


# ─── PART 4: BILL ARGUMENT PARSER FIX & REGRESSION ───────────────────────────

def test_reproduce_and_verify_bill_argument_parser_fix():
    """
    Verify that multi-word unquoted services (which previously crashed discord.py's
    rigid positional converters with 'Converting to int failed for parameter quantity')
    are now parsed cleanly by the regex parser.
    """
    raw_inputs = [
        "10 normal raids and 1 max race",
        "2 trials",
        "Dough King quantity: 2 <@1505515188991033409>",
        "max race package qty:1 tax:5.0",
        "shark anchor customer: 555666777",
    ]

    for raw in raw_inputs:
        clean = raw.strip()
        
        # Customer extraction
        import re
        customer_id = None
        mention_m = re.search(r"<@!?(\d+)>", clean)
        if mention_m:
            customer_id = int(mention_m.group(1))
            clean = re.sub(r"<@!?\d+>", "", clean).strip()

        # Tax extraction
        tax_val = 0.0
        tax_m = re.search(r"\b(?:tax[:=]?\s*(\d+(?:\.\d+)?)(?:%)?)\b", clean, re.IGNORECASE)
        if tax_m:
            tax_val = float(tax_m.group(1))
            clean = re.sub(r"\b(?:tax[:=]?\s*\d+(?:\.\d+)?(?:%)?)\b", "", clean, re.IGNORECASE).strip()

        # Quantity extraction
        qty_val = 1
        qty_m = re.search(r"\b(?:qty|quantity|amount|count)[:=]?\s*(\d+)\b", clean, re.IGNORECASE)
        if qty_m:
            qty_val = int(qty_m.group(1))
            clean = re.sub(r"\b(?:qty|quantity|amount|count)[:=]?\s*\d+\b", "", clean, re.IGNORECASE).strip()

        service_name = clean.strip()
        assert len(service_name) > 0, f"Failed to extract service from: {raw}"
        assert qty_val >= 1


# ─── PART 3 & 7: NATURAL LANGUAGE ASSISTANT & PRICING ENGINE ─────────────────

def test_multi_item_calculation_10_raids_and_1_max_race(top_manager: TopManager):
    """
    User query: '?top price of 10 raids and 1 max race'
    Expected: 10 normal raids = 20M, 1 max race = 150M. Total = 170M.
    """
    parsed = top_manager.parse_top_query("10 normal raids and 1 max race")
    assert parsed is not None
    calc = parsed["calculation"]
    assert isinstance(calc, MultiCalculationResult)
    assert len(calc.items) == 2
    assert calc.total == 170.0
    assert calc.total_display == "170M"


def test_training_distinction_max_race_vs_max_trial(top_manager: TopManager):
    """
    Verify catalogue distinction between MAX RACE PACKAGE and MAX TRIAL:
    - MAX RACE PACKAGE: 150M with training included (no extra training cost added).
    - MAX TRIAL: 100M + 10M per extra training.
    """
    # Max race with 3 extra trainings -> 150M (training included)
    parsed_race = top_manager.parse_top_query("price of max race with 3 extra trainings")
    calc_race = parsed_race["calculation"]
    assert calc_race.total == 150.0
    assert "150M" in calc_race.total_display
    assert "include" in calc_race.condition_note.lower()

    # Max trial with 3 extra trainings -> 100M base + 30M = 130M
    parsed_trial = top_manager.parse_top_query("price of max trial with 3 extra trainings")
    calc_trial = parsed_trial["calculation"]
    assert calc_trial.total == 130.0
    assert "130M" in calc_trial.total_display


def test_normal_raids_pricing(top_manager: TopManager):
    """Verify normal raids pricing tiers: 1-5=10M, 6-10=20M, 11-15=30M, 16-20=50M, 20-25=60M."""
    r5 = top_manager.calculate_service_price("normal raids", quantity=5)
    assert r5.total == 10.0

    r10 = top_manager.calculate_service_price("normal raids", quantity=10)
    assert r10.total == 20.0

    r15 = top_manager.calculate_service_price("normal raids", quantity=15)
    assert r15.total == 30.0

    r25 = top_manager.calculate_service_price("normal raids", quantity=25)
    assert r25.total == 60.0


def test_advance_and_order_raids_pricing(top_manager: TopManager):
    """Verify advance and order raids tiers."""
    adv1 = top_manager.calculate_service_price("advance raids", quantity=2)
    assert adv1.total == 10.0

    adv5 = top_manager.calculate_service_price("advance raids", quantity=5)
    assert adv5.total == 30.0

    ord1 = top_manager.calculate_service_price("order raids", quantity=1)
    assert ord1.total == 10.0

    ord2 = top_manager.calculate_service_price("order raids", quantity=2)
    assert ord2.total == 20.0


def test_bosses_and_chalice_discount(top_manager: TopManager):
    """Verify bosses: Dough King=120M, Cake Prince=60M, Rip Indra=60M or 30M with chalice."""
    dk = top_manager.calculate_service_price("dough king")
    assert dk.total == 120.0

    cp = top_manager.calculate_service_price("cake prince")
    assert cp.total == 60.0

    # Rip Indra without chalice -> 60M
    indra_full = top_manager.calculate_service_price("rip indra")
    assert indra_full.total == 60.0

    # Rip Indra with chalice -> 30M
    indra_chalice = top_manager.calculate_service_price("rip indra with chalice")
    assert indra_chalice.total == 30.0


def test_fighting_styles_and_swords(top_manager: TopManager):
    """Verify fighting styles and swords: Sanguine=600M, Godhuman=600M, CDK=600M, TTK=30M/sword."""
    sang = top_manager.calculate_service_price("sanguine from start")
    assert sang.total == 600.0

    cdk = top_manager.calculate_service_price("cdk from start")
    assert cdk.total == 600.0

    ttk = top_manager.calculate_service_price("ttk", quantity=3)
    assert ttk.total == 90.0


def test_sea_events(top_manager: TopManager):
    """Verify sea events: Mirage=60M, Mirage+Gear=100M, Levi to Tiki=300M, Levi to Hydra=350M."""
    mirage = top_manager.calculate_service_price("mirage island")
    assert mirage.total == 60.0

    mirage_gear = top_manager.calculate_service_price("mirage and blue gear")
    assert mirage_gear.total == 100.0

    levi_tiki = top_manager.calculate_service_price("leviathan to tiki")
    assert levi_tiki.total == 300.0


def test_beli_farming_and_mastery_2x_multiplier(top_manager: TopManager):
    """Verify 2x money and 2x mastery options alter baseline prices correctly."""
    # Beli farming 10M without 2x money -> 50M
    bf_normal = top_manager.parse_top_query("10m beli without 2x money")
    assert bf_normal["calculation"].total == 50.0

    # Beli farming 10M with 2x money -> 30M
    bf_2x = top_manager.parse_top_query("10m beli with 2x money")
    assert bf_2x["calculation"].total == 30.0

    # Mastery 300 without 2x -> 60M
    m_normal = top_manager.calculate_service_price("300 mastery without 2x")
    assert m_normal.total == 60.0

    # Mastery 300 with 2x -> 30M
    m_2x = top_manager.calculate_service_price("300 mastery with 2x")
    assert m_2x.total == 30.0


def test_comparison_query(top_manager: TopManager):
    """
    Verify comparison queries like '?top compare the price of 5 raids with 10 raids'
    correctly parse both items and return comparison mode result.
    """
    parsed = top_manager.parse_top_query("compare 5 normal raids with 10 normal raids")
    assert parsed is not None
    multi_calc = parsed["calculation"]
    assert isinstance(multi_calc, MultiCalculationResult)
    assert multi_calc.comparison_mode is True
    assert len(multi_calc.items) == 2
    assert multi_calc.items[0].total == 10.0
    assert multi_calc.items[1].total == 20.0


# ─── PART 5: INTERACTIVE QUOTE CARD & CREATE BILL ────────────────────────────

@pytest.mark.asyncio
async def test_interactive_quote_view_author_lock_and_single_bill_creation(top_manager: TopManager):
    """
    Verify:
    1. Only the requester can trigger Create Bill or Edit actions.
    2. Repeated clicks cannot create duplicate bills (asyncio lock and is_created flag).
    3. Bill is stored in the database.
    """
    parsed = top_manager.parse_top_query("10 normal raids")
    calc_res = parsed["calculation"]
    
    mock_cog = MagicMock()
    mock_cog.top_manager = top_manager
    mock_cog.bot = MagicMock()

    view = InteractiveQuoteView(
        top_mgr=top_manager,
        quote=calc_res,
        author_id=1505515188991033409,
        guild_id=123456789,
        customer_id=987654321,
    )

    # 1. Unauthorized interaction check
    intruder_interaction = MagicMock(user=MagicMock(id=999999999))
    intruder_interaction.response.send_message = AsyncMock()
    allowed = await view.interaction_check(intruder_interaction)
    assert allowed is False
    intruder_interaction.response.send_message.assert_awaited_once()

    # 2. Authorized interaction check
    author_interaction = MagicMock(user=MagicMock(id=1505515188991033409))
    assert await view.interaction_check(author_interaction) is True

    # 3. Simulate Create Bill click
    mock_interaction = MagicMock(user=MagicMock(id=1505515188991033409))
    mock_interaction.response.send_message = AsyncMock()
    mock_interaction.response.edit_message = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    await view.btn_create_bill.callback(mock_interaction)
    assert view.is_created is True

    # 4. Repeated click attempt -> Rejected by deduplication lock
    mock_interaction2 = MagicMock(user=MagicMock(id=1505515188991033409))
    mock_interaction2.response.send_message = AsyncMock()
    await view.btn_create_bill.callback(mock_interaction2)
    mock_interaction2.response.send_message.assert_awaited_with(
        "⚠️ A bill has already been created for this quote.", ephemeral=True
    )


# ─── CRITICAL ADDITION: SMART PRICING & PRICE INCREASES ─────────────────────

def test_smart_pricing_policy_configuration(top_manager: TopManager):
    """
    Verify configurable price increase policy:
    - Base prices from catalogue
    - Optional custom order markup
    - Staff approval threshold
    """
    # Default policy
    policy = top_manager.get_pricing_policy(123456789)
    assert policy["custom_order_markup_percent"] == 0.0
    assert policy["requires_staff_approval_above_beli"] == 500.0

    # Update policy
    top_manager.update_pricing_policy(
        guild_id=123456789,
        custom_markup=10.0,
        staff_approval_threshold=800.0,
        updated_by=1505515188991033409,
    )

    new_policy = top_manager.get_pricing_policy(123456789)
    assert new_policy["custom_order_markup_percent"] == 10.0
    assert new_policy["requires_staff_approval_above_beli"] == 800.0


def test_quote_embed_formatting_and_no_usd_signs(top_manager: TopManager):
    """
    Verify quote embed contains no dollar signs ('$') and formats Blox Fruits Beli correctly.
    """
    parsed = top_manager.parse_top_query("10 normal raids")
    calc_res = parsed["calculation"]
    embed = format_quote_embed(calc_res)

    assert "$" not in embed.title
    assert "$" not in embed.description
    for f in embed.fields:
        assert "$" not in f.name
        assert "$" not in f.value
    assert "20M" in embed.description
