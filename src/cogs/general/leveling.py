from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.canvas import render_rank_card
from src.utils.containers import KyokaContainer, send_container_response
from src.utils.image_tools import download_image_bytes

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.General.Leveling")


class Leveling(commands.Cog, name="General-Leveling"):
    """Server XP, Progression, Rank Cards, and Leaderboards."""
    category: str = "General"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="rank",
        aliases=["level", "lvl", "xp"],
        description="Display your or another member's level, XP, and rank card.",
    )
    @app_commands.describe(member="Member whose rank to inspect (defaults to yourself)")
    async def rank(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member | discord.User] = None,
    ) -> None:
        """Display glassmorphic rank card with progress and server standing."""
        if not ctx.guild:
            return await ctx.send_warning("The rank command can only be used in a server.")

        target = member or ctx.author
        if not isinstance(target, discord.Member):
            target = ctx.guild.get_member(target.id) or target

        # Fetch stats from LevelingManager
        level_mgr = getattr(self.bot, "leveling_mgr", None)
        if not level_mgr:
            return await ctx.send_error("Leveling system is initializing. Please try again shortly.")

        stats = await level_mgr.get_user_rank(ctx.guild.id, target.id)

        # Download avatar bytes for canvas card safely
        avatar_bytes: bytes | None = None
        av_url = str(target.display_avatar.url)
        session = getattr(self.bot, "session", None)
        if session and not session.closed:
            avatar_bytes = await download_image_bytes(av_url, session)

        # Determine accent color from top role or default
        accent_color = None
        if isinstance(target, discord.Member) and target.top_role and target.top_role.color.value != 0:
            accent_color = target.top_role.color.to_rgb()

        # Render rank card in background thread to never block event loop
        buf: io.BytesIO | None = None
        try:
            buf = await asyncio.to_thread(
                render_rank_card,
                avatar_bytes=avatar_bytes,
                username=target.name,
                display_name=target.display_name,
                rank=stats["rank"],
                level=stats["level"],
                current_xp=stats["current_xp"],
                needed_xp=stats["needed_xp"],
                total_xp=stats["total_xp"],
                accent_color=accent_color,
            )
        except Exception as e:
            logger.debug(f"Pillow rank card generation exception (falling back to embed): {e}")

        if buf:
            buf.seek(0)
            file = discord.File(fp=buf, filename=f"rank_{target.id}.png")
            if ctx.interaction:
                if ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(file=file)
                else:
                    await ctx.interaction.response.send_message(file=file)
            else:
                await ctx.send(file=file)
        else:
            # High-fidelity container fallback if Pillow is absent or rendering failed
            pct = min(100, int((stats["current_xp"] / max(1, stats["needed_xp"])) * 100))
            blocks = int(pct / 10)
            bar = "▰" * blocks + "▱" * (10 - blocks)

            container = KyokaContainer()
            container.add_section(
                content=f"# **Rank: {target.display_name}**\n> Server: **{ctx.guild.name}**"
            )
            container.add_separator(divider=True)
            container.add_text(
                f"🏆 **Server Rank:** `#{stats['rank']}`\n"
                f"⭐ **Current Level:** `Level {stats['level']}`\n"
                f"📈 **Level Progress:** `{stats['current_xp']:,} / {stats['needed_xp']:,} XP` ({pct}%)\n"
                f"> `[{bar}]`\n"
                f"✨ **Total Experience:** `{stats['total_xp']:,} XP`"
            )
            container.add_thumbnail(target.display_avatar.url)
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="levels",
        aliases=["xptop", "leveltop", "lb"],
        description="Show the server XP and level leaderboard.",
    )
    @app_commands.describe(limit="Number of members to display (default: 10, max: 25)")
    async def levels_leaderboard(self, ctx: CustomContext, limit: int = 10) -> None:
        """Display server members ranked by total XP."""
        if not ctx.guild:
            return await ctx.send_warning("This command can only be used in a server.")

        level_mgr = getattr(self.bot, "leveling_mgr", None)
        if not level_mgr:
            return await ctx.send_error("Leveling system is initializing.")

        rows = await level_mgr.get_leaderboard(ctx.guild.id, limit=limit)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        container.add_section(
            content=f"# **Progression Leaderboard • {ctx.guild.name}**\n> Ranking members by total experience"
        )
        container.add_separator(divider=True)

        if not rows:
            container.add_text(f"{dot} No members have earned XP in this server yet.")
        else:
            lines = []
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            for idx, r in enumerate(rows, start=1):
                badge = medals.get(idx, f"`#{idx}`")
                lines.append(
                    f"{badge} <@{r['user_id']}> — **Level {r['level']}** (`{r['total_xp']:,} XP`)"
                )
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text("-# Earn XP by actively chatting in server text channels")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="levelconfig",
        description="Configure XP progression settings for this server (Admins only).",
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(
        enabled="Enable or disable XP progression in this server",
        announce="Announce level up messages",
    )
    async def level_config(
        self,
        ctx: CustomContext,
        enabled: Optional[bool] = None,
        announce: Optional[bool] = None,
    ) -> None:
        """View or update server leveling configuration."""
        if not ctx.guild:
            return await ctx.send_warning("This command can only be used in a server.")

        level_mgr = getattr(self.bot, "leveling_mgr", None)
        if not level_mgr:
            return await ctx.send_error("Leveling system is initializing.")

        current = level_mgr.get_guild_settings(ctx.guild.id)
        new_enabled = enabled if enabled is not None else current["enabled"]
        new_announce = announce if announce is not None else current["announce"]

        if enabled is not None or announce is not None:
            await self.bot.db.execute(
                """
                INSERT INTO leveling_settings (guild_id, enabled, announce_level_up, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    announce_level_up = EXCLUDED.announce_level_up,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                ctx.guild.id,
                new_enabled,
                new_announce,
            )
            level_mgr._guild_settings[ctx.guild.id] = {
                **current,
                "enabled": new_enabled,
                "announce": new_announce,
            }
            await ctx.send_success(
                f"Leveling configuration updated:\n"
                f"• XP Progression: **{'Enabled' if new_enabled else 'Disabled'}**\n"
                f"• Level-up Alerts: **{'Enabled' if new_announce else 'Disabled'}**"
            )
        else:
            container = KyokaContainer()
            container.add_section(content=f"**Leveling Settings • {ctx.guild.name}**")
            container.add_separator(divider=True)
            container.add_text(
                f"• **Status:** {'Active (Tracking XP)' if current['enabled'] else 'Disabled'}\n"
                f"• **Level-Up Notifications:** {'Enabled' if current['announce'] else 'Disabled'}\n"
                f"• **Message Cooldown:** `{current['cooldown']} seconds`\n"
                f"• **XP Range per Message:** `{current['min_xp']} - {current['max_xp']} XP`"
            )
            await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Leveling(bot))
