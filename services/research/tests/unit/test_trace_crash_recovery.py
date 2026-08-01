"""测试 TraceRecorder 在断点续跑场景下的行为 —— 模拟崩溃恢复全流程。

验证：
1. checkpoint snapshot() 中间持久化
2. 恢复时 previous_trace 预加载
3. finish() 合并所有阶段（preloaded + newly recorded）
4. phase_durations_ms / breakdown / phases 完整性
"""
import pytest
from app.core.trace_recorder import TraceRecorder


class TestCrashRecoveryTraceMerge:
    """模拟崩溃恢复全流程的 Trace 合并测试。

    场景：Worker 在 Phase 4 (rerank) 执行前崩溃，Phase 1-3 已完成并通过
    checkpoint 持久化到 task.trace。恢复时从 task.trace 读取 previous_trace，
    Phase 1-3 被跳过（step 终态检查），Phase 4-7 重新执行。
    """

    def test_preload_from_snapshot_then_finish_includes_all_phases(self):
        """核心场景：snapshot → preload → 补录后续阶段 → finish 产出完整七阶段 trace"""
        # ── 第一次运行：Phase 1-3 完成，Phase 4 崩溃 ──
        rec1 = TraceRecorder(
            task_id="task-001",
            user_id=1,
            topic="测试主题",
        )

        # Phase 1: Planning
        rec1.record_planning(
            duration_ms=4500,
            input_tokens=800,
            output_tokens=200,
            sub_questions_count=3,
            model="gpt-4",
        )
        # Phase 2: Search
        rec1.record_search(
            duration_ms=3200,
            total_results=50,
            success_count=48,
            cost_usd=0.05,
        )
        # Phase 3: Fetch
        rec1.record_fetch(
            duration_ms=15000,
            total_urls=15,
            success_count=12,
            failed_count=3,
            cost_usd=0.10,
        )

        # checkpoint: 模拟 Phase 3 完成后持久化到 DB
        checkpoint_trace = rec1.snapshot()

        # 验证 checkpoint 包含 Phase 1-3
        assert checkpoint_trace["phases"]["planning"] is not None
        assert checkpoint_trace["phases"]["search"] is not None
        assert checkpoint_trace["phases"]["fetch"] is not None
        assert checkpoint_trace["phases"]["rerank"] is None
        assert checkpoint_trace["phases"]["synthesis"] is None
        assert checkpoint_trace["phases"]["evidence_graph"] is None
        assert checkpoint_trace["phases"]["render"] is None

        # 验证 checkpoint phase_durations_ms 仅包含已执行阶段
        assert "planning" in checkpoint_trace["phase_durations_ms"]
        assert "search" in checkpoint_trace["phase_durations_ms"]
        assert "fetch" in checkpoint_trace["phase_durations_ms"]
        assert "rerank" not in checkpoint_trace["phase_durations_ms"]
        assert checkpoint_trace["phase_durations_ms"]["planning"] == 4500
        assert checkpoint_trace["phase_durations_ms"]["search"] == 3200
        assert checkpoint_trace["phase_durations_ms"]["fetch"] == 15000

        # 验证 checkpoint 总耗时
        assert checkpoint_trace["total_duration_ms"] == 4500 + 3200 + 15000

        # ── 第二次运行（恢复）：从 task.trace 读取 previous_trace ──
        rec2 = TraceRecorder(
            task_id="task-001",
            user_id=1,
            topic="测试主题",
            previous_trace=checkpoint_trace,
        )

        # 验证 preload 成功：_xxx_data 已设置
        assert rec2._planning_data is not None
        assert rec2._planning_data["duration_ms"] == 4500
        assert rec2._search_data is not None
        assert rec2._search_data["duration_ms"] == 3200
        assert rec2._fetch_data is not None
        assert rec2._fetch_data["duration_ms"] == 15000

        # Phase 1-3 被跳过（step 终态），不调用 record_*
        # Phase 4: Rerank（重新执行）
        rec2.record_rerank(
            duration_ms=12000,
            bm25_candidates=30,
            llm_reranked=10,
            input_tokens=5000,
            output_tokens=800,
            model="gpt-4",
        )
        # Phase 5: Synthesis
        rec2.record_synthesis(
            duration_ms=35000,
            input_tokens=15000,
            output_tokens=5000,
            clusters_count=8,
            model="gpt-4",
        )
        # Phase 6: Evidence Graph
        rec2.record_evidence_graph(
            duration_ms=150,
            evidence_count=25,
            source_count=10,
        )
        # Phase 7: Render
        rec2.record_render(
            duration_ms=28000,
            input_tokens=10000,
            output_tokens=6000,
            sections_count=9,
            citations_count=37,
            model="gpt-4",
        )

        # ── finish() 产出最终 trace ──
        final_trace = rec2.finish()

        # === 断言：phases 完整性 ===
        phases = final_trace["phases"]
        assert phases["planning"] is not None, "planning phase 丢失"
        assert phases["search"] is not None, "search phase 丢失"
        assert phases["fetch"] is not None, "fetch phase 丢失"
        assert phases["rerank"] is not None
        assert phases["synthesis"] is not None
        assert phases["evidence_graph"] is not None
        assert phases["render"] is not None

        # === 断言：phase_durations_ms 包含全部 7 个阶段 ===
        durations = final_trace["phase_durations_ms"]
        expected_phases = [
            "planning", "search", "fetch", "rerank",
            "synthesis", "evidence_graph", "render",
        ]
        for phase_name in expected_phases:
            assert phase_name in durations, (
                f"{phase_name} 缺失于 phase_durations_ms，keys={list(durations.keys())}"
            )

        # === 断言：各阶段时长正确 ===
        assert durations["planning"] == 4500
        assert durations["search"] == 3200
        assert durations["fetch"] == 15000
        assert durations["rerank"] == 12000
        assert durations["synthesis"] == 35000
        assert durations["evidence_graph"] == 150
        assert durations["render"] == 28000

        # === 断言：总耗时正确 ===
        expected_total = 4500 + 3200 + 15000 + 12000 + 35000 + 150 + 28000
        assert final_trace["total_duration_ms"] == expected_total, (
            f"total_duration_ms={final_trace['total_duration_ms']}, expected={expected_total}"
        )

        # === 断言：breakdown 包含全部 7 个阶段 ===
        breakdown = final_trace["breakdown"]
        for phase_name in expected_phases:
            assert phase_name in breakdown, (
                f"{phase_name} 缺失于 breakdown"
            )

        # === 断言：token 总计正确 ===
        # planning: 800+200=1000, search: 0 (no tokens), fetch: 0,
        # rerank: 5000+800=5800, synthesis: 15000+5000=20000,
        # evidence_graph: 0, render: 10000+6000=16000
        expected_total_input = 800 + 0 + 0 + 5000 + 15000 + 0 + 10000
        expected_total_output = 200 + 0 + 0 + 800 + 5000 + 0 + 6000
        assert final_trace["total_input_tokens"] == expected_total_input, (
            f"total_input_tokens={final_trace['total_input_tokens']}, expected={expected_total_input}"
        )
        assert final_trace["total_output_tokens"] == expected_total_output, (
            f"total_output_tokens={final_trace['total_output_tokens']}, expected={expected_total_output}"
        )
        assert final_trace["total_tokens"] == expected_total_input + expected_total_output

    def test_snapshot_is_idempotent(self):
        """snapshot() 多次调用不改变内部状态"""
        rec = TraceRecorder(task_id="t1", user_id=1, topic="test")
        rec.record_planning(duration_ms=1000, input_tokens=100, output_tokens=50, model="gpt-4")

        snap1 = rec.snapshot()
        snap2 = rec.snapshot()
        snap3 = rec.snapshot()

        assert snap1 == snap2 == snap3

        # 验证内部状态未变
        assert rec._planning_data is not None
        assert rec._current_run_phases == {"planning"}

    def test_finish_without_previous_trace(self):
        """无 previous_trace 时 finish() 正常产出（非续跑场景）"""
        rec = TraceRecorder(task_id="t1", user_id=1, topic="test")
        rec.record_planning(duration_ms=1000, input_tokens=100, output_tokens=50, model="gpt-4")
        rec.record_search(duration_ms=2000, total_results=10, cost_usd=0.01)

        trace = rec.finish()

        assert trace["phases"]["planning"] is not None
        assert trace["phases"]["search"] is not None
        assert trace["phase_durations_ms"]["planning"] == 1000
        assert trace["phase_durations_ms"]["search"] == 2000
        assert trace["total_duration_ms"] == 3000

    def test_previous_trace_none_handled_gracefully(self):
        """previous_trace=None 时不崩溃"""
        rec = TraceRecorder(
            task_id="t1", user_id=1, topic="test",
            previous_trace=None,
        )
        rec.record_planning(duration_ms=1000, input_tokens=100, output_tokens=50, model="gpt-4")
        trace = rec.finish()
        assert trace["phases"]["planning"] is not None
        assert trace["total_duration_ms"] == 1000

    def test_previous_trace_empty_dict_handled(self):
        """previous_trace={} 不崩溃"""
        rec = TraceRecorder(
            task_id="t1", user_id=1, topic="test",
            previous_trace={},
        )
        rec.record_planning(duration_ms=1000, input_tokens=100, output_tokens=50, model="gpt-4")
        trace = rec.finish()
        assert trace["phases"]["planning"] is not None

    def test_previous_trace_stale_format(self):
        """old-format previous_trace (no phases key) 不崩溃"""
        rec = TraceRecorder(
            task_id="t1", user_id=1, topic="test",
            previous_trace={"total_duration_ms": 5000},
        )
        rec.record_planning(duration_ms=1000, input_tokens=100, output_tokens=50, model="gpt-4")
        trace = rec.finish()
        assert trace["phases"]["planning"] is not None
        # 不因缺少 phases key 而崩溃
        assert trace["total_duration_ms"] == 1000

    def test_merge_flag_prevents_double_merge(self):
        """_merged 标志防止 _merge_skipped_previous_phases 重复执行"""
        prev_trace = {
            "phases": {
                "planning": {
                    "duration_ms": 1000, "input_tokens": 100,
                    "output_tokens": 50, "model": "gpt-4",
                },
            },
            "breakdown": {
                "planning": {"tokens": 150, "cost": 0.001},
            },
        }
        rec = TraceRecorder(
            task_id="t2", user_id=1, topic="test",
            previous_trace=prev_trace,
        )
        # 第一次 finish
        t1 = rec.finish()
        assert t1 is not None

        # 第二次 finish：不应因重复 merge 导致 token 翻倍
        t2 = rec.finish()
        assert t2["total_input_tokens"] == t1["total_input_tokens"]
        assert t2["total_output_tokens"] == t1["total_output_tokens"]
        assert t2["total_tokens"] == t1["total_tokens"]

    def test_full_pipeline_crash_at_every_phase(self):
        """参数化：在任一 Phase 崩溃，恢复后 trace 均完整"""
        all_phases = [
            ("planning", "record_planning", {"duration_ms": 1000, "input_tokens": 100, "output_tokens": 50, "model": "gpt-4"}),
            ("search", "record_search", {"duration_ms": 500, "total_results": 10, "cost_usd": 0.01}),
            ("fetch", "record_fetch", {"duration_ms": 2000, "total_urls": 5, "success_count": 4, "cost_usd": 0.02}),
            ("rerank", "record_rerank", {"duration_ms": 800, "input_tokens": 200, "output_tokens": 30, "model": "gpt-4"}),
            ("synthesis", "record_synthesis", {"duration_ms": 3000, "input_tokens": 1000, "output_tokens": 400, "model": "gpt-4"}),
            ("evidence_graph", "record_evidence_graph", {"duration_ms": 100, "evidence_count": 10, "source_count": 5}),
            ("render", "record_render", {"duration_ms": 1500, "input_tokens": 500, "output_tokens": 200, "model": "gpt-4"}),
        ]

        for crash_after_index in range(len(all_phases)):
            crash_phase_name = all_phases[crash_after_index][0]

            # 第一次运行：执行到 crash_after_index（含）
            rec1 = TraceRecorder(task_id="t-crash", user_id=1, topic="test")
            for i in range(crash_after_index + 1):
                _, method_name, kwargs = all_phases[i]
                getattr(rec1, method_name)(**kwargs)

            checkpoint_trace = rec1.snapshot()

            # 恢复：从 checkpoint 开始，执行剩余阶段
            rec2 = TraceRecorder(
                task_id="t-crash", user_id=1, topic="test",
                previous_trace=checkpoint_trace,
            )
            for i in range(crash_after_index + 1, len(all_phases)):
                _, method_name, kwargs = all_phases[i]
                getattr(rec2, method_name)(**kwargs)

            final_trace = rec2.finish()

            # 验证：所有 7 个阶段都在 phase_durations_ms 中
            durations = final_trace["phase_durations_ms"]
            for phase_name, _, _ in all_phases:
                assert phase_name in durations, (
                    f"崩溃在 {crash_phase_name} 之后，恢复后 {phase_name} 缺失于 phase_durations_ms"
                )

            # 验证：总耗时等于各阶段之和
            expected_total = sum(durations.values())
            assert final_trace["total_duration_ms"] == expected_total, (
                f"崩溃在 {crash_phase_name}: total={final_trace['total_duration_ms']}, "
                f"expected={expected_total}, durations={durations}"
            )

            # 验证：phases 字段无 None
            for phase_name, _, _ in all_phases:
                assert final_trace["phases"][phase_name] is not None, (
                    f"崩溃在 {crash_phase_name} 之后，恢复后 phases.{phase_name} 为 null"
                )
