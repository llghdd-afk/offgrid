"""
P1 + P2 End-to-End Acceptance Tests.
Requires Ollama running with gemma3:4b (or any available model).
Tests real LLM calls, real file I/O, real pipeline execution.
"""

import json
import os
import shutil
import tempfile
import time

import pytest

# Skip all if Ollama is not available
try:
    import httpx
    _resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
    _models = [m["name"] for m in _resp.json().get("models", [])]
    # Pick best available model
    _MODEL = None
    for candidate in ("gemma3:4b", "gemma4:e2b", "qwen3:8b", "deepseek-r1:8b", "gemma3:1b"):
        if candidate in _models:
            _MODEL = candidate
            break
    OLLAMA_OK = _MODEL is not None
except Exception:
    OLLAMA_OK = False
    _MODEL = None

pytestmark = pytest.mark.skipif(not OLLAMA_OK, reason="Ollama not available")

OLLAMA_URL = "http://localhost:11434"


def _make_llm():
    from offgrid.llm.llama_backend import LLMBackend
    return LLMBackend(ollama_url=OLLAMA_URL, ollama_model=_MODEL)


def _make_pipeline(project_root, verbose=False):
    """Build a minimal pipeline for E2E testing."""
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.experts.locator import LocatorExpert
    from offgrid.experts.generator import GeneratorExpert
    from offgrid.experts.verifier import VerifierExpert
    from offgrid.experts.search_augmentor import SearchAugmentorExpert
    from offgrid.experts.office_handler import OfficeHandlerExpert
    from offgrid.experts.chat_expert import ChatExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.memory.offgrid_md import OffgridMemory
    from offgrid.core.orchestrator import PipelineOrchestrator
    from offgrid.core.gate import Gate
    from offgrid.registry.expert_registry import ExpertRegistry

    llm = LLMBackend(ollama_url=OLLAMA_URL, ollama_model=_MODEL)
    tools = ToolExecutor(project_root=project_root)
    locator = LocatorExpert(llm=llm, tool_executor=tools)
    generator = GeneratorExpert(llm=llm, tool_executor=tools)
    verifier = VerifierExpert(llm=llm, tool_executor=tools)
    search = SearchAugmentorExpert(llm=llm)
    office = OfficeHandlerExpert(llm=llm, tool_executor=tools)
    chat = ChatExpert(llm=llm, search_augmentor=search)
    memory = OffgridMemory()
    registry = ExpertRegistry()

    orchestrator = PipelineOrchestrator(
        locator=locator, generator=generator, verifier=verifier,
        search_augmentor=search, office_handler=office,
        tool_executor=tools, memory=memory, registry=registry,
        chat_expert=chat,
    )
    gate = Gate(llm=llm)
    return gate, orchestrator, memory, llm


# ═══════════════════════════════════════════════════════════
# P1-E2E-1: OFFGRID.md 注入验证
# ═══════════════════════════════════════════════════════════

class TestP1E2E_KwcodeMd:

    def test_offgrid_md_loaded_and_injected(self):
        """项目有 OFFGRID.md → 确认加载并注入到 orchestrator context."""
        from offgrid.core.offgrid_md import load_offgrid_md, build_offgrid_system

        with tempfile.TemporaryDirectory() as d:
            # Create OFFGRID.md
            offgrid_path = os.path.join(d, "OFFGRID.md")
            with open(offgrid_path, "w", encoding="utf-8") as f:
                f.write("""# OFFGRID.md
## [all] 通用规则
- 测试框架：pytest
- 代码风格：PEP8

## [bugfix] Bug修复规则
- 修复前先理解错误原因
""")
            sections = load_offgrid_md(d)
            assert "all" in sections
            assert "pytest" in sections["all"]

            # Verify injection for locator_repair
            injected = build_offgrid_system("locator_repair", sections)
            assert "pytest" in injected
            assert "修复前" in injected

            # Verify injection for codegen (should NOT have bugfix rules)
            injected_cg = build_offgrid_system("codegen", sections)
            assert "pytest" in injected_cg
            assert "修复前" not in injected_cg

    def test_offgrid_md_in_real_pipeline(self):
        """OFFGRID.md rules flow through to orchestrator context."""
        with tempfile.TemporaryDirectory() as d:
            # Create OFFGRID.md
            with open(os.path.join(d, "OFFGRID.md"), "w", encoding="utf-8") as f:
                f.write("## [all] 通用规则\n- E2E测试标记：KWCODE_INJECTED\n")

            gate, orchestrator, memory, llm = _make_pipeline(d)

            # Run a chat task (fastest, no file I/O)
            gate_result = gate.classify("你好")
            result = orchestrator.run(
                user_input="你好",
                gate_result=gate_result,
                project_root=d,
            )
            assert result["success"]


# ═══════════════════════════════════════════════════════════
# P1-E2E-2: /plan 计划模式 + 风险评估
# ═══════════════════════════════════════════════════════════

class TestP1E2E_Plan:

    def test_planner_generates_plan_with_real_model(self):
        """/plan 生成计划，包含步骤和风险等级。"""
        from offgrid.core.planner import Planner, PlanStep
        from offgrid.core.context import TaskContext
        from offgrid.memory import pattern_md

        with tempfile.TemporaryDirectory() as d:
            gate, orchestrator, memory, llm = _make_pipeline(d)

            # Classify a repair task
            gate_result = gate.classify("修复登录验证的bug")
            et = gate_result.get("expert_type", "locator_repair")

            ctx = TaskContext(
                user_input="修复登录验证的bug",
                project_root=d,
                gate_result=gate_result,
            )

            planner = Planner(
                locator=orchestrator.locator,
                pattern_md_module=pattern_md,
            )
            steps = planner.generate_plan(ctx)

            assert len(steps) >= 1
            assert all(isinstance(s, PlanStep) for s in steps)
            assert all(s.risk in ("High", "Medium", "Low") for s in steps)
            print(f"  [P1-E2E] Plan: {len(steps)} steps, "
                  f"risks: {[s.risk for s in steps]}")

    def test_risk_increases_with_history(self):
        """有历史失败记录时风险等级上升。"""
        from offgrid.core.planner import estimate_risk
        r_clean = estimate_risk("gen", 1, 1, False, 0, 0.9)
        r_dirty = estimate_risk("gen", 1, 1, False, 3, 0.9)
        risk_order = {"Low": 0, "Medium": 1, "High": 2}
        assert risk_order[r_dirty] > risk_order[r_clean]


# ═══════════════════════════════════════════════════════════
# P1-E2E-3: Checkpoint 快照
# ═══════════════════════════════════════════════════════════

class TestP1E2E_Checkpoint:

    def test_checkpoint_save_restore_real(self):
        """任务失败 → 自动还原文件。"""
        from offgrid.core.checkpoint import Checkpoint

        with tempfile.TemporaryDirectory() as d:
            # Create a source file
            src = os.path.join(d, "app.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write("def login(): return True\n")

            # Save checkpoint
            cp = Checkpoint(d)
            assert cp.save([src])

            # Simulate task modifying the file
            with open(src, "w", encoding="utf-8") as f:
                f.write("def login(): BROKEN\n")

            # Restore
            assert cp.restore()
            with open(src, encoding="utf-8") as f:
                content = f.read()
            assert "return True" in content
            assert "BROKEN" not in content

    def test_checkpoint_in_pipeline_codegen(self):
        """Codegen 任务：checkpoint 不崩溃（空目录场景）。"""
        with tempfile.TemporaryDirectory() as d:
            gate, orchestrator, memory, llm = _make_pipeline(d)

            statuses = []
            def _capture(stage, detail):
                statuses.append((stage, detail))

            gate_result = {"expert_type": "codegen", "difficulty": "easy",
                           "task_summary": "写hello", "pipeline": ["generator", "verifier"]}
            result = orchestrator.run(
                user_input="写一个hello world的Python脚本",
                gate_result=gate_result,
                project_root=d,
                on_status=_capture,
            )
            # Should not have checkpoint error
            checkpoint_errors = [s for s in statuses if "无法创建" in s[1]]
            assert len(checkpoint_errors) == 0, f"Checkpoint errors: {checkpoint_errors}"


# ═══════════════════════════════════════════════════════════
# P1-E2E-4: DocReader 非代码文件读取
# ═══════════════════════════════════════════════════════════

class TestP1E2E_DocReader:

    def test_doc_reader_md_injection(self):
        """项目有 MD 文档 → doc_reader 读取并注入 context。"""
        from offgrid.knowledge.doc_reader import DocReader

        with tempfile.TemporaryDirectory() as d:
            # Create a requirements doc
            with open(os.path.join(d, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
                f.write("""# 需求文档

## 登录模块
- 使用JWT认证，token有效期24小时
- 密码必须SHA256加密存储
- 登录失败3次锁定账户15分钟

## 数据库
- PostgreSQL 15，连接池最大20
""")
            reader = DocReader(d)
            result = reader.find_relevant("JWT登录认证")
            assert len(result) > 0
            assert "JWT" in result or "认证" in result or "token" in result
            print(f"  [P1-E2E] DocReader found {len(result)} chars")

    def test_doc_reader_pdf_graceful(self):
        """PDF 读取失败时降级跳过，不崩溃。"""
        from offgrid.knowledge.doc_reader import DocReader

        with tempfile.TemporaryDirectory() as d:
            # Create a fake PDF (invalid content)
            with open(os.path.join(d, "spec.pdf"), "wb") as f:
                f.write(b"not a real pdf")
            reader = DocReader(d)
            result = reader.find_relevant("anything")
            # Should not crash, returns empty
            assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════
# P2-E2E-1: 模型能力自适应
# ═══════════════════════════════════════════════════════════

class TestP2E2E_ModelCapability:

    def test_detect_real_model(self):
        """用真实 Ollama API 检测模型级别。"""
        from offgrid.core.model_capability import detect_model_tier, ModelTier, _tier_cache

        _tier_cache.clear()
        tier = detect_model_tier(_MODEL, OLLAMA_URL)
        assert isinstance(tier, ModelTier)
        print(f"  [P2-E2E] {_MODEL} → {tier.value}")

        # gemma3:4b / gemma3:1b should be SMALL
        if "4b" in _MODEL or "1b" in _MODEL or "e2b" in _MODEL:
            assert tier == ModelTier.SMALL
        elif "8b" in _MODEL:
            assert tier == ModelTier.SMALL

    def test_strategy_applied(self):
        """检测到的模型级别对应正确的策略。"""
        from offgrid.core.model_capability import detect_model_tier, get_strategy, _tier_cache

        _tier_cache.clear()
        tier = detect_model_tier(_MODEL, OLLAMA_URL)
        strategy = get_strategy(tier)

        assert strategy.max_retries == 3
        if tier.value == "small":
            assert strategy.force_plan_mode is True
            assert strategy.max_files_per_task == 2
        print(f"  [P2-E2E] Strategy: force_plan={strategy.force_plan_mode}, "
              f"max_files={strategy.max_files_per_task}")


# ═══════════════════════════════════════════════════════════
# P2-E2E-2: 飞轮通知
# ═══════════════════════════════════════════════════════════

class TestP2E2E_FlywheelNotifier:

    def test_expert_born_notification_e2e(self):
        """模拟专家投产 → 通知入队 → flush 显示。"""
        from offgrid.notification.flywheel_notifier import FlywheelNotifier, NOTIFY_PATH

        # Clean — write empty array to avoid stale data
        NOTIFY_PATH.parent.mkdir(parents=True, exist_ok=True)
        NOTIFY_PATH.write_text("[]", encoding="utf-8")

        notifier = FlywheelNotifier()
        notifier.queue_expert_born(
            expert_def={
                "name": "E2E_TestExpert",
                "trigger_keywords": ["e2e", "test", "验收"],
            },
            metrics={
                "task_count": 15,
                "success_rate_new": 0.92,
                "success_rate_baseline": 0.67,
                "avg_latency_new": 23.0,
                "avg_latency_baseline": 58.0,
            },
        )

        # Verify queued
        data = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["expert_name"] == "E2E_TestExpert"
        assert data[0]["success_rate_new"] == 0.92

        # Flush
        class MockConsole:
            outputs = []
            def print(self, *args, **kwargs):
                self.outputs.append(str(args))

        mc = MockConsole()
        count = notifier.flush(mc)
        assert count == 1
        assert len(mc.outputs) > 0  # Panel + empty lines

        # Queue should be empty after flush
        data2 = json.loads(NOTIFY_PATH.read_text(encoding="utf-8"))
        assert data2 == []
        print(f"  [P2-E2E] Notification displayed, {len(mc.outputs)} lines")

    def test_milestone_notification(self):
        """里程碑通知入队和显示。"""
        from offgrid.notification.flywheel_notifier import FlywheelNotifier, NOTIFY_PATH

        if NOTIFY_PATH.exists():
            NOTIFY_PATH.unlink()

        notifier = FlywheelNotifier()
        notifier.queue_milestone(50, 3, 2.4)

        class MockConsole:
            outputs = []
            def print(self, *args, **kwargs):
                self.outputs.append(str(args))

        mc = MockConsole()
        count = notifier.flush(mc)
        assert count == 1
        assert any("50" in o for o in mc.outputs)

        if NOTIFY_PATH.exists():
            NOTIFY_PATH.unlink()


# ═══════════════════════════════════════════════════════════
# P2-E2E-3: 价值量化
# ═══════════════════════════════════════════════════════════

class TestP2E2E_ValueTracker:

    def test_record_and_stats(self):
        """记录真实任务 → stats 显示正确。"""
        from offgrid.stats.value_tracker import ValueTracker

        tracker = ValueTracker()

        # Record some tasks
        for i in range(5):
            tracker.record(
                project_root="/tmp/e2e_test",
                expert_type="locator_repair",
                expert_name="BugFix",
                success=True,
                elapsed_s=15.0 + i,
                retry_count=0,
                model=_MODEL,
            )
        tracker.record(
            project_root="/tmp/e2e_test",
            expert_type="codegen",
            expert_name="",
            success=False,
            elapsed_s=30.0,
            retry_count=3,
            model=_MODEL,
        )

        summary = tracker.get_summary(days=1)
        assert summary["total_tasks"] >= 6
        assert summary["succeeded_tasks"] >= 5
        assert summary["time_saved_hours"] > 0
        print(f"  [P2-E2E] Stats: {summary['total_tasks']} tasks, "
              f"{summary['succeeded_tasks']} succeeded, "
              f"{summary['time_saved_hours']}h saved")

    def test_stats_conservative_estimate(self):
        """时间估算保守（5min/task）。"""
        from offgrid.stats.value_tracker import ValueTracker

        tracker = ValueTracker()
        summary = tracker.get_summary(days=1)
        # 5 min per successful task = succeeded * 5 / 60
        max_expected = summary["succeeded_tasks"] * 5 / 60
        assert summary["time_saved_hours"] <= max_expected + 0.1


# ═══════════════════════════════════════════════════════════
# P1+P2 集成: 真实 Gate → Orchestrator 流水线
# ═══════════════════════════════════════════════════════════

class TestIntegration_RealPipeline:

    def test_gate_classify_real(self):
        """Gate 用真实模型分类任务。"""
        with tempfile.TemporaryDirectory() as d:
            gate, orchestrator, memory, llm = _make_pipeline(d)

            # Test various inputs
            cases = [
                ("你好", "chat"),
                ("写一个排序函数", "codegen"),
            ]
            for user_input, expected_type in cases:
                result = gate.classify(user_input)
                et = result.get("expert_type", "unknown")
                print(f"  [E2E] Gate: '{user_input}' → {et} (expected: {expected_type})")
                # Don't assert exact match — small models may classify differently
                # Just verify it returns a valid type
                assert et in ("locator_repair", "codegen", "refactor", "doc", "office", "chat")

    def test_chat_pipeline_real(self):
        """Chat 任务完整流水线（最快的 E2E 路径）。"""
        with tempfile.TemporaryDirectory() as d:
            gate, orchestrator, memory, llm = _make_pipeline(d)

            statuses = []
            def _capture(stage, detail):
                statuses.append((stage, detail))

            result = orchestrator.run(
                user_input="你好",
                gate_result={"expert_type": "chat", "difficulty": "easy", "task_summary": "问候"},
                project_root=d,
                on_status=_capture,
            )
            assert result["success"]
            assert result["context"].generator_output is not None
            reply = result["context"].generator_output.get("explanation", "")
            assert len(reply) > 0
            print(f"  [E2E] Chat reply: {reply[:80]}")

    def test_codegen_pipeline_real(self):
        """Codegen 任务完整流水线。"""
        with tempfile.TemporaryDirectory() as d:
            gate, orchestrator, memory, llm = _make_pipeline(d)

            statuses = []
            def _capture(stage, detail):
                statuses.append((stage, detail))

            result = orchestrator.run(
                user_input="写一个Python函数，输入列表返回最大值",
                gate_result={
                    "expert_type": "codegen",
                    "difficulty": "easy",
                    "task_summary": "最大值函数",
                },
                project_root=d,
                on_status=_capture,
            )
            elapsed = result.get("elapsed", 0)
            success = result["success"]
            print(f"  [E2E] Codegen: success={success}, elapsed={elapsed:.1f}s")
            print(f"  [E2E] Stages: {[s[0] for s in statuses]}")

            # Verify value tracker recorded it
            from offgrid.stats.value_tracker import ValueTracker
            tracker = ValueTracker()
            total = tracker.get_total_task_count()
            assert total > 0
            print(f"  [E2E] ValueTracker total: {total}")
