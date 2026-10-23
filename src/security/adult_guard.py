"""
Central fail-closed authorization guard for restricted Adult Humor commands.
Validates against ADULT_COMMAND_ALLOWLIST environment variable and Primary Owner.
"""
from __future__ import annotations

import logging
import os
from typing import Any
import discord

from src.security.owner import OWNER_ID, is_primary_owner

logger = logging.getLogger("Kyoka.Security.AdultGuard")


def get_adult_allowlist() -> set[int]:
    """
    Parse and validate authorized Discord user IDs from ADULT_COMMAND_ALLOWLIST.
    Fails closed (empty set) if missing, empty, or improperly formatted.
    Primary bot owner is always authorized.
    """
    raw = os.getenv("ADULT_COMMAND_ALLOWLIST", "").strip()
    allowlist: set[int] = {OWNER_ID}

    if not raw:
        return allowlist

    for token in raw.split(","):
        cleaned = token.strip()
        if cleaned.isdigit():
            allowlist.add(int(cleaned))

    return allowlist


def is_adult_authorized(user_id: int | None) -> bool:
    """Check if the given Discord user ID is on the adult command allowlist."""
    if user_id is None:
        return False
    try:
        uid = int(user_id)
        if is_primary_owner(uid):
            return True
        return uid in get_adult_allowlist()
    except (TypeError, ValueError):
        return False


async def authorize_adult(ctx_or_interaction: Any, action_name: str = "adult-action") -> bool:
    """
    Verify authorization before executing any adult-category command or fetching adult GIFs.
    If unauthorized, immediately sends a polite, private rejection notice without leaking keys or allowlists.
    """
    user_id = None
    if hasattr(ctx_or_interaction, "author") and ctx_or_interaction.author:
        user_id = ctx_or_interaction.author.id
    elif hasattr(ctx_or_interaction, "user") and ctx_or_interaction.user:
        user_id = ctx_or_interaction.user.id

    if is_adult_authorized(user_id):
        return True

    msg = (
        "⛔ **Access Denied: Restricted Category**\n"
        "> This command is part of the restricted **Adult Humor** suite.\n"
        "> Execution is limited to explicitly approved Discord accounts configured in `ADULT_COMMAND_ALLOWLIST`."
    )

    try:
        interaction = getattr(ctx_or_interaction, "interaction", None)
        if interaction is not None:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return False

        if isinstance(ctx_or_interaction, discord.Interaction):
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(msg, ephemeral=True)
            return False

        # Regular prefix context
        await ctx_or_interaction.send(msg)
    except Exception as e:
        logger.debug(f"Could not send adult authorization rejection notice: {e}")

    return False
