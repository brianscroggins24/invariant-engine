from __future__ import annotations

import hashlib
import io
import socket

import invariant_engine.capture.transport as transport_module
from conftest import (
    SIGNATURE,
    capture_batch,
    complete_transport,
    kalshi_body,
    kalshi_target,
    polymarket_body,
    polymarket_target,
    specification,
)
from invariant_engine.capture import (
    AcquisitionOutcome,
    BatchStatus,
    CaptureEnvironment,
    KalshiAuthenticationBinding,
    RetentionState,
    TargetStatus,
    TransportFailureKind,
    TransportResult,
    serialize_capture_bytes,
)
from invariant_engine.capture.specification import KALSHI_DEMO_ORIGIN


def binding(signer=lambda _: SIGNATURE) -> KalshiAuthenticationBinding:
    return KalshiAuthenticationBinding(CaptureEnvironment.DEMO, KALSHI_DEMO_ORIGIN, "key-1", signer)


def test_sequential_success_and_authentication_is_not_sent_to_polymarket(fixed_clock) -> None:
    seen = []

    def fake(target, headers=(), *, confidentiality_values=()):
        seen.append((target.position, headers, confidentiality_values))
        body = polymarket_body() if target.position == 0 else kalshi_body()
        return complete_transport(body)

    result = capture_batch(
        specification(polymarket_target(0), kalshi_target(1)),
        (binding(),),
        transport=fake,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "123",
    )
    assert result.status is BatchStatus.COMPLETED
    assert [attempt.status for attempt in result.attempts] == [TargetStatus.CAPTURED] * 2
    assert seen[0] == (0, (), ())
    assert [name for name, _ in seen[1][1]] == [
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-TIMESTAMP",
        "KALSHI-ACCESS-SIGNATURE",
    ]


def test_invalid_spec_or_bindings_make_zero_signer_calls_and_dispatches(fixed_clock) -> None:
    calls = []
    signer_calls = []
    invalid = specification(polymarket_target(1))
    result = capture_batch(
        invalid, transport=lambda *a, **k: calls.append(1), observer_clock=fixed_clock
    )
    assert result.status is BatchStatus.SPECIFICATION_INVALID
    missing = capture_batch(
        specification(kalshi_target()),
        (),
        transport=lambda *a, **k: calls.append(1),
        observer_clock=fixed_clock,
    )
    assert missing.status is BatchStatus.AUTHENTICATION_BINDING_INVALID
    assert not calls and not signer_calls


def test_invalid_later_target_rejects_before_signing_or_dispatch(fixed_clock) -> None:
    signer_calls = []
    dispatches = []
    invalid_later_target = polymarket_target(1)
    object.__setattr__(invalid_later_target.limits, "elapsed_budget_seconds", 20)

    result = capture_batch(
        specification(kalshi_target(0), invalid_later_target),
        (binding(lambda value: signer_calls.append(value) or SIGNATURE),),
        transport=lambda *args, **kwargs: dispatches.append((args, kwargs)),
        observer_clock=fixed_clock,
    )

    assert result.status is BatchStatus.SPECIFICATION_INVALID
    assert result.attempts == ()
    assert signer_calls == []
    assert dispatches == []


def test_signing_failure_dispatches_zero_and_later_target_continues(fixed_clock) -> None:
    calls = []

    def fail(_: bytes) -> str:
        raise RuntimeError("do-not-expose")

    result = capture_batch(
        specification(kalshi_target(0), polymarket_target(1)),
        (binding(fail),),
        transport=lambda target, *a, **k: (
            calls.append(target.position) or complete_transport(polymarket_body())
        ),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.SIGNING_FAILED,
        TargetStatus.CAPTURED,
    ]
    assert [attempt.dispatch_count for attempt in result.attempts] == [0, 1]
    assert calls == [1]


def test_empty_200_and_empty_404_have_distinct_statuses_and_real_digest(fixed_clock) -> None:
    statuses = iter((200, 404))

    def fake(*args, **kwargs):
        return complete_transport(b"", next(statuses))

    result = capture_batch(
        specification(polymarket_target(0, "1"), polymarket_target(1, "2")),
        transport=fake,
        observer_clock=fixed_clock,
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.BODY_EMPTY,
        TargetStatus.HTTP_STATUS_UNSUPPORTED,
    ]
    assert all(attempt.retained_body == b"" for attempt in result.attempts)
    assert all(
        attempt.retained_body_sha256 == hashlib.sha256(b"").hexdigest()
        for attempt in result.attempts
    )


def test_transport_failure_statuses_continue(fixed_clock) -> None:
    failures = [
        (
            TransportFailureKind.HEADERS,
            AcquisitionOutcome.NOT_STARTED,
            RetentionState.ABSENT,
            0,
            None,
        ),
        (
            TransportFailureKind.OVERSIZED,
            AcquisitionOutcome.NOT_STARTED,
            RetentionState.ABSENT,
            0,
            None,
        ),
        (
            TransportFailureKind.TIMEOUT,
            AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
            RetentionState.ABSENT,
            0,
            None,
        ),
        (
            TransportFailureKind.TRANSPORT,
            AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE,
            RetentionState.ABSENT,
            0,
            None,
        ),
    ]
    responses = iter(
        TransportResult(
            failure,
            None,
            1_048_577 if failure is TransportFailureKind.OVERSIZED else None,
            None,
            outcome,
            retention,
            count,
            body,
            None,
            None,
        )
        for failure, outcome, retention, count, body in failures
    )
    targets = tuple(polymarket_target(index, str(index + 1)) for index in range(4))
    result = capture_batch(
        specification(*targets),
        transport=lambda *a, **k: next(responses),
        observer_clock=fixed_clock,
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.RESPONSE_HEADERS_INVALID,
        TargetStatus.BODY_OVERSIZED,
        TargetStatus.TIMEOUT,
        TargetStatus.TLS_OR_TRANSPORT_FAILED,
    ]


def test_post_read_deadline_confidentiality_propagates_and_batch_continues(
    monkeypatch, fixed_clock
) -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

    class Response:
        status = 200

        def __init__(self, body: bytes, *, expire: bool) -> None:
            self.body = body
            self.expire = expire
            self.returned = False

        def getheaders(self):
            return [("Content-Type", "application/json")]

        def read(self, amount: int) -> bytes:
            if self.returned:
                return b""
            self.returned = True
            assert len(self.body) <= amount
            if self.expire:
                active_clock.now = 20.1
            return self.body

        def close(self) -> None:
            pass

    responses = iter((Response(b"key-1", expire=True), Response(polymarket_body(), expire=False)))
    connection_count = 0
    active_clock = Clock()

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs) -> None:
            nonlocal connection_count
            connection_count += 1

        def configure_budget(self, *args) -> None:
            pass

        def connect(self) -> None:
            pass

        def putrequest(self, *args, **kwargs) -> None:
            pass

        def putheader(self, *args) -> None:
            pass

        def endheaders(self) -> None:
            pass

        def getresponse(self):
            return next(responses)

        def close(self) -> None:
            pass

    monkeypatch.setattr(transport_module, "_DirectHTTPSConnection", Connection)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        nonlocal active_clock
        active_clock = Clock()
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
            clock=active_clock,
        )

    result = capture_batch(
        specification(kalshi_target(0), polymarket_target(1)),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    first = result.attempts[0]
    assert first.status is TargetStatus.CONFIDENTIALITY_FAILURE
    assert first.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert first.received_byte_count == len(b"key-1")
    assert first.retention_state is RetentionState.SUPPRESSED
    assert first.retained_body is None
    assert first.retained_body_sha256 is None
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1]
    assert result.attempts[1].status is TargetStatus.CAPTURED
    assert connection_count == 2


def test_raw_initial_header_failures_propagate_and_batch_continues(
    monkeypatch, fixed_clock
) -> None:
    class SocketBytes:
        def __init__(self, wire: bytes) -> None:
            self.wire = wire

        def makefile(self, *args, **kwargs):
            return io.BytesIO(self.wire)

    wires = iter(
        (
            b"HTTP/1.1 200 OK\r\nBad Header: x\r\n\r\n{}",
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nBad Header: x\r\n"
            b"X-Reflection: key-1\r\n\r\n{}",
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(polymarket_body('2'))}\r\n\r\n".encode("ascii")
            + polymarket_body("2"),
        )
    )
    connection_count = 0

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs) -> None:
            nonlocal connection_count
            connection_count += 1

        def configure_budget(self, *args) -> None:
            pass

        def connect(self) -> None:
            pass

        def putrequest(self, *args, **kwargs) -> None:
            pass

        def putheader(self, *args) -> None:
            pass

        def endheaders(self) -> None:
            pass

        def getresponse(self):
            response = transport_module._StrictHTTPResponse(SocketBytes(next(wires)), method="GET")
            response.begin()
            return response

        def close(self) -> None:
            pass

    monkeypatch.setattr(transport_module, "_DirectHTTPSConnection", Connection)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            polymarket_target(0, "1"),
            kalshi_target(1),
            polymarket_target(2, "2"),
        ),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.RESPONSE_HEADERS_INVALID,
        TargetStatus.CONFIDENTIALITY_FAILURE,
        TargetStatus.CAPTURED,
    ]
    assert result.attempts[0].acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.attempts[0].retention_state is RetentionState.ABSENT
    assert result.attempts[1].acquisition_outcome is AcquisitionOutcome.NOT_STARTED
    assert result.attempts[1].retention_state is RetentionState.SUPPRESSED
    assert result.attempts[1].received_byte_count == 0
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3


def test_discarded_trailers_and_trailer_failure_propagate_without_leakage(
    monkeypatch, fixed_clock
) -> None:
    class RawSocket:
        def __init__(self, wire: bytes) -> None:
            self.stream = io.BytesIO(wire)

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    def chunked(body: bytes, trailers: bytes) -> bytes:
        encoded_body = f"{len(body):x}\r\n".encode("ascii") + body + b"\r\n"
        return (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
            b"Content-Type: application/json\r\n\r\n" + encoded_body + b"0\r\n" + trailers
        )

    final_body = polymarket_body("2")
    sockets = iter(
        (
            RawSocket(
                chunked(
                    kalshi_body(),
                    b"Content-Type: text/plain\r\nX-Key: key-1\r\nX-Signature: "
                    + SIGNATURE.encode("ascii")
                    + b"\r\n\r\n",
                )
            ),
            RawSocket(chunked(b"partial", b"X-Unterminated: discarded\r\n")),
            RawSocket(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(final_body)}\r\n\r\n".encode("ascii")
                + final_body
            ),
        )
    )
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = next(sockets)

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            kalshi_target(0),
            polymarket_target(1, "1"),
            polymarket_target(2, "2"),
        ),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.CAPTURED,
        TargetStatus.BODY_PARTIAL,
        TargetStatus.CAPTURED,
    ]
    assert result.attempts[0].retention_state is RetentionState.COMPLETE
    assert result.attempts[1].acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.attempts[1].received_byte_count == len(b"partial")
    assert result.attempts[1].retained_body == b"partial"
    assert result.attempts[1].retained_body_sha256 == hashlib.sha256(b"partial").hexdigest()
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3
    serialized = serialize_capture_bytes(result)
    assert b"key-1" not in serialized
    assert SIGNATURE.encode("ascii") not in serialized
    assert b"X-Unterminated" not in serialized
    assert b"text/plain" not in serialized


def test_interrupted_chunk_reads_preserve_body_and_batch_continues(
    monkeypatch, fixed_clock
) -> None:
    class Stream(io.BytesIO):
        def __init__(self, wire: bytes, failure: BaseException | None = None) -> None:
            super().__init__(wire)
            self.failure = failure
            self.readline_calls = 0

        def readline(self, size: int = -1) -> bytes:
            self.readline_calls += 1
            if self.failure is not None and self.readline_calls == 6:
                raise self.failure
            return super().readline(size)

    class RawSocket:
        def __init__(self, stream: Stream) -> None:
            self.stream = stream

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    def interrupted_wire(body: bytes) -> bytes:
        return (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
            b"Content-Type: application/json\r\n\r\n"
            + f"{len(body):x}\r\n".encode("ascii")
            + body
            + b"\r\n"
        )

    final_body = polymarket_body("3")
    reflected = b"key-1"
    ordinary = b"ordinary-prefix"
    streams = iter(
        (
            Stream(interrupted_wire(reflected), TimeoutError("synthetic timeout key-1")),
            Stream(interrupted_wire(ordinary), OSError("synthetic failure key-1")),
            Stream(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(final_body)}\r\n\r\n".encode("ascii")
                + final_body
            ),
        )
    )
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = RawSocket(next(streams))

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            kalshi_target(0),
            polymarket_target(1, "2"),
            polymarket_target(2, "3"),
        ),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.CONFIDENTIALITY_FAILURE,
        TargetStatus.BODY_PARTIAL,
        TargetStatus.CAPTURED,
    ]
    first, second, third = result.attempts
    assert first.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert first.received_byte_count == len(reflected)
    assert first.retention_state is RetentionState.SUPPRESSED
    assert first.retained_body is None
    assert first.retained_body_sha256 is None
    assert second.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert second.received_byte_count == len(ordinary)
    assert second.retention_state is RetentionState.PARTIAL
    assert second.retained_body == ordinary
    assert second.retained_body_sha256 == hashlib.sha256(ordinary).hexdigest()
    assert third.status is TargetStatus.CAPTURED
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3
    serialized = serialize_capture_bytes(result)
    assert reflected not in serialized
    assert b"synthetic timeout" not in serialized
    assert b"synthetic failure" not in serialized


def test_negative_chunk_lengths_fail_once_and_batch_continues(monkeypatch, fixed_clock) -> None:
    class Stream(io.BytesIO):
        def __init__(self, wire: bytes) -> None:
            super().__init__(wire)
            self.read_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return super().read(size)

    class RawSocket:
        def __init__(self, stream: Stream) -> None:
            self.stream = stream

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    def chunked(body: bytes) -> bytes:
        return (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
            b"Content-Type: application/json\r\n\r\n" + body
        )

    final_body = polymarket_body("3")
    streams = (
        Stream(chunked(b"-1\r\n")),
        Stream(chunked(b"3\r\nabc\r\n-1\r\n")),
        Stream(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(final_body)}\r\n\r\n".encode("ascii")
            + final_body
        ),
    )
    stream_iter = iter(streams)
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = RawSocket(next(stream_iter))

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            polymarket_target(0, "1"),
            polymarket_target(1, "2"),
            polymarket_target(2, "3"),
        ),
        transport=production_transport,
        observer_clock=fixed_clock,
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.TLS_OR_TRANSPORT_FAILED,
        TargetStatus.BODY_PARTIAL,
        TargetStatus.CAPTURED,
    ]
    assert result.attempts[0].acquisition_outcome is AcquisitionOutcome.FAILED_BEFORE_FIRST_BYTE
    assert result.attempts[0].received_byte_count == 0
    assert result.attempts[0].retention_state is RetentionState.ABSENT
    assert result.attempts[1].acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert result.attempts[1].received_byte_count == 3
    assert result.attempts[1].retained_body == b"abc"
    assert result.attempts[1].retained_body_sha256 == hashlib.sha256(b"abc").hexdigest()
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3
    assert all(0 < size <= 65_536 for stream in streams for size in stream.read_sizes)


def test_chunk_deadline_preserves_reflection_and_batch_continues(monkeypatch, fixed_clock) -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

    class Stream(io.BytesIO):
        def __init__(self, wire: bytes, clock: Clock, *, expire_on_read: bool) -> None:
            super().__init__(wire)
            self.clock = clock
            self.expire_on_read = expire_on_read
            self.read_calls = 0

        def read(self, size: int = -1) -> bytes:
            self.read_calls += 1
            result = super().read(size)
            if self.expire_on_read and self.read_calls == 1:
                self.clock.now = 20.1
            return result

    class RawSocket:
        def __init__(self, stream: Stream) -> None:
            self.stream = stream

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    reflected = b"key-1"
    first_wire = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        b"Content-Type: application/json\r\n\r\n"
        + f"{len(reflected):x}\r\n".encode("ascii")
        + reflected
        + b"\r\n0\r\n\r\n"
    )
    final_body = polymarket_body("2")
    second_wire = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {len(final_body)}\r\n\r\n".encode("ascii")
        + final_body
    )
    clocks = (Clock(), Clock())
    streams = iter(
        (
            Stream(first_wire, clocks[0], expire_on_read=True),
            Stream(second_wire, clocks[1], expire_on_read=False),
        )
    )
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = RawSocket(next(streams))

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    clock_iter = iter(clocks)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
            clock=next(clock_iter),
        )

    result = capture_batch(
        specification(kalshi_target(0), polymarket_target(1, "2")),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    first, second = result.attempts
    assert first.status is TargetStatus.CONFIDENTIALITY_FAILURE
    assert first.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert first.received_byte_count == len(reflected)
    assert first.retention_state is RetentionState.SUPPRESSED
    assert first.retained_body is None
    assert first.retained_body_sha256 is None
    assert second.status is TargetStatus.CAPTURED
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1]
    assert connection_count == 2
    serialized = serialize_capture_bytes(result)
    assert reflected not in serialized


def test_interrupted_and_informational_headers_propagate_and_continue(
    monkeypatch, fixed_clock
) -> None:
    class Stream(io.BytesIO):
        def __init__(self, wire: bytes, failure: BaseException | None = None) -> None:
            super().__init__(wire)
            self.failure = failure
            self.readline_calls = 0

        def readline(self, size: int = -1) -> bytes:
            self.readline_calls += 1
            if self.failure is not None and self.readline_calls == 3:
                raise self.failure
            return super().readline(size)

    class RawSocket:
        def __init__(self, stream: Stream) -> None:
            self.stream = stream

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    body = polymarket_body("2")
    streams = iter(
        (
            Stream(
                b"HTTP/1.1 200 OK\r\nX-Visible: ordinary\r\n",
                TimeoutError("synthetic timeout"),
            ),
            Stream(
                b"HTTP/1.1 200 OK\r\nX-Reflection: key-1\r\n",
                OSError("synthetic failure"),
            ),
            Stream(
                b"HTTP/1.1 100 Continue\r\nX-Interim: visible\r\n\r\n"
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            ),
        )
    )
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = RawSocket(next(streams))

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            polymarket_target(0, "1"),
            kalshi_target(1),
            polymarket_target(2, "2"),
        ),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.TIMEOUT,
        TargetStatus.CONFIDENTIALITY_FAILURE,
        TargetStatus.CAPTURED,
    ]
    assert all(
        attempt.acquisition_outcome is AcquisitionOutcome.NOT_STARTED
        for attempt in result.attempts[:2]
    )
    assert result.attempts[0].retention_state is RetentionState.ABSENT
    assert result.attempts[1].retention_state is RetentionState.SUPPRESSED
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3


def test_surrogate_body_scanning_classification_serialization_and_continuation(
    monkeypatch, fixed_clock
) -> None:
    class RawSocket:
        def __init__(self, wire: bytes) -> None:
            self.stream = io.BytesIO(wire)

        def makefile(self, *args, **kwargs):
            return self.stream

        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    nonsecret = b'{"bad":"\\ud800","ordinary":"value"}'
    reflected = b'{"bad":"\\udc00","secret":"key\\u002d1"}'
    final_body = polymarket_body("2")

    def wire(body: bytes) -> bytes:
        return (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(body)).encode("ascii")
            + b"\r\n\r\n"
            + body
        )

    sockets = iter(
        (RawSocket(wire(nonsecret)), RawSocket(wire(reflected)), RawSocket(wire(final_body)))
    )
    connection_count = 0

    def connect(connection) -> None:
        nonlocal connection_count
        connection_count += 1
        connection.sock = next(sockets)

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(transport_module._DirectHTTPSConnection, "connect", connect)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def production_transport(target, headers=(), *, confidentiality_values=()):
        return transport_module.dispatch(
            target,
            headers,
            confidentiality_values=confidentiality_values,
        )

    result = capture_batch(
        specification(
            kalshi_target(0, "TEST-1"),
            kalshi_target(1, "TEST-2"),
            polymarket_target(2, "2"),
        ),
        (binding(),),
        transport=production_transport,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.JSON_INVALID,
        TargetStatus.CONFIDENTIALITY_FAILURE,
        TargetStatus.CAPTURED,
    ]
    assert result.attempts[0].acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.attempts[0].received_byte_count == len(nonsecret)
    assert result.attempts[0].retained_body == nonsecret
    assert result.attempts[1].acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert result.attempts[1].received_byte_count == len(reflected)
    assert result.attempts[1].retention_state is RetentionState.SUPPRESSED
    assert result.attempts[1].retained_body is None
    assert result.attempts[1].retained_body_sha256 is None
    assert [attempt.dispatch_count for attempt in result.attempts] == [1, 1, 1]
    assert connection_count == 3
    serialized = serialize_capture_bytes(result)
    assert b"key-1" not in serialized
    assert b"key\\u002d1" not in serialized
    assert SIGNATURE.encode("ascii") not in serialized


def test_mutation_during_signer_is_integrity_failure_and_zero_dispatch(fixed_clock) -> None:
    original = kalshi_target()
    spec = specification(original)
    dispatches = []

    def mutate(_: bytes) -> str:
        object.__setattr__(original, "identifier", "CHANGED")
        return SIGNATURE

    result = capture_batch(
        spec,
        (binding(mutate),),
        transport=lambda *a, **k: dispatches.append(1),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert result.attempts[0].status is TargetStatus.INTEGRITY_FAILURE
    assert result.attempts[0].dispatch_count == 0
    assert not dispatches


def test_post_acquisition_mutation_preserves_trustworthy_facts_with_integrity_precedence(
    fixed_clock,
) -> None:
    original = polymarket_target()
    spec = specification(original)
    transport_result = complete_transport(polymarket_body())

    def mutate(*args, **kwargs):
        object.__setattr__(original, "identifier", "999")
        return transport_result

    result = capture_batch(spec, transport=mutate, observer_clock=fixed_clock)
    attempt = result.attempts[0]
    assert attempt.status is TargetStatus.INTEGRITY_FAILURE
    assert attempt.acquisition_outcome is AcquisitionOutcome.COMPLETED
    assert attempt.retained_body == polymarket_body()


def test_confidentiality_precedes_integrity_and_preserves_completion(fixed_clock) -> None:
    target = kalshi_target()
    spec = specification(target)
    response = TransportResult(
        TransportFailureKind.CONFIDENTIALITY,
        200,
        None,
        None,
        AcquisitionOutcome.COMPLETED,
        RetentionState.SUPPRESSED,
        12,
        None,
        None,
        "body",
    )

    def reflected(*args, **kwargs):
        object.__setattr__(target, "identifier", "CHANGED")
        return response

    result = capture_batch(
        spec,
        (binding(),),
        transport=reflected,
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    attempt = result.attempts[0]
    assert attempt.status is TargetStatus.CONFIDENTIALITY_FAILURE
    assert attempt.normal_completion is True
    assert attempt.retained_body is None


def test_contradictory_transport_material_causes_safe_outer_failure(fixed_clock) -> None:
    contradictory = TransportResult(
        None,
        200,
        3,
        "application/json",
        AcquisitionOutcome.COMPLETED,
        RetentionState.COMPLETE,
        3,
        b"abc",
        "wrong",
        None,
    )
    result = capture_batch(
        specification(polymarket_target()),
        transport=lambda *a, **k: contradictory,
        observer_clock=fixed_clock,
    )
    assert result.status is BatchStatus.INTEGRITY_FAILURE
    assert result.attempts == ()
    assert result.specification is None


def test_malformed_signer_result_does_not_dispatch_and_later_target_runs(fixed_clock) -> None:
    dispatched = []
    result = capture_batch(
        specification(kalshi_target(0), polymarket_target(1)),
        (binding(lambda _: "not-base64"),),
        transport=lambda target, *a, **k: (
            dispatched.append(target.position) or complete_transport(polymarket_body())
        ),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.SIGNING_FAILED,
        TargetStatus.CAPTURED,
    ]
    assert dispatched == [1]


def test_signer_mutation_wins_over_signer_exception(fixed_clock) -> None:
    target = kalshi_target()
    spec = specification(target)

    def mutate_then_fail(_: bytes) -> str:
        object.__setattr__(target, "identifier", "CHANGED")
        raise RuntimeError("secret")

    result = capture_batch(
        spec,
        (binding(mutate_then_fail),),
        transport=lambda *a, **k: complete_transport(kalshi_body()),
        observer_clock=fixed_clock,
        timestamp_factory=lambda: "1",
    )
    assert result.attempts[0].status is TargetStatus.INTEGRITY_FAILURE
    assert result.attempts[0].dispatch_count == 0


def test_integrity_after_partial_acquisition_preserves_exact_prefix(fixed_clock) -> None:
    target = polymarket_target()
    spec = specification(target)
    prefix = b"partial"
    response = TransportResult(
        TransportFailureKind.PARTIAL,
        200,
        None,
        "application/json",
        AcquisitionOutcome.PARTIAL,
        RetentionState.PARTIAL,
        len(prefix),
        prefix,
        hashlib.sha256(prefix).hexdigest(),
        None,
    )

    def mutate(*args, **kwargs):
        object.__setattr__(target, "identifier", "999")
        return response

    result = capture_batch(spec, transport=mutate, observer_clock=fixed_clock)
    attempt = result.attempts[0]
    assert attempt.status is TargetStatus.INTEGRITY_FAILURE
    assert attempt.acquisition_outcome is AcquisitionOutcome.PARTIAL
    assert attempt.retained_body == prefix


def test_complete_http_200_parser_failures_have_closed_precedence(fixed_clock) -> None:
    bodies = iter((b"\xff", b"{", b"{}", polymarket_body("999")))
    targets = tuple(polymarket_target(index, str(index + 1)) for index in range(4))
    result = capture_batch(
        specification(*targets),
        transport=lambda *a, **k: complete_transport(next(bodies)),
        observer_clock=fixed_clock,
    )
    assert [attempt.status for attempt in result.attempts] == [
        TargetStatus.UTF8_INVALID,
        TargetStatus.JSON_INVALID,
        TargetStatus.SCHEMA_INVALID,
        TargetStatus.IDENTIFIER_MISMATCH,
    ]
