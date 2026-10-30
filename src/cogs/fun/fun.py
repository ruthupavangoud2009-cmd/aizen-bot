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

from src.core.config import Config
from src.core.context import CustomContext
from src.security.owner import is_primary_owner
from src.security.adult_guard import authorize_adult
from src.managers.gif_manager import GIFManager

SUPPORT_URL = Config.SUPPORT_URL or "https://discord.gg/7q4tn6dA6V"
logger = logging.getLogger("Kyoka.Fun")


def parse_guess_bounds(bounds: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", bounds)
    if not match:
        raise ValueError("Enter a range like `1-1000`.")
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
        self._guess_locks: dict[int, asyncio.Lock] = {}
        self._spam_tasks: dict[int, asyncio.Task] = {}
        self._countdown_tasks: dict[int, asyncio.Task] = {}
        self._locked_channels_original_overwrites: dict[int, Optional[bool]] = {}
        self._cooldowns = commands.CooldownMapping.from_cooldown(
            1, 2.0, commands.BucketType.user
        )

    async def cog_unload(self) -> None:
        """Cancel active repeat-message and countdown tasks when the cog/bot shuts down."""
        tasks = [t for t in list(self._spam_tasks.values()) + list(self._countdown_tasks.values()) if not t.done()]
        self._spam_tasks.clear()
        self._countdown_tasks.clear()
        for task in tasks:
            try:
                task.cancel()
            except Exception:
                pass
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

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


    @commands.command(
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

    @commands.command(name="guessanumber", aliases=["guessnumber", "guess"], help="Start an authorized number guessing game with unlimited guesses.")
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
        if not created or ctx.channel.id in self.games or ctx.channel.id in self._countdown_tasks:
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

        start_time = time.monotonic() + 3.0
        self.games[ctx.channel.id] = {
            "game_id": int(created["game_id"]),
            "answer": answer,
            "low": low,
            "high": high,
            "starter": ctx.author.id,
            "expires_at": expiry.timestamp(),
            "start_time": start_time,
            "countdown_active": True,
        }
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
        except (discord.Forbidden, discord.HTTPException, AttributeError, TypeError):
            # Never reveal the answer publicly if the owner cannot receive a DM.
            logger.warning("Could not privately notify primary owner about a number game; secret remains hidden")
            try:
                await ctx.author.send("⚠️ I could not deliver the private game details to the primary owner. The answer has not been posted publicly.")
            except (discord.Forbidden, discord.HTTPException, TypeError):
                logger.info("Could not notify host about owner DM failure")

        # Announce 3-second cooldown
        await ctx.send("🎮 **Guess a Number starts in 3 seconds! Get ready!**")

        async def _run_countdown():
            try:
                await asyncio.sleep(3.0)
                g = self.games.get(ctx.channel.id)
                if g and g.get("countdown_active"):
                    g["countdown_active"] = False
                    await ctx.send(
                        f"🌀 **Aizen's Number Game has begun!** Guess a number from **{low}–{high}** by typing it in this channel.\n"
                        "`➕` means too low; `➖` means too high. First correct guess wins! The game expires in 30 minutes."
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Countdown task notice: {e}")
            finally:
                self._countdown_tasks.pop(ctx.channel.id, None)

        cd_task = asyncio.create_task(_run_countdown())
        self._countdown_tasks[ctx.channel.id] = cd_task

    async def _lock_channel_after_game(self, channel: Any, reason: str) -> bool:
        """Lock channel for regular members (@everyone send_messages = False) when game ends.
        Preserves other role/user overwrites. Stores original send_messages setting.
        Handles permissions safely and does not crash.
        """
        if not hasattr(channel, "guild") or not hasattr(channel, "set_permissions"):
            return False
        guild = channel.guild
        if not guild:
            return False

        # Verify bot has manage_channels permission in this channel
        me = getattr(guild, "me", None)
        if me:
            perms = channel.permissions_for(me)
            if not getattr(perms, "manage_channels", False):
                logger.warning("Cannot lock channel %s: Bot lacks manage_channels permission", channel.id)
                return False

        try:
            target_role = guild.default_role
            current_overwrite = channel.overwrites_for(target_role)

            # Store original permission overwrite before locking
            if channel.id not in self._locked_channels_original_overwrites:
                self._locked_channels_original_overwrites[channel.id] = current_overwrite.send_messages

            current_overwrite.send_messages = False
            await channel.set_permissions(
                target_role,
                overwrite=current_overwrite,
                reason=f"Guess a Number game ended ({reason})",
            )
            try:
                await channel.send(
                    f"🔒 **Channel Locked:** This channel has been automatically locked because the Guess a Number event ended ({reason}). "
                    f"An administrator can unlock it with `?guessunlock` or `?unlock`."
                )
            except Exception:
                pass
            return True
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("Permission error locking channel %s after number game: %s", channel.id, e)
            return False
        except Exception as e:
            logger.debug("Notice locking channel %s: %s", channel.id, e)
            return False

    @commands.command(name="guessunlock", aliases=["gunlock"], help="Unlock a channel locked by a Guess a Number game.")
    @commands.has_permissions(manage_channels=True)
    async def guessunlock(self, ctx: CustomContext):
        """Restore channel permissions locked after a Guess a Number event."""
        if not ctx.guild or not hasattr(ctx.channel, "set_permissions"):
            return await ctx.send("This command must be run in a server text channel.")

        original_setting = self._locked_channels_original_overwrites.pop(ctx.channel.id, None)
        try:
            target_role = ctx.guild.default_role
            overwrite = ctx.channel.overwrites_for(target_role)
            overwrite.send_messages = original_setting
            await ctx.channel.set_permissions(
                target_role,
                overwrite=overwrite,
                reason=f"Channel unlocked by {ctx.author} via guessunlock",
            )
            await ctx.send(f"🔓 **Channel Unlocked:** Permissions for {target_role.name} have been restored.")
        except (discord.Forbidden, discord.HTTPException) as e:
            await ctx.send(f"⚠️ Could not unlock channel: {e}")

    @commands.command(name="guessstatus", help="Check the current number game in this channel.")
    async def guessstatus(self, ctx: CustomContext):
        game = self.games.get(ctx.channel.id)
        if not game or game["expires_at"] <= time.time():
            if game:
                cd_task = self._countdown_tasks.pop(ctx.channel.id, None)
                if cd_task and not cd_task.done():
                    cd_task.cancel()
                self.games.pop(ctx.channel.id, None)
                await self.bot.db.execute(
                    "UPDATE guess_number_games SET status = 'expired' "
                    "WHERE channel_id = ? AND status = 'active';",
                    ctx.channel.id,
                )
                await self.bot.db.execute(
                    "DELETE FROM guess_number_attempts WHERE game_id = ?;",
                    game["game_id"],
                )
                await ctx.send("⌛ The number game timed out.")
                await self._lock_channel_after_game(ctx.channel, "Game timed out")
            return await ctx.send("There is no active number game in this channel.")
        if ctx.author.id != game["starter"] and not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the game host or primary bot owner can check its status.")
        status_text = "Starting soon (cooldown)" if game.get("countdown_active") else "Active"
        await ctx.send(f"Number game {status_text.lower()}: range **{game['low']}–{game['high']}**. The answer remains private.")

    @commands.command(name="guesscancel", help="Cancel the number game you started in this channel.")
    async def guesscancel(self, ctx: CustomContext):
        game = self.games.get(ctx.channel.id)
        if not game:
            return await ctx.send("There is no active number game in this channel.")
        if ctx.author.id != game["starter"] and not is_primary_owner(ctx.author.id):
            return await ctx.send("Only the game host or primary bot owner can cancel this number game.")
        
        cd_task = self._countdown_tasks.pop(ctx.channel.id, None)
        if cd_task and not cd_task.done():
            cd_task.cancel()

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
        await ctx.send("The number game was cancelled. The answer was not revealed.")
        await self._lock_channel_after_game(ctx.channel, "Game cancelled by host")

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

            # Check 3-second cooldown
            if game.get("countdown_active") or time.monotonic() < game.get("start_time", 0.0):
                try:
                    await message.add_reaction("⏳")
                except Exception:
                    pass
                return

            if game["expires_at"] <= time.time():
                self.games.pop(message.channel.id, None)
                await self.bot.db.execute(
                    "UPDATE guess_number_games SET status = 'expired' "
                    "WHERE channel_id = ? AND status = 'active';", message.channel.id,
                )
                await self.bot.db.execute(
                    "DELETE FROM guess_number_attempts WHERE game_id = ?;", game["game_id"],
                )
                await message.channel.send("⌛ The number game timed out.")
                await self._lock_channel_after_game(message.channel, "Game timed out")
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
                await message.add_reaction("🎉")
                await message.reply(
                    f"🏆 **{message.author.mention} got it!** The secret number was **{answer}**. The illusion is broken. Congratulations!",
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions(users=[message.author], roles=False, everyone=False),
                )
                gif_url = await self.gif_mgr.get_action_gif("celebrate")
                celebration = discord.Embed(
                    title="🏆 Number Game Champion!",
                    description=f"{message.author.mention} found **{answer}**!",
                    color=0x7C3AED,
                )
                if gif_url:
                    celebration.set_image(url=gif_url)
                await message.channel.send(embed=celebration)
                guild_name = getattr(message.guild, "name", "Server")
                channel_mention = getattr(message.channel, "mention", getattr(message.channel, "name", "channel"))
                try:
                    await message.author.send(
                        f"🏆 Congratulations! You won the KYŌKA number game in **{guild_name}** "
                        f"by guessing **{answer}** in {channel_mention}."
                    )
                except (discord.Forbidden, discord.HTTPException, AttributeError, TypeError):
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
                except (discord.Forbidden, discord.HTTPException, AttributeError, TypeError):
                    logger.info("Could not DM primary owner about game winner")

                # Lock the channel now that result has been sent
                await self._lock_channel_after_game(message.channel, "Winner found")
                self._guess_locks.pop(message.channel.id, None)
            elif guess < game["answer"]:
                await message.add_reaction("➕")
            else:
                await message.add_reaction("➖")

    def _get_task_manager(self):
        from src.core.task_manager import TaskManager
        mgr = getattr(self.bot, "task_mgr", None)
        if isinstance(mgr, TaskManager):
            return mgr
        return None

    @commands.command(
        name="spam",
        help="Owner & Bot Staff: repeat a message (Owner limit: 10,000, Staff limit: 20; interval: 0.4s). Supports roles, @everyone, and @here.",
    )
    async def spam(self, ctx: CustomContext, count: int, *, message: str):
        # Auto-delete the invoking command message immediately (e.g. "spam 10 hi")
        mentioned_users = list({user.id: user for user in ctx.message.mentions}.values()) if hasattr(ctx, "message") and ctx.message and hasattr(ctx.message, "mentions") else []
        if hasattr(ctx, "message") and ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        # Enforce authorization: Primary Owner or Bot Staff
        author_id = getattr(ctx.author, "id", None)
        from src.security.owner import is_primary_owner, is_owner_or_staff, OWNER_ID

        if not is_owner_or_staff(author_id):
            return await ctx.send("⛔ Only the primary bot owner or bot staff can use this command.", delete_after=6)

        is_owner = is_primary_owner(author_id)
        max_limit = 10000 if is_owner else 20

        if not 1 <= count <= max_limit:
            if is_owner:
                return await ctx.send("Choose a count from **1 to 10,000**.", delete_after=6)
            return await ctx.send("Choose a count from **1 to 20** (Bot Staff limit: 20; Primary Owner limit: 10,000).", delete_after=6)

        message = message.strip()
        if not message:
            return await ctx.send(
                f"Usage: `{ctx.prefix}spam 5 @user Hello there!`",
                delete_after=6,
            )
        if len(message) > 1800:
            return await ctx.send("Keep the repeated message under 1,800 characters.", delete_after=6)

        # Protection: Spam command cannot target or ping the bot owner when used by bot staff
        if not is_owner:
            # 1. Block if owner is in message mentions
            mentioned_user_ids = {u.id for u in ctx.message.mentions} if hasattr(ctx, "message") and ctx.message and hasattr(ctx.message, "mentions") else set()
            if OWNER_ID in mentioned_user_ids:
                return await ctx.send("⛔ You cannot target or ping the bot owner with the spam command.", delete_after=6)

            # 2. Block if raw message contains owner mention or ID
            if str(OWNER_ID) in message or f"<@{OWNER_ID}>" in message or f"<@!{OWNER_ID}>" in message:
                return await ctx.send("⛔ You cannot target or ping the bot owner with the spam command.", delete_after=6)

            # 3. Block if executed in owner's DM channel
            channel_recipient = getattr(ctx.channel, "recipient", None)
            if channel_recipient and getattr(channel_recipient, "id", None) == OWNER_ID:
                return await ctx.send("⛔ You cannot use the spam command on the bot owner.", delete_after=6)

        task_mgr = self._get_task_manager()

        # Check existing channel task
        channel_task_running = False
        if ctx.channel.id in self._spam_tasks and not self._spam_tasks[ctx.channel.id].done():
            channel_task_running = True
        elif task_mgr and task_mgr.get_task_by_channel(ctx.channel.id):
            channel_task_running = True

        if channel_task_running:
            return await ctx.send(
                f"A repeat-message task is already running in this channel. Use `{ctx.prefix}spamcancel` to stop it.",
                delete_after=6,
            )

        # Allow spamming roles, @everyone, @here, and users
        allowed_mentions = discord.AllowedMentions(
            everyone=True,
            roles=True,
            users=True,
            replied_user=False,
        )

        task_id = task_mgr.get_next_task_id() if task_mgr else f"SPAM-{int(time.time() * 1000) % 10000:04d}"
        from src.core.task_manager import SpamControlView
        view = SpamControlView(task_id, task_mgr, ctx.author.id) if task_mgr else None

        await ctx.send(
            f"⚡ Starting **{count}** messages (Task: `{task_id}`, interval: 0.4s). "
            f"Mentions (roles, everyone, users): **enabled**. "
            f"Use `{ctx.prefix}spamcancel` to halt.",
            view=view,
            delete_after=6,
        )

        channel_id = int(ctx.channel.id)
        task_info_ref = [None]

        async def repeat_messages():
            try:
                for idx in range(count):
                    try:
                        await ctx.send(
                            message,
                            allowed_mentions=allowed_mentions,
                            delete_after=5,
                        )
                        if task_info_ref[0]:
                            task_info_ref[0].sent_count += 1
                    except discord.HTTPException as http_err:
                        if getattr(http_err, "status", None) == 429:
                            logger.warning(f"Spam task {task_id} paused due to rate-limit (429), terminating task safely.")
                        else:
                            logger.warning(f"Spam task {task_id} encountered HTTPException: {http_err}")
                        break
                    await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                logger.info(f"Spam task {task_id} was cancelled.")
                raise
            except Exception as e:
                logger.warning(f"Spam task {task_id} stopped unexpectedly: {e}")
            finally:
                if task_mgr:
                    task_mgr.unregister_task(task_id)
                self._spam_tasks.pop(channel_id, None)

        task = asyncio.create_task(repeat_messages())
        self._spam_tasks[channel_id] = task

        def _on_done(t: asyncio.Task) -> None:
            if task_mgr:
                task_mgr.unregister_task(task_id)
            self._spam_tasks.pop(channel_id, None)

        task.add_done_callback(_on_done)

        if task_mgr:
            initiating_msg_id = ctx.message.id if hasattr(ctx, "message") and ctx.message else None
            task_info_ref[0] = task_mgr.register_spam_task(
                task_id=task_id,
                task=task,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                invoker_id=ctx.author.id,
                initiating_message_id=initiating_msg_id,
                count=count,
            )

    @commands.command(
        name="spamcancel",
        aliases=["spamstop"],
        help="Owner & Bot Staff: cancel running repeat-message tasks. Use '?spamcancel all' for emergency global stop.",
    )
    async def spamcancel(self, ctx: CustomContext, target: str | None = None):
        author_id = getattr(ctx.author, "id", None)
        from src.security.owner import is_primary_owner, is_owner_or_staff
        if not is_owner_or_staff(author_id):
            return await ctx.send("⛔ Only the primary bot owner or bot staff can use this command.")

        task_mgr = self._get_task_manager()

        # Global emergency cancel: ?spamcancel all / ?spamstop all (Primary Owner only)
        if target and target.lower() in ("all", "global", "stop"):
            if not is_primary_owner(author_id):
                return await ctx.send("⛔ Only the primary bot owner can execute an emergency stop across all channels.")
            cancelled = 0
            if task_mgr:
                cancelled += task_mgr.cancel_all(reason="emergency_stop_command")
            for t in list(self._spam_tasks.values()):
                if not t.done():
                    t.cancel()
                    cancelled += 1
            self._spam_tasks.clear()
            return await ctx.send(f"🛑 Emergency stop executed: cancelled **{cancelled}** active repeat-message tasks.")

        # Targeted task cancel by Task ID: e.g. ?spamcancel SPAM-0001
        if target and target.upper().startswith("SPAM-"):
            if task_mgr and task_mgr.cancel_task(target.upper(), reason="owner_targeted_cancel"):
                return await ctx.send(f"🛑 Task **{target.upper()}** cancelled.")
            return await ctx.send(f"No active task found with ID `{target}`.")

        # Channel-specific cancel
        task = self._spam_tasks.get(ctx.channel.id)
        if task and not task.done():
            task.cancel()
            self._spam_tasks.pop(ctx.channel.id, None)
            if task_mgr:
                task_mgr.cancel_by_channel(ctx.channel.id, reason="channel_cancel_command")
            return await ctx.send("🛑 Repeat-message task cancelled.")

        if task_mgr:
            cancelled_id = task_mgr.cancel_by_channel(ctx.channel.id, reason="channel_cancel_command")
            if cancelled_id:
                return await ctx.send(f"🛑 Repeat-message task (`{cancelled_id}`) cancelled.")

        return await ctx.send("There is no repeat-message task running in this channel.")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Cancel task if initiating command message was deleted."""
        task_mgr = self._get_task_manager()
        if task_mgr:
            task_mgr.cancel_by_message_id(payload.message_id, reason="initiating_message_deleted")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Cancel task if initiating command message was deleted."""
        task_mgr = self._get_task_manager()
        if task_mgr:
            task_mgr.cancel_by_message_id(message.id, reason="initiating_message_deleted")

    @commands.command(name="guesshelp", help="Explain number-game rules and host authorization.")
    async def guesshelp(self, ctx: CustomContext):
        embed = discord.Embed(title="🌀 KYŌKA Number Game", color=0x7C3AED, description=(
            f"An authorized host starts a game with `{ctx.prefix}guessanumber 1-10000`. Members type guesses in that same channel.\n\n"
            "• `+` means your guess is lower than the secret number.\n"
            "• `-` means your guess is higher than the secret number.\n"
            "• There is no guess-count limit; the first correct guess wins. The answer is privately DM'd to the host and primary owner.\n"
            "• Only the primary owner or a host on the server allowlist may start a game.\n\n"
            f"Owner allowlist commands: `{ctx.prefix}guesshostadd @member`, `{ctx.prefix}guesshostremove @member`, `{ctx.prefix}guesshosts`."
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

    @commands.command(name="redeem", help="Redeem a KYOKA license key for yourself or this server.")
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
        embed = discord.Embed(
            title="🌀 Aizen's Fun Commands",
            description=(
                "`slap/hug/pat/kiss/bonk/cuddle/poke/highfive/kill @user` · "
                "`roast/compliment @user` · `ship @user [@user]`\n"
                f"`{ctx.prefix}games` — Interactive games\n"
                f"`{ctx.prefix}guessanumber 1-1000` — Number game with unlimited guesses\n"
                f"`{ctx.prefix}guessstatus` · `{ctx.prefix}guesscancel` · `{ctx.prefix}premium`\n\n"
                "Use the main `help` command for the full command menu."
            ),
            color=0x7C3AED,
        )
        embed.set_footer(text="Made by Aizen • Support server linked in botinfo")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
