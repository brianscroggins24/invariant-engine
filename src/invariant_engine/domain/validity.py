"""Machine-readable validity state for replayed market data."""

from enum import StrEnum


class StateValidity(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
