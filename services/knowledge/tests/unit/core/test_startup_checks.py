"""启动配置校验单测 — app.core.startup_checks.validate_production_config

对齐 CONFIGURATION.md 生产必填项（I2）：AUTH_ALLOWED_ORIGINS 生产必填、
Service 公钥文件可加载；DEBUG=True 不阻断开发迭代。
"""
import json

from app.config import settings
from app.core.startup_checks import validate_production_config


def _write_keys(tmp_path):
    f = tmp_path / "public_keys.json"
    f.write_text(json.dumps({"kid": "PEM"}), encoding="utf-8")
    return str(f)


class TestValidateProductionConfig:
    def test_DEBUG模式_不阻断(self, monkeypatch):
        monkeypatch.setattr(settings, "DEBUG", True)
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        monkeypatch.setattr(settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", "")
        assert validate_production_config() == []

    def test_生产_空origins与坏keys_返回两项错误(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "")
        monkeypatch.setattr(
            settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE",
            str(tmp_path / "missing.json"),
        )
        errors = validate_production_config()
        assert any("AUTH_ALLOWED_ORIGINS" in e for e in errors)
        assert any("PUBLIC_KEYS_FILE" in e for e in errors)

    def test_生产_配置齐全_返回空(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "DEBUG", False)
        monkeypatch.setattr(
            settings, "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS", "https://app.evidsight.cn",
        )
        monkeypatch.setattr(
            settings, "EVIDSIGHT_KNOWLEDGE_SERVICE_JWT_PUBLIC_KEYS_FILE", _write_keys(tmp_path),
        )
        assert validate_production_config() == []
