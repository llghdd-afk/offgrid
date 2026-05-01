"""
ContextCompressor: 一次 LLM 调用，将多页面正文压缩为 ≤400 字摘要注入 context。
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from offgrid.llm.llama_backend import LLMBackend

logger = logging.getLogger(__name__)

COMPRESS_PROMPT = """你是信息提炼专家。从搜索结果中提取对解决任务最有用的信息。

当前任务：{task}

搜索内容：
{search_results}

要求：
1. 只保留和任务直接相关的信息
2. 输出不超过400字
3. 保留具体代码片段、函数名、配置项、版本号等关键细节
4. 用中文总结，保留英文技术术语
5. 直接输出文字，不要加标题"""


class ContextCompressor:
    def __init__(self, llm: "LLMBackend"):
        self.llm = llm

    def compress(self, task: str, contents: list[str]) -> str:
        """
        将多个页面正文压缩为一段摘要。
        ≤500字直接截断返回，省掉一次 LLM 调用。
        """
        valid = [c for c in contents if c and c.strip()]
        if not valid:
            return ""

        combined = "\n\n".join(valid)

        # 内容够短，直接截断返回，不浪费 LLM 调用
        if len(combined) <= 500:
            return combined[:400]

        # 内容多才调 LLM 压缩
        prompt = COMPRESS_PROMPT.format(
            task=task,
            search_results=combined[:3000],
        )

        try:
            result = self.llm.generate(prompt=prompt, max_tokens=600, temperature=0.0)
            result = result.strip()
            # 硬截断：LLM 可能超出 400 字限制
            if len(result) > 400:
                result = result[:400]
            return result
        except Exception as e:
            logger.warning("[compressor] LLM failed: %s, returning raw", e)
            return combined[:400]
