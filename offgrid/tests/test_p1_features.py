"""
P1 feature tests: OFFGRID.md, Planner, Checkpoint, DocReader.
"""

import json
import os
import shutil
import tempfile
import time

import pytest


# ── Task 1: OFFGRID.md ──────────────────────────────────────

class TestKwcodeMd:

    def test_load_offgrid_md_basic(self):
        from offgrid.core.offgrid_md import load_offgrid_md
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "OFFGRID.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("""# OFFGRID.md

## [all] 通用规则
- 测试框架：pytest
- 认证逻辑在：src/auth/

## [bugfix] Bug修复规则
- 修复前先理解错误原因
- 不要改测试代码

## [codegen] 代码生成规则
- 变量命名用snake_case
""")
            sections = load_offgrid_md(d)
            assert "all" in sections
            assert "pytest" in sections["all"]
            assert "bugfix" in sections
            assert "不要改测试代码" in sections["bugfix"]
            assert "codegen" in sections
            assert "snake_case" in sections["codegen"]

    def test_load_offgrid_md_missing_file(self):
        from offgrid.core.offgrid_md import load_offgrid_md
        with tempfile.TemporaryDirectory() as d:
            sections = load_offgrid_md(d)
            assert sections == {}

    def test_load_offgrid_md_no_tags(self):
        """No section tags → everything goes to 'all'."""
        from offgrid.core.offgrid_md import load_offgrid_md
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "OFFGRID.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("- 使用pytest\n- 代码风格PEP8\n")
            sections = load_offgrid_md(d)
            assert "all" in sections
            assert "pytest" in sections["all"]

    def test_build_offgrid_system_injection(self):
        from offgrid.core.offgrid_md import build_offgrid_system
        sections = {
            "all": "- 测试框架：pytest",
            "bugfix": "- 修复前先理解错误原因",
            "codegen": "- 变量命名用snake_case",
        }
        # locator_repair → should inject all + bugfix
        result = build_offgrid_system("locator_repair", sections)
        assert "pytest" in result
        assert "修复前" in result
        assert "snake_case" not in result

        # codegen → should inject all + codegen
        result = build_offgrid_system("codegen", sections)
        assert "pytest" in result
        assert "snake_case" in result
        assert "修复前" not in result

    def test_build_offgrid_system_empty(self):
        from offgrid.core.offgrid_md import build_offgrid_system
        assert build_offgrid_system("codegen", {}) == ""

    def test_build_offgrid_system_truncation(self):
        """P1-RED-1: token cap at ~4800 chars."""
        from offgrid.core.offgrid_md import build_offgrid_system
        sections = {"all": "x" * 6000}
        result = build_offgrid_system("codegen", sections)
        assert len(result) <= 5000  # 4800 + some overhead
        assert "已截断" in result

    def test_generate_offgrid_template(self):
        from offgrid.core.offgrid_md import generate_offgrid_template
        with tempfile.TemporaryDirectory() as d:
            result = generate_offgrid_template(d)
            assert "✓" in result
            path = os.path.join(d, "OFFGRID.md")
            assert os.path.exists(path)
            content = open(path, encoding="utf-8").read()
            assert "[all]" in content
            assert "[bugfix]" in content
            assert "pytest" in content

    def test_generate_offgrid_template_skip_existing(self):
        from offgrid.core.offgrid_md import generate_offgrid_template
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "OFFGRID.md")
            with open(path, "w") as f:
                f.write("existing")
            result = generate_offgrid_template(d)
            assert "已存在" in result

    def test_generate_offgrid_template_nodejs(self):
        from offgrid.core.offgrid_md import generate_offgrid_template
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "package.json"), "w") as f:
                f.write("{}")
            generate_offgrid_template(d)
            content = open(os.path.join(d, "OFFGRID.md"), encoding="utf-8").read()
            assert "npm test" in content

    def test_global_offgrid_md_fallback(self):
        """Falls back to ~/.offgrid/OFFGRID.md when project root has none."""
        from offgrid.core.offgrid_md import load_offgrid_md
        global_dir = os.path.join(os.path.expanduser("~"), ".offgrid")
        global_path = os.path.join(global_dir, "OFFGRID.md")
        had_global = os.path.exists(global_path)
        try:
            os.makedirs(global_dir, exist_ok=True)
            with open(global_path, "w", encoding="utf-8") as f:
                f.write("## [all] 全局规则\n- 全局规则测试\n")
            with tempfile.TemporaryDirectory() as d:
                sections = load_offgrid_md(d)
                assert "all" in sections
                assert "全局规则测试" in sections["all"]
        finally:
            if not had_global and os.path.exists(global_path):
                os.remove(global_path)


# ── Task 2: Planner + Risk Assessment ──────────────────────

class TestPlanner:

    def test_estimate_risk_low(self):
        from offgrid.core.planner import estimate_risk
        assert estimate_risk("locator", 1, 1, False, 0, 0.9) == "Low"

    def test_estimate_risk_medium(self):
        from offgrid.core.planner import estimate_risk
        assert estimate_risk("generator", 2, 4, False, 1, 0.8) == "Medium"

    def test_estimate_risk_high(self):
        from offgrid.core.planner import estimate_risk
        assert estimate_risk("generator", 5, 10, True, 3, 0.4) == "High"

    def test_estimate_risk_history_dominates(self):
        """Historical failures should push risk up even with simple task."""
        from offgrid.core.planner import estimate_risk
        result = estimate_risk("locator", 1, 1, False, 3, 0.9)
        assert result in ("Medium", "High")

    def test_plan_step_dataclass(self):
        from offgrid.core.planner import PlanStep
        step = PlanStep(index=1, description="test", risk="Low", risk_reason="ok")
        assert step.index == 1
        assert step.target_files == []

    def test_planner_generate_plan_basic(self):
        """Planner generates steps matching pipeline."""
        from offgrid.core.planner import Planner
        from offgrid.core.context import TaskContext

        class MockLocator:
            _retriever = None
        class MockPatternMd:
            def count_similar_failures(self, expert_type, keywords, project_root):
                return 0

        planner = Planner(locator=MockLocator(), pattern_md_module=MockPatternMd())
        ctx = TaskContext(
            user_input="修复登录bug",
            project_root=".",
            gate_result={"expert_type": "locator_repair", "difficulty": "easy"},
        )
        steps = planner.generate_plan(ctx)
        assert len(steps) == 3  # locator + generator + verifier
        assert steps[0].description == "定位相关文件和函数"
        assert steps[2].description.startswith("验证")

    def test_planner_chat_pipeline(self):
        from offgrid.core.planner import Planner
        from offgrid.core.context import TaskContext

        class MockLocator:
            _retriever = None
        class MockPatternMd:
            def count_similar_failures(self, expert_type, keywords, project_root):
                return 0

        planner = Planner(locator=MockLocator(), pattern_md_module=MockPatternMd())
        ctx = TaskContext(
            user_input="你好",
            project_root=".",
            gate_result={"expert_type": "chat", "difficulty": "easy"},
        )
        steps = planner.generate_plan(ctx)
        assert len(steps) == 1
        assert steps[0].risk == "Low"


# ── Task 3: Checkpoint ─────────────────────────────────────

class TestCheckpoint:

    def test_checkpoint_file_copy_and_restore(self):
        from offgrid.core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as d:
            # Create a test file
            test_file = os.path.join(d, "test.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("original content")

            cp = Checkpoint(d)
            assert cp.save([test_file])

            # Modify the file
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("modified content")

            # Restore
            assert cp.restore()
            with open(test_file, encoding="utf-8") as f:
                assert f.read() == "original content"

    def test_checkpoint_discard(self):
        from offgrid.core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as d:
            test_file = os.path.join(d, "test.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("content")

            cp = Checkpoint(d)
            cp.save([test_file])
            cp.discard()  # Should not raise

    def test_checkpoint_restore_without_save(self):
        from offgrid.core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as d:
            cp = Checkpoint(d)
            assert not cp.restore()

    def test_checkpoint_git_detection(self):
        from offgrid.core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as d:
            cp = Checkpoint(d)
            assert not cp._is_git

            os.makedirs(os.path.join(d, ".git"))
            cp2 = Checkpoint(d)
            assert cp2._is_git

    def test_list_checkpoints_empty(self):
        from offgrid.core.checkpoint import list_checkpoints
        # Should not crash even if dir doesn't exist
        result = list_checkpoints()
        assert isinstance(result, list)

    def test_checkpoint_manifest_based_restore(self):
        """Manifest-based restore preserves directory structure."""
        from offgrid.core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as d:
            subdir = os.path.join(d, "src")
            os.makedirs(subdir)
            test_file = os.path.join(subdir, "app.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("def main(): pass")

            cp = Checkpoint(d)
            cp.save([test_file])

            with open(test_file, "w", encoding="utf-8") as f:
                f.write("def main(): broken")

            cp.restore()
            with open(test_file, encoding="utf-8") as f:
                assert f.read() == "def main(): pass"


# ── Task 4: DocReader ──────────────────────────────────────

class TestDocReader:

    def test_find_relevant_md(self):
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
                f.write("""# Project

This project uses JWT authentication for all API endpoints.
The auth module is in src/auth/jwt.py.

## Database

We use PostgreSQL with SQLAlchemy ORM.
Connection pooling is configured in src/db/pool.py.
""")
            reader = DocReader(d)
            result = reader.find_relevant("JWT authentication login")
            assert "JWT" in result or "auth" in result

    def test_find_relevant_empty_project(self):
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            reader = DocReader(d)
            assert reader.find_relevant("anything") == ""

    def test_find_relevant_txt(self):
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as f:
                f.write("The payment gateway uses Stripe API v3.\nAPI key is stored in environment variables.\n\n"
                        "Error handling follows the retry pattern with exponential backoff.\n")
            reader = DocReader(d)
            result = reader.find_relevant("Stripe payment API")
            assert "Stripe" in result or "payment" in result

    def test_skip_dirs(self):
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            # File in .git should be skipped
            git_dir = os.path.join(d, ".git")
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "notes.md"), "w") as f:
                f.write("This should be skipped because it is very long content in git dir.\n")
            reader = DocReader(d)
            assert reader.find_relevant("notes") == ""

    def test_token_budget(self):
        """Output should respect max_tokens budget."""
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "big.md"), "w", encoding="utf-8") as f:
                for i in range(100):
                    f.write(f"Paragraph {i}: " + "word " * 50 + "\n\n")
            reader = DocReader(d)
            result = reader.find_relevant("Paragraph", max_tokens=200)
            assert len(result) <= 200 * 4 + 100  # Some overhead for formatting

    def test_cache(self):
        from offgrid.knowledge.doc_reader import DocReader
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "doc.md"), "w", encoding="utf-8") as f:
                f.write("This is a test document with enough content to be a paragraph.\n")
            reader = DocReader(d)
            reader.find_relevant("test")
            # Second call should use cache
            assert str(os.path.join(d, "doc.md")) in reader._cache


# ── PatternMd.count_similar_failures ───────────────────────

class TestPatternMdFailures:

    def test_count_similar_failures_basic(self):
        from offgrid.memory import pattern_md
        with tempfile.TemporaryDirectory() as d:
            # Create stats with failures
            stats = {
                "locator_repair": {
                    "count": 5,
                    "success": 3,
                    "total_elapsed": 50.0,
                    "last_trigger": "2026-04-28 10:00",
                    "recent_failures": [
                        "[2026-04-28 09:00] IndexError in parser.py",
                        "[2026-04-28 09:30] TypeError in auth module",
                    ],
                }
            }
            pattern_md._save_stats(d, stats)
            count = pattern_md.count_similar_failures(
                expert_type="locator_repair",
                keywords=["parser", "IndexError"],
                project_root=d,
            )
            assert count >= 1

    def test_count_similar_failures_no_match(self):
        from offgrid.memory import pattern_md
        with tempfile.TemporaryDirectory() as d:
            stats = {
                "locator_repair": {
                    "count": 2,
                    "success": 1,
                    "total_elapsed": 20.0,
                    "last_trigger": "",
                    "recent_failures": ["[2026-04-28] some error"],
                }
            }
            pattern_md._save_stats(d, stats)
            count = pattern_md.count_similar_failures(
                expert_type="codegen",
                keywords=["unrelated"],
                project_root=d,
            )
            assert count == 0

    def test_count_similar_failures_empty(self):
        from offgrid.memory import pattern_md
        with tempfile.TemporaryDirectory() as d:
            count = pattern_md.count_similar_failures(
                expert_type="codegen",
                keywords=["test"],
                project_root=d,
            )
            assert count == 0


# ── Integration: context fields ────────────────────────────

class TestContextFields:

    def test_task_context_new_fields(self):
        from offgrid.core.context import TaskContext
        ctx = TaskContext()
        assert ctx.doc_context == ""
        assert ctx.offgrid_rules == ""
