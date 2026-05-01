"""
E2E test harness for offgrid: 30 tasks against a real Ollama LLM.
First half: framework infrastructure (no task definitions).

Usage:
    python -m offgrid.validation.e2e_30tasks --model gemma4:e2b --group all
    python -m offgrid.validation.e2e_30tasks --task 5
"""

import argparse
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from typing import Callable

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

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e2b"
GROUPS = [1, 2, 3]
VALID_CATEGORIES = {"fix", "codegen", "chat", "refactor", "doc"}

COL_ID = 4
COL_GROUP = 6
COL_CAT = 10
COL_PASS = 6
COL_TIME = 8
COL_REASON = 40


# ── Pipeline builder ──────────────────────────────────────────────────────

def build_pipeline(project_root: str, ollama_model: str = DEFAULT_MODEL):
    """
    Build the full offgrid pipeline wired to a real Ollama backend.
    Returns (gate, orchestrator, memory).
    """
    llm = LLMBackend(ollama_url=DEFAULT_OLLAMA_URL, ollama_model=ollama_model)
    tool_executor = ToolExecutor(project_root)

    memory = OffgridMemory()
    memory.init(project_root)

    # Experts
    locator = LocatorExpert(llm, tool_executor)
    generator = GeneratorExpert(llm, tool_executor)
    verifier = VerifierExpert(llm, tool_executor)
    search_augmentor = SearchAugmentorExpert(llm)
    office_handler = OfficeHandlerExpert()
    chat_expert = ChatExpert(llm, search_augmentor=search_augmentor)

    # Registry
    registry = ExpertRegistry()
    registry.load_builtin()

    # Orchestrator
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

    # Gate
    gate = Gate(llm, registry=registry)

    return gate, orchestrator, memory


# ── Single task runner ────────────────────────────────────────────────────

def run_task(task_desc: str, gate, orchestrator, memory, project_root: str) -> dict:
    """
    Run a single task through the full pipeline (gate -> orchestrator).
    Returns a result dict with success, expert_type, elapsed, output, files, error, ctx.
    """
    t0 = time.time()
    error = None
    ctx = None
    expert_type = "unknown"
    output = ""
    files_changed = []

    try:
        memory_context = memory.load(project_root)
        gate_result = gate.classify(task_desc, memory_context=memory_context)
        expert_type = gate_result.get("expert_type", "unknown")

        result = orchestrator.run(
            user_input=task_desc,
            gate_result=gate_result,
            project_root=project_root,
        )

        success = result.get("success", False)
        ctx = result.get("context")
        error = result.get("error")

        # Extract output text
        if ctx and ctx.generator_output:
            output = ctx.generator_output.get("explanation", "")
            patches = ctx.generator_output.get("patches", [])
            files_changed = [p.get("file", "") for p in patches if isinstance(p, dict)]

    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"
        logger.error("Task failed with exception:\n%s", traceback.format_exc())

    elapsed = time.time() - t0

    return {
        "success": success,
        "expert_type": expert_type,
        "elapsed": elapsed,
        "output": output,
        "files": files_changed,
        "error": error,
        "ctx": ctx,
    }


# ── Task definition ──────────────────────────────────────────────────────

@dataclass
class TaskDef:
    id: int
    group: int          # 1, 2, or 3
    task: str           # natural language task description
    category: str       # "fix", "codegen", "chat", "refactor", "doc"
    setup: Callable     # function(project_root) -> None, sets up files
    check: Callable     # function(project_root, result) -> (bool, str)


# ── Group runner ──────────────────────────────────────────────────────────

def run_group(tasks: list, ollama_model: str = DEFAULT_MODEL):
    """
    Run a list of TaskDef items. Each task gets its own temp directory.
    Prints a results table and returns list of (task_id, passed, reason, elapsed).
    """
    results = []

    # Header
    header = (
        f"{'ID':>{COL_ID}} | "
        f"{'Group':>{COL_GROUP}} | "
        f"{'Category':<{COL_CAT}} | "
        f"{'Pass?':<{COL_PASS}} | "
        f"{'Time':>{COL_TIME}} | "
        f"{'Reason':<{COL_REASON}}"
    )
    sep = "-" * len(header)
    print(f"\n{sep}")
    print(header)
    print(sep)

    for td in tasks:
        tid = td["id"] if isinstance(td, dict) else td.id
        tgroup = td["group"] if isinstance(td, dict) else td.group
        ttask = td["task"] if isinstance(td, dict) else td.task
        tcat = td["category"] if isinstance(td, dict) else td.category
        tsetup = td["setup"] if isinstance(td, dict) else td.setup
        tcheck = td["check"] if isinstance(td, dict) else td.check

        tmp_dir = tempfile.mkdtemp(prefix=f"e2e_task{tid}_")
        try:
            # Setup
            tsetup(tmp_dir)

            # Build pipeline fresh for each task
            gate, orchestrator, memory = build_pipeline(tmp_dir, ollama_model)

            # Run
            result = run_task(ttask, gate, orchestrator, memory, tmp_dir)

            # Check
            try:
                passed, reason = tcheck(tmp_dir, result)
            except Exception as e:
                passed = False
                reason = f"check() error: {e}"

            elapsed = result["elapsed"]
            results.append((tid, passed, reason, elapsed))

            # Print row
            pass_str = "PASS" if passed else "FAIL"
            reason_trunc = reason[:COL_REASON] if reason else ""
            print(
                f"{tid:>{COL_ID}} | "
                f"{tgroup:>{COL_GROUP}} | "
                f"{tcat:<{COL_CAT}} | "
                f"{pass_str:<{COL_PASS}} | "
                f"{elapsed:>{COL_TIME}.1f}s | "
                f"{reason_trunc:<{COL_REASON}}"
            )

        except Exception as e:
            results.append((tid, False, f"setup/run error: {e}", 0.0))
            print(
                f"{tid:>{COL_ID}} | "
                f"{tgroup:>{COL_GROUP}} | "
                f"{tcat:<{COL_CAT}} | "
                f"{'ERROR':<{COL_PASS}} | "
                f"{'0.0':>{COL_TIME}}s | "
                f"{str(e)[:COL_REASON]:<{COL_REASON}}"
            )

        finally:
            # Cleanup temp dir
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass

    # Summary
    total = len(results)
    passed_count = sum(1 for _, p, _, _ in results if p)
    total_time = sum(e for _, _, _, e in results)
    print(sep)
    print(f"Total: {passed_count}/{total} passed | {total_time:.1f}s elapsed")
    print(sep)

    return results


# ── Task registry (populated by second half of this file) ────────────────

ALL_TASKS: list = []

# Load task definitions from group files (dicts with keys: id, group, task, category, setup, check)
try:
    from offgrid.validation.e2e_tasks_group1 import GROUP1_TASKS
    ALL_TASKS.extend(GROUP1_TASKS)
except ImportError:
    pass
try:
    from offgrid.validation.e2e_tasks_group2 import GROUP2_TASKS
    ALL_TASKS.extend(GROUP2_TASKS)
except ImportError:
    pass
try:
    from offgrid.validation.e2e_tasks_group3 import GROUP3_TASKS
    ALL_TASKS.extend(GROUP3_TASKS)
except ImportError:
    pass


def _get(t, key):
    return t[key] if isinstance(t, dict) else getattr(t, key)


def _tasks_by_group(group: int) -> list:
    return [t for t in ALL_TASKS if _get(t, "group") == group]


def _task_by_id(task_id: int):
    for t in ALL_TASKS:
        if _get(t, "id") == task_id:
            return t
    return None


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="E2E 30-task validation for offgrid")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--group", default="all", help="Task group: 1, 2, 3, or 'all'")
    parser.add_argument("--task", type=str, default=None, help="Run single task by ID (e.g. T16)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.task is not None:
        td = _task_by_id(args.task)
        if td is None:
            print(f"Task ID {args.task} not found. Available: {[_get(t,'id') for t in ALL_TASKS]}")
            sys.exit(1)
        results = run_group([td], ollama_model=args.model)
    elif args.group == "all":
        results = run_group(ALL_TASKS, ollama_model=args.model)
    else:
        try:
            group_num = int(args.group)
        except ValueError:
            print(f"Invalid group: {args.group}. Use 1, 2, 3, or 'all'.")
            sys.exit(1)
        if group_num not in GROUPS:
            print(f"Invalid group: {group_num}. Use 1, 2, or 3.")
            sys.exit(1)
        tasks = _tasks_by_group(group_num)
        if not tasks:
            print(f"No tasks defined for group {group_num}.")
            sys.exit(1)
        results = run_group(tasks, ollama_model=args.model)

    # Exit code: 0 if all passed, 1 otherwise
    all_passed = all(p for _, p, _, _ in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
