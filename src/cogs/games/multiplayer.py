"""
KYOKA 3.0 — Multiplayer Games, Turn-Based Challenges & Puzzles Cog.
Commands:
?tictactoe @user, ?connect4 @user, ?chess @user, ?battleship @user, ?duel @user,
?reaction, ?fasttype, ?trivia, ?quiz, ?hangman, ?wordle, ?riddle, ?2048
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.economy_manager import EconomyManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

AIZEN_PURPLE = 0x2D142C
AIZEN_GOLD = 0xD4AF37


class TicTacToeView(discord.ui.View):
    """3x3 Tic Tac Toe game grid with turn validation."""

    def __init__(self, p1: discord.Member, p2: discord.Member):
        super().__init__(timeout=90)
        self.p1 = p1
        self.p2 = p2
        self.turn = p1
        self.board = [0] * 9  # 0 empty, 1 = p1 (❌), 2 = p2 (⭕)

        for i in range(9):
            btn = discord.ui.Button(label="·", style=discord.ButtonStyle.secondary, row=i // 3)
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn.id:
                return await interaction.response.send_message("It's not your turn!", ephemeral=True)

            piece = 1 if self.turn == self.p1 else 2
            self.board[idx] = piece

            btn = self.children[idx]
            btn.label = "❌" if piece == 1 else "⭕"
            btn.style = discord.ButtonStyle.danger if piece == 1 else discord.ButtonStyle.primary
            btn.disabled = True

            winner = self._check_win()
            if winner:
                self.stop()
                for c in self.children: c.disabled = True
                win_member = self.p1 if winner == 1 else self.p2
                embed = discord.Embed(
                    title=f"🏆 {win_member.display_name} Won Tic-Tac-Toe!",
                    description=f"> Outstanding strategy! **{win_member.mention}** claims the match.",
                    color=0x22C55E
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            if 0 not in self.board:
                self.stop()
                for c in self.children: c.disabled = True
                embed = discord.Embed(
                    title="🤝 Tic-Tac-Toe Draw!",
                    description="> Stalemate. The board is full with no winner.",
                    color=AIZEN_PURPLE
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            self.turn = self.p2 if self.turn == self.p1 else self.p1
            embed = discord.Embed(
                title="⚔️ Tic-Tac-Toe Duel",
                description=f"> Turn: **{self.turn.mention}** ({'❌' if self.turn == self.p1 else '⭕'})",
                color=AIZEN_PURPLE
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _callback

    def _check_win(self) -> Optional[int]:
        b = self.board
        lines = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8), # rows
            (0, 3, 6), (1, 4, 7), (2, 5, 8), # cols
            (0, 4, 8), (2, 4, 6)             # diagonals
        ]
        for p1, p2, p3 in lines:
            if b[p1] != 0 and b[p1] == b[p2] == b[p3]:
                return b[p1]
        return None


class Connect4View(discord.ui.View):
    """Interactive Connect 4 drop column game."""

    def __init__(self, p1: discord.Member, p2: discord.Member):
        super().__init__(timeout=120)
        self.p1 = p1
        self.p2 = p2
        self.turn = p1
        self.rows = 6
        self.cols = 7
        self.grid = [[0 for _ in range(self.cols)] for _ in range(self.rows)]

        for col in range(self.cols):
            btn = discord.ui.Button(label=str(col + 1), style=discord.ButtonStyle.secondary, row=col // 4)
            btn.callback = self._make_cb(col)
            self.add_item(btn)

    def _render_board(self) -> str:
        emojis = {0: "⚪", 1: "🔴", 2: "🟡"}
        lines = []
        for r in range(self.rows):
            lines.append("".join(emojis[self.grid[r][c]] for c in range(self.cols)))
        lines.append("1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣")
        return "\n".join(lines)

    def _make_cb(self, col: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn.id:
                return await interaction.response.send_message("Not your turn!", ephemeral=True)

            # Drop into lowest open row in col
            target_r = -1
            for r in reversed(range(self.rows)):
                if self.grid[r][col] == 0:
                    target_r = r
                    break

            if target_r == -1:
                return await interaction.response.send_message("Column is full! Choose another column.", ephemeral=True)

            piece = 1 if self.turn == self.p1 else 2
            self.grid[target_r][col] = piece

            if self._check_win(target_r, col, piece):
                self.stop()
                for c in self.children: c.disabled = True
                embed = discord.Embed(
                    title=f"🎉 {self.turn.display_name} Won Connect 4!",
                    description=f"{self._render_board()}\n\n> 4 in a row! Winner: **{self.turn.mention}**",
                    color=0x22C55E
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            self.turn = self.p2 if self.turn == self.p1 else self.p1
            sym = "🔴" if self.turn == self.p1 else "🟡"
            embed = discord.Embed(
                title=f"🔴 Connect 4 • Turn: {self.turn.display_name} ({sym})",
                description=self._render_board(),
                color=AIZEN_PURPLE
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _callback

    def _check_win(self, r: int, c: int, piece: int) -> bool:
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            count = 1
            # forward
            nr, nc = r + dr, c + dc
            while 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == piece:
                count += 1
                nr += dr
                nc += dc
            # backward
            nr, nc = r - dr, c - dc
            while 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == piece:
                count += 1
                nr -= dr
                nc -= dc
            if count >= 4:
                return True
        return False


class WordleView(discord.ui.View):
    """5-letter Wordle puzzle with text input handling."""

    def __init__(self, target_word: str, user_id: int):
        super().__init__(timeout=180)
        self.target = target_word.upper()
        self.user_id = user_id
        self.guesses = []
        self.max_attempts = 6

    def render_guesses(self) -> str:
        lines = []
        for g in self.guesses:
            res = []
            for i, char in enumerate(g):
                if char == self.target[i]:
                    res.append(f"🟩 `{char}`")
                elif char in self.target:
                    res.append(f"🟨 `{char}`")
                else:
                    res.append(f"⬛ `{char}`")
            lines.append(" ".join(res))
        for _ in range(self.max_attempts - len(self.guesses)):
            lines.append("⬜ ⬜ ⬜ ⬜ ⬜")
        return "\n".join(lines)


class MultiplayerGames(commands.Cog):
    """
    🎮 Kyoka Multiplayer & Puzzle Suite
    TicTacToe, Connect4, Chess, Battleship, RPG Duels, Wordle, Hangman & Trivia.
    """

    category = "Multiplayer Games"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.eco = EconomyManager(bot.db)
        self._active_sessions: set[int] = set()

    @commands.hybrid_command(name="tictactoe", aliases=["ttt"], description="Challenge a member to Tic-Tac-Toe.")
    async def tictactoe(self, ctx: CustomContext, member: discord.Member) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("You must challenge another human member!")

        view = TicTacToeView(ctx.author, member)
        embed = discord.Embed(
            title="⚔️ Tic-Tac-Toe Match Started",
            description=f"> **{ctx.author.mention}** (❌) vs **{member.mention}** (⭕)\n> First Turn: **{ctx.author.mention}**",
            color=AIZEN_PURPLE
        )
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="connect4", aliases=["c4"], description="Challenge a member to a 7x6 Connect 4 match.")
    async def connect4(self, ctx: CustomContext, member: discord.Member) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("You must challenge another human member!")

        view = Connect4View(ctx.author, member)
        embed = discord.Embed(
            title=f"🔴 Connect 4 • Turn: {ctx.author.display_name} (🔴)",
            description=view._render_board(),
            color=AIZEN_PURPLE
        )
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="duel", description="Engage in a turn-based combat duel against another member.")
    async def duel(self, ctx: CustomContext, member: discord.Member, bet: int = 0) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("Invalid duel opponent!")

        guild_id = ctx.guild.id if ctx.guild else 0
        if bet > 0:
            p1 = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
            p2 = await self.eco.get_or_create_profile(guild_id, member.id)
            if p1.get("balance", 0) < bet or p2.get("balance", 0) < bet:
                return await ctx.send("Both duelists must have enough wallet balance for the wager!")

        # Roll simulated high-stakes turn battle
        hp1, hp2 = 100, 100
        rounds = 0
        combat_log = []

        while hp1 > 0 and hp2 > 0 and rounds < 10:
            rounds += 1
            dmg1 = random.randint(15, 35)
            hp2 -= dmg1
            combat_log.append(f"⚔️ **{ctx.author.display_name}** strikes for **{dmg1} DMG**! ({max(0, hp2)} HP remaining)")
            if hp2 <= 0: break

            dmg2 = random.randint(15, 35)
            hp1 -= dmg2
            combat_log.append(f"🛡️ **{member.display_name}** counters for **{dmg2} DMG**! ({max(0, hp1)} HP remaining)")

        winner = ctx.author if hp1 > 0 else member
        loser = member if winner == ctx.author else ctx.author

        if bet > 0:
            await self.eco.update_balance(guild_id, winner.id, wallet_delta=bet, tx_type="duel_win", metadata="Duel winner")
            await self.eco.update_balance(guild_id, loser.id, wallet_delta=-bet, tx_type="duel_loss", metadata="Duel loser")
            bounty_str = f"\n> 💰 Wager Payout: **+{bet:,}** transferred to {winner.mention}!"
        else:
            bounty_str = ""

        embed = discord.Embed(
            title=f"⚔️ Duel Results: {winner.display_name} Triumphs!",
            description="\n".join(combat_log[-4:]) + bounty_str,
            color=0x22C55E
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="reaction", description="Test your reaction speed against a randomized timer.")
    async def reaction(self, ctx: CustomContext) -> None:
        msg = await ctx.send("⚡ **Get ready… Press the button as fast as possible when it turns GREEN!**")
        delay = random.uniform(2.5, 6.0)
        await asyncio.sleep(delay)

        start_time = time.perf_counter()
        view = discord.ui.View(timeout=15)
        btn = discord.ui.Button(label="CLICK NOW! 🎯", style=discord.ButtonStyle.success)

        async def _click(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("This test is not for you!", ephemeral=True)
            elapsed = round((time.perf_counter() - start_time) * 1000)
            btn.disabled = True
            view.stop()
            await interaction.response.edit_message(
                content=f"⚡ **Incredible Reflexes!** Reaction time: **{elapsed} ms** ({ctx.author.mention})",
                view=view
            )

        btn.callback = _click
        view.add_item(btn)
        await msg.edit(content="🟢 **CLICK NOW!**", view=view)

    @commands.hybrid_command(name="fasttype", description="Test your typing speed (WPM) against an anime quote.")
    async def fasttype(self, ctx: CustomContext) -> None:
        sentences = [
            "Fear is necessary for evolution. The fear that one could be extinguished at any moment.",
            "Admiration is the furthest thing from understanding.",
            "No one stands on the heavens from the beginning.",
            "Change is inevitable in the face of absolute spiritual pressure.",
        ]
        target = random.choice(sentences)
        await ctx.send(f"⌨️ **Type this exact sentence below:**\n>>> **{target}**")
        start_t = time.perf_counter()

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            user_msg = await self.bot.wait_for("message", timeout=30, check=check)
            if user_msg.content.strip().lower() == target.lower():
                elapsed = max(1.0, time.perf_counter() - start_t)
                words = len(target.split())
                wpm = round((words / elapsed) * 60)
                await ctx.send(f"🏁 **Flawless Typing!** Completed in **{elapsed:.2f}s** with a speed of **{wpm} WPM**!")
            else:
                await ctx.send("❌ Typo detected! Accuracy is vital.")
        except asyncio.TimeoutError:
            await ctx.send("⏳ Time's up! Speed typing expired.")

    @commands.hybrid_command(name="trivia", description="Answer a multi-choice anime & general trivia question.")
    async def trivia(self, ctx: CustomContext) -> None:
        questions = [
            ("What is Sosuke Aizen's Zanpakuto name?", "Kyoka Suigetsu", ["Senbonzakura", "Zangetsu", "Wabisuke"]),
            ("How many Dragon Balls are required to summon Shenron?", "7", ["6", "8", "5"]),
            ("In Naruto, who taught the Rasengan to Jiraiya?", "Minato Namikaze", ["Hiruzen", "Tobirama", "Kakashi"]),
            ("What division did Aizen originally captain in the Gotei 13?", "Squad 5", ["Squad 4", "Squad 6", "Squad 3"]),
        ]
        q, correct, wrong = random.choice(questions)
        all_options = wrong + [correct]
        random.shuffle(all_options)

        view = discord.ui.View(timeout=30)
        for opt in all_options:
            btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.secondary)
            async def _cb(interaction: discord.Interaction, selected=opt):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your trivia!", ephemeral=True)
                for child in view.children: child.disabled = True
                if selected == correct:
                    await interaction.response.edit_message(content=f"✅ **Correct!** The answer was **{correct}**.", view=view)
                else:
                    await interaction.response.edit_message(content=f"❌ **Incorrect!** The correct answer was **{correct}**.", view=view)
                view.stop()
            btn.callback = _cb
            view.add_item(btn)

        await ctx.send(f"🧠 **Trivia Challenge:** {q}", view=view)

    @commands.hybrid_command(name="hangman", description="Play interactive word hangman with letter guesses.")
    async def hangman(self, ctx: CustomContext) -> None:
        words = ["HOLLOW", "ZANPAKUTO", "BANKAI", "BLEACH", "AIZEN", "SOUL", "ESPADA", "HUECO"]
        target = random.choice(words)
        guessed = set()
        lives = 6

        await ctx.send(f"🪢 **Hangman Started!** Word length: `{len(target)}` letters. Type single letters to guess (Lives: **{lives}**).")

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and len(m.content.strip()) == 1

        while lives > 0:
            display = " ".join([c if c in guessed else "_" for c in target])
            if all(c in guessed for c in target):
                return await ctx.send(f"🎉 **You Escaped the Noose!** Word was: **{target}**!")

            try:
                m = await self.bot.wait_for("message", timeout=30, check=check)
                letter = m.content.strip().upper()
                if letter in guessed:
                    await ctx.send(f"Already guessed `{letter}`! Word: `{display}`")
                    continue
                guessed.add(letter)
                if letter in target:
                    new_disp = " ".join([c if c in guessed else "_" for c in target])
                    await ctx.send(f"✅ Hit `{letter}`! Word: `{new_disp}` (Lives: {lives})")
                else:
                    lives -= 1
                    await ctx.send(f"❌ Miss `{letter}`! Lives remaining: **{lives}**")
            except asyncio.TimeoutError:
                return await ctx.send(f"⏳ Hangman timed out. Word was: **{target}**.")

        await ctx.send(f"💀 **Game Over!** You ran out of lives. Word was **{target}**.")

    @commands.hybrid_command(name="riddle", description="Solve a challenging riddle with hint button.")
    async def riddle(self, ctx: CustomContext) -> None:
        riddles = [
            ("I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", "An echo", "Think sound reflection"),
            ("What can travel all around the world while remaining in a corner?", "A postage stamp", "Found on envelopes"),
            ("The more of this there is, the less you see. What is it?", "Darkness", "Think light absence"),
        ]
        q, ans, hint = random.choice(riddles)
        view = discord.ui.View(timeout=60)
        btn_hint = discord.ui.Button(label="Hint 💡", style=discord.ButtonStyle.secondary)
        btn_ans = discord.ui.Button(label="Reveal Answer 👁️", style=discord.ButtonStyle.primary)

        async def _h(interaction: discord.Interaction):
            await interaction.response.send_message(f"💡 **Hint:** {hint}", ephemeral=True)

        async def _a(interaction: discord.Interaction):
            await interaction.response.send_message(f"👁️ **Answer:** {ans}", ephemeral=True)

        btn_hint.callback = _h
        btn_ans.callback = _a
        view.add_item(btn_hint)
        view.add_item(btn_ans)

        embed = discord.Embed(
            title="🧩 Aizen's Enigma & Riddle",
            description=f"> *“{q}”*",
            color=AIZEN_PURPLE
        )
        await ctx.send(embed=embed, view=view)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(MultiplayerGames(bot))
