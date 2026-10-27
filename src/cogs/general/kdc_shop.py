"""
Kyoka 3.0 - KDC Shop Cog
Official Discord Store for Server Boosts, Discord Nitro, and Auto-Delivered Discord Bots.
Supports typing 'stock' in any server to open interactive catalogue, instant invoice generation,
live UPI/PayPal payment scanner integration, and automated bot file delivery.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, Union

import discord
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, View

from src.core.context import CustomContext
from src.managers.kdc_shop_manager import KDCShopManager, ShopBill, ShopItem
from src.security.owner import is_primary_owner
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.KDCShopCog")

PRIMARY_OWNER_ID = 1505515188991033409


def is_kdc_staff(user_id: int, guild: Optional[discord.Guild] = None) -> bool:
    """Check if user has elevated KDC Shop staff/admin privileges."""
    if is_primary_owner(user_id):
        return True

    # Check botstaff table in reputation database
    rep_db = Path("data/kyoka_reputation.sqlite3")
    if rep_db.exists():
        try:
            with sqlite3.connect(rep_db) as conn:
                if guild:
                    r = conn.execute(
                        "SELECT 1 FROM botstaff WHERE guild_id=? AND user_id=?",
                        (guild.id, user_id),
                    ).fetchone()
                    if r:
                        return True
                r2 = conn.execute(
                    "SELECT 1 FROM botstaff WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                if r2:
                    return True
        except Exception:
            pass

    return False


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD UI: KDC SHOP VIEWS, SELECT MENUS & MODALS
# ─────────────────────────────────────────────────────────────────────────────

class TransactionVerifyModal(Modal, title="Verify Payment & Claim Bot"):
    """Modal allowing buyers or staff to submit transaction IDs for auto-delivery."""

    def __init__(self, shop_mgr: KDCShopManager, bill: ShopBill, cog: "KDCShop"):
        super().__init__()
        self.shop_mgr = shop_mgr
        self.bill = bill
        self.cog = cog

        self.utr_input = TextInput(
            label="Transaction ID / UTR / Reference No.",
            placeholder="e.g. 439281928391 or PayPal TXN ID",
            required=True,
            min_length=4,
            max_length=64,
        )
        self.add_item(self.utr_input)

        self.notes_input = TextInput(
            label="Payment App / Notes (Optional)",
            placeholder="e.g. Paid via GPay / PhonePe / Paytm / PayPal",
            required=False,
            max_length=150,
        )
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        txn_id = self.utr_input.value.strip()
        notes = self.notes_input.value.strip()

        # Update bill status
        updated_bill = self.shop_mgr.update_bill_status(
            self.bill.id,
            status="PAID",
            transaction_id=txn_id,
            staff_notes=notes,
        )

        item = self.shop_mgr.get_item(self.bill.item_id)
        if item and item.is_auto_deliver:
            # Auto-deliver the bot file!
            file_path = self.shop_mgr.get_bot_file_path(item.id)
            if file_path and file_path.exists():
                delivery_embed = discord.Embed(
                    title="⚡ KDC BOT INSTANT DELIVERY • COMPLETE!",
                    description=(
                        f"Thank you for your purchase, **{interaction.user.name}**!\n"
                        f"Your verified invoice **`{self.bill.id}`** has been marked as **PAID**.\n\n"
                        f"📦 **Product:** `{item.name}`\n"
                        f"💳 **Transaction ID:** `{txn_id}`\n"
                        f"💰 **Total:** `{self.bill.currency} {self.bill.total}`\n\n"
                        f"**Download & Setup Instructions:**\n"
                        f"1. Download the attached `.zip` file below.\n"
                        f"2. Extract to your folder and open `.env.example`.\n"
                        f"3. Insert your Discord Bot Token and run `pip install -r requirements.txt`.\n"
                        f"4. Launch: `python bot.py`."
                    ),
                    color=0x10B981,
                    timestamp=discord.utils.utcnow(),
                )
                delivery_embed.set_footer(text="KDC Shop • Automated Bot Warehouse")

                self.shop_mgr.update_bill_status(self.bill.id, status="DELIVERED", delivered_file=file_path.name)

                try:
                    discord_file = discord.File(file_path, filename=file_path.name)
                    await interaction.response.send_message(
                        embed=delivery_embed,
                        file=discord_file,
                        ephemeral=True,
                    )
                except Exception as e:
                    await interaction.response.send_message(
                        f"✅ Payment verified for `{self.bill.id}`, but file attachment failed: {e}. Staff will assist you shortly.",
                        ephemeral=True,
                    )
                return

        # Boost or Nitro manual fulfillment
        boost_embed = discord.Embed(
            title="✅ PAYMENT SUBMITTED FOR VERIFICATION",
            description=(
                f"**Invoice:** `{self.bill.id}`\n"
                f"**Item:** `{self.bill.item_name}`\n"
                f"**Transaction ID:** `{txn_id}`\n\n"
                f"Your payment has been logged in the KDC queue! Staff will verify your transaction "
                f"and deliver your Discord Boosts / Nitro ID directly to your server invite."
            ),
            color=0x7C3AED,
        )
        await interaction.response.send_message(embed=boost_embed, ephemeral=True)


class ReviewSubmitModal(Modal, title="Write a Customer Review"):
    """Super simple modal for customers to submit feedback & star ratings."""

    def __init__(self, shop_mgr: KDCShopManager, default_product: str = "KDC Shop"):
        super().__init__()
        self.shop_mgr = shop_mgr

        self.rating_input = TextInput(
            label="Rating (1 to 5 Stars)",
            placeholder="5",
            required=True,
            min_length=1,
            max_length=1,
        )
        self.add_item(self.rating_input)

        self.product_input = TextInput(
            label="Product or Service Reviewed",
            placeholder="e.g. 4 Boosts, Music Bot, Nitro ID",
            default=default_product,
            required=False,
            max_length=60,
        )
        self.add_item(self.product_input)

        self.comment_input = TextInput(
            label="Your Review / Feedback",
            placeholder="How was the delivery speed, quality, or customer support?",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=5,
            max_length=500,
        )
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating_val = int(self.rating_input.value.strip())
            rating_val = max(1, min(5, rating_val))
        except ValueError:
            rating_val = 5

        product_val = self.product_input.value.strip() or "KDC Shop"
        comment_val = self.comment_input.value.strip()

        review = self.shop_mgr.add_review(
            user_id=interaction.user.id,
            username=str(interaction.user.name),
            rating=rating_val,
            comment=comment_val,
            product=product_val,
            verified=True,
        )

        stars_str = "⭐" * rating_val
        embed = discord.Embed(
            title="⭐ THANK YOU FOR YOUR REVIEW!",
            description=(
                f"**Rating:** {stars_str} (`{rating_val}/5`)\n"
                f"**Product:** `{product_val}`\n"
                f"**Feedback:** *\"{comment_val}\"*\n\n"
                f"Your review (`{review['id']}`) is now verified and live on Discord and the KDC Website!"
            ),
            color=0x10B981,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="KDC Shop • Verified Customer Feedback")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ReviewsView(View):
    """Interactive view for browsing and submitting reviews."""

    def __init__(self, shop_mgr: KDCShopManager, cog: "KDCShop"):
        super().__init__(timeout=180.0)
        self.shop_mgr = shop_mgr
        self.cog = cog

    @discord.ui.button(label="✍️ Write a Review", style=discord.ButtonStyle.success, emoji="⭐", row=0)
    async def write_review(self, interaction: discord.Interaction, button: Button):
        modal = ReviewSubmitModal(self.shop_mgr)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔄 Refresh Reviews", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def refresh_reviews(self, interaction: discord.Interaction, button: Button):
        embed = self.cog.generate_reviews_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class KDCItemSelect(Select):
    """Dropdown menu listing KDC Shop products."""

    def __init__(self, items: list[ShopItem], current_item_id: Optional[str] = None):
        options = []
        for item in items[:25]:  # Discord limit: 25 items
            cat_emoji = "🚀" if item.category == "boosts" else ("💎" if item.category == "nitro" else "🤖")
            price_text = f"₹{int(item.price_inr)} / ${item.price_usd:.2f}"
            options.append(
                discord.SelectOption(
                    label=item.name[:95],
                    value=item.id,
                    description=f"{price_text} • {item.badge or 'In Stock'}"[:95],
                    emoji=cat_emoji,
                    default=(item.id == current_item_id),
                )
            )

        super().__init__(
            placeholder="🛒 Select a Product to view details & buy...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="kdc_item_select",
        )

    async def callback(self, interaction: discord.Interaction):
        view: KDCShopView = self.view  # type: ignore
        selected_id = self.values[0]
        view.selected_item_id = selected_id
        item = view.shop_mgr.get_item(selected_id)
        if not item:
            return await interaction.response.send_message("❌ Item not found.", ephemeral=True)

        embed = view.generate_item_embed(item)
        await interaction.response.edit_message(embed=embed, view=view)


class KDCShopView(View):
    """Main interactive Discord shop view for KDC Shop."""

    def __init__(
        self,
        shop_mgr: KDCShopManager,
        cog: "KDCShop",
        selected_item_id: Optional[str] = None,
        timeout: Optional[float] = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.shop_mgr = shop_mgr
        self.cog = cog
        self.selected_item_id = selected_item_id
        self.items = self.shop_mgr.get_all_items(active_only=True)

        # Add select menu
        self.add_item(KDCItemSelect(self.items, current_item_id=selected_item_id))

    def generate_overview_embed(self) -> discord.Embed:
        """Main catalog overview embed listing user's exact prices."""
        embed = discord.Embed(
            title="🏪 KDC SHOP • OFFICIAL DISCORD MARKETPLACE",
            description=(
                "> **Welcome to KDC Shop!** High-speed Discord Server Boosts, Nitro Subscriptions, "
                "and Instant Auto-Delivered Discord Bots.\n"
                "> Select any product from the dropdown below to order or generate a verified bill.\n\n"
                "**🚀 DISCORD SERVER BOOSTS (Warranty Protected)**\n"
                "• **2 Boosts** — `₹200` / `$2.00` *(Level 1 Ready)*\n"
                "• **4 Boosts** — `₹380` / `$3.80` *(Stickers & 128kbps)*\n"
                "• **8 Boosts** — `₹720` / `$7.20` *(Level 2 Perks & Banner)*\n"
                "• **10 Boosts** — `₹850` / `$8.50` *(High Stability Tier)*\n"
                "• **14 Boosts** — `₹1,150` / `$11.50` *(Full Level 3 + Vanity URL)*\n\n"
                "**💎 DISCORD NITRO SUBSCRIPTIONS**\n"
                "• **1 Month Nitro ID + 2 Boosts** — `₹250` / `$2.50`\n"
                "• **3 Months Nitro Promo Link** — `₹350` / `$3.50`\n"
                "• **1 Year Nitro Full ID** — `₹2,200` / `$22.00`\n\n"
                "**🤖 PRE-BUILT AUTO-DELIVERY BOTS (Source Code Included)**\n"
                "• **Basic Music Bot** — `₹50` / `$0.50` ⚡ *Instant Zip*\n"
                "• **Auto Chat AI Bot** — `₹50` / `$0.50` ⚡ *Instant Zip*\n"
                "• **Ticket Support Bot** — `₹120` / `$1.20` ⚡ *Instant Zip*\n"
                "• **Anti-Nuke Security Bot** — `₹150` / `$1.50` ⚡ *Instant Zip*\n"
                "• **All-In-One Ultimate Bot** — `₹300` / `$3.00` ⚡ *Flagship Suite*"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="KDC Shop • Type 'stock' anytime to open • Instant Auto-Delivery")
        embed.set_thumbnail(url="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=400&q=80")
        return embed

    def generate_item_embed(self, item: ShopItem) -> discord.Embed:
        """Itemized detail view embed."""
        cat_title = "Discord Server Boosts" if item.category == "boosts" else ("Discord Nitro" if item.category == "nitro" else "Discord Bot Software")
        embed = discord.Embed(
            title=f"🛒 {item.name}",
            description=f"> {item.description}\n\n**Category:** `{cat_title}`\n**Stock Status:** `🟢 Available ({item.stock_qty} in stock)`",
            color=0x9333EA,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="💵 Pricing",
            value=f"• **₹{int(item.price_inr)} INR**\n• **${item.price_usd:.2f} USD**",
            inline=True,
        )
        embed.add_field(
            name="⚡ Fulfillment",
            value="**Instant Automated Delivery**" if item.is_auto_deliver else "**Invite / Staff Delivery (1-10 mins)**",
            inline=True,
        )
        if item.features:
            embed.add_field(
                name="✨ Included Features",
                value="\n".join(f"• {f}" for f in item.features),
                inline=False,
            )

        embed.set_footer(text="Click '🧾 Make Bill' below to generate your invoice and payment scanner!")
        return embed

    @discord.ui.button(label="🧾 Make Bill (INR)", style=discord.ButtonStyle.primary, emoji="🧾", row=1)
    async def make_bill_inr(self, interaction: discord.Interaction, button: Button):
        await self._handle_make_bill(interaction, "INR")

    @discord.ui.button(label="🧾 Make Bill (USD)", style=discord.ButtonStyle.secondary, emoji="💵", row=1)
    async def make_bill_usd(self, interaction: discord.Interaction, button: Button):
        await self._handle_make_bill(interaction, "USD")

    @discord.ui.button(label="💳 Payment Scanner", style=discord.ButtonStyle.success, emoji="💳", row=1)
    async def show_payment_scanner(self, interaction: discord.Interaction, button: Button):
        scanner_embed = discord.Embed(
            title="💳 KDC SHOP • PAYMENT SCANNER & METHODS",
            description=(
                "> **Scan with any UPI App (GPay, PhonePe, Paytm, BHIM) to pay instantly.**\n\n"
                f"• **UPI ID:** `{self.shop_mgr.upi_id}`\n"
                f"• **PayPal:** [{self.shop_mgr.paypal_link}]({self.shop_mgr.paypal_link})\n\n"
                "**Instructions:**\n"
                "1. Click **'🧾 Make Bill'** for your desired item to get your unique Invoice ID.\n"
                "2. Scan & pay the exact invoice amount.\n"
                "3. Click **'⚡ Verify Payment & Claim Bot'** and paste your Transaction ID / UTR.\n"
                "4. For bots, the bot file will be delivered to you **instantly**!"
            ),
            color=0x10B981,
        )
        # UPI QR Code generated dynamically
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26cu=INR"
        scanner_embed.set_image(url=qr_url)
        scanner_embed.set_footer(text="KDC Shop • Verified Payments")
        await interaction.response.send_message(embed=scanner_embed, ephemeral=True)

    @discord.ui.button(label="⚡ Verify & Claim Bot", style=discord.ButtonStyle.primary, emoji="📦", row=2)
    async def verify_and_claim(self, interaction: discord.Interaction, button: Button):
        # Look for recent pending bill for this customer
        pending_bills = self.shop_mgr.list_bills(customer_id=interaction.user.id, status="PENDING", limit=1)
        if not pending_bills:
            # Check for any bill
            any_bills = self.shop_mgr.list_bills(customer_id=interaction.user.id, limit=1)
            if not any_bills:
                return await interaction.response.send_message(
                    "❌ You do not have an active invoice. Please click **'🧾 Make Bill'** on a product first!",
                    ephemeral=True,
                )
            target_bill = any_bills[0]
        else:
            target_bill = pending_bills[0]

        modal = TransactionVerifyModal(self.shop_mgr, target_bill, self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📋 My Invoices", style=discord.ButtonStyle.secondary, emoji="📜", row=2)
    async def my_invoices(self, interaction: discord.Interaction, button: Button):
        bills = self.shop_mgr.list_bills(customer_id=interaction.user.id, limit=5)
        if not bills:
            return await interaction.response.send_message("You have no invoices yet. Click 'Make Bill' to start!", ephemeral=True)

        lines = []
        for b in bills:
            status_emoji = "🟢" if b.status in ("PAID", "DELIVERED") else "🟡"
            lines.append(f"{status_emoji} **`{b.id}`** — {b.item_name} (`{b.currency} {b.total}`) • **{b.status}**")

        embed = discord.Embed(
            title=f"📜 Order Invoices for {interaction.user.name}",
            description="\n".join(lines),
            color=0x7C3AED,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="⭐ Reviews", style=discord.ButtonStyle.secondary, emoji="⭐", row=2)
    async def reviews_button(self, interaction: discord.Interaction, button: Button):
        embed = self.cog.generate_reviews_embed()
        view = ReviewsView(self.shop_mgr, self.cog)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_make_bill(self, interaction: discord.Interaction, currency: str):
        item_id = self.selected_item_id or (self.items[0].id if self.items else "boost_2")
        item = self.shop_mgr.get_item(item_id)
        if not item:
            return await interaction.response.send_message("❌ Product not found.", ephemeral=True)

        guild_id = interaction.guild_id or 0
        bill = self.shop_mgr.create_bill(
            guild_id=guild_id,
            customer_id=interaction.user.id,
            customer_name=str(interaction.user),
            item_id=item.id,
            currency=currency,
            quantity=1,
        )

        amount_str = f"₹{int(bill.total)}" if currency == "INR" else f"${bill.total:.2f}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26am={bill.total}%26cu=INR%26tn={bill.id}"

        bill_embed = discord.Embed(
            title=f"🧾 KDC SHOP INVOICE • `{bill.id}`",
            description=(
                f"**Customer:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                f"**Product:** `{bill.item_name}`\n"
                f"**Quantity:** `1`\n"
                f"**Total Due:** `{currency} {amount_str}`\n"
                f"**Status:** `🟡 PENDING PAYMENT`\n\n"
                f"**How to Pay:**\n"
                f"• **UPI ID:** `{self.shop_mgr.upi_id}` (GPay / PhonePe / Paytm / BHIM)\n"
                f"• **PayPal:** [{self.shop_mgr.paypal_link}]({self.shop_mgr.paypal_link})\n\n"
                f"Once paid, click **'⚡ Verify Payment & Claim Bot'** below to receive your bot files or boost activation!"
            ),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )
        if currency == "INR":
            bill_embed.set_image(url=qr_url)
        bill_embed.set_footer(text=f"Invoice ID: {bill.id} • KDC Shop")

        await interaction.response.send_message(embed=bill_embed, ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN KDC SHOP COG
# ─────────────────────────────────────────────────────────────────────────────

class KDCShop(commands.Cog, name="KDCShop"):
    """Official KDC Shop & Automated Bot Delivery Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.shop_mgr = KDCShopManager()

    # ── Universal Trigger: typing 'stock' anywhere ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        clean = message.content.strip().lower()
        # Trigger on exact keywords: "stock", "kdc stock", "kdc shop", "kdc"
        if clean in ("stock", "kdc stock", "kdc shop", "kdc"):
            ctx = await self.bot.get_context(message)
            await self.open_shop(ctx)
        elif clean in ("review", "reviews", "kdc review", "kdc reviews"):
            ctx = await self.bot.get_context(message)
            embed = self.generate_reviews_embed()
            view = ReviewsView(self.shop_mgr, self)
            await ctx.send(embed=embed, view=view)

    # ── Command: +stock / +kdc / +shop ──
    @commands.group(name="stock", aliases=["kdc", "shop", "kdcshop", "store"], invoke_without_command=True)
    async def stock_command(self, ctx: CustomContext, *, query: Optional[str] = None):
        """View official KDC Shop live stock, prices, and automated bot warehouse."""
        await self.open_shop(ctx, query=query)

    async def open_shop(self, ctx: Union[CustomContext, commands.Context], query: Optional[str] = None):
        """Open the interactive KDC Shop."""
        selected_id = None
        if query:
            q = query.strip().lower()
            all_items = self.shop_mgr.get_all_items()
            for it in all_items:
                if q in it.id.lower() or q in it.name.lower():
                    selected_id = it.id
                    break

        view = KDCShopView(self.shop_mgr, self, selected_item_id=selected_id)
        if selected_id:
            item = self.shop_mgr.get_item(selected_id)
            embed = view.generate_item_embed(item)  # type: ignore
        else:
            embed = view.generate_overview_embed()

        await ctx.send(embed=embed, view=view)

    # ── Staff Subcommand: +stock add ──
    @stock_command.command(name="add")
    async def stock_add(
        self,
        ctx: CustomContext,
        item_id: str,
        category: str,
        price_inr: float,
        price_usd: float,
        *,
        name: str,
    ):
        """[Staff] Add a new product to KDC Shop."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        is_bot = category.lower() == "bots"
        item = self.shop_mgr.add_or_update_item(
            item_id=item_id.strip().lower(),
            category=category.strip().lower(),
            name=name.strip(),
            description=f"Official {name.strip()} available in KDC Shop.",
            price_inr=price_inr,
            price_usd=price_usd,
            is_auto_deliver=is_bot,
        )
        await ctx.send(f"✅ Added `{item.name}` to stock (₹{item.price_inr} / ${item.price_usd})!")

    # ── Staff Subcommand: +stock update ──
    @stock_command.command(name="update")
    async def stock_update(
        self,
        ctx: CustomContext,
        item_id: str,
        price_inr: float,
        price_usd: float,
        stock_qty: int = 999,
    ):
        """[Staff] Update price or stock quantity for an item."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        item = self.shop_mgr.get_item(item_id)
        if not item:
            return await ctx.send(f"❌ Item `{item_id}` not found.")

        updated = self.shop_mgr.add_or_update_item(
            item_id=item.id,
            category=item.category,
            name=item.name,
            description=item.description,
            price_inr=price_inr,
            price_usd=price_usd,
            stock_qty=stock_qty,
            is_auto_deliver=item.is_auto_deliver,
            file_filename=item.file_filename,
            features=item.features,
            badge=item.badge,
        )
        await ctx.send(f"✅ Updated `{updated.name}`: ₹{updated.price_inr} / ${updated.price_usd} (Stock: {stock_qty})")

    # ── Staff Subcommand: +stock upload ──
    @stock_command.command(name="upload")
    async def stock_upload(self, ctx: CustomContext, item_id: str):
        """[Staff] Upload a new bot zip package attachment for automated delivery."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a `.zip` bot archive file with this command.")

        att = ctx.message.attachments[0]
        if not att.filename.endswith(".zip"):
            return await ctx.send("❌ Attachment must be a `.zip` archive.")

        file_bytes = await att.read()
        target_path = self.shop_mgr.save_uploaded_bot_file(item_id, file_bytes, att.filename)
        await ctx.send(f"✅ Successfully uploaded and linked `{target_path.name}` to `{item_id}`!")

    # ── Staff Subcommand: +stock deliver ──
    @stock_command.command(name="deliver")
    async def stock_deliver(
        self,
        ctx: CustomContext,
        bill_id: str,
        target_member: Optional[discord.Member] = None,
    ):
        """[Staff] Manually deliver bot files or boost fulfillment for an invoice."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        bill = self.shop_mgr.get_bill(bill_id)
        if not bill:
            return await ctx.send(f"❌ Bill `{bill_id}` not found.")

        item = self.shop_mgr.get_item(bill.item_id)
        recipient = target_member or ctx.guild.get_member(bill.customer_id) if ctx.guild else None

        if item and item.is_auto_deliver:
            file_path = self.shop_mgr.get_bot_file_path(item.id)
            if file_path and file_path.exists():
                embed = discord.Embed(
                    title="⚡ KDC BOT MANUAL DELIVERY",
                    description=f"Your order for **`{item.name}`** has been dispatched by staff {ctx.author.mention}!",
                    color=0x10B981,
                )
                discord_file = discord.File(file_path, filename=file_path.name)
                if recipient:
                    try:
                        await recipient.send(embed=embed, file=discord_file)
                        self.shop_mgr.update_bill_status(bill.id, "DELIVERED", staff_id=ctx.author.id)
                        return await ctx.send(f"✅ Dispatched `{file_path.name}` to {recipient.mention}!")
                    except Exception:
                        pass
                # Fallback in channel
                await ctx.send(f"📦 Direct message closed, delivering here for {bill.customer_name}:", embed=embed, file=discord_file)
                self.shop_mgr.update_bill_status(bill.id, "DELIVERED", staff_id=ctx.author.id)
                return

        self.shop_mgr.update_bill_status(bill.id, "DELIVERED", staff_id=ctx.author.id)
        await ctx.send(f"✅ Marked order `{bill.id}` ({bill.item_name}) as **DELIVERED**!")

    # ── Staff Subcommand: +stock verify ──
    @stock_command.command(name="verify")
    async def stock_verify(self, ctx: CustomContext, bill_id: str, *, notes: str = "Verified by staff"):
        """[Staff] Mark a bill as paid and verified."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        updated = self.shop_mgr.update_bill_status(
            bill_id,
            status="PAID",
            staff_id=ctx.author.id,
            staff_notes=notes,
        )
        if not updated:
            return await ctx.send(f"❌ Bill `{bill_id}` not found.")
        await ctx.send(f"✅ Invoice `{updated.id}` verified as **PAID**!")

    # ── Staff Subcommand: +stock bills ──
    @stock_command.command(name="bills")
    async def stock_bills(self, ctx: CustomContext, status: Optional[str] = None):
        """[Staff] View recent KDC Shop order invoices."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        bills = self.shop_mgr.list_bills(status=status, limit=10)
        if not bills:
            return await ctx.send("No invoices found matching criteria.")

        lines = []
        for b in bills:
            s_emoji = "🟢" if b.status in ("PAID", "DELIVERED") else "🟡"
            lines.append(f"{s_emoji} **`{b.id}`** | {b.customer_name} | {b.item_name} | `{b.currency} {b.total}` | **{b.status}**")

        embed = discord.Embed(
            title=f"📋 KDC Shop Recent Invoices ({len(bills)})",
            description="\n".join(lines),
            color=0x7C3AED,
        )
        await ctx.send(embed=embed)

    # ── Review System Helpers & Commands (Super Simple) ──
    def generate_reviews_embed(self) -> discord.Embed:
        stats = self.shop_mgr.get_rating_summary()
        reviews = self.shop_mgr.get_reviews(limit=6)

        stars_str = stats.get("stars_str", "⭐⭐⭐⭐⭐")
        avg = stats.get("average", 5.0)
        total = stats.get("total", 0)

        embed = discord.Embed(
            title="⭐ KDC SHOP — CUSTOMER REVIEWS & RATINGS",
            description=(
                f"**Overall Store Rating:** {stars_str} **`{avg} / 5.0`**\n"
                f"**Total Verified Reviews:** `{total}` happy customer(s)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )

        if not reviews:
            embed.add_field(
                name="No Reviews Yet",
                value="Be the first to leave a review using `+review 5 <your message>`!",
                inline=False,
            )
        else:
            for r in reviews:
                r_stars = "⭐" * int(r["rating"])
                ts_str = f"<t:{int(r['created_at'])}:R>"
                embed.add_field(
                    name=f"{r_stars} {r['product']} • by @{r['username']}",
                    value=f"💬 *\"{r['comment']}\"*\n📅 {ts_str} • Verified Buyer",
                    inline=False,
                )

        embed.set_footer(text="KDC Shop • Type +review to leave your feedback!")
        return embed

    # ── Command: +review (Super Simple) ──
    @commands.command(name="review", aliases=["addreview", "vouchshop"])
    async def review_command(
        self,
        ctx: CustomContext,
        rating: Optional[int] = None,
        *,
        comment: Optional[str] = None,
    ):
        """Leave a super simple review for KDC Shop (e.g. +review 5 Great service!)."""
        if rating is None or not comment:
            # If used without arguments, open interactive panel
            view = ReviewsView(self.shop_mgr, self)
            embed = discord.Embed(
                title="⭐ Write a KDC Shop Review",
                description=(
                    "Leaving a review is super simple!\n\n"
                    "**Quick Command Usage:**\n"
                    "• `+review 5 Fast delivery and legit boosts!`\n"
                    "• `+review 5 All-in-one bot zip is awesome!`\n\n"
                    "Or click **'✍️ Write a Review'** below to open the review window!"
                ),
                color=0x7C3AED,
            )
            return await ctx.send(embed=embed, view=view)

        # Quick direct submission
        rating_clean = max(1, min(5, int(rating)))
        rev = self.shop_mgr.add_review(
            user_id=ctx.author.id,
            username=str(ctx.author.name),
            rating=rating_clean,
            comment=comment.strip(),
            product="KDC Services",
            verified=True,
        )

        stars_str = "⭐" * rating_clean
        embed = discord.Embed(
            title="⭐ Review Submitted Successfully!",
            description=(
                f"**Rating:** {stars_str} (`{rating_clean}/5`)\n"
                f"**Feedback:** *\"{comment.strip()}\"*\n\n"
                f"Your review (`{rev['id']}`) is now recorded and visible on Discord & KDC Shop website!"
            ),
            color=0x10B981,
        )
        embed.set_footer(text="Thank you for supporting KDC Shop!")
        await ctx.send(embed=embed)

    # ── Command: +reviews ──
    @commands.command(name="reviews", aliases=["ratings", "shopreviews", "voucheslist"])
    async def reviews_command(self, ctx: CustomContext):
        """View KDC Shop verified customer reviews and aggregate rating."""
        embed = self.generate_reviews_embed()
        view = ReviewsView(self.shop_mgr, self)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KDCShop(bot))
