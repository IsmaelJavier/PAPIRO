from types import SimpleNamespace

import jwt
import pytest

from app.auth import create_access_token, hash_password, verify_password
from app.config import settings


def test_password_hashing_and_verification():
    encoded = hash_password("a-long-password-for-tests")
    assert encoded != "a-long-password-for-tests"
    assert verify_password("a-long-password-for-tests", encoded)
    assert not verify_password("wrong-password", encoded)


def test_short_password_is_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


def test_access_token_has_subject_and_expiry(monkeypatch):
    monkeypatch.setattr(settings, "auth_secret_key", "t" * 64)
    monkeypatch.setattr(settings, "auth_token_ttl_minutes", 15)
    token, ttl = create_access_token(SimpleNamespace(id="user-123"))
    claims = jwt.decode(token, "t" * 64, algorithms=["HS256"])
    assert claims["sub"] == "user-123"
    assert claims["exp"] > claims["iat"]
    assert ttl == 900
