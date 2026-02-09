"""Tests for PlumiseConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from plumise_petals.chain.config import PlumiseConfig


class TestPlumiseConfig:
    """Test configuration loading and validation."""

    def test_default_values(self) -> None:
        """Config should have sensible defaults."""
        with patch.dict(os.environ, {}, clear=False):
            config = PlumiseConfig(plumise_private_key="0x" + "ab" * 32)

        assert config.plumise_rpc_url == "http://localhost:26902"
        assert config.plumise_chain_id == 41956
        assert config.oracle_api_url == "http://localhost:3100"
        assert config.report_interval == 60
        assert config.model_name == "meta-llama/Llama-3.1-8B"
        assert config.num_blocks == 4
        assert config.petals_host == "0.0.0.0"
        assert config.petals_port == 31330
        assert config.agent_registry_address is None
        assert config.reward_pool_address is None

    def test_env_override(self) -> None:
        """Environment variables should override defaults."""
        env = {
            "PLUMISE_RPC_URL": "http://custom:8545",
            "PLUMISE_CHAIN_ID": "99999",
            "PLUMISE_PRIVATE_KEY": "0x" + "cd" * 32,
            "ORACLE_API_URL": "http://oracle:3200",
            "REPORT_INTERVAL": "120",
            "MODEL_NAME": "bigscience/bloom-7b1",
            "NUM_BLOCKS": "8",
            "PETALS_HOST": "127.0.0.1",
            "PETALS_PORT": "8080",
        }
        with patch.dict(os.environ, env, clear=False):
            config = PlumiseConfig()

        assert config.plumise_rpc_url == "http://custom:8545"
        assert config.plumise_chain_id == 99999
        assert config.oracle_api_url == "http://oracle:3200"
        assert config.report_interval == 120
        assert config.model_name == "bigscience/bloom-7b1"
        assert config.num_blocks == 8
        assert config.petals_host == "127.0.0.1"
        assert config.petals_port == 8080

    def test_private_key_normalization(self) -> None:
        """Private key should always have 0x prefix."""
        raw_key = "ab" * 32
        config = PlumiseConfig(plumise_private_key=raw_key)
        assert config.plumise_private_key == "0x" + raw_key

    def test_private_key_already_prefixed(self) -> None:
        """Private key with 0x prefix should remain unchanged."""
        key = "0x" + "ab" * 32
        config = PlumiseConfig(plumise_private_key=key)
        assert config.plumise_private_key == key

    def test_report_interval_minimum(self) -> None:
        """Report interval below 10 seconds should be rejected."""
        with pytest.raises(Exception):
            PlumiseConfig(
                plumise_private_key="0x" + "ab" * 32,
                report_interval=5,
            )

    def test_port_range_validation(self) -> None:
        """Port must be in valid range."""
        with pytest.raises(Exception):
            PlumiseConfig(
                plumise_private_key="0x" + "ab" * 32,
                petals_port=70000,
            )

    def test_load_abi_agent_registry(self) -> None:
        """Should load AgentRegistry ABI from contracts/."""
        abi = PlumiseConfig.load_abi("AgentRegistry")
        assert isinstance(abi, list)
        assert len(abi) > 0
        # Check for expected function
        func_names = [
            item["name"] for item in abi if item.get("type") == "function"
        ]
        assert "isRegistered" in func_names
        assert "isActive" in func_names
        assert "getAgent" in func_names

    def test_load_abi_reward_pool(self) -> None:
        """Should load RewardPool ABI from contracts/."""
        abi = PlumiseConfig.load_abi("RewardPool")
        assert isinstance(abi, list)
        func_names = [
            item["name"] for item in abi if item.get("type") == "function"
        ]
        assert "getPendingReward" in func_names
        assert "claimReward" in func_names
        assert "getContribution" in func_names
        assert "getCurrentEpoch" in func_names

    def test_load_abi_not_found(self) -> None:
        """Missing ABI file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PlumiseConfig.load_abi("NonExistent")

    def test_constructor_override(self) -> None:
        """Explicit constructor args should take highest priority."""
        env = {"MODEL_NAME": "from-env"}
        with patch.dict(os.environ, env, clear=False):
            config = PlumiseConfig(
                plumise_private_key="0x" + "ab" * 32,
                model_name="from-constructor",
            )
        assert config.model_name == "from-constructor"
