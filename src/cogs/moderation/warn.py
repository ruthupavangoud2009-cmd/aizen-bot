from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.utils.containers import KyokaContainer, send_container_response

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
            container = KyokaContainer(accent_color=None)
            container.add_section(content=f"**Cannot Moderate Member**\n> {err_msg}")
            await send_container_response(ctx, container)
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
            dm_container = KyokaContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You received a warning in {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`\n"
                    f"> Total Warnings: `{total_warns}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await dispatch_mod_log(self.bot, ctx.guild, "Member Warning", member, ctx.author, reason, extra=f"Total Warns: {total_warns}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Warning Issued**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{member.display_name}** `「{member.id}」`\n"
            f"{dot} **Total Warnings:** `{total_warns}`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

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

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)

        if not records:
            container.add_section(
                content=(
                    f"**Clean Record**\n"
                    f"> **{member}** has no recorded warnings in this server."
                )
            )
            await send_container_response(ctx, container)
            return

        container.add_section(
            content=(
                f"**Member Warnings**\n"
                f"> Showing last {len(records)} warning(s) for **{member}** `「{member.id}」`."
            )
        )
        container.add_separator(divider=True)

        warn_lines = []
        for r in records:
            w_id = r["id"]
            mod_id = r["moderator_id"]
            reason = r["reason"]
            ts = r.get("created_at")
            ts_str = f"<t:{int(ts.timestamp())}:d>" if isinstance(ts, datetime.datetime) else "N/A"
            warn_lines.append(f"{dot} **#{w_id}** by <@{mod_id}> ({ts_str}): `{reason}`")

        container.add_text("\n".join(warn_lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Use `?delwarn <id>` to remove a specific warning.")
        await send_container_response(ctx, container)

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
            container = KyokaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Warning Not Found**\n"
                    f"> No warning with ID `#{warn_id}` exists in this server."
                )
            )
            await send_container_response(ctx, container)
            return

        await self.bot.db.execute(
            "DELETE FROM guild_warns WHERE id = ? AND guild_id = ?;",
            warn_id,
            ctx.guild.id,
        )

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Warning Deleted**\n"
                f"> Warning `#{warn_id}` has been deleted."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Warning ID:** `#{warn_id}`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**"
        )
        await send_container_response(ctx, container)

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
            container = KyokaContainer(accent_color=None)
            container.add_section(content=f"**Case Not Found**\n> No warning case `#{case_id}` exists in this server.")
            return await send_container_response(ctx, container)

        target = ctx.guild.get_member(row["user_id"])
        target_name = target.display_name if target else f"User {row['user_id']}"
        mod = ctx.guild.get_member(row["moderator_id"])
        mod_name = mod.display_name if mod else f"Mod {row['moderator_id']}"

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(content=f"**Moderation Case #{case_id}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{target_name}** `「{row['user_id']}」`\n"
            f"{dot} **Moderator:** **{mod_name}** `「{row['moderator_id']}」`\n"
            f"{dot} **Reason:** `{row['reason']}`\n"
            f"{dot} **Logged At:** `{row.get('created_at', 'N/A')}`"
        )
        await send_container_response(ctx, container)

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
            container = KyokaContainer(accent_color=None)
            container.add_section(content=f"**No Warnings Found**\n> {member.mention} has zero recorded warnings.")
            return await send_container_response(ctx, container)

        await self.bot.db.execute(
            "DELETE FROM guild_warns WHERE guild_id = ? AND user_id = ?;",
            ctx.guild.id,
            member.id,
        )

        await dispatch_mod_log(self.bot, ctx.guild, "Warnings Cleared", member, ctx.author, f"Cleared {total} warnings")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyokaContainer(accent_color=None)
        container.add_section(content="**Warnings Cleared**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{member.display_name}** `「{member.id}」`\n"
            f"{dot} **Cleared Count:** `{total}` warning(s)\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyokaBot) -> None:
    """Load the WarnCog into KyokaBot."""
    await bot.add_cog(WarnCog(bot))
