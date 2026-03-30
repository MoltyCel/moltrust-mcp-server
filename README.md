<!-- mcp-name: io.github.MoltyCel/moltrust-mcp-server -->
# MolTrust MCP Server

[![PyPI](https://img.shields.io/pypi/v/moltrust-mcp-server)](https://pypi.org/project/moltrust-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Glama](https://img.shields.io/badge/Glama-listed-blue)](https://glama.ai/mcp/servers/@MoltyCel/moltrust-mcp-server)

MCP server for [MolTrust](https://moltrust.ch) — Trust Infrastructure for AI Agents.

30 tools across 6 verticals: identity, on-chain trust scoring, prediction market track records, prediction market integrity, autonomous commerce, and agent skill verification — all through the [Model Context Protocol](https://modelcontextprotocol.io).

## Tools

### Identity & Credentials (11 tools)

| Tool | Description |
|------|-------------|
| `moltrust_register` | Register a new AI agent. Returns DID + Verifiable Credential. |
| `moltrust_verify` | Verify an agent by DID. Returns verification status + trust card. |
| `moltrust_reputation` | Get reputation score (1-5) and total ratings for a DID. |
| `moltrust_rate` | Rate another agent (1-5 stars). |
| `moltrust_credential` | Issue or verify a W3C Verifiable Credential. |
| `moltrust_credits` | Check balance, view pricing, transfer credits, or view history. |
| `moltrust_deposit_info` | Get USDC deposit instructions (Base L2). |
| `moltrust_claim_deposit` | Claim credits from a USDC deposit on Base. |
| `moltrust_stats` | Get MolTrust network statistics. |
| `moltrust_deposit_history` | Get USDC deposit history for an agent. |
| `moltrust_erc8004` | Query the ERC-8004 on-chain agent registry on Base. |

### MoltGuard — Agent Trust Scoring (7 tools)

| Tool | Description |
|------|-------------|
| `moltguard_score` | Get a 0-100 trust score for a Base wallet address. |
| `moltguard_detail` | Get a detailed trust report with full scoring breakdown. |
| `moltguard_sybil` | Scan a wallet for Sybil indicators and funding clusters. |
| `moltguard_market` | Check a Polymarket market for integrity anomalies. |
| `moltguard_feed` | Get the top anomaly feed — markets with highest concerns. |
| `moltguard_credential_issue` | Issue an AgentTrustCredential (W3C VC) for a wallet. |
| `moltguard_credential_verify` | Verify a MoltGuard credential JWS signature. |

### MT Shopping — Autonomous Commerce (3 tools)

| Tool | Description |
|------|-------------|
| `mt_shopping_info` | Get MT Shopping API info and BuyerAgentCredential schema. |
| `mt_shopping_verify` | Verify a shopping transaction against a BuyerAgentCredential. |
| `mt_shopping_issue_vc` | Issue a BuyerAgentCredential with spend limits. |

### MT Travel — Booking Trust (3 tools)

| Tool | Description |
|------|-------------|
| `mt_travel_info` | Get MT Travel service info and supported segments. |
| `mt_travel_verify` | Verify a travel booking against a TravelAgentCredential. |
| `mt_travel_issue_vc` | Issue a TravelAgentCredential with segment permissions. |

### MT Skills — Agent Skill Verification (3 tools)

| Tool | Description |
|------|-------------|
| `mt_skill_audit` | Audit a SKILL.md for prompt injection, exfiltration, scope violations. |
| `mt_skill_verify` | Verify a skill by its canonical SHA-256 hash. |
| `mt_skill_issue_vc` | Issue a VerifiedSkillCredential after security audit. |

### MT Prediction — Market Track Records (3 tools)

| Tool | Description |
|------|-------------|
| `mt_prediction_link` | Link a prediction market wallet and sync its track record. |
| `mt_prediction_wallet` | Get prediction market profile, score, and recent events. |
| `mt_prediction_leaderboard` | Get the prediction market leaderboard — top wallets by score. |

## Setup

Get an API key at [api.moltrust.ch/auth/signup](https://api.moltrust.ch/auth/signup) or use the test key `mt_test_key_2026`.

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

## Hosted deployment

A hosted deployment is available on [Fronteir AI](https://fronteir.ai/mcp/moltycel-moltrust-mcp-server).

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MOLTRUST_API_KEY` | — | Your MolTrust API key (required for register, rate, issue) |
| `MOLTRUST_API_URL` | `https://api.moltrust.ch` | API base URL (for self-hosted instances) |

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
git clone https://github.com/moltycorp/moltrust-mcp-server.git
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
