# 任务管理系统 — 所有代码在一个文件里
# 任务：拆分为 models.py, storage.py, task_manager.py 三个文件
# 要求：测试文件不能改，所有 import 从 task_manager 导入
# task_manager.py 必须 re-export 所有公开类

from datetime import datetime
from enum import Enum


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class Task:
    def __init__(self, title: str, description: str = "", priority: Priority = Priority.MEDIUM,
                 tags: list[str] = None, assignee: str = None):
        self.id = None  # set by storage
        self.title = title
        self.description = description
        self.priority = priority
        self.status = Status.TODO
        self.tags = tags or []
        self.assignee = assignee
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.name,
            "status": self.status.value,
            "tags": self.tags,
            "assignee": self.assignee,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class InMemoryStorage:
    def __init__(self):
        self._tasks = {}
        self._next_id = 1

    def save(self, task: Task) -> Task:
        if task.id is None:
            task.id = self._next_id
            self._next_id += 1
        task.updated_at = datetime.now()
        self._tasks[task.id] = task
        return task

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)

    def delete(self, task_id: int) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def find_all(self) -> list[Task]:
        return list(self._tasks.values())

    def find_by_status(self, status: Status) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def find_by_tag(self, tag: str) -> list[Task]:
        return [t for t in self._tasks.values() if tag in t.tags]

    def find_by_assignee(self, assignee: str) -> list[Task]:
        return [t for t in self._tasks.values() if t.assignee == assignee]

    def count(self) -> int:
        return len(self._tasks)

    def clear(self):
        self._tasks.clear()
        self._next_id = 1


class TaskManager:
    def __init__(self, storage: InMemoryStorage = None):
        self.storage = storage or InMemoryStorage()

    def create_task(self, title: str, **kwargs) -> Task:
        if not title.strip():
            raise ValueError("Task title cannot be empty")
        task = Task(title=title, **kwargs)
        return self.storage.save(task)

    def get_task(self, task_id: int) -> Task:
        task = self.storage.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task

    def update_task(self, task_id: int, **fields) -> Task:
        task = self.get_task(task_id)
        for key, value in fields.items():
            if hasattr(task, key) and key not in ('id', 'created_at'):
                setattr(task, key, value)
        return self.storage.save(task)

    def complete_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if task.status == Status.CANCELLED:
            raise ValueError("Cannot complete a cancelled task")
        task.status = Status.DONE
        task.completed_at = datetime.now()
        return self.storage.save(task)

    def cancel_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if task.status == Status.DONE:
            raise ValueError("Cannot cancel a completed task")
        task.status = Status.CANCELLED
        return self.storage.save(task)

    def start_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if task.status != Status.TODO:
            raise ValueError(f"Can only start TODO tasks, current: {task.status.value}")
        task.status = Status.IN_PROGRESS
        return self.storage.save(task)

    def delete_task(self, task_id: int) -> bool:
        return self.storage.delete(task_id)

    def list_tasks(self, status: Status = None, tag: str = None,
                   assignee: str = None, sort_by: str = "created_at") -> list[Task]:
        if status:
            tasks = self.storage.find_by_status(status)
        elif tag:
            tasks = self.storage.find_by_tag(tag)
        elif assignee:
            tasks = self.storage.find_by_assignee(assignee)
        else:
            tasks = self.storage.find_all()

        if sort_by == "priority":
            tasks.sort(key=lambda t: t.priority.value, reverse=True)
        elif sort_by == "created_at":
            tasks.sort(key=lambda t: t.created_at)
        elif sort_by == "title":
            tasks.sort(key=lambda t: t.title.lower())

        return tasks

    def get_stats(self) -> dict:
        all_tasks = self.storage.find_all()
        by_status = {}
        by_priority = {}
        for t in all_tasks:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            by_priority[t.priority.name] = by_priority.get(t.priority.name, 0) + 1
        return {
            "total": len(all_tasks),
            "by_status": by_status,
            "by_priority": by_priority,
        }
