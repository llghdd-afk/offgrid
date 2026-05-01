"""
Expert generator: creates expert YAML drafts from trajectory patterns using LLM.
"""

import json
import logging
from dataclasses import asdict

from offgrid.flywheel.trajectory_collector import TaskTrajectory

logger = logging.getLogger(__name__)

EXPERT_GENERATION_PROMPT = """你是专家设计师。分析以下{count}个成功任务的执行轨迹，提取共性模式，生成一个专家定义。

任务轨迹：
{trajectories}

要求：
1. 分析这些任务的共同特征（触发条件、操作模式、成功策略）
2. 生成一个针对这类任务的专家
3. system_prompt必须具体，包含这类任务的最佳实践
4. trigger_keywords必须精准，避免与其他专家冲突
5. 只输出JSON，不要解释

输出格式：
{{
  "name": "XxxExpert",
  "trigger_keywords": [...],
  "trigger_min_confidence": 0.85,
  "system_prompt": "...",
  "tool_whitelist": [...],
  "pipeline": [...]
}}"""


class ExpertGeneratorFlywheel:
    """Generates expert drafts from trajectory patterns using LLM."""

    def __init__(self, llm):
        self.llm = llm

    def generate(self, pattern: dict) -> dict | None:
        """
        Generate an expert definition from a detected pattern.
        Returns parsed expert dict or None on failure.
        """
        trajs: list[TaskTrajectory] = pattern["trajectories"]
        count = pattern["count"]

        # Build condensed trajectory summaries (avoid token bloat)
        summaries = []
        for t in trajs[:10]:  # Cap at 10 to stay within context
            summaries.append({
                "user_input": t.user_input[:200],
                "expert_type": t.expert_used,
                "pipeline": t.pipeline_steps,
                "files_modified": t.files_modified[:5],
                "latency_s": t.latency_s,
                "search_triggered": t.search_triggered,
            })

        prompt = EXPERT_GENERATION_PROMPT.format(
            count=count,
            trajectories=json.dumps(summaries, ensure_ascii=False, indent=2),
        )

        try:
            raw = self.llm.generate(
                prompt=prompt,
                system="你是Kaiwu专家系统的设计师。只输出合法JSON。",
                max_tokens=2048,
                temperature=0.3,
            )
            return self._parse_expert(raw, pattern)
        except Exception as e:
            logger.error("Expert generation LLM call failed: %s", e)
            return None

    def _parse_expert(self, raw: str, pattern: dict) -> dict | None:
        """Parse LLM output into a validated expert dict."""
        # Extract JSON from possible markdown fences
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Drop first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            expert = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse expert JSON: %s\nRaw: %s", e, raw[:500])
            return None

        # Validate required fields
        required = {"name", "trigger_keywords", "trigger_min_confidence", "system_prompt", "pipeline"}
        missing = required - set(expert.keys())
        if missing:
            logger.warning("Generated expert missing fields: %s", missing)
            return None

        # Validate pipeline steps
        valid_steps = {"locator", "generator", "verifier"}
        for step in expert["pipeline"]:
            if step not in valid_steps:
                logger.warning("Invalid pipeline step in generated expert: %s", step)
                return None

        # Add metadata
        expert.setdefault("version", "1.0")
        expert.setdefault("type", pattern["expert_type"])
        expert.setdefault("lifecycle", "new")
        expert.setdefault("performance", {"success_rate": 0.0, "avg_latency_s": 0, "task_count": 0})
        expert["_source"] = "flywheel"

        return expert
