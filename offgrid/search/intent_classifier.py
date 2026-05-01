"""
意图分类器：关键词快速匹配 + LLM 语义 fallback。
将用户输入分类为 code_search / academic / package / debug / general。

v0.6.2: 增强关键词覆盖 + LLM fallback 分类（零外部API）。
"""

import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from offgrid.llm.llama_backend import LLMBackend

logger = logging.getLogger(__name__)

# 关键词 → 意图映射（优先级从上到下，首次命中即返回）
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("debug", [
        "报错", "error", "bug", "fix", "失败", "异常", "traceback",
        "crash", "segfault", "panic", "exception", "stack trace",
        "不工作", "出错", "修复", "解决",
    ]),
    ("code_search", [
        "开源", "github", "仓库", "repo", "star", "框架推荐",
        "最佳实践", "best practice", "实现方案", "怎么实现",
        "有没有库", "有没有工具", "推荐一个", "哪个框架",
        "源码", "source code", "示例代码", "example",
        "最优解", "算法实现", "设计模式",
    ]),
    ("academic", [
        "论文", "paper", "arxiv", "研究", "survey",
        "算法原理", "理论", "证明", "公式",
        "state of the art", "sota", "benchmark",
        "学术", "文献", "引用", "citation",
    ]),
    ("package", [
        "库", "package", "pip", "安装", "依赖",
        "npm", "cargo", "gem", "maven",
        "版本", "version", "兼容", "compatible",
        "pip install", "requirements",
    ]),
]

# 预编译正则
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    (intent, re.compile("|".join(re.escape(kw) for kw in keywords), re.IGNORECASE))
    for intent, keywords in _INTENT_KEYWORDS
]

# LLM 分类 prompt
_LLM_CLASSIFY_PROMPT = """你是搜索意图分类器。根据用户问题，判断应该搜索什么类型的数据源。

分类选项：
- code_search：找代码实现、开源项目、最佳实践、框架对比
- academic：找论文、算法原理、学术研究、理论证明
- package：找软件包、库、依赖、安装方法
- debug：修bug、解决报错、排查问题
- general：通用问题、天气、新闻、其他

用户问题：{query}

只返回一个分类名称，不要解释。"""


def classify(user_input: str, task_summary: str = "", llm: Optional["LLMBackend"] = None) -> str:
    """
    对用户输入做意图分类。

    流程：
      1. 关键词快速匹配（<1ms）→ 命中直接返回
      2. LLM fallback（如果提供了 llm 参数）

    Returns:
        "code_search" | "academic" | "package" | "debug" | "general"
    """
    combined = f"{user_input} {task_summary}"

    # Level 1: 关键词快速匹配
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(combined):
            logger.debug("[intent] keyword match: %s", intent)
            return intent

    # Level 2: LLM 语义分类（可选）
    if llm:
        result = _llm_classify(user_input, llm)
        if result:
            return result

    return "general"


def _llm_classify(user_input: str, llm: "LLMBackend") -> Optional[str]:
    """LLM 语义分类 fallback。失败返回 None。"""
    VALID_INTENTS = {"code_search", "academic", "package", "debug", "general"}
    try:
        prompt = _LLM_CLASSIFY_PROMPT.format(query=user_input[:200])
        raw = llm.generate(prompt=prompt, max_tokens=20, temperature=0.0)
        result = raw.strip().lower().replace('"', '').replace("'", "")
        # 提取有效意图
        for intent in VALID_INTENTS:
            if intent in result:
                logger.debug("[intent] LLM classified: %s", intent)
                return intent
    except Exception as e:
        logger.debug("[intent] LLM classify failed: %s", e)
    return None
