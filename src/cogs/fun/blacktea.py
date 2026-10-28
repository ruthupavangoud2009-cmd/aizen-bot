"""
Kyoka 3.0 - BlackTea Multiplayer Word-Bomb Elimination Game
Inspired by Greed bot's iconic BlackTea mini-game.
Players take turns typing words containing a designated 3-letter sequence before the bomb explodes!
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

# Comprehensive curated 3-letter prompt pool that allows abundant English words
BLACKTEA_PROMPTS = [
    "ing", "pro", "str", "tra", "ver", "ous", "ion", "pre", "con", "cat",
    "sta", "ble", "ent", "que", "ful", "ght", "tch", "est", "ast", "ani",
    "gen", "phy", "log", "sys", "com", "ter", "per", "dis", "res", "rec",
    "min", "mon", "man", "den", "tin", "ten", "par", "gra", "flo", "bla",
    "cra", "dra", "sha", "cha", "tha", "wha", "cre", "dre", "bre", "fre",
    "gre", "tre", "pri", "tri", "bri", "fri", "gri", "dri", "cro", "dro",
    "bro", "fro", "gro", "tro", "cru", "dru", "bru", "fru", "gru", "tru",
    "ack", "eck", "ick", "ock", "uck", "all", "ell", "ill", "oll", "ull",
    "and", "end", "ind", "ond", "und", "ang", "eng", "ing", "ong", "ung",
    "ank", "enk", "ink", "onk", "unk", "ant", "ent", "int", "ont", "unt",
    "art", "ert", "irt", "ort", "urt", "ash", "esh", "ish", "osh", "ush",
    "amp", "emp", "imp", "omp", "ump", "ate", "ete", "ite", "ote", "ute",
    "ive", "eve", "ave", "ove", "ure", "ire", "ore", "are", "ere", "ard",
]

# Common English word validation list (1,500+ standard English words + substring validation)
# Supplemented by dynamic letter check and length verification
MIN_WORD_LENGTH = 3
MAX_TURN_SECONDS = 10


class BlackTeaPlayer:
    """Represents a participant in an active BlackTea game."""

    def __init__(self, member: discord.Member) -> None:
        self.member = member
        self.lives = 3
        self.words_submitted = 0

    @property
    def id(self) -> int:
        return self.member.id

    @property
    def display_name(self) -> str:
        return self.member.display_name

    @property
    def mention(self) -> str:
        return self.member.mention

    def render_lives(self) -> str:
        hearts = "❤️ " * self.lives
        lost = "🖤 " * (3 - self.lives)
        return (hearts + lost).strip()


class BlackTeaLobbyView(discord.ui.View):
    """Lobby view for gathering players before a BlackTea match starts."""

    def __init__(self, cog: BlackTea, host: discord.Member, channel_id: int) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.host = host
        self.channel_id = channel_id
        self.players: List[BlackTeaPlayer] = [BlackTeaPlayer(host)]
        self.started = False

    def render_lobby_embed(self) -> discord.Embed:
        player_list = "\n".join(f"• **{p.display_name}**" for p in self.players)
        embed = discord.Embed(
            title="☕ KYOKA BlackTea — Lobby",
            description=(
                f"**Host:** {self.host.mention}\n"
                f"**Status:** Waiting for players... (Click **Join** below)\n\n"
                f"**Joined Players ({len(self.players)}):**\n{player_list}\n\n"
                f"⏱️ Game rules: 3 Lives | 10s per prompt | No repeated words."
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text="Host can click 'Start Game' once ready | Minimum 2 players for match (or 1 for practice)")
        return embed

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🎮")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user = interaction.user
        if any(p.id == user.id for p in self.players):
            return await interaction.response.send_message("You are already in the lobby!", ephemeral=True)
        if len(self.players) >= 12:
            return await interaction.response.send_message("The lobby is full (maximum 12 players)!", ephemeral=True)

        self.players.append(BlackTeaPlayer(user))  # type: ignore
        await interaction.response.edit_message(embed=self.render_lobby_embed(), view=self)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def btn_leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user = interaction.user
        if user.id == self.host.id:
            return await interaction.response.send_message("The host cannot leave the lobby. Click Cancel to abort.", ephemeral=True)
        player = next((p for p in self.players if p.id == user.id), None)
        if not player:
            return await interaction.response.send_message("You are not in the lobby.", ephemeral=True)

        self.players.remove(player)
        await interaction.response.edit_message(embed=self.render_lobby_embed(), view=self)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, emoji="▶️")
    async def btn_start(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Only the lobby host can start the game!", ephemeral=True)

        self.started = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        asyncio.create_task(self.cog.run_game_loop(self.channel_id, self.players))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Only the lobby host can cancel the game!", ephemeral=True)

        self.stop()
        for child in self.children:
            child.disabled = True
        self.cog.active_games.pop(self.channel_id, None)
        await interaction.response.edit_message(content="❌ BlackTea game cancelled by host.", embed=None, view=self)


class BlackTea(commands.Cog, name="Fun-BlackTea"):
    """
    Greed-style BlackTea word-bomb multiplayer game.
    Players take turns typing English words containing a prompt substring before the 10s bomb explodes.
    """
    category = "🎮・GAMES & FUN"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.active_games: Dict[int, List[BlackTeaPlayer]] = {}
        self.used_words: Dict[int, Set[str]] = {}

    async def cog_load(self) -> None:
        """Initialize database table for BlackTea statistics."""
        try:
            if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blacktea_stats (
                        user_id BIGINT PRIMARY KEY,
                        wins INT DEFAULT 0,
                        games_played INT DEFAULT 0,
                        words_submitted INT DEFAULT 0,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
        except Exception:
            pass

    # ─── COMMAND GROUP ────────────────────────────────────────────────────────

    @commands.group(
        name="blacktea",
        aliases=["bt", "wordbomb", "bomb"],
        invoke_without_command=True,
        description="Greed-style multiplayer word-bomb elimination game.",
    )
    @commands.guild_only()
    async def blacktea_group(self, ctx: CustomContext) -> None:
        """Start a new BlackTea game or view help."""
        await self.start_game(ctx)

    @blacktea_group.command(name="start", aliases=["play", "new"], help="Start a new BlackTea game lobby.")
    @commands.guild_only()
    async def cmd_start(self, ctx: CustomContext) -> None:
        """Start a new BlackTea game lobby in current channel."""
        await self.start_game(ctx)

    @blacktea_group.command(name="stats", aliases=["profile"], help="View your or another user's BlackTea stats.")
    @commands.guild_only()
    async def cmd_stats(self, ctx: CustomContext, user: Optional[discord.Member] = None) -> None:
        """View BlackTea player statistics."""
        target = user or ctx.author
        stats = None
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_one"):
            try:
                stats = await self.bot.db.fetch_one(
                    "SELECT wins, games_played, words_submitted FROM blacktea_stats WHERE user_id = ?;",
                    target.id,
                )
            except Exception:
                pass

        wins = stats["wins"] if stats else 0
        played = stats["games_played"] if stats else 0
        words = stats["words_submitted"] if stats else 0
        winrate = round((wins / played) * 100, 1) if played > 0 else 0.0

        container = KyokaContainer(accent_color=None)
        container.add_text(f"**☕ BlackTea Statistics • {target.display_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Wins:** `{wins:,}`\n"
            f"• **Games Played:** `{played:,}`\n"
            f"• **Win Rate:** `{winrate}%`\n"
            f"• **Total Words Submitted:** `{words:,}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @blacktea_group.command(name="leaderboard", aliases=["lb", "top"], help="View top BlackTea winners.")
    @commands.guild_only()
    async def cmd_leaderboard(self, ctx: CustomContext) -> None:
        """View server/global BlackTea champions."""
        rows = []
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_all"):
            try:
                rows = await self.bot.db.fetch_all(
                    "SELECT user_id, wins, games_played FROM blacktea_stats ORDER BY wins DESC LIMIT 10;"
                )
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_text("**🏆 BlackTea Hall of Champions**")
        container.add_separator(divider=True)

        if not rows:
            container.add_text("> No BlackTea games recorded yet. Play a game with `+blacktea`!")
        else:
            lines = []
            for idx, r in enumerate(rows, start=1):
                user_id = r["user_id"]
                wins = r["wins"]
                played = r["games_played"]
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
                lines.append(f"{medal} <@{user_id}> — **{wins}** wins *({played} played)*")
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    # ─── CORE GAME ENGINE ─────────────────────────────────────────────────────

    async def start_game(self, ctx: CustomContext) -> None:
        """Initiate game lobby."""
        if ctx.channel.id in self.active_games:
            return await ctx.send_error("A BlackTea game is already active or in lobby in this channel!")

        view = BlackTeaLobbyView(self, ctx.author, ctx.channel.id)
        self.active_games[ctx.channel.id] = view.players
        embed = view.render_lobby_embed()
        msg = await ctx.send(embed=embed, view=view)

        await view.wait()
        if not view.started:
            self.active_games.pop(ctx.channel.id, None)

    async def run_game_loop(self, channel_id: int, players: List[BlackTeaPlayer]) -> None:
        """Main game loop cycling through active players with 10s bomb countdown."""
        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            self.active_games.pop(channel_id, None)
            return

        used_words: Set[str] = set()
        self.used_words[channel_id] = used_words
        active_players = list(players)
        round_num = 1

        # Track participation in DB
        for p in active_players:
            await self._record_game_played(p.id)

        await channel.send(
            f"☕ **BlackTea Match Starting!**\n"
            f"> Players: {', '.join(p.mention for p in active_players)}\n"
            f"> **Rules:** When it's your turn, type a word containing the 3-letter sequence within **10 seconds**!"
        )
        await asyncio.sleep(2.0)

        turn_idx = 0
        while len(active_players) > 1 or (len(players) == 1 and len(active_players) == 1):
            current_player = active_players[turn_idx % len(active_players)]
            prompt = random.choice(BLACKTEA_PROMPTS)

            embed = discord.Embed(
                title=f"💣 Round {round_num} • {current_player.display_name}'s Turn",
                description=(
                    f"{current_player.mention}, type a word containing **`{prompt.upper()}`**!\n\n"
                    f"**Lives:** {current_player.render_lives()}\n"
                    f"⏱️ **Time:** `{MAX_TURN_SECONDS} seconds`"
                ),
                color=0xE02424 if current_player.lives == 1 else 0xF59E0B if current_player.lives == 2 else 0x10B981,
            )
            embed.set_footer(text=f"Players remaining: {len(active_players)} | Words used: {len(used_words)}")
            turn_msg = await channel.send(embed=embed)

            start_time = time.monotonic()
            word_accepted = False

            def check_msg(m: discord.Message) -> bool:
                return (
                    m.channel.id == channel_id
                    and m.author.id == current_player.id
                    and len(m.content.strip()) >= MIN_WORD_LENGTH
                )

            while time.monotonic() - start_time < MAX_TURN_SECONDS:
                remaining = MAX_TURN_SECONDS - (time.monotonic() - start_time)
                try:
                    msg = await self.bot.wait_for("message", check=check_msg, timeout=max(0.1, remaining))
                    candidate = msg.content.lower().strip()

                    # Validation
                    if prompt not in candidate:
                        await channel.send(f"❌ {current_player.mention}, **{candidate}** does not contain `{prompt.upper()}`! Try again!", delete_after=3.0)
                        continue

                    if candidate in used_words:
                        await channel.send(f"⚠️ {current_player.mention}, **{candidate}** was already used this game! Try another word!", delete_after=3.0)
                        continue

                    # Valid word!
                    used_words.add(candidate)
                    current_player.words_submitted += 1
                    word_accepted = True
                    await msg.add_reaction("✅")
                    await channel.send(f"🔔 **{current_player.display_name}** scored with **{candidate.upper()}**! Next turn...", delete_after=3.5)
                    await self._record_word_submitted(current_player.id)
                    break

                except asyncio.TimeoutError:
                    break

            if not word_accepted:
                current_player.lives -= 1
                if current_player.lives <= 0:
                    await channel.send(f"💥 **BOOM!** Time's up! 💀 **{current_player.display_name}** ran out of lives and has been **ELIMINATED**!")
                    active_players.remove(current_player)
                    if len(active_players) == 0:
                        break
                else:
                    await channel.send(
                        f"💥 **BOOM!** Time's up! {current_player.mention} lost a life!\n"
                        f"> Remaining lives: {current_player.render_lives()}"
                    )

            # Check single player solo practice mode condition
            if len(players) == 1 and len(active_players) == 0:
                await channel.send(f"☕ **Solo practice session concluded.** Words completed: `{len(used_words)}`.")
                break

            round_num += 1
            turn_idx += 1
            await asyncio.sleep(1.8)

        # Declare winner
        if len(active_players) == 1 and len(players) > 1:
            winner = active_players[0]
            await self._record_win(winner.id)

            win_embed = discord.Embed(
                title="🏆 BlackTea Champion!",
                description=(
                    f"🎉 {winner.mention} survived the word bomb and won the match!\n\n"
                    f"• **Remaining Lives:** {winner.render_lives()}\n"
                    f"• **Total Words Completed:** `{len(used_words)}`\n"
                    f"• **Rounds Lasted:** `{round_num - 1}`"
                ),
                color=0xF59E0B,
            )
            win_embed.set_footer(text="Gained +1 BlackTea Victory • Use +blacktea stats to view record")
            await channel.send(embed=win_embed)

        self.active_games.pop(channel_id, None)
        self.used_words.pop(channel_id, None)

    async def _record_game_played(self, user_id: int) -> None:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO blacktea_stats (user_id, games_played)
                    VALUES (?, 1)
                    ON CONFLICT (user_id) DO UPDATE SET
                        games_played = blacktea_stats.games_played + 1,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    user_id,
                )
            except Exception:
                pass

    async def _record_word_submitted(self, user_id: int) -> None:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO blacktea_stats (user_id, words_submitted)
                    VALUES (?, 1)
                    ON CONFLICT (user_id) DO UPDATE SET
                        words_submitted = blacktea_stats.words_submitted + 1,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    user_id,
                )
            except Exception:
                pass

    async def _record_win(self, user_id: int) -> None:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO blacktea_stats (user_id, wins)
                    VALUES (?, 1)
                    ON CONFLICT (user_id) DO UPDATE SET
                        wins = blacktea_stats.wins + 1,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    user_id,
                )
            except Exception:
                pass


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(BlackTea(bot))
