#!/usr/bin/env python3
"""AC-006 固定 Knowledge 评估集 Recall@5 验证入口。

对齐 TESTING.md §5（AC-006，Recall@5 ≥ 0.85，固定内部知识评估集）、
PRD AC-006 与 §7 发布记录模板：加载评估集 JSON（[{question, expected_docs}]，
expected_docs 为期望命中文档文件名），对每题调用 Internal Retrieval search，
计算命中期望文档的 Recall@5，输出逐问明细与发布记录。

不伪造结果：Internal Retrieval 返回 503/超时按当题召回 0 计并标注；
评估集缺失或格式非法直接报错退出。

用法:
  python scripts/verify_ac006_recall.py --kb-uuid <uuid> --service-token <jwt>
  python scripts/verify_ac006_recall.py --kb-uuid <uuid> --service-token <jwt> \\
      --eval-set tests/eval/eval_test_set.json --user-id <platform_user_id> --top-k 5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid as uuid_lib
from pathlib import Path
from statistics import mean

import httpx

CONTRACT_VERSION = "1.0.0"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-006 固定评估集 Recall@5 验证")
    parser.add_argument("--kb-uuid", required=True, help="目标知识库 UUID")
    parser.add_argument("--service-token", required=True, help="Internal API Service JWT")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Knowledge API 基地址")
    parser.add_argument(
        "--eval-set", required=True, help="评估集 JSON 路径：[{question, expected_docs:[文件名]}]"
    )
    parser.add_argument(
        "--user-id",
        default="550e8400-e29b-41d4-a716-446655440001",
        help="请求用户 Platform UUID（默认测试用户）",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Recall@K（默认 5）")
    parser.add_argument("--request-timeout", type=int, default=30, help="单请求超时（秒）")
    return parser.parse_args()


def _load_eval_set(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"错误：评估集不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(
        isinstance(q, dict) and q.get("question") and q.get("expected_docs") for q in data
    ):
        raise SystemExit("错误：评估集必须为 [{question, expected_docs}] 列表")
    return data


def _search(
    api_base: str, kb_uuid: str, token: str, user_id: str, query: str, timeout: int
) -> list[str]:
    """调用 Internal Retrieval search，返回命中文档显示名列表。"""
    body = {
        "contract_version": CONTRACT_VERSION,
        "user_id": user_id,
        "knowledge_base_ids": [kb_uuid],
        "query": query,
        "purpose": "research_retrieval",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EvidSight-Contract-Version": CONTRACT_VERSION,
        "X-Request-ID": str(uuid_lib.uuid4()),
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }
    resp = httpx.post(
        f"{api_base}/internal/v1/retrieval/search", json=body, headers=headers, timeout=timeout
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Internal Retrieval {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return [hit.get("document_display_name", "") for hit in data.get("results", [])]


def _name_matches(display_name: str, expected: str) -> bool:
    """显示名与期望文件名匹配：精确相等或末尾文件名相等。"""
    if not display_name:
        return False
    if display_name == expected:
        return True
    # display_name 可能是去掉扩展名的展示名；同时接受文件名后缀匹配
    return display_name.endswith(Path(expected).stem) or display_name.endswith(expected)


def main() -> int:
    args = _parse_args()
    eval_set = _load_eval_set(Path(args.eval_set))

    print(
        f"[AC-006] 评估集: {args.eval_set}（{len(eval_set)} 题），KB: {args.kb_uuid}，"
        f"Recall@{args.top_k}"
    )

    per_question: list[dict] = []
    for item in eval_set:
        expected = item["expected_docs"]
        try:
            hits = _search(
                args.base_url,
                args.kb_uuid,
                args.service_token,
                args.user_id,
                item["question"],
                args.request_timeout,
            )
            # Recall@K 以「期望文档是否出现在命中里」为准，同一文档的多个
            # chunk 命中只计一次；直接数命中条数会得到 >1 的伪 recall。
            recalled = sorted({d for d in hits if any(_name_matches(d, exp) for exp in expected)})
            matched_expected = sum(
                1 for exp in expected if any(_name_matches(d, exp) for d in hits)
            )
            recall = matched_expected / len(expected) if expected else 0.0
            failed = False
        except Exception as e:  # noqa: BLE001
            recalled, recall, failed = [], 0.0, True
            print(f"  - 题 {item.get('id', '?')} 检索异常: {e}")

        per_question.append(
            {
                "id": item.get("id", "?"),
                "question": item["question"],
                "recall": recall,
                "hits": recalled,
                "expected": expected,
                "failed": failed,
            }
        )

    avg_recall = mean(q["recall"] for q in per_question)
    pass_count = sum(1 for q in per_question if q["recall"] == 1.0)
    fail_count = sum(1 for q in per_question if q["failed"])

    print(f"\n[AC-006] 结果统计")
    print(f"  样本数: {len(per_question)}，满分题数: {pass_count}，异常题数: {fail_count}")
    print(f"  Recall@{args.top_k} 均值: {avg_recall:.4f}（门槛 ≥ 0.85）")
    for q in per_question:
        status = "FAILED" if q["failed"] else ("PASS" if q["recall"] >= 1.0 else "PARTIAL")
        print(
            f"  [{status}] 题{q['id']} recall={q['recall']:.2f} "
            f"期望={q['expected']} 命中={q['hits']}"
        )

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print(f"环境与资源：{args.base_url} / KB {args.kb_uuid}")
    print(f"数据集版本：{args.eval_set}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if avg_recall >= 0.85 and fail_count == 0 else "未通过"
    print(f"通过/失败/跳过：{verdict}（Recall@{args.top_k} = {avg_recall:.4f}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if avg_recall >= 0.85 and fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
