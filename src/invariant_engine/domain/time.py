"""Deterministic timestamp parsing for fixture payloads."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from invariant_engine.domain.errors import DomainError


def parse_timestamp(value: Any, *, field: str = "timestamp") -> datetime:
    """Parse ISO-8601 or an integer/Decimal Unix timestamp in milliseconds."""

    if isinstance(value, bool):
        raise DomainError(f"{field} is not a valid timestamp")
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, Decimal)) or isinstance(value, str) and value.isdigit():
        try:
            milliseconds = Decimal(str(value))
            microseconds_decimal = milliseconds * Decimal("1000")
            microseconds = int(microseconds_decimal)
        except (InvalidOperation, ValueError) as exc:
            raise DomainError(f"{field} is not a valid timestamp") from exc
        if microseconds_decimal != microseconds:
            raise DomainError(f"{field} has more precision than microseconds")
        result = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=microseconds)
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DomainError(f"{field} is not a valid ISO-8601 timestamp") from exc
    else:
        raise DomainError(f"{field} is not a valid timestamp")
    if result.tzinfo is None or result.utcoffset() is None:
        raise DomainError(f"{field} must include a timezone")
    return result.astimezone(UTC)
