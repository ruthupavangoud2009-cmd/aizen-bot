"""
KYOKA 3.0 — Sovereign Casino & Luck Games Suite.
Commands:
?slots, ?coinflip, ?blackjack, ?roulette, ?dice, ?highlow, ?wheel, ?scratch,
?crash, ?mines, ?baccarat, ?horserace
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.economy_manager import EconomyManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

AIZEN_PURPLE = 0x2D142C
AIZEN_GOLD = 0xD4AF37
EMBED_GREEN = 0x22C55E
EMBED_RED = 0xEF4444


# ─── BLACKJACK ───────────────────────────────────────────────────────────────

class BlackjackGameView(discord.ui.View):
    """Interactive Discord UI button-driven Blackjack game session."""

    def __init__(self, cog: Casino, ctx: CustomContext, bet: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.guild_id = guild_id
        self.player_hand = [self._draw(), self._draw()]
        self.dealer_hand = [self._draw(), self._draw()]
        self.is_over = False

    def _draw(self) -> int:
        val = random.randint(1, 13)
        return min(val, 10) if val != 1 else 11

    def _calc(self, hand: list[int]) -> int:
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    def build_embed(self, hide_dealer: bool = True, final_text: str = "") -> discord.Embed:
        p_val = self._calc(self.player_hand)
        d_val = self._calc(self.dealer_hand)

        d_str = f"[{self.dealer_hand[0]}, ?]" if hide_dealer else f"{self.dealer_hand} (Score: **{d_val}**)"
        p_str = f"{self.player_hand} (Score: **{p_val}**)"

        embed = discord.Embed(
            title="♠️ Casino Blackjack Table",
            description=f"> High-stakes table • Wager: **{self.bet:,}**\n\n{final_text}",
            color=AIZEN_PURPLE if not self.is_over else (EMBED_GREEN if "Won" in final_text or "WIN" in final_text else EMBED_RED),
        )
        embed.add_field(name="Dealer's Hand", value=f"> {d_str}", inline=False)
        embed.add_field(name="Your Hand", value=f"> {p_str}", inline=False)
        return embed

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def btn_hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your table!", ephemeral=True)

        self.player_hand.append(self._draw())
        p_val = self._calc(self.player_hand)

        if p_val > 21:
            self.is_over = True
            for child in self.children:
                child.disabled = True
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=-self.bet, tx_type="blackjack", metadata="Bust lost")
            embed = self.build_embed(hide_dealer=False, final_text=f"💥 **BUSTED!** You exceeded 21 and lost **-{self.bet:,}**!")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self.build_embed(hide_dealer=True), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, emoji="🛑")
    async def btn_stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your table!", ephemeral=True)

        self.is_over = True
        for child in self.children:
            child.disabled = True

        while self._calc(self.dealer_hand) < 17:
            self.dealer_hand.append(self._draw())

        p_val = self._calc(self.player_hand)
        d_val = self._calc(self.dealer_hand)

        if d_val > 21:
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=self.bet, tx_type="blackjack", metadata="Dealer bust win")
            final = f"🎉 **DEALER BUSTED ({d_val})!** You won **+{self.bet:,}**!"
        elif p_val > d_val:
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=self.bet, tx_type="blackjack", metadata="Player win")
            final = f"🏆 **YOU WIN!** ({p_val} vs {d_val}) • Won **+{self.bet:,}**!"
        elif d_val > p_val:
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=-self.bet, tx_type="blackjack", metadata="Dealer win")
            final = f"💀 **DEALER WINS!** ({d_val} vs {p_val}) • Lost **-{self.bet:,}**."
        else:
            final = f"🤝 **PUSH!** Both tied at **{p_val}** • Bet returned."

        embed = self.build_embed(hide_dealer=False, final_text=final)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.secondary, emoji="💰")
    async def btn_double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your table!", ephemeral=True)

        prof = await self.cog.eco.get_or_create_profile(self.guild_id, self.ctx.author.id)
        if prof.get("balance", 0) < self.bet * 2:
            return await interaction.response.send_message("Insufficient funds to double down!", ephemeral=True)

        self.bet *= 2
        self.player_hand.append(self._draw())
        await self.btn_stand.callback(interaction)


# ─── HIGHER OR LOWER ────────────────────────────────────────────────────────

class HighLowGameView(discord.ui.View):
    """Higher or Lower card guess game."""

    def __init__(self, cog: Casino, ctx: CustomContext, bet: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.guild_id = guild_id
        self.card = random.randint(1, 13)
        self.streak = 0

    @discord.ui.button(label="Higher ▲", style=discord.ButtonStyle.primary)
    async def btn_high(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_guess(interaction, is_higher=True)

    @discord.ui.button(label="Lower ▼", style=discord.ButtonStyle.primary)
    async def btn_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_guess(interaction, is_higher=False)

    @discord.ui.button(label="Cash Out 💵", style=discord.ButtonStyle.success)
    async def btn_cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)

        self.stop()
        for c in self.children: c.disabled = True
        payout = int(self.bet * (1.0 + (self.streak * 0.5))) - self.bet
        if payout > 0:
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=payout, tx_type="highlow", metadata="Cashed out")
            embed = discord.Embed(title="💰 Cashed Out!", description=f"> Won **+{payout:,}** with a streak of **{self.streak}**!", color=EMBED_GREEN)
        else:
            embed = discord.Embed(title="🤝 Cashed Out Even", description="> Bet returned.", color=AIZEN_PURPLE)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _process_guess(self, interaction: discord.Interaction, is_higher: bool):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)

        next_card = random.randint(1, 13)
        correct = (next_card >= self.card) if is_higher else (next_card <= self.card)

        if correct:
            self.streak += 1
            self.card = next_card
            embed = discord.Embed(
                title=f"✅ Correct! Card: **{next_card}**",
                description=f"> Streak: **{self.streak}** • Current multiplier: **{1.0 + (self.streak * 0.5):.1f}x**\n> Will the next card be higher or lower?",
                color=EMBED_GREEN
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.stop()
            for c in self.children: c.disabled = True
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=-self.bet, tx_type="highlow", metadata="Lost highlow")
            embed = discord.Embed(
                title=f"❌ Incorrect! Card was **{next_card}**",
                description=f"> You lost **-{self.bet:,}**!",
                color=EMBED_RED
            )
            await interaction.response.edit_message(embed=embed, view=self)


# ─── SCRATCH CARD ───────────────────────────────────────────────────────────

class ScratchCardView(discord.ui.View):
    """Interactive 3x3 scratch off card."""

    def __init__(self, cog: Casino, ctx: CustomContext, cost: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.cost = cost
        self.guild_id = guild_id
        pool = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
        if random.random() < 0.40:
            win_sym = random.choice(pool)
            self.grid = [win_sym, win_sym, win_sym] + [random.choice(pool) for _ in range(6)]
            random.shuffle(self.grid)
            self.winning_sym = win_sym
        else:
            self.grid = [random.choice(pool) for _ in range(9)]
            self.winning_sym = None
        self.revealed = 0

        for i in range(9):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i // 3)
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def _scratch(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("Not your scratch card!", ephemeral=True)
            btn = self.children[idx]
            if btn.label != "⬛":
                return await interaction.response.defer()
            btn.label = self.grid[idx]
            btn.disabled = True
            self.revealed += 1

            if self.revealed == 9:
                self.stop()
                counts = {}
                for s in self.grid: counts[s] = counts.get(s, 0) + 1
                winner = next((k for k, v in counts.items() if v >= 3), None)
                if winner:
                    multipliers = {"🍒": 2, "🍋": 3, "🔔": 4, "💎": 6, "7️⃣": 10}
                    mult = multipliers.get(winner, 2)
                    payout = self.cost * mult
                    await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=payout, tx_type="scratch", metadata=f"Won scratch {mult}x")
                    embed = discord.Embed(title=f"🎉 Match 3 {winner}! You Won **+{payout:,}**!", color=AIZEN_GOLD)
                else:
                    embed = discord.Embed(title="😢 No Match! Better luck next scratch.", color=EMBED_RED)
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.response.edit_message(view=self)
        return _scratch


# ─── CRASH (ROCKET MULTIPLIER) ──────────────────────────────────────────────

class CrashGameView(discord.ui.View):
    """Rocket Crash game with rising multiplier and interactive cashout."""

    def __init__(self, cog: Casino, ctx: CustomContext, bet: int, guild_id: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.guild_id = guild_id
        r = random.random()
        self.crash_point = round(max(1.05, 0.99 / (1.0 - r + 0.001)), 2)
        if self.crash_point > 25.0:
            self.crash_point = round(random.uniform(5.0, 25.0), 2)
        self.current_mult = 1.00
        self.cashed_out = False
        self.crashed = False

    @discord.ui.button(label="Cash Out 🚀", style=discord.ButtonStyle.success)
    async def btn_cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your crash session!", ephemeral=True)
        if self.cashed_out or self.crashed:
            return await interaction.response.send_message("Game already ended!", ephemeral=True)

        self.cashed_out = True
        self.stop()
        button.disabled = True

        net_profit = int(self.bet * (self.current_mult - 1.0))
        total_payout = int(self.bet * self.current_mult)
        await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=net_profit, tx_type="crash", metadata=f"Cashed out at {self.current_mult}x")

        embed = discord.Embed(
            title=f"🚀 Cashed Out at {self.current_mult:.2f}x!",
            description=f"> Successful ejection! You secured **+{net_profit:,}** *(Total: {total_payout:,})*!\n> The rocket crashed at **{self.crash_point:.2f}x**.",
            color=EMBED_GREEN,
        )
        await interaction.response.edit_message(embed=embed, view=self)


# ─── MINES (STAKE STYLE 5x5) ────────────────────────────────────────────────

class MinesGameView(discord.ui.View):
    """5x5 Stake-style Mines game with safe gems and hidden bombs."""

    def __init__(self, cog: Casino, ctx: CustomContext, bet: int, guild_id: int, bomb_count: int = 3):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.guild_id = guild_id
        self.bomb_count = max(1, min(24, bomb_count))
        self.safe_count = 25 - self.bomb_count
        self.revealed_safe = 0
        self.is_over = False

        tiles = [1] * self.bomb_count + [0] * (25 - self.bomb_count)
        random.shuffle(tiles)
        self.board = tiles

        for i in range(25):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i // 5)
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _calc_mult(self) -> float:
        if self.revealed_safe == 0:
            return 1.0
        num = math.comb(25, self.revealed_safe)
        den = math.comb(25 - self.bomb_count, self.revealed_safe)
        mult = (num / den) * 0.96
        return max(1.10, round(mult, 2))

    def _make_cb(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("Not your minefield!", ephemeral=True)
            if self.is_over:
                return await interaction.response.defer()

            btn = self.children[idx]
            if btn.label != "⬛":
                return await interaction.response.defer()

            if self.board[idx] == 1:
                self.is_over = True
                self.stop()
                for i, child in enumerate(self.children):
                    child.disabled = True
                    if self.board[i] == 1:
                        child.label = "💣"
                        child.style = discord.ButtonStyle.danger
                    elif child.label == "💎":
                        pass
                    else:
                        child.label = "▫️"
                await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=-self.bet, tx_type="mines", metadata="Detonated mine")
                embed = discord.Embed(
                    title="💥 BOOM! You Hit a Mine!",
                    description=f"> All {self.bomb_count} mines revealed. You lost **-{self.bet:,}**.",
                    color=EMBED_RED,
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            self.revealed_safe += 1
            btn.label = "💎"
            btn.style = discord.ButtonStyle.success
            btn.disabled = True

            mult = self._calc_mult()
            payout = int(self.bet * mult)

            if self.revealed_safe == self.safe_count:
                self.is_over = True
                self.stop()
                for child in self.children:
                    child.disabled = True
                profit = payout - self.bet
                await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=profit, tx_type="mines", metadata="Cleared all mines")
                embed = discord.Embed(
                    title=f"🏆 PERFECTION! All {self.safe_count} Gems Cleared!",
                    description=f"> Multiplier: **{mult:.2f}x** • Won **+{profit:,}** *(Total: {payout:,})*!",
                    color=AIZEN_GOLD,
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            embed = discord.Embed(
                title=f"💎 Safe Gem Revealed! ({mult:.2f}x)",
                description=f"> Gems Found: **{self.revealed_safe}/{self.safe_count}** • Current Value: **{payout:,}**\n> Click another tile to increase profit!",
                color=EMBED_GREEN,
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _callback


# ─── CASINO COG ─────────────────────────────────────────────────────────────

class Casino(commands.Cog):
    """
    🎰 Kyoka Sovereign Casino & Luck Games Suite
    Slots, Coinflip, Blackjack, Roulette, Dice, High-Low, Wheel of Fortune, Scratch cards,
    Crash, Mines, Baccarat & Horse Racing.
    """

    category = "Casino"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.eco = EconomyManager(bot.db)

    @commands.command(name="slots", description="Spin the 3-reel Kyoka slot machine.")
    async def slots(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        settings = await self.eco.get_guild_settings(guild_id)
        limit = settings.get("gamble_limit", 50000)
        if bet > limit: return await ctx.send(f"Max bet is **{limit:,}**!")

        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet:
            return await ctx.send("Insufficient funds in your wallet!")

        reels = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]
        r1 = random.choice(reels)
        r2 = random.choice(reels)
        r3 = random.choice(reels)

        if r1 == r2 == r3:
            payout_table = {"🍒": 3, "🍋": 4, "🍇": 5, "🔔": 7, "💎": 12, "7️⃣": 25}
            mult = payout_table.get(r1, 3)
            payout = bet * mult
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="slots", metadata=f"3 of {r1}")
            embed = discord.Embed(
                title=f"🎰 [ {r1} | {r2} | {r3} ] • JACKPOT!",
                description=f"> Triple match of **{r1}**!\n> Won: **+{payout:,}** *(Multiplier: {mult}x)*",
                color=AIZEN_GOLD
            )
        elif r1 == r2 or r2 == r3 or r1 == r3:
            payout = int(bet * 1.5)
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout - bet, tx_type="slots", metadata="Pair match")
            embed = discord.Embed(
                title=f"🎰 [ {r1} | {r2} | {r3} ] • Double Match!",
                description=f"> Matched pair! Won: **+{payout:,}**",
                color=EMBED_GREEN
            )
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="slots", metadata="Lost slots")
            embed = discord.Embed(
                title=f"🎰 [ {r1} | {r2} | {r3} ] • No Match",
                description=f"> You lost **-{bet:,}**.",
                color=EMBED_RED
            )
        await ctx.send(embed=embed)

    @commands.command(name="coinflip", aliases=["cf", "flip"], description="Wager currency on a coinflip or flip a standard coin.")
    async def coinflip(self, ctx: CustomContext, bet: Optional[int] = None, choice: Optional[str] = "heads") -> None:
        if bet is None or bet <= 0:
            outcome = random.choice(["Heads", "Tails"])
            return await ctx.send(f"🪙 Aizen flips the coin… **{outcome}!**")

        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet:
            return await ctx.send("Insufficient wallet balance for this bet!")

        clean_choice = "heads" if choice and choice.lower().startswith("h") else "tails"
        outcome = random.choice(["heads", "tails"])

        if clean_choice == outcome:
            payout = int(bet * 1.95)
            net = payout - bet
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=net, tx_type="coinflip", metadata="Won coinflip")
            await ctx.send(f"🪙 The coin landed on **{outcome.title()}**! You won **+{net:,}** *(Payout: {payout:,})*!")
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="coinflip", metadata="Lost coinflip")
            await ctx.send(f"🪙 The coin landed on **{outcome.title()}**! You lost **-{bet:,}**.")

    @commands.command(name="blackjack", aliases=["bj"], description="Play high-stakes casino blackjack with interactive buttons.")
    async def blackjack(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet:
            return await ctx.send("Insufficient funds to start this hand!")

        view = BlackjackGameView(self, ctx, bet, guild_id)
        embed = view.build_embed(hide_dealer=True)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="roulette", description="Bet on European roulette (red, black, green, or number 0-36).")
    async def roulette(self, ctx: CustomContext, bet: int, space: str) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        rolled_num = random.randint(0, 36)
        reds = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        rolled_color = "green" if rolled_num == 0 else ("red" if rolled_num in reds else "black")

        space_clean = space.lower().strip()
        won = False
        multiplier = 0

        if space_clean in ("red", "black"):
            if space_clean == rolled_color:
                won = True
                multiplier = 2
        elif space_clean in ("green", "0"):
            if rolled_num == 0:
                won = True
                multiplier = 35
        else:
            try:
                target_num = int(space_clean)
                if target_num == rolled_num:
                    won = True
                    multiplier = 35
            except ValueError:
                return await ctx.send("Valid spaces: `red`, `black`, `green`, or numbers `0-36`.")

        if won:
            payout = bet * (multiplier - 1)
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="roulette", metadata="Won roulette")
            embed = discord.Embed(
                title=f"🎡 Roulette Landed on: **{rolled_num} ({rolled_color.title()})**!",
                description=f"> You predicted `{space}` accurately and won **+{payout:,}**!",
                color=EMBED_GREEN
            )
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="roulette", metadata="Lost roulette")
            embed = discord.Embed(
                title=f"🎡 Roulette Landed on: **{rolled_num} ({rolled_color.title()})**!",
                description=f"> You bet on `{space}` and lost **-{bet:,}**.",
                color=EMBED_RED
            )
        await ctx.send(embed=embed)

    @commands.command(name="dice", aliases=["roll", "droll"], description="Roll a die (2-100 sides) or wager against Aizen.")
    async def dice(self, ctx: CustomContext, bet_or_sides: Optional[int] = None, prediction: Optional[int] = None) -> None:
        if prediction is None:
            sides = bet_or_sides if (bet_or_sides and 2 <= bet_or_sides <= 100) else 6
            roll = random.randint(1, sides)
            return await ctx.send(f"🎲 Rolled a d{sides}… **{roll}**!")

        bet = bet_or_sides
        if bet is None or bet <= 0:
            return await ctx.send("Bet must be positive!")

        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        pred = max(1, min(6, prediction))
        roll = random.randint(1, 6)

        if roll == pred:
            payout = bet * 5
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="dice", metadata="Dice exact match")
            await ctx.send(f"🎲 Rolled exact **{roll}**! Won **+{payout:,}** (5x multiplier)!")
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="dice", metadata="Lost dice")
            await ctx.send(f"🎲 Rolled **{roll}** (You picked {pred}). Lost **-{bet:,}**.")

    @commands.command(name="highlow", aliases=["hl"], description="Play Higher or Lower card streak game.")
    async def highlow(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        view = HighLowGameView(self, ctx, bet, guild_id)
        embed = discord.Embed(
            title=f"🃏 Higher or Lower • Starting Card: **{view.card}**",
            description=f"> Bet: **{bet:,}**\n> Predict if the next card will be Higher or Lower!",
            color=AIZEN_PURPLE
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="wheel", description="Spin the Aizen Wheel of Fortune.")
    async def wheel(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        slices = [0.0, 0.5, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0]
        weights = [30, 25, 20, 12, 7, 4, 1.5, 0.5]
        chosen_mult = random.choices(slices, weights=weights, k=1)[0]

        if chosen_mult > 1.0:
            net = int(bet * (chosen_mult - 1.0))
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=net, tx_type="wheel", metadata=f"Wheel {chosen_mult}x")
            embed = discord.Embed(
                title=f"🎡 Wheel Stopped at **{chosen_mult}x**!",
                description=f"> Fortune smiles on you! Won **+{net:,}** *(Total payout: {int(bet * chosen_mult):,})*!",
                color=AIZEN_GOLD if chosen_mult >= 3.0 else EMBED_GREEN
            )
        else:
            loss = bet if chosen_mult == 0.0 else int(bet * 0.5)
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-loss, tx_type="wheel", metadata=f"Wheel {chosen_mult}x")
            embed = discord.Embed(
                title=f"🎡 Wheel Stopped at **{chosen_mult}x**",
                description=f"> You lost **-{loss:,}**.",
                color=EMBED_RED
            )
        await ctx.send(embed=embed)

    @commands.command(name="scratch", description="Play a 3x3 scratch card with matching symbol payouts.")
    async def scratch(self, ctx: CustomContext, cost: int = 500) -> None:
        if cost <= 0: return await ctx.send("Cost must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < cost: return await ctx.send("Insufficient funds to buy a scratch card!")

        await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-cost, tx_type="scratch_card", metadata="Bought scratch card")
        view = ScratchCardView(self, ctx, cost, guild_id)
        embed = discord.Embed(
            title="🎫 Kyoka Lucky Scratch Card",
            description=f"> Cost: **{cost:,}**\n> Click boxes to scratch and reveal. Match 3 identical symbols to win!",
            color=AIZEN_PURPLE
        )
        await ctx.send(embed=embed, view=view)

    # ─── NEW EXPANDED CASINO GAMES ──────────────────────────────────────────

    @commands.command(name="crash", description="High-stakes rocket multiplier game. Cash out before it explodes!")
    async def crash(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient wallet balance for this wager!")

        view = CrashGameView(self, ctx, bet, guild_id)
        embed = discord.Embed(
            title="🚀 Kyoka Rocket Crash",
            description=f"> Wager: **{bet:,}**\n> Current Multiplier: **1.00x**\n> *Click Cash Out before the rocket crashes!*",
            color=AIZEN_PURPLE,
        )
        msg = await ctx.send(embed=embed, view=view)

        multipliers = [1.10, 1.25, 1.45, 1.70, 2.00, 2.40, 2.90, 3.50, 4.30, 5.20, 6.50, 8.00, 10.00, 15.00, 20.00]
        for mult in multipliers:
            await asyncio.sleep(1.0)
            if view.cashed_out:
                break
            if mult >= view.crash_point:
                view.crashed = True
                view.stop()
                for c in view.children: c.disabled = True
                await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="crash", metadata="Crashed lost")
                crash_embed = discord.Embed(
                    title=f"💥 CRASHED at {view.crash_point:.2f}x!",
                    description=f"> The rocket exploded! You lost **-{bet:,}**.",
                    color=EMBED_RED,
                )
                try:
                    await msg.edit(embed=crash_embed, view=view)
                except Exception:
                    pass
                return

            view.current_mult = mult
            payout = int(bet * mult)
            embed.description = (
                f"> Wager: **{bet:,}**\n"
                f"> Current Multiplier: **{mult:.2f}x** *(Value: {payout:,})*\n"
                f"> *Click Cash Out before the rocket explodes!*"
            )
            try:
                await msg.edit(embed=embed, view=view)
            except Exception:
                pass

    @commands.command(name="mines", description="Stake-style 5x5 minefield. Reveal gems and cash out anytime.")
    async def mines(self, ctx: CustomContext, bet: int, bombs: int = 3) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        if not (1 <= bombs <= 20): return await ctx.send("Bomb count must be between **1 and 20**!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds in your wallet!")

        view = MinesGameView(self, ctx, bet, guild_id, bomb_count=bombs)
        embed = discord.Embed(
            title=f"💣 Kyoka Mines • 5x5 Grid ({bombs} Bombs)",
            description=f"> Wager: **{bet:,}** • Safe Gems: **{25 - bombs}**\n> Click tiles to uncover gems 💎. Avoid bombs 💣!",
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="baccarat", aliases=["bac"], description="Classic Punto Banco baccarat (bet on player, banker, or tie).")
    async def baccarat(self, ctx: CustomContext, bet: int, side: str = "player") -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        side_clean = side.lower().strip()
        if side_clean not in ("player", "banker", "tie", "p", "b", "t"):
            return await ctx.send("Valid betting sides: `player`, `banker`, or `tie`.")
        target_side = "player" if side_clean in ("player", "p") else ("banker" if side_clean in ("banker", "b") else "tie")

        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient wallet balance!")

        def card_val(c: int) -> int:
            return 0 if c >= 10 else c

        p_cards = [random.randint(1, 13), random.randint(1, 13)]
        b_cards = [random.randint(1, 13), random.randint(1, 13)]
        p_score = (card_val(p_cards[0]) + card_val(p_cards[1])) % 10
        b_score = (card_val(b_cards[0]) + card_val(b_cards[1])) % 10

        if p_score < 8 and b_score < 8:
            if p_score <= 5:
                extra = random.randint(1, 13)
                p_cards.append(extra)
                p_score = (p_score + card_val(extra)) % 10
            if b_score <= 5:
                extra = random.randint(1, 13)
                b_cards.append(extra)
                b_score = (b_score + card_val(extra)) % 10

        outcome = "player" if p_score > b_score else ("banker" if b_score > p_score else "tie")
        won = (target_side == outcome)

        if won:
            if outcome == "tie":
                payout = bet * 8
            elif outcome == "banker":
                payout = int(bet * 0.95)
            else:
                payout = bet
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="baccarat", metadata=f"Won {outcome}")
            embed = discord.Embed(
                title=f"🎴 Baccarat: {outcome.upper()} WINS! ({p_score} vs {b_score})",
                description=f"> **Player Hand:** {p_cards} (Score: `{p_score}`)\n> **Banker Hand:** {b_cards} (Score: `{b_score}`)\n\n> 🏆 You predicted `{target_side}` and won **+{payout:,}**!",
                color=EMBED_GREEN,
            )
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="baccarat", metadata=f"Lost {outcome}")
            embed = discord.Embed(
                title=f"🎴 Baccarat: {outcome.upper()} WINS! ({p_score} vs {b_score})",
                description=f"> **Player Hand:** {p_cards} (Score: `{p_score}`)\n> **Banker Hand:** {b_cards} (Score: `{b_score}`)\n\n> 💀 You bet on `{target_side}` and lost **-{bet:,}**.",
                color=EMBED_RED,
            )
        await ctx.send(embed=embed)

    @commands.command(name="horserace", aliases=["race"], description="Bet on an animated 4-horse sprint derby.")
    async def horserace(self, ctx: CustomContext, bet: int, horse: int = 1) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        if not (1 <= horse <= 4): return await ctx.send("Pick a horse number between **1 and 4**!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        horses = [
            ("🏇 1. Kyoka Phantom", 0),
            ("🐎 2. Bankai Blitz", 0),
            ("🦄 3. Soul Reaper", 0),
            ("🦓 4. Aizen Mirage", 0),
        ]
        track_len = 12

        def render_track() -> str:
            lines = []
            for name, pos in horses:
                track = "•" * pos + "🏇" + "—" * max(0, track_len - pos) + "🏁"
                lines.append(f"**{name}**\n`[{track}]`")
            return "\n".join(lines)

        embed = discord.Embed(
            title="🏁 Kyoka Grand Derby • The Race is ON!",
            description=render_track(),
            color=AIZEN_PURPLE,
        )
        msg = await ctx.send(embed=embed)

        winner_idx = None
        for step in range(5):
            await asyncio.sleep(1.2)
            for i in range(4):
                adv = random.randint(1, 3)
                new_pos = min(track_len, horses[i][1] + adv)
                horses[i] = (horses[i][0], new_pos)
                if new_pos >= track_len and winner_idx is None:
                    winner_idx = i

            embed.description = render_track()
            try:
                await msg.edit(embed=embed)
            except Exception:
                pass
            if winner_idx is not None:
                break

        winner_num = (winner_idx or 0) + 1
        winner_name = horses[winner_idx or 0][0]

        if horse == winner_num:
            payout = int(bet * 2.8)
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="horserace", metadata="Won horse race")
            embed.title = f"🏆 {winner_name} CROSSES THE FINISH LINE FIRST!"
            embed.color = EMBED_GREEN
            embed.description += f"\n\n🎉 **VICTORY!** Your horse won! Payout: **+{payout:,}** *(2.8x)*!"
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="horserace", metadata="Lost horse race")
            embed.title = f"💀 {winner_name} WON THE DERBY!"
            embed.color = EMBED_RED
            embed.description += f"\n\n❌ Your pick (Horse #{horse}) lost. Deduction: **-{bet:,}**."

        try:
            await msg.edit(embed=embed)
        except Exception:
            pass


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Casino(bot))
