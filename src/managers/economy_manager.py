"""
KYOKA 3.0 — Advanced OwO-Style Economy Engine & Transaction Manager.
Provides:
- Thread-safe, atomic Postgres/Supabase transactions
- Per-server custom currency configuration (name, emoji, starting balance, rewards)
- Cooldown tracking with precision datetime math
- Inventory management, item shop, crates & trading
- Daily quests, achievement tracking & lottery system
- Exploitation & race-condition prevention (locks, atomic balance transfers)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

import discord


logger = logging.getLogger("Kyoka.EconomyManager")

# Default global shop catalog
DEFAULT_SHOP_ITEMS: list[dict[str, Any]] = [
    # Tools
    {"item_id": "fishing_rod", "name": "Standard Fishing Rod", "category": "tool", "price": 500, "sell_price": 250, "rarity": "common", "emoji": "🎣", "description": "Required to catch aquatic creatures with ?fishing."},
    {"item_id": "super_rod", "name": "Super Carbon Rod", "category": "tool", "price": 2500, "sell_price": 1250, "rarity": "rare", "emoji": "🪝", "description": "Increases chance of rare and legendary aquatic catches by +20%."},
    {"item_id": "pickaxe", "name": "Iron Pickaxe", "category": "tool", "price": 600, "sell_price": 300, "rarity": "common", "emoji": "⛏️", "description": "Used to extract precious ores and gems with ?mine."},
    {"item_id": "laser_pickaxe", "name": "Cyber Laser Pickaxe", "category": "tool", "price": 3500, "sell_price": 1750, "rarity": "epic", "emoji": "⚡", "description": "Drills deep into veins, yielding double ore yields and astral crystals."},
    # Weapons & Armor
    {"item_id": "zanpakuto_blade", "name": "Asauchi Zanpakuto", "category": "weapon", "price": 1500, "sell_price": 750, "rarity": "uncommon", "emoji": "⚔️", "description": "Base spiritual blade. Grants +35 Attack Power in adventures and dungeons."},
    {"item_id": "hollow_mask", "name": "Visored Hollow Mask", "category": "armor", "price": 4000, "sell_price": 2000, "rarity": "epic", "emoji": "👺", "description": "Increases Defense by +50 and boosts Critical Hit rate by +10%."},
    {"item_id": "kyoka_cloak", "name": "Aizen's Royal Cloak", "category": "armor", "price": 10000, "sell_price": 5000, "rarity": "legendary", "emoji": "🥋", "description": "Regal white-and-purple mantle. Grants +100 Defense and +200 HP."},
    # Consumables
    {"item_id": "energy_potion", "name": "Spiritual Elixir", "category": "consumable", "price": 250, "sell_price": 100, "rarity": "common", "emoji": "🧪", "description": "Fully restores pet stamina and player HP in dungeons."},
    {"item_id": "lucky_clover", "name": "Four-Leaf Clover", "category": "consumable", "price": 800, "sell_price": 350, "rarity": "rare", "emoji": "🍀", "description": "Increases luck in casino games and hunting for 30 minutes."},
    {"item_id": "pet_food", "name": "Gourmet Pet Kibble", "category": "consumable", "price": 150, "sell_price": 60, "rarity": "common", "emoji": "🍖", "description": "Delicious nutritious meal for feeding creatures to gain affection & XP."},
    # Reward Crates
    {"item_id": "wooden_crate", "name": "Wooden Supply Crate", "category": "crate", "price": 500, "sell_price": 200, "rarity": "common", "emoji": "📦", "description": "Contains common resources, modest cash bonuses, and hunting baits."},
    {"item_id": "silver_crate", "name": "Silver Treasure Chest", "category": "crate", "price": 1500, "sell_price": 600, "rarity": "rare", "emoji": "🧰", "description": "Guarantees rare items, coins, and a high chance of creature drops."},
    {"item_id": "gold_crate", "name": "Golden Relic Vault", "category": "crate", "price": 4500, "sell_price": 1800, "rarity": "epic", "emoji": "🪙", "description": "Contains large coin payouts, epic equipment, and rare creature spawns."},
    {"item_id": "celestial_crate", "name": "Kyoka Suigetsu Celestial Box", "category": "crate", "price": 15000, "sell_price": 6000, "rarity": "legendary", "emoji": "🌌", "description": "The ultimate prize box. Grants legendary gear, massive wealth, and mythical pets."},
]

WORK_JOBS: list[tuple[str, str]] = [
    ("Software Engineer", "fixed a critical memory leak in the production cluster"),
    ("Cyber Investigator", "traced an unauthorized intrusion back to a rogue server"),
    ("Coffee Barista", "brewed 140 bespoke iced lattes during the morning rush"),
    ("Soul Reaper Substitute", "patrolled Karakura Town and purified 3 lost souls"),
    ("Casino Dealer", "managed the high-roller blackjack table with flawless precision"),
    ("Treasure Appraiser", "authenticated a genuine ancient relic for a collector"),
    ("Discord Community Host", "hosted a 500-member trivia night without a single glitch"),
    ("Quantum Physicist", "calibrated the fusion reactor containment field"),
    ("Anime Illustrator", "completed a full-color promotional manga commission"),
    ("Cybersecurity Consultant", "conducted a successful penetration test for a financial firm"),
]

CRIME_OUTCOMES_SUCCESS: list[tuple[str, str]] = [
    ("Heist Master", "infiltrated the high-security bank vault and cracked the digital safe"),
    ("Cyber Hack", "breached an encrypted offshore slush fund and redirected the balance"),
    ("Art Thief", "swapped an invaluable gallery painting with a flawless counterfeit"),
    ("Street Hustler", "won an underground high-stakes backroom card game"),
    ("Smuggler", "delivered a covert crate of rare contraband past the border patrol"),
]

CRIME_OUTCOMES_FAILURE: list[str] = [
    "tripped the laser alarm and had to bribe the guard to escape",
    "was caught on high-definition surveillance and got fined by local authorities",
    "encountered an undercover cyber officer and lost your tools",
    "dropped your wallet while sprinting away from security",
    "got double-crossed by your accomplice and lost your payout",
]

BEG_DONORS: list[str] = [
    "Sosuke Aizen, who tossed a pouch of coins with a knowing smirk",
    "Yoruichi Shihoin, who handed you coins before vanishing in a flash",
    "Kisuke Urahara, who offered you coins in exchange for testing a gadget",
    "A wealthy traveling merchant passing through the server",
    "A kind-hearted server regular who noticed you were low on cash",
    "A retired arena champion who gave you spare winnings",
]


class EconomyManager:
    """Core OwO-style economy business logic and persistent state manager."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self._guild_settings_cache: dict[int, dict[str, Any]] = {}
        self._items_cache: dict[str, dict[str, Any]] = {}
        self._tx_lock = asyncio.Lock()
        self._user_locks: dict[Tuple[int, int], asyncio.Lock] = {}

    def _get_user_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        if key not in self._user_locks:
            self._user_locks[key] = asyncio.Lock()
        return self._user_locks[key]

    async def init_catalog(self) -> None:
        """Seed default shop items catalog into database if missing."""
        try:
            for item in DEFAULT_SHOP_ITEMS:
                await self.db.execute(
                    """
                    INSERT INTO economy_items (item_id, name, category, price, sell_price, rarity, emoji, description)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (item_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        price = EXCLUDED.price,
                        sell_price = EXCLUDED.sell_price,
                        description = EXCLUDED.description,
                        emoji = EXCLUDED.emoji;
                    """,
                    item["item_id"], item["name"], item["category"], item["price"],
                    item["sell_price"], item["rarity"], item["emoji"], item["description"]
                )
            logger.info("Economy items catalog verified and synchronized.")
        except Exception as e:
            logger.warning(f"Notice initializing economy items catalog: {e}")

    async def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        """Fetch server economy configuration with automatic default fallback."""
        if guild_id in self._guild_settings_cache:
            return self._guild_settings_cache[guild_id]

        row = await self.db.fetch_one(
            "SELECT * FROM economy_guild_settings WHERE guild_id = $1;", guild_id
        )
        if not row:
            defaults = {
                "guild_id": guild_id,
                "currency_name": "KYOKA Coins",
                "currency_emoji": "🪙",
                "starting_balance": 1000,
                "daily_reward": 500,
                "weekly_reward": 2500,
                "work_min": 100,
                "work_max": 400,
                "crime_min": 200,
                "crime_max": 800,
                "robbing_enabled": True,
                "gamble_limit": 50000,
                "event_multiplier": 1.0,
            }
            try:
                await self.db.execute(
                    """
                    INSERT INTO economy_guild_settings (guild_id, currency_name, currency_emoji, starting_balance, daily_reward, weekly_reward, work_min, work_max, crime_min, crime_max, robbing_enabled, gamble_limit, event_multiplier)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (guild_id) DO NOTHING;
                    """,
                    guild_id, defaults["currency_name"], defaults["currency_emoji"],
                    defaults["starting_balance"], defaults["daily_reward"], defaults["weekly_reward"],
                    defaults["work_min"], defaults["work_max"], defaults["crime_min"],
                    defaults["crime_max"], defaults["robbing_enabled"], defaults["gamble_limit"],
                    defaults["event_multiplier"]
                )
            except Exception as e:
                logger.debug(f"Error persisting default guild settings: {e}")
            self._guild_settings_cache[guild_id] = defaults
            return defaults

        data = dict(row)
        self._guild_settings_cache[guild_id] = data
        return data

    async def update_guild_settings(self, guild_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update server economy configuration."""
        settings = await self.get_guild_settings(guild_id)
        valid_keys = {
            "currency_name", "currency_emoji", "starting_balance", "daily_reward",
            "weekly_reward", "work_min", "work_max", "crime_min", "crime_max",
            "robbing_enabled", "gamble_limit", "event_multiplier"
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_keys}
        if not updates:
            return settings

        set_clauses = [f"{k} = ${i+2}" for i, k in enumerate(updates.keys())]
        query = f"UPDATE economy_guild_settings SET {', '.join(set_clauses)} WHERE guild_id = $1;"
        await self.db.execute(query, guild_id, *updates.values())
        self._guild_settings_cache.pop(guild_id, None)
        return await self.get_guild_settings(guild_id)

    async def get_or_create_profile(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve user economy profile or initialize with server starting balance."""
        row = await self.db.fetch_one(
            "SELECT * FROM user_profiles WHERE guild_id = $1 AND user_id = $2;",
            guild_id, user_id
        )
        if not row:
            settings = await self.get_guild_settings(guild_id)
            start_bal = settings.get("starting_balance", 1000)
            try:
                await self.db.execute(
                    """
                    INSERT INTO user_profiles (guild_id, user_id, balance, bank, xp, level, daily_streak, weekly_streak, total_earned, total_spent)
                    VALUES ($1, $2, $3, 0, 0, 1, 0, 0, $3, 0)
                    ON CONFLICT (user_id, guild_id) DO NOTHING;
                    """,
                    guild_id, user_id, start_bal
                )
            except Exception as e:
                logger.debug(f"Notice creating user profile: {e}")

            row = await self.db.fetch_one(
                "SELECT * FROM user_profiles WHERE guild_id = $1 AND user_id = $2;",
                guild_id, user_id
            )

        if not row:
            return {
                "guild_id": guild_id, "user_id": user_id,
                "balance": 1000, "bank": 0, "xp": 0, "level": 1,
                "daily_streak": 0, "weekly_streak": 0, "total_earned": 1000, "total_spent": 0,
                "last_daily": None, "last_weekly": None, "last_work": None,
                "last_crime": None, "last_rob": None
            }
        return dict(row)

    async def update_balance(
        self,
        guild_id: int,
        user_id: int,
        wallet_delta: int = 0,
        bank_delta: int = 0,
        tx_type: str = "generic",
        metadata: str = ""
    ) -> Tuple[int, int]:
        """
        Thread-safe atomic balance update preventing negative wallet balances.
        Returns (new_wallet, new_bank).
        """
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            curr_wallet = profile.get("balance", 0)
            curr_bank = profile.get("bank", 0)

            new_wallet = curr_wallet + wallet_delta
            new_bank = curr_bank + bank_delta

            if new_wallet < 0:
                raise ValueError("Insufficient wallet balance.")
            if new_bank < 0:
                raise ValueError("Insufficient bank balance.")

            total_earned_delta = max(0, wallet_delta)
            total_spent_delta = abs(min(0, wallet_delta))

            await self.db.execute(
                """
                UPDATE user_profiles
                SET balance = $3, bank = $4,
                    total_earned = total_earned + $5,
                    total_spent = total_spent + $6
                WHERE guild_id = $1 AND user_id = $2;
                """,
                guild_id, user_id, new_wallet, new_bank, total_earned_delta, total_spent_delta
            )

            # Record atomic transaction log
            try:
                await self.db.execute(
                    """
                    INSERT INTO economy_transactions (guild_id, sender_id, receiver_id, amount, tx_type, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6);
                    """,
                    guild_id, user_id, None, wallet_delta + bank_delta, tx_type, metadata
                )
            except Exception as e:
                logger.debug(f"Error logging transaction: {e}")

            return new_wallet, new_bank

    async def transfer_funds(
        self,
        guild_id: int,
        sender_id: int,
        receiver_id: int,
        amount: int
    ) -> Tuple[int, int]:
        """
        Atomic fund transfer between two users with dual-lock acquisition.
        Prevents race condition double-spending and self-transfers.
        """
        if sender_id == receiver_id:
            raise ValueError("You cannot transfer money to yourself.")
        if amount <= 0:
            raise ValueError("Transfer amount must be a positive integer.")

        # Always lock in consistent order (smaller ID first) to avoid deadlocks
        first_id, second_id = (sender_id, receiver_id) if sender_id < receiver_id else (receiver_id, sender_id)
        lock1 = self._get_user_lock(guild_id, first_id)
        lock2 = self._get_user_lock(guild_id, second_id)

        async with lock1:
            async with lock2:
                sender_prof = await self.get_or_create_profile(guild_id, sender_id)
                receiver_prof = await self.get_or_create_profile(guild_id, receiver_id)

                if sender_prof.get("balance", 0) < amount:
                    raise ValueError(f"You only have **{sender_prof.get('balance', 0):,}** in your wallet!")

                sender_new = sender_prof.get("balance", 0) - amount
                receiver_new = receiver_prof.get("balance", 0) + amount

                await self.db.execute(
                    "UPDATE user_profiles SET balance = $3, total_spent = total_spent + $4 WHERE guild_id = $1 AND user_id = $2;",
                    guild_id, sender_id, sender_new, amount
                )
                await self.db.execute(
                    "UPDATE user_profiles SET balance = $3, total_earned = total_earned + $4 WHERE guild_id = $1 AND user_id = $2;",
                    guild_id, receiver_id, receiver_new, amount
                )

                try:
                    await self.db.execute(
                        """
                        INSERT INTO economy_transactions (guild_id, sender_id, receiver_id, amount, tx_type, metadata)
                        VALUES ($1, $2, $3, $4, 'transfer', 'User to user direct transfer');
                        """,
                        guild_id, sender_id, receiver_id, amount
                    )
                except Exception as e:
                    logger.debug(f"Notice recording transfer tx: {e}")

                return sender_new, receiver_new

    async def claim_daily(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Claim daily reward with streak multipliers and event scaling."""
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            settings = await self.get_guild_settings(guild_id)
            now = discord.utils.utcnow()

            last_daily = profile.get("last_daily")
            if last_daily:
                if last_daily.tzinfo is None:
                    last_daily = last_daily.replace(tzinfo=dt.timezone.utc)
                diff = (now - last_daily).total_seconds()
                if diff < 86400:
                    remaining = int(86400 - diff)
                    return {"success": False, "remaining": remaining}

            # Check streak
            curr_streak = profile.get("daily_streak", 0)
            if last_daily:
                # If claimed within 48 hours, streak continues; otherwise reset
                if (now - last_daily).total_seconds() > (86400 * 2):
                    curr_streak = 0
            curr_streak += 1

            base_reward = settings.get("daily_reward", 500)
            # Streak bonus: +5% per day up to +100%
            streak_mult = 1.0 + min(1.0, (curr_streak - 1) * 0.05)
            event_mult = float(settings.get("event_multiplier", 1.0))

            total_payout = int(base_reward * streak_mult * event_mult)
            new_wallet = profile.get("balance", 0) + total_payout

            await self.db.execute(
                """
                UPDATE user_profiles
                SET balance = $3, last_daily = $4, daily_streak = $5, total_earned = total_earned + $6
                WHERE guild_id = $1 AND user_id = $2;
                """,
                guild_id, user_id, new_wallet, now, curr_streak, total_payout
            )

            # Auto increment daily quest
            await self.increment_quest(guild_id, user_id, "claim_daily", 1)

            return {
                "success": True,
                "amount": total_payout,
                "streak": curr_streak,
                "new_balance": new_wallet,
                "event_multiplier": event_mult,
            }

    async def claim_weekly(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Claim weekly reward with streak multipliers and event scaling."""
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            settings = await self.get_guild_settings(guild_id)
            now = discord.utils.utcnow()

            last_weekly = profile.get("last_weekly")
            if last_weekly:
                if last_weekly.tzinfo is None:
                    last_weekly = last_weekly.replace(tzinfo=dt.timezone.utc)
                diff = (now - last_weekly).total_seconds()
                if diff < 604800:
                    remaining = int(604800 - diff)
                    return {"success": False, "remaining": remaining}

            curr_streak = profile.get("weekly_streak", 0)
            if last_weekly and (now - last_weekly).total_seconds() > (604800 * 2):
                curr_streak = 0
            curr_streak += 1

            base_reward = settings.get("weekly_reward", 2500)
            streak_mult = 1.0 + min(1.0, (curr_streak - 1) * 0.10)
            event_mult = float(settings.get("event_multiplier", 1.0))

            total_payout = int(base_reward * streak_mult * event_mult)
            new_wallet = profile.get("balance", 0) + total_payout

            await self.db.execute(
                """
                UPDATE user_profiles
                SET balance = $3, last_weekly = $4, weekly_streak = $5, total_earned = total_earned + $6
                WHERE guild_id = $1 AND user_id = $2;
                """,
                guild_id, user_id, new_wallet, now, curr_streak, total_payout
            )

            return {
                "success": True,
                "amount": total_payout,
                "streak": curr_streak,
                "new_balance": new_wallet,
                "event_multiplier": event_mult,
            }

    async def work(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Work random jobs for dynamic earnings. Cooldown: 300 seconds (5 min)."""
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            settings = await self.get_guild_settings(guild_id)
            now = discord.utils.utcnow()

            last_work = profile.get("last_work")
            if last_work:
                if last_work.tzinfo is None:
                    last_work = last_work.replace(tzinfo=dt.timezone.utc)
                diff = (now - last_work).total_seconds()
                if diff < 300:
                    return {"success": False, "remaining": int(300 - diff)}

            min_w = settings.get("work_min", 100)
            max_w = settings.get("work_max", 400)
            event_mult = float(settings.get("event_multiplier", 1.0))
            earned = int(random.randint(min_w, max_w) * event_mult)

            role, desc = random.choice(WORK_JOBS)
            new_bal = profile.get("balance", 0) + earned

            await self.db.execute(
                """
                UPDATE user_profiles
                SET balance = $3, last_work = $4, total_earned = total_earned + $5
                WHERE guild_id = $1 AND user_id = $2;
                """,
                guild_id, user_id, new_bal, now, earned
            )

            await self.increment_quest(guild_id, user_id, "work", 1)

            return {
                "success": True,
                "role": role,
                "action": desc,
                "amount": earned,
                "new_balance": new_bal,
            }

    async def crime(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """High-risk high-reward crime action. Cooldown: 600 seconds (10 min)."""
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            settings = await self.get_guild_settings(guild_id)
            now = discord.utils.utcnow()

            last_crime = profile.get("last_crime")
            if last_crime:
                if last_crime.tzinfo is None:
                    last_crime = last_crime.replace(tzinfo=dt.timezone.utc)
                diff = (now - last_crime).total_seconds()
                if diff < 600:
                    return {"success": False, "remaining": int(600 - diff)}

            min_c = settings.get("crime_min", 200)
            max_c = settings.get("crime_max", 800)
            event_mult = float(settings.get("event_multiplier", 1.0))

            # 55% success, 45% failure
            success = random.random() < 0.55

            if success:
                earned = int(random.randint(min_c, max_c) * event_mult)
                role, desc = random.choice(CRIME_OUTCOMES_SUCCESS)
                new_bal = profile.get("balance", 0) + earned
                await self.db.execute(
                    """
                    UPDATE user_profiles
                    SET balance = $3, last_crime = $4, total_earned = total_earned + $5
                    WHERE guild_id = $1 AND user_id = $2;
                    """,
                    guild_id, user_id, new_bal, now, earned
                )
                await self.increment_quest(guild_id, user_id, "crime", 1)
                return {
                    "success": True,
                    "outcome": "success",
                    "role": role,
                    "action": desc,
                    "amount": earned,
                    "new_balance": new_bal,
                }
            else:
                fine = int(random.randint(min_c // 2, max_c // 2))
                curr_bal = profile.get("balance", 0)
                fine = min(fine, curr_bal)  # Don't drop below zero
                new_bal = curr_bal - fine
                desc = random.choice(CRIME_OUTCOMES_FAILURE)
                await self.db.execute(
                    """
                    UPDATE user_profiles
                    SET balance = $3, last_crime = $4, total_spent = total_spent + $5
                    WHERE guild_id = $1 AND user_id = $2;
                    """,
                    guild_id, user_id, new_bal, now, fine
                )
                return {
                    "success": True,
                    "outcome": "failure",
                    "action": desc,
                    "fine": fine,
                    "new_balance": new_bal,
                }

    async def beg(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Beg for money from notable figures. Cooldown: 120 seconds (2 min)."""
        lock = self._get_user_lock(guild_id, user_id)
        async with lock:
            profile = await self.get_or_create_profile(guild_id, user_id)
            now = discord.utils.utcnow()

            last_beg = profile.get("last_work")  # Re-use or track in memory
            min_reward, max_reward = 25, 120

            # 15% chance nothing
            if random.random() < 0.15:
                return {"amount": 0, "donor": "A passerby ignored your requests and walked away."}

            amount = random.randint(min_reward, max_reward)
            donor = random.choice(BEG_DONORS)
            new_bal = profile.get("balance", 0) + amount

            await self.db.execute(
                "UPDATE user_profiles SET balance = $3, total_earned = total_earned + $4 WHERE guild_id = $1 AND user_id = $2;",
                guild_id, user_id, new_bal, amount
            )
            return {"amount": amount, "donor": donor, "new_balance": new_bal}

    async def rob(self, guild_id: int, robber_id: int, target_id: int) -> dict[str, Any]:
        """Attempt to rob another member. Cooldown: 1800s (30 min)."""
        if robber_id == target_id:
            return {"error": "You cannot rob yourself!"}

        settings = await self.get_guild_settings(guild_id)
        if not settings.get("robbing_enabled", True):
            return {"error": "Robbing is disabled on this server."}

        lock1 = self._get_user_lock(guild_id, min(robber_id, target_id))
        lock2 = self._get_user_lock(guild_id, max(robber_id, target_id))

        async with lock1:
            async with lock2:
                robber_prof = await self.get_or_create_profile(guild_id, robber_id)
                target_prof = await self.get_or_create_profile(guild_id, target_id)
                now = discord.utils.utcnow()

                last_rob = robber_prof.get("last_rob")
                if last_rob:
                    if last_rob.tzinfo is None:
                        last_rob = last_rob.replace(tzinfo=dt.timezone.utc)
                    diff = (now - last_rob).total_seconds()
                    if diff < 1800:
                        return {"error": f"You must wait **{int((1800 - diff) // 60)}m {int((1800 - diff) % 60)}s** before robbing again."}

                target_bal = target_prof.get("balance", 0)
                if target_bal < 200:
                    return {"error": "This user does not have enough wallet cash to be worth robbing (minimum 200)!"}

                robber_bal = robber_prof.get("balance", 0)
                if robber_bal < 100:
                    return {"error": "You need at least 100 coins in your wallet to cover potential police fines!"}

                # 45% success rate
                success = random.random() < 0.45

                if success:
                    steal_pct = random.uniform(0.12, 0.35)
                    stolen = max(10, int(target_bal * steal_pct))

                    robber_new = robber_bal + stolen
                    target_new = target_bal - stolen

                    await self.db.execute(
                        "UPDATE user_profiles SET balance = $3, last_rob = $4, total_earned = total_earned + $5 WHERE guild_id = $1 AND user_id = $2;",
                        guild_id, robber_id, robber_new, now, stolen
                    )
                    await self.db.execute(
                        "UPDATE user_profiles SET balance = $3, total_spent = total_spent + $4 WHERE guild_id = $1 AND user_id = $2;",
                        guild_id, target_id, target_new, stolen
                    )
                    return {"success": True, "stolen": stolen, "new_balance": robber_new}
                else:
                    fine = min(robber_bal, random.randint(100, 300))
                    robber_new = robber_bal - fine
                    # Compensate victim with part of fine
                    target_new = target_bal + (fine // 2)

                    await self.db.execute(
                        "UPDATE user_profiles SET balance = $3, last_rob = $4, total_spent = total_spent + $5 WHERE guild_id = $1 AND user_id = $2;",
                        guild_id, robber_id, robber_new, now, fine
                    )
                    await self.db.execute(
                        "UPDATE user_profiles SET balance = $3, total_earned = total_earned + $4 WHERE guild_id = $1 AND user_id = $2;",
                        guild_id, target_id, target_new, fine // 2
                    )
                    return {"success": False, "fine": fine, "new_balance": robber_new}

    async def get_rich_leaderboard(self, guild_id: int, page: int = 1, per_page: int = 10) -> Tuple[list[dict[str, Any]], int]:
        """Fetch rich leaderboard sorted by total net worth (balance + bank)."""
        offset = max(0, (page - 1) * per_page)
        total_row = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM user_profiles WHERE guild_id = $1 AND (balance + bank) > 0;",
            guild_id
        )
        total_count = total_row["count"] if total_row else 0

        rows = await self.db.fetch_all(
            """
            SELECT user_id, balance, bank, (balance + bank) as net_worth, level, daily_streak
            FROM user_profiles
            WHERE guild_id = $1 AND (balance + bank) > 0
            ORDER BY (balance + bank) DESC
            LIMIT $2 OFFSET $3;
            """,
            guild_id, per_page, offset
        )
        return [dict(r) for r in rows], total_count

    async def get_shop_items(self) -> list[dict[str, Any]]:
        """Fetch shop item catalog."""
        rows = await self.db.fetch_all("SELECT * FROM economy_items ORDER BY price ASC;")
        if not rows:
            await self.init_catalog()
            rows = await self.db.fetch_all("SELECT * FROM economy_items ORDER BY price ASC;")
        return [dict(r) for r in rows]

    async def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        """Fetch single item by ID or name."""
        row = await self.db.fetch_one(
            "SELECT * FROM economy_items WHERE LOWER(item_id) = LOWER($1) OR LOWER(name) = LOWER($1);",
            item_id.strip()
        )
        return dict(row) if row else None

    async def buy_item(self, guild_id: int, user_id: int, item_id: str, quantity: int = 1) -> dict[str, Any]:
        """Purchase an item from shop."""
        if quantity <= 0:
            return {"error": "Quantity must be greater than zero!"}

        item = await self.get_item(item_id)
        if not item:
            return {"error": f"Item `{item_id}` not found in the shop! Use `?shop` to browse."}

        total_cost = item["price"] * quantity
        profile = await self.get_or_create_profile(guild_id, user_id)
        if profile.get("balance", 0) < total_cost:
            return {"error": f"You don't have enough cash! Cost: **{total_cost:,}**, Wallet: **{profile.get('balance', 0):,}**."}

        # Deduct wallet atomically
        await self.update_balance(guild_id, user_id, wallet_delta=-total_cost, tx_type="shop_buy", metadata=f"Bought {quantity}x {item['item_id']}")

        # Upsert into inventory
        await self.db.execute(
            """
            INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity, updated_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, user_id, item_id)
            DO UPDATE SET quantity = economy_inventory.quantity + EXCLUDED.quantity, updated_at = CURRENT_TIMESTAMP;
            """,
            guild_id, user_id, item["item_id"], quantity
        )

        return {"success": True, "item": item, "quantity": quantity, "total_cost": total_cost}

    async def sell_item(self, guild_id: int, user_id: int, item_id: str, quantity: int = 1) -> dict[str, Any]:
        """Sell an item from user inventory."""
        if quantity <= 0:
            return {"error": "Quantity must be greater than zero!"}

        item = await self.get_item(item_id)
        if not item:
            return {"error": f"Item `{item_id}` not recognized!"}

        inv_row = await self.db.fetch_one(
            "SELECT quantity FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;",
            guild_id, user_id, item["item_id"]
        )
        if not inv_row or inv_row["quantity"] < quantity:
            owned = inv_row["quantity"] if inv_row else 0
            return {"error": f"You only have **{owned}x {item['name']}** in your inventory!"}

        payout = item["sell_price"] * quantity
        new_qty = inv_row["quantity"] - quantity

        if new_qty <= 0:
            await self.db.execute(
                "DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;",
                guild_id, user_id, item["item_id"]
            )
        else:
            await self.db.execute(
                "UPDATE economy_inventory SET quantity = $4 WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;",
                guild_id, user_id, item["item_id"], new_qty
            )

        await self.update_balance(guild_id, user_id, wallet_delta=payout, tx_type="shop_sell", metadata=f"Sold {quantity}x {item['item_id']}")
        return {"success": True, "item": item, "quantity": quantity, "payout": payout}

    async def get_inventory(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        """Fetch user inventory items with details."""
        rows = await self.db.fetch_all(
            """
            SELECT i.item_id, i.name, i.category, i.rarity, i.emoji, i.description, inv.quantity, inv.equipped
            FROM economy_inventory inv
            JOIN economy_items i ON inv.item_id = i.item_id
            WHERE inv.guild_id = $1 AND inv.user_id = $2 AND inv.quantity > 0
            ORDER BY i.price DESC;
            """,
            guild_id, user_id
        )
        return [dict(r) for r in rows]

    async def open_crate(self, guild_id: int, user_id: int, crate_id: str) -> dict[str, Any]:
        """Open a reward crate from inventory."""
        inv_row = await self.db.fetch_one(
            "SELECT quantity FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;",
            guild_id, user_id, crate_id
        )
        if not inv_row or inv_row["quantity"] <= 0:
            return {"error": f"You don't own any `{crate_id}`! Purchase one from `?shop`."}

        # Deduct 1 crate
        if inv_row["quantity"] == 1:
            await self.db.execute("DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;", guild_id, user_id, crate_id)
        else:
            await self.db.execute("UPDATE economy_inventory SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;", guild_id, user_id, crate_id)

        # Rewards table by crate tier
        loot_table = {
            "wooden_crate": {"cash_range": (200, 800), "items": ["pet_food", "energy_potion"]},
            "silver_crate": {"cash_range": (800, 2500), "items": ["fishing_rod", "pickaxe", "lucky_clover"]},
            "gold_crate": {"cash_range": (2500, 8000), "items": ["super_rod", "laser_pickaxe", "zanpakuto_blade"]},
            "celestial_crate": {"cash_range": (10000, 30000), "items": ["hollow_mask", "kyoka_cloak", "laser_pickaxe"]},
        }
        config = loot_table.get(crate_id, loot_table["wooden_crate"])
        cash_won = random.randint(*config["cash_range"])
        item_won_id = random.choice(config["items"]) if random.random() < 0.65 else None

        await self.update_balance(guild_id, user_id, wallet_delta=cash_won, tx_type="crate_open", metadata=f"Opened {crate_id}")

        item_won = None
        if item_won_id:
            item_won = await self.get_item(item_won_id)
            if item_won:
                await self.db.execute(
                    """
                    INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity)
                    VALUES ($1, $2, $3, 1)
                    ON CONFLICT (guild_id, user_id, item_id)
                    DO UPDATE SET quantity = economy_inventory.quantity + 1;
                    """,
                    guild_id, user_id, item_won_id
                )

        return {"success": True, "cash": cash_won, "item": item_won}

    async def get_or_create_daily_quests(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        """Fetch or generate 3 daily quests for user."""
        now = discord.utils.utcnow()
        rows = await self.db.fetch_all(
            "SELECT * FROM user_quests WHERE guild_id = $1 AND user_id = $2 AND expires_at > $3;",
            guild_id, user_id, now
        )
        if rows:
            return [dict(r) for r in rows]

        # Generate 3 new quests
        end_of_day = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        templates = [
            ("work", "Complete Work Jobs", 3, 600),
            ("claim_daily", "Claim Daily Reward", 1, 400),
            ("gamble", "Play Casino Gambles", 3, 500),
            ("crime", "Execute Risky Crimes", 2, 650),
            ("hunt", "Hunt Wild Animals", 4, 750),
        ]
        chosen = random.sample(templates, 3)
        created = []
        for q_type, title, target, reward in chosen:
            row = await self.db.fetch_one(
                """
                INSERT INTO user_quests (guild_id, user_id, quest_type, target_count, current_count, reward_cash, completed, claimed, expires_at)
                VALUES ($1, $2, $3, $4, 0, $5, FALSE, FALSE, $6)
                RETURNING *;
                """,
                guild_id, user_id, q_type, target, reward, end_of_day
            )
            if row:
                created.append(dict(row))
        return created

    async def increment_quest(self, guild_id: int, user_id: int, quest_type: str, amount: int = 1) -> None:
        """Increment progress towards active quests."""
        try:
            now = discord.utils.utcnow()
            await self.db.execute(
                """
                UPDATE user_quests
                SET current_count = LEAST(target_count, current_count + $4),
                    completed = (current_count + $4 >= target_count)
                WHERE guild_id = $1 AND user_id = $2 AND quest_type = $3 AND completed = FALSE AND expires_at > $5;
                """,
                guild_id, user_id, quest_type, amount, now
            )
        except Exception as e:
            logger.debug(f"Notice incrementing quest: {e}")

    async def claim_quest_reward(self, guild_id: int, user_id: int, quest_id: int) -> dict[str, Any]:
        """Claim completed quest reward."""
        row = await self.db.fetch_one(
            "SELECT * FROM user_quests WHERE id = $1 AND guild_id = $2 AND user_id = $3;",
            quest_id, guild_id, user_id
        )
        if not row:
            return {"error": "Quest not found!"}
        if not row["completed"]:
            return {"error": "Quest is not completed yet!"}
        if row["claimed"]:
            return {"error": "Reward already claimed!"}

        reward = row["reward_cash"]
        await self.db.execute("UPDATE user_quests SET claimed = TRUE WHERE id = $1;", quest_id)
        await self.update_balance(guild_id, user_id, wallet_delta=reward, tx_type="quest_claim", metadata=f"Claimed quest {quest_id}")
        return {"success": True, "reward": reward}

    async def get_active_lottery(self, guild_id: int) -> dict[str, Any]:
        """Fetch or create current active lottery pool."""
        now = discord.utils.utcnow()
        row = await self.db.fetch_one(
            "SELECT * FROM economy_lottery WHERE guild_id = $1 AND status = 'active' AND ends_at > $2;",
            guild_id, now
        )
        if row:
            return dict(row)

        # Create new 24-hour lottery
        ends_at = now + dt.timedelta(hours=24)
        new_row = await self.db.fetch_one(
            """
            INSERT INTO economy_lottery (guild_id, ticket_price, pot, ends_at, status)
            VALUES ($1, 100, 5000, $2, 'active')
            RETURNING *;
            """,
            guild_id, ends_at
        )
        return dict(new_row) if new_row else {}

    async def buy_lottery_tickets(self, guild_id: int, user_id: int, ticket_count: int = 1) -> dict[str, Any]:
        """Buy lottery tickets for active pool."""
        if ticket_count <= 0 or ticket_count > 1000:
            return {"error": "Tickets must be between 1 and 1,000!"}

        lottery = await self.get_active_lottery(guild_id)
        price_per = lottery.get("ticket_price", 100)
        total_cost = price_per * ticket_count

        profile = await self.get_or_create_profile(guild_id, user_id)
        if profile.get("balance", 0) < total_cost:
            return {"error": f"You cannot afford {ticket_count} tickets! Cost: {total_cost:,}, Wallet: {profile.get('balance', 0):,}."}

        await self.update_balance(guild_id, user_id, wallet_delta=-total_cost, tx_type="lottery_buy", metadata=f"Bought {ticket_count} lottery tickets")

        lottery_id = lottery["lottery_id"]
        # Add to pot
        await self.db.execute("UPDATE economy_lottery SET pot = pot + $2 WHERE lottery_id = $1;", lottery_id, total_cost)

        # Upsert user ticket count
        await self.db.execute(
            """
            INSERT INTO economy_lottery_tickets (lottery_id, guild_id, user_id, tickets)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING;
            """,
            lottery_id, guild_id, user_id, ticket_count
        )

        pot = lottery.get("pot", 5000) + total_cost
        return {"success": True, "tickets": ticket_count, "cost": total_cost, "pot": pot}
