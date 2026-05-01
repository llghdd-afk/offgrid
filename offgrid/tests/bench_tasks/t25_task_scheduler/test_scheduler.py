"""Tests for distributed task scheduler.

DO NOT MODIFY THIS FILE.
"""

import pytest
from task_graph import Task, TaskGraph, TaskStatus, CycleError
from worker import Worker, WorkerPool, WorkerStatus
from scheduler import Scheduler


# ═══════════════════════════════════════════════════════════
# Section 1: TaskGraph basics
# ═══════════════════════════════════════════════════════════

class TestTaskBasics:
    def test_create_task(self):
        t = Task("t1", "compile")
        assert t.id == "t1"
        assert t.name == "compile"
        assert t.status == TaskStatus.PENDING
        assert t.retries == 0
        assert t.max_retries == 3

    def test_add_task_to_graph(self):
        g = TaskGraph()
        t = Task("t1", "build")
        g.add_task(t)
        assert g.get_task("t1") is t

    def test_duplicate_task_raises(self):
        g = TaskGraph()
        g.add_task(Task("t1", "a"))
        with pytest.raises(ValueError):
            g.add_task(Task("t1", "b"))

    def test_ready_tasks_no_deps(self):
        g = TaskGraph()
        g.add_task(Task("t1", "a"))
        g.add_task(Task("t2", "b"))
        ready = g.get_ready_tasks()
        assert len(ready) == 2

    def test_ready_tasks_with_deps(self):
        g = TaskGraph()
        g.add_task(Task("t1", "compile"))
        g.add_task(Task("t2", "link", dependencies=["t1"]))
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t1"

    def test_ready_after_dep_complete(self):
        g = TaskGraph()
        g.add_task(Task("t1", "compile"))
        g.add_task(Task("t2", "link", dependencies=["t1"]))
        g.get_task("t1").status = TaskStatus.COMPLETED
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t2"


# ═══════════════════════════════════════════════════════════
# Section 2: Topological sort
# ═══════════════════════════════════════════════════════════

class TestTopologicalSort:
    def test_simple_chain(self):
        g = TaskGraph()
        g.add_task(Task("a", "A"))
        g.add_task(Task("b", "B", dependencies=["a"]))
        g.add_task(Task("c", "C", dependencies=["b"]))
        order = g.topological_sort()
        ids = [t.id for t in order]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_diamond_graph(self):
        g = TaskGraph()
        g.add_task(Task("a", "A"))
        g.add_task(Task("b", "B", dependencies=["a"]))
        g.add_task(Task("c", "C", dependencies=["a"]))
        g.add_task(Task("d", "D", dependencies=["b", "c"]))
        order = g.topological_sort()
        ids = [t.id for t in order]
        assert ids.index("a") < ids.index("b")
        assert ids.index("a") < ids.index("c")
        assert ids.index("b") < ids.index("d")
        assert ids.index("c") < ids.index("d")

    def test_topo_sort_includes_isolated_nodes(self):
        """Isolated tasks (no deps, not depended on) must appear
        in the topological ordering."""
        g = TaskGraph()
        g.add_task(Task("a", "A"))
        g.add_task(Task("b", "B", dependencies=["a"]))
        g.add_task(Task("lone", "Lone"))  # no deps, nobody depends on it
        order = g.topological_sort()
        ids = [t.id for t in order]
        assert "lone" in ids
        assert len(ids) == 3

    def test_topo_sort_all_isolated(self):
        """Graph with ONLY isolated nodes should still produce valid ordering."""
        g = TaskGraph()
        g.add_task(Task("x", "X"))
        g.add_task(Task("y", "Y"))
        g.add_task(Task("z", "Z"))
        order = g.topological_sort()
        assert len(order) == 3
        ids = {t.id for t in order}
        assert ids == {"x", "y", "z"}

    def test_cycle_detection(self):
        g = TaskGraph()
        g.add_task(Task("a", "A", dependencies=["b"]))
        g.add_task(Task("b", "B", dependencies=["a"]))
        assert g.detect_cycle() is True

    def test_no_cycle(self):
        g = TaskGraph()
        g.add_task(Task("a", "A"))
        g.add_task(Task("b", "B", dependencies=["a"]))
        assert g.detect_cycle() is False


# ═══════════════════════════════════════════════════════════
# Section 3: Worker basics
# ═══════════════════════════════════════════════════════════

class TestWorkerBasics:
    def test_create_worker(self):
        w = Worker("w1")
        assert w.id == "w1"
        assert w.status == WorkerStatus.IDLE

    def test_worker_assign_release(self):
        w = Worker("w1")
        t = Task("t1", "build")
        w.assign(t, current_time=100)
        assert w.status == WorkerStatus.BUSY
        assert w.current_task is t
        w.release()
        assert w.status == WorkerStatus.IDLE
        assert w.current_task is None

    def test_heartbeat_keeps_worker_alive(self):
        pool = WorkerPool(heartbeat_timeout=10)
        w = Worker("w1")
        pool.add_worker(w)
        w.heartbeat(50)
        available = pool.get_available(55)
        assert len(available) == 1

    def test_new_worker_available_without_heartbeat(self):
        """A freshly created worker should be available immediately,
        not considered timed out before it has a chance to heartbeat."""
        pool = WorkerPool(heartbeat_timeout=10)
        w = Worker("w1")
        pool.add_worker(w)
        # Current time is 100; worker was just created.
        # With last_heartbeat=0, (100 - 0) = 100 > 10 → falsely offline.
        available = pool.get_available(100)
        assert len(available) == 1
        assert available[0].id == "w1"

    def test_worker_heartbeat_timeout(self):
        """Workers that genuinely miss heartbeats go offline."""
        pool = WorkerPool(heartbeat_timeout=10)
        w = Worker("w1")
        pool.add_worker(w)
        w.heartbeat(50)
        # 40 seconds later — well past timeout
        available = pool.get_available(91)
        assert len(available) == 0
        assert w.status == WorkerStatus.OFFLINE

    def test_offline_worker_recovers_on_heartbeat(self):
        pool = WorkerPool(heartbeat_timeout=10)
        w = Worker("w1")
        pool.add_worker(w)
        w.heartbeat(50)
        pool.get_available(91)  # goes offline
        assert w.status == WorkerStatus.OFFLINE
        pool.heartbeat("w1", 92)
        assert w.status == WorkerStatus.IDLE


# ═══════════════════════════════════════════════════════════
# Section 4: Scheduler state transitions
# ═══════════════════════════════════════════════════════════

class TestStateTransitions:
    def _make_env(self):
        g = TaskGraph()
        pool = WorkerPool(heartbeat_timeout=100)
        w = Worker("w1")
        pool.add_worker(w)
        w.heartbeat(0)
        sched = Scheduler(g, pool)
        return g, pool, w, sched

    def test_normal_completion(self):
        g, pool, w, sched = self._make_env()
        g.add_task(Task("t1", "job", handler=lambda: 42))
        sched.run_step()
        assert g.get_task("t1").status == TaskStatus.COMPLETED
        assert g.get_task("t1").result == 42

    def test_normal_failure(self):
        g, pool, w, sched = self._make_env()

        def boom():
            raise RuntimeError("kaboom")

        g.add_task(Task("t1", "job", handler=boom, max_retries=0))
        sched.run_step()
        assert g.get_task("t1").status == TaskStatus.FAILED

    def test_timeout_prevents_late_completion(self):
        """A timed-out (FAILED) task must NOT transition back to
        COMPLETED when a late result arrives."""
        g, pool, w, sched = self._make_env()
        t = Task("t1", "slow", timeout=5, max_retries=0)
        g.add_task(t)

        # Manually assign
        assignments = sched.schedule()
        assert len(assignments) == 1

        # Advance clock past timeout
        sched.clock = 100
        timed = sched.check_timeouts()
        assert "t1" in timed
        assert t.status == TaskStatus.FAILED

        # Late completion arrives — must be rejected
        result = sched.handle_completion("t1", result="late")
        assert t.status == TaskStatus.FAILED, \
            "Timed-out task must stay FAILED; illegal FAILED->COMPLETED transition"

    def test_completed_task_rejects_failure(self):
        """COMPLETED tasks cannot transition to FAILED."""
        g, pool, w, sched = self._make_env()
        t = Task("t1", "job", handler=lambda: "ok")
        g.add_task(t)
        sched.run_step()
        assert t.status == TaskStatus.COMPLETED

        result = sched.handle_failure("t1", error="phantom error")
        assert t.status == TaskStatus.COMPLETED, \
            "Completed task must stay COMPLETED"


# ═══════════════════════════════════════════════════════════
# Section 5: Retry across workers
# ═══════════════════════════════════════════════════════════

class TestRetryCrossWorker:
    def test_retry_count_persists_across_workers(self):
        """Retry count must follow the task across workers.
        When a task fails on worker A and retries on worker B, the
        cumulative retry count must be preserved."""
        g = TaskGraph()
        pool = WorkerPool(heartbeat_timeout=100)
        max_retries = 2

        fail_count = [0]

        def flaky():
            fail_count[0] += 1
            raise RuntimeError(f"fail #{fail_count[0]}")

        t = Task("t1", "flaky", handler=flaky, max_retries=max_retries)
        g.add_task(t)

        # Create several workers so the task can bounce between them.
        for i in range(5):
            w = Worker(f"w{i}")
            pool.add_worker(w)
            w.heartbeat(0)

        sched = Scheduler(g, pool)

        # Run enough steps; if retry count resets per-worker, the task
        # would retry indefinitely (limited only by max_steps).
        sched.run_all(max_steps=20)

        # The task MUST eventually be marked FAILED after max_retries
        # total failures, not per-worker.
        assert t.status == TaskStatus.FAILED, \
            f"Task should be FAILED after {max_retries} retries, but is {t.status}"
        assert fail_count[0] <= max_retries + 1, \
            f"Handler called {fail_count[0]} times; expected at most {max_retries + 1}"

    def test_retry_succeeds_on_second_worker(self):
        """Task fails once, retries on another worker, succeeds."""
        g = TaskGraph()
        pool = WorkerPool(heartbeat_timeout=100)
        call_count = [0]

        def flaky_once():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient")
            return "ok"

        t = Task("t1", "flaky_once", handler=flaky_once, max_retries=2)
        g.add_task(t)
        for i in range(3):
            w = Worker(f"w{i}")
            pool.add_worker(w)
            w.heartbeat(0)

        sched = Scheduler(g, pool)
        sched.run_all(max_steps=10)
        assert t.status == TaskStatus.COMPLETED
        assert t.result == "ok"


# ═══════════════════════════════════════════════════════════
# Section 6: Deadlock detection
# ═══════════════════════════════════════════════════════════

class TestDeadlockDetection:
    def test_real_deadlock_detected(self):
        """Genuine deadlock: pending tasks whose deps will never complete."""
        g = TaskGraph()
        t1 = Task("t1", "A", dependencies=["t2"])
        t2 = Task("t2", "B", dependencies=["t1"])
        g.add_task(t1)
        g.add_task(t2)
        assert g.check_deadlock(running_ids=set()) is True

    def test_no_deadlock_when_tasks_running(self):
        """A task is RUNNING; its dependents are PENDING but NOT
        ready. This is normal progress, not deadlock."""
        g = TaskGraph()
        t1 = Task("t1", "compile")
        t2 = Task("t2", "link", dependencies=["t1"])
        g.add_task(t1)
        g.add_task(t2)

        # t1 is running; t2 is pending waiting for t1
        t1.status = TaskStatus.RUNNING
        assert g.check_deadlock(running_ids={"t1"}) is False, \
            "Should not flag deadlock while tasks are still running"

    def test_no_deadlock_when_all_complete(self):
        g = TaskGraph()
        g.add_task(Task("t1", "A"))
        g.get_task("t1").status = TaskStatus.COMPLETED
        assert g.check_deadlock() is False

    def test_deadlock_with_failed_dependency(self):
        """A pending task depends on a failed task — genuine deadlock."""
        g = TaskGraph()
        t1 = Task("t1", "A")
        t2 = Task("t2", "B", dependencies=["t1"])
        g.add_task(t1)
        g.add_task(t2)
        t1.status = TaskStatus.FAILED
        assert g.check_deadlock(running_ids=set()) is True


# ═══════════════════════════════════════════════════════════
# Section 7: End-to-end scheduling
# ═══════════════════════════════════════════════════════════

class TestEndToEnd:
    def test_linear_chain(self):
        g = TaskGraph()
        results = []

        def make_handler(label):
            def h():
                results.append(label)
                return label
            return h

        g.add_task(Task("t1", "A", handler=make_handler("A")))
        g.add_task(Task("t2", "B", handler=make_handler("B"),
                        dependencies=["t1"]))
        g.add_task(Task("t3", "C", handler=make_handler("C"),
                        dependencies=["t2"]))

        pool = WorkerPool(heartbeat_timeout=200)
        w = Worker("w1")
        pool.add_worker(w)
        w.heartbeat(0)

        sched = Scheduler(g, pool)
        completed, failed = sched.run_all()
        assert results == ["A", "B", "C"]
        assert len(completed) == 3
        assert len(failed) == 0

    def test_parallel_then_join(self):
        g = TaskGraph()
        order = []

        def make_h(label):
            def h():
                order.append(label)
                return label
            return h

        g.add_task(Task("a", "A", handler=make_h("A")))
        g.add_task(Task("b", "B", handler=make_h("B")))
        g.add_task(Task("c", "C", handler=make_h("C"),
                        dependencies=["a", "b"]))

        pool = WorkerPool(heartbeat_timeout=200)
        for i in range(3):
            w = Worker(f"w{i}")
            pool.add_worker(w)
            w.heartbeat(0)

        sched = Scheduler(g, pool)
        completed, failed = sched.run_all()
        assert "C" in order
        assert order.index("C") > order.index("A")
        assert order.index("C") > order.index("B")
        assert set(completed) == {"a", "b", "c"}

    def test_isolated_and_connected_tasks(self):
        """Isolated tasks must also be scheduled and completed."""
        g = TaskGraph()
        g.add_task(Task("t1", "chain-a", handler=lambda: "a"))
        g.add_task(Task("t2", "chain-b", handler=lambda: "b",
                        dependencies=["t1"]))
        g.add_task(Task("lone", "isolated", handler=lambda: "lone"))

        pool = WorkerPool(heartbeat_timeout=200)
        for i in range(3):
            w = Worker(f"w{i}")
            pool.add_worker(w)
            w.heartbeat(0)

        sched = Scheduler(g, pool)
        completed, failed = sched.run_all()
        assert set(completed) == {"t1", "t2", "lone"}

    def test_cycle_raises_on_run(self):
        g = TaskGraph()
        g.add_task(Task("a", "A", dependencies=["b"]))
        g.add_task(Task("b", "B", dependencies=["a"]))

        pool = WorkerPool(heartbeat_timeout=200)
        pool.add_worker(Worker("w1"))

        sched = Scheduler(g, pool)
        with pytest.raises(CycleError):
            sched.run_all()

    def test_run_all_with_initial_heartbeat(self):
        """Workers created and used immediately should work."""
        g = TaskGraph()
        g.add_task(Task("t1", "quick", handler=lambda: "done"))

        pool = WorkerPool(heartbeat_timeout=10)
        w = Worker("w1")
        pool.add_worker(w)
        # Note: no explicit heartbeat call — relies on creation time.

        sched = Scheduler(g, pool)
        sched.clock = 50  # simulate some time has passed
        completed, failed = sched.run_all()
        assert "t1" in completed

    def test_complex_dag_all_complete(self):
        """
        DAG:  a -> b -> d
              a -> c -> d
              e (isolated)
        All five tasks must complete.
        """
        g = TaskGraph()

        def h(label):
            return lambda: label

        g.add_task(Task("a", "A", handler=h("A")))
        g.add_task(Task("b", "B", handler=h("B"), dependencies=["a"]))
        g.add_task(Task("c", "C", handler=h("C"), dependencies=["a"]))
        g.add_task(Task("d", "D", handler=h("D"), dependencies=["b", "c"]))
        g.add_task(Task("e", "E", handler=h("E")))

        pool = WorkerPool(heartbeat_timeout=200)
        for i in range(3):
            w = Worker(f"w{i}")
            pool.add_worker(w)
            w.heartbeat(0)

        sched = Scheduler(g, pool)
        completed, failed = sched.run_all()
        assert set(completed) == {"a", "b", "c", "d", "e"}
        assert failed == []
