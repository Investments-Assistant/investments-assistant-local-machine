"""Security contracts for dependency behavior used by retained adapters."""

import jwt
import pytest


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
def test_empty_hmac_jwk_cannot_be_used_to_verify_forged_tokens(algorithm):
    # GHSA-pxh4-856f-4h89: an empty JWK must fail before token verification.
    with pytest.raises(jwt.InvalidKeyError):
        jwt.PyJWK.from_dict({"kty": "oct", "k": "", "alg": algorithm})


def test_unverified_peek_cannot_disable_later_expiry_verification():
    # GHSA-gvp8-978c-rx2q: caller-owned options must survive an unverified peek.
    key = "synthetic-hmac-key-32-bytes-minimum-for-test"
    expired = jwt.encode({"exp": 1, "sub": "fixture"}, key, algorithm="HS256")
    options = {"verify_signature": False}
    jwt.decode(expired, options=options)
    assert options == {"verify_signature": False}
    options["verify_signature"] = True
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired, key, algorithms=["HS256"], options=options)
