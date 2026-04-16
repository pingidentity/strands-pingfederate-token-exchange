"""SDK-specific exceptions."""


class SDKError(Exception):
    """Base exception for the SDK."""


class ConfigurationError(SDKError):
    """Raised when SDK configuration is invalid or incomplete."""


class AuthenticationError(SDKError):
    """Raised when the inbound subject token is missing or malformed."""


class TokenExchangeError(SDKError):
    """Raised when the PingFederate token exchange call fails."""

    def __init__(self, status_code: int, error: str, description: str = "") -> None:
        self.status_code = status_code
        self.error = error
        self.description = description
        message = f"Token exchange failed ({status_code}): {error}"
        if description:
            message = f"{message}: {description}"
        super().__init__(message)
