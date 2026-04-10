# core/mcp/servers package
"""
Agentic Development Platform - MCP Servers Package

Exposes server-side MCP tool implementations used by the MCP client.

The design follows MCP tool server conventions in which each server
path exposes a logical set of capabilities (filesystem, git, shell, etc.).[web:199][web:203]
"""

from core.mcp.servers.filesystem_server import FilesystemServer
from core.mcp.servers.git_server import GitServer
from core.mcp.servers.shell_server import ShellServer

__all__ = [
    "FilesystemServer",
    "GitServer",
    "ShellServer",
]
