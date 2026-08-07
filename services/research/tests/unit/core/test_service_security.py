"""Research Service JWT 签发单测 — 载荷对齐 CONFIGURATION.md §3"""

import pytest
from app.config import settings
from app.core.service_security import create_service_token
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt


@pytest.fixture
def keypair(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    priv_file = tmp_path / "private.pem"
    priv_file.write_text(private_pem, encoding="utf-8")
    monkeypatch.setattr(settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_ACTIVE_KID", "test-kid")
    monkeypatch.setattr(settings, "EVIDSIGHT_RESEARCH_SERVICE_JWT_PRIVATE_KEY_FILE", str(priv_file))
    monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS", 60)
    return private_pem, public_pem


class TestCreateServiceToken:
    def test_creates_valid_rs256_token(self, keypair):
        private_pem, public_pem = keypair
        token = create_service_token()
        headers = jwt.get_unverified_headers(token)
        assert headers["alg"] == "RS256"
        assert headers["kid"] == "test-kid"

        payload = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            audience=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE,
            issuer=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_ISSUER,
        )
        assert payload["sub"] == "research-service"
        assert payload["token_type"] == "service"
        assert payload["jti"]

    def test_ttl_within_configured_range(self, keypair):
        private_pem, public_pem = keypair
        token = create_service_token()
        payload = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            audience=settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_AUDIENCE,
        )

        exp = payload["exp"]
        iat = payload["iat"]
        ttl = exp - iat
        assert 10 <= ttl <= 300
        assert ttl == settings.EVIDSIGHT_PLATFORM_SERVICE_JWT_TTL_SECONDS
