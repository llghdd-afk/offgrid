"""
Verifier expert: validates Generator patches via syntax check + test execution.
RED-2: Deterministic verification sequence (syntax → apply → test).
RED-3: Independent context window, does not inherit Generator history.
"""

import json
import logging
from typing import Optional

from offgrid.core.context import TaskContext
from offgrid.llm.llama_backend import LLMBackend
from offgrid.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


class VerifierExpert:
    """Deterministic verification: syntax check → apply patch → run tests."""

    def __init__(self, llm: LLMBackend, tool_executor: ToolExecutor):
        self.llm = llm
        self.tools = tool_executor

    def run(self, ctx: TaskContext) -> Optional[dict]:
        """
        Verify Generator output. Fixed sequence:
        1. Syntax check (python -m py_compile)
        2. Apply patches (write_file)
        3. Run existing tests (pytest, if available)
        4. Return structured result
        """
        gen_output = ctx.generator_output
        if not gen_output or not gen_output.get("patches"):
            result = {
                "passed": False,
                "syntax_ok": False,
                "tests_passed": 0,
                "tests_total": 0,
                "error_detail": "No patches to verify",
            }
            ctx.verifier_output = result
            return result

        patches = gen_output["patches"]

        # Step 1: Backup original files
        backups = {}
        for patch in patches:
            fpath = patch["file"]
            original_content = self.tools.read_file(fpath)
            if not original_content.startswith("[ERROR]"):
                backups[fpath] = original_content

        # Step 2: Apply patches (exact match — original is read from file, not LLM)
        apply_ok = True
        applied_files = []
        for patch in patches:
            fpath = patch["file"]
            original = patch.get("original", "")
            modified = patch.get("modified", "")

            if original and modified:
                success = self.tools.apply_patch(fpath, original, modified)
            elif modified:
                success = self.tools.write_file(fpath, modified)
            else:
                success = False

            if success:
                applied_files.append(fpath)
            else:
                apply_ok = False
                logger.warning("Patch apply failed for %s", fpath)

        if not apply_ok and not applied_files:
            self._rollback(backups)
            result = {
                "passed": False,
                "syntax_ok": False,
                "tests_passed": 0,
                "tests_total": 0,
                "error_detail": "All patches failed to apply",
            }
            ctx.verifier_output = result
            return result

        # Step 3: Syntax check on modified Python files
        syntax_ok = True
        syntax_errors = []
        for fpath in applied_files:
            if fpath.endswith(".py"):
                _, stderr, rc = self.tools.run_bash(
                    f'python -m py_compile "{fpath}"',
                    cwd=ctx.project_root,
                )
                if rc != 0:
                    syntax_ok = False
                    syntax_errors.append(f"{fpath}: {stderr.strip()}")

        if not syntax_ok:
            self._rollback(backups)
            result = {
                "passed": False,
                "syntax_ok": False,
                "tests_passed": 0,
                "tests_total": 0,
                "error_detail": f"Syntax errors: {'; '.join(syntax_errors)}",
            }
            ctx.verifier_output = result
            return result

        # Step 4: Run tests (if test infrastructure exists)
        tests_passed, tests_total, test_error = self._run_tests(ctx)

        # Determine pass/fail
        passed = syntax_ok
        if tests_total > 0:
            passed = passed and (tests_passed == tests_total)

        if not passed:
            self._rollback(backups)

        result = {
            "passed": passed,
            "syntax_ok": syntax_ok,
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "error_detail": test_error if not passed else "",
        }
        ctx.verifier_output = result
        return result

    def _run_tests(self, ctx: TaskContext) -> tuple[int, int, str]:
        """Run project tests. Returns (passed, total, error_detail)."""
        # Try to detect test runner
        test_commands = [
            ("pytest", "python -m pytest tests/ --tb=short -q"),
            ("unittest", "python -m unittest discover -s tests -q"),
        ]

        # Check if pytest is available
        _, _, rc = self.tools.run_bash("python -m pytest --version", cwd=ctx.project_root)
        if rc != 0:
            # No pytest, try unittest
            test_commands = test_commands[1:]

        # Check if tests directory exists
        test_dirs = self.tools.list_dir(ctx.project_root)
        # list_dir returns ["[ERROR] ..."] on failure — treat as no tests
        has_tests = any(d in ("tests", "test") for d in test_dirs if not d.startswith("[ERROR]"))
        if not has_tests:
            return 0, 0, ""  # No tests to run

        for name, cmd in test_commands:
            stdout, stderr, rc = self.tools.run_bash(cmd, cwd=ctx.project_root, timeout=120)
            if rc == 0:
                passed, total = self._parse_test_output(stdout + stderr)
                return passed, total, ""
            else:
                # Parse partial results
                passed, total = self._parse_test_output(stdout + stderr)
                error = stderr.strip() or stdout.strip()
                return passed, total, error[:500]

        return 0, 0, ""

    @staticmethod
    def _parse_test_output(output: str) -> tuple[int, int]:
        """Parse test counts from pytest/unittest output."""
        import re

        # pytest format: "5 passed" or "3 passed, 2 failed"
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        error_match = re.search(r"(\d+) error", output)

        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0
        total = passed + failed + errors

        if total == 0:
            # unittest format: "Ran 5 tests"
            ran_match = re.search(r"Ran (\d+) test", output)
            if ran_match:
                total = int(ran_match.group(1))
                if "OK" in output:
                    passed = total
                else:
                    # Try to find failures
                    fail_match = re.search(r"failures=(\d+)", output)
                    err_match = re.search(r"errors=(\d+)", output)
                    f = int(fail_match.group(1)) if fail_match else 0
                    e = int(err_match.group(1)) if err_match else 0
                    passed = total - f - e

        return passed, total

    def _rollback(self, backups: dict[str, str]):
        """Restore original file contents."""
        for fpath, content in backups.items():
            self.tools.write_file(fpath, content)
            logger.info("Rolled back %s", fpath)
