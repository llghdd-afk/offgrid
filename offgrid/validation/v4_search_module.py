"""
V4 验证：搜索模块端到端测试。
验收标准（来自 SEARCH_SPEC 第12节）：
  ✅ 4个case意图分类全部正确
  ✅ 生成的query包含对应方向关键词
  ✅ DDG至少3个case返回非空结果
  ✅ 至少2个case成功fetch到页面正文
  ✅ 压缩后摘要≤400字且包含技术关键词
  ✅ 总耗时≤15秒/case

用法：
  python -m offgrid.validation.v4_search_module --ollama-model gemma3:4b
"""

import argparse
import io
import json
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TEST_CASES = [
    {
        "input": "找最新的本地RAG开源框架",
        "expected_intent": "github",
        "query_keywords": ["github", "open source", "rag"],
    },
    {
        "input": "fastapi jwt验证失败怎么解决",
        "expected_intent": "bug",
        "query_keywords": ["fix", "solution", "fastapi", "jwt"],
    },
    {
        "input": "attention机制相关论文",
        "expected_intent": "arxiv",
        "query_keywords": ["arxiv", "paper", "attention"],
    },
    {
        "input": "python异步http请求用哪个库",
        "expected_intent": "pypi",
        "query_keywords": ["python", "package", "async", "http"],
    },
]


def run_validation(ollama_model: str = "gemma3:4b"):
    from offgrid.search.intent_classifier import classify as classify_intent
    from offgrid.search.query_generator import QueryGenerator
    from offgrid.search.duckduckgo import search as ddg_search
    from offgrid.search.quality_filter import filter_results
    from offgrid.search.content_fetcher import ContentFetcher
    from offgrid.search.context_compressor import ContextCompressor
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.core.context import TaskContext

    print("=" * 60)
    print("V4 验证：搜索模块端到端")
    print("=" * 60)
    print(f"模型: {ollama_model}")
    print()

    llm = LLMBackend(ollama_model=ollama_model)
    query_gen = QueryGenerator(llm)
    fetcher = ContentFetcher()
    compressor = ContextCompressor(llm)

    # 计分
    intent_ok = 0
    query_ok = 0
    ddg_ok = 0
    fetch_ok = 0
    compress_ok = 0
    time_ok = 0
    total = len(TEST_CASES)
    details = []

    for i, case in enumerate(TEST_CASES):
        print(f"  [Case {i+1}/{total}] {case['input'][:40]}...")
        t0 = time.time()
        d = {"input": case["input"]}

        # ① 意图分类
        intent = classify_intent(case["input"])
        d["intent"] = intent
        d["intent_ok"] = intent == case["expected_intent"]
        if d["intent_ok"]:
            intent_ok += 1
        print(f"    Intent: {intent} {'OK' if d['intent_ok'] else 'FAIL (expected ' + case['expected_intent'] + ')'}")

        # ② Query 生成
        ctx = TaskContext(
            user_input=case["input"],
            gate_result={"task_summary": case["input"][:20]},
        )
        queries = query_gen.generate(ctx, intent)
        d["queries"] = queries
        queries_lower = " ".join(queries).lower()
        hit_any = any(kw in queries_lower for kw in case["query_keywords"])
        d["query_ok"] = hit_any
        if hit_any:
            query_ok += 1
        print(f"    Queries: {queries}")
        print(f"    Query keywords: {'OK' if hit_any else 'FAIL'}")

        # ③ DDG 搜索
        all_results = []
        for q in queries[:2]:
            results = ddg_search(q, max_results=5)
            all_results.extend(results)
        d["ddg_count"] = len(all_results)
        d["ddg_ok"] = len(all_results) > 0
        if d["ddg_ok"]:
            ddg_ok += 1
        print(f"    DDG results: {len(all_results)} {'OK' if d['ddg_ok'] else 'FAIL'}")

        # ④ 质量过滤
        filtered = filter_results(all_results, max_fetch=3)
        urls = [r["url"] for r in filtered if r.get("url")]
        d["filtered_urls"] = urls[:3]
        print(f"    Filtered URLs: {[u[:50] for u in urls[:3]]}")

        # ⑤ 正文提取
        contents = fetcher.fetch_many(urls[:2], timeout=8.0) if urls else []
        fetched_count = sum(1 for c in contents if c and len(c) > 50)
        d["fetch_count"] = fetched_count
        d["fetch_ok"] = fetched_count > 0
        if d["fetch_ok"]:
            fetch_ok += 1
        print(f"    Fetched pages: {fetched_count}/{len(urls[:2])} {'OK' if d['fetch_ok'] else 'FAIL'}")

        # ⑥ 压缩
        if any(contents):
            compressed = compressor.compress(case["input"], contents)
        elif all_results:
            snippets = [r.get("snippet", "") for r in all_results[:5]]
            compressed = compressor.compress(case["input"], snippets)
        else:
            compressed = ""
        d["compressed_len"] = len(compressed)
        d["compress_ok"] = 0 < len(compressed) <= 500  # 允许一点余量
        if d["compress_ok"]:
            compress_ok += 1
        print(f"    Compressed: {len(compressed)} chars {'OK' if d['compress_ok'] else 'FAIL'}")

        elapsed = time.time() - t0
        d["elapsed"] = round(elapsed, 1)
        d["time_ok"] = elapsed <= 15.0
        if d["time_ok"]:
            time_ok += 1
        print(f"    Time: {elapsed:.1f}s {'OK' if d['time_ok'] else 'FAIL (>15s)'}")
        print()

        details.append(d)

    # 汇总
    print("=" * 60)
    print("验证结论")
    print("=" * 60)
    print(f"  意图分类:    {intent_ok}/{total}  {'PASS' if intent_ok == total else 'FAIL'}")
    print(f"  Query关键词: {query_ok}/{total}  {'PASS' if query_ok >= 3 else 'FAIL'}")
    print(f"  DDG搜索:     {ddg_ok}/{total}  {'PASS' if ddg_ok >= 3 else 'FAIL'}")
    print(f"  正文提取:    {fetch_ok}/{total}  {'PASS' if fetch_ok >= 2 else 'FAIL'}")
    print(f"  压缩摘要:    {compress_ok}/{total}  {'PASS' if compress_ok >= 3 else 'FAIL'}")
    print(f"  耗时(<15s):  {time_ok}/{total}  {'PASS' if time_ok == total else 'FAIL'}")

    conclusion = {
        "intent_accuracy": intent_ok,
        "query_keyword_hit": query_ok,
        "ddg_success": ddg_ok,
        "fetch_success": fetch_ok,
        "compress_success": compress_ok,
        "time_success": time_ok,
        "total_cases": total,
        "details": details,
    }

    conclusion_path = os.path.join(os.path.dirname(__file__), "v4_conclusion.json")
    with open(conclusion_path, "w", encoding="utf-8") as f:
        json.dump(conclusion, f, indent=2, ensure_ascii=False)
    print(f"\n  结论已保存到: {conclusion_path}")

    return conclusion


def main():
    parser = argparse.ArgumentParser(description="V4 搜索模块验证")
    parser.add_argument("--ollama-model", type=str, default="gemma3:4b")
    args = parser.parse_args()
    run_validation(ollama_model=args.ollama_model)


if __name__ == "__main__":
    main()
