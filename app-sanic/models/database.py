"""Database initialization and connection management.

Currently uses synchronous sqlite3. Phase 2 will migrate to
aiosqlite for non-blocking I/O and enable WAL-mode.
"""

import logging
import sqlite3

from config.settings import DB_PATH
from models import repositories

logger = logging.getLogger(__name__)


def get_connection():
    """Create and return a new SQLite database connection."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """Create database tables if they do not already exist.

    Called once at application startup from server.py.
    """
    with get_connection() as conn:
        repositories.create_table(conn)
    logger.info("Database initialized at %s", DB_PATH)
