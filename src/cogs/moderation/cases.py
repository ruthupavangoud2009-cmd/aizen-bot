"""
KYOKA — Moderation Case Lookup, History & Reason Management Cog
Provides Greed-inspired case management: +case, +cases, +reason, +modstats.
"""

from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.case_manager import CaseManager
from src.ui.response import KyokaResponse, send_response
from src.utils.containers import KyokaContainer, edit_container_response, send_container_response
from src.utils.emojis import resolve_emoji, resolve_select_emoji

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

CASES_PER_PAGE = 6


class CasePaginatorView(discord.ui.View):
    """Interactive author-locked paginator for moderation case history."""

    def __init__(
        self,
        bot: KyokaBot,
        ctx: CustomContext,
        cases: list[dict],
        title: str,
        target: Optional[discord.User | discord.Member] = None,
    ) -> None:
        super().__init__(timeout=120.0)
        self.bot = bot
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.cases = cases
        self.title = title
        self.target = target
        self.page = 1
        self.total_pages = max(1, math.ceil(len(cases) / CASES_PER_PAGE))
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages
        self.indicator_btn.label = f"{self.page}/{self.total_pages}"

    def build_container(self) -> KyokaContainer:
        dot = resolve_emoji(self.bot, "ARROW", fallback="•")
        shield = resolve_emoji(self.bot, "MODERATION")

        start = (self.page - 1) * CASES_PER_PAGE
        chunk = self.cases[start : start + CASES_PER_PAGE]

        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{shield} {self.title}**\n"
                f"> Total Recorded Cases: `{len(self.cases)}` • Page `{self.page}/{self.total_pages}`"
            ),
            accessory={"type": 11, "media": {"url": self.target.display_avatar.url}}
            if self.target and getattr(self.target, "display_avatar", None)
            else None,
        )
        container.add_separator(divider=True)

        lines = []
        for c in chunk:
            cid = c.get("case_id", "?")
            action = str(c.get("action", "action")).upper()
            uid = c.get("user_id", 0)
            mid = c.get("moderator_id", 0)
            reason = str(c.get("reason") or "No reason provided")[:90]
            ts = c.get("created_at")
            ts_str = f" • <t:{int(ts.timestamp())}:R>" if isinstance(ts, datetime.datetime) else ""
            lines.append(
                f"{dot} **Case `#{cid}` — `{action}`**{ts_str}\n"
                f"> Target: <@{uid}> (`{uid}`) • Mod: <@{mid}>\n"
                f"> Reason: `{reason}`"
            )

        container.add_text("\n\n".join(lines) if lines else "> No moderation cases found.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.display_name} • Use +case <id> for full details")
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This case log belongs to the moderator who opened it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="kyoka:cases:prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page > 1:
            self.page -= 1
        self._sync_buttons()
        await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="kyoka:cases:ind")
    async def indicator_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="kyoka:cases:next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page < self.total_pages:
            self.page += 1
        self._sync_buttons()
        await edit_container_response(interaction, self.build_container(), view=self)


class CasesCog(commands.Cog, name="Cases"):
    """Server moderation case tracking, lookup, editing, and moderator stats."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "case_mgr"):
            self.bot.case_mgr = CaseManager(getattr(self.bot, "db", None))

    def _get_manager(self) -> CaseManager:
        mgr = getattr(self.bot, "case_mgr", None)
        if mgr is None:
            mgr = CaseManager(getattr(self.bot, "db", None))
            self.bot.case_mgr = mgr
        return mgr

    @commands.command(
        name="modcase",
        aliases=["caseinfo", "mcase", "inspectcase"],
        description="Inspect full details of a moderation case by its Case ID.",
    )
    @app_commands.describe(case_id="The numeric moderation case ID (e.g. 12)")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def case_cmd(self, ctx: CustomContext, case_id: int) -> None:
        """Inspect a specific moderation case."""
        mgr = self._get_manager()
        record = await mgr.get_case(ctx.guild.id, case_id)
        if not record:
            resp = KyokaResponse.warning(
                title="Case Not Found",
                description=f"No moderation case `#{case_id}` exists in **{ctx.guild.name}**.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        ts = record.get("created_at")
        ts_str = f"<t:{int(ts.timestamp())}:F> (<t:{int(ts.timestamp())}:R>)" if isinstance(ts, datetime.datetime) else "N/A"
        fields = [
            ("Action", f"`{str(record.get('action', '')).upper()}`", True),
            ("Target", f"<@{record['user_id']}> `「{record['user_id']}」`", True),
            ("Moderator", f"<@{record['moderator_id']}> `「{record['moderator_id']}」`", True),
            ("Reason", f"`{record.get('reason') or 'No reason provided'}`", False),
            ("Recorded", ts_str, False),
        ]
        if record.get("duration"):
            fields.append(("Duration", f"`{record['duration']}`", True))
        if record.get("notes"):
            fields.append(("Staff Notes", f"`{record['notes']}`", False))

        resp = KyokaResponse.info(
            title=f"Moderation Case #{record['case_id']}",
            description=f"Official ledger entry for **{ctx.guild.name}**.",
            fields=fields,
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="cases",
        aliases=["modlogs", "history", "modhistory"],
        description="View moderation case history for the server or a specific member.",
    )
    @app_commands.describe(member="Optional member whose cases to filter")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def cases_cmd(
        self,
        ctx: CustomContext,
        member: Optional[discord.User] = None,
    ) -> None:
        """View paginated moderation cases."""
        mgr = self._get_manager()
        uid = member.id if member else None
        records = await mgr.list_cases(ctx.guild.id, user_id=uid, limit=50)

        if not records:
            target_label = f"**{member}**" if member else f"**{ctx.guild.name}**"
            resp = KyokaResponse.info(
                title="Clean Moderation Ledger",
                description=f"No recorded moderation cases found for {target_label}.",
                author=ctx.author,
            )
            await send_response(ctx, resp)
            return

        title = f"Moderation History — {member.display_name}" if member else f"Server Moderation Cases — {ctx.guild.name}"
        view = CasePaginatorView(self.bot, ctx, records, title=title, target=member)
        await send_container_response(ctx, view.build_container(), view=view)

    @commands.command(
        name="reason",
        aliases=["casereason", "editcase"],
        description="Update the reason on an existing moderation case.",
    )
    @app_commands.describe(case_id="Case ID to update", reason="Updated moderation reason")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def reason_cmd(self, ctx: CustomContext, case_id: int, *, reason: str) -> None:
        """Edit the reason on a recorded moderation case."""
        mgr = self._get_manager()
        ok = await mgr.update_reason(ctx.guild.id, case_id, reason)
        if not ok:
            resp = KyokaResponse.warning(
                title="Case Not Found",
                description=f"Could not locate Case `#{case_id}` in this server.",
                author=ctx.author,
            )
            await send_response(ctx, resp, ephemeral=True)
            return

        resp = KyokaResponse.success(
            title=f"Case #{case_id} Updated",
            description=f"Updated moderation reason for Case `#{case_id}`.",
            fields=[
                ("New Reason", f"`{reason.strip()[:300]}`", False),
                ("Edited By", ctx.author.mention, True),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @commands.command(
        name="modstats",
        aliases=["moderatorstats"],
        description="View moderation case statistics for yourself or another moderator.",
    )
    @app_commands.describe(moderator="Moderator to inspect (defaults to yourself)")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def modstats_cmd(
        self,
        ctx: CustomContext,
        moderator: Optional[discord.Member] = None,
    ) -> None:
        """Display total moderation cases issued by a staff member."""
        target = moderator or ctx.author
        mgr = self._get_manager()
        stats = await mgr.get_moderator_stats(ctx.guild.id, target.id)

        total = stats.get("total", 0)
        fields = [
            ("Total Cases", f"`{total}`", True),
            ("Bans / Softbans", f"`{stats.get('ban', 0) + stats.get('softban', 0)}`", True),
            ("Kicks", f"`{stats.get('kick', 0)}`", True),
            ("Timeouts / Mutes", f"`{stats.get('timeout', 0)}`", True),
            ("Warnings", f"`{stats.get('warn', 0)}`", True),
            ("Jails", f"`{stats.get('jail', 0)}`", True),
        ]
        resp = KyokaResponse.info(
            title=f"Moderator Statistics — {target.display_name}",
            description=f"Logged moderation actions in **{ctx.guild.name}**.",
            fields=fields,
            author=ctx.author,
            thumbnail_url=target.display_avatar.url,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(CasesCog(bot))
