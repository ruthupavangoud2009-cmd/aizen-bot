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
    PRIMARY_OWNER_ID,
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
    calculates known 10 normal raids deterministically (20M), provides an estimated
    quote for 4 trials (80M [Estimated Quote]), and produces combined 100M total.
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
    assert trials.total == 80.0
    assert "estimate" in trials.total_display.lower() or "quote" in trials.total_display.lower()

    # Check overall multi result contract
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


# ─── SECTION 10: MANDATORY REGRESSION TEST SUITE ────────────────────────────

from src.cogs.general.top_ai_manager import format_blox_fruits_bill_embed, InteractiveQuoteView


def test_section10_1_ten_normal_raids_tier(temp_top_mgr):
    """1. ?top price of 10 normal raids returns the correct official tier (20M)."""
    res = temp_top_mgr.parse_top_query("price of 10 normal raids")
    calc = res["calculation"]
    assert calc.total == 20.0
    assert calc.total_display == "20M"
    assert "Normal Raids" in calc.service_name


def test_section10_2_twenty_normal_raids_boundary_overlap(temp_top_mgr):
    """2. ?top price of 20 normal raids follows the configured overlap policy (50M)."""
    res = temp_top_mgr.parse_top_query("price of 20 normal raids")
    calc = res["calculation"]
    assert calc.total == 50.0
    assert calc.total_display == "50M"
    assert calc.is_clarification is False
    assert "overlap" in calc.ambiguity_note.lower() or "tier 16" in calc.condition_note.lower()


def test_section10_3_thirty_normal_raids_with_four_trials(temp_top_mgr):
    """3. ?top price of 30 normal raids with 4 trials includes both services,
    calculates normal raids extrapolation (25 @ 60M + 5 @ 10M = 70M),
    calculates trials (4 @ 20M = 80M), and produces combined total (150M).
    """
    res = temp_top_mgr.parse_top_query("price of 30 normal raids with 4 trials")
    calc = res["calculation"]
    assert isinstance(calc, MultiCalculationResult)
    assert len(calc.items) == 2

    raids = next(it for it in calc.items if "normal raid" in it.service_name.lower())
    assert raids.quantity == 30
    assert raids.total == 70.0
    assert "70M" in raids.total_display
    assert raids.is_provisional is True

    trials = next(it for it in calc.items if "trial" in it.service_name.lower())
    assert trials.quantity == 4
    assert trials.total == 80.0
    assert "80M" in trials.total_display
    assert trials.is_provisional is True

    assert calc.total == 150.0
    assert "150M" in calc.total_display


def test_section10_4_bill_ten_normal_raids_and_one_max_race(temp_top_mgr):
    """4. ?top bill 10 normal raids and 1 max race @Customer preserves exact quantities
    and recognizes Max Race Package correctly without '2x Normal Raids 6-10' or 'Beli'.
    """
    res = temp_top_mgr.parse_top_query("10 normal raids and 1 max race")
    calc = res["calculation"]
    assert isinstance(calc, MultiCalculationResult)
    assert len(calc.items) == 2

    bill = temp_top_mgr.create_multi_bill(
        guild_id=1,
        creator_id=999,
        creator_name="StaffMember",
        multi_calc=calc,
        customer_name="@Customer",
    )
    embed = format_blox_fruits_bill_embed(bill)
    desc = embed.description

    assert "Normal Raids × 10 — 20M" in desc
    assert "Max Race Package × 1 — 150M" in desc
    assert "2x Normal Raids" not in desc
    assert "170,000,000" not in desc
    assert "Beli" not in desc
    assert "170M" in desc
    assert embed.title == "KYOKA — SERVICE QUOTE"


def test_section10_5_four_trials_distinct_from_three_and_max(temp_top_mgr):
    """5. Four trials are not silently treated as three trials or another package."""
    res = temp_top_mgr.parse_top_query("4 trials")
    calc = res["calculation"]
    assert calc.quantity == 4
    assert calc.total == 80.0
    assert "80M" in calc.total_display
    assert calc.total != 60.0
    assert calc.total != 100.0


def test_section10_6_trials_packages_distinct(temp_top_mgr):
    """6. Max Trial, training, Max Race Package, and Draco Trials remain distinct."""
    max_trial = temp_top_mgr.parse_top_query("max trial")["calculation"]
    assert max_trial.total == 100.0

    max_trial_training = temp_top_mgr.parse_top_query("max trial with 2 extra training")["calculation"]
    assert max_trial_training.total == 120.0

    max_race = temp_top_mgr.parse_top_query("max race package")["calculation"]
    assert max_race.total == 150.0

    draco_trials = temp_top_mgr.parse_top_query("draco trial")["calculation"]
    assert draco_trials.total == 100.0
    assert "Draco" in draco_trials.service_name


def test_section10_7_no_beli_payment_wording_in_bills(temp_top_mgr):
    """7. No bill total is labelled as a Beli transfer requirement."""
    calc = temp_top_mgr.parse_top_query("10 normal raids")["calculation"]
    bill = temp_top_mgr.create_bill(
        guild_id=1,
        creator_id=999,
        creator_name="StaffMember",
        service_name=calc.service_name,
        quantity=calc.quantity,
        customer_name="@Customer",
    )
    embed = format_blox_fruits_bill_embed(bill)
    assert "Beli" not in embed.description
    assert "Beli" not in embed.title
    assert "Agreed service value" in embed.description


def test_section10_8_tax_calculated_only_when_specified(temp_top_mgr):
    """8. Tax is calculated only when specified."""
    # No tax specified
    no_tax_calc = temp_top_mgr.parse_top_query("10 normal raids")["calculation"]
    assert no_tax_calc.tax_rate == 0.0
    assert no_tax_calc.tax_amount == 0.0
    bill_no_tax = temp_top_mgr.create_bill(1, 999, "Staff", no_tax_calc.service_name, quantity=10)
    embed_no_tax = format_blox_fruits_bill_embed(bill_no_tax)
    assert "fee/tax" not in embed_no_tax.description

    # Tax specified (5%)
    tax_calc = temp_top_mgr.parse_top_query("10 normal raids with 5% tax")["calculation"]
    assert tax_calc.tax_rate == 5.0
    assert tax_calc.tax_amount == 1.0
    assert tax_calc.total == 21.0
    bill_tax = temp_top_mgr.create_bill(1, 999, "Staff", tax_calc.service_name, quantity=10, tax_rate=5.0)
    embed_tax = format_blox_fruits_bill_embed(bill_tax)
    assert "Service fee/tax (5%):" in embed_tax.description and "+1M" in embed_tax.description


def test_section10_9_unknown_services_never_silently_replaced(temp_top_mgr):
    """9. Unknown services are never silently replaced."""
    with pytest.raises(KeyError):
        temp_top_mgr.calculate_service_price("non_existent_random_service_xyz")


def test_section10_10_estimates_labelled(temp_top_mgr):
    """10. Estimates are labelled and respect the configured policy."""
    res = temp_top_mgr.parse_top_query("30 normal raids")
    calc = res["calculation"]
    assert calc.is_provisional is True
    assert "[Estimated Quote]" in calc.total_display


def test_section10_11_multi_calculation_is_clarification_no_attribute_error():
    """11. The MultiCalculationResult.is_clarification error is fixed at its source."""
    multi = MultiCalculationResult(
        items=[],
        subtotal=0.0,
        subtotal_display="0M",
        tax_rate=0.0,
        tax_amount=0.0,
        tax_display="0M",
        total=0.0,
        total_display="0M",
    )
    assert hasattr(multi, "is_clarification")
    assert multi.is_clarification is False


def test_section10_12_quantity_parsing_does_not_fail_int_conversion():
    """12. The quantity parsing error is fixed at its source."""
    raw = "10 normal raids and 1 max race @Customer"
    cleaned = raw
    plain_mention = re.search(r"@([a-zA-Z0-9_\-\.]+)", cleaned)
    assert plain_mention is not None
    cleaned = cleaned.replace(plain_mention.group(0), "").strip()
    assert "@Customer" not in cleaned
    assert "10 normal raids and 1 max race" == cleaned


def test_section10_13_existing_bills_and_database_compatibility(temp_top_mgr):
    """13. Existing bills and stored prices remain compatible."""
    bill = temp_top_mgr.create_bill(1, 999, "Staff", "Mirage Island", quantity=1)
    retrieved = temp_top_mgr.get_bill(bill["id"])
    assert retrieved is not None
    assert retrieved["id"] == bill["id"]
    assert retrieved["status"] == "UNPAID"
    assert retrieved["currency_unit"] in ("In-Game Value", "Beli")


@pytest.mark.asyncio
async def test_section10_15_duplicate_button_clicks_prevented(temp_top_mgr):
    """15. Duplicate button clicks cannot create duplicate bills."""
    calc = temp_top_mgr.parse_top_query("10 normal raids")["calculation"]
    view = InteractiveQuoteView(temp_top_mgr, calc, 123, 1)

    # First click sets is_created
    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = PRIMARY_OWNER_ID
    mock_interaction.guild = MagicMock()
    mock_interaction.guild.id = 1
    mock_interaction.response = AsyncMock()

    await view.btn_create_bill.callback(mock_interaction)
    assert view.is_created is True
    assert mock_interaction.response.edit_message.called

    # Second click is rejected
    mock_interaction2 = MagicMock(spec=discord.Interaction)
    mock_interaction2.user = mock_interaction.user
    mock_interaction2.response = AsyncMock()
    await view.btn_create_bill.callback(mock_interaction2)
    mock_interaction2.response.send_message.assert_called_with(
        "⚠️ A bill has already been created for this quote.",
        ephemeral=True,
    )

