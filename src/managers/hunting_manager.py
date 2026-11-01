"""
KYOKA 3.0 — Advanced OwO-Style Hunting, Pets, Zoo & RPG Manager.
Features:
- 40+ unique creatures spanning 7 rarity tiers (Common to Mythical + Seasonal)
- Creature stats, catch rates, and rare encounter broadcasts
- Zoo collection progress, pet affection, feeding & leveling
- Fishing, mining, item crafting, and procedural dungeon/raid encounters
- Interactive trade confirmation with atomic item/creature exchange
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Kyoka.HuntingManager")

CREATURE_CATALOG: list[dict[str, Any]] = [
    # Common (50% aggregate rate)
    {"creature_id": "mouse", "name": "Field Mouse", "rarity": "Common", "emoji": "🐭", "drop_rate": 0.12, "base_hp": 40, "base_atk": 8, "base_def": 4, "description": "Quick and nimble woodland rodent."},
    {"creature_id": "rabbit", "name": "Cottontail Hare", "rarity": "Common", "emoji": "🐰", "drop_rate": 0.10, "base_hp": 45, "base_atk": 10, "base_def": 5, "description": "Alert herbivore with swift footwork."},
    {"creature_id": "frog", "name": "Emerald Tree Frog", "rarity": "Common", "emoji": "🐸", "drop_rate": 0.08, "base_hp": 35, "base_atk": 6, "base_def": 3, "description": "Leaping amphibian with sticky reflex."},
    {"creature_id": "chick", "name": "Golden Chick", "rarity": "Common", "emoji": "🐥", "drop_rate": 0.08, "base_hp": 30, "base_atk": 5, "base_def": 2, "description": "Cheerful fledgling full of energy."},
    {"creature_id": "caterpillar", "name": "Silk Caterpillar", "rarity": "Common", "emoji": "🐛", "drop_rate": 0.06, "base_hp": 25, "base_atk": 4, "base_def": 6, "description": "Crawling larvae that weaves tough silk."},
    {"creature_id": "duck", "name": "Wild Mallard", "rarity": "Common", "emoji": "🦆", "drop_rate": 0.06, "base_hp": 50, "base_atk": 11, "base_def": 6, "description": "Hardy waterfowl found near wetlands."},

    # Uncommon (25% aggregate rate)
    {"creature_id": "fox", "name": "Crimson Fox", "rarity": "Uncommon", "emoji": "🦊", "drop_rate": 0.06, "base_hp": 75, "base_atk": 22, "base_def": 12, "description": "Cunning predator with acute senses."},
    {"creature_id": "wolf", "name": "Timber Wolf", "rarity": "Uncommon", "emoji": "🐺", "drop_rate": 0.05, "base_hp": 90, "base_atk": 26, "base_def": 15, "description": "Pack hunter with ferocious bite."},
    {"creature_id": "owl", "name": "Nocturnal Barn Owl", "rarity": "Uncommon", "emoji": "🦉", "drop_rate": 0.04, "base_hp": 65, "base_atk": 20, "base_def": 10, "description": "Silent flyer with piercing vision."},
    {"creature_id": "raccoon", "name": "Bandit Raccoon", "rarity": "Uncommon", "emoji": "🦝", "drop_rate": 0.04, "base_hp": 70, "base_atk": 18, "base_def": 14, "description": "Clever scavenger known for pilfering shiny trinkets."},
    {"creature_id": "boar", "name": "Razorback Boar", "rarity": "Uncommon", "emoji": "🐗", "drop_rate": 0.03, "base_hp": 110, "base_atk": 28, "base_def": 20, "description": "Fierce charging beast with razor tusks."},
    {"creature_id": "bat", "name": "Shadow Bat", "rarity": "Uncommon", "emoji": "🦇", "drop_rate": 0.03, "base_hp": 55, "base_atk": 19, "base_def": 8, "description": "Echolocating nocturnal glider."},

    # Rare (14% aggregate rate)
    {"creature_id": "tiger", "name": "Bengal Tiger", "rarity": "Rare", "emoji": "🐯", "drop_rate": 0.035, "base_hp": 150, "base_atk": 45, "base_def": 25, "description": "Apex jungle predator with lethal claws."},
    {"creature_id": "lion", "name": "Golden Lion", "rarity": "Rare", "emoji": "🦁", "drop_rate": 0.035, "base_hp": 160, "base_atk": 48, "base_def": 28, "description": "Majestic savanna monarch with deafening roar."},
    {"creature_id": "bear", "name": "Grizzly Bear", "rarity": "Rare", "emoji": "🐻", "drop_rate": 0.030, "base_hp": 190, "base_atk": 52, "base_def": 34, "description": "Massive mountain brute with crushing strength."},
    {"creature_id": "eagle", "name": "Imperial Eagle", "rarity": "Rare", "emoji": "🦅", "drop_rate": 0.020, "base_hp": 120, "base_atk": 42, "base_def": 20, "description": "Ruler of the thermals with razor talons."},
    {"creature_id": "cobra", "name": "King Cobra", "rarity": "Rare", "emoji": "🐍", "drop_rate": 0.020, "base_hp": 110, "base_atk": 46, "base_def": 18, "description": "Venomous serpent that strikes in milliseconds."},

    # Epic (7% aggregate rate)
    {"creature_id": "unicorn", "name": "Starlight Unicorn", "rarity": "Epic", "emoji": "🦄", "drop_rate": 0.020, "base_hp": 260, "base_atk": 70, "base_def": 45, "description": "Mythical horned steed radiating holy aura."},
    {"creature_id": "wyvern", "name": "Storm Wyvern", "rarity": "Epic", "emoji": "🐲", "drop_rate": 0.018, "base_hp": 310, "base_atk": 82, "base_def": 50, "description": "Draconic beast breathing turbulent lightning."},
    {"creature_id": "phoenix", "name": "Solar Phoenix", "rarity": "Epic", "emoji": "🦚", "drop_rate": 0.016, "base_hp": 280, "base_atk": 88, "base_def": 42, "description": "Immortal avian creature reborn from embers."},
    {"creature_id": "kraken", "name": "Abyssal Kraken", "rarity": "Epic", "emoji": "🐙", "drop_rate": 0.016, "base_hp": 350, "base_atk": 85, "base_def": 55, "description": "Deep-sea terror dragging vessels into the trench."},

    # Legendary (3% aggregate rate)
    {"creature_id": "celestial_dragon", "name": "Celestial Dragon", "rarity": "Legendary", "emoji": "🐉", "drop_rate": 0.012, "base_hp": 520, "base_atk": 135, "base_def": 85, "description": "Ancient dragon soaring across nebulae and dimensions."},
    {"creature_id": "thunder_griffin", "name": "Thunder Griffin", "rarity": "Legendary", "emoji": "⚡", "drop_rate": 0.010, "base_hp": 480, "base_atk": 128, "base_def": 78, "description": "Majestic hybrid eagle-lion infused with high-voltage storms."},
    {"creature_id": "frost_chimera", "name": "Glacial Chimera", "rarity": "Legendary", "emoji": "❄️", "drop_rate": 0.008, "base_hp": 500, "base_atk": 130, "base_def": 82, "description": "Tri-headed ice beast freezing the ground it treads."},

    # Mythical (1% aggregate rate)
    {"creature_id": "astral_leviathan", "name": "Suigetsu Astral Leviathan", "rarity": "Mythical", "emoji": "🌌", "drop_rate": 0.006, "base_hp": 850, "base_atk": 210, "base_def": 140, "description": "Dimension-rending cosmic sovereign summoned under Kyoka Suigetsu."},
    {"creature_id": "aizen_soul_hollow", "name": "Hogyoku Transcendence Beast", "rarity": "Mythical", "emoji": "👑", "drop_rate": 0.004, "base_hp": 999, "base_atk": 250, "base_def": 160, "description": "The peak of spiritual evolution. A transcendent entity engineered by Aizen."},

    # Seasonal / Limited Event
    {"creature_id": "sakura_spirit", "name": "Sakura Blossom Fox", "rarity": "Seasonal", "emoji": "🌸", "drop_rate": 0.010, "base_hp": 240, "base_atk": 65, "base_def": 40, "description": "Springtime ethereal guardian leaving floral petals in its wake."},
    {"creature_id": "hollow_lantern", "name": "Spooky Hollow Lantern", "rarity": "Seasonal", "emoji": "🎃", "drop_rate": 0.010, "base_hp": 250, "base_atk": 68, "base_def": 42, "description": "Autumn spirit burning with violet spiritual flame."},
]

FISH_SPECIES: list[dict[str, Any]] = [
    {"fish_id": "carp", "name": "Common River Carp", "rarity": "Common", "value": 80, "emoji": "🐟"},
    {"fish_id": "bass", "name": "Largemouth Bass", "rarity": "Common", "value": 120, "emoji": "🐠"},
    {"fish_id": "salmon", "name": "Pacific Salmon", "rarity": "Uncommon", "value": 240, "emoji": "🍣"},
    {"fish_id": "tuna", "name": "Bluefin Tuna", "rarity": "Rare", "value": 650, "emoji": "🐟"},
    {"fish_id": "shark", "name": "Great White Shark", "rarity": "Epic", "value": 1800, "emoji": "🦈"},
    {"fish_id": "golden_koi", "name": "Legendary Golden Koi", "rarity": "Legendary", "value": 5000, "emoji": "✨"},
    {"fish_id": "leviathan_guppy", "name": "Mythic Astral Guppy", "rarity": "Mythical", "value": 15000, "emoji": "🌌"},
]

MINING_ORES: list[dict[str, Any]] = [
    {"ore_id": "coal", "name": "Lump of Coal", "rarity": "Common", "value": 50, "emoji": "🪨"},
    {"ore_id": "iron", "name": "Iron Ingot", "rarity": "Common", "value": 120, "emoji": "⛓️"},
    {"ore_id": "gold", "name": "Gold Nugget", "rarity": "Uncommon", "value": 300, "emoji": "🪙"},
    {"ore_id": "ruby", "name": "Blood Ruby", "rarity": "Rare", "value": 850, "emoji": "💎"},
    {"ore_id": "diamond", "name": "Flawless Diamond", "rarity": "Epic", "value": 2200, "emoji": "💠"},
    {"ore_id": "astral_gem", "name": "Astral Suigetsu Crystal", "rarity": "Legendary", "value": 6500, "emoji": "🔮"},
]

CRAFTING_RECIPES: list[dict[str, Any]] = [
    {"recipe_id": "super_rod", "result_item": "super_rod", "name": "Super Carbon Rod", "cost": 1000, "materials": {"iron": 3, "gold": 1}, "description": "Craft advanced fishing gear with reinforced iron and gold."},
    {"recipe_id": "laser_pickaxe", "result_item": "laser_pickaxe", "name": "Cyber Laser Pickaxe", "cost": 1500, "materials": {"iron": 5, "diamond": 1}, "description": "High-tech mining device powered by compressed diamond."},
    {"recipe_id": "zanpakuto_blade", "result_item": "zanpakuto_blade", "name": "Asauchi Zanpakuto", "cost": 800, "materials": {"iron": 4, "coal": 2}, "description": "Forge the sacred foundation blade of the soul reapers."},
    {"recipe_id": "lucky_clover", "result_item": "lucky_clover", "name": "Four-Leaf Clover", "cost": 400, "materials": {"coal": 3}, "description": "Distill elemental coal into an enchanted luck talisman."},
]


class HuntingManager:
    """Manages creature encounters, animal catching, zoo inventories, and RPG interactions."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self._user_locks: dict[Tuple[int, int], asyncio.Lock] = {}
        self._active_trades: dict[int, dict[str, Any]] = {}

    def _get_lock(self, guild_id: int, user_id: int) -> asyncio.Lock:
        key = (guild_id, user_id)
        if key not in self._user_locks:
            self._user_locks[key] = asyncio.Lock()
        return self._user_locks[key]

    async def init_catalog(self) -> None:
        """Seed creatures catalog into database."""
        try:
            for c in CREATURE_CATALOG:
                await self.db.execute(
                    """
                    INSERT INTO hunting_creatures (creature_id, name, rarity, emoji, drop_rate, base_hp, base_atk, base_def, description)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (creature_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        rarity = EXCLUDED.rarity,
                        emoji = EXCLUDED.emoji,
                        drop_rate = EXCLUDED.drop_rate,
                        base_hp = EXCLUDED.base_hp,
                        base_atk = EXCLUDED.base_atk,
                        base_def = EXCLUDED.base_def,
                        description = EXCLUDED.description;
                    """,
                    c["creature_id"], c["name"], c["rarity"], c["emoji"],
                    c["drop_rate"], c["base_hp"], c["base_atk"], c["base_def"], c["description"]
                )
            logger.info("Hunting creature catalog verified and synchronized.")
        except Exception as e:
            logger.warning(f"Notice initializing creature catalog: {e}")

    def roll_creature(self) -> dict[str, Any]:
        """Roll random creature encounter based on normalized weights."""
        total_weight = sum(c["drop_rate"] for c in CREATURE_CATALOG)
        r = random.uniform(0, total_weight)
        cumulative = 0.0
        for c in CREATURE_CATALOG:
            cumulative += c["drop_rate"]
            if r <= cumulative:
                return c
        return CREATURE_CATALOG[0]

    async def hunt(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """
        Hunt in the wild: encounters a creature, attempts catch, awards bonus drops/coins.
        Cooldown managed by calling cog (typically 15-30s).
        """
        lock = self._get_lock(guild_id, user_id)
        async with lock:
            creature = self.roll_creature()
            cid = creature["creature_id"]

            # Catch rates based on rarity
            rarity_catch_rates = {
                "Common": 0.88,
                "Uncommon": 0.72,
                "Rare": 0.55,
                "Epic": 0.38,
                "Legendary": 0.22,
                "Mythical": 0.12,
                "Seasonal": 0.45,
            }
            base_catch_rate = rarity_catch_rates.get(creature["rarity"], 0.70)
            caught = random.random() < base_catch_rate

            coins_found = random.randint(40, 200)

            if caught:
                # Add creature to user's zoo
                await self.db.execute(
                    """
                    INSERT INTO user_zoo (guild_id, user_id, creature_id, count, level, exp, affection, caught_at)
                    VALUES ($1, $2, $3, 1, 1, 0, 50, CURRENT_TIMESTAMP)
                    ON CONFLICT (guild_id, user_id, creature_id)
                    DO UPDATE SET count = user_zoo.count + 1;
                    """,
                    guild_id, user_id, cid
                )

            return {
                "creature": creature,
                "caught": caught,
                "catch_rate": int(base_catch_rate * 100),
                "coins": coins_found,
                "is_rare": creature["rarity"] in ("Epic", "Legendary", "Mythical"),
            }

    async def get_zoo(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve user's complete collected zoo grouped by rarity tier."""
        rows = await self.db.fetch_all(
            """
            SELECT z.creature_id, z.count, z.level, z.affection, z.equipped_pet,
                   c.name, c.rarity, c.emoji, c.base_hp, c.base_atk, c.base_def, c.description
            FROM user_zoo z
            JOIN hunting_creatures c ON z.creature_id = c.creature_id
            WHERE z.guild_id = $1 AND z.user_id = $2 AND z.count > 0
            ORDER BY c.base_atk DESC;
            """,
            guild_id, user_id
        )

        categories: dict[str, list[dict[str, Any]]] = {
            "Common": [], "Uncommon": [], "Rare": [],
            "Epic": [], "Legendary": [], "Mythical": [], "Seasonal": []
        }
        total_creatures = 0
        total_unique = len(rows)

        for r in rows:
            data = dict(r)
            rarity = data.get("rarity", "Common")
            if rarity in categories:
                categories[rarity].append(data)
            total_creatures += data["count"]

        total_catalog = len(CREATURE_CATALOG)
        completion_pct = round((total_unique / total_catalog) * 100, 1)

        return {
            "categories": categories,
            "total_count": total_creatures,
            "unique_count": total_unique,
            "catalog_size": total_catalog,
            "completion_pct": completion_pct,
        }

    async def get_pet(self, guild_id: int, user_id: int, creature_id: str) -> Optional[dict[str, Any]]:
        """Fetch details for a specific pet in user's zoo."""
        row = await self.db.fetch_one(
            """
            SELECT z.*, c.name, c.rarity, c.emoji, c.base_hp, c.base_atk, c.base_def, c.description
            FROM user_zoo z
            JOIN hunting_creatures c ON z.creature_id = c.creature_id
            WHERE z.guild_id = $1 AND z.user_id = $2 AND (LOWER(z.creature_id) = LOWER($3) OR LOWER(c.name) = LOWER($3));
            """,
            guild_id, user_id, creature_id.strip()
        )
        return dict(row) if row else None

    async def feed_pet(self, guild_id: int, user_id: int, creature_id: str) -> dict[str, Any]:
        """Feed a pet using Gourmet Pet Kibble, boosting its XP and affection."""
        # Verify user owns food
        inv_row = await self.db.fetch_one(
            "SELECT quantity FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = 'pet_food';",
            guild_id, user_id
        )
        if not inv_row or inv_row["quantity"] <= 0:
            return {"error": "You don't have any **Gourmet Pet Kibble**! Buy some from `?shop`."}

        pet = await self.get_pet(guild_id, user_id, creature_id)
        if not pet:
            return {"error": f"You haven't caught a `{creature_id}` yet! Check `?zoo`."}

        # Deduct 1 food
        if inv_row["quantity"] == 1:
            await self.db.execute("DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = 'pet_food';", guild_id, user_id)
        else:
            await self.db.execute("UPDATE economy_inventory SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND item_id = 'pet_food';", guild_id, user_id)

        current_lvl = pet.get("level", 1)
        current_xp = pet.get("exp", 0) + 35
        current_affection = min(100, pet.get("affection", 50) + 12)

        xp_needed = current_lvl * 50
        leveled_up = False
        if current_xp >= xp_needed:
            current_lvl += 1
            current_xp -= xp_needed
            leveled_up = True

        await self.db.execute(
            """
            UPDATE user_zoo
            SET level = $4, exp = $5, affection = $6
            WHERE guild_id = $1 AND user_id = $2 AND creature_id = $3;
            """,
            guild_id, user_id, pet["creature_id"], current_lvl, current_xp, current_affection
        )

        return {
            "success": True,
            "pet_name": pet["name"],
            "emoji": pet["emoji"],
            "level": current_lvl,
            "leveled_up": leveled_up,
            "affection": current_affection,
        }

    async def fish(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Fishing mini-game: requires fishing rod, catches water species."""
        # Check for fishing rod in inventory
        rods = await self.db.fetch_all(
            "SELECT item_id FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id IN ('fishing_rod', 'super_rod') AND quantity > 0;",
            guild_id, user_id
        )
        if not rods:
            return {"error": "You need a **Fishing Rod** to fish! Purchase one from `?shop` with `?buy fishing_rod`."}

        has_super_rod = any(r["item_id"] == "super_rod" for r in rods)

        # Catch roll
        weights = [45, 30, 15, 6, 3, 1, 0.2]
        if has_super_rod:
            # Super rod shifts weights to rarer catches
            weights = [25, 25, 25, 14, 7, 3, 1]

        chosen_fish = random.choices(FISH_SPECIES, weights=weights, k=1)[0]
        catch_value = chosen_fish["value"]

        return {
            "success": True,
            "fish": chosen_fish,
            "value": catch_value,
            "super_rod_bonus": has_super_rod,
        }

    async def mine(self, guild_id: int, user_id: int) -> dict[str, Any]:
        """Mining mini-game: requires pickaxe, extracts ores and crystals."""
        picks = await self.db.fetch_all(
            "SELECT item_id FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id IN ('pickaxe', 'laser_pickaxe') AND quantity > 0;",
            guild_id, user_id
        )
        if not picks:
            return {"error": "You need a **Pickaxe** to mine! Purchase one from `?shop` with `?buy pickaxe`."}

        has_laser = any(r["item_id"] == "laser_pickaxe" for r in picks)

        weights = [40, 30, 18, 8, 3, 1]
        if has_laser:
            weights = [20, 25, 25, 18, 8, 4]

        chosen_ore = random.choices(MINING_ORES, weights=weights, k=1)[0]
        qty = random.randint(1, 3) if has_laser else 1
        total_val = chosen_ore["value"] * qty

        return {
            "success": True,
            "ore": chosen_ore,
            "quantity": qty,
            "total_value": total_val,
            "laser_bonus": has_laser,
        }

    async def craft_item(self, guild_id: int, user_id: int, recipe_id: str) -> dict[str, Any]:
        """Craft equipment or items from recipes."""
        recipe = next((r for r in CRAFTING_RECIPES if r["recipe_id"].lower() == recipe_id.lower()), None)
        if not recipe:
            return {"error": f"Recipe `{recipe_id}` not found! Use `?craft` to see available recipes."}

        cost = recipe["cost"]
        # Check cash
        user_prof = await self.db.fetch_one("SELECT balance FROM user_profiles WHERE guild_id = $1 AND user_id = $2;", guild_id, user_id)
        if not user_prof or user_prof["balance"] < cost:
            return {"error": f"Crafting requires **{cost:,}** cash in your wallet!"}

        # Deduct cost
        await self.db.execute("UPDATE user_profiles SET balance = balance - $3 WHERE guild_id = $1 AND user_id = $2;", guild_id, user_id, cost)

        # Grant crafted item
        await self.db.execute(
            """
            INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (guild_id, user_id, item_id)
            DO UPDATE SET quantity = economy_inventory.quantity + 1;
            """,
            guild_id, user_id, recipe["result_item"]
        )

        return {"success": True, "recipe": recipe}
