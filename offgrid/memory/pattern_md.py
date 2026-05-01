"""
PATTERN.md memory: high-frequency task patterns (flywheel data source).
Spec §7.2: stored in .offgrid/PATTERN.md.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from offgrid.core.context import TaskContext

logger = logging.getLogger(__name__)

PATTERN_MD_TEMPLATE = """# 高频任务模式
> 飞轮数据源，自动维护

## 模式统计
| 任务类型 | 次数 | 成功率 | 平均耗时 | 最近触发 |
|---------|------|--------|---------|---------|

## 候选专家触发
"""

# Internal JSON sidecar for structured stats (markdown is for display)
_STATS_FILENAME = ".pattern_stats.json"


def _offgrid_dir(project_root: str) -> str:
    return os.path.join(project_root, ".offgrid")


def _md_path(project_root: str) -> str:
    return os.path.join(_offgrid_dir(project_root), "PATTERN.md")


def _stats_path(project_root: str) -> str:
    return os.path.join(_offgrid_dir(project_root), _STATS_FILENAME)


def _ensure_dir(project_root: str):
    d = _offgrid_dir(project_root)
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _load_stats(project_root: str) -> dict:
    """Load structured stats from JSON sidecar."""
    path = _stats_path(project_root)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stats(project_root: str, stats: dict):
    """Save structured stats to JSON sidecar."""
    _ensure_dir(project_root)
    path = _stats_path(project_root)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to write pattern stats: %s", e)


def _rebuild_markdown(project_root: str, stats: dict):
    """Rebuild PATTERN.md from structured stats."""
    _ensure_dir(project_root)
    lines = [
        "# 高频任务模式",
        "> 飞轮数据源，自动维护",
        "",
        "## 模式统计",
        "| 任务类型 | 次数 | 成功率 | 平均耗时 | 最近触发 |",
        "|---------|------|--------|---------|---------|",
    ]

    # Sort by count descending
    sorted_types = sorted(stats.items(), key=lambda x: x[1].get("count", 0), reverse=True)
    for task_type, data in sorted_types:
        count = data.get("count", 0)
        success = data.get("success", 0)
        rate = f"{success / count * 100:.0f}%" if count > 0 else "0%"
        total_elapsed = data.get("total_elapsed", 0.0)
        avg_elapsed = f"{total_elapsed / count:.1f}s" if count > 0 else "N/A"
        last_trigger = data.get("last_trigger", "N/A")
        lines.append(f"| {task_type} | {count} | {rate} | {avg_elapsed} | {last_trigger} |")

    lines.append("")
    lines.append("## 候选专家触发")

    # Auto-detect candidates: >=5 tasks with 100% success
    for task_type, data in sorted_types:
        count = data.get("count", 0)
        success = data.get("success", 0)
        if count >= 5 and success == count:
            avg_elapsed = data.get("total_elapsed", 0.0) / count
            lines.append(f"- {task_type}: {count}次全部成功，平均{avg_elapsed:.1f}s")

    # Recent failures section
    has_failures = any(d.get("recent_failures") for _, d in sorted_types)
    if has_failures:
        lines.append("")
        lines.append("## 近期失败模式")
        for task_type, data in sorted_types:
            failures = data.get("recent_failures", [])
            if failures:
                for f in failures[-5:]:  # Show last 5 per type in markdown
                    lines.append(f"- {task_type} {f}")

    lines.append("")

    path = _md_path(project_root)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.warning("Failed to write PATTERN.md: %s", e)


# ── Public API ──


def load(project_root: str) -> str:
    """Return pattern summary as injectable context."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to read PATTERN.md: %s", e)
        return ""


def update(project_root: str, ctx: TaskContext, success: bool, elapsed: float = 0.0):
    """Update pattern stats after every task (success or failure)."""
    expert_type = ctx.gate_result.get("expert_type", "unknown")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    stats = _load_stats(project_root)

    if expert_type not in stats:
        stats[expert_type] = {
            "count": 0,
            "success": 0,
            "total_elapsed": 0.0,
            "last_trigger": "",
            "recent_failures": [],
        }

    entry = stats[expert_type]
    entry["count"] += 1
    if success:
        entry["success"] += 1
    else:
        # Record failure mode for future reference
        error_detail = ""
        if ctx.verifier_output:
            error_detail = ctx.verifier_output.get("error_detail", "")
        failure_record = f"[{now}] {error_detail[:100]}"
        failures = entry.get("recent_failures", [])
        failures.append(failure_record)
        # Keep only last 10 failures
        entry["recent_failures"] = failures[-10:]

    entry["total_elapsed"] += elapsed
    entry["last_trigger"] = now

    _save_stats(project_root, stats)
    _rebuild_markdown(project_root, stats)
    logger.info("Updated PATTERN.md for %s (success=%s)", expert_type, success)


def get_pattern_stats(project_root: str) -> list[dict]:
    """Return structured stats for flywheel consumption."""
    stats = _load_stats(project_root)
    result = []
    for task_type, data in stats.items():
        count = data.get("count", 0)
        success = data.get("success", 0)
        result.append({
            "task_type": task_type,
            "count": count,
            "success_rate": success / count if count > 0 else 0.0,
            "avg_elapsed": data.get("total_elapsed", 0.0) / count if count > 0 else 0.0,
            "last_trigger": data.get("last_trigger", ""),
        })
    return sorted(result, key=lambda x: x["count"], reverse=True)


def count_similar_failures(expert_type: str, keywords: list[str],
                           project_root: str) -> int:
    """
    Count historical failures similar to the given task.
    Simple keyword match against recent_failures, no LLM call.
    Used by Planner for risk assessment.
    """
    stats = _load_stats(project_root)
    entry = stats.get(expert_type, {})
    failures = entry.get("recent_failures", [])
    count = 0
    for line in failures:
        if any(kw in line for kw in keywords if len(kw) > 1):
            count += 1
    return count


def show(project_root: str) -> str:
    """Display PATTERN.md content."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return "PATTERN.md not found. Will be created after first task."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read PATTERN.md: {e}"


# ── Reflexion持久化 (SE-RED-5: 结构化格式) ──

REFLECTION_TEMPLATE = "- [{date}] {task_summary} → {reflection}\n"

_REFLECTION_FILE = "REFLECTION.md"


def _reflection_path(project_root: str) -> str:
    return os.path.join(_offgrid_dir(project_root), _REFLECTION_FILE)


def _read_reflection(project_root: str) -> str:
    path = _reflection_path(project_root)
    if not os.path.exists(path):
        return "# OffGrid Pattern Memory\n"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "# OffGrid Pattern Memory\n"


def _write_reflection(project_root: str, content: str):
    _ensure_dir(project_root)
    path = _reflection_path(project_root)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.warning("Failed to write REFLECTION.md: %s", e)


def save_reflection(
    project_root: str,
    expert_type: str,
    task_summary: str,
    reflection: str,
    success: bool,
):
    """
    把Reflection结果持久化到REFLECTION.md。
    SE-RED-5：结构化格式，不是自由文本。
    """
    from datetime import date as date_mod

    # 根据成败选择section
    if success:
        section = f"## {expert_type} 注意事项"
        prefix = "注意"
    else:
        section = f"## {expert_type} 失败模式"
        prefix = "根因"

    entry = REFLECTION_TEMPLATE.format(
        date=date_mod.today().isoformat(),
        task_summary=task_summary[:30],
        reflection=f"{prefix}：{reflection[:80]}",
    )

    content = _read_reflection(project_root)

    # 找到对应section，追加条目
    if section in content:
        content = content.replace(
            section + "\n",
            section + "\n" + entry,
        )
    else:
        content += f"\n{section}\n{entry}"

    # 限制每个section最多20条（防止无限增长）
    content = _trim_reflection_sections(content, max_entries=20)
    _write_reflection(project_root, content)


def get_reflections_for_plan(project_root: str, expert_type: str) -> str:
    """
    /plan时读取相关历史Reflection，作为风险提示。
    返回最近5条相关记录。
    """
    content = _read_reflection(project_root)
    sections = [
        f"## {expert_type} 失败模式",
        f"## {expert_type} 注意事项",
        f"## {expert_type} 风险点",
    ]

    result = []
    for section in sections:
        if section in content:
            after = content.split(section)[1].split("##")[0].strip()
            recent = "\n".join(after.splitlines()[:5])
            if recent:
                result.append(f"{section}\n{recent}")

    return "\n\n".join(result)


def _trim_reflection_sections(content: str, max_entries: int) -> str:
    """每个section只保留最新的max_entries条。"""
    lines = content.splitlines()
    result = []
    current_section_entries = 0
    in_section = False

    for line in lines:
        if line.startswith("## "):
            in_section = True
            current_section_entries = 0
            result.append(line)
        elif in_section and line.startswith("- ["):
            current_section_entries += 1
            if current_section_entries <= max_entries:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)
