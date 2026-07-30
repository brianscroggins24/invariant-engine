"""Errors raised while validating local market data."""


class DomainError(ValueError):
    """Base class for invalid domain values."""


class PayloadError(DomainError):
    """A fixture payload does not match the supported venue-native shape."""


class ReplayError(DomainError):
    """A local replay cannot be applied deterministically."""
