from __future__ import annotations

import base64
from dataclasses import replace

import pytest

from conftest import SIGNATURE, kalshi_target, polymarket_target
from invariant_engine.capture import (
    AuthenticationBindingError,
    CaptureEnvironment,
    KalshiAuthenticationBinding,
    SigningError,
    sign_target,
    validate_authentication_bindings,
)
from invariant_engine.capture.specification import KALSHI_DEMO_ORIGIN


def binding(signer=lambda message: SIGNATURE) -> KalshiAuthenticationBinding:
    return KalshiAuthenticationBinding(
        CaptureEnvironment.DEMO,
        KALSHI_DEMO_ORIGIN,
        "key-1",
        signer,
    )


def test_exact_signing_bytes_and_headers() -> None:
    messages: list[bytes] = []
    signed = sign_target(
        kalshi_target(), binding(lambda value: messages.append(value) or SIGNATURE), "1234"
    )
    assert messages == [b"1234GET/trade-api/v2/markets/TEST-1/orderbook"]
    assert signed.headers == (
        ("KALSHI-ACCESS-KEY", "key-1"),
        ("KALSHI-ACCESS-TIMESTAMP", "1234"),
        ("KALSHI-ACCESS-SIGNATURE", SIGNATURE),
    )


def rendered_forms(value: object) -> tuple[str, ...]:
    return (
        repr(value),
        str(value),
        format(value),
        f"{value}",
        f"{value!r}",
        repr([value]),
        repr((value,)),
        repr({"value": value}),
        repr({value}),
    )


def test_authentication_representations_are_fixed_and_do_not_format_signer() -> None:
    class SecretSigner:
        repr_calls = 0

        def __call__(self, _: bytes) -> str:
            return SIGNATURE

        def __repr__(self) -> str:
            self.repr_calls += 1
            return "synthetic-signer-secret"

    signer = SecretSigner()
    value = binding(signer)
    assert value.key_id == "key-1"
    assert value.signer is signer
    assert repr(value) == "KalshiAuthenticationBinding(<redacted>)"
    for rendered in rendered_forms(value):
        assert "key-1" not in rendered
        assert "synthetic-signer-secret" not in rendered
        assert SIGNATURE not in rendered
    assert signer.repr_calls == 0


def test_authentication_representations_tolerate_raising_signer_repr() -> None:
    class RaisingSigner:
        def __call__(self, _: bytes) -> str:
            return SIGNATURE

        def __repr__(self) -> str:
            raise RuntimeError("synthetic-repr-secret")

    value = binding(RaisingSigner())
    assert all("synthetic-repr-secret" not in rendered for rendered in rendered_forms(value))


def test_signed_header_representations_are_fixed_while_fields_remain_accessible() -> None:
    signed = sign_target(kalshi_target(), binding(), "1234")
    assert signed.timestamp == "1234"
    assert signed.method == "GET"
    assert signed.path == "/trade-api/v2/markets/TEST-1/orderbook"
    assert signed.headers[0] == ("KALSHI-ACCESS-KEY", "key-1")
    assert signed.headers[2] == ("KALSHI-ACCESS-SIGNATURE", SIGNATURE)
    assert repr(signed) == "SignedHeaders(<redacted>)"
    for rendered in rendered_forms(signed):
        assert "key-1" not in rendered
        assert SIGNATURE not in rendered
        assert "1234" not in rendered


@pytest.mark.parametrize(
    "signature",
    ["", "abcd", base64.urlsafe_b64encode(b"\xfb" * 128).decode(), SIGNATURE + "\n", "é"],
)
def test_signature_contract(signature: str) -> None:
    with pytest.raises(SigningError) as caught:
        sign_target(kalshi_target(), binding(lambda _: signature), "1")
    assert str(caught.value) == "signer returned an invalid signature"


def test_signer_exception_text_is_not_exposed() -> None:
    sentinel = RuntimeError("secret-reflection")

    def fail(_: bytes) -> str:
        raise sentinel

    with pytest.raises(SigningError) as caught:
        sign_target(kalshi_target(), binding(fail), "1")
    error = caught.value
    assert str(error) == "caller signer failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert sentinel.__traceback__ is not None


def test_nested_signer_exception_chain_is_detached_without_mutating_it() -> None:
    inner = ValueError("synthetic-inner-secret")
    outer = RuntimeError("synthetic-outer-secret")

    def fail(_: bytes) -> str:
        try:
            raise inner
        except ValueError:
            raise outer from inner

    with pytest.raises(SigningError) as caught:
        sign_target(kalshi_target(), binding(fail), "1")

    error = caught.value
    assert str(error) == "caller signer failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert outer.__cause__ is inner
    assert outer.__context__ is inner
    assert outer.__traceback__ is not None
    assert inner.__traceback__ is not None


def test_bindings_must_exactly_match_required_environments() -> None:
    assert validate_authentication_bindings((kalshi_target(),), (binding(),))
    for bindings in ((), (binding(), binding()), (binding(), replace(binding(), key_id="bad key"))):
        with pytest.raises(AuthenticationBindingError):
            validate_authentication_bindings((kalshi_target(),), bindings)
    with pytest.raises(AuthenticationBindingError):
        validate_authentication_bindings((polymarket_target(),), (binding(),))


def test_key_id_and_timestamp_boundaries_are_exact() -> None:
    assert sign_target(kalshi_target(), replace(binding(), key_id="k" * 256), "9" * 20)
    for key_id in ("", "k" * 257, "bad key", "é"):
        with pytest.raises(AuthenticationBindingError):
            validate_authentication_bindings(
                (kalshi_target(),),
                (replace(binding(), key_id=key_id),),
            )
    with pytest.raises(AuthenticationBindingError):
        sign_target(kalshi_target(), binding(), "1" * 21)
