"""JWT & 密码哈希单元测试"""

from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_hash_returns_bcrypt_string(self):
        result = hash_password("test123")
        assert result.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("test123")
        assert verify_password("test123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("test123")
        assert verify_password("wrong", hashed) is False

    def test_same_password_different_salt(self):
        h1 = hash_password("test123")
        h2 = hash_password("test123")
        assert h1 != h2

    def test_verify_empty_password(self):
        hashed = hash_password("test123")
        assert verify_password("", hashed) is False


class TestJWT:
    PLATFORM_USER_ID = "550e8400-e29b-41d4-a716-446655440000"

    def test_ia001_access_token包含统一身份必需claims(self):
        """防止签发器遗漏跨服务验证所需 Claim 或退回内部整数用户 ID。"""
        token = create_access_token(self.PLATFORM_USER_ID, "user")
        payload = decode_access_token(token)

        assert payload["iss"] == "evidsight"
        assert payload["aud"] == ["evidsight-knowledge", "evidsight-research"]
        assert payload["sub"] == self.PLATFORM_USER_ID
        assert payload["role"] == "user"
        assert payload["token_type"] == "access"
        assert isinstance(payload["jti"], str) and payload["jti"]
        assert all(name in payload for name in ("iat", "nbf", "exp"))

    def test_ia002_rejects_wrong_audience(self, monkeypatch):
        """防止 Knowledge 接受只签发给 Research 的 Access Token。"""
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-audience-secret")
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": "evidsight",
                "aud": ["evidsight-research"],
                "sub": self.PLATFORM_USER_ID,
                "role": "user",
                "token_type": "access",
                "jti": "knowledge-wrong-audience",
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(minutes=15),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        assert decode_access_token(token) == {}

    def test_ia002_rejects_non_uuid_subject(self, monkeypatch):
        """防止数据库内部整数 ID 再次成为跨服务身份。"""
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-subject-secret")
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": "evidsight",
                "aud": ["evidsight-knowledge", "evidsight-research"],
                "sub": "1",
                "role": "user",
                "token_type": "access",
                "jti": "knowledge-integer-sub",
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(minutes=15),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        assert decode_access_token(token) == {}

    def test_create_token_does_not_contain_username(self):
        """IA-013：Access Token 不得携带 username 等可派生展示字段。"""
        token = create_access_token(self.PLATFORM_USER_ID, "user")
        payload = decode_access_token(token)
        assert payload["sub"] == self.PLATFORM_USER_ID
        assert "username" not in payload
        assert payload["role"] == "user"
        assert "exp" in payload

    def test_decode_valid_token(self):
        token = create_access_token(self.PLATFORM_USER_ID, "admin")
        payload = decode_access_token(token)
        assert payload["role"] == "admin"

    def test_decode_invalid_token(self):
        payload = decode_access_token("invalid.token.here")
        assert payload == {}

    def test_decode_empty_string(self):
        payload = decode_access_token("")
        assert payload == {}

    def test_decode_garbled_text(self):
        payload = decode_access_token("这不是JWT")
        assert payload == {}

    def test_token_exp_uses_utc(self):
        """验证 token 过期时间在 now + TTL 附近（UTC）"""
        import time
        from app.config import settings

        token = create_access_token(self.PLATFORM_USER_ID, "user")
        payload = decode_access_token(token)
        expected_exp = int(time.time()) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        # 允许 5 秒误差（测试执行耗时）
        assert abs(payload["exp"] - expected_exp) < 5
