### sample设计说明
```
┌─────┬───────────────┬────────────┬───────────────────────────────────────────────────────────────────┐
│ ID  │     主题      │ task_type  │                             题目概要                              │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q01 │ 技术趋势      │ comparison │ LLM 推理优化技术对比（投机解码 / KV Cache / 量化）                │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q02 │ 技术趋势      │ explainer  │ RAG 核心原理与架构变体演进                                        │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q03 │ 技术趋势      │ analysis   │ AI Agent 框架格局分析（LangGraph / CrewAI / AutoGen）             │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q04 │ 政策法规      │ comparison │ 欧盟 AI Act / 中国生成式 AI 办法 / 美国 EO 三方对比               │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q05 │ 政策法规      │ explainer  │ 中国《生成式 AI 管理暂行办法》核心要求详解                        │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q06 │ 政策法规      │ analysis   │ 全球 AI 版权诉讼趋势与影响分析                                    │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q07 │ 产品/方案对比 │ comparison │ 企业级向量数据库多维对比（Pinecone / Milvus / Weaviate / Qdrant） │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q08 │ 产品/方案对比 │ explainer  │ LLM 可观测性框架与工具介绍                                        │
├─────┼───────────────┼────────────┼───────────────────────────────────────────────────────────────────┤
│ Q09 │ 产品/方案对比 │ analysis   │ AI 代码助手市场竞争格局分析                                       │
└─────┴───────────────┴────────────┴───────────────────────────────────────────────────────────────────┘
```

```json
[
  {
    "round": 1,
    "task_id": "",
    "topic": "比较 2025-2026 年最受关注的三种大语言模型（LLM）推理优化技术（如投机解码、KV Cache 压缩、模型量化）的优缺点，并给出不同场景下的选型建议。",
    "task_type": "comparison",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 1,
    "task_id": "",
    "topic": "解释 RAG（检索增强生成）技术的核心原理、主流架构变体（如 Naive RAG / Advanced RAG / Modular RAG），以及 2026 年的最新演进方向。",
    "task_type": "explainer",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 1,
    "task_id": "",
    "topic": "分析 AI Agent 框架（如 LangGraph、CrewAI、AutoGen）在 2025-2026 年的发展格局：市场渗透率、技术成熟度曲线、关键差异化能力，以及未来 12 个月的可能走向。",
    "task_type": "analysis",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 2,
    "task_id": "",
    "topic": "比较欧盟 AI Act、中国生成式 AI 管理办法、美国 AI 行政令（Executive Order）三者在 AI 安全监管路径上的核心差异，并分析对跨国 AI 企业的合规影响。",
    "task_type": "comparison",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 2,
    "task_id": "",
    "topic": "详细解释中国《生成式人工智能服务管理暂行办法》的核心要求：训练数据合规、内容安全责任、算法备案流程，以及 2026 年最新的执法动态和典型案例。",
    "task_type": "explainer",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 2,
    "task_id": "",
    "topic": "分析全球 AI 版权诉讼（如 NYT v. OpenAI、Getty Images v. Stability AI）对 AI 训练数据获取策略的深远影响：判决趋势、行业应对措施（如 opt-out 机制、授权协议），以及 2026-2027 年的政策走向预判。",
    "task_type": "analysis",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 3,
    "task_id": "",
    "topic": "对比主流企业级向量数据库（如 Pinecone、Weaviate、Milvus、Qdrant）在性能、扩展性、成本、生态集成方面的差异，并给出不同规模企业（初创 / 中型 / 大型）的选型建议。",
    "task_type": "comparison",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 3,
    "task_id": "",
    "topic": "解释 LLM 可观测性（LLM Observability）的概念框架：Trace / Span / Evaluation 三层模型，并介绍 2026 年主流工具（如 LangSmith、Weights & Biases、Arize AI）的核心能力与最佳实践。",
    "task_type": "explainer",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  },
  {
    "round": 3,
    "task_id": "",
    "topic": "分析 2024-2026 年 AI 代码助手市场（GitHub Copilot、Cursor、Claude Code、通义灵码等）的竞争格局：用户增长趋势、定价策略演变、功能差异化路径，以及市场集中度变化。",
    "task_type": "analysis",
    "rater": "evaluator-1",
    "scores": [
      {"dimension": "结构完整性", "score": null, "comment": ""},
      {"dimension": "引用准确性", "score": null, "comment": ""},
      {"dimension": "综合质量", "score": null, "comment": ""},
      {"dimension": "可读性", "score": null, "comment": ""}
    ],
    "overall_score": null,
    "evaluated_at": ""
  }
]
```
