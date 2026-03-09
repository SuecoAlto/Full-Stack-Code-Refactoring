"""Integration tests for the Unit of Work pattern.

These tests verify the core database guarantees:
  - Test 12: COMMIT on success (data persists)
  - Test 13: ROLLBACK on error (data discarded)
  - Test 14: BEGIN EXCLUSIVE prevents race conditions under concurrency

All tests run against a temporary SQLite file via the test_db fixture.
"""

import asyncio

import aiosqlite

from models.unit_of_work import UnitOfWork
from services import transaction_service


async def test_unit_of_work_commits_on_success(test_db):
    """Test 12: Data persists after a successful UoW block.

    Verifies that when no exception is raised inside the UoW,
    COMMIT is executed and the INSERT is visible to subsequent
    connections.
    """
    async with UnitOfWork() as db:
        await db.execute(
            "INSERT INTO transactions (account_id, amount) VALUES (?, ?)",
            ("uow-commit-test", 100),
        )

    # Read from a separate connection — proves COMMIT actually happened
    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            "SELECT amount FROM transactions WHERE account_id = ?",
            ("uow-commit-test",),
        )
        row = await cursor.fetchone()

    assert row is not None, "Transaction should be persisted after UoW success"
    assert row[0] == 100


async def test_unit_of_work_rolls_back_on_error(test_db):
    """Test 13: Data is discarded when an exception occurs inside UoW.

    Verifies that ROLLBACK is executed when the UoW block raises,
    and that no partial data leaks into the database.
    """
    try:
        async with UnitOfWork() as db:
            await db.execute(
                "INSERT INTO transactions (account_id, amount) VALUES (?, ?)",
                ("uow-rollback-test", 999),
            )
            raise ValueError("Simulated failure")
    except ValueError:
        pass  # Expected — UoW should have rolled back

    # Verify nothing was written
    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM transactions WHERE account_id = ?",
            ("uow-rollback-test",),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 0, "Transaction should NOT be persisted after UoW failure"


async def test_concurrent_inserts_prevent_race_conditions(test_db):
    """Test 14: BEGIN EXCLUSIVE prevents lost updates under concurrency.

    Runs 50 concurrent transactions of 100 kr each to the same account
    via asyncio.gather().  If the exclusive lock works correctly, the
    final balance must be exactly 5000 kr.

    Without BEGIN EXCLUSIVE, concurrent read-modify-write sequences
    could read stale balances, causing lost updates (balance < 5000).
    """
    account_id = "race-condition-test"

    tasks = [
        transaction_service.create_transaction(account_id, 100)
        for _ in range(50)
    ]
    await asyncio.gather(*tasks)

    # Read balance from a fresh connection
    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            "SELECT balance FROM accounts WHERE account_id = ?",
            (account_id,),
        )
        row = await cursor.fetchone()

    assert row is not None, "Account should exist after 50 transactions"
    assert row[0] == 5000, (
        f"Balance should be 5000 (50 × 100), got {row[0]} — lost update detected"
    )
