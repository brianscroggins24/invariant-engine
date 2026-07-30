"""Pure replay of documented snapshot and update fixture events."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from invariant_engine.domain.errors import PayloadError, ReplayError
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.domain.validity import StateValidity
from invariant_engine.domain.warnings import WarningCode, WarningRecord
from invariant_engine.provenance.raw_envelope import RawEnvelope
from invariant_engine.venues.kalshi.order_book import (
    KalshiOrderBookDelta,
    KalshiOrderBookSnapshot,
    KalshiPriceConvention,
)
from invariant_engine.venues.kalshi.order_book import (
    apply_delta as apply_kalshi_delta,
)
from invariant_engine.venues.kalshi.order_book import (
    parse_delta as parse_kalshi_delta,
)
from invariant_engine.venues.kalshi.order_book import (
    parse_snapshot as parse_kalshi_snapshot,
)
from invariant_engine.venues.polymarket.order_book import (
    PolymarketOrderBookSnapshot,
    apply_price_change,
)
from invariant_engine.venues.polymarket.order_book import (
    parse_snapshot as parse_polymarket_snapshot,
)

State = PolymarketOrderBookSnapshot | KalshiOrderBookSnapshot


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    event_index: int
    event_type: str
    timestamp: datetime
    sequence: int | None
    raw_ref: RawReference
    state: State
    validity: StateValidity
    warnings: tuple[WarningRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayResult:
    venue: Venue
    frames: tuple[ReplayFrame, ...]
    warnings: tuple[WarningRecord, ...]
    final_state: State
    validity: StateValidity


def _event_type(envelope: RawEnvelope) -> str:
    payload = envelope.original_payload
    value = payload.get("event_type", payload.get("type"))
    if not isinstance(value, str):
        raise PayloadError("fixture event must contain event_type or type")
    return value


def _state_validity(state: State) -> StateValidity:
    if isinstance(state, PolymarketOrderBookSnapshot):
        return state.order_book.validity
    return state.validity


def _state_warnings(state: State) -> tuple[WarningRecord, ...]:
    if isinstance(state, PolymarketOrderBookSnapshot):
        return state.order_book.warnings
    return state.warnings


def _mark_invalid(state: State, warnings: tuple[WarningRecord, ...]) -> State:
    if isinstance(state, PolymarketOrderBookSnapshot):
        order_book = replace(
            state.order_book,
            validity=StateValidity.INVALID,
            warnings=state.order_book.warnings + warnings,
        )
        return replace(state, order_book=order_book)
    return replace(
        state,
        validity=StateValidity.INVALID,
        warnings=state.warnings + warnings,
    )


def _strict_failure(warning: WarningRecord) -> None:
    raise ReplayError(f"{warning.code.value}: {warning.message}")


def replay_events(
    events: Sequence[RawEnvelope],
    *,
    strict: bool = True,
    kalshi_price_convention: KalshiPriceConvention | None = None,
) -> ReplayResult:
    """Replay local events, failing closed unless explicit audit mode is requested.

    In strict mode, integrity violations raise ``ReplayError`` before a result
    can be returned. With ``strict=False``, the affected state and frame are
    marked ``StateValidity.INVALID`` and replay continues for audit purposes.
    A later fresh snapshot creates a new valid state.
    """

    if not events:
        raise ReplayError("at least one fixture event is required")
    venue = events[0].venue
    if venue is Venue.KALSHI and kalshi_price_convention is None:
        raise ReplayError("Kalshi replay requires explicit price-convention context")
    frames: list[ReplayFrame] = []
    replay_warnings: list[WarningRecord] = []
    state: State | None = None
    previous_timestamp: datetime | None = None
    previous_sequence: int | None = None
    previous_session_id: int | None = None
    for index, envelope in enumerate(events):
        if envelope.venue is not venue:
            raise ReplayError("a replay sequence cannot mix venues")
        event_type = _event_type(envelope)
        is_snapshot = event_type in {"book", "orderbook_snapshot"}
        delta: KalshiOrderBookDelta | None = None
        sequence_gap_prechecked = False
        if venue is Venue.POLYMARKET:
            if event_type == "book":
                polymarket_state = parse_polymarket_snapshot(envelope)
            elif event_type == "price_change":
                if state is None or not isinstance(state, PolymarketOrderBookSnapshot):
                    raise ReplayError("Polymarket price_change requires a preceding book snapshot")
                polymarket_state = apply_price_change(state, envelope)
            else:
                raise ReplayError(f"unsupported Polymarket replay event: {event_type}")
            next_state: State = polymarket_state
            event_timestamp = polymarket_state.timestamp
            sequence = polymarket_state.order_book.sequence
            session_id = None
        else:
            if event_type == "orderbook_snapshot":
                assert kalshi_price_convention is not None
                next_state = parse_kalshi_snapshot(
                    envelope, price_convention=kalshi_price_convention
                )
                event_timestamp = next_state.timestamp
                sequence = next_state.sequence
                session_id = next_state.session_id
            elif event_type == "orderbook_delta":
                if state is None or not isinstance(state, KalshiOrderBookSnapshot):
                    raise ReplayError("Kalshi orderbook_delta requires a preceding snapshot")
                assert kalshi_price_convention is not None
                delta = parse_kalshi_delta(envelope, price_convention=kalshi_price_convention)
                event_timestamp = delta.timestamp
                sequence = delta.sequence
                session_id = delta.session_id
                if delta.session_id != state.session_id:
                    warning = WarningRecord(
                        WarningCode.SESSION_MISMATCH,
                        "Kalshi delta sid does not match the active snapshot sid",
                        "sid",
                    )
                    if strict:
                        _strict_failure(warning)
                    next_state = _mark_invalid(state, (warning,))
                    replay_warnings.append(warning)
                elif delta.price_convention is not state.price_convention:
                    warning = WarningRecord(
                        WarningCode.CONVENTION_MISMATCH,
                        "Kalshi delta price convention does not match the active snapshot",
                        "price_convention",
                    )
                    if strict:
                        _strict_failure(warning)
                    next_state = _mark_invalid(state, (warning,))
                    replay_warnings.append(warning)
                elif delta.sequence != state.sequence + 1:
                    warning = WarningRecord(
                        WarningCode.SEQUENCE_GAP,
                        f"expected sequence {state.sequence + 1}, received {delta.sequence}",
                        "sequence",
                    )
                    if strict:
                        _strict_failure(warning)
                    next_state = _mark_invalid(state, (warning,))
                    replay_warnings.append(warning)
                    sequence_gap_prechecked = True
                else:
                    next_state = apply_kalshi_delta(state, delta)
            else:
                raise ReplayError(f"unsupported Kalshi replay event: {event_type}")

        event_warnings: list[WarningRecord] = []
        if previous_timestamp is not None and event_timestamp < previous_timestamp:
            event_warnings.append(
                WarningRecord(
                    WarningCode.NON_MONOTONIC_EVENT,
                    "fixture event timestamp is earlier than the preceding event",
                    "timestamp",
                )
            )
        if (
            venue is Venue.KALSHI
            and not is_snapshot
            and previous_session_id == session_id
            and previous_sequence is not None
            and sequence is not None
            and sequence != previous_sequence + 1
            and not sequence_gap_prechecked
        ):
            event_warnings.append(
                WarningRecord(
                    WarningCode.SEQUENCE_GAP,
                    f"expected sequence {previous_sequence + 1}, received {sequence}",
                    "sequence",
                )
            )
        if event_warnings:
            if strict:
                _strict_failure(event_warnings[0])
            next_state = _mark_invalid(next_state, tuple(event_warnings))
            replay_warnings.extend(event_warnings)
        frame = ReplayFrame(
            event_index=index,
            event_type=event_type,
            timestamp=event_timestamp,
            sequence=sequence,
            raw_ref=envelope.raw_ref,
            state=next_state,
            validity=_state_validity(next_state),
            warnings=_state_warnings(next_state),
        )
        frames.append(frame)
        state = next_state
        previous_timestamp = event_timestamp
        if isinstance(next_state, KalshiOrderBookSnapshot):
            previous_sequence = next_state.sequence
            previous_session_id = next_state.session_id
        else:
            previous_sequence = None
            previous_session_id = None
    if state is None:  # pragma: no cover - non-empty events always assign state
        raise ReplayError("replay produced no state")
    return ReplayResult(
        venue=venue,
        frames=tuple(frames),
        warnings=tuple(replay_warnings),
        final_state=state,
        validity=_state_validity(state),
    )
