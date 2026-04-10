"""
Agentic Development Platform - Message Bus Abstractions

Defines the AgentMessage data contract and the IMessageBus interface that
orchestrators and agents use to communicate asynchronously.

Follows common event‑driven architecture patterns for microservices.[web:130][web:140]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Protocol, runtime_checkable
import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AgentMessage:
    """
    Immutable event message between agents and orchestrators.

    The content is a JSON‑like dict that is interpreted by the consumer;
    this abstraction keeps the message bus generic and transport‑agnostic.
    """
    sender: str
    receiver: str
    task_id: str
    payload: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IMessageBus(Protocol):
    """
    Abstraction for an asynchronous message bus.

    Orchestrators and agents depend only on this interface (DIP), making it
    easy to swap implementations (local in‑memory bus vs Kafka, etc.).
    """

    async def publish(self, message: AgentMessage) -> None:
        """
        Publish a message to the bus.

        Implementations should be fire‑and‑forget at the API level; errors
        can be handled internally or propagated as specific exceptions.
        """
        ...

    async def subscribe(self, receiver: str, handler: Any) -> None:
        """
        Subscribe a handler to messages addressed to the given receiver.

        In a real implementation the handler would be a coroutine or function
        that receives AgentMessage values.
        """
        ...
