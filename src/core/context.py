from __future__ import annotations

from typing import Any
import discord
from discord.ext import commands

from src.utils.containers import KyokaContainer, send_container_response
from src.utils.emojis import resolve_emoji


class CustomContext(commands.Context):
    """Custom context providing streamlined Components V2 container dispatchers and UI helpers."""

    async def send_container(
        self,
        container: KyokaContainer | list[KyokaContainer],
        view: discord.ui.View | None = None,
        ephemeral: bool = False,
        content: str | None = None,
        file: discord.File | None = None,
        files: list[discord.File] | None = None,
    ) -> Any:
        """Send a Components V2 Container card with full parameter support."""
        return await send_container_response(
            self,
            container,
            view=view,
            ephemeral=ephemeral,
            content=content,
            file=file,
            files=files,
        )

    async def _send_status_card(
        self,
        emoji_key: str,
        message: str,
        title: str,
        *,
        ephemeral: bool = False,
        prefer_animated: bool = False,
    ) -> Any:
        icon = resolve_emoji(self.bot, emoji_key, prefer_animated=prefer_animated)
        icon_str = f"{icon} " if icon else ""
        container = KyokaContainer(accent_color=None)
        container.add_text(f"{icon_str}**{title}**\n> {message}")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name}")
        return await self.send_container(container, ephemeral=ephemeral)

    async def send_success(
        self,
        message: str,
        title: str = "Success",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted success container card."""
        return await self._send_status_card(
            "SUCCESS", message, title, ephemeral=ephemeral, prefer_animated=True
        )

    async def send_error(
        self,
        message: str,
        title: str = "Error",
        ephemeral: bool = True,
    ) -> Any:
        """Send a formatted error container card."""
        return await self._send_status_card(
            "ERROR", message, title, ephemeral=ephemeral, prefer_animated=False
        )

    async def send_warning(
        self,
        message: str,
        title: str = "Warning",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted warning container card."""
        return await self._send_status_card(
            "WARNING", message, title, ephemeral=ephemeral, prefer_animated=False
        )

    async def send_info(
        self,
        message: str,
        title: str = "Information",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted informational container card."""
        return await self._send_status_card(
            "INFO", message, title, ephemeral=ephemeral, prefer_animated=False
        )

    async def send_loading(
        self,
        message: str = "Processing request...",
        title: str = "Working",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted loading container card with optional animated indicator."""
        return await self._send_status_card(
            "LOADING", message, title, ephemeral=ephemeral, prefer_animated=True
        )
