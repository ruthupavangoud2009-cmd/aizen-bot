"""
Kyoka Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by Discord Components V2 Container Cards.
Filters commands so users only see actions they have permission to execute.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyokaContainer, edit_container_response, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot


class Help(commands.Cog):
    """Enterprise SaaS Help & Module Console with dynamic permission filtering."""
    category: str = "Moderation"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    async def _can_run_command(
        self, cmd: commands.Command, ctx: CustomContext, is_dev: bool = False, is_server_owner: bool = False
    ) -> bool:
        """Check if the command should be visible in the help menu."""
        if cmd.hidden:
            return False

        # Developer check - owner/developer only
        if getattr(cmd.cog, "category", "") in ("Developer", "Owner & Developer") and not is_dev:
            return False

        return True

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to execute."""
        categories: dict[str, list[commands.Command]] = {}
        is_dev = False
        if hasattr(self.bot, "perm_mgr") and hasattr(self.bot.perm_mgr, "is_developer_sync"):
            is_dev = self.bot.perm_mgr.is_developer_sync(ctx.author.id)
        elif hasattr(self.bot, "is_owner"):
            is_dev = await self.bot.is_owner(ctx.author)

        is_server_owner = bool(ctx.guild and ctx.author.id == ctx.guild.owner_id)

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler", "noprefix"]:
                continue

            category_name = getattr(cog, "category", cog_name)
            # Remove Developer module completely - owner only, never displayed in public help
            if category_name.lower() in ("developer", "owner", "owner & developer"):
                continue

            # Standardized clean module names
            if category_name.lower() in ("security", "antinuke", "automod & security"):
                category_name = "Antinuke"
            elif cog_name.lower() in ("mediachannels", "media"):
                category_name = "Media"
            elif cog_name.lower() in ("giveaways", "giveaway"):
                category_name = "Giveaway"
            elif category_name.lower() in ("general", "utility", "utilities"):
                category_name = "Utility"
            elif category_name.lower() in ("music", "audio"):
                category_name = "Music"
            elif category_name.lower() in ("ticket", "tickets & support"):
                category_name = "Ticket"
            elif category_name.lower() in ("economy", "casino"):
                category_name = "Economy"
            elif category_name.lower() in ("fun", "games", "social & fun"):
                category_name = "Games"
            elif category_name.lower() in ("ai", "artificial intelligence"):
                category_name = "AI"

            if category_name not in categories:
                categories[category_name] = []

            def _collect_all(cmd_obj: commands.Command) -> list[commands.Command]:
                cmd_list = [cmd_obj]
                if isinstance(cmd_obj, commands.Group):
                    for sub_cmd in sorted(cmd_obj.commands, key=lambda s: s.qualified_name):
                        cmd_list.extend(_collect_all(sub_cmd))
                return cmd_list

            for cmd in cog.get_commands():
                for c in _collect_all(cmd):
                    if await self._can_run_command(c, ctx, is_dev=is_dev, is_server_owner=is_server_owner):
                        if c not in categories[category_name]:
                            categories[category_name].append(c)

        # Priority order for clean SaaS display
        priority_order = [
            "Antinuke",
            "Moderation",
            "Music",
            "Giveaway",
            "Ticket",
            "Utility",
            "Economy",
            "Games",
            "AI",
            "Media",
            "Premium",
        ]
        ordered_categories: dict[str, list[commands.Command]] = {}
        for cat in priority_order:
            if cat in categories and categories[cat]:
                ordered_categories[cat] = categories[cat]
        for cat, cmds in categories.items():
            if cat not in ordered_categories and cmds:
                ordered_categories[cat] = cmds

        return ordered_categories

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji for category header."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return ""

        mapping = {
            "Antinuke": getattr(e_reg, "antinuke", "") or e_reg.get("antinuke_pulse", e_reg.get("antinuke_shield", "")),
            "Music": getattr(e_reg, "music_playing", "") or e_reg.get("music_playing", e_reg.get("music", "")),
            "Ticket": e_reg.get("icon_ticket", e_reg.get("ticket_support", "")),
            "Moderation": e_reg.get("icon_moderation", e_reg.get("icon_mod", "")),
            "Premium": getattr(e_reg, "verified", "") or e_reg.get("verified_glow", e_reg.get("verified_premium", "")),
            "Giveaway": e_reg.get("s_giveaway", e_reg.get("discord_giveaway", e_reg.get("giveaway", ""))),
            "Media": e_reg.get("media", e_reg.get("icon_media", "")),
            "Utility": e_reg.get("icons_utility", e_reg.get("icons_settings", "")),
            "Economy": getattr(e_reg, "coin", "") or e_reg.get("coin_spin", e_reg.get("icon_dollar", "")),
            "Games": e_reg.get("icon_games", e_reg.get("icon_backpack", "")),
            "AI": getattr(e_reg, "sparkle", "") or e_reg.get("sparkle_shine", e_reg.get("ai", "")),
        }
        return mapping.get(cat_name, e_reg.get("icon_moderation", ""))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return None

        mapping = {
            "Antinuke": "antinuke_shield",
            "Music": "music",
            "Ticket": "icon_ticket",
            "Moderation": "icon_moderation",
            "Premium": "verified_premium",
            "Giveaway": "giveaway",
            "Media": "media",
            "Utility": "icons_utility",
            "Economy": "coin_spin",
            "Games": "icon_games",
            "AI": "sparkle_shine",
        }
        emoji_name = mapping.get(cat_name, "icon_moderation")
        return e_reg.get_select_emoji(emoji_name, fallback_unicode=None)

    def _build_home_container(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
        selected_val: str = "home",
    ) -> KyokaContainer:
        """Construct the Signature Kyoka SaaS Overview Card with Default Accent."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = "+"
        if hasattr(self.bot, "guild_mgr") and hasattr(self.bot.guild_mgr, "get_prefix"):
            current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        elif hasattr(self.bot, "command_prefix"):
            current_prefix = str(self.bot.command_prefix)

        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        e_reg = getattr(self.bot, "custom_emojis", None)

        # Animated heart pulse dot (zero unicode clutter)
        dot = ""
        if e_reg:
            dot = (
                getattr(e_reg, "heart_dot", "")
                or e_reg.animated("heart_pulse", fallback="")
                or e_reg.get("heart_pulse", "")
                or e_reg.get("heart_dot", "")
            )
        if not dot:
            dot = ">"

        bot_name = getattr(Config, "BOT_NAME", "Kyoka")

        # Default accent container (Dark Minimalist)
        container = KyokaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Hey, I'm {bot_name}**\n"
                f"> Built for our community — keeping your server safe, active, and effortlessly connected."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Latency:** `{ws_ping}ms`\n"
            f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
            f"{dot} **Available Commands:** `{total_commands}`"
        )
        container.add_separator(divider=True)

        # Dropdown Options (custom emojis only, clean labels)
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None) if e_reg else None
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": selected_val == "home",
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for cat_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": cat_name,
                "value": cat_name.lower(),
                "default": selected_val == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(cat_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a module to view commands...",
                "options": options,
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {author.display_name}**")
        container.add_separator(divider=True)

        buttons = []
        invite_url = getattr(Config, "INVITE_URL", "")
        support_url = getattr(Config, "SUPPORT_URL", "")
        if invite_url:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": f"Invite {bot_name}",
                "url": invite_url,
            })
        if support_url:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": support_url,
            })
        if buttons:
            container.add_action_row(buttons)

        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> KyokaContainer:
        """Construct category command card with default accent and animated folder icons."""
        cat_icon = self._get_category_emoji(cat_name)
        e_reg = getattr(self.bot, "custom_emojis", None)

        container = KyokaContainer(accent_color=None)
        cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
        container.add_section(
            content=(
                f"**{cat_icon_prefix}{cat_name} Commands**\n"
                f"> Listing `{len(commands_list)}` accessible command(s) for your role in this server."
            )
        )
        container.add_separator(divider=True)

        # Sort commands logically
        def _gen_sort_key(cmd: commands.Command) -> tuple[str, int, str]:
            parts = cmd.qualified_name.lower().split()
            root = parts[0]
            is_sub = 1 if len(parts) > 1 else 0
            return (root, is_sub, cmd.qualified_name.lower())

        sorted_cmds = sorted(commands_list, key=_gen_sort_key)
        formatted_cmds = ", ".join([f"`{cmd.qualified_name}`" for cmd in sorted_cmds])
        container.add_text(formatted_cmds)
        container.add_separator(divider=True)

        # Dropdown options
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None) if e_reg else None
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": False,
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for c_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": c_name,
                "value": c_name.lower(),
                "default": c_name.lower() == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(c_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a module to view commands...",
                "options": options,
            }
        ])

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name}**")
        container.add_separator(divider=True)

        buttons = []
        bot_name = getattr(Config, "BOT_NAME", "Kyoka")
        invite_url = getattr(Config, "INVITE_URL", "")
        support_url = getattr(Config, "SUPPORT_URL", "")
        if invite_url:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": f"Invite {bot_name}",
                "url": invite_url,
            })
        if support_url:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": support_url,
            })
        if buttons:
            container.add_action_row(buttons)

        return container

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules", "h"],
        description="Display the Kyoka command directory tailored to your permissions.",
    )
    async def help_command(self, ctx: CustomContext, *, command_or_module: str | None = None) -> None:
        """Interactive help menu filtered by user permissions."""
        visible_categories = await self._get_visible_categories(ctx)

        # direct command or module lookup
        if command_or_module:
            query = command_or_module.lower().strip()

            target_cmd = self.bot.get_command(query)
            if target_cmd and await self._can_run_command(target_cmd, ctx):
                current_prefix = "+"
                if hasattr(self.bot, "guild_mgr") and hasattr(self.bot.guild_mgr, "get_prefix"):
                    current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
                cat = getattr(target_cmd.cog, "category", "Moderation")
                cat_icon = self._get_category_emoji(cat)
                desc = target_cmd.description or target_cmd.help or "No detailed description available."
                aliases = ", ".join([f"`{a}`" for a in target_cmd.aliases]) if target_cmd.aliases else "`None`"
                usage = f"`{current_prefix}{target_cmd.qualified_name} {target_cmd.signature}`".strip()
                e_reg = getattr(self.bot, "custom_emojis", None)
                dot = getattr(e_reg, "heart_dot", "") or ">"

                container = KyokaContainer(accent_color=None)
                cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
                container.add_section(
                    content=(
                        f"**{cat_icon_prefix}Command: `{target_cmd.qualified_name}`**\n"
                        f"> {desc}"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"{dot} **Usage:** `{usage}`\n"
                    f"{dot} **Aliases:** {aliases} | **Category:** `{cat}`"
                )

                if isinstance(target_cmd, commands.Group) and target_cmd.commands:
                    sub_list = []
                    for sub in sorted(target_cmd.commands, key=lambda s: s.name):
                        if not sub.hidden and await self._can_run_command(sub, ctx):
                            sub_sig = f" {sub.signature}" if sub.signature else ""
                            sub_usage = f"`{current_prefix}{sub.qualified_name}{sub_sig}`".strip()
                            sub_desc = sub.description or sub.help or ""
                            if sub_desc:
                                sub_list.append(f"{dot} {sub_usage}\n> {sub_desc}")
                            else:
                                sub_list.append(f"{dot} {sub_usage}")
                    if sub_list:
                        container.add_separator(divider=True)
                        container.add_section(
                            content="**Subcommands:**\n" + "\n".join(sub_list)
                        )

                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

            # Direct module / category lookup
            target_cat_name = next((c for c in visible_categories.keys() if c.lower() == query), None)
            if target_cat_name:
                matched_cat = next((c for c in visible_categories.keys() if c.lower() == target_cat_name.lower()), None)
                if matched_cat:
                    custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
                    container = self._build_category_container(
                        ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                    )
                    await send_container_response(ctx, container)
                    return

        # Main Help Console
        custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
        container = self._build_home_container(ctx, visible_categories, custom_id_prefix)
        await send_container_response(ctx, container)

        def check(interaction: discord.Interaction) -> bool:
            if not interaction.data:
                return False
            custom_id = interaction.data.get("custom_id", "")
            return (
                custom_id.startswith(f"{custom_id_prefix}:")
                and interaction.user.id == ctx.author.id
            )

        while True:
            try:
                interaction: discord.Interaction = await self.bot.wait_for(
                    "interaction", check=check, timeout=120.0
                )
                custom_id = interaction.data.get("custom_id", "")
                action = custom_id.split(":")[-1]

                # Select Menu Navigation
                if action == "select_category":
                    selected = interaction.data.get("values", ["home"])[0]
                    if selected == "home":
                        new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    else:
                        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected), None)
                        if matched_cat:
                            new_container = self._build_category_container(
                                ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                            )
                        else:
                            new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")

                    await edit_container_response(interaction, new_container)

            except asyncio.TimeoutError:
                break


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Help(bot))
