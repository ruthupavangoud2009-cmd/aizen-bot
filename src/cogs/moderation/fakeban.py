from __future__ import annotations

import json
import logging
import time
from typing import Any

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.security.owner import OWNER_ID

logger = logging.getLogger("Kyoka.Moderation.FakeBan")
SIMULATION_COOLDOWN_SECONDS = 15


class FakeBan(commands.Cog):
    """Clearly labeled, simulation-only ban pranks; this cog never moderates members."""

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
            return {"enabled": True, "channel_id": None}
        try:
            data = json.loads(row["value"])
        except (TypeError, ValueError) as exc:
            logger.exception("Invalid fake-ban settings for guild %s", guild_id)
            raise RuntimeError("Stored simulation settings are invalid; ask an administrator to reconfigure them.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Stored simulation settings are invalid; ask an administrator to reconfigure them.")
        return {"enabled": bool(data.get("enabled", True)), "channel_id": data.get("channel_id")}

    async def _save_settings(self, guild_id: int, settings: dict[str, Any]) -> None:
        await self.bot.db.execute(
            """INSERT INTO system_state (key, value) VALUES (?, ?)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            self._state_key(guild_id),
            json.dumps(settings, separators=(",", ":")),
        )

    @staticmethod
    def _simulation_embed(target: discord.abc.User, reason: str, actor: discord.abc.User) -> discord.Embed:
        embed = discord.Embed(
            title="🎭 FAKE BAN SIMULATION — NOT A REAL BAN",
            description="This is a prank simulation only. No moderation action was taken, and the member remains in the server.",
            color=0xE0A72E,
        )
        embed.add_field(name="Simulated target", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.add_field(name="Pretend reason", value=discord.utils.escape_markdown(reason[:500]), inline=False)
        embed.set_footer(text=f"Simulation requested by {actor}")
        return embed

    async def _simulate(
        self,
        ctx: CustomContext,
        target: discord.Member,
        reason: str,
        *,
        send_dm: bool = False,
    ) -> None:
        guild = ctx.guild
        if not guild:
            await ctx.send_error("Fake-ban simulations are available only in a server.")
            return
        if target.id in {OWNER_ID, guild.owner_id, getattr(self.bot.user, "id", None)}:
            await ctx.send_error("The bot owner, server owner, and bot itself are protected from fake-ban simulations.")
            return
        if not ctx.author.guild_permissions.ban_members:
            await ctx.send_error("Ban Members permission is required to run a fake-ban simulation.")
            return

        try:
            settings = await self._settings(guild.id)
        except Exception as exc:
            logger.exception("Could not load fake-ban settings for guild %s", guild.id)
            await ctx.send_error(f"Could not load simulation settings: `{exc}`")
            return
        if not settings["enabled"]:
            await ctx.send_error("Fake-ban simulations are disabled in this server.")
            return

        channel = guild.get_channel(settings["channel_id"]) if settings["channel_id"] else ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await ctx.send_error("The configured simulation log channel is unavailable. Reconfigure it with `fakeban setup #channel`.")
            return

        now = time.monotonic()
        if now < self._cooldowns.get(guild.id, 0):
            await ctx.send_error("A fake-ban simulation was used recently. Please wait before trying again.")
            return
        cooldown_until = now + SIMULATION_COOLDOWN_SECONDS
        self._cooldowns[guild.id] = cooldown_until

        embed = self._simulation_embed(target, reason.strip() or "Just a harmless joke.", ctx.author)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException) as exc:
            if self._cooldowns.get(guild.id) == cooldown_until:
                del self._cooldowns[guild.id]
            logger.warning("Fake-ban simulation could not be posted in guild %s: %s", guild.id, exc)
            await ctx.send_error(f"Could not post the simulation notice in {channel.mention}: `{exc}`")
            return

        logger.info(
            "Fake-ban simulation only: guild=%s actor=%s target=%s dm=%s",
            guild.id,
            ctx.author.id,
            target.id,
            send_dm,
        )
        if send_dm:
            try:
                await target.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException) as exc:
                await ctx.send_warning(f"Simulation was logged, but Discord could not DM {target.mention}: `{exc}`")
                return
        await ctx.send_success("Simulation notice posted. No ban or other moderation action was performed.")

    @commands.hybrid_group(
        name="fakeban",
        invoke_without_command=True,
        description="Run a clearly labeled fake-ban simulation; never bans or removes anyone.",
    )
    @commands.guild_only()
    async def fakeban(
        self,
        ctx: CustomContext,
        member: discord.Member | None = None,
        *,
        reason: str = "Just a harmless joke.",
    ) -> None:
        if not member:
            await ctx.send(
                f"**Simulation only:** `{ctx.prefix}fakeban @member [reason]`\n"
                f"Settings: `{ctx.prefix}fakeban setup #channel`, `{ctx.prefix}fakeban enable|disable`, "
                f"`{ctx.prefix}fakeban preview`, `{ctx.prefix}fakeban dm @member [reason]`."
            )
            return
        await self._simulate(ctx, member, reason)

    @fakeban.command(name="dm", description="Post a simulation notice and send it to the target by DM.")
    @commands.has_permissions(ban_members=True)
    async def fakeban_dm(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "Just a harmless joke.",
    ) -> None:
        await self._simulate(ctx, member, reason, send_dm=True)

    @fakeban.command(name="setup", description="Choose the channel used for fake-ban simulation notices.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_setup(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        if not ctx.guild:
            return
        try:
            settings = await self._settings(ctx.guild.id)
            settings.update({"enabled": True, "channel_id": channel.id})
            await self._save_settings(ctx.guild.id, settings)
        except Exception as exc:
            logger.exception("Could not save fake-ban settings for guild %s", ctx.guild.id)
            await ctx.send_error(f"Could not save simulation settings: `{exc}`")
            return
        await ctx.send_success(f"Fake-ban simulation notices will be posted in {channel.mention}.")

    @fakeban.command(name="enable", description="Enable fake-ban simulations in this server.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_enable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        try:
            settings = await self._settings(ctx.guild.id)
            settings["enabled"] = True
            await self._save_settings(ctx.guild.id, settings)
        except Exception as exc:
            logger.exception("Could not enable fake-ban simulations for guild %s", ctx.guild.id)
            await ctx.send_error(f"Could not enable simulations: `{exc}`")
            return
        await ctx.send_success("Fake-ban simulations are enabled. They never perform real moderation actions.")

    @fakeban.command(name="disable", description="Disable fake-ban simulations in this server.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_disable(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        try:
            settings = await self._settings(ctx.guild.id)
            settings["enabled"] = False
            await self._save_settings(ctx.guild.id, settings)
        except Exception as exc:
            logger.exception("Could not disable fake-ban simulations for guild %s", ctx.guild.id)
            await ctx.send_error(f"Could not disable simulations: `{exc}`")
            return
        await ctx.send_success("Fake-ban simulations are disabled.")

    @fakeban.command(name="preview", description="Preview the simulation notice without targeting a member.")
    @commands.has_permissions(manage_guild=True)
    async def fakeban_preview(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            return
        embed = discord.Embed(
            title="🎭 FAKE BAN SIMULATION PREVIEW — NOT A REAL BAN",
            description="This is only a preview. No member was targeted and no moderation action was taken.",
            color=0xE0A72E,
        )
        embed.add_field(name="Pretend reason", value="Just a harmless joke.", inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FakeBan(bot))
