"""
Unit and integration tests for Blox Fruits Service Invoices:
1. Invoice creation with categories, in-game fruit payments, or currency.
2. Status transitions (PENDING -> PAID, CANCELLED, REFUNDED).
3. Staff permission enforcement.
4. Invoice retrieval and customer list.
5. Revenue and status metrics.
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
def clean_billing_db(tmp_path, monkeypatch):
    test_db = tmp_path / "kyoka_billing.sqlite3"
    monkeypatch.setattr("src.cogs.general.bills.DB", test_db)
    yield test_db


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 55555555
    ctx.guild.name = "Blox Services Official"
    ctx.guild.icon = None
    ctx.author = MagicMock(spec=discord.Member)
    ctx.author.id = 1505515188991033409  # Owner ID: Authoritative Staff
    ctx.author.mention = "<@1505515188991033409>"
    ctx.author.guild_permissions.administrator = True
    ctx.author.guild_permissions.manage_guild = True
    ctx.author.guild_permissions.manage_messages = True
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


@pytest.fixture
def cog():
    c = Bills(MagicMock())
    for attr in dir(c):
        val = getattr(c, attr)
        if isinstance(val, (commands.Command, commands.HybridCommand)):
            val.cog = c
    return c


@pytest.mark.asyncio
async def test_blox_fruits_invoice_creation(cog, mock_ctx, mock_customer):
    # Create bill: category=raid, item="Dough V2 Awakening", payment="Kitsune + Dough"
    await cog.bill(mock_ctx, mock_customer, "raid", "Dough V2 Full Awakening", "Kitsune + Dough", "Complete within 2 hours")

    mock_ctx.reply.assert_called_once()
    call_kwargs = mock_ctx.reply.call_args[1]
    embed = call_kwargs.get("embed")
    assert embed is not None
    assert "INVOICE" in embed.title
    assert "BF-INV-" in embed.title

    with db() as c:
        row = c.execute("SELECT * FROM bills WHERE customer=?", (mock_customer.id,)).fetchone()
        assert row is not None
        assert "BF-INV-" in row["id"]
        assert row["status"] == "PENDING"
        assert row["category"] == "Raids & Carries"
        assert row["payment_method"] == "Kitsune + Dough"


@pytest.mark.asyncio
async def test_invoice_payment_transition_staff_only(cog, mock_ctx, mock_customer):
    # Create bill
    await cog.bill(mock_ctx, mock_customer, "leveling", "1 to 2550 Max Level", "1500 Robux")
    with db() as c:
        row = c.execute("SELECT id FROM bills WHERE customer=?", (mock_customer.id,)).fetchone()
        invoice_id = row["id"]

    mock_ctx.reply.reset_mock()

    # Mark as paid by staff
    await cog.billpaid(mock_ctx, invoice_id)

    mock_ctx.reply.assert_called_once()
    assert "PAID" in mock_ctx.reply.call_args[1]["content"]

    with db() as c:
        updated = c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()
        assert updated["status"] == "PAID"

        # Check audit log
        audit = c.execute("SELECT * FROM bill_audit_log WHERE bill_id=?", (invoice_id,)).fetchall()
        assert len(audit) >= 2  # creation + paid transition


@pytest.mark.asyncio
async def test_non_staff_cannot_create_or_mark_paid(cog, mock_ctx, mock_customer):
    # Demote user to regular member
    mock_ctx.author.id = 99999999
    mock_ctx.author.guild_permissions.administrator = False
    mock_ctx.author.guild_permissions.manage_guild = False
    mock_ctx.author.guild_permissions.manage_messages = False

    await cog.bill(mock_ctx, mock_customer, "raid", "Flame Raid", "Magma")
    assert "Only server staff" in mock_ctx.reply.call_args[0][0]

    mock_ctx.reply.reset_mock()
    await cog.billpaid(mock_ctx, "BF-INV-FAKEXX")
    assert "Only server staff" in mock_ctx.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_invoice_cancellation_and_refund(cog, mock_ctx, mock_customer):
    await cog.bill(mock_ctx, mock_customer, "bounty", "2.5M to 5M Bounty", "Leopard Fruit")
    with db() as c:
        invoice_id = c.execute("SELECT id FROM bills WHERE customer=?", (mock_customer.id,)).fetchone()["id"]

    mock_ctx.reply.reset_mock()
    await cog.billcancel(mock_ctx, invoice_id)
    assert "CANCELLED" in mock_ctx.reply.call_args[0][0]

    with db() as c:
        assert c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()["status"] == "CANCELLED"

    mock_ctx.reply.reset_mock()
    await cog.billrefund(mock_ctx, invoice_id)
    assert "REFUNDED" in mock_ctx.reply.call_args[0][0]

    with db() as c:
        assert c.execute("SELECT status FROM bills WHERE id=?", (invoice_id,)).fetchone()["status"] == "REFUNDED"


@pytest.mark.asyncio
async def test_billstats_metrics(cog, mock_ctx, mock_customer):
    with db() as c:
        now = time.time()
        c.execute("INSERT INTO bills(id, guild, creator, customer, description, subtotal, tax, total, status, created, category) "
                  "VALUES('BF-INV-1', ?, ?, ?, 'Raid', 0, 0, 0, 'PAID', ?, 'Raids & Carries')",
                  (mock_ctx.guild.id, mock_ctx.author.id, mock_customer.id, now))
        c.execute("INSERT INTO bills(id, guild, creator, customer, description, subtotal, tax, total, status, created, category) "
                  "VALUES('BF-INV-2', ?, ?, ?, 'Level', 0, 0, 0, 'PENDING', ?, 'Leveling & Grinding')",
                  (mock_ctx.guild.id, mock_ctx.author.id, mock_customer.id, now))

    await cog.billstats(mock_ctx)
    mock_ctx.reply.assert_called_once()
    embed = mock_ctx.reply.call_args[1]["embed"]
    assert "**Total Invoices Issued:** `2`" in embed.description
    assert "**Completed & Paid:** `1`" in embed.description
    assert "**Pending Orders:** `1`" in embed.description
