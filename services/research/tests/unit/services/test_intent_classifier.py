"""意图识别服务单元测试 — 覆盖规则快路径与 LLM 回退。

对齐 TESTING_STRATEGY.md：
- 强断言验证 intent / direct_answer 内容
- 分支枚举：规则命中、关键词命中、LLM 返回研究/直接回答、LLM 异常降级
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.intent_classifier import (
    INTENT_DIRECT_ANSWER,
    INTENT_RESEARCH,
    classify_intent,
)


class TestRuleClassification:
    """规则快路径：无需 LLM，零 Token 成本。"""

    async def test_中文问候命中规则返回direct_answer(self):
        result = await classify_intent("你好")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "ResearchMind" in result.direct_answer
        assert result.direct_answer != ""

    async def test_英文问候命中规则返回direct_answer(self):
        result = await classify_intent("Hello")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "ResearchMind" in result.direct_answer

    async def test_带语气词的问候仍命中(self):
        result = await classify_intent("你好啊！")
        assert result.intent == INTENT_DIRECT_ANSWER

    async def test_感谢命中规则(self):
        result = await classify_intent("谢谢")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "不客气" in result.direct_answer

    async def test_英文感谢命中规则(self):
        result = await classify_intent("thanks")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "welcome" in result.direct_answer.lower()

    async def test_告别命中规则(self):
        result = await classify_intent("再见")
        assert result.intent == INTENT_DIRECT_ANSWER

    async def test_自我介绍命中规则(self):
        result = await classify_intent("你是谁")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "研究" in result.direct_answer

    async def test_空输入命中规则(self):
        result = await classify_intent("   ")
        assert result.intent == INTENT_DIRECT_ANSWER

    async def test_过短输入命中规则(self):
        result = await classify_intent("好")
        assert result.intent == INTENT_DIRECT_ANSWER
        assert "简短" in result.direct_answer

    async def test_研究关键词命中规则返回research(self):
        result = await classify_intent("Milvus vs Qdrant 对比分析")
        assert result.intent == INTENT_RESEARCH
        assert result.direct_answer == ""

    async def test_中文研究主题命中规则返回research(self):
        result = await classify_intent("量子计算对密码学的影响")
        assert result.intent == INTENT_RESEARCH


class TestLLMFallback:
    """LLM 回退路径：仅对规则未命中且较短的输入调用。"""

    @pytest.mark.asyncio
    async def test_LLM判定为direct_answer(self):
        llm_response = '{"intent": "direct_answer", "direct_answer": "今天天气不错，建议出去走走。", "reason": "询问天气"}'
        with patch(
            "app.services.intent_classifier.chat_completion",
            new=AsyncMock(return_value=AsyncMock(content=llm_response)),
        ):
            result = await classify_intent("今天天气怎么样")

        assert result.intent == INTENT_DIRECT_ANSWER
        assert "天气" in result.direct_answer

    @pytest.mark.asyncio
    async def test_LLM判定为research(self):
        llm_response = '{"intent": "research", "direct_answer": "", "reason": "需调研"}'
        with patch(
            "app.services.intent_classifier.chat_completion",
            new=AsyncMock(return_value=AsyncMock(content=llm_response)),
        ):
            result = await classify_intent("什么是注意力机制")

        assert result.intent == INTENT_RESEARCH
        assert result.direct_answer == ""

    @pytest.mark.asyncio
    async def test_LLM返回无效JSON回退为research(self):
        with patch(
            "app.services.intent_classifier.chat_completion",
            new=AsyncMock(return_value=AsyncMock(content="这不是 JSON")),
        ):
            result = await classify_intent("随便聊聊")

        assert result.intent == INTENT_RESEARCH

    @pytest.mark.asyncio
    async def test_LLM调用异常回退为research(self):
        with patch(
            "app.services.intent_classifier.chat_completion",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            result = await classify_intent("随便聊聊")

        assert result.intent == INTENT_RESEARCH
        assert result.reason == "LLM异常降级"

    async def test_长文本默认研究不调用LLM(self):
        # 长度超过阈值且无明确规则命中，应直接返回 research，不调用 LLM
        long_topic = "随便聊聊" + "。" * 130
        result = await classify_intent(long_topic)
        assert result.intent == INTENT_RESEARCH
