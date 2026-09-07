from __future__ import annotations

import pytest

from backend.utils.security import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("s3cret", rounds=4)
    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed)


def test_wrong_password_rejected():
    hashed = hash_password("s3cret", rounds=4)
    assert not verify_password("nope", hashed)


def test_empty_inputs_rejected():
    with pytest.raises(ValueError):
        hash_password("")
    assert not verify_password("", "whatever")
    assert not verify_password("x", "")
