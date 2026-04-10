"""
Agentic Development Platform - Code Agent

Specialized agent for code generation and modification tasks.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult, IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CodeAgentConfig(AgentConfig):
    """Configuration specific to CodeAgent."""
    file_patterns: List[str] = field(
        default_factory=lambda: [
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".cxx",
            ".c",
            ".h",
            ".hpp",
            ".html",
            ".css",
            ".scss",
            ".less",
        ]
    )
    max_file_size_kb: int = 512
    language_rules: Dict[str, str] = field(
        default_factory=lambda: {
            "python": "PEP8",
            "javascript": "ESLint",
            "typescript": "TSLint",
            "java": "Google Java Style",
        }
    )


class CodeAgent(BaseAgent):
    """
    Code generation and modification agent implementing the T-A-O pattern.

    Responsibilities:
    - Code generation: creates new code files based on requirements.
    - Code modification: updates existing code safely.
    - Basic review: performs light-weight quality checks.
    - Dependency awareness: respects project structure and imports.

    This class extends BaseAgent and can be used anywhere a BaseAgent is
    expected (LSP).
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
        config: CodeAgentConfig | None = None,
    ) -> None:
        """
        Initialize CodeAgent.

        Args:
            agent_id: Unique identifier for the agent.
            project_id: Project this agent operates on.
            tools: Tool executor implementing IToolExecutor.
            scratchpad: Scratchpad manager for task memory.
            config: Code agent configuration.
        """
        super().__init__(agent_id, project_id, tools, scratchpad, config or CodeAgentConfig())
        self._config: CodeAgentConfig = self.config  # Narrowed type
        self._logger = log.bind(agent_id=agent_id, project_id=project_id, agent_type="code")

        self._logger.info("CodeAgent initialized", file_patterns=self._config.file_patterns)

    # THINK PHASE ---------------------------------------------------------

    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a code-related task and produce a concrete implementation plan.

        The plan remains a simple dictionary so that ProjectOrchestrator
        and workflows do not depend on CodeAgent internals (DIP).
        """
        self._logger.info("CodeAgent THINK", task_description=task_description)

        # In a full system this would use LLMs and project metadata; here we keep it deterministic.
        requirements = self._extract_requirements(task_description)
        change_type = self._classify_change_type(requirements)
        target_language = requirements.get("language", "python")
        target_path = requirements.get("target_path", "src/auto_generated.py")

        plan: Dict[str, Any] = {
            "change_type": change_type,
            "requirements": requirements,
            "target_language": target_language,
            "target_path": target_path,
            "validation": self._build_validation_plan(change_type),
            "backup": self._build_backup_plan(change_type),
        }

        if self.config.scratchpad_enabled:
            await self.scratchpad.append_section(
                project_id=self.project_id,
                agent_id=self.agent_id,
                task_id=context.get("task_id", "unknown"),
                section="Plan",
                content=f"CodeAgent plan: {plan}",
            )

        self._logger.info("CodeAgent plan created", plan_summary=plan)
        return plan

    def _extract_requirements(self, task_description: str) -> Dict[str, Any]:
        """Very small deterministic parser for requirements."""
        description_lower = task_description.lower()
        language = "python"
        if "typescript" in description_lower or "ts " in description_lower:
            language = "typescript"
        elif "javascript" in description_lower or "node" in description_lower:
            language = "javascript"
        elif "java" in description_lower:
            language = "java"

        change_type = "modify"
        if "new" in description_lower or "create" in description_lower or "add" in description_lower:
            change_type = "generate"
        if "refactor" in description_lower:
            change_type = "refactor"

        return {
            "raw": task_description,
            "language": language,
            "change_type": change_type,
        }

    def _classify_change_type(self, requirements: Dict[str, Any]) -> str:
        """Classify change type from requirements."""
        return requirements.get("change_type", "modify")

    def _build_validation_plan(self, change_type: str) -> Dict[str, Any]:
        """Build a simple validation strategy."""
        if change_type == "generate":
            return {"run_unit_tests": False, "run_lint": True}
        if change_type == "refactor":
            return {"run_unit_tests": True, "run_lint": True}
        return {"run_unit_tests": True, "run_lint": True}

    def _build_backup_plan(self, change_type: str) -> Dict[str, Any]:
        """Build a simple backup strategy."""
        return {
            "git_checkpoint": True,
            "checkpoint_label": f"code-agent-{change_type}",
        }

    # ACT PHASE -----------------------------------------------------------

    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Decide which MCP tool to invoke and with which parameters.

        The CodeAgent only knows tool *contracts* (names and argument shapes),
        not how they are implemented (that is delegated to the MCP layer).
        """
        self._logger.info("CodeAgent ACT", plan=plan)

        change_type = plan["change_type"]
        target_path = plan["target_path"]
        language = plan["target_language"]

        if change_type == "generate":
            tool_name = "filesystem.write_file"
            arguments = await self._build_generate_arguments(plan, target_path, language)
        elif change_type == "refactor":
            tool_name = "filesystem.write_file"
            arguments = await self._build_refactor_arguments(plan, target_path, language)
        else:
            tool_name = "filesystem.write_file"
            arguments = await self._build_modify_arguments(plan, target_path, language)

        tool_call = ToolCall(
            id=f"{self.agent_id}-iter-{context['iteration']}",
            tool_name=tool_name,
            arguments=arguments,
        )

        self._logger.info("CodeAgent tool selected", tool_name=tool_name, target_path=target_path)
        return tool_call

    async def _build_generate_arguments(
        self,
        plan: Dict[str, Any],
        target_path: str,
        language: str,
    ) -> Dict[str, Any]:
        """Build arguments for generating a new file."""
        content = self._generate_scaffold(plan["requirements"], language)
        return {
            "path": target_path,
            "content": content,
            "overwrite": False,
        }

    async def _build_modify_arguments(
        self,
        plan: Dict[str, Any],
        target_path: str,
        language: str,
    ) -> Dict[str, Any]:
        """Build arguments for modifying an existing file."""
        patch = self._generate_patch(plan["requirements"], language)
        return {
            "path": target_path,
            "patch": patch,
            "create_if_missing": True,
        }

    async def _build_refactor_arguments(
        self,
        plan: Dict[str, Any],
        target_path: str,
        language: str,
    ) -> Dict[str, Any]:
        """Build arguments for refactoring an existing file."""
        refactor_instructions = self._generate_refactor_instructions(plan["requirements"], language)
        return {
            "path": target_path,
            "refactor_instructions": refactor_instructions,
            "create_backup": True,
        }

    def _generate_scaffold(self, requirements: Dict[str, Any], language: str) -> str:
        """Generate a minimal but valid scaffold for a new file."""
        if language == "python":
            return (
                '"""Auto-generated by CodeAgent.\n\n'
                f'Original request: {requirements["raw"]}\n'
                '"""\n\n'
                "def main() -> None:\n"
                '    """Entry point for generated module."""\n'
                "    pass\n\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if language == "javascript":
            return (
                "// Auto-generated by CodeAgent\n"
                f"// Original request: {requirements['raw']}\n\n"
                "export function main() {\n"
                "  // Entry point for generated module\n"
                "}\n"
            )
        if language == "typescript":
            return (
                "// Auto-generated by CodeAgent\n"
                f"// Original request: {requirements['raw']}\n\n"
                "export function main(): void {\n"
                "  // Entry point for generated module\n"
                "}\n"
            )
        if language == "java":
            return (
                "// Auto-generated by CodeAgent\n"
                f"// Original request: {requirements['raw']}\n\n"
                "public class GeneratedModule {\n"
                "    public static void main(String[] args) {\n"
                "        // Entry point for generated module\n"
                "    }\n"
                "}\n"
            )
        # Fallback scaffold
        return f"// Auto-generated file\n// Original request: {requirements['raw']}\n"

    def _generate_patch(self, requirements: Dict[str, Any], language: str) -> str:
        """
        Generate a simple textual patch description.

        The actual application of the patch is the responsibility of the
        filesystem MCP server, which interprets this string.
        """
        return f"apply change described by: {requirements['raw']} (language={language})"

    def _generate_refactor_instructions(self, requirements: Dict[str, Any], language: str) -> str:
        """Generate human-readable refactor instructions."""
        return f"refactor code to better satisfy request: {requirements['raw']} (language={language})"

    # OBSERVE PHASE -------------------------------------------------------

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observe the result of the MCP tool execution and update context.

        The CodeAgent uses only the abstract ToolResult contract and remains
        unaware of transport or tool implementation details (DIP).
        """
        self._logger.info(
            "CodeAgent OBSERVE",
            success=tool_result.success,
            iteration=context["iteration"],
        )

        if not tool_result.success:
            error_message = tool_result.error or "Unknown error from tool"
            await self._record_observation(
                context,
                f"Tool execution failed: {error_message}",
            )
            context["last_error"] = error_message
            context["status"] = "failed"
            return context

        summary = self._summarize_tool_output(tool_result)
        await self._record_observation(context, f"Tool execution succeeded: {summary}")

        context["last_result"] = summary
        context["status"] = "completed"
        return context

    async def _record_observation(self, context: Dict[str, Any], observation: str) -> None:
        """Record an observation into the scratchpad if enabled."""
        if not self.config.scratchpad_enabled:
            return

        await self.scratchpad.append_section(
            project_id=self.project_id,
            agent_id=self.agent_id,
            task_id=context.get("task_id", "unknown"),
            section="Observations",
            content=observation,
        )

    def _summarize_tool_output(self, tool_result: ToolResult) -> str:
        """Create a compact textual summary of the tool result."""
        meta = tool_result.metadata or {}
        path_info = meta.get("path") or meta.get("file") or "n/a"
        operation = meta.get("operation", "unknown")
        return f"operation={operation}, path={path_info}"
