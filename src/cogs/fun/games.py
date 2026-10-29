from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Games")
PURPLE = 0x7C3AED
CYAN = 0x06B6D4
GREEN = 0x10B981


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

    def __init__(self, author: discord.Member) -> None:
        super().__init__(timeout=60.0)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Start your own game with `+tod`!", ephemeral=True)
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
            label = f"{self._emojis[i]} Option {i+1}"
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=f"poll_vote:{i}")
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
            title=f"📊 Poll: {self.question}",
            color=PURPLE,
        )
        lines = []
        for i, opt in enumerate(self.options):
            count = len(self.votes[i])
            pct = round((count / total_votes) * 100) if total_votes > 0 else 0
            bar = "🟩" * (pct // 10) + "⬜" * (10 - pct // 10)
            lines.append(f"**{self._emojis[i]} {opt}**\n{bar} `{count}` vote(s) ({pct}%)")

        embed.description = "\n\n".join(lines)
        embed.set_footer(text=f"Total Votes: {total_votes} • Poll created by {self.author.display_name}")
        return embed


class Games(commands.Cog):
    """Interactive games: Blox Fruits trivia, Truth or Dare, interactive polls, word guessing, and daily challenges."""
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
        "🌸 **Positivity Pulse:** Send a kind compliment to someone using `+compliment @user`.",
        "⚔️ **Roleplay Duel:** Challenge a server friend to a playful duel with `+slap` or `+punch`.",
    ]

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._active_word_games: dict[int, dict[str, Any]] = {}

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
                        return await interaction.response.send_message("Play your own round with `+bloxfruits`!", ephemeral=True)
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
        view = TruthOrDareView(ctx.author)
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

    @commands.command(name="poll", help="Create an interactive voting poll: ?poll Question? | Option 1 | Option 2 | Option 3")
    @commands.guild_only()
    async def poll(self, ctx: CustomContext, *, poll_input: str = "") -> None:
        """Create a real-time button voting poll."""
        parts = [p.strip() for p in poll_input.split("|") if p.strip()]
        if len(parts) < 3:
            return await ctx.send(
                f"Usage: `{ctx.prefix}poll Question? | Option 1 | Option 2 | Option 3` (minimum 2 options, maximum 5)"
            )
        question = parts[0]
        options = parts[1:6]

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
