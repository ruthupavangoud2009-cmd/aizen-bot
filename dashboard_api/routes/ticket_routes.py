"""Support ticket system routes with bidirectional Discord bot thread synchronization.

Features:
- Authenticated user ticket creation, categories, listing, and replying.
- Staff ticket claim, assignment, status update (open/closed), and staff list.
- Discord bot thread creation and real-time message sync between Discord and website.
- Owner-only and administrator-only website staff management.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any, Dict, List, Optional
from aiohttp import web

from dashboard_api.auth import verify_session_token
from src.security.owner import OWNER_ID, is_primary_owner

logger = logging.getLogger("Kyoka.Dashboard.TicketRoutes")

ALLOWED_CATEGORIES = {
    "Support",
    "Bug Report",
    "Premium",
    "Purchase/Orders",
    "Bot Issues",
    "Website Issues",
    "Other",
}


async def get_session_and_user(request: web.Request) -> Dict[str, Any]:
    """Extract authenticated session or raise HTTPUnauthorized."""
    config = request.app["config"]
    token = request.cookies.get(config.session_cookie_name)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise web.HTTPUnauthorized(reason="Authentication required. Please log in with Discord.")

    session_data = verify_session_token(
        token, config.secret_key, max_age_seconds=config.session_max_age_seconds
    )
    if not session_data:
        raise web.HTTPUnauthorized(reason="Session expired or invalid. Please log in again.")
    return session_data


async def check_staff_status(request: web.Request, user_id: int) -> tuple[bool, str]:
    """Check if user is owner or approved staff. Returns (is_staff, role_level)."""
    if is_primary_owner(user_id):
        return True, "admin"

    db = request.app.get("db")
    if db and hasattr(db, "get_website_staff"):
        try:
            staff_info = await db.get_website_staff(user_id)
            if staff_info:
                return True, staff_info.get("role_level", "support")
        except Exception as e:
            logger.debug(f"Staff status check failed: {e}")

    return False, "user"


# ─── DISCORD SYNCHRONIZATION HELPERS ──────────────────────────────────────────

async def _notify_discord_new_ticket(app: web.Application, ticket: Dict[str, Any]) -> None:
    """Send notification and create thread in Discord staff channel."""
    try:
        from src.main import get_current_bot
        bot = get_current_bot()
        if not bot or bot.is_closed():
            logger.debug("Discord bot not online; skipping instant Discord notification.")
            return

        target_channel = None
        guild_id = ticket.get("guild_id")
        if guild_id:
            try:
                g = bot.get_guild(int(guild_id))
                if g:
                    # Look for configured log channel or first text channel
                    target_channel = g.system_channel
            except Exception:
                pass

        # Fallback to bot's first accessible guild or log channel
        if not target_channel:
            for g in bot.guilds:
                if g.system_channel and g.system_channel.permissions_for(g.me).send_messages:
                    target_channel = g.system_channel
                    break
                for ch in g.text_channels:
                    if ch.permissions_for(g.me).send_messages:
                        target_channel = ch
                        break
                if target_channel:
                    break

        if not target_channel:
            return

        import discord
        embed = discord.Embed(
            title=f"🎫 New Website Ticket: {ticket['ticket_id']}",
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=f"{ticket['username']} (`{ticket['user_id']}`)", inline=True)
        embed.add_field(name="Category", value=ticket["category"], inline=True)
        embed.add_field(name="Subject", value=ticket["subject"], inline=False)
        embed.add_field(
            name="Description",
            value=ticket["description"][:1000] + ("..." if len(ticket["description"]) > 1000 else ""),
            inline=False,
        )
        embed.add_field(
            name="Dashboard Portal",
            value="[View & Reply on Website](https://aizen-bot.pages.dev/dashboard.html)",
            inline=False,
        )
        embed.set_footer(text="KYOKA 3.0 • Aizen Edition Website Support")

        msg = await target_channel.send(embed=embed)

        # Create private/public thread if supported
        thread_id = None
        if hasattr(target_channel, "create_thread"):
            try:
                thread = await target_channel.create_thread(
                    name=f"ticket-{ticket['ticket_id']}",
                    message=msg,
                    auto_archive_duration=1440,
                )
                thread_id = thread.id
            except Exception as e:
                logger.debug(f"Thread creation note: {e}")

        # Record thread ID on ticket
        db = app.get("db")
        if db and hasattr(db, "update_website_ticket"):
            updates = {"discord_thread_id": str(thread_id) if thread_id else str(msg.id)}
            await db.update_website_ticket(ticket["ticket_id"], updates)

    except Exception as e:
        logger.warning(f"Error notifying Discord of new website ticket: {e}")


async def _notify_discord_ticket_reply(app: web.Application, ticket: Dict[str, Any], reply_msg: Dict[str, Any]) -> None:
    """Forward website message into corresponding Discord thread."""
    try:
        from src.main import get_current_bot
        bot = get_current_bot()
        if not bot or bot.is_closed():
            return

        thread_id = ticket.get("discord_thread_id")
        if not thread_id:
            return

        ch = bot.get_channel(int(thread_id))
        if not ch:
            try:
                ch = await bot.fetch_channel(int(thread_id))
            except Exception:
                ch = None

        if ch and hasattr(ch, "send"):
            import discord
            sender = reply_msg.get("sender_name", "User")
            role = reply_msg.get("sender_role", "user")
            role_badge = "👑 Admin" if role == "admin" else ("🛡️ Staff" if role == "staff" else "👤 User")
            embed = discord.Embed(
                description=reply_msg["content"],
                color=0x9333EA if role in ("staff", "admin") else 0x6B7280,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(name=f"{sender} ({role_badge})")
            await ch.send(embed=embed)
    except Exception as e:
        logger.debug(f"Error forwarding reply to Discord thread: {e}")


# ─── ROUTE HANDLERS ───────────────────────────────────────────────────────────

async def handle_create_ticket(request: web.Request) -> web.Response:
    """Create a new support ticket."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])
    username = session.get("username", "Unknown User")

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body.")

    category = str(body.get("category", "Support")).strip()
    if category not in ALLOWED_CATEGORIES:
        category = "Support"

    subject = str(body.get("subject", "")).strip()
    if not subject or len(subject) < 3 or len(subject) > 200:
        return web.json_response(
            {"success": False, "error": "Subject must be between 3 and 200 characters."},
            status=400,
        )

    description = str(body.get("description", "")).strip()
    if not description or len(description) < 10 or len(description) > 4000:
        return web.json_response(
            {"success": False, "error": "Description must be between 10 and 4,000 characters."},
            status=400,
        )

    guild_id = body.get("guild_id")
    gid_int = int(guild_id) if guild_id and str(guild_id).isdigit() else None

    db = request.app["db"]
    ticket = await db.create_website_ticket(
        user_id=user_id,
        username=username,
        category=category,
        subject=subject,
        description=description,
        guild_id=gid_int,
    )

    # Asynchronously dispatch Discord notification without blocking caller
    asyncio.create_task(_notify_discord_new_ticket(request.app, ticket))

    return web.json_response({
        "success": True,
        "message": f"Support ticket #{ticket['ticket_id']} opened successfully.",
        "ticket": ticket,
    })


async def handle_list_tickets(request: web.Request) -> web.Response:
    """List tickets. Regular users see only their own; staff see all."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])

    is_staff, _ = await check_staff_status(request, user_id)
    status_filter = request.query.get("status")

    db = request.app["db"]
    if is_staff:
        # Staff can inspect all tickets or filter by user_id query param
        target_uid = request.query.get("user_id")
        uid_int = int(target_uid) if target_uid and target_uid.isdigit() else None
        tickets = await db.list_website_tickets(user_id=uid_int, status=status_filter)
    else:
        # Non-staff strictly restricted to their own tickets
        tickets = await db.list_website_tickets(user_id=user_id, status=status_filter)

    return web.json_response({
        "success": True,
        "tickets": tickets,
        "total": len(tickets),
        "is_staff": is_staff,
    })


async def handle_get_ticket(request: web.Request) -> web.Response:
    """Fetch single ticket metadata and full message history."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])
    ticket_id = request.match_info["ticket_id"].strip().upper()

    db = request.app["db"]
    ticket = await db.get_website_ticket(ticket_id)
    if not ticket:
        raise web.HTTPNotFound(reason=f"Ticket '{ticket_id}' not found.")

    is_staff, staff_role = await check_staff_status(request, user_id)
    # Authorization: author or staff only
    if ticket["user_id"] != str(user_id) and not is_staff:
        raise web.HTTPForbidden(reason="You are not authorized to view this ticket.")

    messages = await db.get_website_ticket_messages(ticket_id)
    return web.json_response({
        "success": True,
        "ticket": ticket,
        "messages": messages,
        "is_staff": is_staff,
        "can_reply": ticket["status"] == "open" or is_staff,
    })


async def handle_reply_ticket(request: web.Request) -> web.Response:
    """Add a message reply to an existing ticket."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])
    username = session.get("username", "Member")
    ticket_id = request.match_info["ticket_id"].strip().upper()

    db = request.app["db"]
    ticket = await db.get_website_ticket(ticket_id)
    if not ticket:
        raise web.HTTPNotFound(reason=f"Ticket '{ticket_id}' not found.")

    is_staff, staff_role = await check_staff_status(request, user_id)
    if ticket["user_id"] != str(user_id) and not is_staff:
        raise web.HTTPForbidden(reason="You are not authorized to reply to this ticket.")

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body.")

    content = str(body.get("content", "")).strip()
    if not content or len(content) > 4000:
        return web.json_response(
            {"success": False, "error": "Reply must be between 1 and 4,000 characters."},
            status=400,
        )

    sender_role = "admin" if is_primary_owner(user_id) else ("staff" if is_staff else "user")
    reply = await db.add_website_ticket_message(
        ticket_id=ticket_id,
        sender_id=user_id,
        sender_name=username,
        sender_role=sender_role,
        content=content,
    )

    # Sync to Discord thread asynchronously
    asyncio.create_task(_notify_discord_ticket_reply(request.app, ticket, reply))

    return web.json_response({
        "success": True,
        "message": "Reply posted successfully.",
        "reply": reply,
    })


async def handle_update_status(request: web.Request) -> web.Response:
    """Close or reopen ticket."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])
    ticket_id = request.match_info["ticket_id"].strip().upper()

    db = request.app["db"]
    ticket = await db.get_website_ticket(ticket_id)
    if not ticket:
        raise web.HTTPNotFound(reason=f"Ticket '{ticket_id}' not found.")

    is_staff, _ = await check_staff_status(request, user_id)
    try:
        body = await request.json()
    except Exception:
        body = {}

    target_status = str(body.get("status", "closed")).lower().strip()
    if target_status not in ("open", "closed"):
        target_status = "closed"

    # Regular user can only close their own ticket, cannot reopen once closed by staff
    if not is_staff:
        if ticket["user_id"] != str(user_id):
            raise web.HTTPForbidden(reason="You cannot change another user's ticket status.")
        if target_status == "open":
            raise web.HTTPForbidden(reason="Only staff can reopen closed tickets.")

    updates: Dict[str, Any] = {"status": target_status}
    if target_status == "closed":
        updates["closed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        updates["closed_by"] = user_id

    updated = await db.update_website_ticket(ticket_id, updates)

    # Post system message into ticket
    await db.add_website_ticket_message(
        ticket_id=ticket_id,
        sender_id=user_id,
        sender_name=session.get("username", "User"),
        sender_role="system",
        content=f"Ticket status changed to '{target_status}'.",
    )

    return web.json_response({
        "success": True,
        "message": f"Ticket #{ticket_id} status updated to '{target_status}'.",
        "ticket": updated,
    })


async def handle_claim_ticket(request: web.Request) -> web.Response:
    """Staff member claims a ticket."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])
    username = session.get("username", "Staff")
    ticket_id = request.match_info["ticket_id"].strip().upper()

    is_staff, _ = await check_staff_status(request, user_id)
    if not is_staff:
        raise web.HTTPForbidden(reason="Only authorized staff can claim tickets.")

    db = request.app["db"]
    ticket = await db.get_website_ticket(ticket_id)
    if not ticket:
        raise web.HTTPNotFound(reason=f"Ticket '{ticket_id}' not found.")

    updated = await db.update_website_ticket(ticket_id, {
        "assigned_staff_id": user_id,
        "assigned_staff_name": username,
    })

    await db.add_website_ticket_message(
        ticket_id=ticket_id,
        sender_id=user_id,
        sender_name=username,
        sender_role="system",
        content=f"Ticket claimed by staff member {username}.",
    )

    return web.json_response({
        "success": True,
        "message": f"You claimed ticket #{ticket_id}.",
        "ticket": updated,
    })


# ─── STAFF MANAGEMENT API (Owner / Admin) ─────────────────────────────────────

async def handle_list_staff(request: web.Request) -> web.Response:
    """List all registered website staff."""
    session = await get_session_and_user(request)
    user_id = int(session["user_id"])

    is_staff, _ = await check_staff_status(request, user_id)
    if not is_staff:
        raise web.HTTPForbidden(reason="Staff access required.")

    db = request.app["db"]
    staff_list = await db.list_website_staff()
    return web.json_response({
        "success": True,
        "staff": staff_list,
        "total": len(staff_list),
    })


async def handle_manage_staff(request: web.Request) -> web.Response:
    """Add or remove website staff (Owner or Administrator only)."""
    session = await get_session_and_user(request)
    actor_id = int(session["user_id"])

    is_owner = is_primary_owner(actor_id)
    is_staff, role_level = await check_staff_status(request, actor_id)

    if not is_owner and role_level != "admin":
        raise web.HTTPForbidden(reason="Administrator permissions required to manage staff.")

    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body.")

    action = str(body.get("action", "add")).lower().strip()
    target_id = body.get("user_id")
    try:
        target_uid = int(target_id)
    except (ValueError, TypeError):
        return web.json_response({"success": False, "error": "Valid target user_id required."}, status=400)

    db = request.app["db"]

    if action == "remove":
        # Cannot remove bot owner
        if is_primary_owner(target_uid):
            return web.json_response({"success": False, "error": "Cannot remove bot owner."}, status=400)

        success = await db.remove_website_staff(target_uid)
        return web.json_response({
            "success": True,
            "message": f"Staff member {target_uid} removed.",
            "removed": success,
        })
    elif action == "add":
        username = str(body.get("username", f"Staff_{target_uid}")).strip()[:64]
        level = str(body.get("role_level", "support")).lower().strip()
        if level not in ("support", "senior", "admin"):
            level = "support"

        staff = await db.add_website_staff(
            user_id=target_uid,
            username=username,
            role_level=level,
            added_by=actor_id,
        )
        return web.json_response({
            "success": True,
            "message": f"Granted '{level}' role to {username}.",
            "staff": staff,
        })
    else:
        return web.json_response({"success": False, "error": f"Unknown action '{action}'."}, status=400)


def register_ticket_routes(app: web.Application) -> None:
    """Register ticket and staff endpoints onto the aiohttp application."""
    app.router.add_post("/api/tickets", handle_create_ticket)
    app.router.add_get("/api/tickets", handle_list_tickets)
    app.router.add_get("/api/tickets/{ticket_id}", handle_get_ticket)
    app.router.add_post("/api/tickets/{ticket_id}/reply", handle_reply_ticket)
    app.router.add_post("/api/tickets/{ticket_id}/status", handle_update_status)
    app.router.add_post("/api/tickets/{ticket_id}/claim", handle_claim_ticket)

    app.router.add_get("/api/staff/list", handle_list_staff)
    app.router.add_post("/api/staff/manage", handle_manage_staff)
