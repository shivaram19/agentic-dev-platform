"""
Agentic Development Platform - Orchestrator Base Abstractions

Defines the Task/TaskResult data contracts and the IOrchestrator interface
implemented by all orchestration layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Mapping, Optional
import structlog

from core.agents.base import AgentPlatformError

log = structlog.get_logger(__name__)


class OrchestratorError(AgentPlatformError):
    """Base exception for orchestrator-related errors."""
    pass


class TaskPriority(Enum):
    """Priority levels for tasks submitted to orchestrators."""
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()


@dataclass(frozen=True)
class Task:
    """
    Immutable description of a work item submitted to an orchestrator.

    SRP: Encapsulates only task metadata, not orchestration behavior.
    """
    id: str
    project_id: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL


@dataclass(frozen=True)
class TaskResult:
    """
    Immutable result of a task executed by an orchestrator.

    Contains both success path data and error information without any
    behavior (pure data transfer object).
    """
    task_id: str
    project_id: str
    session_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class IOrchestrator(ABC):
    """
    Abstract interface for all orchestrators (master and project-level).

    Follows SOLID:
    - SRP: Defines orchestration contract only, no implementation details.
    - OCP: New orchestrator types can be added without modifying this class.
    - LSP: Concrete orchestrators can be used wherever IOrchestrator is expected.
    - ISP: Only orchestration-specific methods, no unrelated concerns.
    - DIP: Higher layers depend on this abstraction, not concrete classes.
    """

    @property
    @abstractmethod
    def orchestrator_id(self) -> str:
        """Return a stable identifier for this orchestrator instance."""
        ...

    @abstractmethod
    async def submit_task(self, task: Task) -> str:
        """
        Submit a task for execution.

        Args:
            task: Task description.

        Returns:
            A session_id used to query task status and results later.
        """
        ...

    @abstractmethod
    async def get_task_result(self, session_id: str) -> Optional[TaskResult]:
        """
        Retrieve the result of a previously submitted task.

        Args:
            session_id: Identifier returned by submit_task().

        Returns:
            TaskResult if available, otherwise None when still in progress.
        """
        ...

    @abstractmethod
    async def cancel_task(self, session_id: str) -> None:
        """
        Attempt to cancel a running task.

        Implementations should be best-effort and idempotent.
        """
        ...
