"""Custom exception hierarchy for standardized error handling.

All application-level errors inherit from AppError so the
global error handler can catch them in one place and return
safe, structured JSON responses without leaking internals.
"""


class AppError(Exception):
    """Base exception for all domain/application errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class BadRequestError(AppError):
    """Client provided invalid or missing input (HTTP 400)."""

    def __init__(self, message: str = "Bad request"):
        super().__init__(message, status_code=400)


class NotFoundError(AppError):
    """Requested resource does not exist (HTTP 404)."""

    def __init__(self, message: str = "Not found"):
        super().__init__(message, status_code=404)
