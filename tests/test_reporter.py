"""Tests for OracleReporter."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.reporter import OracleReporter
from plumise_petals.server.metrics import InferenceMetrics, MetricsCollector


_TEST_PRIVATE_KEY = "0x" + "ab" * 32


@pytest.fixture
def config() -> PlumiseConfig:
    return PlumiseConfig(
        plumise_private_key=_TEST_PRIVATE_KEY,
        oracle_api_url="http://localhost:3100",
        report_interval=60,
    )


@pytest.fixture
def auth(config: PlumiseConfig) -> PlumiseAuth:
    return PlumiseAuth(config)


@pytest.fixture
def reporter(auth: PlumiseAuth) -> OracleReporter:
    return OracleReporter(
        auth=auth,
        oracle_url="http://localhost:3100",
        interval=5,
    )


@pytest.fixture
def collector() -> MetricsCollector:
    mc = MetricsCollector()
    mc.record_inference(tokens=100, latency_ms=50.0)
    mc.record_inference(tokens=200, latency_ms=150.0)
    return mc


class TestOracleReporter:
    """Test the Oracle metrics reporter."""

    def test_initialization(self, reporter: OracleReporter) -> None:
        """Reporter should store configuration correctly."""
        assert reporter.oracle_url == "http://localhost:3100"
        assert reporter.interval == 5
        assert reporter._running is False

    def test_url_trailing_slash_stripped(self, auth: PlumiseAuth) -> None:
        """Trailing slash in oracle URL should be removed."""
        r = OracleReporter(auth=auth, oracle_url="http://example.com/")
        assert r.oracle_url == "http://example.com"

    @pytest.mark.asyncio
    async def test_send_report_builds_correct_payload(
        self, reporter: OracleReporter, collector: MetricsCollector
    ) -> None:
        """Report payload should contain expected fields."""
        snapshot = collector.get_snapshot()

        # Mock aiohttp session
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("plumise_petals.chain.reporter.aiohttp.ClientSession", return_value=mock_session):
            result = await reporter._send_report(snapshot)

        assert result is True

        # Verify post was called with correct URL
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://localhost:3100/api/v1/report"

        # Verify payload structure
        body = call_args[1]["json"]
        assert "payload" in body
        assert "signature" in body
        payload = body["payload"]
        assert payload["agent"] == reporter.auth.address
        assert payload["processed_tokens"] == 300
        assert payload["tasks_completed"] == 2
        assert "avg_latency_ms" in payload
        assert "uptime_seconds" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_send_report_handles_failure(
        self, reporter: OracleReporter, collector: MetricsCollector
    ) -> None:
        """Report should return False on HTTP error."""
        snapshot = collector.get_snapshot()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("plumise_petals.chain.reporter.aiohttp.ClientSession", return_value=mock_session):
            result = await reporter._send_report(snapshot)

        assert result is False

    @pytest.mark.asyncio
    async def test_start_stop(
        self, reporter: OracleReporter, collector: MetricsCollector
    ) -> None:
        """Reporter should start and stop cleanly."""
        assert reporter._running is False

        await reporter.start(collector)
        assert reporter._running is True
        assert reporter._task is not None

        await reporter.stop()
        assert reporter._running is False
        assert reporter._task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(
        self, reporter: OracleReporter, collector: MetricsCollector
    ) -> None:
        """Starting twice should not create duplicate tasks."""
        await reporter.start(collector)
        task1 = reporter._task
        await reporter.start(collector)  # Should warn and skip
        task2 = reporter._task
        assert task1 is task2
        await reporter.stop()

    @pytest.mark.asyncio
    async def test_send_final_report(
        self, reporter: OracleReporter, collector: MetricsCollector
    ) -> None:
        """Final report should send without errors."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("plumise_petals.chain.reporter.aiohttp.ClientSession", return_value=mock_session):
            await reporter.send_final_report(collector)

        # Should have been called once
        assert mock_session.post.call_count == 1
