from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.gif_manager import GIFManager
from src.security.owner import is_owner_or_staff

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.LastToLeaveVC")
PURPLE = 0x7C3AED
CYAN = 0x06B6D4
GOLD = 0xF59E0B
GREEN = 0x10B981


def format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration (e.g. 1h 24m 12s, 4m 32s, 45s)."""
    sec = max(0, int(seconds))
    if sec < 60:
        return f"{sec}s"
    mins, s = divmod(sec, 60)
    if mins < 60:
        return f"{mins}m {s:02d}s"
    hrs, m = divmod(mins, 60)
    return f"{hrs}h {m:02d}m {s:02d}s"


@dataclass
class EliminationRecord:
    user_id: int
    display_name: str
    mention: str
    left_at: float
    survived_seconds: float
    order: int


@dataclass
class LastToLeaveGame:
    guild_id: int
    voice_channel_id: int
    text_channel_id: int
    host_id: int
    start_time: float
    contestants: dict[int, str] = field(default_factory=dict)  # user_id -> display_name
    remaining: set[int] = field(default_factory=set)          # user_ids still in VC
    eliminated: list[EliminationRecord] = field(default_factory=list) # people who left in order
    is_active: bool = True


class LastToLeaveVC(commands.Cog):
    """
    Last To Leave VC (LTLVC) — Competitive Discord Voice Survival Mini-Game.
    Bot joins the voice channel, starts a live survival timer, tracks every member who leaves,
    and crowns the last remaining person as the champion!
    """
    category = "Games"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.gif_manager = GIFManager()
        # guild_id -> LastToLeaveGame
        self.active_games: dict[int, LastToLeaveGame] = {}

    def get_game(self, guild_id: int) -> Optional[LastToLeaveGame]:
        """Fetch active game for guild."""
        return self.active_games.get(guild_id)

    # ─── MASTER COMMAND GROUP: ?ltlvc ────────────────────────────────────────

    @commands.group(
        name="ltlvc",
        aliases=["ltl", "lasttoleave", "lasttoleavevc"],
        invoke_without_command=True,
        help="Last To Leave VC challenge: bot joins, starts timer, and tracks who left.",
    )
    @commands.guild_only()
    async def ltlvc(self, ctx: CustomContext) -> None:
        """View active game status, or view rules and instructions if no game is running."""
        game = self.get_game(ctx.guild.id)
        if game and game.is_active:
            await self._send_game_status(ctx, game)
        else:
            await self._send_game_overview(ctx)

    async def _send_game_overview(self, ctx: CustomContext) -> None:
        """Send game overview and tutorial when no game is active."""
        p = ctx.prefix
        embed = discord.Embed(
            title="🎙️ Last To Leave VC (LTLVC) — Voice Survival Challenge",
            description=(
                "**The rules are simple: the last person remaining in the voice channel wins!**\n\n"
                "**How It Works:**\n"
                f"1. Gather everyone in a voice channel.\n"
                f"2. Run `{p}ltlvc start` — the bot joins the VC and starts the survival timer!\n"
                f"3. When anyone leaves the voice channel, the bot records who left and their survival time.\n"
                f"4. Type `{p}ltlvc` at any time to see the people who left and who is still holding on!\n"
                f"5. When only one person remains, the bot announces the **WINNER** with a celebration card! 🏆\n\n"
                "**Game Commands:**\n"
                f"• `{p}ltlvc start [#channel]` — Start the game in your voice channel\n"
                f"• `{p}ltlvc` or `{p}ltlvc status` — View elapsed timer, remaining members, and who left\n"
                f"• `{p}ltlvc stop` — End the game manually\n"
                f"• `{p}ltlvc reset` — Force reset active game"
            ),
            color=PURPLE,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Join a voice channel and type {p}ltlvc start")
        await ctx.send(embed=embed)

    async def _send_game_status(self, ctx: CustomContext, game: LastToLeaveGame) -> None:
        """Send live game status showing elapsed timer, who is in VC, and who left."""
        elapsed_sec = time.time() - game.start_time
        elapsed_str = format_duration(elapsed_sec)
        start_ts = int(game.start_time)

        embed = discord.Embed(
            title="🎙️ Last To Leave VC — Live Game Status",
            color=CYAN,
        )
        embed.add_field(
            name="⏱️ Survival Timer",
            value=f"**{elapsed_str}** elapsed\n*(Started <t:{start_ts}:R>)*",
            inline=True,
        )
        embed.add_field(
            name="🔊 Voice Channel",
            value=f"<#{game.voice_channel_id}>",
            inline=True,
        )
        embed.add_field(
            name="👑 Host",
            value=f"<@{game.host_id}>",
            inline=True,
        )

        # 1. Remaining Contestants
        if game.remaining:
            remaining_lines = []
            for uid in sorted(game.remaining):
                name = game.contestants.get(uid, f"User {uid}")
                remaining_lines.append(f"• <@{uid}> (`{name}`) — *Holding strong!*")
            rem_text = "\n".join(remaining_lines[:15])
            if len(remaining_lines) > 15:
                rem_text += f"\n*...and {len(remaining_lines) - 15} more*"
        else:
            rem_text = "*No contestants currently remaining.*"

        embed.add_field(
            name=f"👥 Contestants Remaining in VC ({len(game.remaining)}/{len(game.contestants)})",
            value=rem_text,
            inline=False,
        )

        # 2. People Who Left
        if game.eliminated:
            elim_lines = []
            for rec in game.eliminated:
                surv = format_duration(rec.survived_seconds)
                elim_lines.append(f"`#{rec.order}` <@{rec.user_id}> — **Left after {surv}**")
            elim_text = "\n".join(elim_lines[:15])
            if len(elim_lines) > 15:
                elim_text += f"\n*...and {len(elim_lines) - 15} more*"
        else:
            elim_text = "✨ *No one has left yet! All contestants are still in the voice channel.*"

        embed.add_field(
            name=f"🚪 People Who Left VC ({len(game.eliminated)})",
            value=elim_text,
            inline=False,
        )

        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Type {ctx.prefix}ltlvc stop to conclude")
        await ctx.send(embed=embed)

    # ─── SUBCOMMAND: ?ltlvc start ────────────────────────────────────────────

    @ltlvc.command(name="start", help="Start Last To Leave VC in your current voice channel.")
    @commands.guild_only()
    async def ltlvc_start(self, ctx: CustomContext, channel: Optional[discord.VoiceChannel] = None) -> None:
        """Start the challenge: bot joins the voice channel and begins tracking members."""
        existing = self.get_game(ctx.guild.id)
        if existing and existing.is_active:
            return await ctx.send(
                f"⚠️ A Last To Leave VC game is already running in <#{existing.voice_channel_id}>!\n"
                f"Type `{ctx.prefix}ltlvc` to view status or `{ctx.prefix}ltlvc stop` to conclude it."
            )

        target_channel: discord.VoiceChannel | None = channel
        if not target_channel and ctx.author.voice and ctx.author.voice.channel:
            if isinstance(ctx.author.voice.channel, discord.VoiceChannel):
                target_channel = ctx.author.voice.channel

        if not target_channel:
            return await ctx.send(
                f"❌ You must be connected to a voice channel or mention one!\n"
                f"Usage: `{ctx.prefix}ltlvc start` or `{ctx.prefix}ltlvc start #voice-channel`"
            )

        # Gather contestants currently in VC (exclude bots)
        contestants: dict[int, str] = {
            m.id: m.display_name for m in target_channel.members if not m.bot
        }

        if len(contestants) == 0:
            return await ctx.send(
                f"❌ There are no human members in {target_channel.mention}!\n"
                "Have members join the voice channel before starting."
            )

        # Connect bot to voice channel
        try:
            if ctx.guild.voice_client:
                if ctx.guild.voice_client.channel.id != target_channel.id:
                    await ctx.guild.voice_client.move_to(target_channel)
            else:
                await target_channel.connect(timeout=10.0, reconnect=False)
        except (discord.DiscordException, asyncio.TimeoutError):
            logger.exception(
                "Could not join voice channel %s for Last To Leave game in guild %s",
                target_channel.id,
                ctx.guild.id,
            )
            return await ctx.send_error(
                f"I couldn't join {target_channel.mention}. Check my Connect and Speak permissions, then try again."
            )

        # Initialize game
        game = LastToLeaveGame(
            guild_id=ctx.guild.id,
            voice_channel_id=target_channel.id,
            text_channel_id=ctx.channel.id,
            host_id=ctx.author.id,
            start_time=time.time(),
            contestants=contestants,
            remaining=set(contestants.keys()),
            eliminated=[],
            is_active=True,
        )
        self.active_games[ctx.guild.id] = game

        contestant_mentions = ", ".join(f"<@{uid}>" for uid in contestants.keys())
        embed = discord.Embed(
            title="🎙️ Last To Leave VC — Game Started!",
            description=(
                f"The challenge has begun in **{target_channel.mention}**!\n"
                f"The bot has joined and the timer is running.\n\n"
                f"👥 **Contestants ({len(contestants)}):**\n"
                f"> {contestant_mentions}\n\n"
                f"⏱️ **The last person in the VC wins!**\n"
                f"Type `{ctx.prefix}ltlvc` at any time to see the timer and who has left."
            ),
            color=GREEN,
        )
        if len(contestants) == 1:
            embed.set_footer(text="⚠️ Only 1 contestant detected. Invite friends to join the challenge!")
        else:
            embed.set_footer(text=f"Started by {ctx.author.display_name} • May the best survive!")

        await ctx.send(embed=embed)

    # ─── SUBCOMMAND: ?ltlvc status ───────────────────────────────────────────

    @ltlvc.command(name="status", aliases=["info", "list", "wholeft"], help="Show who has left and who is still remaining.")
    @commands.guild_only()
    async def ltlvc_status(self, ctx: CustomContext) -> None:
        """Display the timer, remaining contestants, and full list of people who left."""
        game = self.get_game(ctx.guild.id)
        if not game or not game.is_active:
            return await ctx.send(f"❌ No Last To Leave VC game is currently running. Start one with `{ctx.prefix}ltlvc start`!")
        await self._send_game_status(ctx, game)

    # ─── SUBCOMMAND: ?ltlvc stop ─────────────────────────────────────────────

    @ltlvc.command(name="stop", aliases=["end", "cancel"], help="End the current Last To Leave VC game.")
    @commands.guild_only()
    async def ltlvc_stop(self, ctx: CustomContext) -> None:
        """Conclude the game and display the final survival summary."""
        game = self.get_game(ctx.guild.id)
        if not game or not game.is_active:
            return await ctx.send("❌ No Last To Leave VC game is currently active.")

        # Permissions check: host, manage_channels, or administrator
        is_host = ctx.author.id == game.host_id
        is_mod = (
            is_owner_or_staff(ctx.author.id)
            or ctx.author.guild_permissions.manage_channels
            or ctx.author.guild_permissions.administrator
            or ctx.author.guild_permissions.manage_guild
        )
        if not (is_host or is_mod):
            return await ctx.send(f"❌ Only the game host (<@{game.host_id}>) or a server moderator can stop the game.")

        game.is_active = False
        self.active_games.pop(ctx.guild.id, None)

        # Disconnect bot from VC
        if ctx.guild.voice_client:
            try:
                await ctx.guild.voice_client.disconnect(force=True)
            except Exception:
                pass

        elapsed_str = format_duration(time.time() - game.start_time)
        embed = discord.Embed(
            title="🛑 Last To Leave VC — Game Ended",
            description=(
                f"The challenge was concluded by {ctx.author.mention}.\n"
                f"⏱️ **Total Runtime:** `{elapsed_str}`\n\n"
                f"👥 **Contestants Still in VC ({len(game.remaining)}):**\n"
                + (", ".join(f"<@{u}>" for u in game.remaining) if game.remaining else "*None*")
                + f"\n\n🚪 **People Who Left ({len(game.eliminated)}):**\n"
                + (
                    "\n".join(
                        f"`#{rec.order}` <@{rec.user_id}> — Left after {format_duration(rec.survived_seconds)}"
                        for rec in game.eliminated
                    )
                    if game.eliminated
                    else "*No one left before the game was stopped!*"
                )
            ),
            color=PURPLE,
        )
        await ctx.send(embed=embed)

    # ─── SUBCOMMAND: ?ltlvc reset ────────────────────────────────────────────

    @ltlvc.command(name="reset", help="Admin: force reset any active Last To Leave game.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_channels=True)
    async def ltlvc_reset(self, ctx: CustomContext) -> None:
        """Force cancel any active game and disconnect the bot."""
        self.active_games.pop(ctx.guild.id, None)
        if ctx.guild.voice_client:
            try:
                await ctx.guild.voice_client.disconnect(force=True)
            except Exception:
                pass
        await ctx.send("✅ Last To Leave VC game state has been reset.")

    # ─── VOICE STATE LISTENER ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Detect when members leave the voice channel and track eliminations."""
        if member.bot or member.guild is None:
            return

        game = self.active_games.get(member.guild.id)
        if not game or not game.is_active:
            return

        # Check if member was in the active game voice channel and left
        was_in_vc = before.channel and before.channel.id == game.voice_channel_id
        is_still_in_vc = after.channel and after.channel.id == game.voice_channel_id

        if was_in_vc and not is_still_in_vc:
            if member.id in game.remaining:
                game.remaining.discard(member.id)
                survived_sec = time.time() - game.start_time
                order = len(game.eliminated) + 1

                record = EliminationRecord(
                    user_id=member.id,
                    display_name=member.display_name,
                    mention=member.mention,
                    left_at=time.time(),
                    survived_seconds=survived_sec,
                    order=order,
                )
                game.eliminated.append(record)

                text_ch = self.bot.get_channel(game.text_channel_id)
                surv_str = format_duration(survived_sec)

                # Send elimination announcement
                if text_ch and isinstance(text_ch, discord.TextChannel):
                    try:
                        await text_ch.send(
                            f"🚪 **{member.display_name}** has left the voice channel! "
                            f"(Eliminated `#{order}` • Survived `{surv_str}`)"
                        )
                    except Exception as e:
                        logger.debug(f"Could not send elimination notice: {e}")

                # Check for WINNER condition (1 contestant remaining)
                if len(game.remaining) == 1 and len(game.contestants) > 1:
                    winner_id = next(iter(game.remaining))
                    winner_member = member.guild.get_member(winner_id)
                    total_survived = time.time() - game.start_time
                    total_str = format_duration(total_survived)

                    # Build winner embed
                    embed = discord.Embed(
                        title="🏆 LAST TO LEAVE VC — WE HAVE A WINNER!",
                        description=(
                            f"🎉 Congratulations to {winner_member.mention if winner_member else f'<@{winner_id}>'}!\n"
                            f"👑 You outlasted everyone and are the **LAST TO LEAVE THE VOICE CHANNEL!**\n\n"
                            f"⏱️ **Total Time Survived:** `{total_str}`\n\n"
                            f"📊 **Elimination Leaderboard (People Who Left):**\n"
                            + "\n".join(
                                f"`#{rec.order}` <@{rec.user_id}> — Left after {format_duration(rec.survived_seconds)}"
                                for rec in reversed(game.eliminated)
                            )
                        ),
                        color=GOLD,
                    )
                    embed.set_footer(text=f"Server: {member.guild.name} • Thank you all for playing!")
                    gif_url = await self.gif_manager.get_action_gif("celebrate")
                    if gif_url:
                        embed.set_image(url=gif_url)

                    game.is_active = False
                    self.active_games.pop(member.guild.id, None)

                    if text_ch and isinstance(text_ch, discord.TextChannel):
                        try:
                            await text_ch.send(embed=embed)
                        except Exception as e:
                            logger.debug(f"Could not send winner embed: {e}")

                    # Disconnect bot from VC
                    if member.guild.voice_client:
                        try:
                            await member.guild.voice_client.disconnect(force=True)
                        except Exception:
                            pass

                elif len(game.remaining) == 0:
                    # All members left
                    game.is_active = False
                    self.active_games.pop(member.guild.id, None)
                    if text_ch and isinstance(text_ch, discord.TextChannel):
                        try:
                            await text_ch.send("🏁 Everyone has left the voice channel! Last To Leave VC game concluded.")
                        except Exception:
                            pass
                    if member.guild.voice_client:
                        try:
                            await member.guild.voice_client.disconnect(force=True)
                        except Exception:
                            pass


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(LastToLeaveVC(bot))
