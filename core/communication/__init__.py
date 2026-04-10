# core/communication package
"""
Agentic Development Platform - Communication Package

Exposes the messaging and state coordination abstractions used by orchestrators
and agents:

- IMessageBus: broker for agent‑to‑agent notifications.
- KafkaBus: concrete implementation using Kafka.
- RedisStateStore: centralized state via Redis.

This layer decouples agents and orchestrators from the underlying transport
choice (DIP, dependency injection).[web:130][web:136][web:140]
"""

from core.communication.message_bus import IMessageBus, AgentMessage
from core.communication.kafka_bus import KafkaBus
from core.communication.redis_state import RedisStateStore

__all__ = [
    "IMessageBus",
    "AgentMessage",
    "KafkaBus",
    "RedisStateStore",
]
