"""
Regression tests for Generator stability.
Covers _clean_code_output, _detect_extension, _extract_filename,
_extract_function, apply_patch, and Generator.run() with empty LLM output.
"""

import os
import pytest

from offgrid.experts.generator import GeneratorExpert, _detect_extension
from offgrid.tools.executor import ToolExecutor
from offgrid.core.context import TaskContext


# ── Mock LLM ─────────────────────────────────────────────────

class MockLLM:
    """Minimal mock matching LLMBackend.generate() signature."""

    def __init__(self, response=""):
        self.response = response

    def generate(self, prompt="", system="", max_tokens=1024,
                 temperature=0.0, stop=None, grammar_str=None):
        return self.response

    def chat(self, messages, **kwargs):
        return self.response


# ── Test 1: _clean_code_output handles all LLM output formats ─

class TestCleanCodeOutputFormats:

    @pytest.mark.parametrize("raw, must_contain, must_not_contain", [
        pytest.param(
            "```python\ndef add(a,b): return a+b\n```",
            ["def add"],
            ["```"],
            id="markdown-python-block",
        ),
        pytest.param(
            "```\ndef add(a,b): return a+b\n```",
            ["def add"],
            ["```"],
            id="markdown-no-lang-block",
        ),
        pytest.param(
            "好的，修改后的代码：\ndef add(a,b): return a+b",
            ["def add"],
            [],
            id="text-before-code",
        ),
        pytest.param(
            "修改：\ndef add(a,b): return a+b\n以上修改完成。",
            ["def add"],
            [],
            id="text-before-and-after",
        ),
        pytest.param(
            "def add(a, b):\n    return a + b\n",
            ["def add"],
            [],
            id="clean-output",
        ),
        pytest.param(
            "<think>分析中</think>\ndef add(a,b): return a+b",
            ["def add"],
            ["<think>"],
            id="thinking-tags-stripped",
        ),
        pytest.param(
            "write_file output.py\ndef add(a,b): return a+b",
            ["def add"],
            ["write_file"],
            id="tool-call-line-stripped",
        ),
    ])
    def test_clean_code_output(self, raw, must_contain, must_not_contain):
        result = GeneratorExpert._clean_code_output(raw)
        for s in must_contain:
            assert s in result, f"Expected {s!r} in result: {result!r}"
        for s in must_not_contain:
            assert s not in result, f"Did not expect {s!r} in result: {result!r}"


# ── Test 2: apply_patch handles shorter modified ─────────────

class TestApplyPatchShorterModified:

    def test_shorter_modified_is_legitimate(self, tmp_path):
        verbose_code = (
            "def compute(x):\n"
            "    result = x * 2  # multiply by two\n"
            "    result = result + 0  # add zero (no-op)\n"
            "    return result\n"
        )
        simplified = (
            "def compute(x):\n"
            "    return x * 2\n"
        )
        file_path = tmp_path / "code.py"
        file_path.write_text(verbose_code, encoding="utf-8")

        tools = ToolExecutor(project_root=str(tmp_path))
        assert tools.apply_patch("code.py", verbose_code, simplified) is True

        content = file_path.read_text(encoding="utf-8")
        assert "return x * 2" in content
        assert "add zero" not in content


# ── Test 3: _detect_extension ────────────────────────────────

class TestDetectExtension:

    @pytest.mark.parametrize("user_input, expected", [
        pytest.param("帮我写一个 utils.py 文件", ".py", id="py-keyword"),
        pytest.param("创建 index.html 页面", ".html", id="html-keyword"),
        pytest.param("写一个 TypeScript 的 service.ts", ".ts", id="ts-keyword"),
        pytest.param("生成一个 Java 的 UserService.java", ".java", id="java-keyword"),
        pytest.param("帮我写个排序函数", ".py", id="default-py"),
        pytest.param("写个shell脚本", ".sh", id="shell-keyword"),
        pytest.param("写个javascript函数", ".js", id="js-keyword"),
    ])
    def test_detect_extension(self, user_input, expected):
        assert _detect_extension(user_input) == expected

    def test_go_plain_keyword_does_not_match(self):
        """_LANG_KEYWORDS has 'golang' and 'go语言' but not plain 'go',
        so '写一个 Go 的 main.go' falls back to .py (no keyword hit)."""
        result = _detect_extension("写一个 Go 的 main.go")
        # plain "go" is not in _LANG_KEYWORDS values, so default .py
        assert result == ".py"


# ── Test 4: _extract_filename ────────────────────────────────

class TestExtractFilename:

    def test_explicit_py_filename(self):
        result = GeneratorExpert._extract_filename("帮我写一个 new_utils.py 文件")
        assert result.endswith(".py")

    def test_no_directory_separator(self):
        result = GeneratorExpert._extract_filename("帮我写一个 new_utils.py 文件")
        assert "/" not in result
        assert "\\" not in result


# ── Test 5: _extract_function ────────────────────────────────

class TestExtractFunction:

    SAMPLE_CODE = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def sub(a, b):\n"
        "    return a - b\n"
    )

    def test_extract_existing_function(self):
        result = GeneratorExpert._extract_function(self.SAMPLE_CODE, "add")
        assert result is not None
        assert "def add" in result
        assert "return a + b" in result
        # Should NOT include the sub function
        assert "def sub" not in result

    def test_extract_class_dot_method(self):
        code = (
            "class Calc:\n"
            "    def method(self, x):\n"
            "        return x * 2\n"
            "\n"
            "    def other(self):\n"
            "        pass\n"
        )
        result = GeneratorExpert._extract_function(code, "Calc.method")
        assert result is not None
        assert "def method" in result

    def test_extract_nonexistent_returns_none(self):
        result = GeneratorExpert._extract_function(self.SAMPLE_CODE, "nonexistent")
        assert result is None


# ── Test 6: Generator.run() with empty LLM output ───────────

class TestGeneratorEmptyLLMOutput:

    def test_run_returns_none_on_empty_llm(self, tmp_path):
        """Generator.run() should return None (not crash) when LLM returns ''."""
        # Create a real file for locator_output to reference
        target = tmp_path / "target.py"
        target.write_text("def foo():\n    pass\n", encoding="utf-8")

        llm = MockLLM(response="")
        tools = ToolExecutor(project_root=str(tmp_path))
        gen = GeneratorExpert(llm=llm, tool_executor=tools, num_candidates=1)

        ctx = TaskContext(
            user_input="修复 foo 函数",
            project_root=str(tmp_path),
            gate_result={"expert_type": "locator_repair"},
            locator_output={
                "relevant_files": [str(target)],
                "relevant_functions": ["foo"],
                "edit_locations": [],
            },
        )

        result = gen.run(ctx)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
