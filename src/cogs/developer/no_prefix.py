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

from src.security.owner import OWNER_ID, is_primary_owner, is_bot_staff, is_owner_or_staff, get_all_bot_staff

log = logging.getLogger("Kyoka.NoPrefix")


class NoPrefix(commands.Cog):
    """Manage the allowlist of users allowed to omit the prefix."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="noprefix",
        description="Owner and Staff only: grant, revoke, or list users allowed to use commands without a prefix.",
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
        if not is_owner_or_staff(ctx.author.id):
            await ctx.send("⛔ Only the bot owner or authorized bot staff can manage no-prefix access.", ephemeral=bool(ctx.interaction))
            return

        action = action.strip().lower()
        if action in ("grant", "add"):
            action = "add"
        elif action in ("revoke", "remove", "delete"):
            action = "remove"
        elif action in ("list", "show", "all"):
            action = "list"
        else:
            await ctx.send("Usage: `noprefix add @member`, `noprefix remove @member`, or `noprefix list`.")
            return

        if action == "list":
            try:
                rows = await self.bot.db.fetch_all(
                    "SELECT user_id, added_by, created_at FROM system_no_prefix ORDER BY created_at ASC;"
                )
                db_ids = {int(row["user_id"]) for row in rows}
            except Exception:
                log.exception("Failed to read persistent no-prefix grants")
                db_ids = set()

            all_staff = get_all_bot_staff()
            lines = [f"👑 **Primary Owner:** <@{OWNER_ID}> (`{OWNER_ID}`)"]
            if all_staff:
                lines.append(f"🛡️ **Bot Staff ({len(all_staff)}):** " + ", ".join(f"<@{sid}>" for sid in sorted(all_staff)))
            if db_ids:
                lines.append(f"⚡ **Granted Users ({len(db_ids)}):**\n" + "\n".join(f"• <@{uid}> (`{uid}`)" for uid in sorted(db_ids)[:40]))
            else:
                lines.append("⚡ **Granted Users:** None")

            await ctx.send("**No-Prefix Access Allowlist**\n" + "\n".join(lines), allowed_mentions=discord.AllowedMentions.none())
            return

        if member is None:
            await ctx.send("Please provide a member. Example: `noprefix add @member`.")
            return

        if is_primary_owner(member.id):
            if action == "remove":
                await ctx.send("The primary owner has permanent hardcoded no-prefix access and cannot be revoked.")
            else:
                await ctx.send("The primary owner already has permanent hardcoded no-prefix access.")
            return

        if is_bot_staff(member.id):
            if action == "add":
                await ctx.send(f"{member.mention} is authorized Bot Staff and already has full no-prefix access.")
                return

        try:
            if action == "add":
                await self.bot.db.execute(
                    "INSERT INTO system_no_prefix (user_id, added_by) VALUES (?, ?) ON CONFLICT (user_id) DO NOTHING;",
                    member.id,
                    ctx.author.id,
                )
                if hasattr(self.bot, "no_prefix_users"):
                    self.bot.no_prefix_users.add(member.id)
                await ctx.send(f"✅ Granted persistent no-prefix access to {member.mention} (`{member.id}`).")
            else:
                await self.bot.db.execute(
                    "DELETE FROM system_no_prefix WHERE user_id = ?;",
                    member.id,
                )
                if hasattr(self.bot, "no_prefix_users"):
                    if member.id != OWNER_ID and not is_bot_staff(member.id):
                        self.bot.no_prefix_users.discard(member.id)
                await ctx.send(f"✅ Revoked no-prefix access from {member.mention} (`{member.id}`).")
        except Exception:
            log.exception("Failed to update persistent no-prefix grant for user_id=%s", member.id)
            await ctx.send("⚠️ The database update failed; please try again.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NoPrefix(bot))
