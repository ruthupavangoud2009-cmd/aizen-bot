"""
Test Suite for Discord Gateway Route Failover & 429 Rate Limit Bypass Engine.
Verifies proxy pool parsing, route cooldown tracking, and automated instant failover.
"""

from __future__ import annotations

import time
import pytest
from src.core.config import parse_proxy_pool, Config


def test_parse_proxy_pool_handles_comma_newline_and_whitespace():
    """Verify that multiple proxies separated by commas or newlines are parsed cleanly."""
    raw = "http://user:pass@1.1.1.1:8080, http://2.2.2.2:3128\nhttp://3.3.3.3:9090"
    pool = parse_proxy_pool(raw)
    assert len(pool) == 3
    assert pool[0] == "http://user:pass@1.1.1.1:8080"
    assert pool[1] == "http://2.2.2.2:3128"
    assert pool[2] == "http://3.3.3.3:9090"


def test_parse_proxy_pool_deduplicates_and_ignores_empty():
    """Verify empty entries and duplicate proxies are discarded."""
    raw = ",,http://1.1.1.1:8080, http://1.1.1.1:8080, "
    pool = parse_proxy_pool(raw)
    assert len(pool) == 1
    assert pool[0] == "http://1.1.1.1:8080"


def test_instant_failover_logic_selects_unblocked_alternative():
    """Simulate route failover: direct connection is primary for 10-30ms ping; on 429 it fails over to backup proxy."""
    route_cooldowns: dict[str, float] = {}
    candidate_routes = [None, "http://proxy1:8080"]  # Direct is primary, proxy is backup
    now = time.monotonic()

    # Initially, direct connection is selected for lowest ping
    available = [r for r in candidate_routes if route_cooldowns.get(r or "direct", 0.0) <= now]
    assert available[0] is None

    # Simulate Discord 429 on direct connection with 2854s cooldown
    penalty = 2854.0
    route_cooldowns["direct"] = now + penalty

    # Check unblocked alternatives
    unblocked = [
        r for r in candidate_routes
        if (r or "direct") != "direct"
        and route_cooldowns.get(r or "direct", 0.0) <= now
    ]
    # Backup proxy is immediately available! No 2854s wait!
    assert len(unblocked) == 1
    assert unblocked[0] == "http://proxy1:8080"
