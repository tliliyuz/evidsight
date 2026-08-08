#!/usr/bin/env python3
"""存量报告迁移入口 —— 切片 5（DATABASE.md §12-4 / §7.3 / DATA_MIGRATION_AND_ROLLBACK.md）。

切片 4 前新渲染写 task 级迁移态 `report_sections`（revision_id IS NULL）。本脚本为
已完成/部分完成、有 task 级 sections 且无目标态 reports 根的任务生成 revision 1：
创建 Report + published Revision 1，把 task 级 sections 归入 Revision（保留
section_evidence），幂等可重跑。

用法:
  python scripts/migrate_legacy_report_sections.py --dry-run   # 只扫描，不写入
  python scripts/migrate_legacy_report_sections.py             # 实际迁移

退出码: 0=无失败（migrated+skipped，无残留、无异常）；1=存在失败或残留。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.services.legacy_report_migration import migrate_legacy_report_sections  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="存量报告迁移：task 级 sections 归入目标态 Revision 1"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只扫描并校验，不写入数据库",
    )
    return parser.parse_args()


async def run() -> int:
    args = _parse_args()
    async with async_session_factory() as session:
        result = await migrate_legacy_report_sections(session, dry_run=args.dry_run)

    print(f"[migrate-legacy-sections] {'dry-run 扫描' if args.dry_run else '迁移'}完成")
    print(
        f"  扫描任务: {result.scanned}，已迁移: {result.migrated}，跳过: {result.skipped}，失败: {result.failed}"
    )
    if result.errors:
        print("  校验/失败清单：")
        for err in result.errors[:20]:
            print(f"    - {err}")
        if len(result.errors) > 20:
            print(f"    ... 共 {len(result.errors)} 条")

    ok = result.failed == 0 and not result.errors
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
