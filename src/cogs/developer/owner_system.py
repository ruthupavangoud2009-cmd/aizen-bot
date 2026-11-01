from __future__ import annotations
import datetime as dt
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands, tasks
from src.core.config import Config
from src.security.owner import audit, authorize_owner, is_owner_or_staff
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

    @commands.group(name="owner", description="Show owner-only administration help.", invoke_without_command=True, hidden=True)
    async def owner_help(self, ctx):
        if ctx.author.id != 1505515188991033409:
            return
        if not await self._guard(ctx, "owner-help"): return
        prefix = Config.DEFAULT_PREFIX
        await self._reply(ctx, f"**KYOKA 2.0 owner commands**\nPrefix: `{prefix}`\n`{prefix}owner-botinfo`, `{prefix}owner-sync`, `{prefix}owner-reload <cog>`, `{prefix}owner-load <cog>`, `{prefix}owner-unload <cog>`, `{prefix}restart`, `{prefix}maintenance <on|off>`, `{prefix}health`, `{prefix}extensions`, `{prefix}database-status`, `{prefix}errors`\nPremium: `{prefix}owner-premium grant <user|server> <id> <premium|pro> <duration|lifetime>`, followed by `revoke`, `check`, `list`, `extend`, `info`, or `servers`. This owner-only response is sent privately.")
        await audit(self.bot, ctx.author.id, "owner-help", None, "success")

    # ─── SECRET OWNER-ONLY ECONOMY COMMANDS (ID: 1505515188991033409 ONLY) ──────

    @owner_help.command(name="cash", hidden=True)
    async def owner_cash(self, ctx, member: discord.Member, amount: int):
        """Add money to target user's wallet without limits."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute(
            """
            INSERT INTO user_profiles (guild_id, user_id, balance, bank, xp, level)
            VALUES ($1, $2, $3, 0, 0, 1)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET balance = user_profiles.balance + EXCLUDED.balance, total_earned = user_profiles.total_earned + EXCLUDED.balance;
            """,
            guild_id, member.id, amount
        )
        row = await self.bot.db.fetch_one("SELECT balance FROM user_profiles WHERE guild_id = $1 AND user_id = $2;", guild_id, member.id)
        bal = row["balance"] if row else amount
        await audit(self.bot, ctx.author.id, "owner-cash", member.id, f"+{amount}")
        await ctx.send(f"👑 **Owner Override:** Added **+{amount:,}** to {member.mention}'s wallet! (New Balance: `{bal:,}`)", delete_after=10)

    @owner_help.command(name="setcash", hidden=True)
    async def owner_setcash(self, ctx, member: discord.Member, amount: int):
        """Set target user's wallet balance."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute(
            """
            INSERT INTO user_profiles (guild_id, user_id, balance, bank, xp, level)
            VALUES ($1, $2, $3, 0, 0, 1)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET balance = $3;
            """,
            guild_id, member.id, amount
        )
        await audit(self.bot, ctx.author.id, "owner-setcash", member.id, f"={amount}")
        await ctx.send(f"👑 **Owner Override:** Set {member.mention}'s wallet to **{amount:,}**!", delete_after=10)

    @owner_help.command(name="removecash", hidden=True)
    async def owner_removecash(self, ctx, member: discord.Member, amount: int):
        """Remove money from target user's wallet."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute(
            """
            UPDATE user_profiles
            SET balance = GREATEST(0, balance - $3)
            WHERE guild_id = $1 AND user_id = $2;
            """,
            guild_id, member.id, amount
        )
        await audit(self.bot, ctx.author.id, "owner-removecash", member.id, f"-{amount}")
        await ctx.send(f"👑 **Owner Override:** Deducted **-{amount:,}** from {member.mention}'s wallet!", delete_after=10)

    @owner_help.command(name="giveitem", hidden=True)
    async def owner_giveitem(self, ctx, member: discord.Member, item: str, quantity: int = 1):
        """Give items to a user."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        item_id = item.lower().strip()
        await self.bot.db.execute(
            """
            INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, item_id)
            DO UPDATE SET quantity = economy_inventory.quantity + EXCLUDED.quantity;
            """,
            guild_id, member.id, item_id, quantity
        )
        await audit(self.bot, ctx.author.id, "owner-giveitem", member.id, f"{quantity}x {item_id}")
        await ctx.send(f"👑 **Owner Override:** Granted **{quantity}x `{item_id}`** to {member.mention}!", delete_after=10)

    @owner_help.command(name="setitem", hidden=True)
    async def owner_setitem(self, ctx, member: discord.Member, item: str, amount: int):
        """Set exact item quantity in user's inventory."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        item_id = item.lower().strip()
        if amount <= 0:
            await self.bot.db.execute(
                "DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2 AND item_id = $3;",
                guild_id, member.id, item_id
            )
        else:
            await self.bot.db.execute(
                """
                INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id, user_id, item_id)
                DO UPDATE SET quantity = $4;
                """,
                guild_id, member.id, item_id, amount
            )
        await audit(self.bot, ctx.author.id, "owner-setitem", member.id, f"{amount}x {item_id}")
        await ctx.send(f"👑 **Owner Override:** Set {member.mention}'s `{item_id}` stock to **{amount}**!", delete_after=10)

    @owner_help.command(name="spawn", hidden=True)
    async def owner_spawn(self, ctx, creature: str, member: Optional[discord.Member] = None):
        """Spawn any creature directly into user's zoo."""
        if ctx.author.id != 1505515188991033409:
            return
        target = member or ctx.author
        guild_id = ctx.guild.id if ctx.guild else 0
        cid = creature.lower().strip()

        await self.bot.db.execute(
            """
            INSERT INTO user_zoo (guild_id, user_id, creature_id, count, level, exp, affection, caught_at)
            VALUES ($1, $2, $3, 1, 1, 0, 100, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, user_id, creature_id)
            DO UPDATE SET count = user_zoo.count + 1;
            """,
            guild_id, target.id, cid
        )
        await audit(self.bot, ctx.author.id, "owner-spawn", target.id, cid)
        await ctx.send(f"👑 **Owner Override:** Spawned **`{cid}`** into {target.mention}'s zoo!", delete_after=10)

    @owner_help.command(name="reseteco", hidden=True)
    async def owner_reseteco(self, ctx, member: discord.Member):
        """Reset target user's economy balances, inventory, and zoo."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute("UPDATE user_profiles SET balance = 1000, bank = 0, daily_streak = 0, weekly_streak = 0 WHERE guild_id = $1 AND user_id = $2;", guild_id, member.id)
        await self.bot.db.execute("DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2;", guild_id, member.id)
        await self.bot.db.execute("DELETE FROM user_zoo WHERE guild_id = $1 AND user_id = $2;", guild_id, member.id)
        await audit(self.bot, ctx.author.id, "owner-reseteco", member.id, "full reset")
        await ctx.send(f"👑 **Owner Override:** Economy profile for {member.mention} has been completely reset.", delete_after=10)

    @owner_help.command(name="event", hidden=True)
    async def owner_event(self, ctx, amount: float):
        """Set server economy event multiplier (e.g. 2.0x)."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute(
            """
            INSERT INTO economy_guild_settings (guild_id, event_multiplier)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET event_multiplier = $2;
            """,
            guild_id, amount
        )
        await audit(self.bot, ctx.author.id, "owner-event", None, f"multiplier={amount}")
        await ctx.send(f"🎉 **Economy Event Activated!** Multiplier set to **{amount:.2f}x**!", delete_after=10)

    @owner_help.group(name="leaderboard", invoke_without_command=True, hidden=True)
    async def owner_lb_group(self, ctx):
        if ctx.author.id != 1505515188991033409:
            return
        await ctx.send("Usage: `?owner leaderboard reset`")

    @owner_lb_group.command(name="reset", hidden=True)
    async def owner_lb_reset(self, ctx):
        """Reset server economy leaderboard."""
        if ctx.author.id != 1505515188991033409:
            return
        guild_id = ctx.guild.id if ctx.guild else 0
        await self.bot.db.execute("UPDATE user_profiles SET balance = 1000, bank = 0 WHERE guild_id = $1;", guild_id)
        await audit(self.bot, ctx.author.id, "owner-leaderboard-reset", None, f"guild={guild_id}")
        await ctx.send("👑 **Owner Override:** Server economy leaderboard has been reset to base starting balances.", delete_after=10)

    @commands.command(name="owner-botinfo", description="Owner-only bot diagnostics.")
    async def botinfo(self, ctx):
        if not await self._guard(ctx, "botinfo"): return
        latency = round(self.bot.latency * 1000) if self.bot.latency is not None else -1
        uptime = dt.timedelta(seconds=int((discord.utils.utcnow() - self.bot.start_time).total_seconds()))
        await self._reply(ctx, f"KYOKA `{Config.VERSION}`\nUptime: `{uptime}`\nLatency: `{latency} ms`\nHealth: `{'healthy' if not self.bot.is_closed() else 'closed'}`\nGuilds: `{len(self.bot.guilds)}`")

    @commands.command(name="owner-sync", description="Synchronize application commands.")
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

    @commands.command(name="owner-reload", description="Safely reload an approved extension.")
    async def reload_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "reload")
    @commands.command(name="owner-load", description="Load an approved extension.")
    async def load_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "load")
    @commands.command(name="owner-unload", description="Unload a nonessential extension.")
    async def unload_extension(self, ctx, *, cog: str): await self._extension_action(ctx, cog, "unload")

    @commands.command(name="restart", description="Request a controlled host restart.")
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

    @commands.command(name="maintenance", description="Toggle maintenance mode.")
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

    @commands.command(name="health", description="Show safe operational health.")
    async def health(self, ctx):
        if not await self._guard(ctx, "health"): return
        db_ok = False
        try: db_ok = bool(await self.bot.db.fetch_one("SELECT 1 AS ok"))
        except Exception: pass
        await self._reply(ctx, f"Gateway: `{'connected' if self.bot.is_ready() else 'not ready'}`\nDatabase: `{'healthy' if db_ok else 'unavailable'}`\nExtensions loaded: `{len(self.bot.extensions)}`")

    @commands.command(name="extensions", description="List loaded and failed extensions.")
    async def extensions(self, ctx):
        if not await self._guard(ctx, "extensions-list"): return
        loaded = sorted(self.bot.extensions)
        failed = sorted(self.bot.failed_extensions.items())
        body = f"**Loaded extensions ({len(loaded)})**\n" + ("\n".join(f"• `{x}`" for x in loaded[:40]) or "None")
        body += f"\n\n**Failed extensions ({len(failed)})**\n" + ("\n".join(f"• `{name}` — `{reason}`" for name, reason in failed[:20]) or "None")
        await self._reply(ctx, body[:1800])

    @commands.command(name="database-status", description="Show database connectivity without credentials.")
    async def database_status(self, ctx):
        if not await self._guard(ctx, "database-status"): return
        try: await self.bot.db.fetch_one("SELECT 1 AS ok"); result = "connected"
        except Exception: result = "unavailable"
        await self._reply(ctx, f"Database: `{result}`. Credentials are never displayed.")

    @commands.command(name="errors", description="Show a limited recent error summary.")
    async def errors(self, ctx):
        if not await self._guard(ctx, "errors-summary"): return
        try:
            rows = await self.bot.db.fetch_all("SELECT occurred_at, action, outcome FROM kyoka_audit_log WHERE outcome='failed' ORDER BY occurred_at DESC LIMIT 10")
            msg = "\n".join(f"`{r['occurred_at']}` {r['action']} — {r['outcome']}" for r in rows) or "No recent recorded failures."
        except Exception: msg = "Recent error summary is unavailable. Check application logs."
        await self._reply(ctx, msg[:1800])

    @commands.group(name="owner-premium", description="Owner-only manual premium management.", invoke_without_command=True)
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

    # ── Top-Level Owner Shortcuts for Premium Management ──

    @commands.command(name="grantpremium", aliases=["addpremium", "serverpremium"], hidden=True)
    async def top_grant_premium(self, ctx, scope: str, target_id: str, duration: str = "30d", tier: str = "premium", *, note: str = ""):
        """Owner command to quickly grant server or user premium: +grantpremium server <guild_id> [duration] [tier]"""
        if not is_owner_or_staff(ctx.author.id):
            return
        await self.premium_grant(ctx, scope, target_id, tier, duration, note=note)

    @commands.command(name="revokepremium", aliases=["removepremium"], hidden=True)
    async def top_revoke_premium(self, ctx, scope: str, target_id: str, *, note: str = ""):
        """Owner command to revoke premium: +revokepremium server <guild_id>"""
        if not is_owner_or_staff(ctx.author.id):
            return
        await self.premium_revoke(ctx, scope, target_id, note=note)

    @commands.command(name="checkpremium", aliases=["premiumcheck"], hidden=True)
    async def top_check_premium(self, ctx, scope: str, target_id: str):
        """Owner command to check premium status: +checkpremium server <guild_id>"""
        if not is_owner_or_staff(ctx.author.id):
            return
        await self.premium_check(ctx, scope, target_id)

    @commands.command(name="extendpremium", hidden=True)
    async def top_extend_premium(self, ctx, scope: str, target_id: str, duration: str):
        """Owner command to extend existing premium: +extendpremium server <guild_id> 30d"""
        if not is_owner_or_staff(ctx.author.id):
            return
        await self.premium_extend(ctx, scope, target_id, duration)

    # ── Automatic Expiration & Renewal Sweep Background Task ──

    @tasks.loop(hours=1)
    async def sweep_task(self):
        """Periodically sweep expired subscriptions, revoke features, and send renewal reminders."""
        try:
            if hasattr(self.bot, "premium_mgr") and self.bot.premium_mgr:
                expired_guilds = await self.bot.premium_mgr.sweep_expired_subscriptions()
                if expired_guilds:
                    for g_id in expired_guilds:
                        # Clean up custom avatar for expired guild
                        try:
                            await self.bot.db.execute("DELETE FROM guild_custom_avatars WHERE guild_id = ?;", g_id)
                        except Exception:
                            pass
                        log.info(f"Swept expired premium & revoked custom avatar for guild {g_id}.")
                await self.bot.premium_mgr.send_renewal_reminders(self.bot)
        except Exception as e:
            log.warning(f"Error during subscription expiry sweep: {e}")

    @sweep_task.before_loop
    async def before_sweep(self):
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            pass

    async def cog_load(self):
        self.sweep_task.start()

    async def cog_unload(self):
        self.sweep_task.cancel()


async def setup(bot: KyokaBot):
    await bot.add_cog(OwnerSystem(bot))
