from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_target_layout_exists():
    required = [
        "apps/web/package.json",
        "services/knowledge/app/main.py",
        "services/knowledge/alembic.ini",
        "services/research/app/main.py",
        "services/research/alembic.ini",
        "packages/contracts/README.md",
        "docker-compose.yml",
        "deploy/nginx/default.conf",
    ]
    assert all((ROOT / path).is_file() for path in required)


def test_no_second_runnable_frontend_exists():
    package_files = sorted(ROOT.glob("**/package.json"))
    ignored_parts = {"node_modules", ".worktrees"}
    tracked = [path for path in package_files if ignored_parts.isdisjoint(path.parts)]
    assert tracked == [ROOT / "apps/web/package.json"]


def test_migration_scratch_tree_is_gone():
    assert not (ROOT / ".migration").exists()
