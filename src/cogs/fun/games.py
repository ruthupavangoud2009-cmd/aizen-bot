from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Games")
PURPLE = 0x7C3AED
CYAN = 0x06B6D4
GREEN = 0x10B981


class ReactionRaceView(discord.ui.View):
    """The first member to click after the GO signal wins."""

    def __init__(self) -> None:
        super().__init__(timeout=30)
        self.started = False
        self.winner_id: int | None = None
        self.disqualified: set[int] = set()
        self.message: discord.Message | None = None
        self.gif_manager = GIFManager()

    @discord.ui.button(label="Wait for GO…", style=discord.ButtonStyle.secondary)
    async def race_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.started:
            self.disqualified.add(interaction.user.id)
            await interaction.response.send_message("Too early! Wait for **GO!**", ephemeral=True)
            return
        if interaction.user.id in self.disqualified:
            await interaction.response.send_message("You clicked early, so you're out of this race.", ephemeral=True)
            return
        if self.winner_id is not None:
            await interaction.response.send_message("This race already has a winner.", ephemeral=True)
            return

        self.winner_id = interaction.user.id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        embed = discord.Embed(
            title="🏁 Reaction Race Winner!",
            description=f"{interaction.user.mention} had the fastest reaction!",
            color=GREEN,
        )
        gif_url = await self.gif_manager.get_action_gif("celebrate")
        if gif_url:
            embed.set_image(url=gif_url)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(content="⌛ Reaction race ended with no winner.", view=self)
        except discord.HTTPException:
            logger.exception("Could not disable expired reaction-race controls")


class HideAndSeekView(discord.ui.View):
    """Members race to find the one hidden item among a grid of buttons."""

    def __init__(self, hidden_index: int) -> None:
        super().__init__(timeout=60)
        self.hidden_index = hidden_index
        self.guessed_users: set[int] = set()
        self.message: discord.Message | None = None
        self.gif_manager = GIFManager()

        for index in range(9):
            button = discord.ui.Button(label="🔎 Search", style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(index)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id in self.guessed_users:
                await interaction.response.send_message("You already searched this round.", ephemeral=True)
                return
            self.guessed_users.add(interaction.user.id)

            if index == self.hidden_index:
                for item in self.children:
                    if isinstance(item, discord.ui.Button):
                        item.disabled = True
                        item.label = "🎁 Found!" if item is self.children[index] else "🔒"
                embed = discord.Embed(
                    title="🏆 Scavenger Hunt Winner!",
                    description=f"{interaction.user.mention} found the hidden treasure!",
                    color=GREEN,
                )
                gif_url = await self.gif_manager.get_action_gif("celebrate")
                if gif_url:
                    embed.set_image(url=gif_url)
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()
                return

            button = self.children[index]
            if isinstance(button, discord.ui.Button):
                button.label = "❌ Empty"
                button.disabled = True
                button.style = discord.ButtonStyle.danger
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("Nothing there—keep searching!", ephemeral=True)

        return callback

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(content="⌛ The scavenger hunt ended before anyone found the treasure.", view=self)
        except discord.HTTPException:
            logger.exception("Could not disable expired scavenger-hunt controls")


class TwoTruthsView(discord.ui.View):
    """Collect anonymous guesses, then let the host reveal which statement was false."""

    def __init__(self, author_id: int, statements: list[str], lie_index: int) -> None:
        super().__init__(timeout=120)
        self.author_id = author_id
        self.statements = statements
        self.lie_index = lie_index
        self.votes: dict[int, int] = {}
        self.message: discord.Message | None = None
        self.gif_manager = GIFManager()

        for index in range(3):
            button = discord.ui.Button(label=f"Statement {index + 1}", style=discord.ButtonStyle.secondary)
            button.callback = self._make_vote_callback(index)
            self.add_item(button)

        reveal = discord.ui.Button(label="Reveal the lie", style=discord.ButtonStyle.primary)
        reveal.callback = self._reveal_callback
        self.add_item(reveal)

    def _make_vote_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            self.votes[interaction.user.id] = index
            await interaction.response.send_message(
                f"Your vote for statement {index + 1} is recorded.", ephemeral=True
            )

        return callback

    async def _result_embed(self) -> discord.Embed:
        correct_voters = [user_id for user_id, vote in self.votes.items() if vote == self.lie_index]
        lines = [
            f"**{index + 1}.** {discord.utils.escape_markdown(statement)}"
            for index, statement in enumerate(self.statements)
        ]
        result = f"The lie was **statement {self.lie_index + 1}**."
        if correct_voters:
            result += "\n\n**Correct guesses:** " + ", ".join(f"<@{user_id}>" for user_id in correct_voters)
        else:
            result += "\n\nNo one guessed the lie correctly this time."

        embed = discord.Embed(
            title="🕵️ Two Truths and a Lie — Reveal",
            description="\n".join(lines) + "\n\n" + result,
            color=GREEN if correct_voters else PURPLE,
        )
        if correct_voters:
            gif_url = await self.gif_manager.get_action_gif("celebrate")
            if gif_url:
                embed.set_image(url=gif_url)
        return embed

    async def _reveal_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the game host can reveal the answer.", ephemeral=True)
            return
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(embed=await self._result_embed(), view=self)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(embed=await self._result_embed(), view=self)
        except discord.HTTPException:
            logger.exception("Could not reveal expired Two Truths and a Lie round")


# ─── TRUTH OR DARE INTERACTIVE VIEW ──────────────────────────────────────────

class TruthOrDareView(discord.ui.View):
    """Interactive Truth or Dare view."""

    TRUTHS = [
        "What is the most embarrassing anime opening or pop song you secretly love?",
        "If you could have one anime power in real life, what would it be and why?",
        "What is the most ridiculous excuse you've ever used to avoid hanging out?",
        "Have you ever cried during an anime episode? If so, which one?",
        "What is the weirdest server message you've ever sent by mistake?",
        "If you were trapped in an anime world for a week, which one would you pick?",
        "Who was your very first fictional anime crush?",
    ]

    DARES = [
        "Change your server nickname to 'NPC #42' for the next 10 minutes.",
        "Send your most recently saved anime meme in the chat.",
        "Type your next 3 messages speaking only like an eccentric anime villain.",
        "Post a completely serious rating of your favorite snack out of 10 in general chat.",
        "Describe your day using only 4 emojis without any words.",
        "Give a dramatic 2-sentence speech praising the bot owner.",
    ]

    def __init__(self, author: discord.Member, prefix: str = "+") -> None:
        super().__init__(timeout=60.0)
        self.author = author
        self.prefix = prefix

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"Start your own game with `{self.prefix}tod`!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Truth 💬", style=discord.ButtonStyle.primary, custom_id="tod:truth")
    async def truth_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        prompt = random.choice(self.TRUTHS)
        embed = discord.Embed(
            title="💬 Truth Prompt",
            description=f"**{self.author.mention}, answer honestly:**\n\n> *\"{prompt}\"*",
            color=CYAN,
        )
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Dare 🎭", style=discord.ButtonStyle.danger, custom_id="tod:dare")
    async def dare_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        prompt = random.choice(self.DARES)
        embed = discord.Embed(
            title="🎭 Dare Prompt",
            description=f"**{self.author.mention}, you have accepted the dare:**\n\n> *\"{prompt}\"*",
            color=PURPLE,
        )
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Random 🎲", style=discord.ButtonStyle.secondary, custom_id="tod:random")
    async def random_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        is_truth = random.choice([True, False])
        if is_truth:
            prompt = random.choice(self.TRUTHS)
            title = "💬 Truth (Randomly Selected)"
            color = CYAN
        else:
            prompt = random.choice(self.DARES)
            title = "🎭 Dare (Randomly Selected)"
            color = PURPLE

        embed = discord.Embed(
            title=title,
            description=f"**{self.author.mention}, your challenge:**\n\n> *\"{prompt}\"*",
            color=color,
        )
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ─── INTERACTIVE POLL VIEW ───────────────────────────────────────────────────

class InteractivePollView(discord.ui.View):
    """Dynamic multi-option poll view with real-time button voting."""

    def __init__(self, question: str, options: list[str], author: discord.Member) -> None:
        super().__init__(timeout=300.0)
        self.question = question
        self.options = options
        self.author = author
        # option_index -> set of user_ids
        self.votes: dict[int, set[int]] = {i: set() for i in range(len(options))}
        self._emojis = ["🇦", "🇧", "🇨", "🇩", "🇪"]

        for i, opt in enumerate(options):
            normalized_option = opt.strip().lower()
            emoji = (
                "✅"
                if normalized_option in {"yes", "y"}
                else "❌"
                if normalized_option in {"no", "n"}
                else self._emojis[i]
            )
            style = (
                discord.ButtonStyle.success
                if normalized_option in {"yes", "y"}
                else discord.ButtonStyle.danger
                if normalized_option in {"no", "n"}
                else discord.ButtonStyle.secondary
            )
            btn = discord.ui.Button(
                label=opt[:80],
                style=style,
                emoji=emoji,
                custom_id=f"poll_vote:{i}",
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except discord.HTTPException as error:
            logger.warning("Failed to disable expired poll controls: %s", error)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            user_id = interaction.user.id
            # Remove previous vote if any
            for idx in self.votes:
                self.votes[idx].discard(user_id)
            # Add new vote
            self.votes[index].add(user_id)

            # Update embed tallies
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    def build_embed(self) -> discord.Embed:
        total_votes = sum(len(v) for v in self.votes.values())
        embed = discord.Embed(
            title=f"🗳️ {self.question}",
            description="Select an option below to vote. You can change your vote at any time.",
            color=PURPLE,
        )
        lines = []
        for i, opt in enumerate(self.options):
            count = len(self.votes[i])
            pct = round((count / total_votes) * 100) if total_votes > 0 else 0
            bar = "🟩" * (pct // 10) + "⬜" * (10 - pct // 10)
            lines.append(f"**{opt}**\n{bar} `{count}` vote(s) · `{pct}%`")

        embed.description += "\n\n" + "\n\n".join(lines)
        embed.set_footer(text=f"Total Votes: {total_votes} • Poll created by {self.author.display_name}")
        return embed


class Games(commands.Cog):
    """Interactive text and voice games."""
    category = "Games"

    BLOX_FRUITS_QUESTIONS = [
        {
            "question": "Which Mythical Fruit has the highest trading value and allows transformation into a multi-tailed fox?",
            "choices": ["Dragon", "Kitsune", "Leopard", "Dough"],
            "answer": "Kitsune",
            "fact": "Kitsune is renowned for its blazing speed, tails, and high trade value."
        },
        {
            "question": "What level is required to enter the Third Sea in Blox Fruits?",
            "choices": ["Level 1000", "Level 1500", "Level 1750", "Level 2000"],
            "answer": "Level 1500",
            "fact": "You must defeat the raid boss Don Swan and talk to the King at the Colosseum to enter Sea 3."
        },
        {
            "question": "Which fighting style is obtained from the Martial Arts Master on Floating Turtle in the Third Sea?",
            "choices": ["Electric Claw", "Godhuman", "Dragon Talon", "Superhuman"],
            "answer": "Godhuman",
            "fact": "Godhuman requires 400 mastery on five different fighting styles and various rare materials."
        },
        {
            "question": "Which sword is considered one of the three True Triple Katanas alongside Shisui and Wando?",
            "choices": ["Saddi", "Yoru", "Hallow Scythe", "Cursed Dual Katana"],
            "answer": "Saddi",
            "fact": "The Legendary Sword Dealer sells Shisui, Wando, and Saddi for 2,000,000 Beli each."
        },
        {
            "question": "Which elemental/natural fruit is famous as the #1 best grinding fruit in the entire game?",
            "choices": ["Magma", "Buddha", "Light", "Ice"],
            "answer": "Buddha",
            "fact": "Buddha's massive melee hitbox and damage reduction make it the undisputed king of grinding."
        },
    ]

    WORD_LIST = [
        ("BLEACH", "A legendary anime about Shinigami and Hollows"),
        ("KATANA", "Traditional Japanese curved sword favored by anime samurai"),
        ("KITSUNE", "Legendary mythical fox with supernatural powers"),
        ("SUIGETSU", "Aizen's illusory Zanpakuto: Kyoka _______"),
        ("SHINOBI", "Secret ninjas known for stealth and jutsu"),
        ("HAKI", "Mysterious dormant willpower power from One Piece"),
    ]

    DAILY_CHALLENGES = [
        "🌟 **Social Streak:** React with 🎉 to 3 different members' messages today!",
        "🔥 **Meme Master:** Share your funniest anime meme in the server's media channel.",
        "🧠 **Brain Power:** Win at least one Trivia or Guess-the-Number game today.",
        "🌸 **Positivity Pulse:** Send a kind compliment to someone using the compliment command.",
        "⚔️ **Roleplay Duel:** Challenge a server friend to a playful duel using a roleplay command.",
    ]

class GamesDropdown(discord.ui.Select):
    def __init__(self, prefix: str):
        self.prefix = prefix
        options = [
            discord.SelectOption(label="All Games Overview", value="overview", emoji="🎮", description="Summary of the entire gaming suite"),
            discord.SelectOption(label="Casino & Luck Games", value="casino", emoji="🎰", description="Slots, Blackjack, Crash, Mines, Roulette & more"),
            discord.SelectOption(label="Multiplayer & PVP Battles", value="multiplayer", emoji="⚔️", description="TicTacToe, Connect4, Duel, Battleship, RPS"),
            discord.SelectOption(label="Puzzles & Brain Challenges", value="puzzles", emoji="🧩", description="Wordle, 2048, Hangman, Memory, Trivia, Quiz"),
            discord.SelectOption(label="Number Guessing (Admin Hosted)", value="number", emoji="🔢", description="Server-wide guess a number event & controls"),
            discord.SelectOption(label="Social & Party Events", value="social", emoji="🎉", description="Reaction Race, Hide & Seek, Two Truths, VC Events"),
        ]
        super().__init__(placeholder="Select a game category to explore...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        p = self.prefix
        val = self.values[0]
        if val == "casino":
            embed = discord.Embed(
                title="🎰 Casino & Luck Games Suite",
                description=(
                    f"• `{p}slots <bet>` — 3-reel slot machine with jackpot multipliers\n"
                    f"• `{p}blackjack <bet>` (or `bj`) — Interactive table with Hit, Stand, Double Down\n"
                    f"• `{p}crash <bet>` — Rocket multiplier launch game with live cashout\n"
                    f"• `{p}mines <bet> [bombs]` — Stake-style 5x5 minefield gem hunt\n"
                    f"• `{p}roulette <bet> <space>` — European roulette (red/black/green/0-36)\n"
                    f"• `{p}wheel <bet>` — Wheel of Fortune with up to 10x multipliers\n"
                    f"• `{p}dice [bet] [prediction]` — Standard dice roll or 5x prediction wager\n"
                    f"• `{p}coinflip [bet] [heads/tails]` — Free coinflip or 1.95x wager\n"
                    f"• `{p}highlow <bet>` — Card streak prediction game with cashout\n"
                    f"• `{p}scratch [cost]` — Interactive 3x3 scratch card with 3-match payouts\n"
                    f"• `{p}baccarat <bet> [side]` — Classic Punto Banco baccarat (Player, Banker, Tie)\n"
                    f"• `{p}horserace <bet> [horse]` — Live animated 4-horse sprint derby\n"
                    f"• `{p}russianroulette [bet]` — High-tension 6-chamber revolver game"
                ),
                color=0xD4AF37,
            )
        elif val == "multiplayer":
            embed = discord.Embed(
                title="⚔️ Multiplayer & PVP Battles",
                description=(
                    f"• `{p}tictactoe @user` (or `ttt`) — Interactive 3x3 grid duel\n"
                    f"• `{p}connect4 @user` (or `c4`) — Interactive 7x6 drop column board\n"
                    f"• `{p}duel @user [bet]` — Turn-based RPG fight with health bars and wagers\n"
                    f"• `{p}battleship @user` (or `bs`) — 5x5 naval warfare fleet combat\n"
                    f"• `{p}rps @user [bet]` — Secret-choice simultaneous Rock-Paper-Scissors duel"
                ),
                color=0x22C55E,
            )
        elif val == "puzzles":
            embed = discord.Embed(
                title="🧩 Puzzles & Brain Challenges",
                description=(
                    f"• `{p}wordle` — 5-letter Wordle puzzle with 6 attempts & colored tiles\n"
                    f"• `{p}2048` — 4x4 sliding tile game with directional buttons ⬆️ ⬇️ ⬅️ ➡️\n"
                    f"• `{p}hangman` — Word hangman with lives and letter guessing\n"
                    f"• `{p}memory` — 4x4 card pairing memory game with 8 fruit pairs\n"
                    f"• `{p}trivia` — Anime & general trivia challenge with multi-choice buttons\n"
                    f"• `{p}quiz [category]` — Categorized trivia tournament (Anime, Gaming)\n"
                    f"• `{p}riddle` — Enigma puzzles with hints & answer reveals\n"
                    f"• `{p}reactionspeed` — Reflex testing with millisecond precision\n"
                    f"• `{p}fasttype` — Speed typing WPM challenge against anime quotes\n"
                    f"• `{p}unscramble` — Speed anagram race in chat for bonus coins"
                ),
                color=0x3B82F6,
            )
        elif val == "number":
            embed = discord.Embed(
                title="🔢 Guess a Number (Admin Hosted & Server Events)",
                description=(
                    f"• `{p}guessanumber <range>` — Start a server number game (e.g. `1-1000`)\n"
                    f"• `{p}guessstatus` — Check active number game in current channel\n"
                    f"• `{p}guesscancel` — Cancel active game (Host or Server Admins)\n"
                    f"• `{p}guessunlock` — Restore channel permissions locked after a game\n"
                    f"• `{p}guesshelp` — Detailed rules & gameplay mechanics\n\n"
                    f"**👑 Server Admin & Owner Controls:**\n"
                    f"• `{p}guesssettings` — View server number game settings\n"
                    f"• `{p}guessreward <coins>` — Set prize coins awarded to game winner\n"
                    f"• `{p}guesssettings autolock <on/off>` — Toggle channel auto-lock on completion\n"
                    f"• `{p}guesshostadd @member` — Authorize a number-game host in this server\n"
                    f"• `{p}guesshostremove @member` — Remove an authorized host\n"
                    f"• `{p}guesshosts` — List all authorized hosts for this server"
                ),
                color=0x7C3AED,
            )
        elif val == "social":
            embed = discord.Embed(
                title="🎉 Social & Party Events",
                description=(
                    f"• `{p}reactionrace` — Fastest-click race when the GO signal appears\n"
                    f"• `{p}hideandseek` — Find the hidden treasure on a 9-button grid\n"
                    f"• `{p}twotruths <s1> | <s2> | <s3> | <lie 1-3>` — Two Truths and a Lie host\n"
                    f"• `{p}tod` — Interactive Truth or Dare challenge\n"
                    f"• `{p}ltlvc start` — Last To Leave Voice Channel endurance event\n"
                    f"• `{p}vctrivia` — Voice-channel real-time trivia competition"
                ),
                color=0xEC4899,
            )
        else:
            embed = discord.Embed(
                title="🎮 Kyoka Sovereign Games Universe",
                description=(
                    "> Complete gaming, casino, puzzle & server competition suite!\n\n"
                    f"**🎰 Casino & Luck:** `{p}slots`, `{p}blackjack`, `{p}crash`, `{p}mines`, `{p}roulette`, `{p}wheel`, `{p}dice`, `{p}baccarat`\n"
                    f"**⚔️ Multiplayer & PVP:** `{p}tictactoe`, `{p}connect4`, `{p}duel`, `{p}battleship`, `{p}rps`\n"
                    f"**🧩 Puzzles & Brain:** `{p}wordle`, `{p}2048`, `{p}hangman`, `{p}memory`, `{p}trivia`, `{p}quiz`, `{p}riddle`\n"
                    f"**🔢 Number Game (Admin):** `{p}guessanumber`, `{p}guesssettings`, `{p}guessreward`, `{p}guesshostadd`\n"
                    f"**🎉 Social & VC:** `{p}reactionrace`, `{p}hideandseek`, `{p}twotruths`, `{p}tod`, `{p}ltlvc`\n\n"
                    "-# Use the dropdown menu below to view detailed command instructions & rules."
                ),
                color=PURPLE,
            )

        await interaction.response.edit_message(embed=embed, view=self.view)


class GamesHubView(discord.ui.View):
    def __init__(self, prefix: str):
        super().__init__(timeout=120)
        self.add_item(GamesDropdown(prefix))


    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_manager = GIFManager()
        self._active_word_games: dict[int, dict[str, Any]] = {}

    @commands.command(name="games", help="List the games you can play with Kyoka.")
    async def game_list(self, ctx: CustomContext) -> None:
        p = ctx.prefix
        embed = discord.Embed(
            title="🎮 Kyoka Sovereign Games Universe",
            description=(
                "> Complete gaming, casino, puzzle & server competition suite!\n\n"
                f"**🎰 Casino & Luck:** `{p}slots`, `{p}blackjack`, `{p}crash`, `{p}mines`, `{p}roulette`, `{p}wheel`, `{p}dice`, `{p}baccarat`\n"
                f"**⚔️ Multiplayer & PVP:** `{p}tictactoe`, `{p}connect4`, `{p}duel`, `{p}battleship`, `{p}rps`\n"
                f"**🧩 Puzzles & Brain:** `{p}wordle`, `{p}2048`, `{p}hangman`, `{p}memory`, `{p}trivia`, `{p}quiz`, `{p}riddle`\n"
                f"**🔢 Number Game (Admin):** `{p}guessanumber`, `{p}guesssettings`, `{p}guessreward`, `{p}guesshostadd`\n"
                f"**🎉 Social & VC:** `{p}reactionrace`, `{p}hideandseek`, `{p}twotruths`, `{p}tod`, `{p}ltlvc`\n\n"
                "-# Use the dropdown menu below to view detailed command instructions & rules."
            ),
            color=PURPLE,
        )
        view = GamesHubView(p)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="reactionrace", aliases=["rrace"], help="Race your friends to click first after GO.")
    @commands.guild_only()
    async def reaction_race(self, ctx: CustomContext) -> None:
        view = ReactionRaceView()
        message = await ctx.send(
            embed=discord.Embed(
                title="🏁 Reaction Race",
                description="Wait for **GO!**—click too early and you lose your chance.",
                color=CYAN,
            ),
            view=view,
        )
        view.message = message
        await asyncio.sleep(random.uniform(2.0, 4.0))
        if view.winner_id is None:
            view.started = True
            button = next(item for item in view.children if isinstance(item, discord.ui.Button))
            button.label = "GO!"
            button.style = discord.ButtonStyle.success
            await message.edit(view=view)

    @commands.command(name="hideandseek", aliases=["scavengerhunt", "hns"], help="Find the hidden treasure first.")
    @commands.guild_only()
    async def hide_and_seek(self, ctx: CustomContext) -> None:
        view = HideAndSeekView(random.randrange(9))
        embed = discord.Embed(
            title="🗺️ Treasure Hunt",
            description="One tile hides the treasure. Each player gets one search—who will find it first?",
            color=CYAN,
        )
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="twotruths", aliases=["twotruthsonelie"], help="Host Two Truths and a Lie.")
    @commands.guild_only()
    async def two_truths(self, ctx: CustomContext, *, statements_input: str) -> None:
        parts = [part.strip() for part in statements_input.split("|")]
        if (
            len(parts) != 4
            or any(not statement or len(statement) > 180 for statement in parts[:3])
            or parts[3] not in {"1", "2", "3"}
        ):
            return await ctx.send(
                f"Usage: `{ctx.prefix}twotruths statement 1 | statement 2 | statement 3 | lie number (1-3)`"
            )

        statements = parts[:3]
        lie_index = int(parts[3]) - 1
        view = TwoTruthsView(ctx.author.id, statements, lie_index)
        embed = discord.Embed(
            title="🕵️ Two Truths and a Lie",
            description="\n".join(f"**{index + 1}.** {discord.utils.escape_markdown(text)}" for index, text in enumerate(statements))
            + "\n\nVote for the statement you think is the lie. The host can reveal when everyone has voted.",
            color=PURPLE,
        )
        view.message = await ctx.send(
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ─── 1. BLOX FRUITS TRIVIA ────────────────────────────────────────────────

    @commands.command(
        name="bloxfruits",
        aliases=["bf", "bloxtrivia"],
        help="Test your Blox Fruits expertise with interactive trivia questions.",
    )
    async def bloxfruits(self, ctx: CustomContext) -> None:
        """Answer a multi-choice Blox Fruits trivia question."""
        q_data = random.choice(self.BLOX_FRUITS_QUESTIONS)
        shuffled = list(q_data["choices"])
        random.shuffle(shuffled)

        view = discord.ui.View(timeout=45.0)
        correct_answer = q_data["answer"]

        for choice in shuffled:
            btn = discord.ui.Button(label=choice, style=discord.ButtonStyle.secondary)

            async def _make_click(ans: str):
                async def btn_callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        return await interaction.response.send_message(
                            f"Play your own round with `{ctx.prefix}bloxfruits`!", ephemeral=True
                        )
                    for child in view.children:
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                            if child.label == correct_answer:
                                child.style = discord.ButtonStyle.success
                            elif child.label == ans:
                                child.style = discord.ButtonStyle.danger

                    if ans == correct_answer:
                        res_text = f"🎉 **Correct!** Excellent Blox Fruits knowledge!\n> *{q_data['fact']}*"
                        color = GREEN
                    else:
                        res_text = f"❌ **Incorrect!** The correct answer was **{correct_answer}**.\n> *{q_data['fact']}*"
                        color = PURPLE

                    embed = discord.Embed(title="🏴‍☠️ Blox Fruits Trivia", description=f"**Q:** {q_data['question']}\n\n{res_text}", color=color)
                    if ans == correct_answer:
                        gif_url = await self.gif_manager.get_action_gif("celebrate")
                        if gif_url:
                            embed.set_image(url=gif_url)
                    await interaction.response.edit_message(embed=embed, view=view)
                    view.stop()
                return btn_callback

            btn.callback = await _make_click(choice)
            view.add_item(btn)

        embed = discord.Embed(
            title="🏴‍☠️ Blox Fruits Trivia Challenge",
            description=f"**Question:**\n> **{q_data['question']}**\n\nClick the correct answer below (45s timeout):",
            color=PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed, view=view)

    # ─── 2. TRUTH OR DARE ─────────────────────────────────────────────────────

    @commands.command(
        name="tod",
        aliases=["truthordare"],
        help="Play interactive Truth or Dare with safe, configurable prompts.",
    )
    async def tod(self, ctx: CustomContext) -> None:
        """Interactive Truth or Dare session."""
        view = TruthOrDareView(ctx.author, ctx.prefix)
        embed = discord.Embed(
            title="🎲 Truth or Dare",
            description=(
                f"**{ctx.author.mention}, choose your destiny:**\n\n"
                f"• **Truth 💬** — Answer an honest question.\n"
                f"• **Dare 🎭** — Accept a harmless server dare.\n"
                f"• **Random 🎲** — Let the bot decide!"
            ),
            color=PURPLE,
        )
        await ctx.send(embed=embed, view=view)

    # ─── 3. INTERACTIVE POLL ──────────────────────────────────────────────────

    @commands.command(name="poll", help="Create a professional button poll: Question? | Option 1 | Option 2")
    @commands.guild_only()
    async def poll(self, ctx: CustomContext, *, poll_input: str = "") -> None:
        """Create a real-time button voting poll."""
        parts = [p.strip() for p in poll_input.split("|") if p.strip()]
        if len(parts) < 3 or len(parts[0]) > 256 or any(len(option) > 80 for option in parts[1:]):
            return await ctx.send(
                f"Usage: `{ctx.prefix}poll Question? | Option 1 | Option 2` (2–5 options; each option must fit a button)"
            )
        question = parts[0]
        options = parts[1:6]

        await self._send_poll(ctx, question, options)

    @commands.command(name="legit", aliases=["legitpoll"], help="Create an interactive Yes/No poll asking if the server is legit.")
    @commands.guild_only()
    async def legit_poll(self, ctx: CustomContext) -> None:
        await self._send_poll(ctx, "Are we legit?", ["Yes", "No"])

    async def _send_poll(self, ctx: CustomContext, question: str, options: list[str]) -> None:
        view = InteractivePollView(question, options, ctx.author)
        embed = view.build_embed()
        view.message = await ctx.send(embed=embed, view=view)

    # ─── 4. WORD GUESSING MINI-GAME ───────────────────────────────────────────

    @commands.command(name="wordguess", aliases=["wordgame"], help="Play a word guessing game with letter hints.")
    async def wordguess(self, ctx: CustomContext) -> None:
        """Guess the secret anime/gaming word."""
        channel_id = ctx.channel.id
        if channel_id in self._active_word_games:
            return await ctx.send("A word guessing game is already active in this channel!")

        secret_word, hint = random.choice(self.WORD_LIST)
        masked = " ".join(["\\_" for _ in secret_word])

        self._active_word_games[channel_id] = {
            "word": secret_word,
            "hint": hint,
            "author": ctx.author.id,
            "expires_at": time.time() + 60,
        }

        embed = discord.Embed(
            title="🔤 Word Guessing Challenge",
            description=(
                f"Guess the secret word! Type your answer directly in this channel.\n\n"
                f"**Word:** `{masked}` ({len(secret_word)} letters)\n"
                f"💡 **Hint:** *{hint}*\n\n"
                f"⏳ You have **60 seconds** to guess!"
            ),
            color=CYAN,
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        ch_id = message.channel.id
        game = self._active_word_games.get(ch_id)
        if not game:
            return

        if time.time() > game["expires_at"]:
            self._active_word_games.pop(ch_id, None)
            await message.channel.send(f"⌛ Word guessing game timed out! The word was **{game['word']}**.")
            return

        guess = message.content.strip().upper()
        if guess == game["word"]:
            self._active_word_games.pop(ch_id, None)
            embed = discord.Embed(
                title="🏆 Word Guessed Correctly!",
                description=f"🎉 **{message.author.mention} solved the puzzle!** The secret word was **{game['word']}**!",
                color=GREEN,
            )
            gif_url = await self.gif_manager.get_action_gif("celebrate")
            if gif_url:
                embed.set_image(url=gif_url)
            await message.reply(embed=embed)

    # ─── 5. DAILY CHALLENGE ───────────────────────────────────────────────────

    @commands.command(
        name="dailychallenge",
        aliases=["dailyquest", "challenge"],
        help="Get today's community fun challenge.",
    )
    async def dailychallenge(self, ctx: CustomContext) -> None:
        """Receive today's server community challenge."""
        day_seed = int(time.time() // 86400)
        rng = random.Random(day_seed + (ctx.guild.id if ctx.guild else 0))
        challenge = rng.choice(self.DAILY_CHALLENGES)

        embed = discord.Embed(
            title="🎯 Today's Community Challenge",
            description=f"{challenge}\n\n*Challenges reset every 24 hours at midnight UTC.*",
            color=PURPLE,
        )
        embed.set_footer(text=f"Server Day #{day_seed % 1000} • Keep the momentum going!")
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Games(bot))
