"""Business logic for transaction and account operations.

This layer validates input and orchestrates data access via
the repository.  It knows nothing about HTTP or Sanic — only
domain rules.  Errors are raised as typed exceptions that the
global error handler translates into JSON responses.
"""

from __future__ import annotations

from typing import Any

from models.database import get_connection
from models import repositories
from utils.exceptions import BadRequestError, NotFoundError


def create_transaction(account_id: Any, amount: Any) -> dict:
    """Validate input and persist a new transaction.

    Returns:
        dict with the generated transaction_id.

    Raises:
        BadRequestError: If account_id or amount is missing/invalid.
    """
    if not account_id or amount is None:
        raise BadRequestError("Invalid input")

    with get_connection() as conn:
        transaction_id = repositories.insert_transaction(
            conn, account_id, amount
        )

    return {"transaction_id": str(transaction_id)}


def get_transaction(transaction_id: str) -> dict:
    """Fetch a single transaction by ID.

    Raises:
        NotFoundError: If the transaction does not exist.
    """
    with get_connection() as conn:
        transaction = repositories.get_transaction_by_id(conn, transaction_id)

    if not transaction:
        raise NotFoundError("Transaction not found")

    return transaction


def list_transactions(account_id: str | None = None) -> list[dict]:
    """Return all transactions, optionally filtered by account_id."""
    with get_connection() as conn:
        return repositories.get_all_transactions(conn, account_id)


def get_account(account_id: str) -> dict:
    """Fetch account data including balance.

    Raises:
        NotFoundError: If the account has no transactions.
    """
    with get_connection() as conn:
        account = repositories.get_account_balance(conn, account_id)

    if not account:
        raise NotFoundError("Account not found")

    return account


def get_account_count() -> dict:
    """Return the count of unique accounts and their IDs."""
    with get_connection() as conn:
        account_ids = repositories.get_distinct_account_ids(conn)

    return {"count": len(account_ids), "account_ids": account_ids}
