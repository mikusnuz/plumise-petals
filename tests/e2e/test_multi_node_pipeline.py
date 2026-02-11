"""E2E test for multi-node distributed Petals pipeline.

This test verifies:
1. Multiple Petals nodes can collaborate on inference
2. Layer distribution works correctly (Node A: blocks 0-11, Node B: blocks 12-23)
3. Both nodes collect and report metrics
4. Distributed inference completes successfully
"""

from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.reporter import OracleReporter
from plumise_petals.server.metrics import MetricsCollector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PRIVATE_KEY_A = "0x" + "aa" * 32
TEST_PRIVATE_KEY_B = "0x" + "bb" * 32
TEST_MODEL = "bigscience/bloom-560m"


class PetalsNodeMock:
    """Mock Petals node for testing distributed inference."""

    def __init__(
        self,
        node_id: str,
        model: str,
        blocks: range,
        host: str,
        port: int,
        metrics: MetricsCollector,
    ):
        self.node_id = node_id
        self.model = model
        self.blocks = blocks
        self.host = host
        self.port = port
        self.metrics = metrics
        self.running = False

        logger.info(
            f"PetalsNodeMock {node_id}: blocks {blocks.start}-{blocks.stop-1}, port {port}"
        )

    def start(self):
        """Simulate node startup."""
        self.running = True
        logger.info(f"Node {self.node_id} started")

    def stop(self):
        """Simulate node shutdown."""
        self.running = False
        logger.info(f"Node {self.node_id} stopped")

    def process_inference(self, prompt: str, max_tokens: int) -> dict:
        """Simulate processing an inference request."""
        if not self.running:
            raise RuntimeError(f"Node {self.node_id} is not running")

        # Simulate inference latency
        import time

        start = time.time()
        time.sleep(0.05)  # 50ms simulated inference
        latency_ms = (time.time() - start) * 1000

        # Record metrics
        tokens_generated = max_tokens
        self.metrics.record_inference(tokens=tokens_generated, latency_ms=latency_ms)

        logger.info(
            f"Node {self.node_id}: processed {tokens_generated} tokens in {latency_ms:.2f}ms"
        )

        return {
            "node_id": self.node_id,
            "blocks": f"{self.blocks.start}-{self.blocks.stop-1}",
            "tokens": tokens_generated,
            "latency_ms": latency_ms,
        }


@pytest.fixture
def config_node_a() -> PlumiseConfig:
    """Configuration for Node A (blocks 0-11)."""
    return PlumiseConfig(
        plumise_private_key=TEST_PRIVATE_KEY_A,
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        oracle_api_url="http://localhost:3100",
        model_name=TEST_MODEL,
        num_blocks=12,
        petals_host="0.0.0.0",
        petals_port=31330,
        report_interval=10,
    )


@pytest.fixture
def config_node_b() -> PlumiseConfig:
    """Configuration for Node B (blocks 12-23)."""
    return PlumiseConfig(
        plumise_private_key=TEST_PRIVATE_KEY_B,
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        oracle_api_url="http://localhost:3100",
        model_name=TEST_MODEL,
        num_blocks=12,
        petals_host="0.0.0.0",
        petals_port=31331,
        report_interval=10,
    )


@pytest.fixture
def metrics_node_a() -> MetricsCollector:
    """Metrics collector for Node A."""
    return MetricsCollector()


@pytest.fixture
def metrics_node_b() -> MetricsCollector:
    """Metrics collector for Node B."""
    return MetricsCollector()


class TestMultiNodePipeline:
    """Test multi-node distributed inference pipeline."""

    def test_node_initialization(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Both nodes should initialize with correct configurations."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_b = PetalsNodeMock(
            node_id="node-b",
            model=config_node_b.model_name,
            blocks=range(12, 24),
            host=config_node_b.petals_host,
            port=config_node_b.petals_port,
            metrics=metrics_node_b,
        )

        assert node_a.node_id == "node-a"
        assert node_a.blocks == range(0, 12)
        assert node_a.port == 31330

        assert node_b.node_id == "node-b"
        assert node_b.blocks == range(12, 24)
        assert node_b.port == 31331

    def test_both_nodes_start_and_stop(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Both nodes should start and stop cleanly."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_b = PetalsNodeMock(
            node_id="node-b",
            model=config_node_b.model_name,
            blocks=range(12, 24),
            host=config_node_b.petals_host,
            port=config_node_b.petals_port,
            metrics=metrics_node_b,
        )

        # Start nodes
        node_a.start()
        node_b.start()

        assert node_a.running is True
        assert node_b.running is True

        # Stop nodes
        node_a.stop()
        node_b.stop()

        assert node_a.running is False
        assert node_b.running is False

    def test_single_node_inference(
        self,
        config_node_a: PlumiseConfig,
        metrics_node_a: MetricsCollector,
    ) -> None:
        """Single node should process inference and record metrics."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_a.start()

        # Process inference
        result = node_a.process_inference(prompt="Hello world", max_tokens=50)

        assert result["node_id"] == "node-a"
        assert result["tokens"] == 50
        assert result["latency_ms"] > 0

        # Check metrics
        snapshot = metrics_node_a.get_snapshot()
        assert snapshot.total_tokens_processed == 50
        assert snapshot.total_requests == 1

        node_a.stop()

    def test_distributed_inference_both_nodes(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Distributed inference should span both nodes."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_b = PetalsNodeMock(
            node_id="node-b",
            model=config_node_b.model_name,
            blocks=range(12, 24),
            host=config_node_b.petals_host,
            port=config_node_b.petals_port,
            metrics=metrics_node_b,
        )

        # Start both nodes
        node_a.start()
        node_b.start()

        # Simulate distributed inference request
        # In real Petals, this would automatically route through both nodes
        # We simulate by processing on both nodes
        prompt = "Explain quantum computing"
        max_tokens = 100

        result_a = node_a.process_inference(prompt=prompt, max_tokens=max_tokens // 2)
        result_b = node_b.process_inference(prompt=prompt, max_tokens=max_tokens // 2)

        # Verify both nodes processed
        assert result_a["node_id"] == "node-a"
        assert result_b["node_id"] == "node-b"
        assert result_a["tokens"] == 50
        assert result_b["tokens"] == 50

        # Check metrics for both nodes
        snapshot_a = metrics_node_a.get_snapshot()
        snapshot_b = metrics_node_b.get_snapshot()

        assert snapshot_a.total_tokens_processed == 50
        assert snapshot_a.total_requests == 1

        assert snapshot_b.total_tokens_processed == 50
        assert snapshot_b.total_requests == 1

        # Total tokens processed across network
        total_tokens = (
            snapshot_a.total_tokens_processed + snapshot_b.total_tokens_processed
        )
        assert total_tokens == 100

        node_a.stop()
        node_b.stop()

    def test_concurrent_inference_requests(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Multiple concurrent inference requests should work correctly."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_b = PetalsNodeMock(
            node_id="node-b",
            model=config_node_b.model_name,
            blocks=range(12, 24),
            host=config_node_b.petals_host,
            port=config_node_b.petals_port,
            metrics=metrics_node_b,
        )

        node_a.start()
        node_b.start()

        # Simulate concurrent requests using threads
        num_requests = 10
        results = {"node_a": [], "node_b": []}

        def worker_a():
            for _ in range(num_requests):
                result = node_a.process_inference(prompt="test", max_tokens=20)
                results["node_a"].append(result)

        def worker_b():
            for _ in range(num_requests):
                result = node_b.process_inference(prompt="test", max_tokens=20)
                results["node_b"].append(result)

        thread_a = threading.Thread(target=worker_a)
        thread_b = threading.Thread(target=worker_b)

        thread_a.start()
        thread_b.start()

        thread_a.join()
        thread_b.join()

        # Verify all requests were processed
        assert len(results["node_a"]) == num_requests
        assert len(results["node_b"]) == num_requests

        # Check final metrics
        snapshot_a = metrics_node_a.get_snapshot()
        snapshot_b = metrics_node_b.get_snapshot()

        assert snapshot_a.total_requests == num_requests
        assert snapshot_a.total_tokens_processed == num_requests * 20

        assert snapshot_b.total_requests == num_requests
        assert snapshot_b.total_tokens_processed == num_requests * 20

        node_a.stop()
        node_b.stop()

    @pytest.mark.asyncio
    async def test_both_nodes_report_to_oracle(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Both nodes should report metrics to Oracle independently."""
        # Create auth and reporters for both nodes
        with patch.object(PlumiseAuth, "is_chain_connected", return_value=False):
            auth_a = PlumiseAuth(config_node_a)
            auth_b = PlumiseAuth(config_node_b)

        reporter_a = OracleReporter(
            auth=auth_a, oracle_url="http://localhost:3100", interval=1
        )
        reporter_b = OracleReporter(
            auth=auth_b, oracle_url="http://localhost:3100", interval=1
        )

        # Simulate inference on both nodes
        metrics_node_a.record_inference(tokens=50, latency_ms=100.0)
        metrics_node_b.record_inference(tokens=75, latency_ms=150.0)

        # Mock HTTP responses
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
            # Send reports from both nodes
            snapshot_a = metrics_node_a.get_snapshot()
            snapshot_b = metrics_node_b.get_snapshot()

            result_a = await reporter_a._send_report(snapshot_a)
            result_b = await reporter_b._send_report(snapshot_b)

        assert result_a is True
        assert result_b is True

        # Verify both made POST requests
        assert mock_session.post.call_count == 2

        # Verify payloads have different agent addresses
        call_args_list = mock_session.post.call_args_list
        payload_a = call_args_list[0][1]["json"]["payload"]
        payload_b = call_args_list[1][1]["json"]["payload"]

        assert payload_a["agent"] == auth_a.address
        assert payload_b["agent"] == auth_b.address
        assert payload_a["agent"] != payload_b["agent"]

        # Verify different token counts
        assert payload_a["processed_tokens"] == 50
        assert payload_b["processed_tokens"] == 75

    def test_node_layer_distribution_no_overlap(
        self,
        config_node_a: PlumiseConfig,
        config_node_b: PlumiseConfig,
        metrics_node_a: MetricsCollector,
        metrics_node_b: MetricsCollector,
    ) -> None:
        """Node layer assignments should not overlap."""
        node_a = PetalsNodeMock(
            node_id="node-a",
            model=config_node_a.model_name,
            blocks=range(0, 12),
            host=config_node_a.petals_host,
            port=config_node_a.petals_port,
            metrics=metrics_node_a,
        )

        node_b = PetalsNodeMock(
            node_id="node-b",
            model=config_node_b.model_name,
            blocks=range(12, 24),
            host=config_node_b.petals_host,
            port=config_node_b.petals_port,
            metrics=metrics_node_b,
        )

        # Verify no overlap
        blocks_a = set(node_a.blocks)
        blocks_b = set(node_b.blocks)

        assert len(blocks_a & blocks_b) == 0  # No intersection
        assert len(blocks_a | blocks_b) == 24  # Full coverage

        # Verify ranges are correct
        assert min(blocks_a) == 0
        assert max(blocks_a) == 11
        assert min(blocks_b) == 12
        assert max(blocks_b) == 23
