from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_each_service_owns_its_build_context():
    for service in ("knowledge", "research"):
        root = ROOT / "services" / service
        assert (root / "Dockerfile").is_file()
        assert (root / "requirements.txt").is_file()
        assert (root / ".dockerignore").is_file()


def test_services_do_not_import_each_other_app_package():
    knowledge = "\n".join(
        p.read_text(errors="ignore")
        for p in (ROOT / "services/knowledge/app").rglob("*.py")
    )
    research = "\n".join(
        p.read_text(errors="ignore")
        for p in (ROOT / "services/research/app").rglob("*.py")
    )
    assert "services.research.app" not in knowledge
    assert "services.knowledge.app" not in research
