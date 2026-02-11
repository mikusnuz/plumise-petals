"""Unit tests for ChainAgent."""

from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account
from web3 import Web3

from plumise_petals.chain.agent import ChainAgent
from plumise_petals.chain.config import PlumiseConfig


@pytest.fixture
def mock_w3():
    """Mock Web3 instance."""
    w3 = MagicMock(spec=Web3)
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1000000000
    w3.eth.send_raw_transaction.return_value = b"\x00" * 32
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
    return w3


@pytest.fixture
def mock_config():
    """Mock PlumiseConfig."""
    return PlumiseConfig(
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
        plumise_private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )


@pytest.fixture
def mock_account():
    """Mock eth_account Account."""
    return Account.from_key(
        "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    )


def test_chain_agent_init(mock_config, mock_w3, mock_account):
    """Test ChainAgent initialization."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)
    assert agent.address == mock_account.address
    assert not agent.is_registered


def test_register_success(mock_config, mock_w3, mock_account):
    """Test successful agent registration."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

    with patch.object(mock_account, "sign_transaction") as mock_sign:
        mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
        success = agent.register(name="test-agent")

    assert success
    assert agent.is_registered
    mock_w3.eth.send_raw_transaction.assert_called_once()


def test_register_failure(mock_config, mock_w3, mock_account):
    """Test failed agent registration."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)
    mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}

    with patch.object(mock_account, "sign_transaction") as mock_sign:
        mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
        success = agent.register(name="test-agent")

    assert not success
    assert not agent.is_registered


def test_heartbeat_success(mock_config, mock_w3, mock_account):
    """Test successful heartbeat."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)

    with patch.object(mock_account, "sign_transaction") as mock_sign:
        mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
        success = agent.heartbeat()

    assert success
    mock_w3.eth.send_raw_transaction.assert_called_once()


def test_heartbeat_failure(mock_config, mock_w3, mock_account):
    """Test failed heartbeat."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)
    mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}

    with patch.object(mock_account, "sign_transaction") as mock_sign:
        mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
        success = agent.heartbeat()

    assert not success


def test_register_with_capabilities(mock_config, mock_w3, mock_account):
    """Test registration with capabilities."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)
    capabilities = [b"\x01" * 32, b"\x02" * 32]

    with patch.object(mock_account, "sign_transaction") as mock_sign:
        mock_sign.return_value = MagicMock(raw_transaction=b"\x00" * 100)
        success = agent.register(
            name="test-agent",
            model_hash=b"\xff" * 32,
            capabilities=capabilities,
        )

    assert success
    assert agent.is_registered


def test_register_invalid_capability_length(mock_config, mock_w3, mock_account):
    """Test registration with invalid capability length."""
    agent = ChainAgent(config=mock_config, w3=mock_w3, account=mock_account)
    capabilities = [b"\x01" * 16]  # Wrong length

    with pytest.raises(ValueError, match="exactly 32 bytes"):
        agent.register(name="test-agent", capabilities=capabilities)
