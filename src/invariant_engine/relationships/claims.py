"""Venue-native claim bindings for propositions."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invariant_engine.domain.decimal_policy import ONE, ZERO
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.relationships.ids import ClaimBindingId, EvidenceId, PropositionId
from invariant_engine.venues.kalshi import KalshiMarketIdentity, KalshiNativeSideKind


class ClaimClassification(StrEnum):
    BINARY_UNIT = "binary_unit"
    SCALAR = "scalar"


class PolymarketOutcomeSide(StrEnum):
    YES = "yes"
    NO = "no"


class _ClaimBinding:
    @staticmethod
    def validate_fields(value: object) -> None:
        proposition_id = value.proposition_id  # type: ignore[attr-defined]
        binding_id = value.binding_id  # type: ignore[attr-defined]
        classification = value.classification  # type: ignore[attr-defined]
        if not isinstance(proposition_id, PropositionId):
            raise DomainError("claim proposition_id must be a PropositionId")
        if not isinstance(binding_id, ClaimBindingId):
            raise DomainError("binding_id must be a ClaimBindingId")
        if not isinstance(classification, ClaimClassification):
            raise DomainError("claim classification must be a ClaimClassification")
        evidence_ids = value.evidence_ids  # type: ignore[attr-defined]
        raw_refs = value.raw_refs  # type: ignore[attr-defined]
        if not isinstance(evidence_ids, tuple):
            object.__setattr__(value, "evidence_ids", tuple(evidence_ids))
            evidence_ids = value.evidence_ids  # type: ignore[attr-defined]
        if not isinstance(raw_refs, tuple):
            object.__setattr__(value, "raw_refs", tuple(raw_refs))
            raw_refs = value.raw_refs  # type: ignore[attr-defined]
        if any(not isinstance(item, EvidenceId) for item in evidence_ids):
            raise DomainError("claim evidence_ids must contain EvidenceId values")
        if any(not isinstance(item, RawReference) for item in raw_refs):
            raise DomainError("claim raw_refs must contain RawReference values")

    @staticmethod
    def gross_terminal_payout(proposition_true: bool) -> Decimal:
        """Return the unit payout for the claim's proposition truth value."""

        if not isinstance(proposition_true, bool):
            raise DomainError("proposition truth must be boolean")
        return ONE if proposition_true else ZERO


@dataclass(frozen=True, slots=True)
class PolymarketClaimBinding(_ClaimBinding):
    proposition_id: PropositionId
    binding_id: ClaimBindingId
    classification: ClaimClassification
    market: MarketReference
    outcome_token: ContractReference
    native_outcome_side: PolymarketOutcomeSide | str | None = None
    evidence_ids: tuple[EvidenceId, ...] = ()
    raw_refs: tuple[RawReference, ...] = ()

    def __post_init__(self) -> None:
        _ClaimBinding.validate_fields(self)
        if self.market.venue is not Venue.POLYMARKET:
            raise DomainError("Polymarket binding market must be Polymarket-native")
        if self.outcome_token.venue is not Venue.POLYMARKET:
            raise DomainError("Polymarket outcome token must be Polymarket-native")
        if any(raw_ref.venue is not Venue.POLYMARKET for raw_ref in self.raw_refs):
            raise DomainError("Polymarket binding raw_refs must be Polymarket-native")
        if self.native_outcome_side is not None:
            try:
                object.__setattr__(
                    self, "native_outcome_side", PolymarketOutcomeSide(self.native_outcome_side)
                )
            except ValueError as exc:
                raise DomainError("unsupported Polymarket native outcome side") from exc


@dataclass(frozen=True, slots=True)
class KalshiClaimBinding(_ClaimBinding):
    proposition_id: PropositionId
    binding_id: ClaimBindingId
    classification: ClaimClassification
    market: KalshiMarketIdentity
    native_side: KalshiNativeSideKind
    evidence_ids: tuple[EvidenceId, ...] = ()
    raw_refs: tuple[RawReference, ...] = ()

    def __post_init__(self) -> None:
        _ClaimBinding.validate_fields(self)
        if not isinstance(self.market, KalshiMarketIdentity):
            raise DomainError("Kalshi binding market must be KalshiMarketIdentity")
        if not isinstance(self.native_side, KalshiNativeSideKind):
            raise DomainError("Kalshi binding native_side must be a KalshiNativeSideKind")
        if any(raw_ref.venue is not Venue.KALSHI for raw_ref in self.raw_refs):
            raise DomainError("Kalshi binding raw_refs must be Kalshi-native")


ClaimBinding = PolymarketClaimBinding | KalshiClaimBinding

__all__ = [
    "ClaimBinding",
    "ClaimClassification",
    "KalshiClaimBinding",
    "PolymarketClaimBinding",
    "PolymarketOutcomeSide",
]
