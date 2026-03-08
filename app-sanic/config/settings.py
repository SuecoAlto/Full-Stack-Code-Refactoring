"""Application configuration settings.

Centralizes all environment-specific values so that no magic
strings are scattered across the codebase.
"""

# Database file path (relative to the app-sanic/ working directory)
DB_PATH = "transactions.db"

# CORS — allow the React dev server to call the API
CORS_ORIGINS = "http://localhost:3000"