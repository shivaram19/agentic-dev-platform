# MCP Server Development Guide

The Multi‑Agent Coordination Protocol (MCP) server exposes a set of tools that agents can invoke (e.g., file‑system operations, test runners, linters). This document explains how to develop and extend the MCP server layer.

## Prerequisites

- Familiarity with `core.mcp.protocol` types (`ToolCall`, `ToolResult`, `IToolExecutor`).
- Basic HTTP/WebSocket or in‑process server development in Python.
- Conceptual understanding of the architecture described in `docs/architecture.md`.

## MCP Server Responsibilities

- **Expose tools**: each tool (e.g., `filesystem.read_file`) is exposed via a fixed contract.
- **Validate and sanitize**: tool arguments must be validated and sanitized before execution.
- **Enforce project boundaries**: tools must respect project‑root isolation and permissions.
- **Return structured results**: each tool call returns a `ToolResult` with `success`, `content`, `error`, and optional `metadata`.

## Step 1: Tool Design

When designing a new tool:

1. Decide on the logical name (e.g., `filesystem.write_file`, `test_runner.run`).
2. Define the argument schema as a `Dict[str, Any]` with clear keys.
3. Document the expected shape in `docs/mcp_tools.TABLE.md` (or similar) for reference.

For example, a `filesystem.write_file` tool:

- Arguments:
  - `path`: relative path under the project root.
  - `content`: string content to write.
  - `overwrite` (optional): whether to overwrite existing files.
- Metadata in the result:
  - `path` (canonicalized).
  - `bytes_written`, `created`, `modified` as needed.

## Step 2: Implement Tool Handlers

Each tool maps to a handler function that:

- Validates inputs against expected types and constraints (e.g., path under project root, max file size).
- Performs the actual operation (e.g., file I/O, test execution).
- Returns a `ToolResult` with either `success=True` and `content` or `success=False` and `error`.

Example sketch:

```python
def handle_write_file(arguments: Dict[str, Any]) -> ToolResult:
    project_root = ...  # resolved from context or config
    path = arguments.get("path")
    content = arguments.get("content", "")
    overwrite = arguments.get("overwrite", False)

    abs_path = project_root / path
    if abs_path.resolve().is_relative_to(project_root) is False:
        return ToolResult(success=False, error="Invalid path")

    if abs_path.exists() and not overwrite:
        return ToolResult(success=False, error="File exists and overwrite=False")

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")

    meta = {
        "path": str(abs_path.relative_to(project_root)),
        "bytes_written": len(content.encode("utf-8")),
    }
    return ToolResult(success=True, content="File written", metadata=meta)
```

## Step 3: Wire Tools into the MCP Server

In `core/mcp/server.py` (or equivalent):

1. Define a registry or mapping of `tool_name` → handler function.
2. Implement the request handler:

   - Deserialize the incoming request into a `ToolCall`.
   - Look up the handler by `tool_name`.
   - Call the handler and await its result.
   - Serialize the `ToolResult` back to the response format.

Example loop:

```python
class MCPServer:
    def __init__(self) -> None:
        self._tool_handlers = {
            "filesystem.read_file": handle_read_file,
            "filesystem.write_file": handle_write_file,
            "test_runner.run": handle_test_run,
            # ...
        }

    async def handle_request(self, raw_request: Dict[str, Any]) -> Dict[str, Any]:
        tool_call = ToolCall(
            id=raw_request["id"],
            tool_name=raw_request["tool_name"],
            arguments=raw_request["arguments"],
        )

        handler = self._tool_handlers.get(tool_call.tool_name)
        if not handler:
            return ToolResult.from_dict(
                success=False,
                error=f"Unknown tool: {tool_call.tool_name}",
            ).to_dict()

        try:
            result = handler(tool_call.arguments)
        except Exception as e:
            return ToolResult.from_dict(
                success=False,
                error=f"Tool crashed: {e!r}",
            ).to_dict()

        return result.to_dict()
```

## Step 4: Add Safeguards and Logging

- **Path safety**: always resolve paths relative to the project root and reject any outside.
- **Rate limiting**: cap file‑write or test‑run frequency per project.
- **Audit logging**: log tool calls and results (at least `tool_name`, `project_id`, and `success`).
- **Timeouts**: fail long‑running operations with a message instead of hanging.

## Step 5: Expose the Server Over a Transport

Choose one or more transports:

- **HTTP/REST**: simple JSON endpoints for `POST /tools/{name}`.
- **WebSocket**: streaming model for long‑running tools.
- **In‑process**: direct `IToolExecutor` adapter for local testing.

The `core/mcp/client.MCPClient` already provides a client façade; ensure that:

- Requests are serialized via `ToolCall.to_dict()`.
- Responses are parsed via `ToolResult.from_dict()`.

## Step 6: Test the MCP Server

- **Unit tests**: `tests/unit/test_mcp_server.py` that:
  - Verifies contract conformance (tool‑call and tool‑result shapes).
  - Tests error cases: invalid paths, missing files, permission issues.
- **Integration tests**: `tests/integration/test_mcp_integration.py` that:
  - Starts a real MCP server (HTTP or in‑process).
  - Connects via `MCPClient`.
  - Asserts that agents can complete end‑to‑end tasks.

Example focus areas:

- File read/write round‑trips.
- Test‑runner invocations and pass‑fail handling.
- Concurrency and parallelism (if the server is multi‑threaded/coroutine‑based).

## Extending the MCP Ecosystem

You can add tools for:

- **Security and linting**: `security.scan` or `linter.invoke`.
- **CI/CD hooks**: `build_runner.trigger`, `deploy.request`.
- **Database access**: `db.query` (with strict whitelisted queries).

By following this guide, you keep the MCP server:

- Secure and sandboxed.
- Interoperable with agents and orchestrators.
- Observable and testable.


