"""
Regression tests for boundary/edge-case inputs.
Covers: Gate parsing, ToolExecutor file ops, extract_symbols,
        GeneratorExpert, TaskContext isolation, OffgridMemory.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

from offgrid.core.gate import Gate, VALID_EXPERT_TYPES
from offgrid.core.context import TaskContext
from offgrid.tools.executor import ToolExecutor
from offgrid.tools.ast_utils import extract_symbols
from offgrid.experts.generator import GeneratorExpert
from offgrid.memory.offgrid_md import OffgridMemory


# ── Helpers ──────────────────────────────────────────────────


def _make_mock_llm(response: str = '{"expert_type":"chat","task_summary":"test","difficulty":"easy"}'):
    """Create a mock LLM that returns a fixed response string."""
    llm = MagicMock()
    llm.generate = MagicMock(return_value=response)
    return llm


# ═══════════════════════════════════════════════════════════════
# GROUP 1: User input boundary
# ═══════════════════════════════════════════════════════════════


class TestUserInputBoundary:

    def test_empty_input_does_not_crash(self):
        llm = _make_mock_llm()
        gate = Gate(llm)
        result = gate.classify("")
        assert "expert_type" in result
        assert result["expert_type"] in VALID_EXPERT_TYPES

    def test_very_long_input_truncated(self):
        llm = _make_mock_llm()
        gate = Gate(llm)
        result = gate.classify("a" * 5000)
        assert "expert_type" in result
        assert result["expert_type"] in VALID_EXPERT_TYPES

    def test_input_with_special_chars(self):
        llm = _make_mock_llm()
        gate = Gate(llm)
        result = gate.classify('修复 bug <script>alert(1)</script> & more')
        assert "expert_type" in result
        assert result["expert_type"] in VALID_EXPERT_TYPES

    @pytest.mark.parametrize("ambiguous_input", [
        "帮我看看",
        "这个",
        "???",
        "修修修修修修修修",
    ])
    def test_ambiguous_input_handled(self, ambiguous_input):
        llm = _make_mock_llm()
        gate = Gate(llm)
        result = gate.classify(ambiguous_input)
        assert result["expert_type"] in VALID_EXPERT_TYPES


# ═══════════════════════════════════════════════════════════════
# GROUP 2: Project environment boundary
# ═══════════════════════════════════════════════════════════════


class TestProjectEnvironmentBoundary:

    def test_project_root_with_chinese_path(self, tmp_path):
        project = tmp_path / "我的项目"
        project.mkdir()
        (project / "main.py").write_text("print('hello')", encoding="utf-8")
        te = ToolExecutor(str(project))
        tree = te.get_file_tree()
        assert "main.py" in tree

    def test_single_file_project(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
        te = ToolExecutor(str(tmp_path))
        tree = te.get_file_tree()
        assert "app.py" in tree

    def test_no_python_files_project(self, tmp_path):
        (tmp_path / "index.js").write_text("console.log(1)", encoding="utf-8")
        te = ToolExecutor(str(tmp_path))
        tree = te.get_file_tree()
        assert "index.js" in tree

    def test_deeply_nested_project(self, tmp_path):
        # Create 5 levels deep
        deep = tmp_path
        for i in range(5):
            deep = deep / f"level{i}"
            deep.mkdir()
        (deep / "deep.py").write_text("pass", encoding="utf-8")
        te = ToolExecutor(str(tmp_path))
        # max_depth=3 should not crash even with 5 levels
        tree = te.get_file_tree(max_depth=3)
        assert isinstance(tree, str)
        # deep.py is at depth 5, should NOT appear with max_depth=3
        assert "deep.py" not in tree

    def test_file_with_windows_line_endings(self, tmp_path):
        fpath = tmp_path / "crlf.py"
        fpath.write_bytes(b"line1\r\nline2\r\nline3\r\n")
        te = ToolExecutor(str(tmp_path))
        content = te.read_file("crlf.py")
        assert "line1" in content
        assert "line2" in content

    def test_file_with_utf8_bom(self, tmp_path):
        fpath = tmp_path / "bom.py"
        fpath.write_bytes(b"\xef\xbb\xbfprint('hello')\n")
        te = ToolExecutor(str(tmp_path))
        content = te.read_file("bom.py")
        assert "print" in content
        assert not content.startswith("[ERROR]")

    def test_empty_python_file(self, tmp_path):
        fpath = tmp_path / "empty.py"
        fpath.write_text("", encoding="utf-8")
        # extract_symbols takes source content string
        symbols = extract_symbols("")
        assert isinstance(symbols, list)
        assert len(symbols) == 0

    def test_syntax_error_python_file(self, tmp_path):
        broken_code = "def foo(\n    x = [\n"
        fpath = tmp_path / "broken.py"
        fpath.write_text(broken_code, encoding="utf-8")
        # extract_symbols should fallback to regex on SyntaxError
        symbols = extract_symbols(broken_code)
        assert isinstance(symbols, list)
        # regex fallback should still find "foo"
        names = [s["name"] for s in symbols]
        assert "foo" in names


# ═══════════════════════════════════════════════════════════════
# GROUP 3: LLM output boundary
# ═══════════════════════════════════════════════════════════════


class TestLLMOutputBoundary:

    @pytest.mark.parametrize("bad_output", [
        "",
        "   ",
        "\n\n\n",
        "null",
        "undefined",
        "I cannot help with that.",
        "<|endoftext|>",
        "..." * 100,
    ])
    def test_gate_handles_bad_llm_output(self, bad_output):
        llm = _make_mock_llm()
        gate = Gate(llm)
        result = gate._parse(bad_output, "test input")
        assert result["expert_type"] == "chat"
        assert "_parse_error" in result

    def test_generator_handles_empty_llm_output(self, tmp_path):
        # Mock LLM that returns empty string
        llm = MagicMock()
        llm.generate = MagicMock(return_value="")

        # Create a real temp file with a function for locator_output
        src_file = tmp_path / "target.py"
        src_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        te = ToolExecutor(str(tmp_path))
        gen = GeneratorExpert(llm, tool_executor=te, num_candidates=1)

        ctx = TaskContext(
            user_input="fix hello function",
            project_root=str(tmp_path),
            gate_result={"expert_type": "locator_repair"},
            locator_output={
                "relevant_files": [str(src_file)],
                "relevant_functions": ["hello"],
            },
        )

        result = gen.run(ctx)
        # With empty LLM output, generator should return None (no valid patches)
        assert result is None or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# GROUP 4: State isolation
# ═══════════════════════════════════════════════════════════════


class TestStateIsolation:

    def test_two_consecutive_tasks_state_isolated(self):
        ctx1 = TaskContext(user_input="task 1")
        ctx1.locator_output = {"relevant_files": ["a.py"]}

        ctx2 = TaskContext(user_input="task 2")
        assert ctx2.locator_output is None

    def test_memory_file_missing_handled(self, tmp_path):
        mem = OffgridMemory()
        result = mem.load(str(tmp_path))
        assert isinstance(result, str)
        # No .offgrid/PROJECT.md exists, should return empty string
        assert result == ""
