"""Data access layer — async parameterized SQL queries.

Each function receives an aiosqlite connection and uses await for
all database operations so the event loop stays free.
No business logic belongs here.
"""

import aiosqlite


async def insert_transaction(
    db: aiosqlite.Connection, account_id: str, amount: float, idempotency_key: str | None = None
) -> dict:
    """Insert a new transaction and update the denormalized account balance.

    If idempotency_key is provided and already exists, returns the existing
    transaction without modifying the balance (safe retry).

    Uses INSERT ... ON CONFLICT to atomically create or update the account
    row, and RETURNING balance to get the new balance without a second query.

    NOTE: This function does NOT commit.  Commit responsibility belongs
    to the Unit of Work that owns the connection.

    Returns:
        dict with transaction_id, balance, and is_duplicate flag.
    """
    # Idempotency check: if this key was already processed, return existing result
    if idempotency_key is not None:
        cursor = await db.execute(
            "SELECT transaction_id, created_at FROM transactions WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        existing = await cursor.fetchone()
        if existing:
            transaction_id = existing[0]
            created_at = existing[1]
            # Fetch current balance (already updated by the original request)
            cursor = await db.execute(
                "SELECT balance FROM accounts WHERE account_id = ?",
                (account_id,),
            )
            row = await cursor.fetchone()
            balance = row[0] if row else 0
            return {
                "transaction_id": transaction_id,
                "balance": balance,
                "created_at": created_at,
                "is_duplicate": True,
            }

    cursor = await db.execute(
        "INSERT INTO transactions (account_id, amount, idempotency_key) VALUES (?, ?, ?)"
        " RETURNING transaction_id, created_at",
        (account_id, amount, idempotency_key),
    )
    row = await cursor.fetchone()
    transaction_id = row[0]
    created_at = row[1]

    # Upsert: INSERT the account if new, or add to existing balance.
    # RETURNING gives us the result in the same round-trip — no extra SELECT.
    cursor = await db.execute(
        """
        INSERT INTO accounts (account_id, balance) VALUES (?, ?)
        ON CONFLICT(account_id) DO UPDATE SET balance = balance + excluded.balance
        RETURNING balance
        """,
        (account_id, amount),
    )
    row = await cursor.fetchone()
    balance = row[0]

    return {
        "transaction_id": transaction_id,
        "balance": balance,
        "created_at": created_at,
        "is_duplicate": False,
    }


async def get_transaction_by_id(db: aiosqlite.Connection, transaction_id: str) -> dict | None:
    """Fetch a single transaction by primary key.

    Returns None if not found.
    """
    cursor = await db.execute(
        "SELECT transaction_id, account_id, amount, created_at "
        "FROM transactions WHERE transaction_id = ?",
        (transaction_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "transaction_id": str(row[0]),
        "account_id": row[1],
        "amount": row[2],
        "created_at": row[3],
    }


async def get_all_transactions(db: aiosqlite.Connection, account_id: str | None = None) -> list[dict]:
    """Fetch transactions, optionally filtered by account_id.

    Returns the 50 most recent transactions (ORDER BY transaction_id DESC).
    A real API never dumps an entire table — pagination via LIMIT keeps
    response size bounded and prevents memory exhaustion on the server.
    """
    if account_id:
        cursor = await db.execute(
            "SELECT transaction_id, account_id, amount, created_at "
            "FROM transactions WHERE account_id = ? "
            "ORDER BY transaction_id DESC LIMIT 50",
            (account_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT transaction_id, account_id, amount, created_at "
            "FROM transactions "
            "ORDER BY transaction_id DESC LIMIT 50"
        )
    rows = await cursor.fetchall()
    return [
        {
            "transaction_id": str(row[0]),
            "account_id": row[1],
            "amount": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]


async def get_account_balance(db: aiosqlite.Connection, account_id: str) -> dict | None:
    """Look up the pre-computed balance from the accounts table.

    O(1) via primary key lookup — no SUM over K transactions needed.
    Returns None if the account doesn't exist (→ 404).
    """
    cursor = await db.execute(
        "SELECT balance FROM accounts WHERE account_id = ?",
        (account_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {"account_id": account_id, "balance": row[0]}


async def get_distinct_account_ids(db: aiosqlite.Connection) -> list[str]:
    """Return all unique account IDs from the transactions table."""
    cursor = await db.execute("SELECT DISTINCT account_id FROM transactions")
    rows = await cursor.fetchall()
    return [row[0] for row in rows]
