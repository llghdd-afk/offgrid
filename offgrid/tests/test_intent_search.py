"""
Tests for intent-aware search: classifier, ChatExpert search gating, query generator.
"""

import pytest


class TestIntentClassifier:

    def test_keyword_debug(self):
        from offgrid.search.intent_classifier import classify
        assert classify("这个报错怎么修") == "debug"
        assert classify("fix this traceback") == "debug"
        assert classify("IndexError异常") == "debug"

    def test_keyword_code_search(self):
        from offgrid.search.intent_classifier import classify
        assert classify("有没有开源的异步框架") == "code_search"
        assert classify("这个思路有没有最优解") == "code_search"
        assert classify("推荐一个ORM框架") == "code_search"
        assert classify("best practice for caching") == "code_search"

    def test_keyword_academic(self):
        from offgrid.search.intent_classifier import classify
        assert classify("transformer论文") == "academic"
        assert classify("这个算法的paper在哪") == "academic"
        assert classify("SOTA benchmark results") == "academic"

    def test_keyword_package(self):
        from offgrid.search.intent_classifier import classify
        assert classify("pip install requests") == "package"
        assert classify("这个库怎么安装") == "package"
        assert classify("npm依赖冲突") == "package"

    def test_general_fallback(self):
        from offgrid.search.intent_classifier import classify
        assert classify("今天天气怎么样") == "general"
        assert classify("你好") == "general"

    def test_task_summary_also_checked(self):
        from offgrid.search.intent_classifier import classify
        assert classify("帮我看看", task_summary="修复bug") == "debug"

    def test_llm_fallback_not_called_on_keyword_hit(self):
        """When keyword matches, LLM should not be called."""
        from offgrid.search.intent_classifier import classify
        call_count = [0]
        class FakeLLM:
            def generate(self, **kw):
                call_count[0] += 1
                return "general"
        result = classify("github上有没有", llm=FakeLLM())
        assert result == "code_search"
        assert call_count[0] == 0

    def test_llm_fallback_called_on_no_keyword(self):
        from offgrid.search.intent_classifier import classify
        class FakeLLM:
            def generate(self, **kw):
                return "academic"
        result = classify("attention is all you need", llm=FakeLLM())
        assert result == "academic"

    def test_llm_fallback_invalid_returns_general(self):
        from offgrid.search.intent_classifier import classify
        class FakeLLM:
            def generate(self, **kw):
                return "nonsense_category"
        result = classify("something random", llm=FakeLLM())
        assert result == "general"

    def test_llm_fallback_exception_returns_general(self):
        from offgrid.search.intent_classifier import classify
        class FakeLLM:
            def generate(self, **kw):
                raise RuntimeError("LLM down")
        result = classify("something random", llm=FakeLLM())
        assert result == "general"


class TestChatExpertSearchGating:

    def _make_expert(self):
        from offgrid.experts.chat_expert import ChatExpert
        from offgrid.core.context import TaskContext

        class FakeLLM:
            def generate(self, **kw):
                return "这是LLM直接回复"

        class FakeSearch:
            called = False
            def search_only(self, query):
                FakeSearch.called = True
                return "搜索结果"

        expert = ChatExpert(llm=FakeLLM(), search_augmentor=FakeSearch())
        return expert, FakeSearch

    def test_greeting_no_search(self):
        expert, search_cls = self._make_expert()
        from offgrid.core.context import TaskContext
        ctx = TaskContext(user_input="你好")
        expert.run(ctx)
        assert not search_cls.called

    def test_followup_no_search(self):
        """Follow-up questions should not trigger search."""
        expert, search_cls = self._make_expert()
        from offgrid.core.context import TaskContext

        for q in ["穿什么合适", "为什么", "详细说说", "举个例子"]:
            search_cls.called = False
            ctx = TaskContext(user_input=q)
            expert.run(ctx)
            assert not search_cls.called, f"'{q}' should not trigger search"

    def test_reasoning_no_search(self):
        """Pure reasoning/advice questions should not trigger search."""
        expert, search_cls = self._make_expert()
        from offgrid.core.context import TaskContext

        for q in ["哪个框架合适", "有什么建议", "两者区别是什么"]:
            search_cls.called = False
            ctx = TaskContext(user_input=q)
            expert.run(ctx)
            assert not search_cls.called, f"'{q}' should not trigger search"

    def test_realtime_still_searches(self):
        """Questions needing real-time data should still search."""
        expert, search_cls = self._make_expert()
        from offgrid.core.context import TaskContext

        search_cls.called = False
        ctx = TaskContext(user_input="今天天气怎么样建议穿什么")
        expert.run(ctx)
        assert search_cls.called

    def test_normal_question_searches(self):
        """Normal non-followup questions should trigger search."""
        expert, search_cls = self._make_expert()
        from offgrid.core.context import TaskContext

        search_cls.called = False
        ctx = TaskContext(user_input="韩国釜山近一周的天气预报")
        expert.run(ctx)
        assert search_cls.called


class TestQueryGeneratorDirections:

    def test_new_intents_have_directions(self):
        from offgrid.search.query_generator import _DIRECTION_MAP
        for intent in ["code_search", "academic", "package", "debug", "general"]:
            assert intent in _DIRECTION_MAP, f"Missing direction for {intent}"

    def test_code_search_direction_quality(self):
        from offgrid.search.query_generator import _DIRECTION_MAP
        d = _DIRECTION_MAP["code_search"]
        assert "implementation" in d.lower() or "github" in d.lower()

    def test_academic_direction_quality(self):
        from offgrid.search.query_generator import _DIRECTION_MAP
        d = _DIRECTION_MAP["academic"]
        assert "paper" in d.lower() or "arxiv" in d.lower()

    def test_legacy_compat(self):
        """Old intent names should still work."""
        from offgrid.search.query_generator import _DIRECTION_MAP
        assert "github" in _DIRECTION_MAP
        assert "arxiv" in _DIRECTION_MAP
        assert "bug" in _DIRECTION_MAP
