"""
Agentic Development Platform - Test Agent

Specialized agent responsible for planning and executing automated tests.
"""

from dataclasses import dataclass
from typing import Any, Dict, List
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult, IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TestAgentConfig(AgentConfig):
    """
    Configuration specific to TestAgent.

    Keeps test concerns separate from the generic agent configuration (SRP).
    """
    default_test_command: str = "pytest"
    default_test_path: str = "tests"
    fail_fast: bool = True
    additional_args: List[str] | None = None


class TestAgent(BaseAgent):
    """
    Automated test execution agent implementing the T-A-O pattern.

    Responsibilities:
    - Test planning: decides which tests to run for a given task.
    - Test execution: invokes the MCP shell/filesystem tools to run tests.
    - Result interpretation: summarizes failures and success conditions.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
        config: TestAgentConfig | None = None,
    ) -> None:
        """
        Initialize TestAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
            project_id: Target project for which tests are executed.
            tools: Abstraction over MCP tool execution.
            scratchpad: Persistent task memory manager.
            config: Optional test-specific configuration.
        """
        super().__init__(agent_id, project_id, tools, scratchpad, config or TestAgentConfig())
        self._config: TestAgentConfig = self.config  # Narrow type
        self._logger = log.bind(agent_id=agent_id, project_id=project_id, agent_type="test")

        self._logger.info("TestAgent initialized")

    # THINK PHASE ---------------------------------------------------------

    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the development task and derive an explicit test plan.

        Returns a serializable plan dictionary that higher layers can inspect
        without depending on TestAgent internals (DIP).
        """
        self._logger.info("TestAgent THINK", task_description=task_description)

        scope = self._infer_test_scope(task_description, context)
        selector = self._infer_test_selector(task_description, scope)

        plan: Dict[str, Any] = {
            "scope": scope,
            "selector": selector,
            "command": self._config.default_test_command,
            "path": self._config.default_test_path,
            "fail_fast": self._config.fail_fast,
            "additional_args": self._config.additional_args or [],
        }

        if self.config.scratchpad_enabled:
            await self.scratchpad.append_section(
                project_id=self.project_id,
                agent_id=self.agent_id,
                task_id=context.get("task_id", "unknown"),
                section="Plan",
                content=f"TestAgent plan: {plan}",
            )

        self._logger.info("Test plan created", plan_summary=plan)
        return plan

    def _infer_test_scope(self, task_description: str, context: Dict[str, Any]) -> str:
        """
        Infer whether to run unit, integration, or full test suite.

        The heuristic is intentionally simple and explainable (KISS).
        """
        text = task_description.lower()
        if "integration" in text or "end-to-end" in text or "e2e" in text:
            return "integration"
        if "unit" in text:
            return "unit"
        if "smoke" in text:
            return "smoke"
        return "auto"

    def _infer_test_selector(self, task_description: str, scope: str) -> str:
        """
        Derive a pytest-style selector expression from the task description.
        """
        text = task_description.lower()
        if "auth" in text or "login" in text:
            return "auth"
        if "user" in text:
            return "user"
        if "api" in text:
            return "api"
        if scope == "smoke":
            return "smoke"
        return ""

    # ACT PHASE -----------------------------------------------------------

    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Construct a ToolCall to execute tests via the MCP shell server.

        The agent does not know how tests are actually executed; it only
        constructs a command specification (DIP).
        """
        self._logger.info("TestAgent ACT", plan=plan)

        base_command = plan["command"]
        path = plan["path"]
        scope = plan["scope"]
        selector = plan["selector"]
        fail_fast = plan["fail_fast"]
        additional_args = list(plan.get("additional_args") or [])

        args: List[str] = [base_command, path]

        if fail_fast:
            args.append("--maxfail=1")
        if scope == "integration":
            args.append("-m")
            args.append("integration")
        elif scope == "unit":
            args.append("-m")
            args.append("unit")
        elif scope == "smoke":
            args.append("-m")
            args.append("smoke")

        if selector:
            args.append("-k")
            args.append(selector)

        args.extend(additional_args)

        arguments: Dict[str, Any] = {
            "command": " ".join(args),
            "working_dir": context.get("project_root", "."),
            "timeout_seconds": float(self.config.timeout_seconds),
        }

        tool_call = ToolCall(
            id=f"{self.agent_id}-iter-{context['iteration']}",
            tool_name="shell.run",
            arguments=arguments,
        )

        self._logger.info(
            "TestAgent tool call constructed",
            command=arguments["command"],
            working_dir=arguments["working_dir"],
        )
        return tool_call

    # OBSERVE PHASE -------------------------------------------------------

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret test run results and update the execution context.
        """
        self._logger.info(
            "TestAgent OBSERVE",
            success=tool_result.success,
            iteration=context["iteration"],
        )

        if not tool_result.success:
            summary = self._build_failure_summary(tool_result)
            context["status"] = "failed"
            context["last_error"] = summary
            await self._record_observation(context, f"Tests failed: {summary}")
            return context

        summary = self._build_success_summary(tool_result)
        context["status"] = "completed"
        context["test_summary"] = summary
        await self._record_observation(context, f"Tests succeeded: {summary}")
        return context

    async def _record_observation(self, context: Dict[str, Any], observation: str) -> None:
        """Persist a human-readable observation into the scratchpad."""
        if not self.config.scratchpad_enabled:
            return

        await self.scratchpad.append_section(
            project_id=self.project_id,
            agent_id=self.agent_id,
            task_id=context.get("task_id", "unknown"),
            section="Observations",
            content=observation,
        )

    def _build_failure_summary(self, tool_result: ToolResult) -> str:
        """Create a compact summary of failing test output."""
        meta = tool_result.metadata or {}
        return meta.get("summary") or tool_result.error or "Tests failed"

    def _build_success_summary(self, tool_result: ToolResult) -> str:
        """Create a compact summary of successful test output."""
        meta = tool_result.metadata or {}
        return meta.get("summary") or "All tests passed"


# Implementation of async test execution patterns is compatible with pytest-asyncio[cite:70].
