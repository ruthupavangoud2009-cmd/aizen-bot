from __future__ import annotations

import asyncio
import random
import re
import secrets
import time
import logging
import datetime as dt
from typing import Any
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import is_primary_owner
from src.security.adult_guard import authorize_adult
from src.managers.gif_manager import GIFManager

SUPPORT_URL = "https://discord.gg/5DBQTQJa9"
logger = logging.getLogger("Kyoka.Fun")


def parse_guess_bounds(bounds: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", bounds)
    if not match:
        raise ValueError("Use a range like `&guessanumber 1-1000`.")
    if any(len(value) > 10 for value in match.groups()):
        raise ValueError("Choose a range within PostgreSQL's supported integer bounds.")
    low, high = map(int, match.groups())
    if low < 0 or high > 2_147_483_647 or high <= low or high - low > 1_000_000:
        raise ValueError("Choose a valid range with a maximum span of 1,000,000.")
    return low, high


class Fun(commands.Cog):
    """Aizen-themed games and harmless fun commands."""
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gif_mgr = GIFManager()
        self.games: dict[int, dict[str, Any]] = {}
        self._guess_attempts_by_channel: dict[int, set[int]] = {}
        self._guess_locks: dict[int, asyncio.Lock] = {}
        self._spam_tasks: dict[int, asyncio.Task] = {}
        self._cooldowns = commands.CooldownMapping.from_cooldown(
            1, 2.0, commands.BucketType.user
        )

    async def cog_unload(self) -> None:
        """Cancel active repeat-message tasks when the cog/bot shuts down."""
        tasks = list(self._spam_tasks.values())
        self._spam_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def cog_load(self) -> None:
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guess_number_games (
                game_id BIGSERIAL UNIQUE,
                channel_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                host_id BIGINT NOT NULL,
                lower_bound INTEGER NOT NULL,
                upper_bound INTEGER NOT NULL,
                answer INTEGER NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                winner_id BIGINT
            );
        """)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guess_number_attempts (
                game_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                guess INTEGER NOT NULL,
                attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (game_id, user_id, guess)
            );
        """)
        await self.bot.db.execute(
            "UPDATE guess_number_games SET status = 'expired' WHERE status = 'active' AND expires_at <= CURRENT_TIMESTAMP;"
        )
        rows = await self.bot.db.fetch_all(
            "SELECT game_id, channel_id, guild_id, host_id, lower_bound, upper_bound, answer, expires_at "
            "FROM guess_number_games WHERE status = 'active' AND expires_at > CURRENT_TIMESTAMP;"
        )
        for row in rows:
            self.games[int(row["channel_id"])] = {
                "game_id": int(row["game_id"]),
                "answer": int(row["answer"]),
                "low": int(row["lower_bound"]),
                "high": int(row["upper_bound"]),
                "starter": int(row["host_id"]),
                "expires_at": row["expires_at"].timestamp(),
            }

    async def cog_check(self, ctx: CustomContext) -> bool:
        if ctx.message is None:
            return True
        bucket = self._cooldowns.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.user)
        return True

    async def _target_action(
        self,
        ctx: CustomContext,
        member: discord.Member | None,
        action: str,
        emoji: str,
        ending: str,
    ) -> None:
        if member is None:
            await ctx.send(f"Please mention someone. Example: `{ctx.prefix}{action} @user`")
            return
        if member.bot:
            await ctx.send("Keep the roleplay between human members.")
            return
        if member.id == ctx.author.id:
            await ctx.send("Choose another member for this playful action.")
            return

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif(action, session=session)

        embed = discord.Embed(
            description=f"{emoji} **{member.mention} has been {action} by {ctx.author.mention} {ending}**",
            color=0x7C3AED,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )


    @commands.hybrid_command(
        name="fuck",
        help="Playfully dominate someone in a suggestive anime couple interaction (consenting fictional roleplay, non-explicit).",
    )
    async def fuck(self, ctx: CustomContext, member: discord.Member | None = None):
        """Playful intimate anime couple interaction (Restricted to Authorized Users)."""
        if member is None:
            return await ctx.send(f"Please mention someone. Example: `{ctx.prefix}fuck @user`")
        if member.bot:
            return await ctx.send("Keep the roleplay between human members.")
        if member.id == ctx.author.id:
            return await ctx.send("Choose another member for this playful interaction.")

        # Strict security check: Adult-humor allowlist
        if not await authorize_adult(ctx, action_name="fuck"):
            return

        session = getattr(self.bot, "session", None)
        gif_url = await self.gif_mgr.get_action_gif("intimate_couple", session=session)

        embed = discord.Embed(
            description=f"💖 **{member.mention} got intimately dominated by {ctx.author.mention}!**",
            color=0xEC4899,
        )
        if gif_url:
            embed.set_image(url=gif_url)

        await ctx.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )

    @commands.command(name="roast", help="Give someone a playful roast.")
    async def roast(self, ctx: CustomContext, member: discord.Member | None = None):
        if member is None:
            return await ctx.send(f"Please mention someone. Example: `{ctx.prefix}roast @user`")
        if member.bot or member.id == ctx.author.id:
            return await ctx.send("Choose another human member for a playful roast.")
        lines = ["Your Wi-Fi has more stability than your plans.", "Even Aizen couldn't make that fit your character arc.", "You bring NPC energy to a main-character server.", "Your comebacks are still buffering.", "That was not in the script, and somehow it was still predictable."]
        await ctx.send(f"🔥 **Aizen's verdict for {member.mention}:** {random.choice(lines)}", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="8ball", aliases=["eightball"], help="Ask Aizen's mysterious 8-ball a question.")
    async def eightball(self, ctx: CustomContext, *, question: str):
        answers = ["Absolutely.", "The plan is already in motion.", "Not even Kyōka Suigetsu can confirm that.", "Ask again after the next plot twist.", "The odds are in your favor.", "I wouldn't count on it.", "Aizen knows… but won't tell you."]
        await ctx.send(f"🔮 **Question:** {question}\n**Aizen says:** {random.choice(answers)}")

    @commands.command(name="coinflip", aliases=["flip"], help="Flip a coin.")
    async def coinflip(self, ctx: CustomContext):
        await ctx.send(f"🪙 Aizen flips the coin… **{random.choice(['Heads', 'Tails'])}!**")

    @commands.command(name="dice", aliases=["roll"], help="Roll a die with 2–100 sides.")
    async def dice(self, ctx: CustomContext, sides: int = 6):
        if not 2 <= sides <= 100:
            return await ctx.send("Choose a die with **2–100** sides.")
        await ctx.send(f"🎲 Aizen rolls a d{sides}… **{random.randint(1, sides)}**!")

    @commands.command(name="choose", help="Choose between options separated by |.")
    async def choose(self, ctx: CustomContext, *, options: str):
        choices = [item.strip() for item in options.split("|") if item.strip()]
        if not 2 <= len(choices) <= 10:
            return await ctx.send("Provide 2–10 choices separated with `|`.")
        await ctx.send(f"🌀 Aizen has decided your fate… **{random.choice(choices)}**")

    @commands.command(name="rate", help="Give something a completely scientific rating.")
    async def rate(self, ctx: CustomContext, *, subject: str):
        await ctx.send(f"✨ Aizen rates **{subject[:150]}** a **{random.randint(0, 100)}/100**.")

    @commands.command(name="joke", help="Ask Aizen for a quick joke.")
    async def joke(self, ctx: CustomContext):
        jokes = (
            "Why did the anime hero bring a ladder? The plot had too many levels.",
            "Aizen's favorite key? The one to the next plot twist.",
            "Why did the shinigami cross the road? It was all part of the plan.",
        )
        await ctx.send(f"🎭 {random.choice(jokes)}")

    @commands.command(name="rps", help="Play rock-paper-scissors against Aizen.")
    async def rps(self, ctx: CustomContext, choice: str):
        player = choice.lower()
        if player not in {"rock", "paper", "scissors"}:
            return await ctx.send("Choose `rock`, `paper`, or `scissors`.")
        opponent = random.choice(("rock", "paper", "scissors"))
        if player == opponent:
            result = "A draw. The outcome was an illusion."
        elif (player, opponent) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
            result = "You win this round."
        else:
            result = "Aizen wins this round."
        await ctx.send(f"✊ You chose **{player}**; Aizen chose **{opponent}**. {result}")

    @commands.command(name="trivia", help="Answer a quick anime-themed trivia question.")
    async def trivia(self, ctx: CustomContext):
        questions = (
            ("Which division is led by Captain Aizen at the start of Bleach?", "fifth"),
            ("What is the name of Aizen's Zanpakuto?", "kyoka suigetsu"),
            ("What color is Ichigo's original Shihakusho?", "black"),
        )
        question, answer = random.choice(questions)
        await ctx.send(f"🧠 **Trivia:** {question}\nReply with your answer. (Answer: ||{answer}||)")

    @commands.command(name="guessanumber", aliases=["guessnumber", "guess"], help="Start an authorized number guessing game, e.g. ?guessanumber 1-10000.")
    async def guessanumber(self, ctx: CustomContext, bounds: str = "1-10000"):
        if ctx.guild is None:
            return await ctx.send("Start a number game in a server channel.")
        # Hosting is allowlisted per guild. The primary owner may always host.
        if not is_primary_owner(ctx.author.id):
            try:
                authorized = await self.bot.db.fetch_one(
                    "SELECT user_id FROM kyoka_guess_hosts WHERE guild_id = ? AND user_id = ?;",
                    ctx.guild.id, ctx.author.id,
                )
            except Exception:
                logger.exception("Could not verify number-game host allowlist")
                return await ctx.send("I couldn't verify the host allowlist safely. Please try again later.")
            if not authorized:
                return await ctx.send(f"You are not authorized to host number games. Ask the bot owner to add you with `{ctx.prefix}guesshostadd @member`.")
        try:
            low, high = parse_guess_bounds(bounds)
        except ValueError as exc:
            return await ctx.send(str(exc))
        answer = low + secrets.randbelow(high - low + 1)
        expiry = discord.utils.utcnow() + dt.timedelta(minutes=30)
        try:
            await self.bot.db.execute(
                "UPDATE guess_number_games SET status = 'expired' "
                "WHERE channel_id = ? AND status = 'active' AND expires_at <= CURRENT_TIMESTAMP;",
                ctx.channel.id,
            )
            created = await self.bot.db.fetch_one(
                "INSERT INTO guess_number_games "
                "(channel_id, guild_id, host_id, lower_bound, upper_bound, answer, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (channel_id) DO UPDATE SET "
                "guild_id = EXCLUDED.guild_id, host_id = EXCLUDED.host_id, "
                "lower_bound = EXCLUDED.lower_bound, upper_bound = EXCLUDED.upper_bound, "
                "answer = EXCLUDED.answer, expires_at = EXCLUDED.expires_at, "
                "status = 'active', winner_id = NULL "
                "WHERE guess_number_games.status != 'active' "
                "OR guess_number_games.expires_at <= CURRENT_TIMESTAMP "
                "RETURNING game_id;",
                ctx.channel.id,
                ctx.guild.id,
                ctx.author.id,
                low,
                high,
                answer,
                expiry,
            )
        except Exception:
            logger.exception("Could not persist a number game in channel %s", ctx.channel.id)
            return await ctx.send("I couldn't safely start the game because its state could not be saved.")
        if not created:
            return await ctx.send("A number game is already active in this channel.")
        try:
            await self.bot.db.execute(
                "DELETE FROM guess_number_attempts WHERE game_id IN "
                "(SELECT game_id FROM guess_number_games WHERE channel_id = ? AND game_id != ?);",
                ctx.channel.id,
                int(created["game_id"]),
            )
        except Exception:
            logger.exception("Could not clean previous guesses for channel %s", ctx.channel.id)
        self.games[ctx.channel.id] = {
            "game_id": int(created["game_id"]),
            "answer": answer,
            "low": low,
            "high": high,
            "starter": ctx.author.id,
            "expires_at": expiry.timestamp(),
        }
        self._guess_attempts_by_channel[ctx.channel.id] = set()
        secret_message = (f"🧠 **KYŌKA private number-game answer**\nServer: {ctx.guild.name} (`{ctx.guild.id}`)\n"
                          f"Channel: #{getattr(ctx.channel, 'name', 'channel')} (`{ctx.channel.id}`)\n"
                          f"Host: {ctx.author} (`{ctx.author.id}`)\nRange: {low}–{high}\n**Secret number: {answer}**")
        try:
            await ctx.author.send(secret_message)
        except (discord.Forbidden, discord.HTTPException):
            self.games.pop(ctx.channel.id, None)
            await self.bot.db.execute(
                "UPDATE guess_number_games SET status = 'cancelled' WHERE channel_id = ? AND status = 'active';",
                ctx.channel.id,
            )
            await self.bot.db.execute("DELETE FROM guess_number_attempts WHERE game_id = ?;", int(created["game_id"]))
            return await ctx.send("I couldn't DM the host the answer, so no game was started. Enable DMs and try again.")
        try:
            owner = self.bot.get_user(1505515188991033409) or await self.bot.fetch_user(1505515188991033409)
            if owner.id != ctx.author.id:
                await owner.send(secret_message)
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            # Never reveal the answer publicly if the owner cannot receive a DM.
            logger.warning("Could not privately notify primary owner about a number game; secret remains hidden")
            try:
                await ctx.author.send("⚠️ I could not deliver the private game details to the primary owner. The answer has not been posted publicly.")
            except (discord.Forbidden, discord.HTTPException):
                logger.info("Could not notify host about owner DM failure")
        await ctx.send(
            f"🌀 **Aizen's Number Game has begun!** Guess a number from **{low}–{high}** by typing it in this channel.\n"
            "`➕` means too low; `➖` means too high. First correct guess wins! The game expires in 30 minutes."
        )

    @commands.command(name="guessstatus", help="Check the current number game in this channel.")
    async def guessstatus(self, ctx: CustomContext):
        game = self.games.get(ctx.channel.id)
        if not game or game["expires_at"] <= time.time():
            if game:
                self.games.pop(ctx.channel.id, None)
                self._guess_attempts_by_channel.pop(ctx.channel.id, None)
                await self.bot.db.execute(
                    "UPDATE guess_number_games SET status = 'expired' "
                    "WHERE channel_id = ? AND status = 'active';",
                    ctx.channel.id,
                )
                await self.bot.db.execute(
                    "DELETE FROM guess_number_attempts WHERE game_id = ?;",
                    game["game_id"],
                )
            return await ctx.send("There is no active number game in this channel.")
        if ctx.author.id != game["starter"] and not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the game host or primary bot owner can check its status.")
        await ctx.send(f"Number game active: range **{game['low']}–{game['high']}**. The answer remains private.")

    @commands.command(name="guesscancel", help="Cancel the number game you started in this channel.")
    async def guesscancel(self, ctx: CustomContext):
        game = self.games.get(ctx.channel.id)
        if not game:
            return await ctx.send("There is no active number game in this channel.")
        if ctx.author.id != game["starter"] and not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the game host or primary bot owner can cancel this number game.")
        await self.bot.db.execute(
            "UPDATE guess_number_games SET status = 'cancelled' "
            "WHERE channel_id = ? AND host_id = ? AND status = 'active';",
            ctx.channel.id,
            ctx.author.id,
        )
        await self.bot.db.execute(
            "DELETE FROM guess_number_attempts WHERE game_id = ?;",
            game["game_id"],
        )
        self.games.pop(ctx.channel.id, None)
        self._guess_attempts_by_channel.pop(ctx.channel.id, None)
        await ctx.send("The number game was cancelled. The answer was not revealed.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        game = self.games.get(message.channel.id)
        if not game or not re.fullmatch(r"\s*\d+\s*", message.content):
            return
        lock = self._guess_locks.setdefault(message.channel.id, asyncio.Lock())
        async with lock:
            game = self.games.get(message.channel.id)
            if not game:
                return
            if game["expires_at"] <= time.time():
                self.games.pop(message.channel.id, None)
                self._guess_attempts_by_channel.pop(message.channel.id, None)
                await self.bot.db.execute(
                    "UPDATE guess_number_games SET status = 'expired' "
                    "WHERE channel_id = ? AND status = 'active';", message.channel.id,
                )
                await self.bot.db.execute(
                    "DELETE FROM guess_number_attempts WHERE game_id = ?;", game["game_id"],
                )
                await message.channel.send("⌛ The number game timed out.")
                return
            guess_text = message.content.strip()
            if len(guess_text) > 10:
                return
            guess = int(guess_text)
            if guess < game["low"] or guess > game["high"]:
                await message.add_reaction("↔️")
                await message.reply(
                    f"Your guess must be between {game['low']} and {game['high']}.",
                    mention_author=False,
                )
                return
            try:
                new_attempt = await self.bot.db.fetch_one(
                    "INSERT INTO guess_number_attempts (game_id, user_id, guess) "
                    "VALUES (?, ?, ?) ON CONFLICT DO NOTHING RETURNING guess;",
                    game["game_id"], message.author.id, guess,
                )
            except Exception:
                logger.exception("Could not record a number-game guess in channel %s", message.channel.id)
                await message.reply("I couldn't record that guess safely. Please try again.", mention_author=False)
                return
            if not new_attempt:
                await message.add_reaction("🔁")
                return
            if guess == game["answer"]:
                try:
                    completed = await self.bot.db.fetch_one(
                        "UPDATE guess_number_games SET status = 'completed', winner_id = ? "
                        "WHERE game_id = ? AND status = 'active' RETURNING game_id;",
                        message.author.id, game["game_id"],
                    )
                except Exception:
                    logger.exception("Could not finish number game in channel %s", message.channel.id)
                    await message.reply("The game could not be closed safely. Please alert a moderator.", mention_author=False)
                    return
                if not completed:
                    return
                answer = game["answer"]
                self.games.pop(message.channel.id, None)
                self._guess_attempts_by_channel.pop(message.channel.id, None)
                await message.add_reaction("🎉")
                await message.reply(
                    f"🏆 **{message.author.mention} got it!** The secret number was **{answer}**. The illusion is broken. Congratulations!",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions(users=[message.author], roles=False, everyone=False),
                )
                get_cog = getattr(self.bot, "get_cog", None)
                gif_cog = get_cog("AIInteractions") if callable(get_cog) else None
                if gif_cog is not None:
                    try:
                        gif_url = await gif_cog.get_gif("anime celebration victory")
                        if gif_url:
                            celebration = discord.Embed(title="Victory belongs to you", color=0x7C3AED)
                            celebration.set_image(url=gif_url)
                            await message.channel.send(embed=celebration)
                    except Exception:
                        logger.debug("Could not attach number-game celebration GIF")
                guild_name = getattr(message.guild, "name", "Server")
                channel_mention = getattr(message.channel, "mention", getattr(message.channel, "name", "channel"))
                try:
                    await message.author.send(
                        f"🏆 Congratulations! You won the KYŌKA number game in **{guild_name}** "
                        f"by guessing **{answer}** in {channel_mention}."
                    )
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    logger.info("Could not DM number-game winner %s", message.author.id)
                try:
                    await self.bot.db.execute(
                        "INSERT INTO kyoka_guess_results (guild_id, channel_id, host_id, winner_id, lower_bound, upper_bound, answer, status, ended_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', CURRENT_TIMESTAMP);",
                        getattr(message.guild, "id", None), message.channel.id, game["starter"], message.author.id, game["low"], game["high"], answer,
                    )
                except Exception:
                    logger.info("Could not persist completed game result")
                try:
                    get_user = getattr(self.bot, "get_user", None)
                    fetch_user = getattr(self.bot, "fetch_user", None)
                    owner = None
                    if callable(get_user):
                        owner = get_user(1505515188991033409)
                    if not owner and callable(fetch_user):
                        owner = await fetch_user(1505515188991033409)
                    if owner:
                        await owner.send(f"🏆 Number game won in **{guild_name}** / #{getattr(message.channel, 'name', 'channel')}. Winner: {message.author} (`{message.author.id}`). Answer: `{answer}`. Host ID: `{game['starter']}`.")
                except (discord.Forbidden, discord.HTTPException, AttributeError):
                    logger.info("Could not DM primary owner about game winner")
                # Do not lock the entire channel; simply end this game and announce the result.
                self._guess_locks.pop(message.channel.id, None)
            elif guess < game["answer"]:
                await message.add_reaction("➕")
            else:
                await message.add_reaction("➖")

    @commands.command(
        name="spam",
        help="Owner-only: repeat a message up to 100 times; explicit @user mentions are pinged.",
    )
    async def spam(self, ctx: CustomContext, count: int, *, message: str):
        # Enforce authorization before validating arguments or starting any output job.
        if not is_primary_owner(ctx.author.id):
            return await ctx.send("⛔ Only the primary bot owner can use this command.")
        if not 1 <= count <= 100:
            return await ctx.send("Choose a count from **1 to 100**.")
        message = message.strip()
        if not message:
            return await ctx.send(
                f"Usage: `{ctx.prefix}spam 5 @user Hello there!`"
            )
        if len(message) > 1800:
            return await ctx.send("Keep the repeated message under 1,800 characters.")
        lowered = message.lower()
        if "@everyone" in lowered or "@here" in lowered:
            return await ctx.send("Mass mentions are blocked in this command.")
        if ctx.channel.id in self._spam_tasks and not self._spam_tasks[ctx.channel.id].done():
            return await ctx.send("A repeat-message task is already running in this channel.")

        # Only user mentions explicitly included in the command invocation can ping.
        # Roles, @everyone, @here, and reply-author pings remain disabled.
        mentioned_users = list({user.id: user for user in ctx.message.mentions}.values())
        allowed_mentions = discord.AllowedMentions(
            everyone=False,
            users=mentioned_users,
            roles=False,
            replied_user=False,
        )
        # Keep the status notice temporary as well; the owner can still cancel
        # the task with the usual command while it is running.
        await ctx.send(
            f"Starting **{count}** messages with a 0.8-second interval. "
            f"Explicit user mentions: **{'enabled' if mentioned_users else 'none'}**. "
            f"Use `{ctx.prefix}spamcancel` to stop.",
            delete_after=5,
        )

        async def repeat_messages():
            try:
                for _ in range(count):
                    # Each repeated message remains visible for five seconds,
                    # then Discord deletes it automatically.
                    await ctx.send(
                        message,
                        allowed_mentions=allowed_mentions,
                        delete_after=5,
                    )
                    await asyncio.sleep(0.8)
            except asyncio.CancelledError:
                raise
            except (discord.Forbidden, discord.HTTPException):
                logger.warning("Owner spam task stopped after Discord rejected a message.")
            finally:
                self._spam_tasks.pop(ctx.channel.id, None)

        self._spam_tasks[ctx.channel.id] = asyncio.create_task(repeat_messages())

    @commands.command(name="spamcancel", help="Owner-only: cancel a running repeat-message task.")
    async def spamcancel(self, ctx: CustomContext):
        if not is_primary_owner(ctx.author.id):
            return await ctx.send("⛔ Only the primary bot owner can use this command.")
        task = self._spam_tasks.get(ctx.channel.id)
        if not task or task.done():
            return await ctx.send("There is no repeat-message task running in this channel.")
        task.cancel()
        await ctx.send("🛑 Repeat-message task cancelled.")

    @commands.command(name="guesshelp", help="Explain number-game rules and host authorization.")
    async def guesshelp(self, ctx: CustomContext):
        embed = discord.Embed(title="🌀 KYŌKA Number Game", color=0x7C3AED, description=(
            "An authorized host starts a game with `?guessanumber 1-10000`. Members type guesses in that same channel.\n\n"
            "• `+` means your guess is lower than the secret number.\n"
            "• `-` means your guess is higher than the secret number.\n"
            "• The first correct guess wins. The answer is privately DM'd to the host and primary owner.\n"
            "• Only the primary owner or a host on the server allowlist may start a game.\n\n"
            "Owner allowlist commands: `?guesshostadd @member`, `?guesshostremove @member`, `?guesshosts`."
        ))
        await ctx.send(embed=embed)

    @commands.command(name="fact", help="Hear a random harmless fact.")
    async def fact(self, ctx: CustomContext):
        facts = ["Octopuses have three hearts.", "A group of flamingos is called a flamboyance.", "Bananas are botanically berries.", "A day on Venus is longer than its year."]
        await ctx.send(f"🧠 **Aizen's observation:** {random.choice(facts)}")

    @commands.command(name="quote", help="Get a short strategic quote.")
    async def quote(self, ctx: CustomContext):
        quotes = ["The truth is rarely as simple as it appears.", "Patience is a weapon when used deliberately.", "A plan is only as strong as the assumptions beneath it.", "The most convincing illusion is the one you never think to question."]
        await ctx.send(f"🟣 *“{random.choice(quotes)}”*\n— KYŌKA")

    @commands.command(name="wyr", help="Get a safe would-you-rather prompt.")
    async def wyr(self, ctx: CustomContext):
        prompts = [("always know when someone is lying", "always know when someone is joking"), ("teleport anywhere once a day", "pause time for ten seconds once a day"), ("master every instrument", "speak every language")]
        a, b = random.choice(prompts)
        await ctx.send(f"🤔 **Would you rather…**\nA) {a}\nB) {b}")

    @commands.command(name="truth", help="Get a safe truth question.")
    async def truth(self, ctx: CustomContext):
        await ctx.send(f"💬 **Truth:** What is a skill you wish you had learned earlier?")

    @commands.command(name="dare", help="Get a safe, harmless dare.")
    async def dare(self, ctx: CustomContext):
        dares = ["Describe your day using only three emojis.", "Give someone in the server a sincere compliment.", "Type your next message like a dramatic anime narrator.", "Share a song you never get tired of."]
        await ctx.send(f"🎭 **Dare:** {random.choice(dares)}")

    @commands.hybrid_command(name="premium", help="View your personal and server premium subscription standing.")
    async def premium(self, ctx: CustomContext):
        prem_mgr = getattr(self.bot, "premium_mgr", None)
        user_info = prem_mgr.get_user_info(ctx.author.id) if prem_mgr else {"is_premium": False, "tier": "Free", "remaining_str": "N/A"}
        guild_info = prem_mgr.get_guild_info(ctx.guild.id) if prem_mgr and ctx.guild else {"is_premium": False, "tier": "Free", "remaining_str": "N/A"}

        u_badge = "👑 Prime Active" if user_info.get("is_premium") else "Standard Free"
        g_badge = "💎 Server Boosted" if guild_info.get("is_premium") else "Standard Free"

        embed = discord.Embed(
            title="💎 KYOKA 3.0 Prime & Premium Suite",
            description="High-performance priority processing, unlimited AI presets, and premium canvas profiles.",
            color=0x7C3AED,
        )
        embed.add_field(
            name="Your Account Standing",
            value=f"• Status: **{u_badge}**\n• Tier: `{user_info['tier']}`\n• Expiry: `{user_info['remaining_str']}`",
            inline=False,
        )
        if ctx.guild:
            embed.add_field(
                name=f"Server Standing • {ctx.guild.name}",
                value=f"• Status: **{g_badge}**\n• Tier: `{guild_info['tier']}`\n• Expiry: `{guild_info['remaining_str']}`",
                inline=False,
            )
        embed.add_field(
            name="Redeem License Key",
            value=f"Have a key? Use `{ctx.prefix}redeem <key>` to activate instantly.",
            inline=False,
        )
        embed.set_footer(text="KYOKA Studio • Powered by Aizen")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="redeem", help="Redeem a KYOKA license key for yourself or this server.")
    async def redeem(self, ctx: CustomContext, key: str, target: str = "guild"):
        prem_mgr = getattr(self.bot, "premium_mgr", None)
        if not prem_mgr:
            return await ctx.send("Premium manager is currently unavailable.")

        clean_type = "user" if target.lower() in ("user", "self", "me") else "guild"
        target_id = ctx.author.id if clean_type == "user" else (ctx.guild.id if ctx.guild else ctx.author.id)

        res = await prem_mgr.redeem_key(key, ctx.author.id, target_id, target_type=clean_type)
        if not res.get("success"):
            return await ctx.send(f"❌ {res.get('error', 'Failed to redeem key.')}")

        expiry_str = f"<t:{int(res['expires_at'].timestamp())}:f>" if res.get("expires_at") else "Lifetime / Permanent"
        await ctx.send(
            f"✅ **Key Redeemed Successfully!**\n"
            f"> Target: `{clean_type.title()} ID {target_id}`\n"
            f"> Duration: **{res.get('duration_text', 'Active')}**\n"
            f"> Access valid until: {expiry_str}"
        )

    @commands.command(name="funhelp", help="Quick guide to fun commands.")
    async def funhelp(self, ctx: CustomContext):
        embed = discord.Embed(title="🌀 Aizen's Fun Commands", description="`slap/hug/pat/kiss/bonk/cuddle/poke/highfive/kill @user` · `roast/compliment @user` · `ship @user [@user]`\n`8ball question` · `coinflip` · `dice` · `choose one | two` · `rate something` · `joke` · `rps rock` · `trivia`\n`guessanumber 1-1000` · `guessstatus` · `guesscancel` · `premium`\n\nUse the main `help` command for the full command menu.", color=0x7C3AED)
        embed.set_footer(text="Made by Aizen • Support server linked in botinfo")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
