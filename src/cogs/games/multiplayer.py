"""
KYOKA 3.0 — Multiplayer Games, Turn-Based Challenges & Puzzles Cog.
Commands:
?tictactoe @user, ?connect4 @user, ?duel @user, ?reactionspeed, ?fasttype, ?trivia,
?hangman, ?riddle, ?wordle, ?2048, ?battleship @user, ?minesweeper, ?memory,
?rps @user, ?russianroulette, ?unscramble, ?quiz
"""

from __future__ import annotations

import asyncio
import copy
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


# ─── 1. TIC TAC TOE ─────────────────────────────────────────────────────────

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
                    color=EMBED_GREEN
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
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for p1, p2, p3 in lines:
            if b[p1] != 0 and b[p1] == b[p2] == b[p3]:
                return b[p1]
        return None


# ─── 2. CONNECT 4 ───────────────────────────────────────────────────────────

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
                    color=EMBED_GREEN
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
            nr, nc = r + dr, c + dc
            while 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == piece:
                count += 1
                nr += dr
                nc += dc
            nr, nc = r - dr, c - dc
            while 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == piece:
                count += 1
                nr -= dr
                nc -= dc
            if count >= 4:
                return True
        return False


# ─── 3. 2048 GAME ───────────────────────────────────────────────────────────

class Game2048View(discord.ui.View):
    """Interactive 4x4 sliding 2048 tile puzzle."""

    def __init__(self, cog: MultiplayerGames, ctx: CustomContext):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.board = [[0] * 4 for _ in range(4)]
        self.score = 0
        self._spawn_tile()
        self._spawn_tile()

    def _spawn_tile(self) -> None:
        empty = [(r, c) for r in range(4) for c in range(4) if self.board[r][c] == 0]
        if empty:
            r, c = random.choice(empty)
            self.board[r][c] = 4 if random.random() < 0.1 else 2

    def render_board(self) -> str:
        tile_map = {
            0: "⬛", 2: "2️⃣", 4: "4️⃣", 8: "8️⃣", 16: "🔟",
            32: "🟨", 64: "🟧", 128: "🟥", 256: "🟪", 512: "🟦",
            1024: "⭐", 2048: "👑"
        }
        lines = []
        for row in self.board:
            row_str = " ".join(f"`{val:>4}`" if val != 0 else "`   .`" for val in row)
            lines.append(row_str)
        return "\n".join(lines)

    def _slide_left(self, row: list[int]) -> tuple[list[int], int]:
        non_zero = [v for v in row if v != 0]
        merged = []
        skip = False
        score_gain = 0
        for i in range(len(non_zero)):
            if skip:
                skip = False
                continue
            if i + 1 < len(non_zero) and non_zero[i] == non_zero[i + 1]:
                val = non_zero[i] * 2
                merged.append(val)
                score_gain += val
                skip = True
            else:
                merged.append(non_zero[i])
        merged.extend([0] * (4 - len(merged)))
        return merged, score_gain

    def _move(self, direction: str) -> bool:
        original = [row[:] for row in self.board]
        total_gain = 0

        if direction == "left":
            for r in range(4):
                self.board[r], gain = self._slide_left(self.board[r])
                total_gain += gain
        elif direction == "right":
            for r in range(4):
                rev, gain = self._slide_left(self.board[r][::-1])
                self.board[r] = rev[::-1]
                total_gain += gain
        elif direction == "up":
            for c in range(4):
                col = [self.board[r][c] for r in range(4)]
                new_col, gain = self._slide_left(col)
                total_gain += gain
                for r in range(4): self.board[r][c] = new_col[r]
        elif direction == "down":
            for c in range(4):
                col = [self.board[r][c] for r in range(4)][::-1]
                new_col, gain = self._slide_left(col)
                total_gain += gain
                new_col = new_col[::-1]
                for r in range(4): self.board[r][c] = new_col[r]

        self.score += total_gain
        changed = (self.board != original)
        if changed:
            self._spawn_tile()
        return changed

    def build_embed(self) -> discord.Embed:
        highest = max(max(row) for row in self.board)
        embed = discord.Embed(
            title="🎮 2048 Puzzle • Tile Sliding",
            description=f"> Score: **{self.score:,}** • Highest Tile: **{highest}**\n\n{self.render_board()}",
            color=AIZEN_PURPLE,
        )
        return embed

    @discord.ui.button(label="⬆️", style=discord.ButtonStyle.primary, row=0)
    async def btn_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_move(interaction, "up")

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary, row=1)
    async def btn_left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_move(interaction, "left")

    @discord.ui.button(label="⬇️", style=discord.ButtonStyle.primary, row=1)
    async def btn_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_move(interaction, "down")

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary, row=1)
    async def btn_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_move(interaction, "right")

    @discord.ui.button(label="🛑 End Game", style=discord.ButtonStyle.danger, row=0)
    async def btn_quit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.stop()
        for c in self.children: c.disabled = True
        reward = max(10, int(self.score * 0.1))
        guild_id = self.ctx.guild.id if self.ctx.guild else 0
        await self.cog.eco.update_balance(guild_id, self.ctx.author.id, wallet_delta=reward, tx_type="2048", metadata=f"Score {self.score}")
        embed = discord.Embed(
            title="🛑 2048 Session Ended",
            description=f"> Final Score: **{self.score:,}**\n> 💰 Earned **+{reward:,}** Kyoka Coins!",
            color=EMBED_GREEN,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _handle_move(self, interaction: discord.Interaction, dir_str: str):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self._move(dir_str)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ─── 4. MEMORY MATCH PUZZLE ─────────────────────────────────────────────────

class MemoryMatchView(discord.ui.View):
    """4x4 card pairing memory game."""

    def __init__(self, cog: MultiplayerGames, ctx: CustomContext):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        pool = ["🍎", "🍌", "🍇", "🍓", "🍒", "🍍", "🥝", "🍉"] * 2
        random.shuffle(pool)
        self.cards = pool
        self.revealed = [False] * 16
        self.first_pick: Optional[int] = None
        self.matches = 0
        self.turns = 0

        for i in range(16):
            btn = discord.ui.Button(label="❓", style=discord.ButtonStyle.secondary, row=i // 4)
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("Not your memory game!", ephemeral=True)
            if self.revealed[idx]:
                return await interaction.response.defer()

            btn = self.children[idx]

            if self.first_pick is None:
                # First card flipped
                self.first_pick = idx
                btn.label = self.cards[idx]
                btn.style = discord.ButtonStyle.primary
                await interaction.response.edit_message(view=self)
            else:
                if self.first_pick == idx:
                    return await interaction.response.defer()

                prev_idx = self.first_pick
                self.first_pick = None
                self.turns += 1

                btn.label = self.cards[idx]

                if self.cards[prev_idx] == self.cards[idx]:
                    # Match!
                    self.revealed[prev_idx] = True
                    self.revealed[idx] = True
                    self.children[prev_idx].style = discord.ButtonStyle.success
                    self.children[prev_idx].disabled = True
                    btn.style = discord.ButtonStyle.success
                    btn.disabled = True
                    self.matches += 1

                    if self.matches == 8:
                        self.stop()
                        reward = max(100, 2000 - (self.turns * 80))
                        guild_id = self.ctx.guild.id if self.ctx.guild else 0
                        await self.cog.eco.update_balance(guild_id, self.ctx.author.id, wallet_delta=reward, tx_type="memory", metadata="Memory win")
                        embed = discord.Embed(
                            title="🎉 Memory Match Complete!",
                            description=f"> All 8 pairs matched in **{self.turns} turns**!\n> Won **+{reward:,}** Kyoka Coins!",
                            color=EMBED_GREEN,
                        )
                        return await interaction.response.edit_message(embed=embed, view=self)

                    await interaction.response.edit_message(view=self)
                else:
                    # Mismatch -> show card briefly then reset
                    btn.style = discord.ButtonStyle.danger
                    self.children[prev_idx].style = discord.ButtonStyle.danger
                    await interaction.response.edit_message(view=self)
                    await asyncio.sleep(1.0)
                    btn.label = "❓"
                    btn.style = discord.ButtonStyle.secondary
                    self.children[prev_idx].label = "❓"
                    self.children[prev_idx].style = discord.ButtonStyle.secondary
                    try:
                        await interaction.message.edit(view=self)
                    except Exception:
                        pass

        return _callback


# ─── 5. MULTIPLAYER RPS ─────────────────────────────────────────────────────

class MultiplayerRPSView(discord.ui.View):
    """PVP Rock Paper Scissors with simultaneous button selection."""

    def __init__(self, cog: MultiplayerGames, p1: discord.Member, p2: discord.Member, bet: int = 0):
        super().__init__(timeout=60)
        self.cog = cog
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.choices: dict[int, str] = {}

    @discord.ui.button(label="Rock 🪨", style=discord.ButtonStyle.primary)
    async def btn_rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._record_choice(interaction, "rock")

    @discord.ui.button(label="Paper 📄", style=discord.ButtonStyle.primary)
    async def btn_paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._record_choice(interaction, "paper")

    @discord.ui.button(label="Scissors ✂️", style=discord.ButtonStyle.primary)
    async def btn_scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._record_choice(interaction, "scissors")

    async def _record_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id not in (self.p1.id, self.p2.id):
            return await interaction.response.send_message("You are not part of this duel!", ephemeral=True)
        if interaction.user.id in self.choices:
            return await interaction.response.send_message("You already locked in your choice!", ephemeral=True)

        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(f"Locked in **{choice.title()}**!", ephemeral=True)

        if len(self.choices) == 2:
            self.stop()
            for c in self.children: c.disabled = True
            c1 = self.choices[self.p1.id]
            c2 = self.choices[self.p2.id]

            if c1 == c2:
                res = f"🤝 **DRAW!** Both chose **{c1.title()}** • Wagers returned."
                color = AIZEN_PURPLE
            elif (c1, c2) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
                winner = self.p1
                loser = self.p2
                res = f"🏆 **{self.p1.mention} WINS!** ({c1.title()} beats {c2.title()})"
                color = EMBED_GREEN
            else:
                winner = self.p2
                loser = self.p1
                res = f"🏆 **{self.p2.mention} WINS!** ({c2.title()} beats {c1.title()})"
                color = EMBED_GREEN

            guild_id = interaction.guild_id or 0
            if self.bet > 0 and c1 != c2:
                await self.cog.eco.update_balance(guild_id, winner.id, wallet_delta=self.bet, tx_type="rps_win", metadata="RPS winner")
                await self.cog.eco.update_balance(guild_id, loser.id, wallet_delta=-self.bet, tx_type="rps_loss", metadata="RPS loser")
                res += f"\n> 💰 Wager Payout: **+{self.bet:,}** transferred to {winner.mention}!"

            embed = discord.Embed(
                title="⚔️ Rock-Paper-Scissors Duel Resolved!",
                description=f"> {self.p1.mention}: **{c1.title()}**\n> {self.p2.mention}: **{c2.title()}**\n\n{res}",
                color=color,
            )
            await interaction.message.edit(embed=embed, view=self)


# ─── 6. BATTLESHIP 5x5 ──────────────────────────────────────────────────────

class BattleshipView(discord.ui.View):
    """5x5 turn-based Battleship naval combat."""

    def __init__(self, cog: MultiplayerGames, p1: discord.Member, p2: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.p1 = p1
        self.p2 = p2
        self.turn = p1
        # Random 4 ships on 5x5
        self.ships_p1 = set(random.sample(range(25), 4))
        self.ships_p2 = set(random.sample(range(25), 4))
        self.hits_p1: set[int] = set()
        self.hits_p2: set[int] = set()
        self.misses_p1: set[int] = set()
        self.misses_p2: set[int] = set()

        for i in range(25):
            r = i // 5
            c = i % 5
            label = f"{chr(65 + r)}{c + 1}"
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=r)
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn.id:
                return await interaction.response.send_message("Not your turn to fire!", ephemeral=True)

            target_ships = self.ships_p2 if self.turn == self.p1 else self.ships_p1
            my_hits = self.hits_p1 if self.turn == self.p1 else self.hits_p2
            my_misses = self.misses_p1 if self.turn == self.p1 else self.misses_p2

            if idx in my_hits or idx in my_misses:
                return await interaction.response.send_message("Coordinates already targeted!", ephemeral=True)

            r = idx // 5
            c = idx % 5
            coord_str = f"{chr(65 + r)}{c + 1}"

            if idx in target_ships:
                my_hits.add(idx)
                status_msg = f"💥 **DIRECT HIT** at `{coord_str}` by {self.turn.mention}!"
            else:
                my_misses.add(idx)
                status_msg = f"🌊 **SPLASH (Miss)** at `{coord_str}` by {self.turn.mention}!"

            if len(my_hits) == len(target_ships):
                self.stop()
                for child in self.children: child.disabled = True
                embed = discord.Embed(
                    title=f"⚓ FLEET SUNK! {self.turn.display_name} TRIUMPHS!",
                    description=f"{status_msg}\n\n🏆 All enemy warships eliminated! Winner: **{self.turn.mention}**!",
                    color=EMBED_GREEN,
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            self.turn = self.p2 if self.turn == self.p1 else self.p1
            embed = discord.Embed(
                title="🚢 Battleship 5x5 Naval Warfare",
                description=(
                    f"{status_msg}\n\n"
                    f"> **{self.p1.display_name} Hits:** `{len(self.hits_p1)}/4`\n"
                    f"> **{self.p2.display_name} Hits:** `{len(self.hits_p2)}/4`\n\n"
                    f"> Turn: **{self.turn.mention}** • Pick coordinates to fire torpedo!"
                ),
                color=AIZEN_PURPLE,
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _callback


# ─── MULTIPLAYER GAMES COG ──────────────────────────────────────────────────

class MultiplayerGames(commands.Cog):
    """
    🎮 Kyoka Multiplayer & Puzzle Suite
    TicTacToe, Connect4, Chess, Battleship, RPG Duels, Wordle, Hangman, 2048,
    Memory Match, Rock-Paper-Scissors, Russian Roulette & Trivia.
    """

    category = "Multiplayer Games"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.eco = EconomyManager(bot.db)

    @commands.command(name="tictactoe", aliases=["ttt"], description="Challenge a member to Tic-Tac-Toe.")
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

    @commands.command(name="connect4", aliases=["c4"], description="Challenge a member to a 7x6 Connect 4 match.")
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

    @commands.command(name="duel", description="Engage in a turn-based combat duel against another member.")
    async def duel(self, ctx: CustomContext, member: discord.Member, bet: int = 0) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("Invalid duel opponent!")

        guild_id = ctx.guild.id if ctx.guild else 0
        if bet > 0:
            p1 = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
            p2 = await self.eco.get_or_create_profile(guild_id, member.id)
            if p1.get("balance", 0) < bet or p2.get("balance", 0) < bet:
                return await ctx.send("Both duelists must have enough wallet balance for the wager!")

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
            color=EMBED_GREEN
        )
        await ctx.send(embed=embed)

    @commands.command(name="reactionspeed", aliases=["reactiontime", "rspeed", "rtime"], description="Test your reaction speed against a randomized timer.")
    async def reaction_speed(self, ctx: CustomContext) -> None:
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

    @commands.command(name="fasttype", aliases=["typeracer"], description="Test your typing speed (WPM) against an anime quote.")
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

    @commands.command(name="trivia", description="Answer a multi-choice anime & general trivia question.")
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

    @commands.command(name="hangman", description="Play interactive word hangman with letter guesses.")
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

    @commands.command(name="riddle", description="Solve a challenging riddle with hint button.")
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

    # ─── NEW EXPANDED GAMES ──────────────────────────────────────────────────

    @commands.command(name="wordle", description="Play 5-letter Wordle puzzle with 6 attempts.")
    async def wordle(self, ctx: CustomContext) -> None:
        words = ["AIZEN", "BLEACH", "SOULS", "BANKAI", "BLADE", "MAGIC", "POWER", "SWORD", "TITAN", "NINJA", "GHOST", "FORCE", "HONOR", "FLAME", "LIGHT", "CROWN", "DREAM", "STORM", "BRAVE"]
        five_letter_words = [w for w in words if len(w) == 5]
        target = random.choice(five_letter_words)
        guesses: list[str] = []
        max_attempts = 6

        def render_grid() -> str:
            lines = []
            for g in guesses:
                res = []
                for i, char in enumerate(g):
                    if char == target[i]:
                        res.append(f"🟩 `{char}`")
                    elif char in target:
                        res.append(f"🟨 `{char}`")
                    else:
                        res.append(f"⬛ `{char}`")
                lines.append(" ".join(res))
            for _ in range(max_attempts - len(guesses)):
                lines.append("⬜ ⬜ ⬜ ⬜ ⬜")
            return "\n".join(lines)

        embed = discord.Embed(
            title="🟩 Kyoka Wordle Challenge",
            description=f"> Type 5-letter words in chat to guess!\n\n{render_grid()}",
            color=AIZEN_PURPLE,
        )
        msg = await ctx.send(embed=embed)

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and len(m.content.strip()) == 5 and m.content.strip().isalpha()

        while len(guesses) < max_attempts:
            try:
                user_msg = await self.bot.wait_for("message", timeout=60, check=check)
                guess = user_msg.content.strip().upper()
                guesses.append(guess)

                if guess == target:
                    embed.title = "🎉 Wordle Solved!"
                    embed.color = EMBED_GREEN
                    reward = (max_attempts - len(guesses) + 1) * 500
                    guild_id = ctx.guild.id if ctx.guild else 0
                    await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=reward, tx_type="wordle", metadata="Wordle win")
                    embed.description = f"> Word found in **{len(guesses)}/6 attempts**!\n> 💰 Prize: **+{reward:,}** Kyoka Coins!\n\n{render_grid()}"
                    return await msg.edit(embed=embed)

                embed.description = f"> Attempts: **{len(guesses)}/6**\n\n{render_grid()}"
                await msg.edit(embed=embed)
            except asyncio.TimeoutError:
                return await ctx.send(f"⏳ Wordle timed out! The secret word was **{target}**.")

        await ctx.send(f"💀 Out of attempts! The secret word was **{target}**.")

    @commands.command(name="2048", description="Play interactive 4x4 sliding 2048 puzzle.")
    async def game_2048(self, ctx: CustomContext) -> None:
        view = Game2048View(self, ctx)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="battleship", aliases=["bs"], description="Challenge a member to 5x5 naval Battleship.")
    async def battleship(self, ctx: CustomContext, member: discord.Member) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("You must challenge another human member to Battleship!")

        view = BattleshipView(self, ctx.author, member)
        embed = discord.Embed(
            title="⚓ Battleship 5x5 Fleet Warfare Started!",
            description=(
                f"> **{ctx.author.mention}** vs **{member.mention}**\n"
                f"> Each admiral commands **4 hidden warships** on a 5x5 ocean grid (A1 to E5).\n"
                f"> First Turn: **{ctx.author.mention}** • Pick coordinates to fire!"
            ),
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="memory", aliases=["mem"], description="Play 4x4 card pairing memory game.")
    async def memory_game(self, ctx: CustomContext) -> None:
        view = MemoryMatchView(self, ctx)
        embed = discord.Embed(
            title="🧠 Memory Match 4x4 • Find All Pairs",
            description="> Flip 2 cards per turn. Match all 8 pairs to earn coin rewards!",
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="rps", description="Play Rock-Paper-Scissors against Aizen or challenge a member.")
    async def rps(self, ctx: CustomContext, target_or_choice: Optional[str] = None, bet: int = 0) -> None:
        options = ["rock", "paper", "scissors"]

        # 1. Direct solo play vs Aizen if string choice passed (e.g. ?rps rock)
        if target_or_choice and target_or_choice.lower() in options:
            player_choice = target_or_choice.lower()
            ai_choice = random.choice(options)
            if player_choice == ai_choice:
                res = "🤝 Draw! The outcome was an illusion."
            elif (player_choice, ai_choice) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
                res = "🎉 You win this round!"
            else:
                res = "💀 Aizen wins this round."
            return await ctx.send(f"✊ You chose **{player_choice}**; Aizen chose **{ai_choice}**.\n{res}")

        # 2. Member PVP challenge if member passed (e.g. ?rps @member 100)
        member: Optional[discord.Member] = None
        if target_or_choice and ctx.guild:
            try:
                member = await commands.MemberConverter().convert(ctx, target_or_choice)
            except Exception:
                member = None

        if member is not None and not member.bot and member.id != ctx.author.id:
            # Multiplayer PVP duel
            guild_id = ctx.guild.id if ctx.guild else 0
            if bet > 0:
                p1 = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
                p2 = await self.eco.get_or_create_profile(guild_id, member.id)
                if p1.get("balance", 0) < bet or p2.get("balance", 0) < bet:
                    return await ctx.send("Both players must have enough coins for the wager!")

            view = MultiplayerRPSView(self, ctx.author, member, bet=bet)
            embed = discord.Embed(
                title="⚔️ Rock-Paper-Scissors Duel Initiated",
                description=f"> {ctx.author.mention} vs {member.mention}\n> Both duelists: click a secret button below to lock in your move!",
                color=AIZEN_PURPLE,
            )
            return await ctx.send(embed=embed, view=view)

        # 3. Interactive buttons vs Aizen if no valid member passed
        view = discord.ui.View(timeout=30)
        for opt in options:
            btn = discord.ui.Button(label=opt.title(), style=discord.ButtonStyle.primary)
            async def _cb(interaction: discord.Interaction, player_choice=opt):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                ai_choice = random.choice(options)
                if player_choice == ai_choice:
                    res = "🤝 Draw! The outcome was an illusion."
                    col = AIZEN_PURPLE
                elif (player_choice, ai_choice) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
                    res = "🎉 You win this round!"
                    col = EMBED_GREEN
                else:
                    res = "💀 Aizen wins this round."
                    col = EMBED_RED
                for c in view.children: c.disabled = True
                view.stop()
                await interaction.response.edit_message(
                    content=f"✊ You chose **{player_choice}**; Aizen chose **{ai_choice}**.\n{res}",
                    view=view
                )
            btn.callback = _cb
            view.add_item(btn)

        await ctx.send("Choose your move against Aizen:", view=view)

    @commands.command(name="russianroulette", aliases=["roulettegame", "revolver", "rroulette"], description="Spin the 6-chamber cylinder and pull the trigger.")
    async def russian_roulette(self, ctx: CustomContext, bet: int = 100) -> None:
        if bet <= 0: return await ctx.send("Bet must be positive!")
        guild_id = ctx.guild.id if ctx.guild else 0
        prof = await self.eco.get_or_create_profile(guild_id, ctx.author.id)
        if prof.get("balance", 0) < bet: return await ctx.send("Insufficient funds in your wallet!")

        bullet_chamber = random.randint(1, 6)
        current_chamber = 1
        current_mult = 1.0

        view = discord.ui.View(timeout=60)
        btn_pull = discord.ui.Button(label="Pull Trigger 🔫", style=discord.ButtonStyle.danger)
        btn_walk = discord.ui.Button(label="Walk Away 💵", style=discord.ButtonStyle.success)

        async def _pull(interaction: discord.Interaction):
            nonlocal current_chamber, current_mult
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Not your revolver!", ephemeral=True)

            if current_chamber == bullet_chamber:
                view.stop()
                for c in view.children: c.disabled = True
                await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=-bet, tx_type="roulette_loss", metadata="Shot in roulette")
                embed = discord.Embed(
                    title="💥 *BANG!*",
                    description=f"> Chamber #{current_chamber} was LOADED!\n> You lost **-{bet:,}** Kyoka Coins.",
                    color=EMBED_RED,
                )
                return await interaction.response.edit_message(embed=embed, view=view)

            # Survived!
            current_chamber += 1
            current_mult = round(current_mult * 1.5, 2)
            payout = int(bet * current_mult)
            embed = discord.Embed(
                title="*CLICK…* Safe! 💨",
                description=f"> Chamber was empty! Multiplier: **{current_mult:.2f}x** *(Value: {payout:,})*\n> Pull again or walk away with your winnings?",
                color=EMBED_GREEN,
            )
            await interaction.response.edit_message(embed=embed, view=view)

        async def _walk(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Not your revolver!", ephemeral=True)
            view.stop()
            for c in view.children: c.disabled = True
            profit = int(bet * (current_mult - 1.0))
            if profit > 0:
                await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=profit, tx_type="roulette_win", metadata="Survived roulette")
                embed = discord.Embed(
                    title="💵 Walked Away Alive!",
                    description=f"> Safely cashed out at **{current_mult:.2f}x**!\n> Won **+{profit:,}** Kyoka Coins!",
                    color=EMBED_GREEN,
                )
            else:
                embed = discord.Embed(title="🤝 Walked Away", description="> No rounds played.", color=AIZEN_PURPLE)
            await interaction.response.edit_message(embed=embed, view=view)

        btn_pull.callback = _pull
        btn_walk.callback = _walk
        view.add_item(btn_pull)
        view.add_item(btn_walk)

        embed = discord.Embed(
            title="🔫 Russian Roulette • 6 Chambers",
            description=f"> Bet: **{bet:,}**\n> 1 live bullet in the cylinder. Pull the trigger to multiply your coins!",
            color=AIZEN_PURPLE,
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="unscramble", aliases=["anagram"], description="Speed unscramble anime & gaming words.")
    async def unscramble(self, ctx: CustomContext) -> None:
        word_list = ["BANKAI", "BLEACH", "KYOKA", "SUIGETSU", "ESPADA", "SHINIGAMI", "ZANPAKUTO", "HUECO", "ICHIGO", "SOUSUKE"]
        target = random.choice(word_list)
        scrambled = list(target)
        random.shuffle(scrambled)
        scrambled_str = " ".join(scrambled)

        await ctx.send(f"🔤 **Unscramble this word:** `{scrambled_str}`\n> First member to type the correct word in chat wins 1,000 Coins! (30s timer)")

        def check(m: discord.Message) -> bool:
            return m.channel.id == ctx.channel.id and m.content.strip().upper() == target

        try:
            winner_msg = await self.bot.wait_for("message", timeout=30, check=check)
            guild_id = ctx.guild.id if ctx.guild else 0
            await self.eco.update_balance(guild_id, winner_msg.author.id, wallet_delta=1000, tx_type="unscramble", metadata="Unscramble win")
            await ctx.send(f"🏆 {winner_msg.author.mention} solved it first! The word was **{target}**! Won **+1,000** Coins!")
        except asyncio.TimeoutError:
            await ctx.send(f"⏳ Time's up! The word was **{target}**.")

    @commands.command(name="quiz", description="Interactive trivia quiz with category selection.")
    async def quiz(self, ctx: CustomContext) -> None:
        categories = {
            "anime": [
                ("What was Aizen's ultimate ambition?", "To overthrow the Soul King", ["To destroy Karakura Town", "To become Head Captain", "To become a Hollow"]),
                ("Who forged all Zanpakuto?", "Nimaiya Oetsu", ["Ichibe Hyosube", "Kisuke Urahara", "Senjumaru Shutara"]),
            ],
            "gaming": [
                ("What is the highest rank in League of Legends?", "Challenger", ["Grandmaster", "Master", "Diamond"]),
                ("In Minecraft, how many obsidian blocks are needed for a Nether Portal?", "10", ["8", "12", "14"]),
            ],
        }
        all_q = categories["anime"] + categories["gaming"]
        q, correct, wrong = random.choice(all_q)
        options = wrong + [correct]
        random.shuffle(options)

        view = discord.ui.View(timeout=30)
        for opt in options:
            btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.secondary)
            async def _cb(interaction: discord.Interaction, selected=opt):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your quiz!", ephemeral=True)
                for c in view.children: c.disabled = True
                view.stop()
                if selected == correct:
                    guild_id = ctx.guild.id if ctx.guild else 0
                    await self.eco.update_balance(guild_id, ctx.author.id, wallet_delta=500, tx_type="quiz_win", metadata="Quiz correct")
                    await interaction.response.edit_message(content=f"✅ **Correct!** The answer was **{correct}**! Won **+500** Coins!", view=view)
                else:
                    await interaction.response.edit_message(content=f"❌ **Incorrect!** The correct answer was **{correct}**.", view=view)
            btn.callback = _cb
            view.add_item(btn)

        await ctx.send(f"🧠 **Kyoka Quiz Tournament:**\n>>> **{q}**", view=view)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(MultiplayerGames(bot))
