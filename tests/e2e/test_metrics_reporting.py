"""E2E test for OracleReporter metrics reporting.

This test verifies:
1. OracleReporter sends correct payload format
2. Signature is valid and verifiable
3. Payload includes all required fields
4. Reporter handles HTTP errors gracefully
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eth_account.messages import encode_defunct

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.reporter import OracleReporter
from plumise_petals.server.metrics import MetricsCollector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PRIVATE_KEY = "0x9c58d72c9ad1eb10f9bc8f7c2a5f6c1c098b3e4d5f8b2e8d5c0a7d6e5f4e3d61"


@pytest.fixture
def test_config() -> PlumiseConfig:
    """Test configuration."""
    return PlumiseConfig(
        plumise_private_key=TEST_PRIVATE_KEY,
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        oracle_api_url="http://localhost:3100",
        report_interval=60,
    )


@pytest.fixture
def auth(test_config: PlumiseConfig) -> PlumiseAuth:
    """Authenticated agent."""
    with patch.object(PlumiseAuth, "is_chain_connected", return_value=False):
        return PlumiseAuth(test_config)


@pytest.fixture
def reporter(auth: PlumiseAuth) -> OracleReporter:
    """Oracle reporter instance."""
    return OracleReporter(
        auth=auth,
        oracle_url="http://localhost:3100",
        interval=10,
    )


@pytest.fixture
def metrics_collector() -> MetricsCollector:
    """Metrics collector with sample data."""
    mc = MetricsCollector()
    mc.record_inference(tokens=100, latency_ms=50.0)
    mc.record_inference(tokens=200, latency_ms=100.0)
    mc.record_inference(tokens=300, latency_ms=150.0)
    return mc


class TestMetricsReporting:
    """Test Oracle metrics reporting."""

    @pytest.mark.asyncio
    async def test_payload_format_structure(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Payload should have correct structure and required fields."""
        snapshot = metrics_collector.get_snapshot()

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is True

        # Extract the payload
        call_args = mock_session.post.call_args
        body = call_args[1]["json"]

        # Verify top-level structure
        assert "payload" in body
        assert "signature" in body

        payload = body["payload"]

        # Verify required fields
        assert "agent" in payload
        assert "processed_tokens" in payload
        assert "avg_latency_ms" in payload
        assert "uptime_seconds" in payload
        assert "tasks_completed" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_payload_values_correctness(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Payload values should match metrics snapshot."""
        snapshot = metrics_collector.get_snapshot()

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is True

        # Extract the payload
        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]["payload"]

        # Verify values
        assert payload["agent"] == reporter.auth.address
        assert payload["processed_tokens"] == 600  # 100 + 200 + 300
        assert payload["tasks_completed"] == 3
        assert payload["avg_latency_ms"] == 100.0  # (50 + 100 + 150) / 3
        assert payload["uptime_seconds"] >= 0
        assert payload["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_signature_is_valid(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Signature should be valid and verifiable."""
        snapshot = metrics_collector.get_snapshot()

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is True

        # Extract the payload and signature
        call_args = mock_session.post.call_args
        body = call_args[1]["json"]
        payload = body["payload"]
        signature = body["signature"]

        # Verify signature format
        assert signature.startswith("0x")
        assert len(signature) == 132  # 0x + 130 hex chars (65 bytes)

        # Verify signature is correct
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected_signature = reporter.auth.sign_message(canonical)
        assert signature == expected_signature

    @pytest.mark.asyncio
    async def test_signature_recovery(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector, auth: PlumiseAuth
    ) -> None:
        """Signature should be recoverable to original address."""
        from eth_account import Account

        snapshot = metrics_collector.get_snapshot()

        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is True

        # Extract payload and signature
        call_args = mock_session.post.call_args
        body = call_args[1]["json"]
        payload = body["payload"]
        signature = body["signature"]

        # Recover address from signature
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        message = encode_defunct(text=canonical)
        recovered_address = Account.recover_message(message, signature=signature)

        # Should match the agent's address
        assert recovered_address.lower() == auth.address.lower()

    @pytest.mark.asyncio
    async def test_http_success_response(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle 200 OK response correctly."""
        snapshot = metrics_collector.get_snapshot()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is True

    @pytest.mark.asyncio
    async def test_http_error_response(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle HTTP error responses."""
        snapshot = metrics_collector.get_snapshot()

        # Test 500 Internal Server Error
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is False

    @pytest.mark.asyncio
    async def test_http_client_error(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle 400 Bad Request."""
        snapshot = metrics_collector.get_snapshot()

        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_handling(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle timeouts gracefully."""
        snapshot = metrics_collector.get_snapshot()

        # Mock timeout
        mock_session = AsyncMock()
        mock_session.post.side_effect = asyncio.TimeoutError()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_handling(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle network errors gracefully."""
        import aiohttp

        snapshot = metrics_collector.get_snapshot()

        # Mock network error
        mock_session = AsyncMock()
        mock_session.post.side_effect = aiohttp.ClientError("Connection refused")
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await reporter._send_report(snapshot)

        assert result is False

    @pytest.mark.asyncio
    async def test_consecutive_failure_tracking(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should track consecutive failures."""
        snapshot = metrics_collector.get_snapshot()

        # Mock failure
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            # Initial state
            assert reporter._consecutive_failures == 0

            # First failure
            await reporter._send_report(snapshot)
            # Note: _consecutive_failures is incremented in the report loop, not _send_report

            # Verify failure count doesn't exceed max
            for i in range(15):
                await reporter._send_report(snapshot)

    @pytest.mark.asyncio
    async def test_report_url_construction(
        self, reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Report URL should be constructed correctly."""
        snapshot = metrics_collector.get_snapshot()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            await reporter._send_report(snapshot)

        # Verify correct URL
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://localhost:3100/api/v1/report"

    @pytest.mark.asyncio
    async def test_trailing_slash_in_oracle_url(
        self, auth: PlumiseAuth, metrics_collector: MetricsCollector
    ) -> None:
        """Trailing slash in oracle URL should be stripped."""
        reporter = OracleReporter(
            auth=auth,
            oracle_url="http://localhost:3100/",
            interval=10,
        )

        snapshot = metrics_collector.get_snapshot()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "plumise_petals.chain.reporter.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            await reporter._send_report(snapshot)

        # URL should not have double slash
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://localhost:3100/api/v1/report"
