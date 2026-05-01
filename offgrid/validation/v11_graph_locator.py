"""
V11: BM25+graph locator accuracy and performance validation.
Validates:
  - Graph build succeeds with nodes > 0
  - BM25 retrieval finds expected files for test queries
  - Single retrieval < 3s (LOC-RED-5)
  - Incremental update works
  - Graph persists in SQLite (survives re-init)
"""

import os
import sys
import time
import tempfile
import shutil

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from offgrid.ast_engine.graph_builder import GraphBuilder
from offgrid.ast_engine.graph_retriever import GraphRetriever


def test_graph_build():
    """Test full graph build on offgrid's own codebase."""
    print("=" * 60)
    print("V11-1: Graph Build")
    print("=" * 60)

    builder = GraphBuilder(PROJECT_ROOT)
    result = builder.build_full()
    print(f"  nodes: {result['node_count']}")
    print(f"  edges: {result['edge_count']}")
    print(f"  files: {result['file_count']}")
    print(f"  time:  {result['elapsed_ms']}ms")

    assert result["node_count"] > 0, "node_count must be > 0"
    assert result["file_count"] > 0, "file_count must be > 0"
    assert result["elapsed_ms"] < 30000, f"build too slow: {result['elapsed_ms']}ms"
    print("  PASS")
    return result


def test_bm25_retrieval():
    """Test BM25+graph retrieval accuracy."""
    print("\n" + "=" * 60)
    print("V11-2: BM25+Graph Retrieval Accuracy")
    print("=" * 60)

    retriever = GraphRetriever(PROJECT_ROOT)

    test_cases = [
        {
            "query": "Gate JSON parse classify",
            "expect_file_contains": "gate.py",
        },
        {
            "query": "BM25 search retrieval graph",
            "expect_file_contains": "graph_retriever.py",
        },
        {
            "query": "locator expert run locate",
            "expect_file_contains": "locator",
        },
        {
            "query": "pipeline orchestrator expert sequence",
            "expect_file_contains": "orchestrator.py",
        },
        {
            "query": "tree sitter parser extract functions",
            "expect_file_contains": "parser.py",
        },
    ]

    passed = 0
    for case in test_cases:
        results = retriever.retrieve(case["query"])
        files = [r["file_path"] for r in results]
        matched = any(case["expect_file_contains"] in f for f in files)
        status = "PASS" if matched else "FAIL"
        if matched:
            passed += 1
        print(f"  [{status}] query='{case['query'][:40]}' -> {files[:3]}")

    print(f"  Score: {passed}/{len(test_cases)}")
    assert passed >= 3, f"Only {passed}/{len(test_cases)} passed, need >= 3"
    print("  PASS")


def test_retrieval_performance():
    """Test single retrieval is under 3 seconds (LOC-RED-5)."""
    print("\n" + "=" * 60)
    print("V11-3: Retrieval Performance (LOC-RED-5: <3s)")
    print("=" * 60)

    retriever = GraphRetriever(PROJECT_ROOT)

    queries = [
        "fix authentication bug in JWT token validation",
        "修复登录失败的问题",
        "refactor the pipeline orchestrator retry logic",
    ]

    for query in queries:
        t0 = time.perf_counter()
        retriever.retrieve(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        status = "PASS" if elapsed_ms < 3000 else "FAIL"
        print(f"  [{status}] '{query[:40]}' -> {elapsed_ms:.0f}ms")
        assert elapsed_ms < 3000, f"retrieval too slow: {elapsed_ms:.0f}ms > 3000ms"

    print("  PASS")


def test_incremental_update():
    """Test incremental update after file modification."""
    print("\n" + "=" * 60)
    print("V11-4: Incremental Update")
    print("=" * 60)

    # Create a temp file in the project, update graph, then clean up
    tmp_file = os.path.join(PROJECT_ROOT, "offgrid", "_v11_temp_test.py")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write("def v11_test_function():\n    return 42\n\ndef v11_helper():\n    v11_test_function()\n")

        builder = GraphBuilder(PROJECT_ROOT)
        result = builder.update_files([tmp_file])
        print(f"  updated: {result['files']} files, {result['node_count']} nodes, {result['elapsed_ms']}ms")
        assert result["node_count"] >= 1, "incremental update should find nodes"

        # Verify the new function is retrievable
        retriever = GraphRetriever(PROJECT_ROOT)
        retriever._bm25 = None  # Force rebuild
        results = retriever.retrieve("v11_test_function")
        names = [r["name"] for r in results]
        found = any("v11_test" in n for n in names)
        print(f"  search for 'v11_test_function': {'found' if found else 'not found'} in {names[:5]}")
        assert found, "incremental update node should be retrievable"
        print("  PASS")
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
            # Clean up from DB
            builder.update_files([tmp_file])


def test_persistence():
    """Test graph persists in SQLite (LOC-RED-2)."""
    print("\n" + "=" * 60)
    print("V11-5: Persistence (LOC-RED-2)")
    print("=" * 60)

    # Create a new retriever instance (simulates restart)
    retriever = GraphRetriever(PROJECT_ROOT)
    retriever._bm25 = None  # Force fresh load
    assert retriever.has_graph(), "graph should persist after build"

    results = retriever.retrieve("gate classify")
    assert len(results) > 0, "retrieval should work after simulated restart"
    print(f"  fresh retriever found {len(results)} results")
    print("  PASS")


def main():
    print("V11: BM25+Graph Locator Validation")
    print(f"Project: {PROJECT_ROOT}")
    print()

    try:
        test_graph_build()
        test_bm25_retrieval()
        test_retrieval_performance()
        test_incremental_update()
        test_persistence()

        print("\n" + "=" * 60)
        print("V11 ALL PASS")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nV11 FAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nV11 ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
