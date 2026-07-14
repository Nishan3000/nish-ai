"""In-memory task store.

Deliberately simple: a dict behind a lock. Tasks are lost on restart —
acceptable for this part of the phase, and honest about it. When the
PostgreSQL phase lands, this class keeps its interface and swaps its
internals for SQLAlchemy, so nothing else changes.
"""

import threading

from app.agents.models import AgentTask


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"No task with id '{task_id}'")


class TaskStore:
    """Thread-safe in-memory registry of agent tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._lock = threading.Lock()

    def add(self, task: AgentTask) -> AgentTask:
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> AgentTask:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def list(self) -> list[AgentTask]:
        with self._lock:
            return sorted(
                self._tasks.values(), key=lambda t: t.created_at, reverse=True
            )
