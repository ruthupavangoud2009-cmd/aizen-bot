"""
Kyoka 3.0 - Universal Price Search & Matcher Test Suite.
Verifies all 18 official categories, natural-language price search, quantities, tiers,
singular/plural variations, aliases/capitalization, conditions (2x Money, 2x Mastery, Chalice, Carry),
ambiguity clarifications, custom quotes, decimal-safe tax arithmetic, and concise single-service embed formatting.
"""

import shutil
import tempfile
from pathlib import Path
import pytest
import discord

from src.managers.top_manager import TopManager, CalculationResult
from src.cogs.general.top_ai_manager import format_single_price_embed


@pytest.fixture
def top_mgr():
    """Create an isolated temporary TopManager instance."""
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "test_billing_universal.sqlite3"
    mgr = TopManager(db_path=db_file)
    yield mgr
    shutil.rmtree(temp_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. USER PROMPT CANONICAL EXAMPLES
# ─────────────────────────────────────────────────────────────────────────────

def test_prompt_canonical_example_1_trial(top_mgr: TopManager):
    """?top price of 1 trial -> 1 Trial: 20M."""
    res = top_mgr.parse_top_query("price of 1 trial")
    calc: CalculationResult = res["calculation"]
    assert calc.service_name == "1 Trial"
    assert calc.category == "Trials"
    assert calc.total == 20.0
    assert calc.total_display == "20M"


def test_prompt_canonical_example_5_raids_ambiguous(top_mgr: TopManager):
    """?top price of 5 raids -> identifies ambiguous raid category and asks clarification."""
    res = top_mgr.parse_top_query("price of 5 raids")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    assert "CLARIFICATION" in calc.clarification_title
    # Must offer Normal Raids (1-5: 10M), Advance Raids (5: 30M), Order Raids (3-5: 60M)
    opts_text = " ".join(calc.clarification_options)
    assert "Normal Raids" in opts_text
    assert "Advance Raids" in opts_text
    assert "Order Raids" in opts_text


def test_prompt_canonical_example_10_normal_raids(top_mgr: TopManager):
    """?top price of 10 normal raids -> 6-10 tier: 20M."""
    res = top_mgr.parse_top_query("price of 10 normal raids")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Normal Raids"
    assert calc.total == 20.0
    assert calc.total_display == "20M"


def test_prompt_canonical_example_3_advance_raids(top_mgr: TopManager):
    """?top price of 3 advance raids -> 3-4 tier: 20M."""
    res = top_mgr.parse_top_query("price of 3 advance raids")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Advance Raids"
    assert calc.total == 20.0
    assert calc.total_display == "20M"


def test_prompt_canonical_example_2_trials(top_mgr: TopManager):
    """?top price of 2 trials -> 40M."""
    res = top_mgr.parse_top_query("price of 2 trials")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Trials"
    assert calc.total == 40.0
    assert calc.total_display == "40M"


def test_prompt_canonical_example_draco_v2(top_mgr: TopManager):
    """?top price of Draco V2 -> 20M (must not match V1: 150M)."""
    res = top_mgr.parse_top_query("price of Draco V2")
    calc: CalculationResult = res["calculation"]
    assert calc.service_name == "Draco V2"
    assert calc.category == "Draco"
    assert calc.total == 20.0


def test_prompt_canonical_example_mirage_island(top_mgr: TopManager):
    """?top price of Mirage Island -> 60M."""
    res = top_mgr.parse_top_query("price of Mirage Island")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Sea Events"
    assert calc.total == 60.0
    assert calc.total_display == "60M"


def test_prompt_canonical_example_dough_king(top_mgr: TopManager):
    """?top price of Dough King -> 120M."""
    res = top_mgr.parse_top_query("price of Dough King")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Bosses"
    assert calc.total == 120.0
    assert calc.total_display == "120M"


def test_prompt_canonical_example_cdk(top_mgr: TopManager):
    """?top price of CDK -> 600M."""
    res = top_mgr.parse_top_query("price of CDK")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Swords"
    assert calc.total == 600.0
    assert calc.total_display == "600M"


def test_prompt_canonical_example_electric_claw(top_mgr: TopManager):
    """?top price of Electric Claw -> 60M."""
    res = top_mgr.parse_top_query("price of Electric Claw")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Fighting Styles"
    assert calc.total == 60.0
    assert calc.total_display == "60M"


def test_prompt_canonical_example_level_1000(top_mgr: TopManager):
    """?top price of level 1000 -> 400M (must not multiply 1000 x 30M)."""
    res = top_mgr.parse_top_query("price of level 1000")
    calc: CalculationResult = res["calculation"]
    assert calc.service_name == "Level 1000"
    assert calc.category == "Levels"
    assert calc.total == 400.0
    assert calc.total_display == "400M"


def test_prompt_canonical_example_300_mastery_with_2x(top_mgr: TopManager):
    """?top price of 300 mastery with 2x mastery -> 30M for melee/sword/fruit mastery."""
    res = top_mgr.parse_top_query("price of 300 mastery with 2x mastery")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Mastery"
    assert calc.total == 30.0
    assert calc.total_display == "30M"


def test_prompt_canonical_example_300_gun_mastery_with_2x(top_mgr: TopManager):
    """?top price of 300 gun mastery with 2x mastery -> correctly matches Gun Mastery."""
    res = top_mgr.parse_top_query("price of 300 gun mastery with 2x mastery")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Gun Mastery"
    # Matches the authoritative database price for gun_mastery_2x_300
    assert calc.total == 30.0


def test_prompt_canonical_example_10m_beli_with_2x_money(top_mgr: TopManager):
    """?top price of 10M Beli with 2x money -> distinguishes farmed Beli (10M) from price charged (30M)."""
    res = top_mgr.parse_top_query("price of 10M Beli with 2x money")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Beli Farming"
    assert calc.total == 30.0
    assert calc.total_display == "30M"
    assert "Farmed Beli: 10M" in calc.condition_note


def test_prompt_canonical_example_raging_demon_title(top_mgr: TopManager):
    """?top price of Raging Demon title -> 300M."""
    res = top_mgr.parse_top_query("price of Raging Demon title")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Titles"
    assert calc.total == 300.0
    assert calc.total_display == "300M"


def test_prompt_canonical_example_levi_shield(top_mgr: TopManager):
    """?top price of Levi Shield -> 1.2B."""
    res = top_mgr.parse_top_query("price of Levi Shield")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Accessories"
    assert calc.total == 1200.0
    assert calc.total_display == "1.2B"


def test_prompt_canonical_example_2_trials_with_5_percent_tax(top_mgr: TopManager):
    """?top price of 2 trials with 5% tax -> 40M subtotal + 2M tax = 42M total."""
    res = top_mgr.parse_top_query("price of 2 trials with 5% tax")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Trials"
    assert calc.subtotal == 40.0
    assert calc.tax_rate == 5.0
    assert calc.tax_amount == 2.0
    assert calc.total == 42.0
    assert calc.total_display == "42M"


def test_prompt_canonical_example_5_normal_raids_with_5_percent_tax(top_mgr: TopManager):
    """?top price of 5 normal raids with 5% tax -> 10M subtotal + 0.5M tax = 10.5M total."""
    res = top_mgr.parse_top_query("price of 5 normal raids with 5% tax")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Normal Raids"
    assert calc.subtotal == 10.0
    assert calc.tax_rate == 5.0
    assert calc.tax_amount == 0.5
    assert calc.total == 10.5
    assert calc.total_display == "10.5M"


# ─────────────────────────────────────────────────────────────────────────────
# 2. DISAMBIGUATION & CLARIFICATIONS (Rule 2 & Rule 4)
# ─────────────────────────────────────────────────────────────────────────────

def test_clarification_300_mastery_without_specifying_2x(top_mgr: TopManager):
    """Requesting 300 mastery without 2x condition asks for clarification."""
    res = top_mgr.parse_top_query("price of 300 mastery")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    opts = " ".join(calc.clarification_options)
    assert "With 2x Mastery" in opts
    assert "Without 2x Mastery" in opts


def test_clarification_10m_beli_without_specifying_2x(top_mgr: TopManager):
    """Requesting 10M Beli without 2x condition asks for clarification."""
    res = top_mgr.parse_top_query("price of 10M Beli")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    opts = " ".join(calc.clarification_options)
    assert "With 2x Money" in opts
    assert "Without 2x Money" in opts


def test_clarification_prehistoric_island_without_specifying_carry(top_mgr: TopManager):
    """Requesting Prehistoric Island without carry condition asks for clarification."""
    res = top_mgr.parse_top_query("price of Prehistoric Island")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    opts = " ".join(calc.clarification_options)
    assert "Not Carry" in opts
    assert "Carry" in opts


def test_clarification_20_normal_raids_boundary_overlap(top_mgr: TopManager):
    """Requesting 20 normal raids flags the 16-20 (50M) vs 20-25 (60M) overlap."""
    res = top_mgr.parse_top_query("price of 20 normal raids")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    assert calc.total in (50.0, 60.0)
    assert calc.ambiguity_note != ""


def test_clarification_8_order_raids_boundary_overlap(top_mgr: TopManager):
    """Requesting 8 order raids flags the 6-8 (120M) vs 8-10 (150M) overlap."""
    res = top_mgr.parse_top_query("price of 8 order raids")
    calc: CalculationResult = res["calculation"]
    assert calc.is_clarification is True
    assert calc.total in (120.0, 150.0)
    assert calc.ambiguity_note != ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. CUSTOM-PRICE SERVICES
# ─────────────────────────────────────────────────────────────────────────────

def test_custom_price_26_normal_raids(top_mgr: TopManager):
    """26+ normal raids requires custom quote."""
    res = top_mgr.parse_top_query("price of 26 normal raids")
    calc: CalculationResult = res["calculation"]
    assert calc.custom_quote is True


def test_custom_price_11_order_raids(top_mgr: TopManager):
    """11+ order raids requires custom quote."""
    res = top_mgr.parse_top_query("price of 11 order raids")
    calc: CalculationResult = res["calculation"]
    assert calc.custom_quote is True


def test_custom_price_25m_beli_with_2x_money(top_mgr: TopManager):
    """25M Beli with 2x Money is not listed; must not invent price, requires custom quote."""
    res = top_mgr.parse_top_query("price of 25M Beli with 2x money")
    calc: CalculationResult = res["calculation"]
    assert calc.custom_quote is True


def test_custom_price_custom_titles(top_mgr: TopManager):
    """Custom titles require custom quote."""
    res = top_mgr.parse_top_query("price of custom titles")
    calc: CalculationResult = res["calculation"]
    assert calc.custom_quote is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. ALL REMAINING CATEGORIES VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def test_swords_per_unit_multiplication(top_mgr: TopManager):
    """TTK is 30M per sword; 3 TTK = 90M."""
    res = top_mgr.parse_top_query("price of 3 TTK")
    calc: CalculationResult = res["calculation"]
    assert calc.category == "Swords"
    assert calc.total == 90.0
    assert calc.total_display == "90M"


def test_swords_individual(top_mgr: TopManager):
    """Verify individual swords."""
    assert top_mgr.parse_top_query("price of Tushita")["calculation"].total == 90.0
    assert top_mgr.parse_top_query("price of Yama")["calculation"].total == 30.0
    assert top_mgr.parse_top_query("price of Dark Dagger")["calculation"].total == 600.0
    assert top_mgr.parse_top_query("price of Fox Lamp")["calculation"].total == 150.0
    assert top_mgr.parse_top_query("price of Hollow Scythe")["calculation"].total == 150.0


def test_guns_individual(top_mgr: TopManager):
    """Verify guns."""
    assert top_mgr.parse_top_query("price of Skull Guitar")["calculation"].total == 60.0
    assert top_mgr.parse_top_query("price of DragonStorm")["calculation"].total == 150.0


def test_fighting_styles_individual(top_mgr: TopManager):
    """Verify fighting styles."""
    assert top_mgr.parse_top_query("price of Godhuman")["calculation"].total == 600.0
    assert top_mgr.parse_top_query("price of Sanguine")["calculation"].total == 600.0
    assert top_mgr.parse_top_query("price of Dragon Talon")["calculation"].total == 90.0
    assert top_mgr.parse_top_query("price of Death Step")["calculation"].total == 60.0


def test_admin_panel_individual(top_mgr: TopManager):
    """Verify Admin Panel services."""
    assert top_mgr.parse_top_query("price of Control")["calculation"].total == 1200.0
    assert top_mgr.parse_top_query("price of Gravity")["calculation"].total == 500.0
    assert top_mgr.parse_top_query("price of Lightning")["calculation"].total == 600.0
    assert top_mgr.parse_top_query("price of Pain")["calculation"].total == 600.0
    assert top_mgr.parse_top_query("price of Eagle")["calculation"].total == 150.0


def test_accessories_individual(top_mgr: TopManager):
    """Verify accessories."""
    assert top_mgr.parse_top_query("price of Kit Mask")["calculation"].total == 100.0
    assert top_mgr.parse_top_query("price of Kit Ribbon")["calculation"].total == 80.0
    assert top_mgr.parse_top_query("price of Dino Hood")["calculation"].total == 60.0
    assert top_mgr.parse_top_query("price of Bandana")["calculation"].total == 20.0


def test_races_and_ghoul_dough(top_mgr: TopManager):
    """Verify races and Ghoul Dough requirement."""
    assert top_mgr.parse_top_query("price of Cyborg V1")["calculation"].total == 100.0
    assert top_mgr.parse_top_query("price of Ghoul V1")["calculation"].total == 100.0
    assert top_mgr.parse_top_query("price of Every Race V2")["calculation"].total == 20.0
    assert top_mgr.parse_top_query("price of Every Race V3")["calculation"].total == 10.0
    ghoul_v3 = top_mgr.parse_top_query("price of Ghoul V3")["calculation"]
    assert "dough" in ghoul_v3.condition_note.lower()


def test_bosses_rip_indra_conditions(top_mgr: TopManager):
    """Verify Rip_Indra with and without chalice."""
    without_c = top_mgr.parse_top_query("price of Rip Indra")["calculation"]
    assert without_c.total == 60.0
    assert "chalice" in without_c.condition_note.lower()

    with_c = top_mgr.parse_top_query("price of Rip Indra with chalice")["calculation"]
    assert with_c.total == 30.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. UI EMBED FORMATTING (ONLY SHOW REQUESTED RESULT - Rule 3)
# ─────────────────────────────────────────────────────────────────────────────

def test_format_single_price_embed_normal_raids(top_mgr: TopManager):
    """Verify format_single_price_embed returns concise embed for 5 Normal Raids."""
    res = top_mgr.parse_top_query("price of 5 normal raids")
    embed = format_single_price_embed(res["calculation"])
    assert embed.title == "🏷️ NORMAL RAIDS"
    assert "5 Raids: **10M**" in embed.description
    assert embed.footer.text == "Kyoka Top AI Manager"
    # Ensure no massive catalogue dumps or extra fields
    assert len(embed.fields) == 0


def test_format_single_price_embed_with_tax(top_mgr: TopManager):
    """Verify format_single_price_embed displays subtotal, tax amount, and total."""
    res = top_mgr.parse_top_query("price of 2 trials with 5% tax")
    embed = format_single_price_embed(res["calculation"])
    assert embed.title == "🏷️ TRIALS"
    assert "2 Trials: **40M**" in embed.description
    assert "Tax (5%): **+2M**" in embed.description
    assert "Total: **42M**" in embed.description


def test_format_single_price_embed_clarification(top_mgr: TopManager):
    """Verify clarification embed format."""
    res = top_mgr.parse_top_query("price of 5 raids")
    embed = format_single_price_embed(res["calculation"])
    assert "CLARIFICATION" in embed.title
    assert "Normal Raids" in embed.description
    assert "Advance Raids" in embed.description
    assert "Order Raids" in embed.description


def test_unknown_service_raises_keyerror(top_mgr: TopManager):
    """Unknown service query raises KeyError."""
    with pytest.raises(KeyError):
        top_mgr.parse_top_query("price of nonexistent ultra secret fruit 9999")
