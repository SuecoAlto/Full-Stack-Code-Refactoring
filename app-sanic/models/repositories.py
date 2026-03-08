"""Data access layer — parameterized SQL queries for transactions and accounts.

Each function receives a database connection, executes queries, and
returns plain Python data structures.  No business logic belongs here.
"""

def create_table(conn) -> None:
    """Create database tables if they do not already exist"""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            amount REAL NOT NULL
        )
        """
    )
    conn.commit()

def insert_transaction(conn, account_id: str, amount: float) -> int:
    """Insert a new transaction row and return its auto-generated ID."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (account_id, amount) VALUES (?, ?)",
        (account_id, amount),
    )
    conn.commit()
    return cursor.lastrowid


def get_transaction_by_id(conn, transaction_id: str) -> dict | None:
    """Fetch a single transaction by primary key.

    Returns None if not found.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT transaction_id, account_id, amount "
        "FROM transactions WHERE transaction_id = ?",
        (transaction_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "transaction_id": str(row[0]),
        "account_id": row[1],
        "amount": row[2],
    }


def get_all_transactions(conn, account_id: str | None = None) -> list[dict]:
    """Fetch all transactions, optionally filtered by account_id."""
    cursor = conn.cursor()
    if account_id:
        cursor.execute(
            "SELECT transaction_id, account_id, amount "
            "FROM transactions WHERE account_id = ?",
            (account_id,),
        )
    else:
        cursor.execute(
            "SELECT transaction_id, account_id, amount FROM transactions"
        )
    return [
        {
            "transaction_id": str(row[0]),
            "account_id": row[1],
            "amount": row[2],
        }
        for row in cursor.fetchall()
    ]


def get_account_balance(conn, account_id: str) -> dict | None:
    """Calculate account balance via SUM(amount).

    Returns None if the account has no transactions (→ 404).
    """
    cursor = conn.cursor()

    # Check existence first (LIMIT 1 = fast bail-out)
    cursor.execute(
        "SELECT 1 FROM transactions WHERE account_id = ? LIMIT 1",
        (account_id,),
    )
    if not cursor.fetchone():
        return None

    cursor.execute(
        "SELECT SUM(amount) FROM transactions WHERE account_id = ?",
        (account_id,),
    )
    balance = cursor.fetchone()[0] or 0
    return {"account_id": account_id, "balance": balance}


def get_distinct_account_ids(conn) -> list[str]:
    """Return all unique account IDs from the transactions table."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT account_id FROM transactions")
    return [row[0] for row in cursor.fetchall()]
