"""
AB Tester Simulation: validates Gate 2 backtest and Gate 3 AB test
using real LLM calls (not mock data).

Usage:
    python -m offgrid.validation.ab_tester_simulation --model gemma3:4b

This script:
1. Creates a temp project with a known bug
2. Runs 5 tasks through the generic pipeline (baseline)
3. Generates a candidate expert from the trajectories
4. Gate 2: backtests the candidate against the 5 source tasks
5. Gate 3: runs 10 more tasks, alternating candidate vs baseline
6. Reports pass/fail for each gate
"""

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
logger = logging.getLogger("ab_simulation")


def _create_buggy_project(tmpdir: str, variant: int = 0) -> str:
    """Create a small Python project with a known bug for testing."""
    src_dir = os.path.join(tmpdir, "src")
    tests_dir = os.path.join(tmpdir, "tests")
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(tests_dir, exist_ok=True)

    # Bug variants for different tasks
    bugs = [
        # 0: off-by-one in range
        ("def fibonacci(n):\n    if n <= 0:\n        return 0\n    if n == 1:\n        return 1\n    a, b = 0, 1\n    for i in range(n - 2):  # BUG: should be n - 1\n        a, b = b, a + b\n    return b\n",
         "from src.calc import fibonacci\n\ndef test_fibonacci():\n    assert fibonacci(0) == 0\n    assert fibonacci(1) == 1\n    assert fibonacci(5) == 5\n    assert fibonacci(10) == 55\n"),
        # 1: wrong operator
        ("def add(a, b):\n    return a - b  # BUG: should be +\n",
         "from src.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(0, 0) == 0\n"),
        # 2: missing return
        ("def is_even(n):\n    if n % 2 == 0:\n        return True\n    # BUG: missing return False\n",
         "from src.calc import is_even\n\ndef test_is_even():\n    assert is_even(2) is True\n    assert is_even(3) is False\n"),
        # 3: wrong comparison
        ("def max_val(a, b):\n    if a < b:  # BUG: should be >\n        return a\n    return b\n",
         "from src.calc import max_val\n\ndef test_max_val():\n    assert max_val(3, 5) == 5\n    assert max_val(10, 2) == 10\n"),
        # 4: index error
        ("def first_element(lst):\n    return lst[1]  # BUG: should be lst[0]\n",
         "from src.calc import first_element\n\ndef test_first_element():\n    assert first_element([10, 20, 30]) == 10\n"),
    ]

    idx = variant % len(bugs)
    code, test = bugs[idx]

    with open(os.path.join(src_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(src_dir, "calc.py"), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(tests_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(tests_dir, "test_calc.py"), "w", encoding="utf-8") as f:
        f.write(test)

    return tmpdir


def run_simulation(model: str = "gemma3:4b", ollama_url: str = "http://localhost:11434"):
    """Run the full Gate 2 + Gate 3 simulation."""
    from offgrid.llm.llama_backend import LLMBackend
    from offgrid.core.gate import Gate
    from offgrid.core.orchestrator import PipelineOrchestrator
    from offgrid.experts.locator import LocatorExpert
    from offgrid.experts.generator import GeneratorExpert
    from offgrid.experts.verifier import VerifierExpert
    from offgrid.experts.search_augmentor import SearchAugmentorExpert
    from offgrid.experts.office_handler import OfficeHandlerExpert
    from offgrid.tools.executor import ToolExecutor
    from offgrid.memory.offgrid_md import OffgridMemory
    from offgrid.registry.expert_registry import ExpertRegistry
    from offgrid.flywheel.trajectory_collector import TrajectoryCollector
    from offgrid.flywheel.pattern_detector import PatternDetector
    from offgrid.flywheel.expert_generator import ExpertGeneratorFlywheel
    from offgrid.flywheel.ab_tester import ABTester

    print(f"\n{'='*60}")
    print(f"  AB Tester Simulation — model: {model}")
    print(f"{'='*60}\n")

    # Use a dedicated trajectories dir for this simulation
    sim_dir = tempfile.mkdtemp(prefix="offgrid_ab_sim_")
    traj_dir = os.path.join(sim_dir, "trajectories")

    llm = LLMBackend(ollama_url=ollama_url, ollama_model=model)
    registry = ExpertRegistry()
    registry.load_builtin()
    collector = TrajectoryCollector(trajectories_dir=traj_dir)
    memory = OffgridMemory()

    results = {"gate2": None, "gate3": None, "details": []}

    # ── Phase 1: Run 5 baseline tasks to build trajectories ──
    print("[Phase 1] Running 5 baseline tasks...")
    baseline_trajectories = []

    for i in range(5):
        tmpdir = tempfile.mkdtemp(prefix=f"offgrid_sim_task{i}_")
        _create_buggy_project(tmpdir, variant=i)
        memory.init(tmpdir)

        tools = ToolExecutor(project_root=tmpdir)
        locator = LocatorExpert(llm=llm, tool_executor=tools)
        generator = GeneratorExpert(llm=llm, tool_executor=tools)
        verifier = VerifierExpert(llm=llm, tool_executor=tools)
        search = SearchAugmentorExpert(llm=llm)
        office = OfficeHandlerExpert()

        orchestrator = PipelineOrchestrator(
            locator=locator, generator=generator, verifier=verifier,
            search_augmentor=search, office_handler=office,
            tool_executor=tools, memory=memory, registry=registry,
            trajectory_collector=collector,
        )

        task = "修复 src/calc.py 中的bug，让测试通过"
        gate = Gate(llm=llm, registry=registry)
        gate_result = gate.classify(task)

        result = orchestrator.run(
            user_input=task,
            gate_result=gate_result,
            project_root=tmpdir,
            no_search=True,
        )

        status = "PASS" if result["success"] else "FAIL"
        print(f"  Task {i+1}: {status} ({result.get('elapsed', 0):.1f}s)")
        results["details"].append({"phase": "baseline", "task": i, "success": result["success"]})

        # Clean up temp project
        shutil.rmtree(tmpdir, ignore_errors=True)

    # Load trajectories for pattern detection
    all_trajs = collector.load_recent(limit=100)
    successful_trajs = [t for t in all_trajs if t.success]
    print(f"\n  Baseline: {len(successful_trajs)}/{len(all_trajs)} successful")

    if len(successful_trajs) < 3:
        print("\n  [SKIP] Not enough successful baseline tasks for Gate 2/3 simulation")
        results["gate2"] = "SKIP"
        results["gate3"] = "SKIP"
        _print_summary(results)
        return results

    # ── Phase 2: Generate candidate expert ──
    print("\n[Phase 2] Generating candidate expert from trajectories...")
    expert_gen = ExpertGeneratorFlywheel(llm=llm)
    pattern = {
        "expert_type": successful_trajs[0].expert_used,
        "count": len(successful_trajs),
        "trajectories": successful_trajs,
        "pipeline": successful_trajs[0].pipeline_steps,
    }
    expert_def = expert_gen.generate(pattern)

    if not expert_def:
        print("  [FAIL] Expert generation failed")
        results["gate2"] = "FAIL"
        results["gate3"] = "SKIP"
        _print_summary(results)
        return results

    print(f"  Generated: {expert_def['name']}")
    print(f"  Keywords: {expert_def.get('trigger_keywords', [])}")
    print(f"  Pipeline: {expert_def.get('pipeline', [])}")

    # ── Phase 3: Gate 2 — Backtest ──
    print("\n[Phase 3] Gate 2 — Backtest against source trajectories...")

    # Create a fresh orchestrator for backtest
    backtest_dir = tempfile.mkdtemp(prefix="offgrid_backtest_")
    _create_buggy_project(backtest_dir, variant=0)
    memory.init(backtest_dir)

    tools = ToolExecutor(project_root=backtest_dir)
    locator = LocatorExpert(llm=llm, tool_executor=tools)
    generator = GeneratorExpert(llm=llm, tool_executor=tools)
    verifier = VerifierExpert(llm=llm, tool_executor=tools)
    search = SearchAugmentorExpert(llm=llm)
    office = OfficeHandlerExpert()

    backtest_orchestrator = PipelineOrchestrator(
        locator=locator, generator=generator, verifier=verifier,
        search_augmentor=search, office_handler=office,
        tool_executor=tools, memory=memory, registry=registry,
        trajectory_collector=collector,
    )

    ab_tester = ABTester(
        registry=registry,
        collector=collector,
        orchestrator=backtest_orchestrator,
    )

    ab_tester.submit_candidate(expert_def, successful_trajs[:5])

    candidate_status = ab_tester.get_candidate_status(expert_def["name"])
    if candidate_status and candidate_status["gate2_passed"]:
        backtest_results = candidate_status.get("gate2_backtest", [])
        successes = sum(1 for r in backtest_results if r["success"])
        print(f"  Gate 2 PASSED: backtest {successes}/{len(backtest_results)}")
        results["gate2"] = "PASS"
    else:
        backtest_results = candidate_status.get("gate2_backtest", []) if candidate_status else []
        successes = sum(1 for r in backtest_results if r["success"])
        print(f"  Gate 2 FAILED: backtest {successes}/{len(backtest_results)}")
        results["gate2"] = "FAIL"
        results["gate3"] = "SKIP"
        _print_summary(results)
        shutil.rmtree(backtest_dir, ignore_errors=True)
        return results

    shutil.rmtree(backtest_dir, ignore_errors=True)

    # ── Phase 4: Gate 3 — AB Test (5 candidate + 5 baseline) ──
    print("\n[Phase 4] Gate 3 — AB test (10 real tasks)...")

    for i in range(10):
        tmpdir = tempfile.mkdtemp(prefix=f"offgrid_ab_task{i}_")
        _create_buggy_project(tmpdir, variant=i % 5)
        memory.init(tmpdir)

        tools = ToolExecutor(project_root=tmpdir)
        locator = LocatorExpert(llm=llm, tool_executor=tools)
        generator = GeneratorExpert(llm=llm, tool_executor=tools)
        verifier = VerifierExpert(llm=llm, tool_executor=tools)
        search = SearchAugmentorExpert(llm=llm)
        office = OfficeHandlerExpert()

        ab_orchestrator = PipelineOrchestrator(
            locator=locator, generator=generator, verifier=verifier,
            search_augmentor=search, office_handler=office,
            tool_executor=tools, memory=memory, registry=registry,
            trajectory_collector=collector,
            ab_tester=ab_tester,
        )

        task = "修复 src/calc.py 中的bug，让测试通过"
        gate = Gate(llm=llm, registry=registry)
        gate_result = gate.classify(task)

        result = ab_orchestrator.run(
            user_input=task,
            gate_result=gate_result,
            project_root=tmpdir,
            no_search=True,
        )

        # Determine if this was a candidate or baseline run
        ab_status = ab_tester.get_candidate_status(expert_def["name"])
        ab_count = len(ab_status["ab_results"]) if ab_status else 0
        used_new = i % 2 == 1  # alternating
        label = "候选" if used_new else "基线"
        status = "PASS" if result["success"] else "FAIL"
        print(f"  Task {i+1}/10 [{label}]: {status} ({result.get('elapsed', 0):.1f}s) — AB results: {ab_count}/10")

        results["details"].append({
            "phase": "ab_test", "task": i,
            "used_new": used_new, "success": result["success"],
        })

        shutil.rmtree(tmpdir, ignore_errors=True)

    # Check graduation
    final_status = ab_tester.get_candidate_status(expert_def["name"])
    if final_status:
        ab_results = final_status["ab_results"]
        new_results = [r for r in ab_results if r["used_new"]]
        baseline_results = [r for r in ab_results if not r["used_new"]]
        new_sr = sum(1 for r in new_results if r["success"]) / max(len(new_results), 1)
        baseline_sr = sum(1 for r in baseline_results if r["success"]) / max(len(baseline_results), 1)

        print(f"\n  AB Results: {len(ab_results)} total")
        print(f"  Candidate SR: {new_sr:.0%} ({sum(1 for r in new_results if r['success'])}/{len(new_results)})")
        print(f"  Baseline SR:  {baseline_sr:.0%} ({sum(1 for r in baseline_results if r['success'])}/{len(baseline_results)})")
        print(f"  Status: {final_status['status']}")

        if final_status["status"] == "graduated":
            results["gate3"] = "PASS"
        elif final_status["status"] == "archived":
            results["gate3"] = "FAIL"
        else:
            results["gate3"] = f"PENDING ({len(ab_results)}/10)"
    else:
        results["gate3"] = "ERROR"

    # Cleanup
    shutil.rmtree(sim_dir, ignore_errors=True)

    _print_summary(results)
    return results


def _print_summary(results: dict):
    print(f"\n{'='*60}")
    print("  SIMULATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Gate 2 (Backtest):  {results['gate2']}")
    print(f"  Gate 3 (AB Test):   {results['gate3']}")

    baseline_tasks = [d for d in results["details"] if d["phase"] == "baseline"]
    ab_tasks = [d for d in results["details"] if d["phase"] == "ab_test"]
    baseline_sr = sum(1 for d in baseline_tasks if d["success"]) / max(len(baseline_tasks), 1)
    print(f"  Baseline SR:        {baseline_sr:.0%} ({len(baseline_tasks)} tasks)")

    if ab_tasks:
        ab_sr = sum(1 for d in ab_tasks if d["success"]) / max(len(ab_tasks), 1)
        print(f"  AB Test SR:         {ab_sr:.0%} ({len(ab_tasks)} tasks)")

    all_pass = results["gate2"] == "PASS" and results["gate3"] in ("PASS", "FAIL")
    print(f"\n  Three-gate system: {'FUNCTIONAL' if all_pass else 'NEEDS WORK'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AB Tester Simulation")
    parser.add_argument("--model", default="gemma3:4b", help="Ollama model name")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama URL")
    args = parser.parse_args()

    run_simulation(model=args.model, ollama_url=args.ollama_url)
