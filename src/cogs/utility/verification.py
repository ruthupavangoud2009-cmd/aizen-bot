"""Simple persistent button-based member verification for KYOKA."""
from __future__ import annotations
import logging
import discord
from discord.ext import commands
from src.core.bot import KyokaBot
from src.core.context import CustomContext

logger = logging.getLogger("Kyoka.Verification")

class VerifyButton(discord.ui.View):
    def __init__(self, bot: KyokaBot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="kyoka:verify:member")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Verification is available inside a server only.", ephemeral=True)
            return
        try:
            row = await self.bot.db.fetch_one(
                "SELECT role_id FROM kyoka_verification_settings WHERE guild_id = $1;", interaction.guild.id
            )
        except Exception:
            logger.exception("Unable to read verification settings for guild %s", interaction.guild.id)
            await interaction.response.send_message("Verification is temporarily unavailable. Please contact a server moderator.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(row["role_id"])) if row and row.get("role_id") else None
        if role is None:
            await interaction.response.send_message("The verification role is missing or not configured. Please contact a server moderator.", ephemeral=True)
            return
        member = interaction.user
        if role in member.roles:
            await interaction.response.send_message("You are already verified. Welcome!", ephemeral=True)
            return
        me = interaction.guild.me
        if not me or not me.guild_permissions.manage_roles or me.top_role <= role:
            await interaction.response.send_message("The server needs to give KYOKA Manage Roles and move its role above the verification role.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="Member completed KYOKA button verification")
            await interaction.response.send_message("✅ Verification complete. Welcome to the server!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("I cannot assign the verification role. Check my Manage Roles permission and role position.", ephemeral=True)
        except discord.HTTPException:
            logger.exception("Verification role assignment failed in guild %s", interaction.guild.id)
            await interaction.response.send_message("Discord could not complete verification. Please try again in a moment.", ephemeral=True)

class Verification(commands.Cog):
    def __init__(self, bot: KyokaBot):
        self.bot = bot
        self.verify_view = VerifyButton(bot)

    async def cog_load(self) -> None:
        try:
            await self.bot.db.execute("""
                CREATE TABLE IF NOT EXISTS kyoka_verification_settings (
                    guild_id BIGINT PRIMARY KEY,
                    role_id BIGINT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.bot.add_view(self.verify_view)
        except Exception:
            logger.exception("Could not initialize verification system")

    @commands.hybrid_group(name="verify", invoke_without_command=True, description="Configure or use KYOKA member verification")
    async def verify(self, ctx: CustomContext) -> None:
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        await ctx.send("Use `/verify setup` to create a verification panel, or `"+prefix+"verify setup @role` with a role mention.")

    @verify.command(name="setup", description="Create a verification panel and configure its verified role")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_setup(self, ctx: CustomContext, role: discord.Role) -> None:
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return
        me = ctx.guild.me
        if not me or not me.guild_permissions.manage_roles:
            await ctx.send("Please grant KYOKA the **Manage Roles** permission first.")
            return
        if role.is_default() or role.managed or me.top_role <= role:
            await ctx.send("Choose a normal verification role positioned **below KYOKA's highest role**.")
            return
        try:
            await self.bot.db.execute("""
                INSERT INTO kyoka_verification_settings (guild_id, role_id, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_id) DO UPDATE SET role_id = EXCLUDED.role_id, updated_at = CURRENT_TIMESTAMP;
            """, ctx.guild.id, role.id)
        except Exception:
            logger.exception("Could not save verification settings for guild %s", ctx.guild.id)
            await ctx.send("Could not save verification settings. Check the database connection and try again.")
            return
        embed = discord.Embed(
            title="⟡  KYOKA • Server Verification",
            description=(
                "## Enter the realm\n"
                "Press the button below to verify and receive access to the server.\n\n"
                "🛡️ **Secure access**\n"
                "• One click to receive the verified role.\n"
                "• If the button fails, contact a server moderator.\n\n"
                "**Powered by KYOKA — Made by Aizen**"
            ), color=discord.Color.from_rgb(100, 55, 180)
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Only press Verify Me if you agree to follow this server's rules.")
        try:
            await ctx.send(embed=embed, view=self.verify_view)
        except discord.HTTPException:
            logger.exception("Could not post verification panel")
            await ctx.send("Settings were saved, but I could not post the panel. Check Send Messages and Embed Links permissions.")

async def setup(bot: KyokaBot) -> None:
    await bot.add_cog(Verification(bot))
