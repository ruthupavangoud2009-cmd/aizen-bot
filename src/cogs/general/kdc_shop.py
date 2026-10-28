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
from src.security.owner import is_owner_or_staff, is_primary_owner
from src.ui.theme import KyokaTheme

logger = logging.getLogger("Kyoka.KDCShopCog")

PRIMARY_OWNER_ID = 1505515188991033409


def is_kdc_staff(user_id: int, guild: Optional[discord.Guild] = None) -> bool:
    """Check if user has elevated KDC Shop staff/admin privileges."""
    if is_owner_or_staff(user_id):
        return True

    if guild:
        member = guild.get_member(user_id)
        if member:
            perms = member.guild_permissions
            if perms.administrator or perms.manage_guild or perms.manage_messages:
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

class StaffRejectModal(Modal, title="Reject Order Payment"):
    """Modal for staff to specify why a payment was rejected."""

    def __init__(self, cog: "KDCShop", bill_id: str, review_view: "StaffOrderReviewView"):
        super().__init__()
        self.cog = cog
        self.bill_id = bill_id
        self.review_view = review_view

        self.reason_input = TextInput(
            label="Rejection Reason",
            placeholder="e.g. Invalid UTR / Payment not received / Fruit trade cancelled",
            required=True,
            max_length=200,
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip()
        bill = self.cog.shop_mgr.update_bill_status(
            self.bill_id,
            status="REJECTED",
            staff_id=interaction.user.id,
            staff_notes=f"Rejected by {interaction.user.name}: {reason}",
        )
        if not bill:
            return await interaction.response.send_message("❌ Bill not found.", ephemeral=True)

        for child in self.review_view.children:
            if isinstance(child, Button):
                child.disabled = True

        rejection_embed = discord.Embed(
            title="❌ PAYMENT REJECTED BY STAFF",
            description=(
                f"• **Invoice:** `{bill.id}`\n"
                f"• **Customer:** <@{bill.customer_id}>\n"
                f"• **Product:** `{bill.item_name}`\n"
                f"• **Rejected By:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                f"• **Reason:** `{reason}`\n\n"
                f"The customer may re-verify or contact staff if this was a mistake."
            ),
            color=0xEF4444,
            timestamp=discord.utils.utcnow(),
        )
        rejection_embed.set_footer(text=f"Kyoka Shop • Staff Action • ID: {interaction.user.id}")

        try:
            if interaction.message:
                await interaction.message.edit(embed=rejection_embed, view=self.review_view)
        except Exception:
            pass

        await interaction.response.send_message(f"✅ Order `{bill.id}` marked as **REJECTED**.", ephemeral=True)


class StaffOrderReviewView(View):
    """Interactive view for staff to confirm & auto-deliver or reject customer payments."""

    def __init__(self, cog: "KDCShop", bill_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.bill_id = bill_id

    @discord.ui.button(
        label="Confirm & Auto-Deliver",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="kdc_staff_confirm_delivery_btn",
    )
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        if not is_kdc_staff(interaction.user.id, interaction.guild):
            return await interaction.response.send_message(
                "❌ **Unauthorized:** Only verified Bot Staff or Administrators can confirm payments.",
                ephemeral=True,
            )

        await interaction.response.defer()
        await self.cog.deliver_order(
            bill_id=self.bill_id,
            staff_user=interaction.user,
            channel=interaction.channel,
            origin_interaction=interaction,
            view_to_disable=self,
        )

    @discord.ui.button(
        label="Reject Payment",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="kdc_staff_reject_delivery_btn",
    )
    async def reject_btn(self, interaction: discord.Interaction, button: Button):
        if not is_kdc_staff(interaction.user.id, interaction.guild):
            return await interaction.response.send_message(
                "❌ **Unauthorized:** Only verified Bot Staff or Administrators can reject payments.",
                ephemeral=True,
            )

        modal = StaffRejectModal(self.cog, self.bill_id, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Order Details",
        style=discord.ButtonStyle.secondary,
        emoji="📋",
        custom_id="kdc_staff_order_details_btn",
    )
    async def details_btn(self, interaction: discord.Interaction, button: Button):
        bill = self.cog.shop_mgr.get_bill(self.bill_id)
        if not bill:
            return await interaction.response.send_message("❌ Bill not found.", ephemeral=True)

        embed = discord.Embed(
            title=f"📋 Order Details • `{bill.id}`",
            description=(
                f"• **Customer:** `{bill.customer_name}` (<@{bill.customer_id}>)\n"
                f"• **Customer ID:** `{bill.customer_id}`\n"
                f"• **Product:** `{bill.item_name}` (`{bill.item_id}`)\n"
                f"• **Amount:** `{bill.currency} {bill.total}`\n"
                f"• **Status:** `{bill.status}`\n"
                f"• **Transaction ID / UTR:** `{bill.transaction_id or 'None'}`\n"
                f"• **Staff Notes:** `{bill.staff_notes or 'None'}`\n"
                f"• **Created:** <t:{int(bill.created_at)}:F>\n"
                f"• **Updated:** <t:{int(bill.updated_at)}:R>"
            ),
            color=0x7C3AED,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TransactionVerifyModal(Modal, title="Verify Payment Proof"):
    """Modal allowing buyers to submit transaction IDs for staff verification."""

    def __init__(self, shop_mgr: KDCShopManager, bill: ShopBill, cog: "KDCShop"):
        super().__init__()
        self.shop_mgr = shop_mgr
        self.bill = bill
        self.cog = cog

        self.utr_input = TextInput(
            label="Transaction ID / UTR / Reference No.",
            placeholder="e.g. 439281928391 or Blox Fruit Trade details",
            required=True,
            min_length=4,
            max_length=64,
        )
        self.add_item(self.utr_input)

        self.notes_input = TextInput(
            label="Payment App / Notes (Optional)",
            placeholder="e.g. Paid via GPay / PhonePe / Paytm / Roblox Trade",
            required=False,
            max_length=150,
        )
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        txn_id = self.utr_input.value.strip()
        notes = self.notes_input.value.strip()

        # Update bill status to VERIFYING (requires staff verification before auto-delivery!)
        updated_bill = self.shop_mgr.update_bill_status(
            self.bill.id,
            status="VERIFYING",
            transaction_id=txn_id,
            staff_notes=notes,
        )
        if not updated_bill:
            return await interaction.response.send_message("❌ Error updating invoice.", ephemeral=True)

        # Ephemeral receipt for the customer
        customer_embed = discord.Embed(
            title="⚡ PAYMENT SUBMITTED • AWAITING STAFF APPROVAL",
            description=(
                f"Thank you, **{interaction.user.name}**! Your payment proof has been queued for verification.\n\n"
                f"🧾 **Invoice ID:** `{self.bill.id}`\n"
                f"📦 **Product:** `{self.bill.item_name}`\n"
                f"💳 **Submitted Ref / UTR:** `{txn_id}`\n"
                f"💰 **Total:** `{self.bill.currency} {self.bill.total}`\n"
                f"📝 **Notes:** `{notes or 'None'}`\n\n"
                f"🛡️ **Security Protocol:** To protect store integrity, digital bot packages and server boosts "
                f"are dispatched automatically once a staff member confirms payment receipt. "
                f"You will receive your delivery directly in your DMs and unsealed in this ticket channel!"
            ),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )
        customer_embed.set_footer(text="Kyoka Sovereign Vault • Verification Pending • Staff Confirmation Required")
        await interaction.response.send_message(embed=customer_embed, ephemeral=True)

        # Send Staff Review Action Card into the channel
        staff_card = discord.Embed(
            title="🛡️ [STAFF ACTION REQUIRED] VERIFY PAYMENT & DISPATCH",
            description=(
                f"A customer has submitted payment verification proof!\n\n"
                f"👤 **Customer:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                f"🆔 **Customer ID:** `{interaction.user.id}`\n"
                f"🧾 **Invoice ID:** `{self.bill.id}`\n"
                f"📦 **Product:** `{self.bill.item_name}` (`{self.bill.item_id}`)\n"
                f"💰 **Total Due:** `{self.bill.currency} {self.bill.total}`\n"
                f"💳 **Submitted Ref / UTR:** `{txn_id}`\n"
                f"📝 **Notes / App:** `{notes or 'None'}`\n\n"
                f"**Staff Actions:**\n"
                f"• Click **'Confirm & Auto-Deliver'** to confirm payment and dispatch product files/boosts instantly.\n"
                f"• Click **'Reject Payment'** if the UTR is fake, unpaid, or invalid."
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        staff_card.set_footer(text=f"Kyoka Shop • Invoice #{self.bill.id} • Awaiting Staff Approval")
        review_view = StaffOrderReviewView(self.cog, self.bill.id)
        if interaction.channel and hasattr(interaction.channel, "send"):
            try:
                await interaction.channel.send(
                    content=f"🔔 **Staff Verification Alert:** New payment submitted for order `{self.bill.id}` by {interaction.user.mention}!",
                    embed=staff_card,
                    view=review_view,
                )
            except Exception as e:
                logger.warning(f"Could not send staff review card to channel: {e}")


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
                "> 💳 **Payment:** Scan official UPI QR (**₹ INR**). ❌ *USD payments are currently unavailable.*\n"
                "> Select any product from the dropdown below to order or generate a verified bill.\n\n"
                "**🚀 DISCORD SERVER BOOSTS (Warranty Protected)**\n"
                "• **2 Boosts** — `₹200` *(~$2.00 USD - Unavailable)*\n"
                "• **4 Boosts** — `₹380` *(~$3.80 USD - Unavailable)*\n"
                "• **8 Boosts** — `₹720` *(~$7.20 USD - Unavailable)*\n"
                "• **10 Boosts** — `₹850` *(~$8.50 USD - Unavailable)*\n"
                "• **14 Boosts** — `₹1,150` *(~$11.50 USD - Unavailable)*\n\n"
                "**💎 DISCORD NITRO SUBSCRIPTIONS**\n"
                "• **1 Month Nitro ID + 2 Boosts** — `₹250` *(~$2.50 USD - Unavailable)*\n"
                "• **1 Year Nitro Full ID** — `₹2,200` *(~$22.00 USD - Unavailable)*\n\n"
                "**🤖 PRE-BUILT AUTO-DELIVERY BOTS (Source Code Included)**\n"
                "• **Basic Music Bot** — `₹50` ⚡ *Instant Zip*\n"
                "• **Auto Chat AI Bot** — `₹50` ⚡ *Instant Zip*\n"
                "• **Ticket Support Bot** — `₹120` ⚡ *Instant Zip*\n"
                "• **Anti-Nuke Security Bot** — `₹150` ⚡ *Instant Zip*\n"
                "• **All-In-One Ultimate Bot** — `₹300` ⚡ *Flagship Suite*\n\n"
                "**🍎 ACCEPTED PAYMENT METHODS**\n"
                "• **₹ INR UPI QR Scanner** (GPay, PhonePe, Paytm, BHIM, FamPay)\n"
                "• **🍎 Blox Fruits In-Game Trade** (Kitsune, Dragon, Leopard, Dough, T-Rex, Buddha, etc.)\n"
                "• *❌ USD payments are currently unavailable.*"
            ),
            color=0x7C3AED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="KDC Shop • Type 'stock' or 'scanner' anytime • UPI & Blox Fruits Accepted")
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
            value=f"• **₹{int(item.price_inr)} INR** *(Scan to Pay)*\n• ~~${item.price_usd:.2f} USD~~ *(❌ Unavailable)*",
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

        embed.set_footer(text="Click '🧾 Make Bill (INR)' below to generate your invoice and payment scanner!")
        return embed

    @discord.ui.button(label="🧾 Make Bill (INR)", style=discord.ButtonStyle.primary, emoji="🧾", row=1)
    async def make_bill_inr(self, interaction: discord.Interaction, button: Button):
        await self._handle_make_bill(interaction, "INR")

    @discord.ui.button(label="🍎 Pay with Fruits", style=discord.ButtonStyle.secondary, emoji="🍎", row=1)
    async def make_bill_fruit(self, interaction: discord.Interaction, button: Button):
        await self._handle_make_bill(interaction, "FRUIT")

    @discord.ui.button(label="💳 Payment Scanner", style=discord.ButtonStyle.success, emoji="💳", row=1)
    async def show_payment_scanner(self, interaction: discord.Interaction, button: Button):
        scanner_embed = discord.Embed(
            title="💳 KDC SHOP • OFFICIAL UPI PAYMENT SCANNER",
            description=(
                "> **Scan the QR code below with any UPI App (GPay, PhonePe, Paytm, BHIM, FamPay) to pay.**\n\n"
                "• **Payment Method:** `₹ INR (UPI Scanner Only)`\n"
                "• **Blox Fruits:** Click **'🍎 Pay with Fruits'** to pay in-game via trade!\n"
                "• **USD / International:** `❌ Temporarily Unavailable`\n\n"
                "**Payment & Auto-Delivery Steps:**\n"
                "1. Click **'🧾 Make Bill (INR)'** on your selected item to generate your Invoice ID.\n"
                "2. Scan this QR code and pay the exact amount.\n"
                "3. Click **'⚡ Verify Payment & Claim Bot'** and enter your Transaction ID (UTR).\n"
                "4. For bots, your zip package will be delivered **instantly**!"
            ),
            color=0x10B981,
            timestamp=discord.utils.utcnow(),
        )
        scanner_embed.set_footer(text="KDC Shop • Official UPI Scanner • USD Unavailable")

        qr_file_path = Path("assets/kdc_payment_qr.png")
        if qr_file_path.exists():
            file = discord.File(qr_file_path, filename="kdc_payment_qr.png")
            scanner_embed.set_image(url="attachment://kdc_payment_qr.png")
            await interaction.response.send_message(embed=scanner_embed, file=file, ephemeral=True)
        else:
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26cu=INR"
            scanner_embed.set_image(url=qr_url)
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
                    "❌ You do not have an active invoice. Please click **'🧾 Make Bill (INR)'** or **'🍎 Pay with Fruits'** on a product first!",
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
        if currency.upper() == "USD":
            embed = discord.Embed(
                title="❌ USD PAYMENTS TEMPORARILY UNAVAILABLE",
                description=(
                    "**USD Payments are currently unavailable.**\n\n"
                    "Please select **'🧾 Make Bill (INR)'** to pay via UPI QR, or **'🍎 Pay with Fruits'** to pay using in-game Blox Fruits.\n\n"
                    "For manual international payments, contact staff."
                ),
                color=0xEF4444,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="KDC Shop • USD Unavailable • Please pay in INR or Blox Fruits")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        item_id = self.selected_item_id or (self.items[0].id if self.items else "boost_2")
        item = self.shop_mgr.get_item(item_id)
        if not item:
            return await interaction.response.send_message("❌ Product not found.", ephemeral=True)

        guild_id = interaction.guild_id or 0

        if currency.upper() == "FRUIT":
            bill = self.shop_mgr.create_bill(
                guild_id=guild_id,
                customer_id=interaction.user.id,
                customer_name=str(interaction.user),
                item_id=item.id,
                currency="FRUIT",
                quantity=1,
            )
            bill_embed = discord.Embed(
                title=f"🍎 KDC SHOP BLOX FRUITS INVOICE • `{bill.id}`",
                description=(
                    f"**Customer:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                    f"**Product:** `{bill.item_name}`\n"
                    f"**Payment Method:** `🍎 Blox Fruits In-Game Trade`\n"
                    f"**Invoice Status:** `🟡 AWAITING IN-GAME TRADE`\n\n"
                    f"**🍎 Accepted Fruits:**\n"
                    f"• **Mythical:** Kitsune, Dragon, Leopard, Dough, T-Rex, Spirit, Venom, Mammoth\n"
                    f"• **Legendary:** Buddha, Portal, Blizzard, Sound, Rumble\n\n"
                    f"**Trade & Delivery Steps:**\n"
                    f"1. Open a support ticket or ping Bot Staff with your Invoice ID: **`{bill.id}`**.\n"
                    f"2. Join the staff member's VIP / Private Server to complete the Roblox fruit trade.\n"
                    f"3. Staff will mark your invoice as verified and your bot/boost is delivered immediately!"
                ),
                color=0x10B981,
                timestamp=discord.utils.utcnow(),
            )
            bill_embed.set_footer(text=f"Invoice ID: {bill.id} • KDC Shop • Blox Fruits Trade")
            return await interaction.response.send_message(embed=bill_embed, ephemeral=True)

        bill = self.shop_mgr.create_bill(
            guild_id=guild_id,
            customer_id=interaction.user.id,
            customer_name=str(interaction.user),
            item_id=item.id,
            currency="INR",
            quantity=1,
        )

        amount_str = f"₹{int(bill.total)}"
        bill_embed = discord.Embed(
            title=f"🧾 KDC SHOP INVOICE • `{bill.id}`",
            description=(
                f"**Customer:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                f"**Product:** `{bill.item_name}`\n"
                f"**Quantity:** `1`\n"
                f"**Total Due:** `₹ {amount_str} INR`\n"
                f"**USD Status:** `❌ USD Payments Unavailable (Pay via INR or Blox Fruits)`\n"
                f"**Invoice Status:** `🟡 PENDING PAYMENT`\n\n"
                f"**How to Pay:**\n"
                f"• Scan the official **UPI QR code** below using GPay, PhonePe, Paytm, BHIM, or FamPay.\n\n"
                f"Once paid, click **'⚡ Verify Payment & Claim Bot'** below to receive your bot files or boost activation!"
            ),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )
        bill_embed.set_footer(text=f"Invoice ID: {bill.id} • KDC Shop • UPI Scanner")

        qr_file_path = Path("assets/kdc_payment_qr.png")
        if qr_file_path.exists():
            file = discord.File(qr_file_path, filename="kdc_payment_qr.png")
            bill_embed.set_image(url="attachment://kdc_payment_qr.png")
            await interaction.response.send_message(embed=bill_embed, file=file, ephemeral=True)
        else:
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26am={bill.total}%26cu=INR%26tn={bill.id}"
            bill_embed.set_image(url=qr_url)
            await interaction.response.send_message(embed=bill_embed, ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN KDC SHOP COG
# ─────────────────────────────────────────────────────────────────────────────

class KDCShop(commands.Cog, name="KDCShop"):
    """Official KDC Shop & Automated Bot Delivery Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.shop_mgr = KDCShopManager()

    # ── Universal Trigger: typing 'stock' or 'scanner' anywhere ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        clean = message.content.strip().lower()
        # Trigger on exact keywords: "stock", "kdc stock", "kdc shop", "kdc"
        if clean in ("stock", "kdc stock", "kdc shop", "kdc"):
            ctx = await self.bot.get_context(message)
            if ctx.valid and ctx.command is not None:
                # Bot command dispatcher will invoke this command; don't execute twice!
                return
            await self.open_shop(ctx)
        elif clean in ("scanner", "qr", "kdc scanner", "kdc qr", "upi scanner", "payqr"):
            ctx = await self.bot.get_context(message)
            if ctx.valid and ctx.command is not None:
                return
            await self.send_scanner_embed(ctx)
        elif clean in ("review", "reviews", "kdc review", "kdc reviews"):
            ctx = await self.bot.get_context(message)
            if ctx.valid and ctx.command is not None:
                return
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

    # ── Super Cool Sovereign Vault Delivery Engine ──
    async def deliver_order(
        self,
        bill_id: str,
        staff_user: Union[discord.User, discord.Member],
        channel: Optional[discord.abc.Messageable] = None,
        origin_interaction: Optional[discord.Interaction] = None,
        view_to_disable: Optional[View] = None,
    ) -> bool:
        """Execute super cool auto-delivery after staff confirmation."""
        bill = self.shop_mgr.get_bill(bill_id)
        if not bill:
            if origin_interaction and not origin_interaction.response.is_done():
                await origin_interaction.followup.send(f"❌ Order `{bill_id}` not found.", ephemeral=True)
            elif channel:
                await channel.send(f"❌ Order `{bill_id}` not found.")
            return False

        if bill.status == "DELIVERED":
            msg = f"⚠️ Order `{bill_id}` has already been delivered."
            if origin_interaction:
                await origin_interaction.followup.send(msg, ephemeral=True)
            elif channel:
                await channel.send(msg)
            return False

        item = self.shop_mgr.get_item(bill.item_id)
        if not item:
            msg = f"❌ Product `{bill.item_id}` not found in catalog."
            if origin_interaction:
                await origin_interaction.followup.send(msg, ephemeral=True)
            elif channel:
                await channel.send(msg)
            return False

        # Attempt to resolve customer Discord User
        customer: Optional[Union[discord.User, discord.Member]] = self.bot.get_user(bill.customer_id)
        if not customer:
            try:
                customer = await self.bot.fetch_user(bill.customer_id)
            except Exception:
                customer = None

        customer_mention = customer.mention if customer else f"<@{bill.customer_id}>"
        customer_name = customer.name if customer else bill.customer_name

        # Build Super Cool Sovereign Vault Delivery Embed
        delivery_embed = discord.Embed(
            title="👑 KYOKA SOVEREIGN VAULT • ORDER DISPATCHED",
            description=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "✨ **AUTHENTICATED VAULT DISPATCH RECEIPT** ✨\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Payment has been **VERIFIED & APPROVED** by Staff {staff_user.mention}!\n"
                f"Your licensed assets have been cryptographically unsealed and released."
            ),
            color=0x8B5CF6,
            timestamp=discord.utils.utcnow(),
        )
        delivery_embed.set_thumbnail(url="https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=400&q=80")

        delivery_embed.add_field(
            name="📦 Product Name",
            value=f"**`{item.name}`**\n*Category: {item.category.upper()}*",
            inline=True,
        )
        delivery_embed.add_field(
            name="🔖 Invoice Reference",
            value=f"`#{bill.id}`",
            inline=True,
        )
        delivery_embed.add_field(
            name="💳 Verified Payment",
            value=f"`{bill.currency} {bill.total}`\n*Ref: {bill.transaction_id or 'STAFF-VERIFIED'}*",
            inline=True,
        )
        delivery_embed.add_field(
            name="🛡️ Verified & Dispatched By",
            value=f"{staff_user.mention} (`{staff_user.name}`)",
            inline=True,
        )
        delivery_embed.add_field(
            name="💎 VIP Warranty & Coverage",
            value="`🟢 Active (30-Day Non-Drop & Bugfix Guarantee)`",
            inline=True,
        )
        delivery_embed.add_field(
            name="⚡ Vault Security Tier",
            value="`🔒 Cryptographically Authenticated • Kyoka 3.0`",
            inline=True,
        )

        file_path = None
        if item.is_auto_deliver:
            file_path = self.shop_mgr.get_bot_file_path(item.id)
            delivery_embed.add_field(
                name="🚀 Rapid Setup Walkthrough (3 Steps)",
                value=(
                    "`1️⃣` **Extract**: Unpack the attached `.zip` bot archive to your project folder.\n"
                    "`2️⃣` **Configure**: Copy `.env.example` to `.env` and paste your Bot Token & IDs.\n"
                    "`3️⃣` **Deploy**: Run `pip install -r requirements.txt` and launch with `python bot.py`!"
                ),
                inline=False,
            )
            if file_path and file_path.exists():
                delivery_embed.add_field(
                    name="📁 Attached Package",
                    value=f"📦 **`{file_path.name}`** (`{round(file_path.stat().st_size / 1024, 1)} KB`)",
                    inline=False,
                )
        elif item.category in ("boosts", "nitro"):
            delivery_embed.add_field(
                name="🚀 Boost / Nitro Activation Protocol",
                value=(
                    f"`1️⃣` Send your permanent Server Invite Link in this channel or DM {staff_user.mention}.\n"
                    f"`2️⃣` Keep the invite open for at least 24 hours.\n"
                    f"`3️⃣` Boosts/Nitro transfer will complete within 1-10 minutes with instant anti-drop coverage!"
                ),
                inline=False,
            )
        else:
            delivery_embed.add_field(
                name="🛠️ Service Delivery",
                value=f"Staff member {staff_user.mention} is now actively fulfilling your custom service request.",
                inline=False,
            )

        delivery_embed.set_footer(
            text=f"Kyoka Sovereign Vault • Cryptographically Sealed • Staff Dispatch ID: {staff_user.id}"
        )

        # Update bill status in DB
        delivered_fname = file_path.name if (file_path and file_path.exists()) else ""
        self.shop_mgr.update_bill_status(
            bill.id,
            status="DELIVERED",
            delivered_file=delivered_fname,
            staff_id=staff_user.id,
        )

        # Dispatch delivery to customer DM
        delivered_to_dm = False
        if customer:
            try:
                if file_path and file_path.exists():
                    dm_file = discord.File(file_path, filename=file_path.name)
                    await customer.send(embed=delivery_embed, file=dm_file)
                else:
                    await customer.send(embed=delivery_embed)
                delivered_to_dm = True
            except Exception as e:
                logger.warning(f"Could not send delivery DM to {customer}: {e}")

        # Channel announcement or fallback channel dispatch
        if channel:
            if delivered_to_dm:
                confirm_embed = discord.Embed(
                    title="✅ ORDER CONFIRMED & DISPATCHED",
                    description=(
                        f"**Invoice:** `#{bill.id}`\n"
                        f"**Customer:** {customer_mention}\n"
                        f"**Product:** `{item.name}`\n"
                        f"**Verified By:** {staff_user.mention}\n\n"
                        f"✨ Product package successfully delivered to {customer_mention}'s direct messages (DMs)!"
                    ),
                    color=0x10B981,
                    timestamp=discord.utils.utcnow(),
                )
                confirm_embed.set_footer(text="Kyoka Shop • Automated Dispatch System")
                await channel.send(embed=confirm_embed)
            else:
                # Direct message failed or closed, deliver right in the channel!
                if file_path and file_path.exists():
                    ch_file = discord.File(file_path, filename=file_path.name)
                    await channel.send(
                        content=(
                            f"📦 **Direct Messages Closed for {customer_mention}!**\n"
                            f"Your verified package for `{bill.item_name}` is unsealed and attached below:"
                        ),
                        embed=delivery_embed,
                        file=ch_file,
                    )
                else:
                    await channel.send(
                        content=f"📦 **Delivery Notice for {customer_mention}:**",
                        embed=delivery_embed,
                    )

        # Update staff review card
        if view_to_disable:
            for child in view_to_disable.children:
                if isinstance(child, Button):
                    child.disabled = True

        reviewed_card = discord.Embed(
            title=f"✅ [PAYMENT CONFIRMED & DELIVERED] • #{bill.id}",
            description=(
                f"• **Customer:** {customer_mention} (`{customer_name}`)\n"
                f"• **Product:** `{item.name}`\n"
                f"• **Amount:** `{bill.currency} {bill.total}`\n"
                f"• **Verified By:** {staff_user.mention} (`{staff_user.name}`)\n"
                f"• **Delivery Status:** `🟢 DELIVERED ({'DMs' if delivered_to_dm else 'Ticket Channel'})`\n"
                f"• **Delivered Asset:** `{delivered_fname or 'Service / Invite Activation'}`"
            ),
            color=0x10B981,
            timestamp=discord.utils.utcnow(),
        )
        reviewed_card.set_footer(text=f"Kyoka Shop • Verified by Staff ID: {staff_user.id}")

        if origin_interaction and origin_interaction.message:
            try:
                await origin_interaction.message.edit(embed=reviewed_card, view=view_to_disable)
            except Exception:
                pass

        return True

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

        success = await self.deliver_order(bill_id, ctx.author, channel=ctx.channel)
        if not success:
            await ctx.send(f"⚠️ Delivery could not be completed for `{bill_id}`.")

    # ── Staff Subcommand: +stock confirm ──
    @stock_command.command(name="confirm")
    async def stock_confirm(self, ctx: CustomContext, bill_id: str):
        """[Staff] Confirm payment and auto-deliver a pending or verifying invoice."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        success = await self.deliver_order(bill_id, ctx.author, channel=ctx.channel)
        if success:
            await ctx.send(f"✅ Invoice `{bill_id}` confirmed and auto-delivered by {ctx.author.mention}!")

    # ── Staff Subcommand: +stock reject ──
    @stock_command.command(name="reject")
    async def stock_reject(self, ctx: CustomContext, bill_id: str, *, reason: str = "Invalid payment / UTR not found"):
        """[Staff] Reject an invoice payment with a reason."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        bill = self.shop_mgr.update_bill_status(
            bill_id,
            status="REJECTED",
            staff_id=ctx.author.id,
            staff_notes=f"Rejected: {reason}",
        )
        if not bill:
            return await ctx.send(f"❌ Bill `{bill_id}` not found.")

        embed = discord.Embed(
            title="❌ INVOICE PAYMENT REJECTED",
            description=(
                f"• **Invoice:** `{bill.id}`\n"
                f"• **Customer:** <@{bill.customer_id}>\n"
                f"• **Product:** `{bill.item_name}`\n"
                f"• **Rejected By:** {ctx.author.mention}\n"
                f"• **Reason:** `{reason}`"
            ),
            color=0xEF4444,
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed)

    # ── Staff Subcommand: +stock pending ──
    @stock_command.command(name="pending")
    async def stock_pending(self, ctx: CustomContext):
        """[Staff] View all invoices waiting for payment verification."""
        if not is_kdc_staff(ctx.author.id, ctx.guild):
            return await ctx.send("❌ Unauthorized: You need KDC Staff or Owner permissions.")

        verifying_bills = self.shop_mgr.list_bills(status="VERIFYING", limit=20)
        pending_bills = self.shop_mgr.list_bills(status="PENDING", limit=20)
        all_pending = verifying_bills + pending_bills

        if not all_pending:
            return await ctx.send("✅ No orders currently awaiting verification!")

        lines = []
        for b in all_pending[:15]:
            status_tag = "⚡ VERIFYING" if b.status == "VERIFYING" else "🟡 PENDING"
            utr_str = f"UTR: `{b.transaction_id}`" if b.transaction_id else "No UTR"
            lines.append(
                f"• **`{b.id}`** | <@{b.customer_id}> | **{b.item_name}** | `{b.currency} {b.total}` | **{status_tag}**\n"
                f"  └ {utr_str} • Type `+stock confirm {b.id}`"
            )

        embed = discord.Embed(
            title=f"📋 Orders Awaiting Staff Verification ({len(all_pending)})",
            description="\n".join(lines),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Use +stock confirm <bill_id> or click button on staff card")
        await ctx.send(embed=embed)

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

    # ── Staff Contact View Helper ──
    def get_staff_contact_view(self) -> discord.ui.View:
        """Construct interactive view with direct DM buttons for all bot staff."""
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Direct DM Ruthupavan (Owner)",
                url=f"https://discord.com/users/{PRIMARY_OWNER_ID}",
                style=discord.ButtonStyle.link,
                emoji="💬",
            )
        )
        from src.security.owner import get_all_bot_staff
        for staff_id in get_all_bot_staff():
            if staff_id != PRIMARY_OWNER_ID:
                view.add_item(
                    discord.ui.Button(
                        label=f"Direct DM Staff ({staff_id})",
                        url=f"https://discord.com/users/{staff_id}",
                        style=discord.ButtonStyle.link,
                        emoji="🛡️",
                    )
                )
        return view

    # ── Standalone Scanner Helper & Command ──
    async def send_scanner_embed(self, ctx: Union[CustomContext, commands.Context, discord.Interaction]):
        from src.security.owner import get_all_bot_staff
        staff_ids = [PRIMARY_OWNER_ID] + [s for s in get_all_bot_staff() if s != PRIMARY_OWNER_ID]
        staff_lines = []
        for sid in staff_ids:
            role_label = "Owner / Sovereign" if sid == PRIMARY_OWNER_ID else "Authorized Bot Staff"
            staff_lines.append(f"• **{role_label}:** <@{sid}> (`ID: {sid}`) — [Direct DM User](https://discord.com/users/{sid})")

        scanner_embed = discord.Embed(
            title="💳 KDC SHOP • OFFICIAL UPI PAYMENT SCANNER",
            description=(
                "> **Scan the QR code below with any UPI App (GPay, PhonePe, Paytm, BHIM, FamPay) to pay.**\n\n"
                "• **Payment Method:** `₹ INR (Official UPI Scanner)`\n"
                "• **USD / International Payments:** `❌ Temporarily Unavailable`\n\n"
                "**How to Order & Claim:**\n"
                "1. Type `stock` to view products and select **'🧾 Make Bill (INR)'**.\n"
                "2. Scan this QR code and complete your payment in ₹ INR.\n"
                "3. Type `+stock verify <InvoiceID> <UTR>` or click **'⚡ Verify Payment & Claim Bot'**.\n\n"
                "**🛡️ Contact Bot Staff to Confirm Purchase:**\n"
                "> Once you buy, please **contact bot staff directly** to verify payment & claim:\n"
                + "\n".join(staff_lines)
            ),
            color=0x10B981,
            timestamp=discord.utils.utcnow(),
        )
        scanner_embed.set_footer(text="KDC Shop • UPI Scanner • Click Direct DM button below to contact staff!")

        view = self.get_staff_contact_view()

        qr_file_path = Path("assets/kdc_payment_qr.png")
        if qr_file_path.exists():
            file = discord.File(qr_file_path, filename="kdc_payment_qr.png")
            scanner_embed.set_image(url="attachment://kdc_payment_qr.png")
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(embed=scanner_embed, file=file, view=view)
            else:
                await ctx.send(embed=scanner_embed, file=file, view=view)
        else:
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26cu=INR"
            scanner_embed.set_image(url=qr_url)
            if isinstance(ctx, discord.Interaction):
                await ctx.response.send_message(embed=scanner_embed, view=view)
            else:
                await ctx.send(embed=scanner_embed, view=view)

    @commands.command(name="pay", aliases=["payscanner", "sendscanner", "qrpay", "scanner", "qr", "kdcqr", "kdcscanner", "upiscanner"])
    async def pay_command(self, ctx: CustomContext):
        """Send the official KDC Shop UPI payment QR scanner with bot staff direct DM options."""
        await self.send_scanner_embed(ctx)

    @commands.Cog.listener("on_message")
    async def on_pay_message(self, message: discord.Message) -> None:
        """Trigger scanner automatically when a user simply says 'pay'."""
        if message.author.bot:
            return
        content = message.content.strip().lower()
        if content in ("pay", "pay scanner", "send scanner", "give scanner", "show scanner", "upi pay"):
            ctx = await self.bot.get_context(message)
            await self.send_scanner_embed(ctx)

    # ── Standalone Bill Creation Command ──
    @commands.command(name="makebill", aliases=["buyitem", "shoporder", "orderitem"])
    async def makebill_command(self, ctx: CustomContext, item_id: str = "boost_2", currency: str = "INR"):
        """Create an invoice bill for a product (e.g. +makebill boost_2 INR)."""
        if currency.strip().upper() == "USD":
            embed = discord.Embed(
                title="❌ USD PAYMENTS TEMPORARILY UNAVAILABLE",
                description=(
                    "**USD Payments (PayPal / Stripe) are currently unavailable.**\n\n"
                    "Please use `+makebill [item_id] INR` to pay in Indian Rupees (**₹ INR**) using the official UPI scanner.\n\n"
                    "If you are an international buyer without UPI access, please contact staff or open a support ticket."
                ),
                color=0xEF4444,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="KDC Shop • USD Unavailable • Please pay in INR")
            return await ctx.send(embed=embed)

        item = self.shop_mgr.get_item(item_id.strip().lower())
        if not item:
            return await ctx.send(f"❌ Product `{item_id}` not found. Type `stock` to view available products.")

        guild_id = ctx.guild.id if ctx.guild else 0
        bill = self.shop_mgr.create_bill(
            guild_id=guild_id,
            customer_id=ctx.author.id,
            customer_name=str(ctx.author),
            item_id=item.id,
            currency="INR",
            quantity=1,
        )

        amount_str = f"₹{int(bill.total)}"

        from src.security.owner import get_all_bot_staff
        staff_ids = [PRIMARY_OWNER_ID] + [s for s in get_all_bot_staff() if s != PRIMARY_OWNER_ID]
        staff_lines = []
        for sid in staff_ids:
            role_label = "Owner / Sovereign" if sid == PRIMARY_OWNER_ID else "Authorized Bot Staff"
            staff_lines.append(f"• **{role_label}:** <@{sid}> (`ID: {sid}`) — [Direct DM User](https://discord.com/users/{sid})")

        bill_embed = discord.Embed(
            title=f"🧾 KDC SHOP INVOICE • `{bill.id}`",
            description=(
                f"**Customer:** {ctx.author.mention} (`{ctx.author.name}`)\n"
                f"**Product:** `{bill.item_name}`\n"
                f"**Quantity:** `1`\n"
                f"**Total Due:** `₹ {amount_str} INR`\n"
                f"**USD Status:** `❌ USD Payments Unavailable (Pay via INR)`\n"
                f"**Invoice Status:** `🟡 PENDING PAYMENT`\n\n"
                f"**How to Pay:**\n"
                f"• Scan the official **UPI QR code** below using GPay, PhonePe, Paytm, BHIM, or FamPay.\n"
                f"• Once paid, type `+stock verify {bill.id} <UTR>` or click '⚡ Verify Payment & Claim Bot'.\n\n"
                f"**🛡️ Once You Pay, Contact Bot Staff:**\n"
                + "\n".join(staff_lines)
            ),
            color=0xF59E0B,
            timestamp=discord.utils.utcnow(),
        )
        bill_embed.set_footer(text=f"Invoice ID: {bill.id} • KDC Shop • UPI Scanner")

        view = self.get_staff_contact_view()

        qr_file_path = Path("assets/kdc_payment_qr.png")
        if qr_file_path.exists():
            file = discord.File(qr_file_path, filename="kdc_payment_qr.png")
            bill_embed.set_image(url="attachment://kdc_payment_qr.png")
            await ctx.send(embed=bill_embed, file=file, view=view)
        else:
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={self.shop_mgr.upi_id}%26pn=KDC_Shop%26am={bill.total}%26cu=INR%26tn={bill.id}"
            bill_embed.set_image(url=qr_url)
            await ctx.send(embed=bill_embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KDCShop(bot))
