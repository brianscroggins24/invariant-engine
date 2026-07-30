"""Structured warnings retained alongside normalized market data."""

from dataclasses import dataclass
from enum import StrEnum


class WarningCode(StrEnum):
    MISSING_PROVENANCE = "missing_provenance"
    STALE_SNAPSHOT = "stale_snapshot"
    INCOMPLETE_DEPTH = "incomplete_depth"
    MISSING_FEE = "missing_fee"
    ESTIMATED_FEE = "estimated_fee"
    DERIVED_VALUE = "derived_value"
    AMBIGUOUS_LIFECYCLE = "ambiguous_lifecycle"
    UNAVAILABLE_FIELD = "unavailable_field"
    SEQUENCE_GAP = "sequence_gap"
    DETECTOR_ASSUMPTION = "detector_assumption"
    MISSING_FIELD = "missing_field"
    NON_MONOTONIC_EVENT = "non_monotonic_event"
    IGNORED_EVENT_ENTRY = "ignored_event_entry"
    SESSION_MISMATCH = "session_mismatch"
    CONVENTION_MISMATCH = "convention_mismatch"


@dataclass(frozen=True, slots=True)
class WarningRecord:
    code: WarningCode
    message: str
    field: str | None = None
