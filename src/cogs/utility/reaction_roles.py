"""
Kyoka Discord Bot - Premium Reaction Roles System (Carl-bot & Dyno style)
Supports standard Emoji Reactions, Discord Interactive Buttons, and Select Menus.
Includes Normal (toggle), Unique (exclusive radio choice), and Verify (one-way claim) modes.
"""

from __future__ import annotations

import logging
import re
from typing import Any
import discord
from discord.ext import commands

from src.core.bot import KyokaBot
from src.core.config import Config
from src.core.context import CustomContext

logger = logging.getLogger("Kyoka.Cogs.ReactionRoles")

PURPLE = Config.COLORS.PRIMARY


def normalize_emoji(emoji: discord.Emoji | discord.PartialEmoji | str) -> str:
    """Normalize emoji to uniform key ('name:id' for custom, character for unicode)."""
    if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)):
        return f"{emoji.name}:{emoji.id}" if emoji.id else emoji.name
    s = str(emoji).strip()
    m = re.match(r"<a?:([a-zA-Z0-9_]+):([0-9]+)>", s)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return s


def format_emoji_display(emoji_str: str) -> str:
    """Format normalized emoji string into Discord renderable string."""
    if ":" in emoji_str:
        name, eid = emoji_str.split(":", 1)
        return f"<:{name}:{eid}>"
    return emoji_str


class PersistentRoleButton(discord.ui.Button):
    """Button component that persists and assigns/removes roles dynamically."""

    def __init__(self, role_id: int, label: str, emoji: str | None = None, mode: str = "normal", style: discord.ButtonStyle = discord.ButtonStyle.secondary) -> None:
        custom_id = f"kyoka_rr:{role_id}:{mode}"
        parsed_emoji = None
        if emoji:
            try:
                parsed_emoji = discord.PartialEmoji.from_str(emoji)
            except Exception:
                pass
        super().__init__(
            label=label[:80],
            style=style,
            custom_id=custom_id,
            emoji=parsed_emoji,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        parts = self.custom_id.split(":")
        role_id = int(parts[1])
        mode = parts[2] if len(parts) > 2 else "normal"

        guild = interaction.guild
        member = interaction.user
        role = guild.get_role(role_id)

        if not role:
            return await interaction.response.send_message("❌ This role no longer exists.", ephemeral=True)

        me = guild.me
        if not me.guild_permissions.manage_roles or role >= me.top_role:
            return await interaction.response.send_message(
                f"⚠️ I cannot assign {role.mention} due to role hierarchy. Please place my bot role above it.",
                ephemeral=True,
            )

        if mode == "verify":
            if role not in member.roles:
                await member.add_roles(role, reason="Reaction Role: Verify claim")
                return await interaction.response.send_message(f"✅ Verified! Granted {role.mention}.", ephemeral=True)
            return await interaction.response.send_message(f"ℹ️ You already have {role.mention}.", ephemeral=True)

        if mode == "unique":
            # Remove any sibling button roles from this message view
            view_roles = []
            if interaction.message and interaction.message.components:
                for row in interaction.message.components:
                    for comp in getattr(row, "children", []):
                        cid = getattr(comp, "custom_id", "")
                        if cid and cid.startswith("kyoka_rr:"):
                            try:
                                r_id = int(cid.split(":")[1])
                                if r_id != role.id:
                                    r_obj = guild.get_role(r_id)
                                    if r_obj and r_obj in member.roles:
                                        view_roles.append(r_obj)
                            except Exception:
                                pass
            if view_roles:
                await member.remove_roles(*view_roles, reason="Reaction Role: Exclusive choice switch")
            if role not in member.roles:
                await member.add_roles(role, reason="Reaction Role: Exclusive choice select")
                return await interaction.response.send_message(f"✅ Switched to {role.mention}!", ephemeral=True)
            else:
                await member.remove_roles(role, reason="Reaction Role: Exclusive toggle off")
                return await interaction.response.send_message(f"❌ Removed {role.mention}.", ephemeral=True)

        # Standard toggle mode
        if role in member.roles:
            await member.remove_roles(role, reason="Reaction Role: Toggle off")
            await interaction.response.send_message(f"❌ Removed {role.mention}.", ephemeral=True)
        else:
            await member.add_roles(role, reason="Reaction Role: Toggle on")
            await interaction.response.send_message(f"✅ Added {role.mention}!", ephemeral=True)


class PersistentRoleView(discord.ui.View):
    """View container for interactive Discord Button reaction roles."""

    def __init__(self) -> None:
        super().__init__(timeout=None)


class ReactionRoles(commands.Cog, name="Reaction Roles"):
    """Carl-bot & Dyno grade Reaction Roles system with Emojis & Buttons."""

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        # Register persistent view handler
        self.bot.add_view(PersistentRoleView())

    # ─── LISTENERS ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle role assignment on reaction add."""
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return

        norm_emoji = normalize_emoji(payload.emoji)
        binding = self.bot.reaction_role_mgr.get_binding(payload.message_id, norm_emoji)
        if not binding:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = payload.member
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                return

        if member.bot:
            return

        role = guild.get_role(int(binding["role_id"]))
        if not role:
            return

        me = guild.me
        if not me.guild_permissions.manage_roles or role >= me.top_role:
            logger.warning(f"Cannot assign role {role.name} in {guild.name}: role hierarchy conflict.")
            return

        mode = binding.get("mode", "normal")

        try:
            if mode == "verify":
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Reaction Role [{mode}]: {norm_emoji}")
                return

            if mode == "unique":
                # Strip all other roles registered on this message
                all_msg_bindings = self.bot.reaction_role_mgr.get_message_bindings(payload.message_id)
                sibling_roles = []
                for b in all_msg_bindings:
                    if int(b["role_id"]) != role.id:
                        r = guild.get_role(int(b["role_id"]))
                        if r and r in member.roles:
                            sibling_roles.append(r)
                if sibling_roles:
                    await member.remove_roles(*sibling_roles, reason="Reaction Role [unique]: switch selection")

                if role not in member.roles:
                    await member.add_roles(role, reason=f"Reaction Role [unique]: {norm_emoji}")
                return

            # Normal mode
            if role not in member.roles:
                await member.add_roles(role, reason=f"Reaction Role [normal]: {norm_emoji}")
        except discord.Forbidden:
            logger.warning(f"Forbidden error while assigning role {role.name} in {guild.name}")
        except Exception as e:
            logger.error(f"Error handling reaction add for role {role.name}: {e}", exc_info=e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle role removal on reaction remove."""
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return

        norm_emoji = normalize_emoji(payload.emoji)
        binding = self.bot.reaction_role_mgr.get_binding(payload.message_id, norm_emoji)
        if not binding:
            return

        # In verify mode, removing reaction does NOT remove the verified role
        if binding.get("mode") == "verify":
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        try:
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            return

        if member.bot:
            return

        role = guild.get_role(int(binding["role_id"]))
        if not role or role not in member.roles:
            return

        me = guild.me
        if not me.guild_permissions.manage_roles or role >= me.top_role:
            return

        try:
            await member.remove_roles(role, reason=f"Reaction Role [removed]: {norm_emoji}")
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.error(f"Error handling reaction remove for role {role.name}: {e}", exc_info=e)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Clean up reaction role bindings when host message is deleted."""
        if self.bot.reaction_role_mgr.get_message_bindings(payload.message_id):
            await self.bot.reaction_role_mgr.clear_bindings(payload.message_id)
            logger.info(f"Cleaned up reaction roles for deleted message {payload.message_id}")

    # ─── COMMANDS ─────────────────────────────────────────────────────────────

    @commands.group(
        name="reactionrole",
        aliases=["rr", "reactionroles"],
        invoke_without_command=True,
        help="Carl-bot / Dyno style Reaction Roles management.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def reactionrole(self, ctx: CustomContext) -> None:
        """Reaction Role configuration center and dashboard."""
        embed = discord.Embed(
            title="⚡ KYŌKA • Reaction Roles System",
            description=(
                "Create and manage seamless self-assignable roles like **Carl-bot** & **Dyno**!\n"
                "Supports classic **Reactions**, modern **Buttons**, and specialized operational modes.\n"
            ),
            color=PURPLE,
        )
        embed.add_field(
            name="🛠️ Management Commands",
            value=(
                f"`{ctx.prefix}rr create <#channel> <Title> [pairs...]` — Create a new embed panel\n"
                f"`{ctx.prefix}rr add <message_id> <emoji> <@role> [mode]` — Add reaction to any message\n"
                f"`{ctx.prefix}rr remove <message_id> <emoji>` — Remove reaction role from a message\n"
                f"`{ctx.prefix}rr button <#channel> <Title> <pairs...>` — Create modern clickable buttons\n"
                f"`{ctx.prefix}rr list` — View all active reaction role panels in server\n"
                f"`{ctx.prefix}rr clear <message_id>` — Delete all bindings on a message\n"
                f"`{ctx.prefix}rr modes` — View documentation on operating modes\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="💡 Quick Example",
            value=(
                f"**Create an instant panel:**\n"
                f"`{ctx.prefix}rr create #roles \"Select Roles\" 🎮=@Gamers 💻=@Devs 🎨=@Artists`\n\n"
                f"**Bind to an existing announcement:**\n"
                f"`{ctx.prefix}rr add 123456789012345678 🔔 @Updates normal`"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Manage Roles required", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @reactionrole.command(name="modes", help="Explain the reaction role modes (normal, unique, verify).")
    @commands.guild_only()
    async def rr_modes(self, ctx: CustomContext) -> None:
        """Display documentation for reaction role modes."""
        embed = discord.Embed(
            title="🏷️ Reaction Role Modes Explained",
            color=PURPLE,
            description="You can customize how roles behave when clicked or reacted to:",
        )
        embed.add_field(
            name="1. Normal (Default / Toggle)",
            value="React to claim the role, unreact to remove the role. Perfect for optional interest roles and opt-in alerts.",
            inline=False,
        )
        embed.add_field(
            name="2. Unique (Exclusive / Radio Choice)",
            value="Users can only pick **one** role from the message at a time. Picking a new role automatically strips any previous role from that panel (e.g. Regions, Colors, Factions).",
            inline=False,
        )
        embed.add_field(
            name="3. Verify (One-Way / Permanent Grant)",
            value="Users react to verify or agree to rules. Unreacting does **not** take the role away. Perfect for server verification and gatekeeping.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="add", help="Add a reaction role binding to an existing message.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_add(
        self,
        ctx: CustomContext,
        message_id: int,
        emoji: str,
        role: discord.Role,
        mode: str = "normal",
    ) -> None:
        """Bind an emoji and role to any existing message ID."""
        clean_mode = mode.lower()
        if clean_mode not in ("normal", "unique", "verify"):
            return await ctx.send("❌ Invalid mode. Choose between `normal`, `unique`, or `verify`.")

        me = ctx.guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I need the **Manage Roles** permission to give roles.")

        if role >= me.top_role:
            return await ctx.send(
                f"❌ I cannot assign {role.mention} because it is placed higher than my top role (`{me.top_role.name}`). "
                "Move my bot role higher in **Server Settings -> Roles**."
            )

        if role.is_default() or role.managed:
            return await ctx.send("❌ Cannot bind the `@everyone` role or managed integration roles.")

        # Find target message across server channels
        target_message: discord.Message | None = None
        target_channel: discord.TextChannel | None = None

        for ch in ctx.guild.text_channels:
            try:
                target_message = await ch.fetch_message(message_id)
                target_channel = ch
                break
            except (discord.NotFound, discord.Forbidden):
                continue

        if not target_message or not target_channel:
            return await ctx.send(
                f"❌ Could not find message with ID `{message_id}` in any text channel. Ensure the ID is correct and I have view access."
            )

        # Parse emoji and react to host message
        norm_key = normalize_emoji(emoji)
        try:
            if ":" in norm_key:
                name, eid = norm_key.split(":", 1)
                react_emoji = self.bot.get_emoji(int(eid)) or emoji
            else:
                react_emoji = norm_key
            await target_message.add_reaction(react_emoji)
        except Exception as e:
            return await ctx.send(f"❌ Failed to react with `{emoji}`. Ensure I have permission to add reactions and use external emojis: `{e}`")

        await self.bot.reaction_role_mgr.add_binding(
            guild_id=ctx.guild.id,
            channel_id=target_channel.id,
            message_id=target_message.id,
            emoji=norm_key,
            role_id=role.id,
            mode=clean_mode,
        )

        embed = discord.Embed(
            title="✅ Reaction Role Added",
            description=(
                f"Successfully bound **{format_emoji_display(norm_key)}** to {role.mention}!\n\n"
                f"• **Target Message:** [Jump to Message]({target_message.jump_url})\n"
                f"• **Channel:** {target_channel.mention}\n"
                f"• **Mode:** `{clean_mode.upper()}`\n"
            ),
            color=PURPLE,
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="remove", help="Remove an emoji reaction role from a message.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_remove(self, ctx: CustomContext, message_id: int, emoji: str) -> None:
        """Delete an emoji binding from a reaction role message."""
        norm_key = normalize_emoji(emoji)
        existing = self.bot.reaction_role_mgr.get_binding(message_id, norm_key)
        if not existing:
            return await ctx.send(f"❌ No reaction role found on message `{message_id}` for `{emoji}`.")

        await self.bot.reaction_role_mgr.remove_binding(message_id, norm_key)

        # Try to clear bot's reaction from the message
        channel = ctx.guild.get_channel(int(existing["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(message_id)
                if ":" in norm_key:
                    name, eid = norm_key.split(":", 1)
                    rem_emoji = self.bot.get_emoji(int(eid)) or emoji
                else:
                    rem_emoji = norm_key
                await msg.remove_reaction(rem_emoji, ctx.guild.me)
            except Exception:
                pass

        await ctx.send(f"✅ Removed reaction role binding `{format_emoji_display(norm_key)}` from message `{message_id}`.")

    @reactionrole.command(name="clear", help="Clear all reaction roles from a message.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_clear(self, ctx: CustomContext, message_id: int) -> None:
        """Clear all bindings attached to a message."""
        count = await self.bot.reaction_role_mgr.clear_bindings(message_id)
        if count == 0:
            return await ctx.send(f"ℹ️ Message `{message_id}` had no registered reaction roles.")
        await ctx.send(f"✅ Cleared `{count}` reaction role(s) from message `{message_id}`.")

    @reactionrole.command(name="list", help="List all reaction role messages in the server.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_list(self, ctx: CustomContext) -> None:
        """List every active reaction role panel in the guild."""
        bindings = self.bot.reaction_role_mgr.get_guild_bindings(ctx.guild.id)
        if not bindings:
            return await ctx.send(f"ℹ️ No reaction role panels are configured in **{ctx.guild.name}**. Use `{ctx.prefix}rr create` to make one!")

        # Group by message_id
        grouped: dict[int, list[dict[str, Any]]] = {}
        for b in bindings:
            mid = int(b["message_id"])
            if mid not in grouped:
                grouped[mid] = []
            grouped[mid].append(b)

        embed = discord.Embed(
            title=f"📋 Active Reaction Roles • {ctx.guild.name}",
            description=f"Currently managing **{len(grouped)}** reaction role message(s):\n",
            color=PURPLE,
        )

        for mid, rows in list(grouped.items())[:10]:
            cid = int(rows[0]["channel_id"])
            channel = ctx.guild.get_channel(cid)
            ch_mention = channel.mention if channel else f"<#{cid}>"
            jump_url = f"https://discord.com/channels/{ctx.guild.id}/{cid}/{mid}"

            lines = []
            for r in rows:
                role = ctx.guild.get_role(int(r["role_id"]))
                r_mention = role.mention if role else f"<@&{r['role_id']}> (deleted)"
                lines.append(f"{format_emoji_display(r['emoji'])} ➔ {r_mention} `[{r['mode']}]`")

            embed.add_field(
                name=f"Message ID: {mid} in {ch_mention}",
                value=f"**Jump:** [Link]({jump_url})\n" + "\n".join(lines[:8]),
                inline=False,
            )

        embed.set_footer(text=f"Total: {len(bindings)} active role bindings")
        await ctx.send(embed=embed)

    @reactionrole.command(name="create", help="Create a reaction role embed panel with emoji-role pairs.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_create(
        self,
        ctx: CustomContext,
        channel: discord.TextChannel,
        title: str,
        *pairs: str,
    ) -> None:
        """
        Create a new Carl-bot style reaction role panel.
        Usage: ?rr create #roles "Role Menu" 🎮=@Gamers 💻=@Developers
        """
        me = ctx.guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I need the **Manage Roles** permission to give roles.")

        if not channel.permissions_for(me).send_messages or not channel.permissions_for(me).add_reactions:
            return await ctx.send(f"❌ I don't have permission to send messages or add reactions in {channel.mention}.")

        parsed_pairs: list[tuple[str, discord.Role, str]] = []

        for p in pairs:
            # format: emoji=@Role or emoji=@Role:mode
            if "=" not in p:
                continue
            e_part, r_part = p.split("=", 1)
            e_str = e_part.strip()
            mode = "normal"
            if ":" in r_part and not (r_part.startswith("<@&") and r_part.endswith(">")):
                r_sub, mode_sub = r_part.rsplit(":", 1)
                if mode_sub.lower() in ("normal", "unique", "verify"):
                    r_part = r_sub
                    mode = mode_sub.lower()

            # Resolve role
            role_match = re.search(r"<@&([0-9]+)>", r_part) or re.search(r"^([0-9]+)$", r_part)
            role: discord.Role | None = None
            if role_match:
                role = ctx.guild.get_role(int(role_match.group(1)))
            else:
                role = discord.utils.get(ctx.guild.roles, name=r_part.strip())

            if role:
                parsed_pairs.append((e_str, role, mode))

        if not parsed_pairs:
            # If no pairs provided, give clear help message
            embed_help = discord.Embed(
                title="✨ How to Create a Reaction Role Panel",
                description=(
                    f"**Command Syntax:**\n"
                    f"`{ctx.prefix}rr create <#channel> \"<Panel Title>\" <emoji>=<@role> [emoji2=@role2...]`\n\n"
                    f"**Example (Standard Roles):**\n"
                    f"`{ctx.prefix}rr create {channel.mention} \"Game Roles\" 🎮=@Gamers ⚔️=@RPG 🕹️=@Retro`\n\n"
                    f"**Example with Modes (unique/verify):**\n"
                    f"`{ctx.prefix}rr create {channel.mention} \"Pick One Color\" 🔴=@Red:unique 🔵=@Blue:unique`"
                ),
                color=PURPLE,
            )
            return await ctx.send(embed=embed_help)

        # Build clean, high-end Carl-bot style panel embed
        lines = []
        for e_str, role, mode in parsed_pairs:
            mode_tag = f" `[{mode}]`" if mode != "normal" else ""
            lines.append(f"{e_str} • {role.mention}{mode_tag}")

        panel_embed = discord.Embed(
            title=f"⟡ {title}",
            description=(
                "React with the corresponding emojis below to get your roles!\n\n"
                + "\n".join(lines)
                + "\n\n────────────────────────────"
            ),
            color=PURPLE,
        )
        panel_embed.set_footer(text=f"{ctx.guild.name} • Roles Portal", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)

        panel_msg = await channel.send(embed=panel_embed)

        # Add bindings and react
        for e_str, role, mode in parsed_pairs:
            norm_key = normalize_emoji(e_str)
            await self.bot.reaction_role_mgr.add_binding(
                guild_id=ctx.guild.id,
                channel_id=channel.id,
                message_id=panel_msg.id,
                emoji=norm_key,
                role_id=role.id,
                mode=mode,
            )
            try:
                if ":" in norm_key:
                    name, eid = norm_key.split(":", 1)
                    react_obj = self.bot.get_emoji(int(eid)) or e_str
                else:
                    react_obj = norm_key
                await panel_msg.add_reaction(react_obj)
            except Exception as e:
                logger.debug(f"Notice reacting on panel: {e}")

        await ctx.send(f"✅ Reaction Role panel published in {channel.mention}! [Jump to Panel]({panel_msg.jump_url})")

    @reactionrole.command(name="button", aliases=["buttons"], help="Create an interactive Discord Button role panel.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def rr_button(
        self,
        ctx: CustomContext,
        channel: discord.TextChannel,
        title: str,
        *pairs: str,
    ) -> None:
        """
        Create a modern interactive Button role panel (like Dyno v2).
        Usage: ?rr button #roles "Notifications" Announcements=@Announcements Updates=@Updates
        """
        me = ctx.guild.me
        if not me.guild_permissions.manage_roles:
            return await ctx.send("❌ I need the **Manage Roles** permission to give roles.")

        parsed_buttons: list[tuple[str, discord.Role, str]] = []

        for p in pairs:
            if "=" not in p:
                continue
            lbl_part, r_part = p.split("=", 1)
            lbl = lbl_part.strip()
            mode = "normal"
            if ":" in r_part and not (r_part.startswith("<@&") and r_part.endswith(">")):
                r_sub, mode_sub = r_part.rsplit(":", 1)
                if mode_sub.lower() in ("normal", "unique", "verify"):
                    r_part = r_sub
                    mode = mode_sub.lower()

            role_match = re.search(r"<@&([0-9]+)>", r_part) or re.search(r"^([0-9]+)$", r_part)
            role: discord.Role | None = None
            if role_match:
                role = ctx.guild.get_role(int(role_match.group(1)))
            else:
                role = discord.utils.get(ctx.guild.roles, name=r_part.strip())

            if role:
                parsed_buttons.append((lbl, role, mode))

        if not parsed_buttons:
            return await ctx.send(
                f"**Usage:** `{ctx.prefix}rr button <#channel> \"<Title>\" Label=@Role [Label2=@Role2...]`\n"
                f"**Example:** `{ctx.prefix}rr button {channel.mention} \"Game Roles\" Minecraft=@Minecraft Valorant=@Valorant`"
            )

        view = PersistentRoleView()
        descriptions = []
        for lbl, role, mode in parsed_buttons[:25]:
            mode_tag = f" `[{mode}]`" if mode != "normal" else ""
            descriptions.append(f"🔘 **{lbl}** ➔ {role.mention}{mode_tag}")
            view.add_item(PersistentRoleButton(role_id=role.id, label=lbl, mode=mode))

        embed = discord.Embed(
            title=f"⚡ {title}",
            description=(
                "Click the buttons below to claim or remove your roles instantly!\n\n"
                + "\n".join(descriptions)
                + "\n\n────────────────────────────"
            ),
            color=PURPLE,
        )
        embed.set_footer(text=f"{ctx.guild.name} • Interactive Role Buttons", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)

        msg = await channel.send(embed=embed, view=view)
        await ctx.send(f"✅ Interactive Button Role panel published in {channel.mention}! [Jump to Panel]({msg.jump_url})")


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(ReactionRoles(bot))
