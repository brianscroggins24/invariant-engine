"""Immutable, venue-aware identifier types."""

from dataclasses import dataclass
from enum import StrEnum

from invariant_engine.domain.errors import DomainError


class Venue(StrEnum):
    POLYMARKET = "polymarket"
    POLYMARKET_US = "polymarket_us"
    KALSHI = "kalshi"


@dataclass(frozen=True, slots=True)
class _VenueIdentifier:
    value: str
    venue: Venue

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise DomainError("identifier value must be a non-empty string")
        if not isinstance(self.venue, Venue):
            raise DomainError("identifier venue must be a Venue")


@dataclass(frozen=True, slots=True)
class RawReference(_VenueIdentifier):
    """Reference to an immutable raw envelope."""


@dataclass(frozen=True, slots=True)
class MarketReference(_VenueIdentifier):
    """Reference to a venue-native market."""


@dataclass(frozen=True, slots=True)
class ContractReference(_VenueIdentifier):
    """Reference to a venue-native contract or token."""


@dataclass(frozen=True, slots=True)
class FixtureReference(_VenueIdentifier):
    """Reference to a local fixture artifact."""
