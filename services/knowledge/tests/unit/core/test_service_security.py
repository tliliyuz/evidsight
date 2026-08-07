"""Service JWT 验证单测 — 对齐 CONFIGURATION.md §3、API.md §11.1"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.config import settings
from app.core.service_security import public_keys_loadable, verify_service_token


def _generate_keypair(kid="test-kid"):
    """生成 RSA 密钥对，返回 {"kid", "private_pem", "public_pem"}，不写文件。"""
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
    return {"kid": kid, "private_pem": private_pem, "public_pem": public_pem}


def _write_keys_file(keys_file, keypairs):
    """把多个 keypair 写入 JSON 映射 {"<kid>": "<PEM>"}，供轮换窗口测试使用。"""
    keys_file.write_text(
        json.dumps({kp["kid"]: kp["public_pem"] for kp in keypairs}),
        encoding="utf-8",
    )


def _make_keypair(tmp_path, kid="test-kid"):
    kp = _generate_keypair(kid)
    keys_file = tmp_path / "public_keys.json"
    keys_file.write_text(json.dumps({kid: kp["public_pem"]}), encoding="utf-8")
    return kp


def _sign(
    private_pem,
    kid,
    *,
    issuer=None,
    audience=None,
    sub="research-service",
    token_type="service",
    ttl=60,
    iat=None,
    exp=None,
):
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
        settings,
        "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
        str(tmp_path / "public_keys.json"),
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


class TestServiceKeyRotation:
    """IA-010 签名密钥轮换：窗口内新旧 Token 均可按 Key ID 验证，窗口后旧 Key 失效。

    对齐 IDENTITY_AND_ACCESS.md §12 密钥轮换、兼容与失败：
    - 轮换先发布新验证材料，再切换签发，等待旧 Token 最大有效期结束后移除旧材料；
    - JWT 签名密钥支持 Key ID，并允许受控的双 Key 验证窗口。
    """

    def test_rotation_window_both_keys_verifiable(self, tmp_path, monkeypatch):
        """窗口内：keys 文件同时含新旧两个公钥，新旧 Token 均验证通过。"""
        old = _generate_keypair("kid-old")
        new = _generate_keypair("kid-new")
        keys_file = tmp_path / "public_keys.json"
        _write_keys_file(keys_file, [old, new])
        monkeypatch.setattr(
            settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", str(keys_file)
        )

        old_token = _sign(old["private_pem"], old["kid"])
        new_token = _sign(new["private_pem"], new["kid"])

        assert verify_service_token(old_token)["sub"] == "research-service"
        assert verify_service_token(new_token)["sub"] == "research-service"

    def test_rotation_window_expired_old_key_rejected(self, tmp_path, monkeypatch):
        """窗口后：移除旧公钥，旧 Key 签发的 Token 验证失败，新 Key 仍有效。"""
        old = _generate_keypair("kid-old")
        new = _generate_keypair("kid-new")
        keys_file = tmp_path / "public_keys.json"
        _write_keys_file(keys_file, [old, new])
        monkeypatch.setattr(
            settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", str(keys_file)
        )

        old_token = _sign(old["private_pem"], old["kid"])
        new_token = _sign(new["private_pem"], new["kid"])

        # 窗口结束：仅保留新公钥，移除旧 Key 验证材料
        _write_keys_file(keys_file, [new])

        assert verify_service_token(old_token) == {}
        assert verify_service_token(new_token)["sub"] == "research-service"

    def test_rotation_window_new_key_active_kid_changes(self, tmp_path, monkeypatch):
        """切换签发侧：Research 用新 ACTIVE_KID 签发，验证仍按该 kid 通过。"""
        old = _generate_keypair("kid-old")
        new = _generate_keypair("kid-new")
        keys_file = tmp_path / "public_keys.json"
        _write_keys_file(keys_file, [old, new])
        monkeypatch.setattr(
            settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", str(keys_file)
        )

        # Research 切换签发密钥：ACTIVE_KID 指向新 Key
        new_token = _sign(new["private_pem"], new["kid"])
        assert verify_service_token(new_token)["sub"] == "research-service"


class TestPublicKeysLoadable:
    """public_keys_loadable — 启动 fail-fast / readiness 的键文件可加载检查"""

    def test_空路径_返回False(self, monkeypatch):
        monkeypatch.setattr(settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", "")
        assert public_keys_loadable() is False

    def test_文件不存在_返回False(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            settings,
            "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
            str(tmp_path / "missing.json"),
        )
        assert public_keys_loadable() is False

    def test_合法文件_返回True(self, keys):
        assert public_keys_loadable() is True
