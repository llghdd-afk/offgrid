"""
Tests for DebugSubagent: runtime debugging info capture.
Uses mock LLM and mock tool_executor since Ollama may not be running.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from offgrid.core.context import TaskContext
from offgrid.experts.debug_subagent import DebugSubagent, TRACE_SCRIPT_TEMPLATE


# ── Fixtures ──

def _make_mock_llm(response: str = '{"file": "src/calc.py", "line": 10, "variables": ["x", "y"], "error_type": "exception"}'):
    llm = MagicMock()
    llm.generate = MagicMock(return_value=response)
    return llm


def _make_mock_tools(bash_stdout: str = ""):
    tools = MagicMock()
    tools.run_bash = MagicMock(return_value={"stdout": bash_stdout, "stderr": "", "returncode": 0})
    return tools


def _make_ctx_with_failure(project_root: str = "/tmp/test") -> TaskContext:
    ctx = TaskContext(
        user_input="fix the calculator bug",
        project_root=project_root,
        gate_result={"expert_type": "locator_repair"},
        verifier_output={
            "passed": False,
            "syntax_ok": True,
            "tests_passed": 0,
            "tests_total": 3,
            "error_detail": "FAILED tests/test_calc.py::test_add - AssertionError: assert 5 == 3",
        },
        generator_output={
            "patches": [{"file": "src/calc.py", "original": "return x - y", "modified": "return x + y"}],
            "explanation": "Fixed addition",
        },
    )
    return ctx


# ── Unit Tests ──

class TestDebugSubagentInvestigate:
    """Test the main investigate() method."""

    def test_returns_string_on_success(self):
        """investigate() should return a non-empty string with debug info."""
        llm = _make_mock_llm()
        debug_json = json.dumps({
            "variables": {"x": "3", "y": "2"},
            "exception": None,
            "reached": True,
        })
        tools = _make_mock_tools(bash_stdout=f"__DEBUG_JSON__{debug_json}")
        subagent = DebugSubagent(llm, tools)

        # Create a temp dir with a test file
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            with open(os.path.join(tmpdir, "tests", "test_calc.py"), "w") as f:
                f.write("def test_add(): pass\n")

            ctx = _make_ctx_with_failure(project_root=tmpdir)
            result = subagent.investigate(ctx)

        assert isinstance(result, str)
        assert len(result) > 0
        assert "x = 3" in result or "y = 2" in result

    def test_returns_empty_on_no_verifier_output(self):
        """investigate() should return '' when verifier_output is None."""
        llm = _make_mock_llm()
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        ctx = TaskContext(user_input="test", project_root="/tmp")
        ctx.verifier_output = None

        result = subagent.investigate(ctx)
        assert result == ""

    def test_returns_empty_on_syntax_error(self):
        """investigate() should skip syntax errors (not runtime issues)."""
        llm = _make_mock_llm()
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        ctx = TaskContext(user_input="test", project_root="/tmp")
        ctx.verifier_output = {
            "passed": False,
            "error_detail": "Syntax error in src/main.py: invalid syntax (line 5)",
        }

        result = subagent.investigate(ctx)
        assert result == ""

    def test_fallback_on_trace_failure(self):
        """When trace script fails, should fallback to pytest --tb=long."""
        llm = _make_mock_llm()
        # First call (trace) returns empty, second call (fallback) returns traceback
        tools = MagicMock()
        tools.run_bash = MagicMock(side_effect=[
            {"stdout": "", "stderr": "", "returncode": 1},  # trace fails
            {"stdout": "FAILED test_calc.py\nAssertionError: 5 != 3\n  File calc.py line 10", "stderr": "", "returncode": 1},  # fallback
        ])
        subagent = DebugSubagent(llm, tools)

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            with open(os.path.join(tmpdir, "tests", "test_calc.py"), "w") as f:
                f.write("def test_add(): pass\n")

            ctx = _make_ctx_with_failure(project_root=tmpdir)
            result = subagent.investigate(ctx)

        assert "详细堆栈" in result or "AssertionError" in result

    def test_no_crash_on_llm_failure(self):
        """investigate() should not crash if LLM returns garbage."""
        llm = MagicMock()
        llm.generate = MagicMock(return_value="I don't understand the question")
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            with open(os.path.join(tmpdir, "tests", "test_x.py"), "w") as f:
                f.write("def test_x(): pass\n")

            ctx = _make_ctx_with_failure(project_root=tmpdir)
            result = subagent.investigate(ctx)

        # Should not crash, returns empty or fallback
        assert isinstance(result, str)


class TestDebugSubagentStrategy:
    """Test the _plan_debug_strategy method."""

    def test_parses_valid_json(self):
        """Should extract strategy from LLM JSON response."""
        llm = _make_mock_llm('Here is the analysis: {"file": "app.py", "line": 25, "variables": ["data", "result"], "error_type": "assertion"}')
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        ctx = _make_ctx_with_failure()
        strategy = subagent._plan_debug_strategy(ctx, "AssertionError: 5 != 3")

        assert strategy is not None
        assert strategy["file"] == "app.py"
        assert strategy["line"] == 25
        assert "data" in strategy["variables"]

    def test_returns_none_on_invalid_json(self):
        """Should return None if LLM doesn't produce valid JSON."""
        llm = _make_mock_llm("I think the bug is in the add function")
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        ctx = _make_ctx_with_failure()
        strategy = subagent._plan_debug_strategy(ctx, "some error")

        assert strategy is None

    def test_limits_variables_to_5(self):
        """Should cap variables at 5 even if LLM suggests more."""
        many_vars = '{"file": "x.py", "line": 1, "variables": ["a","b","c","d","e","f","g"], "error_type": "logic"}'
        llm = _make_mock_llm(many_vars)
        tools = _make_mock_tools()
        subagent = DebugSubagent(llm, tools)

        ctx = _make_ctx_with_failure()
        strategy = subagent._plan_debug_strategy(ctx, "error")

        assert len(strategy["variables"]) == 5


class TestTraceScriptGeneration:
    """Test that generated trace scripts are valid Python."""

    def test_script_is_valid_python(self):
        """Generated trace script should compile without syntax errors."""
        script = TRACE_SCRIPT_TEMPLATE.format(
            target_file="src/calc.py",
            target_line=10,
            variables=["x", "y", "result"],
            project_root="/tmp/myproject",
            test_path="tests/test_calc.py",
        )
        # Should not raise SyntaxError
        compile(script, "<trace_script>", "exec")

    def test_script_contains_marker(self):
        """Script output should contain __DEBUG_JSON__ marker."""
        script = TRACE_SCRIPT_TEMPLATE.format(
            target_file="app.py",
            target_line=5,
            variables=["data"],
            project_root="/tmp/proj",
            test_path="tests/test_app.py",
        )
        assert "__DEBUG_JSON__" in script


class TestFormatResults:
    """Test _format_results static method."""

    def test_formats_exception(self):
        strategy = {"file": "x.py", "line": 10, "variables": []}
        data = {"exception": "TypeError: unsupported operand", "reached": False, "variables": {}}
        result = DebugSubagent._format_results(strategy, data)
        assert "TypeError" in result
        assert "未到达" in result

    def test_formats_variables(self):
        strategy = {"file": "x.py", "line": 10, "variables": ["a", "b"]}
        data = {"exception": None, "reached": True, "variables": {"a": "None", "b": "42"}}
        result = DebugSubagent._format_results(strategy, data)
        assert "a = None" in result
        assert "b = 42" in result
        assert "断点命中" in result


class TestOrchestratorIntegration:
    """Test that orchestrator correctly calls debug subagent."""

    def test_do_debug_injects_info(self):
        """_do_debug should write to ctx.debug_info."""
        from offgrid.core.orchestrator import PipelineOrchestrator

        # Create minimal orchestrator with mock debug subagent
        mock_debug = MagicMock()
        mock_debug.investigate = MagicMock(return_value="异常: TypeError at line 10\n变量值:\n  x = None")

        orch = MagicMock(spec=PipelineOrchestrator)
        orch.debug_subagent = mock_debug
        orch._emit = MagicMock()

        # Call _do_debug directly
        ctx = _make_ctx_with_failure()
        PipelineOrchestrator._do_debug(orch, ctx, None)

        assert ctx.debug_info == "异常: TypeError at line 10\n变量值:\n  x = None"
        mock_debug.investigate.assert_called_once_with(ctx)

    def test_do_debug_no_crash_without_subagent(self):
        """_do_debug should be a no-op when debug_subagent is None."""
        from offgrid.core.orchestrator import PipelineOrchestrator

        orch = MagicMock(spec=PipelineOrchestrator)
        orch.debug_subagent = None

        ctx = _make_ctx_with_failure()
        PipelineOrchestrator._do_debug(orch, ctx, None)

        assert ctx.debug_info == ""

    def test_context_has_debug_info_field(self):
        """TaskContext should have debug_info field."""
        ctx = TaskContext()
        assert hasattr(ctx, "debug_info")
        assert ctx.debug_info == ""
