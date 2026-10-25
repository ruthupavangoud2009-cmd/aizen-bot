import pytest
import sqlite3
from src.security.adult_guard import (
    add_adult_user,
    remove_adult_user,
    list_adult_users,
    is_adult_authorized,
    _get_adult_db,
    OWNER_ID,
)

def test_primary_owner_always_authorized():
    assert is_adult_authorized(OWNER_ID) is True
    assert is_adult_authorized(1505515188991033409) is True

def test_unauthorized_user_denied():
    random_user_id = 999999999988888888
    # Ensure user is not currently in allowlist
    remove_adult_user(random_user_id, removed_by=OWNER_ID)
    assert is_adult_authorized(random_user_id) is False

def test_add_and_immediate_authorization():
    test_uid = 123456789012345678
    assert add_adult_user(test_uid, added_by=OWNER_ID, notes="Trusted test user") is True
    # Immediate check
    assert is_adult_authorized(test_uid) is True

    # Check database persistence
    users = list_adult_users()
    matched = [u for u in users if u["user_id"] == test_uid]
    assert len(matched) == 1
    assert matched[0]["notes"] == "Trusted test user"

def test_immediate_revocation():
    test_uid = 123456789012345678
    assert remove_adult_user(test_uid, removed_by=OWNER_ID, notes="Revoked access") is True
    # Immediate check - zero delay
    assert is_adult_authorized(test_uid) is False

    # Check database persistence
    users = list_adult_users()
    matched = [u for u in users if u["user_id"] == test_uid]
    assert len(matched) == 0

def test_cannot_revoke_primary_owner():
    assert remove_adult_user(OWNER_ID, removed_by=OWNER_ID) is False
    assert is_adult_authorized(OWNER_ID) is True
