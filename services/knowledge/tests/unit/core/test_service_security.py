"""Service JWT 验证单测 — 对齐 CONFIGURATION.md §3、API.md §11.1"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.config import settings
from app.core.service_security import verify_service_token


def _make_keypair(tmp_path, kid="test-kid"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    keys_file = tmp_path / "public_keys.json"
    keys_file.write_text(json.dumps({kid: public_pem}), encoding="utf-8")
    return {"kid": kid, "private_pem": private_pem, "public_pem": public_pem}


def _sign(private_pem, kid, *, issuer=None, audience=None, sub="research-service",
          token_type="service", ttl=60, iat=None, exp=None):
    issuer = issuer or settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER
    audience = audience or settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE
    now = iat or datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": sub,
        "token_type": token_type,
        "jti": "test-jti",
        "iat": now,
        "nbf": now,
        "exp": exp or (now + timedelta(seconds=ttl)),
    }
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def keys(tmp_path, monkeypatch):
    kp = _make_keypair(tmp_path)
    monkeypatch.setattr(
        settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", str(tmp_path / "public_keys.json")
    )
    return kp


class TestVerifyServiceToken:
    def test_valid_service_token_passes(self, keys):
        token = _sign(keys["private_pem"], keys["kid"])
        payload = verify_service_token(token)
        assert payload and payload["sub"] == "research-service"
        assert payload["token_type"] == "service"

    def test_wrong_signature_rejected(self, keys, tmp_path):
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other = _make_keypair(other_dir, keys["kid"])
        token = _sign(other["private_pem"], other["kid"])
        assert verify_service_token(token) == {}

    def test_unknown_kid_rejected(self, keys):
        token = _sign(keys["private_pem"], "unknown-kid")
        assert verify_service_token(token) == {}

    def test_wrong_issuer_rejected(self, keys):
        token = _sign(keys["private_pem"], keys["kid"], issuer="evil-platform")
        assert verify_service_token(token) == {}

    def test_wrong_audience_rejected(self, keys):
        token = _sign(keys["private_pem"], keys["kid"], audience="evil-audience")
        assert verify_service_token(token) == {}

    def test_user_token_type_rejected(self, keys):
        token = _sign(keys["private_pem"], keys["kid"], token_type="access")
        assert verify_service_token(token) == {}

    def test_expired_token_rejected(self, keys):
        past = datetime.now(timezone.utc) - timedelta(seconds=120)
        token = _sign(keys["private_pem"], keys["kid"], iat=past - timedelta(seconds=60), exp=past)
        assert verify_service_token(token) == {}
