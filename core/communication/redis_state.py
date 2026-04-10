"""
Agentic Development Platform - Redis‑Backed State Store

Centralized state coordination for long‑running agents and orchestrators using
Redis as a shared, fast, network‑accessible store.

Alignment with common patterns for distributed‑agent state management.[web:229][web:234]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, TypeVar, Protocol
import hashlib
import json
import structlog
from typing_extensions import runtime_checkable

import redis.asyncio as redis

log = structlog.get_logger(__name__)


_KT = TypeVar("_KT", str, bytes)
_T = TypeVar("_T")


@runtime_checkable
class IStateStore(Protocol):
    """
    Abstract contract for a project‑scoped state store.

    Long‑running agents and orchestrators depend only on this interface (DIP),
    so the underlying storage can be swapped (Redis, in‑memory, etc.).
    """

    async def put_state(self, key: str, value: Dict[str, Any]) -> None:
        """Store or update a state object under the given key."""
        ...

    async def get_state(self, key: str) -> Dict[str, Any] | None:
        """Retrieve the state object for the given key, or None if missing."""
        ...

    async def delete_state(self, key: str) -> bool:
        """
        Delete the state entry for the given key.

        Returns True if the key existed and was deleted, False otherwise.
        """
        ...

    async def has_state(self, key: str) -> bool:
        """
        Check whether a state entry exists for the given key.

        Returns True if the key exists, False otherwise.
        """
        ...


@dataclass
class RedisStateConfig:
    """
    Configuration for the Redis state store layer.

    Encapsulates connection and namespace concerns, keeping the IStateStore
    interface independent of infrastructure details.
    """
    redis_url: str = "redis://localhost:6379/0"
    default_timeout_seconds: float = 10.0


class RedisStateStore(IStateStore):
    """
    Redis‑based implementation of project‑scoped agent state.

    Responsibilities:
    - Mapping high‑level keys (project‑id/task‑id) to Redis keys.
    - Serializing/D‑serializing state as JSON.
    - Wrapping Redis connection errors into a consistent, non‑leaky interface.
    """

    def __init__(self, config: RedisStateConfig) -> None:
        """
        Initialize the Redis state store.

        Args:
            config: Redis state configuration.
        """
        self._config = config
        self._client: redis.Redis | None = None
        self._logger = log.bind(store_id=id(self), redis_url=config.redis_url)

        self._logger.info("RedisStateStore created")

    # Lifecycle ------------------------------------------------------------

    async def connect(self) -> None:
        """Open the Redis connection if not already open."""
        if self._client:
            return
        self._client = redis.from_url(
            self._config.redis_url,
            decode_responses=True,
        )
        await self._client.ping()
        self._logger.info("RedisStateStore connected")

    async def close(self) -> None:
        """Close the Redis connection."""
        if not self._client:
            return
        await self._client.close()
        self._logger.info("RedisStateStore closed")

    # Core methods ---------------------------------------------------------

    async def put_state(self, key: str, value: Dict[str, Any]) -> None:
        """
        Store or update a state object under the given key.

        The key is prefixed to avoid collisions (e.g., "project:task:...").
        """
        real_key = self._scoped_key(key)
        data = self._dump_json(value)

        await self._ensure_client()
        await self._client.set(
            real_key,
            data,
            ex=int(self._config.default_timeout_seconds),
        )
        self._logger.info(
            "State stored in Redis",
            scoped_key=real_key,
            key=key,
            size=len(data),
        )

    async def get_state(self, key: str) -> Dict[str, Any] | None:
        """
        Retrieve the state object for the given key, or None if missing.

        If the key is outdated or expired, Redis will return None.
        """
        real_key = self._scoped_key(key)

        await self._ensure_client()
        raw = await self._client.get(real_key)
        if raw is None:
            return None

        try:
            return self._load_json(raw)
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Failed to parse state from Redis",
                key=key,
                error=str(exc),
            )
            return None

    async def delete_state(self, key: str) -> bool:
        """
        Delete the state entry for the given key.

        Returns True if the key existed and was deleted, False otherwise.
        """
        real_key = self._scoped_key(key)

        await self._ensure_client()
        deleted_count = await self._client.delete(real_key)
        self._logger.info(
            "State deleted from Redis",
            key=key,
            deleted_count=deleted_count,
        )
        return bool(deleted_count)

    async def has_state(self, key: str) -> bool:
        """
        Check whether a state entry exists for the given key.

        Returns True if the key exists, False otherwise.
        """
        real_key = self._scoped_key(key)

        await self._ensure_client()
        exists = await self._client.exists(real_key)
        return exists > 0

    # Utilities ------------------------------------------------------------

    async def _ensure_client(self) -> None:
        """Ensure the Redis client is connected."""
        if self._client:
            return
        await self.connect()

    def _scoped_key(self, key: str) -> str:
        """Prefix the logical key with a namespace."""
        return f"adp:state:{key}"

    def _dump_json(self, obj: Mapping[str, Any]) -> str:
        """Serialize an object to JSON string."""
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    def _load_json(self, text: str) -> Dict[str, Any]:
        """Deserialize JSON string into a dict."""
        return json.loads(text)
