from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import OWNER_ID
from src.utils.containers import KyokaContainer, send_container_response

logger = logging.getLogger("Kyoka.Moderation.FakeBan")
SIMULATION_COOLDOWN_SECONDS = 10


class FakeBan(commands.Cog):
    """Realistic fake-ban prank module that mimics authentic moderation bans."""

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
            return {"enabled": True, "channel_id": None, "send_dm": True}
        try:
            data = json.loads(row["value"])
            if isinstance(data, dict):
                return {
                    "enabled": bool(data.get("enabled", True)),
                    "channel_id": data.get("channel_id"),
                    "send_dm": bool(data.get("send_dm", True)),
                }
        except (TypeError, ValueError):
            pass
        return {"enabled": True, "channel_id": None, "send_dm": True}

    async def _save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.bot.db.execute(
            """INSERT INTO system_state (key, value) VALUES (?, ?)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            self._state_key(guild_id),
            json.dumps(settings, separators=(",", ":")),
        )

    def _render_real_ban_card(
        self, target: discord.abc.User | discord.Member, actor: discord.abc.User, reason: str
    ) -> KyokaContainer:
        """Create a 100% authentic Kyoka ban announcement card matching the real ban system."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "•"
        target_name = getattr(target, "display_name", getattr(target, "name", str(target)))
        actor_name = getattr(actor, "display_name", getattr(actor, "name", str(actor)))

        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Member Banned**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{target_name}** `「{target.id}」`\n"
            f"{dot} **Moderator:** **{actor_name}**\n"
            f"{dot} **Reason:** `{reason}`"
        )
        return container

    def _render_ban_dm(
        self, guild_name: str, actor: discord.abc.User, reason: str
    ) -> KyokaContainer:
        """Create a 100% authentic DM notice matching the real ban system."""
        dm_container = KyokaContainer(accent_color=None)
        dm_container.add_section(
            content=(
                f"**You were banned from {guild_name}**\n"
                f"> Moderator: **{actor}**\n"
                f"> Reason: `{reason}`"
            )
        )
        return dm_container

    async def _execute_fakeban(
        self,
        ctx: CustomContext,
        target: discord.Member,
        reason: str,
        *,
        send_dm: bool = True,
    ) -> None:
        guild = ctx.guild
        if not guild:
            await ctx.send_error("Fake-ban commands are available only in a server.")
            return

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

        clean_reason = reason.strip() or "Violating server rules and guidelines"

        # 1. Deliver DM to target if enabled (identical to real ban)
        should_dm = send_dm and settings.get("send_dm", True)
        if should_dm:
            try:
                dm_card = self._render_ban_dm(guild.name, ctx.author, clean_reason)
                await send_container_response(target, dm_card)
            except Exception:
                pass

        # 2. Render and send authentic ban announcement into the channel
        ban_card = self._render_real_ban_card(target, ctx.author, clean_reason)

        if ctx.interaction:
            # If triggered via slash command in the target channel, respond directly
            if ctx.channel.id == target_channel.id:
                await send_container_response(ctx, ban_card)
                # Send private secret ephemeral reassurance to mod
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
            # If command was invoked in a different channel than target_channel
            if target_channel.id != ctx.channel.id:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass

        logger.info(
            "Fake-ban realistic execution: guild=%s actor=%s target=%s dm=%s",
            guild.id,
            ctx.author.id,
            target.id,
            should_dm,
        )

    @commands.hybrid_group(
        name="fakeban",
        invoke_without_command=True,
        description="Trigger an authentic-looking fake ban prank (does not actually ban).",
    )
    @app_commands.describe(
        member="Target member to fake ban",
        reason="Reason for the fake ban",
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
            container.add_section(content="**🎭 Fake Ban System**")
            container.add_separator(divider=True)
            container.add_text(
                f"Create authentic-looking ban announcements and DMs to prank your friends without touching their server membership!\n\n"
                f"• `{p}fakeban @member [reason]` — Post authentic ban announcement\n"
                f"• `{p}fakeban dm @member [reason]` — Post ban card and send realistic ban DM\n"
                f"• `{p}fakeban reveal @member` — Reveal that the ban was a prank\n"
                f"• `{p}fakeban setup #channel` — Set dedicated ban announcement channel\n"
                f"• `{p}fakeban enable / disable` — Toggle the prank module\n"
                f"• `{p}fakeban preview` — Preview the authentic ban card"
            )
            await send_container_response(ctx, container)
            return

        await self._execute_fakeban(ctx, member, reason, send_dm=False)

    @fakeban.command(name="dm", description="Post authentic ban notice and dispatch a realistic ban DM to the member.")
    @app_commands.describe(member="Member to fake ban", reason="Reason for the ban")
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
        container = KyokaContainer(accent_color=None)
        container.add_section(content="**🎭 Prank Revealed!**")
        container.add_separator(divider=True)
        container.add_text(
            f"**Relax everyone!** {member.mention} was **never** actually banned from the server!\n"
            f"> The previous ban notice was a harmless simulation prank orchestrated by **{ctx.author.display_name}**."
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
        )
        await send_container_response(ctx, sample_card)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FakeBan(bot))
