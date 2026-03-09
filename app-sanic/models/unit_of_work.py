"""Unit of Work — wraps a request's database operations in an atomic transaction.

This is the single place where BEGIN / COMMIT / ROLLBACK happen.
Repositories never commit — they just execute SQL against the connection
they receive.  The UoW guarantees all-or-nothing semantics.

Why BEGIN EXCLUSIVE?
  SQLite has three transaction levels:
    DEFERRED  — no lock until first write.  Risk: two parallel readers
                can both succeed, then collide on write → SQLITE_BUSY.
    IMMEDIATE — write-lock immediately, readers still allowed (WAL).
    EXCLUSIVE — full exclusive lock.  No other connection can read or write.

  We use EXCLUSIVE because our write path is a read-modify-write sequence
  (read balance → compute new balance → write).  Without an exclusive lock,
  two concurrent requests could read the same balance and both write,
  causing a lost update.  EXCLUSIVE serializes writers so each one sees
  the result of the previous write.

  Trade-off: one writer at a time.  For SQLite (file-based, single-process)
  this is the only safe option.  PostgreSQL would use row-level locks instead.

Why isolation_level = None?
  Python's sqlite3 module (which aiosqlite wraps) has "smart" auto-transaction
  handling that silently issues BEGIN before DML statements.  Setting
  isolation_level = None disables this entirely, giving us full manual
  control over BEGIN / COMMIT / ROLLBACK.  Without this, our explicit
  BEGIN EXCLUSIVE would conflict with the implicit BEGIN.

Usage:
    async with UnitOfWork() as db:
        await db.execute("INSERT ...")
        await db.execute("UPDATE ...")
        # COMMIT happens automatically on clean exit
        # ROLLBACK happens automatically on exception
"""

import aiosqlite

from config.settings import DB_PATH


class UnitOfWork:
    """Async context manager for atomic database transactions."""

    def __init__(self):
        self._conn: aiosqlite.Connection = None  # type: ignore[assignment]

    async def __aenter__(self) -> aiosqlite.Connection:
        # isolation_level=None disables Python's implicit transaction
        # handling so our explicit BEGIN EXCLUSIVE is the only control.
        # Passed as a kwarg so it runs on aiosqlite's background thread
        # (accessing _conn directly would violate SQLite's thread safety).
        self._conn = await aiosqlite.connect(DB_PATH, isolation_level=None)
        await self._conn.execute("BEGIN EXCLUSIVE")
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                await self._conn.execute("COMMIT")
            else:
                await self._conn.execute("ROLLBACK")
        finally:
            await self._conn.close()
        return False  # Propagate exceptions to the caller
