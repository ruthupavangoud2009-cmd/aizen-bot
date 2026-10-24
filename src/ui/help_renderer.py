"""
Kyoka 3.0 - Help Embed Renderer
Renders compact, beautiful Aizen-themed category lists, home panels, and detailed command cards.
Adheres strictly to the 5-15 commands per page rule, showing descriptions, usage examples,
aliases, and prefix/slash information.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import discord

from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.UI.HelpRenderer")


class HelpRenderer:
    """Renders Aizen-themed embeds for Kyoka's modular help console."""

    @staticmethod
    def render_home_embed(
        bot_user: Optional[discord.User],
        prefix: str,
        total_commands: int,
        total_categories: int,
        guild_name: Optional[str] = None,
    ) -> discord.Embed:
        """Render the compact home console embed."""
        embed = discord.Embed(
            title=f"🌀 KYOKA 3.0 • Command Console",
            description=(
                f"Welcome to **KYOKA 3.0 (Aizen Edition)**{f' in **{guild_name}**' if guild_name else ''}.\n"
                f"A production-grade Discord bot featuring high-fidelity music, enterprise tickets, "
                f"anti-nuke, AI, and advanced server utilities.\n\n"
                f"> **Prefix:** `{prefix}` (Also accepts mentions & slash commands)\n"
                f"> **Total Commands:** `{total_commands}` registered across `{total_categories}` categories\n"
                f"> **Quick Start:** Select a category below or type `{prefix}help <command>`"
            ),
            color=KyokaTheme.PRIMARY,
        )

        embed.add_field(
            name="📚 Core Navigation",
            value=(
                "• Use the **Category Dropdown** below to inspect a module.\n"
                "• Use **◀️ / ▶️** buttons to page through commands (5–15 per page).\n"
                "• Type `+help <command>` for syntax, aliases, and permissions."
            ),
            inline=False,
        )

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
    ) -> discord.Embed:
        """
        Render a category page with 5-15 commands, each displaying:
        - Name & Aliases
        - Short description
        - Usage example
        - Prefix / Slash badge
        """
        embed = discord.Embed(
            title=f"🌀 {category_name.upper()} MODULE",
            description=f"Showing page **{page}** of **{max(1, total_pages)}** • Use `{prefix}help <cmd>` for deep inspect.",
            color=KyokaTheme.PRIMARY,
        )

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
            badge = " `[/]`" if is_slash else " `[+]`"

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
