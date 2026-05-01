"""
Pattern detector: finds repeated successful task patterns that could become experts.
Implements gate 1 of the three-gate validation system (spec §5.1).
"""

import logging
from collections import defaultdict

from offgrid.flywheel.trajectory_collector import TrajectoryCollector, TaskTrajectory

logger = logging.getLogger(__name__)

# Minimum successful occurrences to trigger expert generation
MIN_PATTERN_COUNT = 5


class PatternDetector:
    """Detects repeated successful patterns that could become experts."""

    def __init__(self, collector: TrajectoryCollector):
        self.collector = collector

    def detect(self) -> list[dict]:
        """
        Scan trajectories for expert generation candidates.

        Trigger conditions (ALL must be met — spec §5.1 first gate):
        - Same expert_type appeared >=5 times
        - All 5+ occurrences were successful
        - All used the same pipeline sequence

        Returns list of:
        {
            "expert_type": str,
            "count": int,
            "trajectories": list[TaskTrajectory],
            "pipeline": list[str],
        }
        """
        all_trajs = self.collector.load_recent(limit=500)

        # Group by expert_type
        by_type: dict[str, list[TaskTrajectory]] = defaultdict(list)
        for t in all_trajs:
            by_type[t.expert_used].append(t)

        candidates = []
        for expert_type, trajs in by_type.items():
            # Filter to successful only
            successful = [t for t in trajs if t.success]
            if len(successful) < MIN_PATTERN_COUNT:
                # P2: Queue progress notification for accumulation (3/5, 4/5)
                if len(successful) >= 3:
                    self._notify_progress(expert_type, len(successful))
                continue

            # Check all successful trajectories share the same pipeline
            pipeline_key = _pipeline_key(successful[0].pipeline_steps)
            if not all(_pipeline_key(t.pipeline_steps) == pipeline_key for t in successful):
                # Not all same pipeline — group by pipeline sub-patterns
                sub = self._group_by_pipeline(successful)
                for pipeline_str, sub_trajs in sub.items():
                    if len(sub_trajs) >= MIN_PATTERN_COUNT:
                        candidates.append({
                            "expert_type": expert_type,
                            "count": len(sub_trajs),
                            "trajectories": sub_trajs,
                            "pipeline": sub_trajs[0].pipeline_steps,
                        })
                continue

            # Any failures for this type disqualify (all occurrences must be successful)
            failed = [t for t in trajs if not t.success]
            if failed:
                continue

            candidates.append({
                "expert_type": expert_type,
                "count": len(successful),
                "trajectories": successful,
                "pipeline": successful[0].pipeline_steps,
            })

        if candidates:
            logger.info(
                "Pattern detector found %d candidate(s): %s",
                len(candidates),
                [c["expert_type"] for c in candidates],
            )
        return candidates

    @staticmethod
    def _group_by_pipeline(trajs: list[TaskTrajectory]) -> dict[str, list[TaskTrajectory]]:
        """Group trajectories by their pipeline sequence."""
        groups: dict[str, list[TaskTrajectory]] = defaultdict(list)
        for t in trajs:
            groups[_pipeline_key(t.pipeline_steps)].append(t)
        return groups

    @staticmethod
    def _notify_progress(expert_type: str, current: int):
        """P2: Queue flywheel progress notification (non-blocking)."""
        try:
            from offgrid.notification.flywheel_notifier import FlywheelNotifier
            notifier = FlywheelNotifier()
            notifier.queue_progress(expert_type, current, MIN_PATTERN_COUNT)
        except Exception:
            pass  # Non-blocking


def _pipeline_key(steps: list[str]) -> str:
    return "|".join(steps)
