"""
OffGrid Eval Runner: Standardized benchmark evaluation.

Runs all bench_tasks against the OffGrid pipeline and produces a structured
JSON report for before/after comparison. Designed to be run after each
significant code change to measure impact.

Usage:
    python -m offgrid.eval.run_eval --model qwen3:8b
    python -m offgrid.eval.run_eval --model qwen3:8b --task t01_pipeline
    python -m offgrid.eval.run_eval --compare report_before.json report_after.json

Output:
    offgrid_eval_report_<timestamp>.json
"""

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Task Registry ──

@dataclass
class BenchTask:
    """A single benchmark task definition."""
    task_id: str           # e.g. "t01_pipeline"
    category: str          # "fix", "codegen", "refactor", "chat"
    description: str       # User input that triggers this task
    test_file: str         # Relative path to test file (for verification)
    source_files: list     # Files that need to be modified
    difficulty: str = "easy"  # "easy" or "hard"


# All bench tasks with their metadata
BENCH_TASKS = [
    BenchTask("t01_pipeline", "codegen", "实现一个简单的数据处理流水线", "pipeline_test.py", ["pipeline.py"]),
    BenchTask("t02_config_chain", "codegen", "实现配置链式加载器", "config_test.py", ["config.py"]),
    BenchTask("t03_state_machine", "codegen", "实现有限状态机", "state_machine_test.py", ["state_machine.py"]),
    BenchTask("t04_hidden_bug_calc", "fix", "修复计算器中的隐藏bug", "calc_test.py", ["calc.py"]),
    BenchTask("t05_hidden_bug_parser", "fix", "修复解析器中的隐藏bug", "parser_test.py", ["parser.py"]),
    BenchTask("t06_hidden_bug_cache", "fix", "修复缓存系统中的隐藏bug", "cache_test.py", ["cache.py"]),
    BenchTask("t07_refactor_extract", "refactor", "重构：提取公共方法", "extract_test.py", ["extract.py"]),
    BenchTask("t08_refactor_rename", "refactor", "重构：重命名不规范的变量和函数", "rename_test.py", ["rename.py"]),
    BenchTask("t09_refactor_split", "refactor", "重构：拆分大文件", "split_test.py", ["split.py"]),
    BenchTask("t10_comprehensive", "fix", "修复综合项目中的多个bug", "comprehensive_test.py", ["comprehensive.py"]),
    BenchTask("t11_log_aggregator", "codegen", "实现日志聚合器", "log_aggregator_test.py", ["log_aggregator.py"], "hard"),
    BenchTask("t13_stack_calc", "codegen", "实现基于栈的计算器", "stack_calc_test.py", ["stack_calc.py"]),
    BenchTask("t14_http_router", "codegen", "实现简单的HTTP路由器", "http_router_test.py", ["http_router.py"]),
    BenchTask("t15_json_schema_validator", "codegen", "实现JSON Schema验证器", "json_schema_test.py", ["json_schema.py"], "hard"),
    BenchTask("t16_rbac_system", "codegen", "实现RBAC权限系统", "rbac_test.py", ["rbac.py"], "hard"),
    BenchTask("t19_db_migration", "codegen", "实现数据库迁移工具", "db_migration_test.py", ["db_migration.py"], "hard"),
    BenchTask("t20_doc_generator", "codegen", "实现文档生成器", "doc_generator_test.py", ["doc_generator.py"]),
    BenchTask("t21_expr_engine", "codegen", "实现表达式引擎", "expr_engine_test.py", ["expr_engine.py"], "hard"),
    BenchTask("t23_micro_orm", "codegen", "实现微型ORM", "micro_orm_test.py", ["micro_orm.py"], "hard"),
    BenchTask("t24_compiler_frontend", "codegen", "实现编译器前端", "compiler_test.py", ["compiler.py"], "hard"),
    BenchTask("t25_task_scheduler", "codegen", "实现任务调度器", "test_scheduler.py", ["scheduler.py", "task_graph.py", "worker.py"], "hard"),
    BenchTask("t27_git_objects", "codegen", "实现Git对象存储", "git_objects_test.py", ["objects.py", "index.py", "refs.py"], "hard"),
    BenchTask("t28_protocol_parser", "codegen", "实现协议解析器", "protocol_parser_test.py", ["codec.py", "frame.py", "session.py"], "hard"),
    BenchTask("t30_plugin_system", "codegen", "实现插件系统", "plugin_system_test.py", ["core.py", "loader.py", "registry.py", "sandbox.py"], "hard"),
]

BENCH_DIR = Path(__file__).parent.parent / "tests" / "bench_tasks"


@dataclass
class TaskResult:
    """Result of running a single benchmark task."""
    task_id: str
    category: str
    difficulty: str
    success: bool
    tests_passed: int
    tests_total: int
    elapsed_s: float
    retry_count: int
    error: str = ""
    used_react: bool = False


@dataclass
class EvalReport:
    """Complete evaluation report."""
    model: str
    timestamp: str
    total_tasks: int
    passed: int
    failed: int
    pass_rate: float
    total_elapsed_s: float
    by_category: dict
    by_difficulty: dict
    results: list


def run_eval(model: str, ollama_url: str = "http://localhost:11434",
             task_filter: Optional[str] = None, verbose: bool = False) -> EvalReport:
    """
    Run the full eval suite (or a single task) and produce a report.
    """
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.core.gate import Gate
    from offgrid.core.orchestrator import PipelineOrchestrator
    from offgrid.experts.locator import LocatorExpert
    from offgrid.experts.generator import GeneratorExpert
    from offgrid.experts.verifier import VerifierExpert
    from offgrid.experts.search_augmentor import SearchAugmentorExpert
    from offgrid.experts.office_handler import OfficeHandlerExpert
    from offgrid.experts.chat_expert import ChatExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.memory.offgrid_md import OffgridMemory
    from offgrid.registry.expert_registry import ExpertRegistry

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results = []
    total_start = time.time()

    # Initialize LLM
    llm = LLMBackend(ollama_url=ollama_url, ollama_model=model)

    # Filter tasks
    tasks = BENCH_TASKS
    if task_filter:
        tasks = [t for t in tasks if t.task_id == task_filter]
        if not tasks:
            print(f"❌ Task '{task_filter}' not found")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  OffGrid Eval: {model}")
    print(f"  Tasks: {len(tasks)}")
    print(f"{'='*60}\n")

    for task in tasks:
        print(f"▶ [{task.task_id}] {task.description} ({task.category}/{task.difficulty})")
        result = _run_single_task(task, llm, verbose)
        results.append(result)

        status = "✅ PASS" if result.success else "❌ FAIL"
        print(f"  {status} | {result.tests_passed}/{result.tests_total} tests | {result.elapsed_s:.1f}s")
        if result.error:
            print(f"  Error: {result.error[:80]}")
        print()

    # Build report
    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed

    # Category breakdown
    by_cat = {}
    for r in results:
        cat = r.category
        if cat not in by_cat:
            by_cat[cat] = {"total": 0, "passed": 0}
        by_cat[cat]["total"] += 1
        if r.success:
            by_cat[cat]["passed"] += 1

    # Difficulty breakdown
    by_diff = {}
    for r in results:
        diff = r.difficulty
        if diff not in by_diff:
            by_diff[diff] = {"total": 0, "passed": 0}
        by_diff[diff]["total"] += 1
        if r.success:
            by_diff[diff]["passed"] += 1

    report = EvalReport(
        model=model,
        timestamp=timestamp,
        total_tasks=len(tasks),
        passed=passed,
        failed=failed,
        pass_rate=passed / len(tasks) if tasks else 0,
        total_elapsed_s=total_elapsed,
        by_category=by_cat,
        by_difficulty=by_diff,
        results=[asdict(r) for r in results],
    )

    # Save report
    report_path = f"offgrid_eval_report_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  结果: {passed}/{len(tasks)} PASS ({report.pass_rate:.0%})")
    print(f"  耗时: {total_elapsed:.1f}s")
    print(f"  分类: ", end="")
    for cat, info in by_cat.items():
        print(f"{cat}={info['passed']}/{info['total']} ", end="")
    print()
    print(f"  难度: ", end="")
    for diff, info in by_diff.items():
        print(f"{diff}={info['passed']}/{info['total']} ", end="")
    print()
    print(f"  报告: {report_path}")
    print(f"{'='*60}\n")

    return report


def _run_single_task(task: BenchTask, llm, verbose: bool) -> TaskResult:
    """Run a single benchmark task in an isolated temp directory."""
    from offgrid.core.gate import Gate
    from offgrid.core.orchestrator import PipelineOrchestrator
    from offgrid.experts.locator import LocatorExpert
    from offgrid.experts.generator import GeneratorExpert
    from offgrid.experts.verifier import VerifierExpert
    from offgrid.experts.search_augmentor import SearchAugmentorExpert
    from offgrid.experts.office_handler import OfficeHandlerExpert
    from offgrid.experts.chat_expert import ChatExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.memory.offgrid_md import OffgridMemory
    from offgrid.registry.expert_registry import ExpertRegistry

    task_dir = BENCH_DIR / task.task_id
    if not task_dir.exists():
        return TaskResult(
            task_id=task.task_id, category=task.category,
            difficulty=task.difficulty, success=False,
            tests_passed=0, tests_total=0, elapsed_s=0,
            retry_count=0, error=f"Task directory not found: {task_dir}",
        )

    # Copy task to temp directory (isolation)
    tmpdir = tempfile.mkdtemp(prefix=f"offgrid_eval_{task.task_id}_")
    try:
        for f in task_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, os.path.join(tmpdir, f.name))

        # Initialize components
        tool_executor = ToolExecutor(project_root=tmpdir)
        memory = OffgridMemory()
        registry = ExpertRegistry()
        locator = LocatorExpert(llm=llm, tools=tool_executor)
        generator = GeneratorExpert(llm=llm, tools=tool_executor)
        verifier = VerifierExpert(llm=llm, tools=tool_executor)
        search_augmentor = SearchAugmentorExpert(llm=llm)
        office_handler = OfficeHandlerExpert(llm=llm, tools=tool_executor)
        chat_expert = ChatExpert(llm=llm)
        gate = Gate(llm=llm, registry=registry)

        orchestrator = PipelineOrchestrator(
            locator=locator,
            generator=generator,
            verifier=verifier,
            search_augmentor=search_augmentor,
            office_handler=office_handler,
            tool_executor=tool_executor,
            memory=memory,
            registry=registry,
            chat_expert=chat_expert,
        )

        # Classify
        gate_result = gate.classify(task.description)

        # Run
        t0 = time.time()
        result = orchestrator.run(
            user_input=task.description,
            gate_result=gate_result,
            project_root=tmpdir,
            no_search=True,
            skip_checkpoint=True,
        )
        elapsed = time.time() - t0

        ctx = result.get("context")
        verifier_out = ctx.verifier_output if ctx else {}
        react_out = ctx.react_result if ctx else None

        return TaskResult(
            task_id=task.task_id,
            category=task.category,
            difficulty=task.difficulty,
            success=result.get("success", False),
            tests_passed=verifier_out.get("tests_passed", 0) if verifier_out else 0,
            tests_total=verifier_out.get("tests_total", 0) if verifier_out else 0,
            elapsed_s=elapsed,
            retry_count=ctx.retry_count if ctx else 0,
            error=result.get("error", "") or "",
            used_react=react_out is not None,
        )

    except Exception as e:
        return TaskResult(
            task_id=task.task_id, category=task.category,
            difficulty=task.difficulty, success=False,
            tests_passed=0, tests_total=0, elapsed_s=0,
            retry_count=0, error=f"{type(e).__name__}: {e}",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def compare_reports(before_path: str, after_path: str):
    """Compare two eval reports and show the diff."""
    with open(before_path) as f:
        before = json.load(f)
    with open(after_path) as f:
        after = json.load(f)

    print(f"\n{'='*60}")
    print(f"  对比: {before['model']} → {after['model']}")
    print(f"{'='*60}")

    # Overall
    bp, ap = before["pass_rate"], after["pass_rate"]
    delta = ap - bp
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
    print(f"\n  总通过率: {bp:.0%} → {ap:.0%} ({arrow}{abs(delta):.0%})")

    # Per-task diff
    before_map = {r["task_id"]: r for r in before["results"]}
    after_map = {r["task_id"]: r for r in after["results"]}

    improved = []
    regressed = []
    for tid in sorted(set(before_map) | set(after_map)):
        b = before_map.get(tid, {}).get("success", False)
        a = after_map.get(tid, {}).get("success", False)
        if not b and a:
            improved.append(tid)
        elif b and not a:
            regressed.append(tid)

    if improved:
        print(f"\n  ✅ 改善 ({len(improved)}): {', '.join(improved)}")
    if regressed:
        print(f"\n  ❌ 退步 ({len(regressed)}): {', '.join(regressed)}")
    if not improved and not regressed:
        print("\n  无变化")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="OffGrid Eval Runner")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model name")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--task", help="Run single task (e.g. t01_pipeline)")
    parser.add_argument("--compare", nargs=2, help="Compare two report JSON files")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.compare:
        compare_reports(args.compare[0], args.compare[1])
    else:
        run_eval(model=args.model, ollama_url=args.url,
                 task_filter=args.task, verbose=args.verbose)


if __name__ == "__main__":
    main()
