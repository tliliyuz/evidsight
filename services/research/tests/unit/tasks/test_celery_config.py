"""Celery 队列路由配置测试。"""

import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.tasks.celery_app import celery_app


def test_research_tasks_are_routed_to_worker_queues():
    """所有 Research 任务必须投递到 Worker 实际监听的显式队列。

    契约断言：默认/路由队列必须是命名空间队列（禁止默认 ``celery``）；
    同时绑定 settings，避免“代码与配置自洽但测试硬编码”的假阳性。
    """
    assert celery_app.conf.task_default_queue == settings.CELERY_EXECUTE_QUEUE
    assert celery_app.conf.task_default_queue == "research.execute"
    assert celery_app.conf.task_routes == {
        "execute_research_task": {"queue": settings.CELERY_EXECUTE_QUEUE},
        "app.tasks.periodic.*": {"queue": settings.CELERY_PERIODIC_QUEUE},
    }
    assert celery_app.conf.task_routes["execute_research_task"]["queue"] == "research.execute"
    assert celery_app.conf.task_routes["app.tasks.periodic.*"]["queue"] == "research.periodic"


def test_execute_research_task_is_registered_by_celery_app_import():
    """`celery_app` 模块自身导入必须注册 `execute_research_task`（worker 契约）。

    Worker 以 `celery -A app.tasks.celery_app worker` 启动，只导入 `app.tasks.celery_app`；
    若该模块不直接/传递注册 `execute_research_task`，消息会因「未注册任务」被丢弃。
    回归：`91ede60`（ruff 一次性清理）把副作用导入 `import app.tasks.research_task`
    当作 F401「未使用」误删（收到 unregistered task of type 'execute_research_task'）。

    用子进程隔离：pytest 的 `unit/conftest.py` 会经 `app.api.research` 间接导入
    `research_task` 而掩盖本缺陷，因此必须只在干净进程里 import `celery_app` 验证。
    """
    root = Path(__file__).resolve().parents[3]  # services/research
    code = (
        "from app.tasks.celery_app import celery_app; "
        "print('execute_research_task' in celery_app.tasks)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout
