"""
Agentic Development Platform - Session model.

Sessions group related tasks and interactions (tool calls, messages,
voice commands) into a coherent unit of work, usually corresponding to
a development “session” in the IDE or terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid


class SessionStatus(str, Enum):
    """
    Lifecycle state of a session.
    """
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass
class SessionEvent:
    """
    Immutable event that occurred during a session.

    Examples:

    - user_message: a natural‑language query from the user,
    - agent_message: a response from an agent,
    - tool_call / tool_result: MCP interactions,
    - voice_command: a processed voice input.
    """
    type: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Session:
    """
    Core session state object.

    A session ties together:

    - the user and project,
    - the active agent (if any),
    - the set of tasks that belong to this session,
    - an append‑only list of events for auditing and replay.

    It is intentionally storage‑agnostic; an adapter layer can persist it.
    """

    user_id: str
    project_id: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_agent_id: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)
    events: List[SessionEvent] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def add_task(self, task_id: str) -> None:
        """
        Attach a task to this session if not already present.
        """
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
            self.touch()

    def add_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Record a new event in the session event log.
        """
        self.events.append(SessionEvent(type=event_type, payload=payload))
        self.touch()

    def set_active_agent(self, agent_id: Optional[str]) -> None:
        """
        Set or clear the currently active agent for this session.
        """
        self.active_agent_id = agent_id
        self.touch()

    def mark_completed(self) -> None:
        """
        Mark the session as completed.
        """
        self.status = SessionStatus.COMPLETED
        self.touch()

    def mark_abandoned(self) -> None:
        """
        Mark the session as abandoned (e.g. IDE closed without explicit shutdown).
        """
        self.status = SessionStatus.ABANDONED
        self.touch()

    def pause(self) -> None:
        """
        Pause the session (e.g. user switched projects).
        """
        self.status = SessionStatus.PAUSED
        self.touch()

    def resume(self) -> None:
        """
        Resume a paused session.
        """
        self.status = SessionStatus.ACTIVE
        self.touch()

    def touch(self) -> None:
        """
        Update the `updated_at` timestamp to now (UTC).
        """
        self.updated_at = datetime.now(timezone.utc)
