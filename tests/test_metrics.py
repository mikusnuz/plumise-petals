"""Tests for MetricsCollector and InferenceMetrics."""

from __future__ import annotations

import threading
import time

import pytest

from plumise_petals.server.metrics import InferenceMetrics, MetricsCollector


class TestInferenceMetrics:
    """Test the InferenceMetrics dataclass."""

    def test_default_values(self) -> None:
        """Fresh metrics should have zero counters."""
        m = InferenceMetrics()
        assert m.total_tokens_processed == 0
        assert m.total_requests == 0
        assert m.total_latency_ms == 0.0

    def test_avg_latency_zero_requests(self) -> None:
        """Average latency with no requests should be 0."""
        m = InferenceMetrics()
        assert m.avg_latency_ms == 0.0

    def test_avg_latency(self) -> None:
        """Average latency should be total / count."""
        m = InferenceMetrics(
            total_requests=4,
            total_latency_ms=400.0,
        )
        assert m.avg_latency_ms == 100.0

    def test_uptime_seconds(self) -> None:
        """Uptime should be positive after a short sleep."""
        m = InferenceMetrics(start_time=time.time() - 5.0)
        assert m.uptime_seconds >= 4

    def test_tokens_per_second(self) -> None:
        """Throughput calculation."""
        m = InferenceMetrics(
            total_tokens_processed=100,
            start_time=time.time() - 10.0,
        )
        tps = m.tokens_per_second
        assert 8.0 <= tps <= 12.0  # ~10 tokens/sec, with tolerance

    def test_tokens_per_second_zero_uptime(self) -> None:
        """Throughput with zero uptime should be 0."""
        m = InferenceMetrics(
            total_tokens_processed=100,
            start_time=time.time(),
        )
        assert m.tokens_per_second == 0.0

    def test_to_dict(self) -> None:
        """Serialization should include all expected keys."""
        m = InferenceMetrics(
            total_tokens_processed=50,
            total_requests=5,
            total_latency_ms=250.0,
            start_time=time.time() - 10.0,
        )
        d = m.to_dict()
        assert "total_tokens_processed" in d
        assert "total_requests" in d
        assert "avg_latency_ms" in d
        assert "uptime_seconds" in d
        assert "tokens_per_second" in d
        assert d["total_tokens_processed"] == 50
        assert d["total_requests"] == 5
        assert d["avg_latency_ms"] == 50.0


class TestMetricsCollector:
    """Test the thread-safe MetricsCollector."""

    def test_initial_state(self) -> None:
        """Fresh collector should have zero metrics."""
        mc = MetricsCollector()
        snap = mc.get_snapshot()
        assert snap.total_tokens_processed == 0
        assert snap.total_requests == 0

    def test_record_inference(self) -> None:
        """Recording should increment counters."""
        mc = MetricsCollector()
        mc.record_inference(tokens=10, latency_ms=50.0)
        mc.record_inference(tokens=20, latency_ms=100.0)

        snap = mc.get_snapshot()
        assert snap.total_tokens_processed == 30
        assert snap.total_requests == 2
        assert snap.total_latency_ms == 150.0

    def test_snapshot_is_immutable(self) -> None:
        """Snapshot should not change after further recordings."""
        mc = MetricsCollector()
        mc.record_inference(tokens=10, latency_ms=50.0)

        snap = mc.get_snapshot()
        mc.record_inference(tokens=100, latency_ms=500.0)

        # Original snapshot unchanged
        assert snap.total_tokens_processed == 10
        assert snap.total_requests == 1

    def test_reset(self) -> None:
        """Reset should return snapshot and zero counters."""
        mc = MetricsCollector()
        mc.record_inference(tokens=10, latency_ms=50.0)
        mc.record_inference(tokens=20, latency_ms=100.0)

        snap = mc.reset()
        assert snap.total_tokens_processed == 30
        assert snap.total_requests == 2

        # After reset, counters should be zero
        new_snap = mc.get_snapshot()
        assert new_snap.total_tokens_processed == 0
        assert new_snap.total_requests == 0

    def test_thread_safety(self) -> None:
        """Concurrent recording from multiple threads should not lose data."""
        mc = MetricsCollector()
        num_threads = 10
        records_per_thread = 1000

        def worker() -> None:
            for _ in range(records_per_thread):
                mc.record_inference(tokens=1, latency_ms=1.0)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = mc.get_snapshot()
        expected = num_threads * records_per_thread
        assert snap.total_tokens_processed == expected
        assert snap.total_requests == expected
        assert snap.total_latency_ms == float(expected)

    def test_repr(self) -> None:
        """repr should not raise."""
        mc = MetricsCollector()
        r = repr(mc)
        assert "MetricsCollector" in r
