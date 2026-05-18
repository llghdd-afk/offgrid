"""
ReAct Tools: Adapter layer between ReAct loop and OffGrid's ToolExecutor.

Provides a clean tool interface for the ReAct orchestrator, wrapping
OffGrid's existing ToolExecutor with ReAct-specific safety checks
and output formatting.

Design rationale:
- ReAct loop needs tools that return string observations (not bools/tuples)
- Safety guardrails from ToolExecutor are preserved
- AST syntax check on write_file (Python files only)
- Test file write protection
- File read truncation for context management

Reference:
- ReAct paradigm: Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", ICLR 2023
"""

import ast
import logging
import os
import re

from offgrid.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


class ReactToolAdapter:
    """
    Wraps ToolExecutor for ReAct loop consumption.
    Each tool returns a string observation that goes back to the LLM.
    """

    # Tools available to the ReAct agent
    AVAILABLE_TOOLS = ("read_file", "write_file", "run_test", "grep", "list_dir", "submit")

    def __init__(self, executor: ToolExecutor, project_root: str):
        self.executor = executor
        self.project_root = os.path.abspath(project_root)

    def execute(self, tool_name: str, arg: str = "", content: str = "") -> str:
        """Dispatch tool call. Returns observation string."""
        if tool_name == "read_file":
            return self._read_file(arg)
        elif tool_name == "write_file":
            return self._write_file(arg, content)
        elif tool_name == "run_test":
            return self._run_test()
        elif tool_name == "grep":
            return self._grep(arg)
        elif tool_name == "list_dir":
            return self._list_dir(arg)
        elif tool_name == "submit":
            return "[SUBMIT] 方案已提交。"
        else:
            return f"[ERROR] 未知工具: {tool_name}。可用工具: {', '.join(self.AVAILABLE_TOOLS)}"

    def _read_file(self, path: str) -> str:
        """Read file with truncation for large files."""
        if not path:
            return "[ERROR] 请提供文件路径。格式: <tool>read_file</tool><arg>path/to/file</arg>"
        content = self.executor.read_file(path)
        if content.startswith("[ERROR]"):
            return content
        # Truncate large files to keep context manageable
        lines = content.split("\n")
        if len(lines) > 300:
            return "\n".join(lines[:300]) + f"\n\n... (文件共{len(lines)}行，已截断前300行)"
        return content

    def _write_file(self, path: str, content: str) -> str:
        """Write file with safety checks."""
        if not path or not content:
            return "[ERROR] 请提供文件路径和内容。格式: <tool>write_file</tool><arg>path</arg><content>完整内容</content>"

        # Safety: block test file modification
        norm_path = path.lower().replace("\\", "/")
        if "test" in norm_path and norm_path.endswith(".py"):
            return f"[BLOCKED] 禁止修改测试文件: {path}"

        # Safety: Python syntax check
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as e:
                return f"[ERROR] Python语法错误: {e}"

        # Safety: confine writes to project root
        full = self.executor._resolve(path)
        if not full.startswith(self.project_root):
            return f"[BLOCKED] 禁止写入项目目录外: {path}"

        ok = self.executor.write_file(path, content)
        if ok:
            return f"[OK] 已写入 {path} ({len(content)} bytes, {content.count(chr(10)) + 1} lines)"
        return f"[ERROR] 写入失败: {path}"

    def _run_test(self) -> str:
        """Run pytest and return formatted results."""
        stdout, stderr, rc = self.executor.run_bash(
            "python -m pytest --tb=short -q 2>&1",
            cwd=self.project_root,
            timeout=120,
        )
        output = stdout or stderr
        if not output:
            return "[INFO] 无测试输出"

        # Parse pytest summary line
        passed, total = self._parse_pytest_counts(output)
        summary = f"测试结果: {passed}/{total} 通过"
        if passed == total and total > 0:
            summary += " (全部通过!)"

        # Truncate verbose output
        if len(output) > 2000:
            # Keep the summary line (usually at the end) and truncate the middle
            lines = output.strip().split("\n")
            tail = "\n".join(lines[-10:])
            output = output[:1500] + f"\n... (截断)\n{tail}"

        return f"{summary}\n\n{output}"

    def _grep(self, pattern: str) -> str:
        """Search code in project."""
        if not pattern:
            return "[ERROR] 请提供搜索模式。格式: <tool>grep</tool><arg>搜索关键词</arg>"
        stdout, stderr, rc = self.executor.run_bash(
            f'grep -rn "{pattern}" --include="*.py" --include="*.ts" --include="*.js" --include="*.go" --include="*.java" .',
            cwd=self.project_root,
            timeout=10,
        )
        if stdout:
            lines = stdout.strip().split("\n")
            if len(lines) > 30:
                return "\n".join(lines[:30]) + f"\n... (共{len(lines)}个匹配，显示前30个)"
            return stdout.strip()
        return f"未找到匹配: {pattern}"

    def _list_dir(self, path: str) -> str:
        """List directory contents."""
        target = path if path else "."
        entries = self.executor.list_dir(target)
        if isinstance(entries, list):
            if entries and entries[0].startswith("[ERROR]"):
                return entries[0]
            return "\n".join(entries[:50])
        return str(entries)

    @staticmethod
    def _parse_pytest_counts(output: str) -> tuple[int, int]:
        """Parse pytest pass/total from output."""
        # Match "X passed, Y failed" or "X passed"
        passed_m = re.search(r"(\d+)\s*passed", output)
        failed_m = re.search(r"(\d+)\s*failed", output)
        error_m = re.search(r"(\d+)\s*error", output)
        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        errors = int(error_m.group(1)) if error_m else 0
        total = passed + failed + errors
        return passed, total
