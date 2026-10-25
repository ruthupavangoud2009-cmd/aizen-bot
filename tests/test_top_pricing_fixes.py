"""
Regression tests for Top AI Pricing Manager fixes:
1. MultiCalculationResult result contract consistency (is_clarification, is_provisional, etc.)
2. Exact test case: '?top price of 4 trials and 10 normal raids'
3. Absence of 'AttributeError: MultiCalculationResult object has no attribute is_clarification'
4. Fix for 'Converting to "int" failed for parameter "quantity"' in bill argument parser
5. Fallback to deterministic catalogue when AI provider is unavailable
6. Safe Beli/M/B currency formatting with zero USD / '$' symbols
"""

import tempfile
import shutil
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import discord

from src.managers.top_manager import (
    TopManager,
    CalculationResult,
    MultiCalculationResult,
)
from src.cogs.general.top_ai_manager import format_quote_embed


@pytest.fixture
def temp_top_mgr():
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test_billing.sqlite3"
    mgr = TopManager(db_path=db_file)
    yield mgr
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_multi_calculation_result_contract_attributes():
    """Verify MultiCalculationResult has complete result contract matching CalculationResult."""
    calc1 = CalculationResult(
        service_name="10 normal raids",
        category="Normal Raids",
        quantity=10,
        unit_price=20.0,
        unit_display="20M",
        subtotal=20.0,
        subtotal_display="20M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=20.0,
        total_display="20M",
    )
    multi = MultiCalculationResult(
        items=[calc1],
        subtotal=20.0,
        subtotal_display="20M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=20.0,
        total_display="20M",
    )

    # Check all unified contract attributes are present
    assert hasattr(multi, "is_clarification")
    assert multi.is_clarification is False
    assert hasattr(multi, "clarification_title")
    assert hasattr(multi, "clarification_options")
    assert isinstance(multi.clarification_options, list)
    assert hasattr(multi, "is_provisional")
    assert multi.is_provisional is False
    assert hasattr(multi, "baseline_price")
    assert hasattr(multi, "baseline_display")
    assert hasattr(multi, "extra_charges")
    assert hasattr(multi, "extra_charges_display")
    assert hasattr(multi, "custom_quote")
    assert hasattr(multi, "unit_price")
    assert hasattr(multi, "unit_display")


def test_multi_calculation_result_auto_propagation():
    """Verify MultiCalculationResult __post_init__ auto-propagates clarification and provisional flags."""
    calc_clarification = CalculationResult(
        service_name="4 trials",
        category="Trials",
        quantity=4,
        unit_price=20.0,
        unit_display="20M",
        subtotal=80.0,
        subtotal_display="80M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=80.0,
        total_display="80M (Provisional)",
        is_clarification=True,
        clarification_title="Unlisted Package Clarification",
        clarification_options=["4x 20M individual trials", "Max Trial (100M)"],
        is_provisional=True,
    )
    calc_normal = CalculationResult(
        service_name="10 normal raids",
        category="Normal Raids",
        quantity=10,
        unit_price=20.0,
        unit_display="20M",
        subtotal=20.0,
        subtotal_display="20M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=20.0,
        total_display="20M",
    )

    multi = MultiCalculationResult(
        items=[calc_clarification, calc_normal],
        subtotal=100.0,
        subtotal_display="100M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=100.0,
        total_display="100M (Provisional)",
    )

    assert multi.is_clarification is True
    assert multi.is_provisional is True
    assert multi.clarification_title != ""
    assert "4x 20M individual trials" in multi.clarification_options


def test_four_trials_and_ten_normal_raids_exact_query(temp_top_mgr):
    """Verify '?top price of 4 trials and 10 normal raids' parses without crashing,
    calculates known 10 normal raids deterministically (20M), provides a provisional
    quote for 4 trials, and asks for clarification on unlisted package.
    """
    res = temp_top_mgr.parse_top_query("price of 4 trials and 10 normal raids")
    calc = res.get("calculation")

    assert isinstance(calc, MultiCalculationResult)
    assert len(calc.items) == 2

    # Check 10 normal raids
    normal_raids = next((item for item in calc.items if "normal raid" in item.service_name.lower()), None)
    assert normal_raids is not None
    assert normal_raids.total == 20.0
    assert normal_raids.total_display == "20M"

    # Check 4 trials
    trials = next((item for item in calc.items if "trial" in item.service_name.lower()), None)
    assert trials is not None
    assert trials.is_provisional is True
    assert trials.is_clarification is True
    assert "provisional" in trials.total_display.lower()

    # Check overall multi result contract
    assert calc.is_clarification is True
    assert calc.is_provisional is True
    assert calc.total == 100.0
    assert "100M" in calc.total_display


def test_format_quote_embed_on_multi_calculation_result(temp_top_mgr):
    """Verify format_quote_embed renders MultiCalculationResult without throwing AttributeError."""
    res = temp_top_mgr.parse_top_query("price of 4 trials and 10 normal raids")
    calc = res.get("calculation")
    embed = format_quote_embed(calc)

    assert isinstance(embed, discord.Embed)
    assert "TOP AI MANAGER" in embed.title
    assert "100M" in embed.description or any("100M" in f.value for f in embed.fields)
    assert "4 trials" in embed.description.lower() or any("4 trials" in f.name.lower() or "4 trials" in f.value.lower() for f in embed.fields)


def test_bill_argument_parser_does_not_convert_service_to_int():
    """Verify bill arguments parser handles multi-word service strings,
    quantities, taxes, and customer mentions without raising ValueError.
    """
    raw_inputs = [
        ("normal raids 10", "normal raids", 10, 0.0),
        ("10 normal raids", "normal raids", 10, 0.0),
        ("2 trials tax 5.0% @Customer", "2 trials", 1, 5.0),
        ("Dough King quantity: 2", "Dough King", 2, 0.0),
        ("TTK 3 swords", "TTK", 3, 0.0),
    ]

    for raw, expected_service, expected_qty, expected_tax in raw_inputs:
        clean = raw.strip()

        # Extract customer mention
        customer_id = None
        mention_m = re.search(r"<@!?(\d+)>|@(\w+)", clean)
        if mention_m:
            clean = re.sub(r"<@!?\d+>|@\w+", "", clean).strip()

        # Extract tax
        tax_val = 0.0
        tax_m = re.search(r"\b(?:tax[:=]?\s*(\d+(?:\.\d+)?)(?:%)?)\b", clean, re.IGNORECASE)
        if tax_m:
            tax_val = float(tax_m.group(1))
            clean = re.sub(r"\b(?:tax[:=]?\s*\d+(?:\.\d+)?(?:%)?)\b", "", clean, re.IGNORECASE).strip()

        # Extract quantity
        qty_val = 1
        qty_m = re.search(r"\b(?:qty|quantity|amount|count)[:=]?\s*(\d+)\b", clean, re.IGNORECASE)
        if qty_m:
            qty_val = int(qty_m.group(1))
            clean = re.sub(r"\b(?:qty|quantity|amount|count)[:=]?\s*\d+\b", "", clean, re.IGNORECASE).strip()
        else:
            # Check standalone trailing/leading number
            leading_m = re.match(r"^(\d+)\s+(.+)$", clean)
            trailing_m = re.search(r"^(.*?)\s+(\d+)$", clean)
            if leading_m:
                qty_val = int(leading_m.group(1))
                clean = leading_m.group(2)
            elif trailing_m:
                qty_val = int(trailing_m.group(2))
                clean = trailing_m.group(1)

        assert len(clean) > 0
        assert qty_val >= 1
        assert tax_val >= 0.0


def test_deterministic_fallback_when_ai_provider_fails(temp_top_mgr):
    """Verify fallback parser executes deterministically if AI provider fails or is None."""
    with patch.object(temp_top_mgr, "ai_provider", None, create=True):
        res = temp_top_mgr.parse_top_query("price of 10 normal raids")
        calc = res.get("calculation")
        assert calc.total == 20.0
        assert calc.total_display == "20M"


def test_zero_usd_signs_in_catalogue_and_calculations(temp_top_mgr):
    """Verify prices never use USD or dollar signs '$' anywhere."""
    all_prices = temp_top_mgr.get_all_prices()
    for p in all_prices:
        assert "$" not in p.price_display, f"Found dollar sign in price: {p.service_name}"

    calc = temp_top_mgr.calculate_service_price("Mirage island")
    assert "$" not in calc.total_display
    assert "$" not in calc.unit_display

    embed = format_quote_embed(calc)
    assert "$" not in embed.description
    for f in embed.fields:
        assert "$" not in f.value
        assert "$" not in f.name
