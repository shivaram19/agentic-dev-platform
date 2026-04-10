"""
Agentic Development Platform - MCP Protocol Abstractions

Defines the core ToolCall / ToolResult contracts and the IToolExecutor
interface that agents and orchestrators depend on, decoupled from any
specific MCP client implementation.[web:196][web:199][web:200]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Protocol, runtime_checkable
import structlog

log = structlog.get_logger(__name__)


class MCPError(Exception):
    """Base exception for MCP-related failures."""
    pass


@dataclass(frozen=True)
class ToolCall:
    """
    Immutable description of a single tool invocation.

    Maps closely to the MCP tool invocation model (tool name + arguments)
    without leaking transport-level concerns into agent code.[web:199][web:202]
    """
    id: str
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """
    Immutable result of a tool invocation.

    Contains a success flag, returned data, optional error message, and
    metadata for callers that need additional details (e.g. stdout).
    """
    call_id: str
    tool_name: str
    success: bool
     Any | None = None
    error: str | None = None
    meta: Mapping[str, Any] | None = None


@runtime_checkable
class IToolExecutor(Protocol):
    """
    Abstraction for executing MCP tool calls.

    Agents and orchestrators depend on this interface rather than talking
    to MCP clients or servers directly (DIP). This makes it easy to swap
    implementations (real vs. mock, local vs. remote).
    """

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool call and return the structured result.

        Implementations must:
        - Propagate MCP protocol errors as MCPError.
        - Never raise on expected tool failures; instead set success=False
          and populate the error field in ToolResult.
        """
        ...
