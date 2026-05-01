"""
AST 辅助工具：从 Python 文件中提取函数/类定义列表。
给 Locator 提供候选列表，LLM 只需从中选择，不需要自己找。
"""

import ast
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_symbols(source: str, language: str = "python") -> list[dict]:
    """
    从源代码提取所有函数/类定义。
    返回 [{"name": "func_name", "type": "function"|"class"|"method", "line": 10}, ...]
    """
    if language == "python":
        return _extract_python(source)
    # 非 Python 文件用 regex 降级
    return _extract_regex(source)


def _extract_python(source: str) -> list[dict]:
    """用 AST 精确提取 Python 函数/类。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        logger.warning("[ast] SyntaxError, falling back to regex")
        return _extract_regex(source)

    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            symbols.append({
                "name": node.name,
                "type": "function",
                "line": node.lineno,
            })
        elif isinstance(node, ast.ClassDef):
            symbols.append({
                "name": node.name,
                "type": "class",
                "line": node.lineno,
            })
            # 提取类方法
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append({
                        "name": f"{node.name}.{item.name}",
                        "type": "method",
                        "line": item.lineno,
                    })
    return symbols


def _extract_regex(source: str) -> list[dict]:
    """Regex 降级：支持 Python/JS/Go/Rust 等常见语言。"""
    symbols = []
    patterns = [
        # Python: def func_name(  /  class ClassName
        (r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", "function"),
        (r"^\s*class\s+(\w+)", "class"),
        # JavaScript/TypeScript: function name(  /  const name = (
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(", "function"),
        # Go: func Name(
        (r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(", "function"),
        # Rust: fn name(  /  pub fn name(
        (r"^\s*(?:pub\s+)?fn\s+(\w+)", "function"),
        (r"^\s*(?:pub\s+)?struct\s+(\w+)", "class"),
    ]

    for i, line in enumerate(source.split("\n"), 1):
        for pattern, sym_type in patterns:
            match = re.match(pattern, line)
            if match:
                symbols.append({
                    "name": match.group(1),
                    "type": sym_type,
                    "line": i,
                })
                break  # 一行只匹配一次

    return symbols


def format_symbol_list(symbols: list[dict]) -> str:
    """格式化为 LLM 可读的候选列表。"""
    if not symbols:
        return "(无函数/类定义)"
    lines = []
    for s in symbols:
        lines.append(f"  - {s['name']} ({s['type']}, line {s['line']})")
    return "\n".join(lines)
