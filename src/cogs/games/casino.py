"""
KYOKA 3.0 — Casino & Luck Games Suite.
Commands:
?slots, ?coinflip, ?blackjack, ?roulette, ?dice, ?highlow, ?wheel, ?scratch
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.economy_manager import EconomyManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

AIZEN_PURPLE = 0x2D142C
AIZEN_GOLD = 0xD4AF37


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
            color=AIZEN_PURPLE if not self.is_over else (0x22C55E if "Won" in final_text else 0xEF4444),
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
            embed = discord.Embed(title="💰 Cashed Out!", description=f"> Won **+{payout:,}** with a streak of **{self.streak}**!", color=0x22C55E)
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
                color=0x22C55E
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.stop()
            for c in self.children: c.disabled = True
            await self.cog.eco.update_balance(self.guild_id, self.ctx.author.id, wallet_delta=-self.bet, tx_type="highlow", metadata="Lost highlow")
            embed = discord.Embed(
                title=f"❌ Incorrect! Card was **{next_card}**",
                description=f"> You lost **-{self.bet:,}**!",
                color=0xEF4444
            )
            await interaction.response.edit_message(embed=embed, view=self)


class ScratchCardView(discord.ui.View):
    """Interactive 3x3 scratch off card."""

    def __init__(self, cog: Casino, ctx: CustomContext, cost: int, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.cost = cost
        self.guild_id = guild_id
        # Secret 3x3 symbols (3 matches wins jackpot)
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
                # Check 3 match
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
                    embed = discord.Embed(title="😢 No Match! Better luck next scratch.", color=0xEF4444)
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.response.edit_message(view=self)
        return _scratch


class Casino(commands.Cog):
    """
    🎰 Kyoka Sovereign Casino & Luck Games Suite
    Slots, Coinflip, Blackjack, Roulette, Dice, High-Low, Wheel of Fortune & Scratch cards.
    """

    category = "Casino"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.eco = EconomyManager(bot.db)

    @commands.hybrid_command(name="slots", description="Spin the 3-reel Kyoka slot machine.")
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
        # Weighting
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
                color=0x22C55E
            )
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="slots", metadata="Lost slots")
            embed = discord.Embed(
                title=f"🎰 [ {r1} | {r2} | {r3} ] • No Match",
                description=f"> You lost **-{bet:,}**.",
                color=0xEF4444
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", aliases=["cf"], description="Wager currency on a coinflip or flip a standard coin.")
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

    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="Play high-stakes casino blackjack with interactive buttons.")
    async def blackjack(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet:
            return await ctx.send("Insufficient funds to start this hand!")

        view = BlackjackGameView(self, ctx, bet, guild_id)
        embed = view.build_embed(hide_dealer=True)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="roulette", description="Bet on European roulette (red, black, green, or number 0-36).")
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
                color=0x22C55E
            )
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="roulette", metadata="Lost roulette")
            embed = discord.Embed(
                title=f"🎡 Roulette Landed on: **{rolled_num} ({rolled_color.title()})**!",
                description=f"> You bet on `{space}` and lost **-{bet:,}**.",
                color=0xEF4444
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="dice", description="Roll a dice wager against Aizen.")
    async def dice(self, ctx: CustomContext, bet: Optional[int] = None, prediction: Optional[int] = None) -> None:
        if bet is None or bet <= 0:
            roll = random.randint(1, 6)
            return await ctx.send(f"🎲 Rolled a d6… **{roll}**!")

        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        pred = prediction or 6
        roll = random.randint(1, 6)

        if roll == pred:
            payout = bet * 5
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=payout, tx_type="dice", metadata="Dice exact match")
            await ctx.send(f"🎲 Rolled exact **{roll}**! Won **+{payout:,}** (5x multiplier)!")
        else:
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="dice", metadata="Lost dice")
            await ctx.send(f"🎲 Rolled **{roll}** (You picked {pred}). Lost **-{bet:,}**.")

    @commands.hybrid_command(name="highlow", description="Play Higher or Lower card streak game.")
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

    @commands.hybrid_command(name="wheel", description="Spin the Aizen Wheel of Fortune.")
    async def wheel(self, ctx: CustomContext, bet: int) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds!")

        # Multipliers
        slices = [0.0, 0.5, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0]
        weights = [30, 25, 20, 12, 7, 4, 1.5, 0.5]
        chosen_mult = random.choices(slices, weights=weights, k=1)[0]

        if chosen_mult > 1.0:
            net = int(bet * (chosen_mult - 1.0))
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=net, tx_type="wheel", metadata=f"Wheel {chosen_mult}x")
            embed = discord.Embed(
                title=f"🎡 Wheel Stopped at **{chosen_mult}x**!",
                description=f"> Fortune smiles on you! Won **+{net:,}** *(Total payout: {int(bet * chosen_mult):,})*!",
                color=AIZEN_GOLD if chosen_mult >= 3.0 else 0x22C55E
            )
        else:
            loss = bet if chosen_mult == 0.0 else int(bet * 0.5)
            await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-loss, tx_type="wheel", metadata=f"Wheel {chosen_mult}x")
            embed = discord.Embed(
                title=f"🎡 Wheel Stopped at **{chosen_mult}x**",
                description=f"> You lost **-{loss:,}**.",
                color=0xEF4444
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="scratch", description="Play a 3x3 scratch card with matching symbol payouts.")
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


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Casino(bot))
