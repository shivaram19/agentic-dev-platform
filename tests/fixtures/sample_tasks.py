"""
Common sample tasks for use in tests.

These are plain dictionaries that can be passed to OrchestratorAgent.think
or other agents as task_description and context.
"""
from typing import Dict, Any


def simple_code_generation_task() -> Dict[str, Any]:
    """Generate a simple Python module that prints a greeting."""
    return {
        "task_description": "Create a new Python module that prints a greeting message.",
        "context": {
            "project_id": "sample-app",
            "agent_id": "code-agent",
            "task_id": "sample-task-1",
        },
    }


def refactor_task() -> Dict[str, Any]:
    """Refactor a Python module to use better naming and add a test comment."""
    return {
        "task_description": "Refactor the existing main.py module to improve function naming and add a test comment.",
        "context": {
            "project_id": "sample-app",
            "agent_id": "code-agent",
            "task_id": "sample-task-2",
        },
    }


def multi_file_task() -> Dict[str, Any]:
    """Create a small multi‑file feature: a module and a test file."""
    return {
        "task_description": (
            "Create a Python module src/utils.py with a helper function "
            "and its test file tests/test_utils.py."
        ),
        "context": {
            "project_id": "sample-app",
            "agent_id": "code-agent",
            "task_id": "sample-task-3",
        },
    }


def cross_project_task() -> Dict[str, Any]:
    """A task that should be processed in a specific project (project‑two)."""
    return {
        "task_description": (
            "Rewrite the main entry point of project‑two into TypeScript "
            "and add a configuration file tsconfig.json."
        ),
        "context": {
            "project_id": "project-two",
            "agent_id": "code-agent",
            "task_id": "cross-project-task",
        },
    }


def failed_task() -> Dict[str, Any]:
    """A task that is expected to fail during observation (e.g., file not found)."""
    return {
        "task_description": "Read a non‑existent file and print its contents.",
        "context": {
            "project_id": "sample-app",
            "agent_id": "code-agent",
            "task_id": "failed-task",
        },
    }


def voice_command_task() -> Dict[str, Any]:
    """Simulate a voice‑derived task for the voice command handler."""
    return {
        "task_description": "Refactor the code and improve test coverage based on voice command.",
        "context": {
            "project_id": "sample-app",
            "agent_id": "voice-code-agent",
            "task_id": "voice-task-1",
            "raw_audio_text": "refactor the main module to use async functions and add unit tests",
        },
    }


def complex_decomposition_task() -> Dict[str, Any]:
    """A more complex task that tests the orchestrator's decomposition logic."""
    return {
        "task_description": (
            "Implement a feature that includes a new module, tests, "
            "a README update, and linting fixes."
        ),
        "context": {
            "project_id": "sample-app",
            "agent_id": "orchestrator",
            "task_id": "complex-task",
        },
    }
