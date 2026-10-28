"""
Kyoka 3.0 - Discord Invite Tracer & Attribution Cog
Features:
- Track real joins, leaves, fake joins, and bonus invites for every member
- Interactive paginated invite leaderboard (?inviteleaderboard / ?invlb)
- Member invite card with breakdown & server rank (?invites [member])
- List of members invited by a user (?invitedlist [member])
- Administrative invite controls: addinvites, removeinvites, resetinvites
- Automated join & leave log messages with inviter attribution
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import TYPE_CHECKING, Any, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.invite_tracker_manager import InviteTrackerManager

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Cogs.InviteTracker")

# Sleek Kyoka dark violet aesthetic
KYOKA_VIOLET = 0x2B0938


class InviteLeaderboardView(discord.ui.View):
    """Interactive paginated view for the guild invite leaderboard."""

    def __init__(
        self,
        cog: InviteTracker,
        guild: discord.Guild,
        author_id: int,
        page: int = 1,
        per_page: int = 10,
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild
        self.author_id = author_id
        self.page = page
        self.per_page = per_page
        self.total_count = 0
        self.total_pages = 1

    async def initialize(self) -> None:
        self.total_count = await self.cog.manager.get_leaderboard_count(self.guild.id)
        self.total_pages = max(1, math.ceil(self.total_count / self.per_page))
        self.page = max(1, min(self.page, self.total_pages))
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= self.total_pages
        self.page_indicator.label = f"Page {self.page}/{self.total_pages}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the member who requested this leaderboard can navigate it.",
                ephemeral=True,
            )
            return False
        return True

    async def build_embed(self) -> discord.Embed:
        offset = (self.page - 1) * self.per_page
        entries = await self.cog.manager.get_leaderboard(self.guild.id, limit=self.per_page, offset=offset)

        embed = discord.Embed(
            title=f"🏆 Invite Leaderboard • {self.guild.name}",
            description=f"> *Top inviters ranked by Net Invites (`Real - Left + Bonus`)*\n\n",
            color=KYOKA_VIOLET,
            timestamp=discord.utils.utcnow(),
        )

        if not entries:
            embed.description += "No members have tracked invites in this server yet.\nInvite your friends using standard server invites to claim the #1 spot!"
        else:
            lines = []
            for item in entries:
                rank = item["rank"]
                medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"`#{rank}`"
                user_id = item["user_id"]
                net = item["net"]
                reg = item["regular"]
                left = item["left"]
                fake = item["fake"]
                bonus = item["bonus"]

                user_str = f"<@{user_id}>"
                lines.append(
                    f"{medal} {user_str} — **{net:,}** invites\n"
                    f"     -# `✅ {reg:,} real` · `❌ {left:,} left` · `⚠️ {fake:,} fake` · `🎁 {bonus:+,} bonus`"
                )
            embed.description += "\n\n".join(lines)

        embed.set_thumbnail(url=self.guild.icon.url if self.guild.icon else None)
        embed.set_footer(
            text=f"Total Tracked Inviters: {self.total_count:,} • KYOKA 3.0",
            icon_url=self.guild.icon.url if self.guild.icon else None,
        )
        return embed

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page > 1:
            self.page -= 1
            self._update_buttons()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page < self.total_pages:
            self.page += 1
            self._update_buttons()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)


class ResetConfirmationView(discord.ui.View):
    """Confirmation button prompt for resetting guild invites."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You are not authorized to confirm this action.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Reset All", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        self.stop()
        await interaction.response.defer()


class InviteTracker(commands.Cog):
    """Advanced member invite tracer, attribution analytics, and competitive guild leaderboards."""

    category: str = "Utilities"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        if hasattr(bot, "invite_tracker_mgr") and bot.invite_tracker_mgr:
            self.manager: InviteTrackerManager = bot.invite_tracker_mgr
        else:
            self.manager = InviteTrackerManager(getattr(bot, "db", None), bot=bot)
            self.bot.invite_tracker_mgr = self.manager

    # ─────────────────────────────────────────────────────────────────────────────
    # LISTENERS
    # ─────────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Pre-cache guild invites on startup."""
        logger.info("Pre-caching guild invites for active guilds...")
        for guild in self.bot.guilds:
            try:
                await self.manager.load_guild_invites(guild)
            except Exception as e:
                logger.debug(f"Error loading invites for {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Cache invites when joining a new guild."""
        try:
            await self.manager.load_guild_invites(guild)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Cache newly created invite code."""
        self.manager.add_invite_to_cache(invite)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """Remove deleted invite code from cache."""
        self.manager.remove_invite_from_cache(invite)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Track invite attribution when a member joins."""
        if not member.guild:
            return

        guild = member.guild
        res = await self.manager.track_member_join(member)

        # Check if an invite log channel is configured
        settings = await self.manager.get_settings(guild.id)
        log_channel_id = settings.get("log_channel_id")
        if not log_channel_id or not settings.get("is_enabled", True):
            return

        channel = guild.get_channel(log_channel_id)
        if not channel or not hasattr(channel, "send"):
            return

        inviter = res.get("inviter")
        code = res.get("code") or "Unknown"
        is_fake = res.get("is_fake", False)
        is_vanity = res.get("is_vanity", False)
        is_oauth = res.get("is_oauth", False)
        stats = res.get("stats", {})
        net = stats.get("net", 0)

        # Calculate human-readable account age
        created_at = member.created_at
        now = discord.utils.utcnow()
        age_days = (now - created_at).days if created_at else 0
        if age_days > 365:
            age_str = f"{age_days // 365}y {(age_days % 365) // 30}m"
        elif age_days > 30:
            age_str = f"{age_days // 30}m {age_days % 30}d"
        else:
            age_str = f"{age_days}d"

        embed = discord.Embed(
            title="📥 Member Joined",
            color=0x10B981 if not is_fake else 0xF59E0B,
            timestamp=now,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if inviter:
            inviter_text = f"**{inviter.mention}** (`{inviter.name}`)"
            footer_stats = f"Inviter now has {net:,} invites (✅ {stats.get('regular', 0)} | ❌ {stats.get('left', 0)} | ⚠️ {stats.get('fake', 0)} | 🎁 {stats.get('bonus', 0)})"
        elif is_vanity:
            inviter_text = "**Vanity URL**"
            footer_stats = "Joined via server vanity invite link"
        elif is_oauth:
            inviter_text = "**Bot Integration (OAuth)**"
            footer_stats = "Bot invited via Discord developer portal"
        else:
            inviter_text = "**Unknown / Direct**"
            footer_stats = "Invite source could not be resolved"

        embed.description = (
            f"Welcome {member.mention} to **{guild.name}**!\n\n"
            f"• **Invited By:** {inviter_text}\n"
            f"• **Invite Code:** `{code}`\n"
            f"• **Account Age:** `{age_str}`"
            + ("\n• ⚠️ **Flag:** `New/Suspicious Account (Fake Invite)`" if is_fake else "")
        )
        embed.set_footer(text=footer_stats)

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.debug(f"Could not send join invite log: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Track member departure and deduct from inviter."""
        if not member.guild:
            return

        guild = member.guild
        res = await self.manager.track_member_leave(member)
        if not res:
            return

        settings = await self.manager.get_settings(guild.id)
        log_channel_id = settings.get("log_channel_id")
        if not log_channel_id or not settings.get("is_enabled", True):
            return

        channel = guild.get_channel(log_channel_id)
        if not channel or not hasattr(channel, "send"):
            return

        inviter = res.get("inviter")
        stats = res.get("stats", {})
        net = stats.get("net", 0)

        embed = discord.Embed(
            title="📤 Member Left",
            color=0xEF4444,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        inviter_text = f"**{inviter.mention}**" if inviter else f"`ID: {res.get('inviter_id')}`"
        embed.description = (
            f"**{member.name}** (`{member.id}`) left the server.\n\n"
            f"• **Originally Invited By:** {inviter_text}\n"
            f"• **Inviter Remaining:** **{net:,} net invites** (`{stats.get('regular', 0)} real`, `{stats.get('left', 0)} left`)"
        )
        embed.set_footer(text=f"Server: {guild.name}")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.debug(f"Could not send leave invite log: {e}")

    # ─────────────────────────────────────────────────────────────────────────────
    # USER COMMANDS
    # ─────────────────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="invites",
        aliases=["myinvites", "invcount", "invs"],
        description="View your or another member's total, real, left, fake, and bonus invites.",
    )
    @app_commands.describe(member="The member whose invites you want to view (defaults to yourself).")
    async def invites(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        """Display an itemized invite card showing real, left, fake, and bonus counts with rank."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        target = member or ctx.author
        stats = await self.manager.get_user_stats(ctx.guild.id, target.id)
        rank = await self.manager.get_user_rank(ctx.guild.id, target.id)
        inviter_info = await self.manager.get_user_inviter(ctx.guild.id, target.id)

        embed = discord.Embed(
            title=f"📨 Invite Card • {target.display_name}",
            color=KYOKA_VIOLET,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # Inviter string
        if inviter_info and inviter_info.get("inviter_id"):
            inv_id = inviter_info["inviter_id"]
            inv_member = ctx.guild.get_member(inv_id) or self.bot.get_user(inv_id)
            inviter_str = f"{inv_member.mention} (`{inv_member.name}`)" if inv_member else f"`ID: {inv_id}`"
            code_str = f" [Code: `{inviter_info.get('invite_code')}`]" if inviter_info.get("invite_code") else ""
            invited_by_line = f"{inviter_str}{code_str}"
        elif inviter_info and inviter_info.get("invite_code") == "VANITY":
            invited_by_line = "**Vanity URL**"
        elif inviter_info and inviter_info.get("invite_code") == "OAUTH_BOT":
            invited_by_line = "**Bot OAuth Integration**"
        else:
            invited_by_line = "*Unknown / Pre-dating tracker*"

        rank_display = f"#{rank:,}" if rank else "N/A"

        embed.description = (
            f"> ⚡ **{stats['net']:,} Net Invites**\n\n"
            f"• 🏆 **Server Rank:** **{rank_display}**\n"
            f"• 🔗 **Invited By:** {invited_by_line}\n"
        )

        embed.add_field(
            name="📊 Breakdown",
            value=(
                f"• ✅ **Real / Regular:** `{stats['regular']:,}`\n"
                f"• ❌ **Left:** `{stats['left']:,}`\n"
                f"• ⚠️ **Fake / Suspicious:** `{stats['fake']:,}`\n"
                f"• 🎁 **Bonus Added:** `{stats['bonus']:+,}`"
            ),
            inline=False,
        )

        embed.set_footer(
            text=f"Formula: Net = Real - Left + Bonus • {ctx.guild.name}",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="inviteleaderboard",
        aliases=["invleaderboard", "invlb", "topinvites", "inviteslb"],
        description="View the competitive server invite leaderboard with interactive pagination.",
    )
    async def inviteleaderboard(self, ctx: CustomContext) -> None:
        """Display the interactive top inviters leaderboard for this server."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        view = InviteLeaderboardView(cog=self, guild=ctx.guild, author_id=ctx.author.id, page=1, per_page=10)
        await view.initialize()
        embed = await view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(
        name="invitedlist",
        aliases=["invitelist", "whoinvited"],
        description="List members invited by you or another member.",
    )
    @app_commands.describe(member="The member whose invited list you want to inspect.")
    async def invitedlist(self, ctx: CustomContext, member: discord.Member | None = None) -> None:
        """Display recent members invited by a user and their retention status."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        target = member or ctx.author
        records = await self.manager.get_invited_members(ctx.guild.id, target.id, limit=20)

        embed = discord.Embed(
            title=f"📋 Members Invited by {target.display_name}",
            color=KYOKA_VIOLET,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not records:
            embed.description = f"{target.mention} hasn't invited any recorded members yet."
        else:
            lines = []
            for r in records:
                uid = r["user_id"]
                u = ctx.guild.get_member(uid) or self.bot.get_user(uid)
                u_str = u.mention if u else f"`{uid}`"
                status = "❌ Left" if r["has_left"] else "✅ In Server"
                fake_tag = " `[⚠️ Fake]`" if r["is_fake"] else ""
                code_tag = f"`{r['invite_code']}`" if r.get("invite_code") else ""
                lines.append(f"• {u_str} — {status}{fake_tag} ({code_tag})")
            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Showing up to 20 recent invites • {ctx.guild.name}")
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────────
    # ADMINISTRATIVE COMMANDS
    # ─────────────────────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="addinvites",
        aliases=["bonusinvites"],
        description="Add bonus invites to a server member (Admin only).",
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(member="The member to reward bonus invites to.", amount="Number of bonus invites to grant.")
    async def addinvites(self, ctx: CustomContext, member: discord.Member, amount: int) -> None:
        """Grant bonus invites to a member."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")
        if amount <= 0:
            return await ctx.send("❌ Amount must be a positive integer.")
        if amount > 10000:
            return await ctx.send("❌ Amount cannot exceed 10,000 per invocation.")

        stats = await self.manager.add_bonus_invites(ctx.guild.id, member.id, amount)
        embed = discord.Embed(
            title="🎁 Bonus Invites Added",
            description=(
                f"Successfully granted **+{amount:,}** bonus invites to {member.mention}.\n\n"
                f"• **New Total Net Invites:** **{stats['net']:,}**\n"
                f"• **Bonus Total:** `{stats['bonus']:+,}`"
            ),
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="removeinvites",
        aliases=["subinvites"],
        description="Remove bonus invites from a server member (Admin only).",
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(member="The member to deduct bonus invites from.", amount="Number of bonus invites to remove.")
    async def removeinvites(self, ctx: CustomContext, member: discord.Member, amount: int) -> None:
        """Deduct bonus invites from a member."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")
        if amount <= 0:
            return await ctx.send("❌ Amount must be a positive integer.")

        stats = await self.manager.remove_bonus_invites(ctx.guild.id, member.id, amount)
        embed = discord.Embed(
            title="🔻 Bonus Invites Removed",
            description=(
                f"Successfully removed **-{amount:,}** bonus invites from {member.mention}.\n\n"
                f"• **New Total Net Invites:** **{stats['net']:,}**\n"
                f"• **Bonus Total:** `{stats['bonus']:+,}`"
            ),
            color=0xEF4444,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="resetinvites",
        description="Reset invite statistics for a single member or the entire guild (Admin only).",
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(target="Specify '@member' to reset one user, or 'all' to reset all server invites.")
    async def resetinvites(self, ctx: CustomContext, target: str) -> None:
        """Reset invite stats for a member or clear the entire server invite registry."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        # Single member reset
        if target.lower() not in ("all", "server", "guild"):
            # Try to resolve member by mention or ID
            clean_id = target.strip("<@!>")
            member = None
            if clean_id.isdigit():
                member = ctx.guild.get_member(int(clean_id))

            if not member:
                return await ctx.send("❌ Please mention a valid member or type `all` to reset server-wide.")

            await self.manager.reset_user_invites(ctx.guild.id, member.id)
            embed = discord.Embed(
                title="🔄 Member Invites Reset",
                description=f"Invite statistics for {member.mention} have been reset to zero.",
                color=0x10B981,
            )
            return await ctx.send(embed=embed)

        # Server-wide reset requires confirmation
        view = ResetConfirmationView(author_id=ctx.author.id)
        confirm_embed = discord.Embed(
            title="⚠️ Server-Wide Invite Reset Confirmation",
            description=(
                f"Are you sure you want to completely **wipe all invite records and statistics** for **{ctx.guild.name}**?\n\n"
                "This action is **irreversible**. All member invite attributions, counts, and leaderboards will be deleted."
            ),
            color=0xEF4444,
        )
        msg = await ctx.send(embed=confirm_embed, view=view)
        await view.wait()

        if view.confirmed:
            await self.manager.reset_guild_invites(ctx.guild.id)
            success_embed = discord.Embed(
                title="✅ Guild Invites Wiped",
                description=f"All invite statistics and records for **{ctx.guild.name}** have been successfully wiped.",
                color=0x10B981,
            )
            await msg.edit(embed=success_embed, view=None)
        else:
            cancel_embed = discord.Embed(
                title="❌ Reset Cancelled",
                description="Server-wide invite reset was cancelled. No data was changed.",
                color=KYOKA_VIOLET,
            )
            await msg.edit(embed=cancel_embed, view=None)

    @commands.hybrid_command(
        name="setinvitechannel",
        aliases=["invitechannel", "invitelog"],
        description="Configure or disable the channel for real-time join/leave invite messages (Admin only).",
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(channel="The channel for invite join/leave logs, or leave empty to disable.")
    async def setinvitechannel(self, ctx: CustomContext, channel: discord.TextChannel | None = None) -> None:
        """Set or disable the channel where member join/leave invite messages are broadcast."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        if channel is None:
            await self.manager.set_log_channel(ctx.guild.id, None)
            embed = discord.Embed(
                title="🔕 Invite Logging Disabled",
                description="Member join and leave invite notifications have been disabled for this server.",
                color=KYOKA_VIOLET,
            )
            return await ctx.send(embed=embed)

        await self.manager.set_log_channel(ctx.guild.id, channel.id)
        embed = discord.Embed(
            title="🔔 Invite Logging Configured",
            description=f"Member join and leave invite notifications will now be dispatched to {channel.mention}.",
            color=0x10B981,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="invitesettings",
        aliases=["invitetrackersettings"],
        description="View current invite tracer configuration for this server.",
    )
    async def invitesettings(self, ctx: CustomContext) -> None:
        """Display server invite tracer settings."""
        if not ctx.guild:
            return await ctx.send("❌ This command can only be used in a server.")

        settings = await self.manager.get_settings(ctx.guild.id)
        ch_id = settings.get("log_channel_id")
        ch = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = ch.mention if ch else ("`None (Disabled)`" if not ch_id else f"`Unknown ({ch_id})`")
        total_tracked = await self.manager.get_leaderboard_count(ctx.guild.id)

        embed = discord.Embed(
            title=f"⚙️ Invite Tracer Settings • {ctx.guild.name}",
            color=KYOKA_VIOLET,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="📢 Logging Channel", value=ch_str, inline=True)
        embed.add_field(name="⚠️ Fake Account Age Threshold", value=f"`{settings.get('fake_threshold_days', 7)} days`", inline=True)
        embed.add_field(name="👥 Total Tracked Inviters", value=f"`{total_tracked:,}`", inline=True)
        embed.set_footer(text="Use ?setinvitechannel to configure logging • KYOKA 3.0")
        await ctx.send(embed=embed)


async def setup(bot: KyokaBot) -> None:
    """Load the InviteTracker cog into KyokaBot."""
    await bot.add_cog(InviteTracker(bot))
