"""契约测试共享配置：加载 loader 并暴露 Schema/Fixture 目录与加载函数。"""

import sys
from pathlib import Path

# 将 generated/python 加入 sys.path，复用 evidsight_contracts.loader（避免复制逻辑）
_GENERATED_PY = Path(__file__).resolve().parents[1] / "generated" / "python"
if str(_GENERATED_PY) not in sys.path:
    sys.path.insert(0, str(_GENERATED_PY))

from evidsight_contracts.loader import (  # noqa: E402
    REPO_ROOT,
    list_fixtures,
    load_fixture,
    load_schema,
)

SCHEMAS_DIR = REPO_ROOT / "packages" / "contracts" / "schemas" / "v1"
FIXTURES_DIR = REPO_ROOT / "packages" / "contracts" / "fixtures" / "v1"
