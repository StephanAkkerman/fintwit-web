import pytest

from app import config
from app.services.ibkr import default_ibkr_port

INTEGRATION_VARS = (
    "X_AUTH_TOKEN",
    "X_CT0",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_PERSONAL_USE",
    "REDDIT_SECRET",
    "IBKR_ENABLED",
    "SIGNA_KEY",
    "CLOUDFLARE_ACCESS_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_ACCESS_APP_ID",
    "CLOUDFLARE_ACCESS_POLICY_ID",
    "CHART_ENABLED",
    "API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for name in INTEGRATION_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("X_CURL_PATH", str(tmp_path / "missing.txt"))
    return monkeypatch


@pytest.mark.parametrize(
    "host,mode,port",
    [
        ("ibgateway", "live", 4003),
        ("ibgateway", "paper", 4004),
        ("127.0.0.1", "live", 4001),
        ("127.0.0.1", "PAPER", 4002),
        ("ibgateway", None, 4003),
    ],
)
def test_default_ibkr_port(monkeypatch, host, mode, port):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    assert default_ibkr_port(host, mode) == port


def test_default_ibkr_port_reads_trading_mode(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    assert default_ibkr_port("ibgateway") == 4004


def test_integration_status_defaults_to_off(clean_env):
    status = config.integration_status()
    assert status["X timeline"].startswith("off")
    assert status["Reddit"] == "unauthenticated fallback"
    assert status["IBKR"] == "off"
    assert status["Signa"] == "off"
    assert status["Access admin"] == "off"
    assert status["chart recognition"] == "on"
    assert status["API key"] == "off"


def test_integration_status_reports_configured(clean_env):
    clean_env.setenv("X_AUTH_TOKEN", "tok")
    clean_env.setenv("X_CT0", "csrf")
    clean_env.setenv("REDDIT_PERSONAL_USE", "id")
    clean_env.setenv("REDDIT_SECRET", "secret")
    clean_env.setenv("IBKR_ENABLED", "true")
    clean_env.setenv("SIGNA_KEY", "key")
    clean_env.setenv("API_KEY", "key")

    status = config.integration_status()

    assert status["X timeline"] == "cookies"
    assert status["Reddit"] == "authenticated"
    assert status["IBKR"] == "on"
    assert status["Signa"] == "on"
    assert status["API key"] == "on"


def test_integration_summary_is_one_line(clean_env):
    summary = config.integration_summary()
    assert "\n" not in summary
    assert "X timeline: off" in summary
