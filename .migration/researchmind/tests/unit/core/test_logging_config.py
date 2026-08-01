"""结构化日志测试 — 覆盖 app/core/logging_config.py。

对齐 ROADMAP.md §5.5：
- JSONFormatter 输出格式验证
- RequestIDFilter 注入 request_id / user_id
- setup_logging() 配置 root logger
- contextvars 跨请求传递
"""

import json
import logging

import pytest

from app.core.logging_config import (
    JSONFormatter,
    RequestIDFilter,
    get_request_id,
    get_user_id,
    request_id_var,
    setup_logging,
    user_id_var,
)


class TestJSONFormatter:
    """JSONFormatter 输出格式验证"""

    def test_基础INFO日志输出合法JSON(self):
        """JSONFormatter.format() 输出应为合法 JSON，含标准字段"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.services.research",
            level=logging.INFO,
            pathname="/app/services/research.py",
            lineno=42,
            msg="研究任务已创建: %s",
            args=("task-123",),
            exc_info=None,
        )
        # 注入 request_id / user_id（模拟 RequestIDFilter 效果）
        record.request_id = ""
        record.user_id = 0

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "app.services.research"
        assert "研究任务已创建: task-123" == parsed["message"]
        assert "timestamp" in parsed
        assert parsed["request_id"] == ""
        assert parsed["user_id"] == 0
        # 时间戳格式为 ISO 8601（含 Z 或 +00:00）
        assert "T" in parsed["timestamp"]

    def test_WARNING日志含异常信息(self):
        """exc_info 为真时输出应含 exception 字段"""
        formatter = JSONFormatter()
        try:
            raise ValueError("LLM 调用超时")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="app.pipeline.planner",
                level=logging.WARNING,
                pathname="/app/pipeline/planner.py",
                lineno=88,
                msg="Planning 重试耗尽",
                args=(),
                exc_info=sys.exc_info(),
            )
            record.request_id = "abc123def456"
            record.user_id = 1

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "WARNING"
        assert parsed["request_id"] == "abc123def456"
        assert parsed["user_id"] == 1
        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert "LLM 调用超时" in parsed["exception"]["message"]

    def test_ERROR日志含request_id和user_id(self):
        """request_id 和 user_id 应正确注入到 JSON 输出"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.api.research",
            level=logging.ERROR,
            pathname="/app/api/research.py",
            lineno=55,
            msg="任务不存在",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-001"
        record.user_id = 7

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "ERROR"
        assert parsed["request_id"] == "req-001"
        assert parsed["user_id"] == 7

    def test_extra字段附加到日志输出(self):
        """record 上的非标准字段应进入 extra 字典"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="含额外数据",
            args=(),
            exc_info=None,
        )
        record.request_id = ""
        record.user_id = 0
        # 注入自定义 extra 字段
        record.custom_field = "custom_value"
        record.duration_ms = 1234

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "extra" in parsed
        assert parsed["extra"]["custom_field"] == "custom_value"
        assert parsed["extra"]["duration_ms"] == 1234

    def test_无异常时不含exception字段(self):
        """exc_info 为 None 时输出不含 exception 字段"""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="正常消息",
            args=(),
            exc_info=None,
        )
        record.request_id = ""
        record.user_id = 0

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" not in parsed


class TestRequestIDFilter:
    """RequestIDFilter 从 contextvars 注入上下文到 LogRecord"""

    def test_注入request_id和user_id(self):
        """filter 应从 contextvars 读取并写入 record"""
        # 使用 ContextVar.set() 设置上下文值（monkeypatch 无法 patch read-only ContextVar.get）
        token_rid = request_id_var.set("req-filter-001")
        token_uid = user_id_var.set(42)

        try:
            filt = RequestIDFilter()
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="t.py", lineno=1,
                msg="test", args=(), exc_info=None,
            )

            result = filt.filter(record)
            assert result is True
            assert record.request_id == "req-filter-001"
            assert record.user_id == 42
        finally:
            request_id_var.reset(token_rid)
            user_id_var.reset(token_uid)

    def test_contextvars为空时注入空字符串和0(self):
        """request_id 空时注入 ""，user_id 空时注入 0（默认值）"""
        # 确保 contextvars 处于默认状态（空字符串和 0）
        # ContextVar 默认值由构造函数的 default 参数决定
        filt = RequestIDFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py", lineno=1,
            msg="test", args=(), exc_info=None,
        )

        filt.filter(record)
        assert record.request_id == ""
        assert record.user_id == 0


class TestSetupLogging:
    """setup_logging() 配置 root logger"""

    def test_debug模式使用人类可读格式(self):
        """debug=True 时应使用非 JSON formatter"""
        setup_logging(debug=True)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)

        # debug 模式：非 JSON formatter
        formatter = handler.formatter
        assert not isinstance(formatter, JSONFormatter)

        # 输出人类可读日志以验证
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py", lineno=1,
            msg="开发环境日志", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "开发环境日志" in output
        # 人类可读格式不含 JSON 花括号开头
        assert not output.strip().startswith("{")

    def test_非debug模式使用JSONFormatter(self):
        """debug=False 时应使用 JSONFormatter"""
        setup_logging(debug=False)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]

        formatter = handler.formatter
        assert isinstance(formatter, JSONFormatter)

    def test_重复调用不累积handler(self):
        """多次调用 setup_logging 不累积重复 handler"""
        setup_logging(debug=False)
        count_first = len(logging.getLogger().handlers)

        setup_logging(debug=False)
        count_second = len(logging.getLogger().handlers)

        assert count_first == count_second
        assert count_first == 1

    def test_第三方库日志级别被抑制(self):
        """httpx / sqlalchemy.engine 等第三方 logger 级别应为 WARNING"""
        setup_logging(debug=False)

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
        assert logging.getLogger("aiomysql").level == logging.WARNING

    def test_handler含RequestIDFilter(self):
        """所有 handler 都应添加 RequestIDFilter"""
        setup_logging(debug=False)

        root = logging.getLogger()
        handler = root.handlers[0]
        filters = handler.filters
        assert any(isinstance(f, RequestIDFilter) for f in filters)


class TestContextVars:
    """contextvars 跨请求传递"""

    def test_request_id_var默认值为空字符串(self):
        """新 context 中 request_id_var 默认值为 "" """
        assert request_id_var.get() == ""

    def test_user_id_var默认值为0(self):
        """新 context 中 user_id_var 默认值为 0"""
        assert user_id_var.get() == 0

    def test_get_request_id返回当前值(self):
        """get_request_id() 应返回当前 context 的 request_id"""
        token = request_id_var.set("test-req-id")
        assert get_request_id() == "test-req-id"
        request_id_var.reset(token)

    def test_get_user_id返回当前值(self):
        """get_user_id() 应返回当前 context 的 user_id"""
        token = user_id_var.set(99)
        assert get_user_id() == 99
        user_id_var.reset(token)

    def test_set后get返回新值(self):
        """set 后 get 应返回新设置的值"""
        token_rid = request_id_var.set("new-request-id")
        token_uid = user_id_var.set(55)

        assert request_id_var.get() == "new-request-id"
        assert user_id_var.get() == 55

        request_id_var.reset(token_rid)
        user_id_var.reset(token_uid)

    def test_reset后恢复默认值(self):
        """reset 后应恢复为默认值"""
        token_rid = request_id_var.set("temp-id")
        request_id_var.reset(token_rid)
        assert request_id_var.get() == ""

        token_uid = user_id_var.set(10)
        user_id_var.reset(token_uid)
        assert user_id_var.get() == 0
