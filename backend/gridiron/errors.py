"""Typed exceptions shared across services and platform clients."""


class GridironError(Exception):
    """Base class for all GridIron application errors."""


class CredentialDecryptError(GridironError):
    """Raised when a stored credential can't be decrypted (bad key or corrupt token)."""


class AuthRequiredError(GridironError):
    """Raised when a platform call needs re-authentication (expired/invalid credentials)."""


class RateLimitedError(GridironError):
    """Raised when a platform keeps returning a rate-limit status after backoff retries."""
