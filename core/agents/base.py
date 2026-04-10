"""
Agentic Development Platform - Base Agent Abstraction

Abstract base class for all specialized agents implementing the T-A-O loop.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Protocol
import asyncio
import structlog

from core.mcp import ToolCall, ToolResult, IToolExecutor

log = structlog.get_logger(__name__)


class AgentPlatformError(Exception):
    """Base exception for agent platform errors."""
    pass


class AgentTimeoutError(AgentPlatformError):
    """Raised when an agent operation times out."""
    pass


class AgentExecutionError(AgentPlatformError):
    """Raised when an agent fails to execute an operation."""
    pass


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for an agent."""
    max_iterations: int = 15
    max_retries: int = 3
    timeout_seconds: float = 30.0
    scratchpad_enabled: bool = True


class IToolExecutor(Protocol):
    """Abstract tool executor interface - DIP over direct MCPClient."""

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        ...


@dataclass
class AgentState:
    """Current state of an agent during execution."""
    iteration: int = 0
    scratchpad_path: str = ""
    last_tool_result: ToolResult = None
    completed_steps: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents implementing the T-A-O loop.

    Responsibilities:
    - SRP: Encapsulates the T-A-O loop execution for a single agent type.
    - OCP: Concrete agents extend this without modifying base behavior.
    - LSP: Subclasses can be used in any context expecting BaseAgent.
    - ISP: Agents implement only the methods they need.
    - DIP: Depends on IToolExecutor, not concrete MCP implementation.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: 'ScratchpadManager',
        config: AgentConfig = None
    ) -> None:
        """
        Initialize a base agent.

        Args:
            agent_id: Unique identifier for the agent
            project_id: Project this agent operates on
            tools: Tool executor implementing IToolExecutor
            scratchpad: Scratchpad manager for task memory
            config: Agent configuration
        """
        self._agent_id = agent_id
        self._project_id = project_id
        self._tools = tools
        self._scratchpad = scratchpad
        self._config = config or AgentConfig()
        self._state = AgentState()
        self._logger = log.bind(agent_id=agent_id, project_id=project_id)

        self._logger.info("Agent initialized")

    @property
    def agent_id(self) -> str:
        """Get the agent ID."""
        return self._agent_id

    @property
    def project_id(self) -> str:
        """Get the project ID."""
        return self._project_id

    @property
    def tools(self) -> IToolExecutor:
        """Get the tool executor."""
        return self._tools

    @property
    def scratchpad(self) -> 'ScratchpadManager':
        """Get the scratchpad manager."""
        return self._scratchpad

    @property
    def config(self) -> AgentConfig:
        """Get the agent configuration."""
        return self._config

    @abstractmethod
    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cognitive phase: analyze the task and plan next actions.

        Args:
            task_description: Description of the task to be performed
            context: Additional context from previous steps

        Returns:
            Dictionary containing the plan for the next step
        """
        ...

    @abstractmethod
    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Action phase: decide what tool to use and with what parameters.

        Args:
            plan: Plan from the think phase
            context: Current context

        Returns:
            Tool call to be executed
        """
        ...

    @abstractmethod
    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observation phase: analyze the result of tool execution.

        Args:
            tool_result: Result from tool execution
            context: Current context

        Returns:
            Updated context including observations
        """
        ...

    async def run_tao_loop(self, task_description: str, **kwargs: Any) -> Dict[str, Any]:
        """
        T-A-O loop execution engine (Think → Act → Observe).

        Follows:
        - T-A-O pattern: structured execution of agent operations
        - Retry logic: handles transient failures
        - State management: maintains agent state across iterations
        - Timeout handling: prevents infinite loops

        Args:
            task_description: Description of the task to be performed
            **kwargs: Additional context

        Returns:
            Final result of agent execution
        """
        self._logger.info("Starting T-A-O loop", task_description=task_description)

        context = {
            "task_description": task_description,
            "iteration": 0,
            "max_iterations": self._config.max_iterations,
            **kwargs
        }

        while context["iteration"] < self._config.max_iterations:
            context["iteration"] += 1
            retry_count = 0

            # Think phase
            try:
                self._logger.info("Think phase", iteration=context["iteration"])
                plan = await self.think(task_description, context)

                # Act phase
                self._logger.info("Act phase", iteration=context["iteration"])
                tool_call = await self.act(plan, context)

                # Observe phase
                self._logger.info("Observe phase", iteration=context["iteration"])

                try:
                    tool_result = await asyncio.wait_for(
                        self._tools.execute_tool_call(tool_call),
                        timeout=self._config.timeout_seconds
                    )
                    context = await self.observe(tool_result, context)

                    # Record completed step
                    if context["iteration"] > len(self._state.completed_steps):
                        self._state.completed_steps.append(f"Iteration {context['iteration']}")

                    self._logger.info(
                        "TAO iteration completed",
                        iteration=context["iteration"],
                        completed_steps=len(self._state.completed_steps)
                    )

                except asyncio.TimeoutError:
                    self._logger.error("Tool execution timed out", timeout=self._config.timeout_seconds)
                    raise AgentTimeoutError(f"Tool execution timed out after {self._config.timeout_seconds} seconds")

                except Exception as e:
                    self._logger.error("Tool execution failed", error=str(e))
                    raise AgentExecutionError(f"Tool execution failed: {str(e)}")

            except AgentTimeoutError:
                raise
            except AgentExecutionError:
                raise
            except Exception as e:
                self._logger.error("Agent execution failed", error=str(e))
                retry_count += 1
                if retry_count >= self._config.max_retries:
                    self._logger.error(
                        "Maximum retries exceeded",
                        max_retries=self._config.max_retries,
                        iteration=context["iteration"]
                    )
                    raise AgentExecutionError(
                        f"Agent failed after {self._config.max_retries} retries: {str(e)}"
                    )

                self._logger.warning(
                    "Retrying agent execution",
                    retry_count=retry_count,
                    max_retries=self._config.max_retries
                )
                # Reset some context for retry
                context["needs_retry"] = True

        self._logger.info("TAO loop completed", iterations=context["iteration"])
        return context
