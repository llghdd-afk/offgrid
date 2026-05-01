"""
Execution Trace: 结构化执行可观测性。
记录每个任务的完整执行链路（每步耗时、token、结果），任务完成后输出摘要。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """单步执行记录。"""
    name: str
    started_at: float = 0.0
    ended_at: float = 0.0
    success: bool = True
    detail: str = ""

    @property
    def elapsed_ms(self) -> float:
        return (self.ended_at - self.started_at) * 1000


@dataclass
class ExecutionTrace:
    """一次任务的完整执行轨迹。"""
    task_input: str = ""
    steps: list[TraceStep] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    llm_calls: int = 0
    retries: int = 0
    success: bool = False
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def elapsed_s(self) -> float:
        return self.ended_at - self.started_at

    def begin(self, task_input: str):
        """开始追踪。"""
        self.task_input = task_input[:100]
        self.started_at = time.time()

    def step_start(self, name: str) -> TraceStep:
        """记录一步开始。"""
        step = TraceStep(name=name, started_at=time.time())
        self.steps.append(step)
        return step

    def step_end(self, step: TraceStep, success: bool = True, detail: str = ""):
        """记录一步结束。"""
        step.ended_at = time.time()
        step.success = success
        step.detail = detail[:100]

    def finish(self, success: bool, llm_usage: Optional[dict] = None):
        """结束追踪，记录最终状态。"""
        self.ended_at = time.time()
        self.success = success
        if llm_usage:
            self.total_input_tokens = llm_usage.get("input_tokens", 0)
            self.total_output_tokens = llm_usage.get("output_tokens", 0)
            self.llm_calls = llm_usage.get("call_count", 0)

    def summary(self) -> str:
        """生成人类可读的执行摘要。"""
        lines = []
        status = "成功" if self.success else "失败"
        lines.append(f"[{status}] {self.task_input} ({self.elapsed_s:.1f}s)")

        if self.llm_calls > 0:
            total_tokens = self.total_input_tokens + self.total_output_tokens
            lines.append(f"  LLM: {self.llm_calls}次调用, {total_tokens} tokens")

        if self.retries > 0:
            lines.append(f"  重试: {self.retries}次")

        # 每步耗时
        for step in self.steps:
            icon = "+" if step.success else "x"
            lines.append(f"  {icon} {step.name}: {step.elapsed_ms:.0f}ms")
            if step.detail and not step.success:
                lines.append(f"    {step.detail}")

        return "\n".join(lines)
