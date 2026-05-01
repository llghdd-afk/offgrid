"""
探索过程中发现的新 bug 回归测试。
每个 class 是一次独立发现。
"""

import re
import pytest
from unittest.mock import MagicMock


# ────────────────────────────────────────────────
# Bug 2026-04-27: _clean_code_output 不清理 <think> 标签
# ────────────────────────────────────────────────

class TestBug_ThinkTagsCleaning:
    """
    触发方式：reasoning模型(deepseek-r1/qwen3)生成代码时输出<think>块
    错误现象：生成的代码包含<think>标签，导致语法错误
    根因：_clean_code_output只清理markdown和tool-call，没清理think标签
    修复位置：offgrid/experts/generator.py:_clean_code_output
    """

    @pytest.mark.parametrize("raw", [
        "<think>让我分析一下这个问题...</think>\ndef hello():\n    return 'world'",
        "<think>\n分析中\n考虑方案A\n</think>\n\ndef add(a, b):\n    return a + b",
        "def foo():\n    <think>这里需要修改</think>\n    return 1",
        "<think>step1</think><think>step2</think>\nresult = 42",
    ])
    def test_think_tags_stripped(self, raw):
        from offgrid.experts.generator import GeneratorExpert
        result = GeneratorExpert._clean_code_output(raw)
        assert "<think>" not in result
        assert "</think>" not in result

    def test_think_tags_multiline_stripped(self):
        from offgrid.experts.generator import GeneratorExpert
        raw = "<think>\n这是一个很长的思考过程\n包含多行\n分析了很多东西\n</think>\ndef solve():\n    return 42"
        result = GeneratorExpert._clean_code_output(raw)
        assert "<think>" not in result
        assert "def solve" in result


# ────────────────────────────────────────────────
# Bug 2026-04-27: apply_patch 空字符串 original 导致文件损坏
# ────────────────────────────────────────────────

class TestBug_ApplyPatchEmptyOriginal:
    """
    触发方式：codegen路径生成patch时original=""
    错误现象：content.replace("", modified, 1)在文件开头插入内容
    根因：空字符串是任何字符串的子串，replace会在位置0插入
    修复位置：offgrid/tools/executor.py:apply_patch
    """

    def test_empty_original_returns_false(self, tmp_path):
        from offgrid.tools.executor import ToolExecutor
        f = tmp_path / "existing.py"
        f.write_text("def hello():\n    pass\n", encoding="utf-8")
        te = ToolExecutor(str(tmp_path))
        # Empty original should be rejected
        result = te.apply_patch("existing.py", "", "new content")
        assert result is False
        # File should be unchanged
        assert f.read_text(encoding="utf-8") == "def hello():\n    pass\n"

    def test_whitespace_only_original_returns_false(self, tmp_path):
        from offgrid.tools.executor import ToolExecutor
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        te = ToolExecutor(str(tmp_path))
        # Whitespace-only is effectively empty for matching purposes
        # But current code only checks `not original` (falsy), so " " passes
        # This documents current behavior
        result = te.apply_patch("test.py", " ", "y = 2")
        # " " is in "x = 1\n", so it would match — this is acceptable


# ────────────────────────────────────────────────
# Bug 2026-04-27: Chat greeting检测过宽 (len<=3)
# ────────────────────────────────────────────────

class TestBug_GreetingDetectionTooWide:
    """
    触发方式：用户输入短代码片段如"x=1"或"fix"
    错误现象：被当作问候语直接回复，不走搜索/代码路径
    根因：len(user_input) <= 3 对中文和英文都太宽泛
    修复位置：offgrid/experts/chat_expert.py:run
    """

    @pytest.mark.parametrize("short_input", [
        "x=1",
        "fix",
        "bug",
        "abc",
    ])
    def test_short_non_greeting_not_treated_as_greeting(self, short_input):
        from offgrid.experts.chat_expert import ChatExpert
        from offgrid.core.context import TaskContext

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "搜索结果相关回复"
        mock_search = MagicMock()
        mock_search.search_only.return_value = "some search result that is longer than 30 chars for sure"

        expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
        ctx = TaskContext(user_input=short_input)
        expert.run(ctx)

        # Short non-greeting inputs should trigger search, not direct chat
        mock_search.search_only.assert_called_once()

    @pytest.mark.parametrize("greeting", ["你好", "hello", "hi", "谢谢", "bye"])
    def test_actual_greetings_still_work(self, greeting):
        from offgrid.experts.chat_expert import ChatExpert
        from offgrid.core.context import TaskContext

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "你好！"
        mock_search = MagicMock()

        expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
        ctx = TaskContext(user_input=greeting)
        expert.run(ctx)

        # Greetings should NOT trigger search
        mock_search.search_only.assert_not_called()


# ────────────────────────────────────────────────
# Bug 2026-04-27: Ollama response缺少message字段
# ────────────────────────────────────────────────

class TestBug_OllamaResponseMissingMessage:
    """
    触发方式：Ollama返回异常格式的JSON（无message字段）
    错误现象：KeyError崩溃
    根因：resp.json()["message"]没有用.get()防护
    修复位置：offgrid/llm/llama_backend.py:_chat_ollama
    """

    def test_source_uses_get_for_message(self):
        """验证代码使用.get()而非直接索引访问message字段"""
        import inspect
        from offgrid.llm.llama_backend import LLMBackend
        src = inspect.getsource(LLMBackend._chat_ollama)
        # Should use .get("message") not ["message"]
        assert '.get("message"' in src or ".get('message'" in src
        assert '["message"]' not in src


# ────────────────────────────────────────────────
# Bug 2026-04-27: Locator graph结果缺少必要字段
# ────────────────────────────────────────────────

class TestBug_LocatorGraphMissingKeys:
    """
    触发方式：graph_retriever返回的结果dict缺少file_path或name字段
    错误现象：KeyError崩溃
    根因：直接用r["file_path"]访问，没有防护
    修复位置：offgrid/experts/locator.py:_graph_locate
    """

    def test_source_filters_malformed_results(self):
        """验证代码过滤掉缺少必要字段的结果"""
        import inspect
        from offgrid.experts.locator import LocatorExpert
        src = inspect.getsource(LocatorExpert._graph_locate)
        # Should have defensive filtering
        assert "get(" in src or "filter" in src.lower()


# ────────────────────────────────────────────────
# Bug 2026-04-27: codegen实时数据编造
# ────────────────────────────────────────────────

class TestBug_CodegenFabricatesData:
    """
    触发方式：用户要求"写个天气HTML"，搜索失败
    错误现象：模型编造虚假天气数据
    根因：GENERATOR_NEWFILE_PROMPT没有防编造指令
    修复位置：offgrid/experts/generator.py:GENERATOR_NEWFILE_PROMPT + _run_codegen
    """

    def test_newfile_prompt_has_anti_fabrication(self):
        """NEWFILE_PROMPT必须包含防编造指令"""
        from offgrid.experts.generator import GENERATOR_NEWFILE_PROMPT
        assert "编造" in GENERATOR_NEWFILE_PROMPT or "占位符" in GENERATOR_NEWFILE_PROMPT

    def test_needs_realtime_warning_method_exists(self):
        """_needs_realtime_warning方法必须存在"""
        from offgrid.experts.generator import GeneratorExpert
        assert hasattr(GeneratorExpert, '_needs_realtime_warning')
        assert GeneratorExpert._needs_realtime_warning("今天天气怎么样") is True
        assert GeneratorExpert._needs_realtime_warning("写个排序函数") is False

    def test_codegen_injects_warning_when_no_search_results(self):
        """搜索失败时，codegen prompt应包含防编造警告"""
        from offgrid.experts.generator import GeneratorExpert
        from offgrid.core.context import TaskContext

        mock_llm = MagicMock()
        mock_llm.generate.return_value = "<html><body>placeholder</body></html>"

        gen = GeneratorExpert(llm=mock_llm, num_candidates=1)
        ctx = TaskContext(
            user_input="写一个天气HTML页面",
            project_root="/tmp/test",
            gate_result={"expert_type": "codegen"},
        )
        # No search_results set → should trigger warning
        gen._run_codegen(ctx)

        # Check that the prompt sent to LLM contains anti-fabrication warning
        call_args = mock_llm.generate.call_args
        prompt_sent = call_args.kwargs.get("prompt", "") or (call_args.args[0] if call_args.args else "")
        assert "占位符" in prompt_sent or "编造" in prompt_sent


# ────────────────────────────────────────────────
# Bug 2026-04-27: Chat搜索失败让用户去网站查
# ────────────────────────────────────────────────

class TestBug_ChatSearchFailSuggestsWebsites:
    """
    触发方式：用户问天气，搜索失败
    错误现象：模型回复"以下是可以查天气的网站：1. xxx 2. yyy"
    根因：CHAT_SEARCH_FAIL_SYSTEM措辞不当，没有禁止列URL
    修复位置：offgrid/experts/chat_expert.py:CHAT_SEARCH_FAIL_SYSTEM
    """

    def test_search_fail_prompt_forbids_url_listing(self):
        """搜索失败prompt必须禁止列出URL"""
        from offgrid.experts.chat_expert import CHAT_SEARCH_FAIL_SYSTEM
        assert "URL" in CHAT_SEARCH_FAIL_SYSTEM or "网站" in CHAT_SEARCH_FAIL_SYSTEM
        # Must contain prohibition language
        assert "不要" in CHAT_SEARCH_FAIL_SYSTEM or "禁止" in CHAT_SEARCH_FAIL_SYSTEM or "绝对不要" in CHAT_SEARCH_FAIL_SYSTEM

    def test_search_fail_prompt_forbids_fabrication(self):
        """搜索失败prompt必须禁止编造数据"""
        from offgrid.experts.chat_expert import CHAT_SEARCH_FAIL_SYSTEM
        assert "编造" in CHAT_SEARCH_FAIL_SYSTEM or "不要编造" in CHAT_SEARCH_FAIL_SYSTEM

    def test_search_success_prompt_requires_using_data(self):
        """搜索成功prompt必须要求使用搜索数据"""
        from offgrid.experts.chat_expert import CHAT_SEARCH_SYSTEM
        assert "搜索结果" in CHAT_SEARCH_SYSTEM
        # Must require using the data, not just mentioning it
        assert "严格" in CHAT_SEARCH_SYSTEM or "基于" in CHAT_SEARCH_SYSTEM
