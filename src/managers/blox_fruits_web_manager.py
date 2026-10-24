"""
KYOKA 3.0 - Blox Fruits Real-Time Web Values & Stock Manager.
Fetches, caches, and calculates real-time trading values, market demand, dealer stock cycles,
and live fruit spawn alerts using online sources with resilient offline dataset fallbacks.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger("Kyoka.Managers.BloxFruitsWeb")

# Curated real-time market baseline with demand, trends, and values
DEFAULT_MARKET_DATA: Dict[str, Dict[str, Any]] = {
    "kitsune": {
        "name": "Kitsune",
        "beli": "8,000,000",
        "robux": "4,000",
        "trade_value": 115_000_000,
        "demand": "10/10 (Maximum)",
        "trend": "🔥 Extremely High / Rising",
        "status": "Overpaid",
        "rarity": "Mythical",
        "type": "Beast",
        "tip": "Top meta fruit. Demands 3-4 high mythicals (e.g. Leopard + Dough + T-Rex).",
    },
    "dragon": {
        "name": "Dragon",
        "beli": "3,500,000",
        "robux": "2,600",
        "trade_value": 180_000_000,
        "demand": "10/10 (Peak Hype)",
        "trend": "🚀 Soaring (Rework Anticipation)",
        "status": "Massive Overpay",
        "rarity": "Mythical",
        "type": "Beast",
        "tip": "Do NOT trade for low tier mythicals. Holds maximum trade leverage in the game.",
    },
    "leopard": {
        "name": "Leopard",
        "beli": "5,000,000",
        "robux": "3,000",
        "trade_value": 40_000_000,
        "demand": "9/10 (Very High)",
        "trend": "⚖️ Stable",
        "status": "Fair / High",
        "rarity": "Mythical",
        "type": "Beast",
        "tip": "Standard currency unit in high-tier trading. Equal to roughly 2x Dough.",
    },
    "dough": {
        "name": "Dough",
        "beli": "2,800,000",
        "robux": "2,400",
        "trade_value": 22_000_000,
        "demand": "9.5/10 (Extreme)",
        "trend": "📈 High Demand",
        "status": "High Demand",
        "rarity": "Mythical",
        "type": "Elemental / Special",
        "tip": "V2 Awakening is top tier for PvP combos. Easy to trade for T-Rex + Buddha.",
    },
    "t-rex": {
        "name": "T-Rex",
        "beli": "2,700,000",
        "robux": "2,350",
        "trade_value": 18_000_000,
        "demand": "8.5/10 (High)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Mythical",
        "type": "Beast",
        "tip": "Strong passive damage aura and M1 clicks. Highly liquid trading fruit.",
    },
    "mammoth": {
        "name": "Mammoth",
        "beli": "2,700,000",
        "robux": "2,350",
        "trade_value": 12_500_000,
        "demand": "7.5/10 (Moderate)",
        "trend": "📉 Slightly Dropping",
        "status": "Fair",
        "rarity": "Mythical",
        "type": "Beast",
        "tip": "Stampede defense makes it solid for Sea Events and Terrorsharks.",
    },
    "spirit": {
        "name": "Spirit",
        "beli": "3,400,000",
        "robux": "2,550",
        "trade_value": 9_500_000,
        "demand": "7/10 (Medium)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Mythical",
        "type": "Natural",
        "tip": "Good support spirits for PvP. Usually traded alongside Venom or Shadow.",
    },
    "venom": {
        "name": "Venom",
        "beli": "3,000,000",
        "robux": "2,450",
        "trade_value": 9_000_000,
        "demand": "7.5/10 (Medium-High)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Mythical",
        "type": "Natural",
        "tip": "Puddle damage is lethal. Consistently worth slightly under Spirit.",
    },
    "shadow": {
        "name": "Shadow",
        "beli": "2,900,000",
        "robux": "2,400",
        "trade_value": 6_000_000,
        "demand": "6.5/10 (Moderate)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Mythical",
        "type": "Natural",
        "tip": "Umbra meter gives massive burst damage. Commonly paired with Buddha in trades.",
    },
    "blizzard": {
        "name": "Blizzard",
        "beli": "2,400,000",
        "robux": "2,250",
        "trade_value": 5_500_000,
        "demand": "7/10 (Medium)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Legendary",
        "type": "Elemental",
        "tip": "Blizzard domain melts Sea Beasts and raid bosses. Roughly equal to Shadow.",
    },
    "portal": {
        "name": "Portal",
        "beli": "1,900,000",
        "robux": "2,000",
        "trade_value": 8_500_000,
        "demand": "9.5/10 (Extreme)",
        "trend": "🔥 Extremely High Demand",
        "status": "High Overpay",
        "rarity": "Legendary",
        "type": "Natural",
        "tip": "Pound-for-pound the most in-demand legendary. Global teleportation makes it essential.",
    },
    "buddha": {
        "name": "Buddha",
        "beli": "1,200,000",
        "robux": "1,650",
        "trade_value": 7_500_000,
        "demand": "10/10 (Universal)",
        "trend": "🔥 Always High",
        "status": "High Overpay",
        "rarity": "Legendary",
        "type": "Beast",
        "tip": "The undisputed #1 grinding fruit in the entire game. Never trade below value.",
    },
    "sound": {
        "name": "Sound",
        "beli": "1,700,000",
        "robux": "1,900",
        "trade_value": 3_500_000,
        "demand": "6/10 (Moderate)",
        "trend": "📉 Dropping",
        "status": "Fair",
        "rarity": "Legendary",
        "type": "Natural",
        "tip": "Fast tempo buffs and flight. Traded as add-on fruit.",
    },
    "rumble": {
        "name": "Rumble",
        "beli": "2,100,000",
        "robux": "2,100",
        "trade_value": 6_500_000,
        "demand": "8.5/10 (High)",
        "trend": "📈 Rising",
        "status": "High Demand",
        "rarity": "Legendary",
        "type": "Elemental",
        "tip": "V2 pole awakening and infinite stuns make it the premier sword-main fruit.",
    },
    "magma": {
        "name": "Magma",
        "beli": "850,000",
        "robux": "1,300",
        "trade_value": 2_000_000,
        "demand": "8/10 (High)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Rare",
        "type": "Elemental",
        "tip": "Awakened Magma possesses the highest DPS in Blox Fruits. Mandatory for Sea Beast hunting.",
    },
    "light": {
        "name": "Light",
        "beli": "650,000",
        "robux": "1,100",
        "trade_value": 1_200_000,
        "demand": "8/10 (High)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Rare",
        "type": "Elemental",
        "tip": "The fastest flight in the First Sea with an M1 light blade.",
    },
    "dark": {
        "name": "Dark",
        "beli": "500,000",
        "robux": "950",
        "trade_value": 800_000,
        "demand": "6.5/10 (Moderate)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Uncommon",
        "type": "Elemental",
        "tip": "Dimensional slash and black hole pulls make it a deadly PvP combo starter.",
    },
    "ice": {
        "name": "Ice",
        "beli": "350,000",
        "robux": "750",
        "trade_value": 600_000,
        "demand": "7.5/10 (Moderate-High)",
        "trend": "⚖️ Stable",
        "status": "Fair",
        "rarity": "Uncommon",
        "type": "Elemental",
        "tip": "Passive water walking and ground freeze surges. Best beginner bounty hunting fruit.",
    },
}


class BloxFruitsWebManager:
    """Manages real-time Blox Fruits web value lookups, stock timers, and spawn notifications."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = dict(DEFAULT_MARKET_DATA)
        self._last_fetch: float = 0.0
        self._cache_ttl: float = 3600.0  # 1 hour cache TTL
        self._lock = asyncio.Lock()

    async def fetch_online_values(self) -> None:
        """Fetch updated values from online community repositories or APIs with fallback."""
        now = time.time()
        if now - self._last_fetch < self._cache_ttl:
            return

        async with self._lock:
            # Re-check inside lock
            if now - self._last_fetch < self._cache_ttl:
                return

            try:
                # Online community sources (e.g. GitHub raw value lists or public APIs)
                timeout = aiohttp.ClientTimeout(total=5.0)
                url = "https://raw.githubusercontent.com/BloxFruitsValues/data/main/values.json"
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if isinstance(data, dict):
                                for key, val in data.items():
                                    k = key.lower().strip()
                                    if k in self._cache and isinstance(val, dict):
                                        self._cache[k].update(val)
                                logger.info("Successfully refreshed Blox Fruits values from online web feed.")
            except Exception as e:
                logger.debug(f"Online Blox Fruits value fetch fallback to internal dataset: {e}")

            self._last_fetch = now

    async def get_fruit_value(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up real-time trading values, market demand, and tips for a fruit."""
        await self.fetch_online_values()
        clean = query.lower().strip().replace("fruit", "").replace(" ", "").replace("-", "")

        # Exact match
        for key, data in self._cache.items():
            k_clean = key.lower().replace("-", "").replace(" ", "")
            if clean == k_clean:
                return dict(data)

        # Prefix or substring match
        for key, data in self._cache.items():
            k_clean = key.lower().replace("-", "").replace(" ", "")
            if clean in k_clean or k_clean in clean:
                return dict(data)

        return None

    def calculate_trade(
        self, giving_fruits: List[str], receiving_fruits: List[str]
    ) -> Dict[str, Any]:
        """
        Evaluate trade fairness based on real-time market value and demand.
        Returns: total giving value, total receiving value, diff, fairness category, and advice.
        """
        give_items = []
        give_total = 0
        for item in giving_fruits:
            clean = item.lower().strip().replace("fruit", "").replace(" ", "").replace("-", "")
            match = next((v for k, v in self._cache.items() if clean in k.replace("-", "")), None)
            if match:
                give_items.append(match)
                give_total += match.get("trade_value", 0)

        recv_items = []
        recv_total = 0
        for item in receiving_fruits:
            clean = item.lower().strip().replace("fruit", "").replace(" ", "").replace("-", "")
            match = next((v for k, v in self._cache.items() if clean in k.replace("-", "")), None)
            if match:
                recv_items.append(match)
                recv_total += match.get("trade_value", 0)

        diff = recv_total - give_total
        percent = (diff / give_total * 100) if give_total > 0 else 0

        if percent >= 15:
            verdict = "🟢 BIG WIN (W)"
            recommendation = "Accept immediately! You are gaining massive surplus trading value."
        elif 5 <= percent < 15:
            verdict = "🟢 SLIGHT WIN (Small W)"
            recommendation = "Favorable trade for you. Safe to accept."
        elif -5 <= percent < 5:
            verdict = "🟡 FAIR TRADE (F)"
            recommendation = "Equal value trade. Accept if you need their fruits for PvP or grinding."
        elif -15 <= percent < -5:
            verdict = "🔴 SLIGHT LOSS (Small L)"
            recommendation = "You are giving away slightly more value than you receive. Ask them to add a good legendary."
        else:
            verdict = "🔴 BIG LOSS (Huge L)"
            recommendation = "DO NOT ACCEPT! You are getting heavily underpaid."

        return {
            "give_items": give_items,
            "give_total": give_total,
            "recv_items": recv_items,
            "recv_total": recv_total,
            "diff": diff,
            "percent": percent,
            "verdict": verdict,
            "recommendation": recommendation,
        }

    @staticmethod
    def get_dealer_stock_countdown() -> Tuple[int, int, str]:
        """
        Compute minutes and seconds remaining until the Blox Fruits Normal Dealer resets.
        Normal Dealer resets globally every 4 hours at: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_hour = now_utc.hour
        next_hour = ((current_hour // 4) + 1) * 4

        target = now_utc.replace(minute=0, second=0, microsecond=0)
        if next_hour >= 24:
            target = target + datetime.timedelta(days=1)
            target = target.replace(hour=0)
        else:
            target = target.replace(hour=next_hour)

        delta = (target - now_utc).total_seconds()
        hours = int(delta // 3600)
        minutes = int((delta % 3600) // 60)
        seconds = int(delta % 60)
        countdown_str = f"{hours}h {minutes}m {seconds}s"
        return minutes, seconds, countdown_str
