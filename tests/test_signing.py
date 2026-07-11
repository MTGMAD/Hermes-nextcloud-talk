from __future__ import annotations

import hashlib
import hmac

import pytest

from hermes_nextcloud_talk.signing import (
    SignatureError,
    verify_inbound_signature,
)

SECRET = "test-secret"
RANDOM = "r" * 64
BODY = b'{"type":"Create"}'


def signature(secret: str = SECRET, random: str = RANDOM, body: bytes = BODY) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        random.encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()


def test_accepts_valid_talk_hmac_signature() -> None:
    verify_inbound_signature(
        secret=SECRET,
        random_header=RANDOM,
        signature_header=signature(),
        body=BODY,
    )


def test_accepts_valid_signature_for_exact_received_random_value() -> None:
    short_random = "r"
    verify_inbound_signature(
        secret=SECRET,
        random_header=short_random,
        signature_header=signature(random=short_random),
        body=BODY,
    )


def test_accepts_uppercase_hex_signature() -> None:
    verify_inbound_signature(
        secret=SECRET,
        random_header=RANDOM,
        signature_header=signature().upper(),
        body=BODY,
    )


@pytest.mark.parametrize(
    ("random_header", "signature_header", "body"),
    [
        ("", signature(), BODY),
        (RANDOM, "", BODY),
        (RANDOM, "not-a-hex-signature", BODY),
        (RANDOM, signature(), b'{"type":"Delete"}'),
    ],
)
def test_rejects_missing_malformed_or_tampered_signature(
    random_header: str,
    signature_header: str,
    body: bytes,
) -> None:
    with pytest.raises(SignatureError):
        verify_inbound_signature(
            secret=SECRET,
            random_header=random_header,
            signature_header=signature_header,
            body=body,
        )
