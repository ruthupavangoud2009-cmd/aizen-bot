import pytest
import sqlite3
import time
from unittest.mock import MagicMock
from src.cogs.general.vouches import Vouches, conn, DB

def test_vouch_database_schema():
    with conn() as c:
        # Check columns
        info = c.execute("PRAGMA table_info(vouches)").fetchall()
        col_names = [r["name"] for r in info]
        assert "message_id" in col_names
        assert "target_id" in col_names
        assert "voucher_id" in col_names
        assert "is_active" in col_names

        # Check scan state table
        scan_info = c.execute("PRAGMA table_info(vouch_scan_state)").fetchall()
        scan_col_names = [r["name"] for r in scan_info]
        assert "guild_id" in scan_col_names
        assert "channel_id" in scan_col_names
        assert "last_scanned_message_id" in scan_col_names

def test_extract_vouch_patterns():
    cog = Vouches(bot=MagicMock())

    # 1. Standard command message: +vouch <@123456789012345678> raid 5x dough raids completed
    msg1 = MagicMock()
    msg1.embeds = []
    msg1.content = "+vouch <@123456789012345678> raid 5x dough raids completed"
    msg1.author.id = 987654321098765432

    parsed = cog._extract_vouch_from_message(msg1)
    assert parsed is not None
    target_id, voucher_id, reason, service_type = parsed
    assert target_id == 123456789012345678
    assert voucher_id == 987654321098765432
    assert "dough raids" in reason
    assert service_type == "raid"

    # 2. Mention + rep format: <@123456789012345678> +rep fast kitsune trade
    msg2 = MagicMock()
    msg2.embeds = []
    msg2.content = "<@123456789012345678> +rep fruit fast kitsune trade"
    msg2.author.id = 987654321098765432

    parsed2 = cog._extract_vouch_from_message(msg2)
    assert parsed2 is not None
    t2, v2, r2, s2 = parsed2
    assert t2 == 123456789012345678
    assert s2 == "fruit"

    # 3. Non-vouch chatter: hello everyone what is up
    msg3 = MagicMock()
    msg3.embeds = []
    msg3.content = "hello everyone what is up"
    msg3.mentions = []
    assert cog._extract_vouch_from_message(msg3) is None

def test_vouch_deduplication():
    with conn() as c:
        test_msg_id = "999888777666555444"
        now = time.time()
        # Clean up if existing
        c.execute("DELETE FROM vouches WHERE message_id = ?", (test_msg_id,))

        # Insert first time
        c.execute(
            """INSERT INTO vouches(
                guild_id, voucher_id, target_id, reason, created, held,
                service_type, rating, source, is_active, message_id
            ) VALUES(1, 100, 200, 'Test Vouch', ?, 0, 'raid', 5, 'scanned_channel', 1, ?)""",
            (now, test_msg_id)
        )

        row = c.execute("SELECT id FROM vouches WHERE message_id = ?", (test_msg_id,)).fetchone()
        assert row is not None

        # Clean up
        c.execute("DELETE FROM vouches WHERE message_id = ?", (test_msg_id,))
