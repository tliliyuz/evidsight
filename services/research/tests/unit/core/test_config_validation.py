"""配置校验测试 —— 租约时间关系（RESEARCH_PIPELINE §13.1）。"""

import pytest
from app.config import Settings


def test_租约间隔约束_续租周期不小于租约一半时拒绝():
    """续租周期必须 < 租约时长 / 2（§13.1），违反则配置加载失败（fail-fast）。"""
    with pytest.raises(ValueError, match="RESEARCH_TASK_LEASE_RENEW_INTERVAL"):
        Settings(
            RESEARCH_TASK_LEASE_TTL_SECONDS=100,
            RESEARCH_TASK_LEASE_RENEW_INTERVAL=60,  # 60 >= 100/2 → 拒绝
        )


def test_租约间隔约束_扫描间隔大于租约时长时拒绝():
    """Recovery Scanner 扫描间隔必须 <= 租约时长（§13.1）。"""
    with pytest.raises(ValueError, match="RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS"):
        Settings(
            RESEARCH_TASK_LEASE_TTL_SECONDS=100,
            RESEARCH_TASK_LEASE_RENEW_INTERVAL=40,
            RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS=101,  # 101 > 100 → 拒绝
        )


def test_租约间隔约束_合法组合通过():
    """合法组合：续租 < 租约/2 且扫描间隔 <= 租约。"""
    settings = Settings(
        RESEARCH_TASK_LEASE_TTL_SECONDS=300,
        RESEARCH_TASK_LEASE_RENEW_INTERVAL=60,
        RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS=60,
    )
    assert settings.RESEARCH_TASK_LEASE_TTL_SECONDS == 300
    assert settings.RESEARCH_TASK_LEASE_RENEW_INTERVAL == 60
    assert settings.RESEARCH_RECOVERY_SCAN_INTERVAL_SECONDS == 60


def test_LLM额外请求头_JSON配置可选且默认为空(monkeypatch):
    """Provider 专用请求头不配置时为空，配置后按 JSON 对象读取。"""
    monkeypatch.delenv("LLM_EXTRA_HEADERS_JSON", raising=False)
    default_settings = Settings(_env_file=None)
    assert default_settings.LLM_EXTRA_HEADERS_JSON == {}

    monkeypatch.setenv(
        "LLM_EXTRA_HEADERS_JSON",
        '{"x-opencode-session":"evidsight-{task_id}"}',
    )
    configured = Settings(_env_file=None)
    assert configured.LLM_EXTRA_HEADERS_JSON == {"x-opencode-session": "evidsight-{task_id}"}
