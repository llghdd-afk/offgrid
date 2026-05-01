"""DAG task graph for distributed task scheduler."""

from enum import Enum
from collections import deque


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    def __init__(self, task_id, name, handler=None, dependencies=None,
                 max_retries=3, timeout=30):
        self.id = task_id
        self.name = name
        self.handler = handler or (lambda: None)
        self.dependencies = dependencies or []
        self.status = TaskStatus.PENDING
        self.retries = 0
        self.max_retries = max_retries
        self.timeout = timeout
        self.result = None
        self.error = None
        self.started_at = None

    def __repr__(self):
        return f"Task({self.id}, {self.name}, {self.status.value})"


class TaskGraph:
    """DAG-based task dependency graph."""

    def __init__(self):
        self.tasks = {}  # task_id -> Task

    def add_task(self, task):
        """Add a task to the graph."""
        if task.id in self.tasks:
            raise ValueError(f"Task {task.id} already exists")
        self.tasks[task.id] = task
        return task

    def get_task(self, task_id):
        """Get task by ID."""
        return self.tasks.get(task_id)

    def get_ready_tasks(self):
        """Return tasks whose dependencies are all completed."""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            if deps_met:
                ready.append(task)
        return ready

    def topological_sort(self):
        """Return tasks in topological order. Raises if cycle detected."""
        in_degree = {}
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    if dep_id not in in_degree:
                        in_degree[dep_id] = 0
                    if task.id not in in_degree:
                        in_degree[task.id] = 0
                    in_degree[task.id] += 1

        queue = deque(
            tid for tid, deg in in_degree.items() if deg == 0
        )
        order = []

        while queue:
            tid = queue.popleft()
            order.append(tid)
            for task in self.tasks.values():
                if tid in task.dependencies:
                    in_degree[task.id] -= 1
                    if in_degree[task.id] == 0:
                        queue.append(task.id)

        if len(order) != len(self.tasks):
            raise CycleError("Cycle detected in task graph")

        return [self.tasks[tid] for tid in order]

    def detect_cycle(self):
        """Return True if graph contains a cycle."""
        try:
            self.topological_sort()
            return False
        except CycleError:
            return True

    def check_deadlock(self, running_ids=None):
        """Check for deadlock: pending tasks exist but nothing can progress.

        Returns True if deadlocked.
        """
        running_ids = running_ids or set()
        pending = [t for t in self.tasks.values()
                   if t.status == TaskStatus.PENDING]
        ready = self.get_ready_tasks()

        if pending and not ready:
            return True
        return False


class CycleError(Exception):
    pass
