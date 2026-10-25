import pytest
import time
from src.managers.top_manager import TopManager
from src.cogs.general.top_ai_manager import format_beli_amount, format_blox_fruits_bill_embed

def test_format_beli_amount():
    assert format_beli_amount(0) == "0M"
    assert format_beli_amount(30.0) == "30M"
    assert format_beli_amount(1.5) == "1.5M"
    assert format_beli_amount(31.5) == "31.5M"
    assert format_beli_amount(30000000) == "30M"

def test_blox_fruits_billing_lifecycle(tmp_path):
    db_path = tmp_path / "test_billing.sqlite3"
    mgr = TopManager(db_path=str(db_path))

    # 1. Create a 2 Trials bill with 5% tax
    calc = mgr.calculate_service_price("2 Trials", quantity=1, tax_rate=5.0)
    assert calc.subtotal == 40.0
    assert calc.tax_amount == 2.0
    assert calc.total == 42.0

    bill = mgr.create_bill(
        guild_id=12345,
        creator_id=1505515188991033409,
        creator_name="Owner",
        service_name="2 Trials",
        quantity=1,
        tax_rate=5.0,
        customer_id=987654321,
        customer_name="TestCustomer",
        payment_type="Beli",
    )

    assert bill["id"].startswith("TOP-")
    assert bill["status"] == "UNPAID"
    assert bill["subtotal"] == 40.0
    assert bill["tax_amount"] == 2.0
    assert bill["total"] == 42.0

    # 2. Check embed formatter
    embed = format_blox_fruits_bill_embed(bill)
    assert "KYOKA" in embed.title
    assert "SERVICE QUOTE" in embed.title
    assert "40M" in embed.description
    assert "2M" in embed.description
    assert "42M" in embed.description
    assert "UNPAID" in embed.description
    assert "Beli" not in embed.description

    # 3. Associate with posted Discord message ID (18-digit snowflake)
    message_id = "123456789012345678"
    channel_id = 1122334455
    mgr.set_bill_posted_message(bill["id"], channel_id, message_id)

    # 4. Find bill by message ID
    found = mgr.find_bill_by_message_id(message_id)
    assert len(found) >= 1
    assert found[0]["id"] == bill["id"]

    # 5. Mark bill as paid by message ID
    paid_bill = mgr.mark_bill_paid_by_message_id(message_id, staff_id=1505515188991033409, staff_name="Owner")
    assert paid_bill["status"] == "PAID"
    assert paid_bill["paid_by_id"] == 1505515188991033409

    # 6. Duplicate payment prevention
    with pytest.raises(ValueError, match="already been marked as PAID"):
        mgr.mark_bill_paid_by_message_id(message_id, staff_id=1505515188991033409, staff_name="Owner")

    # 7. Today and Monthly revenue reports
    today_rep = mgr.get_today_report(12345)
    assert today_rep["paid_count"] == 1
    assert today_rep["received_revenue_m"] == 42.0
    assert today_rep["tax_collected_m"] == 2.0
    assert "Beli" in today_rep["revenue_by_payment_type"]

    month_rep = mgr.get_monthly_report(12345)
    assert month_rep["paid_count"] == 1
    assert month_rep["received_revenue_m"] == 42.0

def test_fruit_based_bill(tmp_path):
    db_path = tmp_path / "test_fruit_billing.sqlite3"
    mgr = TopManager(db_path=str(db_path))

    bill = mgr.create_bill(
        guild_id=12345,
        creator_id=1505515188991033409,
        creator_name="Owner",
        service_name="Leviathan Hunt",
        quantity=1,
        tax_rate=0.0,
        customer_id=987654321,
        customer_name="FruitTrader",
        payment_type="Fruits",
        fruit_details="Kitsune + Leopard",
        custom_price=0.0,
        custom_price_display="Kitsune + Leopard Fruit",
    )

    assert bill["payment_type"] == "Fruits"
    assert bill["fruit_details"] == "Kitsune + Leopard"

    embed = format_blox_fruits_bill_embed(bill)
    assert "Kitsune + Leopard" in embed.description

    # Mark paid with 18-digit message ID
    mgr.mark_bill_paid(bill["id"], staff_id=1505515188991033409, staff_name="Owner", message_id="111222333444555666")
    today_rep = mgr.get_today_report(12345)
    assert today_rep["paid_count"] == 1
    assert "Fruits" in today_rep["revenue_by_payment_type"]
    assert "Kitsune + Leopard" in today_rep["fruit_summary"]
