import pytest


@pytest.fixture(autouse=True)
def _no_auto_register(monkeypatch):
    """No test may register a real DID; tests of the registration opt back in."""
    monkeypatch.setenv("MOLTRUST_NO_AUTO_REGISTER", "1")
