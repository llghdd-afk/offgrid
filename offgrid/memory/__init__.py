"""
Kaiwu 3-layer memory system.

- project_md: PROJECT.md — project structure info
- expert_md: EXPERT.md — successful expert call records
- pattern_md: PATTERN.md — high-frequency task patterns (flywheel)
- offgrid_md: OffgridMemory facade (backward-compatible)
"""

from offgrid.memory.offgrid_md import OffgridMemory
from offgrid.memory import project_md, expert_md, pattern_md

__all__ = ["OffgridMemory", "project_md", "expert_md", "pattern_md"]
