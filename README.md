<!-- mcp-name: io.github.MoltyCel/moltrust-mcp-server -->
# MolTrust MCP Server

[![PyPI](https://img.shields.io/pypi/v/moltrust-mcp-server)](https://pypi.org/project/moltrust-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Glama](https://img.shields.io/badge/Glama-listed-blue)](https://glama.ai/mcp/servers/@MoltyCel/moltrust-mcp-server)
[![Smithery](https://img.shields.io/badge/Smithery-listed-8A2BE2)](https://smithery.ai/servers/moltrust/moltrust-mcp-server)

MCP server for [MolTrust](https://moltrust.ch) — Trust Infrastructure for AI Agents.

61 tools at the hosted endpoint `https://api.moltrust.ch/mcp`, across 13 areas: identity and credentials, on-chain trust scoring, mandate conformance, swarm intelligence, verified badges, autonomous commerce, booking trust, agent skill verification, prediction market track records, fantasy lineup commitments, music provenance, brand and reseller provenance, and Amazon Ads verdicts — all through the [Model Context Protocol](https://modelcontextprotocol.io). The pip package carries 48 of them; the MolCheck verifier tools and the Amazon Ads tools run only at the hosted endpoint.

## Tools

### Identity & Credentials (11 tools)

- `moltrust_claim_deposit` — Claim MolTrust credits from a USDC deposit on Base.
- `moltrust_credential` — Issue or verify a W3C Verifiable Credential.
- `moltrust_credits` — Manage MolTrust credits: check balance, view pricing, transfer credits, or view transaction history.
- `moltrust_deposit_history` — Get USDC deposit history for an agent.
- `moltrust_deposit_info` — Get USDC deposit instructions to buy MolTrust credits.
- `moltrust_erc8004` — Query the ERC-8004 on-chain agent registry on Base.
- `moltrust_rate` — Rate another AI agent (1-5 stars).
- `moltrust_register` — Register a new AI agent on MolTrust.
- `moltrust_reputation` — Get the reputation score for an AI agent.
- `moltrust_stats` — Get MolTrust network statistics.
- `moltrust_verify` — Verify an AI agent by its DID.

### MoltGuard — Agent Trust Scoring (7 tools)

- `moltguard_credential_issue` — Issue a W3C Verifiable Credential (AgentTrustCredential) for a wallet.
- `moltguard_credential_verify` — Verify a MoltGuard Verifiable Credential JWS signature.
- `moltguard_detail` — Get a detailed agent trust report for a Base wallet address.
- `moltguard_feed` — Get the top anomaly feed — markets with highest integrity concerns.
- `moltguard_market` — Check a Polymarket prediction market for integrity anomalies.
- `moltguard_score` — Get an agent trust score for a Base wallet address.
- `moltguard_sybil` — Scan a Base wallet for Sybil indicators.

### MolCheck verifier — Mandate Conformance (5 tools, hosted endpoint only)

- `molcheck_evidence` — Verdict plus the decoded transactions that breached the mandate.
- `molcheck_mandate` — The committed AAE mandate for an agent (venues, position cap, validity).
- `molcheck_registry` — Agents with committed mandates and their current verdict.
- `molcheck_verdict` — Verdict + per-check breakdown for an agent against its committed mandate.
- `molcheck_verify` — Recompute a verdict from public inputs and check its signature.

The former names `moltproof_evidence`, `moltproof_mandate`, `moltproof_registry`, `moltproof_verdict` and
`moltproof_verify` still answer as deprecated aliases of the same tools, so `tools/list` shows 10 entries here.

### Swarm Intelligence (4 tools)

- `mt_get_swarm_graph` — Get the trust propagation graph for an agent (2 hops).
- `mt_get_swarm_stats` — Get global Swarm Intelligence statistics.
- `mt_get_trust_score` — Get the Swarm Intelligence Trust Score for an agent (Phase 2).
- `mt_register_seed` — Register a trusted seed agent in the Swarm Intelligence network (admin only).

### Verified Badges (3 tools)

- `mt_check_badge` — Quick check: is this agent badge-verified by MolTrust?
- `mt_get_badge` — Get the Verified by MolTrust badge status for an agent.
- `mt_issue_badge` — Issue a Verified by MolTrust badge for an agent.

### MT Shopping — Autonomous Commerce (3 tools)

- `mt_shopping_info` — Get MT Shopping API information.
- `mt_shopping_issue_vc` — Issue a BuyerAgentCredential (W3C Verifiable Credential) for a shopping agent.
- `mt_shopping_verify` — Verify a shopping transaction against a BuyerAgentCredential.

### MT Travel — Booking Trust (3 tools)

- `mt_travel_info` — Get MT Travel service information and available endpoints.
- `mt_travel_issue_vc` — Issue a TravelAgentCredential (W3C Verifiable Credential) for a booking agent.
- `mt_travel_verify` — Verify a travel booking against a TravelAgentCredential.

### MT Skills — Agent Skill Verification (5 tools)

- `mt_create_interaction_proof` — Create an interaction proof before issuing a SkillEndorsementCredential.
- `mt_endorse_agent` — Issue a W3C SkillEndorsementCredential for another agent.
- `mt_skill_audit` — Audit an AI agent skill (SKILL.md) for security risks.
- `mt_skill_issue_vc` — Issue a VerifiedSkillCredential for an AI agent skill.
- `mt_skill_verify` — Verify an AI agent skill by its canonical SHA-256 hash.

### MT Prediction — Market Track Records (3 tools)

- `mt_prediction_leaderboard` — Get the prediction market leaderboard — top wallets by prediction score.
- `mt_prediction_link` — Link a prediction market wallet and sync its track record.
- `mt_prediction_wallet` — Get prediction market profile and track record for a wallet.

### MT Sports — Fantasy Lineup Commitments (3 tools)

- `mt_fantasy_commit` — Commit a fantasy lineup with a SHA-256 hash anchored on Base L2.
- `mt_fantasy_history` — Get fantasy lineup history and stats for an agent.
- `mt_fantasy_verify` — Verify a fantasy lineup commitment. Public endpoint, no auth required.

### MT Music — Provenance (3 tools)

- `mt_get_track_provenance` — Get full provenance details for a music credential.
- `mt_issue_music_credential` — Issue a VerifiedMusicCredential for an AI-generated music track.
- `mt_verify_music_credential` — Verify a VerifiedMusicCredential by its ID.

### MT Salesguard — Brand & Reseller Provenance (3 tools)

- `mt_salesguard_register` — Register a brand with MT Salesguard.
- `mt_salesguard_reseller` — Verify reseller authorization via MT Salesguard.
- `mt_salesguard_verify` — Verify product provenance via MT Salesguard.

### MT Ads — Amazon Ads Verdicts (3 tools, hosted endpoint only)

- `ads_check` — Allow / hold / forbid for one intended Amazon Ads MCP tool call, before it runs.
- `ads_mandate_template` — Build an ads profile and its AAE mandate for one or more Amazon Ads accounts.
- `ads_onboard` — How an agent starts with MolTrust Ads: verdicts (allow / hold / forbid) on Amazon Ads tool calls.

## Setup

Get an API key at [api.moltrust.ch/auth/signup](https://api.moltrust.ch/auth/signup).
The read-only tools also work without one.

### Hosted endpoint (all 61 tools)

The hosted endpoint is `https://api.moltrust.ch/mcp` (streamable HTTP). It serves
every tool, including the MolCheck verifier and Amazon Ads tools that the pip package
does not carry. Send the API key as the `X-API-Key` header.

Claude Code:

```bash
claude mcp add --transport http moltrust https://api.moltrust.ch/mcp \
  --header "X-API-Key: your_api_key"
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "moltrust": {
      "url": "https://api.moltrust.ch/mcp",
      "headers": { "X-API-Key": "your_api_key" }
    }
  }
}
```

OpenCode (`opencode.json`):

```json
{
  "mcp": {
    "moltrust": {
      "type": "remote",
      "url": "https://api.moltrust.ch/mcp",
      "enabled": true,
      "headers": { "X-API-Key": "your_api_key" }
    }
  }
}
```

The tool list and schemas are published at
[api.moltrust.ch/.well-known/mcp/server-card.json](https://api.moltrust.ch/.well-known/mcp/server-card.json).

### Local package (48 tools)

The sections below run the pip package locally over stdio with `uvx`. It carries 48
tools; the MolCheck verifier and Amazon Ads tools are only on the hosted endpoint.

### Claude Code

```bash
claude mcp add moltrust -- uvx moltrust-mcp-server
```

Set your API key:

```bash
export MOLTRUST_API_KEY="your_api_key"
```

Or add it permanently to Claude Code:

```bash
claude mcp add moltrust -e MOLTRUST_API_KEY=your_api_key -- uvx moltrust-mcp-server
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "moltrust": {
      "command": "uvx",
      "args": ["moltrust-mcp-server"],
      "env": {
        "MOLTRUST_API_KEY": "your_api_key"
      }
    }
  }
}
```

Config file location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Cursor

Add to Cursor MCP settings (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "moltrust": {
      "command": "uvx",
      "args": ["moltrust-mcp-server"],
      "env": {
        "MOLTRUST_API_KEY": "your_api_key"
      }
    }
  }
}
```

### OpenCode

Add to `opencode.json`:

```json
{
  "mcp": {
    "moltrust": {
      "command": "uvx",
      "args": ["moltrust-mcp-server"],
      "env": {
        "MOLTRUST_API_KEY": "your_api_key"
      }
    }
  }
}
```

### pip install (manual)

```bash
pip install moltrust-mcp-server
```

Then run:

```bash
MOLTRUST_API_KEY=your_api_key moltrust-mcp-server
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MOLTRUST_API_KEY` | — | Your MolTrust API key (required for register, rate, issue) |
| `MOLTRUST_API_URL` | `https://api.moltrust.ch` | API base URL (for self-hosted instances) |
| `MOLTRUST_NO_AUTO_REGISTER` | — | Set to `1` to turn off the automatic DID registration described below |
| `MOLTRUST_DID` | — | Your existing MolTrust DID; when set, nothing is registered |
| `MOLTRUST_IDENTITY_FILE` | `~/.moltrust/mcp-identity.json` | Where the registered identity is stored |
| `MOLTRUST_REGISTER_PLATFORM` | `usage-mcp` | The `platform` value sent with the registration |

## Automatic DID registration

Since 1.3.0 the local package gives itself a MolTrust identity (a
`did:moltrust:` DID) on its first tool call, if it has none. This section says
exactly what that does, so you can decide whether you want it.

**When it runs.** Once per installation and API URL, on the first tool call of
the local stdio server. It does not run when `MOLTRUST_API_KEY` or
`MOLTRUST_DID` is set (you already have an identity), when the `CI`
environment variable is set, on the hosted HTTP endpoint, or when you opt out.

**What is created.** An Ed25519 key pair, generated on your machine. The
private key never leaves it.

**What is sent.** Two requests to the API URL: `GET /identity/register-challenge`
and `POST /identity/register-pop` with the public key, a signature over the
challenge, a proof-of-work nonce, the display name `mcp-server-<first 12 hex
characters of the public key>`, the platform `usage-mcp`, the source
`mcp-server` and the framework `mcp`. Nothing about your tools, prompts,
arguments or environment is sent. The registration is free and creates a
public registry entry for the DID, anchored on Base like any other
registration.

**What is stored.** The DID, the public key and the private key, in
`~/.moltrust/mcp-identity.json` with file mode 0600. Delete the file to forget
the identity; the next first call then registers a new one.

**If it fails.** One line on stderr, and the tool call goes on unchanged. The
registration runs in the background and never delays or fails a tool call.

**Opt out.** Set `MOLTRUST_NO_AUTO_REGISTER=1` in the server's environment, for
example in the `env` block of your MCP client configuration.

## Examples

Once connected, you can ask your AI assistant:

- "Register a new agent called 'my-assistant' on the 'openai' platform"
- "Verify the agent with DID did:moltrust:a1b2c3d4e5f60718"
- "What's the reputation of did:moltrust:a1b2c3d4e5f60718?"
- "Rate agent did:moltrust:b2c3d4e5f6071890 with 5 stars"
- "Get the trust score for wallet 0x1234...abcd"
- "Scan wallet 0x1234...abcd for Sybil indicators"
- "Check Polymarket market abc123 for anomalies"
- "Issue a BuyerAgentCredential for my shopping agent"
- "Verify this travel booking against the agent's credential"
- "Audit this agent skill for security risks: https://github.com/example/skill"
- "Link my Polymarket wallet 0x1234...abcd and show my prediction score"
- "Show the prediction market leaderboard"

## Development

```bash
git clone https://github.com/MoltyCel/moltrust-mcp-server.git
cd moltrust-mcp-server
pip install -e ".[dev]"

# Lint
ruff check src/
ruff format src/

# Type check
pyright src/

# Test
pytest tests/ -v
```

## Security Research

We regularly scan agent infrastructure for security issues and publish our findings:

- **[We Scanned 50 Agent Endpoints — Here's What We Found](https://moltrust.ch/blog/scanned-50-agent-endpoints.html)** — Common vulnerabilities in the agent ecosystem and how to fix them

## License

MIT — CryptoKRI GmbH
