from __future__ import annotations

import asyncio
import datetime
import io
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.cogs.moderation._helpers import resolve_role
from src.core.context import CustomContext
from src.security.owner import is_primary_owner
from src.utils.containers import (
    KyokaContainer,
    edit_container_response,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.Giveaway")


def parse_giveaway_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """
    Parse duration strings like '10s', '5m', '2h', '1d', '2w', '1d12h'.
    Returns timedelta or None if invalid.
    """
    clean = duration_str.strip().lower()
    matches = re.findall(r"(\d+)\s*([smhdw])", clean)
    if not matches:
        return None

    total_seconds = 0
    unit_multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    for val_str, unit in matches:
        total_seconds += int(val_str) * unit_multipliers[unit]

    if total_seconds < 5:  # Minimum 5 seconds
        return None
    if total_seconds > 2592000:  # Maximum 30 days
        return None

    return datetime.timedelta(seconds=total_seconds)


async def is_giveaway_authorized(
    bot: KyokaBot,
    user: discord.Member | discord.User,
    guild: Optional[discord.Guild] = None,
) -> bool:
    """Check if member has permission to manage giveaways in this server."""
    if is_primary_owner(user.id):
        return True
    if guild is None and isinstance(user, discord.Member):
        guild = user.guild
    if not guild or not isinstance(user, discord.Member):
        return False
    if getattr(guild, "owner_id", None) == user.id:
        return True
    if user.guild_permissions.administrator or user.guild_permissions.manage_guild or user.guild_permissions.manage_messages:
        return True

    # Check configured manager role from server_giveaway_config
    try:
        cfg = await bot.db.fetch_one(
            "SELECT manager_role_id FROM server_giveaway_config WHERE guild_id = $1;",
            guild.id,
        )
        if cfg and cfg.get("manager_role_id"):
            mgr_role_id = int(cfg["manager_role_id"])
            if any(r.id == mgr_role_id for r in user.roles):
                return True
    except Exception:
        pass

    return False


def build_giveaway_container(
    prize: str,
    host_id: int,
    winner_count: int,
    ends_at: datetime.datetime,
    entries_count: int = 0,
    description: str = "",
    required_role_id: Optional[int] = None,
    entry_limit: int = 0,
    claim_deadline_seconds: int = 0,
    is_paused: bool = False,
    is_ended: bool = False,
    is_cancelled: bool = False,
    winners: Optional[list[int]] = None,
    bonus_summary: str = "",
    gw_emoji: str = "🎉",
    dot: str = "•",
    win_emoji: str = "🎉",
) -> KyokaContainer:
    """Build rich and engaging Components V2 container card for active, paused, or ended giveaways."""
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=datetime.timezone.utc)
    ts = int(ends_at.timestamp())
    title_prize = prize.title() if prize.islower() else prize

    container = KyokaContainer(accent_color=None)

    if is_cancelled:
        container.add_section(content=f"# **[CANCELLED] {title_prize}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Hosted By:** <@{host_id}>\n"
            f"> This giveaway was cancelled by an administrator. No winners were drawn."
        )
        container.add_separator(divider=True)
        return container

    if not is_ended:
        status_tag = " **[PAUSED]**" if is_paused else ""
        container.add_section(content=f"# **{title_prize}**{status_tag}")
        container.add_separator(divider=True)

        if description:
            container.add_text(f"> {description}\n")

        winner_label = "Winner" if winner_count == 1 else "Winners"
        limit_text = f" / `{entry_limit}` max" if entry_limit > 0 else ""
        req_text = f"\n{dot} **Required Role:** <@&{required_role_id}>" if required_role_id else ""
        claim_text = f"\n{dot} **Claim Period:** `{claim_deadline_seconds // 3600}h`" if claim_deadline_seconds > 0 else ""
        bonus_text = f"\n{dot} **Bonus Multipliers:** Active" if bonus_summary else ""

        container.add_text(
            f"{dot} **Hosted By:** <@{host_id}>\n"
            f"{dot} **{winner_label}:** `{winner_count}`\n"
            f"{dot} **Entries:** `{entries_count}`{limit_text}{req_text}{claim_text}{bonus_text}"
        )
        container.add_separator(divider=True)
        if is_paused:
            container.add_text("-# Giveaway is currently PAUSED")
        else:
            container.add_text(f"-# Ends: <t:{ts}:R> (<t:{ts}:f>)")
        container.add_separator(divider=True)
        return container

    # Ended giveaway
    container.add_section(content=f"# **{title_prize}**")
    container.add_separator(divider=True)

    if winners:
        winner_str = ", ".join(f"<@{w}>" for w in winners)
        winner_label = "Winner" if len(winners) == 1 else "Winners"
        if len(winners) == 1 and host_id in winners:
            celebration = f"\n\n{dot} **{winner_label}:** {winner_str}\n> {win_emoji} Congratulations! You won your own giveaway!"
        else:
            celebration = f"\n\n{dot} **{winner_label}:** {winner_str}\n> {win_emoji} Congratulations! Contact <@{host_id}> to claim your prize."
    else:
        winner_str = "*No one entered*"
        celebration = f"\n\n{dot} **Winners:** {winner_str}\n> No winner could be drawn."

    container.add_text(
        f"{dot} **Hosted By:** <@{host_id}>\n"
        f"{dot} **Total Participants:** `{entries_count}`"
        f"{celebration}"
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Ended: <t:{ts}:R>")
    container.add_separator(divider=True)
    return container


class PersistentGiveawayView(discord.ui.View):
    """Global persistent view for ongoing giveaways surviving bot restarts."""

    def __init__(self, bot: KyokaBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        e_reg = getattr(self.bot, "custom_emojis", None)
        get_obj = getattr(e_reg, "get_emoji_obj", None)
        gw_emoji_obj = None
        if callable(get_obj):
            gw_emoji_obj = (
                get_obj("s_giveaway")
                or get_obj("discord_giveaway")
                or get_obj("giveaway")
            )
        if isinstance(gw_emoji_obj, (str, discord.Emoji, discord.PartialEmoji)):
            self.enter_giveaway.emoji = gw_emoji_obj

    @discord.ui.button(
        label="Join Giveaway",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:giveaway:enter",
    )
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Handle dynamic entry and withdrawal on click with anti-race locking."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        msg_id = interaction.message.id
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(msg_id)

        # Fallback check from DB if not in active memory
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", msg_id)
            if not gw_row or gw_row.get("is_ended") or gw_row.get("is_cancelled"):
                container = KyokaContainer(accent_color=None)
                container.add_section(content="**Giveaway Ended**")
                container.add_separator(divider=True)
                container.add_text("> This giveaway has already ended or was cancelled.")
                await send_container_response(interaction, container, ephemeral=True)
                return
            gw = self.bot.giveaway_mgr._row_to_giveaway_dict(gw_row)

        giveaway_id = gw["id"]
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        # Check required role requirement if set
        if gw.get("required_role_id") and isinstance(interaction.user, discord.Member):
            req_role = interaction.guild.get_role(int(gw["required_role_id"]))
            if req_role and req_role not in interaction.user.roles:
                container = KyokaContainer(accent_color=None)
                container.add_section(content="**Role Required**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} You need the {req_role.mention} role to enter this giveaway.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {interaction.user.display_name}")
                await send_container_response(interaction, container, ephemeral=True)
                return

        # Toggle participation via GiveawayManager
        res = await self.bot.giveaway_mgr.toggle_participant(
            giveaway_id,
            interaction.user,
            activity_mgr=getattr(self.bot, "activity_mgr", None),
        )
        success, action, count = res[0], res[1], res[2]
        failure_reason = getattr(res, "failure_reason", res[3] if len(res) > 3 else None)

        resp_container = KyokaContainer(accent_color=None)

        if not success:
            resp_container.add_section(content="**Entry Unsuccessful**")
            resp_container.add_separator(divider=True)
            resp_container.add_text(f"{dot} {failure_reason or 'You do not meet the entry requirements.'}")
            resp_container.add_separator(divider=True)
            resp_container.add_text(f"-# Requested by {interaction.user.display_name}")
            await send_container_response(interaction, resp_container, ephemeral=True)
            return

        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))

        if action == "entered":
            # Calculate member bonus weight to display
            _, weight, qroles, breakdown_str = await self.bot.giveaway_mgr.calculate_member_bonus(gw, interaction.user)
            bonus_info = f"\n> **Your Weight:** `{weight:.1f}x` ({breakdown_str})" if weight > 1.0 else ""

            resp_container.add_section(content="**You're In!**")
            resp_container.add_separator(divider=True)
            resp_container.add_text(
                f"{dot} You joined the giveaway for **{gw['prize']}**!\n"
                f"> Total entries: `{count}`.{bonus_info}\n"
                f"> Click again anytime to withdraw."
            )
        else:
            resp_container.add_section(content="**You Left**")
            resp_container.add_separator(divider=True)
            resp_container.add_text(
                f"{dot} You left the giveaway for **{gw['prize']}**.\n"
                f"> Total entries remaining: `{count}`."
            )
        resp_container.add_separator(divider=True)
        resp_container.add_text(f"-# Requested by {interaction.user.display_name}")

        await send_container_response(interaction, resp_container, ephemeral=True)

        # Update message card
        try:
            updated_card = build_giveaway_container(
                prize=gw["prize"],
                host_id=gw["host_id"],
                winner_count=gw["winner_count"],
                ends_at=gw["ends_at"],
                entries_count=count,
                description=gw.get("description", ""),
                required_role_id=gw.get("required_role_id"),
                entry_limit=gw.get("entry_limit", 0),
                claim_deadline_seconds=gw.get("claim_deadline_seconds", 0),
                is_paused=gw.get("is_paused", False),
                gw_emoji=gw_emoji,
                dot=dot,
            )
            await edit_container_response(
                interaction.message,
                updated_card,
                view=self,
                content=f"### {gw_emoji} Active Giveaway {gw_emoji}",
            )
        except Exception as e:
            logger.debug(f"Notice updating giveaway card: {e}")

    @discord.ui.button(
        label="Requirements",
        style=discord.ButtonStyle.secondary,
        custom_id="kyoka:giveaway:requirements",
        emoji="📋",
    )
    async def view_requirements(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Privately check and display member's requirement pass/fail breakdown."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        msg_id = interaction.message.id
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(msg_id)
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", msg_id)
            if not gw_row:
                return await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            gw = self.bot.giveaway_mgr._row_to_giveaway_dict(gw_row)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        passed, breakdown = await self.bot.giveaway_mgr.check_member_eligibility(
            gw,
            interaction.user,
            activity_mgr=getattr(self.bot, "activity_mgr", None),
        )
        _, weight, _, breakdown_str = await self.bot.giveaway_mgr.calculate_member_bonus(gw, interaction.user)

        container = KyokaContainer(accent_color=None)
        status_header = "**Eligible to Enter**" if passed else "**Requirements Unmet**"
        container.add_section(content=f"### {status_header}")
        container.add_separator(divider=True)

        if not breakdown:
            container.add_text(f"{dot} **Requirements:** No restrictions. Open to all members!\n")
        else:
            lines = []
            for b in breakdown:
                icon = "✅" if b["passed"] else "❌"
                lines.append(f"{icon} **{b['label']}**\n> Status: `{b['reason']}`")
            container.add_text("\n\n".join(lines) + "\n")

        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Bonus Multiplier:** `{weight:.1f}x` ({breakdown_str})\n"
            f"-# Checked for {interaction.user.display_name}"
        )
        await send_container_response(interaction, container, ephemeral=True)


class ConcludedGiveawayView(discord.ui.View):
    """View with disabled buttons marking giveaway conclusion."""

    def __init__(self, bot: KyokaBot, count: int = 0) -> None:
        super().__init__(timeout=None)
        gw_emoji_obj = (
            bot.custom_emojis.get_emoji_obj("s_giveaway")
            or bot.custom_emojis.get_emoji_obj("discord_giveaway")
            or bot.custom_emojis.get_emoji_obj("giveaway")
        )
        self.add_item(
            discord.ui.Button(
                label="Giveaway Ended",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                custom_id="kyoka:giveaway:concluded",
                emoji=gw_emoji_obj if gw_emoji_obj else "🎉",
            )
        )


class Giveaways(commands.Cog):
    """
    KYOKA 3.0 Enterprise Giveaway Cog.
    Houses the `/giveaway` group with all 18 documented subcommands,
    preserves all legacy prefix commands (+gstart, +gend, +greroll, +glist),
    and coordinates live countdowns, weighted draws, and claim deadlines.
    """

    category: str = "Utility"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self.bot.add_view(PersistentGiveawayView(self.bot))

    async def cog_load(self) -> None:
        """Start autonomous background ticker."""
        if not self.giveaway_ticker.is_running():
            self.giveaway_ticker.start()

    async def cog_unload(self) -> None:
        """Cancel background loop cleanly on unload."""
        self.giveaway_ticker.cancel()

    # ─── AUTONOMOUS TICKER TASK ──────────────────────────────────────────────

    @tasks.loop(seconds=10.0)
    async def giveaway_ticker(self) -> None:
        """Periodic loop monitoring active giveaways and triggering conclusion upon expiry."""
        try:
            due = self.bot.giveaway_mgr.get_due_giveaways()
            for gw in due:
                try:
                    await self.conclude_giveaway(gw["message_id"])
                except Exception as e:
                    logger.error(f"Error concluding giveaway message {gw.get('message_id')}: {e}", exc_info=e)
        except Exception as e:
            logger.debug(f"Giveaway loop notice: {e}")

    @giveaway_ticker.before_loop
    async def before_ticker(self) -> None:
        await self.bot.wait_until_ready()

    async def conclude_giveaway(self, message_id: int) -> Optional[dict[str, Any]]:
        """Finalize giveaway, edit card, disable button, and announce winners."""
        res = await self.bot.giveaway_mgr.end_giveaway(message_id)
        if not res:
            return None

        channel = self.bot.get_channel(res["channel_id"])
        if not channel:
            try:
                channel = await self.bot.fetch_channel(res["channel_id"])
            except Exception:
                return res

        msg = None
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            pass

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))
        win_emoji = self.bot.custom_emojis.get("gpp_winner", self.bot.custom_emojis.get("winner", "🎉"))
        winners = res.get("winners", [])
        total_entries = res.get("total_entries", 0)

        # Build concluded card & disabled view
        concluded_card = build_giveaway_container(
            prize=res["prize"],
            host_id=res["host_id"],
            winner_count=res["winner_count"],
            ends_at=res["ends_at"],
            entries_count=total_entries,
            description=res.get("description", ""),
            required_role_id=res.get("required_role_id"),
            claim_deadline_seconds=res.get("claim_deadline_seconds", 0),
            is_ended=True,
            winners=winners,
            gw_emoji=gw_emoji,
            dot=dot,
            win_emoji=win_emoji,
        )
        ended_view = ConcludedGiveawayView(self.bot, count=total_entries)

        if msg:
            try:
                await edit_container_response(
                    msg,
                    concluded_card,
                    view=ended_view,
                    content=f"### {gw_emoji} Giveaway Ended {gw_emoji}",
                )
            except Exception as e:
                logger.debug(f"Failed to edit giveaway message {message_id}: {e}")

        # Send public winner announcement in channel
        if winners:
            winner_mentions = ", ".join(f"<@{w}>" for w in winners)
            prize_name = res["prize"]
            host_mention = f"<@{res['host_id']}>"
            deadline_str = ""
            if res.get("claim_deadline"):
                dl_ts = int(res["claim_deadline"].timestamp())
                deadline_str = f"\n> ⏰ **Claim Deadline:** <t:{dl_ts}:R> (<t:{dl_ts}:f>)"

            announce_text = (
                f"### {win_emoji} Congratulations {winner_mentions}! {win_emoji}\n"
                f"> You won **{prize_name}** hosted by {host_mention}!{deadline_str}\n"
                f"-# Contact {host_mention} to claim your prize."
            )
            try:
                await channel.send(announce_text)
            except Exception as e:
                logger.debug(f"Failed to send winner announcement: {e}")

        return res

    # ─── SLASH COMMAND GROUP (18 SUBCOMMANDS) ────────────────────────────────

    giveaway_group = app_commands.Group(
        name="giveaway",
        description="KYOKA 3.0 Advanced Giveaway Management System",
    )

    # 1. /giveaway create
    @giveaway_group.command(name="create", description="Create and publish an advanced giveaway.")
    @app_commands.describe(
        prize="The prize to give away",
        duration="Duration of the giveaway (e.g. 10m, 2h, 1d, 3d)",
        winners="Number of winners to draw (default: 1)",
        channel="Channel to host the giveaway (default: current channel)",
        required_role="Optional role required to enter",
        description="Optional custom description/notes for the giveaway card",
        claim_deadline_hours="Optional hours winners have to claim before reroll",
        entry_limit="Optional max number of participants permitted",
    )
    async def slash_create(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: int = 1,
        channel: Optional[discord.TextChannel] = None,
        required_role: Optional[discord.Role] = None,
        description: str = "",
        claim_deadline_hours: int = 0,
        entry_limit: int = 0,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("You are not authorized to manage giveaways.", ephemeral=True)

        target_channel = channel or interaction.channel
        if not target_channel or not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("Please specify a valid text channel.", ephemeral=True)

        delta = parse_giveaway_duration(duration)
        if not delta:
            return await interaction.response.send_message(
                "Invalid duration. Use formats like `10m`, `2h`, `1d`, `3d`.", ephemeral=True
            )

        if winners < 1 or winners > 50:
            return await interaction.response.send_message("Winner count must be between 1 and 50.", ephemeral=True)

        ends_at = datetime.datetime.now(datetime.timezone.utc) + delta
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))

        card = build_giveaway_container(
            prize=prize,
            host_id=interaction.user.id,
            winner_count=winners,
            ends_at=ends_at,
            entries_count=0,
            description=description,
            required_role_id=required_role.id if required_role else None,
            entry_limit=entry_limit,
            claim_deadline_seconds=claim_deadline_hours * 3600,
            gw_emoji=gw_emoji,
            dot=dot,
        )

        view = PersistentGiveawayView(self.bot)
        gw_msg = await send_container_response(
            target_channel,
            card,
            view=view,
            content=f"### {gw_emoji} New Giveaway {gw_emoji}",
        )

        gw_id = await self.bot.giveaway_mgr.create_giveaway(
            guild_id=interaction.guild.id,
            channel_id=target_channel.id,
            message_id=gw_msg.id,
            host_id=interaction.user.id,
            prize=prize,
            winner_count=winners,
            ends_at=ends_at,
            description=description,
            required_role_id=required_role.id if required_role else None,
            claim_deadline_seconds=claim_deadline_hours * 3600,
            entry_limit=entry_limit,
        )

        ack = KyokaContainer()
        ack.add_section(content=f"**Giveaway Published (ID: `{gw_id}`)**")
        ack.add_separator(divider=True)
        ack.add_text(
            f"{dot} **Prize:** **{prize}**\n"
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Winners:** `{winners}` | **Ends:** <t:{int(ends_at.timestamp())}:R>"
        )
        await send_container_response(interaction, ack, ephemeral=True)

    # 2. /giveaway quick
    @giveaway_group.command(name="quick", description="Quickly launch a giveaway with sensible defaults.")
    @app_commands.describe(
        prize="The prize to give away",
        duration="Duration (e.g. 10m, 1h, 1d)",
        winners="Number of winners (default: 1)",
        channel="Channel to post in (default: current channel)",
    )
    async def slash_quick(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str = "1h",
        winners: int = 1,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        await self.slash_create(
            interaction,
            prize=prize,
            duration=duration,
            winners=winners,
            channel=channel,
        )

    # 3. /giveaway end
    @giveaway_group.command(name="end", description="End an active giveaway early and pick winners now.")
    @app_commands.describe(message_id="Message ID of the giveaway (optional if in same channel)")
    async def slash_end(self, interaction: discord.Interaction, message_id: Optional[str] = None) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        mid = self._resolve_message_id(interaction.channel.id, message_id)
        if not mid:
            return await interaction.response.send_message("Please provide the giveaway message ID.", ephemeral=True)

        res = await self.conclude_giveaway(mid)
        if not res:
            return await interaction.response.send_message("No active giveaway found with that ID.", ephemeral=True)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyokaContainer()
        container.add_section(content="**Giveaway Concluded**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Prize:** **{res['prize']}**\n"
            f"{dot} **Winners Drawn:** `{len(res.get('winners', []))}`\n"
            f"{dot} **Total Entries:** `{res.get('total_entries', 0)}`"
        )
        await send_container_response(interaction, container)

    # 4. /giveaway cancel
    @giveaway_group.command(name="cancel", description="Cancel an active giveaway without picking winners.")
    @app_commands.describe(
        message_id="Message ID of the giveaway",
        reason="Reason for cancelling the giveaway",
    )
    async def slash_cancel(self, interaction: discord.Interaction, message_id: str, reason: str = "") -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        res = await self.bot.giveaway_mgr.cancel_giveaway(int(message_id), interaction.user.id, reason)
        if not res:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        # Update message
        try:
            channel = self.bot.get_channel(res["channel_id"])
            if channel:
                msg = await channel.fetch_message(int(message_id))
                card = build_giveaway_container(
                    prize=res["prize"],
                    host_id=res["host_id"],
                    winner_count=res["winner_count"],
                    ends_at=res["ends_at"],
                    is_cancelled=True,
                )
                await edit_container_response(msg, card, view=None, content="### ⚠️ Giveaway Cancelled")
        except Exception:
            pass

        await interaction.response.send_message(f"Cancelled giveaway **{res['prize']}**.", ephemeral=True)

    # 5. /giveaway pause
    @giveaway_group.command(name="pause", description="Pause entries and freeze the countdown on a giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_pause(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        res = await self.bot.giveaway_mgr.pause_giveaway(int(message_id), interaction.user.id)
        if not res:
            return await interaction.response.send_message("Could not pause. Giveaway not found, ended, or already paused.", ephemeral=True)

        # Edit card to show paused state
        try:
            channel = self.bot.get_channel(res["channel_id"])
            if channel:
                msg = await channel.fetch_message(int(message_id))
                card = build_giveaway_container(
                    prize=res["prize"],
                    host_id=res["host_id"],
                    winner_count=res["winner_count"],
                    ends_at=res["ends_at"],
                    is_paused=True,
                )
                await edit_container_response(msg, card, view=PersistentGiveawayView(self.bot))
        except Exception:
            pass

        await interaction.response.send_message(f"Paused giveaway **{res['prize']}**.", ephemeral=True)

    # 6. /giveaway resume
    @giveaway_group.command(name="resume", description="Resume a paused giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_resume(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        res = await self.bot.giveaway_mgr.resume_giveaway(int(message_id), interaction.user.id)
        if not res:
            return await interaction.response.send_message("Could not resume. Giveaway is not paused or not found.", ephemeral=True)

        try:
            channel = self.bot.get_channel(res["channel_id"])
            if channel:
                msg = await channel.fetch_message(int(message_id))
                card = build_giveaway_container(
                    prize=res["prize"],
                    host_id=res["host_id"],
                    winner_count=res["winner_count"],
                    ends_at=res["ends_at"],
                    is_paused=False,
                )
                await edit_container_response(msg, card, view=PersistentGiveawayView(self.bot))
        except Exception:
            pass

        await interaction.response.send_message(f"Resumed giveaway **{res['prize']}**.", ephemeral=True)

    # 7. /giveaway reroll
    @giveaway_group.command(name="reroll", description="Draw new replacement winners from an ended giveaway.")
    @app_commands.describe(
        message_id="Message ID of the ended giveaway",
        winners="Number of new winners to select (default: 1)",
    )
    async def slash_reroll(self, interaction: discord.Interaction, message_id: str, winners: int = 1) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        res = await self.bot.giveaway_mgr.reroll_giveaway(int(message_id), count=winners, actor_id=interaction.user.id)
        if not res:
            return await interaction.response.send_message("Ended giveaway not found.", ephemeral=True)

        data, new_winners = res
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        win_emoji = self.bot.custom_emojis.get("gpp_winner", "🎉")

        if not new_winners:
            return await interaction.response.send_message("No eligible participants to draw from.", ephemeral=True)

        mentions = ", ".join(f"<@{w}>" for w in new_winners)
        container = KyokaContainer()
        container.add_section(content=f"# **Reroll: {data['prize']}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **New Winners:** {mentions}\n"
            f"{dot} **Rerolled By:** {interaction.user.mention}\n\n"
            f"> {win_emoji} Congratulations! Contact the host to claim your prize."
        )
        await send_container_response(interaction, container)

    # 8. /giveaway edit
    @giveaway_group.command(name="edit", description="Edit settings for an active giveaway.")
    @app_commands.describe(
        message_id="Message ID of the giveaway to edit",
        prize="New prize title",
        winners="New winner count",
        add_minutes="Add or subtract minutes (e.g. 10 or -5)",
        required_role="New required role (use @everyone or None to remove)",
    )
    async def slash_edit(
        self,
        interaction: discord.Interaction,
        message_id: str,
        prize: Optional[str] = None,
        winners: Optional[int] = None,
        add_minutes: Optional[int] = None,
        required_role: Optional[discord.Role] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        delta = datetime.timedelta(minutes=add_minutes) if add_minutes is not None else None
        role_id = required_role.id if required_role else None

        res = await self.bot.giveaway_mgr.edit_giveaway(
            int(message_id),
            actor_id=interaction.user.id,
            prize=prize,
            winner_count=winners,
            duration_delta=delta,
            required_role_id=role_id,
        )
        if not res:
            return await interaction.response.send_message("Giveaway not found or already ended.", ephemeral=True)

        await interaction.response.send_message(f"Updated giveaway settings for **{res['prize']}**.", ephemeral=True)

    # 9. /giveaway list
    @giveaway_group.command(name="list", description="List active and recent giveaways in this server.")
    async def slash_list(self, interaction: discord.Interaction) -> None:
        active_list = self.bot.giveaway_mgr.get_active_giveaways_for_guild(interaction.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        if not active_list:
            container.add_section(content="# **No Active Giveaways**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} No giveaways are currently running in **{interaction.guild.name}**.")
            return await send_container_response(interaction, container, ephemeral=True)

        container.add_section(content=f"# **Active Giveaways ({len(active_list)})**")
        container.add_separator(divider=True)

        blocks = []
        for idx, g in enumerate(active_list, start=1):
            ts = int(g["ends_at"].timestamp())
            msg_link = f"https://discord.com/channels/{interaction.guild.id}/{g['channel_id']}/{g['message_id']}"
            blocks.append(
                f"**{idx}. [{g['prize']}]({msg_link})**\n"
                f"{dot} Channel: <#{g['channel_id']}> | Winners: `{g['winner_count']}`\n"
                f"{dot} Host: <@{g['host_id']}> | Ends: <t:{ts}:R>"
            )

        container.add_text("\n\n".join(blocks))
        await send_container_response(interaction, container)

    # 10. /giveaway info
    @giveaway_group.command(name="info", description="View detailed parameters of a giveaway.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_info(self, interaction: discord.Interaction, message_id: str) -> None:
        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        gw = self.bot.giveaway_mgr._row_to_giveaway_dict(row)
        entries_count = await self.bot.giveaway_mgr.get_participant_count(gw["id"])
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        ts = int(gw["ends_at"].timestamp())

        status = "Paused" if gw.get("is_paused") else ("Ended" if gw.get("is_ended") else "Active")

        container = KyokaContainer()
        container.add_section(content=f"# **Giveaway Dossier: {gw['prize']}**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **ID:** `{gw['id']}` | **Status:** `{status}`\n"
            f"{dot} **Channel:** <#{gw['channel_id']}> | **Message ID:** `{gw['message_id']}`\n"
            f"{dot} **Host:** <@{gw['host_id']}> | **Winners:** `{gw['winner_count']}`\n"
            f"{dot} **Entries:** `{entries_count}` | **Entry Limit:** `{gw.get('entry_limit') or 'Unlimited'}`\n"
            f"{dot} **Ends:** <t:{ts}:f> (<t:{ts}:R>)\n"
            f"{dot} **Bonus Policy:** `{gw.get('bonus_stacking_policy')}` (cap `{gw.get('bonus_multiplier_cap')}x`)"
        )
        await send_container_response(interaction, container, ephemeral=True)

    # 11. /giveaway entries
    @giveaway_group.command(name="entries", description="View participant counts and weighted entry details.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_entries(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to inspect entry details.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT id, prize FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        gid = int(row["id"])
        participants = await self.bot.db.fetch_all(
            "SELECT user_id, effective_weight, qualifying_roles, is_excluded FROM giveaway_participants WHERE giveaway_id = $1 ORDER BY effective_weight DESC LIMIT 25;",
            gid,
        )

        total_count = await self.bot.giveaway_mgr.get_participant_count(gid)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        container.add_section(content=f"**Entries: {row['prize']} (Total: {total_count})**")
        container.add_separator(divider=True)

        if not participants:
            container.add_text(f"{dot} No participants have entered yet.")
        else:
            lines = []
            for p in participants[:15]:
                exc = " [EXCLUDED]" if p.get("is_excluded") else ""
                lines.append(f"{dot} <@{p['user_id']}> — Weight: `{p['effective_weight']:.1f}x`{exc}")
            container.add_text("\n".join(lines))

        await send_container_response(interaction, container, ephemeral=True)

    # 12. /giveaway check
    @giveaway_group.command(name="check", description="Check a member's eligibility for a giveaway.")
    @app_commands.describe(
        message_id="Message ID of the giveaway",
        member="Member to evaluate",
    )
    async def slash_check(self, interaction: discord.Interaction, message_id: str, member: discord.Member) -> None:
        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        gw = self.bot.giveaway_mgr._row_to_giveaway_dict(row)
        passed, breakdown = await self.bot.giveaway_mgr.check_member_eligibility(
            gw, member, activity_mgr=getattr(self.bot, "activity_mgr", None)
        )
        _, weight, _, breakdown_str = await self.bot.giveaway_mgr.calculate_member_bonus(gw, member)

        container = KyokaContainer()
        status_label = "✅ Eligible" if passed else "❌ Ineligible"
        container.add_section(content=f"**Eligibility Check: {member.display_name} ({status_label})**")
        container.add_separator(divider=True)

        if not breakdown:
            container.add_text("No entry requirements configured.")
        else:
            lines = [f"{'✅' if b['passed'] else '❌'} **{b['label']}** ({b['reason']})" for b in breakdown]
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"Effective Weight: `{weight:.1f}x` ({breakdown_str})")
        await send_container_response(interaction, container, ephemeral=True)

    # 13. /giveaway exclude
    @giveaway_group.command(name="exclude", description="Exclude a user from winning a giveaway with a reason.")
    @app_commands.describe(
        message_id="Message ID of the giveaway",
        member="Member to exclude",
        reason="Reason for exclusion",
    )
    async def slash_exclude(
        self,
        interaction: discord.Interaction,
        message_id: str,
        member: discord.Member,
        reason: str,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT id FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        await self.bot.giveaway_mgr.exclude_participant(int(row["id"]), member.id, interaction.user.id, reason)
        await interaction.response.send_message(
            f"Excluded {member.mention} from giveaway entries. Reason: `{reason}`", ephemeral=True
        )

    # 14. /giveaway include
    @giveaway_group.command(name="include", description="Restore a previously excluded participant.")
    @app_commands.describe(
        message_id="Message ID of the giveaway",
        member="Member to restore",
    )
    async def slash_include(self, interaction: discord.Interaction, message_id: str, member: discord.Member) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT id FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        await self.bot.giveaway_mgr.include_participant(int(row["id"]), member.id, interaction.user.id)
        await interaction.response.send_message(f"Restored {member.mention} to giveaway entries.", ephemeral=True)

    # 15. /giveaway remind
    @giveaway_group.command(name="remind", description="Send an active giveaway countdown reminder to the channel.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_remind(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(int(message_id))
        if not gw or gw.get("is_ended"):
            return await interaction.response.send_message("Active giveaway not found.", ephemeral=True)

        channel = self.bot.get_channel(gw["channel_id"])
        if not channel:
            return await interaction.response.send_message("Channel unavailable.", ephemeral=True)

        ts = int(gw["ends_at"].timestamp())
        msg_link = f"https://discord.com/channels/{interaction.guild.id}/{gw['channel_id']}/{gw['message_id']}"
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", "🎉")

        await channel.send(
            f"### ⏰ Giveaway Reminder {gw_emoji}\n"
            f"> The giveaway for **[{gw['prize']}]({msg_link})** ends <t:{ts}:R>!\n"
            f"> Click the link above to join before time expires!"
        )
        await interaction.response.send_message("Reminder broadcasted successfully.", ephemeral=True)

    # 16. /giveaway clone
    @giveaway_group.command(name="clone", description="Clone settings from a previous giveaway into a new one.")
    @app_commands.describe(
        message_id="Message ID of the giveaway to clone",
        duration="Duration for the new giveaway (e.g. 1d, 2h)",
        channel="Channel to post in (default: current channel)",
    )
    async def slash_clone(
        self,
        interaction: discord.Interaction,
        message_id: str,
        duration: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage giveaways.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway to clone was not found.", ephemeral=True)

        gw = self.bot.giveaway_mgr._row_to_giveaway_dict(row)
        req_role = interaction.guild.get_role(gw["required_role_id"]) if gw.get("required_role_id") else None

        await self.slash_create(
            interaction,
            prize=gw["prize"],
            duration=duration,
            winners=gw["winner_count"],
            channel=channel or interaction.channel,
            required_role=req_role,
            description=gw.get("description", ""),
            entry_limit=gw.get("entry_limit", 0),
        )

    # 17. /giveaway export
    @giveaway_group.command(name="export", description="Export participants and weights as a CSV file.")
    @app_commands.describe(message_id="Message ID of the giveaway")
    async def slash_export(self, interaction: discord.Interaction, message_id: str) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to export giveaway records.", ephemeral=True)

        if not message_id.isdigit():
            return await interaction.response.send_message("Invalid message ID.", ephemeral=True)

        row = await self.bot.db.fetch_one("SELECT id, prize FROM giveaways WHERE message_id = $1;", int(message_id))
        if not row:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        csv_content = await self.bot.giveaway_mgr.export_giveaway_csv(int(row["id"]))
        if not csv_content:
            return await interaction.response.send_message("No records found for this giveaway.", ephemeral=True)

        file = discord.File(
            io.BytesIO(csv_content.encode("utf-8")),
            filename=f"giveaway_{row['id']}_export.csv",
        )
        await interaction.response.send_message(
            f"Here is the CSV export for giveaway **{row['prize']}**:", file=file, ephemeral=True
        )

    # 18. /giveaway templates
    @giveaway_group.command(name="templates", description="Manage and apply giveaway templates.")
    @app_commands.describe(
        action="Template action to perform",
        name="Name of the template (when saving, applying, or deleting)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="List saved templates", value="list"),
            app_commands.Choice(name="Delete a template", value="delete"),
        ]
    )
    async def slash_templates(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        name: Optional[str] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage templates.", ephemeral=True)

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if action.value == "list":
            tpls = await self.bot.giveaway_mgr.get_templates(interaction.guild.id)
            container = KyokaContainer()
            container.add_section(content=f"# **Giveaway Templates ({len(tpls)})**")
            container.add_separator(divider=True)
            if not tpls:
                container.add_text(f"{dot} No templates saved. Use `/giveaway create` or admin commands to save templates.")
            else:
                lines = [
                    f"{dot} **{t['name']}** — Prize: `{t['prize']}` ({t['winner_count']} winners, {t['duration_seconds'] // 3600}h)"
                    for t in tpls
                ]
                container.add_text("\n".join(lines))
            return await send_container_response(interaction, container, ephemeral=True)

        elif action.value == "delete":
            if not name:
                return await interaction.response.send_message("Please specify the template name to delete.", ephemeral=True)
            await self.bot.giveaway_mgr.delete_template(interaction.guild.id, name)
            return await interaction.response.send_message(f"Deleted template `{name}`.", ephemeral=True)

    # ─── HELPER FOR MESSAGE RESOLUTION ───────────────────────────────────────

    def _resolve_message_id(self, channel_id: int, message_id_input: Optional[str]) -> Optional[int]:
        if message_id_input and message_id_input.isdigit():
            return int(message_id_input)
        active_in_chan = [
            g for g in self.bot.giveaway_mgr._active_giveaways.values()
            if g["channel_id"] == channel_id
        ]
        if len(active_in_chan) == 1:
            return active_in_chan[0]["message_id"]
        return None

    # ─── LEGACY PREFIX SHORTCUTS PRESERVED ───────────────────────────────────

    @commands.command(name="gstart")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gstart(
        self,
        ctx: CustomContext,
        duration: Optional[str] = None,
        arg2: Optional[str] = None,
        *,
        rest: Optional[str] = None,
    ) -> None:
        """Legacy shortcut command for ?gstart preserving full backward compatibility."""
        if not duration:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            return await ctx.send(f"Usage: `{prefix}gstart <time> [winners] <prize>`")

        if arg2 and arg2.isdigit():
            winners = int(arg2)
            prize = rest or "Prize"
        elif arg2:
            winners = 1
            prize = f"{arg2} {rest}" if rest else arg2
        else:
            winners = 1
            prize = "Prize"

        delta = parse_giveaway_duration(duration)
        if not delta:
            return await ctx.send("Invalid duration format (e.g. 10m, 2h, 1d).")

        ends_at = datetime.datetime.now(datetime.timezone.utc) + delta
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", "🎉")

        card = build_giveaway_container(
            prize=prize,
            host_id=ctx.author.id,
            winner_count=winners,
            ends_at=ends_at,
            entries_count=0,
            gw_emoji=gw_emoji,
            dot=dot,
        )
        view = PersistentGiveawayView(self.bot)
        gw_msg = await send_container_response(
            ctx.channel,
            card,
            view=view,
            content=f"### {gw_emoji} New Giveaway {gw_emoji}",
        )
        if ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        await self.bot.giveaway_mgr.create_giveaway(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=gw_msg.id,
            host_id=ctx.author.id,
            prize=prize,
            winner_count=winners,
            ends_at=ends_at,
        )

    @commands.command(name="gend")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gend(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """Legacy shortcut command for ?gend."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message.")
        await self.conclude_giveaway(mid)
        await ctx.send("Giveaway concluded.")

    @commands.command(name="greroll")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_greroll(
        self,
        ctx: CustomContext,
        message_id: Optional[str] = None,
        winners: int = 1,
    ) -> None:
        """Legacy shortcut command for ?greroll."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message.")

        res = await self.bot.giveaway_mgr.reroll_giveaway(mid, count=winners, actor_id=ctx.author.id)
        if not res:
            return await ctx.send("Giveaway not found.")
        data, new_winners = res
        if not new_winners:
            return await ctx.send("No participants available to reroll.")
        mentions = ", ".join(f"<@{w}>" for w in new_winners)
        await ctx.send(f"🎉 New Winner(s) for **{data['prize']}**: {mentions}!")

    @commands.command(name="glist")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_glist(self, ctx: CustomContext) -> None:
        """Legacy shortcut command for ?glist."""
        active = self.bot.giveaway_mgr.get_active_giveaways_for_guild(ctx.guild.id)
        if not active:
            return await ctx.send("No active giveaways.")
        lines = [f"• **{g['prize']}** in <#{g['channel_id']}> ({g['winner_count']} winners)" for g in active]
        await ctx.send("\n".join(lines))

    @commands.command(name="gpause")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gpause(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """Pause a giveaway via prefix command."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message ID.")
        res = await self.bot.giveaway_mgr.pause_giveaway(mid, ctx.author.id)
        if not res:
            return await ctx.send("Could not pause giveaway. Verify it is active and not already paused.")
        await ctx.send(f"⏸️ Paused giveaway **{res['prize']}**.")

    @commands.command(name="gresume")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gresume(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """Resume a paused giveaway via prefix command."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message ID.")
        res = await self.bot.giveaway_mgr.resume_giveaway(mid, ctx.author.id)
        if not res:
            return await ctx.send("Could not resume giveaway. Verify it is paused.")
        await ctx.send(f"▶️ Resumed giveaway **{res['prize']}**.")

    @commands.command(name="gcancel")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gcancel(self, ctx: CustomContext, message_id: Optional[str] = None, *, reason: str = "") -> None:
        """Cancel a giveaway without drawing winners."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message ID.")
        res = await self.bot.giveaway_mgr.cancel_giveaway(mid, ctx.author.id, reason)
        if not res:
            return await ctx.send("Giveaway not found.")
        await ctx.send(f"❌ Cancelled giveaway **{res['prize']}**.")

    @commands.command(name="ginfo")
    @commands.guild_only()
    async def shortcut_ginfo(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """View giveaway details via prefix command."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message ID.")
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(mid)
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", mid)
            if not gw_row:
                return await ctx.send("Giveaway not found.")
            gw = self.bot.giveaway_mgr._row_to_giveaway_dict(gw_row)
        count = await self.bot.giveaway_mgr.get_participant_count(gw["id"])
        status = "Paused" if gw.get("is_paused") else ("Ended" if gw.get("is_ended") else "Active")
        await ctx.send(
            f"**Giveaway Info (ID: `{gw['id']}`)**\n"
            f"• Prize: **{gw['prize']}**\n"
            f"• Winners: `{gw['winner_count']}`\n"
            f"• Status: `{status}`\n"
            f"• Participants: `{count}`"
        )

    @commands.command(name="gcheck")
    @commands.guild_only()
    async def shortcut_gcheck(self, ctx: CustomContext, member: discord.Member, message_id: Optional[str] = None) -> None:
        """Check member eligibility via prefix command."""
        mid = self._resolve_message_id(ctx.channel.id, message_id)
        if not mid and ctx.message and ctx.message.reference:
            mid = ctx.message.reference.message_id
        if not mid:
            return await ctx.send("Please provide or reply to the giveaway message ID.")
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(mid)
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", mid)
            if not gw_row:
                return await ctx.send("Giveaway not found.")
            gw = self.bot.giveaway_mgr._row_to_giveaway_dict(gw_row)
        act_mgr = getattr(self.bot, "activity_mgr", None)
        passed, breakdown = await self.bot.giveaway_mgr.check_member_eligibility(gw, member, act_mgr)
        lines = [f"{'✅' if b['passed'] else '❌'} {b['type']}: {b['reason']}" for b in breakdown]
        res_str = "**Eligible**" if passed else "**Not Eligible**"
        await ctx.send(f"Eligibility for {member.mention}: {res_str}\n" + "\n".join(lines))

    @commands.command(name="gbonus")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def shortcut_gbonus(self, ctx: CustomContext, role: discord.Role, multiplier: float) -> None:
        """Configure role bonus multiplier via prefix command."""
        await self.bot.giveaway_mgr.add_bonus_role(
            guild_id=ctx.guild.id,
            role_id=role.id,
            multiplier=multiplier,
        )
        await ctx.send(f"✅ Configured **{multiplier}x** entry multiplier for {role.mention}.")

    @commands.command(name="greq")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def shortcut_greq(self, ctx: CustomContext, period: str, message_count: int) -> None:
        """Configure message activity requirement: +greq daily 10 or +greq weekly 100."""
        clean = period.lower().strip()
        if clean not in ("daily", "today", "weekly", "week"):
            return await ctx.send("Choose `daily` or `weekly` for period.")
        req_type = "messages_daily" if clean in ("daily", "today") else "messages_weekly"
        await self.bot.giveaway_mgr.add_requirement(
            guild_id=ctx.guild.id,
            req_type=req_type,
            req_value=str(message_count),
        )
        await ctx.send(f"✅ Added requirement: At least **{message_count}** messages {clean}.")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Giveaways(bot))
