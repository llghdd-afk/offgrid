#!/usr/bin/env python3
"""
OffGrid Prompt Optimizer — 基于 bench 测试结果自动优化专家 system_prompt。

流程：
1. 跑 bench 任务集，记录通过率
2. 把失败任务详情发给 Opus API 分析
3. Opus 返回 system_prompt 改进建议
4. 应用改动到 builtin_experts/*.yaml
5. 再跑一遍测试，对比通过率
6. 变好→保留，变差→回滚
7. 记录到 changelogs/

用法：
  python offgrid/scripts/prompt_optimizer.py --rounds 10 --target-pass-rate 0.8
  python offgrid/scripts/prompt_optimizer.py --rounds 1 --dry-run
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import yaml
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────
KAIWU_ROOT = Path(__file__).resolve().parent.parent  # offgrid/
BENCH_JSON = KAIWU_ROOT / "tests" / "bench_tasks.json"
BENCH_DIR = KAIWU_ROOT / "tests" / "bench_tasks"
EXPERTS_DIR = KAIWU_ROOT / "builtin_experts"
CHANGELOGS_DIR = KAIWU_ROOT / "changelogs"
PYTHON = sys.executable


def load_bench_tasks() -> list[dict]:
    """Load bench tasks from JSON."""
    with open(BENCH_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["tasks"]


def run_single_task(task: dict, timeout: int = 60) -> dict:
    """Run a single bench task in an isolated temp directory. Returns result dict."""
    task_id = task["task_id"]
    dir_name = task["dir_name"]
    test_file = task["test_file"]
    src_dir = BENCH_DIR / dir_name

    if not src_dir.exists():
        return {"task_id": task_id, "passed": False, "error": f"Dir not found: {src_dir}"}

    # Copy to temp workspace
    work_dir = tempfile.mkdtemp(prefix=f"kwbench_{task_id}_")
    try:
        for f in task["files"]:
            src = src_dir / f
            if src.exists():
                shutil.copy2(src, Path(work_dir) / f)

        # Run pytest
        t0 = time.time()
        try:
            result = subprocess.run(
                [PYTHON, "-m", "pytest", test_file, "-v", "--tb=short", "-q"],
                capture_output=True, text=True, cwd=work_dir,
                timeout=timeout, encoding="utf-8", errors="replace",
            )
            elapsed = time.time() - t0
            output = result.stdout + result.stderr
            passed_count, failed_count = _parse_pytest(output)
            all_passed = result.returncode == 0

            return {
                "task_id": task_id,
                "passed": all_passed,
                "passed_count": passed_count,
                "failed_count": failed_count,
                "elapsed": round(elapsed, 1),
                "output": output[-2000:],
                "error": "" if all_passed else output[-500:],
            }
        except subprocess.TimeoutExpired:
            return {"task_id": task_id, "passed": False, "error": "TIMEOUT", "elapsed": timeout}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _parse_pytest(output: str) -> tuple[int, int]:
    """Parse passed/failed counts from pytest output."""
    passed = 0
    failed = 0
    m = re.search(r"(\d+) passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", output)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+) error", output)
    if m:
        failed += int(m.group(1))
    return passed, failed


def run_bench(tasks: list[dict], timeout: int = 60) -> list[dict]:
    """Run all bench tasks sequentially. Returns list of result dicts."""
    results = []
    for i, task in enumerate(tasks):
        tag = f"[{i+1}/{len(tasks)}]"
        result = run_single_task(task, timeout=timeout)
        status = "PASS" if result["passed"] else "FAIL"
        elapsed = result.get("elapsed", 0)
        logger.info(f"{tag} {task['task_id']:5s} {task['dir_name']:30s} {status} ({elapsed}s)")
        results.append(result)
    return results


def compute_pass_rate(results: list[dict]) -> float:
    """Compute pass rate from results."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r["passed"])
    return passed / len(results)


def format_results_summary(results: list[dict]) -> str:
    """Format results as a human-readable summary."""
    lines = []
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"  {r['task_id']:5s} {status} ({r.get('elapsed', 0)}s)")
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    lines.append(f"\n  Pass rate: {passed}/{total} = {passed/total*100:.0f}%")
    return "\n".join(lines)


# ── Opus API integration ──────────────────────────────────────────────

def call_opus_for_analysis(failed_tasks: list[dict], expert_yamls: dict[str, str]) -> dict:
    """
    Send failed task details to Opus API for analysis.
    Returns: {"expert_name": str, "new_system_prompt": str, "reasoning": str}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Cannot call Opus API.")
        return {}

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return {}

    # Build context: failed tasks + current expert prompts
    failed_summary = []
    for ft in failed_tasks[:5]:  # Cap at 5 to save tokens
        failed_summary.append({
            "task_id": ft["task_id"],
            "description": ft.get("description", ""),
            "error": ft.get("error", "")[:500],
        })

    expert_prompts = {}
    for name, content in expert_yamls.items():
        try:
            data = yaml.safe_load(content)
            expert_prompts[name] = {
                "system_prompt": data.get("system_prompt", "")[:1000],
                "pipeline": data.get("pipeline", []),
            }
        except Exception:
            pass

    prompt = f"""你是OffGrid的prompt优化专家。以下是bench测试中失败的任务：

{json.dumps(failed_summary, ensure_ascii=False, indent=2)}

以下是当前所有专家的system_prompt（截取前1000字符）：

{json.dumps(expert_prompts, ensure_ascii=False, indent=2)}

分析失败原因，提出一个具体的system_prompt改进建议。

要求：
1. 只修改一个专家的system_prompt
2. 改动要具体，给出完整的新system_prompt
3. 不要修改trigger_keywords或pipeline
4. 改动要针对失败的根因，不要泛泛而谈

返回JSON格式：
{{"expert_file": "bugfix.yaml", "new_system_prompt": "完整的新prompt...", "reasoning": "改动原因..."}}

只返回JSON，不要解释。"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        # Parse JSON from response
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start:end + 1])
    except Exception as e:
        logger.error(f"Opus API call failed: {e}")

    return {}


def load_expert_yamls() -> dict[str, str]:
    """Load all expert YAML files as raw strings."""
    yamls = {}
    for f in sorted(EXPERTS_DIR.glob("*.yaml")):
        yamls[f.name] = f.read_text(encoding="utf-8")
    return yamls


def backup_expert(expert_file: str) -> str:
    """Backup an expert YAML file. Returns backup path."""
    src = EXPERTS_DIR / expert_file
    backup = src.with_suffix(".yaml.bak")
    shutil.copy2(src, backup)
    return str(backup)


def apply_prompt_change(expert_file: str, new_prompt: str) -> bool:
    """Apply a new system_prompt to an expert YAML file."""
    fpath = EXPERTS_DIR / expert_file
    if not fpath.exists():
        logger.error(f"Expert file not found: {fpath}")
        return False

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["system_prompt"] = new_prompt
        with open(fpath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False, width=120)
        return True
    except Exception as e:
        logger.error(f"Failed to apply change to {expert_file}: {e}")
        return False


def rollback_expert(expert_file: str):
    """Rollback an expert YAML from backup."""
    backup = EXPERTS_DIR / (expert_file + ".bak")
    target = EXPERTS_DIR / expert_file
    if backup.exists():
        shutil.copy2(backup, target)
        backup.unlink()
        logger.info(f"Rolled back {expert_file}")
    else:
        logger.warning(f"No backup found for {expert_file}")


def cleanup_backups():
    """Remove all .bak files."""
    for f in EXPERTS_DIR.glob("*.bak"):
        f.unlink()


def write_changelog(round_num: int, before_rate: float, after_rate: float,
                    change: dict, kept: bool):
    """Append optimization result to changelog."""
    CHANGELOGS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = CHANGELOGS_DIR / f"optimizer_{date_str}.md"

    entry = f"""
## Round {round_num} — {datetime.now().strftime("%H:%M:%S")}

- Before: {before_rate*100:.0f}%
- After: {after_rate*100:.0f}%
- Changed: {change.get('expert_file', 'none')}
- Kept: {'Yes' if kept else 'No (rolled back)'}
- Reasoning: {change.get('reasoning', 'N/A')[:200]}

---
"""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


# ── Main loop ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OffGrid Prompt Optimizer")
    parser.add_argument("--rounds", type=int, default=5, help="Max optimization rounds")
    parser.add_argument("--target-pass-rate", type=float, default=0.8, help="Target pass rate (0-1)")
    parser.add_argument("--dry-run", action="store_true", help="Only run bench, no optimization")
    parser.add_argument("--timeout", type=int, default=60, help="Per-task timeout in seconds")
    parser.add_argument("--tasks", type=str, default=None, help="Comma-separated task IDs to run")
    args = parser.parse_args()

    # Load tasks
    tasks = load_bench_tasks()
    if args.tasks:
        task_ids = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["task_id"] in task_ids]

    logger.info(f"Loaded {len(tasks)} bench tasks")

    # Initial bench run
    logger.info("=" * 60)
    logger.info("Running initial benchmark...")
    results = run_bench(tasks, timeout=args.timeout)
    pass_rate = compute_pass_rate(results)
    logger.info(f"\n{format_results_summary(results)}")

    if args.dry_run:
        logger.info("Dry run complete. No optimization performed.")
        return

    if pass_rate >= args.target_pass_rate:
        logger.info(f"Already at target ({pass_rate*100:.0f}% >= {args.target_pass_rate*100:.0f}%). Done.")
        return

    # Optimization loop
    for round_num in range(1, args.rounds + 1):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Optimization round {round_num}/{args.rounds}")
        logger.info(f"Current pass rate: {pass_rate*100:.0f}%")

        # Collect failed tasks with descriptions
        failed = []
        for r, t in zip(results, tasks):
            if not r["passed"]:
                failed.append({**r, "description": t.get("description", "")})

        if not failed:
            logger.info("All tasks passing. Done.")
            break

        # Load current expert YAMLs
        expert_yamls = load_expert_yamls()

        # Ask Opus for improvement
        logger.info(f"Analyzing {len(failed)} failures with Opus API...")
        change = call_opus_for_analysis(failed, expert_yamls)

        if not change or "expert_file" not in change or "new_system_prompt" not in change:
            logger.warning("Opus returned no actionable suggestion. Stopping.")
            break

        expert_file = change["expert_file"]
        new_prompt = change["new_system_prompt"]
        reasoning = change.get("reasoning", "")

        logger.info(f"Suggestion: modify {expert_file}")
        logger.info(f"Reasoning: {reasoning[:150]}...")

        # Backup and apply
        backup_expert(expert_file)
        if not apply_prompt_change(expert_file, new_prompt):
            logger.error("Failed to apply change. Stopping.")
            break

        # Re-run bench
        logger.info("Re-running benchmark after change...")
        new_results = run_bench(tasks, timeout=args.timeout)
        new_rate = compute_pass_rate(new_results)
        logger.info(f"\n{format_results_summary(new_results)}")

        # Compare
        if new_rate > pass_rate:
            logger.info(f"Improvement: {pass_rate*100:.0f}% -> {new_rate*100:.0f}%. Keeping change.")
            cleanup_backups()
            write_changelog(round_num, pass_rate, new_rate, change, kept=True)
            results = new_results
            pass_rate = new_rate
        else:
            logger.info(f"No improvement ({pass_rate*100:.0f}% -> {new_rate*100:.0f}%). Rolling back.")
            rollback_expert(expert_file)
            write_changelog(round_num, pass_rate, new_rate, change, kept=False)

        if pass_rate >= args.target_pass_rate:
            logger.info(f"Target reached ({pass_rate*100:.0f}% >= {args.target_pass_rate*100:.0f}%). Done.")
            break

    logger.info(f"\nFinal pass rate: {pass_rate*100:.0f}%")


if __name__ == "__main__":
    main()
