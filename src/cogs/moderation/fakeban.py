from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import OWNER_ID
from src.utils.containers import KyokaContainer, send_container_response

logger = logging.getLogger("Kyoka.Moderation.FakeBan")


def parse_fakeban_duration(text: str) -> tuple[Optional[str], str]:
    """Extract optional duration (e.g. 7d, 24h, 30m, 3 days) from reason text."""
    clean = text.strip()
    match = re.match(r"^(\d+)\s*([smhdw]|days?|hours?|mins?|minutes?|weeks?|secs?|seconds?)\s*(.*)$", clean, re.IGNORECASE)
    if match:
        val = match.group(1)
        unit = match.group(2).lower()
        rest = match.group(3).strip() or "Violating server rules and guidelines"
        if unit.startswith("s"):
            dur_str = f"{val} Second(s)"
        elif unit.startswith("m"):
            dur_str = f"{val} Minute(s)"
        elif unit.startswith("h"):
            dur_str = f"{val} Hour(s)"
        elif unit.startswith("d"):
            dur_str = f"{val} Day(s)"
        elif unit.startswith("w"):
            dur_str = f"{val} Week(s)"
        else:
            dur_str = f"{val} {unit}"
        return dur_str, rest
    return None, clean


class FakeBan(commands.Cog):
    """Ultra-realistic fake-ban prank engine with stealth invocation, voice disconnects, and authentic DMs."""

    category = "🛡️・MODERATION"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cooldowns: dict[int, float] = {}

    @staticmethod
    def _state_key(guild_id: int) -> str:
        return f"fakeban:{guild_id}"

    async def _settings(self, guild_id: int) -> dict[str, Any]:
        row = await self.bot.db.fetch_one(
            "SELECT value FROM system_state WHERE key = ?",
            self._state_key(guild_id),
        )
        if not row or not row.get("value"):
            return {"enabled": True, "channel_id": None, "send_dm": True, "voice_kick": True}
        try:
            data = json.loads(row["value"])
            if isinstance(data, dict):
                return {
                    "enabled": bool(data.get("enabled", True)),
                    "channel_id": data.get("channel_id"),
                    "send_dm": bool(data.get("send_dm", True)),
                    "voice_kick": bool(data.get("voice_kick", True)),
                }
        except (TypeError, ValueError):
            pass
        return {"enabled": True, "channel_id": None, "send_dm": True, "voice_kick": True}

    async def _save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.bot.db.execute(
            """INSERT INTO system_state (key, value) VALUES (?, ?)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            self._state_key(guild_id),
            json.dumps(settings, separators=(",", ":")),
        )

    def _render_real_ban_card(
        self,
        target: discord.abc.User | discord.Member,
        actor: discord.abc.User,
        reason: str,
        duration: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> KyokaContainer:
        """Create a 100% authentic Kyoka ban announcement card matching the real ban system."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "•"
        target_name = getattr(target, "display_name", getattr(target, "name", str(target)))
        actor_name = getattr(actor, "display_name", getattr(actor, "name", str(actor)))
        cid = case_id or f"#B-{random.randint(1000, 9999)}"

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Member Banned**")
        container.add_separator(divider=True)

        lines = [
            f"{dot} **Target:** **{target_name}** `「{target.id}」`",
            f"{dot} **Moderator:** **{actor_name}**",
        ]
        if duration:
            lines.append(f"{dot} **Duration:** `{duration}`")
        lines.append(f"{dot} **Reason:** `{reason}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Timestamp: <t:{int(time.time())}:f> • Case: `{cid}`")
        return container

    def _render_ban_dm(
        self,
        guild: discord.Guild,
        actor: discord.abc.User,
        reason: str,
        duration: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> KyokaContainer:
        """Create a 100% authentic DM notice matching genuine moderation server bans."""
        cid = case_id or f"#B-{random.randint(1000, 9999)}"
        dm_container = KyokaContainer(accent_color=None)
        dm_container.add_section(
            content=(
                f"**You were banned from {guild.name}**\n"
                f"> Moderator: **{actor}**\n"
                + (f"> Duration: `{duration}`\n" if duration else "")
                + f"> Reason: `{reason}`\n"
                f"> Case Reference: `{cid}`\n\n"
                f"-# If you believe this action was issued in error, you may submit an appeal to server administration."
            )
        )
        return dm_container

    async def _execute_fakeban(
        self,
        ctx: CustomContext,
        target: discord.Member,
        raw_reason: str,
        *,
        send_dm: bool = True,
        auto_reveal_seconds: Optional[int] = None,
    ) -> None:
        guild = ctx.guild
        if not guild:
            await ctx.send_error("Fake-ban commands are available only in a server.")
            return

        # 1. Stealth invocation: delete the command message so nobody sees "+fakeban" in chat!
        if ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        bot_id = getattr(self.bot.user, "id", None)
        if target.id in {OWNER_ID, guild.owner_id, bot_id}:
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**Cannot Moderate Member**\n> You cannot fake ban the server owner or bot.")
            await send_container_response(ctx, container)
            return

        if not (ctx.author.guild_permissions.ban_members or ctx.author.guild_permissions.administrator):
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> Ban Members permission is required to run fake ban.")
            await send_container_response(ctx, container)
            return

        settings = await self._settings(guild.id)
        if not settings["enabled"]:
            await ctx.send_error("Fake-ban simulations are disabled in this server. An admin can re-enable with `+fakeban enable`.")
            return

        target_channel = guild.get_channel(settings["channel_id"]) if settings["channel_id"] else ctx.channel
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            target_channel = ctx.channel

        # Parse duration and reveal flags from raw_reason if present
        text = raw_reason.strip()
        reveal_sec = auto_reveal_seconds
        timer_match = re.search(r"--(?:timer|reveal)\s+(\d+)", text, re.IGNORECASE)
        if timer_match:
            reveal_sec = int(timer_match.group(1))
            text = text[:timer_match.start()] + text[timer_match.end():]

        duration_str, clean_reason = parse_fakeban_duration(text.strip())
        if not clean_reason:
            clean_reason = "Violating server rules and guidelines"

        case_id = f"#B-{random.randint(1000, 9999)}"

        # 2. Simulated voice kick if target is in VC (mimics genuine Discord ban behavior)
        if settings.get("voice_kick", True) and target.voice and target.voice.channel:
            try:
                if guild.me.guild_permissions.move_members:
                    await target.move_to(None, reason="Kyoka Moderation: Ban disconnect simulation")
            except Exception:
                pass

        # 3. Deliver DM to target if enabled (100% authentic moderation look)
        should_dm = send_dm and settings.get("send_dm", True)
        if should_dm:
            try:
                dm_card = self._render_ban_dm(guild, ctx.author, clean_reason, duration_str, case_id)
                await send_container_response(target, dm_card)
            except Exception:
                pass

        # 4. Render and broadcast authentic ban announcement card into the channel
        ban_card = self._render_real_ban_card(target, ctx.author, clean_reason, duration_str, case_id)

        if ctx.interaction:
            # Slash command invocation
            if ctx.channel.id == target_channel.id:
                await send_container_response(ctx, ban_card)
                try:
                    await ctx.interaction.followup.send(
                        f"-# 🤫 *[Prank Active: {target.mention} was not actually banned. Use `+fakeban reveal @{target.name}` when ready!]*",
                        ephemeral=True,
                    )
                except Exception:
                    pass
            else:
                await send_container_response(target_channel, ban_card)
                await ctx.send_success(f"Fake ban card posted in {target_channel.mention}.")
        else:
            # Prefix invocation: post realistic card directly to channel
            await send_container_response(target_channel, ban_card)

        # 5. Handle optional auto-reveal timer
        if reveal_sec and reveal_sec > 0:
            asyncio.create_task(
                self._schedule_reveal(target_channel, target, ctx.author, reveal_sec, should_dm)
            )

        logger.info(
            "Fake-ban realistic execution: guild=%s actor=%s target=%s dm=%s reveal=%s",
            guild.id,
            ctx.author.id,
            target.id,
            should_dm,
            reveal_sec,
        )

    async def _schedule_reveal(
        self,
        channel: discord.TextChannel | discord.Thread,
        target: discord.Member,
        actor: discord.abc.User,
        delay_seconds: int,
        dm_target: bool = False,
    ) -> None:
        """Wait for delay then post the prank reveal card in chat and optionally DM the target."""
        await asyncio.sleep(delay_seconds)
        try:
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**🎉 PRANK REVEALED!**")
            container.add_separator(divider=True)
            container.add_text(
                f"**Relax everyone!** {target.mention} was **never** actually banned from the server!\n\n"
                f"> The ban announcement was a harmless simulation prank set up by **{actor.display_name if hasattr(actor, 'display_name') else actor.name}**!\n"
                f"> No moderation actions were taken, and all roles and permissions remain intact. 💜"
            )
            await send_container_response(channel, container)

            if dm_target:
                try:
                    dm_reveal = KyokaContainer(accent_color=None)
                    dm_reveal.add_section(
                        content=(
                            f"**🎉 It Was Just a Prank!**\n"
                            f"> You were **not** actually banned from **{channel.guild.name}**!\n"
                            f"> The ban was a harmless prank orchestrated by **{actor}**."
                        )
                    )
                    await send_container_response(target, dm_reveal)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Error delivering scheduled fakeban reveal: %s", e)

    @commands.hybrid_group(
        name="fakeban",
        invoke_without_command=True,
        description="Trigger an authentic-looking fake ban prank (does not actually ban).",
    )
    @app_commands.describe(
        member="Target member to fake ban",
        reason="Reason and optional duration (e.g. '7d spamming' or '--timer 30')",
    )
    @commands.guild_only()
    async def fakeban(
        self,
        ctx: CustomContext,
        member: discord.Member | None = None,
        *,
        reason: str = "Violating server rules and guidelines",
    ) -> None:
        """Trigger an authentic-looking fake ban announcement without actually banning the member."""
        if not member:
            p = ctx.prefix
            container = KyokaContainer(accent_color=None)
            container.add_section(content="**🎭 Ultra-Realistic Fake Ban System**")
            container.add_separator(divider=True)
            container.add_text(
                f"Create authentic-looking ban announcements and DMs to prank your friends without touching their server membership!\n\n"
                f"• `{p}fakeban @member [reason]` — Post authentic ban announcement *(stealth deletes command)*\n"
                f"• `{p}fakeban @member 7d [reason]` — Post ban card with simulated duration\n"
                f"• `{p}fakeban @member [reason] --timer 30` — Auto-reveal after 30 seconds\n"
                f"• `{p}fakeban dm @member [reason]` — Post ban card and dispatch realistic DM\n"
                f"• `{p}fakeban reveal @member` — Reveal that the ban was a prank\n"
                f"• `{p}fakeban setup #channel` — Set dedicated ban announcement channel\n"
                f"• `{p}fakeban enable / disable` — Toggle the prank module\n"
                f"• `{p}fakeban preview` — Preview the authentic ban card"
            )
            await send_container_response(ctx, container)
            return

        await self._execute_fakeban(ctx, member, reason, send_dm=False)

    @fakeban.command(name="dm", description="Post authentic ban notice and dispatch a realistic ban DM to the member.")
    @app_commands.describe(member="Member to fake ban", reason="Reason for the ban (e.g. '7d rule violation --timer 60')")
    @commands.has_permissions(ban_members=True)
    async def fakeban_dm(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "Violating server rules and guidelines",
    ) -> None:
        """Post a realistic ban card and send an authentic ban notice directly to the member's DMs."""
        await self._execute_fakeban(ctx, member, reason, send_dm=True)

    @fakeban.command(name="reveal", aliases=["unmask", "prank"], description="Reveal that a previous ban on a member was just a harmless prank.")
    @app_commands.describe(member="Member to reveal the prank for")
    @commands.has_permissions(ban_members=True)
    async def fakeban_reveal(self, ctx: CustomContext, member: discord.Member) -> None:
        """Reveal that the ban on the specified member was a prank simulation."""
        # Stealth delete invoking command message
        if ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**🎉 PRANK REVEALED!**")
        container.add_separator(divider=True)
        container.add_text(
            f"**Relax everyone!** {member.mention} was **never** actually banned from the server!\n\n"
            f"> The previous ban notice was a harmless simulation prank orchestrated by **{ctx.author.display_name}**!\n"
            f"> No moderation actions were taken, and all roles and permissions remain intact. 💜"
        )
        await send_container_response(ctx, container)

    @fakeban.command(name="setup", description="Configure the channel where fake ban notices are broadcast.")
    @app_commands.describe(channel="Channel for fake ban announcements")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_setup(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Choose the channel used for fake-ban announcements."""
        if not ctx.guild:
            return
        settings = await self._settings(ctx.guild.id)
        settings.update({"enabled": True, "channel_id": channel.id})
        await self._save_settings(ctx.guild.id, settings)
        await ctx.send_success(f"Fake-ban announcements will now be posted in {channel.mention}.")

    @fakeban.command(name="enable", description="Enable fake-ban announcements in this server.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_enable(self, ctx: CustomContext) -> None:
        """Enable fake-ban prank commands in this server."""
        if not ctx.guild:
            return
        settings = await self._settings(ctx.guild.id)
        settings["enabled"] = True
        await self._save_settings(ctx.guild.id, settings)
        await ctx.send_success("Fake-ban commands are now **enabled** in this server.")

    @fakeban.command(name="disable", description="Disable fake-ban announcements in this server.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_disable(self, ctx: CustomContext) -> None:
        """Disable fake-ban prank commands in this server."""
        if not ctx.guild:
            return
        settings = await self._settings(ctx.guild.id)
        settings["enabled"] = False
        await self._save_settings(ctx.guild.id, settings)
        await ctx.send_success("Fake-ban commands are now **disabled**.")

    @fakeban.command(name="preview", description="Preview what the authentic ban announcement looks like.")
    @commands.has_permissions(ban_members=True)
    async def fakeban_preview(self, ctx: CustomContext) -> None:
        """Preview the realistic ban card with sample data."""
        sample_card = self._render_real_ban_card(
            target=ctx.author,
            actor=self.bot.user or ctx.author,
            reason="Violating server rules and guidelines [Preview]",
            duration="7 Day(s)",
            case_id="#B-7741",
        )
        await send_container_response(ctx, sample_card)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FakeBan(bot))
