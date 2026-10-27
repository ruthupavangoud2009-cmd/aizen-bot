"""Discord-based website staff management commands.

Enforces:
- Strict authorization: restricted to primary owner (1505515188991033409) or administrators.
- Least-privilege roles: support, senior, admin.
- Persistent database synchronization via website_staff table.
- Comprehensive security audit logging.
- Available via both prefix (+webstaff) and slash (/webstaff) commands.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.security.owner import OWNER_ID, audit, authorize_owner, is_primary_owner

if TYPE_CHECKING:
    from src.core.bot import KyokaBot
    from src.core.context import CustomContext

logger = logging.getLogger("Kyoka.WebStaff")

VALID_ROLE_LEVELS = ("support", "senior", "admin")


class WebStaffCog(commands.Cog, name="WebStaff"):
    """Commands to manage website staff access and permissions from Discord."""
    category = "Developer"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    async def _check_admin_auth(self, ctx: commands.Context) -> bool:
        """Check if caller is primary owner or authorized administrator."""
        if is_primary_owner(ctx.author.id):
            return True

        # Check if caller has administrator permission in a server or is registered admin in website_staff
        if ctx.guild and ctx.author.guild_permissions.administrator:
            # Server admins can view, but only owner or explicitly approved admin staff can manage
            pass

        if hasattr(self.bot, "db") and self.bot.db:
            try:
                row = await self.bot.db.fetch_one(
                    "SELECT role_level FROM website_staff WHERE user_id = $1;",
                    ctx.author.id,
                )
                if row and row.get("role_level") == "admin":
                    return True
            except Exception:
                pass

        # Unauthorized
        await audit(self.bot, ctx.author.id, "webstaff-unauthorized", None, "denied")
        msg = "❌ You are not authorized to manage website staff. Only the Bot Owner or authorized administrators can run this."
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx.interaction.followup.send(msg, ephemeral=True)
        else:
            await ctx.reply(msg, mention_author=False)
        return False

    # ─── HYBRID COMMAND GROUP: +webstaff / /webstaff ─────────────────────────

    @commands.hybrid_group(name="webstaff", aliases=["staff", "addstaff", "web_staff"], description="Manage website staff access from Discord.", invoke_without_command=True)
    async def webstaff_group(self, ctx: commands.Context) -> None:
        """List website staff members."""
        await self.webstaff_list(ctx)

    @webstaff_group.command(name="list", description="List all registered website staff members.")
    async def webstaff_list(self, ctx: commands.Context) -> None:
        """List all registered website staff members."""
        staff_rows = []
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                staff_rows = await self.bot.db.fetch_all(
                    "SELECT user_id, username, role_level, added_by, added_at FROM website_staff ORDER BY added_at ASC;"
                )
            except Exception as e:
                logger.warning(f"Error querying website_staff: {e}")

        embed = discord.Embed(
            title="🛡️ KYOKA 3.0 — Authorized Website Staff",
            description="Members authorized to access ticket administration and staff dashboard.",
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="👑 Authoritative Bot Owner",
            value=f"<@{OWNER_ID}> (`{OWNER_ID}`) — Full Access (Hardcoded)",
            inline=False,
        )

        if staff_rows:
            lines = []
            for r in staff_rows:
                badge = "👑 Admin" if r["role_level"] == "admin" else ("⭐ Senior Staff" if r["role_level"] == "senior" else "🎫 Support Staff")
                lines.append(f"• <@{r['user_id']}> (`{r['user_id']}`) — **{badge}** (Added by <@{r['added_by']}>)")
            embed.add_field(name=f"Configured Staff ({len(staff_rows)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Configured Staff", value="*No additional staff members registered yet.*", inline=False)

        embed.set_footer(text="KYOKA 3.0 • Aizen Edition Dashboard Security")
        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @webstaff_group.command(name="add", description="Grant website staff access to a Discord user.")
    @app_commands.describe(
        user="Discord user to grant staff access",
        role_level="Least-privilege role level (support, senior, admin)",
    )
    async def webstaff_add(
        self,
        ctx: commands.Context,
        user: discord.User,
        role_level: Literal["support", "senior", "admin"] = "support",
    ) -> None:
        """Grant website staff access to a user."""
        if not await self._check_admin_auth(ctx):
            return

        clean_role = role_level.lower().strip()
        if clean_role not in VALID_ROLE_LEVELS:
            clean_role = "support"

        if hasattr(self.bot, "db") and self.bot.db:
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO website_staff (user_id, username, role_level, added_by, added_at, updated_at)
                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        role_level = EXCLUDED.role_level,
                        added_by = EXCLUDED.added_by,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    user.id,
                    str(user.name)[:64],
                    clean_role,
                    ctx.author.id,
                )
            except Exception as e:
                logger.error(f"Failed to persist website staff: {e}")
                msg = f"❌ Database error adding staff: {e}"
                if ctx.interaction:
                    await ctx.interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx.reply(msg, mention_author=False)
                return

        await audit(self.bot, ctx.author.id, "webstaff-add", user.id, "success", f"role={clean_role}")

        embed = discord.Embed(
            title="✅ Website Staff Access Granted",
            description=f"Successfully granted **{clean_role.upper()}** staff privileges to {user.mention}.",
            color=0x10B981,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{user.name} (`{user.id}`)", inline=True)
        embed.add_field(name="Privilege Level", value=f"`{clean_role}`", inline=True)
        embed.add_field(name="Authorized By", value=f"{ctx.author.mention}", inline=True)
        embed.set_footer(text="KYOKA 3.0 Dashboard Staff Registry")

        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    @webstaff_group.command(name="remove", description="Revoke website staff access from a user.")
    @app_commands.describe(user="Discord user to revoke staff access from")
    async def webstaff_remove(self, ctx: commands.Context, user: discord.User) -> None:
        """Revoke website staff access from a user."""
        if not await self._check_admin_auth(ctx):
            return

        if is_primary_owner(user.id):
            msg = "❌ Cannot revoke staff access from the primary bot owner."
            if ctx.interaction:
                await ctx.interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        deleted = False
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                res = await self.bot.db.execute("DELETE FROM website_staff WHERE user_id = $1;", user.id)
                deleted = bool(res and "DELETE 0" not in str(res))
            except Exception as e:
                logger.error(f"Failed to delete website staff: {e}")

        await audit(self.bot, ctx.author.id, "webstaff-remove", user.id, "success")

        embed = discord.Embed(
            title="🗑️ Website Staff Access Revoked",
            description=f"Staff privileges for {user.mention} (`{user.id}`) have been revoked.",
            color=0xEF4444,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Status", value="Removed from website_staff registry." if deleted else "User was not registered.", inline=True)
        embed.add_field(name="Revoked By", value=f"{ctx.author.mention}", inline=True)
        embed.set_footer(text="KYOKA 3.0 Dashboard Staff Registry")

        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(WebStaffCog(bot))
