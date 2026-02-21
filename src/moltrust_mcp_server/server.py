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
        headers={"User-Agent": "moltrust-mcp-server/0.1.0"},
    ) as http:
        yield MolTrustClient(http=http, api_key=api_key, api_url=api_url)


mcp = FastMCP(
    "moltrust",
    instructions=(
        "MolTrust — Trust Infrastructure for AI Agents. "
        "Register agents, verify identities, query reputation scores, "
        "rate agents, and manage W3C Verifiable Credentials."
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
        f"Agent registered successfully!",
        f"",
        f"DID:      {did}",
        f"Name:     {data.get('display_name')}",
        f"Status:   {data.get('status')}",
    ]
    if tx:
        lines.append(f"Base TX:  {anchor.get('explorer', tx)}")

    cred = data.get("credential")
    if cred:
        lines.append(f"")
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
        return f"Invalid DID format. Expected: did:moltrust:<16 hex chars>"
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
    ctx: Context[ServerSession, MolTrustClient] = None,
) -> str:
    """Issue or verify a W3C Verifiable Credential.

    Args:
        action: Either "issue" or "verify"
        subject_did: DID of the credential subject (required for "issue")
        credential_type: Type of credential (default: "AgentTrustCredential", only for "issue")
        credential: JSON string of the credential to verify (required for "verify")
    """
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
