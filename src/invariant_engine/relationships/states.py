"""Explicit immutable feasible truth and payoff states."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from invariant_engine.domain.decimal_policy import parse_decimal
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference
from invariant_engine.relationships.ids import (
    ClaimBindingId,
    EvidenceId,
    FeasibleStateId,
    PropositionId,
)


class TerminalStateKind(StrEnum):
    NORMAL = "normal"
    CANCELLATION = "cancellation"
    VOID = "void"
    REFUND = "refund"


def _assignment_items(value: object, field: str) -> tuple[tuple[Any, Any], ...]:
    if isinstance(value, Mapping):
        return tuple(value.items())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        result: list[tuple[Any, Any]] = []
        for item in value:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise DomainError(f"{field} pair assignments must contain key/value pairs")
            result.append((item[0], item[1]))
        return tuple(result)
    raise DomainError(f"{field} must be a mapping or ordered key/value pairs")


def _freeze_truth(value: object) -> MappingProxyType[PropositionId, bool]:
    result: dict[PropositionId, bool] = {}
    for key, item in _assignment_items(value, "truth_assignments"):
        if not isinstance(key, PropositionId) or not isinstance(item, bool):
            raise DomainError("truth assignments must map PropositionId to bool")
        if key in result:
            raise DomainError("duplicate truth assignment")
        result[key] = item
    return MappingProxyType(result)


def _freeze_payouts(value: object) -> MappingProxyType[ClaimBindingId, Decimal]:
    result: dict[ClaimBindingId, Decimal] = {}
    for key, item in _assignment_items(value, "payout_assignments"):
        if not isinstance(key, ClaimBindingId):
            raise DomainError("payout assignments must use ClaimBindingId keys")
        if key in result:
            raise DomainError("duplicate payout assignment")
        result[key] = parse_decimal(item, field=f"payout[{key.value}]")
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class FeasibleState:
    state_id: FeasibleStateId
    terminal_kind: TerminalStateKind
    truth_assignments: Mapping[PropositionId, bool]
    payout_assignments: Mapping[ClaimBindingId, Decimal]
    evidence_ids: tuple[EvidenceId, ...] = ()
    raw_refs: tuple[RawReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state_id, FeasibleStateId):
            raise DomainError("state_id must be a FeasibleStateId")
        if not isinstance(self.terminal_kind, TerminalStateKind):
            raise DomainError("terminal_kind must be a TerminalStateKind")
        object.__setattr__(self, "truth_assignments", _freeze_truth(self.truth_assignments))
        object.__setattr__(self, "payout_assignments", _freeze_payouts(self.payout_assignments))
        if not isinstance(self.evidence_ids, tuple):
            object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        if not isinstance(self.raw_refs, tuple):
            object.__setattr__(self, "raw_refs", tuple(self.raw_refs))
        if any(not isinstance(item, EvidenceId) for item in self.evidence_ids):
            raise DomainError("state evidence_ids must contain EvidenceId values")
        if any(not isinstance(item, RawReference) for item in self.raw_refs):
            raise DomainError("state raw_refs must contain RawReference values")


FeasibleTruthPayoffState = FeasibleState
TerminalState = TerminalStateKind

__all__ = ["FeasibleState", "FeasibleTruthPayoffState", "TerminalState", "TerminalStateKind"]
