"""
Agentic Development Platform - Registry package.

This package exposes registry contracts (project, agent, tool, etc.) so that
higher‑level components can depend on simple interfaces instead of concrete
storage or discovery mechanisms.
"""
from .project_registry import ProjectRegistry, ProjectMetadata, InMemoryProjectRegistry

__all__ = [
    "ProjectRegistry",
    "ProjectMetadata",
    "InMemoryProjectRegistry",
]
