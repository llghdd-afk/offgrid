"""Regression tests for Chat + search pipeline."""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from offgrid.core.context import TaskContext
from offgrid.core.gate import Gate
from offgrid.core.orchestrator import PipelineOrchestrator
from offgrid.experts.chat_expert import ChatExpert
from offgrid.experts.search_augmentor import SearchAugmentorExpert


# ── Test 1: ChatExpert uses search results in LLM prompt ────────────────

def test_chat_expert_uses_search_results():
    mock_llm = MagicMock()
    mock_search = MagicMock()
    mock_search.search_only.return_value = "首尔本周天气：周一15度晴，周二16度多云"

    captured_prompts = []

    def fake_generate(prompt, **kwargs):
        captured_prompts.append(prompt)
        return "首尔本周天气晴朗"

    mock_llm.generate.side_effect = fake_generate

    expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
    ctx = TaskContext(user_input="帮我查一下韩国最近一周的天气")
    result = expert.run(ctx)

    assert result["passed"] is True
    mock_search.search_only.assert_called_once()
    assert len(captured_prompts) == 1
    assert "天气" in captured_prompts[0] or "首尔" in captured_prompts[0]


# ── Test 2: search exception doesn't crash ChatExpert ───────────────────

def test_chat_expert_search_fail_graceful():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "搜索暂时不可用"
    mock_search = MagicMock()
    mock_search.search_only.side_effect = Exception("SearXNG down")

    expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
    ctx = TaskContext(user_input="今天上海天气怎么样")
    result = expert.run(ctx)

    assert result["passed"] is True
    assert ctx.generator_output is not None


# ── Test 3: greeting bypasses search entirely ───────────────────────────

def test_chat_expert_greeting_no_search():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "你好！有什么代码问题吗？"
    mock_search = MagicMock()

    expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
    ctx = TaskContext(user_input="你好")
    result = expert.run(ctx)

    assert result["passed"] is True
    mock_search.search_only.assert_not_called()


# ── Test 4: _needs_realtime_data keyword detection ──────────────────────

@pytest.mark.parametrize("task, expected", [
    ("韩国最近一周的天气怎么样", True),
    ("今天上海天气如何", True),
    ("最近有什么新闻", True),
    ("比特币今天多少钱", True),
    ("帮我修复登录bug", False),
    ("写个排序函数", False),
])
def test_needs_realtime_data(task: str, expected: bool):
    assert PipelineOrchestrator._needs_realtime_data(task) is expected


# ── Test 5: Gate prompt contains "chat" type description ────────────────

def test_gate_routes_realtime_to_chat():
    from offgrid.core.gate import GATE_PROMPT
    assert "chat" in GATE_PROMPT


# ── Test 6: short search result triggers fallback ───────────────────────

def test_chat_expert_short_search_result_triggers_fallback():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "搜索服务暂时不可用"
    mock_search = MagicMock()
    mock_search.search_only.return_value = "短"  # < 30 chars

    expert = ChatExpert(llm=mock_llm, search_augmentor=mock_search)
    ctx = TaskContext(user_input="韩国天气怎么样")
    result = expert.run(ctx)

    assert result["passed"] is True
    assert ctx.generator_output is not None
    # LLM should have been called with the search_fail system prompt, not search prompt
    call_kwargs = mock_llm.generate.call_args
    system_used = call_kwargs.kwargs.get("system", "")
    # The fallback prompt should mention inability to get data (not the search-success prompt)
    assert "实时" in system_used or "无法获取" in system_used or "不可用" in system_used


# ── Test 7: SearchAugmentorExpert._clean_query ──────────────────────────

@pytest.mark.parametrize("raw, should_strip", [
    ("你好帮我查一下韩国天气", "你好"),
    ("帮我搜索最新新闻", "帮我搜索"),
])
def test_search_augmentor_clean_query_strips_prefix(raw: str, should_strip: str):
    result = SearchAugmentorExpert._clean_query(raw)
    assert not result.startswith(should_strip)
    assert len(result) < len(raw)


def test_search_augmentor_clean_query_short_returns_original():
    # "天气" is 2 chars (< 4), so _clean_query returns original
    result = SearchAugmentorExpert._clean_query("天气")
    assert result == "天气"
