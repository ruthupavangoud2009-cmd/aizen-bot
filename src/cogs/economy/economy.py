"""
KYOKA 3.0 — Complete OwO-Style Economy Cog.
Commands:
?cash, ?daily, ?weekly, ?work, ?crime, ?beg, ?deposit, ?withdraw,
?pay, ?rob, ?rich, ?shop, ?buy, ?sell, ?inventory, ?gamble,
?quests, ?achievements, ?lottery, ?profile
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import random
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.economy_manager import EconomyManager
from src.utils.ui import AizenPalette, KyokaEmbed

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

AIZEN_PURPLE = 0x2D142C
AIZEN_GOLD = 0xD4AF37


class PagedLeaderboardView(discord.ui.View):
    """Interactive pagination for economy rich leaderboard."""

    def __init__(self, cog: Economy, ctx: CustomContext, guild_id: int, page: int, total_pages: int, currency: str, emoji: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.guild_id = guild_id
        self.page = page
        self.total_pages = max(1, total_pages)
        self.currency = currency
        self.emoji = emoji
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.disabled = self.page <= 1
        self.btn_next.disabled = self.page >= self.total_pages

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This menu belongs to someone else!", ephemeral=True)
        self.page -= 1
        self._update_buttons()
        embed = await self.cog.build_rich_embed(self.guild_id, self.page, self.currency, self.emoji, self.total_pages)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This menu belongs to someone else!", ephemeral=True)
        self.page += 1
        self._update_buttons()
        embed = await self.cog.build_rich_embed(self.guild_id, self.page, self.currency, self.emoji, self.total_pages)
        await interaction.response.edit_message(embed=embed, view=self)


class PagedShopView(discord.ui.View):
    """Interactive pagination for browsing shop catalog."""

    def __init__(self, items: list[dict[str, Any]], ctx: CustomContext, currency: str, emoji: str, page: int = 1, per_page: int = 4):
        super().__init__(timeout=120)
        self.items = items
        self.ctx = ctx
        self.currency = currency
        self.emoji = emoji
        self.page = page
        self.per_page = per_page
        self.total_pages = max(1, math.ceil(len(items) / per_page))
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.disabled = self.page <= 1
        self.btn_next.disabled = self.page >= self.total_pages

    def build_embed(self) -> discord.Embed:
        start_idx = (self.page - 1) * self.per_page
        current_items = self.items[start_idx : start_idx + self.per_page]

        embed = discord.Embed(
            title=f"🏪 Aizen's Sovereign Emporium",
            description=f"> All goods certified by Kyoka Suigetsu.\n> Use `{self.ctx.clean_prefix}buy <item_id> [amount]` to purchase.\n",
            color=AIZEN_PURPLE,
        )
        for it in current_items:
            embed.add_field(
                name=f"{it.get('emoji', '📦')} {it['name']} (`{it['item_id']}`)",
                value=f"• **Price:** {it['price']:,} {self.emoji} {self.currency}\n• **Sell:** {it['sell_price']:,} {self.emoji}\n• **Rarity:** `{it.get('rarity', 'common').upper()}`\n• *{it.get('description', '')}*",
                inline=False
            )
        embed.set_footer(text=f"Page {self.page} of {self.total_pages} • Items: {len(self.items)}")
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the command requester can navigate!", ephemeral=True)
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the command requester can navigate!", ephemeral=True)
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class Economy(commands.Cog):
    """
    🪙 Kyoka Sovereign Economy Suite
    OwO-style economy with wallet, bank, jobs, robbery, casino gambling, quests & shop.
    """

    category = "Economy"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.eco = EconomyManager(bot.db)

    async def cog_load(self) -> None:
        await self.eco.init_catalog()

    async def _get_settings(self, guild_id: int) -> dict[str, Any]:
        return await self.eco.get_guild_settings(guild_id)

    @commands.hybrid_command(name="cash", aliases=["bal", "balance", "money"], description="View your wallet and bank balances.")
    async def cash(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0

        profile = await self.eco.get_or_create_profile(guild_id, target.id)
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        wallet = profile.get("balance", 0)
        bank = profile.get("bank", 0)
        net_worth = wallet + bank

        embed = discord.Embed(
            title=f"{curr_emoji} {target.display_name}'s Financial Portfolio",
            color=AIZEN_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💵 Wallet Balance", value=f"`{wallet:,}` {curr_emoji} {curr_name}", inline=True)
        embed.add_field(name="🏛️ Bank Vault", value=f"`{bank:,}` {curr_emoji} {curr_name}", inline=True)
        embed.add_field(name="💎 Net Worth", value=f"`{net_worth:,}` {curr_emoji} {curr_name}", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"`{profile.get('daily_streak', 0)}` consecutive days", inline=True)
        embed.add_field(name="📈 Total Earned", value=f"`{profile.get('total_earned', 0):,}` {curr_emoji}", inline=True)
        embed.add_field(name="📉 Total Spent", value=f"`{profile.get('total_spent', 0):,}` {curr_emoji}", inline=True)

        embed.set_footer(text=f"Server Currency: {curr_name} • Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="daily", aliases=["claimdaily"], description="Claim your daily currency allowance and streak bonuses.")
    async def daily(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.claim_daily(guild_id, ctx.author.id)
        if not res["success"]:
            rem = res["remaining"]
            hrs = rem // 3600
            mins = (rem % 3600) // 60
            secs = rem % 60
            return await ctx.send(f"⏳ **Patience.** You already claimed your daily reward! Return in **{hrs}h {mins}m {secs}s**.")

        streak = res["streak"]
        amt = res["amount"]
        new_bal = res["new_balance"]

        embed = discord.Embed(
            title=f"🎁 Daily Allowance Granted!",
            description=(
                f"> **Sosuke Aizen acknowledges your daily loyalty.**\n\n"
                f"• Payout: **+{amt:,}** {curr_emoji} {curr_name}\n"
                f"• Current Streak: **{streak} days** 🔥 *(+{(streak-1)*5}% bonus)*\n"
                f"• New Wallet: **{new_bal:,}** {curr_emoji}\n"
            ),
            color=AIZEN_GOLD,
        )
        embed.set_footer(text=f"Claim again in 24 hours to keep your streak alive!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="weekly", aliases=["claimweekly"], description="Claim your weekly loyalty reward.")
    async def weekly(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.claim_weekly(guild_id, ctx.author.id)
        if not res["success"]:
            rem = res["remaining"]
            days = rem // 86400
            hrs = (rem % 86400) // 3600
            mins = (rem % 3600) // 60
            return await ctx.send(f"⏳ Weekly reward cooldown in effect. Return in **{days}d {hrs}h {mins}m**.")

        embed = discord.Embed(
            title=f"👑 Weekly Treasury Grant Received!",
            description=(
                f"> Payout: **+{res['amount']:,}** {curr_emoji} {curr_name}\n"
                f"> Weekly Streak: **{res['streak']} weeks**\n"
                f"> New Wallet: **{res['new_balance']:,}** {curr_emoji}"
            ),
            color=AIZEN_GOLD,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="work", aliases=["job"], description="Earn currency through dynamic jobs.")
    async def work(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.work(guild_id, ctx.author.id)
        if not res.get("success"):
            rem = res["remaining"]
            return await ctx.send(f"⏳ You are resting between shifts! Return in **{rem // 60}m {rem % 60}s**.")

        embed = discord.Embed(
            title=f"💼 Shift Completed: {res['role']}",
            description=f"> You {res['action']} and earned **+{res['amount']:,}** {curr_emoji} {curr_name}!\n> Wallet: **{res['new_balance']:,}** {curr_emoji}",
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="crime", aliases=["heist"], description="Attempt a high-risk illicit operation for big rewards.")
    async def crime(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.crime(guild_id, ctx.author.id)
        if not res.get("success"):
            rem = res["remaining"]
            return await ctx.send(f"⏳ The heat is still on you! Lay low for another **{rem // 60}m {rem % 60}s**.")

        if res["outcome"] == "success":
            embed = discord.Embed(
                title=f"🕶️ Criminal Operation Succeeded!",
                description=f"> You {res['action']} and made away with **+{res['amount']:,}** {curr_emoji} {curr_name}!\n> Wallet: **{res['new_balance']:,}** {curr_emoji}",
                color=0x22C55E,
            )
        else:
            embed = discord.Embed(
                title=f"🚨 Busted by Authorities!",
                description=f"> You {res['action']} and got fined **-{res['fine']:,}** {curr_emoji} {curr_name}!\n> Wallet: **{res['new_balance']:,}** {curr_emoji}",
                color=0xEF4444,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="beg", description="Ask notable server figures for spare coins.")
    async def beg(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.beg(guild_id, ctx.author.id)
        if res["amount"] == 0:
            return await ctx.send(f"💔 {res['donor']}")

        await ctx.send(f"🪙 **{res['donor']}** handed you **+{res['amount']:,}** {curr_emoji} {curr_name}!")

    @commands.hybrid_command(name="deposit", aliases=["dep"], description="Deposit money from your wallet into the secure bank vault.")
    async def deposit(self, ctx: CustomContext, amount: str) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        profile = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        wallet = profile.get("balance", 0)

        if amount.lower() in ("all", "max"):
            amt = wallet
        else:
            try:
                amt = int(amount.replace(",", ""))
            except ValueError:
                return await ctx.send("Please provide a valid numeric amount, or `all`.")

        if amt <= 0:
            return await ctx.send("Deposit amount must be greater than zero!")
        if amt > wallet:
            return await ctx.send(f"You only have **{wallet:,}** in your wallet!")

        new_wallet, new_bank = await self.eco.update_balance(
            guild_id, ctx.author.id, wallet_delta=-amt, bank_delta=amt, tx_type="deposit", metadata="Vault Deposit"
        )
        await ctx.send(f"🏛️ Successfully deposited **{amt:,}** {curr_emoji} into your bank!\n• Wallet: `{new_wallet:,}` • Bank: `{new_bank:,}`")

    @commands.hybrid_command(name="withdraw", aliases=["with"], description="Withdraw money from your bank into your wallet.")
    async def withdraw(self, ctx: CustomContext, amount: str) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        profile = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        bank = profile.get("bank", 0)

        if amount.lower() in ("all", "max"):
            amt = bank
        else:
            try:
                amt = int(amount.replace(",", ""))
            except ValueError:
                return await ctx.send("Please provide a valid numeric amount, or `all`.")

        if amt <= 0:
            return await ctx.send("Withdrawal amount must be greater than zero!")
        if amt > bank:
            return await ctx.send(f"You only have **{bank:,}** in your bank vault!")

        new_wallet, new_bank = await self.eco.update_balance(
            guild_id, ctx.author.id, wallet_delta=amt, bank_delta=-amt, tx_type="withdraw", metadata="Vault Withdrawal"
        )
        await ctx.send(f"💵 Successfully withdrew **{amt:,}** {curr_emoji} from your bank!\n• Wallet: `{new_wallet:,}` • Bank: `{new_bank:,}`")

    @commands.hybrid_command(name="pay", aliases=["give", "transfer"], description="Transfer money safely to another member.")
    async def pay(self, ctx: CustomContext, member: discord.Member, amount: int) -> None:
        if member.bot:
            return await ctx.send("⛔ You cannot transfer money to bot accounts.")
        if member.id == ctx.author.id:
            return await ctx.send("⛔ You cannot transfer money to yourself.")
        if amount <= 0:
            return await ctx.send("⛔ Transfer amount must be positive.")

        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        try:
            sender_bal, receiver_bal = await self.eco.transfer_funds(guild_id, ctx.author.id, member.id, amount)
            await ctx.send(
                f"✅ **Transaction Complete!** Transferred **{amount:,}** {curr_emoji} {curr_name} to {member.mention}.\n"
                f"• Your new wallet: **{sender_bal:,}** {curr_emoji}"
            )
        except ValueError as err:
            await ctx.send(f"❌ {err}")

    @commands.hybrid_command(name="rob", aliases=["steal"], description="Attempt to pickpocket another member's wallet.")
    async def rob(self, ctx: CustomContext, member: discord.Member) -> None:
        if member.bot:
            return await ctx.send("You cannot rob a bot!")
        if member.id == ctx.author.id:
            return await ctx.send("You cannot rob yourself!")

        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.rob(guild_id, ctx.author.id, member.id)
        if "error" in res:
            return await ctx.send(f"⛔ {res['error']}")

        if res["success"]:
            await ctx.send(f"🥷 **Clean getaway!** You snuck up on {member.mention} and pickpocketed **+{res['stolen']:,}** {curr_emoji} {curr_name}!")
        else:
            await ctx.send(f"🚨 **Busted!** {member.mention} caught you with your hands in their pockets! You were fined **-{res['fine']:,}** {curr_emoji}!")

    async def build_rich_embed(self, guild_id: int, page: int, currency: str, emoji: str, total_pages: int) -> discord.Embed:
        rows, total = await self.eco.get_rich_leaderboard(guild_id, page=page, per_page=10)
        embed = discord.Embed(
            title=f"👑 High Society • Wealth Leaderboard",
            description=f"> Ranking members by Total Net Worth (Wallet + Bank).\n",
            color=AIZEN_PURPLE,
        )
        if not rows:
            embed.description += "\n*No recorded balances in this server yet.*"
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, r in enumerate(rows):
                rank = (page - 1) * 10 + i + 1
                badge = medals[rank - 1] if rank <= 3 else f"`#{rank:02d}`"
                user_str = f"<@{r['user_id']}>"
                embed.add_field(
                    name=f"{badge} {user_str}",
                    value=f"• Net Worth: **{r['net_worth']:,}** {emoji} {currency}\n• Wallet: `{r['balance']:,}` | Vault: `{r['bank']:,}`",
                    inline=False
                )
        embed.set_footer(text=f"Page {page} of {total_pages} • Total Wealthy Members: {total}")
        return embed

    @commands.hybrid_command(name="rich", aliases=["leaderboard", "ecotop"], description="View the server economy wealth leaderboard.")
    async def rich(self, ctx: CustomContext, page: int = 1) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        _, total = await self.eco.get_rich_leaderboard(guild_id, page=1, per_page=10)
        total_pages = max(1, math.ceil(total / 10))
        page = max(1, min(page, total_pages))

        embed = await self.build_rich_embed(guild_id, page, curr_name, curr_emoji, total_pages)
        view = PagedLeaderboardView(self, ctx, guild_id, page, total_pages, curr_name, curr_emoji)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="shop", aliases=["market", "store"], description="Browse the Kyoka item shop.")
    async def shop(self, ctx: CustomContext, page: int = 1) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        items = await self.eco.get_shop_items()
        view = PagedShopView(items, ctx, curr_name, curr_emoji, page=page)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.hybrid_command(name="buy", description="Purchase items or crates from the shop.")
    async def buy(self, ctx: CustomContext, item_id: str, quantity: int = 1) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.buy_item(guild_id, ctx.author.id, item_id, quantity)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")

        it = res["item"]
        await ctx.send(
            f"🛍️ **Purchase Confirmed!** You acquired **{res['quantity']}x {it['name']}** for **{res['total_cost']:,}** {curr_emoji} {curr_name}!\n"
            f"Use `{ctx.clean_prefix}inventory` to inspect your items."
        )

    @commands.hybrid_command(name="sell", description="Sell items from your inventory for currency.")
    async def sell(self, ctx: CustomContext, item_id: str, quantity: int = 1) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.sell_item(guild_id, ctx.author.id, item_id, quantity)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")

        it = res["item"]
        await ctx.send(f"💰 Sold **{res['quantity']}x {it['name']}** for **+{res['payout']:,}** {curr_emoji} {curr_name}!")

    @commands.hybrid_command(name="inventory", aliases=["inv", "backpack"], description="View items, tools, and crates in your backpack.")
    async def inventory(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0

        inv = await self.eco.get_inventory(guild_id, target.id)
        embed = discord.Embed(
            title=f"🎒 {target.display_name}'s Vault & Inventory",
            color=AIZEN_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not inv:
            embed.description = f"> *Backpack is completely empty!*\n> Visit `{ctx.clean_prefix}shop` to purchase tools, crates & equipment."
        else:
            for item in inv:
                equipped_str = " `[Equipped]`" if item.get("equipped") else ""
                embed.add_field(
                    name=f"{item.get('emoji', '📦')} {item['name']} ×{item['quantity']}{equipped_str}",
                    value=f"• ID: `{item['item_id']}` | Type: `{item['category']}`\n• *{item.get('description', '')}*",
                    inline=False
                )
        embed.set_footer(text=f"Total Item Stacks: {len(inv)} • Open crates with ?crate <crate_id>")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="gamble", aliases=["bet"], description="Wager currency in fair high-stakes gambling.")
    async def gamble(self, ctx: CustomContext, amount: int) -> None:
        if amount <= 0:
            return await ctx.send("Wager must be a positive integer!")

        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        max_limit = settings.get("gamble_limit", 50000)
        if amount > max_limit:
            return await ctx.send(f"Maximum table bet allowed is **{max_limit:,}** {curr_emoji}!")

        profile = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        wallet = profile.get("balance", 0)
        if wallet < amount:
            return await ctx.send(f"Insufficient funds! You only have **{wallet:,}** in your wallet.")

        roll = random.randint(1, 100)
        # 1-48: Lost
        # 49-92: Won 2x (net +1x)
        # 93-98: Won 3x (net +2x)
        # 99-100: Jackpot 5x (net +4x)

        if roll <= 48:
            new_bal = wallet - amount
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-amount, tx_type="gamble", metadata="Lost gamble")
            embed = discord.Embed(
                title="🎲 The Illusion Dissolves • You Lost",
                description=f"> You rolled **{roll}** and lost **-{amount:,}** {curr_emoji} {curr_name}!\n> Remaining: **{new_bal:,}** {curr_emoji}",
                color=0xEF4444,
            )
        elif roll <= 92:
            payout = amount
            new_bal = wallet + payout
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="gamble", metadata="Won gamble 2x")
            embed = discord.Embed(
                title="🎲 Fortune Favors the Bold • You Won!",
                description=f"> You rolled **{roll}** and doubled your wager!\n> Won: **+{payout:,}** {curr_emoji} *(Total payout: {amount*2:,})*\n> Wallet: **{new_bal:,}** {curr_emoji}",
                color=0x22C55E,
            )
        elif roll <= 98:
            payout = amount * 2
            new_bal = wallet + payout
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="gamble", metadata="Won gamble 3x")
            embed = discord.Embed(
                title="✨ Super Critical Win! (3x Multiplier)",
                description=f"> You rolled an impressive **{roll}**!\n> Won: **+{payout:,}** {curr_emoji}!\n> Wallet: **{new_bal:,}** {curr_emoji}",
                color=AIZEN_GOLD,
            )
        else:
            payout = amount * 4
            new_bal = wallet + payout
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="gamble", metadata="Won gamble 5x Jackpot")
            embed = discord.Embed(
                title="🌟 JACKPOT TRIPLE 7s! (5x Multiplier)",
                description=f"> Legendary roll of **{roll}**!\n> Won: **+{payout:,}** {curr_emoji}!\n> Wallet: **{new_bal:,}** {curr_emoji}",
                color=AIZEN_GOLD,
            )

        await self.eco.increment_quest(guild_id, ctx.author.id, "gamble", 1)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="quests", aliases=["dailyquests"], description="View and claim your active daily challenges.")
    async def quests(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        q_list = await self.eco.get_or_create_daily_quests(guild_id, ctx.author.id)
        embed = discord.Embed(
            title="📜 Daily Quests & Objectives",
            description="> Complete daily activities to earn bonus gold reserves!\n",
            color=AIZEN_PURPLE,
        )
        for q in q_list:
            status = "✅ Completed (Claimable)" if q["completed"] and not q["claimed"] else ("🎁 Claimed" if q["claimed"] else f"⏳ `{q['current_count']}/{q['target_count']}`")
            embed.add_field(
                name=f"Objective: {q['quest_type'].replace('_', ' ').title()}",
                value=f"• Progress: {status}\n• Reward: **{q['reward_cash']:,}** {curr_emoji} {curr_name}\n• ID: `{q['id']}`",
                inline=False
            )
        embed.set_footer(text=f"Use ?claimquest <id> to claim completed rewards!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="claimquest", description="Claim a completed quest reward by ID.")
    async def claimquest(self, ctx: CustomContext, quest_id: int) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        res = await self.eco.claim_quest_reward(guild_id, ctx.author.id, quest_id)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")
        await ctx.send(f"🎉 **Quest Completed!** Claimed **+{res['reward']:,}** {curr_emoji} {curr_name}!")

    @commands.hybrid_command(name="lottery", aliases=["lotto"], description="View or participate in the server lottery jackpot.")
    async def lottery(self, ctx: CustomContext, tickets: int = 0) -> None:
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        if tickets <= 0:
            lottery = await self.eco.get_active_lottery(guild_id)
            ends_ts = int(lottery["ends_at"].timestamp()) if hasattr(lottery["ends_at"], "timestamp") else int(dt.datetime.utcnow().timestamp() + 86400)
            embed = discord.Embed(
                title=f"🎰 Kyoka Suigetsu Grand Lottery",
                description=(
                    f"> Current Prize Pool: **{lottery.get('pot', 5000):,}** {curr_emoji} {curr_name}\n"
                    f"> Ticket Price: **{lottery.get('ticket_price', 100):,}** {curr_emoji}\n"
                    f"> Drawing Time: <t:{ends_ts}:R>\n\n"
                    f"*Purchase tickets with `{ctx.clean_prefix}lottery <number_of_tickets>`!*"
                ),
                color=AIZEN_GOLD,
            )
            return await ctx.send(embed=embed)

        res = await self.eco.buy_lottery_tickets(guild_id, ctx.author.id, tickets)
        if "error" in res:
            return await ctx.send(f"❌ {res['error']}")

        await ctx.send(
            f"🎟️ Successfully purchased **{res['tickets']} lottery ticket(s)** for **{res['cost']:,}** {curr_emoji}!\n"
            f"• Current Jackpot Pool: **{res['pot']:,}** {curr_emoji} {curr_name}!"
        )

    @commands.hybrid_command(name="achievements", aliases=["badges"], description="View unlocked economy achievements and milestones.")
    async def achievements(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0
        profile = await self.eco.get_or_create_profile(guild_id, target.id)
        net_worth = profile.get("balance", 0) + profile.get("bank", 0)
        streak = profile.get("daily_streak", 0)

        badges = []
        if net_worth >= 10000: badges.append(("🪙 Novice Capitalist", "Accumulate over 10,000 net worth"))
        if net_worth >= 100000: badges.append(("💎 High Roller", "Accumulate over 100,000 net worth"))
        if net_worth >= 1000000: badges.append(("👑 Aizen's Sovereign", "Accumulate over 1,000,000 net worth"))
        if streak >= 7: badges.append(("🔥 Weekly Devotee", "Maintain a 7-day daily streak"))
        if streak >= 30: badges.append(("🌟 Dedicated Disciple", "Maintain a 30-day daily streak"))

        embed = discord.Embed(
            title=f"🏆 {target.display_name}'s Achievements",
            description=f"Unlocked **{len(badges)}/5** Milestones\n",
            color=AIZEN_PURPLE,
        )
        for b_name, b_desc in badges:
            embed.add_field(name=f"✨ {b_name}", value=f"*{b_desc}*", inline=False)
        if not badges:
            embed.description += "\n*No achievements unlocked yet. Work, gamble, and claim daily rewards to unlock milestones!*"
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="profile", aliases=["ecoprofile", "me"], description="View comprehensive economy, bank, and progression stats.")
    async def profile(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self._get_settings(guild_id)
        curr_name = settings.get("currency_name", "KYOKA Coins")
        curr_emoji = settings.get("currency_emoji", "🪙")

        profile = await self.eco.get_or_create_profile(guild_id, target.id)
        inv = await self.eco.get_inventory(guild_id, target.id)

        wallet = profile.get("balance", 0)
        bank = profile.get("bank", 0)
        net_worth = wallet + bank

        embed = discord.Embed(
            title=f"💳 {target.display_name}'s Executive Profile",
            color=AIZEN_PURPLE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💰 Net Worth", value=f"`{net_worth:,}` {curr_emoji}", inline=True)
        embed.add_field(name="💵 Wallet", value=f"`{wallet:,}` {curr_emoji}", inline=True)
        embed.add_field(name="🏛️ Bank Vault", value=f"`{bank:,}` {curr_emoji}", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"`{profile.get('daily_streak', 0)}` Days", inline=True)
        embed.add_field(name="🎒 Inventory Stacks", value=f"`{len(inv)}` Items", inline=True)
        embed.add_field(name="🌐 Currency", value=f"{curr_emoji} {curr_name}", inline=True)

        embed.set_footer(text=f"KYOKA Sovereign Economy • ID: {target.id}")
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Economy(bot))
