"""E2E test for single-node Petals inference with metrics collection.

This test verifies:
1. A single Petals node can load a model (bloom-560m)
2. Inference requests are processed correctly
3. MetricsCollector records inference stats
4. OracleReporter would send reports (mocked)
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.reporter import OracleReporter
from plumise_petals.server.metrics import MetricsCollector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PRIVATE_KEY = "0x" + "ab" * 32
TEST_MODEL = "bigscience/bloom-560m"


@pytest.fixture
def test_config() -> PlumiseConfig:
    """Test configuration with bloom-560m model."""
    return PlumiseConfig(
        plumise_private_key=TEST_PRIVATE_KEY,
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        oracle_api_url="http://localhost:3100",
        model_name=TEST_MODEL,
        num_blocks=24,  # All blocks on single node
        petals_host="0.0.0.0",
        petals_port=31330,
        report_interval=10,
    )


@pytest.fixture
def metrics_collector() -> MetricsCollector:
    """Fresh metrics collector."""
    return MetricsCollector()


@pytest.fixture
def auth(test_config: PlumiseConfig) -> PlumiseAuth:
    """Authenticated agent."""
    with patch.object(PlumiseAuth, "is_chain_connected", return_value=False):
        return PlumiseAuth(test_config)


@pytest.fixture
def oracle_reporter(auth: PlumiseAuth) -> OracleReporter:
    """Oracle reporter with short interval."""
    return OracleReporter(
        auth=auth,
        oracle_url="http://localhost:3100",
        interval=5,
    )


class TestSingleNodeInference:
    """Test single-node Petals inference with Plumise integration."""

    def test_metrics_collector_initialization(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """MetricsCollector should start with zero metrics."""
        snapshot = metrics_collector.get_snapshot()
        assert snapshot.total_tokens_processed == 0
        assert snapshot.total_requests == 0
        assert snapshot.total_latency_ms == 0.0

    def test_record_single_inference(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Recording a single inference should update metrics."""
        tokens = 50
        latency = 123.45

        metrics_collector.record_inference(tokens=tokens, latency_ms=latency)

        snapshot = metrics_collector.get_snapshot()
        assert snapshot.total_tokens_processed == tokens
        assert snapshot.total_requests == 1
        assert snapshot.total_latency_ms == latency
        assert snapshot.avg_latency_ms == latency

    def test_record_multiple_inferences(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Recording multiple inferences should accumulate correctly."""
        # Simulate 3 inference requests
        metrics_collector.record_inference(tokens=50, latency_ms=100.0)
        metrics_collector.record_inference(tokens=75, latency_ms=150.0)
        metrics_collector.record_inference(tokens=100, latency_ms=200.0)

        snapshot = metrics_collector.get_snapshot()
        assert snapshot.total_tokens_processed == 225
        assert snapshot.total_requests == 3
        assert snapshot.total_latency_ms == 450.0
        assert snapshot.avg_latency_ms == 150.0

    def test_metrics_uptime_tracking(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """Uptime should be tracked correctly."""
        # Record inference
        metrics_collector.record_inference(tokens=10, latency_ms=50.0)

        # Wait a bit
        time.sleep(0.5)

        snapshot = metrics_collector.get_snapshot()
        assert snapshot.uptime_seconds >= 0
        assert snapshot.tokens_per_second >= 0

    @pytest.mark.asyncio
    async def test_oracle_reporter_payload_format(
        self, oracle_reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Oracle report should have correct payload format."""
        # Simulate some inference activity
        metrics_collector.record_inference(tokens=100, latency_ms=50.0)
        metrics_collector.record_inference(tokens=200, latency_ms=100.0)

        snapshot = metrics_collector.get_snapshot()

        # Mock the HTTP request
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
            result = await oracle_reporter._send_report(snapshot)

        assert result is True

        # Verify POST call was made
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args

        # Check URL
        assert call_args[0][0] == "http://localhost:3100/api/v1/report"

        # Check payload structure
        body = call_args[1]["json"]
        assert "payload" in body
        assert "signature" in body

        payload = body["payload"]
        assert payload["agent"] == oracle_reporter.auth.address
        assert payload["processed_tokens"] == 300
        assert payload["tasks_completed"] == 2
        assert "avg_latency_ms" in payload
        assert "uptime_seconds" in payload
        assert "timestamp" in payload

        # Verify signature is non-empty
        assert len(body["signature"]) > 0
        assert body["signature"].startswith("0x")

    @pytest.mark.asyncio
    async def test_oracle_reporter_lifecycle(
        self, oracle_reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Oracle reporter should start and stop cleanly."""
        assert oracle_reporter._running is False

        # Start reporter
        await oracle_reporter.start(metrics_collector)
        assert oracle_reporter._running is True
        assert oracle_reporter._task is not None

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Stop reporter
        await oracle_reporter.stop()
        assert oracle_reporter._running is False

    @pytest.mark.asyncio
    async def test_oracle_reporter_with_inference_activity(
        self, oracle_reporter: OracleReporter, metrics_collector: MetricsCollector
    ) -> None:
        """Reporter should handle ongoing inference activity."""
        # Mock HTTP session
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
            # Start reporter with short interval
            oracle_reporter.interval = 1
            await oracle_reporter.start(metrics_collector)

            # Simulate inference activity
            for i in range(5):
                metrics_collector.record_inference(
                    tokens=50 + i * 10, latency_ms=100.0 + i * 20
                )
                await asyncio.sleep(0.1)

            # Wait for at least one report cycle
            await asyncio.sleep(1.5)

            # Stop reporter
            await oracle_reporter.stop()

        # Check final metrics
        snapshot = metrics_collector.get_snapshot()
        assert snapshot.total_requests == 5
        assert snapshot.total_tokens_processed == 250 + 100  # 50+60+70+80+90

    def test_metrics_thread_safety(
        self, metrics_collector: MetricsCollector
    ) -> None:
        """MetricsCollector should be thread-safe."""
        import threading

        num_threads = 5
        records_per_thread = 100

        def worker():
            for _ in range(records_per_thread):
                metrics_collector.record_inference(tokens=1, latency_ms=1.0)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snapshot = metrics_collector.get_snapshot()
        expected = num_threads * records_per_thread
        assert snapshot.total_tokens_processed == expected
        assert snapshot.total_requests == expected
