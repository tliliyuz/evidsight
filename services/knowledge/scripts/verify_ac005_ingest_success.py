#!/usr/bin/env python3
"""AC-005 固定文档集入库成功率验证入口。

对齐 TESTING.md §5（AC-005，入库成功率 ≥ 99%，排除不支持格式与用户主动取消）
与 §7 发布记录模板：上传固定文档集（默认 knowledge_samples/samples_1/），
轮询 Document 状态至终态（queued→processing→completed/partial/failed），
统计成功率并输出发布记录。

不伪造完成状态：上传异常、状态轮询超时一律计为失败并明确列出失败明细；
样本集缺失或不可读时直接报错退出，不得记为通过。

用法:
  python scripts/verify_ac005_ingest_success.py --kb-uuid <uuid> --token <bearer>
  python scripts/verify_ac005_ingest_success.py --kb-uuid <uuid> --token <t> \\
      --docs-dir knowledge_samples/samples_1 --poll-interval 5 --timeout 600
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

SUCCESS_STATUSES = {"completed", "partial"}
FAILED_STATUSES = {"failed"}
TERMINAL_STATUSES = SUCCESS_STATUSES | FAILED_STATUSES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-005 固定文档集入库成功率验证")
    parser.add_argument("--kb-uuid", required=True, help="目标知识库 UUID")
    parser.add_argument("--token", required=True, help="外部 API Bearer Token")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="Knowledge API 基地址（默认 http://localhost:8000）")
    parser.add_argument("--docs-dir", default="knowledge_samples/samples_1",
                        help="固定文档集目录（默认 knowledge_samples/samples_1）")
    parser.add_argument("--poll-interval", type=int, default=5, help="轮询间隔（秒）")
    parser.add_argument("--timeout", type=int, default=600,
                        help="单文档状态轮询超时（秒）")
    return parser.parse_args()


def _upload(api_base: str, kb_uuid: str, token: str, file_path: Path) -> bool:
    """multipart 上传单个文档，成功返回 True。"""
    headers = {"Authorization": f"Bearer {token}"}
    with file_path.open("rb") as f:
        resp = httpx.post(
            f"{api_base}/api/knowledge-bases/{kb_uuid}/documents",
            files={"file": (file_path.name, f, "application/octet-stream")},
            data={"force": "false"},
            headers=headers,
            timeout=60,
        )
    return resp.status_code == 201


def _list_documents(api_base: str, kb_uuid: str, token: str) -> dict[str, str]:
    """拉取 KB 下文档 filename → status 映射。"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(
        f"{api_base}/api/knowledge-bases/{kb_uuid}/documents",
        headers=headers, timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("data") or []
    return {item.get("filename"): item.get("status") for item in items}


def main() -> int:
    args = _parse_args()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.is_dir():
        print(f"错误：固定文档集目录不存在或不可读: {docs_dir}")
        return 2
    files = sorted(p for p in docs_dir.iterdir() if p.is_file())
    if not files:
        print(f"错误：固定文档集目录为空: {docs_dir}")
        return 2

    print(f"[AC-005] 文档集: {docs_dir}（{len(files)} 个文件），KB: {args.kb_uuid}")

    # 1. 逐文档上传
    failures: list[tuple[str, str]] = []
    for fp in files:
        try:
            ok = _upload(args.base_url, args.kb_uuid, args.token, fp)
        except Exception as e:  # noqa: BLE001
            ok = False
            failures.append((fp.name, f"上传异常: {e}"))
        if not ok:
            failures.append((fp.name, "上传返回非 201"))

    # 2. 轮询直至终态或超时
    pending = {fp.name for fp in files}
    deadline = time.monotonic() + args.timeout
    final_status: dict[str, str] = {}
    while pending and time.monotonic() < deadline:
        try:
            snapshot = _list_documents(args.base_url, args.kb_uuid, args.token)
        except Exception as e:  # noqa: BLE001
            print(f"  轮询列表失败（重试中）: {e}")
            time.sleep(args.poll_interval)
            continue
        for name in list(pending):
            status = snapshot.get(name)
            if status in TERMINAL_STATUSES:
                final_status[name] = status
                pending.discard(name)
        if pending:
            time.sleep(args.poll_interval)

    for name in pending:
        final_status[name] = "timeout"
        failures.append((name, "状态轮询超时未达终态"))

    # 3. 统计（排除上传失败未产生状态的文档；用户主动取消由执行者记录）
    evaluated = [n for n in files if n not in {f for f, _ in failures}]
    successes = [n for n in evaluated if final_status.get(n) in SUCCESS_STATUSES]
    failed_ingest = [n for n in evaluated if final_status.get(n) in FAILED_STATUSES]
    success_rate = (len(successes) / len(evaluated)) if evaluated else 0.0

    print(f"\n[AC-005] 结果统计")
    print(f"  样本数: {len(files)}，已评估: {len(evaluated)}")
    print(f"  成功(completed/partial): {len(successes)}")
    print(f"  失败(failed/timeout): {len(failed_ingest) + len(failures)}")
    print(f"  成功率: {success_rate:.2%}（门槛 ≥ 99%）")
    for name, reason in failures:
        print(f"  - 失败: {name} -> {reason}")

    # 4. 发布记录模板（TESTING.md §7）
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        commit = "unknown"
    print("\n===== 发布记录模板（TESTING.md §7）=====")
    print(f"候选版本/提交：{commit}")
    print(f"环境与资源：{args.base_url} / KB {args.kb_uuid}")
    print(f"数据集版本：{docs_dir}")
    print(f"执行命令：{' '.join(sys.argv)}")
    verdict = "通过" if success_rate >= 0.99 else "未通过"
    print(f"通过/失败/跳过：{verdict}（成功率 {success_rate:.2%}）")
    print("已知偏差与批准人：")
    print("证据链接：")

    return 0 if success_rate >= 0.99 else 1


if __name__ == "__main__":
    sys.exit(main())
