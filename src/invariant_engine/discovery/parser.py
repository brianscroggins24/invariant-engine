"""Strict parsers for recorded discovery input and output bytes."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import NoReturn, cast

from invariant_engine.discovery.schema import (
    DISCOVERY_INPUT_SCHEMA_VERSION,
    DISCOVERY_OUTPUT_SCHEMA_VERSION,
    DiscoveryInput,
    DiscoveryOutcome,
    DiscoveryProposal,
    DiscoveryRequest,
    DiscoveryRuleInput,
    DiscoverySimilarity,
    DiscoveryThreshold,
    EvidenceSpanProposal,
    KalshiDiscoveryIdentity,
    ParsedDiscoveryOutput,
    PolymarketDiscoveryIdentity,
    PropositionProposal,
)
from invariant_engine.domain.errors import DomainError
from invariant_engine.domain.ids import RawReference, Venue


class DiscoveryParseError(DomainError):
    """A recorded input or output is not strictly supported."""


_JSON_WHITESPACE = " \t\r\n"


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DiscoveryParseError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiscoveryParseError(f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryParseError(f"{field} must be non-empty text")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise DiscoveryParseError(f"{field} must be non-empty text when supplied")
    return value


def _optional_bool(value: object, field: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise DiscoveryParseError(f"{field} must be boolean when supplied")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    return tuple(_text(item, f"{field}[]") for item in _array(value, field))


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise DiscoveryParseError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise DiscoveryParseError(f"{field} must be a decimal string") from exc
    if not parsed.is_finite():
        raise DiscoveryParseError(f"{field} must be finite")
    return parsed


def _raw_refs(value: object, field: str) -> tuple[RawReference, ...]:
    result: list[RawReference] = []
    for item in _array(value, field):
        record = _object(item, f"{field}[]")
        if set(record) != {"value", "venue"}:
            raise DiscoveryParseError(f"{field}[] has unexpected structure")
        try:
            venue = Venue(_text(record["venue"], f"{field}[].venue"))
        except ValueError as exc:
            raise DiscoveryParseError(f"{field}[].venue is unsupported") from exc
        result.append(RawReference(_text(record["value"], f"{field}[].value"), venue))
    return tuple(result)


def _reject_json_numbers(value: object, field: str = "JSON") -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise DiscoveryParseError(f"{field} contains text that is not valid UTF-8") from exc
    elif isinstance(value, float):
        raise DiscoveryParseError(f"{field} cannot contain binary floating-point values")
    elif isinstance(value, dict):
        for key, item in value.items():
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise DiscoveryParseError(
                    f"{field} contains an object key that is not valid UTF-8"
                ) from exc
            _reject_json_numbers(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_json_numbers(item, f"{field}[{index}]")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DiscoveryParseError(f"duplicate JSON object key: {key}")
        try:
            key.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise DiscoveryParseError("JSON object key is not valid UTF-8") from exc
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise DiscoveryParseError(f"non-standard JSON constant is not supported: {value}")


def _json_bytes(data: bytes, field: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiscoveryParseError(f"{field} must be exact UTF-8 JSON") from exc
    try:
        decoder = json.JSONDecoder(
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
        start = len(text) - len(text.lstrip(_JSON_WHITESPACE))
        value, end = decoder.raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise DiscoveryParseError(f"{field} is malformed JSON") from exc
    if text[end:].strip(_JSON_WHITESPACE):
        raise DiscoveryParseError(f"{field} contains trailing content")
    _reject_json_numbers(value, field)
    return value


def parse_strict_json_bytes(data: bytes, field: str) -> object:
    """Parse one duplicate-key-free JSON document with explicit constants."""

    return _json_bytes(data, field)


def _identity(value: object, venue: Venue) -> PolymarketDiscoveryIdentity | KalshiDiscoveryIdentity:
    record = _object(value, "venue_identity")
    if venue is Venue.POLYMARKET:
        if set(record) != {
            "market_reference",
            "outcome_token_reference",
            "native_outcome_side",
        }:
            raise DiscoveryParseError("Polymarket venue_identity has unexpected structure")
        return PolymarketDiscoveryIdentity(
            _text(record["market_reference"], "market_reference"),
            _text(record["outcome_token_reference"], "outcome_token_reference"),
            _optional_text(record["native_outcome_side"], "native_outcome_side"),
        )
    if set(record) != {"market_ticker", "market_id", "native_side"}:
        raise DiscoveryParseError("Kalshi venue_identity has unexpected structure")
    return KalshiDiscoveryIdentity(
        _text(record["market_ticker"], "market_ticker"),
        _text(record["market_id"], "market_id"),
        _text(record["native_side"], "native_side"),
    )


def _thresholds(value: object) -> tuple[DiscoveryThreshold, ...]:
    result: list[DiscoveryThreshold] = []
    for item in _array(value, "thresholds"):
        record = _object(item, "threshold")
        if set(record) != {"name", "comparator", "value", "unit"}:
            raise DiscoveryParseError("threshold has unexpected structure")
        result.append(
            DiscoveryThreshold(
                _text(record["name"], "threshold.name"),
                _text(record["comparator"], "threshold.comparator"),
                _decimal(record["value"], "threshold.value"),
                _text(record["unit"], "threshold.unit"),
            )
        )
    return tuple(result)


def _rules(value: object) -> tuple[DiscoveryRuleInput, ...]:
    result: list[DiscoveryRuleInput] = []
    for item in _array(value, "market_rules"):
        record = _object(item, "market_rule")
        if set(record) != {"rule_input_id", "rule_text", "raw_refs"}:
            raise DiscoveryParseError("market_rule has unexpected structure")
        result.append(
            DiscoveryRuleInput(
                _text(record["rule_input_id"], "rule_input_id"),
                _text(record["rule_text"], "rule_text"),
                _raw_refs(record["raw_refs"], "market_rule.raw_refs"),
            )
        )
    return tuple(result)


def _parse_discovery_request(data: bytes) -> DiscoveryRequest:
    payload = _object(_json_bytes(data, "discovery input"), "discovery input")
    required = {"schema_version", "inputs"}
    if set(payload) != required:
        raise DiscoveryParseError("discovery input has unexpected structure")
    if payload["schema_version"] != DISCOVERY_INPUT_SCHEMA_VERSION:
        raise DiscoveryParseError("unsupported discovery input schema version")
    inputs: list[DiscoveryInput] = []
    allowed = {
        "input_id",
        "venue",
        "venue_identity",
        "claim_classification",
        "question",
        "market_rules",
        "raw_refs",
        "topics",
        "entities",
        "end_date",
        "thresholds",
        "unit",
        "similarity",
    }
    for item in _array(payload["inputs"], "inputs"):
        record = _object(item, "input")
        if not {
            "input_id",
            "venue",
            "venue_identity",
            "claim_classification",
            "question",
            "market_rules",
            "raw_refs",
        }.issubset(record):
            raise DiscoveryParseError("input is missing required fields")
        if set(record) - allowed:
            raise DiscoveryParseError("input has unexpected structure")
        try:
            venue = Venue(_text(record["venue"], "input.venue"))
        except ValueError as exc:
            raise DiscoveryParseError("input.venue is unsupported") from exc
        similarity_value = record.get("similarity")
        similarity: DiscoverySimilarity | None = None
        if similarity_value is not None:
            similarity_record = _object(similarity_value, "similarity")
            if set(similarity_record) != {"value", "label", "provider", "version"}:
                raise DiscoveryParseError("similarity has unexpected structure")
            similarity = DiscoverySimilarity(
                _decimal(similarity_record["value"], "similarity.value"),
                _optional_text(similarity_record["label"], "similarity.label"),
                _optional_text(similarity_record["provider"], "similarity.provider"),
                _optional_text(similarity_record["version"], "similarity.version"),
            )
        end_date_value = record.get("end_date")
        end_date: date | None = None
        if end_date_value is not None:
            try:
                end_date = date.fromisoformat(_text(end_date_value, "end_date"))
            except ValueError as exc:
                raise DiscoveryParseError("end_date must be an ISO date") from exc
        inputs.append(
            DiscoveryInput(
                _text(record["input_id"], "input_id"),
                venue,
                _identity(record["venue_identity"], venue),
                _text(record["claim_classification"], "claim_classification"),
                _text(record["question"], "question"),
                _rules(record["market_rules"]),
                _raw_refs(record["raw_refs"], "input.raw_refs"),
                _strings(record.get("topics", []), "topics"),
                _strings(record.get("entities", []), "entities"),
                end_date,
                _thresholds(record.get("thresholds", [])),
                _optional_text(record.get("unit"), "unit"),
                similarity,
            )
        )
    try:
        return DiscoveryRequest(tuple(inputs))
    except DomainError as exc:
        raise DiscoveryParseError(str(exc)) from exc


def parse_discovery_request(data: bytes) -> DiscoveryRequest:
    try:
        return _parse_discovery_request(data)
    except DiscoveryParseError:
        raise
    except DomainError as exc:
        raise DiscoveryParseError(str(exc)) from exc


def _span(value: object) -> EvidenceSpanProposal:
    record = _object(value, "evidence span")
    required = {"rule_input_id", "start", "end", "text", "raw_refs"}
    if not required.issubset(record) or set(record) - required:
        raise DiscoveryParseError("evidence span has missing or unexpected fields")
    start = record["start"]
    end = record["end"]
    if not isinstance(start, int) or isinstance(start, bool):
        raise DiscoveryParseError("evidence span start must be an integer")
    if not isinstance(end, int) or isinstance(end, bool):
        raise DiscoveryParseError("evidence span end must be an integer")
    return EvidenceSpanProposal(
        _text(record["rule_input_id"], "evidence span rule_input_id"),
        start,
        end,
        _text(record["text"], "evidence span text"),
        _raw_refs(record["raw_refs"], "evidence span raw_refs"),
    )


def _proposal(value: object) -> DiscoveryProposal:
    record = _object(value, "proposal")
    fields = {
        "proposal_id",
        "relationship_type",
        "propositions",
        "claim_classification",
        "evidence_spans",
        "assumptions",
        "uncertainties",
        "edge_cases",
        "event_scope",
        "thresholds",
        "condition",
        "close_time",
        "resolution_time",
        "resolution_sources",
        "cancellation_behavior",
        "void_behavior",
        "refund_behavior",
        "payout_structure",
        "observation_start",
        "observation_end",
        "unit",
        "timing",
        "resolution",
        "conflicting_evidence",
    }
    required = {
        "proposal_id",
        "relationship_type",
        "propositions",
        "claim_classification",
        "evidence_spans",
        "assumptions",
        "uncertainties",
        "edge_cases",
    }
    if not required.issubset(record) or set(record) - fields:
        raise DiscoveryParseError("proposal has missing or unexpected fields")
    propositions: list[PropositionProposal] = []
    for item in _array(record["propositions"], "proposal propositions"):
        proposition = _object(item, "proposal proposition")
        if set(proposition) != {"proposal_proposition_id", "input_id", "binding_ref"}:
            raise DiscoveryParseError("proposal proposition has unexpected structure")
        propositions.append(
            PropositionProposal(
                _text(proposition["proposal_proposition_id"], "proposal_proposition_id"),
                _text(proposition["input_id"], "proposal input_id"),
                _text(proposition["binding_ref"], "proposal binding_ref"),
            )
        )
    thresholds = _thresholds(record.get("thresholds", []))
    return DiscoveryProposal(
        _text(record["proposal_id"], "proposal_id"),
        _text(record["relationship_type"], "relationship_type"),
        tuple(propositions),
        _text(record["claim_classification"], "claim_classification"),
        tuple(_span(item) for item in _array(record["evidence_spans"], "evidence_spans")),
        _strings(record["assumptions"], "assumptions"),
        _strings(record["uncertainties"], "uncertainties"),
        _strings(record["edge_cases"], "edge_cases"),
        _optional_text(record.get("event_scope"), "event_scope"),
        thresholds,
        _optional_text(record.get("condition"), "condition"),
        _optional_text(record.get("close_time"), "close_time"),
        _optional_text(record.get("resolution_time"), "resolution_time"),
        _strings(record.get("resolution_sources", []), "resolution_sources"),
        _optional_text(record.get("cancellation_behavior"), "cancellation_behavior"),
        _optional_text(record.get("void_behavior"), "void_behavior"),
        _optional_text(record.get("refund_behavior"), "refund_behavior"),
        _optional_text(record.get("payout_structure"), "payout_structure"),
        _optional_text(record.get("observation_start"), "observation_start"),
        _optional_text(record.get("observation_end"), "observation_end"),
        _optional_text(record.get("unit"), "unit"),
        _optional_text(record.get("timing"), "timing"),
        _optional_text(record.get("resolution"), "resolution"),
        _optional_bool(record.get("conflicting_evidence"), "conflicting_evidence"),
    )


def _parse_discovery_output(data: bytes) -> ParsedDiscoveryOutput:
    payload = _object(_json_bytes(data, "discovery output"), "discovery output")
    if "schema_version" not in payload or "outcome" not in payload:
        raise DiscoveryParseError("discovery output is missing required fields")
    if payload["schema_version"] != DISCOVERY_OUTPUT_SCHEMA_VERSION:
        raise DiscoveryParseError("unsupported discovery output schema version")
    try:
        outcome = DiscoveryOutcome(_text(payload["outcome"], "outcome"))
    except ValueError as exc:
        raise DiscoveryParseError("unsupported discovery output outcome") from exc
    if outcome is DiscoveryOutcome.PROPOSALS:
        if set(payload) != {"schema_version", "outcome", "proposals"}:
            raise DiscoveryParseError("proposal output has unexpected structure")
        proposals = tuple(_proposal(item) for item in _array(payload["proposals"], "proposals"))
        try:
            return ParsedDiscoveryOutput(outcome, proposals)
        except DomainError as exc:
            raise DiscoveryParseError(str(exc)) from exc
    if set(payload) != {"schema_version", "outcome", "reason"}:
        raise DiscoveryParseError("terminal output has unexpected structure")
    try:
        return ParsedDiscoveryOutput(outcome, reason=_text(payload["reason"], "reason"))
    except DomainError as exc:
        raise DiscoveryParseError(str(exc)) from exc


def parse_discovery_output(data: bytes) -> ParsedDiscoveryOutput:
    try:
        return _parse_discovery_output(data)
    except DiscoveryParseError:
        raise
    except DomainError as exc:
        raise DiscoveryParseError(str(exc)) from exc


__all__ = [
    "DiscoveryParseError",
    "parse_discovery_output",
    "parse_discovery_request",
    "parse_strict_json_bytes",
]
