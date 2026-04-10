# core/mcp package
"""
Agentic Development Platform - MCP Integration Package

Thin re-export layer for core MCP abstractions:

- ToolCall / ToolResult: unified tool invocation data contracts.
- IToolExecutor: abstraction that agents/orchestrators depend on.
- MCPClient: concrete client implementation that speaks MCP to servers.

The design mirrors the MCP client–server split defined in the public
Model Context Protocol specification.[web:196][web:204][web:207]
"""

from core.mcp.protocol import IToolExecutor, MCPError, ToolCall, ToolResult
from core.mcp.mcp_client import MCPClient

__all__ = [
    "IToolExecutor",
    "MCPError",
    "ToolCall",
    "ToolResult",
    "MCPClient",
]
