"""
Unit tests for a generic MCP client (e.g., client for the MCP server).

This tests:
  - how the client serializes tool calls,
  - how it parses tool results,
  - and basic error handling when the underlying transport fails.

We assume the client is an async‑capable HTTP or WebSocket client,
but for the unit tests we stub the transport layer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from core.mcp.client import MCPClient, MCPClientConfig
from core.mcp.protocol import ToolCall, ToolResult
from core.models.task_model import TaskStatus


class StubTransport:
    """Stub for the underlying HTTP/WebSocket transport."""

    def __init__(self, responses: Dict[str, Any]) -> None:
        self.responses = responses
        self.sent = []

    async def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Return a canned response for the given request."""
        key = request.get("tool_name", "default")
        self.sent.append(request)
        return self.responses.get(key, {"success": True, "content": "ok"})


class TestMCPClient:
    """Unit tests for MCPClient."""

    @pytest.fixture
    def config(self) -> MCPClientConfig:
        return MCPClientConfig(
            base_url="http://localhost:3333",
            default_timeout=5.0,
        )

    @pytest.fixture
    def transport(self) -> StubTransport:
        return StubTransport(
            {
                "filesystem.read_file": {
                    "success": True,
                    "content": "def main(): pass\n",
                    "metadata": {"path": "src/main.py"},
                },
                "filesystem.write_file": {
                    "success": True,
                    "metadata": {"path": "src/main.py"},
                },
                "test_runner.run": {
                    "success": True,
                    "content": "Ran 1 test, 0 failures",
                    "metadata": {"passed": 1, "failed": 0},
                },
            }
        )

    @pytest.fixture
    def client(self, config: MCPClientConfig, transport: StubTransport) -> MCPClient:
        c = MCPClient(config=config)
        c._transport = transport
        return c

    def test_tool_call_serialization(self) -> None:
        """MCPClient serializes a ToolCall into a dict matching the server contract."""
        tool_call = ToolCall(
            id="t-1",
            tool_name="filesystem.read_file",
            arguments={"path": "src/main.py"},
        )
        req = MCPClient._serialize_tool_call(tool_call)
        assert req["id"] == "t-1"
        assert req["tool_name"] == "filesystem.read_file"
        assert req["arguments"] == {"path": "src/main.py"}

    def test_tool_result_parsing(self) -> None:
        """MCPClient parses a server response into a ToolResult."""
        raw = {
            "success": True,
            "content": "file content",
            "error": None,
            "metadata": {"path": "src/main.py"},
        }
        result = MCPClient._parse_tool_result(raw)
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.content == "file content"
        assert result.metadata == {"path": "src.main.py"}
        assert result.error is None

    def test_error_parsing(self) -> None:
        """MCPClient parses error fields into ToolResult."""
        raw = {
            "success": False,
            "error": "File not found",
            "metadata": {"path": "src/missing.py"},
        }
        result = MCPClient._parse_tool_result(raw)
        assert result.success is False
        assert result.error == "File not found"
        assert result.metadata == {"path": "src.missing.py"}

    async def test_execute_tool_call_success(
        self, client: MCPClient, transport: StubTransport
    ) -> None:
       
