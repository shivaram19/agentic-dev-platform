"""
Agentic Development Platform - Agent Pool.

Manages the lifecycle of specialist agents for a single project.

SRP : This class ONLY manages agent registration, lookup, and cleanup.
      It does NOT orchestrate task execution (that is ProjectOrchestrator's job).
DIP : Depends on BaseAgent abstraction, not concrete agent types.
OCP : New agent types register themselves — no switch/if chains here.
"""

from typing import Dict, Type
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


class AgentPoolError(Exception):
    """Raised when AgentPool operations fail."""


class AgentPool:
    """
    Registry and factory for all specialist agents in a project.

    Usage:
        pool = AgentPool(project_id="medicine-mgmt", tools=..., scratchpad=...)
        pool.register(AgentType.CODE, CodeAgent)
        agent = pool.get("code")
    """

    def __init__(
        self,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
    ) -> None:
        """
        Args:
            project_id:  Project this pool belongs to.
            tools:       Shared tool executor injected into every agent.
            scratchpad:  Shared scratchpad manager injected into every agent.
        """
        self._project_id = project_id
        self._tools = tools
        self._scratchpad = scratchpad
        self._registry: Dict[str, Type[BaseAgent]] = {}
        self._instances: Dict[str, BaseAgent] = {}
        self._logger = log.bind(project_id=project_id)

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Register an agent class under a given type key.

        Args:
            agent_type:  Short string key, e.g. "code", "test", "db".
            agent_class: Concrete class that extends BaseAgent.

        Raises:
            AgentPoolError: If agent_type is already registered.
        """
        if agent_type in self._registry:
            raise AgentPoolError(
                f"Agent type '{agent_type}' is already registered in pool "
                f"for project '{self._project_id}'."
            )
        self._registry[agent_type] = agent_class
        self._logger.info("AgentPool.registered", agent_type=agent_type)

    # ── Retrieval / lazy instantiation ───────────────────────────────────

    def get(self, agent_type: str, config: AgentConfig | None = None) -> BaseAgent:
        """
        Return a live agent instance for the given type.

        Instances are created lazily on first access and cached.

        Args:
            agent_type: Key used during register().
            config:     Optional config override for first-time creation.

        Returns:
            A BaseAgent instance (concrete type hidden from caller — LSP).

        Raises:
            AgentPoolError: If agent_type was never registered.
        """
        if agent_type not in self._registry:
            raise AgentPoolError(
                f"No agent registered for type '{agent_type}' in project "
                f"'{self._project_id}'. Did you call pool.register() first?"
            )

        if agent_type not in self._instances:
            agent_class = self._registry[agent_type]
            agent_id = f"{self._project_id}-{agent_type}-agent"
            instance = agent_class(
                agent_id=agent_id,
                project_id=self._project_id,
                tools=self._tools,
                scratchpad=self._scratchpad,
                config=config,
            )
            self._instances[agent_type] = instance
            self._logger.info("AgentPool.instantiated", agent_type=agent_type, agent_id=agent_id)

        return self._instances[agent_type]

    # ── Inspection ────────────────────────────────────────────────────────

    def registered_types(self) -> list[str]:
        """Return all registered agent type keys."""
        return list(self._registry.keys())

    def active_instances(self) -> list[str]:
        """Return agent type keys that have live instances."""
        return list(self._instances.keys())

    # ── Cleanup ───────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """
        Release all cached agent instances.

        Call this when the project session ends to free resources.
        """
        self._logger.info(
            "AgentPool.shutdown",
            active_agents=list(self._instances.keys()),
        )
        self._instances.clear()