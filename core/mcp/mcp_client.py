"""
Agentic Development Platform - MCP Client

Concrete client implementing the MCP wire protocol and exposing tools via
IToolExecutor so that agents remain unaware of the transport.

Follows the MCP client–server interaction model in which the client:
- Sends tool calls over a streaming channel.
- Receives events and tool results asynchronously.[web:196][web:204][web:207]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, cast
import asyncio
import structlog
from aiohttp import ClientSession, ClientTimeout, WSCloseCode, WSMessage, WSMsgType
from aiohttp.web import WebSocketResponse

from core.mcp.protocol import IToolExecutor, MCPError, ToolCall, ToolResult

log = structlog.get_logger(__name__)


@dataclass
class MCPClientConfig:
    """
    Configuration for the MCPClient.

    Keeps connection and serialization concerns separate from the interface
    contract (SRP).
    """
    server_url: str
    connect_timeout_seconds: float = 10.0
    request_timeout_seconds: float = 30.0


class MCPClient(IToolExecutor):
    """
    MCP client that speaks the MCP wire protocol and exposes tools via
    IToolExecutor so that agents never depend on MCP internals (DIP).

    Responsibilities:
    - Maintain a logical MCP client–server connection.
    - Translate ToolCall into MCP tool invocations.
    - Re-serialize MCP tool results into ToolResult.
    - Handle connection and protocol errors defensively.
    """

    def __init__(self, config: MCPClientConfig) -> None:
        """
        Initialize the MCPClient.

        Args:
            config: Client configuration (URL, timeouts).
        """
        self._config = config
        self._session: ClientSession | None = None
        self._ws: WebSocketResponse | None = None
        self._response_lock: asyncio.Lock = asyncio.Lock()
        self._pending_responses: Dict[str, asyncio.Future[ToolResult]] = {}
        self._logger = log.bind(client_id=id(self), server_url=config.server_url)

        self._logger.info("MCPClient created")

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool call via the MCP client.

        The agent only knows ToolCall/ToolResult; the client hides the MCP
        wire protocol and JSON‑based message format.[web:199][web:203]
        """
        self._logger.info(
            "Executing MCP tool call",
            call_id=tool_call.id,
            tool_name=tool_call.tool_name,
            server_url=self._config.server_url,
        )

        await self._ensure_connection()

        future = asyncio.get_event_loop().create_future()
        async with self._response_lock:
            self._pending_responses[tool_call.id] = future

        await self._send_call(tool_call)

        try:
            return await future
        except Exception:  # noqa: BLE001
            return ToolResult(
                call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                success=False,
                error="MCPClient call failed with unknown exception",
            )

    # Connection lifecycle ------------------------------------------------

    async def _ensure_connection(self) -> None:
        """Open or reuse the MCP WebSocket connection."""
        if self._ws and not self._ws.closed:
            return

        timeout = ClientTimeout(total=self._config.connect_timeout_seconds)
        self._session = ClientSession(timeout=timeout)
        self._ws = await self._session.ws_connect(self._config.server_url)

        # Start listening for responses in the background
        asyncio.create_task(self._receive_response_loop())

    async def _receive_response_loop(self) -> None:
        """
        Wait for MCP tool result events and correlate them with ToolCalls.

        This method runs until the server closes the connection.
        """
        if not self._ws:
            return

        try:
            async for msg in self._ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type in {WSMsgType.CLOSED, WSMsgType.ERROR}:
                    self._logger.info(
                        "WebSocket closed",
                        ws_type="receive_response_loop",
                    )
                    break
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Error in MCPClient response loop",
                error=str(exc),
            )
        finally:
            self._close_response_futures("MCP connection closed unexpectedly")

    async def _send_call(self, tool_call: ToolCall) -> None:
        """
        Serialize and send a ToolCall as an MCP tool invocation event.

        Intentionally avoids embedding MCP‑specific abstractions in the agent
        layer by translating ToolCall into MCP JSON format.
        """
        if not self._ws:
            raise MCPError("Cannot send call: no active connection")

        # MCP tool call as per MCP tools JSON schema.[web:199]
        payload: Dict[str, Any] = {
            "type": "tool_call",
            "call_id": tool_call.id,
            "name": tool_call.tool_name,
            "arguments": tool_call.arguments,
        }

        # In a real MCP server the payload would be sent as bytes over the
        # streaming channel; here we just stringify for simplicity.
        await self._ws.send_json(payload)

    async def _handle_message(self, text: str) -> None:
        """
        Parse an MCP tool result event and resolve the matching ToolCall future.

        This is the only place where MCP message format knowledge lives;
        agents see only ToolResult values.
        """
        import json

        try:
            event = json.loads(text)
            ev_type = event.get("type")
            if ev_type != "tool_result":
                self._logger.info("Ignoring non-tool-result MCP event", event_type=ev_type)
                return

            call_id = event.get("call_id", "")
            error = event.get("error")
            results: Any = event.get("results", None)
            meta: Mapping[str, Any] | None = event.get("metadata", None)

            success = error is None and results is not None

            tool_result = ToolResult(
                call_id=call_id,
                tool_name="",  # MCP wire protocol does not always echo tool name
                success=success,
                data=results,
                error=error,
                metadata=metadata or None,
            )

            future: asyncio.Future[ToolResult] | None = None
            async with self._response_lock:
                future = self._pending_responses.pop(call_id, None)

            if future and not future.done():
                future.set_result(tool_result)

        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Error parsing MCP tool result event",
                error=str(exc),
                raw_text=text,
            )
            # Do not fail the whole connection on a single bad event.
            pass

    async def _close_response_futures(self, reason: str) -> None:
        """
        Mark any pending ToolCall futures as failed with the given reason.

        Keeps the client observable and prevents stuck agent T‑A‑O loops
        when the server disappears.
        """
        futures = []
        async with self._response_lock:
            futures = list(self._pending_responses.values())
            self._pending_responses.clear()

        for fut in futures:
            if not fut.done():
                fut.set_exception(MCPError(reason))

    async def close(self) -> None:
        """
        Close the MCP client connection gracefully.

        Should be called during application shutdown or when the client is no
        longer needed.
        """
        self._logger.info("Closing MCPClient")

        await self._response_lock.acquire()
        await self._close_response_futures("MCPClient explicitly closed")
        self._response_lock.release()

        if self._ws:
            await self._ws.close(code=WSCloseCode.GOING_AWAY)
        if self._session:
            await self._session.close()
