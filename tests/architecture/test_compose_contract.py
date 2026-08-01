from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _compose(name: str = "docker-compose.yml"):
    return yaml.safe_load((ROOT / name).read_text())


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
