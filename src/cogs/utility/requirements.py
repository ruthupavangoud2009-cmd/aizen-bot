from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.cogs.utility.giveaway import is_giveaway_authorized
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.Requirements")


class Requirements(commands.Cog):
    """
    KYOKA 3.0 Eligibility Requirements & Bonus Entries Management.
    Houses the `/requirements` slash group with all 8 documented subcommands.
    """

    category: str = "Utility"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    requirements_group = app_commands.Group(
        name="requirements",
        description="KYOKA 3.0 Giveaway Requirements & Bonus Multipliers",
    )

    # 19. /requirements add
    @requirements_group.command(name="add", description="Add an eligibility requirement to a giveaway or server defaults.")
    @app_commands.describe(
        req_type="Type of eligibility requirement",
        value="Requirement value (e.g. role ID/mention, message count, day count, or tag string)",
        giveaway_id="Optional giveaway database ID (leave blank for server-wide defaults)",
        channel="Optional channel constraint (for message activity in a specific channel)",
    )
    @app_commands.choices(
        req_type=[
            app_commands.Choice(name="Must have specific role", value="role_required"),
            app_commands.Choice(name="Must NOT have role (excluded)", value="role_excluded"),
            app_commands.Choice(name="Must have ANY of roles (comma-separated IDs)", value="role_any"),
            app_commands.Choice(name="Must have ALL of roles (comma-separated IDs)", value="role_all"),
            app_commands.Choice(name="Messages sent today", value="messages_daily"),
            app_commands.Choice(name="Messages sent in past 7 days", value="messages_weekly"),
            app_commands.Choice(name="Messages in specific channel", value="messages_channel"),
            app_commands.Choice(name="Discord account age (in days)", value="account_age_days"),
            app_commands.Choice(name="Server membership age (in days)", value="server_age_days"),
            app_commands.Choice(name="Equipped server tag (Clan tag)", value="server_tag"),
        ]
    )
    async def slash_add(
        self,
        interaction: discord.Interaction,
        req_type: app_commands.Choice[str],
        value: str,
        giveaway_id: Optional[int] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage requirements.", ephemeral=True)

        clean_val = value.strip()
        # Clean role mentions if present
        if req_type.value in ("role_required", "role_excluded"):
            clean_val = clean_val.replace("<@&", "").replace(">", "").strip()
            if not clean_val.isdigit():
                return await interaction.response.send_message("Please provide a valid role mention or ID.", ephemeral=True)

        elif req_type.value in ("role_any", "role_all"):
            clean_val = re_clean_ids = ",".join(
                part.replace("<@&", "").replace(">", "").strip()
                for part in clean_val.split(",")
                if part.replace("<@&", "").replace(">", "").strip().isdigit()
            )
            if not clean_val:
                return await interaction.response.send_message("Please provide valid role mentions or IDs.", ephemeral=True)

        elif req_type.value in ("messages_daily", "messages_weekly", "messages_channel", "account_age_days", "server_age_days"):
            if not clean_val.isdigit() or int(clean_val) < 1:
                return await interaction.response.send_message("Value must be a positive number.", ephemeral=True)

        chan_id = channel.id if channel else None
        req_id = await self.bot.giveaway_mgr.add_requirement(
            interaction.guild.id,
            giveaway_id,
            req_type.value,
            clean_val,
            channel_id=chan_id,
        )

        scope_str = f"giveaway `#{giveaway_id}`" if giveaway_id else "server defaults"
        await interaction.response.send_message(
            f"✅ Added requirement (ID: `{req_id}`) for {scope_str}: **{req_type.name}** (`{clean_val}`).",
            ephemeral=True,
        )

    # 20. /requirements remove
    @requirements_group.command(name="remove", description="Remove an eligibility requirement by its requirement ID.")
    @app_commands.describe(requirement_id="The ID of the requirement to remove (view IDs via /requirements list)")
    async def slash_remove(self, interaction: discord.Interaction, requirement_id: int) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage requirements.", ephemeral=True)

        await self.bot.giveaway_mgr.remove_requirement(requirement_id)
        await interaction.response.send_message(f"Removed requirement `#{requirement_id}`.", ephemeral=True)

    # 21. /requirements list
    @requirements_group.command(name="list", description="List all eligibility requirements configured for a giveaway or server.")
    @app_commands.describe(giveaway_id="Optional giveaway database ID (leave blank for all server requirements)")
    async def slash_list(self, interaction: discord.Interaction, giveaway_id: Optional[int] = None) -> None:
        reqs = await self.bot.giveaway_mgr.get_requirements(interaction.guild.id, giveaway_id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyokaContainer()
        title = f"Requirements for Giveaway #{giveaway_id}" if giveaway_id else f"Server Default Requirements: {interaction.guild.name}"
        container.add_section(content=f"# **{title}**")
        container.add_separator(divider=True)

        if not reqs:
            container.add_text(f"{dot} No eligibility requirements are currently configured.")
        else:
            lines = []
            for r in reqs:
                gw_tag = f"[GW #{r['giveaway_id']}] " if r.get("giveaway_id") else "[Default] "
                lines.append(f"{dot} `ID {r['id']}` {gw_tag}**{r['req_type']}**: `{r['req_value']}`")
            container.add_text("\n".join(lines))

        await send_container_response(interaction, container, ephemeral=True)

    # 22. /requirements test
    @requirements_group.command(name="test", description="Test a member against configured requirements without joining.")
    @app_commands.describe(
        member="Member to test (defaults to yourself)",
        giveaway_id="Optional giveaway database ID",
    )
    async def slash_test(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        giveaway_id: Optional[int] = None,
    ) -> None:
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            return await interaction.response.send_message("Target must be a member in this server.", ephemeral=True)

        gw = self.bot.giveaway_mgr.get_giveaway_by_id(giveaway_id) if giveaway_id else None
        if not gw:
            gw = {
                "id": giveaway_id,
                "guild_id": interaction.guild.id,
                "bonus_stacking_policy": "highest",
                "bonus_multiplier_cap": 10.0,
            }

        passed, breakdown = await self.bot.giveaway_mgr.check_member_eligibility(
            gw,
            target,
            activity_mgr=getattr(self.bot, "activity_mgr", None),
        )
        _, weight, _, breakdown_str = await self.bot.giveaway_mgr.calculate_member_bonus(gw, target)

        status_tag = "✅ Passed All Requirements" if passed else "❌ Ineligible"
        container = KyokaContainer()
        container.add_section(content=f"**Eligibility Test: {target.display_name} ({status_tag})**")
        container.add_separator(divider=True)

        if not breakdown:
            container.add_text("No entry requirements currently configured. Anyone can enter!")
        else:
            lines = [f"{'✅' if b['passed'] else '❌'} **{b['label']}** ({b['reason']})" for b in breakdown]
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"Bonus Multiplier: `{weight:.1f}x` ({breakdown_str})")
        await send_container_response(interaction, container, ephemeral=True)

    # 23. /requirements activity
    @requirements_group.command(name="activity", description="Configure daily or weekly message activity requirements.")
    @app_commands.describe(
        period="Activity measurement period",
        min_messages="Minimum required qualifying messages",
        giveaway_id="Optional giveaway database ID (leave blank for server defaults)",
        channel="Optional channel constraint (for channel-specific activity)",
    )
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Daily (messages sent today)", value="messages_daily"),
            app_commands.Choice(name="Weekly (messages sent over rolling 7 days)", value="messages_weekly"),
            app_commands.Choice(name="Channel-specific (messages in specified channel)", value="messages_channel"),
        ]
    )
    async def slash_activity(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str],
        min_messages: int,
        giveaway_id: Optional[int] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage requirements.", ephemeral=True)

        if min_messages < 1:
            return await interaction.response.send_message("Message count must be at least 1.", ephemeral=True)

        chan_id = channel.id if channel else None
        req_id = await self.bot.giveaway_mgr.add_requirement(
            interaction.guild.id,
            giveaway_id,
            period.value,
            str(min_messages),
            channel_id=chan_id,
        )
        scope = f"giveaway `#{giveaway_id}`" if giveaway_id else "server defaults"
        chan_text = f" in {channel.mention}" if channel else ""
        await interaction.response.send_message(
            f"✅ Configured activity requirement (ID: `{req_id}`) for {scope}: "
            f"**{period.name}** >= `{min_messages}` messages{chan_text}.",
            ephemeral=True,
        )

    # 24. /requirements roles
    @requirements_group.command(name="roles", description="Configure required, permitted, or excluded roles.")
    @app_commands.describe(
        mode="Role requirement logic",
        role="The target role to configure",
        giveaway_id="Optional giveaway database ID (leave blank for server defaults)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Must have this role", value="role_required"),
            app_commands.Choice(name="Must NOT have this role (excluded)", value="role_excluded"),
        ]
    )
    async def slash_roles(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        role: discord.Role,
        giveaway_id: Optional[int] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage requirements.", ephemeral=True)

        req_id = await self.bot.giveaway_mgr.add_requirement(
            interaction.guild.id,
            giveaway_id,
            mode.value,
            str(role.id),
        )
        scope = f"giveaway `#{giveaway_id}`" if giveaway_id else "server defaults"
        await interaction.response.send_message(
            f"✅ Configured role requirement (ID: `{req_id}`) for {scope}: {mode.name} -> {role.mention}.",
            ephemeral=True,
        )

    # 25. /requirements tag
    @requirements_group.command(name="tag", description="Configure supported Discord server-tag verification.")
    @app_commands.describe(
        tag="The tag members must have equipped in their Discord primary profile",
        giveaway_id="Optional giveaway database ID (leave blank for server defaults)",
    )
    async def slash_tag(
        self,
        interaction: discord.Interaction,
        tag: str,
        giveaway_id: Optional[int] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to manage requirements.", ephemeral=True)

        clean_tag = tag.strip().upper().replace("[", "").replace("]", "")
        if not clean_tag:
            return await interaction.response.send_message("Please provide a valid tag string.", ephemeral=True)

        req_id = await self.bot.giveaway_mgr.add_requirement(
            interaction.guild.id,
            giveaway_id,
            "server_tag",
            clean_tag,
        )

        note = (
            "\n\n> ℹ️ **Discord API Limitation Notice:**\n"
            "> Discord Server Tags (Clans) are an experimental Discord platform feature. "
            "KYOKA reads official `member.primary_guild.tag`. "
            "Members who have equipped your server tag in their profile will pass automatically. "
            "If a member's client or server does not have Clan features activated by Discord, "
            "they will be informed with a clear explanation rather than a silent failure."
        )

        await interaction.response.send_message(
            f"✅ Configured server tag requirement (ID: `{req_id}`): Must have `[{clean_tag}]` equipped.{note}",
            ephemeral=True,
        )

    # 26. /requirements bonus
    @requirements_group.command(name="bonus", description="Configure role-based bonus entry multipliers.")
    @app_commands.describe(
        role="Role that receives bonus entries",
        multiplier="Multiplication factor (e.g. 2.0 for 2x, 3.0 for 3x)",
        extra_entries="Flat extra bonus entries (e.g. +1, +5)",
        giveaway_id="Optional giveaway database ID (leave blank for server defaults)",
    )
    async def slash_bonus(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        multiplier: float = 1.0,
        extra_entries: int = 0,
        giveaway_id: Optional[int] = None,
    ) -> None:
        if not await is_giveaway_authorized(self.bot, interaction.user, interaction.guild):
            return await interaction.response.send_message("Not authorized to configure bonus roles.", ephemeral=True)

        if multiplier < 1.0:
            return await interaction.response.send_message("Multiplier must be at least 1.0x.", ephemeral=True)

        bonus_id = await self.bot.giveaway_mgr.add_bonus_role(
            interaction.guild.id,
            role.id,
            multiplier=multiplier,
            extra_entries=extra_entries,
            giveaway_id=giveaway_id,
        )
        scope = f"giveaway `#{giveaway_id}`" if giveaway_id else "server defaults"
        await interaction.response.send_message(
            f"✅ Configured bonus entries (ID: `{bonus_id}`) for {scope}: {role.mention} -> `{multiplier:.1f}x` multiplier (+{extra_entries} extra entries).",
            ephemeral=True,
        )

    # ─── PREFIX COMMAND GROUP ────────────────────────────────────────────────

    @commands.group(name="requirements", aliases=["reqs", "requirement", "req"], invoke_without_command=True)
    async def prefix_requirements(self, ctx: commands.Context) -> None:
        """KYOKA 3.0 Giveaway Requirements & Bonus Multipliers via prefix."""
        p = ctx.prefix
        await ctx.send(
            f"**Giveaway Requirements Console**\n"
            f"> `{p}requirements list [giveaway_id]` — List configured requirements\n"
            f"> `{p}requirements add <type> <value> [giveaway_id]` — Add a requirement\n"
            f"> `{p}requirements remove <req_id>` — Delete requirement by ID\n"
            f"> `{p}requirements test [@member] [giveaway_id]` — Test eligibility\n"
            f"> `{p}requirements bonus <@role> <multiplier> [giveaway_id]` — Set role bonus"
        )

    @prefix_requirements.command(name="list")
    async def prefix_req_list(self, ctx: commands.Context, giveaway_id: Optional[int] = None) -> None:
        reqs = await self.bot.giveaway_mgr.get_requirements(ctx.guild.id, giveaway_id=giveaway_id)
        if not reqs:
            return await ctx.send("No requirements configured.")
        lines = [f"`#{r['id']}` **{r['requirement_type']}**: `{r.get('requirement_value')}`" for r in reqs]
        await ctx.send(f"**Configured Requirements:**\n" + "\n".join(lines))

    @prefix_requirements.command(name="remove", aliases=["del", "rm"])
    async def prefix_req_remove(self, ctx: commands.Context, req_id: int) -> None:
        if not await is_giveaway_authorized(self.bot, ctx.author, ctx.guild):
            return await ctx.send("Not authorized to manage requirements.")
        ok = await self.bot.giveaway_mgr.remove_requirement(req_id, ctx.guild.id)
        if ok:
            await ctx.send(f"✅ Removed requirement `#{req_id}`.")
        else:
            await ctx.send(f"Requirement `#{req_id}` not found.")

    @prefix_requirements.command(name="test")
    async def prefix_req_test(self, ctx: commands.Context, member: Optional[discord.Member] = None, giveaway_id: Optional[int] = None) -> None:
        target = member or ctx.author
        eligible, reasons, weight = await self.bot.giveaway_mgr.evaluate_eligibility(target, giveaway_id=giveaway_id)
        status = "Eligible ✅" if eligible else "Ineligible ❌"
        msg = f"**Eligibility for {target.mention}:** {status} (Weight: `{weight}x`)"
        if reasons:
            msg += "\n" + "\n".join(f"> • {r}" for r in reasons)
        await ctx.send(msg)

    @prefix_requirements.command(name="bonus")
    async def prefix_req_bonus(self, ctx: commands.Context, role: discord.Role, multiplier: float = 1.0, extra_entries: int = 0, giveaway_id: Optional[int] = None) -> None:
        if not await is_giveaway_authorized(self.bot, ctx.author, ctx.guild):
            return await ctx.send("Not authorized to configure bonus roles.")
        bonus_id = await self.bot.giveaway_mgr.add_bonus_role(ctx.guild.id, role.id, multiplier=multiplier, extra_entries=extra_entries, giveaway_id=giveaway_id)
        await ctx.send(f"✅ Configured bonus `#{bonus_id}`: {role.mention} -> `{multiplier:.1f}x` (+{extra_entries}).")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Requirements(bot))
