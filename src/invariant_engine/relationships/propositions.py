"""Truth-bearing propositions independent of venue instruments."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from invariant_engine.domain.errors import DomainError
from invariant_engine.relationships.ids import PropositionId


@dataclass(frozen=True, slots=True)
class Threshold:
    """A threshold retained with its explicit unit and semantic label."""

    name: str
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DomainError("threshold name must be non-empty")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise DomainError("threshold value must be a finite Decimal")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise DomainError("threshold unit must be non-empty")


@dataclass(frozen=True, slots=True)
class ObservationPeriod:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for label, value in (("start", self.start), ("end", self.end)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise DomainError(f"observation period {label} must be timezone-aware")
        if self.end < self.start:
            raise DomainError("observation period end must not precede start")


@dataclass(frozen=True, slots=True)
class Proposition:
    """A truth-bearing statement with no market, token, or venue identity."""

    proposition_id: PropositionId
    statement: str
    event_scope: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.proposition_id, PropositionId):
            raise DomainError("proposition_id must be a PropositionId")
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise DomainError("proposition statement must be non-empty")
        if self.event_scope is not None and (
            not isinstance(self.event_scope, str) or not self.event_scope.strip()
        ):
            raise DomainError("event_scope must be non-empty when supplied")


__all__ = ["ObservationPeriod", "Proposition", "Threshold"]
