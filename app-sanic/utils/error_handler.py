"""Centralized error handler — catches domain exceptions and returns
standardized JSON responses.  Internal details are logged but never
exposed to the client.
"""

import logging

from sanic.response import json

from utils.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """Attach global error handlers to the Sanic application."""

    @app.exception(AppError)
    async def handle_app_error(request, exception):
        """Return a safe JSON envelope for known application errors."""
        logger.warning(
            "AppError: %s (status=%d)",
            exception.message,
            exception.status_code,
        )
        return json({"error": exception.message}, status=exception.status_code)
