"""Every tool says what it does to the world, and every parameter says what it is.

A client decides from tools/list whether it may run a tool without asking its
user, and a model fills in parameters from the schema, not from the prose under
Args:. Both read what the server publishes, so that is what these tests read.

The sets below are the classification, checked against the code of the route
each tool calls. A new tool, or a tool that starts charging, has to be placed
here by hand: the test fails until it is.
"""

import pytest

from moltrust_mcp_server.server import mcp

# Moves money: charges the caller (credits or x402), moves credits, books a
# deposit, or makes us pay gas for an on-chain write. Stays behind the client's
# confirmation.
MONEY = {
    "moltrust_register",           # 1 credit once the key has a DID; anchor + ERC-8004 gas
    "moltrust_rate",               # 1 credit; ERC-8004 feedback gas
    "moltrust_credential",         # 2 credits per issue or verify, first issue free
    "moltrust_credits",            # transfer moves credits to another DID
    "moltrust_claim_deposit",      # books a USDC payment as credits
    "moltguard_credential_issue",  # x402 0.10 USDC
    "mt_shopping_issue_vc",        # x402 5.00 USDC
    "mt_travel_issue_vc",          # x402 5.00 USDC
    "mt_skill_issue_vc",           # x402 5.00 USDC
    "mt_fantasy_commit",           # 1 credit; anchor gas
    "mt_issue_badge",              # 5 USDC per its own description
    "mt_issue_music_credential",   # anchor gas
    "mt_fantasy_history",          # 1 credit, although it only reads
}

# Changes something and costs nobody anything: a client may run these without
# asking.
FREE_WRITE = {
    "mt_prediction_link",
    "mt_salesguard_register",
    "mt_create_interaction_proof",
    "mt_endorse_agent",
    "mt_register_seed",
    "mt_skill_audit",
}

IDEMPOTENT = {
    "moltrust_claim_deposit",   # tx_hash is unique, a repeat is a 409
    "mt_fantasy_commit",        # a repeat is a 409, and a 409 is not charged
    "mt_prediction_link",
    "mt_endorse_agent",
    "mt_register_seed",
    "mt_skill_audit",
}


@pytest.fixture(scope="module")
async def tools():
    return await mcp.list_tools()


async def test_every_tool_is_classified(tools):
    names = {t.name for t in tools}
    assert MONEY <= names, sorted(MONEY - names)
    assert FREE_WRITE <= names, sorted(FREE_WRITE - names)
    assert not MONEY & FREE_WRITE


async def test_every_tool_carries_annotations(tools):
    bare = [t.name for t in tools if t.annotations is None or t.annotations.readOnlyHint is None]
    assert bare == []


async def test_annotations_match_the_classification(tools):
    wrong = []
    for t in tools:
        a = t.annotations
        if t.name in MONEY or t.name in FREE_WRITE:
            want = (False, t.name in MONEY, t.name in IDEMPOTENT)
            got = (a.readOnlyHint, a.destructiveHint, a.idempotentHint)
        else:
            want, got = True, a.readOnlyHint
        if got != want:
            wrong.append((t.name, got, want))
    assert wrong == []


async def test_only_money_tools_are_destructive(tools):
    destructive = {t.name for t in tools if t.annotations.destructiveHint}
    assert destructive == MONEY


async def test_every_parameter_has_a_description(tools):
    bare = [
        (t.name, p)
        for t in tools
        for p, schema in t.inputSchema.get("properties", {}).items()
        if not (schema.get("description") or "").strip()
    ]
    assert bare == []
