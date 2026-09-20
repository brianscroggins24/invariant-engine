from __future__ import annotations

import copy
import pickle
from decimal import Decimal

import pytest

from conftest import (
    capture_batch,
    complete_transport,
    polymarket_body,
    polymarket_target,
    polymarket_us_body,
    polymarket_us_target,
    specification,
    specification_v2,
)
from invariant_engine.capture import (
    CAPTURE_RESULT_SCHEMA_VERSION,
    CaptureSerializationError,
    PolymarketUSOrderBook,
    PolymarketUSPriceLevel,
    is_trusted_attempt,
    is_trusted_batch,
    serialize_capture_bytes,
)
from invariant_engine.constraints import TrustedQuoteObservation
from invariant_engine.diagnostics import SuccessfulHistoricalValidationRecord
from invariant_engine.opportunities import OpportunityCandidate
from invariant_engine.provenance import RawEnvelope
from invariant_engine.relationships import RelationshipCertificate


class StringSubclass(str):
    pass


class DecimalSubclass(Decimal):
    pass


class TupleSubclass(tuple[object, ...]):
    pass


class PolymarketUSPriceLevelSubclass(PolymarketUSPriceLevel):
    pass


def produced_result(fixed_clock):
    return capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: complete_transport(polymarket_body()),
        observer_clock=fixed_clock,
    )


def produced_v2_result(fixed_clock):
    return capture_batch(
        specification_v2(polymarket_us_target()),
        transport=lambda *a, **k: complete_transport(polymarket_us_body()),
        observer_clock=fixed_clock,
    )


def test_process_local_trust_does_not_transfer_through_copy_pickle_or_json(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    assert is_trusted_batch(result)
    assert is_trusted_attempt(result.attempts[0])
    for transferred in (
        copy.copy(result),
        copy.deepcopy(result),
        pickle.loads(pickle.dumps(result)),
    ):
        assert not is_trusted_batch(transferred)
        with pytest.raises(CaptureSerializationError):
            serialize_capture_bytes(transferred)
    assert isinstance(__import__("json").loads(serialize_capture_bytes(result)), dict)


def test_material_mutation_revokes_trust(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    object.__setattr__(result.attempts[0], "reason_code", "changed")
    assert not is_trusted_attempt(result.attempts[0])
    assert not is_trusted_batch(result)


def test_capture_artifacts_cannot_impersonate_historical_trust_types(fixed_clock) -> None:
    attempt = produced_result(fixed_clock).attempts[0]
    protected = (
        RawEnvelope,
        RelationshipCertificate,
        TrustedQuoteObservation,
        OpportunityCandidate,
        SuccessfulHistoricalValidationRecord,
    )
    assert not isinstance(attempt, protected)


def test_each_contradictory_state_mutation_revokes_attempt_and_batch_trust(fixed_clock) -> None:
    mutations = (
        ("acquisition_started", False),
        ("normal_completion", False),
        ("received_byte_count", 0),
        ("retained_byte_count", 0),
        ("retained_body_sha256", "0" * 64),
        ("dispatch_count", 0),
        ("status", "captured"),
        ("suppression_source", "body"),
    )
    for field, value in mutations:
        result = produced_result(fixed_clock)
        object.__setattr__(result.attempts[0], field, value)
        assert not is_trusted_attempt(result.attempts[0])
        assert not is_trusted_batch(result)


def test_attempt_identity_position_and_specification_binding_are_committed(fixed_clock) -> None:
    result = produced_result(fixed_clock)
    object.__setattr__(result.attempts[0].target, "position", 1)
    assert not is_trusted_attempt(result.attempts[0])
    with pytest.raises(CaptureSerializationError):
        serialize_capture_bytes(result)


def test_v2_trust_does_not_transfer_and_native_mutation_revokes_trust(fixed_clock) -> None:
    result = produced_v2_result(fixed_clock)
    assert is_trusted_batch(result)
    for transferred in (
        copy.copy(result),
        copy.deepcopy(result),
        pickle.loads(pickle.dumps(result)),
    ):
        assert not is_trusted_batch(transferred)
    book = result.attempts[0].order_book
    assert type(book) is PolymarketUSOrderBook
    object.__setattr__(book.bids[0], "currency", "EUR")
    assert not is_trusted_attempt(result.attempts[0])
    assert not is_trusted_batch(result)


@pytest.mark.parametrize(
    "mutation",
    [
        "bids_list",
        "offers_tuple_subclass",
        "bid_dictionary",
        "offer_level_subclass",
        "market_slug_subclass",
        "market_slug_mismatch",
        "bid_price_text_subclass",
        "offer_quantity_text_non_string",
        "bid_currency_subclass",
        "offer_currency_mismatch",
        "bid_price_string",
        "offer_quantity_string",
        "bid_price_decimal_subclass",
        "offer_quantity_decimal_subclass",
        "bid_price_value_mismatch",
        "offer_quantity_value_mismatch",
    ],
)
def test_v2_native_nested_type_and_consistency_mutations_revoke_trust(
    fixed_clock,
    mutation: str,
) -> None:
    result = produced_v2_result(fixed_clock)
    attempt = result.attempts[0]
    book = attempt.order_book
    assert type(book) is PolymarketUSOrderBook
    original = serialize_capture_bytes(result)
    bid = book.bids[0]
    offer = book.offers[0]
    if mutation == "bids_list":
        object.__setattr__(book, "bids", list(book.bids))
    elif mutation == "offers_tuple_subclass":
        object.__setattr__(book, "offers", TupleSubclass(book.offers))
    elif mutation == "bid_dictionary":
        object.__setattr__(
            book,
            "bids",
            (
                {
                    "price_text": bid.price_text,
                    "quantity_text": bid.quantity_text,
                    "currency": bid.currency,
                    "price": bid.price,
                    "quantity": bid.quantity,
                },
            ),
        )
    elif mutation == "offer_level_subclass":
        object.__setattr__(
            book,
            "offers",
            (
                PolymarketUSPriceLevelSubclass(
                    offer.price_text,
                    offer.quantity_text,
                    offer.currency,
                    offer.price,
                    offer.quantity,
                ),
            ),
        )
    elif mutation == "market_slug_subclass":
        object.__setattr__(book, "market_slug", StringSubclass(book.market_slug))
    elif mutation == "market_slug_mismatch":
        object.__setattr__(book, "market_slug", "different-market")
    elif mutation == "bid_price_text_subclass":
        object.__setattr__(bid, "price_text", StringSubclass(bid.price_text))
    elif mutation == "offer_quantity_text_non_string":
        object.__setattr__(offer, "quantity_text", Decimal(offer.quantity_text))
    elif mutation == "bid_currency_subclass":
        object.__setattr__(bid, "currency", StringSubclass("USD"))
    elif mutation == "offer_currency_mismatch":
        object.__setattr__(offer, "currency", "EUR")
    elif mutation == "bid_price_string":
        object.__setattr__(bid, "price", str(bid.price))
    elif mutation == "offer_quantity_string":
        object.__setattr__(offer, "quantity", str(offer.quantity))
    elif mutation == "bid_price_decimal_subclass":
        object.__setattr__(bid, "price", DecimalSubclass(bid.price_text))
    elif mutation == "offer_quantity_decimal_subclass":
        object.__setattr__(offer, "quantity", DecimalSubclass(offer.quantity_text))
    elif mutation == "bid_price_value_mismatch":
        object.__setattr__(bid, "price", Decimal("0.501"))
    else:
        object.__setattr__(offer, "quantity", Decimal("3.26"))
    assert not is_trusted_attempt(attempt), mutation
    assert not is_trusted_batch(result), mutation
    with pytest.raises(CaptureSerializationError):
        serialize_capture_bytes(result)
    assert original


def test_v2_native_nested_exact_type_controls_remain_trusted(fixed_clock) -> None:
    result = produced_v2_result(fixed_clock)
    book = result.attempts[0].order_book
    assert type(book) is PolymarketUSOrderBook
    assert type(book.market_slug) is str
    for ladder in (book.bids, book.offers):
        assert type(ladder) is tuple
        for level in ladder:
            assert type(level) is PolymarketUSPriceLevel
            assert type(level.price_text) is str
            assert type(level.quantity_text) is str
            assert type(level.currency) is str
            assert type(level.price) is Decimal
            assert type(level.quantity) is Decimal
    assert is_trusted_attempt(result.attempts[0])
    assert is_trusted_batch(result)
    assert serialize_capture_bytes(result)


def test_v2_attempt_version_mutation_and_historical_impersonation_fail(fixed_clock) -> None:
    attempt = produced_v2_result(fixed_clock).attempts[0]
    protected = (
        RawEnvelope,
        RelationshipCertificate,
        TrustedQuoteObservation,
        OpportunityCandidate,
        SuccessfulHistoricalValidationRecord,
    )
    assert not isinstance(attempt, protected)
    object.__setattr__(attempt, "schema_version", CAPTURE_RESULT_SCHEMA_VERSION)
    assert not is_trusted_attempt(attempt)
