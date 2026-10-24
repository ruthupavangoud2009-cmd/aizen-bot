from __future__ import annotations
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Union
import discord
from discord.ext import commands

from src.ui.theme import KyokaTheme
from src.ui.asset_manager import AssetManager

DB = Path('data/kyoka_reputation.sqlite3')
PURPLE = discord.Color.from_rgb(111, 67, 190)

SERVICE_TYPES = {
    "fruit": ("🍎", "Fruit Delivery / Trade"),
    "raid": ("⚡", "Raid Carry / Awakening"),
    "leveling": ("📈", "Leveling & Grinding"),
    "bounty": ("⚔️", "Bounty Hunting / PvP"),
    "trade": ("🤝", "Trading Assistance"),
    "boss": ("👹", "Boss Farming"),
    "general": ("🛡️", "General Service"),
}


def conn():
    """Establish SQLite connection and ensure schema with backward-compatible migrations."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE IF NOT EXISTS vouches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            voucher_id INTEGER,
            target_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created REAL NOT NULL,
            held INTEGER NOT NULL DEFAULT 0,
            reviewer_id INTEGER,
            service_type TEXT DEFAULT 'general',
            rating INTEGER DEFAULT 5,
            source TEXT DEFAULT 'normal',
            staff_id INTEGER,
            imported_at REAL,
            channel_id INTEGER,
            origin_guild_name TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS vouch_cooldowns(
            guild_id INTEGER NOT NULL,
            voucher_id INTEGER NOT NULL,
            created REAL NOT NULL,
            PRIMARY KEY(guild_id, voucher_id)
        );
        CREATE TABLE IF NOT EXISTS botstaff(
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY(guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS vouch_global_cooldowns(
            voucher_id INTEGER PRIMARY KEY,
            created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vouch_config(
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            min_age_days INTEGER DEFAULT 0,
            log_channel_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS vouch_audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            mod_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            vouch_id INTEGER NOT NULL,
            reason TEXT,
            created REAL NOT NULL
        );
    ''')

    # Safe column migrations
    for col_name, col_def in [
        ("service_type", "TEXT DEFAULT 'general'"),
        ("rating", "INTEGER DEFAULT 5"),
        ("source", "TEXT DEFAULT 'normal'"),
        ("staff_id", "INTEGER"),
        ("imported_at", "REAL"),
        ("channel_id", "INTEGER"),
        ("origin_guild_name", "TEXT"),
        ("is_active", "INTEGER DEFAULT 1"),
    ]:
        try:
            c.execute(f"ALTER TABLE vouches ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass

    return c


class VouchesPaginationView(discord.ui.View):
    """Interactive pagination view for browsing member vouches across all servers."""

    def __init__(self, author_id: int, target_member: Union[discord.Member, discord.User], total_count: int, guild_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.target_member = target_member
        self.total_count = total_count
        self.guild_id = guild_id
        self.per_page = 5
        self.total_pages = max(1, math.ceil(total_count / self.per_page))
        self.current_page = 1
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.disabled = (self.current_page <= 1)
        self.btn_next.disabled = (self.current_page >= self.total_pages)

    def build_embed(self) -> discord.Embed:
        offset = (self.current_page - 1) * self.per_page
        with conn() as c:
            rows = c.execute(
                'SELECT id, guild_id, voucher_id, reason, created, service_type, rating, source, staff_id, imported_at FROM vouches '
                'WHERE target_id=? AND held=0 AND is_active=1 ORDER BY created DESC LIMIT ? OFFSET ?',
                (self.target_member.id, self.per_page, offset)
            ).fetchall()

        display_name = getattr(self.target_member, "display_name", getattr(self.target_member, "name", str(self.target_member.id)))
        embed = discord.Embed(
            title=f"✦ {display_name} • GLOBAL VOUCH REVIEWS",
            description=f"**Global Verified Vouches:** `{self.total_count}`\n"
                        f"**Page:** `{self.current_page}/{self.total_pages}`\n\n",
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        avatar_url = getattr(self.target_member, "display_avatar", getattr(self.target_member, "avatar", None))
        if avatar_url:
            embed.set_thumbnail(url=avatar_url.url)

        if not rows:
            embed.description += "*No vouches found on this page.*"
        else:
            for r in rows:
                stype = r["service_type"] or "general"
                icon, label = SERVICE_TYPES.get(stype, ("🛡️", stype.title()))
                stars = "⭐" * int(r["rating"] or 5)
                raw_ts = r["created"]
                ts_str = f"<t:{int(raw_ts)}:R>" if raw_ts else "*Date Unknown*"

                # Determine voucher attribution
                v_id = r["voucher_id"]
                is_import = (r["source"] == "historical_import")
                import_badge = " `[STAFF IMPORT]`" if is_import else ""

                if v_id:
                    voucher_desc = f"<@{v_id}>"
                elif is_import:
                    voucher_desc = "*Historical / Unknown Author*"
                else:
                    voucher_desc = "*Anonymous Voucher*"

                embed.add_field(
                    name=f"`#VOUCH-{r['id']:04d}` {icon} {label} · {stars}{import_badge}",
                    value=f"> {discord.utils.escape_markdown(r['reason'])}\n"
                          f"> *Vouched by {voucher_desc} • {ts_str}*",
                    inline=False
                )

        embed.set_footer(text=f"KYŌKA Global Reputation • Page {self.current_page}/{self.total_pages}")
        return embed

    @discord.ui.button(label="Prev", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command requester can paginate.", ephemeral=True)
        if self.current_page > 1:
            self.current_page -= 1
            self._update_buttons()
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            else:
                await interaction.edit_original_response(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command requester can paginate.", ephemeral=True)
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_buttons()
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            else:
                await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class Vouches(commands.Cog, name="Vouches"):
    """Global Blox Fruits & Community Reputation Engine."""
    category = 'Vouches'

    def __init__(self, bot):
        self.bot = bot

    def is_bot_staff(self, ctx) -> bool:
        """Check if author has authoritative Bot Staff or Administrator privileges."""
        # 1. Authoritative Primary Owner
        if ctx.author.id == 1505515188991033409:
            return True
        # 2. Server Administrator
        if ctx.guild and getattr(ctx.author, "guild_permissions", None) and ctx.author.guild_permissions.administrator:
            return True
        # 3. Developer status from permission manager
        perm_mgr = getattr(self.bot, "perm_mgr", None)
        if perm_mgr and hasattr(perm_mgr, "is_developer_sync"):
            try:
                if perm_mgr.is_developer_sync(ctx.author.id) is True:
                    return True
            except Exception:
                pass
        # 4. Registered botstaff table
        try:
            with conn() as c:
                if ctx.guild:
                    row = c.execute('SELECT 1 FROM botstaff WHERE guild_id=? AND user_id=?',
                                    (ctx.guild.id, ctx.author.id)).fetchone()
                    if row:
                        return True
                # Global staff check
                row_global = c.execute('SELECT 1 FROM botstaff WHERE user_id=?', (ctx.author.id,)).fetchone()
                if row_global:
                    return True
        except Exception:
            pass
        return False

    def staff(self, ctx) -> bool:
        """Backward-compatible alias for staff check."""
        return self.is_bot_staff(ctx)

    async def vouchleaderboard(self, ctx):
        """Backward-compatible proxy for tests and internal callers."""
        return await self.vlb(ctx)

    async def vouchprofile(self, ctx, member=None):
        """Backward-compatible proxy for tests and internal callers."""
        return await self.vouchinfo(ctx, member=member)

    async def vouches(self, ctx, member=None):
        """Backward-compatible proxy for tests and internal callers."""
        return await self.vouchhistory(ctx, member=member)

    def _parse_service_and_reason(self, raw_text: str) -> tuple[str, str]:
        parts = raw_text.strip().split(maxsplit=1)
        if not parts:
            return "general", ""
        first_word = parts[0].lower().strip()
        matched = None
        for key in SERVICE_TYPES:
            if first_word == key or first_word.startswith(key):
                matched = key
                break
        if matched and len(parts) > 1:
            return matched, parts[1].strip()
        return "general", raw_text.strip()

    # ── 1. VOUCH COMMAND ───────────────────────────────────────────────────────
    @commands.command(name='vouch')
    @commands.guild_only()
    async def vouch(self, ctx, member: Union[discord.Member, discord.User], *, reason: str):
        """Give a reputation vouch to a member for Blox Fruits trades or services.
        
        Usage: +vouch @user [service] <reason>
        Services: raid, fruit, leveling, bounty, trade, boss, general
        """
        if not ctx.guild:
            return
        if getattr(member, "bot", False) or member.id == ctx.author.id:
            return await ctx.reply('Self-vouches and bot vouches are not allowed.', mention_author=False)

        service_type, clean_reason = self._parse_service_and_reason(reason)
        clean_reason = clean_reason[:500].strip()
        if not clean_reason:
            return await ctx.reply('Please provide a meaningful review or service description.', mention_author=False)

        now = time.time()
        with conn() as c:
            # Check global cooldown (300 seconds between vouches from same voucher)
            last = c.execute('SELECT created FROM vouch_global_cooldowns WHERE voucher_id=?',
                             (ctx.author.id,)).fetchone()
            if last and (now - last['created']) < 300:
                rem = int(300 - (now - last["created"]))
                return await ctx.reply(f'⏳ You can vouch again in **{rem}** seconds.', mention_author=False)

            # Check duplicate within 24 hours
            duplicate = c.execute(
                'SELECT id FROM vouches WHERE voucher_id=? AND target_id=? AND (? - created) < 86400 AND is_active=1',
                (ctx.author.id, member.id, now)
            ).fetchone()
            held = 1 if duplicate else 0

            c.execute(
                'INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type, rating, source, is_active) '
                'VALUES(?,?,?,?,?,?,?,?,?,1)',
                (ctx.guild.id, ctx.author.id, member.id, clean_reason, now, held, service_type, 5, 'normal')
            )
            vid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT OR REPLACE INTO vouch_cooldowns VALUES(?,?,?)', (ctx.guild.id, ctx.author.id, now))
            c.execute('INSERT OR REPLACE INTO vouch_global_cooldowns VALUES(?,?)', (ctx.author.id, now))

            # Fetch target's GLOBAL total vouches across all servers
            total = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE target_id=? AND held=0 AND is_active=1',
                (member.id,)
            ).fetchone()['n']

            # Check configured showcase channel in current guild
            cfg = c.execute('SELECT channel_id FROM vouch_config WHERE guild_id=?', (ctx.guild.id,)).fetchone()
            vouch_ch_id = cfg['channel_id'] if cfg else None

        if held:
            return await ctx.reply(
                f'🔒 Vouch **#VOUCH-{vid:04d}** was held for review because you recently vouched for {member.mention}. '
                f'A staff member can review it using `+heldvouches`.',
                mention_author=False
            )

        icon, s_label = SERVICE_TYPES.get(service_type, ("🛡️", service_type.title()))
        e = discord.Embed(
            title='✦ KYŌKA • BLOX FRUITS VOUCH REGISTERED',
            description=f'**{member.mention}** received a verified reputation vouch!\n\n'
                        f"> {discord.utils.escape_markdown(clean_reason)}",
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        avatar = getattr(member, "display_avatar", getattr(member, "avatar", None))
        if avatar:
            e.set_thumbnail(url=avatar.url)

        e.add_field(name='Vouched By', value=ctx.author.mention, inline=True)
        e.add_field(name='Service Category', value=f'{icon} {s_label}', inline=True)
        e.add_field(name='Vouch ID', value=f'`#VOUCH-{vid:04d}`', inline=True)
        e.add_field(name='Rating', value='⭐⭐⭐⭐⭐ (5/5)', inline=True)
        e.add_field(name='Global Vouches', value=f'`{total}` active across servers', inline=True)
        e.set_footer(text=f'KYŌKA Global Reputation • Verified #{vid:04d}')

        banner_file = AssetManager.attach_feature_banner(e, "vouches")
        await ctx.reply(embed=e, file=banner_file, mention_author=False)

        # Dispatch copy to configured guild vouch channel if distinct
        if vouch_ch_id and vouch_ch_id != ctx.channel.id:
            v_channel = ctx.guild.get_channel(vouch_ch_id)
            if isinstance(v_channel, discord.TextChannel):
                try:
                    await v_channel.send(embed=e)
                except Exception:
                    pass

    # ── 2. GLOBAL LEADERBOARD (VLB) ───────────────────────────────────────────
    @commands.command(name='vlb', aliases=['vouchleaderboard', 'vouchlb', 'topvouches', 'repleaderboard'])
    @commands.guild_only()
    async def vlb(self, ctx):
        """Display the global top trusted members and service providers across all servers."""
        with conn() as c:
            rows = c.execute(
                'SELECT target_id, COUNT(*) as total FROM vouches '
                'WHERE held=0 AND is_active=1 GROUP BY target_id ORDER BY total DESC LIMIT 10'
            ).fetchall()

        embed = discord.Embed(
            title='✦ KYŌKA • GLOBAL VOUCH LEADERBOARD',
            description='Top trusted Blox Fruits service providers and traders across all servers:\n\n',
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        if not rows:
            embed.description += "*No verified vouches recorded globally yet. Use `+vouch @user [service] <reason>` to start!*"
        else:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for idx, r in enumerate(rows):
                medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
                target_user = self.bot.get_user(r['target_id']) or (ctx.guild.get_member(r['target_id']) if ctx.guild else None)
                name = target_user.mention if target_user else f"<@{r['target_id']}>"
                embed.description += f"{medal} {name} — **{r['total']} vouches** (100% ⭐⭐⭐⭐⭐)\n"

        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text='KYŌKA Global Reputation Leaderboard • Real-time Cross-Server Sync')

        banner_file = AssetManager.attach_feature_banner(embed, "vouches")
        await ctx.reply(embed=embed, file=banner_file, mention_author=False)

    # ── 3. VOUCH PROFILE / VOUCHINFO ──────────────────────────────────────────
    @commands.command(name='vouchinfo', aliases=['vouchprofile', 'rep', 'reputation'])
    @commands.guild_only()
    async def vouchinfo(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None):
        """Display global Blox Fruits reputation statistics, breakdown by service, and provenance."""
        member = member or ctx.author
        with conn() as c:
            total = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE target_id=? AND held=0 AND is_active=1',
                (member.id,)
            ).fetchone()['n']
            held = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE target_id=? AND held=1 AND is_active=1',
                (member.id,)
            ).fetchone()['n']
            imported_count = c.execute(
                "SELECT COUNT(*) n FROM vouches WHERE target_id=? AND source='historical_import' AND held=0 AND is_active=1",
                (member.id,)
            ).fetchone()['n']
            breakdown = c.execute(
                'SELECT service_type, COUNT(*) as cnt FROM vouches WHERE target_id=? AND held=0 AND is_active=1 GROUP BY service_type',
                (member.id,)
            ).fetchall()

        # Build service breakdown
        bd_dict = {r['service_type'] or 'general': r['cnt'] for r in breakdown}
        lines = []
        for key, (icon, label) in SERVICE_TYPES.items():
            count = bd_dict.get(key, 0)
            if count > 0:
                lines.append(f"{icon} **{label}:** `{count}`")

        breakdown_text = "\n".join(lines) if lines else "*No categorized services yet.*"

        # Tier classification
        if total >= 50:
            badge = "💎 **Elite Merchant / Master Provider**"
        elif total >= 25:
            badge = "🥇 **Trusted Veteran Provider**"
        elif total >= 10:
            badge = "🥈 **Verified Community Provider**"
        elif total >= 3:
            badge = "🥉 **Recognized Trader**"
        else:
            badge = "🌱 **New Provider**"

        disp_name = getattr(member, "display_name", getattr(member, "name", str(member.id)))
        live_count = max(0, total - imported_count)
        e = discord.Embed(
            title=f'✦ {disp_name} • GLOBAL REPUTATION PROFILE',
            description=f'{member.mention}\n{badge}\n\n'
                        f'**Global Verified Vouches:** `{total}`\n'
                        f'**Positive Review Rate:** `100%` ⭐⭐⭐⭐⭐\n'
                        f'**Live Verified Vouches:** `{live_count}`\n'
                        f'**Historical Staff Imports:** `{imported_count}`\n'
                        f'**Held Entries Pending:** `{held}`\n\n'
                        f'**Services Completed:**\n{breakdown_text}',
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        avatar = getattr(member, "display_avatar", getattr(member, "avatar", None))
        if avatar:
            e.set_thumbnail(url=avatar.url)

        e.set_footer(text=f'User ID: {member.id} • KYŌKA Global Trust & Safety')
        banner_file = AssetManager.attach_feature_banner(e, "vouches")
        await ctx.reply(embed=e, file=banner_file, mention_author=False)

    # ── 4. VOUCH HISTORY / VOUCHES ────────────────────────────────────────────
    @commands.command(name='vouchhistory', aliases=['vouches', 'repcheck'])
    @commands.guild_only()
    async def vouchhistory(self, ctx, member: Optional[Union[discord.Member, discord.User]] = None):
        """View paginated global vouch reviews and history for a member."""
        member = member or ctx.author
        with conn() as c:
            total = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE target_id=? AND held=0 AND is_active=1',
                (member.id,)
            ).fetchone()['n']

        disp_name = getattr(member, "display_name", getattr(member, "name", str(member.id)))
        if total == 0:
            e = discord.Embed(
                title=f'✦ {disp_name} • GLOBAL VOUCHES',
                description=f'{member.mention} has not received any public vouches yet across servers.',
                color=KyokaTheme.PRIMARY
            )
            avatar = getattr(member, "display_avatar", getattr(member, "avatar", None))
            if avatar:
                e.set_thumbnail(url=avatar.url)
            return await ctx.reply(embed=e, mention_author=False)

        view = VouchesPaginationView(ctx.author.id, member, total, ctx.guild.id)
        embed = view.build_embed()
        banner_file = AssetManager.attach_feature_banner(embed, "vouches")
        msg = await ctx.reply(embed=embed, file=banner_file, view=view, mention_author=False)
        view.message = msg

    # ── 5. BOT STAFF HISTORICAL IMPORT ────────────────────────────────────────
    @commands.command(name='vouchimport')
    @commands.guild_only()
    async def vouchimport(
        self,
        ctx,
        target: Union[discord.Member, discord.User],
        original_voucher: str,
        *,
        reason: str,
    ):
        """Import historical vouches from previous servers or platforms (Bot Staff Only).
        
        Usage:
        • +vouchimport @user @original_voucher Completed raid service
        • +vouchimport @user unknown Completed raid service (when original author is unknown)
        • +vouchimport 123456789 987654321 Delivered dough fruit (via Discord user IDs)
        """
        if not self.is_bot_staff(ctx):
            return await ctx.reply('❌ Access Denied: Only authorized Bot Staff or administrators can import historical vouches.', mention_author=False)

        clean_reason = reason.strip()[:500]
        if len(clean_reason) < 3:
            return await ctx.reply('❌ Please provide a valid historical review or service reason.', mention_author=False)

        # Parse original voucher argument: can be mention, numeric ID, or 'unknown'
        orig_clean = original_voucher.lower().strip()
        orig_voucher_id: Optional[int] = None
        orig_label: str = "Unknown / Historical Author"

        if orig_clean in ("unknown", "none", "na", "null", "?", "historical"):
            orig_voucher_id = None
            orig_label = "Unknown / Historical Author"
        else:
            digits = "".join(filter(str.isdigit, original_voucher))
            if digits:
                parsed_id = int(digits)
                if parsed_id == target.id:
                    return await ctx.reply('❌ Self-vouches cannot be imported.', mention_author=False)
                orig_voucher_id = parsed_id
                orig_label = f"<@{parsed_id}>"
            else:
                orig_voucher_id = None
                orig_label = f"`{original_voucher[:40]}`"

        service_type, parsed_reason = self._parse_service_and_reason(clean_reason)
        now = time.time()

        with conn() as c:
            # Check for exact duplicate historical import
            dup = c.execute(
                "SELECT id FROM vouches WHERE target_id=? AND reason=? AND source='historical_import' AND is_active=1",
                (target.id, clean_reason)
            ).fetchone()
            if dup:
                return await ctx.reply(
                    f'⚠️ A historical import with identical reason already exists: `#VOUCH-{dup["id"]:04d}`.',
                    mention_author=False
                )

            c.execute(
                '''INSERT INTO vouches(
                    guild_id, voucher_id, target_id, reason, created, held,
                    service_type, rating, source, staff_id, imported_at, origin_guild_name, is_active
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)''',
                (
                    ctx.guild.id,
                    orig_voucher_id,
                    target.id,
                    clean_reason,
                    now,
                    0,
                    service_type,
                    5,
                    'historical_import',
                    ctx.author.id,
                    now,
                    ctx.guild.name,
                )
            )
            vid = c.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Audit log entry
            c.execute(
                'INSERT INTO vouch_audit_log(guild_id, mod_id, action, vouch_id, reason, created) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, ctx.author.id, 'IMPORT', vid, f"Historical import for {target.id} by {ctx.author.id}", now)
            )

            # Global total
            new_total = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE target_id=? AND held=0 AND is_active=1',
                (target.id,)
            ).fetchone()['n']

        icon, s_label = SERVICE_TYPES.get(service_type, ("🛡️", service_type.title()))
        embed = discord.Embed(
            title='✦ KYŌKA • HISTORICAL VOUCH IMPORTED',
            description=f'**{target.mention}** has a new verified historical vouch record.\n\n'
                        f'> {discord.utils.escape_markdown(clean_reason)}',
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        avatar = getattr(target, "display_avatar", getattr(target, "avatar", None))
        if avatar:
            embed.set_thumbnail(url=avatar.url)

        embed.add_field(name='Vouch ID', value=f'`#VOUCH-{vid:04d}` `[STAFF IMPORT]`', inline=True)
        embed.add_field(name='Original Voucher', value=orig_label, inline=True)
        embed.add_field(name='Service Category', value=f'{icon} {s_label}', inline=True)
        embed.add_field(name='Importing Staff', value=ctx.author.mention, inline=True)
        embed.add_field(name='New Global Total', value=f'`{new_total}` vouches', inline=True)
        embed.add_field(name='Origin Server', value=f'`{ctx.guild.name}`', inline=True)

        embed.set_footer(text=f'Staff Audit ID #{vid:04d} • KYŌKA Global Reputation System')
        banner_file = AssetManager.attach_feature_banner(embed, "vouches")
        await ctx.reply(embed=embed, file=banner_file, mention_author=False)

    # ── 6. VOUCH REMOVAL (STAFF / MOD) ────────────────────────────────────────
    @commands.command(name='vouchremove')
    @commands.guild_only()
    async def vouchremove(self, ctx, vouch_id: int, *, reason: Optional[str] = "Moderator removal"):
        """Remove a vouch from public records and log the action in the audit trail."""
        if not self.is_bot_staff(ctx):
            return await ctx.reply('❌ Only authorized Bot Staff or administrators can remove vouches.', mention_author=False)

        with conn() as c:
            row = c.execute('SELECT * FROM vouches WHERE id=? AND is_active=1', (vouch_id,)).fetchone()
            if not row:
                return await ctx.reply(f'Vouch `#{vouch_id}` not found or already inactive.', mention_author=False)

            c.execute('DELETE FROM vouches WHERE id=?', (vouch_id,))
            c.execute(
                'INSERT INTO vouch_audit_log(guild_id, mod_id, action, vouch_id, reason, created) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, ctx.author.id, 'REMOVE', vouch_id, reason, time.time())
            )

        await ctx.reply(f'✅ Vouch `#{vouch_id:04d}` has been removed from global records. Audit log recorded.', mention_author=False)

    # ── 7. HELD VOUCHES REVIEW QUEUE ──────────────────────────────────────────
    @commands.command(name='heldvouches')
    @commands.guild_only()
    async def heldvouches(self, ctx):
        """Staff review queue for duplicate or held vouches."""
        if not self.is_bot_staff(ctx):
            return await ctx.reply('Only botstaff, administrators, or the bot owner can review held vouches.',
                                   mention_author=False)
        with conn() as c:
            c.execute('UPDATE vouches SET reviewer_id=? WHERE guild_id=? AND held=1 AND reviewer_id IS NULL',
                      (ctx.author.id, ctx.guild.id))
            if ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator:
                rows = c.execute(
                    'SELECT id, voucher_id, target_id, reason, reviewer_id, service_type FROM vouches WHERE guild_id=? AND held=1 AND is_active=1 ORDER BY id DESC LIMIT 20',
                    (ctx.guild.id,)
                ).fetchall()
            else:
                rows = c.execute(
                    'SELECT id, voucher_id, target_id, reason, reviewer_id, service_type FROM vouches WHERE guild_id=? AND held=1 AND reviewer_id=? AND is_active=1 ORDER BY id DESC LIMIT 20',
                    (ctx.guild.id, ctx.author.id)
                ).fetchall()

        if not rows:
            desc = 'No held vouches are currently in the review queue.'
        else:
            lines = []
            for r in rows:
                rev = f"<@{r['reviewer_id']}>" if r['reviewer_id'] else "unassigned"
                st = r['service_type'] or "general"
                lines.append(f"`#VOUCH-{r['id']:04d}` [{st}] <@{r['voucher_id']}> → <@{r['target_id']}>\n> {r['reason']}\n> Reviewer: {rev}")
            desc = "\n\n".join(lines)

        e = discord.Embed(title='✦ HELD VOUCHES • REVIEW QUEUE', color=KyokaTheme.PRIMARY, description=desc)
        banner_file = AssetManager.attach_feature_banner(e, "vouches")
        await ctx.reply(embed=e, file=banner_file, mention_author=False)

    # ── 8. BOT STAFF MANAGEMENT ───────────────────────────────────────────────
    @commands.command(name='botstaff')
    @commands.guild_only()
    async def botstaff(self, ctx, action: str, member: discord.Member):
        """Add or remove a staff member with vouch moderation privileges."""
        if ctx.author.id != 1505515188991033409 and not ctx.author.guild_permissions.administrator:
            return await ctx.reply('Only the bot owner or server administrators can manage botstaff.', mention_author=False)
        with conn() as c:
            act = action.lower().strip()
            if act == 'add':
                c.execute('INSERT OR IGNORE INTO botstaff VALUES(?,?)', (ctx.guild.id, member.id))
                msg = f'✅ {member.mention} added to reputation botstaff.'
            elif act == 'remove':
                c.execute('DELETE FROM botstaff WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
                msg = f'✅ {member.mention} removed from reputation botstaff.'
            else:
                return await ctx.reply('Use `+botstaff add @user` or `+botstaff remove @user`.', mention_author=False)
        await ctx.reply(msg, mention_author=False)

    # ── 9. SHOWCASE CHANNEL CONFIGURATION ─────────────────────────────────────
    @commands.command(name='vouchchannel')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def vouchchannel(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Configure or clear the dedicated vouch showcase channel."""
        with conn() as c:
            if channel is None:
                c.execute('DELETE FROM vouch_config WHERE guild_id=?', (ctx.guild.id,))
                return await ctx.reply('Vouch showcase channel has been reset to default.', mention_author=False)
            c.execute('INSERT OR REPLACE INTO vouch_config(guild_id, channel_id) VALUES(?,?)',
                      (ctx.guild.id, channel.id))
        await ctx.reply(f'✅ Vouch showcase channel set to {channel.mention}. All new verified vouches will be auto-posted there.', mention_author=False)


async def setup(bot):
    await bot.add_cog(Vouches(bot))
