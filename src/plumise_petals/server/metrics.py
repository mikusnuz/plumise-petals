"""Inference metrics collection for the Plumise Petals server.

Provides a thread-safe ``MetricsCollector`` that hooks into the Petals
inference pipeline and aggregates per-request statistics for reporting
to the Plumise Oracle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class InferenceMetrics:
    """Snapshot of inference metrics at a point in time.

    Attributes:
        total_tokens_processed: Cumulative tokens generated/processed.
        total_requests: Number of inference requests handled.
        total_latency_ms: Sum of all request latencies in milliseconds.
        start_time: Epoch timestamp when metrics collection started.
    """

    total_tokens_processed: int = 0
    total_requests: int = 0
    total_latency_ms: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        """Average per-request latency in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def uptime_seconds(self) -> int:
        """Seconds elapsed since collection started."""
        return int(time.time() - self.start_time)

    @property
    def tokens_per_second(self) -> float:
        """Throughput: tokens per second since start."""
        elapsed = self.uptime_seconds
        if elapsed == 0:
            return 0.0
        return self.total_tokens_processed / elapsed

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "total_tokens_processed": self.total_tokens_processed,
            "total_requests": self.total_requests,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "uptime_seconds": self.uptime_seconds,
            "tokens_per_second": round(self.tokens_per_second, 2),
        }


class MetricsCollector:
    """Thread-safe inference metrics collector.

    This object is shared between Petals server handler threads and the
    async reporter loop. All mutations are guarded by a lock.
    """

    def __init__(self) -> None:
        self._metrics = InferenceMetrics(start_time=time.time())
        self._lock = threading.Lock()

    def record_inference(self, tokens: int, latency_ms: float) -> None:
        """Record a single inference request.

        Args:
            tokens: Number of tokens generated/processed in this request.
            latency_ms: End-to-end latency of the request in milliseconds.
        """
        with self._lock:
            self._metrics.total_tokens_processed += tokens
            self._metrics.total_requests += 1
            self._metrics.total_latency_ms += latency_ms

    def get_snapshot(self) -> InferenceMetrics:
        """Return an immutable snapshot of the current metrics.

        The returned ``InferenceMetrics`` is a copy and will not be
        affected by further calls to ``record_inference``.
        """
        with self._lock:
            return InferenceMetrics(
                total_tokens_processed=self._metrics.total_tokens_processed,
                total_requests=self._metrics.total_requests,
                total_latency_ms=self._metrics.total_latency_ms,
                start_time=self._metrics.start_time,
            )

    def reset(self) -> InferenceMetrics:
        """Snapshot and reset all counters (preserving start_time).

        Returns the snapshot taken just before the reset.
        """
        with self._lock:
            snapshot = InferenceMetrics(
                total_tokens_processed=self._metrics.total_tokens_processed,
                total_requests=self._metrics.total_requests,
                total_latency_ms=self._metrics.total_latency_ms,
                start_time=self._metrics.start_time,
            )
            self._metrics.total_tokens_processed = 0
            self._metrics.total_requests = 0
            self._metrics.total_latency_ms = 0.0
            return snapshot

    def __repr__(self) -> str:
        snap = self.get_snapshot()
        return (
            f"MetricsCollector(tokens={snap.total_tokens_processed}, "
            f"requests={snap.total_requests}, "
            f"uptime={snap.uptime_seconds}s)"
        )
