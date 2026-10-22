import datetime as dt
import importlib.util
from pathlib import Path
import pytest
_spec = importlib.util.spec_from_file_location("kyoka_premium_service", Path(__file__).parents[1] / "src" / "managers" / "premium_service.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
PremiumService, parse_duration = _module.PremiumService, _module.parse_duration

class FakeDB:
    def __init__(self, row=None, fail=False): self.row=row; self.fail=fail; self.calls=[]
    async def fetch_one(self, query, *args):
        self.calls.append((query,args))
        if self.fail: raise RuntimeError("database unavailable")
        return self.row

@pytest.mark.parametrize("value,seconds", [("30d",2592000),("2w",1209600),("12h",43200)])
def test_duration_parser(value, seconds): assert parse_duration(value).total_seconds() == seconds

def test_lifetime_duration(): assert parse_duration("lifetime") is None

def test_invalid_duration_rejected():
    with pytest.raises(ValueError): parse_duration("forever-and-a-day")

@pytest.mark.asyncio
async def test_expired_premium_is_denied():
    db=FakeDB({"tier":"pro","status":"active","expires_at":dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)})
    assert not await PremiumService(db).has_premium(scope="server",target_id=1)

@pytest.mark.asyncio
async def test_revoked_and_wrong_scope_are_denied():
    db=FakeDB({"tier":"pro","status":"revoked","expires_at":None})
    service=PremiumService(db)
    assert not await service.has_premium(scope="server",target_id=1)
    assert not await service.has_premium(scope="user",target_id=1)
    assert not await service.has_premium(scope="guild",target_id=1)

@pytest.mark.asyncio
async def test_database_failure_fails_closed():
    assert not await PremiumService(FakeDB(fail=True)).has_premium(scope="server",target_id=123)

@pytest.mark.asyncio
async def test_server_scope_uses_guild_table_not_user_table():
    db=FakeDB({"tier":"premium","status":"active","expires_at":None})
    assert await PremiumService(db).has_premium(scope="server",target_id=44)
    assert "guild_premium" in db.calls[0][0]
    assert "user_premium" not in db.calls[0][0]

class _AsyncCM:
    def __init__(self, value): self.value=value
    async def __aenter__(self): return self.value
    async def __aexit__(self, *args): return False

class _TxConn:
    def __init__(self): self.rows={"user_premium":{},"guild_premium":{}}
    def transaction(self): return _AsyncCM(None)
    async def fetchrow(self, query, target_id):
        table="guild_premium" if "guild_premium" in query else "user_premium"
        return self.rows[table].get(target_id)
    async def execute(self, query, *args):
        if query.startswith("INSERT INTO user_premium"):
            target,tier,expiry,actor,updated=args
            self.rows["user_premium"][target]={"tier":tier,"expires_at":expiry,"status":"active","activated_by":actor}
        elif query.startswith("INSERT INTO guild_premium"):
            target,tier,expiry,actor,updated=args
            self.rows["guild_premium"][target]={"tier":tier,"expires_at":expiry,"status":"active","activated_by":actor}
        elif query.startswith("UPDATE user_premium"):
            target,updated=args; self.rows["user_premium"][target]["status"]="revoked"
        elif query.startswith("UPDATE guild_premium"):
            target,updated=args; self.rows["guild_premium"][target]["status"]="revoked"

class _TxDB:
    def __init__(self): self.conn=_TxConn(); self.pool=self
    def acquire(self): return _AsyncCM(self.conn)
    async def fetch_one(self, query, target_id):
        table="guild_premium" if "guild_premium" in query else "user_premium"
        row=self.conn.rows[table].get(target_id)
        if not row: return None
        return {"target_id":target_id,**row,"created_at":None,"updated_at":None}

@pytest.mark.asyncio
async def test_grant_is_persistent_and_repeated_grant_does_not_stack():
    db=_TxDB(); service=PremiumService(db)
    first=await service.grant(scope="server",target_id=77,tier="premium",duration="30d",actor_id=OWNER_ID_FOR_TEST)
    second=await service.grant(scope="server",target_id=77,tier="premium",duration="30d",actor_id=OWNER_ID_FOR_TEST)
    assert first["expires_at"] == second["expires_at"]
    assert await service.has_premium(scope="server",target_id=77)

@pytest.mark.asyncio
async def test_extend_and_revoke_subscription_lifecycle():
    db=_TxDB(); service=PremiumService(db)
    first=await service.grant(scope="user",target_id=88,tier="pro",duration="7d",actor_id=OWNER_ID_FOR_TEST)
    extended=await service.grant(scope="user",target_id=88,tier="pro",duration="7d",actor_id=OWNER_ID_FOR_TEST,extend_existing=True)
    assert extended["expires_at"] > first["expires_at"]
    assert await service.revoke(scope="user",target_id=88,actor_id=OWNER_ID_FOR_TEST)
    assert not await service.has_premium(scope="user",target_id=88)

OWNER_ID_FOR_TEST = 1505515188991033409
