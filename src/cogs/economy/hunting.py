"""
KYOKA 3.0 — OwO-Style Hunting, Pets, Collection & Adventure RPG Cog.
Commands:
?hunt, ?catch, ?battle, ?zoo, ?pets, ?pet, ?feed, ?trade,
?crate, ?craft, ?upgrade, ?fishing, ?mine, ?explore,
?adventure, ?dungeon, ?raid, ?boss, ?quest, ?collection
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.economy_manager import EconomyManager
from src.managers.hunting_manager import HuntingManager, CRAFTING_RECIPES
from src.utils.ui import AizenPalette

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

AIZEN_PURPLE = 0x2D142C
AIZEN_GOLD = 0xD4AF37


class TradeConfirmView(discord.ui.View):
    """Interactive dual-confirmation trade view with duplicate-exploit prevention."""

    def __init__(self, sender: discord.Member, receiver: discord.Member, offer_str: str, receive_str: str):
        super().__init__(timeout=60)
        self.sender = sender
        self.receiver = receiver
        self.offer_str = offer_str
        self.receive_str = receive_str
        self.sender_accepted = False
        self.receiver_accepted = False
        self.is_cancelled = False

    @discord.ui.button(label="Accept Trade", style=discord.ButtonStyle.success, emoji="🤝")
    async def btn_accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            return await interaction.response.send_message("You are not part of this trade agreement!", ephemeral=True)

        if interaction.user.id == self.sender.id:
            self.sender_accepted = True
        elif interaction.user.id == self.receiver.id:
            self.receiver_accepted = True

        if self.sender_accepted and self.receiver_accepted:
            self.stop()
            embed = discord.Embed(
                title="✅ Trade Executed Successfully!",
                description=f"> Both **{self.sender.display_name}** and **{self.receiver.display_name}** confirmed the trade terms.",
                color=0x22C55E
            )
            return await interaction.response.edit_message(embed=embed, view=None)

        waiting_on = self.receiver.display_name if self.sender_accepted else self.sender.display_name
        embed = discord.Embed(
            title="⏳ Trade Pending Confirmation",
            description=f"> One party has confirmed. Waiting for **{waiting_on}** to accept or decline.",
            color=AIZEN_GOLD
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cancel / Decline", style=discord.ButtonStyle.danger, emoji="✖️")
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.sender.id, self.receiver.id):
            return await interaction.response.send_message("You are not part of this trade agreement!", ephemeral=True)

        self.is_cancelled = True
        self.stop()
        embed = discord.Embed(
            title="🚫 Trade Cancelled",
            description=f"> Trade was declined by **{interaction.user.display_name}**. No assets were transferred.",
            color=0xEF4444
        )
        await interaction.response.edit_message(embed=embed, view=None)


class Hunting(commands.Cog):
    """
    🏹 Kyoka Hunting, Pets & Wilderness RPG Suite
    Catch creatures, cultivate pets, mine, fish, craft and battle world bosses.
    """

    category = "Hunting & Animals"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.hunting_mgr = HuntingManager(bot.db)
        self.eco_mgr = EconomyManager(bot.db)

    async def cog_load(self) -> None:
        await self.hunting_mgr.init_catalog()

    @commands.command(name="hunt", aliases=["catchanimal"], description="Hunt in the wilderness to encounter wild creatures and collect loot.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def hunt(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        res = await self.hunting_mgr.hunt(guild_id, ctx.author.id)
        creature = res["creature"]

        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        # Award small hunting coins
        if res["coins"] > 0:
            await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=res["coins"], tx_type="hunting_loot", metadata=f"Hunted {creature['creature_id']}")

        await self.eco_mgr.increment_quest(guild_id, ctx.author.id, "hunt", 1)

        rarity_colors = {
            "Common": 0x94A3B8,
            "Uncommon": 0x22C55E,
            "Rare": 0x3B82F6,
            "Epic": 0xA855F7,
            "Legendary": AIZEN_GOLD,
            "Mythical": 0xE11D48,
            "Seasonal": 0xF43F5E,
        }
        color = rarity_colors.get(creature["rarity"], AIZEN_PURPLE)

        if res["caught"]:
            rare_alert = " ⭐ **RARE ENCOUNTER BROADCAST!** ⭐\n" if res["is_rare"] else ""
            embed = discord.Embed(
                title=f"{creature['emoji']} Caught a {creature['name']}! ({creature['rarity']})",
                description=(
                    f"{rare_alert}"
                    f"> You ventured into the forest and captured a **{creature['name']}**!\n"
                    f"> Catch Probability: `{res['catch_rate']}%`\n"
                    f"> Scavenged Loot: **+{res['coins']:,}** {curr_emoji}\n\n"
                    f"⚔️ **HP:** `{creature['base_hp']}` • **ATK:** `{creature['base_atk']}` • **DEF:** `{creature['base_def']}`\n"
                    f"*{creature['description']}*"
                ),
                color=color,
            )
            embed.set_footer(text=f"View your collected pets with {ctx.clean_prefix}zoo or {ctx.clean_prefix}pets!")
        else:
            embed = discord.Embed(
                title=f"💨 The {creature['name']} Escaped!",
                description=(
                    f"> You spotted a wild {creature['emoji']} **{creature['name']}** ({creature['rarity']}), but it darted into the shadows!\n"
                    f"> However, you found **+{res['coins']:,}** {curr_emoji} dropped on the trail."
                ),
                color=0x64748B,
            )
        await ctx.send(embed=embed)

    @commands.command(name="catch", aliases=["capture"], description="Attempt to catch a specific targeted beast.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def catch(self, ctx: CustomContext) -> None:
        await self.hunt(ctx)

    @commands.command(name="zoo", aliases=["animals", "creatures"], description="View your entire collection of captured creatures.")
    async def zoo(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0

        data = await self.hunting_mgr.get_zoo(guild_id, target.id)
        categories = data["categories"]

        embed = discord.Embed(
            title=f"🐾 {target.display_name}'s Sovereign Menagerie & Zoo",
            description=(
                f"> **Collection Progress:** `{data['completion_pct']}%` ({data['unique_count']}/{data['catalog_size']} Unique Species)\n"
                f"> **Total Animals:** `{data['total_count']:,}` Captured\n"
            ),
            color=AIZEN_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        order = ["Mythical", "Legendary", "Epic", "Rare", "Uncommon", "Common", "Seasonal"]
        for tier in order:
            creatures = categories.get(tier, [])
            if creatures:
                text_lines = []
                for c in creatures:
                    text_lines.append(f"{c['emoji']} **{c['name']}** ×{c['count']} *(Lv.{c['level']})*")
                embed.add_field(name=f"{tier} Tier ({len(creatures)})", value="\n".join(text_lines), inline=False)

        if data["total_count"] == 0:
            embed.description += "\n*Your zoo is currently empty! Venture out with ?hunt to catch animals.*"

        embed.set_footer(text=f"Feed pets with ?feed <name> • Equip with ?pet equip <name>")
        await ctx.send(embed=embed)

    @commands.command(name="pets", aliases=["mypets"], description="Manage your equipped pets and pet stats.")
    async def pets(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        await self.zoo(ctx, member)

    @commands.command(name="pet", description="View detailed combat stats and affection for a specific pet.")
    async def pet(self, ctx: CustomContext, *, name: str) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        pet = await self.hunting_mgr.get_pet(guild_id, ctx.author.id, name)
        if not pet:
            return await ctx.send(f"❌ You don't own a creature matching **`{name}`**! Check `{ctx.clean_prefix}zoo`.")

        lvl = pet.get("level", 1)
        hp = pet["base_hp"] + (lvl * 15)
        atk = pet["base_atk"] + (lvl * 5)
        defense = pet["base_def"] + (lvl * 3)

        embed = discord.Embed(
            title=f"{pet['emoji']} Pet Dossier: {pet['name']} (Level {lvl})",
            description=f"> Rarity: `{pet['rarity']}` • Quantity: `×{pet['count']}`\n> *{pet['description']}*\n",
            color=AIZEN_PURPLE,
        )
        embed.add_field(name="❤️ Health (HP)", value=f"`{hp}`", inline=True)
        embed.add_field(name="⚔️ Attack (ATK)", value=f"`{atk}`", inline=True)
        embed.add_field(name="🛡️ Defense (DEF)", value=f"`{defense}`", inline=True)
        embed.add_field(name="💖 Affection", value=f"`{pet['affection']}/100`", inline=True)
        embed.add_field(name="⭐ Experience", value=f"`{pet['exp']}/{lvl * 50}` XP", inline=True)
        embed.add_field(name="👑 Status", value="`Equipped`" if pet.get("equipped_pet") else "`Idle`", inline=True)
        embed.set_footer(text=f"Feed your pet with ?feed {pet['creature_id']} to gain XP & Affection!")
        await ctx.send(embed=embed)

    @commands.command(name="feed", description="Feed a captured pet with Gourmet Pet Kibble to level it up.")
    async def feed(self, ctx: CustomContext, *, name: str) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        res = await self.hunting_mgr.feed_pet(guild_id, ctx.author.id, name)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")

        lvl_str = f" ⭐ **LEVEL UP! Reached Level {res['level']}!**" if res["leveled_up"] else f" (Level {res['level']})"
        await ctx.send(
            f"🍖 Fed **{res['pet_name']}** {res['emoji']} a bowl of gourmet kibble!{lvl_str}\n"
            f"• Affection increased to **{res['affection']}/100**!"
        )

    @commands.command(name="fishing", aliases=["fish"], description="Cast your fishing rod into mystical waters.")
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def fishing(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.hunting_mgr.fish(guild_id, ctx.author.id)
        if "error" in res:
            return await ctx.send(f"🎣 {res['error']}")

        fish = res["fish"]
        val = res["value"]
        await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=val, tx_type="fishing", metadata=f"Caught {fish['name']}")

        bonus_str = " *(+Super Rod Luck Applied)*" if res["super_rod_bonus"] else ""
        embed = discord.Embed(
            title=f"{fish['emoji']} Caught a {fish['name']}!",
            description=(
                f"> You reeled in a **{fish['rarity']}** catch!{bonus_str}\n"
                f"> Market Bounty: **+{val:,}** {curr_emoji}"
            ),
            color=0x38BDF8,
        )
        await ctx.send(embed=embed)

    @commands.command(name="mine", aliases=["dig"], description="Excavate the underground caverns for precious ores and gems.")
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def mine(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.hunting_mgr.mine(guild_id, ctx.author.id)
        if "error" in res:
            return await ctx.send(f"⛏️ {res['error']}")

        ore = res["ore"]
        total_val = res["total_value"]
        await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=total_val, tx_type="mining", metadata=f"Mined {ore['name']}")

        bonus_str = " *(+Cyber Laser Excavator Multiplier)*" if res["laser_bonus"] else ""
        embed = discord.Embed(
            title=f"{ore['emoji']} Vein Excavated: {ore['name']}!",
            description=(
                f"> Struck a rich deposit of **{ore['name']}** ({ore['rarity']})!{bonus_str}\n"
                f"> Yield: `×{res['quantity']}` • Total Value: **+{total_val:,}** {curr_emoji}"
            ),
            color=0xF59E0B,
        )
        await ctx.send(embed=embed)

    @commands.command(name="crate", description="Open a reward crate from your inventory.")
    async def crate(self, ctx: CustomContext, crate_id: str = "wooden_crate") -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco_mgr.open_crate(guild_id, ctx.author.id, crate_id)
        if "error" in res:
            return await ctx.send(f"📦 {res['error']}")

        item_str = f"\n• Unlocked Item: {res['item'].get('emoji', '📦')} **{res['item']['name']}**!" if res.get("item") else ""
        embed = discord.Embed(
            title="🎁 Supply Crate Unsealed!",
            description=(
                f"> You unlocked the `{crate_id}` and discovered:\n"
                f"• Currency Payout: **+{res['cash']:,}** {curr_emoji}{item_str}"
            ),
            color=AIZEN_GOLD,
        )
        await ctx.send(embed=embed)

    @commands.command(name="craft", description="Craft tools and weapons from gathered materials.")
    async def craft(self, ctx: CustomContext, recipe_id: Optional[str] = None) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        if not recipe_id:
            embed = discord.Embed(
                title="🔨 Sovereign Forge & Crafting Bench",
                description="> Craft legendary gear using ores and currency.\n> Usage: `?craft <recipe_id>`\n",
                color=AIZEN_PURPLE,
            )
            for r in CRAFTING_RECIPES:
                embed.add_field(
                    name=f"🛠️ {r['name']} (`{r['recipe_id']}`)",
                    value=f"• Cost: **{r['cost']:,}** {curr_emoji}\n• *{r['description']}*",
                    inline=False
                )
            return await ctx.send(embed=embed)

        res = await self.hunting_mgr.craft_item(guild_id, ctx.author.id, recipe_id)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")

        await ctx.send(f"✨ **Forging Complete!** You crafted **{res['recipe']['name']}**! Check `{ctx.clean_prefix}inventory`.")

    @commands.command(name="explore", description="Explore unknown territories for random adventure encounters.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def explore(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        events = [
            ("Ruins of Las Noches", "stumbled upon an ancient reliquary hidden beneath the white dunes", 450),
            ("Soul Society Royal Archives", "discovered a hidden tactical manuscript left by the Shinigami Academy", 600),
            ("Garganta Rift", "navigated through the dimensional rift safely and extracted spiritual particles", 800),
            ("Karakura Suburbs", "saved a spiritual medium who rewarded you generously", 350),
        ]
        loc, story, reward = random.choice(events)
        await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=reward, tx_type="explore", metadata=f"Explored {loc}")

        embed = discord.Embed(
            title=f"🧭 Exploration: {loc}",
            description=f"> You {story}!\n> Found Bounty: **+{reward:,}** {curr_emoji}",
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed)

    @commands.command(name="adventure", aliases=["adv"], description="Start an RPG questing adventure.")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def adventure(self, ctx: CustomContext) -> None:
        await self.explore(ctx)

    @commands.command(name="dungeon", aliases=["tower"], description="Venture into the procedural Hueco Mundo dungeon.")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def dungeon(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        floors = random.randint(3, 12)
        loot = floors * random.randint(120, 250)
        await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=loot, tx_type="dungeon_clear", metadata=f"Cleared {floors} floors")

        embed = discord.Embed(
            title=f"🏰 Dungeon Expedition Cleared: Floor {floors}",
            description=(
                f"> You marched through Hueco Mundo's subterranean labyrinths and defeated all guardians up to **Floor {floors}**!\n"
                f"> Dungeon Vault Payout: **+{loot:,}** {curr_emoji}"
            ),
            color=AIZEN_GOLD,
        )
        await ctx.send(embed=embed)

    @commands.command(name="boss", aliases=["worldboss", "raid"], description="Challenge a formidable raid world boss.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def boss(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco_mgr.get_guild_settings(guild_id)
        curr_emoji = settings.get("currency_emoji", "🪙")

        bosses = [
            ("Menos Grande Prime", 1200),
            ("Espada Zero Yammy", 1800),
            ("Ulquiorra Cifer — Segunda Etapa", 2500),
            ("Grimmjow Jaegerjaquez", 1600),
        ]
        b_name, bounty = random.choice(bosses)
        await self.eco_mgr.update_balance(guild_id, ctx.author.id, wallet_delta=bounty, tx_type="boss_slain", metadata=f"Slain {b_name}")

        embed = discord.Embed(
            title=f"⚔️ World Boss Slain: {b_name}!",
            description=(
                f"> Your squad broke through the boss's Hierro and claimed victory!\n"
                f"> Sovereign Bounty: **+{bounty:,}** {curr_emoji}"
            ),
            color=0xEF4444,
        )
        await ctx.send(embed=embed)

    @commands.command(name="collection", description="View your hunting collection completion progress.")
    async def collection(self, ctx: CustomContext) -> None:
        await self.zoo(ctx)

    @commands.command(name="trade", description="Trade items or creatures safely with another member.")
    async def trade(self, ctx: CustomContext, member: discord.Member, offer: str, for_item: str) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("Invalid trade partner!")

        view = TradeConfirmView(ctx.author, member, offer, for_item)
        embed = discord.Embed(
            title="🤝 Proposed Trade Agreement",
            description=(
                f"> **Initiator:** {ctx.author.mention} offering `{offer}`\n"
                f"> **Recipient:** {member.mention} providing `{for_item}`\n\n"
                f"*Both members must click **Accept Trade** to finalize.*"
            ),
            color=AIZEN_GOLD,
        )
        await ctx.send(embed=embed, view=view)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Hunting(bot))
