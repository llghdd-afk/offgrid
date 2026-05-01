"""
预置专家验证框架
验证 BugFixExpert / TestGenExpert 在标准任务上的通过率（目标 ≥85%）。
每个专家 5 个任务，走完整 Gate → Locator → Generator → Verifier 流水线。

用法:
  python -m offgrid.validation.expert_benchmark --ollama-model gemma3:4b
  python -m offgrid.validation.expert_benchmark --ollama-model gemma3:4b --expert BugFixExpert
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time

# ── Windows GBK encoding fix ──
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════════════════════════════
# BugFixExpert 测试任务 — 每个 setup 创建带 bug 的源码 + 会失败的测试
# ═══════════════════════════════════════════════════════════════════

def _setup_off_by_one(tmpdir: str):
    """Off-by-one: range(n) should be range(n+1) to include n."""
    src = os.path.join(tmpdir, "src")
    tests = os.path.join(tmpdir, "tests")
    os.makedirs(src); os.makedirs(tests)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "utils.py"), "w", encoding="utf-8") as f:
        f.write(
            'def sum_range(n):\n'
            '    """Return sum of 0..n inclusive."""\n'
            '    total = 0\n'
            '    for i in range(n):  # BUG: should be range(n + 1)\n'
            '        total += i\n'
            '    return total\n'
        )
    with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests, "test_utils.py"), "w", encoding="utf-8") as f:
        f.write(
            'import sys, os\n'
            'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))\n'
            'from src.utils import sum_range\n\n'
            'def test_sum_range_5():\n'
            '    assert sum_range(5) == 15\n\n'
            'def test_sum_range_0():\n'
            '    assert sum_range(0) == 0\n\n'
            'def test_sum_range_1():\n'
            '    assert sum_range(1) == 1\n'
        )


def _setup_missing_return(tmpdir: str):
    """Missing return: function computes result but doesn't return it."""
    src = os.path.join(tmpdir, "src")
    tests = os.path.join(tmpdir, "tests")
    os.makedirs(src); os.makedirs(tests)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "math_ops.py"), "w", encoding="utf-8") as f:
        f.write(
            'def multiply(a, b):\n'
            '    """Return a * b."""\n'
            '    result = a * b\n'
            '    # BUG: missing return statement\n'
        )
    with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests, "test_math_ops.py"), "w", encoding="utf-8") as f:
        f.write(
            'import sys, os\n'
            'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))\n'
            'from src.math_ops import multiply\n\n'
            'def test_multiply_positive():\n'
            '    assert multiply(3, 4) == 12\n\n'
            'def test_multiply_zero():\n'
            '    assert multiply(0, 5) == 0\n\n'
            'def test_multiply_negative():\n'
            '    assert multiply(-2, 3) == -6\n'
        )


def _setup_wrong_comparison(tmpdir: str):
    """Wrong operator: uses == instead of != for filtering."""
    src = os.path.join(tmpdir, "src")
    tests = os.path.join(tmpdir, "tests")
    os.makedirs(src); os.makedirs(tests)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "filters.py"), "w", encoding="utf-8") as f:
        f.write(
            'def remove_empty(items):\n'
            '    """Remove empty strings from list."""\n'
            '    result = []\n'
            '    for item in items:\n'
            '        if item == "":  # BUG: should be != ""\n'
            '            result.append(item)\n'
            '    return result\n'
        )
    with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests, "test_filters.py"), "w", encoding="utf-8") as f:
        f.write(
            'import sys, os\n'
            'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))\n'
            'from src.filters import remove_empty\n\n'
            'def test_remove_empty_basic():\n'
            '    assert remove_empty(["a", "", "b", ""]) == ["a", "b"]\n\n'
            'def test_remove_empty_none():\n'
            '    assert remove_empty(["x", "y"]) == ["x", "y"]\n\n'
            'def test_remove_empty_all():\n'
            '    assert remove_empty(["", ""]) == []\n'
        )


def _setup_uninitialized_var(tmpdir: str):
    """Uninitialized variable: counter used before assignment in branch."""
    src = os.path.join(tmpdir, "src")
    tests = os.path.join(tmpdir, "tests")
    os.makedirs(src); os.makedirs(tests)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "counter.py"), "w", encoding="utf-8") as f:
        f.write(
            'def count_positives(numbers):\n'
            '    """Count how many positive numbers in list."""\n'
            '    # BUG: count not initialized before loop\n'
            '    for n in numbers:\n'
            '        if n > 0:\n'
            '            count += 1\n'
            '    return count\n'
        )
    with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests, "test_counter.py"), "w", encoding="utf-8") as f:
        f.write(
            'import sys, os\n'
            'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))\n'
            'from src.counter import count_positives\n\n'
            'def test_count_mixed():\n'
            '    assert count_positives([1, -2, 3, 0, 5]) == 3\n\n'
            'def test_count_none():\n'
            '    assert count_positives([-1, -2]) == 0\n\n'
            'def test_count_all():\n'
            '    assert count_positives([1, 2, 3]) == 3\n'
        )


def _setup_wrong_format(tmpdir: str):
    """Wrong string format: f-string placeholder typo."""
    src = os.path.join(tmpdir, "src")
    tests = os.path.join(tmpdir, "tests")
    os.makedirs(src); os.makedirs(tests)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "greeting.py"), "w", encoding="utf-8") as f:
        f.write(
            'def greet(name, age):\n'
            '    """Return greeting string."""\n'
            '    return f"Hello {name}, you are {nam} years old"  # BUG: nam instead of age\n'
        )
    with open(os.path.join(tests, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests, "test_greeting.py"), "w", encoding="utf-8") as f:
        f.write(
            'import sys, os\n'
            'sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))\n'
            'from src.greeting import greet\n\n'
            'def test_greet_basic():\n'
            '    assert greet("Alice", 30) == "Hello Alice, you are 30 years old"\n\n'
            'def test_greet_empty():\n'
            '    assert greet("", 0) == "Hello , you are 0 years old"\n'
        )


# ═══════════════════════════════════════════════════════════════════
# TestGenExpert 测试任务 — 每个 setup 创建源码但无测试文件
# ═══════════════════════════════════════════════════════════════════

def _setup_calc_no_tests(tmpdir: str):
    """Calculator module, no tests."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "calc.py"), "w", encoding="utf-8") as f:
        f.write(
            'def add(a, b):\n'
            '    return a + b\n\n'
            'def subtract(a, b):\n'
            '    return a - b\n\n'
            'def divide(a, b):\n'
            '    if b == 0:\n'
            '        raise ValueError("Cannot divide by zero")\n'
            '    return a / b\n'
        )


def _setup_string_utils_no_tests(tmpdir: str):
    """String utility module, no tests."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "string_utils.py"), "w", encoding="utf-8") as f:
        f.write(
            'def reverse_string(s):\n'
            '    return s[::-1]\n\n'
            'def is_palindrome(s):\n'
            '    cleaned = s.lower().replace(" ", "")\n'
            '    return cleaned == cleaned[::-1]\n\n'
            'def truncate(s, max_len):\n'
            '    if len(s) <= max_len:\n'
            '        return s\n'
            '    return s[:max_len - 3] + "..."\n'
        )


def _setup_sort_no_tests(tmpdir: str):
    """List sorting module, no tests."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "sorting.py"), "w", encoding="utf-8") as f:
        f.write(
            'def bubble_sort(arr):\n'
            '    result = list(arr)\n'
            '    n = len(result)\n'
            '    for i in range(n):\n'
            '        for j in range(0, n - i - 1):\n'
            '            if result[j] > result[j + 1]:\n'
            '                result[j], result[j + 1] = result[j + 1], result[j]\n'
            '    return result\n\n'
            'def find_max(arr):\n'
            '    if not arr:\n'
            '        return None\n'
            '    return max(arr)\n'
        )


def _setup_filepath_no_tests(tmpdir: str):
    """File path utility module, no tests."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "pathutil.py"), "w", encoding="utf-8") as f:
        f.write(
            'import os\n\n'
            'def get_extension(filepath):\n'
            '    _, ext = os.path.splitext(filepath)\n'
            '    return ext\n\n'
            'def join_paths(*parts):\n'
            '    return os.path.join(*parts)\n\n'
            'def is_python_file(filepath):\n'
            '    return filepath.endswith(".py")\n'
        )


def _setup_validator_no_tests(tmpdir: str):
    """Data validation module, no tests."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src)

    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src, "validator.py"), "w", encoding="utf-8") as f:
        f.write(
            'def is_valid_email(email):\n'
            '    return isinstance(email, str) and "@" in email and "." in email.split("@")[-1]\n\n'
            'def is_positive_int(value):\n'
            '    return isinstance(value, int) and value > 0\n\n'
            'def is_non_empty_string(value):\n'
            '    return isinstance(value, str) and len(value.strip()) > 0\n'
        )


# ═══════════════════════════════════════════════════════════════════
# 任务定义
# ═══════════════════════════════════════════════════════════════════

BENCHMARK_TASKS = {
    "BugFixExpert": [
        {
            "name": "off_by_one_loop",
            "description": "修复 src/utils.py 中 sum_range 函数的 off-by-one 错误，测试失败",
            "setup": _setup_off_by_one,
            "expected_expert_type": "locator_repair",
        },
        {
            "name": "missing_return",
            "description": "修复 src/math_ops.py 中 multiply 函数缺少 return 语句的 bug",
            "setup": _setup_missing_return,
            "expected_expert_type": "locator_repair",
        },
        {
            "name": "wrong_comparison",
            "description": "修复 src/filters.py 中 remove_empty 函数的比较运算符错误",
            "setup": _setup_wrong_comparison,
            "expected_expert_type": "locator_repair",
        },
        {
            "name": "uninitialized_variable",
            "description": "修复 src/counter.py 中 count_positives 函数的变量未初始化错误",
            "setup": _setup_uninitialized_var,
            "expected_expert_type": "locator_repair",
        },
        {
            "name": "wrong_string_format",
            "description": "修复 src/greeting.py 中 greet 函数的 f-string 变量名错误",
            "setup": _setup_wrong_format,
            "expected_expert_type": "locator_repair",
        },
    ],
    "TestGenExpert": [
        {
            "name": "calc_tests",
            "description": "为 src/calc.py 中的 add, subtract, divide 函数生成 pytest 单元测试",
            "setup": _setup_calc_no_tests,
            "expected_expert_type": "codegen",
        },
        {
            "name": "string_utils_tests",
            "description": "为 src/string_utils.py 中的字符串工具函数生成 pytest 单元测试",
            "setup": _setup_string_utils_no_tests,
            "expected_expert_type": "codegen",
        },
        {
            "name": "sort_tests",
            "description": "为 src/sorting.py 中的排序函数生成 pytest 单元测试",
            "setup": _setup_sort_no_tests,
            "expected_expert_type": "codegen",
        },
        {
            "name": "filepath_tests",
            "description": "为 src/pathutil.py 中的路径工具函数生成 pytest 单元测试",
            "setup": _setup_filepath_no_tests,
            "expected_expert_type": "codegen",
        },
        {
            "name": "validator_tests",
            "description": "为 src/validator.py 中的数据验证函数生成 pytest 单元测试",
            "setup": _setup_validator_no_tests,
            "expected_expert_type": "codegen",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════
# 流水线构建 & 执行
# ═══════════════════════════════════════════════════════════════════

def _build_pipeline(llm):
    """Build a full pipeline (Gate, Orchestrator) from an LLM backend."""
    from offgrid.core.gate import Gate
    from offgrid.core.orchestrator import PipelineOrchestrator
    from offgrid.experts.locator import LocatorExpert
    from offgrid.experts.generator import GeneratorExpert
    from offgrid.experts.verifier import VerifierExpert
    from offgrid.experts.search_augmentor import SearchAugmentorExpert
    from offgrid.experts.office_handler import OfficeHandlerExpert
    from offgrid.memory.offgrid_md import OffgridMemory
    from offgrid.registry.expert_registry import ExpertRegistry
    from offgrid.tools.executor import ToolExecutor

    registry = ExpertRegistry()
    registry.load_builtin()

    # ToolExecutor with a dummy root — will be overridden per task
    tool_executor = ToolExecutor(project_root=".")

    gate = Gate(llm, registry=registry)
    locator = LocatorExpert(llm, tool_executor)
    generator = GeneratorExpert(llm, tool_executor, num_candidates=1)
    verifier = VerifierExpert(llm, tool_executor)
    search = SearchAugmentorExpert(llm)
    office = OfficeHandlerExpert()
    memory = OffgridMemory()

    orchestrator = PipelineOrchestrator(
        locator=locator,
        generator=generator,
        verifier=verifier,
        search_augmentor=search,
        office_handler=office,
        tool_executor=tool_executor,
        memory=memory,
        registry=registry,
    )

    return gate, orchestrator, tool_executor


def _run_single_task(task: dict, gate, orchestrator, tool_executor, status_lines: list) -> dict:
    """Run one benchmark task through the full pipeline. Returns result dict."""
    tmpdir = tempfile.mkdtemp(prefix=f"offgrid_bench_{task['name']}_")
    try:
        # Setup project
        task["setup"](tmpdir)

        # Point tool_executor at this temp project
        tool_executor.project_root = os.path.abspath(tmpdir)

        # Gate
        gate_result = gate.classify(task["description"])

        # Override expert_type if gate misroutes (benchmark needs deterministic routing)
        gate_result["expert_type"] = task["expected_expert_type"]

        def on_status(stage, detail):
            status_lines.append(f"    [{stage}] {detail}")

        # Run pipeline
        result = orchestrator.run(
            user_input=task["description"],
            gate_result=gate_result,
            project_root=tmpdir,
            on_status=on_status,
        )

        return {
            "name": task["name"],
            "success": result["success"],
            "elapsed_s": round(result["elapsed"], 2),
            "error": result.get("error"),
            "tmpdir": tmpdir,
        }
    except Exception as e:
        return {
            "name": task["name"],
            "success": False,
            "elapsed_s": 0,
            "error": str(e),
            "tmpdir": tmpdir,
        }
    finally:
        # Cleanup temp dir
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

def run_benchmark(ollama_model: str = "gemma3:4b", experts_to_test: list[str] | None = None):
    """Run benchmark for specified experts (or all)."""
    from offgrid.llm.llama_backend import LLMBackend
    import httpx

    print("=" * 60)
    print("Expert Benchmark Validation")
    print("=" * 60)
    print(f"模型: {ollama_model}")

    # Check Ollama
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code != 200:
            raise ConnectionError()
    except Exception:
        print("  Ollama 不在线。请启动: ollama serve")
        _save_results({"status": "skipped", "reason": "Ollama offline", "experts": {}})
        return

    llm = LLMBackend(ollama_model=ollama_model)
    gate, orchestrator, tool_executor = _build_pipeline(llm)

    # Filter experts
    expert_names = list(BENCHMARK_TASKS.keys())
    if experts_to_test:
        expert_names = [e for e in expert_names if e in experts_to_test]

    total_tasks = sum(len(BENCHMARK_TASKS[e]) for e in expert_names)
    print(f"专家: {expert_names}")
    print(f"任务总数: {total_tasks}")
    print()

    all_results = {}

    for expert_name in expert_names:
        tasks = BENCHMARK_TASKS[expert_name]
        print(f"── {expert_name} ({len(tasks)} tasks) ──")

        expert_results = []
        passed = 0

        for i, task in enumerate(tasks):
            print(f"  [{i+1}/{len(tasks)}] {task['name']}: {task['description']}")
            status_lines = []

            t0 = time.time()
            result = _run_single_task(task, gate, orchestrator, tool_executor, status_lines)
            wall_time = time.time() - t0

            # Print status lines (pipeline trace)
            for line in status_lines[-5:]:  # last 5 lines to keep output manageable
                print(line)

            if result["success"]:
                passed += 1
                print(f"  => PASS ({result['elapsed_s']:.1f}s)")
            else:
                err = result.get("error", "")
                print(f"  => FAIL ({result['elapsed_s']:.1f}s) {err[:100]}")
            print()

            expert_results.append(result)

        rate = passed / len(tasks) if tasks else 0
        avg_latency = sum(r["elapsed_s"] for r in expert_results) / len(expert_results) if expert_results else 0
        threshold_met = rate >= 0.85

        print(f"  {expert_name} 结果: {passed}/{len(tasks)} = {rate*100:.0f}%"
              f" (avg {avg_latency:.1f}s) {'PASS' if threshold_met else 'FAIL'}")
        print()

        all_results[expert_name] = {
            "passed": passed,
            "total": len(tasks),
            "success_rate": round(rate, 4),
            "avg_latency_s": round(avg_latency, 2),
            "threshold_met": threshold_met,
            "tasks": [{k: v for k, v in r.items() if k != "tmpdir"} for r in expert_results],
        }

    # Summary
    print("=" * 60)
    print("总结")
    print("=" * 60)
    all_pass = all(r["threshold_met"] for r in all_results.values())
    for name, r in all_results.items():
        status = "PASS" if r["threshold_met"] else "FAIL"
        print(f"  {name}: {r['passed']}/{r['total']} = {r['success_rate']*100:.0f}% [{status}]")
    print(f"  总体: {'PASS' if all_pass else 'FAIL'} (阈值 ≥85%)")

    conclusion = {
        "status": "completed",
        "model": ollama_model,
        "overall_pass": all_pass,
        "experts": all_results,
    }
    _save_results(conclusion)
    return conclusion


def _save_results(data: dict):
    results_path = os.path.join(os.path.dirname(__file__), "expert_benchmark_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {results_path}")


def main():
    parser = argparse.ArgumentParser(description="Expert Benchmark Validation")
    parser.add_argument("--ollama-model", type=str, default="gemma3:4b",
                        help="Ollama model to use")
    parser.add_argument("--expert", type=str, default=None,
                        help="Only test this expert (e.g. BugFixExpert)")
    args = parser.parse_args()

    experts = [args.expert] if args.expert else None
    run_benchmark(ollama_model=args.ollama_model, experts_to_test=experts)


if __name__ == "__main__":
    main()
