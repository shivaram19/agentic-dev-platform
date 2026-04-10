"""
Agentic Development Platform - Master Orchestrator

Top-level orchestrator responsible for:
- Receiving tasks from voice/text interfaces.
- Routing tasks to the correct ProjectOrchestrator.
- Coordinating cross-project dependencies via a dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
import asyncio
import uuid
import structlog

from core.orchestrators.base import IOrchestrator, Task, TaskResult, OrchestratorError
from core.orchestrators.project_orchestrator import ProjectOrchestrator
from core.communication.message_bus import IMessageBus, AgentMessage
from core.registry.project_registry import ProjectRegistry, DependencyGraph

log = structlog.get_logger(__name__)


@dataclass
class MasterOrchestratorConfig:
    """
    Configuration for MasterOrchestrator.

    Keeps master-level concerns separate from project configuration (SRP).
    """
    max_concurrent_projects: int = 16


class MasterOrchestrator(IOrchestrator):
    """
    Hierarchical master orchestrator implementing IOrchestrator.

    Responsibilities:
    - Task ingress from external channels (voice, API, CLI).
    - Project selection and orchestration delegation.
    - Cross-project dependency scheduling using DependencyGraph.

    The design follows common orchestration patterns in microservice
    architectures, separating orchestration logic from execution details.[web:130][web:136][web:140]
    """

    def __init__(
        self,
        orchestrator_id: str,
        message_bus: IMessageBus,
        project_registry: ProjectRegistry,
        dependency_graph: DependencyGraph,
        config: MasterOrchestratorConfig | None = None,
    ) -> None:
        """
        Initialize MasterOrchestrator.

        Args:
            orchestrator_id: Identifier for this orchestrator instance.
            message_bus: Asynchronous message bus for agent-to-agent signaling.
            project_registry: Registry of known projects and their metadata.
            dependency_graph: Graph describing cross-project dependencies.
            config: Optional master-level configuration.
        """
        self._id = orchestrator_id
        self._message_bus = message_bus
        self._project_registry = project_registry
        self._dependency_graph = dependency_graph
        self._config = config or MasterOrchestratorConfig()
        self._project_orchestrators: Dict[str, ProjectOrchestrator] = {}
        self._session_to_project: Dict[str, str] = {}

        self._logger = log.bind(orchestrator_id=orchestrator_id, layer="master_orchestrator")
        self._logger.info("MasterOrchestrator initialized")

    # IOrchestrator API ---------------------------------------------------

    @property
    def orchestrator_id(self) -> str:
        return self._id

    async def submit_task(self, task: Task) -> str:
        """
        Submit a task and route it to the appropriate ProjectOrchestrator.

        If the task involves cross-project dependencies, they are scheduled
        in dependency order using the DependencyGraph.
        """
        self._logger.info(
            "Submitting task to MasterOrchestrator",
            task_id=task.id,
            project_id=task.project_id,
        )

        await self._validate_project(task.project_id)
        project_orch = await self._get_or_create_project_orchestrator(task.project_id)

        # For now, we execute only in the primary project; dependency-aware
        # fan-out can be added later while preserving this contract (OCP).
        session_id = await project_orch.submit_task(task)
        self._session_to_project[session_id] = task.project_id

        await self._emit_task_submitted(task, session_id)
        return session_id

    async def get_task_result(self, session_id: str) -> Optional[TaskResult]:
        """
        Retrieve result from the appropriate ProjectOrchestrator.

        Delegates without knowing project details beyond the mapping.
        """
        project_id = self._session_to_project.get(session_id)
        if not project_id:
            self._logger.warning("Unknown session_id in MasterOrchestrator", session_id=session_id)
            return None

        project_orch = self._project_orchestrators.get(project_id)
        if not project_orch:
            self._logger.error(
                "Missing ProjectOrchestrator for known session",
                session_id=session_id,
                project_id=project_id,
            )
            return None

        return await project_orch.get_task_result(session_id)

    async def cancel_task(self, session_id: str) -> None:
        """
        Cancel a task running in one of the ProjectOrchestrators.
        """
        project_id = self._session_to_project.get(session_id)
        if not project_id:
            self._logger.warning("Unknown session_id for cancellation", session_id=session_id)
            return

        project_orch = self._project_orchestrators.get(project_id)
        if not project_orch:
            self._logger.warning(
                "No ProjectOrchestrator found for cancellation",
                session_id=session_id,
                project_id=project_id,
            )
            return

        await project_orch.cancel_task(session_id)

    # Internal Helpers ----------------------------------------------------

    async def _validate_project(self, project_id: str) -> None:
        """Ensure the project exists in the registry."""
        project = self._project_registry.get_project(project_id)
        if project is None:
            self._logger.error("Unknown project_id submitted", project_id=project_id)
            raise OrchestratorError(f"Unknown project_id: {project_id}")

    async def _get_or_create_project_orchestrator(self, project_id: str) -> ProjectOrchestrator:
        """
        Lazily create a ProjectOrchestrator for the given project_id.

        Keeps project-level orchestration separate from master logic (SRP).
        """
        if project_id in self._project_orchestrators:
            return self._project_orchestrators[project_id]

        if len(self._project_orchestrators) >= self._config.max_concurrent_projects:
            self._logger.error(
                "Max concurrent project orchestrators reached",
                max_projects=self._config.max_concurrent_projects,
            )
            raise OrchestratorError("Max concurrent project orchestrators reached")

        project_meta = self._project_registry.get_project(project_id)
        if project_meta is None:
            raise OrchestratorError(f"Unknown project_id: {project_id}")

        orchestrator = ProjectOrchestrator(
            orchestrator_id=f"project-{project_id}",
            project_id=project_id,
            message_bus=self._message_bus,
        )
        self._project_orchestrators[project_id] = orchestrator

        self._logger.info("Created ProjectOrchestrator", project_id=project_id)
        return orchestrator

    async def _emit_task_submitted(self, task: Task, session_id: str) -> None:
        """Emit a bus message indicating a task has been submitted."""
        message = AgentMessage(
            sender=self._id,
            receiver="*",
            task_id=task.id,
            payload={
                "event": "task_submitted",
                "project_id": task.project_id,
                "session_id": session_id,
            },
        )
        await self._message_bus.publish(message)
