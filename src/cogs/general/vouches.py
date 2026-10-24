from __future__ import annotations
import math
import sqlite3
import time
from pathlib import Path
from typing import Optional
import discord
from discord.ext import commands

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
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE IF NOT EXISTS vouches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            voucher_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created REAL NOT NULL,
            held INTEGER NOT NULL DEFAULT 0,
            reviewer_id INTEGER,
            service_type TEXT DEFAULT 'general',
            rating INTEGER DEFAULT 5
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
    try:
        c.execute("ALTER TABLE vouches ADD COLUMN service_type TEXT DEFAULT 'general'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE vouches ADD COLUMN rating INTEGER DEFAULT 5")
    except sqlite3.OperationalError:
        pass
    return c


class VouchesPaginationView(discord.ui.View):
    """Interactive pagination view for browsing member vouches."""

    def __init__(self, author_id: int, target_member: discord.Member, total_count: int, guild_id: int):
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
                'SELECT id, voucher_id, reason, created, service_type, rating FROM vouches '
                'WHERE guild_id=? AND target_id=? AND held=0 ORDER BY created DESC LIMIT ? OFFSET ?',
                (self.guild_id, self.target_member.id, self.per_page, offset)
            ).fetchall()

        embed = discord.Embed(
            title=f"✦ {self.target_member.display_name} • VOUCH REVIEWS",
            description=f"**Total Verified Vouches:** `{self.total_count}`\n"
                        f"**Page:** `{self.current_page}/{self.total_pages}`\n\n",
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=self.target_member.display_avatar.url)

        if not rows:
            embed.description += "*No vouches found on this page.*"
        else:
            for r in rows:
                stype = r["service_type"] or "general"
                icon, label = SERVICE_TYPES.get(stype, ("🛡️", stype.title()))
                stars = "⭐" * int(r["rating"] or 5)
                ts = int(r["created"])
                embed.add_field(
                    name=f"`#VOUCH-{r['id']:04d}` {icon} {label} · {stars}",
                    value=f"> {discord.utils.escape_markdown(r['reason'])}\n"
                          f"> *Vouched by <@{r['voucher_id']}> • <t:{ts}:R>*",
                    inline=False
                )

        embed.set_footer(text=f"KYŌKA Blox Fruits Reputation • Page {self.current_page}/{self.total_pages}")
        return embed

    @discord.ui.button(label="Prev", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command requester can paginate.", ephemeral=True)
        if self.current_page > 1:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command requester can paginate.", ephemeral=True)
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class Vouches(commands.Cog):
    category = 'Vouches'

    def __init__(self, bot):
        self.bot = bot

    def staff(self, ctx) -> bool:
        if ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator:
            return True
        with conn() as c:
            return c.execute('SELECT 1 FROM botstaff WHERE guild_id=? AND user_id=?',
                             (ctx.guild.id, ctx.author.id)).fetchone() is not None

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

    @commands.command(name='vouch')
    @commands.guild_only()
    async def vouch(self, ctx, member: discord.Member, *, reason: str):
        """Give a reputation vouch to a member for Blox Fruits trades or services."""
        if not ctx.guild:
            return
        if member.bot or member.id == ctx.author.id:
            return await ctx.reply('Self-vouches and bot vouches are not allowed.', mention_author=False)

        service_type, clean_reason = self._parse_service_and_reason(reason)
        clean_reason = clean_reason[:500].strip()
        if not clean_reason:
            return await ctx.reply('Please provide a meaningful review or service description.', mention_author=False)

        now = time.time()
        with conn() as c:
            # Check global and server cooldowns
            last = c.execute('SELECT created FROM vouch_global_cooldowns WHERE voucher_id=?',
                             (ctx.author.id,)).fetchone()
            if last and now - last['created'] < 300:
                rem = int(300 - (now - last["created"]))
                return await ctx.reply(f'⏳ You can vouch again in **{rem}** seconds.', mention_author=False)

            duplicate = c.execute('SELECT id FROM vouches WHERE guild_id=? AND voucher_id=? AND target_id=?',
                                  (ctx.guild.id, ctx.author.id, member.id)).fetchone()
            held = 1 if duplicate else 0

            c.execute(
                'INSERT INTO vouches(guild_id, voucher_id, target_id, reason, created, held, service_type, rating) '
                'VALUES(?,?,?,?,?,?,?,5)',
                (ctx.guild.id, ctx.author.id, member.id, clean_reason, now, held, service_type)
            )
            vid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT OR REPLACE INTO vouch_cooldowns VALUES(?,?,?)', (ctx.guild.id, ctx.author.id, now))
            c.execute('INSERT OR REPLACE INTO vouch_global_cooldowns VALUES(?,?)', (ctx.author.id, now))

            # Fetch target total vouches
            total = c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=0',
                              (ctx.guild.id, member.id)).fetchone()['n']

            # Check configured vouch channel
            cfg = c.execute('SELECT channel_id FROM vouch_config WHERE guild_id=?', (ctx.guild.id,)).fetchone()
            vouch_ch_id = cfg['channel_id'] if cfg else None

        if held:
            return await ctx.reply(
                f'🔒 Vouch **#VOUCH-{vid:04d}** was held for review because you already vouched for {member.mention}. '
                f'A staff member can review it using `+heldvouches`.',
                mention_author=False
            )

        icon, s_label = SERVICE_TYPES.get(service_type, ("🛡️", service_type.title()))
        e = discord.Embed(
            title='✦ KYŌKA • BLOX FRUITS VOUCH REGISTERED',
            description=f'**{member.mention}** received a verified reputation vouch!\n\n'
                        f"> {discord.utils.escape_markdown(clean_reason)}",
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name='Vouched By', value=ctx.author.mention, inline=True)
        e.add_field(name='Service Category', value=f'{icon} {s_label}', inline=True)
        e.add_field(name='Vouch ID', value=f'`#VOUCH-{vid:04d}`', inline=True)
        e.add_field(name='Rating', value='⭐⭐⭐⭐⭐ (5/5)', inline=True)
        e.add_field(name='Total Vouches', value=f'`{total}` active', inline=True)
        e.set_footer(text=f'KYŌKA Reputation System • Verified #{vid:04d}')

        await ctx.reply(embed=e, mention_author=False)

        # Dispatch to dedicated vouch channel if configured and distinct
        if vouch_ch_id and vouch_ch_id != ctx.channel.id:
            v_channel = ctx.guild.get_channel(vouch_ch_id)
            if isinstance(v_channel, discord.TextChannel):
                try:
                    await v_channel.send(embed=e)
                except Exception:
                    pass

    @commands.command(name='vouches', aliases=['repcheck'])
    @commands.guild_only()
    async def vouches(self, ctx, member: discord.Member = None):
        """View paginated vouch reviews and history for a member."""
        member = member or ctx.author
        with conn() as c:
            total = c.execute(
                'SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=0',
                (ctx.guild.id, member.id)
            ).fetchone()['n']

        if total == 0:
            e = discord.Embed(
                title=f'✦ {member.display_name} • VOUCHES',
                description=f'{member.mention} has not received any public vouches yet in this server.',
                color=PURPLE
            )
            e.set_thumbnail(url=member.display_avatar.url)
            return await ctx.reply(embed=e, mention_author=False)

        view = VouchesPaginationView(ctx.author.id, member, total, ctx.guild.id)
        embed = view.build_embed()
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    @commands.command(name='vouchprofile', aliases=['rep', 'reputation'])
    @commands.guild_only()
    async def vouchprofile(self, ctx, member: discord.Member = None):
        """Display Blox Fruits reputation statistics, breakdown by service, and vouch level."""
        member = member or ctx.author
        with conn() as c:
            total = c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=0',
                              (ctx.guild.id, member.id)).fetchone()['n']
            held = c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=1',
                             (ctx.guild.id, member.id)).fetchone()['n']
            breakdown = c.execute(
                'SELECT service_type, COUNT(*) as cnt FROM vouches WHERE guild_id=? AND target_id=? AND held=0 GROUP BY service_type',
                (ctx.guild.id, member.id)
            ).fetchall()

        # Build breakdown string
        bd_dict = {r['service_type'] or 'general': r['cnt'] for r in breakdown}
        lines = []
        for key, (icon, label) in SERVICE_TYPES.items():
            count = bd_dict.get(key, 0)
            if count > 0:
                lines.append(f"{icon} **{label}:** `{count}`")

        breakdown_text = "\n".join(lines) if lines else "*No categorized services yet.*"

        # Vouch tier title
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

        e = discord.Embed(
            title=f'✦ {member.display_name} • REPUTATION PROFILE',
            description=f'{member.mention}\n{badge}\n\n'
                        f'**Active Verified Vouches:** `{total}`\n'
                        f'**Positive Review Rate:** `100%` ⭐⭐⭐⭐⭐\n'
                        f'**Held Entries Pending:** `{held}`\n\n'
                        f'**Services Completed:**\n{breakdown_text}',
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f'User ID: {member.id} • KYŌKA Blox Fruits Trust & Safety')
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name='vouchleaderboard', aliases=['vouchlb', 'topvouches', 'repleaderboard'])
    @commands.guild_only()
    async def vouchleaderboard(self, ctx):
        """Display the server's top trusted members and service providers."""
        with conn() as c:
            rows = c.execute(
                'SELECT target_id, COUNT(*) as total FROM vouches '
                'WHERE guild_id=? AND held=0 GROUP BY target_id ORDER BY total DESC LIMIT 10',
                (ctx.guild.id,)
            ).fetchall()

        embed = discord.Embed(
            title=f'✦ {ctx.guild.name} • VOUCH LEADERBOARD',
            description='Top trusted Blox Fruits service providers and traders:\n\n',
            color=PURPLE,
            timestamp=discord.utils.utcnow()
        )
        if not rows:
            embed.description += "*No vouches recorded yet in this server. Use `+vouch @user [service] <reason>` to start!*"
        else:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for idx, r in enumerate(rows):
                medal = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
                target_user = ctx.guild.get_member(r['target_id'])
                name = target_user.mention if target_user else f"<@{r['target_id']}>"
                embed.description += f"{medal} {name} — **{r['total']} vouches** (100% ⭐⭐⭐⭐⭐)\n"

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.display_avatar.url)
        embed.set_footer(text='KYŌKA Reputation Leaderboard • Real-time stats')
        await ctx.reply(embed=embed, mention_author=False)

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

    @commands.command(name='heldvouches')
    @commands.guild_only()
    async def heldvouches(self, ctx):
        """Staff review queue for held duplicate vouches."""
        if not self.staff(ctx):
            return await ctx.reply('Only botstaff, administrators, or the bot owner can review held vouches.',
                                   mention_author=False)
        with conn() as c:
            c.execute('UPDATE vouches SET reviewer_id=? WHERE guild_id=? AND held=1 AND reviewer_id IS NULL',
                      (ctx.author.id, ctx.guild.id))
            if ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator:
                rows = c.execute(
                    'SELECT id, voucher_id, target_id, reason, reviewer_id, service_type FROM vouches WHERE guild_id=? AND held=1 ORDER BY id DESC LIMIT 20',
                    (ctx.guild.id,)
                ).fetchall()
            else:
                rows = c.execute(
                    'SELECT id, voucher_id, target_id, reason, reviewer_id, service_type FROM vouches WHERE guild_id=? AND held=1 AND reviewer_id=? ORDER BY id DESC LIMIT 20',
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

        e = discord.Embed(title='✦ HELD VOUCHES • REVIEW QUEUE', color=PURPLE, description=desc)
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name='vouchremove')
    @commands.guild_only()
    async def vouchremove(self, ctx, vouch_id: int, *, reason: Optional[str] = "Moderator removal"):
        """Remove a vouch from public records and log the action in audit trail."""
        with conn() as c:
            row = c.execute('SELECT * FROM vouches WHERE id=? AND guild_id=?', (vouch_id, ctx.guild.id)).fetchone()
            if not row:
                return await ctx.reply(f'Vouch `#{vouch_id}` not found in this server.', mention_author=False)

            if row['held']:
                privileged = (ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator)
                if not privileged and row['reviewer_id'] != ctx.author.id:
                    return await ctx.reply('Only the assigned reviewer, an administrator, or the bot owner can remove this held vouch.', mention_author=False)
            elif not self.staff(ctx):
                return await ctx.reply('Only botstaff, administrators, or the bot owner can remove public vouches.', mention_author=False)

            c.execute('DELETE FROM vouches WHERE id=?', (vouch_id,))
            c.execute('INSERT INTO vouch_audit_log(guild_id, mod_id, action, vouch_id, reason, created) VALUES(?,?,?,?,?,?)',
                      (ctx.guild.id, ctx.author.id, 'REMOVE', vouch_id, reason, time.time()))

        await ctx.reply(f'✅ Vouch `#{vouch_id:04d}` has been removed. Audit log recorded.', mention_author=False)

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


async def setup(bot):
    await bot.add_cog(Vouches(bot))

