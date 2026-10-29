from __future__ import annotations

import logging

import discord
from discord.ext import commands

from src.security.owner import OWNER_ID, is_primary_owner

log = logging.getLogger("Kyoka.NoPrefix")


async def _primary_owner_only(ctx: commands.Context) -> bool:
    """Fail closed: only the configured primary owner can manage no-prefix access."""
    if is_primary_owner(getattr(ctx.author, "id", None)):
        return True
    raise commands.CheckFailure("Only the primary bot owner can manage no-prefix access.")


class NoPrefix(commands.Cog):
    """Persistent, owner-managed allowlist for no-prefix command access."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="noprefix",
        description="Manage users allowed to run commands without the server prefix.",
        invoke_without_command=True,
    )
    @commands.check(_primary_owner_only)
    async def noprefix(self, ctx: commands.Context) -> None:
        await ctx.send(
            "**No-prefix access**\n"
            "`noprefix grant @user` — allow a user to invoke commands without the prefix\n"
            "`noprefix revoke @user` — remove no-prefix access\n"
            "`noprefix list` — show the current allowlist",
            **({"ephemeral": True} if ctx.interaction is not None else {}),
        )

    @noprefix.command(name="grant", description="Grant no-prefix access to one user (owner only).")
    @commands.check(_primary_owner_only)
    async def noprefix_grant(self, ctx: commands.Context, user: discord.User) -> None:
        if user.bot and user.id != self.bot.user.id:
            await ctx.send("No-prefix access is intended for human users.", ephemeral=ctx.interaction is not None)
            return
        if is_primary_owner(user.id):
            await ctx.send("The primary owner already has no-prefix access.", ephemeral=ctx.interaction is not None)
            return

        try:
            await self.bot.db.execute(
                "INSERT INTO system_no_prefix (user_id, added_by) VALUES (?, ?) ON CONFLICT (user_id) DO NOTHING;",
                int(user.id),
                int(ctx.author.id),
            )
            self.bot.no_prefix_users.add(int(user.id))
        except Exception:
            log.exception("Failed to persist no-prefix grant")
            await ctx.send(
                "Could not save this grant to the database. No change was made to the in-memory allowlist.",
                **({"ephemeral": True} if ctx.interaction is not None else {}),
            )
            return

        await ctx.send(
            f"Granted no-prefix access to {user.mention} (`{user.id}`).",
            **({"ephemeral": True} if ctx.interaction is not None else {}),
        )

    @noprefix.command(name="revoke", description="Revoke no-prefix access from one user (owner only).")
    @commands.check(_primary_owner_only)
    async def noprefix_revoke(self, ctx: commands.Context, user: discord.User) -> None:
        if is_primary_owner(user.id):
            await ctx.send("The primary owner's no-prefix access cannot be revoked.", ephemeral=ctx.interaction is not None)
            return

        try:
            await self.bot.db.execute(
                "DELETE FROM system_no_prefix WHERE user_id = ?;",
                int(user.id),
            )
            self.bot.no_prefix_users.discard(int(user.id))
        except Exception:
            log.exception("Failed to persist no-prefix revocation")
            await ctx.send(
                "Could not update the database. The in-memory allowlist was left unchanged.",
                **({"ephemeral": True} if ctx.interaction is not None else {}),
            )
            return

        await ctx.send(
            f"Revoked no-prefix access from {user.mention} (`{user.id}`).",
            **({"ephemeral": True} if ctx.interaction is not None else {}),
        )

    @noprefix.command(name="list", description="List users who can run commands without a prefix (owner only).")
    @commands.check(_primary_owner_only)
    async def noprefix_list(self, ctx: commands.Context) -> None:
        try:
            rows = await self.bot.db.fetch_all(
                "SELECT user_id FROM system_no_prefix ORDER BY user_id;"
            )
            ids = sorted({OWNER_ID, *(int(row["user_id"]) for row in rows)})
        except Exception:
            log.exception("Failed to read no-prefix allowlist")
            await ctx.send("Could not load the no-prefix allowlist from the database.", ephemeral=ctx.interaction is not None)
            return

        rendered = "\n".join(f"• <@{user_id}> — `{user_id}`" for user_id in ids)
        await ctx.send(
            f"**No-prefix allowlist ({len(ids)})**\n{rendered}",
            **({"ephemeral": True} if ctx.interaction is not None else {}),
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NoPrefix(bot))
