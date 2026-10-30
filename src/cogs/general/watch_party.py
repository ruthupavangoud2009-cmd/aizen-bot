from __future__ import annotations

import logging

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.core.bot import KyokaBot
from src.watch_party import broadcast_room, new_token, player_url, token_hash, validate_media_url

logger = logging.getLogger("Kyoka.WatchParty")


async def send_reply(ctx: CustomContext, content: str | None = None, *, embed: discord.Embed | None = None, ephemeral: bool = False) -> None:
    if ctx.interaction:
        if ctx.interaction.response.is_done():
            await ctx.interaction.followup.send(content, embed=embed, ephemeral=ephemeral)
        else:
            await ctx.interaction.response.send_message(content, embed=embed, ephemeral=ephemeral)
        return
    await ctx.send(content, embed=embed)


def parse_timestamp(value: str) -> float | None:
    try:
        parts = value.strip().split(":")
        if not 1 <= len(parts) <= 3 or any(not part.isdecimal() for part in parts):
            return None
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return float(total) if total < 86_400 else None
    except ValueError:
        return None


class WatchParty(commands.Cog):
    """Synchronized web-based video rooms managed through Discord."""

    category = "Watch Party"

    def __init__(self, bot: KyokaBot) -> None:
        self.bot = bot

    async def _room(self, guild_id: int) -> dict | None:
        expired = await self.bot.db.fetch_all(
            """UPDATE watch_party_rooms SET status = 'closed', closed_at = NOW()
               WHERE guild_id = ? AND status <> 'closed'
               AND last_activity < NOW() - INTERVAL '24 hours' RETURNING room_id""",
            guild_id,
        )
        for row in expired:
            await broadcast_room(row["room_id"], {"type": "closed"})
        return await self.bot.db.fetch_one(
            "SELECT * FROM watch_party_rooms WHERE guild_id = ? AND status <> 'closed' ORDER BY created_at DESC LIMIT 1",
            guild_id,
        )

    async def _host_room(self, ctx: CustomContext, *, manager_fallback: bool = False) -> dict | None:
        if not ctx.guild:
            await send_reply(ctx, "Watch Party commands are available only in a server.", ephemeral=True)
            return None
        room = await self._room(ctx.guild.id)
        if not room:
            await send_reply(ctx, "There is no active Watch Party in this server.", ephemeral=True)
            return None
        if int(room["host_id"]) != ctx.author.id and not (manager_fallback and ctx.author.guild_permissions.manage_guild):
            await send_reply(ctx, "Only the room host or a server manager can control this Watch Party.", ephemeral=True)
            return None
        return room

    @commands.hybrid_group(name="watch", aliases=["watchparty"], invoke_without_command=True, description="Manage synchronized KYOKA Watch Parties.")
    async def watch(self, ctx: CustomContext) -> None:
        prefix = ctx.prefix
        embed = discord.Embed(
            title="⛩️ KYOKA WATCH PARTY",
            description=(
                "Watch browser-playable video together with synchronized playback. "
                "The bot manages the room; each member plays the media in their own browser.\n\n"
                f"`{prefix}watch create` · Create a room\n"
                f"`{prefix}watch play <https-url>` · Set and play a direct video URL\n"
                f"`{prefix}watch pause` / `{prefix}watch resume` · Control playback\n"
                f"`{prefix}watch seek <time>` · Seek (for example `1:23` or `00:01:23`)\n"
                f"`{prefix}watch sync` · Broadcast the current state\n"
                f"`{prefix}watch invite` · Rotate and display an invite\n"
                f"`{prefix}watch info` · Show room details\n"
                f"`{prefix}watch stop` / `{prefix}watch close` · Stop or close the room\n"
                f"`{prefix}watch transfer @member` · Transfer host controls\n"
                f"`{prefix}watch leave` · Leave the room roster"
            ),
            color=Config.COLORS.PRIMARY,
        )
        embed.set_footer(text="Direct HTTPS MP4, M4V, WebM, OGV and OGG media URLs only. No DRM bypass or Discord Go Live.")
        await send_reply(ctx, embed=embed)

    @watch.command(name="create", description="Create a synchronized Watch Party room.")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def watch_create(self, ctx: CustomContext) -> None:
        active = await self._room(ctx.guild.id)
        if active:
            await send_reply(ctx, f"This server already has an active room: `{active['room_id']}`. Use `{ctx.prefix}watch info`.", ephemeral=True)
            return

        invite = new_token()
        host_key = new_token()
        room_id = new_token()[:12]
        settings = await self.bot.db.fetch_one(
            "SELECT max_members FROM watch_party_settings WHERE guild_id = ?",
            ctx.guild.id,
        )
        max_members = int(settings["max_members"]) if settings else 25
        try:
            await self.bot.db.execute(
                """INSERT INTO watch_party_rooms
                   (room_id, guild_id, host_id, invite_hash, host_hash, max_members, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'idle')""",
                room_id, ctx.guild.id, ctx.author.id, token_hash(invite), token_hash(host_key), max_members,
            )
        except Exception as exc:
            logger.warning("Watch Party room creation failed: %s", exc)
            await send_reply(ctx, "The room could not be created. Please try again shortly.", ephemeral=True)
            return

        invite_url = player_url(room_id, invite)
        control_url = player_url(room_id, host_key, invite)
        embed = discord.Embed(
            title="⛩️ KYOKA WATCH PARTY CREATED",
            description=f"**Host:** {ctx.author.mention}\n**Status:** Waiting for a video\n**Room:** `{room_id}`\n\nJoin the web player to watch. Playback is synchronized between connected browsers.",
            color=Config.COLORS.PRIMARY,
        )
        embed.add_field(name="Invite", value=f"[Join Watch Party]({invite_url})", inline=False)
        embed.set_footer(text="Use watch play with a direct HTTPS video URL. Discord does not broadcast video.")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Join Watch Party", url=invite_url, style=discord.ButtonStyle.link, emoji="🎬"))
        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, view=view)
        else:
            await ctx.send(embed=embed, view=view)
        try:
            await ctx.author.send(
                f"Your KYOKA Watch Party host controls: [Open host player]({control_url})\n"
                "Keep this private. Anyone with this URL can control playback."
            )
        except discord.Forbidden:
            await send_reply(ctx, "I couldn't DM your private host controls. You can still control playback with the `watch` Discord commands.", ephemeral=True)

    @watch.command(name="play", description="Play a supported direct HTTPS video URL.")
    async def watch_play(self, ctx: CustomContext, url: str) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        if not validate_media_url(url):
            await send_reply(ctx, "Unsupported URL. Provide a direct HTTPS URL ending in MP4, M4V, WebM, OGV, or OGG.", ephemeral=True)
            return
        await self.bot.db.execute(
            "UPDATE watch_party_rooms SET source_url = ?, current_time = 0, status = 'playing', playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = ?",
            url.strip(), room["room_id"],
        )
        await broadcast_room(room["room_id"], {"type": "state", "source": url.strip(), "currentTime": 0, "status": "playing"})
        await send_reply(ctx, "▶️ Video set. Connected viewers will load it and start playback.", ephemeral=True)

    async def _set_status(self, ctx: CustomContext, status: str, position: float | None = None) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        if status == "playing" and not room.get("source_url"):
            await send_reply(ctx, "Set a video first with `watch play <url>`.", ephemeral=True)
            return
        if position is None:
            await self.bot.db.execute(
                "UPDATE watch_party_rooms SET status = ?, playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = ?",
                status, room["room_id"],
            )
        else:
            await self.bot.db.execute(
                "UPDATE watch_party_rooms SET current_time = ?, status = ?, playback_updated_at = NOW(), last_activity = NOW() WHERE room_id = ?",
                position, status, room["room_id"],
            )
        await broadcast_room(room["room_id"], {"type": "state", "source": room.get("source_url"), "currentTime": position if position is not None else room.get("current_time", 0), "status": status})
        await send_reply(ctx, f"Watch Party playback set to **{status}**.", ephemeral=True)

    @watch.command(name="pause", description="Pause playback for all viewers.")
    async def watch_pause(self, ctx: CustomContext) -> None:
        await self._set_status(ctx, "paused")

    @watch.command(name="resume", description="Resume playback for all viewers.")
    async def watch_resume(self, ctx: CustomContext) -> None:
        await self._set_status(ctx, "playing")

    @watch.command(name="stop", description="Stop playback without closing the room.")
    async def watch_stop(self, ctx: CustomContext) -> None:
        await self._set_status(ctx, "stopped", 0)

    @watch.command(name="seek", description="Seek playback to a timestamp such as 1:23.")
    async def watch_seek(self, ctx: CustomContext, timestamp: str) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        position = parse_timestamp(timestamp)
        if position is None:
            await send_reply(ctx, "Invalid timestamp. Use `SS`, `MM:SS`, or `HH:MM:SS`.", ephemeral=True)
            return
        await self._set_status(ctx, room["status"], position)

    @watch.command(name="sync", description="Broadcast the saved playback state to all viewers.")
    async def watch_sync(self, ctx: CustomContext) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        current_time = float(room.get("current_time") or 0)
        if room["status"] == "playing" and room.get("playback_updated_at"):
            current_time += max(
                0,
                (discord.utils.utcnow() - room["playback_updated_at"]).total_seconds(),
            )
        await broadcast_room(room["room_id"], {
            "type": "state",
            "source": room.get("source_url"),
            "currentTime": current_time,
            "status": room["status"],
        })
        await send_reply(ctx, "🔄 Current room state synchronized to connected viewers.", ephemeral=True)

    @watch.command(name="invite", description="Create a fresh guest invitation link.")
    async def watch_invite(self, ctx: CustomContext) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        invite = new_token()
        await self.bot.db.execute(
            "UPDATE watch_party_rooms SET invite_hash = ?, last_activity = NOW() WHERE room_id = ?",
            token_hash(invite), room["room_id"],
        )
        await send_reply(ctx, f"🎬 [Join the Watch Party]({player_url(room['room_id'], invite)})", ephemeral=True)

    @watch.command(name="transfer", description="Transfer room ownership and playback controls.")
    async def watch_transfer(self, ctx: CustomContext, member: discord.Member) -> None:
        room = await self._host_room(ctx)
        if not room:
            return
        if member.bot:
            await send_reply(ctx, "Room ownership can only be transferred to a human server member.", ephemeral=True)
            return
        invite = new_token()
        host_key = new_token()
        await self.bot.db.execute(
            "UPDATE watch_party_rooms SET host_id = ?, invite_hash = ?, host_hash = ?, last_activity = NOW() WHERE room_id = ?",
            member.id, token_hash(invite), token_hash(host_key), room["room_id"],
        )
        try:
            await member.send(
                f"Watch Party ownership for **{ctx.guild.name}** was transferred to you.\n"
                f"Host player: {player_url(room['room_id'], host_key, invite)}"
            )
        except discord.Forbidden:
            await send_reply(ctx, f"Ownership was transferred to {member.mention}, but I could not DM their private host link. They can still control playback with the `watch` Discord commands.", ephemeral=True)
        await broadcast_room(room["room_id"], {"type": "host_changed"})
        await send_reply(ctx, f"Watch Party ownership transferred to {member.mention}.", ephemeral=True)

    @watch.command(name="leave", description="Remove your Discord account from the room roster.")
    async def watch_leave(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            await send_reply(ctx, "Use the Leave Room button in the browser player.", ephemeral=True)
            return
        room = await self._room(ctx.guild.id)
        if not room:
            await send_reply(ctx, "There is no active Watch Party in this server.", ephemeral=True)
            return
        await self.bot.db.execute(
            "DELETE FROM watch_party_members WHERE room_id = ? AND member_key = ?",
            room["room_id"], f"discord:{ctx.author.id}",
        )
        await send_reply(ctx, "You have left the Discord-linked room roster. Use the player’s Leave Room button to disconnect a browser.", ephemeral=True)

    @watch.command(name="info", description="Show the current Watch Party room.")
    async def watch_info(self, ctx: CustomContext) -> None:
        if not ctx.guild:
            await send_reply(ctx, "Watch Party information is available in a server.", ephemeral=True)
            return
        room = await self._room(ctx.guild.id)
        if not room:
            await send_reply(ctx, "There is no active Watch Party in this server.", ephemeral=True)
            return
        count = await self.bot.db.fetchval("SELECT COUNT(*) FROM watch_party_members WHERE room_id = ?", room["room_id"])
        embed = discord.Embed(title="⛩️ KYOKA WATCH PARTY", color=Config.COLORS.PRIMARY)
        embed.add_field(name="Host", value=f"<@{room['host_id']}>", inline=True)
        embed.add_field(name="Status", value=room["status"].title(), inline=True)
        embed.add_field(name="Viewers", value=f"{count or 0}/{room['max_members']}", inline=True)
        embed.add_field(name="Video", value=room.get("source_url") or "Not set", inline=False)
        await send_reply(ctx, embed=embed)

    @watch.command(name="close", description="Close the Watch Party room.")
    async def watch_close(self, ctx: CustomContext) -> None:
        room = await self._host_room(ctx, manager_fallback=True)
        if not room:
            return
        await self.bot.db.execute(
            "UPDATE watch_party_rooms SET status = 'closed', closed_at = NOW(), last_activity = NOW() WHERE room_id = ?",
            room["room_id"],
        )
        await broadcast_room(room["room_id"], {"type": "closed"})
        await send_reply(ctx, "🔒 Watch Party room closed.", ephemeral=True)


async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(WatchParty(bot))
