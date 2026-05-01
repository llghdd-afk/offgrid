import pytest
from datetime import datetime
from task_manager import Task, TaskManager, InMemoryStorage, Priority, Status


@pytest.fixture
def mgr():
    return TaskManager()


class TestCreateTask:
    def test_create_basic(self, mgr):
        task = mgr.create_task("Buy groceries")
        assert task.id is not None
        assert task.title == "Buy groceries"
        assert task.status == Status.TODO
        assert task.priority == Priority.MEDIUM

    def test_create_with_options(self, mgr):
        task = mgr.create_task("Fix bug", priority=Priority.HIGH, tags=["backend"], assignee="alice")
        assert task.priority == Priority.HIGH
        assert "backend" in task.tags
        assert task.assignee == "alice"

    def test_create_empty_title_raises(self, mgr):
        with pytest.raises(ValueError):
            mgr.create_task("")

    def test_create_whitespace_title_raises(self, mgr):
        with pytest.raises(ValueError):
            mgr.create_task("   ")

    def test_auto_increment_id(self, mgr):
        t1 = mgr.create_task("A")
        t2 = mgr.create_task("B")
        assert t2.id == t1.id + 1


class TestGetTask:
    def test_get_existing(self, mgr):
        task = mgr.create_task("Test")
        found = mgr.get_task(task.id)
        assert found.title == "Test"

    def test_get_missing_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.get_task(999)


class TestUpdateTask:
    def test_update_title(self, mgr):
        task = mgr.create_task("Old title")
        updated = mgr.update_task(task.id, title="New title")
        assert updated.title == "New title"

    def test_update_multiple_fields(self, mgr):
        task = mgr.create_task("Test")
        updated = mgr.update_task(task.id, description="desc", assignee="bob")
        assert updated.description == "desc"
        assert updated.assignee == "bob"

    def test_cannot_update_id(self, mgr):
        task = mgr.create_task("Test")
        original_id = task.id
        mgr.update_task(task.id, id=999)
        assert mgr.get_task(original_id).id == original_id

    def test_update_sets_updated_at(self, mgr):
        task = mgr.create_task("Test")
        old_updated = task.updated_at
        import time; time.sleep(0.01)
        mgr.update_task(task.id, title="Changed")
        assert mgr.get_task(task.id).updated_at > old_updated


class TestStatusTransitions:
    def test_start_task(self, mgr):
        task = mgr.create_task("Test")
        started = mgr.start_task(task.id)
        assert started.status == Status.IN_PROGRESS

    def test_complete_task(self, mgr):
        task = mgr.create_task("Test")
        completed = mgr.complete_task(task.id)
        assert completed.status == Status.DONE
        assert completed.completed_at is not None

    def test_cancel_task(self, mgr):
        task = mgr.create_task("Test")
        cancelled = mgr.cancel_task(task.id)
        assert cancelled.status == Status.CANCELLED

    def test_cannot_start_non_todo(self, mgr):
        task = mgr.create_task("Test")
        mgr.start_task(task.id)
        with pytest.raises(ValueError):
            mgr.start_task(task.id)

    def test_cannot_complete_cancelled(self, mgr):
        task = mgr.create_task("Test")
        mgr.cancel_task(task.id)
        with pytest.raises(ValueError):
            mgr.complete_task(task.id)

    def test_cannot_cancel_completed(self, mgr):
        task = mgr.create_task("Test")
        mgr.complete_task(task.id)
        with pytest.raises(ValueError):
            mgr.cancel_task(task.id)


class TestDeleteTask:
    def test_delete_existing(self, mgr):
        task = mgr.create_task("Test")
        assert mgr.delete_task(task.id) is True
        with pytest.raises(KeyError):
            mgr.get_task(task.id)

    def test_delete_missing(self, mgr):
        assert mgr.delete_task(999) is False


class TestListTasks:
    def test_list_all(self, mgr):
        mgr.create_task("A")
        mgr.create_task("B")
        mgr.create_task("C")
        assert len(mgr.list_tasks()) == 3

    def test_list_by_status(self, mgr):
        t1 = mgr.create_task("A")
        t2 = mgr.create_task("B")
        mgr.complete_task(t1.id)
        done = mgr.list_tasks(status=Status.DONE)
        assert len(done) == 1
        assert done[0].title == "A"

    def test_list_by_tag(self, mgr):
        mgr.create_task("A", tags=["frontend"])
        mgr.create_task("B", tags=["backend"])
        mgr.create_task("C", tags=["frontend", "backend"])
        frontend = mgr.list_tasks(tag="frontend")
        assert len(frontend) == 2

    def test_list_by_assignee(self, mgr):
        mgr.create_task("A", assignee="alice")
        mgr.create_task("B", assignee="bob")
        mgr.create_task("C", assignee="alice")
        alice_tasks = mgr.list_tasks(assignee="alice")
        assert len(alice_tasks) == 2

    def test_sort_by_priority(self, mgr):
        mgr.create_task("Low", priority=Priority.LOW)
        mgr.create_task("High", priority=Priority.HIGH)
        mgr.create_task("Medium", priority=Priority.MEDIUM)
        tasks = mgr.list_tasks(sort_by="priority")
        assert tasks[0].priority == Priority.HIGH
        assert tasks[-1].priority == Priority.LOW

    def test_sort_by_title(self, mgr):
        mgr.create_task("Charlie")
        mgr.create_task("Alice")
        mgr.create_task("Bob")
        tasks = mgr.list_tasks(sort_by="title")
        assert [t.title for t in tasks] == ["Alice", "Bob", "Charlie"]


class TestStats:
    def test_empty_stats(self, mgr):
        stats = mgr.get_stats()
        assert stats["total"] == 0

    def test_stats_by_status(self, mgr):
        t1 = mgr.create_task("A")
        t2 = mgr.create_task("B")
        mgr.complete_task(t1.id)
        stats = mgr.get_stats()
        assert stats["total"] == 2
        assert stats["by_status"]["done"] == 1
        assert stats["by_status"]["todo"] == 1

    def test_stats_by_priority(self, mgr):
        mgr.create_task("A", priority=Priority.HIGH)
        mgr.create_task("B", priority=Priority.HIGH)
        mgr.create_task("C", priority=Priority.LOW)
        stats = mgr.get_stats()
        assert stats["by_priority"]["HIGH"] == 2
        assert stats["by_priority"]["LOW"] == 1


class TestTaskSerialization:
    def test_to_dict(self, mgr):
        task = mgr.create_task("Test", priority=Priority.HIGH, tags=["a"])
        d = task.to_dict()
        assert d["title"] == "Test"
        assert d["priority"] == "HIGH"
        assert d["status"] == "todo"
        assert d["tags"] == ["a"]
        assert d["id"] is not None


class TestStorage:
    def test_storage_count(self):
        storage = InMemoryStorage()
        t = Task("Test")
        storage.save(t)
        assert storage.count() == 1

    def test_storage_clear(self):
        storage = InMemoryStorage()
        storage.save(Task("A"))
        storage.save(Task("B"))
        storage.clear()
        assert storage.count() == 0
        # IDs should reset
        t = Task("C")
        storage.save(t)
        assert t.id == 1

    def test_custom_storage(self):
        storage = InMemoryStorage()
        mgr = TaskManager(storage=storage)
        mgr.create_task("Test")
        assert storage.count() == 1


class TestRefactoring:
    """验证拆分要求"""

    def test_models_module_exists(self):
        import models
        assert hasattr(models, 'Task')
        assert hasattr(models, 'Priority')
        assert hasattr(models, 'Status')

    def test_storage_module_exists(self):
        import storage
        assert hasattr(storage, 'InMemoryStorage')

    def test_task_manager_reexports(self):
        """task_manager 应该 re-export 所有公开类"""
        from task_manager import Task, TaskManager, InMemoryStorage, Priority, Status
        assert Task is not None
        assert TaskManager is not None
        assert InMemoryStorage is not None
        assert Priority is not None
        assert Status is not None

    def test_task_manager_not_monolithic(self):
        """task_manager.py 不应该包含 Task 和 InMemoryStorage 的定义"""
        import inspect
        import task_manager
        source = inspect.getsource(task_manager)
        # TaskManager class 应该在 task_manager.py 中
        assert "class TaskManager" in source
        # 但 Task 和 InMemoryStorage 应该是从其他模块导入的
        assert "class Task:" not in source or "class Task(" not in source
        assert "class InMemoryStorage" not in source
