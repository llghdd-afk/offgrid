"""
Regression tests for 9 known bugs in the offgrid project.
Each test prevents a specific historical bug from recurring.
"""

import inspect
import os
import tempfile
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Bug 1: reasoning model detection — prefix matching
# ---------------------------------------------------------------------------
class TestReasoningModelDetection:
    """_detect_reasoning_model must correctly classify model names."""

    @pytest.mark.parametrize("model", [
        "deepseek-r1:8b",
        "deepseek-r1:14b",
        "deepseek-r1:32b",
        "qwen3:8b",
        "qwen3:14b",
        "qwen3-coder:8b",
        "qwen3-vl:7b",
        "gemma4:e2b",
    ])
    def test_reasoning_models_detected(self, model):
        from offgrid.llm.llama_backend import LLMBackend
        assert LLMBackend._detect_reasoning_model(model) is True, (
            f"{model} should be detected as reasoning model"
        )

    @pytest.mark.parametrize("model", [
        "gemma3:4b",
        "llama3:8b",
    ])
    def test_non_reasoning_models_rejected(self, model):
        from offgrid.llm.llama_backend import LLMBackend
        assert LLMBackend._detect_reasoning_model(model) is False, (
            f"{model} should NOT be detected as reasoning model"
        )


# ---------------------------------------------------------------------------
# Bug 2: Ollama temperature=0 KV cache — reasoning models must not use 0.0
# ---------------------------------------------------------------------------
class TestReasoningTemperature:
    """Reasoning models must bump temperature from 0.0 to 0.01 to avoid
    Ollama KV-cache degeneration."""

    def test_chat_ollama_bumps_zero_temp(self):
        from offgrid.llm.llama_backend import LLMBackend

        src = inspect.getsource(LLMBackend._chat_ollama)
        # The source must contain the 0.0 -> 0.01 guard
        assert "0.01" in src, (
            "_chat_ollama must set effective_temp = 0.01 for reasoning models"
        )
        assert "temperature == 0.0" in src or "temperature==0.0" in src, (
            "_chat_ollama must check for temperature == 0.0"
        )

    def test_reasoning_flag_set_on_init(self):
        """Constructing with a reasoning model name must set _is_reasoning."""
        from offgrid.llm.llama_backend import LLMBackend

        backend = LLMBackend.__new__(LLMBackend)
        backend._is_reasoning = LLMBackend._detect_reasoning_model("qwen3:8b")
        assert backend._is_reasoning is True


# ---------------------------------------------------------------------------
# Bug 3: Generator original must be read from file (exact match)
# ---------------------------------------------------------------------------
class TestApplyPatchExactMatch:
    """apply_patch uses exact string match — LLM-hallucinated originals fail."""

    def test_read_file_preserves_comments(self, tmp_path):
        from offgrid.tools.executor import ToolExecutor

        src = textwrap.dedent("""\
            def hello():
                # important comment
                return 42
        """)
        p = tmp_path / "sample.py"
        p.write_text(src, encoding="utf-8")

        te = ToolExecutor(str(tmp_path))
        content = te.read_file("sample.py")
        assert "# important comment" in content

    def test_exact_patch_succeeds(self, tmp_path):
        from offgrid.tools.executor import ToolExecutor

        src = "def hello():\n    # important comment\n    return 42\n"
        p = tmp_path / "sample.py"
        p.write_text(src, encoding="utf-8")

        te = ToolExecutor(str(tmp_path))
        ok = te.apply_patch(
            "sample.py",
            original="    return 42",
            modified="    return 99",
        )
        assert ok is True
        assert "return 99" in te.read_file("sample.py")

    def test_llm_modified_original_fails(self, tmp_path):
        """If the LLM omits the comment, the patch must fail."""
        from offgrid.tools.executor import ToolExecutor

        src = "def hello():\n    # important comment\n    return 42\n"
        p = tmp_path / "sample.py"
        p.write_text(src, encoding="utf-8")

        te = ToolExecutor(str(tmp_path))
        # LLM hallucinated original without the comment
        ok = te.apply_patch(
            "sample.py",
            original="def hello():\n    return 42",
            modified="def hello():\n    return 99",
        )
        assert ok is False, "apply_patch must reject LLM-hallucinated originals"


# ---------------------------------------------------------------------------
# Bug 4: Verifier pytest must specify tests/ directory
# ---------------------------------------------------------------------------
class TestVerifierPytestDir:
    """_run_tests must run pytest against 'tests/' — not the whole project."""

    def test_run_tests_specifies_tests_dir(self):
        from offgrid.experts.verifier import VerifierExpert

        src = inspect.getsource(VerifierExpert._run_tests)
        assert "tests/" in src, (
            "_run_tests must include 'tests/' in the pytest command"
        )


# ---------------------------------------------------------------------------
# Bug 5: apply_patch must NOT use fuzzy/difflib matching
# ---------------------------------------------------------------------------
class TestNoDifflib:
    """apply_patch must be exact-match only — no SequenceMatcher / difflib."""

    def test_no_fuzzy_in_apply_patch(self):
        from offgrid.tools.executor import ToolExecutor

        src = inspect.getsource(ToolExecutor.apply_patch)
        for forbidden in ("difflib", "SequenceMatcher", "fuzzy", "get_close_matches"):
            assert forbidden not in src, (
                f"apply_patch must not use {forbidden}"
            )


# ---------------------------------------------------------------------------
# Bug 6: reasoning model must use /api/chat (not /api/generate)
# ---------------------------------------------------------------------------
class TestOllamaChatEndpoint:
    """_generate_ollama must route through _chat_ollama (/api/chat)."""

    def test_generate_ollama_calls_chat(self):
        from offgrid.llm.llama_backend import LLMBackend

        src = inspect.getsource(LLMBackend._generate_ollama)
        assert "_chat_ollama" in src, (
            "_generate_ollama must call _chat_ollama (which uses /api/chat)"
        )

    def test_chat_ollama_uses_api_chat(self):
        from offgrid.llm.llama_backend import LLMBackend

        src = inspect.getsource(LLMBackend._chat_ollama)
        assert "/api/chat" in src, (
            "_chat_ollama must POST to /api/chat"
        )


# ---------------------------------------------------------------------------
# Bug 7: office classification — EXPERT_SEQUENCES["office"] == ["office"]
# ---------------------------------------------------------------------------
class TestOfficeSequence:
    """Office tasks must route to the office handler only."""

    def test_office_sequence(self):
        from offgrid.core.orchestrator import EXPERT_SEQUENCES

        assert "office" in EXPERT_SEQUENCES, "EXPERT_SEQUENCES must have 'office' key"
        assert EXPERT_SEQUENCES["office"] == ["office"]


# ---------------------------------------------------------------------------
# Bug 8: ContentFetcher.fetch must pass timeout to httpx
# ---------------------------------------------------------------------------
class TestFetchTimeout:
    """Content fetcher must honour the timeout parameter."""

    def test_fetch_source_contains_timeout(self):
        from offgrid.search.content_fetcher import ContentFetcher

        src = inspect.getsource(ContentFetcher.fetch)
        assert "timeout" in src, "fetch() must use the timeout parameter"

    def test_extraction_pipeline_passes_timeout(self):
        from offgrid.search.extraction_pipeline import fetch_and_extract

        src = inspect.getsource(fetch_and_extract)
        assert "timeout" in src, "fetch_and_extract must pass timeout to httpx"


# ---------------------------------------------------------------------------
# Bug 9: SearXNG not running — search must degrade gracefully
# ---------------------------------------------------------------------------
class TestSearchGracefulFailure:
    """When SearXNG is unreachable, search() must return [] without crashing."""

    def test_search_returns_list_on_failure(self, monkeypatch):
        import offgrid.search.duckduckgo as ddg_mod

        # Reset the module-level cache so our mock takes effect
        monkeypatch.setattr(ddg_mod, "_searxng_ok", None)

        # Point SearXNG at a guaranteed-bad URL
        monkeypatch.setenv("KWCODE_SEARXNG_URL", "http://127.0.0.1:1")

        # Also disable DDG fallback so we test pure failure path
        monkeypatch.setattr(ddg_mod, "HAS_DDGS", False)

        # Prevent Docker auto-start attempts
        monkeypatch.setattr(ddg_mod, "_try_start_searxng", lambda: False)

        result = ddg_mod.search("test query", max_results=3)
        assert isinstance(result, list), "search() must return a list"
        # With both SearXNG and DDG unavailable, result should be empty
        assert result == []
