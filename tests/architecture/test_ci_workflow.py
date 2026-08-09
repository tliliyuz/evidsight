"""基础 CI workflow 架构验收。

验收条件来自 TESTING §2.1/§4 与 TEST_EXECUTION §1.1：六个只读 required
checks、受保护分支触发、过时运行取消，以及不启动全栈数据服务。
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
EXPECTED_JOBS = {
    "python-quality",
    "backend-fast-unit",
    "contracts",
    "architecture-compose",
    "openapi",
    "web",
}
FORBIDDEN_WRITES = (
    "--fix",
    "--write",
    "git commit",
    "git push",
    "git add",
)


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.is_file(), "缺少基础 CI workflow：.github/workflows/ci.yml"
    # BaseLoader 保留 GitHub Actions 的 `on` 键，避免 YAML 1.1 将其解析为布尔值。
    workflow = yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return workflow


def _job_commands(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job.get("steps", []) if isinstance(step, dict))


def test_ci_has_six_read_only_required_checks():
    workflow = _load_workflow()

    assert workflow.get("permissions") == {"contents": "read"}
    assert set(workflow.get("jobs", {})) == EXPECTED_JOBS
    assert workflow.get("concurrency", {}).get("cancel-in-progress") == "true"

    for job_name, job in workflow["jobs"].items():
        assert "services" not in job, f"基础 CI job {job_name} 不得启动全栈数据服务"
        commands = _job_commands(job)
        for forbidden in FORBIDDEN_WRITES:
            assert forbidden not in commands, f"基础 CI 禁止写操作：{job_name} 包含 {forbidden}"


def test_ci_triggers_protected_branch_prs_and_pushes():
    workflow = _load_workflow()
    triggers = workflow.get("on", {})

    for event in ("pull_request", "push"):
        branches = triggers.get(event, {}).get("branches", [])
        assert {"main", "dev"}.issubset(set(branches)), f"{event} 必须覆盖 main/dev"


def test_ci_jobs_call_the_registered_read_only_entrypoints():
    jobs = _load_workflow()["jobs"]

    python_commands = _job_commands(jobs["python-quality"])
    assert "ruff check" in python_commands
    assert "ruff format --check" in python_commands
    assert "scripts/check_python_types.sh" in python_commands

    assert "scripts/test_fast_unit.sh" in _job_commands(jobs["backend-fast-unit"])
    assert "scripts/test_contracts_ci.sh" in _job_commands(jobs["contracts"])

    architecture_commands = _job_commands(jobs["architecture-compose"])
    assert "tests/architecture" in architecture_commands
    assert "docker compose config --quiet" in architecture_commands

    assert "scripts/check_openapi_ci.sh" in _job_commands(jobs["openapi"])

    web_commands = _job_commands(jobs["web"])
    for command in (
        "install --frozen-lockfile",
        "run lint",
        "run format:check",
        "test",
        "run build",
    ):
        assert command in web_commands


def test_python_ci_uses_frozen_hashed_service_dependencies():
    setup_script = (ROOT / "scripts" / "setup_python_dev.sh").read_text(encoding="utf-8")
    dockerfile = (ROOT / "services" / "knowledge" / "Dockerfile").read_text(encoding="utf-8")

    for service in ("knowledge", "research"):
        lock_path = ROOT / "services" / service / "requirements-dev.lock"
        assert lock_path.is_file(), f"缺少 {service} 开发依赖锁文件"
        lock_text = lock_path.read_text(encoding="utf-8")
        assert "--hash=sha256:" in lock_text

    assert "requirements-dev.lock" in setup_script
    assert "--require-hashes" in setup_script
    assert "FROM python:3.12-slim AS ci-test" in dockerfile
    assert "pip install --no-cache-dir --require-hashes -r requirements-dev.lock" in dockerfile
