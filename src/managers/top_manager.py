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
        "aliases": ["cdk", "cursed dual katana"],
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

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
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

    def calculate_service_price(
        self,
        service_query: str,
        quantity: int = 1,
        tax_rate: float = 0.0,
        with_chalice: bool = False,
    ) -> CalculationResult:
        """Find authoritative service price and compute subtotal, tax, and total."""
        norm = service_query.lower().strip()

        # Handle chalice condition for Rip_Indra
        if "chalice" in norm or with_chalice:
            if "indra" in norm:
                item = self.get_price("boss_rip_indra_chalice")
                if item:
                    tax_amt, tot = self.calculate_tax(item.price_amount * quantity, tax_rate)
                    return CalculationResult(
                        service_name=item.service_name,
                        category=item.category,
                        quantity=quantity,
                        unit_price=item.price_amount,
                        unit_display=item.price_display,
                        subtotal=item.price_amount * quantity,
                        subtotal_display=self.format_price(item.price_amount * quantity),
                        tax_rate=tax_rate,
                        tax_amount=tax_amt,
                        tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                        total=tot,
                        total_display=self.format_price(tot),
                        condition_note=item.condition_note,
                        custom_quote=bool(item.custom_quote_required),
                    )

        # Handle tiered trials (1 trial, 2 trials, 3 trials)
        if "trial" in norm and not ("draco" in norm or "tushita" in norm or "yama" in norm):
            if "2 trial" in norm or "two trial" in norm or quantity == 2:
                tax_amt, tot = self.calculate_tax(40.0, tax_rate)
                return CalculationResult(
                    service_name="2 Trials",
                    category="Trials",
                    quantity=2,
                    unit_price=20.0,
                    unit_display="20M",
                    subtotal=40.0,
                    subtotal_display="40M",
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note="",
                )
            elif "3 trial" in norm or "three trial" in norm or quantity == 3:
                tax_amt, tot = self.calculate_tax(60.0, tax_rate)
                return CalculationResult(
                    service_name="3 Trials",
                    category="Trials",
                    quantity=3,
                    unit_price=20.0,
                    unit_display="20M",
                    subtotal=60.0,
                    subtotal_display="60M",
                    tax_rate=tax_rate,
                    tax_amount=tax_amt,
                    tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
                    total=tot,
                    total_display=self.format_price(tot),
                    condition_note="",
                )
            elif "max race package" in norm or "max package" in norm:
                item = self.get_price("trial_max_race_package")
            elif "max" in norm:
                item = self.get_price("trial_max")
            elif "training" in norm:
                item = self.get_price("trial_training")
            else:
                item = self.get_price("trial_1")

        # Handle Normal Raids tiered ranges (1-5, 6-10, 11-15, 16-20, 20-25, 25+)
        elif "normal raid" in norm or (("raid" in norm or "raids" in norm) and not ("advance" in norm or "adv" in norm or "order" in norm or "law" in norm)):
            if quantity >= 25 and quantity != 25:
                item = self.get_price("normal_raid_25_plus")
            elif quantity == 20:
                # Boundary Overlap Note (16-20 vs 20-25)
                item = self.get_price("normal_raid_16_20")
            elif 21 <= quantity <= 25:
                item = self.get_price("normal_raid_20_25")
            elif 16 <= quantity <= 19:
                item = self.get_price("normal_raid_16_20")
            elif 11 <= quantity <= 15:
                item = self.get_price("normal_raid_11_15")
            elif 6 <= quantity <= 10:
                item = self.get_price("normal_raid_6_10")
            else:
                item = self.get_price("normal_raid_1_5")

        # Handle Advance Raids (1-2: 10M, 3-4: 20M, 5: 30M, 6-8: 60M)
        elif "advance raid" in norm or "adv raid" in norm:
            if 6 <= quantity <= 8:
                item = self.get_price("adv_raid_6_8")
            elif quantity == 5:
                item = self.get_price("adv_raid_5")
            elif 3 <= quantity <= 4:
                item = self.get_price("adv_raid_3_4")
            else:
                item = self.get_price("adv_raid_1_2")

        # Handle Order Raids (1: 10M, 2: 20M, 3-5: 60M, 6-8: 120M, 8-10: 150M, 10+: custom)
        elif "order raid" in norm or "law raid" in norm:
            if quantity > 10:
                item = self.get_price("order_raid_10_plus")
            elif quantity == 8:
                # Boundary Overlap Note (6-8 vs 8-10)
                item = self.get_price("order_raid_6_8")
            elif 9 <= quantity <= 10:
                item = self.get_price("order_raid_8_10")
            elif 6 <= quantity <= 7:
                item = self.get_price("order_raid_6_8")
            elif 3 <= quantity <= 5:
                item = self.get_price("order_raid_3_5")
            elif quantity == 2:
                item = self.get_price("order_raid_2")
            else:
                item = self.get_price("order_raid_1")

        else:
            # Generic matching
            item = self.get_price(norm)
            if not item:
                # Try finding closest match
                matches = self.search_prices(norm)
                if matches:
                    item = matches[0]

        if not item:
            raise KeyError(f"No official price found for service '{service_query}'. Contact staff for custom pricing.")

        # Compute totals
        if item.custom_quote_required:
            return CalculationResult(
                service_name=item.service_name,
                category=item.category,
                quantity=quantity,
                unit_price=0.0,
                unit_display="Custom Quote",
                subtotal=0.0,
                subtotal_display="Custom Quote",
                tax_rate=tax_rate,
                tax_amount=0.0,
                tax_display="Custom Quote",
                total=0.0,
                total_display="Custom Quote",
                condition_note=item.condition_note,
                custom_quote=True,
            )

        # For tiered packages where price is for the range itself (e.g. Normal Raids 1-5 = 10M tier)
        if "tier" in item.unit_desc.lower() or item.service_key.startswith("normal_raid_") or item.service_key.startswith("adv_raid_") or item.service_key.startswith("order_raid_"):
            subtotal = item.price_amount
        else:
            subtotal = item.price_amount * quantity

        tax_amt, total = self.calculate_tax(subtotal, tax_rate)

        # Add notes for flagged boundaries
        ambiguity = ""
        if "overlap" in item.condition_note.lower():
            ambiguity = item.condition_note

        return CalculationResult(
            service_name=item.service_name,
            category=item.category,
            quantity=quantity,
            unit_price=item.price_amount,
            unit_display=item.price_display,
            subtotal=subtotal,
            subtotal_display=self.format_price(subtotal),
            tax_rate=tax_rate,
            tax_amount=tax_amt,
            tax_display=self.format_price(tax_amt) if tax_amt > 0 else "0M",
            total=total,
            total_display=self.format_price(total),
            condition_note=item.condition_note,
            custom_quote=False,
            ambiguity_note=ambiguity,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. NATURAL LANGUAGE INTENT PARSER
    # ─────────────────────────────────────────────────────────────────────────

    def parse_top_query(self, query: str) -> dict[str, Any]:
        """Natural-language intent parser for '?top ...' requests.
        Understands:
        - "what's the price of 1 trial?"
        - "price of 2 trials"
        - "what is the cost of 5 normal raids?"
        - "price of Draco V2"
        - "how much is Dough King?"
        - "what's the price of 2 trials with 5% tax?"
        - "calculate 3 trials with 10% tax"
        - "make a bill for 2 trials with 5% tax unpaid"
        """
        raw = query.strip()
        low = raw.lower()

        # Check intent: BILL vs CALCULATION vs LOOKUP
        is_make_bill = any(
            phrase in low for phrase in [
                "make bill", "make a bill", "create bill", "generate bill", "new bill"
            ]
        )

        # Extract Tax percentage if present (e.g. "5% tax", "with 10% tax", "tax 5%", "7.5% tax")
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

        # Extract Chalice condition if present
        with_chalice = "chalice" in low

        # Clean prompt of prefix boilerplate
        cleaned = low
        for noise in [
            "what's the price of", "what is the price of", "what is the cost of",
            "price of", "cost of", "how much is", "how much for", "calculate",
            "make a bill for", "make bill for", "make bill of", "make a bill of",
            "make bill", "create bill for", "bill for", "unpaid", "paid",
        ]:
            cleaned = cleaned.replace(noise, " ")

        # Strip tax substring from service string
        cleaned = re.sub(r'with\s*\d+(?:\.\d+)?\s*%\s*tax', ' ', cleaned)
        cleaned = re.sub(r'\d+(?:\.\d+)?\s*%\s*tax', ' ', cleaned)
        cleaned = re.sub(r'tax\s*\d+(?:\.\d+)?\s*%?', ' ', cleaned)
        cleaned = re.sub(r'[?.,!]', ' ', cleaned).strip()

        # Extract Quantity if present (e.g. "2 trials", "5 normal raids", "3")
        quantity = 1
        qty_match = re.search(r'\b(\d+)\b', cleaned)
        if qty_match:
            quantity = int(qty_match.group(1))
            # Remove isolated number from service string if not part of a version like V2
            # E.g. "2 trials" -> keep "trials", quantity=2
            # But "draco v2" -> keep "draco v2", quantity=1
            if not re.search(r'\bv\d+\b', cleaned):
                cleaned = re.sub(r'\b' + str(quantity) + r'\b', ' ', cleaned).strip()

        service_candidate = re.sub(r'\s+', ' ', cleaned).strip()
        if not service_candidate:
            service_candidate = "trials"

        # Special casing: if candidate is "trials" and quantity was extracted, candidate is "trials"
        calc = self.calculate_service_price(
            service_candidate,
            quantity=quantity,
            tax_rate=tax_rate,
            with_chalice=with_chalice,
        )

        return {
            "intent": "make_bill" if is_make_bill else "price_lookup",
            "calculation": calc,
            "quantity": quantity,
            "tax_rate": tax_rate,
            "raw_query": raw,
            "with_chalice": with_chalice,
        }

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
    ) -> dict[str, Any]:
        """Create and persist a new bill in UNPAID status."""
        calc = self.calculate_service_price(service_name, quantity=quantity, tax_rate=tax_rate)

        bill_id = self.generate_bill_id()
        now = time.time()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_bills (
                    id, guild_id, customer_id, customer_name, service_name, category,
                    quantity, unit_price, unit_price_display, subtotal, subtotal_display,
                    tax_rate, tax_amount, tax_display, total, total_display, status,
                    condition_notes, notes, creator_id, creator_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNPAID', ?, ?, ?, ?, ?, ?)
            """, (
                bill_id,
                guild_id,
                customer_id,
                customer_name,
                calc.service_name,
                calc.category,
                quantity,
                calc.unit_price,
                calc.unit_display,
                calc.subtotal,
                calc.subtotal_display,
                calc.tax_rate,
                calc.tax_amount,
                calc.tax_display,
                calc.total,
                calc.total_display,
                condition_notes or calc.condition_note,
                notes,
                creator_id,
                creator_name,
                now,
                now,
            ))

            # Audit record
            conn.execute("""
                INSERT INTO top_bill_audit (
                    bill_id, guild_id, staff_id, action, old_status, new_status, details, timestamp
                ) VALUES (?, ?, ?, 'CREATED', NULL, 'UNPAID', ?, ?)
            """, (bill_id, guild_id, creator_id, f"Created bill for {calc.service_name} (Total: {calc.total_display})", now))

            conn.commit()

        return self.get_bill(bill_id)

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
        """Search database for any bills associated with this payment message ID."""
        msg_id_str = str(message_id).strip()
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM top_bills WHERE payment_message_id = ?", (msg_id_str,)).fetchall()
            return [dict(r) for r in rows]

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

            return {
                "period_name": period_name,
                "start_time": start_timestamp,
                "end_time": end_timestamp,
                "created_count": len(created_bills),
                "created_total_value": total_created_value,
                "created_total_display": self.format_price(total_created_value),
                "paid_count": len(paid_in_period),
                "received_revenue": received_revenue,
                "received_revenue_display": self.format_price(received_revenue),
                "unpaid_count": len(unpaid_bills),
                "outstanding_amount": outstanding_amount,
                "outstanding_display": self.format_price(outstanding_amount),
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

    def get_today_report(self, guild_id: Optional[int]) -> dict[str, Any]:
        """Report for current 24-hour UTC day."""
        now = dt.datetime.now(dt.timezone.utc)
        start_of_day = dt.datetime(now.year, now.month, now.day, tzinfo=dt.timezone.utc)
        start_ts = start_of_day.timestamp()
        end_ts = start_ts + 86400
        return self.get_financial_report(guild_id, start_ts, end_ts, period_name="Today's Performance")

    def get_weekly_report(self, guild_id: Optional[int]) -> dict[str, Any]:
        """Report for the current 7-day period."""
        now = dt.datetime.now(dt.timezone.utc)
        start_of_week = now - dt.timedelta(days=7)
        return self.get_financial_report(guild_id, start_of_week.timestamp(), now.timestamp(), period_name="Weekly Performance (Last 7 Days)")

    def get_monthly_report(self, guild_id: Optional[int]) -> dict[str, Any]:
        """Report for the current 30-day period."""
        now = dt.datetime.now(dt.timezone.utc)
        start_of_month = now - dt.timedelta(days=30)
        return self.get_financial_report(guild_id, start_of_month.timestamp(), now.timestamp(), period_name="Monthly Performance (Last 30 Days)")

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
        """Submit a new staff application with cooldown & duplicate check."""
        with self._get_connection() as conn:
            # Check for existing pending application
            existing = conn.execute("""
                SELECT id, status, created_at FROM top_applications
                WHERE guild_id = ? AND applicant_id = ? AND status IN ('PENDING', 'UNDER_REVIEW')
            """, (guild_id, applicant_id)).fetchone()

            if existing:
                raise ValueError(
                    f"You already have an active application ({existing['id']}) with status '{existing['status']}'. "
                    f"Please wait for staff review."
                )

            # Check cooldown config
            cfg = conn.execute("SELECT cooldown_days FROM top_applications_config WHERE guild_id = ?", (guild_id,)).fetchone()
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
        """Review application: ACCEPTED, REJECTED, or UNDER_REVIEW."""
        app = self.get_application(app_id)
        if not app:
            raise KeyError(f"Application '{app_id}' not found.")

        target_status = new_status.strip().upper()
        if target_status not in ("ACCEPTED", "REJECTED", "UNDER_REVIEW", "WITHDRAWN"):
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

    def get_app_config(self, guild_id: int) -> dict[str, Any]:
        """Get guild staff application config."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM top_applications_config WHERE guild_id = ?", (guild_id,)).fetchone()
            if row:
                return dict(row)
            return {
                "guild_id": guild_id,
                "review_channel_id": None,
                "role_on_accept_id": None,
                "cooldown_days": 7,
                "default_tax": 0.0,
            }

    def set_app_config(
        self,
        guild_id: int,
        review_channel_id: Optional[int] = None,
        role_on_accept_id: Optional[int] = None,
        cooldown_days: Optional[int] = None,
        default_tax: Optional[float] = None,
    ) -> dict[str, Any]:
        """Save guild staff application config."""
        cur = self.get_app_config(guild_id)
        r_ch = review_channel_id if review_channel_id is not None else cur.get("review_channel_id")
        r_role = role_on_accept_id if role_on_accept_id is not None else cur.get("role_on_accept_id")
        c_days = cooldown_days if cooldown_days is not None else cur.get("cooldown_days", 7)
        d_tax = default_tax if default_tax is not None else cur.get("default_tax", 0.0)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO top_applications_config (
                    guild_id, review_channel_id, role_on_accept_id, cooldown_days, default_tax
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    review_channel_id = excluded.review_channel_id,
                    role_on_accept_id = excluded.role_on_accept_id,
                    cooldown_days = excluded.cooldown_days,
                    default_tax = excluded.default_tax
            """, (guild_id, r_ch, r_role, c_days, d_tax))
            conn.commit()

        return self.get_app_config(guild_id)
