"""Unit tests for Discord bitwise permissions check and cross-server isolation."""
import pytest
from dashboard_api.permissions import (
    ADMINISTRATOR,
    MANAGE_GUILD,
    has_manage_permission,
    can_manage_guild,
    find_manageable_guild,
)


def test_permission_bitwise_checks():
    # Administrator only
    assert has_manage_permission(ADMINISTRATOR) is True
    assert has_manage_permission(8) is True

    # Manage Guild only
    assert has_manage_permission(MANAGE_GUILD) is True
    assert has_manage_permission(32) is True

    # Both bits
    assert has_manage_permission(ADMINISTRATOR | MANAGE_GUILD) is True

    # Guild owner overrides missing permissions
    assert has_manage_permission(0, is_owner=True) is True

    # Regular user permissions (e.g., Send Messages = 0x800, View Channel = 0x400)
    regular_perms = 0x800 | 0x400
    assert has_manage_permission(regular_perms, is_owner=False) is False
    assert has_manage_permission(0, is_owner=False) is False
    assert has_manage_permission(None, is_owner=False) is False


def test_can_manage_guild():
    # Admin server
    g1 = {"id": "1001", "name": "Admin Server", "permissions": "8", "owner": False}
    assert can_manage_guild(g1) is True

    # Manage Guild server
    g2 = {"id": "1002", "name": "Mod Server", "permissions": "32", "owner": False}
    assert can_manage_guild(g2) is True

    # Owned server with 0 permissions
    g3 = {"id": "1003", "name": "Owner Server", "permissions": "0", "owner": True}
    assert can_manage_guild(g3) is True

    # Member server (no manage rights)
    g4 = {"id": "1004", "name": "Public Server", "permissions": "1024", "owner": False}
    assert can_manage_guild(g4) is False


def test_cross_server_isolation():
    user_guilds = [
        {"id": "1001", "name": "My Server", "permissions": "32", "owner": False},
        {"id": "1002", "name": "Foreign Server Without Rights", "permissions": "0", "owner": False},
    ]

    # Authorized access to server user manages
    authorized = find_manageable_guild(user_guilds, "1001")
    assert authorized is not None
    assert authorized["name"] == "My Server"

    # Attempted access to server in user's list but WITHOUT manage rights
    denied_unauthorized = find_manageable_guild(user_guilds, "1002")
    assert denied_unauthorized is None

    # Attempted access to server completely outside user's guilds (Server 9999)
    denied_foreign = find_manageable_guild(user_guilds, "9999")
    assert denied_foreign is None
