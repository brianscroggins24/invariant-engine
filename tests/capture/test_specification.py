from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from conftest import kalshi_target, polymarket_target, specification
from invariant_engine.capture import (
    CAPTURE_SPECIFICATION_SCHEMA_VERSION,
    CaptureEnvironment,
    CaptureLimits,
    CaptureProvenance,
    CaptureSpecification,
    CaptureSpecificationError,
    CaptureTarget,
    specification_fingerprint,
    validate_specification,
)
from invariant_engine.capture.specification import KALSHI_PRODUCTION_ORIGIN
from invariant_engine.domain.ids import Venue


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class DecimalSubclass(Decimal):
    pass


class TupleSubclass(tuple[object, ...]):
    pass


class ProvenanceSubclass(CaptureProvenance):
    pass


class LimitsSubclass(CaptureLimits):
    pass


class TargetSubclass(CaptureTarget):
    pass


class SpecificationSubclass(CaptureSpecification):
    pass


def assert_specification_invalid(value: CaptureSpecification) -> None:
    with pytest.raises(CaptureSpecificationError):
        validate_specification(value)


def test_valid_ordered_specification_and_identity() -> None:
    value = specification(polymarket_target(0), kalshi_target(1))
    validated = validate_specification(value)
    assert validated == value
    assert type(validated.schema_version) is str
    assert type(validated.specification_id) is str
    assert all(type(item.kind) is str and type(item.value) is str for item in validated.provenance)
    for target in validated.targets:
        assert type(target.position) is int
        assert type(target.venue) is Venue
        assert type(target.environment) is CaptureEnvironment
        assert type(target.origin) is str
        assert type(target.identifier) is str
        assert type(target.limits) is CaptureLimits
        assert type(target.limits.connect_timeout_seconds) is Decimal
        assert type(target.limits.inactivity_timeout_seconds) is Decimal
        assert type(target.limits.elapsed_budget_seconds) is Decimal
        assert all(type(item.kind) is str and type(item.value) is str for item in target.provenance)
    assert specification_fingerprint(value) == specification_fingerprint(value)


@pytest.mark.parametrize("field", ["schema_version", "specification_id"])
@pytest.mark.parametrize("bad_kind", ["wrong_scalar", "subclass"])
def test_specification_string_fields_require_exact_str(field: str, bad_kind: str) -> None:
    value = specification(polymarket_target())
    original = getattr(value, field)
    bad_value: object = 1 if bad_kind == "wrong_scalar" else StringSubclass(original)
    object.__setattr__(value, field, bad_value)
    assert_specification_invalid(value)


@pytest.mark.parametrize("field", ["kind", "value"])
@pytest.mark.parametrize("location", ["specification", "target"])
@pytest.mark.parametrize("bad_kind", ["wrong_scalar", "subclass"])
def test_provenance_components_require_exact_str(field: str, location: str, bad_kind: str) -> None:
    value = specification(polymarket_target())
    provenance = value.provenance if location == "specification" else value.targets[0].provenance
    component = provenance[0]
    original = getattr(component, field)
    bad_value: object = 1 if bad_kind == "wrong_scalar" else StringSubclass(original)
    object.__setattr__(component, field, bad_value)
    assert_specification_invalid(value)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("connect_timeout_seconds", "5.0"),
        ("inactivity_timeout_seconds", "5.0"),
        ("elapsed_budget_seconds", "20.0"),
    ],
)
@pytest.mark.parametrize("bad_kind", ["integer", "float", "subclass", "invalid_decimal"])
def test_timeout_limits_require_exact_decimal(field: str, expected: str, bad_kind: str) -> None:
    value = specification(polymarket_target())
    bad_values: dict[str, object] = {
        "integer": int(Decimal(expected)),
        "float": float(expected),
        "subclass": DecimalSubclass(expected),
        "invalid_decimal": Decimal("sNaN"),
    }
    object.__setattr__(value.targets[0].limits, field, bad_values[bad_kind])
    assert_specification_invalid(value)


@pytest.mark.parametrize(
    "field",
    [
        "max_header_fields",
        "max_header_pair_bytes",
        "max_header_bytes",
        "max_body_bytes",
        "body_chunk_bytes",
    ],
)
@pytest.mark.parametrize("bad_kind", ["boolean", "decimal", "subclass"])
def test_integer_limits_require_exact_int(field: str, bad_kind: str) -> None:
    value = specification(polymarket_target())
    original = getattr(value.targets[0].limits, field)
    bad_values: dict[str, object] = {
        "boolean": True,
        "decimal": Decimal(original),
        "subclass": IntegerSubclass(original),
    }
    object.__setattr__(value.targets[0].limits, field, bad_values[bad_kind])
    assert_specification_invalid(value)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("position", True),
        ("position", IntegerSubclass(0)),
        ("venue", Venue.POLYMARKET.value),
        ("environment", CaptureEnvironment.PRODUCTION.value),
        ("origin", StringSubclass("https://clob.polymarket.com")),
        ("identifier", StringSubclass("123")),
    ],
)
def test_target_scalar_fields_require_exact_declared_types(field: str, bad_value: object) -> None:
    value = specification(polymarket_target())
    object.__setattr__(value.targets[0], field, bad_value)
    assert_specification_invalid(value)


@pytest.mark.parametrize("bad_kind", ["wrong_scalar", "subclass"])
def test_specification_collections_require_exact_tuples(bad_kind: str) -> None:
    for field in ("targets", "provenance"):
        value = specification(polymarket_target())
        original = getattr(value, field)
        bad_value: object = (
            list(original) if bad_kind == "wrong_scalar" else TupleSubclass(original)
        )
        object.__setattr__(value, field, bad_value)
        assert_specification_invalid(value)


@pytest.mark.parametrize("bad_kind", ["wrong_scalar", "subclass"])
def test_target_provenance_requires_an_exact_tuple(bad_kind: str) -> None:
    value = specification(polymarket_target())
    original = value.targets[0].provenance
    bad_value: object = list(original) if bad_kind == "wrong_scalar" else TupleSubclass(original)
    object.__setattr__(value.targets[0], "provenance", bad_value)
    assert_specification_invalid(value)


def test_nested_models_and_top_level_model_require_exact_types() -> None:
    value = specification(polymarket_target())
    target = value.targets[0]

    provenance_subclass = ProvenanceSubclass("fixture", "capture/cases")
    object.__setattr__(value, "provenance", (provenance_subclass,))
    assert_specification_invalid(value)

    value = specification(polymarket_target())
    object.__setattr__(value.targets[0], "limits", LimitsSubclass())
    assert_specification_invalid(value)

    target_subclass = TargetSubclass(
        target.position,
        target.venue,
        target.environment,
        target.origin,
        target.identifier,
        target.limits,
        target.provenance,
    )
    assert_specification_invalid(specification(target_subclass))

    exact = specification(polymarket_target())
    specification_subclass = SpecificationSubclass(
        exact.schema_version,
        exact.specification_id,
        exact.targets,
        exact.provenance,
    )
    assert_specification_invalid(specification_subclass)


@pytest.mark.parametrize("count", [1, 64])
def test_target_count_boundaries(count: int) -> None:
    targets = tuple(polymarket_target(index, str(index + 1)) for index in range(count))
    assert len(validate_specification(specification(*targets)).targets) == count


@pytest.mark.parametrize("count", [0, 65])
def test_target_count_outside_contract(count: int) -> None:
    targets = tuple(polymarket_target(index, str(index + 1)) for index in range(count))
    with pytest.raises(CaptureSpecificationError):
        validate_specification(specification(*targets))


@pytest.mark.parametrize("identifier", ["", "1a", "1" * 129, "\N{ARABIC-INDIC DIGIT ONE}"])
def test_polymarket_identifier_grammar(identifier: str) -> None:
    with pytest.raises(CaptureSpecificationError):
        validate_specification(specification(polymarket_target(identifier=identifier)))


@pytest.mark.parametrize("identifier", ["", "lower", "-BAD", "A" * 129, "A/B"])
def test_kalshi_identifier_grammar(identifier: str) -> None:
    with pytest.raises(CaptureSpecificationError):
        validate_specification(specification(kalshi_target(identifier=identifier)))


def test_duplicate_and_position_mismatch_reject_whole_specification() -> None:
    duplicate = specification(polymarket_target(0), polymarket_target(1))
    with pytest.raises(CaptureSpecificationError):
        validate_specification(duplicate)
    with pytest.raises(CaptureSpecificationError):
        validate_specification(specification(polymarket_target(1)))


def test_environment_origin_and_fixed_limits_are_closed() -> None:
    bad_environment = replace(polymarket_target(), environment=CaptureEnvironment.DEMO)
    bad_limit = replace(polymarket_target(), limits=replace(CaptureLimits(), max_body_bytes=1))
    for target in (bad_environment, bad_limit):
        with pytest.raises(CaptureSpecificationError):
            validate_specification(specification(target))


def test_exact_types_and_provenance_limits() -> None:
    target = polymarket_target()
    object.__setattr__(target, "position", True)
    with pytest.raises(CaptureSpecificationError):
        validate_specification(specification(target))
    too_many = tuple(CaptureProvenance("p", str(index)) for index in range(65))
    with pytest.raises(CaptureSpecificationError):
        validate_specification(
            CaptureSpecification(
                CAPTURE_SPECIFICATION_SCHEMA_VERSION,
                "id",
                (polymarket_target(),),
                too_many,
            )
        )


def test_same_kalshi_ticker_in_two_environments_is_not_duplicate() -> None:
    demo = kalshi_target(0)
    production = CaptureTarget(
        1,
        Venue.KALSHI,
        CaptureEnvironment.PRODUCTION,
        KALSHI_PRODUCTION_ORIGIN,
        demo.identifier,
        demo.limits,
        demo.provenance,
    )
    assert len(validate_specification(specification(demo, production)).targets) == 2


def test_provenance_is_required_and_components_are_closed() -> None:
    value = specification(polymarket_target())
    for provenance in ((), (CaptureProvenance("bad key", "value"),)):
        with pytest.raises(CaptureSpecificationError):
            validate_specification(replace(value, provenance=provenance))


def test_no_identifier_normalization_occurs() -> None:
    target = kalshi_target(identifier="ABC_DEF.1")
    assert validate_specification(specification(target)).targets[0].identifier == "ABC_DEF.1"
