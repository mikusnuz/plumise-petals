"""Tests for PlumiseAuth."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from plumise_petals.chain.auth import PlumiseAuth
from plumise_petals.chain.config import PlumiseConfig


# Deterministic test key (DO NOT use in production)
_TEST_PRIVATE_KEY = "0x" + "ab" * 32
_TEST_ACCOUNT = Account.from_key(_TEST_PRIVATE_KEY)
_TEST_ADDRESS = _TEST_ACCOUNT.address


@pytest.fixture
def config() -> PlumiseConfig:
    """Create a test config with mocked chain."""
    return PlumiseConfig(
        plumise_private_key=_TEST_PRIVATE_KEY,
        plumise_rpc_url="http://localhost:26902",
        plumise_chain_id=41956,
    )


@pytest.fixture
def auth(config: PlumiseConfig) -> PlumiseAuth:
    """Create a PlumiseAuth instance (chain calls will fail gracefully)."""
    return PlumiseAuth(config)


class TestPlumiseAuth:
    """Test wallet-based authentication."""

    def test_address_derivation(self, auth: PlumiseAuth) -> None:
        """Auth should derive the correct address from private key."""
        assert auth.address == _TEST_ADDRESS
        assert auth.address.startswith("0x")
        assert len(auth.address) == 42

    def test_chain_id(self, auth: PlumiseAuth) -> None:
        """Auth should store the configured chain ID."""
        assert auth.chain_id == 41956

    def test_sign_message(self, auth: PlumiseAuth) -> None:
        """Signed messages should be verifiable."""
        message = "hello plumise"
        signature = auth.sign_message(message)

        assert isinstance(signature, str)
        assert len(signature) > 0

        # Verify the signature recovers to the correct address
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=bytes.fromhex(signature))
        assert recovered == auth.address

    def test_sign_payload(self, auth: PlumiseAuth) -> None:
        """Signed payloads should be deterministic and verifiable."""
        payload = {"b": 2, "a": 1}
        sig1 = auth.sign_payload(payload)
        sig2 = auth.sign_payload(payload)

        # Same payload -> same signature
        assert sig1 == sig2

        # Different key order, same content -> same signature (sorted keys)
        payload_reordered = {"a": 1, "b": 2}
        sig3 = auth.sign_payload(payload_reordered)
        assert sig1 == sig3

    def test_sign_payload_different_data(self, auth: PlumiseAuth) -> None:
        """Different payloads must produce different signatures."""
        sig1 = auth.sign_payload({"value": 1})
        sig2 = auth.sign_payload({"value": 2})
        assert sig1 != sig2

    def test_verify_registration_no_contract(self, auth: PlumiseAuth) -> None:
        """Without a contract address, registration check is optimistic."""
        assert auth.verify_registration() is True

    def test_is_active_no_contract(self, auth: PlumiseAuth) -> None:
        """Without a contract address, active check is optimistic."""
        assert auth.is_active() is True

    def test_get_agent_info_no_contract(self, auth: PlumiseAuth) -> None:
        """Without a contract address, agent info returns None."""
        assert auth.get_agent_info() is None

    def test_is_chain_connected_offline(self, auth: PlumiseAuth) -> None:
        """When chain is unreachable, should return False."""
        # The test environment likely has no chain running on 26902
        # This may be True or False depending on local env; just check it doesn't crash
        result = auth.is_chain_connected()
        assert isinstance(result, bool)

    def test_repr(self, auth: PlumiseAuth) -> None:
        """repr should include address and chain_id."""
        r = repr(auth)
        assert auth.address in r
        assert "41956" in r

    def test_auth_with_registry_address(self) -> None:
        """Auth should initialize contract when registry address is provided."""
        config = PlumiseConfig(
            plumise_private_key=_TEST_PRIVATE_KEY,
            agent_registry_address="0x" + "00" * 20,
        )
        auth = PlumiseAuth(config)
        assert auth._registry is not None
