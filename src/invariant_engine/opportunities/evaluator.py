"""Deterministic, non-actionable economics for one historical violation."""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from invariant_engine.constraints import (
    ConstraintEvaluationStatus,
    compile_certificate,
    evaluate_constraint,
    is_trusted_constraint,
    observe_kalshi,
    observe_polymarket,
)
from invariant_engine.constraints.compiler import constraint_identity_matches
from invariant_engine.constraints.models import (
    QuoteObservation,
    TrustedCompiledPricingConstraint,
    constraint_identity_content,
)
from invariant_engine.domain.decimal_policy import parse_decimal, parse_quantity
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.domain.order_book import BookSide, BookSideKind, PriceLevel
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.opportunities.models import (
    _CANDIDATE_TRUST_TOKEN,
    OPPORTUNITY_SCHEMA_VERSION,
    DecimalInterval,
    DepthSlice,
    FeeCalculationScope,
    FeeFormulaKind,
    FeePolicy,
    FeePolicyAssignment,
    FeeRole,
    FeeRoundingScope,
    FeeTradeSide,
    LegEconomics,
    OpportunityCandidate,
    OpportunityEconomicsEvaluation,
    OpportunityEconomicsResult,
    OpportunityEconomicsStatus,
    OpportunityReason,
    OpportunityReasonCode,
    ResidualFailureScenario,
    ResidualFailureState,
    StateEconomics,
)
from invariant_engine.relationships.candidates import RelationshipType
from invariant_engine.relationships.certificates import RelationshipCertificate
from invariant_engine.relationships.claims import (
    ClaimBinding,
    KalshiClaimBinding,
    PolymarketClaimBinding,
)
from invariant_engine.relationships.ids import ClaimBindingId
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiNativeBookSide,
    KalshiNativeSideKind,
    KalshiOrderBookSnapshot,
)
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
    PolymarketOrderBookSnapshot,
)


def _reason(
    code: OpportunityReasonCode,
    message: str,
    binding_id: ClaimBindingId | None = None,
    state_id: str | None = None,
) -> OpportunityReason:
    return OpportunityReason(code, message, binding_id, state_id)


def _unique_refs(values: Iterable[RawReference]) -> tuple[RawReference, ...]:
    result: list[RawReference] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _evaluation_id(fields: dict[str, object]) -> str:
    return "opportunity-evaluation:" + hashlib.sha256(stable_json_bytes(fields)).hexdigest()


def _make_evaluation(
    *,
    status: OpportunityEconomicsStatus,
    certificate_id: object | None = None,
    constraint_id: object | None = None,
    fresh_constraint_evaluation_id: object | None = None,
    certificate_material: object | None = None,
    supplied_constraint_material: object | None = None,
    reconstructed_constraint_material: object | None = None,
    fresh_constraint_evaluation_material: object | None = None,
    relationship_type: RelationshipType | None = None,
    quantity: Decimal | None = None,
    common_timestamp: object | None = None,
    currency: str | None = None,
    legs: tuple[LegEconomics, ...] = (),
    total_purchase_cost: Decimal | None = None,
    total_fee_interval: DecimalInterval | None = None,
    state_results: tuple[StateEconomics, ...] = (),
    aggregate_gross_edge: DecimalInterval | None = None,
    aggregate_net_edge: DecimalInterval | None = None,
    residual_failures: tuple[ResidualFailureScenario, ...] = (),
    certificate_provenance: tuple[RawReference, ...] = (),
    observation_provenance: tuple[RawReference, ...] = (),
    fee_provenance: tuple[RawReference, ...] = (),
    combined_provenance: tuple[RawReference, ...] = (),
    warnings: tuple[object, ...] = (),
    reasons: tuple[OpportunityReason, ...] = (),
) -> OpportunityEconomicsEvaluation:
    fields = {
        "schema_version": OPPORTUNITY_SCHEMA_VERSION,
        "status": status,
        "certificate_id": certificate_id,
        "constraint_id": constraint_id,
        "fresh_constraint_evaluation_id": fresh_constraint_evaluation_id,
        "certificate_material": certificate_material,
        "supplied_constraint_material": supplied_constraint_material,
        "reconstructed_constraint_material": reconstructed_constraint_material,
        "fresh_constraint_evaluation_material": fresh_constraint_evaluation_material,
        "relationship_type": relationship_type,
        "quantity": quantity,
        "common_timestamp": common_timestamp,
        "currency": currency,
        "legs": legs,
        "total_purchase_cost": total_purchase_cost,
        "total_fee_interval": total_fee_interval,
        "state_results": state_results,
        "aggregate_gross_edge": aggregate_gross_edge,
        "aggregate_net_edge": aggregate_net_edge,
        "residual_failures": residual_failures,
        "certificate_provenance": certificate_provenance,
        "observation_provenance": observation_provenance,
        "fee_provenance": fee_provenance,
        "combined_provenance": combined_provenance,
        "warnings": warnings,
        "reasons": reasons,
    }
    return OpportunityEconomicsEvaluation(
        schema_version=OPPORTUNITY_SCHEMA_VERSION,
        evaluation_id=_evaluation_id(fields),
        status=status,
        certificate_id=certificate_id,  # type: ignore[arg-type]
        constraint_id=constraint_id,
        fresh_constraint_evaluation_id=fresh_constraint_evaluation_id,
        certificate_material=certificate_material,
        supplied_constraint_material=supplied_constraint_material,
        reconstructed_constraint_material=reconstructed_constraint_material,
        fresh_constraint_evaluation_material=fresh_constraint_evaluation_material,
        relationship_type=relationship_type,
        quantity=quantity,
        common_timestamp=common_timestamp,  # type: ignore[arg-type]
        currency=currency,
        legs=legs,
        total_purchase_cost=total_purchase_cost,
        total_fee_interval=total_fee_interval,
        state_results=state_results,
        aggregate_gross_edge=aggregate_gross_edge,
        aggregate_net_edge=aggregate_net_edge,
        residual_failures=residual_failures,
        certificate_provenance=certificate_provenance,
        observation_provenance=observation_provenance,
        fee_provenance=fee_provenance,
        combined_provenance=combined_provenance,
        warnings=warnings,
        reasons=reasons,
    )


def _unavailable(
    *reasons: OpportunityReason,
    certificate_id: object | None = None,
    constraint_id: object | None = None,
    relationship_type: RelationshipType | None = None,
    quantity: Decimal | None = None,
    certificate_provenance: tuple[RawReference, ...] = (),
    warnings: tuple[object, ...] = (),
    **kwargs: Any,
) -> OpportunityEconomicsResult:
    evaluation = _make_evaluation(
        status=OpportunityEconomicsStatus.UNAVAILABLE,
        certificate_id=certificate_id,
        constraint_id=constraint_id,
        relationship_type=relationship_type,
        quantity=quantity,
        certificate_provenance=certificate_provenance,
        warnings=warnings,
        reasons=tuple(reasons),
        **kwargs,
    )
    return OpportunityEconomicsResult(evaluation)


def _same_constraint(supplied: object, reconstructed: TrustedCompiledPricingConstraint) -> bool:
    if type(supplied) is not TrustedCompiledPricingConstraint:
        return False
    if not is_trusted_constraint(supplied) or not constraint_identity_matches(supplied):
        return False
    try:
        return supplied.constraint_id == reconstructed.constraint_id and stable_json_bytes(
            constraint_identity_content(supplied)
        ) == stable_json_bytes(constraint_identity_content(reconstructed))
    except Exception:
        return False


def _normalize_snapshots(value: object) -> tuple[tuple[ClaimBindingId, object], ...]:
    if isinstance(value, Mapping):
        items = tuple(value.items())
    else:
        items = tuple(value)  # type: ignore[arg-type]
    result: list[tuple[ClaimBindingId, object]] = []
    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise DomainError("snapshots must be a binding-to-snapshot mapping")
        binding_id, snapshot = item
        if not isinstance(binding_id, ClaimBindingId):
            raise DomainError("snapshot mapping keys must be ClaimBindingId values")
        if any(existing == binding_id for existing, _ in result):
            raise DomainError("snapshot mapping contains a duplicate binding")
        result.append((binding_id, snapshot))
    return tuple(result)


def _normalize_fee_assignments(value: object) -> tuple[FeePolicyAssignment, ...]:
    if isinstance(value, Mapping):
        items = tuple(
            FeePolicyAssignment(binding_id, policy) for binding_id, policy in value.items()
        )
    else:
        raw_items: tuple[Any, ...] = tuple(value)  # type: ignore[arg-type]
        items = tuple(
            item if isinstance(item, FeePolicyAssignment) else FeePolicyAssignment(item[0], item[1])
            for item in raw_items
        )
    if len({item.claim_binding_id for item in items}) != len(items):
        raise DomainError("fee policy assignments contain duplicate bindings")
    return items


def _fresh_observations(
    certificate: RelationshipCertificate,
    constraint: TrustedCompiledPricingConstraint,
    snapshots: object,
) -> tuple[
    tuple[QuoteObservation, ...],
    tuple[tuple[ClaimBindingId, object], ...],
    tuple[OpportunityReason, ...],
]:
    supplied = dict(_normalize_snapshots(snapshots))
    expected = tuple(term.claim_binding_id for term in constraint.terms)
    expected_set = set(expected)
    reasons: list[OpportunityReason] = []
    for binding_id in supplied:
        if binding_id not in expected_set:
            reasons.append(
                _reason(
                    OpportunityReasonCode.EXTRA_SNAPSHOT,
                    "snapshot is not a required leg",
                    binding_id,
                )
            )
    bindings = {binding.binding_id: binding for binding in certificate.bindings}
    observations: list[QuoteObservation] = []
    ordered_snapshots: list[tuple[ClaimBindingId, object]] = []
    for binding_id in expected:
        snapshot = supplied.get(binding_id)
        if snapshot is None:
            reasons.append(
                _reason(
                    OpportunityReasonCode.MISSING_SNAPSHOT,
                    "required historical snapshot is missing",
                    binding_id,
                )
            )
            continue
        binding = bindings.get(binding_id)
        if binding is None:
            reasons.append(
                _reason(
                    OpportunityReasonCode.INVALID_CONSTRAINT,
                    "constraint binding is absent from certificate",
                    binding_id,
                )
            )
            continue
        try:
            _validate_snapshot_sides(binding, snapshot)
        except Exception as exc:
            reasons.append(_reason(OpportunityReasonCode.INVALID_SNAPSHOT, str(exc), binding_id))
            continue
        if isinstance(binding, PolymarketClaimBinding):
            result = observe_polymarket(binding, snapshot)  # type: ignore[arg-type]
        elif isinstance(binding, KalshiClaimBinding):
            result = observe_kalshi(binding, snapshot)  # type: ignore[arg-type]
        else:
            reasons.append(
                _reason(
                    OpportunityReasonCode.INVALID_SNAPSHOT,
                    "certificate binding type is unsupported",
                    binding_id,
                )
            )
            continue
        if not result.ok or result.observation is None:
            detail = (
                result.failure.message if result.failure is not None else "observation unavailable"
            )
            reasons.append(_reason(OpportunityReasonCode.OBSERVATION_FAILURE, detail, binding_id))
            continue
        observations.append(result.observation)
        ordered_snapshots.append((binding_id, snapshot))
    return tuple(observations), tuple(ordered_snapshots), tuple(reasons)


def _direction_supported(
    constraint: TrustedCompiledPricingConstraint,
    relationship: RelationshipType,
    maximum_lhs: Decimal | None,
) -> bool:
    if maximum_lhs is None:
        return False
    if any(term.coefficient != Decimal("1") for term in constraint.terms):
        return False
    expected = {term.claim_binding_id for term in constraint.terms}
    identities = {identity.claim_binding_id for identity in constraint.binding_identities}
    if expected != identities or len(expected) != len(constraint.terms):
        return False
    if relationship is RelationshipType.COMPLEMENT:
        return (
            constraint.relation.value == "="
            and constraint.bound == Decimal("1")
            and maximum_lhs < constraint.bound
        )
    if relationship is RelationshipType.EXHAUSTIVE_SET:
        return (
            constraint.relation.value == ">="
            and constraint.bound == Decimal("1")
            and maximum_lhs < constraint.bound
        )
    if relationship is RelationshipType.EXCLUSIVE_AND_EXHAUSTIVE_PARTITION:
        return (
            constraint.relation.value == "="
            and constraint.bound == Decimal("1")
            and maximum_lhs < constraint.bound
        )
    return False


def _warning_tuple(value: object, field: str) -> tuple[WarningRecord, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, WarningRecord) for item in value):
        raise DomainError(f"malformed depth: {field} warnings are invalid")
    return value


def _reject_incomplete(warnings: Iterable[WarningRecord]) -> None:
    if any(warning.code is WarningCode.INCOMPLETE_DEPTH for warning in warnings):
        raise DomainError("incomplete historical depth: explicit incomplete-depth warning")


def _validate_price_levels(
    side: BookSide,
    *,
    expected_kind: BookSideKind,
    descending: bool,
    field: str,
) -> None:
    if type(side) is not BookSide:
        raise DomainError(f"malformed depth: {field} must be an exact BookSide")
    if side.kind is not expected_kind:
        raise DomainError(f"malformed depth: {field} kind is invalid")
    if type(side.levels) is not tuple:
        raise DomainError(f"malformed depth: {field} levels must be a tuple")
    _warning_tuple(side.warnings, field)
    prices: list[Decimal] = []
    for level in side.levels:
        if type(level) is not PriceLevel:
            raise DomainError(f"malformed depth: {field} contains a non-PriceLevel record")
        if type(level.price) is not Decimal or not level.price.is_finite():
            raise DomainError(f"malformed depth: {field} price is not finite Decimal data")
        if level.price < Decimal("0") or level.price > Decimal("1"):
            raise DomainError(f"malformed depth: {field} price is outside [0, 1]")
        if type(level.size) is not Decimal or not level.size.is_finite():
            raise DomainError(f"malformed depth: {field} size is not finite Decimal data")
        if level.size <= Decimal("0"):
            raise DomainError(f"malformed depth: {field} size must be strictly positive")
        prices.append(level.price)
    if len(set(prices)) != len(prices):
        raise DomainError(f"malformed depth: {field} contains duplicate prices")
    ordered = tuple(sorted(prices, reverse=descending))
    if tuple(prices) != ordered:
        raise DomainError(f"malformed depth: {field} is not in best-to-worst order")
    try:
        canonical = BookSide.normalized(side.kind, side.levels, warnings=side.warnings)
    except Exception as exc:
        raise DomainError(f"malformed depth: {field} cannot be canonicalized") from exc
    if canonical != side:
        raise DomainError(f"malformed depth: {field} differs from canonical normalized content")


def _validate_native_side(
    side: KalshiNativeBookSide,
    *,
    expected_kind: KalshiNativeSideKind,
    field: str,
) -> None:
    if type(side) is not KalshiNativeBookSide:
        raise DomainError(f"malformed depth: {field} must be an exact KalshiNativeBookSide")
    if side.kind is not expected_kind:
        raise DomainError(f"malformed depth: {field} kind is invalid")
    if type(side.levels) is not tuple:
        raise DomainError(f"malformed depth: {field} levels must be a tuple")
    _warning_tuple(side.warnings, field)
    prices: list[Decimal] = []
    for level in side.levels:
        if type(level) is not PriceLevel:
            raise DomainError(f"malformed depth: {field} contains a non-PriceLevel record")
        if type(level.price) is not Decimal or not level.price.is_finite():
            raise DomainError(f"malformed depth: {field} price is not finite Decimal data")
        if level.price < Decimal("0") or level.price > Decimal("1"):
            raise DomainError(f"malformed depth: {field} price is outside [0, 1]")
        if type(level.size) is not Decimal or not level.size.is_finite():
            raise DomainError(f"malformed depth: {field} size is not finite Decimal data")
        if level.size <= Decimal("0"):
            raise DomainError(f"malformed depth: {field} size must be strictly positive")
        prices.append(level.price)
    if len(set(prices)) != len(prices):
        raise DomainError(f"malformed depth: {field} contains duplicate prices")
    if tuple(prices) != tuple(sorted(prices, reverse=True)):
        raise DomainError(f"malformed depth: {field} is not in best-to-worst order")
    try:
        canonical = KalshiNativeBookSide.normalized(side.kind, side.levels, warnings=side.warnings)
    except Exception as exc:
        raise DomainError(f"malformed depth: {field} cannot be canonicalized") from exc
    if canonical != side:
        raise DomainError(f"malformed depth: {field} differs from canonical content")


def _validate_snapshot_sides(binding: ClaimBinding, snapshot: object) -> None:
    if isinstance(binding, PolymarketClaimBinding):
        if type(snapshot) is not PolymarketOrderBookSnapshot:
            raise DomainError("Polymarket leg requires a PolymarketOrderBookSnapshot")
        if snapshot.schema_version != POLYMARKET_DIRECT_SCHEMA_VERSION:
            raise DomainError("unsupported Polymarket snapshot schema")
        if snapshot.order_book.validity is not StateValidity.VALID:
            raise DomainError("Polymarket snapshot replay state is invalid")
        order_book = snapshot.order_book
        snapshot_warnings = _warning_tuple(order_book.warnings, "Polymarket snapshot")
        _validate_price_levels(
            order_book.bids,
            expected_kind=BookSideKind.BID,
            descending=True,
            field="Polymarket bid side",
        )
        _validate_price_levels(
            order_book.asks,
            expected_kind=BookSideKind.ASK,
            descending=False,
            field="Polymarket ask side",
        )
        bid_warnings = order_book.bids.warnings
        ask_warnings = order_book.asks.warnings
        _reject_incomplete((*snapshot_warnings, *bid_warnings, *ask_warnings))
        return
    if isinstance(binding, KalshiClaimBinding):
        if type(snapshot) is not KalshiOrderBookSnapshot:
            raise DomainError("Kalshi leg requires a KalshiOrderBookSnapshot")
        if snapshot.schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION:
            raise DomainError("unsupported Kalshi snapshot schema")
        if snapshot.validity is not StateValidity.VALID:
            raise DomainError("Kalshi snapshot replay state is invalid")
        snapshot_warnings = _warning_tuple(snapshot.warnings, "Kalshi snapshot")
        _validate_native_side(
            snapshot.yes_side,
            expected_kind=KalshiNativeSideKind.YES,
            field="Kalshi YES native side",
        )
        _validate_native_side(
            snapshot.no_side,
            expected_kind=KalshiNativeSideKind.NO,
            field="Kalshi NO native side",
        )
        yes_warnings = snapshot.yes_side.warnings
        no_warnings = snapshot.no_side.warnings
        _reject_incomplete((*snapshot_warnings, *yes_warnings, *no_warnings))
        return
    raise DomainError("unsupported claim binding")


def _ask_levels(binding: ClaimBinding, snapshot: object) -> Any:
    _validate_snapshot_sides(binding, snapshot)
    if isinstance(binding, PolymarketClaimBinding):
        polymarket_snapshot = cast(PolymarketOrderBookSnapshot, snapshot)
        return polymarket_snapshot.order_book.asks
    if isinstance(binding, KalshiClaimBinding):
        kalshi_snapshot = cast(KalshiOrderBookSnapshot, snapshot)
        if binding.native_side.value == "yes":
            asks = kalshi_snapshot.derived_yes_asks()
            _validate_price_levels(
                asks,
                expected_kind=BookSideKind.YES_ASK,
                descending=False,
                field="derived Kalshi YES ask side",
            )
            return asks
        if binding.native_side.value == "no":
            asks = kalshi_snapshot.derived_no_asks()
            _validate_price_levels(
                asks,
                expected_kind=BookSideKind.NO_ASK,
                descending=False,
                field="derived Kalshi NO ask side",
            )
            return asks
        raise DomainError("unsupported Kalshi native side")
    raise DomainError("unsupported claim binding")


def _walk_depth(
    binding: ClaimBinding, snapshot: object, observation: QuoteObservation, quantity: Decimal
) -> LegEconomics:
    asks = _ask_levels(binding, snapshot)
    snapshot_data: Any = snapshot
    remaining = quantity
    slices: list[DepthSlice] = []
    capacity = Decimal("0")
    for index, level in enumerate(asks.levels):
        capacity += level.size
        if remaining <= 0:
            continue
        taken = min(remaining, level.size)
        slices.append(DepthSlice(index, taken, level.price, taken * level.price))
        remaining -= taken
    if remaining > 0:
        raise _InsufficientDepth(capacity)
    total_cost = sum((item.cost for item in slices), Decimal("0"))
    if quantity <= 0 or total_cost < 0:
        raise DomainError("depth calculation produced an invalid cost")
    if isinstance(binding, PolymarketClaimBinding):
        venue = Venue.POLYMARKET
        market: object = binding.market
        contract = binding.outcome_token
        snapshot_schema_version = snapshot_data.schema_version
        snapshot_price_convention = None
    else:
        venue = Venue.KALSHI
        market = binding.market
        contract = None
        snapshot_schema_version = snapshot_data.schema_version
        snapshot_price_convention = snapshot_data.price_convention.value
    return LegEconomics(
        claim_binding_id=binding.binding_id,
        proposition_id=binding.proposition_id,
        venue=venue,
        market=market,
        contract=contract,
        native_claim_side=(
            observation.native_claim_side if hasattr(observation, "native_claim_side") else None
        ),
        snapshot_identity="snapshot:" + hashlib.sha256(stable_json_bytes(snapshot)).hexdigest(),
        snapshot_schema_version=snapshot_schema_version,
        snapshot_price_convention=snapshot_price_convention,
        observation_id=observation.observation_id,
        timestamp=observation.timestamp,
        raw_refs=observation.raw_refs,
        required_quantity=quantity,
        observed_ask_capacity=capacity,
        depth_slices=tuple(slices),
        total_purchase_cost=total_cost,
        vwap=total_cost / quantity,
    )


class _InsufficientDepth(Exception):
    def __init__(self, capacity: Decimal) -> None:
        super().__init__("observed ask depth is insufficient")
        self.capacity = capacity


def _validated_policy(policy: FeePolicy) -> FeePolicy:
    if type(policy) is not FeePolicy:
        raise DomainError("fee policy must be an exact FeePolicy")
    return FeePolicy(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        venue=policy.venue,
        effective_start=policy.effective_start,
        effective_end=policy.effective_end,
        start_inclusive=policy.start_inclusive,
        end_inclusive=policy.end_inclusive,
        role=policy.role,
        trade_side=policy.trade_side,
        formula_kind=policy.formula_kind,
        formula_parameters=policy.formula_parameters,
        calculation_scope=policy.calculation_scope,
        rounding_scope=policy.rounding_scope,
        rounding_mode=policy.rounding_mode,
        currency=policy.currency,
        rounding_quantum=policy.rounding_quantum,
        provenance=policy.provenance,
    )


def _round(policy: FeePolicy, value: Decimal) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value < Decimal("0"):
        raise DomainError("rounded fee component must be finite and non-negative Decimal data")
    quantum = policy.rounding_quantum
    if type(quantum) is not Decimal or not quantum.is_finite() or quantum <= Decimal("0"):
        raise DomainError("rounding quantum must be a finite positive Decimal")
    try:
        units = (value / quantum).to_integral_value(rounding=policy.rounding_mode)
        rounded = units * quantum
    except Exception as exc:
        raise DomainError("fee component could not be rounded to quantum multiples") from exc
    if not rounded.is_finite() or rounded < Decimal("0"):
        raise DomainError("rounded fee component is invalid")
    return rounded


def _formula_interval(policy: FeePolicy, quantity: Decimal, price: Decimal) -> DecimalInterval:
    parameters = dict(policy.formula_parameters)
    if policy.formula_kind is FeeFormulaKind.ZERO:
        return DecimalInterval(Decimal("0"), Decimal("0"))
    if policy.formula_kind is FeeFormulaKind.FLAT_PER_CONTRACT:
        amount = parameters["amount"]
        return DecimalInterval(quantity * amount.lower, quantity * amount.upper)
    rate = parameters["rate"]
    multiplier = price * (Decimal("1") - price)
    return DecimalInterval(quantity * rate.lower * multiplier, quantity * rate.upper * multiplier)


def _fee_interval(policy: FeePolicy, leg: LegEconomics) -> DecimalInterval:
    components: tuple[DecimalInterval, ...]
    if policy.calculation_scope is FeeCalculationScope.PER_DEPTH_SLICE:
        components = tuple(
            _formula_interval(policy, item.quantity, item.price) for item in leg.depth_slices
        )
    elif policy.calculation_scope is FeeCalculationScope.PER_LEG_AGGREGATE:
        components = (_formula_interval(policy, leg.required_quantity, leg.vwap),)
    else:
        raise DomainError("unsupported fee calculation scope")
    if policy.rounding_scope is FeeRoundingScope.EACH_CALCULATION_COMPONENT:
        rounded_components = tuple(
            DecimalInterval(_round(policy, item.lower), _round(policy, item.upper))
            for item in components
        )
        return DecimalInterval(
            sum((item.lower for item in rounded_components), Decimal("0")),
            sum((item.upper for item in rounded_components), Decimal("0")),
        )
    if policy.rounding_scope is FeeRoundingScope.LEG_TOTAL:
        raw = DecimalInterval(
            sum((item.lower for item in components), Decimal("0")),
            sum((item.upper for item in components), Decimal("0")),
        )
        rounded = DecimalInterval(_round(policy, raw.lower), _round(policy, raw.upper))
        return rounded
    raise DomainError("unsupported fee rounding scope")


def _attach_policies(
    legs: tuple[LegEconomics, ...],
    assignments: object,
    timestamp: datetime | None,
) -> tuple[tuple[LegEconomics, ...], tuple[RawReference, ...], str, tuple[OpportunityReason, ...]]:
    policies = _normalize_fee_assignments(assignments)
    by_binding = {item.claim_binding_id: item.policy for item in policies}
    expected = {leg.claim_binding_id for leg in legs}
    reasons: list[OpportunityReason] = []
    if set(by_binding) != expected:
        for binding_id in sorted(expected - set(by_binding), key=lambda item: item.value):
            reasons.append(
                _reason(
                    OpportunityReasonCode.MISSING_FEE_POLICY,
                    "no fee policy is assigned to the required leg",
                    binding_id,
                )
            )
        for binding_id in sorted(set(by_binding) - expected, key=lambda item: item.value):
            reasons.append(
                _reason(
                    OpportunityReasonCode.EXTRA_SNAPSHOT,
                    "fee policy assignment is not a required leg",
                    binding_id,
                )
            )
    validated: dict[ClaimBindingId, FeePolicy] = {}
    for leg in legs:
        policy = by_binding.get(leg.claim_binding_id)
        if policy is None:
            continue
        try:
            policy = _validated_policy(policy)
        except Exception as exc:
            reasons.append(
                _reason(OpportunityReasonCode.INVALID_FEE_POLICY, str(exc), leg.claim_binding_id)
            )
            continue
        if policy.venue is not leg.venue:
            reasons.append(
                _reason(
                    OpportunityReasonCode.INVALID_FEE_POLICY,
                    "fee policy venue does not match leg venue",
                    leg.claim_binding_id,
                )
            )
        elif policy.role is not FeeRole.TAKER or policy.trade_side is not FeeTradeSide.BUY:
            reasons.append(
                _reason(
                    OpportunityReasonCode.INVALID_FEE_POLICY,
                    "fee policy must explicitly cover taker buy ask consumption",
                    leg.claim_binding_id,
                )
            )
        elif timestamp is None or not policy.applies_at(timestamp):
            reasons.append(
                _reason(
                    OpportunityReasonCode.INEFFECTIVE_FEE_POLICY,
                    "fee policy effective interval does not contain the snapshot instant",
                    leg.claim_binding_id,
                )
            )
        else:
            validated[leg.claim_binding_id] = policy
    currencies = {policy.currency for policy in validated.values()}
    if len(currencies) > 1:
        reasons.append(
            _reason(
                OpportunityReasonCode.CURRENCY_INCOMPATIBLE,
                "required fee policies use incompatible currencies",
            )
        )
    if reasons:
        return legs, (), "", tuple(reasons)
    if len(validated) != len(legs):
        return legs, (), "", tuple(reasons)
    currency = next(iter(currencies))
    updated: list[LegEconomics] = []
    provenance: list[RawReference] = []
    for leg in legs:
        policy = validated[leg.claim_binding_id]
        interval = _fee_interval(policy, leg)
        updated.append(
            replace(
                leg,
                fee_policy_id=policy.policy_id,
                fee_policy=policy,
                fee_policy_provenance=policy.provenance,
                fee_interval=interval,
            )
        )
        provenance.extend(policy.provenance)
    return tuple(updated), _unique_refs(provenance), currency, ()


def _state_results(
    certificate: RelationshipCertificate,
    legs: tuple[LegEconomics, ...],
    quantity: Decimal,
    total_cost: Decimal,
    total_fees: DecimalInterval,
) -> tuple[StateEconomics, ...]:
    result: list[StateEconomics] = []
    for state in certificate.feasible_states:
        payoff = sum(
            (
                quantity
                * parse_decimal(state.payout_assignments[leg.claim_binding_id], field="payout")
                for leg in legs
            ),
            Decimal("0"),
        )
        gross_edge = payoff - total_cost
        result.append(
            StateEconomics(
                state_id=state.state_id.value,
                terminal_kind=state.terminal_kind,
                gross_payoff=payoff,
                gross_edge=gross_edge,
                net_edge_lower=gross_edge - total_fees.upper,
                net_edge_upper=gross_edge - total_fees.lower,
            )
        )
    return tuple(result)


def _residual_failures(
    certificate: RelationshipCertificate,
    legs: tuple[LegEconomics, ...],
    quantity: Decimal,
) -> tuple[ResidualFailureScenario, ...]:
    result: list[ResidualFailureScenario] = []
    for failed in legs:
        successful = tuple(leg for leg in legs if leg.claim_binding_id != failed.claim_binding_id)
        successful_ids = tuple(leg.claim_binding_id for leg in successful)
        purchase_cost = sum((leg.total_purchase_cost for leg in successful), Decimal("0"))
        fee_lower = sum(
            (leg.fee_interval.lower for leg in successful if leg.fee_interval is not None),
            Decimal("0"),
        )
        fee_upper = sum(
            (leg.fee_interval.upper for leg in successful if leg.fee_interval is not None),
            Decimal("0"),
        )
        states: list[ResidualFailureState] = []
        for state in certificate.feasible_states:
            payoff = sum(
                (
                    quantity
                    * parse_decimal(state.payout_assignments[leg.claim_binding_id], field="payout")
                    for leg in successful
                ),
                Decimal("0"),
            )
            gross = payoff - purchase_cost
            states.append(
                ResidualFailureState(
                    state_id=state.state_id.value,
                    terminal_kind=state.terminal_kind,
                    gross_payoff=payoff,
                    gross_pnl=gross,
                    fee_interval=DecimalInterval(fee_lower, fee_upper),
                    net_pnl_lower=gross - fee_upper,
                    net_pnl_upper=gross - fee_lower,
                )
            )
        minimum = min(states, key=lambda item: (item.net_pnl_lower, item.state_id))
        maximum = max(states, key=lambda item: (item.net_pnl_upper, item.state_id))
        result.append(
            ResidualFailureScenario(
                failed_claim_binding_id=failed.claim_binding_id,
                successful_claim_binding_ids=successful_ids,
                states=tuple(states),
                minimum_net_pnl=minimum.net_pnl_lower,
                minimum_state_id=minimum.state_id,
                maximum_net_pnl=maximum.net_pnl_upper,
                maximum_state_id=maximum.state_id,
            )
        )
    return tuple(result)


def evaluate_opportunity(
    certificate: object,
    constraint: object,
    snapshots: object,
    quantity: object,
    fee_policies: object,
    *,
    constraint_evaluation: object | None = None,
) -> OpportunityEconomicsResult:
    """Evaluate one synchronized historical violation from trusted upstream data.

    ``constraint_evaluation`` is intentionally accepted only for compatibility
    with callers carrying upstream diagnostics; it is never consulted as proof.
    Fresh observations and a fresh constraint evaluation are always constructed.
    """

    del constraint_evaluation
    certificate_id = getattr(certificate, "certificate_id", None)
    certificate_provenance = getattr(certificate, "evidence_provenance", ())
    if not isinstance(certificate, RelationshipCertificate):
        return _unavailable(
            _reason(
                OpportunityReasonCode.INVALID_CERTIFICATE,
                "economics requires a validator-produced RelationshipCertificate",
            )
        )
    if not isinstance(certificate_provenance, tuple) or any(
        not isinstance(item, RawReference) for item in certificate_provenance
    ):
        certificate_provenance = ()
    try:
        parsed_quantity = parse_quantity(quantity, field="counterfactual quantity")
        if parsed_quantity <= 0:
            return _unavailable(
                _reason(
                    OpportunityReasonCode.INVALID_QUANTITY,
                    "counterfactual quantity must be positive",
                ),
                certificate_id=certificate_id,
                certificate_provenance=certificate_provenance,
                certificate_material=certificate,
            )
    except Exception:
        return _unavailable(
            _reason(
                OpportunityReasonCode.INVALID_QUANTITY,
                "counterfactual quantity must be an exact Decimal value",
            ),
            certificate_id=certificate_id,
            certificate_provenance=certificate_provenance,
        )

    compiled = compile_certificate(certificate)
    reconstructed = compiled.constraint
    if not compiled.ok or reconstructed is None or not is_trusted_constraint(reconstructed):
        return _unavailable(
            _reason(
                OpportunityReasonCode.INVALID_CERTIFICATE,
                "certificate integrity or deterministic compilation failed",
            ),
            certificate_id=certificate_id,
            quantity=parsed_quantity,
            certificate_provenance=certificate_provenance,
            certificate_material=certificate,
        )
    if not _same_constraint(constraint, reconstructed):
        return _unavailable(
            _reason(
                OpportunityReasonCode.CONSTRAINT_MISMATCH,
                "supplied constraint does not exactly match fresh compiler output",
            ),
            certificate_id=certificate.certificate_id,
            constraint_id=getattr(constraint, "constraint_id", None),
            relationship_type=certificate.proposed_relationship.relationship_type,
            quantity=parsed_quantity,
            certificate_provenance=certificate_provenance,
            certificate_material=certificate,
            supplied_constraint_material=constraint,
            reconstructed_constraint_material=reconstructed,
        )

    material: dict[str, Any] = {
        "certificate_material": certificate,
        "supplied_constraint_material": constraint,
        "reconstructed_constraint_material": reconstructed,
    }

    try:
        observations, ordered_snapshots, snapshot_reasons = _fresh_observations(
            certificate, reconstructed, snapshots
        )
    except Exception as exc:
        return _unavailable(
            _reason(OpportunityReasonCode.INVALID_SNAPSHOT, str(exc)),
            certificate_id=certificate.certificate_id,
            constraint_id=reconstructed.constraint_id,
            relationship_type=reconstructed.relationship_type,
            quantity=parsed_quantity,
            certificate_provenance=certificate_provenance,
            **material,
        )
    if snapshot_reasons:
        return _unavailable(
            *snapshot_reasons,
            certificate_id=certificate.certificate_id,
            constraint_id=reconstructed.constraint_id,
            relationship_type=reconstructed.relationship_type,
            quantity=parsed_quantity,
            certificate_provenance=certificate_provenance,
            **material,
        )
    fresh_result = evaluate_constraint(reconstructed, observations)
    fresh_evaluation = fresh_result.evaluation
    material_with_evaluation: dict[str, Any] = {
        **material,
        "fresh_constraint_evaluation_material": fresh_evaluation,
    }
    if fresh_evaluation is None or fresh_result.status is not ConstraintEvaluationStatus.VIOLATED:
        return _unavailable(
            _reason(
                OpportunityReasonCode.UPSTREAM_NOT_VIOLATED,
                "fresh Milestone 2.3 evaluation did not produce a genuine violation",
            ),
            certificate_id=certificate.certificate_id,
            constraint_id=reconstructed.constraint_id,
            fresh_constraint_evaluation_id=(
                fresh_evaluation.evaluation_id if fresh_evaluation else None
            ),
            relationship_type=reconstructed.relationship_type,
            quantity=parsed_quantity,
            certificate_provenance=certificate_provenance,
            observation_provenance=tuple(ref for item in observations for ref in item.raw_refs),
            combined_provenance=_unique_refs(
                (*certificate_provenance, *(ref for item in observations for ref in item.raw_refs))
            ),
            warnings=(fresh_evaluation.warnings if fresh_evaluation else ()),
            **material_with_evaluation,
        )

    if not _direction_supported(
        reconstructed, reconstructed.relationship_type, fresh_evaluation.maximum_lhs
    ):
        return OpportunityEconomicsResult(
            _make_evaluation(
                status=OpportunityEconomicsStatus.UNSUPPORTED_TRADE_DIRECTION,
                certificate_id=certificate.certificate_id,
                constraint_id=reconstructed.constraint_id,
                fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
                relationship_type=reconstructed.relationship_type,
                quantity=parsed_quantity,
                common_timestamp=fresh_evaluation.common_timestamp,
                warnings=fresh_evaluation.warnings,
                reasons=(
                    _reason(
                        OpportunityReasonCode.UNSUPPORTED_TRADE_DIRECTION,
                        "violation is not an approved buy-only direction",
                    ),
                ),
                certificate_provenance=certificate_provenance,
                observation_provenance=tuple(ref for item in observations for ref in item.raw_refs),
                combined_provenance=_unique_refs(
                    (
                        *certificate_provenance,
                        *(ref for item in observations for ref in item.raw_refs),
                    )
                ),
                **material_with_evaluation,
            )
        )

    observations_by_binding = {
        observation.claim_binding_id: observation for observation in observations
    }
    bindings = {binding.binding_id: binding for binding in certificate.bindings}
    legs: list[LegEconomics] = []
    depth_reasons: list[OpportunityReason] = []
    for binding_id, snapshot in ordered_snapshots:
        try:
            leg = _walk_depth(
                bindings[binding_id], snapshot, observations_by_binding[binding_id], parsed_quantity
            )
            legs.append(leg)
        except _InsufficientDepth as exc:
            depth_reasons.append(
                _reason(
                    OpportunityReasonCode.INSUFFICIENT_DEPTH,
                    f"observed ask capacity {exc.capacity} is below required quantity "
                    f"{parsed_quantity}",
                    binding_id,
                )
            )
        except Exception as exc:
            return _unavailable(
                _reason(OpportunityReasonCode.INVALID_SNAPSHOT, str(exc), binding_id),
                certificate_id=certificate.certificate_id,
                constraint_id=reconstructed.constraint_id,
                fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
                relationship_type=reconstructed.relationship_type,
                quantity=parsed_quantity,
                common_timestamp=fresh_evaluation.common_timestamp,
                certificate_provenance=certificate_provenance,
                warnings=fresh_evaluation.warnings,
            )
    if depth_reasons:
        return OpportunityEconomicsResult(
            _make_evaluation(
                status=OpportunityEconomicsStatus.INSUFFICIENT_DEPTH,
                certificate_id=certificate.certificate_id,
                constraint_id=reconstructed.constraint_id,
                fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
                relationship_type=reconstructed.relationship_type,
                quantity=parsed_quantity,
                common_timestamp=fresh_evaluation.common_timestamp,
                certificate_provenance=certificate_provenance,
                observation_provenance=tuple(ref for item in observations for ref in item.raw_refs),
                combined_provenance=_unique_refs(
                    (
                        *certificate_provenance,
                        *(ref for item in observations for ref in item.raw_refs),
                    )
                ),
                warnings=fresh_evaluation.warnings,
                reasons=tuple(depth_reasons),
                **material_with_evaluation,
            )
        )

    try:
        attached_legs, fee_provenance, currency, fee_reasons = _attach_policies(
            tuple(legs), fee_policies, fresh_evaluation.common_timestamp
        )
    except Exception as exc:
        return _unavailable(
            _reason(OpportunityReasonCode.INVALID_FEE_POLICY, str(exc)),
            certificate_id=certificate.certificate_id,
            constraint_id=reconstructed.constraint_id,
            fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
            relationship_type=reconstructed.relationship_type,
            quantity=parsed_quantity,
            common_timestamp=fresh_evaluation.common_timestamp,
            certificate_provenance=certificate_provenance,
            warnings=fresh_evaluation.warnings,
            **material_with_evaluation,
        )
    if fee_reasons:
        return _unavailable(
            *fee_reasons,
            certificate_id=certificate.certificate_id,
            constraint_id=reconstructed.constraint_id,
            fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
            relationship_type=reconstructed.relationship_type,
            quantity=parsed_quantity,
            common_timestamp=fresh_evaluation.common_timestamp,
            certificate_provenance=certificate_provenance,
            warnings=fresh_evaluation.warnings,
            **material_with_evaluation,
        )

    total_cost = sum((leg.total_purchase_cost for leg in attached_legs), Decimal("0"))
    total_fees = DecimalInterval(
        sum((leg.fee_interval.lower for leg in attached_legs if leg.fee_interval), Decimal("0")),
        sum((leg.fee_interval.upper for leg in attached_legs if leg.fee_interval), Decimal("0")),
    )
    states = _state_results(certificate, attached_legs, parsed_quantity, total_cost, total_fees)
    gross = DecimalInterval(
        min(item.gross_edge for item in states), max(item.gross_edge for item in states)
    )
    net = DecimalInterval(
        min(item.net_edge_lower for item in states), max(item.net_edge_upper for item in states)
    )
    residual = _residual_failures(certificate, attached_legs, parsed_quantity)
    observation_provenance = tuple(ref for item in observations for ref in item.raw_refs)
    combined = _unique_refs((*certificate_provenance, *observation_provenance, *fee_provenance))
    status = (
        OpportunityEconomicsStatus.VALIDATED
        if net.lower > 0
        else OpportunityEconomicsStatus.NO_NET_EDGE
    )
    reasons = (
        ()
        if status is OpportunityEconomicsStatus.VALIDATED
        else (
            _reason(
                OpportunityReasonCode.NO_NET_EDGE, "worst-case net edge is not strictly positive"
            ),
        )
    )
    evaluation = _make_evaluation(
        status=status,
        certificate_id=certificate.certificate_id,
        constraint_id=reconstructed.constraint_id,
        fresh_constraint_evaluation_id=fresh_evaluation.evaluation_id,
        relationship_type=reconstructed.relationship_type,
        quantity=parsed_quantity,
        common_timestamp=fresh_evaluation.common_timestamp,
        currency=currency,
        legs=attached_legs,
        total_purchase_cost=total_cost,
        total_fee_interval=total_fees,
        state_results=states,
        aggregate_gross_edge=gross,
        aggregate_net_edge=net,
        residual_failures=residual,
        certificate_provenance=certificate_provenance,
        observation_provenance=observation_provenance,
        fee_provenance=fee_provenance,
        combined_provenance=combined,
        warnings=fresh_evaluation.warnings,
        reasons=reasons,
        **material_with_evaluation,
    )
    if status is not OpportunityEconomicsStatus.VALIDATED:
        return OpportunityEconomicsResult(evaluation)
    candidate = OpportunityCandidate._from_evaluator(evaluation, token=_CANDIDATE_TRUST_TOKEN)
    return OpportunityEconomicsResult(evaluation, candidate)


evaluate_historical_opportunity = evaluate_opportunity
evaluate_economics = evaluate_opportunity


__all__ = ["evaluate_economics", "evaluate_historical_opportunity", "evaluate_opportunity"]
