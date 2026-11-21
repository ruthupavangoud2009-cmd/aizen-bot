from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.ui.response import KyokaResponse, send_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class WarnCog(commands.Cog):
    """Server member warning system."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="warn",
        description="Issue an official warning to a server member.",
    )
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warn(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Warn a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            resp = KyokaResponse.permission("Cannot Moderate Member", err_msg or "Hierarchy check failed.")
            await send_response(ctx, resp, ephemeral=True)
            return

        await self.bot.db.execute(
            """
            INSERT INTO guild_warns (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?);
            """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
            reason,
        )

        # Count total warns
        count_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM guild_warns WHERE guild_id = ? AND user_id = ?;",
            ctx.guild.id,
            member.id,
        )
        total_warns = count_row["cnt"] if count_row else 1

        # Attempt DM notification
        try:
            dm_resp = KyokaResponse.moderation(
                action="warned",
                target=member,
                moderator=ctx.author,
                reason=reason,
                extra_fields=[("Server", ctx.guild.name, True), ("Total Warnings", str(total_warns), True)],
            )
            await send_response(member, dm_resp)
        except Exception:
            pass

        await dispatch_mod_log(self.bot, ctx.guild, "Member Warning", member, ctx.author, reason, extra=f"Total Warns: {total_warns}")

        resp = KyokaResponse.moderation(
            action="warn",
            target=member,
            moderator=ctx.author,
            reason=reason,
            extra_fields=[("Total Warnings", str(total_warns), True)],
        )
        await send_response(ctx, resp)

    @commands.hybrid_command(
        name="warnings",
        aliases=["warns"],
        description="View all recorded warnings for a member.",
    )
    @app_commands.describe(member="Member whose warnings to inspect")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warnings(self, ctx: CustomContext, member: discord.Member) -> None:
        """View warnings of a member."""
        records = await self.bot.db.fetch_all(
            """
            SELECT id, moderator_id, reason, created_at
            FROM guild_warns
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT 10;
            """,
            ctx.guild.id,
            member.id,
        )

        if not records:
            resp = KyokaResponse.info(
                title="Clean Record",
                description=f"**{member}** has no recorded warnings in this server.",
                author=ctx.author,
            )
            await send_response(ctx, resp)
            return

        fields = []
        for r in records:
            w_id = r["id"]
            mod_id = r["moderator_id"]
            reason = r["reason"]
            ts = r.get("created_at")
            ts_str = f"<t:{int(ts.timestamp())}:d>" if isinstance(ts, datetime.datetime) else "N/A"
            fields.append((f"#{w_id} • {ts_str}", f"Moderator: <@{mod_id}>\nReason: `{reason}`", False))

        resp = KyokaResponse.info(
            title=f"Warnings for {member.display_name}",
            description=f"Showing last {len(records)} warning(s) for **{member}** `「{member.id}」`.\n-# Use `?delwarn <id>` to remove a specific warning.",
            fields=fields,
            author=ctx.author,
            thumbnail_url=member.display_avatar.url,
        )
        await send_response(ctx, resp)

    @commands.hybrid_command(
        name="delwarn",
        aliases=["unwarn", "removewarn"],
        description="Delete a warning record by its ID.",
    )
    @app_commands.describe(warn_id="The ID of the warning to delete")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def delwarn(self, ctx: CustomContext, warn_id: int) -> None:
        """Delete a warning by ID."""
        row = await self.bot.db.fetch_one(
            "SELECT id, user_id FROM guild_warns WHERE id = ? AND guild_id = ?;",
            warn_id,
            ctx.guild.id,
        )
        if not row:
            resp = KyokaResponse.warning(
                title="Warning Not Found",
                description=f"No warning with ID `#{warn_id}` exists in this server.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        await self.bot.db.execute(
            "DELETE FROM guild_warns WHERE id = ? AND guild_id = ?;",
            warn_id,
            ctx.guild.id,
        )

        resp = KyokaResponse.success(
            title="Warning Deleted",
            description=f"Warning `#{warn_id}` has been deleted from this server.",
            fields=[("Warning ID", f"`#{warn_id}`", True), ("Moderator", f"**{ctx.author.display_name}**", True)],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="case",
        description="Inspect a specific moderation warning case by its ID.",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def case(self, ctx: CustomContext, case_id: int) -> None:
        """View warning case details."""
        row = await self.bot.db.fetch_one(
            "SELECT id, user_id, moderator_id, reason, created_at FROM guild_warns WHERE id = ? AND guild_id = ?;",
            case_id,
            ctx.guild.id,
        )
        if not row:
            resp = KyokaResponse.warning(
                title="Case Not Found",
                description=f"No warning case `#{case_id}` exists in this server.",
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        target = ctx.guild.get_member(row["user_id"])
        target_name = target.display_name if target else f"User {row['user_id']}"
        mod = ctx.guild.get_member(row["moderator_id"])
        mod_name = mod.display_name if mod else f"Mod {row['moderator_id']}"

        fields = [
            ("Target", f"**{target_name}** `「{row['user_id']}」`", True),
            ("Moderator", f"**{mod_name}** `「{row['moderator_id']}」`", True),
            ("Reason", f"`{row['reason']}`", False),
            ("Logged At", f"`{row.get('created_at', 'N/A')}`", False),
        ]
        resp = KyokaResponse.info(
            title=f"Moderation Case #{case_id}",
            fields=fields,
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="clearwarnings",
        aliases=["clearwarns"],
        description="Clear all warning records for a member.",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def clearwarnings(self, ctx: CustomContext, member: discord.Member) -> None:
        """Clear all warnings for a member."""
        count_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM guild_warns WHERE guild_id = ? AND user_id = ?;",
            ctx.guild.id,
            member.id,
        )
        total = count_row["cnt"] if count_row else 0
        if total == 0:
            resp = KyokaResponse.info(
                title="No Warnings Found",
                description=f"{member.mention} has zero recorded warnings.",
                author=ctx.author,
            )
            return await send_response(ctx, resp)

        await self.bot.db.execute(
            "DELETE FROM guild_warns WHERE guild_id = ? AND user_id = ?;",
            ctx.guild.id,
            member.id,
        )

        await dispatch_mod_log(self.bot, ctx.guild, "Warnings Cleared", member, ctx.author, f"Cleared {total} warnings")

        resp = KyokaResponse.success(
            title="Warnings Cleared",
            description=f"Cleared `{total}` warning(s) for **{member.display_name}**.",
            fields=[
                ("Target", f"**{member.display_name}** `「{member.id}」`", True),
                ("Cleared Count", f"`{total}` warning(s)", True),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    """Load the WarnCog into KyokaBot."""
    await bot.add_cog(WarnCog(bot))
