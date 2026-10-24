"""
Kyoka 3.0 - Command Registry
Centralized metadata, discovery, category mapping, and permission checks for all
prefix and application (slash) commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Core.CommandRegistry")


@dataclass
class CommandMetadata:
    """Rich metadata for a registered command."""
    name: str
    qualified_name: str
    category: str
    description: str = ""
    usage: str = ""
    aliases: List[str] = field(default_factory=list)
    is_slash: bool = False
    is_prefix: bool = True
    is_hidden: bool = False
    is_owner_only: bool = False
    required_permissions: List[str] = field(default_factory=list)
    parent: Optional[str] = None


class CommandRegistry:
    """Central registry and query interface for all registered bot commands."""

    def __init__(self, bot: Optional[KyokaBot] = None) -> None:
        self.bot = bot
        self._commands: Dict[str, CommandMetadata] = {}
        self._alias_map: Dict[str, str] = {}
        self._category_map: Dict[str, Set[str]] = {}

    def register_command(
        self,
        name: str,
        category: str,
        description: str = "",
        usage: str = "",
        aliases: Optional[List[str]] = None,
        is_slash: bool = False,
        is_prefix: bool = True,
        is_hidden: bool = False,
        is_owner_only: bool = False,
        required_permissions: Optional[List[str]] = None,
        parent: Optional[str] = None,
    ) -> CommandMetadata:
        """Register command metadata."""
        cmd = CommandMetadata(
            name=name,
            qualified_name=f"{parent} {name}".strip() if parent else name,
            category=category,
            description=description,
            usage=usage,
            aliases=aliases or [],
            is_slash=is_slash,
            is_prefix=is_prefix,
            is_hidden=is_hidden,
            is_owner_only=is_owner_only,
            required_permissions=required_permissions or [],
            parent=parent,
        )
        norm_name = name.lower()
        self._commands[norm_name] = cmd

        # Index aliases
        for alias in cmd.aliases:
            self._alias_map[alias.lower()] = norm_name

        # Index categories
        cat_key = category.title()
        if cat_key not in self._category_map:
            self._category_map[cat_key] = set()
        self._category_map[cat_key].add(norm_name)

        return cmd

    def get_command(self, name: str) -> Optional[CommandMetadata]:
        """Look up command by primary name or alias."""
        clean = name.lower().strip()
        if clean in self._commands:
            return self._commands[clean]
        primary = self._alias_map.get(clean)
        if primary and primary in self._commands:
            return self._commands[primary]
        return None

    def get_commands_in_category(self, category: str, include_hidden: bool = False) -> List[CommandMetadata]:
        """Retrieve all commands within a category."""
        cmd_names = self._category_map.get(category.title(), set())
        results: List[CommandMetadata] = []
        for name in sorted(cmd_names):
            cmd = self._commands.get(name)
            if cmd:
                if cmd.is_hidden and not include_hidden:
                    continue
                results.append(cmd)
        return results

    def get_all_categories(self) -> List[str]:
        """Return list of distinct registered categories."""
        return sorted(self._category_map.keys())

    def rebuild_from_bot(self, bot: commands.Bot) -> None:
        """Dynamically build registry from live Discord bot command tree."""
        self._commands.clear()
        self._alias_map.clear()
        self._category_map.clear()

        # Enumerate prefix commands
        for cmd in bot.walk_commands():
            cog = cmd.cog
            cat = getattr(cog, "category", getattr(cog, "qualified_name", "General")) if cog else "General"
            perms = []
            owner_only = False

            for check in cmd.checks:
                check_name = getattr(check, "__qualname__", "")
                if "is_owner" in check_name or "is_primary_owner" in check_name:
                    owner_only = True
                elif "has_permissions" in check_name:
                    perms.append(check_name)

            self.register_command(
                name=cmd.name,
                category=cat,
                description=cmd.short_doc or cmd.help or "",
                usage=cmd.usage or f"{cmd.qualified_name} {cmd.signature}".strip(),
                aliases=list(cmd.aliases),
                is_slash=False,
                is_prefix=True,
                is_hidden=cmd.hidden or owner_only,
                is_owner_only=owner_only,
                required_permissions=perms,
                parent=cmd.parent.qualified_name if cmd.parent else None,
            )

        # Enumerate slash commands
        if hasattr(bot, "tree"):
            for app_cmd in bot.tree.get_commands():
                self.register_command(
                    name=app_cmd.name,
                    category=getattr(app_cmd, "category", "Slash"),
                    description=app_cmd.description or "",
                    is_slash=True,
                    is_prefix=False,
                    is_hidden=False,
                    is_owner_only=False,
                )

        logger.info(f"[CommandRegistry] Indexed {len(self._commands)} commands across {len(self._category_map)} categories.")
