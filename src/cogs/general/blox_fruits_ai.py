"""
KYOKA 3.0 Blox Fruits AI & Community Knowledge Engine.
Provides comprehensive Blox Fruits intelligence, fruit specifications, optimal grinding routes,
trade evaluation calculators, build advisors, and AI conversational assistance.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("Kyoka.BloxFruitsAI")
PURPLE = discord.Color.from_rgb(111, 67, 190)
from src.ui.asset_manager import AssetManager

# ─────────────────────────────────────────────────────────────────────────────
# BLOX FRUITS ENCYCLOPEDIA (OFFLINE 100% ACCURATE KNOWLEDGE BASE)
# ─────────────────────────────────────────────────────────────────────────────

FRUITS_DATABASE = {
    "kitsune": {
        "name": "Kitsune",
        "type": "Beast",
        "rarity": "Mythical",
        "beli": "8,000,000",
        "robux": "4,000",
        "pvp_tier": "SSS",
        "grind_tier": "S",
        "description": "Transforms into a nine-tailed mythical fox with unmatched agility, passive fox-fire aura, and insane combo potential.",
        "moves": ["Yamata no Orochi", "Fox Fire Blast", "Wild Assault", "Tail Beast Flare", "Transformation"],
        "awakenable": False,
        "trade_value": 115_000_000,
    },
    "dragon": {
        "name": "Dragon",
        "type": "Beast",
        "rarity": "Mythical",
        "beli": "3,500,000 (Rework Meta)",
        "robux": "2,600",
        "pvp_tier": "SSS",
        "grind_tier": "A+",
        "description": "Massive draconic transformation with catastrophic AoE devastation, extreme flight mobility, and super-armor.",
        "moves": ["Heatwave Beam", "Dragon Flight", "Fire Shower", "Draconic Claws", "Dragon Form"],
        "awakenable": False,
        "trade_value": 120_000_000,
    },
    "leopard": {
        "name": "Leopard",
        "type": "Beast",
        "rarity": "Mythical",
        "beli": "5,000,000",
        "robux": "3,000",
        "pvp_tier": "SS",
        "grind_tier": "A",
        "description": "High-velocity beast transformation with relentless M1 claw attacks, heavy stuns, and high burst damage.",
        "moves": ["Finger Revolver", "Spiral Kick", "Afterimage Assault", "Body Flicker", "Transformation"],
        "awakenable": False,
        "trade_value": 40_000_000,
    },
    "dough": {
        "name": "Dough",
        "type": "Natural (Special Paramecia)",
        "rarity": "Mythical",
        "beli": "2,800,000",
        "robux": "2,400",
        "pvp_tier": "SSS (V2 Awakened)",
        "grind_tier": "A",
        "description": "The ultimate stun-combo fruit in Blox Fruits. Awakened V2 locks opponents in endless Piercing Clothesline and Roller Donut chains.",
        "moves": ["Roller Donut (V2)", "Missile Fist (V2)", "Pastry River (V2)", "Piercing Clothesline (V2)", "Dough Fist Fusillade (V2)"],
        "awakenable": True,
        "trade_value": 25_000_000,
    },
    "buddha": {
        "name": "Buddha",
        "type": "Beast",
        "rarity": "Legendary",
        "beli": "1,200,000",
        "robux": "1,650",
        "pvp_tier": "A (Spam Meta)",
        "grind_tier": "SSS (Undisputed #1 Grinding Fruit)",
        "description": "The absolute king of grinding and raids. Awakened Shift expands character size, provides massive 50% damage reduction, and huge melee/sword reach.",
        "moves": ["Shift (Awakened)", "Heavenly Impact", "Light of Annihilation", "Twilight of the Gods"],
        "awakenable": True,
        "trade_value": 7_000_000,
    },
    "portal": {
        "name": "Portal",
        "type": "Natural",
        "rarity": "Legendary",
        "beli": "1,900,000",
        "robux": "2,000",
        "pvp_tier": "SSS (Trickster / Hunter Meta)",
        "grind_tier": "B",
        "description": "Instant teleportation anywhere in the current Sea. Dimensional Rift creates inescapable pocket dimensions for PvP setup.",
        "moves": ["Portal Dash", "Parallel Escape", "World Warp", "Dimensional Rift", "Quantum Leap"],
        "awakenable": False,
        "trade_value": 6_000_000,
    },
    "magma": {
        "name": "Magma",
        "type": "Elemental",
        "rarity": "Rare",
        "beli": "850,000",
        "robux": "1,300",
        "pvp_tier": "S (Awakened)",
        "grind_tier": "SS (Sea Beast / Ship Raid Destroyer)",
        "description": "Possesses the highest raw base DPS in the entire game. Awakened magma pools melt Sea Beasts, Terrorsharks, and Bosses in seconds.",
        "moves": ["Magma Shower (V2)", "Volcanic Assault (V2)", "Great Magma Hound (V2)", "Magma Fist", "Magma Floor"],
        "awakenable": True,
        "trade_value": 2_000_000,
    },
    "t-rex": {
        "name": "T-Rex",
        "type": "Beast",
        "rarity": "Mythical",
        "beli": "2,700,000",
        "robux": "2,350",
        "pvp_tier": "SS",
        "grind_tier": "S",
        "description": "Prehistoric beast transformation featuring continuous predatory M1 bite chains, terror roar debuff, and bleeding damage.",
        "moves": ["Prehistoric Slash", "Furious Roar", "Tail Swipe", "Carnivore Crush", "Transformation"],
        "awakenable": False,
        "trade_value": 20_000_000,
    },
    "mammoth": {
        "name": "Mammoth",
        "type": "Beast",
        "rarity": "Mythical",
        "beli": "2,700,000",
        "robux": "2,350",
        "pvp_tier": "S+",
        "grind_tier": "S",
        "description": "Ancient elephant transformation with continuous Stampede charge that tramples Sea Beasts and raid bosses.",
        "moves": ["Ancient Cutter", "True Prehistoric Jump", "Colossal Crusher", "Stampede", "Transformation"],
        "awakenable": False,
        "trade_value": 12_000_000,
    },
    "venom": {
        "name": "Venom",
        "type": "Natural",
        "rarity": "Mythical",
        "beli": "3,000,000",
        "robux": "2,450",
        "pvp_tier": "S+",
        "grind_tier": "S",
        "description": "Three-headed dragon venom transformation with deadly toxic gas pools that deplete enemy health ticks rapidly.",
        "moves": ["Poison Daggers", "Carnation Extinction", "Toxic Fog", "Serpent Glide", "Transformation"],
        "awakenable": False,
        "trade_value": 9_000_000,
    },
    "spirit": {
        "name": "Spirit",
        "type": "Natural",
        "rarity": "Mythical",
        "beli": "3,400,000",
        "robux": "2,550",
        "pvp_tier": "S+",
        "grind_tier": "A+",
        "description": "Harnesses both burning Sun and frozen Moon spirits for extreme versatility, burst fireballs, and freeze stuns.",
        "moves": ["Sun/Moon Spirits", "Celestial Fire", "Wrath of the Heavens", "End of the World"],
        "awakenable": False,
        "trade_value": 10_000_000,
    },
    "blizzard": {
        "name": "Blizzard",
        "type": "Elemental",
        "rarity": "Legendary",
        "beli": "2,400,000",
        "robux": "2,250",
        "pvp_tier": "S",
        "grind_tier": "S",
        "description": "Massive swirling snowstorms that constantly tick damage onto surrounding targets while keeping user safe.",
        "moves": ["Snow Squall", "Permafrost Domain", "Blizzard Vortex", "Flight"],
        "awakenable": False,
        "trade_value": 5_000_000,
    },
    "rumble": {
        "name": "Rumble",
        "type": "Elemental",
        "rarity": "Legendary",
        "beli": "2,100,000",
        "robux": "2,100",
        "pvp_tier": "SS (Sword Main Meta)",
        "grind_tier": "A",
        "description": "Awakened thunder storms and multi-dashes providing extreme lightning stun combos for sword and gun users.",
        "moves": ["Lightning Beast (V2)", "Thunderstorm (V2)", "Sky Judgment (V2)", "Thunder Flash (V2)"],
        "awakenable": True,
        "trade_value": 5_000_000,
    },
    "light": {
        "name": "Light",
        "type": "Elemental",
        "rarity": "Rare",
        "beli": "650,000",
        "robux": "1,100",
        "pvp_tier": "A",
        "grind_tier": "S (Best Sea 1 Fruit)",
        "description": "Ultra-fast light-speed flight, light sword M1 melee attacks, and high AoE blasts. The #1 starter fruit in First Sea.",
        "moves": ["Light Blade", "Light Beam", "Skylight Kick", "Wrath of God", "Light Flight"],
        "awakenable": True,
        "trade_value": 1_000_000,
    },
    "ice": {
        "name": "Ice",
        "type": "Elemental",
        "rarity": "Uncommon",
        "beli": "350,000",
        "robux": "750",
        "pvp_tier": "S (Awakened Freeze Combos)",
        "grind_tier": "A+",
        "description": "Walk on water with ice skating passive. Awakened Ice Dragon and Glacial Surge provide instant one-shot stun combos.",
        "moves": ["Glacial Surge (V2)", "Ice Dragon (V2)", "Absolute Zero (V2)", "Ice Skating"],
        "awakenable": True,
        "trade_value": 500_000,
    },
}

GRINDING_GUIDE = [
    (1, 10, "First Sea", "Starter Island", "Bandit (Lv. 5)", "Light or any Elemental fruit"),
    (10, 30, "First Sea", "Jungle", "Monkey (Lv. 14) / Gorilla (Lv. 20)", "Unlock Saber boss at Lv. 200"),
    (30, 60, "First Sea", "Pirate Village", "Pirate (Lv. 35) / Brute (Lv. 45)", "Buy Dark Step fighting style"),
    (60, 90, "First Sea", "Desert", "Desert Bandit (Lv. 60) / Officer (Lv. 75)", "Elemental immunity active"),
    (90, 120, "First Sea", "Frozen Village", "Snow Bandit (Lv. 90) / Snowman (Lv. 100)", "Buy Skyjump & Enhancement Haki"),
    (120, 150, "First Sea", "Marine Fortress", "Chief Petty Officer (Lv. 120) / Vice Admiral", "Vice Admiral boss farming"),
    (150, 190, "First Sea", "Skylands (Sky 1)", "Sky Bandit (Lv. 150) / Dark Master (Lv. 175)", "Unlock Observation Haki at Upper Sky"),
    (190, 250, "First Sea", "Prison", "Prisoner (Lv. 190) / Dangerous Prisoner (Lv. 210)", "Boss hop: Warden, Chief Warden, Swan"),
    (250, 300, "First Sea", "Colosseum", "Toga Warrior (Lv. 250) / Gladiator (Lv. 275)", "Group NPCs with AoE moves"),
    (300, 375, "First Sea", "Magma Village", "Military Soldier (Lv. 300) / Spy (Lv. 325)", "Avoid magma lava pits"),
    (375, 450, "First Sea", "Underwater City", "Fishman Warrior (Lv. 375) / Commando (Lv. 400)", "Fishman Lord boss drop Trident"),
    (450, 525, "First Sea", "Upper Skylands", "God's Guard (Lv. 450) / Shanda (Lv. 475)", "Unlock Observation Haki (Ken)"),
    (525, 625, "First Sea", "Fountain City", "Galley Pirate (Lv. 525) / Captain (Lv. 550)", "High exp rate with Buddha or Light"),
    (625, 700, "First Sea", "Fountain City & Colosseum", "Cyborg Boss / Military", "Complete Prison Quest to unlock Second Sea"),
    (700, 775, "Second Sea", "Kingdom of Rose", "Raider (Lv. 700) / Mercenary (Lv. 725)", "Equip Buddha fruit & reset stats into Melee/Def"),
    (775, 875, "Second Sea", "Green Zone", "Marine Lieutenant (Lv. 775) / Captain (Lv. 800)", "Defeat Fajita boss for Gravity Cane"),
    (875, 1000, "Second Sea", "Snow Mountain & Graveyard", "Snow Trooper (Lv. 875) / Zombie (Lv. 950)", "Complete Bartilo Quest for Swan Glasses"),
    (1000, 1100, "Second Sea", "Hot and Cold", "Lab Subordinate (Lv. 1000) / Horned Warrior", "Raid Core: start awakening Buddha/Magma"),
    (1100, 1250, "Second Sea", "Cursed Ship", "Ship Deckhand (Lv. 1250) / Ship Engineer", "Farm Ectoplasm for Ghoul Mask & Ghoul Race"),
    (1250, 1350, "Second Sea", "Ice Castle", "Arctic Warrior (Lv. 1250) / Snow Lurker", "Awakened Ice Admiral for Rengoku sword"),
    (1350, 1425, "Second Sea", "Forgotten Island", "Sea Soldier (Lv. 1350) / Water Fighter", "Tide Keeper boss drop Dragon Trident"),
    (1425, 1500, "Second Sea", "Forgotten Island", "Water Fighter (Lv. 1425)", "Complete Colosseum & King Red Head for Third Sea"),
    (1500, 1575, "Third Sea", "Port Town", "Pirate Millionaire (Lv. 1500) / Pistol Billionaire", "Third Sea unlocked! Stone boss"),
    (1575, 1700, "Third Sea", "Hydra Island", "Dragon Crew Warrior (Lv. 1575) / Archer", "Explore Secret Waterfall for Yama Sword"),
    (1700, 1825, "Third Sea", "Great Tree", "Marine Commodore (Lv. 1700) / Rear Admiral", "Island Empress / Kilo Admiral boss"),
    (1825, 1975, "Third Sea", "Floating Turtle", "Fishman Raider (Lv. 1825) / Captain", "Farm Bones, unlock Tushita & CDK"),
    (1975, 2075, "Third Sea", "Haunted Castle", "Reborn Skeleton (Lv. 1975) / Demonic Soul", "Soul Guitar quest & Hallow Essence"),
    (2075, 2200, "Third Sea", "Sea of Treats (Peanut Land)", "Peanut Scout (Lv. 2075) / Ice Cream Chef", "Godhuman fighting style requirements"),
    (2200, 2450, "Third Sea", "Cake Land & Chocolate Island", "Cookie Crafter (Lv. 2200) / Cocoa Warrior", "Farm 10 Cocoa for Mirror Fractal & Dough King"),
    (2450, 2600, "Third Sea", "Tiki Outpost / Submerged Island", "Isle Outlaw (Lv. 2450) / Sun-kissed Warrior", "Leviathan hunt, Shark Anchor, Max Level 2600!"),
]

META_BUILDS = {
    "pvp": {
        "title": "⚔️ Top Tier Bounty Hunter / PvP Meta",
        "fruit": "Dough V2 (Awakened) OR Portal OR Kitsune",
        "sword": "Cursed Dual Katana (CDK) OR Shark Anchor",
        "gun": "Soul Guitar (El Diablo 3s Stun)",
        "fighting_style": "Godhuman OR Sanguine Art",
        "race": "Cyborg V4 (Defense & Energy Orbit) OR Human V4 (Psycho Boost)",
        "stats": "2550 Melee, 2550 Defense, 2550 Sword (Sword Main) OR Blox Fruit (Fruit Main)",
        "combos": "Portal Z -> Godhuman C -> CDK Z -> Soul Guitar Z -> Godhuman X Z",
    },
    "grinding": {
        "title": "📈 Ultimate Leveling & Raid Carry Build",
        "fruit": "Buddha (Awakened Z Shift)",
        "sword": "Cursed Dual Katana OR True Triple Katana OR Shark Anchor",
        "gun": "Soul Guitar OR Kabucha",
        "fighting_style": "Sharkman Karate OR Godhuman OR Electric Claw",
        "race": "Ghoul V3/V4 (Life Leech per hit) OR Shark V3/V4 (Immunity)",
        "stats": "2550 Melee, 2550 Defense, 2550 Sword",
        "combos": "Shift -> Spam M1 clicks -> Use Ghoul Life Leech -> Clear entire mob in seconds",
    },
    "seabeast": {
        "title": "🌊 Sea Beast & Leviathan Hunting Build",
        "fruit": "Magma V2 (Full Awakening - Highest DPS)",
        "sword": "Dragon Trident OR Shark Anchor",
        "gun": "Soul Guitar",
        "fighting_style": "Sharkman Karate (Fast water attacks)",
        "race": "Shark V3/V4 (Immunity to water damage)",
        "stats": "2550 Melee, 2550 Defense, 2550 Blox Fruit",
        "combos": "Magma Shower -> Great Magma Hound -> Volcanic Assault -> Repeat from boat",
    },
}


class BloxFruitsAI(commands.Cog):
    """
    KYOKA 3.0 Blox Fruits AI Assistant.
    Specialized intelligence in Fruits, Builds, Grinding, Trading, and Raids.
    """
    category = "Blox Fruits AI"

    def __init__(self, bot):
        self.bot = bot
        self._user_cooldowns: dict[int, float] = {}

    def _check_cooldown(self, user_id: int) -> float:
        now = time.monotonic()
        last = self._user_cooldowns.get(user_id, 0.0)
        rem = 3.0 - (now - last)
        if rem > 0:
            return rem
        self._user_cooldowns[user_id] = now
        return 0.0

    # ─── 1. +bloxai <question> ───────────────────────────────────────────────

    @commands.command(
        name="bloxai",
        aliases=["bfai", "askblox"],
        description="Ask the specialized Blox Fruits AI any question about the game.",
    )
    async def bloxai(self, ctx: commands.Context, *, question: str):
        """Ask the specialized Blox Fruits AI assistant any question."""
        rem = self._check_cooldown(ctx.author.id)
        if rem > 0:
            return await ctx.reply(f"⏳ Please wait `{rem:.1f}s` before asking another question.", mention_author=False)

        async with ctx.typing():
            # Check if Gemini AI manager is active with valid key
            ai_mgr = getattr(self.bot, "ai_mgr", None)
            answer_text = None

            if ai_mgr and os.getenv("GEMINI_API_KEY") and not os.getenv("GEMINI_API_KEY", "").startswith("replace_"):
                try:
                    session = getattr(self.bot, "session", None)
                    if session:
                        prompt_enriched = (
                            f"You are the KYOKA Blox Fruits AI Master. "
                            f"Answer this player's question with precise, meta-accurate game mechanics, optimal builds, stats, "
                            f"and concise formatting: {question[:1000]}"
                        )
                        answer_text = await ai_mgr.generate_persona_reply(
                            session=session,
                            guild_id=ctx.guild.id if ctx.guild else 0,
                            user_id=ctx.author.id,
                            persona_key="gaming_expert",
                            prompt=prompt_enriched,
                            enforce_cooldown=False
                        )
                except Exception as e:
                    logger.debug(f"Gemini Blox Fruits fallback triggered: {e}")

            # Offline Fallback matching
            if not answer_text:
                q_low = question.lower()
                # Check for fruit matches
                matched_fruit = None
                for fk, fd in FRUITS_DATABASE.items():
                    if fk in q_low or fd["name"].lower() in q_low:
                        matched_fruit = fd
                        break

                if matched_fruit:
                    answer_text = (
                        f"**{matched_fruit['name']} Fruit Overview:**\n"
                        f"• **Type:** {matched_fruit['type']} | **Rarity:** {matched_fruit['rarity']}\n"
                        f"• **Price:** {matched_fruit['beli']} Beli / {matched_fruit['robux']} Robux\n"
                        f"• **PvP Tier:** `{matched_fruit['pvp_tier']}` | **Grinding Tier:** `{matched_fruit['grind_tier']}`\n"
                        f"• **Description:** {matched_fruit['description']}\n"
                        f"• **Awakenable:** {'Yes (Raid)' if matched_fruit['awakenable'] else 'No'}\n"
                        f"• **Key Moves:** {', '.join(matched_fruit['moves'][:4])}"
                    )
                elif any(w in q_low for w in ["grind", "level", "island", "xp", "farm"]):
                    answer_text = (
                        "**Optimal Blox Fruits Grinding Strategy:**\n"
                        "• **First Sea (1-700):** Use Light Fruit or any Elemental fruit for Logia immunity. Put all stats in Melee + Defense.\n"
                        "• **Second Sea (700-1500):** Immediately switch to **Buddha Fruit (Awakened Z)**. Reset stats into Melee (max) + Defense (max). Use Sharkman Karate.\n"
                        "• **Third Sea (1500-2600):** Stick with Buddha or switch to Kitsune/Mammoth. Complete Cursed Dual Katana & Godhuman quests at Tiki Outpost."
                    )
                elif any(w in q_low for w in ["pvp", "bounty", "combo"]):
                    answer_text = (
                        "**Current Blox Fruits PvP Meta (Update 20+):**\n"
                        "• **Top Fruits:** Dough V2, Portal, Kitsune, Leopard, Rumble V2.\n"
                        "• **Top Swords:** Cursed Dual Katana (CDK), Shark Anchor, Spikey Trident.\n"
                        "• **Top Guns:** Soul Guitar (El Diablo 3s Stun).\n"
                        "• **Fighting Styles:** Godhuman or Sanguine Art.\n"
                        "• **Races:** Cyborg V4 (best against teamers) or Human V4 (massive damage amp)."
                    )
                elif any(w in q_low for w in ["raid", "awaken", "chip"]):
                    answer_text = (
                        "**Blox Fruits Raids & Awakening Guide:**\n"
                        "• **Location:** Castle on the Sea (Third Sea) or Hot and Cold (Second Sea).\n"
                        "• **Cost:** 100,000 Beli or any physical fruit to purchase a Microchip (2-hour cooldown without fruit sacrifice).\n"
                        "• **Best Solo Raid Fruit:** Awakened Buddha (Melee spam) or Awakened Magma.\n"
                        "• **Advanced Raids:** Dough and Phoenix require unlocking through special quests."
                    )
                else:
                    answer_text = (
                        f"**KYOKA Blox Fruits Knowledge Answer:**\n"
                        f"> Regarding *\"{question[:100]}\"*\n\n"
                        f"• For leveling up fast, use `+grindhelp <level>`.\n"
                        f"• For detailed stats on any fruit, use `+fruitinfo <fruit>`.\n"
                        f"• For optimal stats & gear setups, use `+buildhelp <pvp|grinding|seabeast>`.\n"
                        f"• To evaluate a trade offer, use `+tradehelp <offer> for <target>`."
                    )

            embed = discord.Embed(
                title="⛩️ KYŌKA • BLOX FRUITS AI ASSISTANT",
                description=answer_text[:2000],
                color=PURPLE,
                timestamp=discord.utils.utcnow()
            )
            banner_file = AssetManager.attach_feature_banner(embed, "blox_fruits_ai")
            embed.set_footer(text=f"Requested by {ctx.author.display_name} • KYOKA Blox Fruits Engine")
            if banner_file:
                await ctx.reply(embed=embed, file=banner_file, mention_author=False)
            else:
                await ctx.reply(embed=embed, mention_author=False)

    # ─── 2. +fruitinfo <fruit> ────────────────────────────────────────────────

    @commands.command(
        name="fruitinfo",
        aliases=["finfo", "fruit"],
        description="View comprehensive statistics, moveset, and trade tier for any Blox Fruit.",
    )
    async def fruitinfo(self, ctx: commands.Context, *, fruit: str):
        """Display detailed specifications and meta ratings for a Blox Fruit."""
        clean_name = fruit.lower().strip().replace("fruit", "").replace(" ", "").replace("-", "")
        matched = None
        for key, data in FRUITS_DATABASE.items():
            if clean_name in key or key in clean_name:
                matched = data
                break

        if not matched:
            available = ", ".join(f"`{d['name']}`" for d in list(FRUITS_DATABASE.values())[:10])
            return await ctx.reply(
                f"❌ Fruit `{fruit}` not found. Try one of these: {available}...",
                mention_author=False
            )

        embed = discord.Embed(
            title=f"🍎 Blox Fruits • {matched['name']} Fruit",
            description=f"> {matched['description']}",
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🏷️ Classification", value=f"• **Type:** `{matched['type']}`\n• **Rarity:** `{matched['rarity']}`", inline=True)
        embed.add_field(name="💰 Store Cost", value=f"• **Beli:** `{matched['beli']}`\n• **Robux:** `{matched['robux']}`", inline=True)
        embed.add_field(name="⭐ Meta Ratings", value=f"• **PvP Tier:** `{matched['pvp_tier']}`\n• **Grinding:** `{matched['grind_tier']}`", inline=True)
        embed.add_field(name="⚡ Moveset", value="\n".join(f"• {m}" for m in matched["moves"]), inline=False)
        embed.add_field(name="📈 Trade Value Estimate", value=f"`~{matched['trade_value']:,} Trade Value Points`", inline=True)
        embed.add_field(name="✨ Awakening Available", value="`Yes (Raid)`" if matched["awakenable"] else "`No`", inline=True)

        embed.set_footer(text="KYŌKA Blox Fruits Database • Current Game Meta")
        await ctx.reply(embed=embed, mention_author=False)

    # ─── 3. +grindhelp <level> ───────────────────────────────────────────────

    @commands.command(
        name="grindhelp",
        aliases=["levelhelp", "grindguide"],
        description="Find the optimal island, quest NPC, and strategy for your exact level (1 to 2600).",
    )
    async def grindhelp(self, ctx: commands.Context, level: int):
        """Find the exact island, quest NPC, and advice for your current level."""
        if level < 1:
            return await ctx.reply("Level must be at least 1.", mention_author=False)

        matched_step = None
        for min_lvl, max_lvl, sea, island, enemies, tip in GRINDING_GUIDE:
            if min_lvl <= level <= max_lvl:
                matched_step = (min_lvl, max_lvl, sea, island, enemies, tip)
                break

        if not matched_step:
            if level >= 2450:
                matched_step = (2450, 2600, "Third Sea", "Tiki Outpost & Submerged Island", "Isle Outlaws / Sun-kissed Warriors", "Leviathan hunt, Shark Anchor, Max Level 2600!")
            else:
                matched_step = GRINDING_GUIDE[-1]

        min_l, max_l, sea, island, enemies, tip = matched_step

        embed = discord.Embed(
            title=f"📈 Blox Fruits Leveling Guide • Level {level}",
            description=f"Optimal progression route for **Level {level}** (Range: `{min_l} - {max_l}`):",
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🌊 Current Sea", value=f"`{sea}`", inline=True)
        embed.add_field(name="🏝️ Recommended Island", value=f"**{island}**", inline=True)
        embed.add_field(name="⚔️ Target Quest & NPCs", value=f"`{enemies}`", inline=False)
        embed.add_field(name="💡 Pro Leveling Advice", value=f"> {tip}", inline=False)

        # General Leveling Tips
        if sea == "First Sea":
            general_tip = "Eat **Light Fruit** for fast elemental flight and Logia immunity. Put 60% stats into Melee and 40% into Defense."
        elif sea == "Second Sea":
            general_tip = "Immediately switch to **Awakened Buddha Fruit**. Reset stats to max out **Melee** and **Defense** (Zero in Blox Fruit)."
        else:
            general_tip = "Use Buddha or Kitsune. Farm Bones at Haunted Castle for 2x EXP boosts, and unlock Cursed Dual Katana."

        embed.add_field(name="✨ Key Strategy for This Sea", value=f"> {general_tip}", inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Max Level: 2600")
        await ctx.reply(embed=embed, mention_author=False)

    # ─── 4. +tradehelp <offer> for <target> ───────────────────────────────────

    @commands.command(
        name="tradehelp",
        aliases=["tradecalc", "tradeeval"],
        description="Calculate trade fairness and profit between fruit offers (e.g. Kitsune for Dragon).",
    )
    async def tradehelp(self, ctx: commands.Context, offer: str, target: str):
        """Evaluate a Blox Fruits trade offer (Win, Fair, or Lose)."""
        def get_value(text: str) -> tuple[int, list[str]]:
            total_val = 0
            found_fruits = []
            low_text = text.lower()
            for key, data in FRUITS_DATABASE.items():
                if key in low_text or data["name"].lower() in low_text:
                    total_val += data["trade_value"]
                    found_fruits.append(data["name"])
            return total_val, found_fruits

        val_offer, fruits_offer = get_value(offer)
        val_target, fruits_target = get_value(target)

        if not fruits_offer or not fruits_target:
            return await ctx.reply(
                "❌ Could not recognize fruits in your trade query.\n"
                "Example usage: `+tradehelp Kitsune for Dragon` or `+tradehelp Leopard for Dough Buddha`",
                mention_author=False
            )

        diff = val_target - val_offer
        # Percentage difference relative to offer
        pct = (diff / max(1, val_offer)) * 100

        if pct >= 25:
            verdict = "🟢 **MASSIVE WIN (Huge Profit)**"
            advice = "Accept immediately! You are receiving far higher community trade value."
            color = discord.Color.green()
        elif pct >= 5:
            verdict = "🟢 **SMALL WIN (Favorable Trade)**"
            advice = "Good trade for you. You gain slight market value."
            color = discord.Color.green()
        elif -5 <= pct <= 5:
            verdict = "🟡 **FAIR TRADE (Equal Market Value)**"
            advice = "Even trade. Decide based on which fruit moveset fits your playstyle."
            color = discord.Color.gold()
        elif pct >= -20:
            verdict = "🟠 **SMALL LOSE (Slight Overpay)**"
            advice = "You are giving slightly more value than you receive. Try asking for an add."
            color = discord.Color.orange()
        else:
            verdict = "🔴 **MASSIVE L (Severe Overpay / Scam)**"
            advice = "Do NOT accept! You are overpaying significantly in community trade value."
            color = discord.Color.red()

        embed = discord.Embed(
            title="🤝 Blox Fruits Trade Evaluator",
            description=f"**Verdict:** {verdict}\n> {advice}",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="📤 Your Offer",
            value=f"• Fruits: **{', '.join(fruits_offer)}**\n• Trade Value: `{val_offer:,}` pts",
            inline=True
        )
        embed.add_field(
            name="📥 You Receive",
            value=f"• Fruits: **{', '.join(fruits_target)}**\n• Trade Value: `{val_target:,}` pts",
            inline=True
        )
        embed.add_field(
            name="📊 Value Differential",
            value=f"**{diff:+d} pts ({pct:+.1f}%)**",
            inline=False
        )
        embed.set_footer(text="Values based on current Blox Fruits community trading demand")
        await ctx.reply(embed=embed, mention_author=False)

    # ─── 5. +buildhelp <goal> ────────────────────────────────────────────────

    @commands.command(
        name="buildhelp",
        aliases=["bfbuild", "bestbuild"],
        description="Get optimal fruit, sword, gun, fighting style, race, and stats for your goal.",
    )
    async def buildhelp(self, ctx: commands.Context, goal: str = "pvp"):
        """Display recommended meta builds for PvP, Grinding, or Sea Events."""
        g_clean = goal.lower().strip()
        matched_key = "pvp"
        if any(w in g_clean for w in ["grind", "level", "raid", "pve"]):
            matched_key = "grinding"
        elif any(w in g_clean for w in ["sea", "beast", "leviathan", "shark"]):
            matched_key = "seabeast"

        build = META_BUILDS[matched_key]

        embed = discord.Embed(
            title=f"⛩️ {build['title']}",
            description=f"Comprehensive gear and stat loadout tailored for `{matched_key.upper()}`:",
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🍎 Recommended Fruit", value=f"• {build['fruit']}", inline=False)
        embed.add_field(name="⚔️ Primary Sword", value=f"• {build['sword']}", inline=True)
        embed.add_field(name="🔫 Stun / Support Gun", value=f"• {build['gun']}", inline=True)
        embed.add_field(name="🥊 Fighting Style", value=f"• {build['fighting_style']}", inline=False)
        embed.add_field(name="🧬 Ideal Race V4", value=f"• {build['race']}", inline=True)
        embed.add_field(name="📊 Stat Allocation", value=f"• {build['stats']}", inline=True)
        embed.add_field(name="⚡ Primary Combo / Rotation", value=f"> `{build['combos']}`", inline=False)

        embed.set_footer(text="KYŌKA Blox Fruits Meta Advisor • Update 20+")
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(BloxFruitsAI(bot))
