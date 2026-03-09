"""Database initialization and connection management.

Uses aiosqlite for non-blocking I/O — database operations run in a
background thread so the event loop stays free to handle other requests.

ARCHITECTURE DECISION: One connection per request via async context manager.

Why per-request instead of a persistent connection?
  Each request gets its own isolated aiosqlite connection.  This is
  essential for the Unit of Work pattern where each request needs its
  own BEGIN EXCLUSIVE transaction — impossible with a shared connection.
  The trade-off is ~2-3ms overhead per request for thread creation,
  but data integrity and transaction isolation are non-negotiable.

Usage in service layer:
    async with get_connection() as db:
        cursor = await db.execute(...)
"""

import logging

import aiosqlite

from config.settings import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> aiosqlite.Connection:
    """Return an async context manager that opens a new aiosqlite connection.

    Each call creates a fresh connection with its own background thread.
    The connection is automatically closed when the context manager exits.

    Usage:
        async with get_connection() as db:
            await db.execute("SELECT ...")
    """
    return aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """Enable WAL-mode and create schema.

    Called once at server startup via @app.before_server_start.

    WAL-mode:  Separates readers from writers. Without WAL, a write
               locks the entire database — readers must wait.  With WAL,
               readers see a consistent snapshot while writers append
               to a separate log file.

    INDEX:     Without an index on account_id, every query that filters
               by account_id must scan all N rows (O(N)).  The B-tree
               index lets SQLite jump directly to the relevant rows
               (O(log N) to find the start, then O(K) to read K matches).
               Trade-off: each INSERT is slightly slower (~1-2μs) because
               the index must also be updated.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # WAL-mode — persistent (survives restarts, stored in DB file)
        await db.execute("PRAGMA journal_mode=WAL")

        # Create the transactions table if it doesn't exist.
        # idempotency_key: optional client-generated key for retry safety.
        # UNIQUE allows multiple NULLs (SQL standard) so requests without
        # a key still work.  When a key IS provided, a duplicate INSERT
        # is caught and the existing transaction is returned instead.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                idempotency_key TEXT UNIQUE
            )
            """
        )

        # Denormalized accounts table — stores pre-computed balance.
        # Without this, balance requires SUM(amount) over all K transactions
        # for an account (O(K)).  With this, balance is a single row lookup
        # on the primary key (O(1)).
        # Trade-off: each INSERT into transactions also needs an UPDATE here,
        # but reads are dramatically faster and reads >> writes in practice.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0
            )
            """
        )

        # Index on account_id — makes WHERE account_id=? queries fast
        # IF NOT EXISTS prevents errors on subsequent startups
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_account_id
            ON transactions(account_id)
            """
        )

        await db.commit()
    logger.info("Database initialized at %s (WAL-mode, indexed)", DB_PATH)
