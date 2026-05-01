"""
KAIWU.md memory system: backward-compatible facade.
Delegates to the 3-layer memory system (project_md, expert_md, pattern_md).
Files are stored under {project_root}/.offgrid/.

The old KAIWU.md in project root is still read for migration but new writes
go to .offgrid/ directory.
"""

import logging
import os
from typing import Optional

from offgrid.core.context import TaskContext
from offgrid.memory import project_md, expert_md, pattern_md

logger = logging.getLogger(__name__)


class OffgridMemory:
    """Facade over the 3-layer memory system. Same interface as before."""

    def __init__(self):
        pass

    def load(self, project_root: str) -> str:
        """
        Load memory for Gate context injection.
        Returns 基础信息 section from PROJECT.md (token-limited).
        """
        return project_md.load_for_gate(project_root)

    def save(self, project_root: str, ctx: TaskContext, elapsed: float = 0.0):
        """
        Save to all three memory layers.
        project_md and expert_md only write on verifier pass.
        pattern_md always records (tracks both success and failure).
        """
        passed = False
        if ctx.verifier_output and ctx.verifier_output.get("passed"):
            passed = True
        else:
            # Verifier-less pipelines (doc, office) count as success
            expert_type = ctx.gate_result.get("expert_type", "")
            if expert_type in ("doc", "office"):
                passed = True

        if passed:
            project_md.save(project_root, ctx)
            expert_md.save(project_root, ctx, elapsed=elapsed)

        pattern_md.update(project_root, ctx, success=passed, elapsed=elapsed)

    def save_failure(self, project_root: str, ctx: TaskContext, elapsed: float = 0.0):
        """
        Record a failed task (only pattern_md tracks failures).
        """
        pattern_md.update(project_root, ctx, success=False, elapsed=elapsed)

    def init(self, project_root: str) -> str:
        """Initialize .offgrid/ directory and PROJECT.md with auto-detected info."""
        offgrid_dir = os.path.join(project_root, ".offgrid")
        if not os.path.exists(offgrid_dir):
            os.makedirs(offgrid_dir, exist_ok=True)
        return project_md.init(project_root)

    def show(self, project_root: str) -> str:
        """Show all three memory files."""
        parts = []

        proj = project_md.show(project_root)
        parts.append(f"═══ PROJECT.md ═══\n{proj}")

        exp = expert_md.show(project_root)
        parts.append(f"═══ EXPERT.md ═══\n{exp}")

        pat = pattern_md.show(project_root)
        parts.append(f"═══ PATTERN.md ═══\n{pat}")

        return "\n\n".join(parts)

    # ── Section-specific loaders for pipeline stages ──

    def load_for_gate(self, project_root: str) -> str:
        """Gate gets 基础信息 only."""
        return project_md.load_for_gate(project_root)

    def load_for_locator(self, project_root: str) -> str:
        """Locator gets 已知结构规律."""
        return project_md.load_for_locator(project_root)

    def load_for_verifier(self, project_root: str) -> str:
        """Verifier gets 注意事项."""
        return project_md.load_for_verifier(project_root)
