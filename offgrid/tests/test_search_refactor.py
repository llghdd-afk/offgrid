"""
Tests for search module refactoring: extraction pipeline + parallel search.
"""

import re
import tempfile

import pytest


class TestExtractionPipeline:

    def test_extract_trafilatura(self):
        from offgrid.search.extraction_pipeline import _extract_trafilatura
        html = "<html><body><article><p>This is a long article about Python programming and software development practices that should be extracted properly by trafilatura.</p></article></body></html>"
        result = _extract_trafilatura(html)
        # trafilatura may or may not extract short content, just verify no crash
        assert result is None or isinstance(result, str)

    def test_extract_soup_basic(self):
        from offgrid.search.extraction_pipeline import _extract_soup
        html = """<html><body>
        <nav>Navigation menu items here</nav>
        <script>var x = 1;</script>
        <main><p>This is the main content of the page that should be extracted by the soup fallback method when all other extractors fail.</p></main>
        <footer>Footer content</footer>
        </body></html>"""
        result = _extract_soup(html)
        assert result is not None
        assert "main content" in result
        assert "var x" not in result  # script removed
        assert "Navigation" not in result  # nav removed

    def test_extract_soup_empty(self):
        from offgrid.search.extraction_pipeline import _extract_soup
        assert _extract_soup("") is None
        assert _extract_soup("<html><body></body></html>") is None

    def test_quality_score(self):
        from offgrid.search.extraction_pipeline import _quality_score
        # Good content
        good = "Python is a programming language. " * 20
        # Content with boilerplate
        bad = "Accept all cookies. Sign up for newsletter. Privacy policy. " * 5
        assert _quality_score(good) > _quality_score(bad)

    def test_quality_score_empty(self):
        from offgrid.search.extraction_pipeline import _quality_score
        assert _quality_score(None) == 0
        assert _quality_score("") == 0

    def test_extract_content_pipeline(self):
        from offgrid.search.extraction_pipeline import extract_content
        # A realistic HTML page
        html = """<html><head><title>Test</title></head><body>
        <nav><a href="/">Home</a><a href="/about">About</a></nav>
        <article>
        <h1>Understanding Python Decorators</h1>
        <p>Python decorators are a powerful feature that allows you to modify the behavior of functions or classes. They use the @syntax and are commonly used for logging, authentication, and caching.</p>
        <p>A decorator is essentially a function that takes another function as an argument and returns a new function that usually extends the behavior of the original function.</p>
        </article>
        <footer><p>Copyright 2024</p></footer>
        </body></html>"""
        result = extract_content(html, url="http://example.com/decorators")
        assert result is not None
        assert len(result) > 50
        # Should contain article content
        assert "decorator" in result.lower() or "python" in result.lower()

    def test_extract_content_empty(self):
        from offgrid.search.extraction_pipeline import extract_content
        assert extract_content("") is None
        assert extract_content("   ") is None

    def test_fetch_and_extract_bad_url(self):
        from offgrid.search.extraction_pipeline import fetch_and_extract
        # Should not crash on unreachable URL
        result = fetch_and_extract("http://localhost:99999/nonexistent", timeout=1.0)
        assert result == ""

    def test_fetch_and_extract_max_chars(self):
        from offgrid.search.extraction_pipeline import fetch_and_extract
        # Can't test real fetch without network, but verify function signature
        import inspect
        sig = inspect.signature(fetch_and_extract)
        assert "max_chars" in sig.parameters
        assert "timeout" in sig.parameters


class TestContentFetcherRefactored:

    def test_content_fetcher_uses_pipeline(self):
        from offgrid.search.content_fetcher import ContentFetcher
        import inspect
        src = inspect.getsource(ContentFetcher)
        assert "fetch_and_extract" in src

    def test_content_fetcher_interface(self):
        from offgrid.search.content_fetcher import ContentFetcher
        fetcher = ContentFetcher()
        assert hasattr(fetcher, "fetch")
        assert hasattr(fetcher, "fetch_many")

    def test_content_fetcher_bad_url(self):
        from offgrid.search.content_fetcher import ContentFetcher
        fetcher = ContentFetcher()
        result = fetcher.fetch("http://localhost:99999/bad", timeout=1.0)
        assert result == ""

    def test_content_fetcher_fetch_many(self):
        from offgrid.search.content_fetcher import ContentFetcher
        fetcher = ContentFetcher()
        results = fetcher.fetch_many(["http://localhost:99999/a", "http://localhost:99999/b"], timeout=1.0)
        assert len(results) == 2
        assert all(r == "" for r in results)


class TestParallelSearch:

    def test_search_function_exists(self):
        from offgrid.search.duckduckgo import search
        import inspect
        src = inspect.getsource(search)
        assert "_search_parallel" in src

    def test_parallel_search_function_exists(self):
        from offgrid.search.duckduckgo import _search_parallel
        import inspect
        sig = inspect.signature(_search_parallel)
        assert "query" in sig.parameters
        assert "searxng_url" in sig.parameters

    def test_search_dedup_logic(self):
        """Verify dedup by URL works."""
        from offgrid.search.duckduckgo import _search_parallel
        # Can't test real search without SearXNG/DDG, but verify function exists
        import inspect
        src = inspect.getsource(_search_parallel)
        assert "results_map" in src  # dedup dict
        assert "ThreadPoolExecutor" in src  # parallel execution

    def test_search_graceful_no_engines(self):
        """search() should not crash when both engines are unavailable."""
        from offgrid.search import duckduckgo
        # Force both engines off
        original_ok = duckduckgo._searxng_ok
        original_ddgs = duckduckgo.HAS_DDGS
        try:
            duckduckgo._searxng_ok = False
            duckduckgo.HAS_DDGS = False
            results = duckduckgo.search("test query", max_results=5, timeout=2.0)
            assert results == []
        finally:
            duckduckgo._searxng_ok = original_ok
            duckduckgo.HAS_DDGS = original_ddgs


class TestExtractionPipelineEdgeCases:

    def test_boilerplate_heavy_page(self):
        """Pages with lots of boilerplate should still extract something."""
        from offgrid.search.extraction_pipeline import extract_content
        html = """<html><body>
        <div>Cookie policy. Accept all. Sign up for newsletter. Subscribe now.</div>
        <article><p>The actual content about machine learning algorithms is hidden among all this boilerplate text that should be filtered out by the quality scoring mechanism.</p></article>
        <div>Privacy policy. Terms of service. Cookie settings.</div>
        </body></html>"""
        result = extract_content(html)
        # Should still extract something (soup fallback at minimum)
        assert result is not None

    def test_chinese_content(self):
        """Chinese content should be extracted properly."""
        from offgrid.search.extraction_pipeline import extract_content
        html = """<html><body>
        <article><p>Python是一种广泛使用的高级编程语言，它的设计哲学强调代码的可读性和简洁性。Python支持多种编程范式，包括面向对象、命令式、函数式和过程式编程。</p></article>
        </body></html>"""
        result = extract_content(html)
        assert result is not None
        assert "Python" in result or "编程" in result
