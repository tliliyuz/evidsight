"""离线 Pipeline 评估脚本入口

用法：
    python scripts/eval_offline.py --task-id <uuid>
    python scripts/eval_offline.py --task-id <uuid> --json
    python scripts/eval_offline.py --all-completed --limit 50
    python scripts/eval_offline.py --all-completed --system   # 含系统可靠性指标
    python scripts/eval_offline.py --manual-round eval/manual/round1
    python scripts/eval_offline.py --manual-round eval/manual/round1 --json
    python scripts/eval_offline.py --manual-all-rounds        # 聚合 eval/manual/round* 所有轮次
    python scripts/eval_offline.py --manual-all-rounds --json
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evaluation.cli import run_cli


if __name__ == "__main__":
    sys.exit(asyncio.run(run_cli()))
