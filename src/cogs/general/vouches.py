from __future__ import annotations
import sqlite3, time
from pathlib import Path
import discord
from discord.ext import commands

DB = Path('data/kyoka_reputation.sqlite3')
PURPLE = discord.Color.from_rgb(111, 67, 190)

def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.executescript('''CREATE TABLE IF NOT EXISTS vouches(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,voucher_id INTEGER NOT NULL,target_id INTEGER NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL,held INTEGER NOT NULL DEFAULT 0,reviewer_id INTEGER); CREATE TABLE IF NOT EXISTS vouch_cooldowns(guild_id INTEGER NOT NULL,voucher_id INTEGER NOT NULL,created REAL NOT NULL,PRIMARY KEY(guild_id,voucher_id)); CREATE TABLE IF NOT EXISTS botstaff(guild_id INTEGER NOT NULL,user_id INTEGER NOT NULL,PRIMARY KEY(guild_id,user_id)); CREATE TABLE IF NOT EXISTS vouch_global_cooldowns(voucher_id INTEGER PRIMARY KEY,created REAL NOT NULL);''')
    return c

class Vouches(commands.Cog):
    category = 'Vouches'

    def __init__(self, bot): self.bot=bot

    def staff(self, ctx):
        if ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator: return True
        with conn() as c: return c.execute('SELECT 1 FROM botstaff WHERE guild_id=? AND user_id=?',(ctx.guild.id,ctx.author.id)).fetchone() is not None
    @commands.command(name='vouch')
    @commands.guild_only()
    async def vouch(self, ctx, member: discord.Member, *, reason: str):
        if not ctx.guild: return
        if member.bot or member.id == ctx.author.id: return await ctx.reply('Self-vouches and bot vouches are not allowed.', mention_author=False)
        reason=reason.strip()[:500]
        if not reason: return await ctx.reply('Please provide a reason.', mention_author=False)
        now=time.time()
        with conn() as c:
            last=c.execute('SELECT created FROM vouch_global_cooldowns WHERE voucher_id=?',(ctx.author.id,)).fetchone()
            if last and now-last['created'] < 300: return await ctx.reply(f'You can vouch again in {int(300-(now-last["created"]))} seconds.', mention_author=False)
            duplicate=c.execute('SELECT id FROM vouches WHERE guild_id=? AND voucher_id=? AND target_id=?',(ctx.guild.id,ctx.author.id,member.id)).fetchone()
            held=1 if duplicate else 0
            c.execute('INSERT INTO vouches(guild_id,voucher_id,target_id,reason,created,held) VALUES(?,?,?,?,?,?)',(ctx.guild.id,ctx.author.id,member.id,reason,now,held))
            vid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT OR REPLACE INTO vouch_cooldowns VALUES(?,?,?)',(ctx.guild.id,ctx.author.id,now))
            c.execute('INSERT OR REPLACE INTO vouch_global_cooldowns VALUES(?,?)',(ctx.author.id,now))
        if held: return await ctx.reply(f'🔒 Vouch **#{vid}** was held for review because you already vouched for {member.mention}.', mention_author=False)
        e=discord.Embed(title='✦ KYŌKA • VOUCH REGISTERED',description=f'{member.mention} received a new reputation vouch.',color=PURPLE,timestamp=discord.utils.utcnow())
        e.set_thumbnail(url=member.display_avatar.url); e.add_field(name='Vouched by',value=ctx.author.mention,inline=True); e.add_field(name='Vouch ID',value=f'`#{vid}`',inline=True); e.add_field(name='Reason',value=reason,inline=False); e.set_footer(text='KYŌKA Reputation • Verified submission')
        await ctx.reply(embed=e,mention_author=False)
    @commands.command(name='vouches', aliases=['repcheck'])
    @commands.guild_only()
    async def vouches(self,ctx,member:discord.Member=None):
        member=member or ctx.author
        with conn() as c:
            rows=c.execute('SELECT voucher_id,reason,created,id FROM vouches WHERE guild_id=? AND target_id=? AND held=0 ORDER BY created DESC LIMIT 10',(ctx.guild.id,member.id)).fetchall()
            total=c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=0',(ctx.guild.id,member.id)).fetchone()['n']
        e=discord.Embed(title=f'✦ {member.display_name} • VOUCHES',description=f'**Active reputation:** {total}\n' + ('\n'.join(f'`#{r["id"]}` <@{r["voucher_id"]}> — {discord.utils.escape_markdown(r["reason"])}' for r in rows) if rows else 'No public vouches yet.'),color=PURPLE);e.set_thumbnail(url=member.display_avatar.url);await ctx.reply(embed=e,mention_author=False)
    @commands.command(name='vouchprofile')
    @commands.guild_only()
    async def vouchprofile(self,ctx,member:discord.Member=None):
        member=member or ctx.author
        with conn() as c:
            total=c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=0',(ctx.guild.id,member.id)).fetchone()['n']
            held=c.execute('SELECT COUNT(*) n FROM vouches WHERE guild_id=? AND target_id=? AND held=1',(ctx.guild.id,member.id)).fetchone()['n']
        e=discord.Embed(title='✦ KYŌKA • REPUTATION PROFILE',description=f'{member.mention}\n\n**Active vouches** `{total}`\n**Held entries** `{held}`\n**Member ID** `{member.id}`',color=PURPLE);e.set_thumbnail(url=member.display_avatar.url);await ctx.reply(embed=e,mention_author=False)
    @commands.command(name='heldvouches')
    @commands.guild_only()
    async def heldvouches(self,ctx):
        if not self.staff(ctx): return await ctx.reply('Only botstaff, administrators, or the bot owner can review held vouches.',mention_author=False)
        with conn() as c:
            # Assign unclaimed entries to the staff member who opens the queue.
            c.execute('UPDATE vouches SET reviewer_id=? WHERE guild_id=? AND held=1 AND reviewer_id IS NULL',(ctx.author.id,ctx.guild.id))
            if ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator:
                rows=c.execute('SELECT id,voucher_id,target_id,reason,reviewer_id FROM vouches WHERE guild_id=? AND held=1 ORDER BY id DESC LIMIT 20',(ctx.guild.id,)).fetchall()
            else:
                rows=c.execute('SELECT id,voucher_id,target_id,reason,reviewer_id FROM vouches WHERE guild_id=? AND held=1 AND reviewer_id=? ORDER BY id DESC LIMIT 20',(ctx.guild.id,ctx.author.id)).fetchall()
        e=discord.Embed(title='✦ HELD VOUCHES • REVIEW QUEUE',color=PURPLE,description='\n'.join(f'`#{r["id"]}` <@{r["voucher_id"]}> → <@{r["target_id"]}>\n{r["reason"]} • reviewer: {("<@"+str(r["reviewer_id"])+">") if r["reviewer_id"] else "unassigned"}' for r in rows) or 'No held vouches are assigned to you.');await ctx.reply(embed=e,mention_author=False)
    @commands.command(name='vouchremove')
    @commands.guild_only()
    async def vouchremove(self,ctx,vouch_id:int):
        with conn() as c:
            row=c.execute('SELECT * FROM vouches WHERE id=? AND guild_id=?',(vouch_id,ctx.guild.id)).fetchone()
            if not row: return await ctx.reply('Vouch ID not found.',mention_author=False)
            if row['held']:
                privileged = (ctx.author.id == 1505515188991033409 or ctx.author.guild_permissions.administrator)
                if not privileged and row['reviewer_id'] != ctx.author.id:
                    return await ctx.reply('Only the assigned reviewer, an administrator, or the bot owner can remove this held vouch.', mention_author=False)
            elif not self.staff(ctx):
                return await ctx.reply('Only botstaff, administrators, or the bot owner can remove public vouches.', mention_author=False)
            c.execute('DELETE FROM vouches WHERE id=?',(vouch_id,))
        await ctx.reply(f'Vouch `#{vouch_id}` removed.',mention_author=False)
    @commands.command(name='botstaff')
    @commands.guild_only()
    async def botstaff(self,ctx,action:str,member:discord.Member):
        if ctx.author.id != 1505515188991033409 and not ctx.author.guild_permissions.administrator: return await ctx.reply('Only the bot owner or server administrators can manage botstaff.',mention_author=False)
        with conn() as c:
            if action.lower()=='add': c.execute('INSERT OR IGNORE INTO botstaff VALUES(?,?)',(ctx.guild.id,member.id)); msg=f'{member.mention} added to botstaff.'
            elif action.lower()=='remove': c.execute('DELETE FROM botstaff WHERE guild_id=? AND user_id=?',(ctx.guild.id,member.id)); msg=f'{member.mention} removed from botstaff.'
            else: return await ctx.reply('Use `?botstaff add @user` or `?botstaff remove @user`.',mention_author=False)
        await ctx.reply(msg,mention_author=False)

async def setup(bot): await bot.add_cog(Vouches(bot))
