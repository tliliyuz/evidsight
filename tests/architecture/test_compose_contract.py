from pathlib import Path

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
    assert "research.execute,research.recovery,research.periodic" in research


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
