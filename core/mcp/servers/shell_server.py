"""
Agentic Development Platform - MCP Shell Server

MCP server that exposes shell command execution capabilities, for example:
- run, stream, or wait for a command
- enforce timeouts and working directory

This layer keeps the MCP‑wire‑protocol logic separate from agents and
orchestrators (Single Responsibility + DIP).[web:199][web:203]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping
import asyncio
import shlex
from typing_extensions import TypeAlias

from aiohttp import web
from aiohttp.web import WebSocketResponse

from core.mcp.protocol import ToolCall, ToolResult

log = web.Application.logger.getChild("shell_server")

ToolContext: TypeAlias = Dict[str, Any]


@dataclass(frozen=True)
class ShellServerConfig:
    """
    Configuration for the shell server.

    Encapsulates resource constraints and security policy, keeping protocol
    and execution decoupled.
    """
    default_timeout_seconds: float = 30.0
    max_timeout_seconds: float = 300.0
    allowed_working_dirs: list[str] = field(default_factory=lambda: ["."])
    allow_any_working_dir: bool = False
    max_env_vars: int = 100


class ShellServer:
    """
    MCP Shell Server that exposes command execution to the MCP tool layer.

    Responsibilities:
    - Command validation and sandboxing.
    - Execution with configurable timeout and working directory.
    - Structured result formatting for the MCP client.
    """

    def __init__(self, config: ShellServerConfig) -> None:
        """
        Initialize the shell server.

        Args:
            config: Shell server configuration.
        """
        self._config = config
        self._logger = log.getChild("ShellServer")
        self._logger.info("ShellServer initialized")

    def register_routes(self, app: web.Application) -> None:
        """Register MCP shell routes into the given web application."""
        prefix = "/mcp/shell"

        app.router.add_post(f"{prefix}/run", self._handle_run)
        app.router.add_post(f"{prefix}/run_stream", self._handle_run_stream)

        self._logger.info("ShellServer routes registered", prefix=prefix)

    # Handlers ------------------------------------------------------------

    async def _handle_run(self, request: web.Request) -> web.Response:
        """
        MCP tool handler for running a shell command and returning the result synchronously.

        Expects:
            {
                "command": str,
                "working_dir": str,
                "timeout_seconds": number
            }
        Returns:
            {
                "success": bool,
                "code": int,
                "stdout": str,
                "stderr": str,
                "operation": "run"
            }
        """
        try:
            body = await request.json()
            command = body.get("command")
            working_dir = body.get("working_dir", ".")
            raw_timeout = body.get("timeout_seconds")
            timeout = float(raw_timeout) if raw_timeout is not None else self._config.default_timeout_seconds

            if not command:
                return self._error("command parameter is required")

            if not self._is_allowed_working_dir(working_dir):
                return self._error(f"working_dir not allowed: {working_dir}")

            if timeout <= 0:
                timeout = self._config.default_timeout_seconds
            if timeout > self._config.max_timeout_seconds:
                timeout = self._config.max_timeout_seconds

            # Split the command for asyncio.run_executable
            args = shlex.split(command)
            cwd: str | None = str(working_dir) if working_dir else None

            # Run the command with timeout
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.terminate()
                await proc.wait()
                return self._error(f"command timed out after {timeout} seconds")

            code = proc.returncode
            stdout_text = stdout.decode("utf‑8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf‑8", errors="replace") if stderr else ""

            payload = {
                "code": code,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "command": command,
                "working_dir": working_dir,
            }

            if code == 0:
                return self._success(payload, operation="run")
            else:
                return self._error(f"command failed with exit code {code}", payload=payload)

        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

    async def _handle_run_stream(self, request: web.Request) -> web.Response:
        """
        MCP tool handler that streams shell output to the caller.

        For simplicity this returns immediately without true streaming;
        a real MCP server would use the streaming channel instead.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # In a real MCP server the streaming tool would keep the tool active
        # until the client sends a stop or the command ends, aligning with
        # MCP tool‑stream semantics.[web:199][web:203]
        await ws.send_json({"error": "not implemented in skeleton"})
        await ws.close()
        return ws

    # Utilities -----------------------------------------------------------

    def _is_allowed_working_dir(self, working_dir: str | None) -> bool:
        """
        Validate that the working directory is allowed by configuration.

        Used to prevent arbitrary directory access and sandbox commands.
        """
        if working_dir is None:
            return True
        if self._config.allow_any_working_dir:
            return True
        allowed = [str(Path(p).resolve()) for p in self._config.allowed_working_dirs]
        try:
            resolved = Path(working_dir).resolve()
            return str(resolved) in allowed
        except Exception:  # noqa: BLE001
            return False

    def _success(self, payload: Mapping[str, Any], *, operation: str) -> web.Response:
        """Return a 200 JSON response with success metadata."""
        payload = dict(payload)
        payload["success"] = True
        payload["operation"] = operation
        return web.json_response(payload)

    def _error(self, message: str, payload: Mapping[str, Any] | None = None) -> web.Response:
        """Return a 200 JSON response with an error message for the MCP client."""
        payload = dict(payload) if payload is not None else {}
        payload["success"] = False
        payload["error"] = message
        return web.json_response(payload)


# Shell server routes are defined under /mcp/shell, following MCP tool‑server path conventions.[web:199][web:203]
