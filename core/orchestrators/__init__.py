# core/orchestrators package
"""
Agentic Development Platform - Orchestrators Package

Exposes the orchestration abstractions and concrete orchestrators used to
coordinate agents across and within projects.
"""

from core.orchestrators.base import IOrchestrator, Task, TaskResult
from core.orchestrators.master_orchestrator import MasterOrchestrator
from core.orchestrators.project_orchestrator import ProjectOrchestrator

__all__ = [
    "IOrchestrator",
    "Task",
    "TaskResult",
    "MasterOrchestrator",
    "ProjectOrchestrator",
]
