"""MolTrust MCP Server — Trust Infrastructure for AI Agents."""

import json
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

API_URL_DEFAULT = "https://api.moltrust.ch"
GUARD_PREFIX = "/guard"
TIMEOUT = 30.0
VERSION = "1.0.0"


@dataclass
class MolTrustClient:
    http: httpx.AsyncClient
    api_key: str
    api_url: str


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[MolTrustClient]:
    api_key = os.environ.get("MOLTRUST_API_KEY", "")
    api_url = os.environ.get("MOLTRUST_API_URL", API_URL_DEFAULT).rstrip("/")

    async with httpx.AsyncClient(
        base_url=api_url,
        timeout=TIMEOUT,
        headers={"User-Agent": f"moltrust-mcp-server/{VERSION}"},
    ) as http:
        yield MolTrustClient(http=http, api_key=api_key, api_url=api_url)


mcp = FastMCP(
    "moltrust",
    instructions=(
        "MolTrust — Trust Infrastructure for AI Agents. "
        "Register agents, verify identities, query reputation scores, "
        "rate agents, manage W3C Verifiable Credentials, query "
        "ERC-8004 on-chain agent registries on Base, score wallet trust, "
        "detect Sybil wallets, check prediction market integrity, "
        "track prediction market wallet performance and leaderboards, "
        "verify shopping/travel/skill credentials, and audit agent skills."
    ),
    lifespan=lifespan,
)


def _client(ctx: Context[ServerSession, MolTrustClient]) -> MolTrustClient:
    return ctx.request_context.lifespan_context


def _auth_headers(client: MolTrustClient) -> dict[str, str]:
    return {"X-API-Key": client.api_key}


def _fmt(data: dict) -> str:
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def moltrust_register(
    display_name: str,
    platform: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Register a new AI agent on MolTrust.

    Creates a decentralised identity (DID), issues a W3C Verifiable Credential,
    and anchors the agent on the Base blockchain.

    Args:
        display_name: Agent name (1-64 chars, alphanumeric/dash/underscore/dot/space)
        platform: Platform identifier (e.g. "openai", "langchain", "custom")
    """
    client = _client(ctx)
    if not client.api_key:
        return "Error: MOLTRUST_API_KEY environment variable is not set."

    resp = await client.http.post(
        "/identity/register",
        json={"display_name": display_name, "platform": platform},
        headers=_auth_headers(client),
    )

    if resp.status_code == 409:
        return f"Duplicate: An agent named '{display_name}' on '{platform}' was already registered in the last 24 hours."
    if resp.status_code == 429:
        return "Rate limit exceeded. Max 5 registrations per API key per hour."
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    did = data.get("did", "?")
    anchor = data.get("base_anchor", {})
    tx = anchor.get("tx_hash") if anchor else None

    lines = [
        "Agent registered successfully!",
        "",
        f"DID:      {did}",
        f"Name:     {data.get('display_name')}",
        f"Status:   {data.get('status')}",
    ]
    if tx:
        lines.append(f"Base TX:  {anchor.get('explorer', tx)}")

    cred = data.get("credential")
    if cred:
        lines.append("")
        lines.append(f"Credential issued: {', '.join(cred.get('type', []))}")
        lines.append(f"Issuer:    {cred.get('issuer')}")
        lines.append(f"Expires:   {cred.get('expirationDate')}")

    return "\n".join(lines)


@mcp.tool()
async def moltrust_verify(
    did: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify an AI agent by its DID.

    Checks whether the DID is registered and returns verification status
    along with the agent's trust card (reputation, credentials, blockchain anchor).

    Args:
        did: Decentralised identifier (e.g. "did:moltrust:a1b2c3d4e5f60718")
    """
    client = _client(ctx)

    # Fetch verification status and trust card in parallel
    verify_resp, card_resp = await gather_requests(
        client.http.get(f"/identity/verify/{did}"),
        client.http.get(f"/a2a/agent-card/{did}"),
    )

    if verify_resp.status_code == 400:
        return "Invalid DID format. Expected: did:moltrust:<16 hex chars>"
    if verify_resp.status_code != 200:
        return f"Error {verify_resp.status_code}: {verify_resp.text}"

    v = verify_resp.json()
    verified = v.get("verified", False)

    lines = [
        f"DID:      {did}",
        f"Verified: {'Yes' if verified else 'No'}",
    ]

    if card_resp.status_code == 200:
        card = card_resp.json()
        trust = card.get("trust", {})
        lines.extend(
            [
                f"Name:     {card.get('name', '?')}",
                f"Platform: {card.get('platform', '?')}",
                f"Score:    {trust.get('score', 0)}/5 ({trust.get('totalRatings', 0)} ratings)",
                f"On-chain: {'Yes' if trust.get('baseAnchor') else 'No'}",
            ]
        )
        if trust.get("registeredAt"):
            lines.append(f"Registered: {trust['registeredAt']}")
        if trust.get("baseScanUrl"):
            lines.append(f"BaseScan: {trust['baseScanUrl']}")
    elif not verified:
        lines.append("Agent not found in MolTrust registry.")

    return "\n".join(lines)


@mcp.tool()
async def moltrust_reputation(
    did: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get the reputation score for an AI agent.

    Returns the aggregate trust score (1-5) and total number of ratings.

    Args:
        did: Decentralised identifier (e.g. "did:moltrust:a1b2c3d4e5f60718")
    """
    client = _client(ctx)

    resp = await client.http.get(f"/reputation/query/{did}")

    if resp.status_code == 400:
        return "Invalid DID format. Expected: did:moltrust:<16 hex chars>"
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    score = data.get("score", 0)
    total = data.get("total_ratings", 0)

    if total == 0:
        return f"DID: {did}\nReputation: No ratings yet."

    return f"DID: {did}\nScore: {score}/5\nTotal ratings: {total}"


@mcp.tool()
async def moltrust_rate(
    from_did: str,
    to_did: str,
    score: int,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Rate another AI agent (1-5 stars).

    Submit a trust rating from one agent to another.

    Args:
        from_did: Your agent's DID (the rater)
        to_did: Target agent's DID (the agent being rated)
        score: Rating from 1 (untrusted) to 5 (highly trusted)
    """
    client = _client(ctx)
    if not client.api_key:
        return "Error: MOLTRUST_API_KEY environment variable is not set."

    if score < 1 or score > 5:
        return "Error: Score must be between 1 and 5."

    resp = await client.http.post(
        "/reputation/rate",
        json={"from_did": from_did, "to_did": to_did, "score": score},
        headers=_auth_headers(client),
    )

    if resp.status_code == 400:
        return f"Bad request: {resp.json().get('detail', resp.text)}"
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    return (
        f"Rating submitted!\n"
        f"From: {data.get('from')}\n"
        f"To:   {data.get('to')}\n"
        f"Score: {data.get('score')}/5"
    )


@mcp.tool()
async def moltrust_credential(
    action: str,
    subject_did: str = "",
    credential_type: str = "AgentTrustCredential",
    credential: str = "",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue or verify a W3C Verifiable Credential.

    Args:
        action: Either "issue" or "verify"
        subject_did: DID of the credential subject (required for "issue")
        credential_type: Type of credential (default: "AgentTrustCredential", only for "issue")
        credential: JSON string of the credential to verify (required for "verify")
    """
    assert ctx is not None
    client = _client(ctx)

    if action == "issue":
        if not client.api_key:
            return "Error: MOLTRUST_API_KEY environment variable is not set."
        if not subject_did:
            return "Error: subject_did is required for issuing a credential."

        resp = await client.http.post(
            "/credentials/issue",
            json={"subject_did": subject_did, "credential_type": credential_type},
            headers=_auth_headers(client),
        )

        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        cred = resp.json()
        subject = cred.get("credentialSubject", {})
        rep = subject.get("reputation", {})

        lines = [
            "Credential issued!",
            "",
            f"Type:    {', '.join(cred.get('type', []))}",
            f"Issuer:  {cred.get('issuer')}",
            f"Subject: {subject.get('id')}",
            f"Issued:  {cred.get('issuanceDate')}",
            f"Expires: {cred.get('expirationDate')}",
        ]
        if rep:
            lines.append(
                f"Score:   {rep.get('score', 0)}/5 ({rep.get('total_ratings', 0)} ratings)"
            )
        lines.extend(["", "Full credential:", _fmt(cred)])
        return "\n".join(lines)

    elif action == "verify":
        if not credential:
            return "Error: credential JSON string is required for verification."

        try:
            cred_dict = json.loads(credential)
        except json.JSONDecodeError:
            return "Error: credential is not valid JSON."

        resp = await client.http.post(
            "/credentials/verify",
            json={"credential": cred_dict},
        )

        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        result = resp.json()
        valid = result.get("valid", False)

        lines = [f"Valid: {'Yes' if valid else 'No'}"]
        if result.get("issuer"):
            lines.append(f"Issuer:  {result['issuer']}")
        if result.get("subject"):
            lines.append(f"Subject: {result['subject']}")
        if result.get("credential_type"):
            lines.append(f"Type:    {result['credential_type']}")
        if result.get("expired") is not None:
            lines.append(f"Expired: {'Yes' if result['expired'] else 'No'}")
        if result.get("error"):
            lines.append(f"Error:   {result['error']}")
        return "\n".join(lines)

    else:
        return 'Error: action must be "issue" or "verify".'


@mcp.tool()
async def moltrust_credits(
    action: str,
    did: str = "",
    to_did: str = "",
    amount: int = 0,
    reference: str = "",
    limit: int = 20,
    offset: int = 0,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Manage MolTrust credits: check balance, view pricing, transfer credits, or view transaction history.

    Args:
        action: One of "balance", "pricing", "transfer", or "transactions"
        did: Agent DID (required for "balance" and "transactions")
        to_did: Recipient DID (required for "transfer")
        amount: Number of credits to transfer (required for "transfer", must be >= 1)
        reference: Optional reference string for transfers
        limit: Max transactions to return (default 20, for "transactions")
        offset: Pagination offset (default 0, for "transactions")
    """
    assert ctx is not None
    client = _client(ctx)

    if action == "balance":
        if not did:
            return "Error: did is required for balance check."
        resp = await client.http.get(f"/credits/balance/{did}")
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"
        data = resp.json()
        return f"DID: {data['did']}\nBalance: {data['balance']} {data['currency']}"

    elif action == "pricing":
        resp = await client.http.get("/credits/pricing")
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"
        data = resp.json()
        lines = [
            "MolTrust API Pricing",
            f"Free credits on registration: {data.get('free_on_registration', 100)}",
            "",
        ]
        pricing = data.get("pricing", {})
        free = []
        paid = []
        for endpoint, cost in sorted(pricing.items()):
            if cost == 0:
                free.append(endpoint)
            else:
                paid.append((endpoint, cost))
        if free:
            lines.append("Free endpoints:")
            for ep in free:
                lines.append(f"  {ep}")
        if paid:
            lines.append("")
            lines.append("Paid endpoints:")
            for ep, cost in paid:
                lines.append(f"  {ep}: {cost} credit{'s' if cost != 1 else ''}")
        return "\n".join(lines)

    elif action == "transfer":
        if not client.api_key:
            return "Error: MOLTRUST_API_KEY environment variable is not set."
        if not did:
            return "Error: did (sender) is required for transfer."
        if not to_did:
            return "Error: to_did (recipient) is required for transfer."
        if amount < 1:
            return "Error: amount must be at least 1."

        resp = await client.http.post(
            "/credits/transfer",
            json={
                "from_did": did,
                "to_did": to_did,
                "amount": amount,
                "reference": reference,
            },
            headers=_auth_headers(client),
        )
        if resp.status_code == 402:
            data = resp.json()
            return f"Insufficient credits: {data.get('error', 'balance too low')}"
        if resp.status_code == 403:
            return f"Forbidden: {resp.json().get('detail', 'API key does not own the source DID')}"
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        data = resp.json()
        return (
            f"Transfer successful!\n"
            f"From:    {data['from_did']}\n"
            f"To:      {data['to_did']}\n"
            f"Amount:  {data['amount']} {data['currency']}\n"
            f"Balance: {data['balance_after']} {data['currency']}"
        )

    elif action == "transactions":
        if not client.api_key:
            return "Error: MOLTRUST_API_KEY environment variable is not set."
        if not did:
            return "Error: did is required for transaction history."

        resp = await client.http.get(
            f"/credits/transactions/{did}",
            params={"limit": limit, "offset": offset},
            headers=_auth_headers(client),
        )
        if resp.status_code == 403:
            return f"Forbidden: {resp.json().get('detail', 'API key does not own this DID')}"
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        data = resp.json()
        txs = data.get("transactions", [])
        if not txs:
            return f"No transactions found for {did}."

        lines = [f"Transaction history for {did} ({len(txs)} entries):"]
        for tx in txs:
            direction = ""
            if tx.get("from_did") == did:
                direction = f"-> {tx.get('to_did', 'system')}"
            else:
                direction = f"<- {tx.get('from_did', 'system')}"
            lines.append(
                f"  [{tx['tx_type']}] {tx['amount']} credits {direction} "
                f"| bal: {tx['balance_after']} | {tx.get('created_at', '?')}"
            )
        return "\n".join(lines)

    else:
        return (
            'Error: action must be "balance", "pricing", "transfer", or "transactions".'
        )


@mcp.tool()
async def moltrust_deposit_info(
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get USDC deposit instructions to buy MolTrust credits.

    Returns the MolTrust wallet address on Base (Ethereum L2),
    USDC token contract, conversion rate (1 USDC = 100 credits),
    and step-by-step instructions.
    """
    client = _client(ctx)
    resp = await client.http.get("/credits/deposit-info")

    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    lines = [
        "USDC Deposit Instructions",
        "",
        f"Wallet:   {data.get('wallet', '?')}",
        f"Network:  {data.get('network', '?')}",
        f"Token:    {data.get('token', '?')}",
        f"Contract: {data.get('token_contract', '?')}",
        f"Rate:     {data.get('rate', '?')}",
        f"Min conf: {data.get('min_confirmations', '?')}",
        "",
    ]
    for step in data.get("instructions", []):
        lines.append(f"  {step}")

    return "\n".join(lines)


@mcp.tool()
async def moltrust_claim_deposit(
    tx_hash: str,
    did: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Claim MolTrust credits from a USDC deposit on Base.

    After sending USDC to the MolTrust wallet on Base (L2),
    submit the transaction hash to receive credits.
    1 USDC = 100 credits, verified on-chain.

    Args:
        tx_hash: Base blockchain transaction hash (0x...)
        did: Your agent's DID to credit
    """
    client = _client(ctx)
    if not client.api_key:
        return "Error: MOLTRUST_API_KEY environment variable is not set."

    tx_hash = tx_hash.strip()
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return "Error: tx_hash must be a 0x-prefixed 64-character hex string (e.g. 0xabc...def)."

    resp = await client.http.post(
        "/credits/deposit",
        json={"tx_hash": tx_hash, "did": did},
        headers=_auth_headers(client),
    )

    if resp.status_code == 400:
        return f"Verification failed: {resp.json().get('detail', resp.text)}"
    if resp.status_code == 403:
        return (
            f"Forbidden: {resp.json().get('detail', 'API key does not own this DID')}"
        )
    if resp.status_code == 409:
        return "This transaction has already been claimed."
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    return (
        f"Deposit successful!\n"
        f"\n"
        f"TX:       {data.get('tx_hash', '?')}\n"
        f"From:     {data.get('from_address', '?')}\n"
        f"USDC:     {data.get('usdc_amount', '?')}\n"
        f"Credits:  +{data.get('credits_granted', '?')}\n"
        f"Balance:  {data.get('new_balance', '?')} CREDITS\n"
        f"Rate:     {data.get('rate', '?')}\n"
        f"BaseScan: {data.get('basescan_url', '?')}"
    )


@mcp.tool()
async def moltrust_stats(
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get MolTrust network statistics.

    Returns total registered agents, credentials issued,
    ratings given, and other network health metrics.
    """
    client = _client(ctx)
    resp = await client.http.get("/stats")

    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    lines = ["MolTrust Network Statistics", ""]
    for key, value in data.items():
        label = key.replace("_", " ").title()
        lines.append(f"  {label}: {value}")

    return "\n".join(lines)


@mcp.tool()
async def moltrust_deposit_history(
    did: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get USDC deposit history for an agent.

    Args:
        did: The agent's DID
    """
    client = _client(ctx)
    if not client.api_key:
        return "Error: MOLTRUST_API_KEY environment variable is not set."

    resp = await client.http.get(
        f"/credits/deposits/{did}",
        headers=_auth_headers(client),
    )

    if resp.status_code == 403:
        return (
            f"Forbidden: {resp.json().get('detail', 'API key does not own this DID')}"
        )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    deposits = data.get("deposits", [])

    if not deposits:
        return f"No USDC deposits found for {did}."

    lines = [
        f"USDC Deposit History for {did}",
        f"Wallet: {data.get('wallet', '?')}",
        f"Network: {data.get('network', '?')}",
        "",
    ]
    for d in deposits:
        lines.append(
            f"  {d.get('usdc_amount', '?')} USDC -> {d.get('credits_granted', '?')} credits "
            f"| {d.get('claimed_at', '?')} | {d.get('basescan_url', '')}"
        )

    return "\n".join(lines)


@mcp.tool()
async def moltrust_erc8004(
    action: str,
    did: str = "",
    agent_id: int = 0,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Query the ERC-8004 on-chain agent registry on Base.

    Resolve MolTrust agents to their on-chain ERC-8004 identity, fetch Agent Cards,
    or look up on-chain agents by their agentId.

    Args:
        action: One of "card", "resolve", or "well-known"
        did: Agent DID (required for "card", e.g. "did:moltrust:a1b2c3d4e5f60718")
        agent_id: On-chain ERC-8004 agent ID (required for "resolve", e.g. 21023)
    """
    assert ctx is not None
    client = _client(ctx)

    if action == "card":
        if not did:
            return "Error: did is required for fetching an Agent Card."
        resp = await client.http.get(f"/agents/{did}/erc8004")
        if resp.status_code == 404:
            return f"Agent not found: {did}"
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        data = resp.json()
        regs = data.get("registrations", [])
        services = data.get("services", [])

        lines = [
            "ERC-8004 Agent Card",
            "",
            f"Name:   {data.get('name', '?')}",
            f"Type:   {data.get('type', '?')}",
            f"Active: {'Yes' if data.get('active') else 'No'}",
        ]
        if data.get("description"):
            lines.append(f"Info:   {data['description']}")
        if services:
            lines.append("")
            lines.append("Services:")
            for svc in services:
                lines.append(f"  {svc.get('name', '?')}: {svc.get('endpoint', '?')}")
        if regs:
            lines.append("")
            lines.append("On-chain registrations:")
            for reg in regs:
                lines.append(
                    f"  agentId {reg.get('agentId')} on {reg.get('agentRegistry', '?')}"
                )
        return "\n".join(lines)

    elif action == "resolve":
        if agent_id < 1:
            return "Error: agent_id (>= 1) is required for resolving an on-chain agent."
        resp = await client.http.get(f"/resolve/erc8004/{agent_id}")
        if resp.status_code == 404:
            return f"Agent ID {agent_id} not found on ERC-8004 IdentityRegistry."
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"

        data = resp.json()
        rep = data.get("onchain_reputation", {})

        lines = [
            "ERC-8004 On-Chain Agent",
            "",
            f"Agent ID: {data.get('agent_id')}",
            f"Chain:    {data.get('chain')} (ID {data.get('chain_id')})",
            f"Owner:    {data.get('owner')}",
            f"Wallet:   {data.get('agent_wallet')}",
        ]
        if data.get("agent_uri"):
            lines.append(f"URI:      {data['agent_uri']}")
        if data.get("moltrust_did"):
            lines.append("")
            lines.append(f"MolTrust DID:     {data['moltrust_did']}")
            lines.append(f"MolTrust Profile: {data.get('moltrust_profile', '?')}")
        if rep and rep.get("count", 0) > 0:
            lines.append("")
            lines.append(
                f"On-chain reputation: value={rep['summary_value']} ({rep['count']} feedbacks, {rep.get('clients', 0)} clients)"
            )
        elif rep:
            lines.append("")
            lines.append("On-chain reputation: No feedback yet")
        return "\n".join(lines)

    elif action == "well-known":
        resp = await client.http.get("/.well-known/agent-registration.json")
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.text}"
        return _fmt(resp.json())

    else:
        return 'Error: action must be "card", "resolve", or "well-known".'


# ---------------------------------------------------------------------------
# MoltGuard Tools — Agent Trust Scoring & Market Integrity
# ---------------------------------------------------------------------------


@mcp.tool()
async def moltguard_score(
    address: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get an agent trust score for a Base wallet address.

    Analyzes on-chain activity, ERC-8004 registration, USDC balance,
    counterparty diversity, and MolTrust credentials to produce a 0-100 score.

    Args:
        address: Base (EVM) wallet address (0x...)
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/api/agent/score/{address}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Agent Trust Score: {data['score']}/100",
        f"Wallet: {data['wallet']}",
        "",
        "Breakdown:",
    ]
    for k, v in data.get("breakdown", {}).items():
        lines.append(f"  {k}: {v}")
    lines.append(f"\nData source: {data.get('_meta', {}).get('dataSource', 'unknown')}")
    return "\n".join(lines)


@mcp.tool()
async def moltguard_detail(
    address: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get a detailed agent trust report for a Base wallet address.

    Returns full scoring breakdown, wallet history from Blockscout,
    ERC-8004 registration, MolTrust DID cross-reference, and Sybil indicators.

    Args:
        address: Base (EVM) wallet address (0x...)
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/api/agent/detail/{address}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    return _fmt(resp.json())


@mcp.tool()
async def moltguard_sybil(
    address: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Scan a Base wallet for Sybil indicators.

    Analyzes wallet age, transaction patterns, counterparty diversity,
    and funding source to detect potential Sybil wallets.
    Also traces funding clusters — if the funder sent ETH to many wallets,
    it indicates a Sybil ring.

    Args:
        address: Base (EVM) wallet address (0x...)
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/api/sybil/scan/{address}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Sybil Score: {data['sybilScore']} ({data['confidence']} confidence)",
        f"Wallet: {data['wallet']}",
        f"Recommendation: {data['recommendation']}",
        "",
        "Indicators:",
        f"  Wallet age: {data['indicators']['walletAgeDays']} days",
        f"  TX count: {data['indicators']['txCount']}",
        f"  Unique counterparties: {data['indicators']['uniqueCounterparties']}",
        f"  Has USDC: {data['indicators']['hasUsdcBalance']}",
        f"  Patterns: {', '.join(data['indicators']['patternMatch']) or 'none'}",
    ]
    cluster = data.get("cluster", {})
    if cluster.get("detected"):
        lines.append(f"\nCluster DETECTED: ~{cluster['estimatedSize']} sibling wallets")
    if cluster.get("fundingSource"):
        lines.append(f"  Funding source: {cluster['fundingSource']}")
        lines.append(f"  Funding amount: {cluster.get('fundingAmountEth', '?')} ETH")
        lines.append(f"  Sibling wallets: {cluster.get('siblingWallets', '?')}")
    return "\n".join(lines)


@mcp.tool()
async def moltguard_market(
    market_id: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Check a Polymarket prediction market for integrity anomalies.

    Analyzes volume spikes, price-volume divergence, liquidity ratios,
    and outcome price spreads to detect potential manipulation.

    Args:
        market_id: Polymarket market/condition ID
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/api/market/check/{market_id}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Anomaly Score: {data['anomalyScore']}/100",
        f"Market: {data.get('marketQuestion') or data['marketId']}",
        f"Assessment: {data['assessment']}",
        "",
        "Signals:",
        f"  Volume spike: {data['signals']['volumeSpike']}",
        f"  24h volume: ${data['signals'].get('volumeChange24h') or 0:,.0f}",
        f"  Price-volume divergence: {data['signals']['priceVolumeDiv']}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def moltguard_feed(
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get the top anomaly feed — markets with highest integrity concerns.

    Scans the top 20 active Polymarket markets by 24h volume and returns
    those with anomaly indicators, sorted by anomaly score.
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/api/market/feed")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [f"Scanned: {data['totalScanned']} markets", ""]
    for m in data.get("markets", []):
        lines.append(
            f"  [{m['anomalyScore']}] {m.get('marketQuestion', m['marketId'])[:60]}"
        )
    if not data.get("markets"):
        lines.append("  No anomalies detected in top markets.")
    return "\n".join(lines)


@mcp.tool()
async def moltguard_credential_issue(
    address: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Issue a W3C Verifiable Credential (AgentTrustCredential) for a wallet.

    The credential contains the agent's trust score, Sybil score,
    ERC-8004 registration status, and MolTrust verification status.
    It is cryptographically signed with Ed25519 (JWS).

    Args:
        address: Base (EVM) wallet address (0x...)
    """
    client = _client(ctx)
    resp = await client.http.post(
        f"{GUARD_PREFIX}/api/credential/issue",
        json={"address": address},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    return _fmt(resp.json())


@mcp.tool()
async def moltguard_credential_verify(
    jws: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify a MoltGuard Verifiable Credential JWS signature.

    Checks the Ed25519 signature and returns the credential payload if valid.

    Args:
        jws: JWS compact serialization string from a MoltGuard credential
    """
    client = _client(ctx)
    resp = await client.http.post(
        f"{GUARD_PREFIX}/api/credential/verify",
        json={"jws": jws},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if data.get("valid"):
        return f"VALID credential\n\n{_fmt(data['payload'])}"
    return "INVALID — signature verification failed."


# ---------------------------------------------------------------------------
# MT Shopping Tools — Autonomous Commerce Trust
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_shopping_info(
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get MT Shopping API information.

    Returns the MT Shopping service info including version, supported
    endpoints, BuyerAgentCredential schema, and verification details.
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/shopping/info")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    return _fmt(resp.json())


@mcp.tool()
async def mt_shopping_verify(
    credential_jws: str,
    transaction_amount: float,
    transaction_currency: str,
    merchant_id: str,
    item_description: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify a shopping transaction against a BuyerAgentCredential.

    Checks the credential signature, spend limits, trust score, and
    returns a verification receipt with approval status.

    Args:
        credential_jws: JWS compact serialization of the BuyerAgentCredential
        transaction_amount: Transaction amount (e.g. 189.99)
        transaction_currency: Currency code (e.g. "USDC")
        merchant_id: Merchant identifier string
        item_description: Description of the item being purchased
    """
    client = _client(ctx)
    resp = await client.http.post(
        f"{GUARD_PREFIX}/shopping/verify",
        json={
            "credentialJws": credential_jws,
            "transaction": {
                "amount": transaction_amount,
                "currency": transaction_currency,
                "merchantId": merchant_id,
                "itemDescription": item_description,
            },
        },
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Result: {data.get('result', 'unknown')}",
        f"Receipt ID: {data.get('receiptId', 'N/A')}",
        f"Guard Score: {data.get('guardScore', 'N/A')}/100",
    ]
    if data.get("receiptId"):
        lines.append(
            f"Receipt URL: {client.api_url}/guard/shopping/receipt/{data['receiptId']}"
        )
    return "\n".join(lines)


@mcp.tool()
async def mt_shopping_issue_vc(
    agent_did: str,
    human_did: str,
    spend_limit: float,
    currency: str,
    categories: str,
    validity_days: int = 30,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue a BuyerAgentCredential (W3C Verifiable Credential) for a shopping agent.

    Creates a cryptographically signed credential that authorizes an AI agent
    to make purchases on behalf of a human, with enforced spend limits.

    Args:
        agent_did: DID of the shopping agent (e.g. "did:moltrust:agent123")
        human_did: DID of the authorizing human (e.g. "did:moltrust:human456")
        spend_limit: Maximum spend amount per transaction
        currency: Currency code (e.g. "USDC", "USD")
        categories: Comma-separated allowed categories (e.g. "electronics,books")
        validity_days: Number of days the credential is valid (default 30)
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.post(
        f"{GUARD_PREFIX}/vc/buyer-agent/issue",
        json={
            "agentDid": agent_did,
            "humanDid": human_did,
            "spendLimit": spend_limit,
            "currency": currency,
            "categories": [c.strip() for c in categories.split(",")],
            "validityDays": validity_days,
        },
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        "Credential issued successfully.",
        f"Agent: {agent_did}",
        f"Human: {human_did}",
        f"Spend limit: {spend_limit} {currency}",
        f"Categories: {categories}",
        f"Valid for: {validity_days} days",
    ]
    if data.get("jws"):
        lines.append(f"\nJWS (first 80 chars): {data['jws'][:80]}...")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MT Travel Tools — Booking Trust Protocol
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_travel_info(
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get MT Travel service information and available endpoints.

    Returns service description, supported segments, and API endpoints
    for the MT Travel booking trust protocol.
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/travel/info")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    return _fmt(resp.json())


@mcp.tool()
async def mt_travel_verify(
    agent_did: str,
    vc_json: str,
    merchant: str,
    segment: str,
    amount: float,
    currency: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify a travel booking against a TravelAgentCredential.

    Runs a 10-step verification pipeline: VC signature, expiry, agent DID match,
    segment authorization, spend limit, currency, daily cap, trust score,
    delegation chain, and traveler binding.

    Args:
        agent_did: DID of the booking agent (e.g. "did:base:0x...")
        vc_json: The TravelAgentCredential as a JSON string
        merchant: Merchant domain (e.g. "hilton.com")
        segment: Booking segment: hotel, flight, car_rental, or rail
        amount: Booking amount
        currency: Currency code (e.g. "USDC")
    """
    client = _client(ctx)
    try:
        vc = json.loads(vc_json)
    except json.JSONDecodeError:
        vc = {}
    resp = await client.http.post(
        f"{GUARD_PREFIX}/travel/verify",
        json={
            "agentDID": agent_did,
            "vc": vc,
            "merchant": merchant,
            "segment": segment,
            "amount": amount,
            "currency": currency,
        },
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Result: {data.get('result', 'unknown')}",
        f"Merchant: {merchant}",
        f"Segment: {segment}",
        f"Amount: {amount} {currency}",
        f"Guard Score: {data.get('guardScore', 'N/A')}/100",
    ]
    if data.get("receiptId"):
        lines.append(
            f"Receipt: {client.api_url}/guard/travel/receipt/{data['receiptId']}"
        )
    if data.get("tripId"):
        lines.append(f"Trip ID: {data['tripId']}")
    if data.get("reason"):
        lines.append(f"Reason: {data['reason']}")
    return "\n".join(lines)


@mcp.tool()
async def mt_travel_issue_vc(
    agent_did: str,
    principal_did: str,
    segments: str,
    spend_limit: float,
    currency: str,
    traveler_name: str = "",
    validity_days: int = 30,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue a TravelAgentCredential (W3C Verifiable Credential) for a booking agent.

    Creates a cryptographically signed credential that authorizes an AI agent
    to book travel on behalf of a principal (company/human), with enforced
    segment permissions and spend limits.

    Args:
        agent_did: DID of the travel agent (e.g. "did:base:0x...")
        principal_did: DID of the authorizing entity (e.g. "did:base:acme-corp")
        segments: Comma-separated allowed segments (e.g. "hotel,flight,car_rental")
        spend_limit: Maximum spend amount per booking
        currency: Currency code (e.g. "USDC")
        traveler_name: Name of the authorized traveler (optional)
        validity_days: Number of days the credential is valid (default 30)
    """
    assert ctx is not None
    client = _client(ctx)
    body: dict = {
        "agentDID": agent_did,
        "principalDID": principal_did,
        "segments": [s.strip() for s in segments.split(",")],
        "spendLimit": spend_limit,
        "currency": currency,
        "validDays": validity_days,
    }
    if traveler_name:
        body["traveler"] = {"name": traveler_name}
    resp = await client.http.post(f"{GUARD_PREFIX}/vc/travel-agent/issue", json=body)
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        "TravelAgentCredential issued.",
        f"Agent: {agent_did}",
        f"Principal: {principal_did}",
        f"Segments: {segments}",
        f"Spend limit: {spend_limit} {currency}",
        f"Valid for: {validity_days} days",
    ]
    if traveler_name:
        lines.append(f"Traveler: {traveler_name}")
    if data.get("jws"):
        lines.append(f"\nJWS (first 80 chars): {data['jws'][:80]}...")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MT Skill Verification Tools — Agent Skill Auditing
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_skill_audit(
    github_url: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Audit an AI agent skill (SKILL.md) for security risks.

    Fetches the SKILL.md from a URL, computes its canonical SHA-256 hash,
    and runs an 8-point security audit checking for prompt injection,
    data exfiltration, tool scope violations, and metadata completeness.
    Score starts at 100 with deductions per finding. Passing score: >= 70.

    Args:
        github_url: URL to the skill (GitHub repo or direct HTTPS link to SKILL.md)
    """
    client = _client(ctx)
    resp = await client.http.get(
        f"{GUARD_PREFIX}/skill/audit",
        params={"url": github_url},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if "error" in data:
        return f"Audit failed: {data.get('message', data['error'])}"
    lines = [
        f"Skill: {data.get('skillName', 'unknown')} v{data.get('skillVersion', '?')}",
        f"Score: {data['audit']['score']}/100 ({'PASS' if data.get('passed') else 'FAIL'})",
        f"Hash: {data.get('skillHash', 'N/A')}",
        f"Repository: {data.get('repositoryUrl', github_url)}",
        "",
    ]
    findings = data.get("audit", {}).get("findings", [])
    if findings:
        lines.append("Findings:")
        for f in findings:
            lines.append(
                f"  [{f['severity'].upper()}] {f['category']}: {f['description']} (-{f['deduction']})"
            )
    else:
        lines.append("No security findings.")
    return "\n".join(lines)


@mcp.tool()
async def mt_skill_verify(
    skill_hash: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify an AI agent skill by its canonical SHA-256 hash.

    Checks if a VerifiedSkillCredential has been issued for this skill hash.
    Returns credential details if verified.

    Args:
        skill_hash: Canonical skill hash (e.g. "sha256:a1b2c3...")
    """
    client = _client(ctx)
    resp = await client.http.get(f"{GUARD_PREFIX}/skill/verify/{skill_hash}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if data.get("verified"):
        vc = data["credential"]
        sub = vc["credentialSubject"]
        lines = [
            f"VERIFIED: {sub['skillName']} v{sub['skillVersion']}",
            f"Author: {sub['id']}",
            f"Audit score: {sub['audit']['score']}/100",
            f"Issued: {vc['issuanceDate']}",
            f"Expires: {vc['expirationDate']}",
            f"Anchor TX: {sub.get('anchorTx', 'N/A')}",
        ]
        return "\n".join(lines)
    return f"NOT VERIFIED: {data.get('message', 'No credential found')}"


@mcp.tool()
async def mt_skill_issue_vc(
    author_did: str,
    repository_url: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Issue a VerifiedSkillCredential for an AI agent skill.

    Fetches SKILL.md, runs security audit, and if score >= 70, issues a
    W3C Verifiable Credential signed with Ed25519 (JWS compact serialization).
    Requires x402 payment ($5 USDC) when paywall is active.

    Args:
        author_did: DID of the skill author (e.g. "did:base:0x...")
        repository_url: URL to the skill repository or SKILL.md
    """
    client = _client(ctx)
    resp = await client.http.post(
        f"{GUARD_PREFIX}/vc/skill/issue",
        json={
            "authorDID": author_did,
            "repositoryUrl": repository_url,
        },
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if "error" in data:
        return f"Issuance FAILED: {data.get('message', data['error'])}"
    sub = data["credentialSubject"]
    lines = [
        "VerifiedSkillCredential issued.",
        f"Skill: {sub['skillName']} v{sub['skillVersion']}",
        f"Author: {sub['id']}",
        f"Hash: {sub['skillHash']}",
        f"Audit score: {sub['audit']['score']}/100",
        f"Expires: {data['expirationDate']}",
        f"Anchor TX: {sub.get('anchorTx', 'N/A')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MT Prediction Tools — Prediction Market Track Records
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_prediction_link(
    address: str,
    platform: str = "polymarket",
    did: str = "",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Link a prediction market wallet and sync its track record.

    Fetches trade history from Polymarket, calculates a prediction score (0-100),
    and stores the wallet profile. Optionally links it to a MolTrust DID.

    Args:
        address: Prediction market wallet address (0x-prefixed, 42 chars)
        platform: Platform name (default: "polymarket")
        did: Optional MolTrust DID to link (e.g. "did:moltrust:a1b2c3d4e5f60718")
    """
    assert ctx is not None
    client = _client(ctx)
    body: dict = {"address": address, "platform": platform}
    if did:
        body["did"] = did
    resp = await client.http.post(
        f"{GUARD_PREFIX}/prediction/wallet-link",
        json=body,
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if "error" in data:
        return f"Error: {data['error']}"
    lines = [
        f"Wallet linked: {data.get('address', address)}",
        f"Platform: {data.get('platform', platform)}",
        f"Prediction Score: {data.get('predictionScore', 0)}/100",
        f"Total Bets: {data.get('totalBets', 0)}",
    ]
    if data.get("wins") is not None:
        lines.append(f"Record: {data['wins']}W / {data.get('losses', 0)}L")
    if data.get("totalVolume"):
        lines.append(f"Volume: ${data['totalVolume']:,.2f} USDC")
    if data.get("netPnl") is not None:
        lines.append(f"Net P&L: ${data['netPnl']:+,.2f} USDC")
    if data.get("linked_did"):
        lines.append(f"Linked DID: {data['linked_did']}")
    lines.append(
        f"Synced: {'Yes' if data.get('synced') else 'No (no Polymarket data found)'}"
    )
    return "\n".join(lines)


@mcp.tool()
async def mt_prediction_wallet(
    address: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Get prediction market profile and track record for a wallet.

    Returns the prediction score (0-100), win/loss record, volume, ROI,
    score breakdown, and recent market events.

    Args:
        address: Prediction market wallet address (0x-prefixed, 42 chars)
    """
    client = _client(ctx)
    resp = await client.http.get(
        f"{GUARD_PREFIX}/prediction/wallet/{address}",
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    if "error" in data:
        return f"Error: {data['error']}"
    lines = [
        f"Prediction Wallet: {data['address']}",
        f"Platform: {data.get('platform', 'polymarket')}",
        f"Prediction Score: {data.get('predictionScore', 0)}/100",
    ]
    bd = data.get("scoreBreakdown", {})
    if bd:
        lines.append(
            f"  Breakdown: WinRate={bd.get('winRate', 0)} "
            f"ROI={bd.get('roi', 0)} Volume={bd.get('volume', 0)} "
            f"Sample={bd.get('sampleSize', 0)} Recency={bd.get('recency', 0)}"
        )
    lines.append(f"Record: {data.get('wins', 0)}W / {data.get('losses', 0)}L")
    lines.append(f"Total Bets: {data.get('totalBets', 0)}")
    if data.get("totalVolume"):
        lines.append(f"Volume: ${data['totalVolume']:,.2f} USDC")
    if data.get("netPnl") is not None:
        lines.append(f"Net P&L: ${data['netPnl']:+,.2f} USDC")
    if data.get("linked_did"):
        lines.append(f"DID: {data['linked_did']}")
    if data.get("lastSynced"):
        lines.append(f"Last Synced: {data['lastSynced']}")
    events = data.get("recentEvents", [])
    if events:
        lines.append(f"\nRecent Events ({len(events)}):")
        for e in events[:10]:
            q = e.get("question", e.get("marketId", "?"))
            pos = e.get("position", "?")
            amt = e.get("amountIn")
            amt_str = f" ${amt:,.2f}" if amt else ""
            lines.append(f"  {q[:60]} | {pos}{amt_str}")
    return "\n".join(lines)


@mcp.tool()
async def mt_prediction_leaderboard(
    limit: int = 20,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get the prediction market leaderboard — top wallets by prediction score.

    Returns wallets ranked by their composite prediction score,
    which factors in win rate, ROI, volume, sample size, and recency.

    Args:
        limit: Number of entries to return (default 20, max 100)
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(
        f"{GUARD_PREFIX}/prediction/leaderboard",
        params={"limit": str(min(limit, 100))},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    entries = data.get("entries", [])
    if not entries:
        return "No entries in the prediction leaderboard yet."
    lines = [f"Prediction Leaderboard (top {len(entries)}):", ""]
    for e in entries:
        rank = e.get("rank", "?")
        addr = e.get("address", "?")
        short = addr[:6] + "..." + addr[-4:] if len(addr) > 12 else addr
        score = e.get("predictionScore", 0)
        wins = e.get("wins", 0)
        losses = e.get("losses", 0)
        vol = e.get("totalVolume", 0)
        pnl = e.get("netPnl", 0)
        did = e.get("did")
        did_str = f" ({did})" if did else ""
        lines.append(
            f"#{rank} {short}{did_str}  "
            f"Score:{score}  {wins}W/{losses}L  "
            f"Vol:${vol:,.0f}  P&L:${pnl:+,.0f}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MT Salesguard — Brand Product Provenance
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_salesguard_verify(
    product_id: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify product provenance via MT Salesguard.

    Checks whether a product ID has a valid ProductProvenanceCredential
    issued by an authorized brand. Returns brand info, credential hash,
    Base anchor, and risk level.

    Args:
        product_id: Product identifier (e.g. "AIRMAX-90-WHITE-43")
    """
    client = _client(ctx)
    resp = await client.http.get(
        f"{GUARD_PREFIX}/salesguard/verify/{product_id}",
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Product: {data.get('product_id', product_id)}",
        f"Verified: {data.get('verified', False)}",
        f"Risk Level: {data.get('risk_level', 'UNKNOWN')}",
    ]
    if data.get("verified"):
        brand = data.get("brand", {})
        lines.append(f"Brand: {brand.get('name', '?')}")
        lines.append(f"Brand DID: {brand.get('did', '?')}")
        lines.append(f"Domain: {brand.get('domain', '?')}")
        lines.append(f"Credential Hash: {data.get('credential_hash', '?')}")
        lines.append(f"Base Anchor: {data.get('base_anchor', '?')}")
        lines.append(f"Registered: {data.get('registered_at', '?')}")
    else:
        lines.append(data.get("message", "No provenance record found."))
    return "\n".join(lines)


@mcp.tool()
async def mt_salesguard_reseller(
    reseller_did: str,
    ctx: Context[ServerSession, MolTrustClient],
) -> str:
    """Verify reseller authorization via MT Salesguard.

    Checks whether a reseller DID has been authorized by a brand
    to sell specific products. Returns authorization status, brand info,
    authorized SKUs, and expiry.

    Args:
        reseller_did: Reseller DID (e.g. "did:web:sneakerstore.com")
    """
    client = _client(ctx)
    resp = await client.http.get(
        f"{GUARD_PREFIX}/salesguard/reseller/verify/{reseller_did}",
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Reseller: {data.get('reseller_did', reseller_did)}",
        f"Authorized: {data.get('authorized', False)}",
    ]
    if data.get("authorized"):
        brand = data.get("brand", {})
        lines.append(f"Brand: {brand.get('name', '?')}")
        lines.append(f"Brand DID: {brand.get('did', '?')}")
        lines.append(f"Reseller Name: {data.get('reseller_name', '?')}")
        skus = data.get("authorized_skus", [])
        lines.append(f"Authorized SKUs: {', '.join(skus) if skus else 'none'}")
        lines.append(f"Expires: {data.get('expires_at', '?')}")
        lines.append(f"Expired: {data.get('expired', False)}")
    else:
        lines.append(data.get("message", "No authorization record found."))
    return "\n".join(lines)


@mcp.tool()
async def mt_salesguard_register(
    name: str,
    domain: str,
    contact_email: str = "",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Register a brand with MT Salesguard.

    Creates a new brand identity with a DID and API key.
    The API key is used to authenticate product registration
    and reseller authorization requests.

    Args:
        name: Brand name (e.g. "Nike", "Adidas")
        domain: Brand domain (e.g. "nike.com")
        contact_email: Contact email for the brand (optional)
    """
    assert ctx is not None
    client = _client(ctx)
    body: dict = {"name": name, "domain": domain}
    if contact_email:
        body["contact_email"] = contact_email
    resp = await client.http.post(
        f"{GUARD_PREFIX}/salesguard/brand/register",
        json=body,
    )
    if resp.status_code == 400:
        return f"Bad request: {resp.json().get('message', resp.text)}"
    if resp.status_code not in (200, 201):
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        "Brand Registered Successfully",
        "",
        f"DID: {data.get('did', '?')}",
        f"API Key: {data.get('api_key', '?')}",
        f"Name: {data.get('name', '?')}",
        f"Domain: {data.get('domain', '?')}",
        f"Created: {data.get('created_at', '?')}",
        "",
        "Use the API key with Authorization: Bearer <api_key>",
        "to register products and authorize resellers.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MT Fantasy Sports
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_fantasy_commit(
    agent_did: str,
    contest_id: str,
    platform: str,
    sport: str,
    contest_start_iso: str,
    lineup_json: str,
    projected_score: float = 0.0,
    confidence: float = 0.0,
    entry_fee_usd: float = 0.0,
    contest_type: str = "classic",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Commit a fantasy lineup with a SHA-256 hash anchored on Base L2.

    Creates a FantasyLineupCredential (W3C VC) proving the lineup was
    locked before contest start. The commitment hash is tamper-proof.

    Args:
        agent_did: Agent DID (e.g. "did:moltrust:a1b2c3d4e5f67890")
        contest_id: Unique contest identifier (e.g. "dk-nfl-sun-main-2026w12")
        platform: Platform name: draftkings, fanduel, yahoo, sleeper, custom
        sport: Sport type: nfl, nba, mlb, nhl, pga, nascar, soccer, custom
        contest_start_iso: Contest start time in ISO 8601 (must be in the future)
        lineup_json: JSON string of lineup object (e.g. '{"QB":"Mahomes","RB1":"Henry"}')
        projected_score: Agent's projected score for this lineup
        confidence: Confidence level 0.0 to 1.0
        entry_fee_usd: Contest entry fee in USD
        contest_type: Contest type (e.g. "classic", "showdown")
    """
    assert ctx is not None
    client = _client(ctx)
    try:
        lineup = json.loads(lineup_json)
    except (json.JSONDecodeError, TypeError):
        return "Error: lineup_json must be a valid JSON string"
    body: dict = {
        "agent_did": agent_did,
        "contest_id": contest_id,
        "platform": platform,
        "sport": sport,
        "contest_start_iso": contest_start_iso,
        "lineup": lineup,
    }
    if projected_score:
        body["projected_score"] = projected_score
    if confidence:
        body["confidence"] = confidence
    if entry_fee_usd:
        body["entry_fee_usd"] = entry_fee_usd
    if contest_type:
        body["contest_type"] = contest_type
    resp = await client.http.post(
        "/sports/fantasy/lineups/commit",
        json=body,
        headers=_auth_headers(client),
    )
    if resp.status_code == 409:
        return "Duplicate: Lineup already committed for this contest."
    if resp.status_code not in (200, 201):
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    cred = data.get("credential", {})
    lines = [
        "Fantasy Lineup Committed",
        "",
        f"Commitment Hash: {data.get('commitment_hash', '?')}",
        f"Lineup Hash: {data.get('lineup_hash', '?')}",
        f"Agent: {data.get('agent_did', '?')}",
        f"Contest: {data.get('contest_id', '?')}",
        f"Chain: {data.get('chain', 'base')}",
        f"Tx Hash: {data.get('tx_hash', '?')}",
        f"Status: {data.get('status', '?')}",
        f"Verify URL: {data.get('verify_url', '?')}",
        "",
        f"Credential Type: {', '.join(cred.get('type', []))}",
        f"Issuer: {cred.get('issuer', '?')}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def mt_fantasy_verify(
    commitment_hash: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Verify a fantasy lineup commitment. Public endpoint, no auth required.

    Returns the full lineup, timing proof (minutes before contest),
    on-chain verification status, and the FantasyLineupCredential.

    Args:
        commitment_hash: The 64-char SHA-256 commitment hash
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(
        f"/sports/fantasy/lineups/verify/{commitment_hash}",
    )
    if resp.status_code == 404:
        return "Lineup commitment not found."
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    on_chain = data.get("on_chain", {})
    result = data.get("result", {})
    cred = data.get("credential", {})
    lines = [
        f"Commitment Hash: {data.get('commitment_hash', '?')}",
        f"Agent: {data.get('agent_did', '?')}",
        f"Contest: {data.get('contest_id', '?')}",
        f"Platform: {data.get('platform', '?')}",
        f"Sport: {data.get('sport', '?')}",
        f"Minutes Before Contest: {data.get('minutes_before_contest', '?')}",
        f"Committed At: {data.get('committed_at', '?')}",
        "",
        f"Lineup: {json.dumps(data.get('lineup', {}), indent=2)}",
        f"Projected Score: {data.get('projected_score', '?')}",
        f"Confidence: {data.get('confidence', '?')}",
        "",
        f"On-Chain Verified: {on_chain.get('verified', False)}",
        f"Tx Hash: {on_chain.get('tx_hash', '?')}",
        f"Chain: {on_chain.get('chain', 'base')}",
    ]
    if result.get("settled"):
        lines.extend(
            [
                "",
                f"Actual Score: {result.get('actual_score', '?')}",
                f"Rank: {result.get('rank', '?')}",
                f"Prize: ${result.get('prize_usd', 0):.2f}",
            ]
        )
    if cred:
        cred_type = cred.get("type", [])
        lines.extend(
            [
                "",
                f"Credential: {', '.join(cred_type) if isinstance(cred_type, list) else cred_type}",
                f"Issuer: {cred.get('issuer', '?')}",
            ]
        )
    return "\n".join(lines)


@mcp.tool()
async def mt_fantasy_history(
    did: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get fantasy lineup history and stats for an agent.

    Returns ITM rate, ROI, projection accuracy, and recent lineups
    for the specified agent DID.

    Args:
        did: Agent DID (e.g. "did:moltrust:a1b2c3d4e5f67890")
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(
        f"/sports/fantasy/history/{did}",
        headers=_auth_headers(client),
    )
    if resp.status_code == 404:
        return f"Agent {did} not found or has no fantasy history."
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    stats = data.get("fantasy_stats", {})
    lineups = data.get("lineups", [])
    lines = [
        f"Fantasy Stats for {data.get('agent_did', did)}",
        "",
        f"Total Lineups: {stats.get('total_lineups', 0)}",
        f"Settled: {stats.get('settled', 0)}",
        f"ITM Rate: {stats.get('itm_rate', 0):.1%}",
        f"ROI: {stats.get('roi', 0):.1%}",
        f"Projection Accuracy: {stats.get('projection_accuracy', 'N/A')}",
        f"Avg Projected: {stats.get('avg_projected_score', '?')}",
        f"Avg Actual: {stats.get('avg_actual_score', '?')}",
        f"Platforms: {', '.join(stats.get('platforms', []))}",
        f"Sports: {', '.join(stats.get('sports', []))}",
    ]
    if lineups:
        lines.append("")
        lines.append(f"Recent Lineups ({len(lineups)}):")
        for lu in lineups[:5]:
            settled = "Settled" if lu.get("settled_at") else "Pending"
            lines.append(
                f"  - {lu.get('contest_id', '?')} ({lu.get('platform', '?')}/{lu.get('sport', '?')}) "
                f"[{settled}] hash={lu.get('commitment_hash', '?')[:12]}..."
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Swarm Intelligence — Trust Score & Endorsements
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_create_interaction_proof(
    api_key: str,
    agent_a: str,
    agent_b: str,
    interaction_type: str = "skill_verification",
    outcome: str = "success",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Create an interaction proof before issuing a SkillEndorsementCredential.

    Returns evidence_hash and base_tx_hash anchored on Base L2.
    Required before calling mt_endorse_agent. Valid for 72 hours.

    Args:
        api_key: MolTrust API key of the agent creating the proof
        agent_a: DID of the first agent in the interaction
        agent_b: DID of the second agent in the interaction
        interaction_type: Type of interaction (e.g. skill_verification, purchase, prediction)
        outcome: Outcome of the interaction: success or failure
    """
    assert ctx is not None
    client = _client(ctx)
    from datetime import datetime, timezone

    payload = {
        "type": interaction_type,
        "agent_a": agent_a,
        "agent_b": agent_b,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
    }
    resp = await client.http.post(
        "/skill/interaction-proof",
        json={"api_key": api_key, "interaction_payload": payload},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        "Interaction Proof Created",
        "",
        f"Evidence Hash: {data.get('evidence_hash', '?')}",
        f"Base Tx Hash: {data.get('base_tx_hash', '?')}",
        f"Anchored At: {data.get('anchored_at', '?')}",
        f"Valid Until: {data.get('valid_for_endorsement_until', '?')}",
        f"Agent DID: {data.get('agent_did', '?')}",
        "",
        "Use evidence_hash and anchored_at with mt_endorse_agent.",
    ]
    return "\n".join(lines)


@mcp.tool()
async def mt_endorse_agent(
    endorser_api_key: str,
    endorsed_did: str,
    skill: str,
    evidence_hash: str,
    evidence_timestamp: str,
    vertical: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue a W3C SkillEndorsementCredential for another agent.

    Requires a valid evidence_hash from mt_create_interaction_proof
    (max 72h old). Self-endorsement is rejected.
    Contributes to the endorsed agent's Trust Score.

    Args:
        endorser_api_key: MolTrust API key of the endorsing agent
        endorsed_did: DID of the agent to endorse
        skill: Skill being endorsed (python, javascript, security, prediction, trading, data_analysis, api_integration, smart_contracts, nlp, computer_vision, general)
        evidence_hash: SHA-256 hash from mt_create_interaction_proof (sha256:...)
        evidence_timestamp: ISO 8601 timestamp from mt_create_interaction_proof
        vertical: MolTrust vertical (skill, shopping, travel, prediction, salesguard, sports, core)
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.post(
        "/skill/endorse",
        json={
            "api_key": endorser_api_key,
            "endorsed_did": endorsed_did,
            "skill": skill,
            "evidence_hash": evidence_hash,
            "evidence_timestamp": evidence_timestamp,
            "vertical": vertical,
        },
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    vc = resp.json()
    subj = vc.get("credentialSubject", {})
    proof = vc.get("proof", {})
    lines = [
        "SkillEndorsementCredential Issued",
        "",
        f"VC ID: {vc.get('id', '?')}",
        f"Type: {', '.join(vc.get('type', []))}",
        f"Issuer: {vc.get('issuer', '?')}",
        f"Endorsed: {subj.get('id', '?')}",
        f"Skill: {subj.get('skill', '?')}",
        f"Vertical: {subj.get('vertical', '?')}",
        f"Evidence: {subj.get('evidenceHash', '?')}",
        f"Issued: {vc.get('issuanceDate', '?')}",
        f"Expires: {vc.get('expirationDate', '?')}",
        f"Proof: {proof.get('type', '?')}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def mt_get_trust_score(
    did: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get the Swarm Intelligence Trust Score for an agent (Phase 2).

    Score combines direct endorsements, propagated trust from endorsers,
    cross-vertical credential bonus, and interaction proof activity.
    Returns null/withheld if fewer than 3 independent endorsers (non-seed).
    Seed agents get their base score directly.

    Args:
        did: DID of the agent to score (e.g. "did:moltrust:a1b2c3d4e5f67890")
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(f"/skill/trust-score/{did}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    score = data.get("trust_score")
    breakdown = data.get("breakdown", {})
    if data.get("withheld"):
        lines = [
            f"Trust Score for {data.get('did', did)}",
            "",
            "Score: WITHHELD (fewer than 3 independent endorsers)",
            f"Current Endorsers: {data.get('endorser_count', 0)}",
            "Need at least 3 endorsers from different verticals.",
        ]
    else:
        grade = data.get("grade", "N/A")
        lines = [
            f"Trust Score for {data.get('did', did)}",
            "",
            f"Score: {score}" if score is not None else "Score: N/A",
            f"Grade: {grade}",
            f"Endorser Count: {data.get('endorser_count', 0)}",
            f"Method: {breakdown.get('computation_method', '?')}",
            "",
            "Breakdown:",
            f"  Direct Score: {breakdown.get('direct_score', 0)}",
            f"  Propagated Score: {breakdown.get('propagated_score', 0)}",
            f"  Cross-Vertical Bonus: {breakdown.get('cross_vertical_bonus', 0)}",
            f"  Interaction Bonus: {breakdown.get('interaction_bonus', 0)}",
            f"  Sybil Penalty: {breakdown.get('sybil_penalty', 0)}",
            "",
            f"Computed At: {data.get('computed_at', '?')}",
            f"Cache Valid Until: {data.get('cache_valid_until', '?')}",
        ]
    return "\n".join(lines)


@mcp.tool()
async def mt_get_swarm_graph(
    did: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get the trust propagation graph for an agent (2 hops).

    Returns nodes (agents with scores) and edges (endorsements) showing
    who endorses this agent and who endorses them.

    Args:
        did: DID of the agent to get graph for
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(f"/swarm/graph/{did}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        f"Trust Propagation Graph for {did}",
        f"Nodes: {data.get('node_count', 0)} | Edges: {data.get('edge_count', 0)}",
        "",
    ]
    for node in data.get("nodes", []):
        label = f" ({node['label']})" if node.get("label") else ""
        score_str = f"{node['score']}" if node.get("score") is not None else "N/A"
        lines.append(
            f"  [Hop {node.get('hop', '?')}] {node['did']}{label} — "
            f"Score: {score_str} ({node.get('grade', 'N/A')})"
        )
    if data.get("edges"):
        lines.append("")
        lines.append("Edges:")
        for edge in data["edges"]:
            lines.append(
                f"  {edge['from']} → {edge['to']} ({edge.get('vertical', '?')})"
            )
    return "\n".join(lines)


@mcp.tool()
async def mt_get_swarm_stats(
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get global Swarm Intelligence statistics.

    Returns total agents, endorsements, seed agents, average trust score,
    propagation depth, and top trusted agents.
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get("/swarm/stats")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    lines = [
        "Swarm Intelligence Statistics",
        "",
        f"Total Agents: {data.get('total_agents', 0)}",
        f"Total Endorsements: {data.get('total_endorsements', 0)}",
        f"Avg Trust Score: {data.get('avg_trust_score', 'N/A')}",
        f"Max Propagation Depth: {data.get('propagation_depth', 0)}",
        "",
        "Seed Agents:",
    ]
    for s in data.get("seed_agents", []):
        lines.append(f"  {s['did']} ({s.get('label', '?')}) — base: {s['base_score']}")
    top = data.get("top_trusted", [])
    if top:
        lines.append("")
        lines.append("Top Trusted:")
        for t in top:
            lines.append(f"  {t['did']} — {t['score']}")
    return "\n".join(lines)


@mcp.tool()
async def mt_register_seed(
    did: str,
    label: str,
    base_score: float = 80.0,
    admin_key: str = "",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Register a trusted seed agent in the Swarm Intelligence network (admin only).

    Seed agents bootstrap the trust network with a base score.
    Requires the ADMIN_KEY for authorization.

    Args:
        did: DID of the agent to register as seed
        label: Human-readable label for the seed agent
        base_score: Base trust score (0-100, default 80)
        admin_key: Admin key for authorization
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.post(
        "/swarm/seed",
        json={"did": did, "label": label, "base_score": base_score},
        headers={"x-admin-key": admin_key},
    )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    return (
        f"Seed Agent Registered\n\n"
        f"DID: {data.get('did')}\n"
        f"Label: {data.get('label')}\n"
        f"Base Score: {data.get('base_score')}"
    )


# ---------------------------------------------------------------------------
# Verified Badge Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_get_badge(
    did: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get the Verified by MolTrust badge status for an agent.

    Returns badge tier, trust score, grade, issue/expiry dates,
    and embeddable SVG URL.

    Args:
        did: The DID of the agent to check
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(f"/identity/badge/{did}")
    if resp.status_code != 200:
        return f"Error: {resp.status_code} — {resp.text[:200]}"
    data = resp.json()
    if not data.get("verified"):
        return (
            f"Badge Status: Not Verified\n\n"
            f"DID: {data.get('did')}\n"
            f"Trust Score: {data.get('trust_score', 'N/A')}\n"
            f"Grade: {data.get('grade', 'N/A')}\n\n"
            f"Badge URL: {data.get('badge_url')}\n"
            f"Verify: {data.get('verify_url')}"
        )
    return (
        f"Badge Status: {data.get('tier', '').capitalize()} ✓\n\n"
        f"DID: {data.get('did')}\n"
        f"Tier: {data.get('tier')}\n"
        f"Trust Score: {data.get('trust_score')}\n"
        f"Grade: {data.get('grade')}\n"
        f"Issued: {data.get('issued_at')}\n"
        f"Expires: {data.get('expires_at')}\n"
        f"VC Hash: {data.get('vc_hash')}\n\n"
        f"Badge SVG: {data.get('badge_url')}\n"
        f"Verify: {data.get('verify_url')}\n\n"
        f"Embed: [![Verified by MolTrust]({data.get('badge_url')})]({data.get('verify_url')})"
    )


@mcp.tool()
async def mt_issue_badge(
    did: str,
    tier: str = "verified",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue a Verified by MolTrust badge for an agent.

    Tiers: 'verified' (score 40+, $5), 'trusted' (score 60+, $20).
    Badge is valid for 1 year and auto-revokes if trust score drops.

    Args:
        did: The DID of the agent to issue a badge for
        tier: Badge tier — 'verified' or 'trusted'
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.post(
        "/identity/badge/issue",
        json={"did": did, "tier": tier},
    )
    if resp.status_code != 200:
        return f"Error: {resp.status_code} — {resp.text[:200]}"
    data = resp.json()
    return (
        f"Badge Issued Successfully\n\n"
        f"DID: {data.get('did')}\n"
        f"Tier: {data.get('tier')}\n"
        f"Trust Score: {data.get('trust_score')}\n"
        f"Issued: {data.get('issued_at')}\n"
        f"Expires: {data.get('expires_at')}\n"
        f"VC Hash: {data.get('vc_hash')}\n\n"
        f"Badge SVG: {data.get('badge_url')}\n"
        f"Verify: {data.get('verify_url')}\n\n"
        f"Embed in README:\n"
        f"[![Verified by MolTrust]({data.get('badge_url')})]({data.get('verify_url')})"
    )


@mcp.tool()
async def mt_check_badge(
    did: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Quick check: is this agent badge-verified by MolTrust?

    Returns a simple yes/no with tier and expiry info.

    Args:
        did: The DID of the agent to check
    """
    assert ctx is not None
    client = _client(ctx)
    resp = await client.http.get(f"/identity/badge/check/{did}")
    if resp.status_code != 200:
        return f"Error: {resp.status_code} — {resp.text[:200]}"
    data = resp.json()
    if data.get("verified"):
        return (
            f"Verified: YES\n"
            f"Tier: {data.get('tier')}\n"
            f"Expires in: {data.get('expires_in_days')} days"
        )
    return "Verified: NO"


# ---------------------------------------------------------------------------
# MT Music — AI-Generated Music Provenance
# ---------------------------------------------------------------------------


@mcp.tool()
async def mt_issue_music_credential(
    agent_did: str,
    tool: str,
    human_oversight: str,
    rights: str,
    track_title: str,
    track_description: str = "",
    genre: str = "",
    isrc: str = "",
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Issue a VerifiedMusicCredential for an AI-generated music track.

    Creates a W3C Verifiable Credential proving the provenance of an
    AI-generated music track — which tool created it, whether a human
    was involved, and what rights apply. Anchored on Base L2.
    EU AI Act Article 50(2) compliant.

    Args:
        agent_did: DID of the agent/creator (e.g. "did:moltrust:abc123")
        tool: AI tool used (e.g. "Suno API v3.2", "Udio", "Magenta")
        human_oversight: "true", "false", or "partial"
        rights: Rights declaration (e.g. "CC-BY", "All Rights Reserved", "Agent-Wallet")
        track_title: Title of the track
        track_description: Optional description
        genre: Optional genre (e.g. "ambient", "jazz", "classical")
        isrc: Optional ISRC code (ISO 3901)
    """
    client = _client(ctx)
    body = {
        "agent_did": agent_did,
        "tool": tool,
        "human_oversight": human_oversight,
        "rights": rights,
        "track_title": track_title,
        "track_description": track_description or None,
        "genre": genre or None,
        "isrc": isrc or None,
    }
    resp = await client.http.post("/music/credential/issue", json=body)
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    prov = data.get("credentialSubject", {}).get("provenance", {})
    anchor = data.get("anchor", {})
    return (
        f"Credential ID: {data.get('id')}\n"
        f"Track: {track_title}\n"
        f"Tool: {tool}\n"
        f"Human Oversight: {human_oversight}\n"
        f"Rights: {rights}\n"
        f"Track Hash: {prov.get('trackHash')}\n"
        f"EU AI Act: {prov.get('euAiActCompliance')}\n"
        f"Issued: {data.get('issuanceDate')}\n"
        f"Anchor TX: {anchor.get('anchorTx', 'pending')}\n"
        f"Anchor Block: {anchor.get('anchorBlock', 'pending')}"
    )


@mcp.tool()
async def mt_verify_music_credential(
    credential_id: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Verify a VerifiedMusicCredential by its ID.

    Checks whether a music credential is valid (not revoked),
    returns provenance summary including tool, human oversight,
    rights, and on-chain anchor status.

    Args:
        credential_id: UUID of the music credential
    """
    client = _client(ctx)
    resp = await client.http.get(f"/music/verify/{credential_id}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    cred = data.get("credential", {})
    subj = cred.get("credentialSubject", {})
    track = subj.get("track", {})
    anchor = cred.get("anchor", {})
    lines = [
        f"Valid: {data.get('valid')}",
        f"Revoked: {data.get('revoked')}",
    ]
    if data.get("revoked"):
        lines.append(f"Revocation Reason: {data.get('revocationReason')}")
    lines.extend([
        f"Track: {track.get('title')}",
        f"Tool: {track.get('tool')}",
        f"Human Oversight: {track.get('humanOversight')}",
        f"Rights: {track.get('rights')}",
        f"Genre: {track.get('genre')}",
        f"Issued: {cred.get('issuanceDate')}",
        f"Anchored: {data.get('anchored')}",
        f"Anchor TX: {anchor.get('anchorTx', 'N/A')}",
    ])
    return "\n".join(lines)


@mcp.tool()
async def mt_get_track_provenance(
    credential_id: str,
    ctx: Context[ServerSession, MolTrustClient] | None = None,
) -> str:
    """Get full provenance details for a music credential.

    Returns the complete VerifiedMusicCredential including track
    metadata, provenance hash, EU AI Act compliance status,
    and on-chain anchor information.

    Args:
        credential_id: UUID of the music credential
    """
    client = _client(ctx)
    resp = await client.http.get(f"/music/credential/{credential_id}")
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    subj = data.get("credentialSubject", {})
    track = subj.get("track", {})
    prov = subj.get("provenance", {})
    anchor = data.get("anchor", {})
    lines = [
        "=== Track Provenance ===",
        f"Credential ID: {data.get('id')}",
        f"Agent DID: {subj.get('agentDid')}",
        f"Human Name: {subj.get('humanName', 'N/A')}",
        "",
        f"Track: {track.get('title')}",
        f"Description: {track.get('description', 'N/A')}",
        f"Tool: {track.get('tool')}",
        f"Human Oversight: {track.get('humanOversight')}",
        f"Genre: {track.get('genre', 'N/A')}",
        f"Rights: {track.get('rights')}",
        f"ISRC: {track.get('isrc', 'N/A')}",
        f"Session: {track.get('session', 'N/A')}",
        "",
        f"Track Hash: {prov.get('trackHash')}",
        f"EU AI Act: {prov.get('euAiActCompliance')}",
        f"Issued: {prov.get('issuanceDate')}",
        "",
        f"Chain: {anchor.get('chain')}",
        f"Anchor TX: {anchor.get('anchorTx', 'pending')}",
        f"Anchor Block: {anchor.get('anchorBlock', 'pending')}",
        f"Calldata: {anchor.get('calldata')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def gather_requests(*coros):
    """Run multiple httpx requests concurrently."""
    import asyncio

    return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
