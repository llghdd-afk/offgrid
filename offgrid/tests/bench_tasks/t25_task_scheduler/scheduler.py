"""Distributed task scheduler engine."""

from task_graph import TaskGraph, TaskStatus, CycleError
from worker import WorkerPool, WorkerStatus


class Scheduler:
    """Coordinates task execution across workers using a DAG graph."""

    def __init__(self, graph, pool):
        self.graph = graph
        self.pool = pool
        self.completed = []
        self.failed = []
        self._assignments = {}  # task_id -> worker_id
        self.clock = 0

    def tick(self, dt=1):
        """Advance the simulated clock."""
        self.clock += dt

    def schedule(self):
        """Assign ready tasks to available workers.

        Returns list of (task, worker) pairs that were assigned.
        """
        ready = self.graph.get_ready_tasks()
        available = self.pool.get_available(self.clock)
        assignments = []

        for task in ready:
            if not available:
                break
            worker = available.pop(0)
            worker.assign(task, self.clock)
            task.status = TaskStatus.RUNNING
            self._assignments[task.id] = worker.id
            assignments.append((task, worker))

        return assignments

    def handle_completion(self, task_id, result=None):
        """Mark a task as completed."""
        task = self.graph.get_task(task_id)
        if task is None:
            return False

        task.status = TaskStatus.COMPLETED
        task.result = result

        worker_id = self._assignments.get(task_id)
        if worker_id:
            worker = self.pool.get_worker(worker_id)
            if worker:
                worker.release()

        self.completed.append(task_id)
        return True

    def handle_failure(self, task_id, error=None):
        """Handle a task failure — retry if possible."""
        task = self.graph.get_task(task_id)
        if task is None:
            return False

        worker_id = self._assignments.get(task_id)
        worker = self.pool.get_worker(worker_id) if worker_id else None

        if worker:
            worker.record_retry(task_id)
            retries_used = worker.get_retry_count(task_id)
            worker.release()
        else:
            retries_used = 0

        if retries_used < task.max_retries:
            task.status = TaskStatus.PENDING
            task.error = error
        else:
            task.status = TaskStatus.FAILED
            task.error = error
            self.failed.append(task_id)

        return True

    def check_timeouts(self):
        """Check for timed-out running tasks and fail them."""
        timed_out = []
        for task in self.graph.tasks.values():
            if task.status != TaskStatus.RUNNING:
                continue
            if task.started_at is not None:
                elapsed = self.clock - task.started_at
                if elapsed > task.timeout:
                    self.handle_failure(task.id, error="timeout")
                    timed_out.append(task.id)
        return timed_out

    def is_finished(self):
        """Check if all tasks are done (completed or failed)."""
        for task in self.graph.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING,
                               TaskStatus.READY):
                return False
        return True

    def run_step(self):
        """Execute one scheduling step: schedule, run handlers, collect.

        Returns dict with step results.
        """
        assignments = self.schedule()
        results = {}

        for task, worker in assignments:
            try:
                result = task.handler()
                self.handle_completion(task.id, result)
                results[task.id] = ("completed", result)
            except Exception as e:
                self.handle_failure(task.id, str(e))
                results[task.id] = ("failed", str(e))

        return results

    def run_all(self, max_steps=100):
        """Run all tasks to completion.

        Returns (completed_ids, failed_ids).
        """
        if self.graph.detect_cycle():
            raise CycleError("Cannot run: cycle detected in task graph")

        for _ in range(max_steps):
            if self.is_finished():
                break
            self.check_timeouts()
            self.run_step()
            self.tick()

        return list(self.completed), list(self.failed)
