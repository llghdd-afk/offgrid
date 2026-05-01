"""Worker node simulation for distributed task scheduler."""

from enum import Enum


class WorkerStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class Worker:
    def __init__(self, worker_id, name=None):
        self.id = worker_id
        self.name = name or f"worker-{worker_id}"
        self.status = WorkerStatus.IDLE
        self.current_task = None
        self.last_heartbeat = 0
        self._retry_counts = {}  # task_id -> retry count on THIS worker

    def heartbeat(self, current_time):
        """Record a heartbeat at the given time."""
        self.last_heartbeat = current_time

    def assign(self, task, current_time):
        """Assign a task to this worker."""
        self.status = WorkerStatus.BUSY
        self.current_task = task
        task.started_at = current_time

    def release(self):
        """Release the current task."""
        self.current_task = None
        self.status = WorkerStatus.IDLE

    def record_retry(self, task_id):
        """Record a retry attempt for a task on this worker."""
        self._retry_counts[task_id] = self._retry_counts.get(task_id, 0) + 1

    def get_retry_count(self, task_id):
        """Get retry count for a task on this specific worker."""
        return self._retry_counts.get(task_id, 0)


class WorkerPool:
    """Manages a pool of workers."""

    def __init__(self, heartbeat_timeout=10):
        self.workers = {}  # worker_id -> Worker
        self.heartbeat_timeout = heartbeat_timeout

    def add_worker(self, worker):
        """Add a worker to the pool."""
        self.workers[worker.id] = worker
        return worker

    def get_available(self, current_time):
        """Return idle workers that are not timed out."""
        available = []
        for w in self.workers.values():
            if w.status != WorkerStatus.IDLE:
                continue
            if current_time - w.last_heartbeat > self.heartbeat_timeout:
                w.status = WorkerStatus.OFFLINE
                continue
            available.append(w)
        return available

    def get_worker(self, worker_id):
        """Get worker by ID."""
        return self.workers.get(worker_id)

    def heartbeat(self, worker_id, current_time):
        """Process heartbeat from a worker."""
        w = self.workers.get(worker_id)
        if w is None:
            return False
        w.heartbeat(current_time)
        if w.status == WorkerStatus.OFFLINE:
            w.status = WorkerStatus.IDLE
        return True
