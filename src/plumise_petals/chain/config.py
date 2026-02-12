"""Configuration management for Plumise Petals.

Loads settings from environment variables and/or .env file using pydantic BaseSettings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field, validator


# Contract ABI paths (relative to project root)
_CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contracts"


class PlumiseConfig(BaseSettings):
    """Plumise Petals configuration.

    Values are loaded in priority order:
    1. Explicit constructor arguments
    2. Environment variables
    3. .env file
    """

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    # -- Plumise Chain --
    plumise_rpc_url: str = Field(
        default="http://localhost:26902",
        description="Plumise chain JSON-RPC endpoint",
    )
    plumise_chain_id: int = Field(
        default=41956,
        description="Plumise chain ID",
    )
    plumise_private_key: str = Field(
        default="",
        description="Hex-encoded private key for the agent wallet",
    )

    # -- Contract addresses (set after deployment) --
    agent_registry_address: Optional[str] = Field(
        default=None,
        description="AgentRegistry contract address (deployed post-genesis)",
    )
    reward_pool_address: Optional[str] = Field(
        default=None,
        description="RewardPool contract address (deployed post-genesis)",
    )

    # -- Oracle --
    oracle_api_url: str = Field(
        default="http://localhost:3100",
        description="Plumise Oracle API base URL",
    )
    report_interval: int = Field(
        default=60,
        ge=10,
        description="Metrics report interval in seconds",
    )

    # -- Petals Server --
    model_name: str = Field(
        default="bigscience/bloom-560m",
        description="HuggingFace model identifier to serve",
    )
    num_blocks: int = Field(
        default=2,
        ge=1,
        description="Number of transformer blocks (shards) to serve",
    )
    petals_host: str = Field(
        default="0.0.0.0",
        description="Petals server listen address",
    )
    petals_port: int = Field(
        default=31330,
        ge=1,
        le=65535,
        description="Petals server listen port",
    )

    # -- Petals DHT --
    petals_initial_peers: str = Field(
        default="",
        description="Comma-separated initial DHT peer multiaddrs",
    )
    petals_dht_prefix: str = Field(
        default="plumise",
        description="DHT prefix for model routing",
    )
    petals_throughput: str = Field(
        default="auto",
        description="Server throughput setting (auto or float)",
    )
    petals_announce_ip: str = Field(
        default="",
        description="Public IP to announce in DHT (empty = auto-detect)",
    )
    petals_identity_path: str = Field(
        default="/data/identity.key",
        description="Path to persist P2P identity key (fixes peer ID across restarts)",
    )

    # -- Device --
    device: str = Field(
        default="auto",
        description="Device to use: auto, cpu, cuda, cuda:0, etc.",
    )

    # -- HTTP API --
    api_port: int = Field(
        default=31331,
        ge=1,
        le=65535,
        description="HTTP API server port for inference requests",
    )

    # -- Inference proof --
    verify_on_chain: bool = Field(
        default=False,
        description="Enable on-chain proof verification via precompile 0x20 (default OFF)",
    )

    # -- Reward claim --
    claim_threshold_wei: int = Field(
        default=10**18,  # 1 PLM
        ge=0,
        description="Minimum pending reward (in wei) to trigger auto-claim",
    )

    @validator("plumise_private_key")
    @classmethod
    def _normalize_private_key(cls, v: str) -> str:
        if not v:
            return v
        v = v.strip()
        if not v.startswith("0x"):
            v = "0x" + v
        return v

    # -- ABI loaders --
    @staticmethod
    def load_abi(name: str) -> list:
        """Load a contract ABI from the contracts/ directory.

        Args:
            name: Contract name without extension, e.g. ``"AgentRegistry"``.

        Returns:
            Parsed ABI as a list of dicts.
        """
        path = _CONTRACTS_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"ABI file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        # Support both raw ABI arrays and {abi: [...]} wrappers
        if isinstance(data, list):
            return data
        return data.get("abi", data)
