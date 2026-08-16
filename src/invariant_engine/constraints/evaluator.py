"""Deterministic, non-actionable interval evaluation."""

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from invariant_engine.constraints.compiler import constraint_identity_matches
from invariant_engine.constraints.models import (
    EVALUATION_SCHEMA_VERSION,
    ClaimBindingIdentity,
    CompiledPricingConstraint,
    ConstraintEvaluation,
    ConstraintEvaluationStatus,
    ConstraintRelation,
    EvaluationFailure,
    EvaluationFailureCode,
    EvaluationId,
    EvaluationResult,
    QuoteObservation,
    TrustedCompiledPricingConstraint,
    is_trusted_constraint,
    is_trusted_observation,
    observation_identity_content,
)
from invariant_engine.domain.decimal_policy import parse_price
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.relationships.ids import ClaimBindingId
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiPriceConvention,
    KalshiTimestampSource,
)
from invariant_engine.venues.polymarket import POLYMARKET_DIRECT_SCHEMA_VERSION


def _failure(
    code: EvaluationFailureCode,
    message: str,
    binding_id: ClaimBindingId | None = None,
) -> EvaluationFailure:
    return EvaluationFailure(code, message, binding_id)


def _ordered_unique(values: Iterable[RawReference]) -> tuple[RawReference, ...]:
    result: list[RawReference] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _identity_matches(observation: QuoteObservation, identity: ClaimBindingIdentity) -> bool:
    return (
        observation.proposition_id == identity.proposition_id
        and observation.claim_binding_id == identity.claim_binding_id
        and observation.venue is identity.venue
        and observation.market == identity.market
        and observation.contract == identity.contract
        and observation.native_claim_side == (identity.native_side or identity.native_outcome_side)
    )


def _instant(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _observation_identity_matches(observation: QuoteObservation) -> bool:
    try:
        if not is_trusted_observation(observation):
            return False
        if observation.schema_version != "quote-observation-v1":
            return False
        if observation.timestamp.tzinfo is None or observation.timestamp.utcoffset() is None:
            return False
        if observation.timestamp_source is not None and not isinstance(
            observation.timestamp_source, str
        ):
            return False
        if not isinstance(observation.source_snapshot_schema_version, str):
            return False
        if observation.source_price_convention is not None and not isinstance(
            observation.source_price_convention, str
        ):
            return False
        if not isinstance(observation.validity, StateValidity):
            return False
        if not isinstance(observation.raw_refs, tuple) or not observation.raw_refs:
            return False
        if any(
            not isinstance(raw_ref, RawReference) or raw_ref.venue is not observation.venue
            for raw_ref in observation.raw_refs
        ):
            return False
        if len(set(observation.raw_refs)) != len(observation.raw_refs):
            return False
        if not isinstance(observation.warnings, tuple):
            return False
        if any(
            not isinstance(warning, WarningRecord)
            or not isinstance(warning.code, WarningCode)
            or not isinstance(warning.message, str)
            or (warning.field is not None and not isinstance(warning.field, str))
            for warning in observation.warnings
        ):
            return False
        stable_content = stable_json_bytes(observation_identity_content(observation))
        expected = "observation:" + hashlib.sha256(stable_content).hexdigest()
        return observation.observation_id == expected
    except (AttributeError, DomainError, TypeError, ValueError):
        return False


def _make_evaluation(
    *,
    constraint: CompiledPricingConstraint,
    status: ConstraintEvaluationStatus,
    minimum_lhs: Decimal | None,
    maximum_lhs: Decimal | None,
    common_timestamp: datetime | None,
    observations: tuple[QuoteObservation, ...],
    failures: tuple[EvaluationFailure, ...],
    warnings: tuple[WarningRecord, ...],
) -> ConstraintEvaluation:
    certificate_provenance = constraint.certificate_provenance
    observation_provenance = tuple(
        raw_ref for observation in observations for raw_ref in observation.raw_refs
    )
    combined_provenance = _ordered_unique((*certificate_provenance, *observation_provenance))
    participating_observations = tuple(item.observation_id for item in observations)
    participating_bindings = tuple(item.claim_binding_id for item in observations)
    canonical = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "constraint_id": constraint.constraint_id,
        "certificate_id": constraint.certificate_id,
        "status": status,
        "minimum_lhs": minimum_lhs,
        "maximum_lhs": maximum_lhs,
        "relation": constraint.relation,
        "bound": constraint.bound,
        "common_timestamp": common_timestamp,
        "participating_observations": participating_observations,
        "participating_bindings": participating_bindings,
        "certificate_provenance": certificate_provenance,
        "observation_provenance": observation_provenance,
        "combined_provenance": combined_provenance,
        "failures": failures,
        "warnings": warnings,
    }
    evaluation_id = EvaluationId(
        "evaluation:" + hashlib.sha256(stable_json_bytes(canonical)).hexdigest()
    )
    return ConstraintEvaluation(
        schema_version=EVALUATION_SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        constraint_id=constraint.constraint_id,
        certificate_id=constraint.certificate_id,
        status=status,
        minimum_lhs=minimum_lhs,
        maximum_lhs=maximum_lhs,
        relation=constraint.relation,
        bound=constraint.bound,
        common_timestamp=common_timestamp,
        participating_observations=participating_observations,
        participating_bindings=participating_bindings,
        certificate_provenance=certificate_provenance,
        observation_provenance=observation_provenance,
        combined_provenance=combined_provenance,
        failures=failures,
        warnings=warnings,
    )


def _unavailable(
    constraint: CompiledPricingConstraint,
    failures: tuple[EvaluationFailure, ...],
    observations: tuple[QuoteObservation, ...] = (),
    warnings: tuple[WarningRecord, ...] = (),
) -> EvaluationResult:
    evaluation = _make_evaluation(
        constraint=constraint,
        status=ConstraintEvaluationStatus.UNAVAILABLE,
        minimum_lhs=None,
        maximum_lhs=None,
        common_timestamp=None,
        observations=observations,
        failures=failures,
        warnings=warnings,
    )
    return EvaluationResult(evaluation, failures)


def _evaluate_constraint(
    constraint: TrustedCompiledPricingConstraint,
    observations: Iterable[QuoteObservation],
) -> EvaluationResult:
    """Evaluate one compiled constraint over exactly its claim-aligned intervals."""

    if not is_trusted_constraint(constraint) or not constraint_identity_matches(constraint):
        return EvaluationResult(
            None,
            (
                _failure(
                    EvaluationFailureCode.INVALID_CONSTRAINT,
                    "evaluation requires an intact compiler-produced constraint",
                ),
            ),
        )
    try:
        input_observations = tuple(observations)
    except TypeError:
        return _unavailable(
            constraint,
            (
                _failure(
                    EvaluationFailureCode.WRONG_TYPE,
                    "observations must be iterable QuoteObservation values",
                ),
            ),
        )
    failures: list[EvaluationFailure] = []
    by_binding: dict[ClaimBindingId, QuoteObservation] = {}
    for item in input_observations:
        if not is_trusted_observation(item) or not _observation_identity_matches(item):
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "each observation must be an intact venue-boundary observation",
                )
            )
            continue
        if item.claim_binding_id in by_binding:
            failures.append(
                _failure(
                    EvaluationFailureCode.DUPLICATE_OBSERVATION,
                    "duplicate observation for one claim binding",
                    item.claim_binding_id,
                )
            )
        else:
            by_binding[item.claim_binding_id] = item
    identities = {identity.claim_binding_id: identity for identity in constraint.binding_identities}
    expected_bindings = tuple(term.claim_binding_id for term in constraint.terms)
    expected_set = set(expected_bindings)
    for binding_id in expected_bindings:
        if binding_id not in by_binding:
            failures.append(
                _failure(
                    EvaluationFailureCode.MISSING_OBSERVATION,
                    "one required claim binding has no observation",
                    binding_id,
                )
            )
    for item in input_observations:
        if isinstance(item, QuoteObservation) and item.claim_binding_id not in expected_set:
            binding_id = item.claim_binding_id
            failures.append(
                _failure(
                    EvaluationFailureCode.UNEXPECTED_OBSERVATION,
                    "observation is not a term of the compiled constraint",
                    binding_id,
                )
            )

    ordered: list[QuoteObservation] = []
    for binding_id in expected_bindings:
        observation = by_binding.get(binding_id)
        if observation is None:
            continue
        ordered.append(observation)
        identity = identities.get(binding_id)
        if identity is None or not _identity_matches(observation, identity):
            failures.append(
                _failure(
                    EvaluationFailureCode.IDENTITY_MISMATCH,
                    "observation does not exactly match the certified binding identity",
                    binding_id,
                )
            )
        if not observation.raw_refs or any(
            not isinstance(item, RawReference) or item.venue is not observation.venue
            for item in observation.raw_refs
        ):
            failures.append(
                _failure(
                    EvaluationFailureCode.MISSING_PROVENANCE,
                    "observation requires ordered raw provenance",
                    binding_id,
                )
            )
        elif len(set(observation.raw_refs)) != len(observation.raw_refs):
            failures.append(
                _failure(
                    EvaluationFailureCode.MISSING_PROVENANCE,
                    "observation raw provenance must retain a unique ordered lineage",
                    binding_id,
                )
            )
        if observation.venue is Venue.POLYMARKET and (
            observation.source_snapshot_schema_version != POLYMARKET_DIRECT_SCHEMA_VERSION
            or observation.source_price_convention is not None
        ):
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "Polymarket observation schema or convention metadata is unsupported",
                    binding_id,
                )
            )
        if observation.venue is Venue.KALSHI and (
            observation.source_snapshot_schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION
            or observation.source_price_convention
            not in {item.value for item in KalshiPriceConvention}
        ):
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "Kalshi observation schema or convention metadata is unsupported",
                    binding_id,
                )
            )
        if observation.validity is not StateValidity.VALID:
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "observation replay state is invalid",
                    binding_id,
                )
            )
        if any(warning.code is WarningCode.STALE_SNAPSHOT for warning in observation.warnings):
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "observation is explicitly stale",
                    binding_id,
                )
            )
        if observation.venue is Venue.KALSHI and observation.timestamp_source in {
            KalshiTimestampSource.CAPTURE_FALLBACK.value,
            KalshiTimestampSource.CAPTURE_FALLBACK,
        }:
            failures.append(
                _failure(
                    EvaluationFailureCode.UNAVAILABLE_TIMESTAMP,
                    "capture fallback is not an exact participating observation timestamp",
                    binding_id,
                )
            )
        try:
            bid = parse_price(observation.best_bid, field="best_bid")
            ask = parse_price(observation.best_ask, field="best_ask")
            if bid > ask:
                failures.append(
                    _failure(
                        EvaluationFailureCode.INVALID_OBSERVATION,
                        "observation quote interval is crossed",
                        binding_id,
                    )
                )
        except (DomainError, TypeError):
            failures.append(
                _failure(
                    EvaluationFailureCode.INVALID_OBSERVATION,
                    "observation requires finite bid and ask prices in [0, 1]",
                    binding_id,
                )
            )

    if failures:
        return _unavailable(
            constraint,
            tuple(failures),
            tuple(ordered),
            tuple(warning for item in ordered for warning in item.warnings),
        )

    timestamps = tuple(_instant(item.timestamp) for item in ordered)
    if not timestamps:
        return _unavailable(
            constraint,
            (
                _failure(
                    EvaluationFailureCode.MISSING_OBSERVATION,
                    "constraint has no participating observations",
                ),
            ),
        )
    if any(timestamp != timestamps[0] for timestamp in timestamps[1:]):
        return _unavailable(
            constraint,
            (
                _failure(
                    EvaluationFailureCode.UNSYNCHRONIZED,
                    "all participating observation instants must be exactly equal",
                ),
            ),
            tuple(ordered),
            tuple(warning for item in ordered for warning in item.warnings),
        )

    minimum = Decimal("0")
    maximum = Decimal("0")
    for term, observation in zip(constraint.terms, ordered, strict=True):
        bid = parse_price(observation.best_bid, field="best_bid")
        ask = parse_price(observation.best_ask, field="best_ask")
        if term.coefficient >= 0:
            minimum += term.coefficient * bid
            maximum += term.coefficient * ask
        else:
            minimum += term.coefficient * ask
            maximum += term.coefficient * bid

    if constraint.relation is ConstraintRelation.LESS_THAN_OR_EQUAL:
        if maximum <= constraint.bound:
            status = ConstraintEvaluationStatus.SATISFIED
        elif minimum > constraint.bound:
            status = ConstraintEvaluationStatus.VIOLATED
        else:
            status = ConstraintEvaluationStatus.INDETERMINATE
    elif constraint.relation is ConstraintRelation.GREATER_THAN_OR_EQUAL:
        if minimum >= constraint.bound:
            status = ConstraintEvaluationStatus.SATISFIED
        elif maximum < constraint.bound:
            status = ConstraintEvaluationStatus.VIOLATED
        else:
            status = ConstraintEvaluationStatus.INDETERMINATE
    elif minimum == maximum == constraint.bound:
        status = ConstraintEvaluationStatus.SATISFIED
    elif constraint.bound < minimum or constraint.bound > maximum:
        status = ConstraintEvaluationStatus.VIOLATED
    else:
        status = ConstraintEvaluationStatus.INDETERMINATE
    warnings = tuple(warning for item in ordered for warning in item.warnings)
    evaluation = _make_evaluation(
        constraint=constraint,
        status=status,
        minimum_lhs=minimum,
        maximum_lhs=maximum,
        common_timestamp=timestamps[0],
        observations=tuple(ordered),
        failures=(),
        warnings=warnings,
    )
    return EvaluationResult(evaluation)


def evaluate_constraint(
    constraint: TrustedCompiledPricingConstraint,
    observations: Iterable[QuoteObservation],
) -> EvaluationResult:
    """Evaluate and convert all data-triggered exceptions to structured failure."""

    try:
        return _evaluate_constraint(constraint, observations)
    except Exception:
        try:
            intact_constraint = is_trusted_constraint(constraint) and constraint_identity_matches(
                constraint
            )
        except Exception:
            intact_constraint = False
        if intact_constraint:
            try:
                return _unavailable(
                    constraint,
                    (
                        _failure(
                            EvaluationFailureCode.INVALID_OBSERVATION,
                            "evaluation input could not be represented deterministically",
                        ),
                    ),
                )
            except Exception:
                pass
        return EvaluationResult(
            None,
            (
                _failure(
                    EvaluationFailureCode.INVALID_CONSTRAINT,
                    "evaluation could not be represented deterministically",
                ),
            ),
        )


evaluate = evaluate_constraint

__all__ = ["evaluate_constraint", "evaluate"]
