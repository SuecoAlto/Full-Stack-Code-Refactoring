"""Centralized error handler — catches domain exceptions and returns
standardized JSON responses.  Internal details are logged but never
exposed to the client.
"""

import logging

from sanic import Sanic
from sanic.request import Request
from sanic.response import json, HTTPResponse

from utils.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: Sanic) -> None:
    """Attach global error handlers to the Sanic application."""

    @app.exception(AppError)
    async def handle_app_error(request: Request, exception: AppError) -> HTTPResponse:
        """Tier 1 — domain errors (400, 404).

        These are expected conditions raised by the service layer.
        Logged at WARNING (no traceback needed — the cause is known).
        The error message is safe to show the client.
        """
        logger.warning(
            "AppError: %s (status=%d)",
            exception.message,
            exception.status_code,
        )
        return json({"error": exception.message}, status=exception.status_code)

    @app.exception(Exception)
    async def handle_unexpected_error(request: Request, exception: Exception) -> HTTPResponse:
        """Tier 2 — unexpected errors (500).

        Catches everything not handled by Tier 1 (TypeError, sqlite3 errors,
        bugs, etc.).  The full traceback is logged server-side for debugging,
        but only a generic message is returned to the client — never leak
        internal details (file paths, SQL, variable names).
        """
        logger.exception("Unhandled error: %s", exception)
        return json(
            {"error": "An unexpected error occurred"},
            status=500,
        )
