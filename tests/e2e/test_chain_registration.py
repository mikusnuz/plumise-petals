"""E2E test for ChainAgent registration flow.

This test verifies:
1. Agent registration via precompile 0x21
2. Heartbeat via precompile 0x22
3. Transaction construction and signing
4. Error handling for failed transactions
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound

from plumise_petals.chain.agent import ChainAgent
from plumise_petals.chain.config import PlumiseConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
TEST_PRIVATE_KEY = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"


@pytest.fixture
def mock_w3():
    """Mock Web3 instance with successful transaction responses."""
    w3 = MagicMock(spec=Web3)
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1000000000  # 1 gwei
    w3.eth.send_raw_transaction.return_value = b"\xaa" * 32
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
    return w3


@pytest.fixture
def mock_config() -> PlumiseConfig:
    """Test configuration."""
    return PlumiseConfig(
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        plumise_private_key=TEST_PRIVATE_KEY,
    )


@pytest.fixture
def mock_account() -> Account:
    """Test account."""
    return Account.from_key(TEST_PRIVATE_KEY)


class TestChainRegistration:
    """Test agent registration and heartbeat on Plumise chain."""

    def test_chain_agent_initialization(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """ChainAgent should initialize with correct parameters."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        assert agent.address == mock_account.address
        assert agent.config.plumise_chain_id == 41956
        assert not agent.is_registered

    def test_register_success(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Registration should succeed with valid transaction."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.register(name="test-agent")

        assert success
        assert agent.is_registered

        # Verify transaction was sent
        mock_w3.eth.send_raw_transaction.assert_called_once()

        # Verify transaction structure
        call_args = mock_sign.call_args[0][0]
        assert call_args["to"] == Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000021"
        )
        assert call_args["chainId"] == 41956
        assert call_args["gas"] == 300000

    def test_register_with_name_normalization(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Agent name should be normalized to 32 bytes."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)

            # Test short name (should be padded)
            success = agent.register(name="short")
            assert success

            # Verify data field contains padded name
            call_args = mock_sign.call_args[0][0]
            data = bytes.fromhex(call_args["data"][2:])
            assert len(data) >= 32  # Name field

            # Test long name (should be truncated)
            agent._registered = False
            agent._registration_attempted = False
            success = agent.register(name="a" * 100)
            assert success

    def test_register_with_model_hash_and_capabilities(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Registration should include model hash and capabilities."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        model_hash = b"\xff" * 32
        capabilities = [b"\x01" * 32, b"\x02" * 32, b"\x03" * 32]

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.register(
                name="test-agent", model_hash=model_hash, capabilities=capabilities
            )

        assert success

        # Verify data length
        call_args = mock_sign.call_args[0][0]
        data = bytes.fromhex(call_args["data"][2:])

        # Expected: name(32) + modelHash(32) + capCount(32) + 3×cap(32) = 160 bytes
        expected_length = 32 + 32 + 32 + (32 * 3)
        assert len(data) == expected_length

    def test_register_failure_reverted_transaction(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Registration should fail gracefully if transaction reverts."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        # Mock failed transaction
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.register(name="test-agent")

        assert not success
        assert not agent.is_registered

    def test_register_failure_exception(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Registration should handle exceptions gracefully."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        # Mock exception during transaction send
        mock_w3.eth.send_raw_transaction.side_effect = Exception("Network error")

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.register(name="test-agent")

        assert not success
        assert not agent.is_registered

    def test_register_idempotent(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Calling register twice should not resend transaction."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)

            # First registration
            success1 = agent.register(name="test-agent")
            assert success1
            assert agent.is_registered

            # Second registration (should skip)
            success2 = agent.register(name="test-agent")
            assert success2

        # Should only be called once
        mock_w3.eth.send_raw_transaction.assert_called_once()

    def test_heartbeat_success(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Heartbeat should succeed with valid transaction."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.heartbeat()

        assert success

        # Verify transaction was sent
        mock_w3.eth.send_raw_transaction.assert_called_once()

        # Verify transaction structure
        call_args = mock_sign.call_args[0][0]
        assert call_args["to"] == Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000022"
        )
        assert call_args["data"] == "0x"  # No input data
        assert call_args["gas"] == 100000

    def test_heartbeat_failure(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Heartbeat should handle failure gracefully."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        # Mock failed transaction
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.heartbeat()

        assert not success

    def test_heartbeat_exception(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Heartbeat should handle exceptions gracefully."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        # Mock exception
        mock_w3.eth.send_raw_transaction.side_effect = Exception("Network error")

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
            success = agent.heartbeat()

        assert not success

    def test_multiple_heartbeats(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Multiple heartbeats should each send a transaction."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)

            # Send multiple heartbeats
            success1 = agent.heartbeat()
            success2 = agent.heartbeat()
            success3 = agent.heartbeat()

        assert success1 and success2 and success3

        # Should be called 3 times
        assert mock_w3.eth.send_raw_transaction.call_count == 3

    def test_nonce_increments(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Nonce should be fetched fresh for each transaction."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        # Mock incrementing nonce
        mock_w3.eth.get_transaction_count.side_effect = [0, 1, 2]

        with patch.object(mock_account, "sign_transaction") as mock_sign:
            mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)

            # Register
            agent.register(name="test")
            call_args_0 = mock_sign.call_args_list[0][0][0]
            assert call_args_0["nonce"] == 0

            # Heartbeat 1
            agent.heartbeat()
            call_args_1 = mock_sign.call_args_list[1][0][0]
            assert call_args_1["nonce"] == 1

            # Heartbeat 2
            agent.heartbeat()
            call_args_2 = mock_sign.call_args_list[2][0][0]
            assert call_args_2["nonce"] == 2

    def test_invalid_capability_length(
        self, mock_config: PlumiseConfig, mock_w3: MagicMock, mock_account: Account
    ) -> None:
        """Registration should reject capabilities with wrong length."""
        agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

        invalid_capabilities = [b"\x01" * 16]  # Wrong length (16 instead of 32)

        with pytest.raises(ValueError, match="exactly 32 bytes"):
            agent.register(name="test", capabilities=invalid_capabilities)
