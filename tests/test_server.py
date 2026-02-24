"""Tests for moltrust-mcp-server."""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from moltrust_mcp_server.server import (
    mcp,
    MolTrustClient,
)


@pytest.fixture
def mock_client():
    http = AsyncMock(spec=httpx.AsyncClient)
    return MolTrustClient(
        http=http,
        api_key="mt_test_key",
        api_url="https://api.moltrust.ch",
    )


def make_response(status_code: int, json_data: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://api.moltrust.ch/test"),
    )


def make_ctx(client: MolTrustClient):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = client
    return ctx


class TestMoltrustRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "did": "did:moltrust:abc123def4567890",
            "display_name": "test-agent",
            "status": "registered",
            "base_anchor": {"tx_hash": "0xabc", "explorer": "https://basescan.org/tx/0xabc"},
            "credential": {
                "type": ["VerifiableCredential", "AgentTrustCredential"],
                "issuer": "did:web:api.moltrust.ch",
                "expirationDate": "2027-01-01T00:00:00Z",
            },
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_register"].fn(
            display_name="test-agent",
            platform="openai",
            ctx=ctx,
        )

        assert "did:moltrust:abc123def4567890" in result
        assert "registered" in result.lower()
        mock_client.http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_no_api_key(self, mock_client):
        mock_client.api_key = ""
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_register"].fn(
            display_name="test", platform="test", ctx=ctx,
        )
        assert "MOLTRUST_API_KEY" in result

    @pytest.mark.asyncio
    async def test_register_duplicate(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(409, {}))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_register"].fn(
            display_name="dup-agent", platform="test", ctx=ctx,
        )
        assert "Duplicate" in result


class TestMoltrustReputation:
    @pytest.mark.asyncio
    async def test_reputation_with_ratings(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "did": "did:moltrust:abc123def4567890",
            "score": 4.5,
            "total_ratings": 12,
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_reputation"].fn(
            did="did:moltrust:abc123def4567890", ctx=ctx,
        )
        assert "4.5" in result
        assert "12" in result

    @pytest.mark.asyncio
    async def test_reputation_no_ratings(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "did": "did:moltrust:abc123def4567890",
            "score": 0,
            "total_ratings": 0,
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_reputation"].fn(
            did="did:moltrust:abc123def4567890", ctx=ctx,
        )
        assert "No ratings" in result


class TestMoltrustRate:
    @pytest.mark.asyncio
    async def test_rate_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "status": "rated",
            "from": "did:moltrust:aaaaaaaaaaaaaaaa",
            "to": "did:moltrust:bbbbbbbbbbbbbbbb",
            "score": 4,
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_rate"].fn(
            from_did="did:moltrust:aaaaaaaaaaaaaaaa",
            to_did="did:moltrust:bbbbbbbbbbbbbbbb",
            score=4,
            ctx=ctx,
        )
        assert "submitted" in result.lower()
        assert "4" in result

    @pytest.mark.asyncio
    async def test_rate_invalid_score(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_rate"].fn(
            from_did="did:moltrust:aaaaaaaaaaaaaaaa",
            to_did="did:moltrust:bbbbbbbbbbbbbbbb",
            score=6,
            ctx=ctx,
        )
        assert "between 1 and 5" in result


class TestMoltrustCredential:
    @pytest.mark.asyncio
    async def test_issue_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "type": ["VerifiableCredential", "AgentTrustCredential"],
            "issuer": "did:web:api.moltrust.ch",
            "issuanceDate": "2026-01-01T00:00:00Z",
            "expirationDate": "2027-01-01T00:00:00Z",
            "credentialSubject": {
                "id": "did:moltrust:abc123def4567890",
                "reputation": {"score": 4.0, "total_ratings": 5},
            },
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_credential"].fn(
            action="issue",
            subject_did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "issued" in result.lower()
        assert "did:web:api.moltrust.ch" in result

    @pytest.mark.asyncio
    async def test_verify_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "valid": True,
            "issuer": "did:web:api.moltrust.ch",
            "subject": "did:moltrust:abc123def4567890",
            "credential_type": "AgentTrustCredential",
            "expired": False,
        }))

        cred_json = json.dumps({"type": "VerifiableCredential"})
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_credential"].fn(
            action="verify",
            credential=cred_json,
            ctx=ctx,
        )
        assert "Yes" in result
        assert "did:web:api.moltrust.ch" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_credential"].fn(
            action="delete", ctx=ctx,
        )
        assert "issue" in result and "verify" in result


class TestMoltrustDepositInfo:
    @pytest.mark.asyncio
    async def test_deposit_info_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "wallet": "0xWALLET",
            "network": "Base",
            "token": "USDC",
            "token_contract": "0xCONTRACT",
            "rate": "1 USDC = 100 credits",
            "min_confirmations": 12,
            "instructions": ["Step 1: Send USDC", "Step 2: Claim"],
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_info"].fn(
            ctx=ctx,
        )
        assert "0xWALLET" in result
        assert "Base" in result
        assert "USDC" in result
        assert "Step 1" in result

    @pytest.mark.asyncio
    async def test_deposit_info_missing_fields(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {}))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_info"].fn(
            ctx=ctx,
        )
        assert "?" in result

    @pytest.mark.asyncio
    async def test_deposit_info_error(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(500, {}))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_info"].fn(
            ctx=ctx,
        )
        assert "Error 500" in result


class TestMoltrustClaimDeposit:
    @pytest.mark.asyncio
    async def test_claim_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "tx_hash": "0x" + "a1" * 32,
            "from_address": "0xSENDER",
            "usdc_amount": "10.0",
            "credits_granted": 1000,
            "new_balance": 1100,
            "rate": "1 USDC = 100 credits",
            "basescan_url": "https://basescan.org/tx/0x...",
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="0x" + "a1" * 32,
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "Deposit successful" in result
        assert "1000" in result

    @pytest.mark.asyncio
    async def test_claim_no_api_key(self, mock_client):
        mock_client.api_key = ""
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="0x" + "a1" * 32,
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "MOLTRUST_API_KEY" in result

    @pytest.mark.asyncio
    async def test_claim_invalid_tx_hash_no_prefix(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="a1" * 32,
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "0x-prefixed" in result

    @pytest.mark.asyncio
    async def test_claim_invalid_tx_hash_too_short(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="0xabc",
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "0x-prefixed" in result

    @pytest.mark.asyncio
    async def test_claim_duplicate(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(409, {}))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="0x" + "a1" * 32,
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "already been claimed" in result

    @pytest.mark.asyncio
    async def test_claim_forbidden(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(403, {
            "detail": "API key does not own this DID",
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_claim_deposit"].fn(
            tx_hash="0x" + "a1" * 32,
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "Forbidden" in result


class TestMoltrustStats:
    @pytest.mark.asyncio
    async def test_stats_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "total_agents": 42,
            "credentials_issued": 100,
            "total_ratings": 250,
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_stats"].fn(
            ctx=ctx,
        )
        assert "42" in result
        assert "100" in result
        assert "Total Agents" in result

    @pytest.mark.asyncio
    async def test_stats_error(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(503, {}))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_stats"].fn(
            ctx=ctx,
        )
        assert "Error 503" in result


class TestMoltrustDepositHistory:
    @pytest.mark.asyncio
    async def test_history_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "wallet": "0xWALLET",
            "network": "Base",
            "deposits": [
                {
                    "usdc_amount": "10.0",
                    "credits_granted": 1000,
                    "claimed_at": "2026-01-15T12:00:00Z",
                    "basescan_url": "https://basescan.org/tx/0x...",
                },
            ],
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_history"].fn(
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "10.0" in result
        assert "1000" in result
        assert "0xWALLET" in result

    @pytest.mark.asyncio
    async def test_history_empty(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "deposits": [],
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_history"].fn(
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "No USDC deposits" in result

    @pytest.mark.asyncio
    async def test_history_no_api_key(self, mock_client):
        mock_client.api_key = ""
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_history"].fn(
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "MOLTRUST_API_KEY" in result

    @pytest.mark.asyncio
    async def test_history_forbidden(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(403, {
            "detail": "API key does not own this DID",
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_deposit_history"].fn(
            did="did:moltrust:abc123def4567890",
            ctx=ctx,
        )
        assert "Forbidden" in result
