"""
Session continuity: 会话结束时自动生成 SESSION.md 摘要，下次启动自动加载。

参考：
- Claude Code 4-Layer Memory (MEMORY.md → Topic Files → Learnings → Patterns)
- Augment Code "Session-End Spec Update" pattern (DEC-001, CONSTRAINT-001)
- Hermes Agent cross-session memory

设计：
- 会话结束时，把本次完成的任务摘要写入 .offgrid/SESSION.md
- 下次启动时自动读取，注入到首次 Gate 调用的 memory_context
- 文件限制 50 行，超出时保留最近的条目
"""

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_FILE = "SESSION.md"
MAX_LINES = 50


def _session_path(project_root: str) -> str:
    return os.path.join(project_root, ".offgrid", SESSION_FILE)


def load_session(project_root: str) -> str:
    """
    加载上次会话摘要。启动时调用，注入到 memory_context。
    返回摘要文本或空字符串。
    """
    path = _session_path(project_root)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            logger.info("[session] Loaded session context (%d chars)", len(content))
        return content
    except Exception as e:
        logger.warning("[session] Failed to load SESSION.md: %s", e)
        return ""


def save_session(project_root: str, tasks_completed: list[dict]):
    """
    会话结束时保存摘要。

    tasks_completed: [{"input": str, "success": bool, "files": list[str], "elapsed": float}]
    """
    if not tasks_completed:
        return

    path = _session_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 生成本次会话摘要
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entries = [f"## 会话 {now} ({len(tasks_completed)} 个任务)\n"]

    for task in tasks_completed[-10:]:  # 最多记录最近10个任务
        status = "OK" if task.get("success") else "FAIL"
        input_text = task.get("input", "")[:50]
        files = task.get("files", [])
        files_str = ", ".join(files[:3]) if files else ""
        elapsed = task.get("elapsed", 0)
        line = f"- [{status}] {input_text}"
        if files_str:
            line += f" → {files_str}"
        if elapsed > 0:
            line += f" ({elapsed:.0f}s)"
        new_entries.append(line)

    new_entries.append("")  # blank line separator

    # 读取现有内容并追加
    existing = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            pass

    # 新内容在前（最近的在最上面）
    combined = "\n".join(new_entries) + "\n" + existing

    # 限制行数
    lines = combined.splitlines()
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info("[session] Saved session summary (%d tasks)", len(tasks_completed))
    except Exception as e:
        logger.warning("[session] Failed to save SESSION.md: %s", e)
