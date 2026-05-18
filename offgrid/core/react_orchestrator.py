"""
ReAct Orchestrator: Multi-step reasoning + acting loop for complex tasks.

When the Gate detects a complex task (multi-file refactor, exploration-heavy
bug fix, or tasks requiring iterative discovery), the PipelineOrchestrator
delegates to this module instead of the fixed expert sequence.

The LLM autonomously decides: read file → analyze → write file → run test →
grep for references → ... → submit final solution. Each step produces a
real observation that feeds back into the next reasoning step.

Architecture fit:
- Sits alongside PipelineOrchestrator, not replacing it
- Gate routes: simple tasks → Pipeline, complex tasks → ReAct
- Reuses OffGrid's ToolExecutor via ReactToolAdapter
- Uses LLMBackend.chat() for multi-turn conversation
- Integrates with Checkpoint (save/restore), ValueTracker, TrajectoryCollector

Reference:
- ReAct paradigm: Yao et al., "ReAct: Synergizing Reasoning and Acting in
  Language Models", ICLR 2023. This is a well-known AI design pattern.
- Tool use patterns inspired by OpenAI function calling conventions.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from offgrid.core.context import TaskContext
from offgrid.core.react_tools import ReactToolAdapter
from offgrid.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


# ── Tool description for the LLM system prompt ──

TOOL_DESCRIPTIONS = """\
你可以使用以下工具来探索和修改代码。每次回复只能调用一个工具。

## 可用工具

### read_file
读取文件内容。
格式: <tool>read_file</tool><arg>文件路径</arg>

### write_file
写入完整文件内容（覆盖）。
格式: <tool>write_file</tool><arg>文件路径</arg>
<content>
完整文件内容
</content>

### run_test
运行项目测试，查看哪些通过哪些失败。
格式: <tool>run_test</tool>

### grep
在项目中搜索代码模式。
格式: <tool>grep</tool><arg>搜索模式</arg>

### list_dir
列出目录内容。
格式: <tool>list_dir</tool><arg>目录路径（可选，默认项目根目录）</arg>

### submit
提交最终方案，结束任务。确认所有修改已完成后调用。
格式: <tool>submit</tool>

## 重要规则
- 每次回复只调用一个工具
- 先读文件了解现状，再修改
- 修改后跑测试验证
- 不要修改测试文件
- 目标：完成用户要求的任务
"""


@dataclass
class ReactStep:
    """One step of ReAct interaction."""
    step_idx: int = 0
    thought: str = ""
    tool: str = ""
    tool_arg: str = ""
    tool_content: str = ""
    observation: str = ""
    elapsed_ms: float = 0.0


@dataclass
class ReactResult:
    """Final result of a ReAct loop run."""
    success: bool = False
    steps: list = field(default_factory=list)
    modified_files: dict = field(default_factory=dict)  # {path: content}
    tests_passed: int = 0
    tests_total: int = 0
    total_elapsed_s: float = 0.0
    submitted: bool = False


# ── Complexity signals for Gate routing ──
# These keywords suggest the task benefits from multi-step exploration.
_REACT_KEYWORDS = [
    "重构", "refactor", "rename", "重命名", "拆分", "split",
    "迁移到", "migrate", "升级", "upgrade",
    "找出所有", "find all", "搜索所有",
    "多文件", "multi-file",
    "逐步", "step by step",
]


class ReActOrchestrator:
    """
    Multi-step ReAct loop for complex tasks.

    Usage:
        react = ReActOrchestrator(llm, tool_executor, max_steps=10)
        result = react.run(ctx)
    """

    def __init__(
        self,
        llm,
        tool_executor: ToolExecutor,
        max_steps: int = 10,
        step_timeout: int = 120,
    ):
        self.llm = llm
        self.tools = ReactToolAdapter(tool_executor, tool_executor.project_root)
        self.max_steps = max_steps
        self.step_timeout = step_timeout

    @staticmethod
    def should_use_react(gate_result: dict, user_input: str) -> bool:
        """
        Determine if a task should use ReAct instead of the fixed pipeline.
        Called by the Gate or orchestrator to decide routing.

        Criteria:
        - Gate marks it as hard difficulty
        - User input contains complexity keywords
        - Subtask hints suggest multi-step work
        """
        difficulty = gate_result.get("difficulty", "easy")
        lower = user_input.lower()

        # Hard tasks with subtask hints → always ReAct
        if difficulty == "hard" and gate_result.get("subtask_hint"):
            return True

        # Hard tasks with complexity keywords → ReAct
        if difficulty == "hard" and any(kw in lower for kw in _REACT_KEYWORDS):
            return True

        # Explicit multi-step keywords even on easy tasks
        multi_step_signals = ["重构", "refactor", "rename", "重命名", "迁移", "migrate"]
        if any(kw in lower for kw in multi_step_signals):
            return True

        return False

    def run(
        self,
        ctx: TaskContext,
        on_status=None,
    ) -> ReactResult:
        """
        Execute the ReAct loop.

        Args:
            ctx: TaskContext with user_input, project_root, gate_result, etc.
            on_status: Optional callback(stage, detail) for progress display.

        Returns:
            ReactResult with final state.
        """
        t0 = time.time()
        result = ReactResult()

        # Build conversation
        system = self._build_system_prompt(ctx)
        initial_msg = self._build_initial_message(ctx)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": initial_msg},
        ]

        self._emit(on_status, "react_start", f"ReAct模式启动 (最大{self.max_steps}步)")

        for step_idx in range(self.max_steps):
            step = ReactStep(step_idx=step_idx)
            step_t0 = time.time()

            # Determine token budget based on model size
            is_small = self._is_small_model()
            max_tokens = 2048 if is_small else 4096

            # Call LLM
            try:
                response = self.llm.chat(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
            except Exception as e:
                logger.error("[react] LLM call failed at step %d: %s", step_idx, e)
                step.observation = f"[LLM_ERROR] {e}"
                result.steps.append(step)
                break

            if not response or response.startswith("[LLM_ERROR]"):
                logger.warning("[react] LLM returned error at step %d: %s", step_idx, response)
                step.observation = response or "[ERROR] LLM返回空"
                result.steps.append(step)
                break

            # Parse thought + tool call
            step.thought, step.tool, step.tool_arg, step.tool_content = self._parse_response(response)

            logger.info(
                "[react] step %d: tool=%s arg=%s thought=%s",
                step_idx, step.tool, step.tool_arg[:80] if step.tool_arg else "",
                step.thought[:80] if step.thought else "",
            )

            # Handle submit
            if step.tool == "submit":
                step.observation = "[SUBMIT] 方案已提交。"
                step.elapsed_ms = (time.time() - step_t0) * 1000
                result.steps.append(step)
                result.success = True
                result.submitted = True
                self._emit(on_status, "react_submit", f"ReAct完成于第{step_idx + 1}步")
                break

            # Execute tool
            if step.tool in self.tools.AVAILABLE_TOOLS:
                step.observation = self.tools.execute(
                    step.tool, step.tool_arg, step.tool_content
                )
                # Track write_file modifications
                if step.tool == "write_file" and step.observation.startswith("[OK]"):
                    result.modified_files[step.tool_arg] = step.tool_content
                # Track test results
                if step.tool == "run_test":
                    passed, total = ReactToolAdapter._parse_pytest_counts(step.observation)
                    result.tests_passed = passed
                    result.tests_total = total
            else:
                # Unrecognized tool or LLM didn't call a tool
                if not step.tool:
                    step.observation = (
                        "请调用一个工具来继续。"
                        f"可用工具: {', '.join(self.tools.AVAILABLE_TOOLS)}"
                    )
                else:
                    step.observation = (
                        f"未识别的工具: {step.tool}。"
                        f"可用工具: {', '.join(self.tools.AVAILABLE_TOOLS)}"
                    )

            step.elapsed_ms = (time.time() - step_t0) * 1000
            result.steps.append(step)

            self._emit(
                on_status, "react_step",
                f"Step {step_idx + 1}/{self.max_steps}: "
                f"{step.tool or 'no_tool'} ({step.elapsed_ms:.0f}ms)"
            )

            # Add to conversation history
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"[观察结果]\n{step.observation}"})

            # Compress history if too long
            messages = self._maybe_compress_history(messages)

        # If no explicit submit but files were modified, run final test
        if not result.submitted and result.modified_files:
            self._emit(on_status, "react_final_test", "最终验证...")
            test_obs = self.tools.execute("run_test")
            passed, total = ReactToolAdapter._parse_pytest_counts(test_obs)
            result.tests_passed = passed
            result.tests_total = total
            # If all tests pass, count as success
            if total > 0 and passed == total:
                result.success = True

        result.total_elapsed_s = time.time() - t0

        logger.info(
            "[react] completed: %d steps, %d files modified, %d/%d tests, %.1fs, success=%s",
            len(result.steps), len(result.modified_files),
            result.tests_passed, result.tests_total,
            result.total_elapsed_s, result.success,
        )

        return result

    # ── Prompt Construction ──

    def _build_system_prompt(self, ctx: TaskContext) -> str:
        """Build system prompt with tool descriptions and project context."""
        parts = [
            "你是一个代码修复Agent。你的任务是通过多轮交互完成用户的代码任务。",
            "",
            TOOL_DESCRIPTIONS,
            "",
            "## 工作流程建议",
            "1. 先 read_file 查看相关文件，了解现状",
            "2. 分析问题",
            "3. write_file 修改代码",
            "4. run_test 验证修改",
            "5. 如果还有问题，继续分析和修复",
            "6. 全部完成后 submit",
            "",
            f"## 项目根目录: {ctx.project_root}",
        ]

        # Inject OFFGRID.md rules if available
        if ctx.offgrid_rules:
            parts.append(f"\n## 项目规则\n{ctx.offgrid_rules}")

        # Inject expert system prompt if available (domain knowledge)
        if ctx.expert_system_prompt:
            parts.append(f"\n## 领域知识\n{ctx.expert_system_prompt}")

        # Inject locator results if available (pre-identified files)
        if ctx.locator_output:
            files = ctx.locator_output.get("relevant_files", [])
            funcs = ctx.locator_output.get("relevant_functions", [])
            if files:
                parts.append(f"\n## 已定位的相关文件: {', '.join(files[:5])}")
            if funcs:
                parts.append(f"## 已定位的相关函数: {', '.join(funcs[:5])}")

        return "\n".join(parts)

    def _build_initial_message(self, ctx: TaskContext) -> str:
        """Build initial user message with task description and context."""
        parts = [f"## 任务\n{ctx.user_input}"]

        # Inject subtask hints from Gate if available
        subtask_hint = ctx.gate_result.get("subtask_hint", "")
        if subtask_hint:
            parts.append(f"\n## 子任务提示\n{subtask_hint}")

        # Inject relevant code snippets from Locator if available
        if ctx.relevant_code_snippets:
            parts.append("\n## 已定位的代码片段")
            for path, snippet in list(ctx.relevant_code_snippets.items())[:3]:
                # Truncate each snippet
                if len(snippet) > 1000:
                    snippet = snippet[:1000] + "\n... (截断)"
                parts.append(f"\n### {path}\n```\n{snippet}\n```")

        # Inject search results if available
        if ctx.search_results:
            parts.append(f"\n## 参考信息\n{ctx.search_results[:1500]}")

        # Inject previous failure info for retry context
        if ctx.previous_failure:
            parts.append(f"\n## 上次尝试失败原因\n{ctx.previous_failure[:500]}")

        # Inject reflection if available
        if ctx.reflection:
            parts.append(f"\n## 失败分析\n{ctx.reflection}")

        # Inject debug info if available
        if ctx.debug_info:
            parts.append(f"\n## 调试信息\n{ctx.debug_info[:500]}")

        parts.append("\n请开始工作。先读取相关文件了解现状。")
        return "\n".join(parts)

    # ── Response Parsing ──

    def _parse_response(self, response: str) -> tuple[str, str, str, str]:
        """
        Parse LLM response to extract thought and tool call.

        Format expected:
            <thinking>reasoning text</thinking>
            <tool>tool_name</tool><arg>argument</arg>
            <content>file content (for write_file only)</content>

        Also handles simpler format without <thinking> tags:
            reasoning text
            <tool>tool_name</tool><arg>argument</arg>

        Returns: (thought, tool_name, tool_arg, tool_content)
        """
        # Extract tool call
        tool_match = re.search(r"<tool>(.*?)</tool>", response, re.DOTALL)
        arg_match = re.search(r"<arg>(.*?)</arg>", response, re.DOTALL)
        content_match = re.search(r"<content>\n?(.*?)</content>", response, re.DOTALL)

        tool = tool_match.group(1).strip() if tool_match else ""
        tool_arg = arg_match.group(1).strip() if arg_match else ""
        tool_content = content_match.group(1) if content_match else ""

        # Thought is everything before the tool tag
        if tool_match:
            thought = response[:tool_match.start()].strip()
        else:
            thought = response.strip()

        # Clean up thinking tags if present
        thought = re.sub(r"<thinking>.*?</thinking>", "", thought, flags=re.DOTALL).strip()

        return thought, tool, tool_arg, tool_content

    # ── Helpers ──

    def _is_small_model(self) -> bool:
        """Detect if the model is small (≤8B parameters)."""
        model_name = getattr(self.llm, "ollama_model", "").lower()
        return any(s in model_name for s in ("1b", "3b", "4b", "7b", "8b"))

    def _maybe_compress_history(self, messages: list[dict]) -> list[dict]:
        """
        Compress conversation history if too long.
        Keeps: system + initial user + recent N turns.
        """
        # system(1) + initial_user(1) + pairs(assistant+user) = 2 + 2*N
        max_messages = 14  # Keep recent 6 turns = 12 messages + 2 header
        if len(messages) <= max_messages:
            return messages

        head = messages[:2]  # system + initial user
        tail = messages[-(max_messages - 2):]  # recent interactions

        # Insert compression summary
        compressed_count = len(messages) - max_messages
        summary = (
            f"[前{compressed_count // 2}步已压缩。"
            f"你已经读取了文件并进行了一些修改。"
            f"请继续基于最近的观察结果工作。]"
        )
        head.append({"role": "user", "content": summary})

        return head + tail

    @staticmethod
    def _emit(callback, stage: str, detail: str):
        """Emit status update if callback provided."""
        if callback:
            callback(stage, detail)
        logger.info("[%s] %s", stage, detail)
