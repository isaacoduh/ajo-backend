from typing import Any

import pytest
from app.modules.payments import truelayer_signing
from app.modules.payments.truelayer_signing import (
    build_signed_empty_request,
    build_signed_json_request,
)
from truelayer_signing import HttpMethod


class RecordingSigner:
    def __init__(self) -> None:
        self.method: HttpMethod | None = None
        self.path: str | None = None
        self.headers: dict[str, str] = {}
        self.body: str | None = None

    def set_method(self, method: HttpMethod) -> "RecordingSigner":
        self.method = method
        return self

    def set_path(self, path: str) -> "RecordingSigner":
        self.path = path
        return self

    def add_header(self, name: str, value: str) -> "RecordingSigner":
        self.headers[name] = value
        return self

    def set_body(self, body: str) -> "RecordingSigner":
        self.body = body
        return self

    def sign(self) -> str:
        return "signed-test-value"


def test_build_signed_json_request_reuses_exact_body_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = RecordingSigner()

    def fake_sign_with_pem(kid: str, private_key_pem: str) -> RecordingSigner:
        assert kid == "kid-test"
        assert private_key_pem == "private-key-test"
        return signer

    monkeypatch.setattr(truelayer_signing, "sign_with_pem", fake_sign_with_pem)
    payload: dict[str, Any] = {
        "amount_in_minor": 1234,
        "currency": "GBP",
        "metadata": {"idempotency_key": "tl-key-1"},
    }

    signed = build_signed_json_request(
        kid="kid-test",
        private_key_pem="private-key-test",
        method=HttpMethod.POST,
        path="/payments",
        payload=payload,
        idempotency_key="tl-key-1",
    )

    assert signed.body == (
        b'{"amount_in_minor":1234,"currency":"GBP",'
        b'"metadata":{"idempotency_key":"tl-key-1"}}'
    )
    assert signer.method == HttpMethod.POST
    assert signer.path == "/payments"
    assert signer.headers == {"Idempotency-Key": "tl-key-1"}
    assert signer.body == signed.body.decode("utf-8")
    assert signed.headers == {
        "Content-Type": "application/json",
        "Idempotency-Key": "tl-key-1",
        "Tl-Signature": "signed-test-value",
    }


def test_build_signed_json_request_rejects_full_url_path() -> None:
    with pytest.raises(ValueError, match="must not include scheme or host"):
        build_signed_json_request(
            kid="kid-test",
            private_key_pem="private-key-test",
            method=HttpMethod.POST,
            path="https://api.truelayer-sandbox.com/payments",
            payload={},
            idempotency_key="tl-key-1",
        )


def test_build_signed_empty_request_signs_empty_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = RecordingSigner()

    def fake_sign_with_pem(kid: str, private_key_pem: str) -> RecordingSigner:
        assert kid == "kid-test"
        assert private_key_pem == "private-key-test"
        return signer

    monkeypatch.setattr(truelayer_signing, "sign_with_pem", fake_sign_with_pem)

    signed = build_signed_empty_request(
        kid="kid-test",
        private_key_pem="private-key-test",
        method=HttpMethod.GET,
        path="/v3/payments/pay_test",
        idempotency_key="tl-get-key-1",
        extra_headers={"Authorization": "Bearer access-token"},
    )

    assert signed.body == b""
    assert signer.method == HttpMethod.GET
    assert signer.path == "/v3/payments/pay_test"
    assert signer.headers == {"Idempotency-Key": "tl-get-key-1"}
    assert signer.body == ""
    assert signed.headers == {
        "Authorization": "Bearer access-token",
        "Idempotency-Key": "tl-get-key-1",
        "Tl-Signature": "signed-test-value",
    }
