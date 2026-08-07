"""Knowledge Service 契约测试共享配置：复用 packages/contracts 的 loader。"""

import sys
from pathlib import Path


def _find_contracts_root() -> Path:
    """从本文件所在目录向上定位 packages/contracts 目录（兼容宿主机与容器内路径）。"""
    start = Path(__file__).resolve().parent
    for parent in [start] + list(start.parents):
        candidate = parent / "packages" / "contracts"
        if candidate.is_dir() and (candidate / "schemas" / "v1").is_dir():
            return candidate
    raise RuntimeError("无法定位 packages/contracts 目录")


_GENERATED_PY = _find_contracts_root() / "generated" / "python"
if str(_GENERATED_PY) not in sys.path:
    sys.path.insert(0, str(_GENERATED_PY))
