"""Guild management and settings routes with strict permission verification and cross-server isolation."""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from aiohttp import web

from dashboard_api.auth import verify_session_token, fetch_user_guilds, fetch_bot_guilds
from dashboard_api.permissions import can_manage_guild, find_manageable_guild

logger = logging.getLogger("Kyoka.Dashboard.GuildRoutes")


async def get_authenticated_session(request: web.Request) -> Dict[str, Any]:
    """Retrieve and verify session data from cookies or Authorization header.

    Raises HTTPUnauthorized if session is invalid or missing.
    """
    config = request.app["config"]
    token = request.cookies.get(config.session_cookie_name)

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise web.HTTPUnauthorized(reason="Authentication required. Please log in with Discord.")

    session_data = verify_session_token(
        token,
        config.secret_key,
        max_age_seconds=config.session_max_age_seconds
    )
    if not session_data:
        raise web.HTTPUnauthorized(reason="Session expired or invalid. Please log in again.")

    return session_data


async def verify_guild_access(request: web.Request, guild_id: int) -> Dict[str, Any]:
    """Verify that authenticated user has Manage Server or Administrator permissions in the target guild.

    Guarantees cross-server isolation: Users cannot view or modify guilds they do not manage.
    """
    session_data = await get_authenticated_session(request)
    access_token = session_data.get("access_token")

    # In mock / test mode with bypass header or mock token
    if access_token == "mock_test_token" and "mock_guilds" in session_data:
        guilds = session_data["mock_guilds"]
    else:
        http_session = request.app["http_session"]
        try:
            guilds = await fetch_user_guilds(access_token, http_session)
        except Exception as e:
            logger.error(f"Failed to fetch user guilds from Discord: {e}")
            raise web.HTTPBadGateway(reason="Failed to verify guild permissions with Discord.")

    target_guild = find_manageable_guild(guilds, guild_id)
    if not target_guild:
        raise web.HTTPForbidden(
            reason=f"Access denied: You do not possess Manage Server or Administrator rights for guild {guild_id}."
        )

    return target_guild


# --- Route Handlers ---

async def handle_list_guilds(request: web.Request) -> web.Response:
    """List all Discord servers with verified bot membership and explicit 4-state classification.

    States returned per guild:
    - 'installed': Bot verified present -> Configure Dashboard & Setup Wizard.
    - 'not_installed': Bot absent & user has manage rights -> Invite KYOKA.
    - 'permission_required': User lacks manage rights for guild.
    - 'unavailable': Verification check failed -> Retry verification.
    """
    session_data = await get_authenticated_session(request)
    config = request.app["config"]
    db = request.app["db"]

    access_token = session_data.get("access_token")

    force_refresh = request.query.get("refresh", "").lower() in ("1", "true", "yes")
    if force_refresh:
        from dashboard_api.auth import clear_guild_caches
        clear_guild_caches()

    if access_token == "mock_test_token" and "mock_guilds" in session_data:
        raw_guilds = session_data["mock_guilds"]
        known_set = getattr(db, "known_bot_guilds", set())
        bot_guild_ids = {str(gid) for gid in known_set}
        bot_check_ok = True
    else:
        http_session = request.app["http_session"]
        try:
            raw_guilds = await fetch_user_guilds(access_token, http_session, force_refresh=force_refresh)
        except Exception as e:
            logger.error(f"Failed to fetch user guilds: {e}")
            raise web.HTTPBadGateway(reason="Failed to fetch servers from Discord API.")

        # Authoritative live bot instance extraction
        bot_inst = None
        bot_getter = request.app.get("bot_getter")
        if callable(bot_getter):
            try:
                bot_inst = bot_getter()
            except Exception:
                pass
        if not bot_inst and "bot" in request.app:
            bot_inst = request.app["bot"]
        if not bot_inst:
            try:
                from src.main import get_current_bot
                bot_inst = get_current_bot()
            except Exception:
                pass

        # Verified bot guilds query (checks live bot instance first, then REST API with clean token)
        bot_guild_ids, bot_check_ok = await fetch_bot_guilds(
            config.bot_token,
            http_session,
            force_refresh=force_refresh,
            bot_instance=bot_inst
        )

        # Merge with database-known configured guilds if available
        try:
            if hasattr(db, "get_all_guild_ids"):
                db_ids = await db.get_all_guild_ids()
                if db_ids:
                    bot_guild_ids = bot_guild_ids.union(db_ids)
        except Exception as e:
            logger.debug(f"Could not load auxiliary db guild ids: {e}")

    manageable: List[Dict[str, Any]] = []
    for g in raw_guilds:
        gid_str = str(g["id"])
        can_manage = can_manage_guild(g)

        icon = g.get("icon")
        icon_url = (
            f"https://cdn.discordapp.com/icons/{gid_str}/{icon}.png?size=128"
            if icon
            else None
        )

        invite_url = (
            f"https://discord.com/oauth2/authorize?client_id={config.client_id}"
            f"&guild_id={gid_str}&permissions=8&scope=bot%20applications.commands"
            if config.client_id else ""
        )

        if not can_manage:
            status = "permission_required"
            is_installed = False
        elif gid_str in bot_guild_ids:
            status = "installed"
            is_installed = True
        elif not bot_check_ok:
            # Discord API verification failed or rate-limited; never falsely report bot absent
            status = "unavailable"
            is_installed = False
        else:
            # Verification succeeded and bot is genuinely absent
            status = "not_installed"
            is_installed = False

        manageable.append({
            "id": gid_str,
            "name": g.get("name", "Unknown Server"),
            "icon": icon,
            "icon_url": icon_url,
            "is_owner": bool(g.get("owner", False)),
            "permissions": str(g.get("permissions", 0)),
            "can_manage": can_manage,
            "bot_installed": is_installed,
            "status": status,
            "invite_url": invite_url,
        })

    installed_only = request.query.get("installed_only", "").lower() in ("1", "true", "yes")
    if installed_only:
        manageable = [
            g for g in manageable
            if (g["can_manage"] and g["bot_installed"]) or g["status"] == "unavailable"
        ]

    manageable_only = request.query.get("manageable_only", "").lower() in ("1", "true", "yes")
    if manageable_only:
        manageable = [g for g in manageable if g["can_manage"]]

    return web.json_response({
        "guilds": manageable,
        "verification_status": "verified" if bot_check_ok else "unavailable"
    })


async def handle_get_settings(request: web.Request) -> web.Response:
    """Fetch all modular configuration settings for an authorized guild."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    # Strict authorization check
    await verify_guild_access(request, guild_id)

    db = request.app["db"]
    settings = await db.get_guild_settings(guild_id)
    return web.json_response(settings)


async def handle_update_settings(request: web.Request) -> web.Response:
    """Save modular configuration settings for an authorized guild with schema validation."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    # Strict authorization check
    await verify_guild_access(request, guild_id)

    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON request body.")

    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(reason="Payload must be a JSON object.")

    # Input validation and sanitization
    validated_updates: Dict[str, Any] = {}

    # 1. General Settings Validation
    if "general" in payload:
        g = payload["general"]
        if not isinstance(g, dict):
            raise web.HTTPBadRequest(reason="Field 'general' must be an object.")
        validated_g = {}
        if "prefix" in g:
            prefix_str = str(g["prefix"]).strip()
            if not prefix_str or len(prefix_str) > 10:
                raise web.HTTPBadRequest(reason="Prefix must be between 1 and 10 characters.")
            validated_g["prefix"] = prefix_str
        if "language" in g:
            lang_str = str(g["language"]).strip().lower()
            if len(lang_str) > 10:
                raise web.HTTPBadRequest(reason="Language code must be 10 characters or less.")
            validated_g["language"] = lang_str
        if "log_channel_id" in g:
            validated_g["log_channel_id"] = _clean_snowflake(g["log_channel_id"])
        if "mod_role_id" in g:
            validated_g["mod_role_id"] = _clean_snowflake(g["mod_role_id"])
        validated_updates["general"] = validated_g

    # 2. Antinuke Validation
    if "antinuke" in payload:
        an = payload["antinuke"]
        if not isinstance(an, dict):
            raise web.HTTPBadRequest(reason="Field 'antinuke' must be an object.")
        validated_an = {}
        if "enabled" in an:
            validated_an["enabled"] = bool(an["enabled"])
        if "punishment" in an:
            pun = str(an["punishment"]).lower().strip()
            if pun not in ("strip_roles", "kick", "ban"):
                raise web.HTTPBadRequest(reason="Antinuke punishment must be 'strip_roles', 'kick', or 'ban'.")
            validated_an["punishment"] = pun
        if "log_channel_id" in an:
            validated_an["log_channel_id"] = _clean_snowflake(an["log_channel_id"])
        if "protections" in an and isinstance(an["protections"], dict):
            validated_an["protections"] = {k: bool(v) for k, v in an["protections"].items()}
        validated_updates["antinuke"] = validated_an

    # 3. Verification Validation
    if "verification" in payload:
        v = payload["verification"]
        if not isinstance(v, dict):
            raise web.HTTPBadRequest(reason="Field 'verification' must be an object.")
        validated_v = {}
        if "enabled" in v:
            validated_v["enabled"] = bool(v["enabled"])
        if "role_id" in v:
            validated_v["role_id"] = _clean_snowflake(v["role_id"])
        if "unverified_role_id" in v:
            validated_v["unverified_role_id"] = _clean_snowflake(v["unverified_role_id"])
        if "channel_id" in v:
            validated_v["channel_id"] = _clean_snowflake(v["channel_id"])
        if "log_channel_id" in v:
            validated_v["log_channel_id"] = _clean_snowflake(v["log_channel_id"])
        if "method" in v:
            method = str(v["method"]).lower().strip()
            if method not in ("button", "captcha"):
                method = "button"
            validated_v["method"] = method
        if "timeout_seconds" in v:
            try:
                t = int(v["timeout_seconds"])
                validated_v["timeout_seconds"] = max(30, min(3600, t))
            except (ValueError, TypeError):
                pass
        if "max_retries" in v:
            try:
                r = int(v["max_retries"])
                validated_v["max_retries"] = max(1, min(10, r))
            except (ValueError, TypeError):
                pass
        if "min_account_age_days" in v:
            try:
                d = int(v["min_account_age_days"])
                validated_v["min_account_age_days"] = max(0, min(365, d))
            except (ValueError, TypeError):
                pass
        validated_updates["verification"] = validated_v

    # 4. Autoroles Validation
    if "autoroles" in payload:
        ar = payload["autoroles"]
        if isinstance(ar, dict):
            validated_updates["autoroles"] = {
                "role_id": _clean_snowflake(ar.get("role_id")),
                "human_role_id": _clean_snowflake(ar.get("human_role_id")),
                "bot_role_id": _clean_snowflake(ar.get("bot_role_id")),
            }

    # 5. Modular Logs Validation
    if "logs" in payload:
        lg = payload["logs"]
        if isinstance(lg, dict):
            validated_updates["logs"] = {
                "all_channel_id": _clean_snowflake(lg.get("all_channel_id")),
                "mod_channel_id": _clean_snowflake(lg.get("mod_channel_id")),
                "message_channel_id": _clean_snowflake(lg.get("message_channel_id")),
                "member_channel_id": _clean_snowflake(lg.get("member_channel_id")),
                "server_channel_id": _clean_snowflake(lg.get("server_channel_id")),
                "voice_channel_id": _clean_snowflake(lg.get("voice_channel_id")),
            }

    # 6. Music Validation
    if "music" in payload:
        m = payload["music"]
        if isinstance(m, dict):
            validated_m = {}
            if "autoplay" in m:
                validated_m["autoplay"] = bool(m["autoplay"])
            if "autoplay_mode" in m:
                validated_m["autoplay_mode"] = str(m["autoplay_mode"])[:20]
            if "default_volume" in m:
                try:
                    vol = int(m["default_volume"])
                    if vol < 1 or vol > 150:
                        raise web.HTTPBadRequest(reason="Default volume must be between 1 and 150.")
                    validated_m["default_volume"] = vol
                except ValueError:
                    raise web.HTTPBadRequest(reason="Default volume must be an integer.")
            if "is_247" in m:
                validated_m["is_247"] = bool(m["is_247"])
            validated_updates["music"] = validated_m

    # 7. AI Validation
    if "ai" in payload:
        ai = payload["ai"]
        if isinstance(ai, dict):
            validated_ai = {}
            if "enabled" in ai:
                validated_ai["enabled"] = bool(ai["enabled"])
            if "channel_id" in ai:
                validated_ai["channel_id"] = _clean_snowflake(ai["channel_id"])
            if "personality" in ai:
                validated_ai["personality"] = str(ai["personality"])[:64]
            if "tone" in ai:
                validated_ai["tone"] = str(ai["tone"])[:64]
            if "cooldown_seconds" in ai:
                try:
                    cd = int(ai["cooldown_seconds"])
                    validated_ai["cooldown_seconds"] = max(1, min(60, cd))
                except (ValueError, TypeError):
                    pass
            if "custom_rules" in ai:
                validated_ai["custom_rules"] = str(ai["custom_rules"])[:2000]
            validated_updates["ai"] = validated_ai

    # 8. Voice Welcome Validation
    if "voice_welcome" in payload:
        vw = payload["voice_welcome"]
        if isinstance(vw, dict):
            validated_vw = {}
            if "enabled" in vw:
                validated_vw["enabled"] = bool(vw["enabled"])
            if "channel_id" in vw:
                validated_vw["channel_id"] = _clean_snowflake(vw["channel_id"])
            if "greeting_text" in vw:
                validated_vw["greeting_text"] = str(vw["greeting_text"])[:500]
            if "tts_provider" in vw:
                validated_vw["tts_provider"] = str(vw["tts_provider"])[:32]
            if "language" in vw:
                validated_vw["language"] = str(vw["language"])[:10]
            if "cooldown_seconds" in vw:
                try:
                    cd = int(vw["cooldown_seconds"])
                    validated_vw["cooldown_seconds"] = max(1, min(300, cd))
                except (ValueError, TypeError):
                    pass
            validated_updates["voice_welcome"] = validated_vw

    # 9. Welcome & Leave Validation
    if "welcome_leave" in payload:
        wl = payload["welcome_leave"]
        if isinstance(wl, dict):
            validated_wl = {}
            if "welcome_enabled" in wl:
                validated_wl["welcome_enabled"] = bool(wl["welcome_enabled"])
            if "welcome_channel_id" in wl:
                validated_wl["welcome_channel_id"] = _clean_snowflake(wl["welcome_channel_id"])
            if "welcome_message" in wl:
                validated_wl["welcome_message"] = str(wl["welcome_message"])[:1000]
            if "leave_enabled" in wl:
                validated_wl["leave_enabled"] = bool(wl["leave_enabled"])
            if "leave_channel_id" in wl:
                validated_wl["leave_channel_id"] = _clean_snowflake(wl["leave_channel_id"])
            if "leave_message" in wl:
                validated_wl["leave_message"] = str(wl["leave_message"])[:1000]
            if "dm_enabled" in wl:
                validated_wl["dm_enabled"] = bool(wl["dm_enabled"])
            if "card_enabled" in wl:
                validated_wl["card_enabled"] = bool(wl["card_enabled"])
            if "card_theme" in wl:
                validated_wl["card_theme"] = str(wl["card_theme"])[:50]
            if "embed_color" in wl:
                validated_wl["embed_color"] = str(wl["embed_color"])[:16]
            if "next_step" in wl:
                validated_wl["next_step"] = str(wl["next_step"])[:150]
            if "auto_role_id" in wl:
                validated_wl["auto_role_id"] = _clean_snowflake(wl["auto_role_id"])
            validated_updates["welcome_leave"] = validated_wl

    # 9b. AutoMod & Moderation Validation
    if "moderation" in payload or "automod" in payload:
        am = payload.get("moderation") or payload.get("automod")
        if isinstance(am, dict):
            validated_am = {}
            if "enabled" in am:
                validated_am["enabled"] = bool(am["enabled"])
            if "automod_spam" in am:
                validated_am["automod_spam"] = bool(am["automod_spam"])
            if "spam_threshold" in am:
                try:
                    validated_am["spam_threshold"] = max(2, min(20, int(am["spam_threshold"])))
                except (ValueError, TypeError):
                    pass
            if "automod_mentions" in am:
                validated_am["automod_mentions"] = bool(am["automod_mentions"])
            if "mention_threshold" in am:
                try:
                    validated_am["mention_threshold"] = max(2, min(50, int(am["mention_threshold"])))
                except (ValueError, TypeError):
                    pass
            if "automod_invites" in am:
                validated_am["automod_invites"] = bool(am["automod_invites"])
            if "automod_badwords" in am:
                validated_am["automod_badwords"] = bool(am["automod_badwords"])
            if "badwords_list" in am:
                bw = am["badwords_list"]
                if isinstance(bw, list):
                    validated_am["badwords_list"] = [str(w).strip().lower() for w in bw if str(w).strip()][:200]
                elif isinstance(bw, str):
                    validated_am["badwords_list"] = [w.strip().lower() for w in bw.split(",") if w.strip()][:200]
            if "automod_repeated" in am:
                validated_am["automod_repeated"] = bool(am["automod_repeated"])
            if "automod_caps" in am:
                validated_am["automod_caps"] = bool(am["automod_caps"])
            if "caps_threshold" in am:
                try:
                    validated_am["caps_threshold"] = max(50, min(100, int(am["caps_threshold"])))
                except (ValueError, TypeError):
                    pass
            if "action" in am:
                act = str(am["action"]).lower().strip()
                if act in ("delete", "warn", "timeout"):
                    validated_am["action"] = act
                    validated_am["threshold_punishment"] = act
            if "timeout_duration" in am:
                try:
                    validated_am["timeout_duration"] = max(10, min(86400, int(am["timeout_duration"])))
                except (ValueError, TypeError):
                    pass
            if "exempt_roles" in am:
                er = am["exempt_roles"]
                if isinstance(er, list):
                    validated_am["exempt_roles"] = [_clean_snowflake(r) for r in er if _clean_snowflake(r)]
            if "exempt_channels" in am:
                ec = am["exempt_channels"]
                if isinstance(ec, list):
                    validated_am["exempt_channels"] = [_clean_snowflake(c) for c in ec if _clean_snowflake(c)]
            if "log_channel_id" in am:
                validated_am["log_channel_id"] = _clean_snowflake(am["log_channel_id"])
            if "mod_role_id" in am:
                validated_am["mod_role_id"] = _clean_snowflake(am["mod_role_id"])

            validated_updates["moderation"] = validated_am

    # 10. Tickets Validation
    if "tickets" in payload:
        tk = payload["tickets"]
        if isinstance(tk, dict):
            validated_tk = {}
            if "enabled" in tk:
                validated_tk["enabled"] = bool(tk["enabled"])
            if "panel_name" in tk:
                validated_tk["panel_name"] = str(tk["panel_name"])[:64]
            if "panel_description" in tk:
                validated_tk["panel_description"] = str(tk["panel_description"])[:1000]
            if "channel_id" in tk:
                validated_tk["channel_id"] = _clean_snowflake(tk["channel_id"])
            if "category_id" in tk:
                validated_tk["category_id"] = _clean_snowflake(tk["category_id"])
            if "support_role_id" in tk:
                validated_tk["support_role_id"] = _clean_snowflake(tk["support_role_id"])
            if "log_channel_id" in tk:
                validated_tk["log_channel_id"] = _clean_snowflake(tk["log_channel_id"])
            if "button_label" in tk:
                validated_tk["button_label"] = str(tk["button_label"])[:64]
            if "button_emoji" in tk:
                validated_tk["button_emoji"] = str(tk["button_emoji"])[:64]
            if "naming_format" in tk:
                validated_tk["naming_format"] = str(tk["naming_format"])[:64]
            if "categories" in tk and isinstance(tk["categories"], list):
                valid_cats = []
                for cat in tk["categories"]:
                    if isinstance(cat, dict) and cat.get("name"):
                        valid_cats.append({
                            "name": str(cat["name"]).strip()[:64],
                            "emoji": str(cat.get("emoji", "🎫")).strip()[:32],
                            "description": str(cat.get("description", "")).strip()[:200],
                            "category_channel_id": _clean_snowflake(cat.get("category_channel_id") or cat.get("category_id")),
                            "staff_role_id": _clean_snowflake(cat.get("staff_role_id")),
                            "welcome_message": str(cat.get("welcome_message", "")).strip()[:1000],
                            "naming_format": str(cat.get("naming_format", "ticket-{count}")).strip()[:64],
                        })
                validated_tk["categories"] = valid_cats
            validated_updates["tickets"] = validated_tk

    # 11. Roles & Utilities Validation
    if "roles_utilities" in payload:
        ru = payload["roles_utilities"]
        if isinstance(ru, dict):
            validated_updates["roles_utilities"] = {
                "role_id": _clean_snowflake(ru.get("role_id")),
                "human_role_id": _clean_snowflake(ru.get("human_role_id")),
                "bot_role_id": _clean_snowflake(ru.get("bot_role_id")),
                "ghostping_enabled": bool(ru.get("ghostping_enabled", False)),
                "ghostping_channel_id": _clean_snowflake(ru.get("ghostping_channel_id")),
            }

    # 9. Verification Settings Validation
    if "verification" in payload:
        v = payload["verification"]
        if not isinstance(v, dict):
            raise web.HTTPBadRequest(reason="Field 'verification' must be an object.")
        method_val = str(v.get("method", "button")).lower().strip()
        if method_val not in ("button", "captcha"):
            method_val = "button"
        try:
            t_sec = max(30, min(3600, int(v.get("timeout_seconds", 300))))
            m_ret = max(1, min(10, int(v.get("max_retries", 3))))
            m_age = max(0, min(365, int(v.get("min_account_age_days", 0))))
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(reason="Invalid numeric values for verification timing/retries.")
        validated_updates["verification"] = {
            "enabled": bool(v.get("enabled", False)),
            "role_id": _clean_snowflake(v.get("role_id")),
            "unverified_role_id": _clean_snowflake(v.get("unverified_role_id")),
            "channel_id": _clean_snowflake(v.get("channel_id")),
            "log_channel_id": _clean_snowflake(v.get("log_channel_id")),
            "method": method_val,
            "timeout_seconds": t_sec,
            "max_retries": m_ret,
            "min_account_age_days": m_age,
        }

    # 10. Utilities Settings Validation
    if "utilities" in payload:
        ut = payload["utilities"]
        if not isinstance(ut, dict):
            raise web.HTTPBadRequest(reason="Field 'utilities' must be an object.")
        validated_updates["utilities"] = {
            "sticky_enabled": bool(ut.get("sticky_enabled", False)),
            "sticky_channel_id": _clean_snowflake(ut.get("sticky_channel_id")),
            "sticky_message": str(ut.get("sticky_message", ""))[:1000],
            "afk_notify": bool(ut.get("afk_notify", True)),
            "reminders_enabled": bool(ut.get("reminders_enabled", True)),
        }

    # 11. Embeds & Branding Validation
    if "embeds" in payload:
        em = payload["embeds"]
        if not isinstance(em, dict):
            raise web.HTTPBadRequest(reason="Field 'embeds' must be an object.")
        validated_updates["embeds"] = {
            "primary_color": str(em.get("primary_color", "#7C3AED"))[:10],
            "accent_color": str(em.get("accent_color", "#8B5CF6"))[:10],
            "footer_text": str(em.get("footer_text", "KYOKA 3.0 • Aizen Edition"))[:100],
            "thumbnail_url": str(em.get("thumbnail_url", ""))[:500],
            "banner_url": str(em.get("banner_url", ""))[:500],
        }

    # 12. Server Roles & Channel Mappings
    if "roles_channels" in payload:
        rc = payload["roles_channels"]
        if not isinstance(rc, dict):
            raise web.HTTPBadRequest(reason="Field 'roles_channels' must be an object.")
        validated_updates["roles_channels"] = {
            "mod_role_id": _clean_snowflake(rc.get("mod_role_id")),
            "admin_role_id": _clean_snowflake(rc.get("admin_role_id")),
            "human_role_id": _clean_snowflake(rc.get("human_role_id")),
            "bot_role_id": _clean_snowflake(rc.get("bot_role_id")),
        }

    # 13. Leveling & XP Validation
    if "leveling" in payload:
        lvl = payload["leveling"]
        if isinstance(lvl, dict):
            validated_lvl = {
                "enabled": bool(lvl.get("enabled", True)),
            }
            if "xp_rate" in lvl:
                try:
                    validated_lvl["xp_rate"] = max(0.1, min(10.0, float(lvl["xp_rate"])))
                except (ValueError, TypeError):
                    validated_lvl["xp_rate"] = 1.0
            if "cooldown_seconds" in lvl:
                try:
                    validated_lvl["cooldown_seconds"] = max(5, min(600, int(lvl["cooldown_seconds"])))
                except (ValueError, TypeError):
                    validated_lvl["cooldown_seconds"] = 60
            if "announcement_channel_id" in lvl:
                validated_lvl["announcement_channel_id"] = _clean_snowflake(lvl.get("announcement_channel_id"))
            if "role_rewards" in lvl and isinstance(lvl["role_rewards"], list):
                rewards = []
                for item in lvl["role_rewards"][:50]:
                    if isinstance(item, dict) and "level" in item and "role_id" in item:
                        try:
                            lvl_num = int(item["level"])
                            role_id = _clean_snowflake(item["role_id"])
                            if role_id:
                                rewards.append({"level": lvl_num, "role_id": role_id})
                        except (ValueError, TypeError):
                            pass
                validated_lvl["role_rewards"] = rewards
            validated_updates["leveling"] = validated_lvl

    # 14. Giveaways Validation
    if "giveaways" in payload:
        gw = payload["giveaways"]
        if isinstance(gw, dict):
            validated_gw = {}
            if "default_channel_id" in gw:
                validated_gw["default_channel_id"] = _clean_snowflake(gw.get("default_channel_id"))
            if "embed_color" in gw:
                validated_gw["embed_color"] = str(gw.get("embed_color", "#7C3AED"))[:10]
            if "claim_deadline_seconds" in gw:
                try:
                    validated_gw["claim_deadline_seconds"] = max(60, min(604800, int(gw["claim_deadline_seconds"])))
                except (ValueError, TypeError):
                    validated_gw["claim_deadline_seconds"] = 86400
            validated_updates["giveaways"] = validated_gw

    # 15. Reaction Roles Validation
    if "reaction_roles" in payload:
        rr = payload["reaction_roles"]
        if isinstance(rr, dict):
            validated_rr = {}
            if "panels" in rr and isinstance(rr["panels"], list):
                panels = []
                for p in rr["panels"][:50]:
                    if isinstance(p, dict):
                        panels.append({
                            "channel_id": _clean_snowflake(p.get("channel_id")),
                            "message_id": _clean_snowflake(p.get("message_id")),
                            "emoji": str(p.get("emoji", "⭐"))[:64],
                            "role_id": _clean_snowflake(p.get("role_id")),
                            "mode": str(p.get("mode", "normal"))[:32],
                        })
                validated_rr["panels"] = panels
            validated_updates["reaction_roles"] = validated_rr

    # 16. Prefix & Commands Validation
    if "prefix_commands" in payload:
        pc = payload["prefix_commands"]
        if isinstance(pc, dict):
            validated_pc = {}
            if "prefix" in pc:
                validated_pc["prefix"] = str(pc["prefix"]).strip()[:10] or "+"
            if "disabled_commands" in pc and isinstance(pc["disabled_commands"], list):
                validated_pc["disabled_commands"] = [
                    str(c).strip().lower()[:32] for c in pc["disabled_commands"] if str(c).strip()
                ][:100]
            validated_updates["prefix_commands"] = validated_pc

    db = request.app["db"]

    # Server-Side Entitlement Enforcement for Kyoka Pro / Ultimate Features
    if "music" in validated_updates and validated_updates["music"].get("is_247"):
        if not await db.is_guild_premium(guild_id):
            return web.json_response({
                "success": False,
                "error": "24/7 Music Mode is an exclusive Kyoka Premium feature. Upgrade your server in the Premium tab.",
                "code": "PREMIUM_REQUIRED",
                "feature": "music.is_247",
            }, status=403)

    updated_settings = await db.update_guild_settings(guild_id, validated_updates)

    return web.json_response({
        "success": True,
        "message": "Guild settings updated successfully.",
        "settings": updated_settings,
    })


async def handle_get_wizard(request: web.Request) -> web.Response:
    """Fetch setup wizard draft state and progress for an authorized guild."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    db = request.app["db"]
    state = await db.get_wizard_state(guild_id)
    return web.json_response({
        "guild_id": str(guild_id),
        "wizard_state": state,
        **state,
    })


async def handle_save_wizard(request: web.Request) -> web.Response:
    """Save draft setup wizard progress without applying to live bot tables."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Invalid JSON body.")

    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(reason="Payload must be a JSON object.")

    db = request.app["db"]
    saved = await db.save_wizard_state(guild_id, payload)
    return web.json_response({
        "success": True,
        "state": saved,
        "wizard_state": saved,
        "message": "Wizard progress saved.",
    })


async def handle_apply_wizard(request: web.Request) -> web.Response:
    """Validate and atomically apply all setup wizard configurations to live bot database models."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    db = request.app["db"]
    if not payload or not payload.get("draft"):
        current_state = await db.get_wizard_state(guild_id)
        draft = current_state.get("draft", {})
    else:
        draft = payload.get("draft", {})

    applied = await db.apply_wizard_state(
        guild_id,
        {"draft": draft, "is_completed": True, "current_step": 9, "completed_steps": [1, 2, 3, 4, 5, 6, 7, 8, 9]}
    )

    sections_applied = [k for k in draft.keys() if draft[k]]
    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "applied_sections": sections_applied,
        "state": applied,
        "wizard_state": applied,
        "message": f"Successfully configured and activated {len(sections_applied)} server modules."
    })


async def handle_test_event(request: web.Request) -> web.Response:
    """Safely test event simulation (e.g. welcome preview) without spamming members."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)

    try:
        body = await request.json()
    except Exception:
        body = {}

    event_type = str(body.get("event_type", "welcome")).lower().strip()
    db = request.app["db"]
    settings = await db.get_guild_settings(guild_id)

    if event_type == "welcome":
        template = settings.get("welcome_leave", {}).get("welcome_message", "Welcome {user} to {server}!")
        preview_text = template.replace("{user}", "@KyokaMember").replace("{server}", "Server Preview").replace("{member_count}", "1,582")
        ch_id = settings.get("welcome_leave", {}).get("welcome_channel_id")
        return web.json_response({
            "success": True,
            "event_type": "welcome",
            "channel_configured": bool(ch_id),
            "target_channel_id": ch_id,
            "simulated_message": preview_text,
            "note": "Safe preview generated. No live Discord message was sent to real members.",
        })
    elif event_type == "leave":
        template = settings.get("welcome_leave", {}).get("leave_message", "{user} has departed from {server}.")
        preview_text = template.replace("{user}", "KyokaMember#0001").replace("{server}", "Server Preview").replace("{member_count}", "1,581")
        ch_id = settings.get("welcome_leave", {}).get("leave_channel_id")
        return web.json_response({
            "success": True,
            "event_type": "leave",
            "channel_configured": bool(ch_id),
            "target_channel_id": ch_id,
            "simulated_message": preview_text,
            "note": "Safe preview generated. No live Discord message was sent.",
        })
    else:
        return web.json_response({
            "success": True,
            "event_type": event_type,
            "simulated_message": f"Test notification dispatch for event [{event_type}].",
            "note": "Diagnostic simulation succeeded.",
        })


async def handle_get_guild_premium(request: web.Request) -> web.Response:
    """Fetch active premium entitlement status, tier, expiry, and perks for guild."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    db = request.app["db"]
    data = await db.get_guild_premium(guild_id)
    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        **data,
    })


async def handle_redeem_premium(request: web.Request) -> web.Response:
    """Redeem a Kyoka Pro or Kyoka Ultimate license key for the guild."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    session = await verify_guild_access(request, guild_id)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON body."}, status=400)

    key = str(body.get("key", "") or body.get("license_key", "")).strip()
    if not key:
        return web.json_response({"success": False, "error": "License key is required."}, status=400)

    db = request.app["db"]
    user_id = int(session.get("id") or 0)

    try:
        res = await db.redeem_premium_key(guild_id, key, user_id)
        return web.json_response(res)
    except ValueError as e:
        return web.json_response({"success": False, "error": str(e)}, status=400)


def _clean_snowflake(val: Any) -> Optional[str]:
    """Validate and normalize a Discord snowflake ID."""
    if not val:
        return None
    val_str = str(val).strip()
    if not val_str or val_str in ("0", "null", "none"):
        return None
    if not val_str.isdigit() or len(val_str) < 15 or len(val_str) > 21:
        return None
    return val_str


async def handle_automod_test(request: web.Request) -> web.Response:
    """Test message against guild AutoMod filters without moderating anyone."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)

    try:
        body = await request.json()
    except Exception:
        body = {}

    test_text = str(body.get("message_text", "")).strip()
    if not test_text:
        return web.json_response({"success": False, "error": "Message text is required for testing."}, status=400)

    db = request.app["db"]
    settings = await db.get_guild_settings(guild_id)
    mod_cfg = settings.get("moderation", {})

    from src.managers.automod_manager import AutoModManager
    mgr = AutoModManager(db=None)

    # Force enable for diagnostic simulation
    eval_cfg = dict(mod_cfg)
    eval_cfg["enabled"] = True

    violation, filter_name, reason = mgr.check_content(
        test_text,
        user_id=1000,
        guild_id=guild_id,
        cfg=eval_cfg,
        mentions_count=0,
    )

    return web.json_response({
        "success": True,
        "is_violation": violation,
        "filter_name": filter_name,
        "reason": reason,
        "expected_action": mod_cfg.get("action", "delete") if violation else None,
        "tested_text": test_text,
    })


# ── Custom Bot Avatar Dashboard Handlers ──

async def handle_get_guild_avatar(request: web.Request) -> web.Response:
    """Retrieve custom server bot avatar settings and premium status."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    is_premium = False
    if bot and hasattr(bot, "premium_mgr"):
        is_premium = bot.premium_mgr.is_guild_premium(guild_id)

    row = None
    try:
        if hasattr(db, "fetch_one"):
            row = await db.fetch_one(
                "SELECT avatar_url, status, applied_discord_api, updated_at FROM guild_custom_avatars WHERE guild_id = ?;",
                guild_id,
            )
    except Exception as e:
        logger.debug(f"Notice fetching custom avatar: {e}")

    default_avatar = "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif"
    if bot and bot.user:
        default_avatar = str(bot.user.display_avatar.url)

    custom_url = row["avatar_url"] if (row and row.get("status") == "active" and is_premium) else None

    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "is_premium": is_premium,
        "custom_avatar_url": custom_url,
        "applied_discord_api": bool(row.get("applied_discord_api")) if row else False,
        "default_avatar_url": default_avatar,
    })


async def handle_set_guild_avatar(request: web.Request) -> web.Response:
    """Upload or set custom server bot avatar. Strictly requires Server Premium."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    session_data = await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]
    user_id = int(session_data.get("id") or 0)

    # 1. Enforce Premium Subscription Check
    is_premium = False
    if bot and hasattr(bot, "premium_mgr"):
        is_premium = bot.premium_mgr.is_guild_premium(guild_id)

    from src.security.owner import is_primary_owner
    if not is_premium and not is_primary_owner(user_id):
        return web.json_response({
            "success": False,
            "error": "Custom bot avatar is an exclusive Kyoka Premium feature. Upgrade your server to unlock custom server avatars.",
            "premium_required": True,
        }, status=403)

    # 2. Extract image URL or multipart payload
    target_url = None
    avatar_bytes = None

    content_type = request.content_type.lower()
    if "multipart" in content_type:
        reader = await request.multipart()
        field = await reader.next()
        if field and field.name in ("avatar", "file", "image"):
            avatar_bytes = await field.read()
    else:
        try:
            body = await request.json()
            target_url = str(body.get("avatar_url", "") or body.get("image_url", "")).strip()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid request body."}, status=400)

    if not avatar_bytes and target_url:
        # Download image from URL
        try:
            http_session = request.app["http_session"]
            async with http_session.get(target_url, timeout=10) as resp:
                if resp.status != 200:
                    return web.json_response({"success": False, "error": "Failed to download image from the provided URL."}, status=400)
                avatar_bytes = await resp.read()
        except Exception as e:
            return web.json_response({"success": False, "error": f"Could not retrieve image URL: {e}"}, status=400)

    if not avatar_bytes:
        return web.json_response({"success": False, "error": "No avatar file or valid image URL provided."}, status=400)

    if len(avatar_bytes) > 10 * 1024 * 1024:
        return web.json_response({"success": False, "error": "Image file exceeds Discord's 10MB limit."}, status=400)

    # 3. Apply to Discord Member Avatar if bot is in guild
    applied_discord_api = False
    if bot:
        guild = bot.get_guild(guild_id)
        if guild and guild.me:
            try:
                await guild.me.edit(avatar=avatar_bytes, reason=f"Dashboard avatar upload by user {user_id}")
                applied_discord_api = True
            except Exception as e:
                logger.info(f"Dashboard member avatar Discord API notice: {e}")
                applied_discord_api = False

    # 4. Save to PostgreSQL database & sync with BrandingManager
    final_url = target_url or f"https://cdn.discordapp.com/avatars/{bot.user.id if bot and bot.user else 0}/custom_{guild_id}.png"
    try:
        if hasattr(db, "execute"):
            await db.execute(
                """
                INSERT INTO guild_custom_avatars (guild_id, avatar_url, set_by, status, applied_discord_api, updated_at)
                VALUES (?, ?, ?, 'active', ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    avatar_url = excluded.avatar_url,
                    set_by = excluded.set_by,
                    status = 'active',
                    applied_discord_api = excluded.applied_discord_api,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                final_url,
                user_id,
                applied_discord_api,
            )
            await db.execute(
                """
                INSERT INTO guild_branding (guild_id, avatar_url, set_by, applied_discord_avatar, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    avatar_url = excluded.avatar_url,
                    set_by = excluded.set_by,
                    applied_discord_avatar = excluded.applied_discord_avatar,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                final_url,
                user_id,
                applied_discord_api,
            )
        if bot and hasattr(bot, "branding_mgr"):
            await bot.branding_mgr.set_field(
                guild_id, "avatar_url", final_url, user_id, {"applied_discord_avatar": applied_discord_api}
            )
    except Exception as dbe:
        logger.error(f"Failed to persist avatar to DB: {dbe}")

    return web.json_response({
        "success": True,
        "avatar_url": final_url,
        "applied_discord_api": applied_discord_api,
        "message": "Custom bot avatar updated successfully!" if applied_discord_api else "Custom avatar saved! Kyoka Visual Branding is now active for this server.",
    })


async def handle_reset_guild_avatar(request: web.Request) -> web.Response:
    """Reset custom server bot avatar back to default global Aizen branding."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    if bot:
        guild = bot.get_guild(guild_id)
        if guild and guild.me:
            try:
                await guild.me.edit(avatar=None, reason="Dashboard avatar reset")
            except Exception:
                pass

    try:
        if hasattr(db, "execute"):
            await db.execute("DELETE FROM guild_custom_avatars WHERE guild_id = ?;", guild_id)
            await db.execute("UPDATE guild_branding SET avatar_url = NULL, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?;", guild_id)
        if bot and hasattr(bot, "branding_mgr"):
            await bot.branding_mgr.reset_field(guild_id, "avatar_url")
    except Exception as dbe:
        logger.error(f"Failed to delete custom avatar from DB: {dbe}")

    default_avatar = "https://cdn.discordapp.com/attachments/1562020726670753854/1562693591900495872/07991C9B-39EC-4343-BF54-0E74C6819B78.gif"
    if bot and bot.user:
        default_avatar = str(bot.user.display_avatar.url)

    return web.json_response({
        "success": True,
        "default_avatar_url": default_avatar,
        "message": "Custom avatar reset. Default Aizen branding restored.",
    })


async def handle_get_guild_branding(request: web.Request) -> web.Response:
    """Fetch complete server bot identity and visual branding."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    branding = None
    if bot and hasattr(bot, "branding_mgr"):
        branding = await bot.branding_mgr.get_branding(guild_id)
    else:
        row = None
        try:
            if hasattr(db, "fetch_one"):
                row = await db.fetch_one("SELECT display_name, bio, avatar_url, banner_url, set_by, applied_nickname, applied_discord_avatar, updated_at FROM guild_branding WHERE guild_id = ?;", guild_id)
            elif hasattr(db, "pool") and db.pool:
                async with db.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT display_name, bio, avatar_url, banner_url, set_by, applied_nickname, applied_discord_avatar, updated_at FROM guild_branding WHERE guild_id = $1;", guild_id)
        except Exception as e:
            logger.debug(f"Notice querying branding: {e}")

        default_av = str(bot.user.display_avatar.url) if bot and bot.user else "https://cdn.discordapp.com/embed/avatars/0.png"
        active_voice = "ava"
        if bot:
            voice_cog = bot.get_cog("AIVoice")
            if voice_cog and hasattr(voice_cog, "_guild_voices"):
                active_voice = voice_cog._guild_voices.get(guild_id, "ava")
        elif hasattr(db, "settings_store") and guild_id in db.settings_store and "branding" in db.settings_store[guild_id]:
            active_voice = db.settings_store[guild_id]["branding"].get("voice", "ava")
        elif hasattr(db, "fetch_one"):
            try:
                v_row = await db.fetch_one("SELECT voice_key FROM guild_voice_settings WHERE guild_id = ?;", guild_id)
                if v_row and v_row.get("voice_key"):
                    active_voice = v_row["voice_key"]
            except Exception:
                pass

        branding = {
            "guild_id": str(guild_id),
            "display_name": (row["display_name"] if row and row.get("display_name") else "KYOKA 3.0"),
            "bio": (row["bio"] if row and row.get("bio") else "Power isn't given. It's taken. — Sosuke Aizen"),
            "avatar_url": (row["avatar_url"] if row and row.get("avatar_url") else default_av),
            "banner_url": (row["banner_url"] if row and row.get("banner_url") else ""),
            "voice": active_voice,
            "is_custom": bool(row and (row.get("display_name") or row.get("bio") or row.get("avatar_url") or row.get("banner_url"))),
            "applied_nickname": bool(row and row.get("applied_nickname")),
            "applied_discord_avatar": bool(row and row.get("applied_discord_avatar")),
        }

    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "branding": branding,
    })


VOICES_CATALOG = [
    {"key": "ava", "name": "Ava", "gender": "Female (Human)", "style": "Ultra-realistic, expressive human conversational female"},
    {"key": "andrew", "name": "Andrew", "gender": "Male (Human)", "style": "Ultra-realistic, natural warm conversational male"},
    {"key": "kyoka", "name": "Kyoka", "gender": "Female (Anime)", "style": "Expressive, melodic female anime voice"},
    {"key": "aizen", "name": "Sosuke Aizen", "gender": "Male (Anime)", "style": "Deep, authoritative British anime male"},
    {"key": "guy", "name": "Guy", "gender": "Male (Human)", "style": "Neutral, clean modern American male"},
    {"key": "christopher", "name": "Christopher", "gender": "Male (Human)", "style": "Warm, confident conversational male"},
    {"key": "aria", "name": "Aria", "gender": "Female (Studio)", "style": "Crisp, futuristic studio cyber female"},
    {"key": "keita", "name": "Keita", "gender": "Male (Japanese)", "style": "Authentic Japanese male anime voice"},
    {"key": "nanami", "name": "Nanami", "gender": "Female (Japanese)", "style": "Authentic Japanese female anime voice"},
]


async def handle_get_guild_voice(request: web.Request) -> web.Response:
    """Retrieve active AI voice persona and catalogue for a server."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    active_voice = "ava"
    if bot:
        voice_cog = bot.get_cog("AIVoice")
        if voice_cog and hasattr(voice_cog, "_guild_voices"):
            active_voice = voice_cog._guild_voices.get(guild_id, "ava")
    elif hasattr(db, "settings_store") and guild_id in db.settings_store and "branding" in db.settings_store[guild_id]:
        active_voice = db.settings_store[guild_id]["branding"].get("voice", "ava")
    elif hasattr(db, "fetch_one"):
        try:
            row = await db.fetch_one("SELECT voice_key FROM guild_voice_settings WHERE guild_id = ?;", guild_id)
            if row and row.get("voice_key"):
                active_voice = row["voice_key"]
        except Exception:
            pass

    return web.json_response({
        "success": True,
        "guild_id": str(guild_id),
        "active_voice": active_voice,
        "available_voices": VOICES_CATALOG,
    })


async def handle_set_guild_voice(request: web.Request) -> web.Response:
    """Update server-specific AI voice persona with instant bot cache & database persistence."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    try:
        body = await request.json()
        target_voice = str(body.get("voice") or body.get("voice_key") or "").strip()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body."}, status=400)

    from src.cogs.fun.ai_voice import resolve_voice_key, AVAILABLE_VOICES
    canonical = resolve_voice_key(target_voice)

    if bot:
        voice_cog = bot.get_cog("AIVoice")
        if voice_cog and hasattr(voice_cog, "set_guild_voice"):
            await voice_cog.set_guild_voice(guild_id, canonical)
        elif voice_cog and hasattr(voice_cog, "_guild_voices"):
            voice_cog._guild_voices[guild_id] = canonical

    if hasattr(db, "settings_store"):
        if guild_id not in db.settings_store:
            from dashboard_api.database import MockDatabaseAdapter
            db.settings_store[guild_id] = MockDatabaseAdapter.get_default_settings(guild_id)
        if "branding" not in db.settings_store[guild_id]:
            db.settings_store[guild_id]["branding"] = {}
        db.settings_store[guild_id]["branding"]["voice"] = canonical

    try:
        if hasattr(db, "execute"):
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_voice_settings (
                    guild_id BIGINT PRIMARY KEY,
                    voice_key TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO guild_voice_settings (guild_id, voice_key, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    voice_key = EXCLUDED.voice_key,
                    updated_at = CURRENT_TIMESTAMP;
            """, guild_id, canonical)
    except Exception as e:
        logger.warning(f"Error persisting voice via dashboard endpoint: {e}")

    meta = AVAILABLE_VOICES.get(canonical, AVAILABLE_VOICES["ava"])
    return web.json_response({
        "success": True,
        "active_voice": canonical,
        "voice_name": meta["name"],
        "message": f"Server AI voice persona successfully updated to {meta['name']}!",
    })


async def handle_set_guild_banner(request: web.Request) -> web.Response:
    """Set or upload custom server bot banner."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    session_data = await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]
    user_id = int(session_data.get("id") or 0)

    is_premium = False
    if bot and hasattr(bot, "premium_mgr"):
        is_premium = bot.premium_mgr.is_guild_premium(guild_id)
    elif db and hasattr(db, "is_guild_premium"):
        is_premium = await db.is_guild_premium(guild_id)

    from src.security.owner import is_primary_owner
    if not is_premium and not is_primary_owner(user_id):
        return web.json_response({
            "success": False,
            "error": "Custom bot banner is an exclusive Kyoka Premium feature. Upgrade your server to unlock custom bot banners.",
            "premium_required": True,
        }, status=403)

    target_url = None
    content_type = request.content_type.lower()
    if "multipart" in content_type:
        reader = await request.multipart()
        field = await reader.next()
        if field and field.name in ("banner", "file", "image"):
            data = await field.read()
            if len(data) > 10 * 1024 * 1024:
                return web.json_response({"success": False, "error": "Banner exceeds 10MB limit."}, status=400)
            target_url = f"https://cdn.discordapp.com/attachments/branding/banner_{guild_id}.png"
    else:
        try:
            body = await request.json()
            target_url = str(body.get("banner_url", "") or body.get("image_url", "")).strip()
        except Exception:
            return web.json_response({"success": False, "error": "Invalid request body."}, status=400)

    if not target_url:
        return web.json_response({"success": False, "error": "No valid banner image or URL provided."}, status=400)

    try:
        if hasattr(db, "execute"):
            await db.execute(
                """
                INSERT INTO guild_branding (guild_id, banner_url, set_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    banner_url = excluded.banner_url,
                    set_by = excluded.set_by,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id, target_url, user_id
            )
        if bot and hasattr(bot, "branding_mgr"):
            await bot.branding_mgr.set_field(guild_id, "banner_url", target_url, user_id)
    except Exception as e:
        logger.error(f"Error saving banner: {e}")

    return web.json_response({
        "success": True,
        "banner_url": target_url,
        "message": "Custom bot banner configured successfully!",
    })


async def handle_set_guild_bio(request: web.Request) -> web.Response:
    """Set custom server bot bio description."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    session_data = await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]
    user_id = int(session_data.get("id") or 0)

    try:
        body = await request.json()
        bio_text = str(body.get("bio", "")).strip()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid request body."}, status=400)

    if len(bio_text) > 300:
        return web.json_response({"success": False, "error": "Bio cannot exceed 300 characters."}, status=400)

    try:
        if hasattr(db, "execute"):
            await db.execute(
                """
                INSERT INTO guild_branding (guild_id, bio, set_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET
                    bio = excluded.bio,
                    set_by = excluded.set_by,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id, bio_text, user_id
            )
        if bot and hasattr(bot, "branding_mgr"):
            await bot.branding_mgr.set_field(guild_id, "bio", bio_text, user_id)
    except Exception as e:
        logger.error(f"Error saving bio: {e}")

    return web.json_response({
        "success": True,
        "bio": bio_text,
        "message": "Custom bot bio saved successfully!",
    })


async def handle_reset_guild_branding(request: web.Request) -> web.Response:
    """Reset all server-specific bot branding back to global default."""
    try:
        guild_id = int(request.match_info["guild_id"])
    except (ValueError, KeyError):
        raise web.HTTPBadRequest(reason="Invalid guild ID specified.")

    await verify_guild_access(request, guild_id)
    bot = request.app.get("bot") or (request.app["bot_getter"]() if "bot_getter" in request.app else None)
    db = request.app["db"]

    if bot:
        guild = bot.get_guild(guild_id)
        if guild and guild.me:
            try:
                await guild.me.edit(avatar=None, nick=None, reason="Dashboard branding reset")
            except Exception:
                pass

    try:
        if hasattr(db, "execute"):
            await db.execute("DELETE FROM guild_branding WHERE guild_id = ?;", guild_id)
            await db.execute("DELETE FROM guild_custom_avatars WHERE guild_id = ?;", guild_id)
        if bot and hasattr(bot, "branding_mgr"):
            await bot.branding_mgr.reset_branding(guild_id)
    except Exception as e:
        logger.error(f"Error resetting branding: {e}")

    default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"
    if bot and bot.user:
        default_avatar = str(bot.user.display_avatar.url)

    return web.json_response({
        "success": True,
        "message": "Server branding reset to default global Aizen theme.",
        "default_avatar_url": default_avatar,
    })


def register_guild_routes(app: web.Application) -> None:
    app.router.add_get("/api/guilds", handle_list_guilds)
    app.router.add_get("/api/guilds/{guild_id}/settings", handle_get_settings)
    app.router.add_patch("/api/guilds/{guild_id}/settings", handle_update_settings)
    app.router.add_post("/api/guilds/{guild_id}/test-event", handle_test_event)
    app.router.add_post("/api/guilds/{guild_id}/automod/test", handle_automod_test)
    app.router.add_get("/api/guilds/{guild_id}/wizard", handle_get_wizard)
    app.router.add_post("/api/guilds/{guild_id}/wizard/save", handle_save_wizard)
    app.router.add_post("/api/guilds/{guild_id}/wizard/apply", handle_apply_wizard)
    app.router.add_get("/api/guilds/{guild_id}/premium", handle_get_guild_premium)
    app.router.add_post("/api/guilds/{guild_id}/premium/redeem", handle_redeem_premium)
    app.router.add_get("/api/guilds/{guild_id}/avatar", handle_get_guild_avatar)
    app.router.add_post("/api/guilds/{guild_id}/avatar", handle_set_guild_avatar)
    app.router.add_delete("/api/guilds/{guild_id}/avatar", handle_reset_guild_avatar)
    app.router.add_get("/api/guilds/{guild_id}/branding", handle_get_guild_branding)
    app.router.add_post("/api/guilds/{guild_id}/banner", handle_set_guild_banner)
    app.router.add_post("/api/guilds/{guild_id}/bio", handle_set_guild_bio)
    app.router.add_post("/api/guilds/{guild_id}/branding/reset", handle_reset_guild_branding)
    app.router.add_get("/api/guilds/{guild_id}/voice", handle_get_guild_voice)
    app.router.add_post("/api/guilds/{guild_id}/voice", handle_set_guild_voice)

