"""
Reviewer expert: 需求对齐验证（第二层回检）。
验证 Generator 输出是否真正满足用户意图，而不只是"能跑通"。

元专家体系第5个原子能力：
  Locator（定位）→ Generator（生成）→ Verifier（测试）→ Debugger（调试）→ Reviewer（审查）

Reviewer 在 Verifier 通过后执行，用 LLM 对比：
  - 用户原始意图
  - 实际代码变更
判断是否对齐，输出 {aligned: bool, gap: str}
"""

import json
import logging
import re
from typing import Optional

from offgrid.core.context import TaskContext
from offgrid.llm.llama_backend import LLMBackend

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """你是代码审查专家。判断以下代码修改是否真正满足了用户的需求。

## 用户需求
{user_input}

## 实际代码变更
{changes}

## 判断标准
1. 修改是否解决了用户描述的核心问题？
2. 是否有遗漏（用户要求了但没做的）？
3. 是否有多余（用户没要求但做了的，可能引入风险）？

## 输出格式（JSON，不要解释）
{{"aligned": true/false, "confidence": 0.0-1.0, "gap": "如果不对齐，说明差距是什么（一句话）"}}"""


class ReviewerExpert:
    """
    需求对齐审查。Verifier 通过后执行。
    用 LLM 对比用户意图和实际变更，判断是否真正完成了任务。
    非阻塞：审查失败不回滚，只记录 gap 供用户参考。
    """

    def __init__(self, llm: LLMBackend):
        self.llm = llm

    def review(self, ctx: TaskContext) -> dict:
        """
        审查 Generator 输出是否对齐用户需求。
        返回 {"aligned": bool, "confidence": float, "gap": str}
        失败时返回 {"aligned": True, "confidence": 0.0, "gap": ""} (乐观降级)
        """
        try:
            # 提取变更摘要
            changes = self._extract_changes(ctx)
            if not changes:
                return {"aligned": True, "confidence": 0.0, "gap": ""}

            # LLM 审查
            prompt = REVIEW_PROMPT.format(
                user_input=ctx.user_input[:200],
                changes=changes[:800],
            )

            response = self.llm.generate(
                prompt=prompt,
                system="你是代码审查专家，只输出JSON判断，不要解释。",
                max_tokens=150,
                temperature=0.0,
            )

            # 解析结果
            return self._parse_response(response)

        except Exception as e:
            logger.warning("[reviewer] review failed: %s", e)
            return {"aligned": True, "confidence": 0.0, "gap": ""}

    @staticmethod
    def _extract_changes(ctx: TaskContext) -> str:
        """从 ctx 提取代码变更摘要。"""
        if not ctx.generator_output:
            return ""

        parts = []
        patches = ctx.generator_output.get("patches", [])
        for patch in patches[:3]:  # 最多看3个文件
            file_path = patch.get("file", "unknown")
            modified = patch.get("modified", "")[:300]
            original = patch.get("original", "")[:200]
            if modified:
                parts.append(f"文件: {file_path}\n修改后:\n{modified}")
                if original:
                    parts.append(f"修改前:\n{original}")

        explanation = ctx.generator_output.get("explanation", "")
        if explanation:
            parts.append(f"说明: {explanation[:200]}")

        return "\n\n".join(parts)

    @staticmethod
    def _parse_response(response: str) -> dict:
        """解析 LLM 的 JSON 审查结果。"""
        # 提取 JSON
        json_match = re.search(r'\{[^}]+\}', response)
        if not json_match:
            return {"aligned": True, "confidence": 0.0, "gap": ""}

        try:
            result = json.loads(json_match.group())
            return {
                "aligned": bool(result.get("aligned", True)),
                "confidence": float(result.get("confidence", 0.0)),
                "gap": str(result.get("gap", ""))[:100],
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            return {"aligned": True, "confidence": 0.0, "gap": ""}
