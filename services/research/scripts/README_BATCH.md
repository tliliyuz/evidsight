# 批量研究任务运行脚本

`batch_research_runner.py` 用于在云服务器通宵批量提交并监控 ResearchMind 研究任务。

## 前置条件

1. 后端已启动：
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. Celery Worker 已启动（单 worker）：
   ```bash
   # Linux / macOS
   celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1

   # Windows
   celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
   ```
3. 已创建好登录用户（可通过 `/api/auth/register` 或数据库初始化）。

## 快速开始

### 方式 1：自动生成 500 个任务（推荐通宵测试）

```bash
python scripts/batch_research_runner.py \
  --base-url http://localhost:8000 \
  --username zhangsan \
  --password mypassword123 \
  --generate-count 500 \
  --max-inflight 1 \
  --interval 1.0 \
  --poll-interval 30
```

### 方式 2：使用自定义任务列表

```bash
python scripts/batch_research_runner.py \
  --username zhangsan \
  --password mypassword123 \
  --tasks scripts/data/example_tasks.json
```

任务列表格式示例：

```json
[
  {"topic": "量子计算对现有密码学体系的影响"},
  {"topic": "大语言模型在医疗诊断中的应用现状", "task_type": "analysis", "max_sources": 15}
]
```

## 云服务器通宵挂机

推荐用 `screen` 或 `nohup`：

```bash
# screen 方式
screen -S research-batch
python scripts/batch_research_runner.py \
  --username zhangsan \
  --password mypassword123 \
  --generate-count 500 \
  --max-inflight 1 \
  --interval 1.0 \
  --poll-interval 30
# Ctrl+A D  detach，第二天 screen -r research-batch 回来查看

# nohup 方式
nohup python scripts/batch_research_runner.py \
  --username zhangsan \
  --password mypassword123 \
  --generate-count 500 \
  --max-inflight 1 \
  --interval 1.0 \
  --poll-interval 30 \
  > scripts/logs/batch_run.log 2>&1 &
```

## 断点续跑

脚本会把进度写入 `scripts/data/batch_progress.json`。如果中途断网或 Ctrl+C 中断，直接重新运行相同命令即可：

- 已提交的 `task_id` 会自动跳过。
- 之前处于 `pending` / `running` 的任务会重新进入轮询。

如果想完全重新开始，先删除进度文件：

```bash
rm scripts/data/batch_progress.json
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `scripts/data/batch_progress.json` | 运行进度与所有任务状态，可断点续跑 |
| `scripts/output/batch_result_YYYYMMDD_HHMMSS.csv` | 最终统计 CSV |
| 控制台 / `nohup` 日志 | 实时提交与轮询日志 |

## 常用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--base-url` | `http://localhost:8000` | 后端地址 |
| `--interval` | `1.0` | 提交间隔（秒）。限流关闭后可调小，但不建议设为 0，避免瞬间压垮 worker |
| `--poll-interval` | `30.0` | 状态轮询间隔（秒） |
| `--max-inflight` | `1` | 同时在途（pending+running）任务上限。**单 worker + 30s pending timeout 时必须为 1**，否则监察者会超时 |
| `--progress-file` | `scripts/data/batch_progress.json` | 进度文件路径 |
| `--output-dir` | `scripts/output` | 结果 CSV 输出目录 |
| `--no-wait` | 否 | 提交完所有任务后直接退出，不等终态 |
| `--log-level` | `INFO` | 日志级别 |

## 注意事项

- **单 worker 跑 500 个任务时，`--max-inflight` 必须设为 1**。因为系统默认 `PENDING_TASK_TIMEOUT_SECONDS=30`，如果队列里堆积多个 pending 任务， worker 来不及在 30 秒内 pick up，监察者会把它们标记为 failed。只有当前任务完成、进入轮询后，脚本才会提交下一个。
- 如果想提速，有两种方式：
  1. 增加 worker 数量（`--concurrency=N` 或开多个 worker 进程），同时按比例提高 `--max-inflight`；
  2. 临时调大 `.env` 里的 `PENDING_TASK_TIMEOUT_SECONDS`（仅限测试环境）。
- 当前版本**不会自动 retry** 失败任务，第二天可查看 CSV 中的 `error_code` 与 `error_message`。
- 脚本不下载完整 report，只记录状态。需要 report 请调用 `GET /api/research/{task_id}/report`。
- 自动刷新 `access_token`：过期前 60 秒会调用 `/api/auth/refresh`。
