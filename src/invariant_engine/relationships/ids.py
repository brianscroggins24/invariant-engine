"""Nominal immutable identifiers for the relationship trust pipeline."""

import re
from dataclasses import dataclass

from invariant_engine.domain.errors import DomainError

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


def _check_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or _IDENTIFIER.fullmatch(value) is None:
        raise DomainError(f"{label} must be a non-empty well-formed identifier")
    return value


@dataclass(frozen=True, slots=True)
class _RelationshipIdentifier:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _check_identifier(self.value, type(self).__name__))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PropositionId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class ClaimBindingId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class CandidateId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class DraftId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class CertificateId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class FeasibleStateId(_RelationshipIdentifier):
    pass


@dataclass(frozen=True, slots=True)
class SemanticReviewId(_RelationshipIdentifier):
    pass


RelationshipId = _RelationshipIdentifier


__all__ = [
    "CandidateId",
    "CertificateId",
    "ClaimBindingId",
    "DraftId",
    "EvidenceId",
    "FeasibleStateId",
    "PropositionId",
    "RelationshipId",
    "SemanticReviewId",
]
