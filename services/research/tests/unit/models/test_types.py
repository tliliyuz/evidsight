"""时区策略测试 — 覆盖 app/models/_types.py 的 UTCDateTime TypeDecorator 和 utcnow()。

对齐 TESTING_STRATEGY.md §4.8：
- UTCDateTime aware↔naive 双向转换（写入剥离 tzinfo / 读取附加 UTC）
- utcnow() 返回 aware datetime
"""

from datetime import datetime, timezone

from app.models._types import UTCDateTime, utcnow


class TestUTCDateTime:
    """UTCDateTime TypeDecorator — ORM 层 aware↔naive 双向转换"""

    def test_process_bind_param_aware_datetime写入时剥离tzinfo(self):
        """写入 DB 前：UTC aware → naive UTC 值（剥离 tzinfo）"""
        utc_dt = UTCDateTime()
        aware = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
        result = utc_dt.process_bind_param(aware, dialect=None)
        assert result.tzinfo is None
        assert result == datetime(2026, 6, 20, 12, 0, 0)

    def test_process_bind_param_非UTC时区自动转换后剥离tzinfo(self):
        """写入前：非 UTC aware → 转为 UTC → 剥离 tzinfo"""
        utc_dt = UTCDateTime()
        # UTC+8 → 写入应为 UTC，即 04:00
        cst = timezone(timedelta(hours=8))
        aware_cst = datetime(2026, 6, 20, 12, 0, 0, tzinfo=cst)
        result = utc_dt.process_bind_param(aware_cst, dialect=None)
        assert result.tzinfo is None
        assert result.hour == 4  # 转为 UTC

    def test_process_bind_param_naive视为已是UTC直接剥离(self):
        """naive datetime 视为已是 UTC 值，直接剥离 tzinfo（仍为 None）"""
        utc_dt = UTCDateTime()
        naive = datetime(2026, 6, 20, 12, 0, 0)
        result = utc_dt.process_bind_param(naive, dialect=None)
        assert result.tzinfo is None
        assert result == naive

    def test_process_bind_param_None返回None(self):
        utc_dt = UTCDateTime()
        assert utc_dt.process_bind_param(None, dialect=None) is None

    def test_process_result_value_读取时附加UTC_tzinfo(self):
        """从 DB 读取后：naive → 附加 UTC tzinfo → aware"""
        utc_dt = UTCDateTime()
        naive = datetime(2026, 6, 20, 12, 0, 0)
        result = utc_dt.process_result_value(naive, dialect=None)
        assert result.tzinfo == timezone.utc
        # 时间数值不变
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 20
        assert result.hour == 12

    def test_process_result_value_None返回None(self):
        utc_dt = UTCDateTime()
        assert utc_dt.process_result_value(None, dialect=None) is None


class TestUtcnow:
    """utcnow() 返回 UTC aware datetime"""

    def test_返回aware_datetime带UTC_tzinfo(self):
        result = utcnow()
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_写入UTCDateTime不丢失信息(self):
        """验证 utcnow() 的值经 UTCDateTime 完整读写后保持一致"""
        utc_dt = UTCDateTime()
        now = utcnow()
        # 模拟写入→读取完整链路
        stored = utc_dt.process_bind_param(now, dialect=None)
        restored = utc_dt.process_result_value(stored, dialect=None)
        # 恢复后的 aware datetime 应与原始值在同一时刻
        assert restored.tzinfo == timezone.utc
        # 数值相同（去掉微秒因为 MySQL DATETIME 可能不支持微秒）
        assert restored.replace(microsecond=0) == now.replace(microsecond=0)


# 需要 timedelta 在稍后导入中用
from datetime import timedelta
