"""Shared test fixtures for backend integration tests.

Each test gets a fresh SQLite database (temp file) with the full
schema pre-created.  Cleanup is automatic via pytest's tmp_path.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest_asyncio

# Add app-sanic/ to sys.path so bare imports like
# 'from models.database import ...' work the same way
# as when running the server from the app-sanic/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Provide a clean, isolated database for each test.

    Why a temp FILE instead of :memory:?
      Our architecture uses per-request connections — each call to
      get_connection() or UnitOfWork() opens a NEW aiosqlite connection.
      With :memory:, each connection gets its own empty database.
      A temp file ensures all connections within a test reach the
      same database, just like production.

    Why patch TWO modules?
      Both database.py and unit_of_work.py do:
          from config.settings import DB_PATH
      This creates a local binding in each module.  Patching
      config.settings.DB_PATH alone would NOT affect the already-
      imported local copies.  We must patch where the value is USED.

    Lifecycle:
      1. Create temp file path (pytest's tmp_path ensures uniqueness)
      2. Patch DB_PATH in both modules that use it
      3. Run init_db() → creates tables, indexes, enables WAL
      4. Yield → test runs against this clean database
      5. Context manager exits → patches are restored
      6. pytest deletes tmp_path automatically
    """
    db_path = str(tmp_path / "test.db")

    with (
        patch("models.database.DB_PATH", db_path),
        patch("models.unit_of_work.DB_PATH", db_path),
    ):
        from models.database import init_db

        await init_db()
        yield db_path
