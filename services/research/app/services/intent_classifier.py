"""意图识别服务 — 在 Research Pipeline 入口前做门控。

对齐 RESEARCH_PIPELINE.md §1.2 / ARCHITECTURE.md §2.4：
- 规则快路径：零 Token 识别常见问候、致谢、告别、自我介绍、过短输入。
- 研究关键词快路径：出现明确研究意图关键词时直接判定为 research，避免浪费 Token。
- LLM 回退：对模糊短输入调用轻量 LLM（settings.LLM_FLASH_MODEL）做 JSON 分类，
  任何异常均降级为 research，确保可用性优先。
"""

import json
import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.core.llm import chat_completion

logger = logging.getLogger(__name__)

INTENT_RESEARCH = "research"
INTENT_DIRECT_ANSWER = "direct_answer"

# ── 规则快路径词表 ──────────────────────────────────────────────

_DIRECT_GREETINGS_ZH = {
    "你好", "您好", "嗨", "哈喽", "早上好", "晚上好", "中午好", "下午好",
    "大家好", "在吗", "有人吗", "喂", "嗨嗨", "哈喽啊",
}
_DIRECT_GREETINGS_EN = {
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "how are you", "how are u", "what's up", "whats up", "sup", "greetings",
    "howdy", "yo",
}
_DIRECT_THANKS_ZH = {"谢谢", "谢谢你", "感谢", "多谢", "谢了"}
_DIRECT_THANKS_EN = {"thanks", "thank you", "thx", "thank u"}
_DIRECT_FAREWELLS_ZH = {"再见", "拜拜", "bye bye", "拜拜了", "回头见"}
_DIRECT_FAREWELLS_EN = {"bye", "goodbye", "see you", "see ya", "later"}
_DIRECT_SELF_INTRO = {
    "你是谁", "你是什么", "你是干嘛的", "你能做什么", "你会什么", "介绍下自己",
    "who are you", "what are you", "what can you do", "help", "帮助",
}

_RESEARCH_KEYWORDS_ZH = {
    "对比", "比较", "vs", "v.s", "分析", "影响", "机制", "原理", "研究", "调研",
    "方案", "应用", "趋势", "评价", "评估", "差异", "区别", "优劣", "现状",
    "案例", "挑战", "机遇", "策略", "问题", "总结", "综述", "查询", "测试",
    "技术", "产品", "工具", "框架", "模型", "算法", "系统", "平台", "事件",
    "历史", "前景", "发展", "改进", "创新", "方法", "流程", "效果", "性能",
}
_RESEARCH_KEYWORDS_EN = {
    "compare", "comparison", "vs", "versus", "analysis", "analyze", "impact",
    "mechanism", "principle", "research", "study", "review", "survey", "solution",
    "application", "trends", "trend", "evaluate", "assessment", "difference",
    "differences", "pros and cons", "advantages", "disadvantages", "status",
    "case", "cases", "challenges", "opportunities", "strategy", "strategies",
    "technology", "product", "tool", "framework", "model", "algorithm", "system",
    "platform", "event", "history", "future", "development", "improvement",
    "innovation", "method", "process", "performance", "effect",
}

# 标点与常见语气词，用于规则归一化
_PUNCTUATION_CHARS = set(
    "！？。，、；：“”‘’（）【】…—~!?,;:\"'()[]…—~`"
)
_MODAL_PARTICLES = ["啊", "呀", "呢", "吧", "了", "哦", "哈", "哇", "喽", "嘛"]

# LLM 回退长度阈值：超过该长度默认视为研究意图，不再调用 LLM
_LLM_FALLBACK_MAX_LEN = 120

_INTENT_PROMPT = """你是 ResearchMind 的意图识别器。判断用户输入是否希望启动深度研究，还是只需要闲聊/问候/致谢/简单问答。
你只输出 JSON，不要任何解释。

输出格式：
{
  "intent": "research" | "direct_answer",
  "direct_answer": "若 intent=direct_answer，给出简短、友好、与用户输入同语言的回答（不超过150字）；否则空字符串",
  "reason": "判断理由，不超过30字"
}

判断规则（按优先级）：
1. 输入是问候、寒暄、感谢、告别、自我介绍、无明确研究主题 → direct_answer
2. 输入要求对比、分析、解释、调研、查找资料、总结某个主题 → research
3. 输入包含具体实体、问题、技术、产品、事件 → research
4. 不确定时，优先 research，避免漏判真正研究需求

用户输入："""


@dataclass
class IntentResult:
    """意图识别结果。"""

    intent: str
    direct_answer: str = ""
    reason: str = ""


def _normalize(text: str) -> str:
    """移除首尾空白、标点与常见语气词，用于规则匹配。"""
    chars = [c for c in text.strip() if c not in _PUNCTUATION_CHARS]
    s = "".join(chars)
    for particle in _MODAL_PARTICLES:
        if s.endswith(particle):
            s = s[: -len(particle)]
            break
    return s.strip().lower()


def _contains_any(text: str, keywords: set[str]) -> bool:
    """判断文本中是否包含任一关键词（全词/子串匹配，大小写不敏感）。"""
    lowered = text.lower()
    return any(kw in lowered for kw in keywords)


def _is_chinese(text: str) -> bool:
    """是否包含中文字符。"""
    return any("一" <= ch <= "鿿" for ch in text)


def _build_direct_answer(topic: str, key: str) -> str:
    """根据输入语言选择直接回答文案。"""
    templates = _DIRECT_ANSWER_TEMPLATES.get(key)
    if templates is None:
        return key
    if _is_chinese(topic):
        return templates["zh"]
    return templates["en"]


_DIRECT_ANSWER_TEMPLATES = {
    "greeting": {
        "zh": "你好！我是 ResearchMind，可以帮你做深度研究。请告诉我你想研究的主题。",
        "en": "Hello! I'm ResearchMind and can help you with structured research. What topic would you like to explore?",
    },
    "thanks": {
        "zh": "不客气！如果有研究需求，随时告诉我。",
        "en": "You're welcome! Feel free to ask if you have a research topic in mind.",
    },
    "farewell": {
        "zh": "再见！期待下次为你做研究。",
        "en": "Goodbye! Looking forward to helping you with your next research.",
    },
    "self_intro": {
        "zh": "我是 ResearchMind，一个可审计的 Agentic 研究助手。我可以针对你感兴趣的主题做结构化深度研究，请告诉我研究主题。",
        "en": "I'm ResearchMind, an agentic research assistant. I can conduct structured deep research for you. Please tell me the topic you'd like to explore.",
    },
    "too_short": {
        "zh": "你的输入比较简短，请补充更具体的研究主题，我会为你进行结构化研究。",
        "en": "Your input is a bit short. Please provide a more specific research topic, and I'll conduct a structured study for you.",
    },
    "empty": {
        "zh": "请输入一个研究主题，我会为你进行结构化研究。",
        "en": "Please enter a research topic, and I'll conduct a structured study for you.",
    },
}


def _rule_classify(topic: str) -> IntentResult | None:
    """规则快路径。命中直接回答/研究意图时立即返回，否则 None。"""
    raw = topic.strip()
    if not raw:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "empty"),
            "空输入",
        )

    normalized = _normalize(raw)

    # 问候（优先于过短判断，避免“你好”等被误判）
    if normalized in _DIRECT_GREETINGS_ZH or normalized in _DIRECT_GREETINGS_EN:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "greeting"),
            "问候语",
        )

    # 致谢
    if normalized in _DIRECT_THANKS_ZH or normalized in _DIRECT_THANKS_EN:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "thanks"),
            "致谢",
        )

    # 告别
    if normalized in _DIRECT_FAREWELLS_ZH or normalized in _DIRECT_FAREWELLS_EN:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "farewell"),
            "告别",
        )

    # 自我介绍 / 求助
    if normalized in _DIRECT_SELF_INTRO:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "self_intro"),
            "自我介绍/求助",
        )

    # 过短输入通常无法构成研究主题
    if len(raw) <= 2:
        return IntentResult(
            INTENT_DIRECT_ANSWER,
            _build_direct_answer(raw, "too_short"),
            "输入过短",
        )

    # 研究关键词快路径：避免为明显研究主题浪费 LLM Token
    if _contains_any(raw, _RESEARCH_KEYWORDS_ZH) or _contains_any(raw, _RESEARCH_KEYWORDS_EN):
        return IntentResult(INTENT_RESEARCH, "", "研究关键词命中")

    return None


def _extract_json_object(text: str) -> dict:
    """从 LLM 返回文本中提取第一个 JSON 对象。"""
    # 去掉可能的 markdown 代码块标记
    stripped = text.strip()
    if stripped.startswith("```"):
        # 去掉首行 ```json
        parts = stripped.split("\n", 1)
        stripped = parts[1] if len(parts) > 1 else stripped
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 返回中未找到 JSON 对象")

    return json.loads(stripped[start : end + 1])


def _parse_llm_result(raw: str) -> IntentResult:
    """解析 LLM 返回的 JSON 并校验。"""
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON 根非对象")

    intent = data.get("intent", INTENT_RESEARCH)
    if intent not in (INTENT_RESEARCH, INTENT_DIRECT_ANSWER):
        intent = INTENT_RESEARCH

    direct_answer = data.get("direct_answer", "")
    if not isinstance(direct_answer, str):
        direct_answer = ""

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = ""

    return IntentResult(intent, direct_answer.strip(), reason.strip())


async def classify_intent(topic: str) -> IntentResult:
    """对输入主题进行意图识别。

    优先级：
    1. 规则快路径（问候/致谢/告别/自我介绍/过短/研究关键词）
    2. 对较短模糊输入调用轻量 LLM
    3. 默认 research

    任何异常均降级为 research，避免阻塞用户真正研究需求。
    """
    rule_result = _rule_classify(topic)
    if rule_result is not None:
        logger.debug(
            "意图识别规则命中: intent=%s, reason=%s, topic=%s",
            rule_result.intent, rule_result.reason, topic[:50]
        )
        return rule_result

    # 较长输入默认视为研究，避免无意义 Token 消耗
    if len(topic.strip()) > _LLM_FALLBACK_MAX_LEN:
        return IntentResult(INTENT_RESEARCH, "", "长文本默认研究")

    # LLM 回退
    messages = [
        {"role": "system", "content": "你是 ResearchMind 的意图识别器。你只输出 JSON，不要任何解释。"},
        {"role": "user", "content": _INTENT_PROMPT + topic.strip()},
    ]
    try:
        llm_result = await chat_completion(
            messages,
            model=settings.LLM_FLASH_MODEL,
            temperature=0.0,
            max_tokens=250,
        )
        parsed = _parse_llm_result(llm_result.content)
        logger.info(
            "意图识别 LLM 判定: intent=%s, reason=%s, topic=%s",
            parsed.intent, parsed.reason, topic[:50]
        )
        return parsed
    except Exception as e:
        logger.warning(
            "意图识别 LLM 失败，降级为 research: topic=%s, error=%s",
            topic[:50], e
        )
        return IntentResult(INTENT_RESEARCH, "", "LLM异常降级")
