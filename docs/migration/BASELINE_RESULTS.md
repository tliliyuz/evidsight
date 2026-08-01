# 源仓库基线结果

| 来源 | 提交 | 命令 | 结果 |
|:---|:---|:---|:---|
| DocMind 后端 | `a390a2a` | `.venv/bin/python -m pytest -m "not integration and not performance" --tb=short` | PASS，1301 passed，5 deselected |
| DocMind 前端 | `a390a2a` | `npm test && npm run build` | PASS，513 passed，构建成功 |
| ResearchMind 后端 | `40f7faa` | `.venv/bin/python -m pytest -m "not integration and not slow" --tb=short` | PASS，856 passed，1 skipped，13 deselected |
| ResearchMind 前端 | `40f7faa` | `npm test && npm run build` | PASS，260 passed，构建成功 |

记录时间：2026-08-01T08:35:41Z
