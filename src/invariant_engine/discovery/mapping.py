"""Map strictly parsed, still-untrusted proposals into 2.1 candidate/draft records."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime

from invariant_engine.discovery.schema import (
    DiscoveryInput,
    DiscoveryProposal,
    DiscoveryRequest,
    DiscoveryRuleInput,
    KalshiDiscoveryIdentity,
    PolymarketDiscoveryIdentity,
)
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import ContractReference, MarketReference, RawReference, Venue
from invariant_engine.relationships.candidates import (
    RelationshipCandidate,
    RelationshipCertificateDraft,
    RelationshipDeclaration,
    RelationshipType,
)
from invariant_engine.relationships.claims import (
    ClaimClassification,
    KalshiClaimBinding,
    PolymarketClaimBinding,
    PolymarketOutcomeSide,
)
from invariant_engine.relationships.evidence import (
    CompletenessDeclaration,
    Evidence,
    EvidenceKind,
)
from invariant_engine.relationships.ids import (
    CandidateId,
    ClaimBindingId,
    DraftId,
    EvidenceId,
    PropositionId,
)
from invariant_engine.relationships.propositions import ObservationPeriod, Proposition
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import KalshiMarketIdentity, KalshiNativeSideKind

UNTRUSTED_DISCOVERY_VALIDATION_METHOD = "recorded-discovery-untrusted-v1"
RELATIONSHIP_DRAFT_SCHEMA_VERSION = "relationship-draft-v1"


class ProposalMappingError(DomainError):
    """A structurally parsed proposal cannot be mapped without invention."""


@dataclass(frozen=True, slots=True)
class MappedProposal:
    candidate: RelationshipCandidate
    draft: RelationshipCertificateDraft


def _digest(value: object) -> str:
    return hashlib.sha256(stable_json_bytes(value)).hexdigest()


def _unique_raw_refs(values: tuple[RawReference, ...]) -> tuple[RawReference, ...]:
    result: list[RawReference] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def request_provenance_closure(request: DiscoveryRequest) -> tuple[RawReference, ...]:
    """Return the v1 ordered raw-reference closure for one discovery request."""

    return _unique_raw_refs(
        tuple(raw for item in request.inputs for raw in item.raw_refs)
        + tuple(
            raw for item in request.inputs for rule in item.market_rules for raw in rule.raw_refs
        )
    )


def _time(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProposalMappingError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProposalMappingError(f"{field} must be timezone-aware")
    return parsed


def _input_map(request: DiscoveryRequest) -> dict[str, DiscoveryInput]:
    return {item.input_id: item for item in request.inputs}


def _canonical_proposal(proposal: DiscoveryProposal) -> DiscoveryProposal:
    propositions = tuple(
        replace(item, proposal_proposition_id="canonical-proposition")
        for item in proposal.propositions
    )
    if proposal.relationship_type in {
        "mutually_exclusive_set",
        "exhaustive_set",
        "exclusive_and_exhaustive_partition",
    }:
        propositions = tuple(sorted(propositions, key=lambda item: item.input_id))
    return replace(
        proposal,
        proposal_id="canonical-proposal",
        propositions=propositions,
    )


def _relationship_type(value: str) -> RelationshipType:
    try:
        relationship = RelationshipType(value)
    except ValueError as exc:
        raise ProposalMappingError("unknown relationship type") from exc
    if relationship is RelationshipType.CONDITIONAL:
        raise ProposalMappingError("conditional relationships are unsupported")
    return relationship


def _check_arity(relationship: RelationshipType, count: int) -> None:
    if (
        relationship
        in {
            RelationshipType.IMPLICATION,
            RelationshipType.EQUIVALENCE,
            RelationshipType.COMPLEMENT,
            RelationshipType.SUBSET,
            RelationshipType.SUPERSET,
        }
        and count != 2
    ):
        raise ProposalMappingError("directional relationship requires exactly two propositions")
    if (
        relationship
        in {
            RelationshipType.MUTUALLY_EXCLUSIVE_SET,
            RelationshipType.EXHAUSTIVE_SET,
            RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION,
        }
        and count < 2
    ):
        raise ProposalMappingError("set relationship requires at least two propositions")


def _binding(
    input_record: DiscoveryInput,
    proposition_id: PropositionId,
    binding_id: ClaimBindingId,
    evidence_ids: tuple[EvidenceId, ...],
) -> PolymarketClaimBinding | KalshiClaimBinding:
    identity = input_record.venue_identity
    if isinstance(identity, PolymarketDiscoveryIdentity):
        native_side = (
            PolymarketOutcomeSide(identity.native_outcome_side)
            if identity.native_outcome_side is not None
            else None
        )
        return PolymarketClaimBinding(
            proposition_id=proposition_id,
            binding_id=binding_id,
            classification=ClaimClassification.BINARY_UNIT,
            market=MarketReference(identity.market_reference, Venue.POLYMARKET),
            outcome_token=ContractReference(identity.outcome_token_reference, Venue.POLYMARKET),
            native_outcome_side=native_side,
            evidence_ids=evidence_ids,
            raw_refs=input_record.raw_refs,
        )
    if not isinstance(identity, KalshiDiscoveryIdentity):
        raise ProposalMappingError("unsupported venue identity")
    return KalshiClaimBinding(
        proposition_id=proposition_id,
        binding_id=binding_id,
        classification=ClaimClassification.BINARY_UNIT,
        market=KalshiMarketIdentity(identity.market_ticker, identity.market_id),
        native_side=KalshiNativeSideKind(identity.native_side),
        evidence_ids=evidence_ids,
        raw_refs=input_record.raw_refs,
    )


def map_proposal(proposal: DiscoveryProposal, request: DiscoveryRequest) -> MappedProposal:
    """Map one valid proposal; this function imports no validator or certificate type."""

    relationship = _relationship_type(proposal.relationship_type)
    _check_arity(relationship, len(proposal.propositions))
    if proposal.claim_classification != "binary_unit":
        raise ProposalMappingError("scalar or non-binary-unit proposals are unsupported")
    if proposal.condition is not None:
        raise ProposalMappingError("conditional proposal content is unsupported")
    if proposal.conflicting_evidence:
        raise ProposalMappingError("conflicting evidence requires rejection")
    if proposal.unit is not None or proposal.timing is not None or proposal.resolution is not None:
        raise ProposalMappingError(
            "unit, timing, and resolution metadata have no existing draft representation"
        )
    inputs = _input_map(request)
    proposition_input_records: list[DiscoveryInput] = []
    for item in proposal.propositions:
        if item.binding_ref != item.input_id:
            raise ProposalMappingError("binding_ref must exactly reference its supplied input")
        input_record = inputs.get(item.input_id)
        if input_record is None:
            raise ProposalMappingError("proposal references an unknown discovery input")
        if not input_record.raw_refs:
            raise ProposalMappingError("proposal input lacks required raw provenance")
        if input_record.claim_classification != "binary_unit":
            raise ProposalMappingError("a proposal references a non-binary-unit input")
        proposition_input_records.append(input_record)
    if len({item.input_id for item in proposition_input_records}) != len(proposition_input_records):
        raise ProposalMappingError("proposal proposition inputs must be unique")

    participating_input_ids = {item.input_id for item in proposition_input_records}
    rules: dict[str, DiscoveryRuleInput] = {}
    rule_owners: dict[str, str] = {}
    for input_record in request.inputs:
        for rule in input_record.market_rules:
            if rule.rule_input_id in rules:
                raise ProposalMappingError("duplicate rule input ID cannot be reconciled")
            rules[rule.rule_input_id] = rule
            rule_owners[rule.rule_input_id] = input_record.input_id
    evidence_ids: list[EvidenceId] = []
    evidence: list[Evidence] = []
    evidence_rules: list[str] = []
    evidence_raw_refs: list[RawReference] = []
    for index, span in enumerate(proposal.evidence_spans):
        rule_input = rules.get(span.rule_input_id)
        if rule_input is None:
            raise ProposalMappingError("evidence span references an unknown rule input")
        if rule_owners[span.rule_input_id] not in participating_input_ids:
            raise ProposalMappingError("evidence rule input is outside proposal participants")
        if not rule_input.raw_refs:
            raise ProposalMappingError("evidence rule input lacks required raw provenance")
        if span.end > len(rule_input.rule_text):
            raise ProposalMappingError("evidence span exceeds supplied rule text boundary")
        if span.text != rule_input.rule_text[span.start : span.end]:
            raise ProposalMappingError("evidence span text does not close over supplied rule text")
        if span.raw_refs != rule_input.raw_refs:
            raise ProposalMappingError("evidence span raw provenance differs from supplied rule")
        evidence_digest = _digest(
            {
                "rule_input_id": rule_input.rule_input_id,
                "start": span.start,
                "end": span.end,
                "text": span.text,
                "raw_refs": span.raw_refs,
            }
        )
        evidence_id = EvidenceId(f"discovery:evidence:{index:04d}:{evidence_digest}")
        evidence_ids.append(evidence_id)
        evidence_rules.append(rule_input.rule_input_id)
        evidence_raw_refs.extend(rule_input.raw_refs)
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=EvidenceKind.MARKET_RULE,
                rule_text=rule_input.rule_text,
                evidence_span=span.text,
                locator=f"discovery-rule:{rule_input.rule_input_id}[{span.start}:{span.end}]",
                content_digest=hashlib.sha256(rule_input.rule_text.encode("utf-8")).hexdigest(),
                raw_refs=rule_input.raw_refs,
                synthetic=True,
            )
        )
    if not evidence:
        raise ProposalMappingError("proposal must supply at least one evidence span")

    proposition_ids: list[PropositionId] = []
    propositions: list[Proposition] = []
    for index, input_record in enumerate(proposition_input_records):
        proposition_digest = _digest(
            {
                "input_id": input_record.input_id,
                "question": input_record.question,
                "venue": input_record.venue,
                "identity": input_record.venue_identity,
                "raw_refs": input_record.raw_refs,
            }
        )
        proposition_id = PropositionId(f"discovery:proposition:{index:04d}:{proposition_digest}")
        proposition_ids.append(proposition_id)
        propositions.append(Proposition(proposition_id, input_record.question))

    declaration = RelationshipDeclaration(relationship, tuple(proposition_ids))
    bindings: list[PolymarketClaimBinding | KalshiClaimBinding] = []
    for index, input_record in enumerate(proposition_input_records):
        binding_digest = _digest(
            {
                "input": input_record,
                "proposition_id": proposition_ids[index],
                "evidence": evidence_ids,
            }
        )
        binding_id = ClaimBindingId(f"discovery:binding:{index:04d}:{binding_digest}")
        bindings.append(
            _binding(input_record, proposition_ids[index], binding_id, tuple(evidence_ids))
        )

    resolution_sources: list[EvidenceId] = []
    for rule_id in proposal.resolution_sources:
        try:
            resolution_sources.append(evidence_ids[evidence_rules.index(rule_id)])
        except ValueError as exc:
            raise ProposalMappingError(
                "resolution source does not reference supplied evidence"
            ) from exc

    close_time = _time(proposal.close_time, "close_time")
    resolution_time = _time(proposal.resolution_time, "resolution_time")
    observation_period = None
    if proposal.observation_start is not None or proposal.observation_end is not None:
        if proposal.observation_start is None or proposal.observation_end is None:
            raise ProposalMappingError("observation period requires both bounds")
        observation_start = _time(proposal.observation_start, "observation_start")
        observation_end = _time(proposal.observation_end, "observation_end")
        assert observation_start is not None and observation_end is not None
        observation_period = ObservationPeriod(observation_start, observation_end)
    canonical_proposal = _canonical_proposal(proposal)
    candidate_digest = _digest(
        {
            "proposal": canonical_proposal,
            "request": request,
            "proposition_ids": tuple(proposition_ids),
            "evidence_ids": tuple(evidence_ids),
        }
    )
    top_level_provenance = _unique_raw_refs(
        tuple(raw for item in proposition_input_records for raw in item.raw_refs)
        + tuple(evidence_raw_refs)
    )
    candidate = RelationshipCandidate(
        candidate_id=CandidateId(f"discovery:candidate:{candidate_digest}"),
        proposition_ids=declaration.proposition_ids,
        proposed_relationship=declaration,
        evidence_ids=tuple(evidence_ids),
        raw_refs=top_level_provenance,
        source="recorded_discovery",
    )
    draft_digest = _digest(
        {
            "candidate_id": candidate.candidate_id,
            "bindings": tuple(bindings),
            "evidence": tuple(evidence),
            "metadata": canonical_proposal,
        }
    )
    draft = RelationshipCertificateDraft(
        draft_id=DraftId(f"discovery:draft:{draft_digest}"),
        originating_candidate_id=candidate.candidate_id,
        propositions=tuple(propositions),
        bindings=tuple(bindings),
        proposed_relationship=declaration,
        evidence=tuple(evidence),
        event_scope=proposal.event_scope,
        thresholds=tuple(item.to_relationship_threshold() for item in proposal.thresholds),
        observation_period=observation_period,
        close_time=close_time,
        resolution_time=resolution_time,
        resolution_sources=tuple(resolution_sources),
        cancellation_behavior=proposal.cancellation_behavior,
        void_behavior=proposal.void_behavior,
        refund_behavior=proposal.refund_behavior,
        payout_structure=proposal.payout_structure,
        edge_cases=proposal.edge_cases,
        assumptions=proposal.assumptions,
        uncertainties=proposal.uncertainties,
        evidence_provenance=top_level_provenance,
        validation_method=UNTRUSTED_DISCOVERY_VALIDATION_METHOD,
        feasible_states=(),
        completeness=CompletenessDeclaration(
            declared_complete=False,
            basis="Discovery does not attest state-space completeness.",
            attestation_scope="untrusted-recorded-discovery",
            evidence_ids=tuple(evidence_ids),
            raw_refs=top_level_provenance,
        ),
        semantic_review=None,
        schema_version=RELATIONSHIP_DRAFT_SCHEMA_VERSION,
    )
    return MappedProposal(candidate, draft)


__all__ = [
    "MappedProposal",
    "ProposalMappingError",
    "RELATIONSHIP_DRAFT_SCHEMA_VERSION",
    "UNTRUSTED_DISCOVERY_VALIDATION_METHOD",
    "map_proposal",
    "request_provenance_closure",
]
