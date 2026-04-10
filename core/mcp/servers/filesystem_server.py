"""
Agentic Development Platform - MCP Filesystem Server

MCP server that exposes filesystem operations such as:
- Reading files
- Writing and patching files
- Managing directory trees

This server maps MCP tool calls onto the local filesystem and never depends
on agents or orchestrators (Single Responsibility + DIP).[web:199][web:203]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, cast
import asyncio
import json
import os
from pathlib import Path
from typing_extensions import TypeAlias

from aiohttp import web
from aiohttp.web import WebSocketResponse

from core.mcp.protocol import ToolCall, ToolResult

log = web.Application.logger.getChild("fileservers")

ToolContext: TypeAlias = Dict[str, Any]


@dataclass(frozen=True)
class FilesystemServerConfig:
    """
    Configuration for the filesystem server.

    Keeps path and permission policy decisions separate from the protocol logic.
    """
    base_path: str
    allowed_extensions: list[str] = field(
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
            ".md",
        ]
    )
    max_file_size_bytes: int = 1024 * 1024
    allow_create: bool = True
    allow_overwrite: bool = True


class FilesystemServer:
    """
    MCP Filesystem Server that exposes file operations to the MCP tool layer.

    Responsibilities:
    - Tool routing: map /mcp/filesystem onto various file operations.
    - Validation: enforce path and size constraints.
    - Execution: read/write files and return structured results.
    """

    def __init__(self, config: FilesystemServerConfig) -> None:
        """
        Initialize the filesystem server.

        Args:
            config: Server configuration (base path, allowed extensions, etc.).
        """
        self._config = config
        self._logger = log.getChild("FilesystemServer")
        self._base_path = Path(self._config.base_path).resolve()
        self._logger.info("FilesystemServer initialized", base_path=str(self._base_path))

    def register_routes(self, app: web.Application) -> None:
        """Register MCP filesystem routes into the given web application."""
        route_prefix = "/mcp/filesystem"

        app.router.add_post(f"{route_prefix}/read_file", self._handle_read_file)
        app.router.add_post(f"{route_prefix}/write_file", self._handle_write_file)
        app.router.add_post(f"{route_prefix}/patch_file", self._handle_patch_file)
        app.router.add_post(f"{route_prefix}/list_dir", self._handle_list_dir)

        self._logger.info("FilesystemServer routes registered", prefix=route_prefix)

    # Handlers ------------------------------------------------------------

    async def _handle_read_file(self, request: web.Request) -> web.Response:
        """
        MCP tool handler for reading a file.

        Expects:
            {"path": str}

        Returns:
            {"content": str} on success, {"error": str} otherwise.
        """
        try:
            body = await request.json()
            rel_path = cast(str, body.get("path"))
            if not rel_path:
                return self._error("path parameter is required")

            path = self._resolve(rel_path)
            if path is None:
                return self._error("path not allowed")

            if not path.is_file():
                return self._error(f"not a file: {path}")

            if path.stat().st_size > self._config.max_file_size_bytes:
                return self._error(f"file too large (>{self._config.max_file_size_bytes} bytes)")

            async with asyncio.to_thread(path.read_text) as content:
                payload = {"content": content}
                return self._success(payload, path=str(path))

        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

    async def _handle_write_file(self, request: web.Request) -> web.Response:
        """
        MCP tool handler for writing a file.

        Expects:
            {
                "path": str,
                "content": str,
                "overwrite": bool,
                "create_if_missing": bool
            }

        Respects allow_create/allow_overwrite config.
        """
        try:
            body = await request.json()
            rel_path = cast(str, body.get("path"))
            content = cast(str, body.get("content", ""))
            overwrite = cast(bool, body.get("overwrite", False))
            create_if_missing = cast(bool, body.get("create_if_missing", True))

            if not rel_path:
                return self._error("path parameter is required")

            path = self._resolve(rel_path)
            if path is None:
                return self._error("path not allowed")

            if path.exists() and not overwrite:
                return self._error("overwrite not allowed")

            if path.exists() and not self._config.allow_overwrite:
                return self._error("server does not allow overwrites")

            if not path.exists() and not create_if_missing and not self._config.allow_create:
                return self._error("server does not allow file creation")

            # Create parent directory if needed and allowed.
            parent = path.parent
            if not parent.exists() and self._config.allow_create:
                parent.mkdir(parents=True, exist_ok=True)

            async with asyncio.to_thread(path.write_text, content):
                payload = {"path": str(path)}
                return self._success(payload, operation="write_file")

        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

    async def _handle_patch_file(self, request: web.Request) -> web.Response:
        """
        MCP tool handler for patching a file.

        Expects:
            {
                "path": str,
                "patch": str,
                "create_if_missing": bool
            }

        The patch format is server-agnostic and left to the client (e.g., diff,
        regex‑based replacement, etc.).
        """
        try:
            body = await request.json()
            rel_path = cast(str, body.get("path"))
            patch = cast(str, body.get("patch", ""))
            create_if_missing = cast(bool, body.get("create_if_missing", False))

            if not rel_path:
                return self._error("path parameter is required")

            path = self._resolve(rel_path)
            if path is None:
                return self._error("path not allowed")

            if not path.exists() and not create_if_missing:
                return self._error("file does not exist and create_if_missing is false")

            if not path.exists() and self._config.allow_create:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            async with asyncio.to_thread(path.read_text) as before:
                # In a real implementation, patch logic would live in a
                # separate patching module, not the MCP server.
                after = self._apply_patch_text(before, patch)

            async with asyncio.to_thread(path.write_text, after):
                payload = {"path": str(path)}
                return self._success(payload, operation="patch_file")

        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

    async def _handle_list_dir(self, request: web.Request) -> web.Response:
        """
        MCP tool handler for listing directory contents.

        Expects:
            {"path": str}

        Returns:
            {"files": list, "dirs": list} on success.
        """
        try:
            body = await request.json()
            rel_path = cast(str, body.get("path", "."))
            path = self._resolve(rel_path)
            if path is None:
                return self._error("path not allowed")

            if not path.exists():
                return self._error("path does not exist")

            if not path.is_dir():
                return self._error("path is not a directory")

            files: list[str] = []
            dirs: list[str] = []

            for ent in path.iterdir():
                if ent.is_dir():
                    dirs.append(ent.name)
                else:
                    files.append(ent.name)

            payload = {
                "path": str(path),
                "files": files,
                "dirs": dirs,
            }
            return self._success(payload, path=str(path))

        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc))

    # Internal helpers ----------------------------------------------------

    def _resolve(self, rel_path: str) -> Path | None:
        """
        Resolve a relative path under the base path, applying security checks.

        Ensures that no path escapes the configured base and extension constraints.
        """
        # Prevent path traversal
        path = self._base_path.joinpath(rel_path).resolve()
        if not path.is_relative_to(self._base_path):
            self._logger.warning("Path traversal attempt", requested=rel_path)
            return None

        if not self._config.allowed_extensions:
            return path

        # Simple extension check; in practice you might want to ignore dotfiles.
        suffix = path.suffix.lower()
        if suffix not in self._config.allowed_extensions:
            self._logger.info("Extension not allowed", path=str(path), suffix=suffix)
            return None

        return path

    def _apply_patch_text(self, text: str, patch: str) -> str:
        """
        Apply a patch to text; trivial example using substring replacement.

        A real MCP implementation would delegate to a dedicated patching library
        tied to the patch format (diff, regex, etc.).
        """
        if not patch:
            return text

        old, sep, new = patch.partition("=>")
        if not sep:
            return text

        return text.replace(old.strip(), new.strip())

    def _success(
        self,
        payload: Mapping[str, Any],
        *,
        path: str | None = None,
        operation: str | None = None,
    ) -> web.Response:
        """Return a 200 JSON response with success metadata."""
        payload = dict(payload)
        payload["success"] = True
        if path is not None:
            payload["path"] = path
        if operation is not None:
            payload["operation"] = operation
        return web.json_response(payload)

    def _error(self, message: str) -> web.Response:
        """Return a 200 JSON response with an error message for the MCP client."""
        return web.json_response({"success": False, "error": message})