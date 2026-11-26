"""
KYOKA — Safe Server Custom Command Builder Cog
Allows server administrators to create configurable prefix commands stored in PostgreSQL
using safe template variable substitution (zero arbitrary code execution).
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.ui.response import KyokaResponse, send_response
from src.utils.containers import KyokaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Utility.CustomCommands")

VALID_CMD_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def render_safe_template(template: str, message: discord.Message) -> str:
    """Safely substitute supported template variables without eval/format injection."""
    guild = message.guild
    author = message.author
    channel = message.channel

    replacements = {
        "{user}": str(author),
        "{user.mention}": author.mention,
        "{user.name}": getattr(author, "display_name", str(author)),
        "{user.id}": str(author.id),
        "{server}": guild.name if guild else "Direct Message",
        "{server.id}": str(guild.id) if guild else "0",
        "{members}": f"{guild.member_count or len(guild.members):,}" if guild else "1",
        "{channel}": getattr(channel, "mention", "#channel"),
        "{channel.name}": getattr(channel, "name", "channel"),
    }
    output = template
    for token, val in replacements.items():
        output = output.replace(token, str(val))
    return output[:2000]


class CustomCommandsCog(commands.Cog, name="CustomCommands"):
    """Safe, admin-configurable per-server custom commands."""
    category: str = "🔧・UTILITIES"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot
        self._cache: dict[int, dict[str, dict[str, Any]]] = {}
        self._cooldowns: dict[tuple[int, str, int], float] = {}

    async def cog_load(self) -> None:
        await self.load_cache()

    def _has_db(self) -> bool:
        db = getattr(self.bot, "db", None)
        return bool(db and getattr(db, "_connected_once", False))

    async def load_cache(self) -> None:
        """Warm custom command cache from PostgreSQL."""
        if not self._has_db():
            return
        try:
            rows = await self.bot.db.fetch_all("SELECT * FROM guild_custom_commands;")
            self._cache.clear()
            for r in rows:
                gid = int(r["guild_id"])
                self._cache.setdefault(gid, {})[str(r["name"]).lower()] = dict(r)
        except Exception as exc:
            logger.debug("Custom commands cache load notice: %s", exc)

    def get_guild_commands(self, guild_id: int) -> dict[str, dict[str, Any]]:
        return self._cache.get(guild_id, {})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Dispatch matching custom server commands safely."""
        if not message.guild or message.author.bot or not message.content:
            return

        guild_cmds = self._cache.get(message.guild.id)
        if not guild_cmds:
            return

        guild_mgr = getattr(self.bot, "guild_mgr", None)
        prefix = guild_mgr.get_prefix(message.guild.id) if guild_mgr else "+"
        if not message.content.startswith(prefix):
            return

        raw_after = message.content[len(prefix):].strip()
        if not raw_after:
            return
        cmd_token = raw_after.split()[0].lower()

        # Never shadow real built-in commands
        if self.bot.get_command(cmd_token) is not None:
            return

        entry = guild_cmds.get(cmd_token)
        if not entry:
            return

        # Role restriction check
        req_role_id = entry.get("required_role_id")
        if req_role_id and isinstance(message.author, discord.Member):
            if not any(r.id == int(req_role_id) for r in message.author.roles) and not message.author.guild_permissions.administrator:
                return

        # Cooldown check
        cd = max(1, int(entry.get("cooldown_seconds") or 3))
        ckey = (message.guild.id, cmd_token, message.author.id)
        now = time.monotonic()
        if now - self._cooldowns.get(ckey, 0.0) < cd:
            return
        self._cooldowns[ckey] = now
        if len(self._cooldowns) > 2000:
            self._cooldowns.clear()

        rendered = render_safe_template(str(entry["response"]), message)
        if entry.get("use_embed"):
            container = KyokaContainer(accent_color=None)
            title = str(entry.get("embed_title") or cmd_token).strip()
            container.add_section(content=f"**{title}**\n> {rendered}")
            await send_container_response(message.channel, container)
        else:
            await message.channel.send(rendered, allowed_mentions=discord.AllowedMentions(users=True))

        if self._has_db():
            try:
                await self.bot.db.execute(
                    "UPDATE guild_custom_commands SET uses = uses + 1 WHERE guild_id = ? AND name = ?;",
                    message.guild.id,
                    cmd_token,
                )
            except Exception:
                pass

    @commands.hybrid_group(
        name="customcmd",
        aliases=["cc", "customcommand"],
        invoke_without_command=True,
        description="Manage safe server-specific custom commands.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def cc_group(self, ctx: CustomContext) -> None:
        """Show custom command builder usage and list."""
        await self.cc_list(ctx)

    @cc_group.command(name="create", aliases=["add", "set"], description="Create or update a text custom command.")
    @app_commands.describe(name="Trigger name (letters, numbers, - or _)", response="Response template ({user}, {user.mention}, {server}, {members}, {channel})")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def cc_create(self, ctx: CustomContext, name: str, *, response: str) -> None:
        """Create or update a plain-text custom command."""
        clean_name = name.strip().lower()
        if not VALID_CMD_NAME_RE.match(clean_name):
            resp = KyokaResponse.warning(
                title="Invalid Command Name",
                description="Command names must be `1-32` characters (`a-z`, `0-9`, `_`, `-`).",
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        if self.bot.get_command(clean_name) is not None:
            resp = KyokaResponse.warning(
                title="Reserved Built-In Command",
                description=f"`{clean_name}` is already a built-in KYOKA command and cannot be overwritten.",
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        clean_resp = response.strip()[:1800]
        record = {
            "guild_id": ctx.guild.id,
            "name": clean_name,
            "response": clean_resp,
            "use_embed": False,
            "embed_title": None,
            "required_role_id": None,
            "cooldown_seconds": 3,
            "uses": 0,
            "created_by": ctx.author.id,
        }
        self._cache.setdefault(ctx.guild.id, {})[clean_name] = record

        if self._has_db():
            await self.bot.db.execute(
                """
                INSERT INTO guild_custom_commands (guild_id, name, response, use_embed, created_by)
                VALUES (?, ?, ?, FALSE, ?)
                ON CONFLICT (guild_id, name) DO UPDATE SET
                    response = EXCLUDED.response,
                    use_embed = FALSE,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                ctx.guild.id,
                clean_name,
                clean_resp,
                ctx.author.id,
            )

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id) if hasattr(self.bot, "guild_mgr") else "+"
        resp = KyokaResponse.success(
            title="Custom Command Saved",
            description=f"Run `{prefix}{clean_name}` anywhere in **{ctx.guild.name}** to trigger it.",
            fields=[
                ("Trigger", f"`{prefix}{clean_name}`", True),
                ("Mode", "`Text`", True),
                ("Preview", clean_resp[:300], False),
            ],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @cc_group.command(name="embed", description="Create a custom command rendered as a KYOKA container card.")
    @app_commands.describe(name="Trigger name", title="Card title", response="Card description/body")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def cc_embed(self, ctx: CustomContext, name: str, title: str, *, response: str) -> None:
        """Create or update a card-styled custom command."""
        clean_name = name.strip().lower()
        if not VALID_CMD_NAME_RE.match(clean_name) or self.bot.get_command(clean_name) is not None:
            resp = KyokaResponse.warning(
                title="Invalid or Reserved Name",
                description="Choose an unused `1-32` character alphanumeric name.",
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        clean_title = title.strip()[:200]
        clean_resp = response.strip()[:1800]
        self._cache.setdefault(ctx.guild.id, {})[clean_name] = {
            "guild_id": ctx.guild.id,
            "name": clean_name,
            "response": clean_resp,
            "use_embed": True,
            "embed_title": clean_title,
            "required_role_id": None,
            "cooldown_seconds": 3,
            "uses": 0,
            "created_by": ctx.author.id,
        }

        if self._has_db():
            await self.bot.db.execute(
                """
                INSERT INTO guild_custom_commands (guild_id, name, response, use_embed, embed_title, created_by)
                VALUES (?, ?, ?, TRUE, ?, ?)
                ON CONFLICT (guild_id, name) DO UPDATE SET
                    response = EXCLUDED.response,
                    use_embed = TRUE,
                    embed_title = EXCLUDED.embed_title,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                ctx.guild.id,
                clean_name,
                clean_resp,
                clean_title,
                ctx.author.id,
            )

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id) if hasattr(self.bot, "guild_mgr") else "+"
        resp = KyokaResponse.success(
            title="Custom Card Command Saved",
            description=f"Run `{prefix}{clean_name}` to display your custom container card.",
            fields=[("Title", f"`{clean_title}`", True), ("Trigger", f"`{prefix}{clean_name}`", True)],
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @cc_group.command(name="delete", aliases=["remove", "del"], description="Delete a custom server command.")
    @app_commands.describe(name="Custom command name to delete")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def cc_delete(self, ctx: CustomContext, name: str) -> None:
        """Delete a custom command."""
        clean_name = name.strip().lower()
        existed = clean_name in self._cache.get(ctx.guild.id, {})
        if existed:
            self._cache[ctx.guild.id].pop(clean_name, None)
        if self._has_db():
            await self.bot.db.execute(
                "DELETE FROM guild_custom_commands WHERE guild_id = ? AND name = ?;",
                ctx.guild.id,
                clean_name,
            )

        if not existed:
            resp = KyokaResponse.warning(
                title="Custom Command Not Found",
                description=f"No custom command named `{clean_name}` exists in this server.",
                author=ctx.author,
            )
            return await send_response(ctx, resp, ephemeral=True)

        resp = KyokaResponse.success(
            title="Custom Command Deleted",
            description=f"Removed custom command `{clean_name}`.",
            author=ctx.author,
        )
        await send_response(ctx, resp)

    @cc_group.command(name="list", description="List all custom commands configured in this server.")
    @commands.guild_only()
    async def cc_list(self, ctx: CustomContext) -> None:
        """List server custom commands."""
        cmds = self._cache.get(ctx.guild.id, {})
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id) if hasattr(self.bot, "guild_mgr") else "+"
        if not cmds:
            resp = KyokaResponse.info(
                title="Custom Commands",
                description=(
                    f"No custom commands configured yet in **{ctx.guild.name}**.\n\n"
                    f"**Create one:** `{prefix}cc create rules Check #rules for server guidelines!`\n"
                    f"**Variables:** `{{user}}`, `{{user.mention}}`, `{{server}}`, `{{members}}`, `{{channel}}`"
                ),
                author=ctx.author,
            )
            return await send_response(ctx, resp)

        lines = [
            f"• `{prefix}{name}` — {'`[Card]`' if data.get('use_embed') else '`[Text]`'} ({data.get('uses', 0)} uses)"
            for name, data in sorted(cmds.items())
        ]
        resp = KyokaResponse.info(
            title=f"Custom Commands ({len(cmds)})",
            description="\n".join(lines[:25]),
            author=ctx.author,
        )
        await send_response(ctx, resp)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(CustomCommandsCog(bot))
