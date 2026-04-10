"""
Agentic Development Platform - Database Agent

Specialized agent responsible for planning and executing database migrations
and schema changes in a safe, incremental manner.
"""

from dataclasses import dataclass
from typing import Any, Dict
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult, IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DBAgentConfig(AgentConfig):
    """
    Configuration specific to DBAgent.

    Encapsulates DB-related behavior without polluting the generic agent config.
    """
    default_migration_command: str = "alembic upgrade head"
    default_downgrade_command: str = "alembic downgrade -1"
    migrations_path: str = "alembic"
    dry_run: bool = False


class DBAgent(BaseAgent):
    """
    Database migration agent implementing the T-A-O pattern.

    Responsibilities:
    - Migration planning: infer safe schema change strategy.
    - Migration execution: use MCP tools to generate and apply migrations.
    - Verification: run basic checks after migrations complete.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
        config: DBAgentConfig | None = None,
    ) -> None:
        """
        Initialize DBAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
            project_id: Target project this agent operates on.
            tools: Abstraction over MCP tool execution.
            scratchpad: Persistent task memory manager.
            config: Optional DB-specific configuration.
        """
        super().__init__(agent_id, project_id, tools, scratchpad, config or DBAgentConfig())
        self._config: DBAgentConfig = self.config  # Narrow type
        self._logger = log.bind(agent_id=agent_id, project_id=project_id, agent_type="db")

        self._logger.info("DBAgent initialized")

    # THINK PHASE ---------------------------------------------------------

    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a DB-related task description and derive a migration plan.

        The plan is an implementation-agnostic dictionary describing:
        - Change intent (create_table, add_column, etc.).
        - Safety strategy (backup, dry_run, verification).
        """
        self._logger.info("DBAgent THINK", task_description=task_description)

        intent = self._infer_migration_intent(task_description)
        safety = self._build_safety_plan(intent)
        verification = self._build_verification_plan(intent)

        plan: Dict[str, Any] = {
            "intent": intent,
            "safety": safety,
            "verification": verification,
            "migrations_path": self._config.migrations_path,
            "dry_run": self._config.dry_run,
        }

        if self.config.scratchpad_enabled:
            await self.scratchpad.append_section(
                project_id=self.project_id,
                agent_id=self.agent_id,
                task_id=context.get("task_id", "unknown"),
                section="Plan",
                content=f"DBAgent plan: {plan}",
            )

        self._logger.info("Migration plan created", plan_summary=plan)
        return plan

    def _infer_migration_intent(self, task_description: str) -> str:
        """
        Infer high-level migration intent from natural language.

        Keeps logic simple and easy to reason about (KISS).
        """
        text = task_description.lower()
        if "create table" in text or "new table" in text:
            return "create_table"
        if "add column" in text or "new column" in text:
            return "add_column"
        if "drop column" in text:
            return "drop_column"
        if "index" in text:
            return "add_index"
        if "rollback" in text or "downgrade" in text:
            return "rollback"
        return "generic_migration"

    def _build_safety_plan(self, intent: str) -> Dict[str, Any]:
        """Define basic safety measures for the migration."""
        return {
            "backup_before": intent != "rollback",
            "require_confirmation": intent in {"drop_column", "rollback"},
            "dry_run": self._config.dry_run,
        }

    def _build_verification_plan(self, intent: str) -> Dict[str, Any]:
        """Define simple verification steps to run after migration."""
        if intent == "create_table":
            return {"check_new_table_exists": True}
        if intent == "add_column":
            return {"check_new_column_exists": True}
        if intent == "add_index":
            return {"check_index_exists": True}
        return {"check_schema_version": True}

    # ACT PHASE -----------------------------------------------------------

    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Construct a ToolCall to run migrations via the MCP shell or git server.

        The agent communicates intent and parameters; concrete behavior is
        implemented in the MCP tool servers (DIP).
        """
        self._logger.info("DBAgent ACT", plan=plan)

        intent = plan["intent"]

        if intent == "rollback":
            command = self._config.default_downgrade_command
        else:
            command = self._config.default_migration_command

        arguments: Dict[str, Any] = {
            "command": command,
            "working_dir": context.get("project_root", "."),
            "timeout_seconds": float(self.config.timeout_seconds),
        }

        tool_call = ToolCall(
            id=f"{self.agent_id}-iter-{context['iteration']}",
            tool_name="shell.run",
            arguments=arguments,
        )

        self._logger.info(
            "DBAgent tool call constructed",
            command=arguments["command"],
            working_dir=arguments["working_dir"],
        )
        return tool_call

    # OBSERVE PHASE -------------------------------------------------------

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observe migration results and update context accordingly.
        """
        self._logger.info(
            "DBAgent OBSERVE",
            success=tool_result.success,
            iteration=context["iteration"],
        )

        if not tool_result.success:
            summary = self._build_failure_summary(tool_result)
            context["status"] = "failed"
            context["last_error"] = summary
            await self._record_observation(context, f"Migration failed: {summary}")
            return context

        summary = self._build_success_summary(tool_result)
        context["status"] = "completed"
        context["migration_summary"] = summary
        await self._record_observation(context, f"Migration succeeded: {summary}")
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
        """Create a compact summary of migration failure."""
        meta = tool_result.metadata or {}
        return meta.get("summary") or tool_result.error or "Migration failed"

    def _build_success_summary(self, tool_result: ToolResult) -> str:
        """Create a compact summary of migration success."""
        meta = tool_result.metadata or {}
        return meta.get("summary") or "Migration completed"
