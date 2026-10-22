from __future__ import annotations
import sqlite3, time, uuid
from pathlib import Path
import discord
from discord.ext import commands
DB=Path('data/kyoka_billing.sqlite3'); PURPLE=discord.Color.from_rgb(111,67,190)
def db():
 DB.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
 c.executescript('''CREATE TABLE IF NOT EXISTS config(guild INTEGER PRIMARY KEY,name TEXT DEFAULT 'KYŌKA SERVICES',currency TEXT DEFAULT 'USD',payment TEXT DEFAULT 'Contact the server staff',taxes TEXT DEFAULT 'APA:0,Conglomerate:0,Priority:0'); CREATE TABLE IF NOT EXISTS bills(id TEXT PRIMARY KEY,guild INTEGER,creator INTEGER,customer INTEGER,description TEXT,subtotal REAL,tax REAL,total REAL,status TEXT,created REAL);'''); return c
class Bills(commands.Cog):
 category='Bills'
 def __init__(self,bot): self.bot=bot
 def config(self,g):
  with db() as c:
   c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)',(g,)); return c.execute('SELECT * FROM config WHERE guild=?',(g,)).fetchone()
 def taxes(self,g):
  cfg=self.config(g); result=[]
  for bit in cfg['taxes'].split(','):
   try: n,v=bit.split(':',1); result.append((n,float(v)))
   except: pass
  return cfg,result
 @commands.command(name='billsetup')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billsetup(self,ctx):
  cfg,_=self.taxes(ctx.guild.id);e=discord.Embed(title='✦ KYŌKA • BILLING CONFIGURATION',description=f'**Business:** {cfg["name"]}\n**Currency:** {cfg["currency"]}\n**Payment:** {cfg["payment"]}\n**Taxes:** {cfg["taxes"]}\n\nCommands: `?billname <name>`, `?billcurrency <code>`, `?billtax <name> <percent>`, `?billpayment <instructions>`',color=PURPLE);await ctx.reply(embed=e,mention_author=False)
 @commands.command(name='billname')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billname(self,ctx,*,name:str):
  with db() as c:c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)',(ctx.guild.id,));c.execute('UPDATE config SET name=? WHERE guild=?',(name[:100],ctx.guild.id))
  await ctx.reply('Billing name updated.',mention_author=False)
 @commands.command(name='billcurrency')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billcurrency(self,ctx,code:str):
  with db() as c:c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)',(ctx.guild.id,));c.execute('UPDATE config SET currency=? WHERE guild=?',(code.upper()[:8],ctx.guild.id))
  await ctx.reply('Currency updated.',mention_author=False)
 @commands.command(name='billtax')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billtax(self,ctx,name:str,percent:float):
  if not 0<=percent<=100:return await ctx.reply('Tax must be between 0 and 100 percent.',mention_author=False)
  cfg,taxes=self.taxes(ctx.guild.id); found=False; taxes=[(n,(percent if n.lower()==name.lower() else v)) for n,v in taxes]
  if not any(n.lower()==name.lower() for n,v in taxes): taxes.append((name[:30],percent))
  serialized=','.join(f'{n}:{v}' for n,v in taxes)
  with db() as c:c.execute('UPDATE config SET taxes=? WHERE guild=?',(serialized,ctx.guild.id))
  await ctx.reply(f'Tax `{name}` set to `{percent:.2f}%`.',mention_author=False)
 @commands.command(name='billpayment')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billpayment(self,ctx,*,instructions:str):
  with db() as c:c.execute('INSERT OR IGNORE INTO config(guild) VALUES(?)',(ctx.guild.id,));c.execute('UPDATE config SET payment=? WHERE guild=?',(instructions[:1000],ctx.guild.id))
  await ctx.reply('Payment instructions updated.',mention_author=False)
 @commands.command(name='bill')
 @commands.guild_only()
 async def bill(self,ctx,customer:discord.Member,amount:float,*,description:str):
  if amount<=0 or amount>1_000_000_000:return await ctx.reply('Enter a valid positive subtotal.',mention_author=False)
  cfg,taxes=self.taxes(ctx.guild.id); tax_total=sum(amount*p/100 for n,p in taxes); total=amount+tax_total; ident=uuid.uuid4().hex[:10].upper(); now=time.time()
  with db() as c:c.execute('INSERT INTO bills VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,ctx.guild.id,ctx.author.id,customer.id,description[:500],amount,tax_total,total,'UNPAID',now))
  e=discord.Embed(title=f'✦ {cfg["name"]} • INVOICE',description=f'**Bill ID:** `{ident}`\n**Billed to:** {customer.mention}\n**Service:** {description[:500]}',color=PURPLE,timestamp=discord.utils.utcnow());e.add_field(name='Subtotal',value=f'{cfg["currency"]} {amount:,.2f}',inline=True);e.add_field(name='Taxes',value='\n'.join(f'{n} ({p:g}%): {cfg["currency"]} {amount*p/100:,.2f}' for n,p in taxes) or 'None',inline=True);e.add_field(name='TOTAL DUE',value=f'**{cfg["currency"]} {total:,.2f}**',inline=False);e.add_field(name='Payment instructions',value=cfg['payment'][:1024],inline=False);e.add_field(name='Status',value='🟠 UNPAID',inline=True);e.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else self.bot.user.display_avatar.url);e.set_footer(text=f'Issued by {ctx.author} • KYŌKA Billing');await ctx.reply(embed=e,mention_author=False)
 @commands.command(name='billview')
 @commands.guild_only()
 async def billview(self,ctx,ident:str):
  with db() as c:r=c.execute('SELECT * FROM bills WHERE id=? AND guild=?',(ident.upper(),ctx.guild.id)).fetchone()
  if not r:return await ctx.reply('Bill not found in this server.',mention_author=False)
  cfg,_=self.taxes(ctx.guild.id);e=discord.Embed(title=f'✦ INVOICE {r["id"]}',description=f'Customer: <@{r["customer"]}>\nService: {r["description"]}\nSubtotal: {cfg["currency"]} {r["subtotal"]:,.2f}\nTax: {cfg["currency"]} {r["tax"]:,.2f}\n**Total: {cfg["currency"]} {r["total"]:,.2f}**\nStatus: **{r["status"]}**',color=PURPLE);await ctx.reply(embed=e,mention_author=False)
 @commands.command(name='billstatus')
 @commands.guild_only()
 @commands.has_guild_permissions(administrator=True)
 async def billstatus(self,ctx,ident:str,status:str):
  status=status.upper()
  if status not in {'UNPAID','PAID','CANCELLED','OVERDUE','REFUNDED'}:return await ctx.reply('Status: UNPAID, PAID, CANCELLED, OVERDUE, or REFUNDED.',mention_author=False)
  with db() as c:cur=c.execute('UPDATE bills SET status=? WHERE id=? AND guild=?',(status,ident.upper(),ctx.guild.id))
  await ctx.reply('Bill status updated.' if cur.rowcount else 'Bill not found.',mention_author=False)
 @commands.command(name='billhistory')
 @commands.guild_only()
 async def billhistory(self,ctx):
  with db() as c:rows=c.execute('SELECT id,customer,total,status FROM bills WHERE guild=? ORDER BY created DESC LIMIT 15',(ctx.guild.id,)).fetchall()
  e=discord.Embed(title='✦ KYŌKA • BILL HISTORY',description='\n'.join(f'`{r["id"]}` • <@{r["customer"]}> • **{r["total"]:,.2f}** • {r["status"]}' for r in rows) or 'No invoices yet.',color=PURPLE);await ctx.reply(embed=e,mention_author=False)
async def setup(bot): await bot.add_cog(Bills(bot))
