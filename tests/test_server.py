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


class TestMoltguardScore:
    @pytest.mark.asyncio
    async def test_score_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "score": 75,
            "wallet": "0x1234567890abcdef1234567890abcdef12345678",
            "breakdown": {"txCount": 20, "walletAge": 15, "usdcBalance": 10},
            "_meta": {"dataSource": "blockscout"},
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_score"].fn(
            address="0x1234567890abcdef1234567890abcdef12345678", ctx=ctx,
        )
        assert "75" in result
        assert "txCount" in result

    @pytest.mark.asyncio
    async def test_score_error(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(400, {}))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_score"].fn(
            address="invalid", ctx=ctx,
        )
        assert "Error 400" in result


class TestMoltguardSybil:
    @pytest.mark.asyncio
    async def test_sybil_clean(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "sybilScore": 15,
            "confidence": "high",
            "wallet": "0xabc",
            "recommendation": "low_risk",
            "indicators": {
                "walletAgeDays": 200,
                "txCount": 50,
                "uniqueCounterparties": 30,
                "hasUsdcBalance": True,
                "patternMatch": [],
            },
            "cluster": {"detected": False},
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_sybil"].fn(
            address="0xabc", ctx=ctx,
        )
        assert "15" in result
        assert "low_risk" in result

    @pytest.mark.asyncio
    async def test_sybil_cluster_detected(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "sybilScore": 85,
            "confidence": "high",
            "wallet": "0xabc",
            "recommendation": "high_risk",
            "indicators": {
                "walletAgeDays": 2,
                "txCount": 3,
                "uniqueCounterparties": 1,
                "hasUsdcBalance": False,
                "patternMatch": ["bulk_funded"],
            },
            "cluster": {
                "detected": True,
                "estimatedSize": 50,
                "fundingSource": "0xfunder",
                "fundingAmountEth": "0.01",
                "siblingWallets": 49,
            },
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_sybil"].fn(
            address="0xabc", ctx=ctx,
        )
        assert "Cluster DETECTED" in result
        assert "50" in result


class TestMoltguardMarket:
    @pytest.mark.asyncio
    async def test_market_check(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "anomalyScore": 42,
            "marketId": "market123",
            "marketQuestion": "Will X happen?",
            "assessment": "moderate_concern",
            "signals": {
                "volumeSpike": True,
                "volumeChange24h": 150000,
                "priceVolumeDiv": False,
            },
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_market"].fn(
            market_id="market123", ctx=ctx,
        )
        assert "42" in result
        assert "Will X happen?" in result


class TestMoltguardFeed:
    @pytest.mark.asyncio
    async def test_feed_with_anomalies(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "totalScanned": 20,
            "markets": [
                {"anomalyScore": 65, "marketId": "m1", "marketQuestion": "Test market?"},
            ],
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_feed"].fn(ctx=ctx)
        assert "20" in result
        assert "65" in result

    @pytest.mark.asyncio
    async def test_feed_no_anomalies(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "totalScanned": 20,
            "markets": [],
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_feed"].fn(ctx=ctx)
        assert "No anomalies" in result


class TestMoltguardCredentials:
    @pytest.mark.asyncio
    async def test_credential_issue(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "type": ["VerifiableCredential", "AgentTrustCredential"],
            "credentialSubject": {"id": "0xabc"},
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_credential_issue"].fn(
            address="0xabc", ctx=ctx,
        )
        assert "AgentTrustCredential" in result

    @pytest.mark.asyncio
    async def test_credential_verify_valid(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "valid": True,
            "payload": {"type": "AgentTrustCredential"},
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_credential_verify"].fn(
            jws="eyJhbGciOiJFZERTQSJ9.payload.sig", ctx=ctx,
        )
        assert "VALID" in result

    @pytest.mark.asyncio
    async def test_credential_verify_invalid(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "valid": False,
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltguard_credential_verify"].fn(
            jws="bad.jws.token", ctx=ctx,
        )
        assert "INVALID" in result


class TestMtShopping:
    @pytest.mark.asyncio
    async def test_shopping_info(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "service": "MT Shopping",
            "version": "1.0.0",
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_shopping_info"].fn(ctx=ctx)
        assert "MT Shopping" in result

    @pytest.mark.asyncio
    async def test_shopping_verify(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "result": "approved",
            "receiptId": "rcpt_123",
            "guardScore": 85,
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_shopping_verify"].fn(
            credential_jws="eyJ.test.jws",
            transaction_amount=99.99,
            transaction_currency="USDC",
            merchant_id="merchant_1",
            item_description="Widget",
            ctx=ctx,
        )
        assert "approved" in result
        assert "85" in result

    @pytest.mark.asyncio
    async def test_shopping_issue_vc(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "jws": "eyJhbGciOiJFZERTQSJ9." + "a" * 200,
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_shopping_issue_vc"].fn(
            agent_did="did:moltrust:agent1",
            human_did="did:moltrust:human1",
            spend_limit=500.0,
            currency="USDC",
            categories="electronics,books",
            ctx=ctx,
        )
        assert "issued" in result.lower()
        assert "500" in result


class TestMtTravel:
    @pytest.mark.asyncio
    async def test_travel_info(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "service": "MT Travel",
            "segments": ["hotel", "flight"],
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_travel_info"].fn(ctx=ctx)
        assert "MT Travel" in result

    @pytest.mark.asyncio
    async def test_travel_verify(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "result": "approved",
            "guardScore": 90,
            "receiptId": "rcpt_travel_1",
            "tripId": "trip_abc",
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_travel_verify"].fn(
            agent_did="did:base:0xagent",
            vc_json='{"type":"TravelAgentCredential"}',
            merchant="hilton.com",
            segment="hotel",
            amount=350.0,
            currency="USDC",
            ctx=ctx,
        )
        assert "approved" in result
        assert "trip_abc" in result

    @pytest.mark.asyncio
    async def test_travel_issue_vc(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "jws": "eyJhbGciOiJFZERTQSJ9." + "b" * 200,
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_travel_issue_vc"].fn(
            agent_did="did:base:0xagent",
            principal_did="did:base:acme",
            segments="hotel,flight",
            spend_limit=2000.0,
            currency="USDC",
            ctx=ctx,
        )
        assert "TravelAgentCredential issued" in result
        assert "2000" in result


class TestMtSkill:
    @pytest.mark.asyncio
    async def test_skill_audit_pass(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "skillName": "web-search",
            "skillVersion": "1.0.0",
            "skillHash": "sha256:abc123",
            "repositoryUrl": "https://github.com/example/skill",
            "passed": True,
            "audit": {"score": 95, "findings": []},
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_skill_audit"].fn(
            github_url="https://github.com/example/skill", ctx=ctx,
        )
        assert "95" in result
        assert "PASS" in result

    @pytest.mark.asyncio
    async def test_skill_audit_fail(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "skillName": "bad-skill",
            "skillVersion": "0.1.0",
            "skillHash": "sha256:bad123",
            "repositoryUrl": "https://github.com/evil/skill",
            "passed": False,
            "audit": {
                "score": 30,
                "findings": [
                    {"severity": "critical", "category": "prompt_injection", "description": "Contains injection", "deduction": 40},
                    {"severity": "critical", "category": "exfiltration", "description": "Data leak pattern", "deduction": 30},
                ],
            },
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_skill_audit"].fn(
            github_url="https://github.com/evil/skill", ctx=ctx,
        )
        assert "FAIL" in result
        assert "prompt_injection" in result

    @pytest.mark.asyncio
    async def test_skill_verify_found(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "verified": True,
            "credential": {
                "issuanceDate": "2026-03-06",
                "expirationDate": "2026-06-04",
                "credentialSubject": {
                    "id": "did:base:0xauthor",
                    "skillName": "web-search",
                    "skillVersion": "1.0.0",
                    "audit": {"score": 95},
                    "anchorTx": "0xabc",
                },
            },
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_skill_verify"].fn(
            skill_hash="sha256:abc123", ctx=ctx,
        )
        assert "VERIFIED" in result
        assert "web-search" in result

    @pytest.mark.asyncio
    async def test_skill_verify_not_found(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "verified": False,
            "message": "No credential found for this hash",
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_skill_verify"].fn(
            skill_hash="sha256:unknown", ctx=ctx,
        )
        assert "NOT VERIFIED" in result

    @pytest.mark.asyncio
    async def test_skill_issue_vc_success(self, mock_client):
        mock_client.http.post = AsyncMock(return_value=make_response(200, {
            "expirationDate": "2026-06-04",
            "credentialSubject": {
                "id": "did:base:0xauthor",
                "skillName": "web-search",
                "skillVersion": "1.0.0",
                "skillHash": "sha256:abc123",
                "audit": {"score": 95},
                "anchorTx": "0xabc",
            },
        }))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["mt_skill_issue_vc"].fn(
            author_did="did:base:0xauthor",
            repository_url="https://github.com/example/skill",
            ctx=ctx,
        )
        assert "VerifiedSkillCredential issued" in result
        assert "web-search" in result


class TestMoltrustErc8004:
    @pytest.mark.asyncio
    async def test_card_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
            "name": "TestAgent",
            "description": "AI agent on MolTrust.",
            "active": True,
            "services": [
                {"name": "DID", "endpoint": "did:moltrust:abc123def4567890"},
                {"name": "web", "endpoint": "https://api.moltrust.ch/identity/resolve/did:moltrust:abc123def4567890"},
            ],
            "registrations": [
                {"agentId": 42, "agentRegistry": "eip155:8453:0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"},
            ],
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="card", did="did:moltrust:abc123def4567890", ctx=ctx,
        )
        assert "TestAgent" in result
        assert "agentId 42" in result
        assert "DID" in result

    @pytest.mark.asyncio
    async def test_card_not_found(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(404, {}))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="card", did="did:moltrust:0000000000000000", ctx=ctx,
        )
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_card_missing_did(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="card", ctx=ctx,
        )
        assert "did is required" in result.lower()

    @pytest.mark.asyncio
    async def test_resolve_success(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(200, {
            "agent_id": 21023,
            "chain": "base",
            "chain_id": 8453,
            "owner": "0x380238347e58435f40B4da1F1A045A271D5838F5",
            "agent_wallet": "0x380238347e58435f40B4da1F1A045A271D5838F5",
            "agent_uri": "https://api.moltrust.ch/agents/did:web:api.moltrust.ch/erc8004",
            "moltrust_did": "did:moltrust:abc123def4567890",
            "moltrust_profile": "https://api.moltrust.ch/identity/resolve/did:moltrust:abc123def4567890",
            "onchain_reputation": {"agent_id": 21023, "count": 0, "summary_value": 0, "decimals": 0, "clients": 0},
        }))

        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="resolve", agent_id=21023, ctx=ctx,
        )
        assert "21023" in result
        assert "base" in result
        assert "did:moltrust:abc123def4567890" in result
        assert "No feedback" in result

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, mock_client):
        mock_client.http.get = AsyncMock(return_value=make_response(404, {}))
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="resolve", agent_id=99999, ctx=ctx,
        )
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_resolve_invalid_id(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="resolve", agent_id=0, ctx=ctx,
        )
        assert "agent_id" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_action(self, mock_client):
        ctx = make_ctx(mock_client)
        result = await mcp._tool_manager._tools["moltrust_erc8004"].fn(
            action="foo", ctx=ctx,
        )
        assert "card" in result and "resolve" in result
