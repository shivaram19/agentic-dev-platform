"""
Agentic Development Platform - Security Agent

Specialized agent responsible for orchestrating application security checks,
including static code analysis and dependency vulnerability scanning.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult, IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SecurityAgentConfig(AgentConfig):
    """
    Configuration specific to SecurityAgent.

    Encapsulates security tooling choices and policies such as which scanners
    to run and what severity thresholds to enforce.
    """
    run_static_analysis: bool = True
    run_dependency_scan: bool = True
    static_tool_command: str = "bandit -r . -f json"
    dependency_tool_command: str = "safety scan --json"
    fail_on_high: bool = True
    excluded_paths: List[str] = field(default_factory=lambda: ["tests", ".venv"])


class SecurityAgent(BaseAgent):
    """
    Application security agent implementing the T-A-O pattern.

    Responsibilities:
    - Security plan: decide which scanners to run for a given task.
    - Scanner execution: delegate execution to MCP shell tools.
    - Policy evaluation: interpret results against configured thresholds.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
        config: SecurityAgentConfig | None = None,
    ) -> None:
        """
        Initialize SecurityAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
            project_id: Project whose security posture is being assessed.
            tools: Abstraction over MCP tool execution.
            scratchpad: Persistent task memory manager.
            config: Optional security-specific configuration.
        """
        super().__init__(agent_id, project_id, tools, scratchpad, config or SecurityAgentConfig())
        self._config: SecurityAgentConfig = self.config  # Narrow type
        self._logger = log.bind(agent_id=agent_id, project_id=project_id, agent_type="security")

        self._logger.info("SecurityAgent initialized")

    # THINK PHASE ---------------------------------------------------------

    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the development task and derive a security scan plan.

        The plan is expressed as a dictionary of which tools to run and with
        what policies, decoupled from specific scanner implementations.
        """
        self._logger.info("SecurityAgent THINK", task_description=task_description)

        scope = self._infer_scope(task_description)
        run_static = self._config.run_static_analysis and scope in {"auto", "static"}
        run_deps = self._config.run_dependency_scan and scope in {"auto", "dependencies"}

        plan: Dict[str, Any] = {
            "scope": scope,
            "run_static_analysis": run_static,
            "run_dependency_scan": run_deps,
            "static_tool_command": self._build_static_command(),
            "dependency_tool_command": self._build_dependency_command(),
            "fail_on_high": self._config.fail_on_high,
        }

        if self.config.scratchpad_enabled:
            await self.scratchpad.append_section(
                project_id=self.project_id,
                agent_id=self.agent_id,
                task_id=context.get("task_id", "unknown"),
                section="Plan",
                content=f"SecurityAgent plan: {plan}",
            )

        self._logger.info(
            "Security scan plan created",
            run_static_analysis=run_static,
            run_dependency_scan=run_deps,
        )
        return plan

    def _infer_scope(self, task_description: str) -> str:
        """
        Infer security scan scope from natural language description.

        Returns one of: "auto", "static", "dependencies".
        """
        text = task_description.lower()
        if "static" in text or "code scan" in text:
            return "static"
        if "dependency" in text or "supply chain" in text:
            return "dependencies"
        return "auto"

    def _build_static_command(self) -> str:
        """
        Build a Bandit command for static analysis.

        Bandit is a widely used Python security scanner for AST-based checks.[web:165][web:171]
        """
        cmd = self._config.static_tool_command
        if self._config.excluded_paths:
            excluded = ",".join(self._config.excluded_paths)
            cmd = f"{cmd} -x {excluded}"
        return cmd

    def _build_dependency_command(self) -> str:
        """
        Build a Safety CLI command for dependency vulnerability scanning.

        Safety scans Python dependencies against a vulnerability database.[web:163][web:166][web:175]
        """
        return self._config.dependency_tool_command

    # ACT PHASE -----------------------------------------------------------

    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Construct a ToolCall for the appropriate security scanner.

        For simplicity and composability, the SecurityAgent runs one scanner
        per T-A-O iteration; orchestrators can invoke multiple iterations
        to chain tools when necessary.
        """
        self._logger.info("SecurityAgent ACT", plan=plan)

        # Decide which scanner to run on this iteration
        iteration = context["iteration"]
        run_static = plan["run_static_analysis"]
        run_deps = plan["run_dependency_scan"]

        if run_static and (iteration % 2 == 1 or not run_deps):
            command = plan["static_tool_command"]
            phase = "static"
        elif run_deps:
            command = plan["dependency_tool_command"]
            phase = "dependencies"
        else:
            # Nothing to run; no-op that still keeps the contract.
            command = "true"
            phase = "noop"

        arguments: Dict[str, Any] = {
            "command": command,
            "working_dir": context.get("project_root", "."),
            "timeout_seconds": float(self.config.timeout_seconds),
        }

        tool_call = ToolCall(
            id=f"{self.agent_id}-iter-{iteration}",
            tool_name="shell.run",
            arguments=arguments,
        )

        self._logger.info(
            "SecurityAgent tool call constructed",
            phase=phase,
            command=command,
            working_dir=arguments["working_dir"],
        )
        # Persist which phase we executed to interpret results later
        context["security_phase"] = phase
        return tool_call

    # OBSERVE PHASE -------------------------------------------------------

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret security scan results and update context.

        Applies a simple pass/fail policy based on severity thresholds,
        leaving detailed reporting to the MCP tool layer.
        """
        phase = context.get("security_phase", "unknown")
        self._logger.info(
            "SecurityAgent OBSERVE",
            success=tool_result.success,
            phase=phase,
            iteration=context["iteration"],
        )

        if not tool_result.success:
            summary = self._build_failure_summary(tool_result, phase)
            context["status"] = "failed"
            context["last_error"] = summary
            await self._record_observation(context, f"Security scan failed ({phase}): {summary}")
            return context

        violated_policy, summary = self._evaluate_policy(tool_result, phase)

        if violated_policy and self._config.fail_on_high:
            context["status"] = "failed"
            context["last_error"] = summary
            await self._record_observation(
                context,
                f"Security policy violated ({phase}): {summary}",
            )
        else:
            context["status"] = "completed"
            key = "static_scan_summary" if phase == "static" else "dependency_scan_summary"
            context[key] = summary
            await self._record_observation(
                context,
                f"Security scan passed ({phase}): {summary}",
            )

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

    def _build_failure_summary(self, tool_result: ToolResult, phase: str) -> str:
        """Create a compact summary of scanner failure."""
        meta = tool_result.metadata or {}
        stdout = (meta.get("stdout") or "")[:200]
        error = tool_result.error or "Security tool failed"
        return f"phase={phase}, error={error}, output_snippet={stdout}"

    def _evaluate_policy(self, tool_result: ToolResult, phase: str) -> tuple[bool, str]:
        """
        Evaluate scanner output against a simple high-severity policy.

        The ToolResult metadata is expected to carry a structured summary
        when available; otherwise we fall back to plain text output.
        """
        meta = tool_result.metadata or {}
        high_count = int(meta.get("high_issues", 0))
        critical_count = int(meta.get("critical_issues", 0))
        stdout = (meta.get("stdout") or "")[:200]

        if critical_count > 0 or (self._config.fail_on_high and high_count > 0):
            summary = (
                f"critical={critical_count}, high={high_count}, "
                f"phase={phase}, output_snippet={stdout}"
            )
            return True, summary

        summary = (
            f"no blocking issues, critical={critical_count}, high={high_count}, "
            f"phase={phase}"
        )
        return False, summary
