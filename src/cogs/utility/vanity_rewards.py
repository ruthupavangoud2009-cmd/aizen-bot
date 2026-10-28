"""
Kyoka 3.0 - Vanity Status Role Rewards
Inspired by Greed bot's Vanity Rewards automation.
Monitors Discord member custom statuses and automatically awards vanity roles to users repping the server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class VanityRewards(commands.Cog, name="Utility-VanityRewards"):
    """
    Greed-style Vanity Status Role Rewards.
    Automatically assigns a supporter role when members set the server vanity or invite code in their Discord status.
    """
    category = "💎・SERVER PERKS & UTILITY"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._cache: Dict[int, Dict[str, Any]] = {}

    async def cog_load(self) -> None:
        """Initialize database table for vanity rewards settings and load memory cache."""
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_vanity_rewards (
                        guild_id BIGINT PRIMARY KEY,
                        vanity_string TEXT,
                        role_id BIGINT,
                        channel_id BIGINT,
                        message TEXT,
                        enabled BOOLEAN DEFAULT TRUE,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            except Exception:
                pass
        await self._load_cache()

    async def _load_cache(self) -> None:
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "fetch_all"):
            try:
                rows = await self.bot.db.fetch_all("SELECT * FROM guild_vanity_rewards WHERE enabled = TRUE;")
                for r in rows:
                    self._cache[r["guild_id"]] = {
                        "vanity_string": r["vanity_string"].lower() if r.get("vanity_string") else "",
                        "role_id": r["role_id"],
                        "channel_id": r.get("channel_id"),
                        "message": r.get("message"),
                    }
            except Exception:
                pass

    def _get_status_text(self, member: discord.Member) -> str:
        """Extract custom status text from member activities."""
        for act in member.activities:
            if isinstance(act, discord.CustomActivity) and act.name:
                return act.name.lower()
        return ""

    # ─── PRESENCE LISTENER ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detect when a member adds or removes the server vanity from their custom status."""
        guild = after.guild
        if not guild or after.bot:
            return

        cfg = self._cache.get(guild.id)
        if not cfg or not cfg.get("vanity_string") or not cfg.get("role_id"):
            return

        vanity_str = cfg["vanity_string"]
        role = guild.get_role(cfg["role_id"])
        if not role or getattr(role, "position", 0) >= getattr(guild.me.top_role, "position", 0):
            return

        before_status = self._get_status_text(before)
        after_status = self._get_status_text(after)

        has_in_before = vanity_str in before_status
        has_in_after = vanity_str in after_status

        # 1. Added vanity to status
        if not has_in_before and has_in_after:
            if role not in after.roles:
                try:
                    await after.add_roles(role, reason=f"Vanity Status Reward: Repping '{vanity_str}'")
                    # Optional notification channel
                    if cfg.get("channel_id"):
                        ch = guild.get_channel(cfg["channel_id"])
                        if ch and isinstance(ch, (discord.TextChannel, discord.Thread)):
                            custom_msg = cfg.get("message") or "Thank you for repping the server in your status!"
                            container = KyokaContainer(accent_color=None)
                            container.add_text(f"**💖 Vanity Status Reward • {after.display_name}**")
                            container.add_separator(divider=True)
                            container.add_text(f"{after.mention} {custom_msg}\n> Awarded {role.mention}!")
                            container.add_separator(divider=True)
                            await ch.send(embed=container.build())
                except Exception:
                    pass

        # 2. Removed vanity from status
        elif has_in_before and not has_in_after:
            if role in after.roles:
                try:
                    await after.remove_roles(role, reason=f"Vanity Status Reward: Removed '{vanity_str}' from status")
                except Exception:
                    pass

    # ─── COMMAND GROUP ────────────────────────────────────────────────────────

    @commands.group(
        name="vanityrewards",
        aliases=["vanityrole", "vr", "vanitystatus"],
        invoke_without_command=True,
        description="Greed-style automated vanity status role rewards.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def vanity_group(self, ctx: CustomContext) -> None:
        """Display vanity status rewards configuration."""
        p = ctx.clean_prefix
        cfg = self._cache.get(ctx.guild.id)
        status_line = "🔴 Not Configured"
        if cfg and cfg.get("vanity_string") and cfg.get("role_id"):
            role = ctx.guild.get_role(cfg["role_id"])
            role_mention = role.mention if role else "`Deleted Role`"
            status_line = f"🟢 Active: Repping `{cfg['vanity_string']}` awards {role_mention}"

        container = KyokaContainer(accent_color=None)
        container.add_text("**💎 Vanity Status Role Rewards**")
        container.add_separator(divider=True)
        container.add_text(
            f"**Current Status:** {status_line}\n\n"
            f"• `{p}vanityrewards set <string> <@role>` — Configure vanity text and award role\n"
            f"• `{p}vanityrewards channel <#channel>` — Set celebration/thank-you channel\n"
            f"• `{p}vanityrewards message <text>` — Set custom thank-you message\n"
            f"• `{p}vanityrewards check [@user]` — Check member status for vanity text\n"
            f"• `{p}vanityrewards reset` — Disable vanity rewards\n\n"
            f"*Example: `{p}vanityrewards set .gg/aizen @VanitySupporter`*"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @vanity_group.command(name="set", help="Configure vanity string and award role.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def cmd_set(self, ctx: CustomContext, vanity_string: str, role: discord.Role) -> None:
        """Configure vanity string and award role."""
        if role >= ctx.guild.me.top_role:
            return await ctx.send_error("I cannot assign this role because it is higher than my highest role!")

        clean_str = vanity_string.lower().strip()
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_vanity_rewards (guild_id, vanity_string, role_id, enabled)
                    VALUES (?, ?, ?, TRUE)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        vanity_string = EXCLUDED.vanity_string,
                        role_id = EXCLUDED.role_id,
                        enabled = TRUE,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    ctx.guild.id,
                    clean_str,
                    role.id,
                )
            except Exception:
                pass

        self._cache[ctx.guild.id] = {
            "vanity_string": clean_str,
            "role_id": role.id,
            "channel_id": self._cache.get(ctx.guild.id, {}).get("channel_id"),
            "message": self._cache.get(ctx.guild.id, {}).get("message"),
        }

        container = KyokaContainer(accent_color=None)
        container.add_text("**✅ Vanity Rewards Configured**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Target String:** `{clean_str}`\n"
            f"• **Award Role:** {role.mention}\n\n"
            f"> Members who set `{clean_str}` in their Discord custom status will automatically receive {role.mention}!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @vanity_group.command(name="channel", help="Set celebration channel for vanity rewards.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def cmd_channel(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Set or clear celebration channel."""
        ch_id = channel.id if channel else None
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute(
                    "UPDATE guild_vanity_rewards SET channel_id = ? WHERE guild_id = ?;",
                    ch_id,
                    ctx.guild.id,
                )
            except Exception:
                pass

        if ctx.guild.id in self._cache:
            self._cache[ctx.guild.id]["channel_id"] = ch_id

        container = KyokaContainer(accent_color=None)
        if channel:
            container.add_text(f"**📢 Vanity Celebration Channel Set to {channel.mention}**")
        else:
            container.add_text("**📢 Vanity Celebration Channel Cleared (Silent Mode)**")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @vanity_group.command(name="check", help="Check if a member has the vanity string in their status.")
    @commands.guild_only()
    async def cmd_check(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        """Check user status against target vanity string."""
        target = member or ctx.author
        cfg = self._cache.get(ctx.guild.id)
        if not cfg or not cfg.get("vanity_string"):
            return await ctx.send_warning("Vanity rewards are not configured yet on this server.")

        vanity_str = cfg["vanity_string"]
        status_text = self._get_status_text(target)
        has_vanity = vanity_str in status_text

        container = KyokaContainer(accent_color=None)
        container.add_text(f"**🔍 Vanity Status Audit • {target.display_name}**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **Member:** {target.mention}\n"
            f"• **Custom Status:** {f'`{status_text}`' if status_text else '*No Custom Status*'}\n"
            f"• **Required String:** `{vanity_str}`\n"
            f"• **Repping Server:** `{'✅ YES (Eligible for role)' if has_vanity else '❌ NO'}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @vanity_group.command(name="reset", help="Disable vanity rewards.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def cmd_reset(self, ctx: CustomContext) -> None:
        """Disable vanity rewards on this server."""
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "execute"):
            try:
                await self.bot.db.execute("DELETE FROM guild_vanity_rewards WHERE guild_id = ?;", ctx.guild.id)
            except Exception:
                pass
        self._cache.pop(ctx.guild.id, None)

        container = KyokaContainer(accent_color=None)
        container.add_text("**🛑 Vanity Status Rewards Disabled**")
        container.add_separator(divider=True)
        container.add_text("> Vanity status tracking and role distribution have been deactivated.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(VanityRewards(bot))
