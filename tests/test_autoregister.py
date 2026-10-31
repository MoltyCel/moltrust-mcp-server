"""One-time DID registration on the first tool call (autoregister.py)."""

import base64
import hashlib
import json
import os
import stat

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from moltrust_mcp_server import autoregister

API = "https://api.example.test"
BITS = 6


def _zero_bits(digest: bytes) -> int:
    n = 0
    for b in digest:
        if b == 0:
            n += 8
            continue
        return n + 8 - b.bit_length()
    return n


class FakeRegistry:
    """Checks what the real register-pop checks: signature and proof-of-work."""

    def __init__(self, fail_status: int | None = None):
        self.fail_status = fail_status
        self.posts: list[dict] = []
        self.gets = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/identity/register-challenge":
            self.gets += 1
            return httpx.Response(200, json={
                "challenge": "abcd1234.9999999999.tag",
                "pow": {"difficulty_bits": BITS, "seed": "abcd1234"},
            })
        if request.url.path == "/identity/register-pop":
            body = json.loads(request.content)
            self.posts.append(body)
            if self.fail_status:
                return httpx.Response(self.fail_status, json={"detail": "nope"})
            sig = base64.urlsafe_b64decode(body["signature"] + "=" * (-len(body["signature"]) % 4))
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(body["public_key"])).verify(
                sig, body["challenge"].encode("ascii"))
            digest = hashlib.sha256(f"abcd1234{body['pow_nonce']}".encode()).digest()
            assert _zero_bits(digest) >= BITS
            return httpx.Response(200, json={"did": "did:moltrust:" + body["public_key"][:16]})
        return httpx.Response(404)


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in ("MOLTRUST_NO_AUTO_REGISTER", "MOLTRUST_DID", "MOLTRUST_API_KEY",
                 "CI", "MOLTRUST_REGISTER_PLATFORM"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "identity.json"
    monkeypatch.setenv("MOLTRUST_IDENTITY_FILE", str(path))
    return path


async def test_first_call_registers_once_and_second_call_reuses_it(env):
    reg = FakeRegistry()
    first = await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg))
    second = await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg))
    assert first and second and first.did == second.did
    assert len(reg.posts) == 1 and reg.gets == 1
    body = reg.posts[0]
    assert body["platform"] == "usage-mcp"
    assert body["source"] == "mcp-server"
    assert body["display_name"] == "mcp-server-" + body["public_key"][:12]
    assert "private_key" not in json.dumps(body)


async def test_the_identity_file_is_private_and_holds_the_key(env):
    await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(FakeRegistry()))
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600
    entry = json.loads(env.read_text())["identities"][API]
    assert len(entry["private_key"]) == 64 and entry["did"].startswith("did:moltrust:")


@pytest.mark.parametrize("name,value", [
    ("MOLTRUST_NO_AUTO_REGISTER", "1"),
    ("MOLTRUST_DID", "did:moltrust:0123456789abcdef"),
    ("MOLTRUST_API_KEY", "mt_whatever"),
    ("CI", "true"),
])
async def test_nothing_is_sent_when_disabled(env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    reg = FakeRegistry()
    assert await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg)) is None
    assert reg.gets == 0 and not reg.posts and not env.exists()


async def test_a_failed_registration_returns_none_and_stores_nothing(env):
    reg = FakeRegistry(fail_status=500)
    assert await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg)) is None
    assert not env.exists()
    assert not env.with_name(env.name + ".lock").exists()


async def test_an_unreachable_api_returns_none(env):
    def boom(request):
        raise httpx.ConnectError("down")
    assert await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(boom)) is None


async def test_a_lock_held_by_another_process_means_no_second_registration(env):
    env.parent.mkdir(parents=True, exist_ok=True)
    env.with_name(env.name + ".lock").write_text("")
    reg = FakeRegistry()
    assert await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg)) is None
    assert not reg.posts


async def test_the_platform_can_be_overridden(env, monkeypatch):
    monkeypatch.setenv("MOLTRUST_REGISTER_PLATFORM", "custom")
    reg = FakeRegistry()
    await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg))
    assert reg.posts[0]["platform"] == "custom"


async def test_identities_are_kept_per_api_url(env):
    reg = FakeRegistry()
    a = await autoregister.ensure(API, "9.9.9", transport=httpx.MockTransport(reg))
    b = await autoregister.ensure("https://other.example.test", "9.9.9",
                                  transport=httpx.MockTransport(reg))
    assert a.did != b.did and len(reg.posts) == 2


class _Ctx:
    def __init__(self, request):
        self.request_context = type("RC", (), {"request": request})()


async def test_the_first_stdio_tool_call_starts_one_registration(monkeypatch):
    from moltrust_mcp_server import server

    calls = []

    async def fake_ensure(api_url, version):
        calls.append(api_url)

    monkeypatch.setattr(server, "_autoregister_task", None)
    monkeypatch.setattr(server.autoregister, "ensure", fake_ensure)
    client = server.MolTrustClient(http=None, api_url=API)  # type: ignore[arg-type]
    server._maybe_autoregister(_Ctx(None), client)
    server._maybe_autoregister(_Ctx(None), client)
    await server._autoregister_task
    assert calls == [API]


async def test_the_http_transport_never_registers(monkeypatch):
    from moltrust_mcp_server import server

    calls = []

    async def fake_ensure(api_url, version):
        calls.append(api_url)

    monkeypatch.setattr(server, "_autoregister_task", None)
    monkeypatch.setattr(server.autoregister, "ensure", fake_ensure)
    client = server.MolTrustClient(http=None, api_url=API)  # type: ignore[arg-type]
    server._maybe_autoregister(_Ctx(object()), client)
    assert server._autoregister_task is None and calls == []
