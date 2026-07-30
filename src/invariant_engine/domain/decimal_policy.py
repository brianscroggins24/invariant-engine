"""Decimal-only policy for market prices, quantities, and fees."""

from decimal import Decimal, InvalidOperation
from typing import Any

from invariant_engine.domain.errors import DomainError

ZERO = Decimal("0")
ONE = Decimal("1")


def parse_decimal(value: Any, *, field: str) -> Decimal:
    """Parse a Decimal, string, or integer without allowing binary-float input."""

    if isinstance(value, bool) or isinstance(value, float):
        raise DomainError(f"{field} must not be supplied as a binary float")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (str, int)):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise DomainError(f"{field} is not a valid Decimal") from exc
    else:
        raise DomainError(f"{field} must be a Decimal, string, or integer")
    if not result.is_finite():
        raise DomainError(f"{field} must be finite")
    return result


def parse_price(value: Any, *, field: str = "price") -> Decimal:
    """Parse a prediction-market price and validate its inclusive [0, 1] range."""

    result = parse_decimal(value, field=field)
    if result < ZERO or result > ONE:
        raise DomainError(f"{field} must be between 0 and 1")
    return result


def parse_quantity(value: Any, *, field: str = "quantity") -> Decimal:
    """Parse a non-negative quantity without rounding or changing its scale."""

    result = parse_decimal(value, field=field)
    if result < ZERO:
        raise DomainError(f"{field} must not be negative")
    return result
