"""Venue-native construction of claim-aligned closed quote intervals."""

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from invariant_engine.constraints.models import (
    _OBSERVATION_TRUST_TOKEN,
    OBSERVATION_SCHEMA_VERSION,
    ObservationFailure,
    ObservationFailureCode,
    ObservationResult,
    QuoteObservation,
    TrustedQuoteObservation,
    observation_identity_content,
)
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.relationships.claims import (
    KalshiClaimBinding,
    PolymarketClaimBinding,
    PolymarketOutcomeSide,
)
from invariant_engine.serialization import stable_json_bytes
from invariant_engine.venues.kalshi import (
    KALSHI_ORDERBOOK_SCHEMA_VERSION,
    KalshiOrderBookSnapshot,
    KalshiPriceConvention,
    KalshiTimestampSource,
)
from invariant_engine.venues.polymarket import (
    POLYMARKET_DIRECT_SCHEMA_VERSION,
    PolymarketOrderBookSnapshot,
)


def _failure(code: ObservationFailureCode, message: str) -> ObservationResult:
    return ObservationResult(None, (ObservationFailure(code, message),))


def _warnings_have(warnings: Iterable[WarningRecord], code: WarningCode) -> bool:
    return any(warning.code is code for warning in warnings)


def _valid_lineage(raw_refs: object) -> tuple[RawReference, ...] | None:
    if (
        not isinstance(raw_refs, tuple)
        or not raw_refs
        or any(not isinstance(item, RawReference) for item in raw_refs)
    ):
        return None
    if len(set(raw_refs)) != len(raw_refs):
        return None
    return raw_refs


def _timestamp_failure(timestamp: object) -> ObservationFailure | None:
    if not isinstance(timestamp, datetime):
        return ObservationFailure(
            ObservationFailureCode.UNAVAILABLE_TIMESTAMP,
            "observation timestamp must be a timezone-aware datetime",
        )
    try:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return ObservationFailure(
                ObservationFailureCode.UNAVAILABLE_TIMESTAMP,
                "observation timestamp must have a usable UTC offset",
            )
        normalized = timestamp.astimezone(UTC)
        if normalized.utcoffset() is None:
            return ObservationFailure(
                ObservationFailureCode.UNAVAILABLE_TIMESTAMP,
                "observation timestamp cannot be normalized to UTC",
            )
        normalized.isoformat(timespec="microseconds")
    except Exception:
        return ObservationFailure(
            ObservationFailureCode.UNAVAILABLE_TIMESTAMP,
            "observation timestamp cannot be normalized or serialized",
        )
    return None


def _observation(
    *,
    proposition_id: Any,
    claim_binding_id: Any,
    venue: Venue,
    market: object,
    contract: Any,
    native_claim_side: str | None,
    best_bid: Any,
    best_ask: Any,
    timestamp: Any,
    timestamp_source: str | None,
    source_snapshot_schema_version: str,
    source_price_convention: str | None,
    validity: StateValidity,
    raw_refs: tuple[RawReference, ...],
    warnings: tuple[WarningRecord, ...],
) -> TrustedQuoteObservation:
    timestamp_failure = _timestamp_failure(timestamp)
    if timestamp_failure is not None:
        raise DomainError(timestamp_failure.message)
    base = QuoteObservation(
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observation_id="observation:pending",
        proposition_id=proposition_id,
        claim_binding_id=claim_binding_id,
        venue=venue,
        market=market,
        contract=contract,
        native_claim_side=native_claim_side,
        best_bid=best_bid,
        best_ask=best_ask,
        timestamp=timestamp,
        timestamp_source=timestamp_source,
        source_snapshot_schema_version=source_snapshot_schema_version,
        source_price_convention=source_price_convention,
        validity=validity,
        raw_refs=raw_refs,
        warnings=warnings,
    )
    content = observation_identity_content(base)
    observation_id = "observation:" + hashlib.sha256(stable_json_bytes(content)).hexdigest()
    return TrustedQuoteObservation._from_boundary(
        QuoteObservation(
            schema_version=OBSERVATION_SCHEMA_VERSION,
            observation_id=observation_id,
            proposition_id=base.proposition_id,
            claim_binding_id=base.claim_binding_id,
            venue=base.venue,
            market=base.market,
            contract=base.contract,
            native_claim_side=base.native_claim_side,
            best_bid=base.best_bid,
            best_ask=base.best_ask,
            timestamp=base.timestamp,
            timestamp_source=base.timestamp_source,
            source_snapshot_schema_version=base.source_snapshot_schema_version,
            source_price_convention=base.source_price_convention,
            validity=base.validity,
            raw_refs=base.raw_refs,
            warnings=base.warnings,
        ),
        token=_OBSERVATION_TRUST_TOKEN,
    )


def _validate_interval(best_bid: Any, best_ask: Any) -> ObservationFailure | None:
    if best_bid is None:
        return ObservationFailure(ObservationFailureCode.MISSING_BID, "required bid side is empty")
    if best_ask is None:
        return ObservationFailure(ObservationFailureCode.MISSING_ASK, "required ask side is empty")
    try:
        if best_bid > best_ask:
            return ObservationFailure(
                ObservationFailureCode.CROSSED_INTERVAL,
                "best bid exceeds best ask",
            )
    except TypeError:
        return ObservationFailure(ObservationFailureCode.INVALID_PRICE, "quote prices are invalid")
    return None


def observe_polymarket(
    binding: PolymarketClaimBinding, snapshot: PolymarketOrderBookSnapshot
) -> ObservationResult:
    """Extract the directly published Polymarket bid and ask for one token."""

    if not isinstance(binding, PolymarketClaimBinding) or not isinstance(
        snapshot, PolymarketOrderBookSnapshot
    ):
        return _failure(
            ObservationFailureCode.WRONG_TYPE,
            "Polymarket observation requires matching typed inputs",
        )
    try:
        order_book = snapshot.order_book
        if order_book.venue is not Venue.POLYMARKET:
            return _failure(ObservationFailureCode.WRONG_VENUE, "snapshot is not Polymarket-native")
        if snapshot.schema_version != POLYMARKET_DIRECT_SCHEMA_VERSION:
            return _failure(
                ObservationFailureCode.UNSUPPORTED_SCHEMA, "unsupported Polymarket schema version"
            )
        if order_book.market != binding.market:
            return _failure(
                ObservationFailureCode.MARKET_MISMATCH,
                "Polymarket market identity does not match binding",
            )
        if snapshot.asset != binding.outcome_token:
            return _failure(
                ObservationFailureCode.CONTRACT_MISMATCH,
                "Polymarket outcome token does not match binding",
            )
        if order_book.validity is not StateValidity.VALID:
            return _failure(
                ObservationFailureCode.INVALID_STATE, "Polymarket snapshot replay state is invalid"
            )
        warnings = order_book.warnings + order_book.bids.warnings + order_book.asks.warnings
        if _warnings_have(warnings, WarningCode.STALE_SNAPSHOT):
            return _failure(ObservationFailureCode.STALE, "Polymarket snapshot is explicitly stale")
        raw_refs = _valid_lineage(snapshot.raw_refs)
        if raw_refs is None:
            return _failure(
                ObservationFailureCode.MISSING_PROVENANCE,
                "Polymarket snapshot lineage is missing or unordered",
            )
        timestamp_failure = _timestamp_failure(order_book.timestamp)
        if timestamp_failure is not None:
            return ObservationResult(None, (timestamp_failure,))
        best_bid = order_book.bids.levels[0].price if order_book.bids.levels else None
        best_ask = order_book.asks.levels[0].price if order_book.asks.levels else None
        interval_failure = _validate_interval(best_bid, best_ask)
        if interval_failure is not None:
            return ObservationResult(None, (interval_failure,))
        observation = _observation(
            proposition_id=binding.proposition_id,
            claim_binding_id=binding.binding_id,
            venue=Venue.POLYMARKET,
            market=binding.market,
            contract=binding.outcome_token,
            native_claim_side=(
                binding.native_outcome_side.value
                if isinstance(binding.native_outcome_side, PolymarketOutcomeSide)
                else binding.native_outcome_side
            ),
            best_bid=best_bid,
            best_ask=best_ask,
            timestamp=order_book.timestamp,
            timestamp_source=None,
            source_snapshot_schema_version=snapshot.schema_version,
            source_price_convention=None,
            validity=order_book.validity,
            raw_refs=raw_refs,
            warnings=warnings,
        )
        return ObservationResult(observation)
    except Exception:
        return _failure(ObservationFailureCode.INVALID_PRICE, "Polymarket observation is invalid")


def observe_kalshi(
    binding: KalshiClaimBinding, snapshot: KalshiOrderBookSnapshot
) -> ObservationResult:
    """Extract a Kalshi claim interval through the accepted convention-aware methods."""

    if not isinstance(binding, KalshiClaimBinding) or not isinstance(
        snapshot, KalshiOrderBookSnapshot
    ):
        return _failure(
            ObservationFailureCode.WRONG_TYPE, "Kalshi observation requires matching typed inputs"
        )
    try:
        if snapshot.venue is not Venue.KALSHI:
            return _failure(ObservationFailureCode.WRONG_VENUE, "snapshot is not Kalshi-native")
        if snapshot.schema_version != KALSHI_ORDERBOOK_SCHEMA_VERSION:
            return _failure(
                ObservationFailureCode.UNSUPPORTED_SCHEMA, "unsupported Kalshi schema version"
            )
        if snapshot.market != binding.market:
            return _failure(
                ObservationFailureCode.MARKET_MISMATCH,
                "Kalshi market identity does not match binding",
            )
        if snapshot.validity is not StateValidity.VALID:
            return _failure(
                ObservationFailureCode.INVALID_STATE, "Kalshi snapshot replay state is invalid"
            )
        warnings = snapshot.warnings + snapshot.yes_side.warnings + snapshot.no_side.warnings
        if _warnings_have(warnings, WarningCode.STALE_SNAPSHOT):
            return _failure(ObservationFailureCode.STALE, "Kalshi snapshot is explicitly stale")
        raw_refs = _valid_lineage(snapshot.raw_refs)
        if raw_refs is None:
            return _failure(
                ObservationFailureCode.MISSING_PROVENANCE,
                "Kalshi snapshot lineage is missing or unordered",
            )
        if snapshot.timestamp_source is KalshiTimestampSource.CAPTURE_FALLBACK:
            return _failure(
                ObservationFailureCode.UNAVAILABLE_TIMESTAMP,
                "Kalshi capture fallback is not an exact venue observation timestamp",
            )
        timestamp_failure = _timestamp_failure(snapshot.timestamp)
        if timestamp_failure is not None:
            return ObservationResult(None, (timestamp_failure,))
        if not isinstance(snapshot.price_convention, KalshiPriceConvention):
            return _failure(
                ObservationFailureCode.UNSUPPORTED_CONVENTION, "unsupported Kalshi price convention"
            )
        if binding.native_side.value == "yes":
            bids = snapshot.interpreted_yes_bids()
            asks = snapshot.derived_yes_asks()
        elif binding.native_side.value == "no":
            bids = snapshot.interpreted_no_bids()
            asks = snapshot.derived_no_asks()
        else:
            return _failure(ObservationFailureCode.CLAIM_SIDE, "Kalshi claim side is unsupported")
        warnings = warnings + bids.warnings + asks.warnings
        best_bid = bids.levels[0].price if bids.levels else None
        best_ask = asks.levels[0].price if asks.levels else None
        interval_failure = _validate_interval(best_bid, best_ask)
        if interval_failure is not None:
            return ObservationResult(None, (interval_failure,))
        observation = _observation(
            proposition_id=binding.proposition_id,
            claim_binding_id=binding.binding_id,
            venue=Venue.KALSHI,
            market=binding.market,
            contract=None,
            native_claim_side=binding.native_side.value,
            best_bid=best_bid,
            best_ask=best_ask,
            timestamp=snapshot.timestamp,
            timestamp_source=(
                snapshot.timestamp_source.value
                if isinstance(snapshot.timestamp_source, KalshiTimestampSource)
                else snapshot.timestamp_source
            ),
            source_snapshot_schema_version=snapshot.schema_version,
            source_price_convention=snapshot.price_convention.value,
            validity=snapshot.validity,
            raw_refs=raw_refs,
            warnings=warnings,
        )
        return ObservationResult(observation)
    except Exception:
        return _failure(
            ObservationFailureCode.UNSUPPORTED_CONVENTION,
            "Kalshi observation is invalid",
        )


build_polymarket_observation = observe_polymarket
build_kalshi_observation = observe_kalshi

__all__ = [
    "observe_polymarket",
    "observe_kalshi",
    "build_polymarket_observation",
    "build_kalshi_observation",
]
