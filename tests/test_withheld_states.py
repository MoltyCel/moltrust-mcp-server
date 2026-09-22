"""Withheld is not "not found", and the tools have to say so.

`verified: false` covers two findings that mean opposite things to whoever reads
the answer. One is that we looked and there is nothing — a did:moltrust we never
registered. The other is that we hold no opinion: the DID belongs to a method we
do not issue, or the score has too few endorsers behind it. The API has always
separated them with `withheld`, `withheld_reason` and a `note` that says in so
many words "Withheld is not a negative finding."

Through 1.2.3 the package threw that away. Probing the hosted origin on
2026-09-22, `did:web:example.com` came back as:

    DID:      did:web:example.com
    Verified: No
    Agent not found in MolTrust registry.

Three states, one of them mislabelled as its opposite. `moltrust_verify`,
`mt_get_badge` and `moltrust_erc8004` rendered no withheld at all;
`mt_get_trust_score` rendered it but asserted one fixed reason for every case,
so a foreign DID was reported as short of endorsers.

The vectors in `withheld_vectors.json` are recorded against the live API rather
than written by hand, because the claim under test is that the package renders
what the API actually sends.
"""

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from moltrust_mcp_server.server import MolTrustClient, _withheld_lines, mcp

VECTORS = json.loads(
    (pathlib.Path(__file__).parent / "withheld_vectors.json").read_text()
)["vectors"]

OURS = "did:moltrust:157224190be24072"
FOREIGN = "did:web:example.com"


def _resp(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code=status, json=body,
                          request=httpx.Request("GET", "https://api.moltrust.ch/t"))


@pytest.fixture
def client():
    return MolTrustClient(http=AsyncMock(spec=httpx.AsyncClient),
                          api_url="https://api.moltrust.ch")


def _ctx(client):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = client
    req = MagicMock()
    req.query_params = {}
    req.headers = {"x-api-key": "mt_test_key"}
    ctx.request_context.request = req
    return ctx


async def _call(tool: str, client, **kwargs) -> str:
    return await mcp._tool_manager._tools[tool].fn(ctx=_ctx(client), **kwargs)


# ---------------------------------------------------------------------------
# The renderer itself
# ---------------------------------------------------------------------------

def test_a_plain_answer_is_left_alone():
    assert _withheld_lines({"withheld": False}, subject="Verified") is None
    assert _withheld_lines({}, subject="Verified") is None


def test_the_reason_and_note_are_carried_verbatim():
    note = "MolTrust issues did:moltrust identifiers. …Withheld is not a negative finding."
    out = _withheld_lines(
        {"withheld": True, "withheld_reason": "did_method_not_issued_here", "note": note},
        subject="Verified")
    assert "WITHHELD" in out[0]
    assert "did_method_not_issued_here" in "\n".join(out)
    assert note in "\n".join(out), "the note must survive intact, not be paraphrased"


def test_the_api_reason_beats_the_callers_fallback():
    """mt_get_trust_score asserted "fewer than 3 endorsers" for every withheld
    score, which is wrong for a foreign DID. The fallback only fills a gap."""
    out = _withheld_lines({"withheld": True, "withheld_reason": "did_method_not_issued_here"},
                          subject="Score", default_reason="fewer than 3 independent endorsers")
    assert "did_method_not_issued_here" in "\n".join(out)
    assert "endorser" not in "\n".join(out)


def test_the_fallback_fills_a_bare_flag():
    """/identity/badge/ sends withheld with no reason and no note."""
    out = _withheld_lines({"withheld": True}, subject="Badge Status",
                          default_reason="the score is withheld")
    assert "the score is withheld" in "\n".join(out)


# ---------------------------------------------------------------------------
# Three states, per tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_renders_a_verified_agent(client):
    client.http.get = AsyncMock(side_effect=[
        _resp(200, {"did": OURS, "verified": True, "withheld": False}),
        _resp(200, {"name": "moltrust-vet", "platform": "clawhub",
                    "trust": {"score": 4.2, "totalRatings": 7, "baseAnchor": True}}),
    ])
    out = await _call("moltrust_verify", client, did=OURS)
    assert "Verified: Yes" in out
    assert "WITHHELD" not in out


@pytest.mark.asyncio
async def test_verify_renders_a_genuine_absence(client):
    """Our own method, no registration: "not found" is the correct answer and
    must survive this change."""
    absent = "did:moltrust:0000000000000000"
    client.http.get = AsyncMock(side_effect=[
        _resp(200, {"did": absent, "verified": False, "withheld": False}),
        _resp(404, {}),
    ])
    out = await _call("moltrust_verify", client, did=absent)
    assert "Verified: No" in out
    assert "Agent not found in MolTrust registry." in out
    assert "WITHHELD" not in out


@pytest.mark.asyncio
async def test_verify_never_calls_a_withheld_answer_not_found(client):
    """The 2026-09-22 defect, in one assertion."""
    note = "MolTrust issues did:moltrust identifiers. Withheld is not a negative finding."
    client.http.get = AsyncMock(side_effect=[
        _resp(200, {"did": FOREIGN, "verified": False, "withheld": True,
                    "withheld_reason": "did_method_not_issued_here", "note": note}),
        _resp(404, {}),
    ])
    out = await _call("moltrust_verify", client, did=FOREIGN)
    assert "WITHHELD" in out
    assert "did_method_not_issued_here" in out
    assert note in out
    assert "not found" not in out.lower(), out


@pytest.mark.asyncio
async def test_trust_score_names_the_reason_the_api_gave(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "did": FOREIGN, "withheld": True,
        "withheld_reason": "did_method_not_issued_here",
        "note": "A withheld score is not a low score.", "endorser_count": 0}))
    out = await _call("mt_get_trust_score", client, did=FOREIGN)
    assert "WITHHELD" in out
    assert "did_method_not_issued_here" in out
    assert "fewer than 3" not in out, "the hardcoded reason must not override the API"


@pytest.mark.asyncio
async def test_trust_score_keeps_the_endorser_reason_when_the_api_gives_none(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "did": OURS, "withheld": True, "endorser_count": 1}))
    out = await _call("mt_get_trust_score", client, did=OURS)
    assert "WITHHELD" in out
    assert "fewer than 3 independent endorsers" in out


@pytest.mark.asyncio
async def test_trust_score_renders_a_real_score(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "did": OURS, "withheld": False, "trust_score": 72, "grade": "B",
        "endorser_count": 5, "breakdown": {}}))
    out = await _call("mt_get_trust_score", client, did=OURS)
    assert "Score: 72" in out
    assert "WITHHELD" not in out


@pytest.mark.asyncio
async def test_badge_reports_a_withheld_score_as_withheld(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "did": OURS, "verified": False, "withheld": True, "score": None,
        "verify_url": f"https://api.moltrust.ch/identity/verify/{OURS}"}))
    out = await _call("mt_get_badge", client, did=OURS)
    assert "WITHHELD" in out
    assert "Not Verified" not in out


@pytest.mark.asyncio
async def test_badge_still_reports_an_unverified_agent(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "did": OURS, "verified": False, "withheld": False,
        "trust_score": 12, "grade": "D", "badge_url": "u", "verify_url": "v"}))
    out = await _call("mt_get_badge", client, did=OURS)
    assert "Not Verified" in out
    assert "WITHHELD" not in out


@pytest.mark.asyncio
async def test_erc8004_resolve_shows_a_withheld_moltrust_score(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "agent_id": 21351, "chain": "base", "chain_id": 8453,
        "owner": "0x1", "agent_wallet": "0x1",
        "moltrust_did": OURS,
        "moltrust_trust_score": {"score": None, "grade": None, "withheld": True,
                                 "verify_url": "https://api.moltrust.ch/x"},
        "onchain_reputation": {"count": 0}}))
    out = await _call("moltrust_erc8004", client, action="resolve", agent_id=21351)
    assert "WITHHELD" in out
    assert "https://api.moltrust.ch/x" in out


@pytest.mark.asyncio
async def test_erc8004_resolve_shows_a_real_moltrust_score(client):
    client.http.get = AsyncMock(return_value=_resp(200, {
        "agent_id": 21351, "chain": "base", "chain_id": 8453,
        "owner": "0x1", "agent_wallet": "0x1",
        "moltrust_trust_score": {"score": 61, "grade": "B", "withheld": False},
        "onchain_reputation": {"count": 0}}))
    out = await _call("moltrust_erc8004", client, action="resolve", agent_id=21351)
    assert "61" in out
    assert "WITHHELD" not in out


# ---------------------------------------------------------------------------
# The vectors: recorded from the live API, not invented here
# ---------------------------------------------------------------------------

def test_the_vectors_cover_every_tool_that_can_receive_withheld():
    """Four endpoints emit `withheld`, and four tools consume them. A fifth
    tool reaching a withheld endpoint without a vector here is the gap this
    asserts against."""
    covered = {v["tool"] for v in VECTORS if v["withheld_payload"]}
    assert covered == {"moltrust_verify", "mt_get_trust_score",
                       "mt_get_badge", "moltrust_erc8004"}


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if v["withheld_payload"]],
    ids=lambda v: f"{v['tool']}::{v['path'][:40]}")
@pytest.mark.asyncio
async def test_every_withheld_response_reaches_the_reader_as_withheld(vector, client):
    """The rule, over real responses: if the API withheld, the text says so."""
    client.http.get = AsyncMock(return_value=_resp(200, vector["response"]))
    tool = vector["tool"]
    if tool == "moltrust_erc8004":
        out = await _call(tool, client, action="resolve", agent_id=21351)
    elif tool == "moltrust_verify":
        # verify fetches the agent card alongside; the second call 404s.
        client.http.get = AsyncMock(side_effect=[
            _resp(200, vector["response"]), _resp(404, {})])
        out = await _call(tool, client, did=vector["response"].get("did", OURS))
    else:
        out = await _call(tool, client, did=vector["response"].get("did", OURS))
    assert "withheld" in out.lower(), f"{tool} dropped it: {out[:200]}"
    assert "not found" not in out.lower(), f"{tool} called it not found: {out[:200]}"


@pytest.mark.asyncio
async def test_the_control_vector_is_not_reported_as_withheld(client):
    """A recorded response with withheld=false must not pick the withheld text
    up — a renderer that says WITHHELD to everything would pass the rule above."""
    ctrl = next(v for v in VECTORS if not v["withheld_payload"])
    client.http.get = AsyncMock(side_effect=[_resp(200, ctrl["response"]), _resp(404, {})])
    out = await _call(ctrl["tool"], client, did=ctrl["response"]["did"])
    assert "withheld" not in out.lower()
