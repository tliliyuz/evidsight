from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _compose(name: str = "docker-compose.yml"):
    return yaml.safe_load((ROOT / name).read_text())


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
