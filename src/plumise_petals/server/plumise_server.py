"""Enhanced Petals server with Plumise chain integration.

Wraps the standard Petals server with:
- On-chain agent authentication
- Inference metrics collection
- Periodic reporting to the Plumise Oracle
- Automatic reward claiming
"""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from typing import Optional

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.reporter import OracleReporter
from plumise_petals.chain.rewards import RewardTracker
from plumise_petals.server.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class PlumiseServer:
    """Distributed LLM inference server with Plumise chain integration.

    This class orchestrates:
    1. Authentication against the Plumise chain
    2. Starting the Petals model server
    3. Collecting inference metrics
    4. Reporting metrics to the Oracle
    5. Claiming rewards when threshold is met

    Args:
        config: Plumise configuration instance.
    """

    def __init__(self, config: PlumiseConfig) -> None:
        self.config = config

        # Chain components
        self.auth = PlumiseAuth(config)
        self.reporter = OracleReporter(
            auth=self.auth,
            oracle_url=config.oracle_api_url,
            interval=config.report_interval,
        )
        self.rewards = RewardTracker(
            config=config,
            w3=self.auth.w3,
            account=self.auth.account,
        )

        # Metrics
        self.metrics = MetricsCollector()

        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._petals_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Plumise Petals server.

        Steps:
        1. Verify chain connectivity and agent registration
        2. Start the Petals model server in a background thread
        3. Start the Oracle reporter
        4. Wait for shutdown signal
        """
        logger.info("=" * 60)
        logger.info("  Plumise Petals Server")
        logger.info("  Agent: %s", self.auth.address)
        logger.info("  Model: %s", self.config.model_name)
        logger.info("  Blocks: %d", self.config.num_blocks)
        logger.info("  Chain: %s (ID %d)", self.config.plumise_rpc_url, self.config.plumise_chain_id)
        logger.info("  Oracle: %s", self.config.oracle_api_url)
        logger.info("=" * 60)

        # Step 1: Chain checks
        await self._preflight_checks()

        # Step 2: Start Petals server
        self._start_petals_server()

        # Step 3: Start reporter
        self._running = True
        await self.reporter.start(self.metrics)

        # Step 4: Periodic reward check
        reward_task = asyncio.create_task(self._reward_check_loop())

        # Step 5: Wait for shutdown
        logger.info("Server is running. Press Ctrl+C to stop.")
        try:
            await self._shutdown_event.wait()
        finally:
            reward_task.cancel()
            await self._shutdown()

    async def _preflight_checks(self) -> None:
        """Verify chain connectivity and agent registration."""
        # Check chain connection
        if self.auth.is_chain_connected():
            logger.info("Chain connection OK")
            balance = self.auth.get_balance()
            logger.info("Agent balance: %s PLM", balance / 10**18)
        else:
            logger.warning(
                "Cannot reach chain at %s; continuing in offline mode",
                self.config.plumise_rpc_url,
            )

        # Check registration
        if self.auth.verify_registration():
            logger.info("Agent registration verified")
        else:
            logger.warning(
                "Agent %s is NOT registered; metrics reporting may be rejected",
                self.auth.address,
            )

        # Check active status
        if self.auth.is_active():
            logger.info("Agent is ACTIVE")
        else:
            logger.warning("Agent is not in Active status")

    def _start_petals_server(self) -> None:
        """Start the Petals model server in a background thread.

        The actual ``petals.Server`` import and instantiation happens here
        to avoid import errors when petals is not installed (e.g. in tests).
        """
        def _run_petals() -> None:
            try:
                from petals import Server as PetalsServer  # type: ignore

                logger.info(
                    "Starting Petals server: model=%s blocks=%d host=%s port=%d",
                    self.config.model_name,
                    self.config.num_blocks,
                    self.config.petals_host,
                    self.config.petals_port,
                )
                server = PetalsServer(
                    model_name_or_path=self.config.model_name,
                    num_blocks=self.config.num_blocks,
                    host=self.config.petals_host,
                    port=self.config.petals_port,
                )
                server.run()
            except ImportError:
                logger.error(
                    "petals package not installed. "
                    "Install with: pip install petals"
                )
            except Exception:
                logger.exception("Petals server crashed")
                self.request_shutdown()

        self._petals_thread = threading.Thread(
            target=_run_petals,
            name="petals-server",
            daemon=True,
        )
        self._petals_thread.start()
        logger.info("Petals server thread started")

    async def _reward_check_loop(self) -> None:
        """Periodically check and claim rewards."""
        # Check rewards every 5 minutes
        interval = max(self.config.report_interval * 5, 300)
        while self._running:
            try:
                await asyncio.sleep(interval)
                tx_hash = self.rewards.claim_if_ready()
                if tx_hash:
                    logger.info("Reward claimed! tx=%s", tx_hash)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in reward check loop")

    async def _shutdown(self) -> None:
        """Graceful shutdown: final report and cleanup."""
        logger.info("Shutting down...")
        self._running = False

        # Final metrics report
        await self.reporter.send_final_report(self.metrics)
        await self.reporter.stop()

        # Log final metrics
        final = self.metrics.get_snapshot()
        logger.info("Final metrics: %s", final.to_dict())

        # Reward summary
        summary = self.rewards.summary()
        logger.info("Reward summary: %s", summary)

        logger.info("Shutdown complete")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown from any thread."""
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Install SIGINT/SIGTERM handlers for graceful shutdown."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.request_shutdown)
