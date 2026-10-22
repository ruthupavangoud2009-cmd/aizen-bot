import pytest
from src.security.owner import OWNER_ID, is_primary_owner, authorize_owner

class FakeDB:
    async def execute(self, *args): pass

class FakeBot:
    db = FakeDB()

class FakeResponse:
    def __init__(self): self.sent = None
    def is_done(self): return False
    async def send_message(self, *args, **kwargs): self.sent = (args, kwargs)

class FakeInteraction:
    def __init__(self): self.response = FakeResponse()

class FakeUser:
    def __init__(self, user_id): self.id = user_id

class FakeCtx:
    def __init__(self, user_id, interaction=False):
        self.author = FakeUser(user_id); self.bot = FakeBot()
        self.interaction = FakeInteraction() if interaction else None
        self.sent = None
    async def send(self, *args, **kwargs): self.sent = (args, kwargs)

@pytest.mark.parametrize("interface", ["prefix", "slash"])
@pytest.mark.asyncio
async def test_only_configured_owner_authorized(interface):
    owner = FakeCtx(OWNER_ID, interface == "slash")
    outsider = FakeCtx(OWNER_ID + 1, interface == "slash")
    assert is_primary_owner(OWNER_ID)
    assert await authorize_owner(owner, "test") is True
    assert await authorize_owner(outsider, "test") is False
    if interface == "slash":
        assert outsider.interaction.response.sent[1]["ephemeral"] is True
    else:
        assert "not authorized" in outsider.sent[0][0].lower()


def test_names_roles_and_invalid_ids_never_authorize():
    assert not is_primary_owner(None)
    assert not is_primary_owner("not-an-id")
    assert not is_primary_owner(1505515188991033408)
