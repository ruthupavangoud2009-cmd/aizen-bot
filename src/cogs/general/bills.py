from __future__ import annotations
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional, Union
import discord
from discord.ext import commands

from src.security.owner import is_owner_or_staff
from src.ui.theme import KyokaTheme
from src.ui.asset_manager import AssetManager

DB = Path('data/kyoka_billing.sqlite3')

BLOX_CATEGORIES = {
    "raid": ("⚡", "Raids & Carries"),
    "level": ("📈", "Leveling & Grinding"),
    "leveling": ("📈", "Leveling & Grinding"),
    "bounty": ("⚔️", "Bounty Hunting / PvP"),
    "fruit": ("🍎", "Fruit Delivery / Trade"),
    "trade": ("🤝", "Trading Assistance"),
    "boss": ("👹", "Boss Farming"),
    "custom": ("🛡️", "Custom Blox Fruits Service"),
}

STATUS_BADGES = {
    "PENDING": ("🟡", "PENDING PAYMENT"),
    "UNPAID": ("🟡", "PENDING PAYMENT"),
    "PAID": ("🟢", "PAID & VERIFIED"),
    "CANCELLED": ("🔴", "CANCELLED"),
    "OVERDUE": ("🟠", "OVERDUE"),
    "REFUNDED": ("🟣", "REFUNDED"),
}


def db():
    """Establish SQLite connection and ensure schema with backward-compatible migrations."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE IF NOT EXISTS config(
            guild INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'KYŌKA BLOX FRUITS SERVICES',
            currency TEXT DEFAULT 'Beli',
            payment TEXT DEFAULT 'Trade fruits in-game or send payment per staff instructions',
            taxes TEXT DEFAULT 'APA:0,Conglomerate:0,Priority:0'
        );
        UPDATE config SET currency = 'Beli' WHERE currency = 'USD';
        CREATE TABLE IF NOT EXISTS bills(
            id TEXT PRIMARY KEY,
            guild INTEGER,
            creator INTEGER,
            customer INTEGER,
            description TEXT,
            subtotal REAL,
            tax REAL,
            total REAL,
            status TEXT,
            created REAL,
            category TEXT DEFAULT 'Raids & Carries',
            service_item TEXT DEFAULT '',
            payment_method TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            quantity INTEGER DEFAULT 1,
            discount REAL DEFAULT 0.0,
            updated REAL,
            evidence_url TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS bill_audit_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild INTEGER NOT NULL,
            bill_id TEXT NOT NULL,
            staff_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            timestamp REAL NOT NULL
        );
    ''')
    for col_def in [
        ("category", "TEXT DEFAULT 'Raids & Carries'"),
        ("service_item", "TEXT DEFAULT ''"),
        ("payment_method", "TEXT DEFAULT ''"),
        ("notes", "TEXT DEFAULT ''"),
        ("quantity", "INTEGER DEFAULT 1"),
        ("discount", "REAL DEFAULT 0.0"),
        ("updated", "REAL"),
        ("evidence_url", "TEXT DEFAULT ''"),
    ]:
        try:
            c.execute(f"ALTER TABLE bills ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass
    return c


class Bills(commands.Cog, name="Bills"):
    """Blox Fruits Service Billing, Invoices & Receipt Ledger."""
    category = 'Bills'

    def __init__(self, bot):
        self.bot = bot

    def is_staff(self, ctx) -> bool:
        """Check if author is an authorized staff member for invoice creation and payment processing."""
        if is_owner_or_staff(ctx.author.id):
            return True
        # 1. Authoritative Primary Owner
        if ctx.author.id == 1505515188991033409:
            return True
        # 2. Server Administrator or Guild Managers
        if ctx.guild and getattr(ctx.author, "guild_permissions", None):
            if ctx.author.guild_permissions.administrator:
                return True
            if ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.manage_messages:
                return True
        # 3. Check botstaff table from reputation database if available
        try:
            rep_db = Path('data/kyoka_reputation.sqlite3')
            if rep_db.exists():
                with sqlite3.connect(rep_db) as rc:
                    if ctx.guild:
                        row = rc.execute('SELECT 1 FROM botstaff WHERE guild_id=? AND user_id=?',
                                         (ctx.guild.id, ctx.author.id)).fetchone()
                        if row:
                            return True
                    row_global = rc.execute('SELECT 1 FROM botstaff WHERE user_id=?',
                                            (ctx.author.id,)).fetchone()
                    if row_global:
                        return True
        except Exception:
            pass
        return False

    def config(self, g: int):
        with db() as c:
            c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)', (g,))
            return c.execute('SELECT * FROM config WHERE guild=?', (g,)).fetchone()

    def taxes(self, g: int):
        cfg = self.config(g)
        result = []
        for bit in cfg['taxes'].split(','):
            try:
                n, v = bit.split(':', 1)
                result.append((n, float(v)))
            except Exception:
                pass
        return cfg, result

    def _format_invoice_embed(self, ctx, r: sqlite3.Row, cfg: sqlite3.Row) -> discord.Embed:
        status_key = (r['status'] or 'PENDING').upper()
        s_icon, s_label = STATUS_BADGES.get(status_key, ("⚪", status_key))
        ts = int(r['created']) if r['created'] else int(time.time())
        category = r['category'] or 'Blox Fruits Service'

        embed = discord.Embed(
            title=f"✦ {cfg['name']} • INVOICE `{r['id']}`",
            description=f"Official Blox Fruits Service Receipt & Payment Ledger\n"
                        f"**Status:** {s_icon} **{s_label}**\n"
                        f"**Issued:** <t:{ts}:f> (<t:{ts}:R>)",
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        elif self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="👤 Customer", value=f"<@{r['customer']}>\n`ID: {r['customer']}`", inline=True)
        embed.add_field(name="🛡️ Service Provider", value=f"<@{r['creator']}>", inline=True)
        embed.add_field(name="🏷️ Category", value=f"`{category}`", inline=True)

        item_name = r['service_item'] or r['description'] or "Blox Fruits Service"
        embed.add_field(name="📦 Service / Item Details", value=f"> {discord.utils.escape_markdown(item_name)}", inline=False)

        pay_method = r['payment_method'] or f"{cfg['currency']} {r['total']:,.2f}"
        embed.add_field(name="💰 Agreed Payment / Total Due", value=f"**{pay_method}**", inline=True)

        if r['subtotal'] and r['subtotal'] > 0:
            embed.add_field(
                name="📊 Price Breakdown",
                value=f"Subtotal: `{cfg['currency']} {r['subtotal']:,.2f}`\nTax: `{cfg['currency']} {r['tax']:,.2f}`\nTotal: `**{cfg['currency']} {r['total']:,.2f}**`",
                inline=True
            )

        notes = r['notes'] or cfg['payment']
        if notes:
            embed.add_field(name="📝 Payment Instructions & Terms", value=f"> {notes[:800]}", inline=False)

        embed.set_footer(text=f"Issued by staff <@{r['creator']}> • KYŌKA Blox Fruits Invoicing")
        return embed

    @commands.command(name='billsetup')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def billsetup(self, ctx):
        """View or configure the server's Blox Fruits invoicing settings."""
        cfg, _ = self.taxes(ctx.guild.id)
        e = discord.Embed(
            title='✦ KYŌKA • BLOX FRUITS INVOICE CONFIGURATION',
            description=f"**Provider Name:** `{cfg['name']}`\n"
                        f"**Default Currency:** `{cfg['currency']}`\n"
                        f"**Payment Instructions:**\n> {cfg['payment']}\n\n"
                        f"**Configuration Commands:**\n"
                        f"• `+billname <business_name>` — Update server shop/service name\n"
                        f"• `+billcurrency <code>` — Set default currency (e.g. `BELI`, `FRUIT`, `ROBUX`)\n"
                        f"• `+billpayment <instructions>` — Set accepted fruit/payment instructions\n"
                        f"• `+billtax <name> <percent>` — Set optional surcharge/tax rate",
            color=KyokaTheme.PRIMARY
        )
        banner_file = AssetManager.attach_feature_banner(e, "service_bills")
        await ctx.reply(embed=e, file=banner_file, mention_author=False)

    @commands.command(name='billname')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def billname(self, ctx, *, name: str):
        """Set the business or provider name displayed on invoices."""
        clean_name = name[:100].strip()
        with db() as c:
            c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)', (ctx.guild.id,))
            c.execute('UPDATE config SET name=? WHERE guild=?', (clean_name, ctx.guild.id))
        await ctx.reply(f'✅ Invoicing provider name updated to: **{clean_name}**', mention_author=False)

    @commands.command(name='billcurrency')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def billcurrency(self, ctx, code: str):
        """Set default currency or payment unit (e.g. BELI, FRUIT, ROBUX)."""
        code_clean = code.upper()[:12].strip()
        with db() as c:
            c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)', (ctx.guild.id,))
            c.execute('UPDATE config SET currency=? WHERE guild=?', (code_clean, ctx.guild.id))
        await ctx.reply(f'✅ Invoice currency updated to: **{code_clean}**', mention_author=False)

    @commands.command(name='billtax')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def billtax(self, ctx, name: str, percent: float):
        """Configure optional tax or fee percentages."""
        if not 0 <= percent <= 100:
            return await ctx.reply('Tax must be between 0 and 100 percent.', mention_author=False)
        cfg, taxes = self.taxes(ctx.guild.id)
        taxes = [(n, (percent if n.lower() == name.lower() else v)) for n, v in taxes]
        if not any(n.lower() == name.lower() for n, v in taxes):
            taxes.append((name[:30], percent))
        serialized = ','.join(f'{n}:{v}' for n, v in taxes)
        with db() as c:
            c.execute('UPDATE config SET taxes=? WHERE guild=?', (serialized, ctx.guild.id))
        await ctx.reply(f'✅ Fee/Tax `{name}` set to `{percent:.2f}%`.', mention_author=False)

    @commands.command(name='billpayment')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def billpayment(self, ctx, *, instructions: str):
        """Set instructions for customer payments (fruit trading details, Robux, etc.)."""
        clean_inst = instructions[:1000].strip()
        with db() as c:
            c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)', (ctx.guild.id,))
            c.execute('UPDATE config SET payment=? WHERE guild=?', (clean_inst, ctx.guild.id))
        await ctx.reply('✅ Invoice payment instructions updated.', mention_author=False)

    @commands.command(name='bill')
    @commands.guild_only()
    async def bill(self, ctx, customer: Union[discord.Member, discord.User], *args):
        """Create a new Blox Fruits service invoice for a customer.
        
        Usage Examples:
        • +bill @user raid Dough V2 Full Awakening Kitsune + Mammoth
        • +bill @user leveling 1 to 2550 Max Level 1500 Robux
        • +bill @user bounty 2.5M to 5M Bounty Leopard Fruit
        • +bill @user 25.00 Fast Raid Carry (Legacy Numeric Syntax)
        """
        if not self.is_staff(ctx):
            return await ctx.reply('❌ Only server staff or administrators can issue service bills.', mention_author=False)

        if getattr(customer, "bot", False):
            return await ctx.reply('Cannot issue an invoice to a bot.', mention_author=False)

        if not args:
            return await ctx.reply(
                "Usage: `+bill @customer <category> <service_item> <agreed_payment> [notes]`\n"
                "Categories: `raid`, `leveling`, `bounty`, `fruit`, `trade`, `boss`, `custom`\n"
                "Example: `+bill @trader raid 5x Dough Raids Kitsune Fruit Fast completion`",
                mention_author=False
            )

        cfg, taxes = self.taxes(ctx.guild.id)
        ident = f"BF-INV-{uuid.uuid4().hex[:6].upper()}"
        now = time.time()

        # Check for legacy numeric syntax: +bill @customer <float_amount> <description>
        is_numeric = False
        amount = 0.0
        try:
            amount = float(args[0])
            is_numeric = True
        except ValueError:
            pass

        if is_numeric and len(args) >= 2:
            description = " ".join(args[1:])[:500]
            tax_total = sum(amount * p / 100 for n, p in taxes)
            total = amount + tax_total
            category = "Blox Fruits Service"
            service_item = description
            payment_method = f"{cfg['currency']} {total:,.2f}"
            notes = cfg['payment']
        else:
            first_arg = args[0].lower()
            matched_cat = None
            for key, (icon, label) in BLOX_CATEGORIES.items():
                if first_arg == key or first_arg.startswith(key):
                    matched_cat = label
                    break

            if matched_cat and len(args) >= 3:
                category = matched_cat
                service_item = args[1]
                payment_method = args[2]
                notes = " ".join(args[3:]) if len(args) > 3 else cfg['payment']
                description = f"{service_item} ({payment_method})"
                subtotal = 0.0
                tax_total = 0.0
                total = 0.0
            else:
                category = "Blox Fruits Service"
                description = " ".join(args)[:500]
                service_item = description
                payment_method = "In-game Fruit / Robux"
                notes = cfg['payment']
                subtotal = 0.0
                tax_total = 0.0
                total = 0.0

        with db() as c:
            c.execute(
                '''INSERT INTO bills(
                    id, guild, creator, customer, description, subtotal, tax, total,
                    status, created, category, service_item, payment_method, notes
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    ident, ctx.guild.id, ctx.author.id, customer.id, description,
                    amount, tax_total if is_numeric else 0.0, total, 'PENDING', now,
                    category, service_item, payment_method, notes
                )
            )
            c.execute(
                'INSERT INTO bill_audit_log(guild, bill_id, staff_id, old_status, new_status, timestamp) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, ident, ctx.author.id, 'NONE', 'PENDING', now)
            )
            row = c.execute('SELECT * FROM bills WHERE id=?', (ident,)).fetchone()

        embed = self._format_invoice_embed(ctx, row, cfg)
        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        await ctx.reply(
            content=f"🔔 {customer.mention}, an official Blox Fruits service invoice has been issued to you by {ctx.author.mention}:",
            embed=embed,
            file=banner_file,
            mention_author=False
        )

    @commands.command(name='billview')
    @commands.guild_only()
    async def billview(self, ctx, ident: str):
        """View complete details and status of an invoice."""
        clean_id = ident.upper().strip()
        with db() as c:
            r = c.execute('SELECT * FROM bills WHERE id=? AND guild=?', (clean_id, ctx.guild.id)).fetchone()
            if not r:
                r = c.execute('SELECT * FROM bills WHERE id LIKE ? AND guild=?', (f"%{clean_id}%", ctx.guild.id)).fetchone()
        if not r:
            return await ctx.reply(f'❌ Invoice `{ident}` was not found in this server.', mention_author=False)

        cfg, _ = self.taxes(ctx.guild.id)
        embed = self._format_invoice_embed(ctx, r, cfg)
        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        await ctx.reply(embed=embed, file=banner_file, mention_author=False)

    @commands.command(name='billpaid')
    @commands.guild_only()
    async def billpaid(self, ctx, ident: str):
        """Mark an invoice as PAID (Staff only)."""
        if not self.is_staff(ctx):
            return await ctx.reply('❌ Only server staff can verify invoice payments.', mention_author=False)
        clean_id = ident.upper().strip()
        with db() as c:
            r = c.execute('SELECT * FROM bills WHERE id=? AND guild=?', (clean_id, ctx.guild.id)).fetchone()
            if not r:
                return await ctx.reply(f'Invoice `{ident}` not found.', mention_author=False)

            # Anti-Fraud Protection: Customers cannot mark their own invoices as paid
            if r['customer'] == ctx.author.id and ctx.author.id != 1505515188991033409:
                return await ctx.reply('❌ Anti-Fraud Protection: Customers cannot verify or mark their own invoices as paid.', mention_author=False)

            old_status = r['status']
            c.execute('UPDATE bills SET status=?, updated=? WHERE id=? AND guild=?', ('PAID', time.time(), clean_id, ctx.guild.id))
            c.execute(
                'INSERT INTO bill_audit_log(guild, bill_id, staff_id, old_status, new_status, timestamp) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, clean_id, ctx.author.id, old_status, 'PAID', time.time())
            )
            r = c.execute('SELECT * FROM bills WHERE id=?', (clean_id,)).fetchone()

        cfg, _ = self.taxes(ctx.guild.id)
        embed = self._format_invoice_embed(ctx, r, cfg)
        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        await ctx.reply(
            content=f"✅ Invoice `{clean_id}` marked as **PAID** by {ctx.author.mention}. Customer: <@{r['customer']}>",
            embed=embed,
            file=banner_file,
            mention_author=False
        )

    @commands.command(name='billcancel')
    @commands.guild_only()
    async def billcancel(self, ctx, ident: str):
        """Cancel an invoice (Staff only)."""
        if not self.is_staff(ctx):
            return await ctx.reply('❌ Only server staff can cancel invoices.', mention_author=False)
        clean_id = ident.upper().strip()
        with db() as c:
            r = c.execute('SELECT * FROM bills WHERE id=? AND guild=?', (clean_id, ctx.guild.id)).fetchone()
            if not r:
                return await ctx.reply(f'Invoice `{ident}` not found.', mention_author=False)
            old_status = r['status']
            c.execute('UPDATE bills SET status=?, updated=? WHERE id=? AND guild=?', ('CANCELLED', time.time(), clean_id, ctx.guild.id))
            c.execute(
                'INSERT INTO bill_audit_log(guild, bill_id, staff_id, old_status, new_status, timestamp) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, clean_id, ctx.author.id, old_status, 'CANCELLED', time.time())
            )
        await ctx.reply(f"🚫 Invoice `{clean_id}` has been **CANCELLED**.", mention_author=False)

    @commands.command(name='billrefund')
    @commands.guild_only()
    async def billrefund(self, ctx, ident: str):
        """Mark an invoice as REFUNDED (Staff only)."""
        if not self.is_staff(ctx):
            return await ctx.reply('❌ Only server staff can issue invoice refunds.', mention_author=False)
        clean_id = ident.upper().strip()
        with db() as c:
            r = c.execute('SELECT * FROM bills WHERE id=? AND guild=?', (clean_id, ctx.guild.id)).fetchone()
            if not r:
                return await ctx.reply(f'Invoice `{ident}` not found.', mention_author=False)
            old_status = r['status']
            c.execute('UPDATE bills SET status=?, updated=? WHERE id=? AND guild=?', ('REFUNDED', time.time(), clean_id, ctx.guild.id))
            c.execute(
                'INSERT INTO bill_audit_log(guild, bill_id, staff_id, old_status, new_status, timestamp) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, clean_id, ctx.author.id, old_status, 'REFUNDED', time.time())
            )
        await ctx.reply(f"🟣 Invoice `{clean_id}` has been marked as **REFUNDED**.", mention_author=False)

    @commands.command(name='billstatus')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def billstatus(self, ctx, ident: str, status: str):
        """Update invoice status to custom value (UNPAID, PENDING, PAID, CANCELLED, OVERDUE, REFUNDED)."""
        clean_id = ident.upper().strip()
        status_clean = status.upper().strip()
        if status_clean not in {'PENDING', 'UNPAID', 'PAID', 'CANCELLED', 'OVERDUE', 'REFUNDED'}:
            return await ctx.reply('Valid statuses: `PENDING`, `PAID`, `CANCELLED`, `OVERDUE`, `REFUNDED`.', mention_author=False)
        with db() as c:
            r = c.execute('SELECT * FROM bills WHERE id=? AND guild=?', (clean_id, ctx.guild.id)).fetchone()
            if not r:
                return await ctx.reply('Invoice not found in this server.', mention_author=False)
            old_status = r['status']
            c.execute('UPDATE bills SET status=?, updated=? WHERE id=? AND guild=?', (status_clean, time.time(), clean_id, ctx.guild.id))
            c.execute(
                'INSERT INTO bill_audit_log(guild, bill_id, staff_id, old_status, new_status, timestamp) VALUES(?,?,?,?,?,?)',
                (ctx.guild.id, clean_id, ctx.author.id, old_status, status_clean, time.time())
            )
        await ctx.reply(f'✅ Invoice `{clean_id}` status updated to **{status_clean}**.', mention_author=False)

    @commands.command(name='billlist', aliases=['billhistory'])
    @commands.guild_only()
    async def billlist(self, ctx, customer: Optional[discord.Member] = None):
        """View recent invoices for a customer or the entire server."""
        with db() as c:
            if customer:
                rows = c.execute(
                    'SELECT id, customer, description, category, payment_method, status, created FROM bills '
                    'WHERE guild=? AND customer=? ORDER BY created DESC LIMIT 15',
                    (ctx.guild.id, customer.id)
                ).fetchall()
                title = f'✦ {customer.display_name} • SERVICE INVOICES'
            else:
                rows = c.execute(
                    'SELECT id, customer, description, category, payment_method, status, created FROM bills '
                    'WHERE guild=? ORDER BY created DESC LIMIT 15',
                    (ctx.guild.id,)
                ).fetchall()
                title = f'✦ {ctx.guild.name} • SERVICE INVOICES'

        if not rows:
            desc = 'No invoices recorded yet.'
        else:
            lines = []
            for r in rows:
                st = (r['status'] or 'PENDING').upper()
                icon, _ = STATUS_BADGES.get(st, ("⚪", st))
                desc_snippet = (r['payment_method'] or r['description'] or 'Service')[:30]
                lines.append(f"`{r['id']}` • {icon} **{st}** • <@{r['customer']}> — *{desc_snippet}*")
            desc = "\n".join(lines)

        embed = discord.Embed(title=title, description=desc, color=KyokaTheme.PRIMARY, timestamp=discord.utils.utcnow())
        embed.set_footer(text='Type +billview <id> to view full details')
        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        await ctx.reply(embed=embed, file=banner_file, mention_author=False)

    @commands.command(name='billstats')
    @commands.guild_only()
    async def billstats(self, ctx):
        """View server invoice statistics, total revenue, and completed orders."""
        with db() as c:
            total = c.execute('SELECT COUNT(*) n FROM bills WHERE guild=?', (ctx.guild.id,)).fetchone()['n']
            paid = c.execute("SELECT COUNT(*) n FROM bills WHERE guild=? AND status='PAID'", (ctx.guild.id,)).fetchone()['n']
            pending = c.execute("SELECT COUNT(*) n FROM bills WHERE guild=? AND status IN ('PENDING', 'UNPAID')", (ctx.guild.id,)).fetchone()['n']
            cancelled = c.execute("SELECT COUNT(*) n FROM bills WHERE guild=? AND status='CANCELLED'", (ctx.guild.id,)).fetchone()['n']
            cat_rows = c.execute(
                'SELECT category, COUNT(*) as cnt FROM bills WHERE guild=? GROUP BY category ORDER BY cnt DESC',
                (ctx.guild.id,)
            ).fetchall()

        cat_text = "\n".join(f"• **{r['category'] or 'Other'}:** `{r['cnt']}` order(s)" for r in cat_rows) if cat_rows else "*No categorized orders yet.*"

        embed = discord.Embed(
            title=f'✦ {ctx.guild.name} • INVOICE METRICS',
            description=f"**Total Invoices Issued:** `{total}`\n\n"
                        f"🟢 **Completed & Paid:** `{paid}`\n"
                        f"🟡 **Pending Orders:** `{pending}`\n"
                        f"🔴 **Cancelled Orders:** `{cancelled}`\n\n"
                        f"**Category Breakdown:**\n{cat_text}",
            color=KyokaTheme.PRIMARY,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text='KYŌKA Blox Fruits Service Analytics')
        banner_file = AssetManager.attach_feature_banner(embed, "service_bills")
        await ctx.reply(embed=embed, file=banner_file, mention_author=False)


async def setup(bot):
    await bot.add_cog(Bills(bot))
