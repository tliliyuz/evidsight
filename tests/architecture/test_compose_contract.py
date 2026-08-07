import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# 统一身份平台命名空间键（CONFIGURATION.md §3.1），由 Knowledge Service 消费。
PLATFORM_IDENTITY_KEYS = {
    "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_NAME",
    "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_PATH",
    "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SECURE",
    "EVIDSIGHT_PLATFORM_REFRESH_COOKIE_SAMESITE",
    "EVIDSIGHT_PLATFORM_CSRF_COOKIE_NAME",
    "EVIDSIGHT_PLATFORM_AUTH_ALLOWED_ORIGINS",
    "EVIDSIGHT_PLATFORM_AUTH_BODY_REFRESH_COMPAT",
}

# 各服务 Redis/Celery 独立 URL，根 .env 以此名覆盖（compose anchor 内插值到 REDIS_URL/CELERY_*）。
SERVICE_REDIS_CELERY_KEYS = {
    "KNOWLEDGE_REDIS_URL",
    "KNOWLEDGE_CELERY_BROKER_URL",
    "KNOWLEDGE_CELERY_RESULT_BACKEND",
    "RESEARCH_REDIS_URL",
    "RESEARCH_CELERY_BROKER_URL",
    "RESEARCH_CELERY_RESULT_BACKEND",
}


def _compose(name: str = "docker-compose.yml"):
    return yaml.safe_load((ROOT / name).read_text())


def _compose_raw(name: str = "docker-compose.yml") -> str:
    return (ROOT / name).read_text()


def _example_env_keys() -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    }


def _nginx_location(marker: str) -> str:
    config = (ROOT / "deploy/nginx/default.conf").read_text()
    match = re.search(rf"    location {re.escape(marker)} \{{\n(.*?)\n    \}}", config, re.DOTALL)
    assert match is not None, f"missing nginx location: {marker}"
    return match.group(1)


def test_required_services_and_external_port_boundary():
    services = _compose()["services"]
    expected = {
        "nginx",
        "mysql",
        "redis",
        "knowledge-api",
        "knowledge-worker",
        "research-api",
        "research-worker",
        "research-beat",
    }
    assert expected <= services.keys()
    assert services["nginx"]["ports"] == ["80:80"]
    for name in expected - {"nginx"}:
        assert "ports" not in services[name]


def test_workers_use_explicit_queues():
    services = _compose()["services"]
    knowledge = " ".join(services["knowledge-worker"]["command"])
    research = " ".join(services["research-worker"]["command"])
    assert "knowledge.ingest,knowledge.delete" in knowledge
    assert "research.execute,research.periodic" in research


def test_development_compose_has_no_hard_memory_limits():
    for service in _compose()["services"].values():
        assert "mem_limit" not in service


def test_production_overlay_defines_2c2g_memory_budget():
    services = _compose("docker-compose.prod.yml")["services"]
    expected = {
        "knowledge-api": "256m",
        "knowledge-worker": "320m",
        "research-api": "256m",
        "research-worker": "320m",
        "research-beat": "64m",
        "mysql": "448m",
        "redis": "96m",
    }
    assert {name: services[name]["mem_limit"] for name in expected} == expected


def test_provider_settings_are_passed_to_the_correct_services():
    compose = _compose()
    knowledge = compose["x-knowledge-environment"]
    research = compose["x-research-environment"]

    assert {
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_FLASH_MODEL",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "RERANK_BASE_URL",
        "RERANK_API_KEY",
        "RERANK_MODEL",
    } <= knowledge.keys()
    assert {
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_FLASH_MODEL",
        "TAVILY_BASE_URL",
        "TAVILY_API_KEY",
    } <= research.keys()


def test_knowledge_clean_settings_are_passed_to_knowledge_only():
    compose = _compose()
    knowledge = compose["x-knowledge-environment"]
    research = compose["x-research-environment"]
    expected = {
        "CLEAN_ENABLED",
        "CLEAN_STRIP_BOILERPLATE",
        "CLEAN_NORMALIZE_WHITESPACE",
        "CLEAN_REPAIR_UNICODE",
    }

    assert expected <= knowledge.keys()
    assert research.keys().isdisjoint(expected)


def test_platform_identity_settings_are_passed_to_knowledge_only():
    """Refresh Cookie/CSRF 与 Origin 白名单由 Knowledge 消费，不得注入 Research。"""
    compose = _compose()
    knowledge = compose["x-knowledge-environment"]
    research = compose["x-research-environment"]

    assert PLATFORM_IDENTITY_KEYS <= knowledge.keys()
    assert research.keys().isdisjoint(PLATFORM_IDENTITY_KEYS)


def test_example_env_contains_platform_identity_keys():
    """根 .env.example 必须登记统一身份平台命名空间键，作为 compose 覆盖入口。"""
    keys = _example_env_keys()

    assert PLATFORM_IDENTITY_KEYS <= keys


def test_redis_and_celery_urls_are_interpolated_per_service():
    """根 .env 的 KNOWLEDGE_*/RESEARCH_* Redis/Celery 键必须被 compose 插值引用。"""
    text = _compose_raw()

    for key in SERVICE_REDIS_CELERY_KEYS:
        assert f"${{{key}:-" in text, f"{key} 未被 compose 引用"


def test_example_env_matches_the_provider_compose_contract():
    keys = _example_env_keys()
    required = {
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_FLASH_MODEL",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "RERANK_BASE_URL",
        "RERANK_API_KEY",
        "RERANK_MODEL",
        "CLEAN_ENABLED",
        "CLEAN_STRIP_BOILERPLATE",
        "CLEAN_NORMALIZE_WHITESPACE",
        "CLEAN_REPAIR_UNICODE",
        "TAVILY_BASE_URL",
        "TAVILY_API_KEY",
    }
    unused = {
        "KNOWLEDGE_DATABASE_URL",
        "RESEARCH_DATABASE_URL",
        "EVIDSIGHT_IMAGE_VERSION",
        "BACKUP_PATH",
    }

    assert required <= keys
    assert keys.isdisjoint(unused)


def test_legacy_research_task_routes_preserve_their_original_path():
    exact = _nginx_location("= /api/research")
    nested = _nginx_location("^~ /api/research/")

    assert "proxy_pass http://research-api:8000;" in exact
    assert "proxy_pass http://research-api:8000;" in nested
    assert "rewrite " not in exact
    assert "rewrite " not in nested


def test_namespaced_research_support_routes_map_to_legacy_service_paths():
    health = _nginx_location("= /api/research/health")
    workers = _nginx_location("= /api/research/health/workers")
    auth = _nginx_location("^~ /api/research/auth/")

    assert "proxy_pass http://research-api:8000/api/health;" in health
    assert "proxy_pass http://research-api:8000/api/health/workers;" in workers
    assert "rewrite ^/api/research/auth/(.*)$ /api/auth/$1 break;" in auth
