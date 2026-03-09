"""Data access layer — async parameterized SQL queries.

Each function receives an aiosqlite connection and uses await for
all database operations so the event loop stays free.
No business logic belongs here.
"""


async def insert_transaction(db, account_id: str, amount: float) -> int:
    """Insert a new transaction row and return its auto-generated ID."""
    cursor = await db.execute(
        "INSERT INTO transactions (account_id, amount) VALUES (?, ?)",
        (account_id, amount),
    )
    await db.commit()
    return cursor.lastrowid


async def get_transaction_by_id(db, transaction_id: str) -> dict | None:
    """Fetch a single transaction by primary key.

    Returns None if not found.
    """
    cursor = await db.execute(
        "SELECT transaction_id, account_id, amount "
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
    }


async def get_all_transactions(db, account_id: str | None = None) -> list[dict]:
    """Fetch all transactions, optionally filtered by account_id."""
    if account_id:
        cursor = await db.execute(
            "SELECT transaction_id, account_id, amount "
            "FROM transactions WHERE account_id = ?",
            (account_id,),
        )
    else:
        cursor = await db.execute(
            "SELECT transaction_id, account_id, amount FROM transactions"
        )
    rows = await cursor.fetchall()
    return [
        {
            "transaction_id": str(row[0]),
            "account_id": row[1],
            "amount": row[2],
        }
        for row in rows
    ]


async def get_account_balance(db, account_id: str) -> dict | None:
    """Calculate account balance via SUM(amount).

    Returns None if the account has no transactions (→ 404).
    """
    # Check existence first (LIMIT 1 = fast bail-out via index)
    cursor = await db.execute(
        "SELECT 1 FROM transactions WHERE account_id = ? LIMIT 1",
        (account_id,),
    )
    if not await cursor.fetchone():
        return None

    cursor = await db.execute(
        "SELECT SUM(amount) FROM transactions WHERE account_id = ?",
        (account_id,),
    )
    row = await cursor.fetchone()
    balance = row[0] or 0
    return {"account_id": account_id, "balance": balance}


async def get_distinct_account_ids(db) -> list[str]:
    """Return all unique account IDs from the transactions table."""
    cursor = await db.execute("SELECT DISTINCT account_id FROM transactions")
    rows = await cursor.fetchall()
    return [row[0] for row in rows]
