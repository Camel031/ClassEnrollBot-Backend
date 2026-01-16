from typing import Any


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    pass


class AuthorizationError(AppException):
    """Raised when user is not authorized to perform an action."""

    pass


class NotFoundError(AppException):
    """Raised when a resource is not found."""

    pass


class ValidationError(AppException):
    """Raised when validation fails."""

    pass


class NTNUClientError(AppException):
    """Raised when NTNU API client encounters an error."""

    pass


class NTNULoginError(NTNUClientError):
    """Raised when NTNU login fails."""

    pass


class NTNUSessionExpiredError(NTNUClientError):
    """Raised when NTNU session has expired."""

    pass


class CaptchaError(AppException):
    """Raised when captcha recognition fails."""

    pass


class EnrollmentError(AppException):
    """Raised when course enrollment fails."""

    pass


class RateLimitError(AppException):
    """Raised when rate limit is exceeded."""

    pass
