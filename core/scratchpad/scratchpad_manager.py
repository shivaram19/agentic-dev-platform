"""
Agentic Development Platform - Scratchpad Manager

Centralized manager for structured task memory (“scratchpad”) that agents and
orchestrators can append to and query.

Draws on the checkpoint‑resume pattern for long‑running AI workflows.[web:253]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
import structlog
from typing_extensions import Protocol, runtime_checkable

log = structlog.get_logger(__name__)


@runtime_checkable
class ScratchpadStore(Protocol):
    """
    Abstract store for scratchpad entries.

    This allows swapping implementations (filesystem, database, etc.) while
    keeping the ScratchpadManager interface the same (DIP).
    """

    def read(self, path: str) -> str | None:
        """Read the contents at path, or None if missing."""
        ...

    def write(self, path: str, content: str) -> None:
        """Write content to path."""
        ...


@dataclass
class FilesystemStore:
    """
    Concrete scratchpad store that writes to a local directory.

    Simple, deterministic, and easy to inspect during development.
    """

    base_dir: Path

    def __post_init__(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, project_id: str, agent_id: str, task_id: str) -> Path:
        return (
            self.base_dir
            / project_id
            / self._sanitize(agent_id)
            / f"{self._sanitize(task_id)}.md"
        )

    def _sanitize(self, s: str) -> str:
        return "".join(c for c in s if c.isalnum() or c in "._-").strip("-")

    def read(self, path: str) -> str | None:
        try:
            p = Path(path)
            if p.is_file():
                return p.read_text(encoding="utf‑8")
            return None
        except Exception:  # noqa: BLE001
            return None

    def write(self, path: str, content: str) -> None:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf‑8")
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to write scratchpad file", path=path, error=str(exc))


class ScratchpadSection:
    """
    Immutable section of a scratchpad entry.

    Sections are keyed by name (e.g., “Plan”, “Observations”) and are ordered
    by insertion time.
    """

    def __init__(
        self,
        name: str,
        content: str,
        timestamp: datetime | None = None,
    ) -> None:
        self.name = name
        self.content = content
        self.timestamp = timestamp or datetime.now()


@dataclass
class ScratchpadConfig:
    """
    Configuration for the scratchpad manager.

    Encapsulates path and serialization choices, keeping them orthogonal to
    agents and orchestrators.
    """
    store: ScratchpadStore
    encoding: str = "utf‑8"
    template: str = ""


class ScratchpadManager:
    """
    Manager for structured, project‑scoped task memory used by agents.

    Responsibilities:
    - Combining a base template with multiple sections.
    - Serializing/Deserializing scratchpad content to/from the store.
    - Providing a simple append‑and‑read interface that agents can use
      without knowing the underlying storage.

    This supports checkpoint‑like behavior where agents can resume from a
    saved state.[web:253]
    """

    def __init__(
        self,
        config: ScratchpadConfig,
    ) -> None:
        """
        Initialize the scratchpad manager.

        Args:
            config: Scratchpad configuration.
        """
        self._config = config
        self._logger = log.bind(manager_id=id(self))

        self._logger.info("ScratchpadManager initialized")

    async def append_section(
        self,
        project_id: str,
        agent_id: str,
        task_id: str,
        section: str,
        content: str,
    ) -> None:
        """
        Append a section to the scratchpad entry for the given task.

        If the scratchpad does not exist, it is created from the base template.
        """
        path = self._scratchpad_path(project_id, agent_id, task_id)
        sections = await self._read_sections(path)
        sections.append(ScratchpadSection(name=section, content=content))

        await self._write_sections(path, sections)

    async def read_scratchpad(
        self,
        project_id: str,
        agent_id: str,
        task_id: str,
    ) -> str | None:
        """
        Read the full scratchpad content for the given task.

        Returns the raw text or None if no scratchpad exists.
        """
        path = self._scratchpad_path(project_id, agent_id, task_id)
        return self._read_text(path)

    # Private helpers -----------------------------------------------------

    def _scratchpad_path(
        self,
        project_id: str,
        agent_id: str,
        task_id: str,
    ) -> str:
        """Return the store path for the given task scratchpad."""
        base = self._config.base_dir / project_id / agent_id / f"{task_id}.md"
        return str(base)

    async def _read_sections(
        self,
        path: str,
    ) -> list[ScratchpadSection]:
        """
        Read all sections from the scratchpad at path.

        If the file does not exist or is empty, return an empty list.
        """
        text = self._read_text(path)
        if text is None:
            return []

        sections: list[ScratchpadSection] = []
        current_name = None
        current_lines: list[str] = []

        for line in text.splitlines(keepends=False):
            if line.startswith("#### ") and line.endswith(" ####"):
                if current_name and current_lines:
                    sections.append(
                        ScratchpadSection(
                            name=current_name,
                            content="\n".join(current_lines),
                        ),
                    )
                current_name = line[5:-5]
                current_lines = []
                continue
            if current_name is not None:
                current_lines.append(line)

        if current_name and current_lines:
            sections.append(
                ScratchpadSection(
                    name=current_name,
                    content="\n".join(current_lines),
                ),
            )
        return sections

    async def _write_sections(self, path: str, sections: list[ScratchpadSection]) -> None:
        """
        Write the given sections into the scratchpad at path.

        Overwrites the existing file.
        """
        lines: list[str] = [self._config.template.strip()]
        if lines and lines[-1]:
            lines.append("")

        for sec in sections:
            lines.append(f"#### {sec.name} ####")
            for line in sec.content.splitlines(keepends=False):
                lines.append(line)
            lines.append("")

        self._config.store.write(path, "\n".join(lines))

    def _read_text(self, path: str) -> str | None:
        """
        Read the text at path via the store, or None if missing.
        """
        raw = self._config.store.read(path)
        if not raw:
            return None
        return raw.strip()
