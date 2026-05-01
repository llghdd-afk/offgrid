"""
EXPERT.md memory: records of successful expert calls.
Spec §7.2: stored in .offgrid/EXPERT.md.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from offgrid.core.context import TaskContext

logger = logging.getLogger(__name__)

EXPERT_MD_TEMPLATE = """# 专家调用记录
> 自动维护

| 时间 | 专家 | 任务类型 | 涉及文件 | 流水线 | 耗时 |
|------|------|---------|---------|--------|------|
"""

MAX_RECORDS = 100


def _offgrid_dir(project_root: str) -> str:
    return os.path.join(project_root, ".offgrid")


def _md_path(project_root: str) -> str:
    return os.path.join(_offgrid_dir(project_root), "EXPERT.md")


def _ensure_dir(project_root: str):
    d = _offgrid_dir(project_root)
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def load(project_root: str) -> str:
    """Return recent expert records as injectable context."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Return last 20 records for context injection
        lines = content.split("\n")
        record_lines = [l for l in lines if l.startswith("|") and "时间" not in l and "---" not in l]
        if len(record_lines) > 20:
            record_lines = record_lines[-20:]
        if not record_lines:
            return ""
        return "最近专家调用：\n" + "\n".join(record_lines) + "\n"
    except Exception as e:
        logger.warning("Failed to read EXPERT.md: %s", e)
        return ""


def save(project_root: str, ctx: TaskContext, elapsed: float = 0.0):
    """Append a successful expert call record."""
    if not ctx.verifier_output or not ctx.verifier_output.get("passed"):
        # Only record successes (verifier-less pipelines like doc/office also count)
        expert_type = ctx.gate_result.get("expert_type", "unknown")
        if expert_type not in ("doc", "office"):
            return

    _ensure_dir(project_root)
    path = _md_path(project_root)

    # Create if not exists
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(EXPERT_MD_TEMPLATE)
        except Exception as e:
            logger.warning("Failed to create EXPERT.md: %s", e)
            return

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning("Failed to read EXPERT.md: %s", e)
        return

    # Build record
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    expert_type = ctx.gate_result.get("expert_type", "unknown")

    files = []
    if ctx.locator_output:
        files = ctx.locator_output.get("relevant_files", [])
    elif ctx.generator_output:
        files = [p.get("file", "") for p in ctx.generator_output.get("patches", [])]
    files_str = ", ".join(files[:3]) if files else "N/A"

    # Determine pipeline sequence
    from offgrid.core.orchestrator import EXPERT_SEQUENCES
    seq = EXPERT_SEQUENCES.get(expert_type, ["generator"])
    seq_str = "→".join([s.capitalize() for s in seq])

    elapsed_str = f"{elapsed:.1f}s" if elapsed > 0 else "N/A"
    # "专家" column = pipeline sequence name, "任务类型" = gate expert_type
    new_record = f"| {now} | {seq_str} | {expert_type} | {files_str} | {seq_str} | {elapsed_str} |"

    # Find separator and insert
    separator = "|------|------|---------|---------|--------|------|"
    if separator in content:
        parts = content.split(separator, 1)
        existing_records = parts[1] if len(parts) > 1 else ""
        record_lines = [
            line for line in existing_records.strip().split("\n")
            if line.startswith("|") and "时间" not in line and "---" not in line
        ]
        # Enforce MAX_RECORDS
        if len(record_lines) >= MAX_RECORDS:
            record_lines = record_lines[-(MAX_RECORDS - 1):]
        record_lines.append(new_record)
        content = parts[0] + separator + "\n" + "\n".join(record_lines) + "\n"
    else:
        content += f"\n{new_record}\n"

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Saved expert record to EXPERT.md")
    except Exception as e:
        logger.warning("Failed to write EXPERT.md: %s", e)


def show(project_root: str) -> str:
    """Display EXPERT.md content."""
    path = _md_path(project_root)
    if not os.path.exists(path):
        return "EXPERT.md not found. Will be created after first successful task."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read EXPERT.md: {e}"
