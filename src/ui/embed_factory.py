"""
Kyoka 3.0 - Premium Aizen Embed Factory
Generates unified, elegant, responsive Discord embeds adhering to Aizen theme guidelines.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, List, Optional
import discord

from src.ui.theme import KyokaTheme


class KyokaEmbedFactory:
    """Factory creating sleek Aizen-styled embeds with consistent layouts and iconography."""

    @staticmethod
    def base(
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: int = KyokaTheme.PRIMARY,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
        footer_text: str = KyokaTheme.FOOTER_TEXT,
        footer_icon: Optional[str] = None,
        timestamp: bool = True,
    ) -> discord.Embed:
        """Create a foundational styled embed."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=dt.datetime.now(dt.timezone.utc) if timestamp else None,
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)

        embed.set_footer(text=footer_text, icon_url=footer_icon)
        return embed

    @classmethod
    def success(
        cls,
        title: str = "Action Successful",
        description: str = "",
        details: Optional[str] = None,
    ) -> discord.Embed:
        desc = f"**{description}**" if description else ""
        if details:
            desc = f"{desc}\n> {details}" if desc else f"> {details}"
        return cls.base(
            title=f"{KyokaTheme.ICON_SUCCESS} {title}",
            description=desc,
            color=KyokaTheme.SUCCESS,
        )

    @classmethod
    def error(
        cls,
        title: str = "Command Error",
        description: str = "",
        details: Optional[str] = None,
    ) -> discord.Embed:
        desc = f"**{description}**" if description else ""
        if details:
            desc = f"{desc}\n> {details}" if desc else f"> {details}"
        return cls.base(
            title=f"{KyokaTheme.ICON_ERROR} {title}",
            description=desc,
            color=KyokaTheme.ERROR,
        )

    @classmethod
    def warning(
        cls,
        title: str = "Warning",
        description: str = "",
        details: Optional[str] = None,
    ) -> discord.Embed:
        desc = f"**{description}**" if description else ""
        if details:
            desc = f"{desc}\n> {details}" if desc else f"> {details}"
        return cls.base(
            title=f"{KyokaTheme.ICON_WARNING} {title}",
            description=desc,
            color=KyokaTheme.WARNING,
        )

    @classmethod
    def info(
        cls,
        title: str = "Information",
        description: str = "",
    ) -> discord.Embed:
        return cls.base(
            title=f"{KyokaTheme.ICON_INFO} {title}",
            description=description,
            color=KyokaTheme.INFO,
        )

    @classmethod
    def loading(
        cls,
        title: str = "Processing Request",
        description: str = "Please wait while Kyoka synchronizes state...",
    ) -> discord.Embed:
        return cls.base(
            title=f"{KyokaTheme.ICON_LOADING} {title}",
            description=description,
            color=KyokaTheme.SECONDARY,
        )

    @classmethod
    def permission_denied(
        cls,
        reason: str = "You do not have the required permissions to execute this action.",
    ) -> discord.Embed:
        return cls.base(
            title=f"{KyokaTheme.ICON_SHIELD} Access Restricted",
            description=f"⛔ **Authorization Denied**\n> {reason}",
            color=KyokaTheme.ERROR,
        )
