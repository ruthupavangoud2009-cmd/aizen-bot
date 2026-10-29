"""Primary-owner-only persistent no-prefix grants.

Usage (configured server prefix or slash commands):
  <prefix>noprefix add @member
  <prefix>noprefix remove @member
  <prefix>noprefix list

Grants are stored in PostgreSQL so they survive bot restarts and deployments.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.security.owner import is_primary_owner

log = logging.getLogger("Kyoka.NoPrefix")


class NoPrefix(commands.Cog):
    """Manage the small, explicit allowlist of users allowed to omit the prefix."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="noprefix",
        description="Owner only: grant, revoke, or list users allowed to use commands without a prefix.",
    )
    @app_commands.describe(
        action="Choose add, remove, or list",
        member="The Discord member to grant or revoke access for",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
    ])
    async def noprefix(
        self,
        ctx: commands.Context,
        action: str,
        member: discord.User | None = None,
    ) -> None:
        """Grant/revoke persistent no-prefix access by Discord user ID."""
        if not is_primary_owner(ctx.author.id):
            await ctx.send("⛔ Only the primary bot owner can manage no-prefix access.", ephemeral=bool(ctx.interaction))
            return

        action = action.strip().lower()
        if action not in {"add", "remove", "list"}:
            await ctx.send("Usage: `noprefix add @member`, `noprefix remove @member`, or `noprefix list`.")
            return

        if action == "list":
            try:
                rows = await self.bot.db.fetch_all(
                    "SELECT user_id, added_by, created_at FROM system_no_prefix ORDER BY created_at ASC;"
                )
            except Exception:
                log.exception("Failed to read persistent no-prefix grants")
                await ctx.send("⚠️ Could not read the no-prefix list because the database query failed.")
                return
            ids = sorted({int(row["user_id"]) for row in rows})
            if not ids:
                await ctx.send("No explicitly granted no-prefix users are saved.")
                return
            lines = [f"• <@{uid}> — `{uid}`" for uid in ids]
            await ctx.send("**Persistent no-prefix users**\n" + "\n".join(lines[:50]))
            return

        if member is None:
            await ctx.send("Please provide a member. Example: `noprefix add @member`.")
            return

        if is_primary_owner(member.id) and action == "remove":
            await ctx.send("The primary owner always retains no-prefix access.")
            return

        try:
            if action == "add":
                await self.bot.db.execute(
                    "INSERT INTO system_no_prefix (user_id, added_by) VALUES (?, ?) ON CONFLICT (user_id) DO NOTHING;",
                    member.id,
                    ctx.author.id,
                )
                self.bot.no_prefix_users.add(member.id)
                await ctx.send(f"✅ Granted persistent no-prefix access to {member.mention} (`{member.id}`).")
            else:
                await self.bot.db.execute(
                    "DELETE FROM system_no_prefix WHERE user_id = ?;",
                    member.id,
                )
                if member.id != ctx.author.id or not is_primary_owner(member.id):
                    self.bot.no_prefix_users.discard(member.id)
                await ctx.send(f"✅ Revoked no-prefix access from {member.mention} (`{member.id}`).")
        except Exception:
            log.exception("Failed to update persistent no-prefix grant for user_id=%s", member.id)
            await ctx.send("⚠️ The database update failed; the in-memory allowlist was not intentionally changed.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NoPrefix(bot))
