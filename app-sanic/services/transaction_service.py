"""Business logic for transaction and account operations.

This layer validates input and orchestrates data access via
the repository.  It knows nothing about HTTP or Sanic — only
domain rules.  Errors are raised as typed exceptions that the
global error handler translates into JSON responses.

All functions are async because the underlying repository layer
uses aiosqlite (non-blocking database access).

Each function opens its own database connection via:
    async with get_connection() as db:
This gives every request an isolated connection — essential for
transaction isolation (BEGIN EXCLUSIVE) in the next phase.
"""

from __future__ import annotations

from typing import Any

from models.database import get_connection
from models import repositories
from utils.exceptions import BadRequestError, NotFoundError


async def create_transaction(account_id: Any, amount: Any) -> dict:
    """Validate input and persist a new transaction.

    Returns:
        dict with the generated transaction_id.

    Raises:
        BadRequestError: If account_id or amount is missing/invalid.
    """
    if not account_id or amount is None:
        raise BadRequestError("Invalid input")

    async with get_connection() as db:
        transaction_id = await repositories.insert_transaction(
            db, account_id, amount
        )
        return {"transaction_id": str(transaction_id)}


async def get_transaction(transaction_id: str) -> dict:
    """Fetch a single transaction by ID.

    Raises:
        NotFoundError: If the transaction does not exist.
    """
    async with get_connection() as db:
        transaction = await repositories.get_transaction_by_id(db, transaction_id)

        if not transaction:
            raise NotFoundError("Transaction not found")

        return transaction


async def list_transactions(account_id: str | None = None) -> list[dict]:
    """Return all transactions, optionally filtered by account_id."""
    async with get_connection() as db:
        return await repositories.get_all_transactions(db, account_id)


async def get_account(account_id: str) -> dict:
    """Fetch account data including balance.

    Raises:
        NotFoundError: If the account has no transactions.
    """
    async with get_connection() as db:
        account = await repositories.get_account_balance(db, account_id)

        if not account:
            raise NotFoundError("Account not found")

        return account


async def get_account_count() -> dict:
    """Return the count of unique accounts and their IDs."""
    async with get_connection() as db:
        account_ids = await repositories.get_distinct_account_ids(db)
        return {"count": len(account_ids), "account_ids": account_ids}
