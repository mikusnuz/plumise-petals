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
from pathlib import Path
from typing import Optional

from plumise_petals.chain.agent import ChainAgent
from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.chain.proof import InferenceProofGenerator, ProofData
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
        self.agent = ChainAgent(
            config=config,
            w3=self.auth.w3,
            account=self.auth.account,
        )
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

        # Proof generation
        self.proof_generator = InferenceProofGenerator(
            model_name=config.model_name,
            agent_address=self.auth.address,
        )

        # Metrics
        self.metrics = MetricsCollector()

        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._petals_thread: Optional[threading.Thread] = None
        self._api_thread: Optional[threading.Thread] = None
        self._petals_server = None
        self._petals_ready = threading.Event()

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
        # Install global asyncio exception handler
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(self._asyncio_exception_handler)

        logger.info("=" * 60)
        logger.info("  Plumise Petals Server")
        logger.info("  Agent: %s", self.auth.address)
        logger.info("  Model: %s", self.config.model_name)
        logger.info("  Blocks: %d", self.config.num_blocks)
        logger.info("  Chain: %s (ID %d)", self.config.plumise_rpc_url, self.config.plumise_chain_id)
        logger.info("  Oracle: %s", self.config.oracle_api_url)
        logger.info("  Device: %s", self.config.device)
        logger.info("  On-chain verify: %s", "ON" if self.config.verify_on_chain else "OFF")
        logger.info("  API port: %d", self.config.api_port)
        logger.info("=" * 60)

        # Step 1: Chain checks
        await self._preflight_checks()

        # Step 2: Start Petals server
        self._start_petals_server()

        # Step 3: Start HTTP API server
        self._start_api_server()

        # Step 4: Register agent on-chain (if not already registered)
        await self._register_agent()

        # Step 5: Start reporter
        self._running = True
        await self.reporter.start(self.metrics)

        # Step 6: Start heartbeat loop
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Step 7: Periodic reward check
        reward_task = asyncio.create_task(self._reward_check_loop())

        # Step 7: Wait for shutdown
        logger.info("Server is running. Press Ctrl+C to stop.")
        try:
            await self._shutdown_event.wait()
        finally:
            heartbeat_task.cancel()
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

        # Check registration (if AgentRegistry is deployed)
        if self.config.agent_registry_address:
            if self.auth.verify_registration():
                logger.info("Agent registration verified (AgentRegistry)")
            else:
                logger.warning(
                    "Agent %s is NOT registered in AgentRegistry; "
                    "will attempt precompile registration",
                    self.auth.address,
                )

            # Check active status
            if self.auth.is_active():
                logger.info("Agent is ACTIVE")
            else:
                logger.warning("Agent is not in Active status")
        else:
            logger.info("AgentRegistry not deployed yet; using precompile-only mode")

    async def _register_agent(self) -> None:
        """Register agent via precompile 0x21."""
        if self.agent.is_registered:
            logger.info("Agent already registered")
            return

        # Generate agent name from model + address suffix
        agent_name = f"{self.config.model_name.split('/')[-1][:16]}-{self.auth.address[-8:]}"

        logger.info("Registering agent on-chain: %s", agent_name)

        # Run registration in thread pool (sync Web3 call)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None,
            lambda: self.agent.register(
                name=agent_name,
                model_hash=b"\x00" * 32,
                capabilities=[],
            ),
        )

        if success:
            logger.info("Agent registration complete")
        else:
            logger.warning("Agent registration failed; will retry on next start")

    def _start_petals_server(self) -> None:
        """Start the Petals model server in a background thread.

        The actual ``petals.Server`` import and instantiation happens here
        to avoid import errors when petals is not installed (e.g. in tests).
        """
        def _run_petals() -> None:
            try:
                from petals.server.server import Server as PetalsServer  # type: ignore

                initial_peers = [
                    p.strip()
                    for p in self.config.petals_initial_peers.split(",")
                    if p.strip()
                ]

                logger.info(
                    "Starting Petals server: model=%s blocks=%d dht_prefix=%s peers=%s",
                    self.config.model_name,
                    self.config.num_blocks,
                    self.config.petals_dht_prefix,
                    initial_peers or "(bootstrap)",
                )
                # Build extra kwargs for DHT
                dht_kwargs = {}
                if self.config.petals_identity_path:
                    # Persist P2P identity so peer ID survives restarts
                    identity_dir = Path(self.config.petals_identity_path).parent
                    identity_dir.mkdir(parents=True, exist_ok=True)
                    dht_kwargs["identity_path"] = self.config.petals_identity_path
                if self.config.petals_announce_ip:
                    # Listen on all interfaces and announce the specified IP
                    dht_kwargs["host_maddrs"] = [
                        f"/ip4/0.0.0.0/tcp/{self.config.petals_port}",
                    ]
                    dht_kwargs["announce_maddrs"] = [
                        f"/ip4/{self.config.petals_announce_ip}/tcp/{self.config.petals_port}",
                    ]

                server = PetalsServer(
                    initial_peers=initial_peers,
                    dht_prefix=self.config.petals_dht_prefix,
                    converted_model_name_or_path=self.config.model_name,
                    throughput=self.config.petals_throughput,
                    num_blocks=self.config.num_blocks,
                    skip_reachability_check=True,
                    **dht_kwargs,
                )
                # Share DHT with API server before blocking run()
                self._petals_server = server
                self._petals_ready.set()
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

    def _start_api_server(self) -> None:
        """Start the HTTP API server in a background thread.

        The API provides /health and /api/v1/generate endpoints that
        the plumise-inference-api can call to perform text generation.
        The thread waits for the Petals DHT to be ready before loading.
        """
        def _run_api() -> None:
            from plumise_petals.api.server import create_app, run_api_server

            # Wait for Petals server to be ready so we can get its peer address
            logger.info("API thread waiting for Petals server...")
            if not self._petals_ready.wait(timeout=300):
                logger.error("Petals server did not start in 300s; skipping API server")
                return

            # Get the local Petals server's multiaddrs as initial_peers
            local_peers = []
            try:
                dht = getattr(self._petals_server, "dht", None)
                if dht is not None:
                    visible = dht.get_visible_maddrs()
                    local_peers = [str(addr) for addr in visible]
                    logger.info("Local Petals DHT peers: %s", local_peers)
            except Exception:
                logger.exception("Failed to get Petals DHT addresses")

            if not local_peers:
                logger.error("No local DHT peers found; skipping API server")
                return

            app = create_app(
                plumise_server=self,
                model_name=self.config.model_name,
                initial_peers=local_peers,
                dht_prefix=self.config.petals_dht_prefix,
                device=self.config.device,
            )
            run_api_server(app, "0.0.0.0", self.config.api_port)

        self._api_thread = threading.Thread(
            target=_run_api,
            name="api-server",
            daemon=True,
        )
        self._api_thread.start()
        logger.info("API server thread started (waiting for DHT on port %d)", self.config.api_port)

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to chain."""
        # Heartbeat every 5 minutes
        interval = 300
        while self._running:
            try:
                await asyncio.sleep(interval)

                # Run heartbeat in thread pool (sync Web3 call)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(None, self.agent.heartbeat)

                if success:
                    logger.debug("Heartbeat sent successfully")
                else:
                    logger.warning("Heartbeat failed")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in heartbeat loop")

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

    # ------------------------------------------------------------------
    # Inference proof integration
    # ------------------------------------------------------------------

    def record_inference(
        self,
        input_data: str | bytes,
        output_data: str | bytes,
        token_count: int,
        latency_ms: float,
    ) -> Optional[ProofData]:
        """Record an inference and generate a proof.

        This is the main entry point called from the inference handler.
        It records metrics, generates a proof, and buffers it for the
        next Oracle report. If ``verify_on_chain`` is enabled, the proof
        is also queued for on-chain verification.

        Args:
            input_data: Raw input (prompt text or bytes).
            output_data: Raw output (generated text or bytes).
            token_count: Number of tokens generated.
            latency_ms: End-to-end latency in milliseconds.

        Returns:
            The generated ``ProofData``, or ``None`` on error.
        """
        # 1. Record metrics (always)
        self.metrics.record_inference(token_count, latency_ms)

        # 2. Generate proof
        try:
            proof = self.proof_generator.generate_proof(
                input_data=input_data,
                output_data=output_data,
                token_count=token_count,
            )
        except Exception:
            logger.exception("Failed to generate inference proof")
            return None

        # 3. Buffer proof for Oracle reporting (always)
        self.metrics.record_proof(proof)

        # 4. Queue on-chain verification (if enabled)
        if self.config.verify_on_chain:
            asyncio.get_event_loop().call_soon_threadsafe(
                self._schedule_on_chain_verify, proof
            )

        return proof

    def _schedule_on_chain_verify(self, proof: ProofData) -> None:
        """Schedule on-chain verification in the event loop."""
        asyncio.ensure_future(self._verify_on_chain(proof))

    async def _verify_on_chain(self, proof: ProofData) -> None:
        """Run on-chain verification in a thread pool."""
        try:
            loop = asyncio.get_event_loop()
            tx_hash = await loop.run_in_executor(
                None,
                self.agent.verify_inference,
                proof,
            )
            if tx_hash:
                logger.info(
                    "On-chain verification complete: tx=%s proofHash=%s",
                    tx_hash,
                    "0x" + proof.proof_hash.hex()[:16] + "...",
                )
        except Exception:
            logger.exception("On-chain verification error")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

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

        # Clear private key from config memory (best effort)
        try:
            self.config.plumise_private_key = ""  # type: ignore[misc]
        except Exception:
            pass

        logger.info("Shutdown complete")

    def request_shutdown(self) -> None:
        """Request a graceful shutdown from any thread."""
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Exception handling
    # ------------------------------------------------------------------

    def _asyncio_exception_handler(
        self, loop: asyncio.AbstractEventLoop, context: dict
    ) -> None:
        """Handle uncaught asyncio exceptions to prevent silent process death."""
        exception = context.get("exception")
        message = context.get("message", "Unhandled asyncio exception")
        if exception:
            logger.error(
                "Unhandled asyncio exception: %s - %s",
                message,
                exception,
                exc_info=exception,
            )
        else:
            logger.error("Unhandled asyncio error: %s", message)
        # Don't crash the process - log and continue

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Install SIGINT/SIGTERM handlers for graceful shutdown."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.request_shutdown)
