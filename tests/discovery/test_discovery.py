import hashlib
import json
import socket
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from invariant_engine.discovery import (
    DISCOVERY_INPUT_SCHEMA_VERSION,
    DISCOVERY_OUTPUT_SCHEMA_VERSION,
    DiscoveryConfig,
    DiscoveryDisposition,
    DiscoveryParseError,
    DiscoveryRequest,
    EvaluationLabel,
    EvaluationRecord,
    FixtureRecordedResponseSource,
    InMemoryRecordedResponseSource,
    PrefilterName,
    PrefilterPolicy,
    PrefilterStatus,
    RecordedAttempt,
    RecordedCost,
    RecordedLatency,
    RepeatGroup,
    ReviewerLabel,
    discover,
    evaluate_metrics,
    evaluate_prefilters,
    parse_discovery_output,
    parse_discovery_request,
)
from invariant_engine.domain.ids import RawReference, Venue
from invariant_engine.relationships import ValidationFailureCode, validate_draft
from invariant_engine.serialization import stable_json_bytes

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "valid_cross_venue.json"
CASES_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "cases.json"


def _source_and_request() -> tuple[FixtureRecordedResponseSource, object, RecordedAttempt]:
    source = FixtureRecordedResponseSource(FIXTURE)
    attempt = source.read_attempts()[0]
    return source, parse_discovery_request(attempt.input_bytes), attempt


def _config(max_attempts: int = 1, required: tuple[PrefilterName, ...] = ()) -> DiscoveryConfig:
    return DiscoveryConfig(True, max_attempts, PrefilterPolicy(required))


def _attempt_with_output(attempt: RecordedAttempt, output: object) -> RecordedAttempt:
    data = json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return replace(attempt, output_bytes=data, output_sha256=hashlib.sha256(data).hexdigest())


def _attempt_with_input(attempt: RecordedAttempt, data: bytes) -> RecordedAttempt:
    return replace(attempt, input_bytes=data, input_sha256=hashlib.sha256(data).hexdigest())


def _output_payload(attempt: RecordedAttempt) -> dict[str, object]:
    return json.loads(attempt.output_bytes.decode("utf-8"))


def test_valid_recorded_cross_venue_proposal_preserves_type_state_and_provenance() -> None:
    source, request, _ = _source_and_request()
    result = discover(request, source, _config(1, tuple(PrefilterName)))

    assert result.disposition is DiscoveryDisposition.PROPOSALS
    assert len(result.candidates) == len(result.drafts) == 1
    candidate = result.candidates[0]
    draft = result.drafts[0]
    assert candidate.source == "recorded_discovery"
    assert draft.semantic_review is None
    assert draft.completeness.declared_complete is False
    assert "does not attest" in draft.completeness.basis
    assert draft.feasible_states == ()
    assert draft.evidence[0].evidence_span == "Synthetic rule A."
    assert draft.evidence[1].evidence_span == "Synthetic rule B."
    assert draft.bindings[0].raw_refs[0].venue.value != draft.bindings[1].raw_refs[0].venue.value
    assert validate_draft(draft).failure.code is ValidationFailureCode.MISSING_REVIEW


def test_discovery_threshold_comparator_stays_in_parsed_discovery_data_only() -> None:
    _, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list) and isinstance(proposals[0], dict)
    proposals[0]["thresholds"] = [
        {"name": "amount", "comparator": ">=", "value": "10.00", "unit": "units"}
    ]
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert result.parsed_outputs[0].proposals[0].thresholds[0].comparator == ">="
    assert b'"comparator"' not in stable_json_bytes(result.drafts[0].thresholds[0])


def test_recorded_attempt_order_parameters_and_raw_provenance_are_retained() -> None:
    source, request, attempt = _source_and_request()
    result = discover(request, source, _config())
    assert result.attempts[0] == attempt
    assert tuple(item.name for item in attempt.parameters) == ("temperature", "response_format")
    assert tuple(item.value for item in attempt.source_raw_refs) == (
        "poly-discovery-raw",
        "kalshi-discovery-raw",
    )
    assert attempt.input_sha256 == hashlib.sha256(attempt.input_bytes).hexdigest()
    assert attempt.output_sha256 == hashlib.sha256(attempt.output_bytes).hexdigest()


def test_repeated_runs_are_byte_identical_and_no_certificate_is_exported() -> None:
    source, request, _ = _source_and_request()
    first = discover(request, source, _config())
    second = discover(request, source, _config())
    assert stable_json_bytes(first) == stable_json_bytes(second)
    import invariant_engine.discovery as discovery

    assert not hasattr(discovery, "RelationshipCertificate")


def test_discovery_never_invokes_the_deterministic_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, request, _ = _source_and_request()

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("discovery invoked certification validation")

    import invariant_engine.relationships.validation as validation

    monkeypatch.setattr(validation, "validate_draft", fail)
    monkeypatch.setattr(validation, "validate_relationship", fail)
    monkeypatch.setattr(validation, "validate_relationship_draft", fail)
    assert discover(request, source, _config()).disposition is DiscoveryDisposition.PROPOSALS


@pytest.mark.parametrize(
    "output_bytes",
    [b"{", b"[]", b'{"schema_version":"discovery-output-v1"}', b"```json\n{}\n```"],
)
def test_malformed_json_and_equivalent_structured_content_retry_fail_closed(
    output_bytes: bytes,
) -> None:
    source, request, attempt = _source_and_request()
    malformed = replace(
        attempt, output_bytes=output_bytes, output_sha256=hashlib.sha256(output_bytes).hexdigest()
    )
    result = discover(request, InMemoryRecordedResponseSource((malformed,)), _config())
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert len(result.malformed_attempts) == 1
    assert result.malformed_attempts[0].output_sha256 == hashlib.sha256(output_bytes).hexdigest()


def test_unsupported_input_and_output_versions_are_malformed() -> None:
    _, request, attempt = _source_and_request()
    bad_input = attempt.input_bytes.replace(
        DISCOVERY_INPUT_SCHEMA_VERSION.encode(), b"discovery-input-v9"
    )
    bad_input_attempt = replace(
        attempt, input_bytes=bad_input, input_sha256=hashlib.sha256(bad_input).hexdigest()
    )
    bad_output_attempt = replace(attempt, output_schema_version="discovery-output-v9")
    assert (
        discover(
            request, InMemoryRecordedResponseSource((bad_input_attempt,)), _config()
        ).disposition
        is DiscoveryDisposition.RETRY_EXHAUSTED
    )
    assert (
        discover(
            request, InMemoryRecordedResponseSource((bad_output_attempt,)), _config()
        ).disposition
        is DiscoveryDisposition.RETRY_EXHAUSTED
    )


@pytest.mark.parametrize(
    "mutation",
    [
        (b'"claim_classification":"binary_unit"', b'"claim_classification":"invalid"'),
        (b'"native_side":"no"', b'"native_side":"maybe"'),
        (b'"comparator":">="', b'"comparator":"??"'),
        (b'"value":"0.91"', b'"value":"not-a-decimal"'),
    ],
)
def test_input_domain_failures_are_malformed_attempts(
    mutation: tuple[bytes, bytes],
) -> None:
    _, request, attempt = _source_and_request()
    data = attempt.input_bytes.replace(*mutation)
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_input(attempt, data),)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert len(result.malformed_attempts) == 1


def test_output_domain_failures_are_malformed_attempts() -> None:
    _, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list) and isinstance(proposals[0], dict)
    spans = proposals[0]["evidence_spans"]
    assert isinstance(spans, list) and isinstance(spans[0], dict)
    spans[0]["start"] = 1
    spans[0]["end"] = 1
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert "non-empty" in result.malformed_attempts[0].reason


def test_duplicate_json_keys_are_rejected_at_input_and_output_boundaries() -> None:
    with pytest.raises(DiscoveryParseError, match="duplicate JSON object key"):
        parse_discovery_request(
            b'{"schema_version":"discovery-input-v1","schema_version":"discovery-input-v1","inputs":[]}'
        )
    with pytest.raises(DiscoveryParseError, match="duplicate JSON object key"):
        parse_discovery_output(
            b'{"schema_version":"discovery-output-v1","outcome":"abstain","outcome":"reject","reason":"conflict"}'
        )


def test_duplicate_fixture_keys_and_nonstandard_constants_are_rejected(tmp_path: Path) -> None:
    duplicate_fixture = tmp_path / "duplicate.json"
    duplicate_fixture.write_bytes(
        b'{"schema_version":"discovery-fixture-v1","schema_version":"discovery-fixture-v1","fixture_id":"x","attempts":[]}'
    )
    with pytest.raises(DiscoveryParseError, match="duplicate JSON object key"):
        FixtureRecordedResponseSource(duplicate_fixture).read_attempts()
    with pytest.raises(DiscoveryParseError, match="non-standard JSON constant"):
        parse_discovery_output(
            b'{"schema_version":"discovery-output-v1","outcome":"abstain","reason":NaN}'
        )


def test_ordinary_json_whitespace_is_accepted_but_trailing_content_is_not() -> None:
    parsed = parse_discovery_output(
        b' \n\t{"schema_version":"discovery-output-v1","outcome":"abstain","reason":"ambiguous"}\n '
    )
    assert parsed.reason == "ambiguous"
    with pytest.raises(DiscoveryParseError, match="trailing content"):
        parse_discovery_output(
            b' {"schema_version":"discovery-output-v1","outcome":"abstain",'
            b'"reason":"ambiguous"} false'
        )


def test_non_json_document_whitespace_is_rejected_at_input_and_output_boundaries() -> None:
    input_document = b'{"schema_version":"discovery-input-v1","inputs":[]}'
    output_document = b'{"schema_version":"discovery-output-v1","outcome":"abstain","reason":"x"}'
    for whitespace in (b"\xc2\xa0", b"\x0b", b"\x0c"):
        with pytest.raises(DiscoveryParseError):
            parse_discovery_request(whitespace + input_document)
        with pytest.raises(DiscoveryParseError):
            parse_discovery_output(output_document + whitespace)


def test_unpaired_surrogates_are_rejected_in_input_output_and_fixture_documents(
    tmp_path: Path,
) -> None:
    with pytest.raises(DiscoveryParseError, match="valid UTF-8"):
        parse_discovery_request(
            rb'{"schema_version":"discovery-input-v1","inputs":[],"\ud800":"x"}'
        )
    with pytest.raises(DiscoveryParseError, match="valid UTF-8"):
        parse_discovery_output(
            rb'{"schema_version":"discovery-output-v1","outcome":"abstain","reason":"\ud800"}'
        )
    surrogate_fixture = tmp_path / "surrogate.json"
    surrogate_fixture.write_bytes(
        rb'{"schema_version":"discovery-fixture-v1","fixture_id":"x","attempts":[],"\ud800":"x"}'
    )
    with pytest.raises(DiscoveryParseError, match="valid UTF-8"):
        FixtureRecordedResponseSource(surrogate_fixture).read_attempts()


def test_unpaired_surrogate_output_becomes_a_malformed_attempt() -> None:
    _, request, attempt = _source_and_request()
    output = rb'{"schema_version":"discovery-output-v1","outcome":"abstain","reason":"\ud800"}'
    changed_attempt = replace(
        attempt,
        output_bytes=output,
        output_sha256=hashlib.sha256(output).hexdigest(),
    )
    result = discover(
        request,
        InMemoryRecordedResponseSource((changed_attempt,)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert "valid UTF-8" in result.malformed_attempts[0].reason


def test_unpaired_surrogate_input_becomes_a_malformed_attempt() -> None:
    _, request, attempt = _source_and_request()
    input_bytes = rb'{"schema_version":"discovery-input-v1","inputs":[],"\ud800":"x"}'
    changed_attempt = _attempt_with_input(attempt, input_bytes)
    result = discover(
        request,
        InMemoryRecordedResponseSource((changed_attempt,)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert "valid UTF-8" in result.malformed_attempts[0].reason


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("relationship_type", "unknown", "unknown relationship type"),
        ("relationship_type", "conditional", "conditional"),
        ("claim_classification", "scalar", "scalar"),
    ],
)
def test_unsupported_and_unknown_proposals_are_explicit_rejections(
    field: str, value: str, reason: str
) -> None:
    source, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list)
    proposal = proposals[0]
    assert isinstance(proposal, dict)
    proposal[field] = value
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.PROPOSALS
    assert not result.candidates
    assert result.proposal_rejections[0].disposition.value == "invalid"
    assert reason in result.proposal_rejections[0].reason


@pytest.mark.parametrize("outcome", ["abstain", "reject"])
def test_explicit_terminal_outcomes_are_preserved_verbatim(outcome: str) -> None:
    source, request, attempt = _source_and_request()
    payload = {
        "schema_version": DISCOVERY_OUTPUT_SCHEMA_VERSION,
        "outcome": outcome,
        "reason": "Ambiguous supplied rules; no proposal.",
    }
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    expected = (
        DiscoveryDisposition.ABSTAINED if outcome == "abstain" else DiscoveryDisposition.REJECTED
    )
    assert result.disposition is expected
    assert result.terminal_reason == payload["reason"]


def test_duplicate_proposals_keep_first_and_reject_later_in_order() -> None:
    source, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list)
    duplicate = dict(proposals[0])
    duplicate["proposal_id"] = "model-p-duplicate"
    proposals.append(duplicate)
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert len(result.candidates) == 1
    assert len(result.proposal_rejections) == 1
    assert result.proposal_rejections[0].disposition.value == "duplicate"


def test_conflicting_evidence_is_rejected_without_silent_resolution() -> None:
    source, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list) and isinstance(proposals[0], dict)
    proposals[0]["conflicting_evidence"] = True
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert not result.candidates
    assert "conflicting evidence" in result.proposal_rejections[0].reason


def test_bounded_retry_exhaustion_preserves_ordered_history() -> None:
    source, request, attempt = _source_and_request()
    bad = _attempt_with_output(attempt, [])
    result = discover(request, InMemoryRecordedResponseSource((bad, bad, bad)), _config(2))
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert [item.attempt_index for item in result.attempts] == [0, 0]
    assert len(result.malformed_attempts) == 2


@pytest.mark.parametrize("change", ["offset", "text", "source"])
def test_evidence_span_closure_rejects_boundary_text_and_source_failures(change: str) -> None:
    source, request, attempt = _source_and_request()
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list) and isinstance(proposals[0], dict)
    spans = proposals[0]["evidence_spans"]
    assert isinstance(spans, list) and isinstance(spans[0], dict)
    if change == "offset":
        spans[0]["end"] = 18
    elif change == "text":
        spans[0]["text"] = "not the supplied span"
    else:
        spans[0]["raw_refs"] = [{"value": "unsupplied", "venue": "polymarket"}]
    result = discover(
        request,
        InMemoryRecordedResponseSource((_attempt_with_output(attempt, payload),)),
        _config(),
    )
    assert not result.candidates
    assert result.proposal_rejections[0].disposition.value == "invalid"


@pytest.mark.parametrize(
    "source_refs",
    [
        (),
        (RawReference("unrelated", Venue.POLYMARKET),),
    ],
)
def test_recorded_source_provenance_must_exactly_close_over_request(
    source_refs: tuple[RawReference, ...],
) -> None:
    _, request, attempt = _source_and_request()
    result = discover(
        request,
        InMemoryRecordedResponseSource((replace(attempt, source_raw_refs=source_refs),)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert "provenance" in result.malformed_attempts[0].reason


def test_evidence_rule_must_belong_to_participating_proposal_inputs() -> None:
    _, request, attempt = _source_and_request()
    unused_rule = replace(request.inputs[0].market_rules[0], rule_input_id="unused-rule")
    unused_input = replace(request.inputs[0], input_id="unused-input", market_rules=(unused_rule,))
    expanded_request = DiscoveryRequest(request.inputs + (unused_input,))
    payload = _output_payload(attempt)
    proposals = payload["proposals"]
    assert isinstance(proposals, list) and isinstance(proposals[0], dict)
    spans = proposals[0]["evidence_spans"]
    assert isinstance(spans, list) and isinstance(spans[0], dict)
    spans[0]["rule_input_id"] = "unused-rule"
    input_bytes = expanded_request.to_bytes()
    changed_attempt = replace(
        _attempt_with_output(attempt, payload),
        input_bytes=input_bytes,
        input_sha256=hashlib.sha256(input_bytes).hexdigest(),
    )
    result = discover(
        expanded_request,
        InMemoryRecordedResponseSource((changed_attempt,)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.PROPOSALS
    assert not result.candidates
    assert "outside proposal participants" in result.proposal_rejections[0].reason


def test_candidate_and_draft_top_level_provenance_closes_over_nested_sources() -> None:
    _, request, attempt = _source_and_request()
    result = discover(request, InMemoryRecordedResponseSource((attempt,)), _config())
    candidate = result.candidates[0]
    draft = result.drafts[0]
    assert candidate.raw_refs == draft.evidence_provenance
    assert draft.completeness.raw_refs == draft.evidence_provenance
    for binding in draft.bindings:
        assert all(raw in draft.evidence_provenance for raw in binding.raw_refs)
    for evidence in draft.evidence:
        assert all(raw in draft.evidence_provenance for raw in evidence.raw_refs)


def test_request_rule_provenance_missing_from_attempt_is_rejected() -> None:
    _, _, attempt = _source_and_request()
    input_payload = json.loads(attempt.input_bytes.decode("utf-8"))
    assert isinstance(input_payload, dict)
    inputs = input_payload["inputs"]
    assert isinstance(inputs, list) and isinstance(inputs[0], dict)
    rules = inputs[0]["market_rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    rules[0]["raw_refs"] = [{"value": "different-rule-raw", "venue": "polymarket"}]
    changed_input = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
    changed_attempt = _attempt_with_input(attempt, changed_input)
    changed_request = parse_discovery_request(changed_input)
    result = discover(
        changed_request,
        InMemoryRecordedResponseSource((changed_attempt,)),
        _config(),
    )
    assert result.disposition is DiscoveryDisposition.RETRY_EXHAUSTED
    assert "provenance" in result.malformed_attempts[0].reason


def test_disabled_discovery_does_not_consume_source_attempts() -> None:
    class FailingSource:
        def read_attempts(self) -> tuple[RecordedAttempt, ...]:
            raise AssertionError("disabled discovery consumed an attempt")

    _, request, _ = _source_and_request()
    result = discover(request, FailingSource(), DiscoveryConfig(False, 1, PrefilterPolicy(())))
    assert result.disposition is DiscoveryDisposition.DISABLED
    assert result.attempts == ()


def test_prefilters_are_exact_and_similarity_is_not_authoritative() -> None:
    _, request, _ = _source_and_request()
    left, right = request.inputs
    evaluation = evaluate_prefilters(left, right, PrefilterPolicy(tuple(PrefilterName)))
    assert [signal.status for signal in evaluation.signals] == [
        PrefilterStatus.PASS,
        PrefilterStatus.PASS,
        PrefilterStatus.PASS,
        PrefilterStatus.PASS,
        PrefilterStatus.PASS,
    ]
    changed = replace(right, end_date=left.end_date.replace(year=2026))
    failed = evaluate_prefilters(left, changed, PrefilterPolicy((PrefilterName.DATE,)))
    assert failed.signals[2].status is PrefilterStatus.FAIL
    assert failed.required_passed is False
    assert left.similarity is not None


def test_evaluation_metrics_use_decimal_ratios_and_none_for_zero_denominators() -> None:
    records = (
        EvaluationRecord("tp", EvaluationLabel.TP, 1, 2, "r", b"same", ReviewerLabel.ACCEPTED),
        EvaluationRecord("fp", EvaluationLabel.FP, 0, 1, "r", b"same", ReviewerLabel.REJECTED),
        EvaluationRecord("abstain", EvaluationLabel.ABSTAIN),
    )
    metrics = evaluate_metrics(records, (RepeatGroup("r", (b"same", b"same")),))
    assert metrics.precision == Decimal("0.5")
    assert metrics.recall == Decimal("1")
    assert metrics.false_positive_rate == Decimal("1")
    assert metrics.malformed_output_rate == Decimal("0.3333333333333333333333333333")
    assert metrics.repeated_run_consistency == Decimal("1")
    assert metrics.reviewer_acceptance == Decimal("0.5")
    empty = evaluate_metrics(())
    assert empty.precision is None
    assert empty.recall is None
    assert empty.false_positive_rate is None
    assert empty.repeated_run_consistency is None


def test_evaluation_records_explicit_decimal_cost_and_latency_units() -> None:
    from invariant_engine.discovery import RecordedCost, RecordedLatency

    record = EvaluationRecord(
        "measured",
        EvaluationLabel.TP,
        cost=RecordedCost(Decimal("0.10"), "USD", "USD"),
        latency=RecordedLatency(Decimal("2.5"), "ms"),
    )
    metrics = evaluate_metrics((record,))
    assert metrics.cost_metrics[0].total == Decimal("0.10")
    assert metrics.cost_metrics[0].mean == Decimal("0.10")
    assert metrics.latency_metrics[0].total == Decimal("2.5")


def test_structured_evaluation_fixture_labels_are_consumed() -> None:
    fixture = json.loads(CASES_FIXTURE.read_text())
    assert fixture["schema_version"] == "discovery-evaluation-labels-v1"
    assert fixture["synthetic"] is True
    assert all(
        {
            "case_id",
            "expected_disposition",
            "expected_accepted_proposals",
            "expected_rejected_proposals",
            "evaluation_label",
            "reviewer_label",
            "malformed_attempts",
            "recorded_attempts",
        }.issubset(case)
        for case in fixture["cases"]
    )
    labels_by_id = {case["case_id"]: case for case in fixture["cases"]}
    assert labels_by_id["valid_proposal"]["expected_disposition"] == "proposals"
    assert labels_by_id["valid_proposal"]["expected_accepted_proposals"] == 1
    assert labels_by_id["explicit_abstention"]["expected_disposition"] == "abstained"
    expected = fixture["expected_metrics"]
    records: list[EvaluationRecord] = []
    repeat_groups: list[RepeatGroup] = []
    for case in fixture["cases"]:
        cost = case.get("cost")
        latency = case.get("latency")
        records.append(
            EvaluationRecord(
                case["case_id"],
                EvaluationLabel(case["evaluation_label"]),
                malformed_attempts=case["malformed_attempts"],
                recorded_attempts=case["recorded_attempts"],
                reviewer_label=(
                    ReviewerLabel(case["reviewer_label"])
                    if case["reviewer_label"] is not None
                    else None
                ),
                cost=(
                    RecordedCost(Decimal(cost["amount"]), cost["unit"], cost["currency"])
                    if cost is not None
                    else RecordedCost()
                ),
                latency=(
                    RecordedLatency(Decimal(latency["value"]), latency["unit"])
                    if latency is not None
                    else RecordedLatency()
                ),
            )
        )
        if "repeat_outputs" in case:
            repeat_groups.append(
                RepeatGroup(
                    case["case_id"], tuple(item.encode("utf-8") for item in case["repeat_outputs"])
                )
            )
    metrics = evaluate_metrics(tuple(records), tuple(repeat_groups))
    assert (metrics.true_positive, metrics.false_positive) == (
        expected["true_positive"],
        expected["false_positive"],
    )
    assert (metrics.false_negative, metrics.true_negative) == (
        expected["false_negative"],
        expected["true_negative"],
    )
    assert metrics.abstention_count == expected["abstention_count"]
    assert metrics.evaluated_case_count == expected["evaluated_case_count"]
    assert (metrics.malformed_attempt_count, metrics.recorded_attempt_count) == (
        expected["malformed_attempt_count"],
        expected["recorded_attempt_count"],
    )
    assert metrics.precision == Decimal(expected["precision"])
    assert metrics.recall == Decimal(expected["recall"])
    assert metrics.false_positive_rate == Decimal(expected["false_positive_rate"])
    assert metrics.abstention_rate == Decimal(expected["abstention_rate"])
    assert metrics.malformed_output_rate == Decimal(expected["malformed_output_rate"])
    assert metrics.repeated_run_consistency == Decimal(expected["repeated_run_consistency"])
    assert metrics.reviewer_acceptance == Decimal(expected["reviewer_acceptance"])
    assert metrics.cost_metrics[0].total == Decimal("0.0125")
    assert metrics.latency_metrics[0].mean == Decimal("125")


def test_no_outbound_socket_is_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("discovery attempted an outbound socket")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    source, request, _ = _source_and_request()
    assert discover(request, source, _config()).disposition is DiscoveryDisposition.PROPOSALS
