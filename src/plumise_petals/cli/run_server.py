"""CLI entry point for Plumise Petals.

Usage::

    plumise-petals serve \\
        --model bigscience/bloom-560m \\
        --private-key 0x... \\
        --rpc-url http://localhost:26902

Or via Python::

    python -m plumise_petals.cli.run_server serve --model ...
"""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from dotenv import load_dotenv

from plumise_petals.chain.config import PlumiseConfig
from plumise_petals.server.plumise_server import PlumiseServer


def _setup_logging(verbose: bool) -> None:
    """Configure root logger."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    # Quiet noisy libraries
    logging.getLogger("web3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


@click.group()
@click.version_option(package_name="plumise-petals")
def cli() -> None:
    """Plumise Petals - Distributed LLM inference on Plumise chain."""


@cli.command()
@click.option(
    "--model",
    "model_name",
    default=None,
    help="HuggingFace model to serve (e.g. bigscience/bloom-560m, meta-llama/Llama-3.1-8B).",
)
@click.option(
    "--private-key",
    "private_key",
    default=None,
    help="Hex-encoded private key for the agent wallet.",
)
@click.option(
    "--rpc-url",
    "rpc_url",
    default=None,
    help="Plumise chain RPC URL.",
)
@click.option(
    "--chain-id",
    "chain_id",
    type=int,
    default=None,
    help="Plumise chain ID (default: 41956).",
)
@click.option(
    "--oracle-url",
    "oracle_url",
    default=None,
    help="Oracle API base URL.",
)
@click.option(
    "--report-interval",
    "report_interval",
    type=int,
    default=None,
    help="Metrics report interval in seconds.",
)
@click.option(
    "--num-blocks",
    "num_blocks",
    type=int,
    default=None,
    help="Number of transformer blocks to serve.",
)
@click.option(
    "--host",
    "host",
    default=None,
    help="Petals server listen address.",
)
@click.option(
    "--port",
    "port",
    type=int,
    default=None,
    help="Petals server listen port.",
)
@click.option(
    "--agent-registry",
    "agent_registry",
    default=None,
    help="AgentRegistry contract address.",
)
@click.option(
    "--reward-pool",
    "reward_pool",
    default=None,
    help="RewardPool contract address.",
)
@click.option(
    "--env-file",
    "env_file",
    default=".env",
    help="Path to .env file.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
def serve(
    model_name: str | None,
    private_key: str | None,
    rpc_url: str | None,
    chain_id: int | None,
    oracle_url: str | None,
    report_interval: int | None,
    num_blocks: int | None,
    host: str | None,
    port: int | None,
    agent_registry: str | None,
    reward_pool: str | None,
    env_file: str,
    verbose: bool,
) -> None:
    """Start the Plumise Petals inference server.

    Configuration is loaded from environment variables / .env file.
    CLI options override environment values.
    """
    _setup_logging(verbose)
    logger = logging.getLogger("plumise_petals.cli")

    # Load .env file first
    load_dotenv(env_file, override=False)

    # Build overrides dict (only non-None CLI values)
    overrides: dict = {}
    if model_name is not None:
        overrides["model_name"] = model_name
    if private_key is not None:
        overrides["plumise_private_key"] = private_key
    if rpc_url is not None:
        overrides["plumise_rpc_url"] = rpc_url
    if chain_id is not None:
        overrides["plumise_chain_id"] = chain_id
    if oracle_url is not None:
        overrides["oracle_api_url"] = oracle_url
    if report_interval is not None:
        overrides["report_interval"] = report_interval
    if num_blocks is not None:
        overrides["num_blocks"] = num_blocks
    if host is not None:
        overrides["petals_host"] = host
    if port is not None:
        overrides["petals_port"] = port
    if agent_registry is not None:
        overrides["agent_registry_address"] = agent_registry
    if reward_pool is not None:
        overrides["reward_pool_address"] = reward_pool

    # Create config
    try:
        config = PlumiseConfig(**overrides)
    except Exception as exc:
        logger.error("Configuration error: %s", exc)
        raise click.Abort() from exc

    if not config.plumise_private_key:
        logger.error(
            "Private key is required. Set PLUMISE_PRIVATE_KEY env var or use --private-key."
        )
        raise click.Abort()

    # Create and run server
    server = PlumiseServer(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        server.install_signal_handlers(loop)
    except NotImplementedError:
        # Signal handlers not supported on Windows
        pass

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.close()


@cli.command()
@click.option("--env-file", default=".env", help="Path to .env file.")
def status(env_file: str) -> None:
    """Show agent status and reward summary."""
    _setup_logging(verbose=False)
    load_dotenv(env_file, override=False)

    try:
        config = PlumiseConfig()
    except Exception as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise click.Abort() from exc

    if not config.plumise_private_key:
        click.echo("Private key is required.", err=True)
        raise click.Abort()

    auth = PlumiseAuth(config)
    rewards = RewardTracker(config, w3=auth.w3, account=auth.account)

    click.echo(f"Agent:   {auth.address}")
    click.echo(f"Chain:   {config.plumise_rpc_url} (ID {config.plumise_chain_id})")
    click.echo(f"Online:  {auth.is_chain_connected()}")

    if auth.is_chain_connected():
        balance = auth.get_balance()
        click.echo(f"Balance: {balance / 10**18:.4f} PLM")

    click.echo(f"Registered: {auth.verify_registration()}")
    click.echo(f"Active:     {auth.is_active()}")

    summary = rewards.summary()
    click.echo(f"Pending Reward: {summary['pending_reward_plm']:.4f} PLM")
    click.echo(f"Current Epoch:  {summary['current_epoch']}")

    if summary["contribution"]:
        c = summary["contribution"]
        click.echo(f"Tasks Completed: {c['task_count']}")
        click.echo(f"Uptime:          {c['uptime_seconds']}s")


# Import here to avoid circular imports in the status command
from plumise_petals.chain.auth import PlumiseAuth  # noqa: E402
from plumise_petals.chain.rewards import RewardTracker  # noqa: E402


def main() -> None:
    """Entry point for ``plumise-petals`` command."""
    cli()


if __name__ == "__main__":
    main()
