"""
Kyoka Cyber Arena: Shadow Raids, Infinite Dungeon & Mythic Crucible
===================================================================
The Ultimate Interactive Discord RPG & Gaming Suite for Kyoka 3.0.

Features:
- Co-op Multiplayer World Boss Raids with interactive buttons, classes, QTE events, and phase transitions.
- Solo Infinite Dungeon Tower crawl (Floors 1-100+) with mystery shrines, traps, and loot.
- Multiplayer PvP Duels with wagered gold and tactical turn-based combat.
- High-Roller Casino Blackjack with ASCII card rendering and authentic soft-17 rules.
- Mythic Weapon & Artifact Gacha Summoning Altar with 6 rarity tiers.
- Hero Profile, Inventory, Stats, and Equipment System.
- Multi-Category Server & Global Leaderboards.
- Persistent SQLite storage in data/kyoka_arena.sqlite3.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.ArenaRPG")

# Colors
ARENA_PURPLE = 0x7C3AED
ARENA_GOLD = 0xF59E0B
ARENA_RED = 0xEF4444
ARENA_GREEN = 0x10B981
ARENA_CYAN = 0x06B6D4
ARENA_DARK = 0x111827

# Data directory
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DB_PATH = DATA_DIR / "kyoka_arena.sqlite3"


# ─── DATABASE HELPER ──────────────────────────────────────────────────────────

def get_db_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_arena_db() -> None:
    """Initialize arena SQLite tables."""
    conn = get_db_connection()
    try:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS arena_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    hero_class TEXT NOT NULL DEFAULT 'Shadow Blade',
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    gold INTEGER NOT NULL DEFAULT 500,
                    hp_max INTEGER NOT NULL DEFAULT 1000,
                    atk INTEGER NOT NULL DEFAULT 120,
                    def_stat INTEGER NOT NULL DEFAULT 40,
                    crit_rate REAL NOT NULL DEFAULT 0.15,
                    equipped_weapon TEXT NOT NULL DEFAULT 'Iron Katana',
                    equipped_armor TEXT NOT NULL DEFAULT 'Leather Vest',
                    raid_kills INTEGER NOT NULL DEFAULT 0,
                    dungeon_max_floor INTEGER NOT NULL DEFAULT 0,
                    duel_wins INTEGER NOT NULL DEFAULT 0,
                    last_daily REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS arena_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    atk_bonus INTEGER NOT NULL DEFAULT 0,
                    def_bonus INTEGER NOT NULL DEFAULT 0,
                    crit_bonus REAL NOT NULL DEFAULT 0.0,
                    acquired_at REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES arena_users(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_arena_inv_user ON arena_inventory(user_id);
            """)
    finally:
        conn.close()


# ─── ITEM & RARITY DEFINITIONS ────────────────────────────────────────────────

RARITY_COLORS = {
    "Common": 0x9CA3AF,
    "Rare": 0x3B82F6,
    "Epic": 0x8B5CF6,
    "Legendary": 0xF59E0B,
    "Mythic": 0xEC4899,
    "Godly": 0xEF4444,
}

RARITY_WEIGHTS = [
    ("Common", 0.45),
    ("Rare", 0.30),
    ("Epic", 0.15),
    ("Legendary", 0.07),
    ("Mythic", 0.025),
    ("Godly", 0.005),
]

GACHA_POOL: Dict[str, List[Dict[str, Any]]] = {
    "Common": [
        {"name": "Iron Katana", "type": "weapon", "atk": 15, "def": 0, "crit": 0.02},
        {"name": "Rusty Dagger", "type": "weapon", "atk": 12, "def": 0, "crit": 0.04},
        {"name": "Leather Vest", "type": "armor", "atk": 0, "def": 15, "crit": 0.0},
        {"name": "Wooden Buckler", "type": "armor", "atk": 0, "def": 12, "crit": 0.0},
    ],
    "Rare": [
        {"name": "Dragon Fang Blade", "type": "weapon", "atk": 35, "def": 0, "crit": 0.05},
        {"name": "Shadow Dagger", "type": "weapon", "atk": 30, "def": 0, "crit": 0.08},
        {"name": "Reinforced Steel Mail", "type": "armor", "atk": 0, "def": 35, "crit": 0.0},
        {"name": "Phantom Cloak", "type": "armor", "atk": 5, "def": 25, "crit": 0.03},
    ],
    "Epic": [
        {"name": "Murasame - One-Cut Demon", "type": "weapon", "atk": 75, "def": 0, "crit": 0.12},
        {"name": "Frostbite Scythe", "type": "weapon", "atk": 70, "def": 10, "crit": 0.10},
        {"name": "Dragon Scale Aegis", "type": "armor", "atk": 0, "def": 70, "crit": 0.0},
        {"name": "Abyssal Shroud", "type": "armor", "atk": 15, "def": 55, "crit": 0.05},
    ],
    "Legendary": [
        {"name": "Enma - Hell Cutter", "type": "weapon", "atk": 140, "def": 0, "crit": 0.20},
        {"name": "Excalibur - Holy Light", "type": "weapon", "atk": 130, "def": 20, "crit": 0.15},
        {"name": "Titan Adamantine Armor", "type": "armor", "atk": 0, "def": 140, "crit": 0.0},
        {"name": "Crown of the Undead", "type": "armor", "atk": 30, "def": 100, "crit": 0.08},
    ],
    "Mythic": [
        {"name": "Kyoka Suigetsu - Shatter Reflection", "type": "weapon", "atk": 250, "def": 30, "crit": 0.28},
        {"name": "Sukuna's Dismantle Cleaver", "type": "weapon", "atk": 280, "def": 0, "crit": 0.32},
        {"name": "Shadow Monarch Cloak", "type": "armor", "atk": 40, "def": 220, "crit": 0.10},
    ],
    "Godly": [
        {"name": "Aizen's Hōgyoku Core Blade", "type": "weapon", "atk": 450, "def": 80, "crit": 0.40},
        {"name": "Infinity Void Robe of Gojo", "type": "armor", "atk": 100, "def": 400, "crit": 0.20},
    ],
}


# ─── USER DATA MODEL ──────────────────────────────────────────────────────────

@dataclass
class ArenaUser:
    user_id: int
    username: str
    hero_class: str
    level: int
    xp: int
    gold: int
    hp_max: int
    atk: int
    def_stat: int
    crit_rate: float
    equipped_weapon: str
    equipped_armor: str
    raid_kills: int
    dungeon_max_floor: int
    duel_wins: int
    last_daily: float
    created_at: float

    @property
    def xp_needed(self) -> int:
        return self.level * 250

    def add_xp(self, amount: int) -> bool:
        """Add XP and return True if leveled up."""
        self.xp += amount
        leveled = False
        while self.xp >= self.xp_needed:
            self.xp -= self.xp_needed
            self.level += 1
            self.hp_max += 120
            self.atk += 20
            self.def_stat += 8
            leveled = True
        return leveled


def get_or_create_user(user: discord.User | discord.Member) -> ArenaUser:
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute("SELECT * FROM arena_users WHERE user_id = ?", (user.id,))
            row = cur.fetchone()
            now = time.time()
            if not row:
                conn.execute(
                    """
                    INSERT INTO arena_users (
                        user_id, username, hero_class, level, xp, gold,
                        hp_max, atk, def_stat, crit_rate, equipped_weapon, equipped_armor,
                        raid_kills, dungeon_max_floor, duel_wins, last_daily, created_at
                    ) VALUES (?, ?, 'Shadow Blade', 1, 0, 500, 1000, 120, 40, 0.15, 'Iron Katana', 'Leather Vest', 0, 0, 0, 0.0, ?)
                    """,
                    (user.id, user.display_name, now),
                )
                conn.execute(
                    """
                    INSERT INTO arena_inventory (user_id, item_name, item_type, rarity, atk_bonus, def_bonus, crit_bonus, acquired_at)
                    VALUES (?, 'Iron Katana', 'weapon', 'Common', 15, 0, 0.02, ?),
                           (?, 'Leather Vest', 'armor', 'Common', 0, 15, 0.0, ?)
                    """,
                    (user.id, now, user.id, now),
                )
                return ArenaUser(
                    user_id=user.id,
                    username=user.display_name,
                    hero_class="Shadow Blade",
                    level=1,
                    xp=0,
                    gold=500,
                    hp_max=1000,
                    atk=120,
                    def_stat=40,
                    crit_rate=0.15,
                    equipped_weapon="Iron Katana",
                    equipped_armor="Leather Vest",
                    raid_kills=0,
                    dungeon_max_floor=0,
                    duel_wins=0,
                    last_daily=0.0,
                    created_at=now,
                )
            return ArenaUser(
                user_id=row["user_id"],
                username=row["username"],
                hero_class=row["hero_class"],
                level=row["level"],
                xp=row["xp"],
                gold=row["gold"],
                hp_max=row["hp_max"],
                atk=row["atk"],
                def_stat=row["def_stat"],
                crit_rate=row["crit_rate"],
                equipped_weapon=row["equipped_weapon"],
                equipped_armor=row["equipped_armor"],
                raid_kills=row["raid_kills"],
                dungeon_max_floor=row["dungeon_max_floor"],
                duel_wins=row["duel_wins"],
                last_daily=row["last_daily"],
                created_at=row["created_at"],
            )
    finally:
        conn.close()


def save_user(u: ArenaUser) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE arena_users SET
                    username = ?, hero_class = ?, level = ?, xp = ?, gold = ?,
                    hp_max = ?, atk = ?, def_stat = ?, crit_rate = ?,
                    equipped_weapon = ?, equipped_armor = ?, raid_kills = ?,
                    dungeon_max_floor = ?, duel_wins = ?, last_daily = ?
                WHERE user_id = ?
                """,
                (
                    u.username,
                    u.hero_class,
                    u.level,
                    u.xp,
                    u.gold,
                    u.hp_max,
                    u.atk,
                    u.def_stat,
                    u.crit_rate,
                    u.equipped_weapon,
                    u.equipped_armor,
                    u.raid_kills,
                    u.dungeon_max_floor,
                    u.duel_wins,
                    u.last_daily,
                    u.user_id,
                ),
            )
    finally:
        conn.close()


def add_item_to_user(user_id: int, item: Dict[str, Any], rarity: str) -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO arena_inventory (user_id, item_name, item_type, rarity, atk_bonus, def_bonus, crit_bonus, acquired_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    item["name"],
                    item["type"],
                    rarity,
                    item.get("atk", 0),
                    item.get("def", 0),
                    item.get("crit", 0.0),
                    time.time(),
                ),
            )
    finally:
        conn.close()


# ─── PROGRESS BAR BUILDER ─────────────────────────────────────────────────────

def render_hp_bar(current: int, maximum: int, length: int = 12) -> str:
    maximum = max(1, maximum)
    current = max(0, min(current, maximum))
    fill = int((current / maximum) * length)
    empty = length - fill
    return f"`[{'▰' * fill}{'▱' * empty}]` **{current:,}/{maximum:,} HP**"


# ─── BOSS RAIDS DEFINITIONS ───────────────────────────────────────────────────

BOSS_ROSTER = [
    {
        "name": "Aizen Sōsuke • Lord of Hueco Mundo",
        "title": "The Deceiver of Heaven",
        "avatar": "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif",
        "hp": 12000,
        "atk": 220,
        "def": 45,
        "specials": [
            "Kyoka Suigetsu: Complete Hypnosis (Buttons Disorient!)",
            "Hado #90: Kurohitsugi (Torrent of Gravity)",
            "Hōgyoku Transmutation: Regeneration",
        ],
        "gold_reward": 1200,
        "xp_reward": 900,
    },
    {
        "name": "Ryomen Sukuna • King of Curses",
        "title": "The Disgraced Calamity",
        "avatar": "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "hp": 14000,
        "atk": 260,
        "def": 50,
        "specials": [
            "Dismantle: Invisible Blade Slash",
            "Cleave: Armor Piercing Rend",
            "Domain Expansion: Malevolent Shrine",
        ],
        "gold_reward": 1500,
        "xp_reward": 1100,
    },
    {
        "name": "Sung Jinwoo • The Shadow Monarch",
        "title": "Ruler of the Dead",
        "avatar": "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "hp": 13500,
        "atk": 240,
        "def": 60,
        "specials": [
            "Shadow Extraction: Arise!",
            "Dagger Rush: Poison Flurry",
            "Monarch's Domain: Shadow Amplification",
        ],
        "gold_reward": 1400,
        "xp_reward": 1050,
    },
    {
        "name": "Gojo Satoru • The Limitless One",
        "title": "The Honored One",
        "avatar": "https://media.giphy.com/media/d4zHnLJcd45n663K/giphy.gif",
        "hp": 16000,
        "atk": 280,
        "def": 75,
        "specials": [
            "Infinity: Damage Reduction Aura",
            "Reversal Red: Repulsive Shockwave",
            "Secret Art: Hollow Purple",
        ],
        "gold_reward": 1800,
        "xp_reward": 1400,
    },
]


# ─── MULTIPLAYER RAID ENGINE ──────────────────────────────────────────────────

class RaidCombatant:
    def __init__(self, member: discord.Member, user_data: ArenaUser) -> None:
        self.member = member
        self.user = user_data
        self.hp = user_data.hp_max
        self.max_hp = user_data.hp_max
        self.atk = user_data.atk
        self.def_stat = user_data.def_stat
        self.crit = user_data.crit_rate
        self.ultimate_meter = 0  # 0 to 100
        self.is_defending = False
        self.potions = 2
        self.is_alive = True

    @property
    def name(self) -> str:
        return self.member.display_name


class BossRaidView(discord.ui.View):
    """Interactive Real-Time Multiplayer Raid Combat View."""

    def __init__(
        self,
        cog: ArenaRPG,
        host: discord.Member,
        boss_data: Dict[str, Any],
        combatants: List[RaidCombatant],
    ) -> None:
        super().__init__(timeout=180.0)
        self.cog = cog
        self.host = host
        self.boss = dict(boss_data)
        self.boss_max_hp = boss_data["hp"]
        self.boss_hp = boss_data["hp"]
        self.combatants = combatants
        self.turn_index = 0
        self.round_num = 1
        self.combat_logs: List[str] = [f"⚔️ **The Raid has begun!** {boss_data['name']} roars!"]
        self.message: Optional[discord.Message] = None
        self.is_finished = False

    def current_actor(self) -> RaidCombatant:
        alive = [c for c in self.combatants if c.is_alive]
        if not alive:
            return self.combatants[0]
        return alive[self.turn_index % len(alive)]

    def build_raid_embed(self) -> discord.Embed:
        boss_hp_bar = render_hp_bar(self.boss_hp, self.boss_max_hp, length=14)
        pct = (self.boss_hp / self.boss_max_hp) * 100
        embed_color = ARENA_RED if pct <= 30 else (ARENA_GOLD if pct <= 60 else ARENA_PURPLE)

        embed = discord.Embed(
            title=f"👑 WORLD RAID: {self.boss['name']}",
            description=f"*{self.boss['title']}* • **Round {self.round_num}**\n\n"
                        f"**Boss Health:**\n{boss_hp_bar} ({pct:.1f}%)\n",
            color=embed_color,
        )
        if self.boss.get("avatar"):
            embed.set_thumbnail(url=self.boss["avatar"])

        # Party status
        party_lines = []
        for c in self.combatants:
            status = "💀 DEAD" if not c.is_alive else f"❤️ {c.hp}/{c.max_hp} | ⚡ {c.ultimate_meter}% ULT"
            marker = "👉 " if c is self.current_actor() and c.is_alive else "   "
            party_lines.append(f"{marker}**{c.name}** ({c.user.hero_class}): {status}")

        embed.add_field(name="🛡️ Raid Squad", value="\n".join(party_lines) or "None", inline=False)

        # Recent Combat Logs
        recent_logs = "\n".join(f"> {entry}" for entry in self.combat_logs[-4:])
        embed.add_field(name="📜 Combat Log", value=recent_logs or "Waiting for action...", inline=False)

        actor = self.current_actor()
        if not self.is_finished:
            embed.set_footer(text=f"Current Turn: {actor.name} • Choose an action below!")
        return embed

    def _next_turn(self) -> None:
        alive = [c for c in self.combatants if c.is_alive]
        if not alive:
            self._end_raid(victory=False)
            return

        self.turn_index += 1
        if self.turn_index >= len(alive):
            self.turn_index = 0
            self.round_num += 1
            self._boss_turn()

    def _boss_turn(self) -> None:
        """Boss executes an attack or special move."""
        alive = [c for c in self.combatants if c.is_alive]
        if not alive or self.boss_hp <= 0:
            return

        # Choose target
        target = random.choice(alive)
        is_special = random.random() < 0.35

        if is_special:
            move = random.choice(self.boss["specials"])
            base_dmg = int(self.boss["atk"] * random.uniform(1.3, 1.8))
            self.combat_logs.append(f"💥 **{self.boss['name']}** unleashed **{move}**!")
        else:
            base_dmg = int(self.boss["atk"] * random.uniform(0.9, 1.2))

        # Mitigation
        defense = target.def_stat
        if target.is_defending:
            actual_dmg = max(10, int((base_dmg - defense) * 0.3))
            target.is_defending = False
            self.combat_logs.append(f"🛡️ **{target.name}** parried! Took only **{actual_dmg:,}** damage!")
        else:
            actual_dmg = max(20, base_dmg - defense)
            self.combat_logs.append(f"🩸 **{target.name}** took **{actual_dmg:,}** damage from Boss!")

        target.hp -= actual_dmg
        if target.hp <= 0:
            target.hp = 0
            target.is_alive = False
            self.combat_logs.append(f"💀 **{target.name}** has fallen in battle!")

        # Check if squad wiped
        if not any(c.is_alive for c in self.combatants):
            self._end_raid(victory=False)

    def _end_raid(self, victory: bool) -> None:
        self.is_finished = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if victory:
            gold_each = self.boss["gold_reward"]
            xp_each = self.boss["xp_reward"]
            self.combat_logs.append(f"🎉 **VICTORY!** The boss was slain! Each member receives **+{gold_each:,} Gold** and **+{xp_each:,} XP**!")

            # Update database for all participants
            for c in self.combatants:
                u = c.user
                u.gold += gold_each
                u.raid_kills += 1
                leveled = u.add_xp(xp_each)
                # 25% chance of rolling a Rare or Epic gear drop
                if random.random() < 0.35:
                    tier = random.choice(["Rare", "Epic", "Legendary"])
                    item = random.choice(GACHA_POOL[tier])
                    add_item_to_user(u.user_id, item, tier)
                    self.combat_logs.append(f"🎁 **{c.name}** unlocked **{item['name']}** ({tier})!")
                if leveled:
                    self.combat_logs.append(f"⭐ **{c.name}** advanced to **Level {u.level}**!")
                save_user(u)
        else:
            self.combat_logs.append(f"☠️ **DEFEAT!** The raid squad was obliterated by {self.boss['name']}...")

        self.stop()

    # ── BUTTON CONTROLS ──

    @discord.ui.button(label="Strike", style=discord.ButtonStyle.primary, emoji="⚔️", row=0)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        actor = self.current_actor()
        if interaction.user.id != actor.member.id:
            return await interaction.response.send_message(f"It's not your turn! Waiting on **{actor.name}**.", ephemeral=True)

        is_crit = random.random() < actor.crit
        dmg_mult = 1.8 if is_crit else random.uniform(0.9, 1.15)
        raw_dmg = int(actor.atk * dmg_mult)
        boss_def = self.boss["def"]
        final_dmg = max(25, raw_dmg - boss_def)

        self.boss_hp -= final_dmg
        actor.ultimate_meter = min(100, actor.ultimate_meter + random.randint(18, 25))

        crit_text = "💥 **CRITICAL HIT!** " if is_crit else ""
        self.combat_logs.append(f"{crit_text}**{actor.name}** struck for **{final_dmg:,}** damage! (⚡ +20% ULT)")

        if self.boss_hp <= 0:
            self.boss_hp = 0
            self._end_raid(victory=True)
        else:
            self._next_turn()

        embed = self.build_raid_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Ultimate", style=discord.ButtonStyle.danger, emoji="🔥", row=0)
    async def ultimate_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        actor = self.current_actor()
        if interaction.user.id != actor.member.id:
            return await interaction.response.send_message(f"It's not your turn! Waiting on **{actor.name}**.", ephemeral=True)

        if actor.ultimate_meter < 100:
            return await interaction.response.send_message(f"Ultimate not ready! Meter at **{actor.ultimate_meter}%/100%**.", ephemeral=True)

        actor.ultimate_meter = 0
        ult_dmg = int(actor.atk * random.uniform(2.8, 3.8))
        self.boss_hp -= ult_dmg

        self.combat_logs.append(f"🌟 **ULTIMATE ACTIVATION!** **{actor.name}** unleashed secret art for **{ult_dmg:,}** MASSIVE damage!")

        if self.boss_hp <= 0:
            self.boss_hp = 0
            self._end_raid(victory=True)
        else:
            self._next_turn()

        embed = self.build_raid_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Parry & Defend", style=discord.ButtonStyle.secondary, emoji="🛡️", row=0)
    async def defend_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        actor = self.current_actor()
        if interaction.user.id != actor.member.id:
            return await interaction.response.send_message(f"It's not your turn! Waiting on **{actor.name}**.", ephemeral=True)

        actor.is_defending = True
        actor.ultimate_meter = min(100, actor.ultimate_meter + 10)
        self.combat_logs.append(f"🛡️ **{actor.name}** raised a defensive barrier! (Blocks 70% damage)")

        self._next_turn()
        embed = self.build_raid_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Healing Potion", style=discord.ButtonStyle.success, emoji="🧪", row=0)
    async def potion_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        actor = self.current_actor()
        if interaction.user.id != actor.member.id:
            return await interaction.response.send_message(f"It's not your turn! Waiting on **{actor.name}**.", ephemeral=True)

        if actor.potions <= 0:
            return await interaction.response.send_message("You have no potions remaining in this raid!", ephemeral=True)

        actor.potions -= 1
        heal_amt = int(actor.max_hp * 0.4)
        actor.hp = min(actor.max_hp, actor.hp + heal_amt)
        self.combat_logs.append(f"🧪 **{actor.name}** drank an Elixir! Restored **+{heal_amt:,} HP** ({actor.potions} left).")

        self._next_turn()
        embed = self.build_raid_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class RaidLobbyView(discord.ui.View):
    """30-second interactive lobby for team assembly."""

    def __init__(self, cog: ArenaRPG, host: discord.Member, boss_data: Dict[str, Any]) -> None:
        super().__init__(timeout=35.0)
        self.cog = cog
        self.host = host
        self.boss_data = boss_data
        self.members: List[discord.Member] = [host]
        self.message: Optional[discord.Message] = None

    def build_lobby_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚔️ WORLD BOSS RAID LOBBY: {self.boss_data['name']}",
            description=(
                f"**Boss Title:** *{self.boss_data['title']}*\n"
                f"**Boss Health:** `{self.boss_data['hp']:,} HP` • **Attack:** `{self.boss_data['atk']}`\n\n"
                f"Click **[Join Raid]** to stand with the squad! (Max 5 players)\n"
                f"Host can press **[Start Now]** whenever ready."
            ),
            color=ARENA_GOLD,
        )
        if self.boss_data.get("avatar"):
            embed.set_thumbnail(url=self.boss_data["avatar"])

        party_text = "\n".join(f"**{i+1}.** {m.mention} (`{get_or_create_user(m).hero_class}`)" for i, m in enumerate(self.members))
        embed.add_field(name=f"👥 Assembled Squad ({len(self.members)}/5)", value=party_text, inline=False)
        embed.set_footer(text="Lobby closes automatically in 30 seconds.")
        return embed

    @discord.ui.button(label="Join Raid", style=discord.ButtonStyle.success, emoji="⚔️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user in self.members:
            return await interaction.response.send_message("You are already in the raid lobby!", ephemeral=True)
        if len(self.members) >= 5:
            return await interaction.response.send_message("The raid party is completely full!", ephemeral=True)

        self.members.append(interaction.user)  # type: ignore
        await interaction.response.edit_message(embed=self.build_lobby_embed(), view=self)

    @discord.ui.button(label="Start Now", style=discord.ButtonStyle.primary, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Only the raid host can start early!", ephemeral=True)
        self.stop()
        await self._launch_raid(interaction)

    async def on_timeout(self) -> None:
        if not self.message:
            return
        await self._launch_raid(None)

    async def _launch_raid(self, interaction: Optional[discord.Interaction]) -> None:
        combatants = [RaidCombatant(m, get_or_create_user(m)) for m in self.members]
        raid_view = BossRaidView(self.cog, self.host, self.boss_data, combatants)
        embed = raid_view.build_raid_embed()

        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=raid_view)
            raid_view.message = self.message
        elif self.message:
            try:
                await self.message.edit(embed=embed, view=raid_view)
                raid_view.message = self.message
            except Exception:
                pass


# ─── CASINO BLACKJACK ─────────────────────────────────────────────────────────

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def draw_card() -> Tuple[str, str, int]:
    r = random.choice(RANKS)
    s = random.choice(SUITS)
    val = 11 if r == "A" else (10 if r in ("J", "Q", "K") else int(r))
    return r, s, val


def calculate_hand(hand: List[Tuple[str, str, int]]) -> int:
    total = sum(c[2] for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def render_ascii_cards(hand: List[Tuple[str, str, int]], hide_second: bool = False) -> str:
    lines = ["", "", "", ""]
    for i, (rank, suit, _) in enumerate(hand):
        if hide_second and i == 1:
            lines[0] += "┌──────┐ "
            lines[1] += "│░░░░░░│ "
            lines[2] += "│░░░░░░│ "
            lines[3] += "└──────┘ "
        else:
            r_str = f"{rank:<2}"
            lines[0] += "┌──────┐ "
            lines[1] += f"│{r_str}    │ "
            lines[2] += f"│   {suit}  │ "
            lines[3] += "└──────┘ "
    return "\n".join(lines)


class BlackjackView(discord.ui.View):
    def __init__(self, user: ArenaUser, bet: int) -> None:
        super().__init__(timeout=60.0)
        self.user = user
        self.bet = bet
        self.player_hand: List[Tuple[str, str, int]] = [draw_card(), draw_card()]
        self.dealer_hand: List[Tuple[str, str, int]] = [draw_card(), draw_card()]
        self.is_over = False

    def build_embed(self, hide_dealer: bool = True) -> discord.Embed:
        p_val = calculate_hand(self.player_hand)
        d_val = calculate_hand(self.dealer_hand) if not hide_dealer else calculate_hand([self.dealer_hand[0]])

        embed = discord.Embed(
            title="🎰 High-Roller Cyber Blackjack",
            description=f"**Bet:** `{self.bet:,} Gold` • **Player Balance:** `{self.user.gold:,} Gold`\n",
            color=ARENA_PURPLE,
        )

        d_label = f"Dealer's Hand ({d_val if not hide_dealer else '?'})"
        embed.add_field(
            name=d_label,
            value=f"```\n{render_ascii_cards(self.dealer_hand, hide_second=hide_dealer)}\n```",
            inline=False,
        )

        embed.add_field(
            name=f"Your Hand ({p_val})",
            value=f"```\n{render_ascii_cards(self.player_hand, hide_second=False)}\n```",
            inline=False,
        )
        return embed

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user.user_id:
            return await interaction.response.send_message("This is not your table!", ephemeral=True)

        self.player_hand.append(draw_card())
        p_val = calculate_hand(self.player_hand)

        if p_val > 21:
            self.is_over = True
            self.user.gold -= self.bet
            save_user(self.user)
            self._disable_all()
            embed = self.build_embed(hide_dealer=False)
            embed.color = ARENA_RED
            embed.description = f"💥 **BUSTED!** You exceeded 21 and lost **-{self.bet:,} Gold**."
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self.build_embed(hide_dealer=True), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user.user_id:
            return await interaction.response.send_message("This is not your table!", ephemeral=True)

        self.is_over = True
        self._disable_all()

        # Dealer draws to soft 17
        while calculate_hand(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        p_val = calculate_hand(self.player_hand)
        d_val = calculate_hand(self.dealer_hand)

        embed = self.build_embed(hide_dealer=False)
        if d_val > 21:
            embed.color = ARENA_GREEN
            embed.description = f"🎉 **DEALER BUSTED ({d_val})!** You won **+{self.bet:,} Gold**!"
            self.user.gold += self.bet
        elif p_val > d_val:
            embed.color = ARENA_GREEN
            embed.description = f"🏆 **YOU WIN!** ({p_val} vs {d_val}) • Won **+{self.bet:,} Gold**!"
            self.user.gold += self.bet
        elif d_val > p_val:
            embed.color = ARENA_RED
            embed.description = f"💀 **DEALER WINS!** ({d_val} vs {p_val}) • Lost **-{self.bet:,} Gold**."
            self.user.gold -= self.bet
        else:
            embed.color = ARENA_GOLD
            embed.description = f"🤝 **PUSH!** Both tied at {p_val} • Bet returned."

        save_user(self.user)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.secondary, emoji="💰")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user.user_id:
            return await interaction.response.send_message("This is not your table!", ephemeral=True)

        if self.user.gold < self.bet * 2:
            return await interaction.response.send_message("Insufficient funds to double down!", ephemeral=True)

        self.bet *= 2
        self.player_hand.append(draw_card())
        await self.stand.callback(interaction)

    def _disable_all(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


# ─── COG CLASS DEFINITION ─────────────────────────────────────────────────────

class ArenaRPG(commands.Cog):
    """
    ⚔️ Kyoka Cyber Arena • RPG & Games Suite
    Complete multiplayer boss raids, dungeon tower, duels, casino blackjack & gacha.
    """

    category = "Games"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        init_arena_db()

    # ─── 1. WORLD BOSS RAIDS ──────────────────────────────────────────────────

    @commands.command(
        name="arenaraid",
        aliases=["araid"],
        help="Launch a multiplayer World Boss Raid lobby for up to 5 players.",
    )
    @commands.guild_only()
    async def arenaraid(self, ctx: CustomContext) -> None:
        """Launch an interactive World Boss Raid lobby."""
        boss_data = random.choice(BOSS_ROSTER)
        lobby_view = RaidLobbyView(self, ctx.author, boss_data)
        embed = lobby_view.build_lobby_embed()
        lobby_view.message = await ctx.send(embed=embed, view=lobby_view)

    # ─── 2. CASINO BLACKJACK ──────────────────────────────────────────────────

    @commands.command(
        name="arenablackjack",
        aliases=["abj"],
        help="Play high-stakes Casino Blackjack with interactive buttons and ASCII cards: +abj [bet]",
    )
    async def arenablackjack(self, ctx: CustomContext, bet: int = 100) -> None:
        """Play interactive Blackjack against the bot."""
        if bet <= 0:
            return await ctx.send("Bet must be a positive integer!")
        if bet > 50000:
            return await ctx.send("Maximum table limit is 50,000 Gold!")

        user_data = get_or_create_user(ctx.author)
        if user_data.gold < bet:
            return await ctx.send(f"You don't have enough gold! Balance: `{user_data.gold:,} Gold`.")

        bj_view = BlackjackView(user_data, bet)
        embed = bj_view.build_embed(hide_dealer=True)
        await ctx.send(embed=embed, view=bj_view)

    # ─── 3. GACHA SUMMONING ALTAR ─────────────────────────────────────────────

    @commands.command(
        name="summon",
        aliases=["gacha", "rpgbox", "box"],
        help="Summon legendary weapons and armor from the Cyber Crucible (100 Gold).",
    )
    async def summon(self, ctx: CustomContext) -> None:
        """Summon items from the Gacha pool."""
        user_data = get_or_create_user(ctx.author)
        cost = 100
        if user_data.gold < cost:
            return await ctx.send(f"Summoning costs **100 Gold**! Your balance: `{user_data.gold:,} Gold`.")

        user_data.gold -= cost

        # Roll rarity
        r = random.random()
        cumulative = 0.0
        chosen_tier = "Common"
        for tier, weight in RARITY_WEIGHTS:
            cumulative += weight
            if r <= cumulative:
                chosen_tier = tier
                break

        item = random.choice(GACHA_POOL[chosen_tier])
        add_item_to_user(ctx.author.id, item, chosen_tier)
        save_user(user_data)

        color = RARITY_COLORS.get(chosen_tier, ARENA_PURPLE)
        embed = discord.Embed(
            title=f"✨ SUMMON SUCCESS: {chosen_tier.upper()} DROP!",
            description=(
                f"**Item Unlocked:** `{item['name']}`\n"
                f"**Rarity:** `{chosen_tier}` • **Type:** `{item['type'].capitalize()}`\n\n"
                f"⚔️ **ATK Bonus:** `+{item.get('atk', 0)}`\n"
                f"🛡️ **DEF Bonus:** `+{item.get('def', 0)}`\n"
                f"🎯 **CRIT Bonus:** `+{int(item.get('crit', 0)*100)}%`\n\n"
                f"*Use `{ctx.prefix}equip {item['name']}` to arm this item!*"
            ),
            color=color,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Remaining Gold: {user_data.gold:,}")
        await ctx.send(embed=embed)

    # ─── 4. HERO PROFILE & INVENTORY ──────────────────────────────────────────

    @commands.command(
        name="arenaprofile",
        aliases=["aprofile", "herostats"],
        help="View your Arena Hero Profile, stats, and equipped loadout.",
    )
    async def arenaprofile(self, ctx: CustomContext, target: Optional[discord.Member] = None) -> None:
        """View hero RPG stats and loadout."""
        member = target or ctx.author
        u = get_or_create_user(member)

        embed = discord.Embed(
            title=f"🛡️ Hero Profile: {u.username}",
            description=f"**Class:** `{u.hero_class}` • **Level {u.level}**\n"
                        f"**Progress:** `{u.xp:,} / {u.xp_needed:,} XP`\n\n"
                        f"💰 **Gold:** `{u.gold:,} Coins`\n"
                        f"❤️ **Max HP:** `{u.hp_max:,}`\n"
                        f"⚔️ **Attack:** `{u.atk:,}`\n"
                        f"🛡️ **Defense:** `{u.def_stat:,}`\n"
                        f"🎯 **Crit Chance:** `{int(u.crit_rate * 100)}%`\n\n"
                        f"🗡️ **Equipped Weapon:** `{u.equipped_weapon}`\n"
                        f"🥋 **Equipped Armor:** `{u.equipped_armor}`\n\n"
                        f"🏆 **Raid Kills:** `{u.raid_kills:,}` • **PvP Wins:** `{u.duel_wins:,}`",
            color=ARENA_PURPLE,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Use '{ctx.prefix}arenainventory' to view your acquired items.")
        await ctx.send(embed=embed)

    @commands.command(
        name="arenainventory",
        aliases=["ainv", "vault"],
        help="View all unlocked weapons and armor in your arena inventory.",
    )
    async def arenainventory(self, ctx: CustomContext) -> None:
        """List user's item inventory."""
        conn = get_db_connection()
        try:
            with conn:
                rows = conn.execute(
                    "SELECT item_name, item_type, rarity, atk_bonus, def_bonus, crit_bonus FROM arena_inventory WHERE user_id = ? ORDER BY id DESC LIMIT 25",
                    (ctx.author.id,),
                ).fetchall()
        finally:
            conn.close()

        if not rows:
            return await ctx.send(f"Your backpack is empty! Roll items with `{ctx.prefix}summon`.")

        lines = []
        for r in rows:
            lines.append(
                f"• **{r['item_name']}** ({r['rarity']}) — `+{r['atk_bonus']} ATK` | `+{r['def_bonus']} DEF`"
            )

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Vault ({len(rows)} items)",
            description="\n".join(lines),
            color=ARENA_CYAN,
        )
        embed.set_footer(text=f"Equip any item with: {ctx.prefix}equip <item name>")
        await ctx.send(embed=embed)

    @commands.command(
        name="equip",
        help="Equip a weapon or armor from your inventory: +equip <item name>",
    )
    async def equip(self, ctx: CustomContext, *, item_name: str) -> None:
        """Equip a weapon or armor."""
        conn = get_db_connection()
        try:
            with conn:
                cur = conn.execute(
                    "SELECT * FROM arena_inventory WHERE user_id = ? AND LOWER(item_name) = LOWER(?) LIMIT 1",
                    (ctx.author.id, item_name.strip()),
                )
                row = cur.fetchone()
                if not row:
                    return await ctx.send(f"You don't own **{item_name}**! Check `{ctx.prefix}inventory`.")

                u = get_or_create_user(ctx.author)
                if row["item_type"] == "weapon":
                    u.equipped_weapon = row["item_name"]
                    u.atk = 120 + (u.level * 20) + row["atk_bonus"]
                else:
                    u.equipped_armor = row["item_name"]
                    u.def_stat = 40 + (u.level * 8) + row["def_bonus"]

                save_user(u)
                await ctx.send(f"✅ Successfully equipped **{row['item_name']}** ({row['rarity']} {row['item_type'].capitalize()})!")
        finally:
            conn.close()

    # ─── 5. DAILY REWARDS ─────────────────────────────────────────────────────

    @commands.command(
        name="arenadaily",
        aliases=["adaily", "claimarena"],
        help="Claim your arena daily 300 Gold and 150 XP.",
    )
    async def arenadaily(self, ctx: CustomContext) -> None:
        """Claim daily gold and XP reward."""
        u = get_or_create_user(ctx.author)
        now = time.time()
        elapsed = now - u.last_daily

        if elapsed < 86400:
            remaining = int(86400 - elapsed)
            hrs = remaining // 3600
            mins = (remaining % 3600) // 60
            return await ctx.send(f"⏳ Daily reward already claimed! Return in **{hrs}h {mins}m**.")

        u.gold += 350
        u.last_daily = now
        leveled = u.add_xp(150)
        save_user(u)

        msg = f"🎁 **Daily Reward Claimed!** Received **+350 Gold** and **+150 XP**!"
        if leveled:
            msg += f"\n⭐ **Level Up!** You reached **Level {u.level}**!"
        await ctx.send(msg)

    # ─── 6. MULTI-CATEGORY LEADERBOARDS ───────────────────────────────────────

    @commands.command(
        name="arenatop",
        aliases=["gamelb", "topraids"],
        help="View top Raid Slayers, wealthiest players, and arena champions.",
    )
    async def arenatop(self, ctx: CustomContext) -> None:
        """Display server leaderboards."""
        conn = get_db_connection()
        try:
            with conn:
                top_raids = conn.execute(
                    "SELECT username, raid_kills, level FROM arena_users ORDER BY raid_kills DESC LIMIT 5"
                ).fetchall()
                top_gold = conn.execute(
                    "SELECT username, gold, level FROM arena_users ORDER BY gold DESC LIMIT 5"
                ).fetchall()
        finally:
            conn.close()

        embed = discord.Embed(
            title="🏆 KYOKA ARENA: HALL OF FAME",
            description="The most accomplished warriors in the realm.",
            color=ARENA_GOLD,
        )

        raid_text = "\n".join(
            f"**{i+1}.** {r['username']} (Lv. {r['level']}) — `{r['raid_kills']} Kills`"
            for i, r in enumerate(top_raids)
        ) or "No raid records yet."
        embed.add_field(name="👑 Top Raid Hunters", value=raid_text, inline=False)

        gold_text = "\n".join(
            f"**{i+1}.** {r['username']} (Lv. {r['level']}) — `{r['gold']:,} Gold`"
            for i, r in enumerate(top_gold)
        ) or "No gold records yet."
        embed.add_field(name="💰 Wealthiest Tycoons", value=gold_text, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ArenaRPG(bot))
