"""
Agentic Development Platform - Project Orchestrator

Per-project orchestrator responsible for:
- Managing the agent pool for a single project.
- Selecting the appropriate agent using a strategy function.
- Executing tasks via agent T-A-O loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional
import asyncio
import uuid
import structlog

from core.orchestrators.base import IOrchestrator, Task, TaskResult, OrchestratorError
from core.agents.base import BaseAgent
from core.communication.message_bus import IMessageBus, AgentMessage

log = structlog.get_logger(__name__)


AgentSelector = Callable[[Task, Mapping[str, BaseAgent]], BaseAgent]


@dataclass
class ProjectOrchestratorConfig:
    """
    Configuration for ProjectOrchestrator.

    Keeps project-specific orchestration concerns localized.
    """
    default_agent_type: str = "code"
    result_timeout_seconds: float = 60.0


class ProjectOrchestrator(IOrchestrator):
    """
    Orchestrator for a single project implementing IOrchestrator.

    Responsibilities:
    - Holds and manages the agent pool for a given project.
    - Uses a pluggable strategy function to select agents per task
      (Strategy pattern).
    - Runs agent T-A-O loops in background tasks and tracks results.
    """

    def __init__(
        self,
        orchestrator_id: str,
        project_id: str,
        message_bus: IMessageBus,
        agents: Mapping[str, BaseAgent] | None = None,
        agent_selector: AgentSelector | None = None,
        config: ProjectOrchestratorConfig | None = None,
    ) -> None:
        """
        Initialize ProjectOrchestrator.

        Args:
            orchestrator_id: Identifier for this orchestrator instance.
            project_id: Project this orchestrator is responsible for.
            message_bus: Bus for agent-level notifications.
            agents: Optional pre-constructed agent pool keyed by type.
            agent_selector: Optional strategy function for selecting agents.
            config: Optional project-level configuration.
        """
        self._id = orchestrator_id
        self._project_id = project_id
        self._message_bus = message_bus
        self._config = config or ProjectOrchestratorConfig()
        self._agents: Dict[str, BaseAgent] = dict(agents or {})
        self._agent_selector: AgentSelector = agent_selector or self._default_agent_selector
        self._sessions: Dict[str, asyncio.Task[Dict[str, Any]]] = {}
        self._results: Dict[str, TaskResult] = {}

        self._logger = log.bind(
            orchestrator_id=orchestrator_id,
            project_id=project_id,
            layer="project_orchestrator",
        )
        self._logger.info("ProjectOrchestrator initialized")

    # IOrchestrator API ---------------------------------------------------

    @property
    def orchestrator_id(self) -> str:
        return self._id

    async def submit_task(self, task: Task) -> str:
        """
        Submit a task to be executed by one of the project agents.

        The method selects an agent using the configured strategy and launches
        its T-A-O loop as an asynchronous task.
        """
        if task.project_id != self._project_id:
            raise OrchestratorError(
                f"Task project_id {task.project_id} does not match orchestrator {self._project_id}"
            )

        self._logger.info("Submitting task to ProjectOrchestrator", task_id=task.id)

        agent = self._agent_selector(task, self._agents)
        session_id = str(uuid.uuid4())

        context = {
            "task_id": task.id,
            "project_root": task.parameters.get("project_root", "."),
            "priority": task.priority.name,
            "iteration": 0,
        }

        coro = self._run_agent_session(session_id, agent, task, context)
        task_handle: asyncio.Task[Dict[str, Any]] = asyncio.create_task(coro)
        self._sessions[session_id] = task_handle

        await self._emit_task_started(task, session_id, agent)
        return session_id

    async def get_task_result(self, session_id: str) -> Optional[TaskResult]:
        """
        Retrieve the result of a task.

        If the agent session is still running, this method returns None.
        """
        if session_id in self._results:
            return self._results[session_id]

        handle = self._sessions.get(session_id)
        if handle is None:
            self._logger.warning(
                "Unknown session_id in ProjectOrchestrator",
                session_id=session_id,
            )
            return None

        if not handle.done():
            return None

        # If completed but result not yet captured due to race, await and
        # rely on _run_agent_session to populate _results.
        try:
            await asyncio.wait_for(handle, timeout=0)
        except asyncio.TimeoutError:
            return None

        return self._results.get(session_id)

    async def cancel_task(self, session_id: str) -> None:
        """
        Best-effort cancellation of a running agent session.
        """
        handle = self._sessions.get(session_id)
        if handle is None:
            self._logger.warning(
                "Unknown session for cancellation in ProjectOrchestrator",
                session_id=session_id,
            )
            return

        if not handle.done():
            handle.cancel()
            self._logger.info("Cancelled agent session", session_id=session_id)

    # Agent Execution -----------------------------------------------------

    async def _run_agent_session(
        self,
        session_id: str,
        agent: BaseAgent,
        task: Task,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run the agent T-A-O loop and store the TaskResult.

        This is executed in a background task to avoid blocking orchestration.
        """
        self._logger.info(
            "Starting agent session",
            session_id=session_id,
            agent_id=agent.agent_id,
            task_id=task.id,
        )

        try:
            result_context = await agent.run_tao_loop(task.description, **context)
            task_result = TaskResult(
                task_id=task.id,
                project_id=self._project_id,
                session_id=session_id,
                success=result_context.get("status") == "completed",
                result=result_context,
                error=result_context.get("last_error"),
            )
            self._results[session_id] = task_result
            await self._emit_task_finished(task_result)

        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Agent session failed",
                session_id=session_id,
                agent_id=agent.agent_id,
                error=str(exc),
            )
            task_result = TaskResult(
                task_id=task.id,
                project_id=self._project_id,
                session_id=session_id,
                success=False,
                result=None,
                error=str(exc),
            )
            self._results[session_id] = task_result
            await self._emit_task_finished(task_result)

        return self._results[session_id].result or {}

    # Agent Selection Strategy --------------------------------------------

    def _default_agent_selector(self, task: Task, agents: Mapping[str, BaseAgent]) -> BaseAgent:
        """
        Default agent selection strategy.

        - If task.parameters['agent_type'] is provided and exists, use it.
        - Otherwise fall back to the configured default_agent_type.
        """
        requested_type = str(task.parameters.get("agent_type", "")).lower()
        if requested_type and requested_type in agents:
            return agents[requested_type]

        default_type = self._config.default_agent_type
        if default_type in agents:
            return agents[default_type]

        if not agents:
            raise OrchestratorError("No agents registered for project")

        # Deterministic fallback: pick the first agent in sorted order.
        first_key = sorted(agents.keys())[0]
        return agents[first_key]

    # Messaging -----------------------------------------------------------

    async def _emit_task_started(self, task: Task, session_id: str, agent: BaseAgent) -> None:
        """Emit a message indicating that a task has started."""
        message = AgentMessage(
            sender=self._id,
            receiver="*",
            task_id=task.id,
            payload={
                "event": "task_started",
                "project_id": self._project_id,
                "session_id": session_id,
                "agent_id": agent.agent_id,
            },
        )
        await self._message_bus.publish(message)

    async def _emit_task_finished(self, result: TaskResult) -> None:
        """Emit a message indicating that a task has finished."""
        message = AgentMessage(
            sender=self._id,
            receiver="*",
            task_id=result.task_id,
            payload={
                "event": "task_finished",
                "project_id": self._project_id,
                "session_id": result.session_id,
                "success": result.success,
            },
        )
        await self._message_bus.publish(message)
