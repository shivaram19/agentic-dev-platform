#!/usr/bin/env python
"""Create a new project workspace for the agentic platform.

This script:

  - creates a project directory under `projects/`,
  - populates a minimal scaffolding (e.g., a `main.py` or equivalent),
  - registers the project in the in‑memory project registry, and
  - prints a usage hint.

It is intended to be called as a CLI tool, e.g.:

    python scripts/create_project.py --name my-project
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
import logging

# Reuse the core registry and models.
from core.registry.project_registry import (
    InMemoryProjectRegistry,
    ProjectMetadata,
)
from core.models.task_model import Task, TaskStatus, TaskPriority


log = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )


def create_project_template(
    project_name: str,
    project_root: Path,
    project_type: str = "python",
) -> None:
    """
    Populate a minimal project layout based on `project_type`.

    Supported types:
      - "python" (default): a src/main.py and pyproject.toml.
    """
    project_dir = project_root / project_name
    if project_dir.exists():
        log.warning("Project directory already exists: %s", project_dir)
        return

    log.info("Creating project directory: %s", project_dir)
    project_dir.mkdir(parents=True)

    # Python‑style minimal project
    src = project_dir / "src"
    src.mkdir()
    main = src / "main.py"
    main.write_text(
        f'''"""{project_name} module created by create_project.py."""

def main() -> None:
    print("Hello from {project_name}!")

if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )

    toml = project_dir / "pyproject.toml"
    toml.write_text(
        f'''[project]
name = "{project_name}"
version = "0.1.0"
description = "Project created by create_project.py"
requires-python = ">=3.9"

[tool.setuptools.packages.find]
where = ["src"]
''',
        encoding="utf-8",
    )

    readme = project_dir / "README.md"
    readme.write_text(
        f"""# {project_name}

This is a project scaffold created by `create_project.py`.

You can now run the agentic platform against it:

    python main.py {project_name} --task "Add a Fibonacci function"
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a new project for the agentic platform")
    parser.add_argument(
        "--name", required=True,
        help="Logical project name (used as directory name and project_id)",
    )
    parser.add_argument(
        "--type", default="python",
        choices=["python"],
        help="Project type / template",
    )
    parser.add_argument(
        "--projects-root",
        default="projects",
        help="Root directory for projects",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Only create the directory; do not register in the registry",
    )

    args = parser.parse_args()

    setup_logging()

    projects_root = Path(args.projects_root).resolve()
    log.info("Projects root: %s", projects_root)

    # Create the layout
    create_project_template(
        project_name=args.name,
        project_root=projects_root,
        project_type=args.type,
    )

    # Register in the in‑memory registry
    if not args.no_register:
        registry = InMemoryProjectRegistry()
        metadata = ProjectMetadata(
            project_id=args.name,
            root_path=(projects_root / args.name),
            default_agent_id="code-agent",
            tags={"type": args.type, "source": "create_project.py"},
        )
        registry.register(metadata)
        log.info(
            "Project registered in in‑memory registry",
            project_id=args.name,
            root_path=str(metadata.root_path),
        )

        # In a real system you might persist this registration to a database.
        # For demo, just log it.
        print(
            "Project created and registered. You can now run:",
            f"  python main.py {args.name} --task 'Add a feature to main.py'",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
