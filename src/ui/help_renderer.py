"""
Kyoka 3.0 - Help Embed Renderer
Renders compact, beautiful Aizen-themed category lists, home panels, and detailed command cards.
Adheres strictly to the 5-15 commands per page rule, showing descriptions, usage examples,
aliases, and prefix/slash information with localized feature artwork.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import discord

from src.ui.theme import KyokaTheme
from src.ui.asset_manager import AssetManager
from src.ui.categories import CATEGORY_BY_TAG, get_category_by_query

logger = logging.getLogger("Kyoka.UI.HelpRenderer")


class KyokaHelpEmbed(discord.Embed):
    """Subclass of discord.Embed that supports banner_file attribute without violating __slots__."""
    __slots__ = ("banner_file",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.banner_file: Optional[discord.File] = None


class HelpRenderer:
    """Renders Aizen-themed embeds for Kyoka's modular help console."""

    @staticmethod
    def render_home_embed(
        bot_user: Optional[discord.User],
        prefix: str,
        total_commands: int,
        total_categories: int,
        guild_name: Optional[str] = None,
    ) -> KyokaHelpEmbed:
        """Render the compact home console embed with high-res Aizen hero banner."""
        embed = KyokaHelpEmbed(
            title="⛩️ KYOKA 3.0 • Command Console",
            description=(
                f"*\"Power isn't given. It's taken.\"* — **Aizen**\n\n"
                f"> **More Than a Bot, It's a Presence.**{f' Serving **{guild_name}**.' if guild_name else ''}\n"
                f"> Built for high-performance communities: high-fidelity audio, Blox Fruits AI,\n"
                f"> automated moderation, enterprise tickets, and community entertainment.\n\n"
                f"⚡ **Quick Start:**\n"
                f"• **Get Started:** Type `{prefix}help` to open the command menu\n"
                f"• **Use Prefix:** All commands work with `{prefix}` (e.g. `{prefix}play`, `{prefix}ai`)\n"
                f"• **Explore Categories:** Use the interactive menu or `{prefix}hca` for full archive\n"
                f"• **Need Support?** Type `{prefix}ticket` or join our official support server"
            ),
            color=KyokaTheme.PRIMARY,
        )

        embed.add_field(
            name="📊 System Status & Metrics",
            value=(
                f"• **Prefix:** `{prefix}` | **Slash:** `/[cmd]`\n"
                f"• **Available Commands:** `{total_commands}` across `{total_categories}` categories"
            ),
            inline=False,
        )

        embed.add_field(
            name="✨ Core Navigation",
            value=(
                "• Use the **Category Dropdown** below to inspect a module.\n"
                "• Use **◀️ / ▶️** buttons to page through commands (5–15 per page).\n"
                f"• Type `{prefix}help <command>` for syntax, aliases, and permissions.\n"
            ),
            inline=False,
        )

        banner_file = AssetManager.attach_help_banner(embed, "home")
        embed.banner_file = banner_file

        if bot_user and bot_user.display_avatar:
            embed.set_thumbnail(url=bot_user.display_avatar.url)

        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Kyoka Suigetsu")
        return embed

    @staticmethod
    def render_category_page(
        category_name: str,
        command_entries: List[Dict[str, Any]],
        page: int,
        total_pages: int,
        prefix: str,
    ) -> KyokaHelpEmbed:
        """
        Render a category page with 5-15 commands, each displaying:
        - Name & Aliases
        - Short description
        - Usage example
        - Prefix / Slash badge
        - Distinct category artwork
        """
        clean_title = category_name.split("・", 1)[-1].strip() if "・" in category_name else category_name
        embed = KyokaHelpEmbed(
            title=f"🌀 {category_name.upper()} MODULE",
            description=f"Showing page **{page}** of **{max(1, total_pages)}** • Use `{prefix}help <cmd>` for deep inspect.",
            color=KyokaTheme.PRIMARY,
        )

        cat_meta = CATEGORY_BY_TAG.get(category_name) or get_category_by_query(clean_title)
        image_key = cat_meta.image_key if cat_meta else "general"
        banner_file = AssetManager.attach_help_banner(embed, image_key)
        embed.banner_file = banner_file

        if not command_entries:
            embed.description = "*No commands available or authorized in this category.*"
            embed.set_footer(text=KyokaTheme.FOOTER_TEXT)
            return embed

        for entry in command_entries:
            name = entry.get("name", "unknown")
            desc = entry.get("description", "No description provided.") or "No description provided."
            usage = entry.get("usage", f"{prefix}{name}")
            aliases = entry.get("aliases", [])
            is_slash = entry.get("is_slash", False)

            alias_str = f" `[{', '.join(aliases[:3])}]`" if aliases else ""
            badge = " `[/]`" if is_slash else " `[Prefix]`"

            field_title = f"`{prefix}{name}`{alias_str}{badge}"
            field_value = f"{desc[:100]}\n> **Usage:** `{usage}`"

            embed.add_field(
                name=field_title,
                value=field_value,
                inline=False,
            )

        embed.set_footer(
            text=f"Page {page}/{max(1, total_pages)} • {KyokaTheme.FOOTER_TEXT}"
        )
        return embed

    @staticmethod
    def render_command_detail(
        name: str,
        description: str,
        usage: str,
        aliases: List[str],
        category: str,
        prefix: str,
        permissions: Optional[List[str]] = None,
        is_slash: bool = False,
    ) -> discord.Embed:
        """Render detailed inspection card for a single command."""
        embed = discord.Embed(
            title=f"🌀 Command Details: `{prefix}{name}`",
            description=description or "No documentation provided.",
            color=KyokaTheme.ACCENT,
        )

        embed.add_field(name="📂 Category", value=f"`{category}`", inline=True)
        embed.add_field(name="⚡ Type", value="`Slash Command`" if is_slash else "`Prefix Command`", inline=True)
        embed.add_field(name="🔄 Aliases", value=", ".join(f"`{a}`" for a in aliases) if aliases else "*None*", inline=True)

        embed.add_field(
            name="📝 Usage Syntax",
            value=f"```{usage or f'{prefix}{name}'}```",
            inline=False,
        )

        if permissions:
            embed.add_field(
                name="🛡️ Required Permissions",
                value=", ".join(f"`{p}`" for p in permissions),
                inline=False,
            )

        embed.set_footer(text=f"{KyokaTheme.FOOTER_TEXT} • Usage Guide")
        return embed
