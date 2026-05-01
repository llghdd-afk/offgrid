"""
Expert lifecycle state machine: new -> mature -> declining -> archived.
Implements spec §4.4 lifecycle transitions.
"""

import logging
import time
from datetime import datetime, timezone

from offgrid.registry.expert_registry import ExpertRegistry

logger = logging.getLogger(__name__)

# Thresholds
MATURE_MIN_TASKS = 5
MATURE_MIN_SUCCESS_RATE = 0.75
DECLINING_SUCCESS_RATE = 0.50
DECLINING_UNUSED_DAYS = 30


class LifecycleManager:
    """Expert lifecycle state machine: new -> mature -> declining -> archived."""

    def __init__(self, registry: ExpertRegistry):
        self.registry = registry

    def evaluate(self, expert_name: str) -> str | None:
        """
        Evaluate and potentially transition an expert's lifecycle.
        Returns new lifecycle state if changed, None if unchanged.

        State machine:
        - new: success_rate>75% AND task_count>5 -> mature
        - mature: success_rate drops <50% -> declining; 30 days unused -> declining
        - declining: (manual) user confirms -> archived; user fixes -> mature
        - archived: (manual) restore -> new
        """
        expert = self.registry.get(expert_name)
        if not expert:
            return None

        lifecycle = expert.get("lifecycle", "new")
        perf = expert.get("performance", {})
        sr = perf.get("success_rate", 0.0)
        count = perf.get("task_count", 0)

        new_state = None

        if lifecycle == "new":
            if count >= MATURE_MIN_TASKS and sr >= MATURE_MIN_SUCCESS_RATE:
                new_state = "mature"

        elif lifecycle == "mature":
            if count >= MATURE_MIN_TASKS and sr < DECLINING_SUCCESS_RATE:
                new_state = "declining"
            elif self._days_since_last_use(expert) >= DECLINING_UNUSED_DAYS:
                new_state = "declining"

        # declining -> archived and archived -> new are manual operations only

        if new_state and new_state != lifecycle:
            expert["lifecycle"] = new_state
            logger.info(
                "Expert %s lifecycle: %s -> %s (sr=%.0f%%, count=%d)",
                expert_name, lifecycle, new_state, sr * 100, count,
            )
            return new_state

        return None

    def check_merge_candidates(self) -> list[tuple[str, str]]:
        """
        Find expert pairs with >60% keyword overlap.
        Returns list of (expert_a, expert_b) pairs.
        """
        experts = self.registry.list_experts()
        pairs = []

        for i, a in enumerate(experts):
            kw_a = set(k.lower() for k in a.get("trigger_keywords", []))
            if not kw_a:
                continue
            for b in experts[i + 1:]:
                kw_b = set(k.lower() for k in b.get("trigger_keywords", []))
                if not kw_b:
                    continue
                overlap = len(kw_a & kw_b)
                total = len(kw_a | kw_b)
                if total > 0 and overlap / total > 0.6:
                    pairs.append((a["name"], b["name"]))

        if pairs:
            logger.info("Found %d merge candidate pair(s): %s", len(pairs), pairs)
        return pairs

    @staticmethod
    def _days_since_last_use(expert: dict) -> float:
        """Calculate days since expert was last used. Returns inf if never used."""
        last_used = expert.get("last_used")
        if not last_used:
            return float("inf")
        try:
            last_dt = datetime.fromisoformat(last_used)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - last_dt
            return delta.total_seconds() / 86400
        except (ValueError, TypeError):
            return float("inf")
