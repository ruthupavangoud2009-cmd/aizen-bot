"""
Tests for Blox Fruits Service Invoices:
1. Anti-Fraud: Customers cannot mark their own invoices as paid.
2. Staff can mark invoices as PAID, CANCELLED, and REFUNDED.
3. Status changes create immutable audit log records.
4. Itemized invoice attributes (item, category, payment method, notes).
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands
import pytest

from src.cogs.general.bills import Bills, db


@pytest.fixture(autouse=True)
def clean_test_billing_db(tmp_path, monkeypatch):
    test_db = tmp_path / "kyoka_billing.sqlite3"
    monkeypatch.setattr("src.cogs.general.bills.DB", test_db)
    yield test_db


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.display_avatar.url = "https://example.com/bot.png"
    return bot


@pytest.fixture
def bills_cog(mock_bot):
    c = Bills(mock_bot)
    for attr in dir(c):
        val = getattr(c, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = c
    return c


@pytest.fixture
def mock_staff_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 55555555
    ctx.guild.name = "Blox Services Official"
    ctx.guild.icon = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 1505515188991033409  # Authoritative Staff/Owner
    ctx.author.mention = "<@1505515188991033409>"
    ctx.author.guild_permissions.administrator = True
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture
def mock_customer():
    c = MagicMock(spec=discord.Member)
    c.id = 77777777
    c.name = "ClientGamer"
    c.display_name = "ClientGamer"
    c.mention = "<@77777777>"
    c.bot = False
    return c


@pytest.mark.asyncio
async def test_anti_fraud_customer_cannot_mark_own_bill_paid(bills_cog, mock_staff_ctx, mock_customer):
    """Customers must not be able to mark their own invoices as paid."""
    # 1. Staff creates invoice for customer
    await bills_cog.bill(mock_staff_ctx, mock_customer, "raid", "Dough V2 Awakening", "Kitsune Fruit", "Complete today")
    with db() as c:
        row = c.execute("SELECT id FROM bills WHERE customer=?", (mock_customer.id,)).fetchone()
        invoice_id = row["id"]

    # 2. Customer attempts to mark own invoice paid
    customer_ctx = MagicMock()
    customer_ctx.guild = mock_staff_ctx.guild
    customer_ctx.author = mock_customer
    customer_ctx.author.guild_permissions.administrator = False
    customer_ctx.author.guild_permissions.manage_guild = False
    customer_ctx.author.guild_permissions.manage_messages = False
    customer_ctx.reply = AsyncMock()

    # Even if customer had staff role, anti-fraud prevents customer self-approval
    await bills_cog.billpaid(customer_ctx, invoice_id)
    customer_ctx.reply.assert_called_once()
    reply_msg = customer_ctx.reply.call_args[0][0].lower()
    assert ("only server staff" in reply_msg) or ("anti-fraud" in reply_msg)

    # Verify invoice remains PENDING in database
    with db() as c:
        check = c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()
        assert check["status"] == "PENDING"


@pytest.mark.asyncio
async def test_staff_invoice_status_transitions_and_audit(bills_cog, mock_staff_ctx, mock_customer):
    """Staff can update invoice statuses and every transition is recorded in the audit log."""
    # Create invoice
    await bills_cog.bill(mock_staff_ctx, mock_customer, "leveling", "1 to 2550 Max Level", "1500 Robux")
    with db() as c:
        row = c.execute("SELECT id FROM bills WHERE customer=?", (mock_customer.id,)).fetchone()
        invoice_id = row["id"]

    mock_staff_ctx.reply.reset_mock()

    # Transition 1: Mark PAID
    await bills_cog.billpaid(mock_staff_ctx, invoice_id)
    with db() as c:
        r = c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()
        assert r["status"] == "PAID"
        audit = c.execute("SELECT * FROM bill_audit_log WHERE bill_id=? AND new_status='PAID'", (invoice_id,)).fetchone()
        assert audit is not None
        assert audit["staff_id"] == mock_staff_ctx.author.id

    # Transition 2: Mark REFUNDED
    mock_staff_ctx.reply.reset_mock()
    await bills_cog.billrefund(mock_staff_ctx, invoice_id)
    with db() as c:
        r = c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()
        assert r["status"] == "REFUNDED"
        audit = c.execute("SELECT * FROM bill_audit_log WHERE bill_id=? AND new_status='REFUNDED'", (invoice_id,)).fetchone()
        assert audit is not None
