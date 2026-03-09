"""Integration tests for the service layer.

Tests 1-9:  Business rules, validation, and error handling.
Tests 10-11: Pagination (LIMIT 50) and account filtering.

All tests call the service functions directly — same interface
as the route handlers, but without HTTP overhead.
"""

import pytest

from services import transaction_service
from utils.exceptions import BadRequestError, NotFoundError


async def test_create_and_read_transaction(test_db):
    """Test 1: Create a transaction and read it back.

    Verifies the basic round-trip: POST data in, GET same data out.
    """
    result = await transaction_service.create_transaction("acc-1", 42.0)
    tx_id = result["transaction_id"]

    tx = await transaction_service.get_transaction(tx_id)

    assert tx["transaction_id"] == tx_id
    assert tx["account_id"] == "acc-1"
    assert tx["amount"] == 42.0


async def test_create_transaction_missing_account_id(test_db):
    """Test 2: Missing account_id raises BadRequestError (400)."""
    with pytest.raises(BadRequestError):
        await transaction_service.create_transaction(None, 10)


async def test_create_transaction_missing_amount(test_db):
    """Test 3: Missing amount raises BadRequestError (400)."""
    with pytest.raises(BadRequestError):
        await transaction_service.create_transaction("acc-1", None)


async def test_get_nonexistent_transaction(test_db):
    """Test 4: Fetching a non-existent transaction raises NotFoundError (404)."""
    with pytest.raises(NotFoundError):
        await transaction_service.get_transaction("99999")


async def test_get_nonexistent_account(test_db):
    """Test 5: Fetching a non-existent account raises NotFoundError (404)."""
    with pytest.raises(NotFoundError):
        await transaction_service.get_account("no-such-account")


async def test_balance_updates_across_transactions(test_db):
    """Test 6: Balance accumulates correctly across multiple transactions.

    +10, -3 = 7.  Proves the denormalized accounts table stays in sync.
    """
    await transaction_service.create_transaction("acc-balance", 10)
    await transaction_service.create_transaction("acc-balance", -3)

    account = await transaction_service.get_account("acc-balance")

    assert account["balance"] == 7


async def test_negative_balance_allowed(test_db):
    """Test 7: Negative balances are permitted (no business rule blocks them)."""
    await transaction_service.create_transaction("acc-negative", -50)

    account = await transaction_service.get_account("acc-negative")

    assert account["balance"] == -50


async def test_idempotency_duplicate_key(test_db):
    """Test 8: Duplicate idempotency_key returns same transaction_id.

    Sending the same key twice must NOT create a second transaction
    or double-credit the account.
    """
    r1 = await transaction_service.create_transaction("acc-idemp", 100, "key-1")
    r2 = await transaction_service.create_transaction("acc-idemp", 100, "key-1")

    assert r1["transaction_id"] == r2["transaction_id"]

    account = await transaction_service.get_account("acc-idemp")
    assert account["balance"] == 100  # NOT 200


async def test_idempotency_null_keys_independent(test_db):
    """Test 9: Two requests without idempotency_key create separate transactions.

    SQL UNIQUE allows multiple NULLs — each NULL is treated as distinct.
    """
    r1 = await transaction_service.create_transaction("acc-null-key", 10)
    r2 = await transaction_service.create_transaction("acc-null-key", 20)

    assert r1["transaction_id"] != r2["transaction_id"]

    account = await transaction_service.get_account("acc-null-key")
    assert account["balance"] == 30


async def test_list_transactions_limit_50(test_db):
    """Test 10: GET /transactions returns at most 50 rows (pagination).

    Inserts 60 transactions, verifies only 50 are returned.
    """
    for i in range(60):
        await transaction_service.create_transaction("acc-limit", 1)

    transactions = await transaction_service.list_transactions()

    assert len(transactions) == 50


async def test_list_transactions_filter_by_account(test_db):
    """Test 11: Filtering by account_id returns only that account's transactions."""
    await transaction_service.create_transaction("acc-A", 10)
    await transaction_service.create_transaction("acc-B", 20)
    await transaction_service.create_transaction("acc-A", 30)

    filtered = await transaction_service.list_transactions("acc-A")

    assert len(filtered) == 2
    assert all(tx["account_id"] == "acc-A" for tx in filtered)
