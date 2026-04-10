"""
Agentic Development Platform - Project registry.

A small service‑registry‑style component that keeps track of known projects
and their metadata (paths, default agents, configuration handles, etc.).

This intentionally mirrors the “service registry” pattern from microservices,
but applied at the level of agentic development projects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Iterable
import threading
import structlog


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProjectMeta :
    """
    Immutable description of a project known to the platform.

    The registry does not try to model every possible dimension of a project;
    it only stores what orchestrators and agents need for routing:

    - `project_id`: logical identifier, unique within the platform.
    - `root_path`: filesystem root for the project workspace.
    - `default_agent_id`: main agent that “owns” the project.
    - `tags`: free‑form labels for grouping, search, and routing.
    - `config`: backend‑specific configuration (e.g. LLM, tools).
    """
    project_id: str
    root_path: Path
    default_agent_id: str
    tags: Dict[str, str] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


class ProjectRegistry(ABC):
    """
    Abstract contract for a project registry.

    The implementation may be in‑memory, persisted to a database, or backed by
    a remote service registry. Callers depend only on this interface.
    """

    @abstractmethod
    def register(self, project: ProjectMetadata) -> None:
        """
        Register or update a project in the registry.

        Args:
            project: Project metadata to store.

        Raises:
            ValueError: If the project data is invalid.
        """
        raise NotImplementedError

    @abstractmethod
    def unregister(self, project_id: str) -> None:
        """
        Remove a project from the registry.

        Args:
            project_id: Logical project identifier.

        It is not an error to unregister a non‑existent project.
        """
        raise NotImplementedError

    @abstractmethod
    def get(self, project_id: str) -> Optional[ProjectMetadata]:
        """
        Lookup a project by its identifier.

        Args:
            project_id: Logical project identifier.

        Returns:
            Project metadata or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    def list_projects(self) -> Iterable[ProjectMetadata]:
        """
        Return a snapshot of all registered projects.
        """
        raise NotImplementedError


class InMemoryProjectRegistry(ProjectRegistry):
    """
    Simple in‑memory project registry implementation.

    This is suitable for local development and testing. In production you can
    replace it with a distributed implementation backed by a database or a
    dedicated service registry.
    """

    def __init__(self) -> None:
        self._projects: Dict[str, ProjectMetadata] = {}
        self._lock = threading.RLock()
        self._logger = log.bind(registry_type=self.__class__.__name__)

    def register(self, project: ProjectMetadata) -> None:
        if not project.project_id:
            raise ValueError("project_id must not be empty")
        if not project.root_path:
            raise ValueError("root_path must not be empty")

        with self._lock:
            self._projects[project.project_id] = project
            self._logger.info(
                "Project registered",
                project_id=project.project_id,
                root_path=str(project.root_path),
                default_agent_id=project.default_agent_id,
                tags=project.tags,
            )

    def unregister(self, project_id: str) -> None:
        with self._lock:
            existed = self._projects.pop(project_id, None) is not None
            self._logger.info(
                "Project unregistered",
                project_id=project_id,
                existed=existed,
            )

    def get(self, project_id: str) -> Optional[ProjectMetadata]:
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self) -> Iterable[ProjectMetadata]:
        with self._lock:
            # Return a shallow copy snapshot to avoid external mutation.
            return list(self._projects.values())
