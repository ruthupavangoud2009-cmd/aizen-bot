"""
Kyoka 3.0 - Centralized Asset Manager
Manages localized Aizen-themed artwork, category banners, feature cards, and fallback URLs.
Provides seamless discord.File attachments for embeds and robust fallback handling.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple
import discord

logger = logging.getLogger("Kyoka.UI.AssetManager")

# Root directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = BASE_DIR / "assets" / "kyoka"


class AssetManager:
    """Enterprise asset resolver for Kyoka's Aizen visual ecosystem."""

    # Default fallback URLs if local files are missing
    FALLBACK_URLS: dict[str, str] = {
        "home": "https://media.discordapp.net/attachments/1234567890/kyoka_aizen_banner.png",
        "music": "https://media.discordapp.net/attachments/1234567890/music_banner.png",
        "ai": "https://media.discordapp.net/attachments/1234567890/ai_banner.png",
        "blox_fruits": "https://media.discordapp.net/attachments/1234567890/blox_fruits_ai.png",
        "tickets": "https://media.discordapp.net/attachments/1234567890/ticket_panel.png",
        "moderation": "https://media.discordapp.net/attachments/1234567890/moderation_banner.png",
        "vouches": "https://media.discordapp.net/attachments/1234567890/vouch_card.png",
        "service_bills": "https://media.discordapp.net/attachments/1234567890/service_bill.png",
        "verification": "https://media.discordapp.net/attachments/1234567890/verification_banner.png",
        "giveaways": "https://media.discordapp.net/attachments/1234567890/giveaway_banner.png",
        "welcome": "https://media.discordapp.net/attachments/1234567890/welcome_banner.png",
        "general": "https://media.discordapp.net/attachments/1234567890/general_banner.png",
        "leveling": "https://media.discordapp.net/attachments/1234567890/rank_banner.png",
        "premium": "https://media.discordapp.net/attachments/1234567890/premium_banner.png",
        "owner": "https://media.discordapp.net/attachments/1234567890/owner_banner.png",
    }

    # Map normalized category keys to local filenames in assets/kyoka/help/
    CATEGORY_HELP_ASSETS: dict[str, str] = {
        "home": "help_home.png",
        "general": "help_general.png",
        "moderation": "help_moderation.png",
        "automod": "help_automod.png",
        "welcome": "help_welcome.png",
        "verification": "help_verification.png",
        "tickets": "help_tickets.png",
        "reaction_roles": "help_reaction_roles.png",
        "giveaways": "help_giveaways.png",
        "music": "help_music.png",
        "afk": "help_afk.png",
        "vouches": "help_vouches.png",
        "service_bills": "help_service_bills.png",
        "blox_fruits": "help_blox_fruits.png",
        "ai": "help_ai.png",
        "ai_voice": "help_ai.png",
        "leveling": "help_leveling.png",
        "premium": "help_premium.png",
        "config": "help_config.png",
        "owner": "help_owner.png",
    }

    # Map feature keys to local filenames in assets/kyoka/features/
    FEATURE_ASSETS: dict[str, str] = {
        "welcome_banner": "welcome_banner.png",
        "goodbye_banner": "goodbye_banner.png",
        "music_banner": "music_banner.png",
        "ai_banner": "ai_banner.png",
        "blox_fruits_ai": "blox_fruits_ai.png",
        "ticket_panel": "ticket_panel.png",
        "vouch_card_background": "vouch_card_background.png",
        "service_bill_background": "service_bill_background.png",
        "verification_banner": "verification_banner.png",
        "reaction_roles_banner": "reaction_roles_banner.png",
        "giveaway_banner": "giveaway_banner.png",
        "rank_card_background": "rank_card_background.png",
        "announcement_banner": "announcement_banner.png",
        "afk_banner": "afk_banner.png",
        "moderation_banner": "moderation_banner.png",
        "premium_banner": "premium_banner.png",
    }

    @classmethod
    def get_help_image_path(cls, category_id: str) -> Optional[Path]:
        """Return absolute Path to local category help banner, or None if not found."""
        norm_key = category_id.lower().strip()
        filename = cls.CATEGORY_HELP_ASSETS.get(norm_key)
        if not filename:
            # Try fuzzy matching
            for key, fname in cls.CATEGORY_HELP_ASSETS.items():
                if key in norm_key or norm_key in key:
                    filename = fname
                    break

        if filename:
            path = ASSETS_DIR / "help" / filename
            if path.is_file():
                return path

        # Try fallback home
        home_path = ASSETS_DIR / "help" / "help_home.png"
        return home_path if home_path.is_file() else None

    @classmethod
    def get_feature_image_path(cls, feature_id: str) -> Optional[Path]:
        """Return absolute Path to local feature artwork banner, or None if not found."""
        norm_key = feature_id.lower().strip()
        filename = cls.FEATURE_ASSETS.get(norm_key)
        if not filename:
            for key, fname in cls.FEATURE_ASSETS.items():
                if key in norm_key or norm_key in key:
                    filename = fname
                    break

        if filename:
            path = ASSETS_DIR / "features" / filename
            if path.is_file():
                return path
        return None

    @classmethod
    def create_help_file(cls, category_id: str) -> Optional[discord.File]:
        """Create a discord.File for the specified category help banner."""
        path = cls.get_help_image_path(category_id)
        if path and path.is_file():
            try:
                # Use clean filename for attachment reference
                return discord.File(str(path), filename=path.name)
            except Exception as e:
                logger.error(f"Failed to create discord.File for {path}: {e}")
        return None

    @classmethod
    def create_feature_file(cls, feature_id: str) -> Optional[discord.File]:
        """Create a discord.File for the specified feature banner."""
        path = cls.get_feature_image_path(feature_id)
        if path and path.is_file():
            try:
                return discord.File(str(path), filename=path.name)
            except Exception as e:
                logger.error(f"Failed to create discord.File for feature {path}: {e}")
        return None

    @classmethod
    def attach_help_banner(cls, embed: discord.Embed, category_id: str) -> Optional[discord.File]:
        """
        Safely attach the category banner to the embed.
        If local file exists, sets attachment URL and returns discord.File.
        Otherwise falls back to hosted URL.
        """
        file_obj = cls.create_help_file(category_id)
        if file_obj:
            embed.set_image(url=f"attachment://{file_obj.filename}")
            return file_obj

        # Fallback to hosted URL
        norm_key = category_id.lower().strip()
        fallback_url = cls.FALLBACK_URLS.get(norm_key, cls.FALLBACK_URLS.get("home"))
        if fallback_url:
            embed.set_image(url=fallback_url)
        return None

    @classmethod
    def attach_feature_banner(cls, embed: discord.Embed, feature_id: str) -> Optional[discord.File]:
        """
        Safely attach a feature banner to the embed.
        If local file exists, sets attachment URL and returns discord.File.
        """
        file_obj = cls.create_feature_file(feature_id)
        if file_obj:
            embed.set_image(url=f"attachment://{file_obj.filename}")
            return file_obj

        # Fallback
        norm_key = feature_id.lower().strip()
        for k, v in cls.FALLBACK_URLS.items():
            if k in norm_key:
                embed.set_image(url=v)
                break
        return None
