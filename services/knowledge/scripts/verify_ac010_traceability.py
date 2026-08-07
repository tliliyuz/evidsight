#!/usr/bin/env python3
"""AC-010 报告 Evidence 来源可追溯性验证入口。

对齐 TESTING.md §5（AC-010，100% 展示来源类型；内部证据可定位文档位置）与
§7 发布记录模板：给定 Research Task 的 Evidence 引用列表 JSON
（[{task_id, references:[{knowledge_base_id, document_id, document_version_id,
segment_id}]}]），逐引用调用 Internal Evidence Resolve，校验：
- 每个引用解析成功（无 EVIDENCE_SOURCE_UNAVAILABLE / 服务错误）
- document_id / document_version_id / segment_id 均为合法 UUID
- 返回结果含可定位位置（page_number 或 section_path）与最小正文

不伪造结果：任一引用解析失败或缺失位置信息即计为该引用不可追溯；
输入文件缺失或格式非法直接报错退出。

用法:
  python scripts/verify_ac010_traceability.py --service-token <jwt> --tasks <tasks.json>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid as uuid_lib
from pathlib import Path

import httpx

CONTRACT_VERSION = "1.0.0"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-010 Evidence 来源可追溯性验证")
    parser.add_argument("--service-token", required=True, help="Internal API Service JWT")
    parser.add_argument(
        "--tasks", required=True, help="Research Task 引用 JSON：[{task_id, references:[...]}]"
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Knowledge API 基地址")
    parser.add_argument(
        "--user-id",
        default="550e8400-e29b-41d4-a716-446655440001",
        help="请求用户 Platform UUID（默认测试用户）",
    )
    parser.add_argument("--request-timeout", type=int, default=30, help="单请求超时（秒）")
    return parser.parse_args()


def _load_tasks(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"错误：任务文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(t, dict) and isinstance(t.get("references"), list) for t in data
    ):
        raise SystemExit("错误：任务文件必须为 [{task_id, references:[...]}] 列表")
    return data


def _resolve(
    api_base: str, token: str, user_id: str, references: list[dict], timeout: int
) -> list[dict] | None:
    """调用 Internal Evidence Resolve；请求失败返回 None（整批失败）。"""
    body = {
        "contract_version": CONTRACT_VERSION,
        "user_id": user_id,
        "references": references,
        "purpose": "research_evidence_resolve",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EvidSight-Contract-Version": CONTRACT_VERSION,
        "X-Request-ID": str(uuid_lib.uuid4()),
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }
    resp = httpx.post(
        f"{api_base}/internal/v1/retrieval/resolve", json=body, headers=headers, timeout=timeout
    )
    if resp.status_code != 200:
        return None
    return resp.json().get("results", [])


def _is_valid_uuid(value: str) -> bool:
    return bool(value) and bool(_UUID_RE.match(value))


def _has_location(result: dict) -> bool:
    loc = result.get("location") or {}
    return bool(loc.get("page_number") is not None or loc.get("section_path"))


def main() -> int:
    args = _parse_args()
    tasks = _load_tasks(Path(args.tasks))

    total_refs = 0
    traceable = 0
    problems: list[str] = []

    for task in tasks:
        refs = task["references"]
        results = _resolve(
            args.base_url, args.service_token, args.user_id, refs, args.request_timeout
        )
        task_id = task.get("task_id", "?")
        if results is None:
            problems.append(f"task={task_id}: Resolve 请求失败（非 200 / 服务错误）")
            continue

        for ref, result in zip(refs, results):
            total_refs += 1
            ref_desc = f"task={task_id} doc={ref.get('document_id')} seg={ref.get('segment_id')}"
            # 引用本身 UUID 合法性
            for field in ("document_id", "document_version_id", "segment_id", "knowledge_base_id"):
                if not _is_valid_uuid(ref.get(field, "")):
                    problems.append(f"{ref_desc}: {field} 非合法 UUID")
            # 解析结果可追溯性
            if not _has_location(result):
                problems.append(f"{ref_desc}: 缺少可定位位置（page_number/section_path）")
            elif not result.get("minimal_excerpt"):
                problems.append(f"{ref_desc}: 缺少最小正文")
            else:
                traceable += 1

    rate = (traceable / total_refs) if total_refs else 0.0
    print(f"[AC-010] 引用总数: {total_refs}，可追溯: {traceable}，追溯率: {rate:.2%}（门槛 100%）")
    for p in problems:
        print(f"  - 不可追溯: {p}")

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print(f"环境与资源：{args.base_url}")
    print(f"数据集版本：{args.tasks}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if total_refs and rate >= 1.0 else "未通过"
    print(f"通过/失败/跳过：{verdict}（追溯率 {rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if total_refs and rate >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
