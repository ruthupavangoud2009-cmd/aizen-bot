from __future__ import annotations
import datetime as dt
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
import discord
from discord.ext import commands
from src.core.config import Config
from src.security.owner import OWNER_ID, audit, authorize_owner, is_primary_owner
from src.managers.premium_service import PremiumService, parse_duration

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

log = logging.getLogger("Kyoka.OwnerSystem")

class OwnerSystem(commands.Cog):
    """Owner-only administration. Every callback uses the same numeric-ID guard."""
    category = "Owner"

    def __init__(self, bot: KyokaBot):
        self.bot = bot
        self.started_at = time.monotonic()
        self.premium = PremiumService(bot.db)
        self.root = Path(__file__).resolve().parents[3]

    async def _guard(self, ctx, action: str) -> bool:
        return await authorize_owner(ctx, action)

    async def _reply(self, ctx, text: str, *, ephemeral: bool = True):
        if ctx.interaction:
            if ctx.interaction.response.is_done(): await ctx.interaction.followup.send(text, ephemeral=ephemeral)
            else: await ctx.interaction.response.send_message(text, ephemeral=ephemeral)
        else:
            if ephemeral:
                try:
                    await ctx.author.send(text)
                    return
                except Exception:
                    await ctx.send("Administrative response sent privately when possible; enable DMs to view details.", delete_after=8)
            else:
                await ctx.send(text)

    @commands.hybrid_command(name="owner", description="Show owner-only administration help.")
    async def owner_help(self, ctx):
        if not await self._guard(ctx, "owner-help"): return
        prefix = Config.DEFAULT_PREFIX
        await self._reply(ctx, f"**KYOKA 2.0 owner commands**\nPrefix: `{prefix}`\n`{prefix}owner-botinfo`, `{prefix}owner-sync`, `{prefix}owner-reload <cog>`, `{prefix}owner-load <cog>`, `{prefix}owner-unload <cog>`, `{prefix}restart`, `{prefix}maintenance <on|off>`, `{prefix}health`, `{prefix}extensions`, `{prefix}database-status`, `{prefix}errors`\nPremium: `{prefix}owner-premium grant <user|server> <id> <premium|pro> <duration|lifetime>`, followed by `revoke`, `check`, `list`, `extend`, `info`, or `servers`. This owner-only response is sent privately.")
        await audit(self.bot, ctx.author.id, "owner-help", None, "success")

    @commands.hybrid_command(name="owner-botinfo", description="Owner-only bot diagnostics.")
    async def botinfo(self, ctx):
        if not await self._guard(ctx, "botinfo"): return
        latency = round(self.bot.latency * 1000) if self.bot.latency is not None else -1
        uptime = dt.timedelta(seconds=int((discord.utils.utcnow() - self.bot.start_time).total_seconds()))
        await self._reply(ctx, f"KYOKA `{Config.VERSION}`\nUptime: `{uptime}`\nLatency: `{latency} ms`\nHealth: `{'healthy' if not self.bot.is_closed() else 'closed'}`\nGuilds: `{len(self.bot.guilds)}`")

    @commands.hybrid_command(name="owner-sync", description="Synchronize application commands.")
    async def sync(self, ctx):
        if not await self._guard(ctx, "sync"): return
        try:
            synced = await self.bot.tree.sync()
            await audit(self.bot, ctx.author.id, "sync", None, "success", f"count={len(synced)}")
            await self._reply(ctx, f"Synced `{len(synced)}` global application commands.")
        except Exception:
            await audit(self.bot, ctx.author.id, "sync", None, "failed")
            await self._reply(ctx, "Command sync failed. Check the application logs.")

    def _extension(self, name: str) -> str:
        clean = name.strip().removesuffix(".py").replace("/", ".").replace("\\", ".")
        if clean.startswith("src.cogs."): ext = clean
        else: ext = "src.cogs." + clean
        allowed_root = (self.root / "src" / "cogs").resolve()
        candidate = (self.root / (ext.replace(".", "/") + ".py")).resolve()
        if not str(candidate).startswith(str(allowed_root) + os.sep) or not candidate.is_file() or any(p.startswith("_") for p in candidate.relative_to(allowed_root).parts):
            raise ValueError("Choose an existing public extension under `src/cogs`.")
        return ext

    async def _extension_action(self, ctx, name: str, action: str):
        if not await self._guard(ctx, action): return
        try: ext = self._extension(name)
        except ValueError as e: await self._reply(ctx, str(e)); return
        try:
            if action == "load":
                if ext in self.bot.extensions: await self._reply(ctx, "That extension is already loaded."); return
                await self.bot.load_extension(ext)
            elif action == "unload":
                if ext not in self.bot.extensions: await self._reply(ctx, "That extension is not loaded."); return
                if ext in {"src.cogs.developer.owner_system"}: await self._reply(ctx, "Refusing to unload essential owner security infrastructure."); return
                await self.bot.unload_extension(ext)
            else:
                if ext not in self.bot.extensions: await self._reply(ctx, "That extension is not loaded; use owner-load first."); return
                await self.bot.reload_extension(ext)
            self.bot.failed_extensions.pop(ext, None)
            await audit(self.bot, ctx.author.id, f"extension-{action}", None, "success", ext)
            await self._reply(ctx, f"Extension `{ext}` {action}ed successfully.")
        except Exception:
            log.exception("Extension operation failed (%s)", action)
            self.bot.failed_extensions[ext] = "operation failed"
            await audit(self.bot, ctx.author.id, f"extension-{action}", None, "failed", ext)
            await self._reply(ctx, f"Extension {action} failed. Check the application logs.")

    @commands.hybrid_command(name="owner-reload", description="Safely reload an approved extension.")
    async def reload_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "reload")
    @commands.hybrid_command(name="owner-load", description="Load an approved extension.")
    async def load_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "load")
    @commands.hybrid_command(name="owner-unload", description="Unload a nonessential extension.")
    async def unload_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "unload")

    @commands.hybrid_command(name="restart", description="Request a controlled host restart.")
    async def restart(self, ctx):
        if not await self._guard(ctx, "restart-request"): return
        # Host process managers (Render, systemd, Docker) restart on process exit; do not exit without explicit opt-in.
        if os.getenv("ALLOW_OWNER_RESTART", "false").lower() not in {"1", "true", "yes"}:
            await self._reply(ctx, "Restart is disabled. Set `ALLOW_OWNER_RESTART=true` and configure your host to restart exited processes.")
            await audit(self.bot, ctx.author.id, "restart-request", None, "blocked", "restart opt-in disabled")
            return
        await audit(self.bot, ctx.author.id, "restart-request", None, "accepted")
        await self._reply(ctx, "Restart requested; KYOKA will reconnect through its existing supervisor loop.")
        await self.bot.close()

    @commands.hybrid_command(name="maintenance", description="Toggle maintenance mode.")
    async def maintenance(self, ctx, mode: str):
        if not await self._guard(ctx, "maintenance-toggle"): return
        mode = mode.lower().strip()
        if mode not in {"on", "off"}: await self._reply(ctx, "Usage: `maintenance <on|off>`"); return
        enabled = mode == "on"
        try:
            await self.bot.sys_mgr.set_maintenance(enabled, "Owner enabled maintenance mode." if enabled else "System maintenance in progress.")
            await audit(self.bot, ctx.author.id, "maintenance-toggle", None, "success", mode)
            await self._reply(ctx, f"Maintenance mode **{'enabled' if enabled else 'disabled'}**.")
        except Exception:
            await audit(self.bot, ctx.author.id, "maintenance-toggle", None, "failed", mode)
            await self._reply(ctx, "Could not update maintenance mode; database operation failed.")

    @commands.hybrid_command(name="health", description="Show safe operational health.")
    async def health(self, ctx):
        if not await self._guard(ctx, "health"): return
        db_ok = False
        try: db_ok = bool(await self.bot.db.fetch_one("SELECT 1 AS ok"))
        except Exception: pass
        await self._reply(ctx, f"Gateway: `{'connected' if self.bot.is_ready() else 'not ready'}`\nDatabase: `{'healthy' if db_ok else 'unavailable'}`\nExtensions loaded: `{len(self.bot.extensions)}`")

    @commands.hybrid_command(name="extensions", description="List loaded and failed extensions.")
    async def extensions(self, ctx):
        if not await self._guard(ctx, "extensions-list"): return
        loaded = sorted(self.bot.extensions)
        failed = sorted(self.bot.failed_extensions.items())
        body = f"**Loaded extensions ({len(loaded)})**\n" + ("\n".join(f"• `{x}`" for x in loaded[:40]) or "None")
        body += f"\n\n**Failed extensions ({len(failed)})**\n" + ("\n".join(f"• `{name}` — `{reason}`" for name, reason in failed[:20]) or "None")
        await self._reply(ctx, body[:1800])

    @commands.hybrid_command(name="database-status", description="Show database connectivity without credentials.")
    async def database_status(self, ctx):
        if not await self._guard(ctx, "database-status"): return
        try: await self.bot.db.fetch_one("SELECT 1 AS ok"); result = "connected"
        except Exception: result = "unavailable"
        await self._reply(ctx, f"Database: `{result}`. Credentials are never displayed.")

    @commands.hybrid_command(name="errors", description="Show a limited recent error summary.")
    async def errors(self, ctx):
        if not await self._guard(ctx, "errors-summary"): return
        try:
            rows = await self.bot.db.fetch_all("SELECT occurred_at, action, outcome FROM kyoka_audit_log WHERE outcome='failed' ORDER BY occurred_at DESC LIMIT 10")
            msg = "\n".join(f"`{r['occurred_at']}` {r['action']} — {r['outcome']}" for r in rows) or "No recent recorded failures."
        except Exception: msg = "Recent error summary is unavailable. Check application logs."
        await self._reply(ctx, msg[:1800])

    @commands.hybrid_group(name="owner-premium", description="Owner-only manual premium management.", invoke_without_command=True)
    async def owner_premium(self, ctx):
        if not await self._guard(ctx, "premium-help"): return
        await self._reply(ctx, "Use `owner-premium grant|revoke|check|list|extend|info|servers`. Grant syntax: `owner-premium grant <user|server> <ID> <premium|pro> <30d|lifetime>`.")

    @owner_premium.command(name="grant", description="Manually grant user or server premium.")
    async def premium_grant(self, ctx, scope: str, target_id: str, tier: str, duration: str, *, note: str = ""):
        if not await self._guard(ctx, "premium-grant"): return
        scope = scope.lower()
        try:
            if scope not in {"user", "server"}: raise ValueError("Scope must be `user` or `server`.")
            if not target_id.isdecimal() or int(target_id) <= 0: raise ValueError("Target must be a numeric Discord ID.")
            result = await self.premium.grant(scope=scope, target_id=int(target_id), tier=tier, duration=duration, actor_id=ctx.author.id, note=note)
            if scope == "server": self.bot.premium_mgr._guild_cache[int(target_id)] = {"tier": tier, "expires_at": result["expires_at"]}
            else: self.bot.premium_mgr._user_cache[int(target_id)] = {"tier": tier, "expires_at": result["expires_at"]}
            await audit(self.bot, ctx.author.id, "premium-grant", int(target_id), "success", f"scope={scope};tier={tier}")
            expiry = "Lifetime" if result["expires_at"] is None else result["expires_at"].isoformat()
            await self._reply(ctx, f"Granted `{tier}` premium to `{scope}:{target_id}` until `{expiry}`.")
        except ValueError as e: await self._reply(ctx, str(e))
        except Exception:
            log.exception("Premium grant failed")
            await audit(self.bot, ctx.author.id, "premium-grant", int(target_id) if target_id.isdecimal() else None, "failed")
            await self._reply(ctx, "Premium grant failed safely; no access should be assumed. Check database health.")

    @owner_premium.command(name="revoke", description="Revoke user or server premium.")
    async def premium_revoke(self, ctx, scope: str, target_id: str, *, note: str = ""):
        if not await self._guard(ctx, "premium-revoke"): return
        try:
            if scope.lower() not in {"user", "server"} or not target_id.isdecimal(): raise ValueError("Usage: `owner-premium revoke <user|server> <numeric ID>`.")
            found = await self.premium.revoke(scope=scope.lower(), target_id=int(target_id), actor_id=ctx.author.id, note=note)
            if found:
                if scope.lower() == "server": self.bot.premium_mgr._guild_cache.pop(int(target_id), None)
                else: self.bot.premium_mgr._user_cache.pop(int(target_id), None)
            await audit(self.bot, ctx.author.id, "premium-revoke", int(target_id), "success" if found else "no-record", f"scope={scope}")
            await self._reply(ctx, "Premium revoked." if found else "No subscription record found; nothing changed.")
        except ValueError as e: await self._reply(ctx, str(e))
        except Exception:
            await audit(self.bot, ctx.author.id, "premium-revoke", None, "failed")
            await self._reply(ctx, "Premium revocation failed; check database health.")

    @owner_premium.command(name="check", description="Check a user's or server's premium status.")
    async def premium_check(self, ctx, scope: str, target_id: str):
        if not await self._guard(ctx, "premium-check"): return
        try:
            if scope.lower() not in {"user", "server"} or not target_id.isdecimal(): raise ValueError("Usage: `owner-premium check <user|server> <numeric ID>`.")
            row = await self.premium.get(scope.lower(), int(target_id))
            await self._reply(ctx, f"`{scope}:{target_id}`: " + (f"tier `{row['tier']}`, status `{row.get('status','active')}`, expiry `{row.get('expires_at') or 'Lifetime'}`" if row else "Free (no record)."))
        except ValueError as e: await self._reply(ctx, str(e))
        except Exception: await self._reply(ctx, "Premium lookup unavailable; access remains denied on lookup errors.")

    @owner_premium.command(name="list", description="List active premium subscriptions.")
    async def premium_list(self, ctx):
        if not await self._guard(ctx, "premium-list"): return
        try:
            users = await self.bot.db.fetch_all("SELECT user_id AS target_id,tier,expires_at,status FROM user_premium ORDER BY created_at DESC LIMIT 30")
            guilds = await self.bot.db.fetch_all("SELECT guild_id AS target_id,tier,expires_at,status FROM guild_premium ORDER BY created_at DESC LIMIT 30")
            lines = [f"user `{r['target_id']}` {r['tier']} {r.get('status','active')} expires `{r['expires_at'] or 'lifetime'}`" for r in users]
            lines += [f"server `{r['target_id']}` {r['tier']} {r.get('status','active')} expires `{r['expires_at'] or 'lifetime'}`" for r in guilds]
            await self._reply(ctx, "**Premium subscriptions (max 60 shown)**\n" + ("\n".join(lines) or "No records."))
        except Exception: await self._reply(ctx, "Premium list unavailable; database lookup failed.")

    @owner_premium.command(name="extend", description="Extend an existing premium subscription.")
    async def premium_extend(self, ctx, scope: str, target_id: str, duration: str):
        if not await self._guard(ctx, "premium-extend"): return
        try:
            if scope.lower() not in {"user", "server"} or not target_id.isdecimal(): raise ValueError("Usage: `owner-premium extend <user|server> <numeric ID> <duration>`.")
            row = await self.premium.get(scope.lower(), int(target_id))
            if not row or row.get("status", "active") != "active": raise ValueError("No active subscription found to extend.")
            result = await self.premium.grant(scope=scope.lower(), target_id=int(target_id), tier=row["tier"], duration=duration, actor_id=ctx.author.id, note="owner extension", extend_existing=True)
            if scope.lower() == "server": self.bot.premium_mgr._guild_cache[int(target_id)] = {"tier": row["tier"], "expires_at": result["expires_at"]}
            else: self.bot.premium_mgr._user_cache[int(target_id)] = {"tier": row["tier"], "expires_at": result["expires_at"]}
            await audit(self.bot, ctx.author.id, "premium-extend", int(target_id), "success", f"scope={scope}")
            await self._reply(ctx, f"Subscription extended. New expiry: `{result['expires_at'] or 'Lifetime'}`.")
        except ValueError as e: await self._reply(ctx, str(e))
        except Exception: await audit(self.bot, ctx.author.id, "premium-extend", None, "failed"); await self._reply(ctx, "Extension failed safely; check database health.")

    @owner_premium.command(name="info", description="Show premium tiers and configured benefit scope.")
    async def premium_info(self, ctx):
        if not await self._guard(ctx, "premium-info"): return
        await self._reply(ctx, "**KYOKA tiers**\nFree: standard features.\nPremium: configured `premium` entitlement checks only.\nPro: configured `pro` entitlement checks only.\nNo automatic payment verification is enabled; grants are owner-manual. Existing features must call the centralized premium service before being marketed as gated.")

    @owner_premium.command(name="servers", description="List servers with premium subscriptions.")
    async def premium_servers(self, ctx):
        if not await self._guard(ctx, "premium-servers"): return
        try:
            rows = await self.bot.db.fetch_all("SELECT guild_id,tier,expires_at,status FROM guild_premium ORDER BY created_at DESC LIMIT 50")
            await self._reply(ctx, "**Server premium (max 50)**\n" + ("\n".join(f"`{r['guild_id']}` — {r['tier']} / {r.get('status','active')} / `{r['expires_at'] or 'lifetime'}`" for r in rows) or "No server subscriptions."))
        except Exception: await self._reply(ctx, "Server premium list unavailable.")

async def setup(bot: KyokaBot):
    await bot.add_cog(OwnerSystem(bot))
