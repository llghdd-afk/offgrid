"""
Flywheel: automatic expert generation from repeated successful task patterns.

Components:
- TrajectoryCollector: records task execution trajectories
- PatternDetector: detects repeated successful patterns (gate 1)
- ExpertGeneratorFlywheel: generates expert YAML drafts from patterns
- ABTester: three-gate expert validation (gate 2 backtest + gate 3 AB test)
- LifecycleManager: expert lifecycle state machine
"""

from offgrid.flywheel.trajectory_collector import TrajectoryCollector, TaskTrajectory
from offgrid.flywheel.pattern_detector import PatternDetector
from offgrid.flywheel.expert_generator import ExpertGeneratorFlywheel
from offgrid.flywheel.ab_tester import ABTester
from offgrid.flywheel.lifecycle_manager import LifecycleManager

__all__ = [
    "TrajectoryCollector",
    "TaskTrajectory",
    "PatternDetector",
    "ExpertGeneratorFlywheel",
    "ABTester",
    "LifecycleManager",
]
