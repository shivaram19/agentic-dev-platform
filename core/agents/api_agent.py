"""
Agentic Development Platform - API Agent

Specialized agent responsible for calling and validating HTTP APIs for a
given project, without embedding transport or client-library details.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping
import json
import shlex
import structlog

from core.agents.base import BaseAgent, AgentConfig
from core.mcp.protocol import ToolCall, ToolResult, IToolExecutor
from core.scratchpad.scratchpad_manager import ScratchpadManager

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class APIAgentConfig(AgentConfig):
    """
    Configuration specific to APIAgent.

    Encapsulates HTTP/API concerns while keeping the base agent configuration
    generic and reusable (SRP, OCP).
    """
    default_method: str = "GET"
    default_timeout_seconds: float = 15.0
    allowed_methods: List[str] = field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE"]
    )
    base_url_overrides: Mapping[str, str] = field(default_factory=dict)


class APIAgent(BaseAgent):
    """
    HTTP API interaction agent implementing the T-A-O pattern.

    Responsibilities:
    - Request planning: derive HTTP method, URL, headers, and payload.
    - Request execution: delegate actual HTTP calls to an MCP shell tool
      (e.g., via curl) to keep the agent independent of HTTP clients (DIP).
    - Response interpretation: summarize results for orchestrators and
      persist key observations to the scratchpad.
    """

    def __init__(
        self,
        agent_id: str,
        project_id: str,
        tools: IToolExecutor,
        scratchpad: ScratchpadManager,
        config: APIAgentConfig | None = None,
    ) -> None:
        """
        Initialize APIAgent.

        Args:
            agent_id: Unique identifier for this agent instance.
            project_id: Project in whose context API calls are made.
            tools: Abstraction over MCP tool execution.
            scratchpad: Persistent task memory manager.
            config: Optional API-specific configuration.
        """
        # Override timeout with API-specific default if not explicitly set
        effective_config = config or APIAgentConfig()
        if effective_config.timeout_seconds == AgentConfig().timeout_seconds:
            object.__setattr__(effective_config, "timeout_seconds", effective_config.default_timeout_seconds)  # type: ignore[arg-type]

        super().__init__(agent_id, project_id, tools, scratchpad, effective_config)
        self._config: APIAgentConfig = self.config  # Narrow type
        self._logger = log.bind(agent_id=agent_id, project_id=project_id, agent_type="api")

        self._logger.info("APIAgent initialized")

    # THINK PHASE ---------------------------------------------------------

    async def think(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an API-related task and derive a concrete request plan.

        The returned plan is a plain dictionary, decoupling orchestrators
        from APIAgent internals (DIP, LSP).
        """
        self._logger.info("APIAgent THINK", task_description=task_description)

        method = self._infer_method(task_description)
        path = self._infer_path(task_description)
        base_url = self._resolve_base_url(context)
        url = self._join_url(base_url, path)
        headers = self._infer_headers(task_description, context)
        body = self._infer_body(task_description, context)

        plan: Dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "expect_status": self._infer_expected_status(task_description),
        }

        if self.config.scratchpad_enabled:
            await self.scratchpad.append_section(
                project_id=self.project_id,
                agent_id=self.agent_id,
                task_id=context.get("task_id", "unknown"),
                section="Plan",
                content=f"APIAgent plan: {plan}",
            )

        self._logger.info("API request plan created", method=method, url=url)
        return plan

    def _infer_method(self, task_description: str) -> str:
        """Infer HTTP method from natural language description."""
        text = task_description.lower()
        if "create" in text or "add " in text or "post " in text:
            return "POST"
        if "update" in text or "edit" in text or "put " in text:
            return "PUT"
        if "patch" in text:
            return "PATCH"
        if "delete" in text or "remove" in text:
            return "DELETE"
        return self._config.default_method

    def _infer_path(self, task_description: str) -> str:
        """Infer an API path from the description in a minimal, deterministic way."""
        text = task_description.lower()
        if "auth" in text or "login" in text:
            return "/api/auth/login"
        if "user" in text and "list" in text:
            return "/api/users"
        if "user" in text and ("detail" in text or "by id" in text):
            return "/api/users/{id}"
        if "health" in text:
            return "/health"
        return "/"

    def _resolve_base_url(self, context: Dict[str, Any]) -> str:
        """
        Resolve base URL from context or config.

        Keeps composition easy to reason about; does not embed environment
        discovery logic (KISS).
        """
        project_root = context.get("project_root", "")
        override = self._config.base_url_overrides.get(self.project_id)
        if override:
            return override.rstrip("/")
        # Fallback to a simple localhost convention
        return context.get("base_url", "http://localhost:8000").rstrip("/")

    def _join_url(self, base_url: str, path: str) -> str:
        """Join base URL and path safely."""
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base_url}{path}"

    def _infer_headers(self, task_description: str, context: Dict[str, Any]) -> Dict[str, str]:
        """Infer minimal headers for JSON-based APIs."""
        headers: Dict[str, str] = {
            "Accept": "application/json",
        }
        text = task_description.lower()
        if any(keyword in text for keyword in ("json", "payload", "body", "post", "put", "patch")):
            headers["Content-Type"] = "application/json"
        token = context.get("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _infer_body(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Infer a JSON body from context.

        The agent avoids guessing domain-specific shapes; higher layers can pass
        explicit 'body' in context when needed (YAGNI).
        """
        if "body" in context:
            return context["body"]
        if "payload" in context:
            return context["payload"]
        return None

    def _infer_expected_status(self, task_description: str) -> int:
        """Infer expected HTTP status code from the task description."""
        text = task_description.lower()
        if any(word in text for word in ("create", "add ")):
            return 201
        if any(word in text for word in ("delete", "remove")):
            return 204
        return 200

    # ACT PHASE -----------------------------------------------------------

    async def act(self, plan: Dict[str, Any], context: Dict[str, Any]) -> ToolCall:
        """
        Construct a ToolCall that executes an HTTP request via the shell MCP tool.

        Uses `curl` to avoid coupling the agent to a specific HTTP client
        library while still enabling rich HTTP behavior (DIP).
        """
        self._logger.info("APIAgent ACT", plan=plan)

        method = plan["method"].upper()
        if method not in self._config.allowed_methods:
            method = self._config.default_method

        url = plan["url"]
        headers: Dict[str, str] = plan["headers"]
        body: Dict[str, Any] | None = plan["body"]

        curl_parts: List[str] = ["curl", "-sS", "-X", shlex.quote(method)]

        for key, value in headers.items():
            curl_parts.extend(["-H", shlex.quote(f"{key}: {value}")])

        if body is not None:
            body_json = json.dumps(body)
            curl_parts.extend(["-d", shlex.quote(body_json)])

        curl_parts.append(shlex.quote(url))

        command = " ".join(curl_parts)

        arguments: Dict[str, Any] = {
            "command": command,
            "working_dir": context.get("project_root", "."),
            "timeout_seconds": float(self._config.timeout_seconds),
        }

        tool_call = ToolCall(
            id=f"{self.agent_id}-iter-{context['iteration']}",
            tool_name="shell.run",
            arguments=arguments,
        )

        self._logger.info("APIAgent tool call constructed", command=command, url=url)
        return tool_call

    # OBSERVE PHASE -------------------------------------------------------

    async def observe(self, tool_result: ToolResult, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret HTTP response and update the execution context.

        The ApiAgent only inspects the abstract ToolResult contract and
        remains unaware of how the shell server executed the command (DIP).
        """
        self._logger.info(
            "APIAgent OBSERVE",
            success=tool_result.success,
            iteration=context["iteration"],
        )

        if not tool_result.success:
            summary = self._build_failure_summary(tool_result)
            context["status"] = "failed"
            context["last_error"] = summary
            await self._record_observation(context, f"API call failed: {summary}")
            return context

        summary = self._build_success_summary(tool_result)
        context["status"] = "completed"
        context["api_response_summary"] = summary
        await self._record_observation(context, f"API call succeeded: {summary}")
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
        """Create a compact summary of an HTTP failure."""
        meta = tool_result.metadata or {}
        status = meta.get("status_code")
        stdout = (meta.get("stdout") or "")[:200]
        error = tool_result.error or "HTTP request failed"
        if status is not None:
            return f"status={status}, error={error}, body_snippet={stdout}"
        return f"error={error}, body_snippet={stdout}"

    def _build_success_summary(self, tool_result: ToolResult) -> str:
        """Create a compact summary of a successful HTTP response."""
        meta = tool_result.metadata or {}
        status = meta.get("status_code", 200)
        stdout = (meta.get("stdout") or "")[:200]
        return f"status={status}, body_snippet={stdout}"
