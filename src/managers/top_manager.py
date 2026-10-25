"""
Kyoka 3.0 - Top AI Manager, Service Billing & Staff Application System
Provides official Blox Fruits price catalogue management, natural-language price lookups,
decimal-safe tax calculation, persistent service bills with Discord message ID verification,
financial reporting (today, weekly, monthly), and Appy-style staff application workflows.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("Kyoka.TopManager")

# Shared SQLite database for accounting and billing
DB_PATH = Path("data/kyoka_billing.sqlite3")

# Primary Authoritative Owner
PRIMARY_OWNER_ID = 1505515188991033409


@dataclass
class PriceItem:
    category: str
    service_key: str
    service_name: str
    price_amount: float
    price_display: str
    unit_desc: str = ""
    condition_note: str = ""
    custom_quote_required: int = 0
    aliases: list[str] = field(default_factory=list)
    min_qty: int = 1
    max_qty: int = 1


@dataclass
class CalculationResult:
    service_name: str
    category: str
    quantity: int
    unit_price: float
    unit_display: str
    subtotal: float
    subtotal_display: str
    tax_rate: float
    tax_amount: float
    tax_display: str
    total: float
    total_display: str
    condition_note: str = ""
    custom_quote: bool = False
    ambiguity_note: str = ""
    is_clarification: bool = False
    clarification_title: str = ""
    clarification_options: list[str] = field(default_factory=list)
    # Smart pricing fields
    is_provisional: bool = False
    baseline_price: float = 0.0
    baseline_display: str = ""
    extra_charges: float = 0.0
    extra_charges_display: str = ""
    pricing_explanation: str = ""
    requires_staff_approval: bool = False


@dataclass
class MultiCalculationResult:
    items: list[CalculationResult]
    subtotal: float
    subtotal_display: str
    tax_rate: float
    tax_amount: float
    tax_display: str
    total: float
    total_display: str
    service_name: str = ""
    is_multi: bool = True
    comparison_mode: bool = False
    clarification_needed: bool = False
    clarifications: list[CalculationResult] = field(default_factory=list)
    requires_staff_approval: bool = False
    pricing_explanation: str = ""
    condition_note: str = ""
    category: str = "Multi-Service Package"
    quantity: int = 1
    # Unified contract with CalculationResult
    is_clarification: bool = False
    clarification_title: str = ""
    clarification_options: list[str] = field(default_factory=list)
    is_provisional: bool = False
    baseline_price: float = 0.0
    baseline_display: str = ""
    extra_charges: float = 0.0
    extra_charges_display: str = ""
    custom_quote: bool = False
    unit_price: float = 0.0
    unit_display: str = ""

    def __post_init__(self) -> None:
        has_clarif = (
            self.clarification_needed
            or self.is_clarification
            or any(getattr(c, "is_clarification", False) for c in self.items)
            or bool(self.clarifications)
        )
        if has_clarif:
            self.is_clarification = True
            self.clarification_needed = True
            if not self.clarification_title:
                self.clarification_title = "❓ TOP AI MANAGER • CLARIFICATION NEEDED"
            if not self.clarification_options:
                all_opts: list[str] = []
                for c in (self.clarifications or self.items):
                    if getattr(c, "is_clarification", False) and getattr(c, "clarification_options", None):
                        all_opts.extend(c.clarification_options)
                self.clarification_options = all_opts
        if any(getattr(c, "is_provisional", False) for c in self.items):
            self.is_provisional = True
        if any(getattr(c, "custom_quote", False) for c in self.items):
            self.custom_quote = True
        if not self.unit_price and self.subtotal:
            self.unit_price = self.subtotal
        if not self.unit_display and self.subtotal_display:
            self.unit_display = self.subtotal_display




# ─────────────────────────────────────────────────────────────────────────────
# 1. OFFICIAL AUTHORITATIVE INITIAL PRICE CATALOGUE
# ─────────────────────────────────────────────────────────────────────────────

INITIAL_PRICES: list[dict[str, Any]] = [
    # TRIALS
    {
        "category": "Trials",
        "service_key": "trial_1",
        "service_name": "1 Trial",
        "aliases": ["1 trial", "one trial", "single trial", "1 v4 trial"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "per trial",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "category": "Trials",
        "service_key": "trial_2",
        "service_name": "2 Trials",
        "aliases": ["2 trials", "two trials", "2 v4 trials"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "package",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 2,
        "max_qty": 2,
    },
    {
        "category": "Trials",
        "service_key": "trial_3",
        "service_name": "3 Trials",
        "aliases": ["3 trials", "three trials", "3 v4 trials"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "package",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 3,
        "max_qty": 3,
    },
    {
        "category": "Trials",
        "service_key": "trial_max",
        "service_name": "Max Trial",
        "aliases": ["max trial", "max trials", "full trial"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "full max",
        "condition_note": "Training not included",
        "custom_quote_required": 0,
    },
    {
        "category": "Trials",
        "service_key": "trial_training",
        "service_name": "Each Training",
        "aliases": ["each training", "training", "trial training", "gear training"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "per training",
        "condition_note": "Additional 10M per training session",
        "custom_quote_required": 0,
    },
    {
        "category": "Trials",
        "service_key": "trial_max_race_package",
        "service_name": "Max Race Package",
        "aliases": ["max race package", "max race", "full race package", "v4 max package"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "complete package",
        "condition_note": "Training included",
        "custom_quote_required": 0,
    },
    {
        "category": "Trials",
        "service_key": "trial_draco",
        "service_name": "Draco Trials",
        "aliases": ["draco trial", "draco trials"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "each",
        "condition_note": "100M each",
        "custom_quote_required": 0,
    },

    # NORMAL RAIDS
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_1_5",
        "service_name": "Normal Raids 1-5",
        "aliases": ["normal raids 1-5", "1-5 normal raids", "normal raid", "normal raids"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "tier (1-5)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 1,
        "max_qty": 5,
    },
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_6_10",
        "service_name": "Normal Raids 6-10",
        "aliases": ["normal raids 6-10", "6-10 normal raids"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "tier (6-10)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 6,
        "max_qty": 10,
    },
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_11_15",
        "service_name": "Normal Raids 11-15",
        "aliases": ["normal raids 11-15", "11-15 normal raids"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "tier (11-15)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 11,
        "max_qty": 15,
    },
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_16_20",
        "service_name": "Normal Raids 16-20",
        "aliases": ["normal raids 16-20", "16-20 normal raids"],
        "price_amount": 50.0,
        "price_display": "50M",
        "unit_desc": "tier (16-20)",
        "condition_note": "Notice: 16-20 (50M) and 20-25 (60M) overlap at 20. Confirm boundary with owner.",
        "custom_quote_required": 0,
        "min_qty": 16,
        "max_qty": 20,
    },
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_20_25",
        "service_name": "Normal Raids 20-25",
        "aliases": ["normal raids 20-25", "20-25 normal raids"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "tier (20-25)",
        "condition_note": "Notice: 16-20 (50M) and 20-25 (60M) overlap at 20. Confirm boundary with owner.",
        "custom_quote_required": 0,
        "min_qty": 20,
        "max_qty": 25,
    },
    {
        "category": "Normal Raids",
        "service_key": "normal_raid_25_plus",
        "service_name": "Normal Raids 25+",
        "aliases": ["normal raids 25+", "25+ normal raids", "26 normal raids", "30 normal raids"],
        "price_amount": 0.0,
        "price_display": "Custom Quote",
        "unit_desc": "custom",
        "condition_note": "Custom price required; please contact staff for a direct quote.",
        "custom_quote_required": 1,
        "min_qty": 26,
        "max_qty": 9999,
    },

    # ADVANCE RAIDS
    {
        "category": "Advance Raids",
        "service_key": "adv_raid_1_2",
        "service_name": "Advance Raids 1-2",
        "aliases": ["advance raids 1-2", "advance raid", "adv raid", "advance raids"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "tier (1-2)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 1,
        "max_qty": 2,
    },
    {
        "category": "Advance Raids",
        "service_key": "adv_raid_3_4",
        "service_name": "Advance Raids 3-4",
        "aliases": ["advance raids 3-4", "3-4 advance raids"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "tier (3-4)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 3,
        "max_qty": 4,
    },
    {
        "category": "Advance Raids",
        "service_key": "adv_raid_5",
        "service_name": "Advance Raids 5",
        "aliases": ["advance raids 5", "5 advance raids"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "tier (5)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 5,
        "max_qty": 5,
    },
    {
        "category": "Advance Raids",
        "service_key": "adv_raid_6_8",
        "service_name": "Advance Raids 6-8",
        "aliases": ["advance raids 6-8", "6-8 advance raids"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "tier (6-8)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 6,
        "max_qty": 8,
    },

    # ORDER RAIDS
    {
        "category": "Order Raids",
        "service_key": "order_raid_1",
        "service_name": "Order Raids 1",
        "aliases": ["order raids 1", "1 order raid", "order raid", "law raid", "order raids"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "tier (1)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 1,
        "max_qty": 1,
    },
    {
        "category": "Order Raids",
        "service_key": "order_raid_2",
        "service_name": "Order Raids 2",
        "aliases": ["order raids 2", "2 order raids"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "tier (2)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 2,
        "max_qty": 2,
    },
    {
        "category": "Order Raids",
        "service_key": "order_raid_3_5",
        "service_name": "Order Raids 3-5",
        "aliases": ["order raids 3-5", "3-5 order raids"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "tier (3-5)",
        "condition_note": "",
        "custom_quote_required": 0,
        "min_qty": 3,
        "max_qty": 5,
    },
    {
        "category": "Order Raids",
        "service_key": "order_raid_6_8",
        "service_name": "Order Raids 6-8",
        "aliases": ["order raids 6-8", "6-8 order raids"],
        "price_amount": 120.0,
        "price_display": "120M",
        "unit_desc": "tier (6-8)",
        "condition_note": "Notice: 6-8 (120M) and 8-10 (150M) overlap at 8. Flagged for owner confirmation.",
        "custom_quote_required": 0,
        "min_qty": 6,
        "max_qty": 8,
    },
    {
        "category": "Order Raids",
        "service_key": "order_raid_8_10",
        "service_name": "Order Raids 8-10",
        "aliases": ["order raids 8-10", "8-10 order raids"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "tier (8-10)",
        "condition_note": "Notice: 6-8 (120M) and 8-10 (150M) overlap at 8. Flagged for owner confirmation.",
        "custom_quote_required": 0,
        "min_qty": 8,
        "max_qty": 10,
    },
    {
        "category": "Order Raids",
        "service_key": "order_raid_10_plus",
        "service_name": "Order Raids 10+",
        "aliases": ["order raids 10+", "10+ order raids", "11 order raids"],
        "price_amount": 0.0,
        "price_display": "Custom Quote",
        "unit_desc": "custom",
        "condition_note": "Custom price required; contact staff for a direct quote.",
        "custom_quote_required": 1,
        "min_qty": 11,
        "max_qty": 9999,
    },

    # RACES (DRACO NOT INCLUDED)
    {
        "category": "Races",
        "service_key": "race_cyborg_v1",
        "service_name": "Cyborg V1",
        "aliases": ["cyborg v1", "cyborg race v1", "cyborg"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Races",
        "service_key": "race_ghoul_v1",
        "service_name": "Ghoul V1",
        "aliases": ["ghoul v1", "ghoul race v1", "ghoul"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Races",
        "service_key": "race_v2_every",
        "service_name": "Every Race V2",
        "aliases": ["race v2", "every race v2", "v2 race", "human v2", "mink v2", "fishman v2", "skypian v2", "angel v2"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "per race",
        "condition_note": "20M per race",
        "custom_quote_required": 0,
    },
    {
        "category": "Races",
        "service_key": "race_v3_every",
        "service_name": "Every Race V3",
        "aliases": ["race v3", "every race v3", "v3 race", "human v3", "mink v3", "fishman v3", "skypian v3", "angel v3", "cyborg v3"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "per race",
        "condition_note": "10M per race (Ghoul V3 requires Dough fruit condition)",
        "custom_quote_required": 0,
    },
    {
        "category": "Races",
        "service_key": "race_ghoul_v3",
        "service_name": "Ghoul V3",
        "aliases": ["ghoul v3", "ghoul race v3"],
        "price_amount": 10.0,
        "price_display": "10M + Dough",
        "unit_desc": "",
        "condition_note": "Condition/Requirement: Dough fruit required (Ask owner to clarify if separate service price).",
        "custom_quote_required": 0,
    },

    # DRACO
    {
        "category": "Draco",
        "service_key": "draco_v1",
        "service_name": "Draco V1",
        "aliases": ["draco v1", "draco race v1"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "From the start; custom depending on belt process",
        "custom_quote_required": 0,
    },
    {
        "category": "Draco",
        "service_key": "draco_v2",
        "service_name": "Draco V2",
        "aliases": ["draco v2", "draco race v2"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Draco",
        "service_key": "draco_v3",
        "service_name": "Draco V3",
        "aliases": ["draco v3", "draco race v3"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Draco",
        "service_key": "draco_v4",
        "service_name": "Draco V4",
        "aliases": ["draco v4", "draco race v4"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Draco",
        "service_key": "draco_max_v4",
        "service_name": "Max Draco V4",
        "aliases": ["max draco v4", "max v4 draco", "max draco", "draco max"],
        "price_amount": 1200.0,
        "price_display": "1.2B",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },

    # SEA EVENTS
    {
        "category": "Sea Events",
        "service_key": "sea_mirage",
        "service_name": "Mirage Island",
        "aliases": ["mirage island", "mirage"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_mirage_blue_gear",
        "service_name": "Mirage + Blue Gear",
        "aliases": ["mirage + blue gear", "mirage blue gear", "blue gear", "mirage gear"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_prehistoric_not_carry",
        "service_name": "Prehistoric Island (Not Carry)",
        "aliases": ["prehistoric island not carry", "prehistoric not carry"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "per island",
        "condition_note": "30M per island",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_prehistoric_carry",
        "service_name": "Prehistoric Island (Carry)",
        "aliases": ["prehistoric island carry", "prehistoric carry"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "per island",
        "condition_note": "60M per island",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_leviathan_tiki",
        "service_name": "Leviathan to Tiki",
        "aliases": ["leviathan to tiki", "levi tiki", "leviathan tiki"],
        "price_amount": 300.0,
        "price_display": "300M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_leviathan_hydra",
        "service_name": "Leviathan to Hydra",
        "aliases": ["leviathan to hydra", "levi hydra", "leviathan hydra"],
        "price_amount": 350.0,
        "price_display": "350M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Sea Events",
        "service_key": "sea_kitsune_shrine",
        "service_name": "Kitsune Shrine",
        "aliases": ["kitsune shrine", "shrine", "kit shrine"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "per island",
        "condition_note": "30M per island",
        "custom_quote_required": 0,
    },

    # BOSSES
    {
        "category": "Bosses",
        "service_key": "boss_dough_king",
        "service_name": "Dough King",
        "aliases": ["dough king", "dk"],
        "price_amount": 120.0,
        "price_display": "120M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Bosses",
        "service_key": "boss_cake_prince",
        "service_name": "Cake Prince",
        "aliases": ["cake prince", "cp"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Bosses",
        "service_key": "boss_soul_reaper",
        "service_name": "Soul Reaper",
        "aliases": ["soul reaper"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Bosses",
        "service_key": "boss_rip_indra",
        "service_name": "Rip_Indra",
        "aliases": ["rip_indra", "rip indra", "indra"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "30M if the customer already has a chalice",
        "custom_quote_required": 0,
    },
    {
        "category": "Bosses",
        "service_key": "boss_rip_indra_chalice",
        "service_name": "Rip_Indra (With Chalice)",
        "aliases": ["rip indra with chalice", "indra with chalice", "rip_indra chalice"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "Customer supplies chalice",
        "custom_quote_required": 0,
    },
    {
        "category": "Bosses",
        "service_key": "boss_dark_beard",
        "service_name": "Dark Beard",
        "aliases": ["dark beard", "blackbeard", "bb"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },

    # FIGHTING STYLES
    {
        "category": "Fighting Styles",
        "service_key": "fs_sanguine",
        "service_name": "Sanguine Art",
        "aliases": ["sanguine", "sanguine art", "sanguine from start"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Fighting Styles",
        "service_key": "fs_godhuman",
        "service_name": "Godhuman",
        "aliases": ["godhuman", "gh", "god human"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Fighting Styles",
        "service_key": "fs_dragon_talon",
        "service_name": "Dragon Talon",
        "aliases": ["dragon talon", "dt"],
        "price_amount": 90.0,
        "price_display": "90M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Fighting Styles",
        "service_key": "fs_electric_claw",
        "service_name": "Electric Claw",
        "aliases": ["electric claw", "e-claw", "eclaw"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Fighting Styles",
        "service_key": "fs_death_step",
        "service_name": "Death Step",
        "aliases": ["death step", "ds"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },

    # SWORDS
    {
        "category": "Swords",
        "service_key": "sword_cdk",
        "service_name": "CDK",
        "aliases": ["cdk", "cursed dual katana", "cdk from start", "cdk from the start"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "From the start",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_ttk",
        "service_name": "TTK",
        "aliases": ["ttk", "true triple katana"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "per sword",
        "condition_note": "30M per sword",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_dragonheart",
        "service_name": "DragonHeart",
        "aliases": ["dragonheart", "dragon heart"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "From the start; custom depending on belt process",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_shark_anchor",
        "service_name": "Shark Anchor",
        "aliases": ["shark anchor", "anchor"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "From the start; custom depending on material",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_hollow_scythe",
        "service_name": "Hollow Scythe",
        "aliases": ["hollow scythe", "scythe"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_dark_dagger",
        "service_name": "Dark Dagger",
        "aliases": ["dark dagger", "dagger"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_fox_lamp",
        "service_name": "Fox Lamp",
        "aliases": ["fox lamp", "lamp"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_tushita",
        "service_name": "Tushita",
        "aliases": ["tushita"],
        "price_amount": 90.0,
        "price_display": "90M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_yama",
        "service_name": "Yama",
        "aliases": ["yama"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_tushita_scroll",
        "service_name": "Tushita Scroll",
        "aliases": ["tushita scroll", "tushita trial"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "per trial",
        "condition_note": "20M per trial",
        "custom_quote_required": 0,
    },
    {
        "category": "Swords",
        "service_key": "sword_yama_scroll",
        "service_name": "Yama Scroll",
        "aliases": ["yama scroll", "yama trial"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "per trial",
        "condition_note": "30M per trial",
        "custom_quote_required": 0,
    },

    # GUNS
    {
        "category": "Guns",
        "service_key": "gun_dragonstorm",
        "service_name": "DragonStorm",
        "aliases": ["dragonstorm", "dragon storm"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "From the start; custom depending on belt process",
        "custom_quote_required": 0,
    },
    {
        "category": "Guns",
        "service_key": "gun_skull_guitar",
        "service_name": "Skull Guitar",
        "aliases": ["skull guitar", "soul guitar"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "From the start; no level grinding",
        "custom_quote_required": 0,
    },

    # BELI FARMING (WITHOUT 2X MONEY)
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_5m",
        "service_name": "5M Beli (Without 2x Money)",
        "aliases": ["5m beli", "5m beli without 2x"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 5M Beli | Without 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_10m",
        "service_name": "10M Beli (Without 2x Money)",
        "aliases": ["10m beli", "10m beli without 2x"],
        "price_amount": 50.0,
        "price_display": "50M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 10M Beli | Without 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_15m",
        "service_name": "15M Beli (Without 2x Money)",
        "aliases": ["15m beli", "15m beli without 2x"],
        "price_amount": 80.0,
        "price_display": "80M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 15M Beli | Without 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_20m",
        "service_name": "20M Beli (Without 2x Money)",
        "aliases": ["20m beli", "20m beli without 2x"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 20M Beli | Without 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_25m",
        "service_name": "25M Beli (Without 2x Money)",
        "aliases": ["25m beli", "25m beli without 2x"],
        "price_amount": 350.0,
        "price_display": "350M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 25M Beli | Without 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_no2x_30m_plus",
        "service_name": "30M+ Beli (Without 2x Money)",
        "aliases": ["30m+ beli", "30m beli without 2x", "30m+ beli without 2x"],
        "price_amount": 0.0,
        "price_display": "Custom Quote",
        "unit_desc": "custom",
        "condition_note": "30M+ contact staff for custom quote.",
        "custom_quote_required": 1,
    },

    # BELI FARMING (WITH 2X MONEY)
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_5m",
        "service_name": "5M Beli (With 2x Money)",
        "aliases": ["5m beli 2x", "5m beli with 2x"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 5M Beli | With 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_10m",
        "service_name": "10M Beli (With 2x Money)",
        "aliases": ["10m beli 2x", "10m beli with 2x"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 10M Beli | With 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_15m",
        "service_name": "15M Beli (With 2x Money)",
        "aliases": ["15m beli 2x", "15m beli with 2x"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 15M Beli | With 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_20m",
        "service_name": "20M Beli (With 2x Money)",
        "aliases": ["20m beli 2x", "20m beli with 2x"],
        "price_amount": 80.0,
        "price_display": "80M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 20M Beli | With 2x Money",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_30m",
        "service_name": "30M Beli (With 2x Money)",
        "aliases": ["30m beli 2x", "30m beli with 2x"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "service price",
        "condition_note": "Farmed: 30M Beli | With 2x Money (Note: No 25M tier for 2x money)",
        "custom_quote_required": 0,
    },
    {
        "category": "Beli Farming",
        "service_key": "beli_2x_30m_plus",
        "service_name": "30M+ Beli (With 2x Money)",
        "aliases": ["30m+ beli 2x", "30m+ beli with 2x"],
        "price_amount": 0.0,
        "price_display": "Custom Quote",
        "unit_desc": "custom",
        "condition_note": "30M+ contact staff for custom quote.",
        "custom_quote_required": 1,
    },

    # LEVELS
    {
        "category": "Levels",
        "service_key": "level_100",
        "service_name": "Level 100",
        "aliases": ["level 100", "lvl 100"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_200",
        "service_name": "Level 200",
        "aliases": ["level 200", "lvl 200"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_300",
        "service_name": "Level 300",
        "aliases": ["level 300", "lvl 300"],
        "price_amount": 90.0,
        "price_display": "90M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_400",
        "service_name": "Level 400",
        "aliases": ["level 400", "lvl 400"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_500",
        "service_name": "Level 500",
        "aliases": ["level 500", "lvl 500"],
        "price_amount": 120.0,
        "price_display": "120M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_1000",
        "service_name": "Level 1000",
        "aliases": ["level 1000", "lvl 1000"],
        "price_amount": 400.0,
        "price_display": "400M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Levels",
        "service_key": "level_max",
        "service_name": "Max Level",
        "aliases": ["max level", "max lvl"],
        "price_amount": 1300.0,
        "price_display": "1.3B",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },

    # ADMIN PANEL
    {
        "category": "Admin Panel",
        "service_key": "admin_gravity",
        "service_name": "Gravity",
        "aliases": ["gravity", "admin gravity"],
        "price_amount": 500.0,
        "price_display": "500M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Admin Panel",
        "service_key": "admin_lightning",
        "service_name": "Lightning",
        "aliases": ["lightning", "admin lightning"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Admin Panel",
        "service_key": "admin_pain",
        "service_name": "Pain",
        "aliases": ["pain", "admin pain"],
        "price_amount": 600.0,
        "price_display": "600M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Admin Panel",
        "service_key": "admin_eagle",
        "service_name": "Eagle",
        "aliases": ["eagle", "admin eagle"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Admin Panel",
        "service_key": "admin_control",
        "service_name": "Control",
        "aliases": ["control", "admin control"],
        "price_amount": 1200.0,
        "price_display": "1.2B",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },

    # TITLES
    {
        "category": "Titles",
        "service_key": "title_custom",
        "service_name": "Custom Titles",
        "aliases": ["custom titles", "custom title"],
        "price_amount": 0.0,
        "price_display": "Custom Quote",
        "unit_desc": "custom",
        "condition_note": "Custom price depending on title",
        "custom_quote_required": 1,
    },
    {
        "category": "Titles",
        "service_key": "title_raging_demon",
        "service_name": "Raging Demon",
        "aliases": ["raging demon", "raging demon title"],
        "price_amount": 300.0,
        "price_display": "300M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },

    # ACCESSORIES
    {
        "category": "Accessories",
        "service_key": "acc_levi_shield",
        "service_name": "Levi Shield",
        "aliases": ["levi shield", "leviathan shield"],
        "price_amount": 1200.0,
        "price_display": "1.2B",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Accessories",
        "service_key": "acc_kit_mask",
        "service_name": "Kit Mask",
        "aliases": ["kit mask", "kitsune mask"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Accessories",
        "service_key": "acc_kit_ribbon",
        "service_name": "Kit Ribbon",
        "aliases": ["kit ribbon", "kitsune ribbon"],
        "price_amount": 80.0,
        "price_display": "80M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Accessories",
        "service_key": "acc_dino_hood",
        "service_name": "Dino Hood",
        "aliases": ["dino hood"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "",
        "custom_quote_required": 0,
    },
    {
        "category": "Accessories",
        "service_key": "acc_bandana_cape",
        "service_name": "Bandana / Hunter's Cape",
        "aliases": ["bandana", "hunter cape", "hunters cape", "cape", "hunter's cape"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "",
        "condition_note": "Colour of choice",
        "custom_quote_required": 0,
    },

    # MELEE, SWORD & BLOX FRUIT MASTERY (WITHOUT 2X MASTERY)
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_100",
        "service_name": "Till 100 Mastery (Without 2x)",
        "aliases": ["100 mastery", "till 100 mastery", "100 mastery without 2x"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_200",
        "service_name": "Till 200 Mastery (Without 2x)",
        "aliases": ["200 mastery", "till 200 mastery", "200 mastery without 2x"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_300",
        "service_name": "Till 300 Mastery (Without 2x)",
        "aliases": ["300 mastery", "till 300 mastery", "300 mastery without 2x"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_400",
        "service_name": "Till 400 Mastery (Without 2x)",
        "aliases": ["400 mastery", "till 400 mastery", "400 mastery without 2x"],
        "price_amount": 80.0,
        "price_display": "80M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_500",
        "service_name": "Till 500 Mastery (Without 2x)",
        "aliases": ["500 mastery", "till 500 mastery", "500 mastery without 2x"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_no2x_600",
        "service_name": "Till 600 Mastery (Without 2x)",
        "aliases": ["600 mastery", "till 600 mastery", "600 mastery without 2x"],
        "price_amount": 120.0,
        "price_display": "120M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },

    # MELEE, SWORD & BLOX FRUIT MASTERY (WITH 2X MASTERY)
    {
        "category": "Mastery",
        "service_key": "mastery_2x_100",
        "service_name": "Till 100 Mastery (With 2x)",
        "aliases": ["100 mastery 2x", "till 100 mastery 2x", "100 mastery with 2x"],
        "price_amount": 10.0,
        "price_display": "10M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_2x_200",
        "service_name": "Till 200 Mastery (With 2x)",
        "aliases": ["200 mastery 2x", "till 200 mastery 2x", "200 mastery with 2x"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_2x_300",
        "service_name": "Till 300 Mastery (With 2x)",
        "aliases": ["300 mastery 2x", "till 300 mastery 2x", "300 mastery with 2x"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_2x_400",
        "service_name": "Till 400 Mastery (With 2x)",
        "aliases": ["400 mastery 2x", "till 400 mastery 2x", "400 mastery with 2x"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_2x_500",
        "service_name": "Till 500 Mastery (With 2x)",
        "aliases": ["500 mastery 2x", "till 500 mastery 2x", "500 mastery with 2x"],
        "price_amount": 50.0,
        "price_display": "50M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Mastery",
        "service_key": "mastery_2x_600",
        "service_name": "Till 600 Mastery (With 2x)",
        "aliases": ["600 mastery 2x", "till 600 mastery 2x", "600 mastery with 2x"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },

    # GUN MASTERY (WITHOUT 2X MASTERY)
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_no2x_200",
        "service_name": "Till 200 Gun Mastery (Without 2x)",
        "aliases": ["200 gun mastery", "till 200 gun mastery", "200 gun mastery without 2x"],
        "price_amount": 40.0,
        "price_display": "40M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_no2x_300",
        "service_name": "Till 300 Gun Mastery (Without 2x)",
        "aliases": ["300 gun mastery", "till 300 gun mastery", "300 gun mastery without 2x"],
        "price_amount": 50.0,
        "price_display": "50M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_no2x_400",
        "service_name": "Till 400 Gun Mastery (Without 2x)",
        "aliases": ["400 gun mastery", "till 400 gun mastery", "400 gun mastery without 2x"],
        "price_amount": 80.0,
        "price_display": "80M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_no2x_500",
        "service_name": "Till 500 Gun Mastery (Without 2x)",
        "aliases": ["500 gun mastery", "till 500 gun mastery", "500 gun mastery without 2x"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_no2x_600",
        "service_name": "Till 600 Gun Mastery (Without 2x)",
        "aliases": ["600 gun mastery", "till 600 gun mastery", "600 gun mastery without 2x"],
        "price_amount": 150.0,
        "price_display": "150M",
        "unit_desc": "",
        "condition_note": "Without 2x Mastery",
        "custom_quote_required": 0,
    },

    # GUN MASTERY (WITH 2X MASTERY)
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_2x_200",
        "service_name": "Till 200 Gun Mastery (With 2x)",
        "aliases": ["200 gun mastery 2x", "till 200 gun mastery 2x", "200 gun mastery with 2x"],
        "price_amount": 20.0,
        "price_display": "20M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_2x_300",
        "service_name": "Till 300 Gun Mastery (With 2x)",
        "aliases": ["300 gun mastery 2x", "till 300 gun mastery 2x", "300 gun mastery with 2x"],
        "price_amount": 30.0,
        "price_display": "30M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_2x_400",
        "service_name": "Till 400 Gun Mastery (With 2x)",
        "aliases": ["400 gun mastery 2x", "till 400 gun mastery 2x", "400 gun mastery with 2x"],
        "price_amount": 50.0,
        "price_display": "50M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_2x_500",
        "service_name": "Till 500 Gun Mastery (With 2x)",
        "aliases": ["500 gun mastery 2x", "till 500 gun mastery 2x", "500 gun mastery with 2x"],
        "price_amount": 60.0,
        "price_display": "60M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
    {
        "category": "Gun Mastery",
        "service_key": "gun_mastery_2x_600",
        "service_name": "Till 600 Gun Mastery (With 2x)",
        "aliases": ["600 gun mastery 2x", "till 600 gun mastery 2x", "600 gun mastery with 2x"],
        "price_amount": 100.0,
        "price_display": "100M",
        "unit_desc": "",
        "condition_note": "With 2x Mastery",
        "custom_quote_required": 0,
    },
]


class TopManager:
    """Enterprise Manager for Top AI Manager, Pricing, Bills, and Staff Applications."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self._cache_prices: dict[str, PriceItem] = {}
        self._cache_aliases: dict[str, str] = {}  # alias -> service_key
        self._init_database()
        self._load_prices()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self) -> None:
        """Create tables for Top AI Manager, Price Catalogue, Bills, and Staff Applications."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS top_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    service_key TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    price_amount REAL NOT NULL,
                    price_display TEXT NOT NULL,
                    unit_desc TEXT DEFAULT '',
                    condition_note TEXT DEFAULT '',
                    custom_quote_required INTEGER DEFAULT 0,
                    aliases_json TEXT DEFAULT '[]',
                    min_qty INTEGER DEFAULT 1,
                    max_qty INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    updated_at REAL NOT NULL,
                    updated_by INTEGER
                );

                CREATE TABLE IF NOT EXISTS top_price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_key TEXT NOT NULL,
                    old_price REAL,
                    new_price REAL NOT NULL,
                    old_display TEXT,
                    new_display TEXT NOT NULL,
                    changed_by INTEGER NOT NULL,
                    reason TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS top_bills (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    customer_id INTEGER,
                    customer_name TEXT DEFAULT '',
                    service_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    unit_price REAL NOT NULL,
                    unit_price_display TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    subtotal_display TEXT NOT NULL,
                    tax_rate REAL NOT NULL DEFAULT 0.0,
                    tax_amount REAL NOT NULL DEFAULT 0.0,
                    tax_display TEXT DEFAULT '',
                    total REAL NOT NULL,
                    total_display TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'UNPAID',
                    condition_notes TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    creator_id INTEGER NOT NULL,
                    creator_name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    paid_at REAL,
                    paid_by_id INTEGER,
                    paid_by_name TEXT DEFAULT '',
                    payment_message_id TEXT DEFAULT '',
                    cancelled_at REAL,
                    cancelled_by_id INTEGER,
                    cancel_reason TEXT DEFAULT '',
                    refunded_at REAL,
                    refunded_by_id INTEGER,
                    refund_reason TEXT DEFAULT '',
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS top_bill_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bill_id TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    staff_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    details TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS top_applications_config (
                    guild_id INTEGER PRIMARY KEY,
                    review_channel_id INTEGER,
                    role_on_accept_id INTEGER,
                    cooldown_days INTEGER DEFAULT 7,
                    default_tax REAL DEFAULT 0.0,
                    panel_message_id INTEGER,
                    panel_channel_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS top_billing_config (
                    guild_id INTEGER PRIMARY KEY,
                    billing_channel_id INTEGER,
                    tax_rate REAL DEFAULT 5.0,
                    currency_unit TEXT DEFAULT 'Beli',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS top_applications (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    applicant_id INTEGER NOT NULL,
                    applicant_name TEXT NOT NULL,
                    position TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    reviewer_id INTEGER,
                    reviewer_name TEXT DEFAULT '',
                    decision_reason TEXT DEFAULT '',
                    staff_notes TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_top_bills_guild ON top_bills(guild_id);
                CREATE INDEX IF NOT EXISTS idx_top_bills_status ON top_bills(status);
                CREATE INDEX IF NOT EXISTS idx_top_bills_customer ON top_bills(customer_id);
                CREATE INDEX IF NOT EXISTS idx_top_bills_created ON top_bills(created_at);
                CREATE INDEX IF NOT EXISTS idx_top_bills_paid ON top_bills(paid_at);
                CREATE INDEX IF NOT EXISTS idx_top_bills_msg ON top_bills(payment_message_id);
                CREATE INDEX IF NOT EXISTS idx_top_apps_guild ON top_applications(guild_id);
                CREATE INDEX IF NOT EXISTS idx_top_apps_status ON top_applications(status);
                CREATE INDEX IF NOT EXISTS idx_top_apps_applicant ON top_applications(applicant_id);
            """)

            # Safe non-destructive schema migrations for Appy-Style Applications
            cols_cfg = {row[1] for row in conn.execute("PRAGMA table_info(top_applications_config)").fetchall()}
            if "is_open" not in cols_cfg:
                conn.execute("ALTER TABLE top_applications_config ADD COLUMN is_open INTEGER DEFAULT 1;")
            if "reviewer_role_id" not in cols_cfg:
                conn.execute("ALTER TABLE top_applications_config ADD COLUMN reviewer_role_id INTEGER;")
            if "audit_channel_id" not in cols_cfg:
                conn.execute("ALTER TABLE top_applications_config ADD COLUMN audit_channel_id INTEGER;")
            if "positions_json" not in cols_cfg:
                conn.execute("ALTER TABLE top_applications_config ADD COLUMN positions_json TEXT;")

            cols_app = {row[1] for row in conn.execute("PRAGMA table_info(top_applications)").fetchall()}
            if "review_message_id" not in cols_app:
                conn.execute("ALTER TABLE top_applications ADD COLUMN review_message_id INTEGER;")

            # Safe non-destructive schema migrations for Blox Fruits Billing System
            cols_bills = {row[1] for row in conn.execute("PRAGMA table_info(top_bills)").fetchall()}
            if "payment_type" not in cols_bills:
                conn.execute("ALTER TABLE top_bills ADD COLUMN payment_type TEXT DEFAULT 'Beli';")
            if "currency_unit" not in cols_bills:
                conn.execute("ALTER TABLE top_bills ADD COLUMN currency_unit TEXT DEFAULT 'Beli';")
            if "fruit_details" not in cols_bills:
                conn.execute("ALTER TABLE top_bills ADD COLUMN fruit_details TEXT DEFAULT '';")
            if "posted_channel_id" not in cols_bills:
                conn.execute("ALTER TABLE top_bills ADD COLUMN posted_channel_id INTEGER DEFAULT 0;")
            if "posted_message_id" not in cols_bills:
                conn.execute("ALTER TABLE top_bills ADD COLUMN posted_message_id TEXT DEFAULT '';")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS top_pricing_policy (
                    guild_id INTEGER PRIMARY KEY,
                    custom_markup_pct REAL DEFAULT 0.0,
                    large_order_surcharge_pct REAL DEFAULT 0.0,
                    max_auto_increase_pct REAL DEFAULT 50.0,
                    approval_threshold_amount REAL DEFAULT 500.0,
                    updated_at REAL NOT NULL,
                    updated_by INTEGER
                );
            """)

            # Seed initial catalogue if table is empty

            count = conn.execute("SELECT COUNT(*) FROM top_prices").fetchone()[0]
            if count == 0:
                now = time.time()
                for p in INITIAL_PRICES:
                    conn.execute("""
                        INSERT INTO top_prices (
                            category, service_key, service_name, price_amount, price_display,
                            unit_desc, condition_note, custom_quote_required, aliases_json,
                            min_qty, max_qty, is_active, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (
                        p["category"],
                        p["service_key"],
                        p["service_name"],
                        p["price_amount"],
                        p["price_display"],
                        p.get("unit_desc", ""),
                        p.get("condition_note", ""),
                        p.get("custom_quote_required", 0),
                        json.dumps(p.get("aliases", [])),
                        p.get("min_qty", 1),
                        p.get("max_qty", 1),
                        now,
                    ))
                conn.commit()
                logger.info(f"Seeded {len(INITIAL_PRICES)} official Blox Fruits service prices.")

    def _load_prices(self) -> None:
        """Load active price catalog into sub-millisecond memory cache."""
        self._cache_prices.clear()
        self._cache_aliases.clear()

        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM top_prices WHERE is_active = 1").fetchall()
            for r in rows:
                aliases = json.loads(r["aliases_json"]) if r["aliases_json"] else []
                item = PriceItem(
                    category=r["category"],
                    service_key=r["service_key"],
                    service_name=r["service_name"],
                    price_amount=float(r["price_amount"]),
                    price_display=r["price_display"],
                    unit_desc=r["unit_desc"] or "",
                    condition_note=r["condition_note"] or "",
                    custom_quote_required=int(r["custom_quote_required"]),
                    aliases=aliases,
                    min_qty=int(r["min_qty"] or 1),
                    max_qty=int(r["max_qty"] or 1),
                )
                self._cache_prices[item.service_key] = item

                # Map exact service name and aliases to key
                self._cache_aliases[item.service_name.lower().strip()] = item.service_key
                for a in aliases:
                    self._cache_aliases[a.lower().strip()] = item.service_key

    # ─────────────────────────────────────────────────────────────────────────
    # 2. DECIMAL-SAFE TAX & ARITHMETIC CALCULATOR
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def calculate_tax(subtotal: float, tax_percentage: float) -> tuple[float, float]:
        """Decimal-safe tax arithmetic:
        tax_amount = subtotal * (tax_percentage / 100)
        total = subtotal + tax_amount
        """
        if tax_percentage < 0 or tax_percentage > 100:
            raise ValueError(f"Tax percentage ({tax_percentage}%) must be between 0% and 100%.")

        dec_sub = Decimal(str(subtotal))
        dec_tax_rate = Decimal(str(tax_percentage)) / Decimal("100")
        dec_tax_amt = (dec_sub * dec_tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        dec_total = (dec_sub + dec_tax_amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return float(dec_tax_amt), float(dec_total)

    @staticmethod
    def format_price(amount: float) -> str:
        """Format price in millions (M) or billions (B)."""
        if amount >= 1000.0:
            b_val = amount / 1000.0
            return f"{b_val:.1f}B" if b_val % 1 != 0 else f"{int(b_val)}B"
        return f"{amount:.1f}M" if amount % 1 != 0 else f"{int(amount)}M"

    # ─────────────────────────────────────────────────────────────────────────
    # 3. PRICE LOOKUP & CALCULATION ENGINE
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_prices(self) -> list[PriceItem]:
        """Return all active price catalogue items."""
        return list(self._cache_prices.values())

    def get_price(self, service_key: str) -> Optional[PriceItem]:
        """Get price item by service key, alias, or normalized name."""
        norm = service_key.lower().strip()
        if norm in self._cache_prices:
            return self._cache_prices[norm]
        if norm in self._cache_aliases:
            return self._cache_prices[self._cache_aliases[norm]]

        # Cleaned normalization
        clean_norm = re.sub(r'[^a-z0-9 ]', ' ', norm)
        clean_norm = re.sub(r'\s+', ' ', clean_norm).strip()
        if clean_norm in self._cache_aliases:
            return self._cache_prices[self._cache_aliases[clean_norm]]

        for item in self._cache_prices.values():
            item_clean = re.sub(r'[^a-z0-9 ]', ' ', item.service_name.lower())
            item_clean = re.sub(r'\s+', ' ', item_clean).strip()
            if clean_norm == item_clean:
                return item
            for a in item.aliases:
                a_clean = re.sub(r'[^a-z0-9 ]', ' ', a.lower())
                a_clean = re.sub(r'\s+', ' ', a_clean).strip()
                if clean_norm == a_clean:
                    return item
        return None

    def search_prices(self, query: str) -> list[PriceItem]:
        """Smart search matching category, service name, or aliases."""
        q = query.lower().strip()
        q_clean = re.sub(r'[^a-z0-9 ]', ' ', q)
        q_clean = re.sub(r'\s+', ' ', q_clean).strip()
        matches = []
        for item in self._cache_prices.values():
            name_clean = re.sub(r'[^a-z0-9 ]', ' ', item.service_name.lower())
            name_clean = re.sub(r'\s+', ' ', name_clean).strip()
            if q_clean in name_clean or name_clean in q_clean or q in item.category.lower():
                matches.append(item)
                continue
            for a in item.aliases:
                a_clean = re.sub(r'[^a-z0-9 ]', ' ', a.lower())
                a_clean = re.sub(r'\s+', ' ', a_clean).strip()
                if q_clean in a_clean or a_clean in q_clean:
                    matches.append(item)
                    break
        return matches

    def parse_top_query(self, query: str, tax_override: Optional[float] = None) -> dict[str, Any]:
        """Universal smart intent and price parser for '?top ...' and '?top price ...'.
        Recognizes natural language queries, quantities, version tags, aliases, conditions,
        overlapping boundaries, clarifications, and optional decimal-safe tax.
        """
        raw = query.strip()
        low = raw.lower()

        # 1. Intent check
        is_make_bill = any(
            phrase in low for phrase in [
                "make bill", "make a bill", "create bill", "generate bill", "new bill"
            ]
        )

        # 2. Extract Tax percentage
        tax_rate = 0.0
        tax_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:tax)?', low)
        if tax_match:
            try:
                tax_rate = float(tax_match.group(1))
            except ValueError:
                pass
        else:
            tax_match_alt = re.search(r'tax\s*(?:of|at|is)?\s*(\d+(?:\.\d+)?)\s*%?', low)
            if tax_match_alt:
                try:
                    tax_rate = float(tax_match_alt.group(1))
                except ValueError:
                    pass

        if tax_override is not None and tax_rate == 0.0:
            tax_rate = float(tax_override)

        # Clean query of filler prefixes and tax substrings
        cleaned = low
        cleaned = re.sub(r'with\s*\d+(?:\.\d+)?\s*%\s*tax', ' ', cleaned)
        cleaned = re.sub(r'\d+(?:\.\d+)?\s*%\s*tax', ' ', cleaned)
        cleaned = re.sub(r'tax\s*\d+(?:\.\d+)?\s*%?', ' ', cleaned)
        cleaned = re.sub(r'\bplus\s*\d+(?:\.\d+)?\s*%\b', ' ', cleaned)

        prefixes = [
            r"^(?:what(?:'s| is)? (?:the )?(?:price|cost) of)\s+",
            r"^(?:what(?:'s| is)? (?:the )?(?:price|cost) for)\s+",
            r"^(?:how much (?:is|for))\s+",
            r"^(?:what(?:'s| is))\s+",
            r"^(?:price of|cost of)\s+",
            r"^(?:price for|cost for)\s+",
            r"^(?:calculate)\s+",
            r"^(?:make (?:a )?bill (?:for|of))\s+",
            r"^(?:create (?:a )?bill (?:for|of))\s+",
            r"^(?:bill (?:for|of))\s+",
            r"^(?:price)\s+",
            r"^(?:of)\s+",
        ]
        for p in prefixes:
            cleaned = re.sub(p, '', cleaned).strip()

        cleaned = re.sub(r'[?.,!]', ' ', cleaned).strip()
        norm = re.sub(r'\s+', ' ', cleaned).strip()

        # Comparison Query: e.g. "compare 5 raids with 10 raids" or "compare the price of 5 normal raids with 10 normal raids"
        comp_m = re.match(r'^compare\b(?:\s+the)?(?:\s+(?:price|cost))?(?:\s+of)?\s+(.+?)\s+(?:with|to|vs|and)\s+(.+)$', norm, re.I)
        if comp_m:
            item1_str = comp_m.group(1).strip()
            item2_str = comp_m.group(2).strip()
            try:
                res1 = self.parse_top_query(item1_str, tax_override=tax_rate)
                res2 = self.parse_top_query(item2_str, tax_override=tax_rate)
                c1 = res1["calculation"]
                c2 = res2["calculation"]
                multi_comp = MultiCalculationResult(
                    items=[c1, c2],
                    subtotal=0.0,
                    subtotal_display="",
                    tax_rate=tax_rate,
                    tax_amount=0.0,
                    tax_display="",
                    total=0.0,
                    total_display="",
                    service_name=f"Comparison: {c1.service_name} vs {c2.service_name}",
                    comparison_mode=True,
                    clarification_needed=(c1.is_clarification or c2.is_clarification),
                    clarifications=[c for c in (c1, c2) if c.is_clarification],
                )
                return {
                    "intent": "price_lookup",
                    "calculation": multi_comp,
                    "multi_calculation": multi_comp,
                    "quantity": 2,
                    "tax_rate": tax_rate,
                    "raw_query": raw,
                }
            except Exception:
                pass

        # Multi-Item Query: e.g. "10 normal raids and 1 max race" or "2 trials and dough king"
        # We split on ' and ' or ',' or ' + ' (ignoring composite names like 'mirage + blue gear')
        if (" and " in norm or ", " in norm or (" + " in norm and "mirage" not in norm)) and "mirage and blue gear" not in norm and "mirage + blue gear" not in norm and "mirage plus blue gear" not in norm:
            multi_parts = [p.strip() for p in re.split(r'\s+and\s+|,\s*|\s*\+\s*', norm) if p.strip()]
            if len(multi_parts) > 1:
                item_calcs: list[CalculationResult] = []
                all_ok = True
                for part in multi_parts:
                    try:
                        part_res = self.parse_top_query(part, tax_override=0.0)
                        part_calc = part_res.get("calculation")
                        if isinstance(part_calc, CalculationResult):
                            item_calcs.append(part_calc)
                        elif isinstance(part_calc, MultiCalculationResult):
                            item_calcs.extend(part_calc.items)
                        else:
                            all_ok = False
                            break
                    except Exception:
                        all_ok = False
                        break

                if all_ok and len(item_calcs) > 1:
                    subtot = sum(c.subtotal for c in item_calcs)
                    tax_amt, tot = self.calculate_tax(subtot, tax_rate)
                    has_custom = any(c.custom_quote for c in item_calcs)
                    clarifs = [c for c in item_calcs if c.is_clarification]
                    multi_calc = MultiCalculationResult(
                        items=item_calcs,
                        subtotal=subtot,
                        subtotal_display=self.format_price(subtot) if not has_custom else "Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=tax_amt,
                        tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                        total=tot,
                        total_display=self.format_price(tot) if not has_custom else "Custom Quote",
                        service_name=" + ".join(c.service_name for c in item_calcs),
                        clarification_needed=len(clarifs) > 0,
                        clarifications=clarifs,
                        requires_staff_approval=any(c.requires_staff_approval for c in item_calcs) or tot >= 500.0,
                    )
                    return {
                        "intent": "make_bill" if is_make_bill else "price_lookup",
                        "calculation": multi_calc,
                        "multi_calculation": multi_calc,
                        "quantity": sum(c.quantity for c in item_calcs),
                        "tax_rate": tax_rate,
                        "raw_query": raw,
                    }

        # ─────────────────────────────────────────────────────────────────────
        # A. BELI FARMING
        # ─────────────────────────────────────────────────────────────────────

        if "beli" in norm or "money" in norm:
            m_amt = re.search(r'\b(5|10|15|20|25|30)\s*(?:m|million)?\b', norm)
            target_amt = int(m_amt.group(1)) if m_amt else 10
            is_plus = "30+" in norm or "30m+" in norm

            has_2x = ("with 2x" in norm or "2x money" in norm or "2x" in norm) and not ("without 2x" in norm or "no 2x" in norm)
            has_no2x = "without 2x" in norm or "no 2x" in norm or "1x" in norm

            if not has_2x and not has_no2x:
                p_2x = self.get_price(f"beli_2x_{target_amt}m")
                p_no2x = self.get_price(f"beli_no2x_{target_amt}m")
                p_2x_str = p_2x.price_display if p_2x else "Custom Quote"
                p_no2x_str = p_no2x.price_display if p_no2x else "Custom Quote"
                return {
                    "intent": "price_lookup",
                    "calculation": CalculationResult(
                        service_name=f"{target_amt}M Beli Farming",
                        category="Beli Farming",
                        quantity=1,
                        unit_price=0.0,
                        unit_display="",
                        subtotal=0.0,
                        subtotal_display="",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="",
                        total=0.0,
                        total_display="",
                        is_clarification=True,
                        clarification_title="❓ TOP AI MANAGER • CLARIFICATION NEEDED",
                        clarification_options=[
                            f"For **{target_amt}M Beli farming**, please specify your 2x Money status:",
                            f"• **With 2x Money:** **{p_2x_str}**",
                            f"• **Without 2x Money:** **{p_no2x_str}**",
                            f"*Ask: `?top price {target_amt}M Beli with 2x money` or `without 2x money`*",
                        ],
                    ),
                    "quantity": 1,
                    "tax_rate": tax_rate,
                    "raw_query": raw,
                }

            if has_2x:
                if target_amt == 25:
                    calc = CalculationResult(
                        service_name="25M Beli (With 2x Money)",
                        category="Beli Farming",
                        quantity=1,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        condition_note="With 2x Money • Tier not listed in official catalogue",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}
                elif target_amt >= 30 and (is_plus or target_amt > 30):
                    calc = CalculationResult(
                        service_name="30M+ Beli (With 2x Money)",
                        category="Beli Farming",
                        quantity=1,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        condition_note="30M+ Beli requires custom quote",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}
                else:
                    item = self.get_price(f"beli_2x_{target_amt}m")
            else:
                if target_amt >= 30:
                    calc = CalculationResult(
                        service_name="30M+ Beli (Without 2x Money)",
                        category="Beli Farming",
                        quantity=1,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        condition_note="30M+ Beli requires custom quote",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}
                else:
                    item = self.get_price(f"beli_no2x_{target_amt}m")

            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=1,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note=f"Farmed Beli: {target_amt}M • Service Price: {item.price_display}",
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # B. MASTERY & GUN MASTERY
        # ─────────────────────────────────────────────────────────────────────
        if "mastery" in norm:
            is_gun = "gun" in norm or "guns" in norm
            m_lvl = re.search(r'\b(100|200|300|400|500|600)\b', norm)
            target_lvl = int(m_lvl.group(1)) if m_lvl else 300

            has_2x = ("with 2x" in norm or "2x mastery" in norm or "2x" in norm) and not ("without 2x" in norm or "no 2x" in norm)
            has_no2x = "without 2x" in norm or "no 2x" in norm or "1x" in norm

            if not has_2x and not has_no2x:
                if is_gun:
                    p_2x = self.get_price(f"gun_mastery_2x_{target_lvl}")
                    p_no2x = self.get_price(f"gun_mastery_no2x_{target_lvl}")
                    svc = f"Till {target_lvl} Gun Mastery"
                else:
                    p_2x = self.get_price(f"mastery_2x_{target_lvl}")
                    p_no2x = self.get_price(f"mastery_no2x_{target_lvl}")
                    svc = f"Till {target_lvl} Mastery"

                p_2x_str = p_2x.price_display if p_2x else "N/A"
                p_no2x_str = p_no2x.price_display if p_no2x else "N/A"
                return {
                    "intent": "price_lookup",
                    "calculation": CalculationResult(
                        service_name=svc,
                        category="Gun Mastery" if is_gun else "Mastery",
                        quantity=1,
                        unit_price=0.0,
                        unit_display="",
                        subtotal=0.0,
                        subtotal_display="",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="",
                        total=0.0,
                        total_display="",
                        is_clarification=True,
                        clarification_title="❓ TOP AI MANAGER • CLARIFICATION NEEDED",
                        clarification_options=[
                            f"For **{svc}**, please specify your 2x Mastery status:",
                            f"• **With 2x Mastery:** **{p_2x_str}**",
                            f"• **Without 2x Mastery:** **{p_no2x_str}**",
                            f"*Ask: `?top price {svc} with 2x mastery` or `without 2x mastery`*",
                        ],
                    ),
                    "quantity": 1,
                    "tax_rate": tax_rate,
                    "raw_query": raw,
                }

            prefix = "gun_mastery" if is_gun else "mastery"
            cond_str = "2x" if has_2x else "no2x"
            item = self.get_price(f"{prefix}_{cond_str}_{target_lvl}")
            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=1,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note=item.condition_note,
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # C. LEVELS
        # ─────────────────────────────────────────────────────────────────────
        if "level" in norm or "lvl" in norm:
            if "max" in norm:
                item = self.get_price("level_max")
            else:
                m_lvl = re.search(r'\b(100|200|300|400|500|1000)\b', norm)
                if m_lvl:
                    item = self.get_price(f"level_{m_lvl.group(1)}")
                else:
                    item = self.get_price("level_100")
            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=1,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # D. RAIDS (NORMAL, ADVANCE, ORDER, or AMBIGUOUS)
        # ─────────────────────────────────────────────────────────────────────
        if "raid" in norm or "raids" in norm:
            is_adv = "advance" in norm or "adv" in norm
            is_ord = "order" in norm or "law" in norm
            is_norm = "normal" in norm

            m_q = re.search(r'\b(\d+)\b', norm)
            qty = int(m_q.group(1)) if m_q else 1

            if not is_adv and not is_ord and not is_norm:
                # AMBIGUOUS: Could be Normal, Advance, or Order Raids!
                if qty <= 5: p_norm = "10M (1–5 Raids)"
                elif qty <= 10: p_norm = "20M (6–10 Raids)"
                elif qty <= 15: p_norm = "30M (11–15 Raids)"
                elif qty <= 20: p_norm = "50M (16–20 Raids)"
                elif qty <= 25: p_norm = "60M (20–25 Raids)"
                else: p_norm = "Custom Quote"

                if qty <= 2: p_adv = "10M (1–2 Raids)"
                elif qty <= 4: p_adv = "20M (3–4 Raids)"
                elif qty == 5: p_adv = "30M (5 Raids)"
                elif qty <= 8: p_adv = "60M (6–8 Raids)"
                else: p_adv = "Custom Quote"

                if qty == 1: p_ord = "10M (1 Raid)"
                elif qty == 2: p_ord = "20M (2 Raids)"
                elif qty <= 5: p_ord = "60M (3–5 Raids)"
                elif qty <= 8: p_ord = "120M (6–8 Raids)"
                elif qty <= 10: p_ord = "150M (8–10 Raids)"
                else: p_ord = "Custom Quote"

                return {
                    "intent": "price_lookup",
                    "calculation": CalculationResult(
                        service_name=f"{qty} Raids",
                        category="Raids",
                        quantity=qty,
                        unit_price=0.0,
                        unit_display="",
                        subtotal=0.0,
                        subtotal_display="",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="",
                        total=0.0,
                        total_display="",
                        is_clarification=True,
                        clarification_title="❓ TOP AI MANAGER • CLARIFICATION NEEDED",
                        clarification_options=[
                            f"Your request for **{qty} raids** matches multiple raid categories. Which one did you mean?",
                            f"• **Normal Raids:** **{p_norm}**",
                            f"• **Advance Raids:** **{p_adv}**",
                            f"• **Order Raids:** **{p_ord}**",
                            f"*Please specify: `normal raids`, `advance raids`, or `order raids`.*",
                        ],
                    ),
                    "quantity": qty,
                    "tax_rate": tax_rate,
                    "raw_query": raw,
                }

            if is_norm:
                if qty == 20:
                    p_tier1 = self.get_price("normal_raid_16_20")
                    p_tier2 = self.get_price("normal_raid_20_25")
                    tax_amt, tot = self.calculate_tax(p_tier1.price_amount, tax_rate)
                    return {
                        "intent": "price_lookup",
                        "calculation": CalculationResult(
                            service_name="20 Normal Raids",
                            category="Normal Raids",
                            quantity=20,
                            unit_price=p_tier1.price_amount,
                            unit_display=p_tier1.price_display,
                            subtotal=p_tier1.price_amount,
                            subtotal_display=p_tier1.price_display,
                            tax_rate=tax_rate,
                            tax_amount=tax_amt,
                            tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                            total=tot,
                            total_display=self.format_price(tot),
                            ambiguity_note="Overlapping tier at 20 raids: Tier 16–20 (50M) vs Tier 20–25 (60M). Defaulting to 50M.",
                            is_clarification=True,
                            clarification_title="❓ TOP AI MANAGER • OVERLAPPING BOUNDARY",
                            clarification_options=[
                                "Normal Raids has overlapping tiers at **20 raids** in the official price list:",
                                f"• **Tier 16–20:** **{p_tier1.price_display}**",
                                f"• **Tier 20–25:** **{p_tier2.price_display}**",
                                "*(Defaulting to 50M per tier 16–20. Please confirm with staff if tier 20–25 applies.)*",
                            ],
                        ),
                        "quantity": 20,
                        "tax_rate": tax_rate,
                        "raw_query": raw,
                    }
                if qty > 25:
                    calc = CalculationResult(
                        service_name=f"{qty} Normal Raids",
                        category="Normal Raids",
                        quantity=qty,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
                elif qty >= 21: item = self.get_price("normal_raid_20_25")
                elif qty >= 16: item = self.get_price("normal_raid_16_20")
                elif qty >= 11: item = self.get_price("normal_raid_11_15")
                elif qty >= 6: item = self.get_price("normal_raid_6_10")
                else: item = self.get_price("normal_raid_1_5")

            elif is_adv:
                if qty > 8:
                    calc = CalculationResult(
                        service_name=f"{qty} Advance Raids",
                        category="Advance Raids",
                        quantity=qty,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
                elif qty >= 6: item = self.get_price("adv_raid_6_8")
                elif qty == 5: item = self.get_price("adv_raid_5")
                elif qty >= 3: item = self.get_price("adv_raid_3_4")
                else: item = self.get_price("adv_raid_1_2")

            else: # is_ord
                if qty == 8:
                    p_tier1 = self.get_price("order_raid_6_8")
                    p_tier2 = self.get_price("order_raid_8_10")
                    tax_amt, tot = self.calculate_tax(p_tier1.price_amount, tax_rate)
                    return {
                        "intent": "price_lookup",
                        "calculation": CalculationResult(
                            service_name="8 Order Raids",
                            category="Order Raids",
                            quantity=8,
                            unit_price=p_tier1.price_amount,
                            unit_display=p_tier1.price_display,
                            subtotal=p_tier1.price_amount,
                            subtotal_display=p_tier1.price_display,
                            tax_rate=tax_rate,
                            tax_amount=tax_amt,
                            tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                            total=tot,
                            total_display=self.format_price(tot),
                            ambiguity_note="Overlapping tier at 8 raids: Tier 6–8 (120M) vs Tier 8–10 (150M). Defaulting to 120M.",
                            is_clarification=True,
                            clarification_title="❓ TOP AI MANAGER • OVERLAPPING BOUNDARY",
                            clarification_options=[
                                "Order Raids has overlapping tiers at **8 raids** in the official price list:",
                                f"• **Tier 6–8:** **{p_tier1.price_display}**",
                                f"• **Tier 8–10:** **{p_tier2.price_display}**",
                                "*(Defaulting to 120M per tier 6–8. Please confirm with staff if tier 8–10 applies.)*",
                            ],
                        ),
                        "quantity": 8,
                        "tax_rate": tax_rate,
                        "raw_query": raw,
                    }
                if qty > 10:
                    calc = CalculationResult(
                        service_name=f"{qty} Order Raids",
                        category="Order Raids",
                        quantity=qty,
                        unit_price=0.0,
                        unit_display="Custom Quote",
                        subtotal=0.0,
                        subtotal_display="Custom Quote",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="Custom Quote",
                        total=0.0,
                        total_display="Custom Quote",
                        custom_quote=True,
                    )
                    return {"intent": "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
                elif qty >= 9: item = self.get_price("order_raid_8_10")
                elif qty >= 6: item = self.get_price("order_raid_6_8")
                elif qty >= 3: item = self.get_price("order_raid_3_5")
                elif qty == 2: item = self.get_price("order_raid_2")
                else: item = self.get_price("order_raid_1")

            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=qty,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # E. TRIALS
        # ─────────────────────────────────────────────────────────────────────
        if "trial" in norm or "trials" in norm or "max race" in norm:
            if "draco" in norm:
                m_q = re.search(r'\b(\d+)\b', norm)
                qty = int(m_q.group(1)) if m_q else 1
                item = self.get_price("trial_draco")
                subtotal = item.price_amount * qty
                tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
                calc = CalculationResult(
                    service_name=f"{qty} Draco Trial{'s' if qty > 1 else ''}" if qty > 1 else "Draco Trial",
                    category=item.category,
                    quantity=qty,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=subtotal,
                    subtotal_display=self.format_price(subtotal),
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
            elif "tushita" in norm:
                m_q = re.search(r'\b(\d+)\b', norm)
                qty = int(m_q.group(1)) if m_q else 1
                item = self.get_price("sword_tushita_scroll")
                subtotal = item.price_amount * qty
                tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
                calc = CalculationResult(
                    service_name=f"{qty} Tushita Scroll Trial{'s' if qty > 1 else ''}",
                    category=item.category,
                    quantity=qty,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=subtotal,
                    subtotal_display=self.format_price(subtotal),
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
            elif "yama" in norm:
                m_q = re.search(r'\b(\d+)\b', norm)
                qty = int(m_q.group(1)) if m_q else 1
                item = self.get_price("sword_yama_scroll")
                subtotal = item.price_amount * qty
                tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
                calc = CalculationResult(
                    service_name=f"{qty} Yama Scroll Trial{'s' if qty > 1 else ''}",
                    category=item.category,
                    quantity=qty,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=subtotal,
                    subtotal_display=self.format_price(subtotal),
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}
            elif "max race package" in norm or "max race" in norm or "race package" in norm:
                m_extra = re.search(r'(?:with|\+)\s*(\d+)\s*(?:extra\s*)?training', norm)
                if m_extra:
                    extra_count = int(m_extra.group(1))
                    item = self.get_price("trial_max_race_package")
                    tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                    calc = CalculationResult(
                        service_name="Max Race Package (Training Included)",
                        category="Trials",
                        quantity=1,
                        unit_price=item.price_amount,
                        unit_display=item.price_display,
                        subtotal=item.price_amount,
                        subtotal_display=item.price_display,
                        tax_rate=tax_rate,
                        tax_amount=tax_amt,
                        tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                        total=tot,
                        total_display=self.format_price(tot),
                        condition_note=f"Max Race Package ({item.price_display}) explicitly includes full training. No additional charge added for {extra_count} trainings.",
                        pricing_explanation="Complete training is already included in the 150M Max Race Package.",
                    )
                    return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}
                item = self.get_price("trial_max_race_package")
            elif "max trial" in norm or "max trials" in norm or "full trial" in norm:
                m_extra = re.search(r'(?:with|\+)\s*(\d+)\s*(?:extra\s*)?training', norm)
                if m_extra:
                    extra_count = int(m_extra.group(1))
                    training_cost = extra_count * 10.0
                    subtotal = 100.0 + training_cost
                    tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
                    calc = CalculationResult(
                        service_name=f"Max Trial + {extra_count} Extra Trainings",
                        category="Trials",
                        quantity=1,
                        unit_price=subtotal,
                        unit_display=self.format_price(subtotal),
                        subtotal=subtotal,
                        subtotal_display=self.format_price(subtotal),
                        tax_rate=tax_rate,
                        tax_amount=tax_amt,
                        tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                        total=tot,
                        total_display=self.format_price(tot),
                        condition_note=f"Max Trial: 100M (training not included) + {extra_count} gear trainings (+{int(training_cost)}M)",
                        pricing_explanation=f"Base Max Trial (100M) + {extra_count}x 10M gear training.",
                    )
                    return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}
                item = self.get_price("trial_max")
            elif "training" in norm:
                item = self.get_price("trial_training")
            else:
                m_q = re.search(r'\b(\d+)\b', norm)
                qty = int(m_q.group(1)) if m_q else 1
                if qty == 2 or "2 trial" in norm or "two trial" in norm:
                    item = self.get_price("trial_2")
                elif qty == 3 or "3 trial" in norm or "three trial" in norm:
                    item = self.get_price("trial_3")
                elif qty == 1 or "1 trial" in norm or "one trial" in norm or "single trial" in norm:
                    item = self.get_price("trial_1")
                else:
                    # Unlisted trials package (catalogue defines 1, 2, 3 trials and Max Trial)
                    provisional_subtotal = qty * 20.0
                    tax_amt, tot = self.calculate_tax(provisional_subtotal, tax_rate)
                    calc = CalculationResult(
                        service_name=f"{qty} Trials [Unlisted Package]",
                        category="Trials",
                        quantity=qty,
                        unit_price=20.0,
                        unit_display="20M/trial (Provisional)",
                        subtotal=provisional_subtotal,
                        subtotal_display=f"{self.format_price(provisional_subtotal)} (Provisional)",
                        tax_rate=tax_rate,
                        tax_amount=tax_amt,
                        tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                        total=tot,
                        total_display=f"{self.format_price(tot)} (Provisional)",
                        is_provisional=True,
                        is_clarification=True,
                        clarification_title=f"❓ CLARIFICATION NEEDED • {qty} Trials",
                        clarification_options=[
                            f"The catalogue defines 1 Trial (20M), 2 Trials (40M), 3 Trials (60M), and Max Trial (100M).",
                            f"• **Provisional Calculation:** **{self.format_price(provisional_subtotal)}** ({qty}x 20M/trial)",
                            f"• **Or choose listed package:** **Max Trial (100M)** for all remaining trials",
                            f"*Please confirm with staff for unlisted quantities.*",
                        ],
                        condition_note=f"The catalogue does not define a {qty}-trial package. Provisional quote at 20M/trial; consider Max Trial (100M).",
                        pricing_explanation=f"Catalogue does not list a {qty}-trial package. Provisional rate at 20M per trial or consider Max Trial (100M).",
                        requires_staff_approval=True,
                    )
                    return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}

            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=item.min_qty,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note=item.condition_note,
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": item.min_qty, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # F. DRACO (DRACO V1, V2, V3, V4, MAX V4)
        # ─────────────────────────────────────────────────────────────────────
        if "draco" in norm:
            if "max" in norm or "draco max" in norm:
                item = self.get_price("draco_max_v4")
            elif "v4" in norm:
                item = self.get_price("draco_v4")
            elif "v3" in norm:
                item = self.get_price("draco_v3")
            elif "v2" in norm:
                item = self.get_price("draco_v2")
            elif "v1" in norm:
                item = self.get_price("draco_v1")
            else:
                item = self.get_price("draco_v1")

            if item:
                tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
                calc = CalculationResult(
                    service_name=item.service_name,
                    category=item.category,
                    quantity=1,
                    unit_price=item.price_amount,
                    unit_display=item.price_display,
                    subtotal=item.price_amount,
                    subtotal_display=item.price_display,
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note=item.condition_note,
                )
                return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # G. SEA EVENTS
        # ─────────────────────────────────────────────────────────────────────
        if "mirage" in norm:
            if "blue gear" in norm or "+" in norm:
                item = self.get_price("sea_mirage_blue_gear")
            else:
                item = self.get_price("sea_mirage")
            tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
            calc = CalculationResult(
                service_name=item.service_name,
                category=item.category,
                quantity=1,
                unit_price=item.price_amount,
                unit_display=item.price_display,
                subtotal=item.price_amount,
                subtotal_display=item.price_display,
                tax_rate=tax_rate,
                tax_amount=tax_amt,
                tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                total=tot,
                total_display=self.format_price(tot),
            )
            return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        if "prehistoric" in norm:
            m_q = re.search(r'\b(\d+)\b', norm)
            qty = int(m_q.group(1)) if m_q else 1

            is_carry = "carry" in norm and not ("not carry" in norm or "no carry" in norm)
            is_not_carry = "not carry" in norm or "no carry" in norm

            if not is_carry and not is_not_carry:
                p_nc = self.get_price("sea_prehistoric_not_carry")
                p_c = self.get_price("sea_prehistoric_carry")
                return {
                    "intent": "price_lookup",
                    "calculation": CalculationResult(
                        service_name="Prehistoric Island",
                        category="Sea Events",
                        quantity=qty,
                        unit_price=0.0,
                        unit_display="",
                        subtotal=0.0,
                        subtotal_display="",
                        tax_rate=tax_rate,
                        tax_amount=0.0,
                        tax_display="",
                        total=0.0,
                        total_display="",
                        is_clarification=True,
                        clarification_title="❓ TOP AI MANAGER • CLARIFICATION NEEDED",
                        clarification_options=[
                            "For **Prehistoric Island**, please specify carry status:",
                            f"• **Not Carry:** **{p_nc.price_display}** per island",
                            f"• **Carry:** **{p_c.price_display}** per island",
                            "*Ask: `?top price Prehistoric Island carry` or `not carry`*",
                        ],
                    ),
                    "quantity": qty,
                    "tax_rate": tax_rate,
                    "raw_query": raw,
                }

            item = self.get_price("sea_prehistoric_carry" if is_carry else "sea_prehistoric_not_carry")
            subtotal = item.price_amount * qty
            tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
            calc = CalculationResult(
                service_name=item.service_name,
                category=item.category,
                quantity=qty,
                unit_price=item.price_amount,
                unit_display=item.price_display,
                subtotal=subtotal,
                subtotal_display=self.format_price(subtotal),
                tax_rate=tax_rate,
                tax_amount=tax_amt,
                tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                total=tot,
                total_display=self.format_price(tot),
                condition_note=item.condition_note,
            )
            return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # H. BOSSES
        # ─────────────────────────────────────────────────────────────────────
        if "dough king" in norm or norm == "dk":
            item = self.get_price("boss_dough_king")
        elif "cake prince" in norm or norm == "cp":
            item = self.get_price("boss_cake_prince")
        elif "soul reaper" in norm:
            item = self.get_price("boss_soul_reaper")
        elif "dark beard" in norm or "darkbeard" in norm:
            item = self.get_price("boss_dark_beard")
        elif "indra" in norm:
            has_chalice = "chalice" in norm
            item = self.get_price("boss_rip_indra_chalice" if has_chalice else "boss_rip_indra")
        else:
            item = None

        if item and item.category == "Bosses":
            tax_amt, tot = self.calculate_tax(item.price_amount, tax_rate)
            calc = CalculationResult(
                service_name=item.service_name,
                category=item.category,
                quantity=1,
                unit_price=item.price_amount,
                unit_display=item.price_display,
                subtotal=item.price_amount,
                subtotal_display=item.price_display,
                tax_rate=tax_rate,
                tax_amount=tax_amt,
                tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                total=tot,
                total_display=self.format_price(tot),
                condition_note=item.condition_note,
            )
            return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": 1, "tax_rate": tax_rate, "raw_query": raw}

        # ─────────────────────────────────────────────────────────────────────
        # I. SWORDS & GUNS & FIGHTING STYLES & ADMIN & ACCESSORIES & TITLES
        # ─────────────────────────────────────────────────────────────────────
        matched = self.get_price(norm)
        if not matched:
            clean_words = [w for w in norm.split() if w not in ("title", "sword", "gun", "style", "accessory", "panel")]
            clean_rejoin = " ".join(clean_words)
            matched = self.get_price(clean_rejoin)
            if not matched:
                matches = self.search_prices(clean_rejoin)
                if matches:
                    matched = matches[0]

        if matched:
            m_q = re.search(r'\b(\d+)\b', norm)
            qty = int(m_q.group(1)) if m_q else 1

            is_per_unit = "per " in matched.unit_desc.lower() or "each" in matched.unit_desc.lower()
            subtotal = matched.price_amount * (qty if is_per_unit else 1)
            tax_amt, tot = self.calculate_tax(subtotal, tax_rate)

            calc = CalculationResult(
                service_name=matched.service_name,
                category=matched.category,
                quantity=qty if is_per_unit else 1,
                unit_price=matched.price_amount,
                unit_display=matched.price_display,
                subtotal=subtotal,
                subtotal_display=self.format_price(subtotal),
                tax_rate=tax_rate,
                tax_amount=tax_amt,
                tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                total=tot,
                total_display=self.format_price(tot),
                condition_note=matched.condition_note,
                custom_quote=bool(matched.custom_quote_required),
            )
            return {"intent": "make_bill" if is_make_bill else "price_lookup", "calculation": calc, "quantity": qty if is_per_unit else 1, "tax_rate": tax_rate, "raw_query": raw}

        raise KeyError(f"No official price found for service '{query}'. Contact staff for custom pricing.")

    def calculate_service_price(
        self,
        service_query: str,
        quantity: int = 1,
        tax_rate: float = 0.0,
        with_chalice: bool = False,
    ) -> CalculationResult:
        """Universal service price calculation engine."""
        q = service_query
        if with_chalice and "chalice" not in q.lower():
            q += " with chalice"
        if quantity > 1 and not any(ch.isdigit() for ch in q):
            q = f"{quantity} {q}"
        res = self.parse_top_query(q, tax_override=tax_rate)
        return res["calculation"]

    # ─────────────────────────────────────────────────────────────────────────
    # 5. PERSISTENT SERVICE BILLING SYSTEM
    # ─────────────────────────────────────────────────────────────────────────

    def generate_bill_id(self) -> str:
        """Generate unique, professional 8-character bill ID."""
        return f"TOP-{uuid.uuid4().hex[:6].upper()}"

    def create_bill(
        self,
        guild_id: int,
        creator_id: int,
        creator_name: str,
        service_name: str,
        quantity: int = 1,
        tax_rate: float = 0.0,
        customer_id: Optional[int] = None,
        customer_name: str = "",
        condition_notes: str = "",
        notes: str = "",
        payment_type: str = "Beli",
        fruit_details: str = "",
        custom_price: Optional[float] = None,
        custom_price_display: Optional[str] = None,
        posted_channel_id: int = 0,
        posted_message_id: str = "",
    ) -> dict[str, Any]:
        """Create and persist a new bill in UNPAID status with Blox Fruits payment specifications."""
        if custom_price is not None:
            unit_price = float(custom_price)
            unit_display = custom_price_display or f"{self.format_price(unit_price)}"
            subtotal = unit_price * max(1, quantity)
            subtotal_display = self.format_price(subtotal)
            tax_amt, tot = self.calculate_tax(subtotal, tax_rate)
            tax_display = self.format_price(tax_amt) if tax_amt > 0 else "0M"
            total = tot
            total_display = self.format_price(tot)
            category = "Custom Services"
            service = service_name
            cond_note = condition_notes
        else:
            calc = self.calculate_service_price(service_name, quantity=quantity, tax_rate=tax_rate)
            unit_price = calc.unit_price
            unit_display = calc.unit_display
            subtotal = calc.subtotal
            subtotal_display = calc.subtotal_display
            tax_rate = calc.tax_rate
            tax_amt = calc.tax_amount
            tax_display = calc.tax_display
            total = calc.total
            total_display = calc.total_display
            category = calc.category
            service = calc.service_name
            cond_note = condition_notes or calc.condition_note

        bill_id = self.generate_bill_id()
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_bills (
                    id, guild_id, customer_id, customer_name, service_name, category,
                    quantity, unit_price, unit_price_display, subtotal, subtotal_display,
                    tax_rate, tax_amount, tax_display, total, total_display, status,
                    condition_notes, notes, creator_id, creator_name, created_at, updated_at,
                    payment_type, currency_unit, fruit_details, posted_channel_id, posted_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNPAID', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bill_id,
                guild_id,
                customer_id,
                customer_name,
                service,
                category,
                quantity,
                unit_price,
                unit_display,
                subtotal,
                subtotal_display,
                tax_rate,
                tax_amt,
                tax_display,
                total,
                total_display,
                cond_note,
                notes,
                creator_id,
                creator_name,
                now,
                now,
                payment_type or "Beli",
                "Beli" if payment_type.lower() == "beli" else payment_type,
                fruit_details or "",
                posted_channel_id,
                str(posted_message_id) if posted_message_id else "",
            ))

            # Audit record
            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'CREATED', NULL, 'UNPAID', ?, ?)
            """, (bill_id, guild_id, creator_id, f"Created bill for {service} (Total: {total_display}, Payment: {payment_type})", now))

            conn.commit()

        return self.get_bill(bill_id)

    def create_multi_bill(
        self,
        guild_id: int,
        creator_id: int,
        creator_name: str,
        multi_calc: MultiCalculationResult,
        customer_id: Optional[int] = None,
        customer_name: str = "",
        payment_type: str = "Beli",
        notes: str = "",
        posted_channel_id: int = 0,
        posted_message_id: str = "",
    ) -> dict[str, Any]:
        """Create and persist a multi-item service bill in UNPAID status."""
        itemized_lines = [f"• {item.service_name} (Qty: {item.quantity}): {item.subtotal_display}" for item in multi_calc.items]
        combined_notes = "\n".join(itemized_lines)
        if notes:
            combined_notes += f"\nNotes: {notes}"

        bill_id = self.generate_bill_id()
        now = time.time()
        service_title = multi_calc.service_name[:100]

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_bills (
                    id, guild_id, customer_id, customer_name, service_name, category,
                    quantity, unit_price, unit_price_display, subtotal, subtotal_display,
                    tax_rate, tax_amount, tax_display, total, total_display, status,
                    condition_notes, notes, creator_id, creator_name, created_at, updated_at,
                    payment_type, currency_unit, fruit_details, posted_channel_id, posted_message_id
                ) VALUES (?, ?, ?, ?, ?, 'Multi-Service Package', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNPAID', ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """, (
                bill_id,
                guild_id,
                customer_id,
                customer_name,
                service_title,
                len(multi_calc.items),
                multi_calc.subtotal,
                multi_calc.subtotal_display,
                multi_calc.subtotal,
                multi_calc.subtotal_display,
                multi_calc.tax_rate,
                multi_calc.tax_amount,
                multi_calc.tax_display,
                multi_calc.total,
                multi_calc.total_display,
                combined_notes,
                notes,
                creator_id,
                creator_name,
                now,
                now,
                payment_type or "Beli",
                "Beli",
                posted_channel_id,
                str(posted_message_id) if posted_message_id else "",
            ))

            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'CREATED', NULL, 'UNPAID', ?, ?)
            """, (bill_id, guild_id, creator_id, f"Created multi-item bill for {len(multi_calc.items)} services (Total: {multi_calc.total_display})", now))

            conn.commit()

        return self.get_bill(bill_id)

    def get_pricing_policy(self, guild_id: int) -> dict[str, Any]:
        """Fetch server-specific pricing markup and surcharge policy."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_pricing_policy WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                return dict(row)
            return {
                "guild_id": guild_id,
                "custom_markup_pct": 0.0,
                "large_order_surcharge_pct": 0.0,
                "max_auto_increase_pct": 50.0,
                "approval_threshold_amount": 500.0,
            }

    def update_pricing_policy(
        self,
        guild_id: int,
        updated_by: int,
        custom_markup_pct: Optional[float] = None,
        large_order_surcharge_pct: Optional[float] = None,
        max_auto_increase_pct: Optional[float] = None,
        approval_threshold_amount: Optional[float] = None,
    ) -> dict[str, Any]:
        """Update configurable price policy parameters."""
        now = time.time()
        curr = self.get_pricing_policy(guild_id)
        new_markup = custom_markup_pct if custom_markup_pct is not None else curr["custom_markup_pct"]
        new_surch = large_order_surcharge_pct if large_order_surcharge_pct is not None else curr["large_order_surcharge_pct"]
        new_max = max_auto_increase_pct if max_auto_increase_pct is not None else curr["max_auto_increase_pct"]
        new_thresh = approval_threshold_amount if approval_threshold_amount is not None else curr["approval_threshold_amount"]

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_pricing_policy (
                    guild_id, custom_markup_pct, large_order_surcharge_pct,
                    max_auto_increase_pct, approval_threshold_amount, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    custom_markup_pct = excluded.custom_markup_pct,
                    large_order_surcharge_pct = excluded.large_order_surcharge_pct,
                    max_auto_increase_pct = excluded.max_auto_increase_pct,
                    approval_threshold_amount = excluded.approval_threshold_amount,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
            """, (guild_id, new_markup, new_surch, new_max, new_thresh, now, updated_by))
            conn.commit()
        return self.get_pricing_policy(guild_id)



    def get_bill(self, bill_id: str) -> Optional[dict[str, Any]]:
        """Fetch bill record by exact ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_bills WHERE id = ?", (bill_id.strip().upper(),)).fetchone()
            return dict(row) if row else None

    def list_bills(
        self,
        guild_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List bills optionally filtered by guild and status."""
        query = "SELECT * FROM top_bills WHERE 1=1"
        params: list[Any] = []

        if guild_id is not None:
            query += " AND guild_id = ?"
            params.append(guild_id)

        if status:
            query += " AND status = ?"
            params.append(status.strip().upper())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def mark_bill_paid(
        self,
        bill_id: str,
        staff_id: int,
        staff_name: str,
        message_id: str | int,
    ) -> dict[str, Any]:
        """Mark bill as PAID with payment message ID verification and audit log."""
        bill = self.get_bill(bill_id)
        if not bill:
            raise KeyError(f"Bill '{bill_id}' not found.")

        if bill["status"] == "PAID":
            raise ValueError(f"Bill '{bill_id}' has already been marked as PAID on {dt.datetime.fromtimestamp(bill['paid_at'], dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}.")

        if bill["status"] in ("CANCELLED", "REFUNDED"):
            raise ValueError(f"Cannot mark bill '{bill_id}' as PAID because it is currently {bill['status']}.")

        msg_id_str = str(message_id).strip()
        if not msg_id_str.isdigit() or len(msg_id_str) < 17:
            raise ValueError(f"'{message_id}' is not a valid Discord message ID.")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_bills
                SET status = 'PAID', paid_at = ?, paid_by_id = ?, paid_by_name = ?,
                    payment_message_id = ?, updated_at = ?
                WHERE id = ?
            """, (now, staff_id, staff_name, msg_id_str, now, bill["id"]))

            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'PAID', ?, 'PAID', ?, ?)
            """, (
                bill["id"],
                bill["guild_id"],
                staff_id,
                bill["status"],
                f"Confirmed payment via Message ID: {msg_id_str}",
                now,
            ))
            conn.commit()

        return self.get_bill(bill["id"])

    def find_bill_by_message_id(self, message_id: str | int) -> list[dict[str, Any]]:
        """Search database for any bills associated with this payment or posted message ID or bill ID."""
        msg_id_str = str(message_id).strip()
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM top_bills WHERE payment_message_id = ? OR posted_message_id = ? OR id = ?",
                (msg_id_str, msg_id_str, msg_id_str.upper())
            ).fetchall()
            return [dict(r) for r in rows]

    def set_bill_posted_message(self, bill_id: str, channel_id: int, message_id: int | str) -> None:
        """Associate the created bill with its Discord message and channel."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE top_bills SET posted_channel_id = ?, posted_message_id = ?, payment_message_id = ? WHERE id = ?",
                (int(channel_id), str(message_id), str(message_id), bill_id.strip().upper())
            )
            conn.commit()

    def mark_bill_paid_by_message_id(
        self,
        message_id: str | int,
        staff_id: int,
        staff_name: str,
    ) -> dict[str, Any]:
        """Find bill by message ID and mark it as PAID, preventing duplicate revenue."""
        bills = self.find_bill_by_message_id(message_id)
        if not bills:
            raise KeyError(f"No bill found associated with message ID '{message_id}'.")

        bill = bills[0]
        if bill["status"] == "PAID":
            paid_ts = bill.get("paid_at") or 0.0
            paid_str = dt.datetime.fromtimestamp(paid_ts, dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if paid_ts else "earlier"
            raise ValueError(f"Bill '{bill['id']}' has already been marked as PAID on {paid_str} by {bill.get('paid_by_name') or 'staff'}.")

        if bill["status"] in ("CANCELLED", "REFUNDED"):
            raise ValueError(f"Cannot mark bill '{bill['id']}' as PAID because it is currently {bill['status']}.")

        msg_id_str = str(message_id).strip()
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_bills
                SET status = 'PAID', paid_at = ?, paid_by_id = ?, paid_by_name = ?,
                    payment_message_id = ?, updated_at = ?
                WHERE id = ?
            """, (now, staff_id, staff_name, msg_id_str, now, bill["id"]))

            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'PAID', ?, 'PAID', ?, ?)
            """, (
                bill["id"],
                bill["guild_id"],
                staff_id,
                bill["status"],
                f"Confirmed payment via Message ID: {msg_id_str}",
                now,
            ))
            conn.commit()

        return self.get_bill(bill["id"])


    def cancel_bill(self, bill_id: str, staff_id: int, reason: str) -> dict[str, Any]:
        """Cancel an UNPAID bill with reason and audit log."""
        bill = self.get_bill(bill_id)
        if not bill:
            raise KeyError(f"Bill '{bill_id}' not found.")

        if bill["status"] == "PAID":
            raise ValueError(f"Bill '{bill_id}' is already PAID. Use refund instead.")

        if bill["status"] == "CANCELLED":
            raise ValueError(f"Bill '{bill_id}' is already CANCELLED.")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_bills
                SET status = 'CANCELLED', cancelled_at = ?, cancelled_by_id = ?,
                    cancel_reason = ?, updated_at = ?
                WHERE id = ?
            """, (now, staff_id, reason, now, bill["id"]))

            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'CANCELLED', ?, 'CANCELLED', ?, ?)
            """, (bill["id"], bill["guild_id"], staff_id, bill["status"], f"Reason: {reason}", now))
            conn.commit()

        return self.get_bill(bill["id"])

    def refund_bill(self, bill_id: str, staff_id: int, reason: str) -> dict[str, Any]:
        """Refund a PAID bill, preserving audit record and updating net revenue."""
        bill = self.get_bill(bill_id)
        if not bill:
            raise KeyError(f"Bill '{bill_id}' not found.")

        if bill["status"] != "PAID":
            raise ValueError(f"Cannot refund bill '{bill_id}' because it is '{bill['status']}' (only PAID bills can be refunded).")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_bills
                SET status = 'REFUNDED', refunded_at = ?, refunded_by_id = ?,
                    refund_reason = ?, updated_at = ?
                WHERE id = ?
            """, (now, staff_id, reason, now, bill["id"]))

            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'REFUNDED', 'PAID', 'REFUNDED', ?, ?)
            """, (bill["id"], bill["guild_id"], staff_id, f"Refund Reason: {reason}", now))
            conn.commit()

        return self.get_bill(bill["id"])

    def add_bill_note(self, bill_id: str, staff_id: int, note: str) -> dict[str, Any]:
        """Append note to bill with audit trail."""
        bill = self.get_bill(bill_id)
        if not bill:
            raise KeyError(f"Bill '{bill_id}' not found.")

        now = time.time()
        current_notes = bill.get("notes", "") or ""
        new_notes = f"{current_notes}\n[{dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime('%m-%d %H:%M')}] {note}".strip()

        with self._get_connection() as conn:
            conn.execute("UPDATE top_bills SET notes = ?, updated_at = ? WHERE id = ?", (new_notes, now, bill["id"]))
            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'NOTE_ADDED', ?, ?, ?, ?)
            """, (bill["id"], bill["guild_id"], staff_id, bill["status"], bill["status"], f"Note: {note}", now))
            conn.commit()

        return self.get_bill(bill["id"])

    # ─────────────────────────────────────────────────────────────────────────
    # 6. DAILY, WEEKLY, MONTHLY REPORTING
    # ─────────────────────────────────────────────────────────────────────────

    def get_financial_report(
        self,
        guild_id: Optional[int],
        start_timestamp: float,
        end_timestamp: float,
        period_name: str = "Custom Period",
    ) -> dict[str, Any]:
        """Aggregate accurate accounting figures for a time window."""
        with self._get_connection() as conn:
            # 1. Bills created within period
            q_created = "SELECT * FROM top_bills WHERE created_at >= ? AND created_at < ?"
            params_created: list[Any] = [start_timestamp, end_timestamp]
            if guild_id is not None:
                q_created += " AND guild_id = ?"
                params_created.append(guild_id)

            created_bills = [dict(r) for r in conn.execute(q_created, params_created).fetchall()]

            # 2. Payments confirmed within period (Crucial: based on paid_at timestamp!)
            q_paid = "SELECT * FROM top_bills WHERE paid_at IS NOT NULL AND paid_at >= ? AND paid_at < ?"
            params_paid: list[Any] = [start_timestamp, end_timestamp]
            if guild_id is not None:
                q_paid += " AND guild_id = ?"
                params_paid.append(guild_id)

            paid_in_period = [dict(r) for r in conn.execute(q_paid, params_paid).fetchall()]

            # 3. Refunds processed within period
            q_refunded = "SELECT * FROM top_bills WHERE refunded_at IS NOT NULL AND refunded_at >= ? AND refunded_at < ?"
            params_refunded: list[Any] = [start_timestamp, end_timestamp]
            if guild_id is not None:
                q_refunded += " AND guild_id = ?"
                params_refunded.append(guild_id)

            refunded_in_period = [dict(r) for r in conn.execute(q_refunded, params_refunded).fetchall()]

            # 4. Active unpaid bills (outstanding)
            q_unpaid = "SELECT * FROM top_bills WHERE status = 'UNPAID'"
            params_unpaid: list[Any] = []
            if guild_id is not None:
                q_unpaid += " AND guild_id = ?"
                params_unpaid.append(guild_id)

            unpaid_bills = [dict(r) for r in conn.execute(q_unpaid, params_unpaid).fetchall()]

            # Calculations
            total_created_value = sum(b["total"] for b in created_bills)
            received_revenue = sum(b["total"] for b in paid_in_period)
            refund_total = sum(b["total"] for b in refunded_in_period)
            net_revenue = max(0.0, received_revenue - refund_total)
            outstanding_amount = sum(b["total"] for b in unpaid_bills)

            # Category breakdown of created bills
            category_breakdown: dict[str, int] = {}
            for b in created_bills:
                cat = b.get("category", "General")
                category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

            # Staff breakdown of confirmed payments
            staff_payments: dict[str, float] = {}
            for b in paid_in_period:
                st = b.get("paid_by_name") or f"Staff #{b.get('paid_by_id', 'Unknown')}"
                staff_payments[st] = staff_payments.get(st, 0.0) + b["total"]

            # Tax collected on bills paid in this period
            tax_collected = sum(b.get("tax_amount", 0.0) or 0.0 for b in paid_in_period)

            # Revenue grouped by payment type (Beli, Fruits, etc.)
            revenue_by_payment_type: dict[str, float] = {}
            fruit_summary: dict[str, int] = {}
            for b in paid_in_period:
                pt = b.get("payment_type") or "Beli"
                revenue_by_payment_type[pt] = revenue_by_payment_type.get(pt, 0.0) + b["total"]
                f_det = b.get("fruit_details") or ""
                if f_det:
                    for f_token in f_det.split(","):
                        f_clean = f_token.strip()
                        if f_clean:
                            fruit_summary[f_clean] = fruit_summary.get(f_clean, 0) + 1

            # Daily breakdown of paid revenue
            daily_breakdown: dict[str, float] = {}
            for b in paid_in_period:
                if b.get("paid_at"):
                    d_key = dt.datetime.fromtimestamp(b["paid_at"], dt.timezone.utc).strftime("%Y-%m-%d")
                    daily_breakdown[d_key] = daily_breakdown.get(d_key, 0.0) + b["total"]

            # Number of unpaid bills created specifically during this period
            unpaid_created_in_period = sum(1 for b in created_bills if b["status"] == "UNPAID")

            return {
                "period_name": period_name,
                "start_time": start_timestamp,
                "end_time": end_timestamp,
                "created_count": len(created_bills),
                "created_total_value": total_created_value,
                "created_total_display": self.format_price(total_created_value),
                "paid_count": len(paid_in_period),
                "received_revenue": received_revenue,
                "received_revenue_m": received_revenue,
                "received_revenue_display": self.format_price(received_revenue),
                "unpaid_count": len(unpaid_bills),
                "unpaid_created_count": unpaid_created_in_period,
                "unpaid_created_in_period": unpaid_created_in_period,
                "outstanding_amount": outstanding_amount,
                "outstanding_display": self.format_price(outstanding_amount),
                "tax_collected": tax_collected,
                "tax_collected_m": tax_collected,
                "tax_collected_display": self.format_price(tax_collected) if tax_collected > 0 else "0M",
                "revenue_by_payment_type": revenue_by_payment_type,
                "fruit_summary": fruit_summary,
                "daily_breakdown": daily_breakdown,
                "cancelled_count": sum(1 for b in created_bills if b["status"] == "CANCELLED"),
                "refunded_count": len(refunded_in_period),
                "refund_total": refund_total,
                "refund_total_display": self.format_price(refund_total),
                "net_revenue": net_revenue,
                "net_revenue_display": self.format_price(net_revenue),
                "category_breakdown": category_breakdown,
                "staff_payments": staff_payments,
                "recent_bills": created_bills[:10],
            }

    def get_today_report(self, guild_id: Optional[int], timezone_offset_hours: float = 0.0) -> dict[str, Any]:
        """Report for current 24-hour UTC or server-configured day."""
        tz = dt.timezone(dt.timedelta(hours=timezone_offset_hours))
        now = dt.datetime.now(tz)
        start_of_day = dt.datetime(now.year, now.month, now.day, tzinfo=tz)
        start_ts = start_of_day.timestamp()
        end_ts = start_ts + 86400
        return self.get_financial_report(guild_id, start_ts, end_ts, period_name="Today's Performance")

    def get_weekly_report(self, guild_id: Optional[int], timezone_offset_hours: float = 0.0) -> dict[str, Any]:
        """Report for the current 7-day period."""
        tz = dt.timezone(dt.timedelta(hours=timezone_offset_hours))
        now = dt.datetime.now(tz)
        start_of_week = now - dt.timedelta(days=7)
        return self.get_financial_report(guild_id, start_of_week.timestamp(), now.timestamp(), period_name="Weekly Performance (Last 7 Days)")

    def get_monthly_report(self, guild_id: Optional[int], timezone_offset_hours: float = 0.0) -> dict[str, Any]:
        """Report for the current calendar month (1st of month to start of next month)."""
        tz = dt.timezone(dt.timedelta(hours=timezone_offset_hours))
        now = dt.datetime.now(tz)
        start_of_month = dt.datetime(now.year, now.month, 1, tzinfo=tz)
        if now.month == 12:
            start_of_next_month = dt.datetime(now.year + 1, 1, 1, tzinfo=tz)
        else:
            start_of_next_month = dt.datetime(now.year, now.month + 1, 1, tzinfo=tz)
        return self.get_financial_report(
            guild_id,
            start_of_month.timestamp(),
            start_of_next_month.timestamp(),
            period_name=f"{now.strftime('%B %Y')} Performance",
        )


    # ─────────────────────────────────────────────────────────────────────────
    # 7. PRICE CATALOGUE MANAGEMENT (STAFF / OWNER WORKFLOW)
    # ─────────────────────────────────────────────────────────────────────────

    def update_price(
        self,
        service_key: str,
        new_price: float,
        staff_id: int,
        reason: str = "Price update",
    ) -> PriceItem:
        """Update service price, record history, and invalidate cache."""
        item = self.get_price(service_key)
        if not item:
            raise KeyError(f"Service '{service_key}' not found in catalogue.")

        old_price = item.price_amount
        old_disp = item.price_display
        new_disp = self.format_price(new_price)
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_prices
                SET price_amount = ?, price_display = ?, updated_at = ?, updated_by = ?
                WHERE service_key = ?
            """, (new_price, new_disp, now, staff_id, item.service_key))

            conn.execute("""
                INSERT INTO top_price_history (
                    service_key, old_price, new_price, old_display, new_display, changed_by, reason, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item.service_key, old_price, new_price, old_disp, new_disp, staff_id, reason, now))
            conn.commit()

        # Reload cache
        self._load_prices()
        return self.get_price(service_key)

    def rename_service(self, service_key: str, new_name: str, staff_id: int) -> PriceItem:
        """Rename a service without changing historical bills."""
        item = self.get_price(service_key)
        if not item:
            raise KeyError(f"Service '{service_key}' not found in catalogue.")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_prices
                SET service_name = ?, updated_at = ?, updated_by = ?
                WHERE service_key = ?
            """, (new_name.strip(), now, staff_id, item.service_key))
            conn.commit()

        self._load_prices()
        return self.get_price(service_key)

    def toggle_custom_quote(self, service_key: str, staff_id: int, required: bool) -> PriceItem:
        """Toggle whether service requires custom quote from staff."""
        item = self.get_price(service_key)
        if not item:
            raise KeyError(f"Service '{service_key}' not found in catalogue.")

        now = time.time()
        flag = 1 if required else 0
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_prices
                SET custom_quote_required = ?, updated_at = ?, updated_by = ?
                WHERE service_key = ?
            """, (flag, now, staff_id, item.service_key))
            conn.commit()

        self._load_prices()
        return self.get_price(service_key)

    def get_price_history(self, service_key: str) -> list[dict[str, Any]]:
        """Fetch audit log of all price updates for a service."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM top_price_history WHERE service_key = ? ORDER BY timestamp DESC
            """, (service_key.strip(),)).fetchall()
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # 8. STAFF APPLICATION SYSTEM (APPY-STYLE)
    # ─────────────────────────────────────────────────────────────────────────

    def submit_application(
        self,
        guild_id: int,
        applicant_id: int,
        applicant_name: str,
        position: str,
        answers: dict[str, str],
    ) -> dict[str, Any]:
        """Submit a new staff application with open-check, cooldown & duplicate prevention."""
        with self._get_connection() as conn:
            # Check if applications are currently open in this server
            cfg = conn.execute("SELECT * FROM top_applications_config WHERE guild_id = ?", (guild_id,)).fetchone()
            if cfg and ("is_open" in cfg.keys()) and cfg["is_open"] == 0:
                raise ValueError("Staff applications are currently closed or paused. Please check back later.")

            # Validate answers
            if not answers or not any(v.strip() for v in answers.values()):
                raise ValueError("Application answers cannot be empty.")

            # Check for existing active application
            existing = conn.execute("""
                SELECT id, status, created_at FROM top_applications
                WHERE guild_id = ? AND applicant_id = ? AND status IN ('PENDING', 'SUBMITTED', 'UNDER_REVIEW', 'MORE_INFO_REQUESTED')
            """, (guild_id, applicant_id)).fetchone()

            if existing:
                raise ValueError(
                    f"You already have an active application ({existing['id']}) with status '{existing['status']}'. "
                    f"Please wait for staff review."
                )

            # Check cooldown config
            cooldown_days = cfg["cooldown_days"] if cfg and cfg["cooldown_days"] else 7

            last_rejected = conn.execute("""
                SELECT created_at FROM top_applications
                WHERE guild_id = ? AND applicant_id = ? AND status = 'REJECTED'
                ORDER BY created_at DESC LIMIT 1
            """, (guild_id, applicant_id)).fetchone()

            if last_rejected:
                days_since = (time.time() - last_rejected["created_at"]) / 86400.0
                if days_since < cooldown_days:
                    rem = int(cooldown_days - days_since)
                    raise ValueError(f"You recently applied. Please wait **{rem} day(s)** before submitting another application.")

            app_id = f"APP-{uuid.uuid4().hex[:6].upper()}"
            now = time.time()
            conn.execute("""
                INSERT INTO top_applications (
                    id, guild_id, applicant_id, applicant_name, position, answers_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """, (app_id, guild_id, applicant_id, applicant_name, position, json.dumps(answers), now, now))
            conn.commit()

        return self.get_application(app_id)

    def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        """Fetch application by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_applications WHERE id = ?", (app_id.strip().upper(),)).fetchone()
            if row:
                d = dict(row)
                d["answers"] = json.loads(d["answers_json"]) if d["answers_json"] else {}
                return d
            return None

    def list_applications(
        self,
        guild_id: int,
        status: Optional[str] = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List staff applications filtered by status."""
        query = "SELECT * FROM top_applications WHERE guild_id = ?"
        params: list[Any] = [guild_id]

        if status:
            query += " AND status = ?"
            params.append(status.strip().upper())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                d["answers"] = json.loads(d["answers_json"]) if d["answers_json"] else {}
                res.append(d)
            return res

    def review_application(
        self,
        app_id: str,
        reviewer_id: int,
        reviewer_name: str,
        new_status: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Review application: ACCEPTED, REJECTED, UNDER_REVIEW, MORE_INFO_REQUESTED, or CLOSED."""
        app = self.get_application(app_id)
        if not app:
            raise KeyError(f"Application '{app_id}' not found.")

        target_status = new_status.strip().upper()
        valid_statuses = ("ACCEPTED", "REJECTED", "UNDER_REVIEW", "MORE_INFO_REQUESTED", "WITHDRAWN", "CLOSED")
        if target_status not in valid_statuses:
            raise ValueError(f"Invalid application status: '{new_status}'.")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE top_applications
                SET status = ?, reviewer_id = ?, reviewer_name = ?, decision_reason = ?, updated_at = ?
                WHERE id = ?
            """, (target_status, reviewer_id, reviewer_name, reason, now, app["id"]))
            conn.commit()

        return self.get_application(app["id"])

    def add_application_note(self, app_id: str, staff_id: int, note: str) -> dict[str, Any]:
        """Add private staff note to application."""
        app = self.get_application(app_id)
        if not app:
            raise KeyError(f"Application '{app_id}' not found.")

        now = time.time()
        current = app.get("staff_notes", "") or ""
        updated = f"{current}\n[{dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime('%m-%d %H:%M')}] {note}".strip()

        with self._get_connection() as conn:
            conn.execute("UPDATE top_applications SET staff_notes = ?, updated_at = ? WHERE id = ?", (updated, now, app["id"]))
            conn.commit()

        return self.get_application(app["id"])

    def get_application_stats(self, guild_id: int) -> dict[str, Any]:
        """Compute recruitment metrics and review time stats for a guild."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM top_applications WHERE guild_id = ?", (guild_id,)).fetchall()
            total = len(rows)
            pending = sum(1 for r in rows if r["status"] in ("PENDING", "SUBMITTED"))
            under_review = sum(1 for r in rows if r["status"] == "UNDER_REVIEW")
            more_info = sum(1 for r in rows if r["status"] == "MORE_INFO_REQUESTED")
            accepted = sum(1 for r in rows if r["status"] == "ACCEPTED")
            rejected = sum(1 for r in rows if r["status"] == "REJECTED")
            closed = sum(1 for r in rows if r["status"] == "CLOSED")

            # Calculate average review duration in hours
            review_times = [
                (r["updated_at"] - r["created_at"]) / 3600.0
                for r in rows
                if r["status"] in ("ACCEPTED", "REJECTED", "CLOSED") and r["updated_at"] > r["created_at"]
            ]
            avg_review_hours = (sum(review_times) / len(review_times)) if review_times else 0.0

            pos_counts: dict[str, int] = {}
            for r in rows:
                pos = r["position"]
                pos_counts[pos] = pos_counts.get(pos, 0) + 1

            return {
                "total": total,
                "pending": pending,
                "under_review": under_review,
                "more_info": more_info,
                "accepted": accepted,
                "rejected": rejected,
                "closed": closed,
                "avg_review_hours": round(avg_review_hours, 1),
                "positions": pos_counts,
            }

    def get_app_config(self, guild_id: int) -> dict[str, Any]:
        """Get guild staff application config."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_applications_config WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                d = dict(row)
                d.setdefault("is_open", 1)
                d.setdefault("reviewer_role_id", None)
                d.setdefault("audit_channel_id", None)
                return d
            return {
                "guild_id": guild_id,
                "review_channel_id": None,
                "role_on_accept_id": None,
                "reviewer_role_id": None,
                "audit_channel_id": None,
                "is_open": 1,
                "cooldown_days": 7,
                "default_tax": 0.0,
            }

    def set_app_config(
        self,
        guild_id: int,
        review_channel_id: Optional[int] = None,
        role_on_accept_id: Optional[int] = None,
        reviewer_role_id: Optional[int] = None,
        audit_channel_id: Optional[int] = None,
        is_open: Optional[int] = None,
        cooldown_days: Optional[int] = None,
        default_tax: Optional[float] = None,
        panel_message_id: Optional[int] = None,
        panel_channel_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Save guild staff application config."""
        cur = self.get_app_config(guild_id)
        r_ch = review_channel_id if review_channel_id is not None else cur.get("review_channel_id")
        r_role = role_on_accept_id if role_on_accept_id is not None else cur.get("role_on_accept_id")
        rev_role = reviewer_role_id if reviewer_role_id is not None else cur.get("reviewer_role_id")
        aud_ch = audit_channel_id if audit_channel_id is not None else cur.get("audit_channel_id")
        o_flag = is_open if is_open is not None else cur.get("is_open", 1)
        c_days = cooldown_days if cooldown_days is not None else cur.get("cooldown_days", 7)
        d_tax = default_tax if default_tax is not None else cur.get("default_tax", 0.0)
        p_msg = panel_message_id if panel_message_id is not None else cur.get("panel_message_id")
        p_ch = panel_channel_id if panel_channel_id is not None else cur.get("panel_channel_id")

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_applications_config (
                    guild_id, review_channel_id, role_on_accept_id, reviewer_role_id,
                    audit_channel_id, is_open, cooldown_days, default_tax,
                    panel_message_id, panel_channel_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    review_channel_id = excluded.review_channel_id,
                    role_on_accept_id = excluded.role_on_accept_id,
                    reviewer_role_id = excluded.reviewer_role_id,
                    audit_channel_id = excluded.audit_channel_id,
                    is_open = excluded.is_open,
                    cooldown_days = excluded.cooldown_days,
                    default_tax = excluded.default_tax,
                    panel_message_id = excluded.panel_message_id,
                    panel_channel_id = excluded.panel_channel_id
            """, (guild_id, r_ch, r_role, rev_role, aud_ch, o_flag, c_days, d_tax, p_msg, p_ch))
            conn.commit()

        return self.get_app_config(guild_id)

    def get_billing_config(self, guild_id: int) -> dict[str, Any]:
        """Get guild billing configuration (billing channel, tax rate, currency unit)."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_billing_config WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                return dict(row)
            return {
                "guild_id": guild_id,
                "billing_channel_id": None,
                "tax_rate": 5.0,
                "currency_unit": "Beli",
                "created_at": time.time(),
                "updated_at": time.time(),
            }

    def set_billing_config(
        self,
        guild_id: int,
        billing_channel_id: Optional[int] = None,
        tax_rate: Optional[float] = None,
        currency_unit: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update or insert guild billing configuration."""
        cur = self.get_billing_config(guild_id)
        b_ch = billing_channel_id if billing_channel_id is not None else cur.get("billing_channel_id")
        t_rate = tax_rate if tax_rate is not None else cur.get("tax_rate", 5.0)
        c_unit = currency_unit if currency_unit is not None else cur.get("currency_unit", "Beli")
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_billing_config (
                    guild_id, billing_channel_id, tax_rate, currency_unit, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    billing_channel_id = excluded.billing_channel_id,
                    tax_rate = excluded.tax_rate,
                    currency_unit = excluded.currency_unit,
                    updated_at = excluded.updated_at
            """, (guild_id, b_ch, t_rate, c_unit, cur.get("created_at", now), now))
            conn.commit()

        return self.get_billing_config(guild_id)

    def get_pricing_policy(self, guild_id: int) -> dict[str, Any]:
        """Get guild smart pricing policy (custom markup, surcharge, max auto increase, staff approval threshold)."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_pricing_policy WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                d = dict(row)
                d["custom_order_markup_percent"] = d.get("custom_markup_pct", 0.0)
                d["requires_staff_approval_above_beli"] = d.get("approval_threshold_amount", 500.0)
                return d
            return {
                "guild_id": guild_id,
                "custom_markup_pct": 0.0,
                "custom_order_markup_percent": 0.0,
                "large_order_surcharge_pct": 0.0,
                "max_auto_increase_pct": 50.0,
                "approval_threshold_amount": 500.0,
                "requires_staff_approval_above_beli": 500.0,
                "updated_at": time.time(),
                "updated_by": None,
            }

    def update_pricing_policy(
        self,
        guild_id: int,
        custom_markup: float = 0.0,
        large_order_surcharge: float = 0.0,
        max_auto_increase: float = 50.0,
        staff_approval_threshold: float = 500.0,
        updated_by: Optional[int] = None,
    ) -> dict[str, Any]:
        """Update or insert guild pricing policy."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_pricing_policy (
                    guild_id, custom_markup_pct, large_order_surcharge_pct,
                    max_auto_increase_pct, approval_threshold_amount, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    custom_markup_pct = excluded.custom_markup_pct,
                    large_order_surcharge_pct = excluded.large_order_surcharge_pct,
                    max_auto_increase_pct = excluded.max_auto_increase_pct,
                    approval_threshold_amount = excluded.approval_threshold_amount,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
            """, (guild_id, custom_markup, large_order_surcharge, max_auto_increase, staff_approval_threshold, now, updated_by))
            conn.commit()
        return self.get_pricing_policy(guild_id)

