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
TIMEOUT = 30.0


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
        headers={"User-Agent": "moltrust-mcp-server/0.4.0"},
    ) as http:
        yield MolTrustClient(http=http, api_key=api_key, api_url=api_url)


mcp = FastMCP(
    "moltrust",
    instructions=(
        "MolTrust — Trust Infrastructure for AI Agents. "
        "Register agents, verify identities, query reputation scores, "
        "rate agents, manage W3C Verifiable Credentials, and query "
        "ERC-8004 on-chain agent registries on Base."
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
        lines.extend([
            f"Name:     {card.get('name', '?')}",
            f"Platform: {card.get('platform', '?')}",
            f"Score:    {trust.get('score', 0)}/5 ({trust.get('totalRatings', 0)} ratings)",
            f"On-chain: {'Yes' if trust.get('baseAnchor') else 'No'}",
        ])
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
            lines.append(f"Score:   {rep.get('score', 0)}/5 ({rep.get('total_ratings', 0)} ratings)")
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
            json={"from_did": did, "to_did": to_did, "amount": amount, "reference": reference},
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
        return 'Error: action must be "balance", "pricing", "transfer", or "transactions".'



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
        return f"Forbidden: {resp.json().get('detail', 'API key does not own this DID')}"
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
        return f"Forbidden: {resp.json().get('detail', 'API key does not own this DID')}"
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
                lines.append(f"  agentId {reg.get('agentId')} on {reg.get('agentRegistry', '?')}")
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
            lines.append(f"On-chain reputation: value={rep['summary_value']} ({rep['count']} feedbacks, {rep.get('clients', 0)} clients)")
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
