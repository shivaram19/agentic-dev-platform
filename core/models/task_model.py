"""
Agentic Development Platform - Task model.

Tasks are the fundamental units of work in the platform. They capture:

- the user’s goal articulated in natural language,
- the project and agent context,
- status and lifecycle timestamps,
- optional hierarchy and dependency information.

These models are intentionally framework‑agnostic and can be stored in any
backend (SQLite, Postgres, Git‑backed, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid


class TaskStatus(str, Enum):
    """
    High‑level lifecycle states for a task.
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """
    Priority levels for tasks.

    These can be used by orchestrators or schedulers to select “ready work”
    when multiple tasks are available, similar to Git‑backed issue trackers
    like Beads.
    """
    LOW = 1
    NORMAL = 5
    HIGH = 9


@dataclass
class Task:
    """
    Core task object used throughout the agentic platform.

    A `Task` is deliberately small and self‑contained:

    - `task_id`: globally unique identifier (UUIDv4 by default).
    - `project_id`: logical project this task belongs to.
    - `title`: short label for UI and logs.
    - `description`: free‑form natural‑language description of the goal.
    - `status`: current lifecycle state.
    - `priority`: rough importance / scheduling hint.
    - `created_at`, `updated_at`: monotonic timestamps in UTC.
    - `parent_id`: optional parent task for hierarchical breakdown.
    - `depends_on`: list of other task IDs that must be completed first.
    - `metadata`: free‑form JSON‑serializable payload for agent‑specific fields.
    """

    project_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    parent_id: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    meta Dict[str, Any] = field(default_factory=dict)

    def mark_in_progress(self) -> None:
        """
        Mark the task as in progress and bump the `updated_at` timestamp.
        """
        self.status = TaskStatus.IN_PROGRESS
        self.touch()

    def mark_completed(self) -> None:
        """
        Mark the task as completed and bump the `updated_at` timestamp.
        """
        self.status = TaskStatus.COMPLETED
        self.touch()

    def mark_failed(self, reason: str | None = None) -> None:
        """
        Mark the task as failed and optionally record a machine‑readable reason.
        """
        self.status = TaskStatus.FAILED
        if reason:
            self.metadata.setdefault("failure_reasons", []).append(reason)
        self.touch()

    def mark_cancelled(self, reason: str | None = None) -> None:
        """
        Mark the task as cancelled and optionally record a human‑readable reason.
        """
        self.status = TaskStatus.CANCELLED
        if reason:
            self.metadata.setdefault("cancel_reasons", []).append(reason)
        self.touch()

    def touch(self) -> None:
        """
        Update the `updated_at` timestamp to now (UTC).
        """
        self.updated_at = datetime.now(timezone.utc)

    def is_terminal(self) -> bool:
        """
        Return True if the task is in a terminal state (completed, failed, or cancelled).
        """
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }

    def is_ready(self, completed_dependencies: List[str] | None = None) -> bool:
        """
        Determine whether the task is ready to be picked up by an agent.

        A task is considered ready if:

        - it is currently in the PENDING state, and
        - all tasks it depends on are in the `completed_dependencies` list
          (if provided).

        This mirrors “ready work” selection in DAG‑based task systems.
        """
        if self.status is not TaskStatus.PENDING:
            return False
        if not self.depends_on:
            return True
        if completed_dependencies is None:
            return False
        return all(dep_id in completed_dependencies for dep_id in self.depends_on)
