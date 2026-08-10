"""Fail-closed orchestration for bounded recorded discovery attempts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum

from invariant_engine.discovery.mapping import (
    MappedProposal,
    ProposalMappingError,
    map_proposal,
    request_provenance_closure,
)
from invariant_engine.discovery.parser import (
    DiscoveryParseError,
    parse_discovery_output,
    parse_discovery_request,
)
from invariant_engine.discovery.prefilters import evaluate_prefilters
from invariant_engine.discovery.schema import (
    DISCOVERY_FIXTURE_SCHEMA_VERSION,
    DISCOVERY_INPUT_SCHEMA_VERSION,
    DISCOVERY_OUTPUT_SCHEMA_VERSION,
    DiscoveryDisposition,
    DiscoveryOutcome,
    DiscoveryProposal,
    DiscoveryRequest,
    ParsedDiscoveryOutput,
    PrefilterEvaluation,
    PrefilterPolicy,
)
from invariant_engine.discovery.source import RecordedAttempt, RecordedResponseSource
from invariant_engine.domain.errors import DomainError
from invariant_engine.relationships.candidates import (
    RelationshipCandidate,
    RelationshipCertificateDraft,
)
from invariant_engine.serialization import stable_json_bytes


class ProposalDisposition(StrEnum):
    INVALID = "invalid"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    enabled: bool
    max_attempts: int
    prefilter_policy: PrefilterPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise DomainError("discovery enabled must be boolean")
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise DomainError("max_attempts must be an integer")
        if self.max_attempts <= 0:
            raise DomainError("max_attempts must be positive")
        if not isinstance(self.prefilter_policy, PrefilterPolicy):
            raise DomainError("prefilter_policy must be explicit")


@dataclass(frozen=True, slots=True)
class MalformedAttemptRecord:
    attempt_index: int
    artifact_id: str
    artifact_sha256: str
    input_sha256: str
    output_sha256: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_index, int) or self.attempt_index < 0:
            raise DomainError("malformed attempt index must be a non-negative integer")
        for field in (
            "artifact_id",
            "artifact_sha256",
            "input_sha256",
            "output_sha256",
            "reason",
        ):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise DomainError(f"malformed attempt {field} must be non-empty")


@dataclass(frozen=True, slots=True)
class ProposalRejectionRecord:
    proposal_id: str
    disposition: ProposalDisposition
    reason: str
    fingerprint: str
    duplicate_of: str | None = None

    def __post_init__(self) -> None:
        for field in ("proposal_id", "reason", "fingerprint"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise DomainError(f"proposal rejection {field} must be non-empty")
        if not isinstance(self.disposition, ProposalDisposition):
            raise DomainError("proposal rejection disposition is unsupported")


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    disposition: DiscoveryDisposition
    attempts: tuple[RecordedAttempt, ...]
    malformed_attempts: tuple[MalformedAttemptRecord, ...]
    candidates: tuple[RelationshipCandidate, ...] = ()
    drafts: tuple[RelationshipCertificateDraft, ...] = ()
    proposal_rejections: tuple[ProposalRejectionRecord, ...] = ()
    prefilter_evaluations: tuple[PrefilterEvaluation, ...] = ()
    parsed_outputs: tuple[ParsedDiscoveryOutput, ...] = ()
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, DiscoveryDisposition):
            raise DomainError("discovery result disposition is unsupported")
        for field in (
            "attempts",
            "malformed_attempts",
            "candidates",
            "drafts",
            "proposal_rejections",
            "prefilter_evaluations",
            "parsed_outputs",
        ):
            if not isinstance(getattr(self, field), tuple):
                object.__setattr__(self, field, tuple(getattr(self, field)))
        if any(not isinstance(item, RecordedAttempt) for item in self.attempts):
            raise DomainError("result attempts must contain RecordedAttempt values")
        if any(not isinstance(item, MalformedAttemptRecord) for item in self.malformed_attempts):
            raise DomainError("result malformed_attempts have an invalid structure")
        if any(not isinstance(item, ProposalRejectionRecord) for item in self.proposal_rejections):
            raise DomainError("result proposal_rejections have an invalid structure")
        if any(not isinstance(item, ParsedDiscoveryOutput) for item in self.parsed_outputs):
            raise DomainError("result parsed_outputs have an invalid structure")


def _fingerprint(proposal: DiscoveryProposal) -> str:
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
    proposal = replace(
        proposal,
        proposal_id="canonical-proposal",
        propositions=propositions,
    )
    if proposal.relationship_type in {
        "mutually_exclusive_set",
        "exhaustive_set",
        "exclusive_and_exhaustive_partition",
    }:
        proposal = replace(
            proposal,
            propositions=tuple(sorted(proposal.propositions, key=lambda item: item.input_id)),
        )
    return hashlib.sha256(stable_json_bytes(proposal)).hexdigest()


def _malformed(attempt: RecordedAttempt, reason: str) -> MalformedAttemptRecord:
    return MalformedAttemptRecord(
        attempt.attempt_index,
        attempt.artifact_id,
        attempt.artifact_sha256,
        attempt.input_sha256,
        attempt.output_sha256,
        reason,
    )


def _proposal_prefilters(
    proposal: DiscoveryProposal, request: DiscoveryRequest, policy: PrefilterPolicy
) -> tuple[PrefilterEvaluation, ...]:
    by_id = {item.input_id: item for item in request.inputs}
    if len(proposal.propositions) < 2:
        return ()
    first = by_id[proposal.propositions[0].input_id]
    return tuple(
        evaluate_prefilters(first, by_id[item.input_id], policy)
        for item in proposal.propositions[1:]
    )


def _process_proposals(
    proposals: tuple[DiscoveryProposal, ...],
    request: DiscoveryRequest,
    config: DiscoveryConfig,
) -> tuple[
    tuple[MappedProposal, ...],
    tuple[ProposalRejectionRecord, ...],
    tuple[PrefilterEvaluation, ...],
]:
    mapped: list[MappedProposal] = []
    rejected: list[ProposalRejectionRecord] = []
    prefilters: list[PrefilterEvaluation] = []
    seen: dict[str, str] = {}
    for proposal in proposals:
        fingerprint = _fingerprint(proposal)
        if fingerprint in seen:
            rejected.append(
                ProposalRejectionRecord(
                    proposal.proposal_id,
                    ProposalDisposition.DUPLICATE,
                    "duplicate canonical proposal fingerprint",
                    fingerprint,
                    seen[fingerprint],
                )
            )
            continue
        seen[fingerprint] = proposal.proposal_id
        try:
            evaluations = _proposal_prefilters(proposal, request, config.prefilter_policy)
            prefilters.extend(evaluations)
            if any(not evaluation.required_passed for evaluation in evaluations):
                raise ProposalMappingError("required deterministic prefilter did not pass")
            mapped.append(map_proposal(proposal, request))
        except (KeyError, ProposalMappingError, DomainError) as exc:
            rejected.append(
                ProposalRejectionRecord(
                    proposal.proposal_id,
                    ProposalDisposition.INVALID,
                    str(exc),
                    fingerprint,
                )
            )
    return tuple(mapped), tuple(rejected), tuple(prefilters)


def discover(
    request: DiscoveryRequest, source: RecordedResponseSource, config: DiscoveryConfig
) -> DiscoveryResult:
    """Run only the bounded local recorded attempts supplied by ``source``."""

    if not config.enabled:
        return DiscoveryResult(DiscoveryDisposition.DISABLED, (), ())
    recorded = source.read_attempts()[: config.max_attempts]
    attempts: list[RecordedAttempt] = []
    malformed: list[MalformedAttemptRecord] = []
    for attempt in recorded:
        attempts.append(attempt)
        try:
            if attempt.input_schema_version != DISCOVERY_INPUT_SCHEMA_VERSION:
                raise DiscoveryParseError("unsupported recorded input schema version")
            if attempt.output_schema_version != DISCOVERY_OUTPUT_SCHEMA_VERSION:
                raise DiscoveryParseError("unsupported recorded output schema version")
            if attempt.fixture_schema_version != DISCOVERY_FIXTURE_SCHEMA_VERSION:
                raise DiscoveryParseError("unsupported recorded fixture schema version")
            parsed_request = parse_discovery_request(attempt.input_bytes)
            if parsed_request != request:
                raise DiscoveryParseError("recorded discovery input differs from supplied request")
            required_raw_refs = request_provenance_closure(parsed_request)
            if not required_raw_refs or attempt.source_raw_refs != required_raw_refs:
                raise DiscoveryParseError("recorded source provenance does not close over request")
            output = parse_discovery_output(attempt.output_bytes)
        except DiscoveryParseError as exc:
            malformed.append(_malformed(attempt, str(exc)))
            continue
        if output.outcome is DiscoveryOutcome.ABSTAIN:
            return DiscoveryResult(
                DiscoveryDisposition.ABSTAINED,
                tuple(attempts),
                tuple(malformed),
                parsed_outputs=(output,),
                terminal_reason=output.reason,
            )
        if output.outcome is DiscoveryOutcome.REJECT:
            return DiscoveryResult(
                DiscoveryDisposition.REJECTED,
                tuple(attempts),
                tuple(malformed),
                parsed_outputs=(output,),
                terminal_reason=output.reason,
            )
        mapped, rejected, prefilters = _process_proposals(output.proposals, request, config)
        return DiscoveryResult(
            DiscoveryDisposition.PROPOSALS,
            tuple(attempts),
            tuple(malformed),
            tuple(item.candidate for item in mapped),
            tuple(item.draft for item in mapped),
            rejected,
            prefilters,
            (output,),
        )
    return DiscoveryResult(
        DiscoveryDisposition.RETRY_EXHAUSTED,
        tuple(attempts),
        tuple(malformed),
        terminal_reason="recorded discovery retry bound exhausted without a valid terminal output",
    )


__all__ = [
    "DiscoveryConfig",
    "DiscoveryResult",
    "MalformedAttemptRecord",
    "ProposalDisposition",
    "ProposalRejectionRecord",
    "discover",
]
