"""Register a MolTrust DID for this installation on its first tool call.

What happens, once per installation and API URL:

1. An Ed25519 key pair is generated on this machine.
2. ``GET /identity/register-challenge`` fetches a challenge and a small
   proof-of-work seed.
3. ``POST /identity/register-pop`` sends the public key, a signature over the
   challenge, the proof-of-work nonce, a display name derived from the public
   key, the platform value ``usage-mcp`` and the source ``mcp-server``.
   The private key never leaves the machine.
4. The returned DID, the public key and the private key are written to
   ``~/.moltrust/mcp-identity.json`` with file mode 0600.

Later calls find the file and do nothing. A failure is logged as one line on
stderr and the tool call goes on unchanged: registration is never on the path
of the call that triggered it.

Opt out with the environment variable ``MOLTRUST_NO_AUTO_REGISTER=1``. Nothing
is registered when ``MOLTRUST_API_KEY`` or ``MOLTRUST_DID`` is set (the caller
already has an identity), when the ``CI`` environment
variable is set, or on the HTTP transport (only the local stdio process
registers itself).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger("moltrust_mcp_server.autoregister")

ENV_OPT_OUT = "MOLTRUST_NO_AUTO_REGISTER"
ENV_IDENTITY_FILE = "MOLTRUST_IDENTITY_FILE"
ENV_PLATFORM = "MOLTRUST_REGISTER_PLATFORM"
ENV_DID = "MOLTRUST_DID"

DEFAULT_PLATFORM = "usage-mcp"
SOURCE = "mcp-server"
FRAMEWORK = "mcp"
DEFAULT_FILE = Path.home() / ".moltrust" / "mcp-identity.json"
TIMEOUT = 10.0
# A second process that finds a lock younger than this assumes the first one
# is still registering and leaves it alone; an older lock is a crashed run.
LOCK_STALE_SECONDS = 120
FILE_FORMAT = 1

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Identity:
    did: str
    public_key: str
    api_url: str


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def disabled_reason() -> str | None:
    """Why nothing is registered, or None when registration may run."""
    if _env_true(ENV_OPT_OUT):
        return ENV_OPT_OUT
    if os.environ.get(ENV_DID, "").strip():
        return ENV_DID
    # An API key belongs to a registered agent, so this caller already has a DID.
    if os.environ.get("MOLTRUST_API_KEY", "").strip():
        return "MOLTRUST_API_KEY"
    if os.environ.get("CI", "").strip():
        return "CI"
    return None


def identity_file() -> Path:
    raw = os.environ.get(ENV_IDENTITY_FILE, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_FILE


def platform() -> str:
    return os.environ.get(ENV_PLATFORM, "").strip() or DEFAULT_PLATFORM


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load(api_url: str, path: Path | None = None) -> Identity | None:
    """The identity stored for `api_url`, if this installation has one."""
    entry = (_read(path or identity_file()).get("identities") or {}).get(api_url)
    if not isinstance(entry, dict) or not entry.get("did"):
        return None
    return Identity(
        did=entry["did"], public_key=entry.get("public_key", ""), api_url=api_url
    )


def _write(path: Path, api_url: str, entry: dict) -> None:
    data = _read(path)
    stored = data.get("identities")
    identities: dict = stored if isinstance(stored, dict) else {}
    identities[api_url] = entry
    data = {"format": FILE_FORMAT, "identities": identities}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _acquire_lock(path: Path) -> Path | None:
    lock = path.with_name(path.name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
            lock.unlink()
    except FileNotFoundError:
        pass
    try:
        os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        return None
    return lock


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _leading_zero_bits(digest: bytes) -> int:
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8
            continue
        return n + 8 - byte.bit_length()
    return n


def solve_pow(seed: str, bits: int) -> str:
    """Smallest hex counter whose sha256(seed + nonce) has `bits` leading zero bits."""
    i = 0
    while True:
        nonce = format(i, "x")
        if (
            _leading_zero_bits(
                hashlib.sha256(f"{seed}{nonce}".encode("ascii")).digest()
            )
            >= bits
        ):
            return nonce
        i += 1


async def _register(http: httpx.AsyncClient, version: str) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex()
    )
    priv = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ).hex()

    ch = await http.get("/identity/register-challenge")
    ch.raise_for_status()
    challenge_doc = ch.json()
    challenge = challenge_doc["challenge"]
    pow_doc = challenge_doc.get("pow") or {}
    nonce = await asyncio.to_thread(
        solve_pow,
        pow_doc.get("seed", challenge.split(".", 1)[0]),
        int(pow_doc.get("difficulty_bits", 0)),
    )

    body = {
        "public_key": pub,
        "challenge": challenge,
        "signature": _b64url(key.sign(challenge.encode("ascii"))),
        "pow_nonce": nonce,
        # The registry refuses a second agent with the same name and platform
        # within 24 hours, so the name carries part of the key.
        "display_name": f"mcp-server-{pub[:12]}",
        "platform": platform(),
        "source": SOURCE,
        "framework": FRAMEWORK,
    }
    resp = await http.post(
        "/identity/register-pop",
        json=body,
        headers={"User-Agent": f"moltrust-mcp-server/{version}"},
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"register-pop answered HTTP {resp.status_code}")
    did = resp.json().get("did")
    if not did:
        raise RuntimeError("register-pop answered without a DID")
    return {
        "did": did,
        "public_key": pub,
        "private_key": priv,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "package": f"moltrust-mcp-server/{version}",
        "platform": body["platform"],
    }


async def ensure(
    api_url: str, version: str, transport: httpx.AsyncBaseTransport | None = None
) -> Identity | None:
    """Return this installation's DID, registering one if there is none yet.

    Never raises. Returns None when registration is disabled, already running in
    another process, or failed.
    """
    try:
        if disabled_reason():
            return None
        path = identity_file()
        found = load(api_url, path)
        if found:
            return found
        lock = _acquire_lock(path)
        if lock is None:
            return None
        try:
            found = load(api_url, path)
            if found:
                return found
            async with httpx.AsyncClient(
                base_url=api_url, timeout=TIMEOUT, transport=transport
            ) as http:
                entry = await _register(http, version)
            _write(path, api_url, entry)
        finally:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
        log.warning(
            "MolTrust: registered %s for this installation (stored in %s). "
            "Opt out: %s=1",
            entry["did"],
            path,
            ENV_OPT_OUT,
        )
        return Identity(
            did=entry["did"], public_key=entry["public_key"], api_url=api_url
        )
    except Exception as exc:  # noqa: BLE001 - registration must never break the tool call
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        log.warning("MolTrust: automatic DID registration skipped (%s)", reason)
        return None
