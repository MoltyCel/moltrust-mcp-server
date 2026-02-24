<!-- mcp-name: io.github.MoltyCel/moltrust-mcp-server -->
# MolTrust MCP Server

MCP server for [MolTrust](https://moltrust.ch) — Trust Infrastructure for AI Agents.

Register agents, verify identities, query reputation, rate agents, and manage W3C Verifiable Credentials — all through the [Model Context Protocol](https://modelcontextprotocol.io).

## Tools

| Tool | Description |
|------|-------------|
| `moltrust_register` | Register a new AI agent. Returns DID + Verifiable Credential. |
| `moltrust_verify` | Verify an agent by DID. Returns verification status + trust card. |
| `moltrust_reputation` | Get reputation score (1-5) and total ratings for a DID. |
| `moltrust_rate` | Rate another agent (1-5 stars). |
| `moltrust_credential` | Issue or verify a W3C Verifiable Credential. |
| `moltrust_credits` | Check balance, view pricing, transfer credits, or view transaction history. |

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
- "Rate agent did:moltrust:b2c3d4e5f6071890 with 5 stars from did:moltrust:a1b2c3d4e5f60718"
- "Issue a credential for did:moltrust:a1b2c3d4e5f60718"
- "Check my credit balance for did:moltrust:a1b2c3d4e5f60718"
- "Show API pricing"
- "Transfer 10 credits from did:moltrust:a1b2c3d4e5f60718 to did:moltrust:b2c3d4e5f6071890"

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

## License

MIT — CryptoKRI GmbH
