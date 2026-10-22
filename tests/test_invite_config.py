from src.core import config


def test_application_id_validation():
    assert config._parse_application_id("123456789") == 123456789
    assert config._parse_application_id("") is None
    assert config._parse_application_id("not-an-id") is None
    assert config._parse_application_id("0") is None
    assert config._parse_application_id(str(2**64)) is None
    assert config._parse_application_id("9" * 5000) is None


def test_invite_url_uses_runtime_application_id(monkeypatch):
    monkeypatch.setattr(config.Config, "INVITE_URL", "")
    monkeypatch.setattr(config.Config, "CLIENT_ID", 111)

    url = config.get_invite_url(222)

    assert url == (
        "https://discord.com/oauth2/authorize?client_id=222"
        "&permissions=8&integration_type=0&scope=applications.commands+bot"
    )


def test_invite_url_uses_configured_client_id_without_runtime_id(monkeypatch):
    monkeypatch.setattr(config.Config, "INVITE_URL", "")
    monkeypatch.setattr(config.Config, "CLIENT_ID", 111)

    assert "client_id=111" in config.get_invite_url()


def test_invite_url_override(monkeypatch):
    custom_url = "https://discord.com/oauth2/authorize?client_id=333"
    monkeypatch.setattr(config.Config, "INVITE_URL", custom_url)
    monkeypatch.setattr(config.Config, "CLIENT_ID", None)

    assert config.get_invite_url() == custom_url


def test_invite_url_missing_id(monkeypatch):
    monkeypatch.setattr(config.Config, "INVITE_URL", "")
    monkeypatch.setattr(config.Config, "CLIENT_ID", None)

    assert config.get_invite_url() is None
