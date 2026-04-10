"""
Agentic Development Platform - LLM provider factory.

A DIP‑compliant factory that instantiates `LLMProvider` implementations from
logical model names, so that higher‑level agents can depend only on the abstract
`LLMFactory` interface.
"""

from enum import Enum
from typing import Dict, Any, List
from abc import ABC, abstractmethod

from core.llm.llm_provider import LLMProvider
from core.llm.claude_provider import ClaudeProvider
from core.llm.ollama_provider import OllamaProvider


class LLMBackendType(Enum):
    """
    Enum of supported LLM backends in the platform.
    """
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class LLMFactory(ABC):
    """
    Abstract factory for LLM provider instances.

    Concrete subclasses implement provider selection and configuration mapping
    for a specific environment (e.g. dev, staging, prod). The returned
    `LLMProvider` may be shared across multiple agents inside the same process.
    """

    @abstractmethod
    def create_provider(self, model_id: str, backend: LLMBackendType, config: dict) -> LLMProvider:
        """
        Create an `LLMProvider` instance for the given model and backend.

        Args:
            model_id: Logical model identifier (e.g. "claude-3-sonnet", "llama3.1-70b").
            backend: Logical backend type (e.g. `LLMBackendType.ANTHROPIC`).
            config: Backend‑specific configuration dictionary.

        Returns:
            A configured `LLMProvider` instance.

        Raises:
            ValueError: If the backend is not supported.
        """
        raise NotImplementedError


class DefaultLLMFactory(LLMFactory):
    """
    Default implementation of the LLM factory, using a simple mapping from
    backend to provider class.

    In production you can extend this to support multi‑model routing, failover,
    and provider pools.
    """

    def __init__(self, global_config: Dict[str, Any] = None) -> None:
        """
        Initialize the default factory.

        Args:
            global_config: Optional global configuration (e.g. default API keys, base URLs).
        """
        self._global_config = global_config or {}
        self._providers: Dict[str, LLMProvider] = {}
        self._logger = None  # Set from structlog later in concrete app context.

    def create_provider(
        self,
        model_id: str,
        backend: LLMBackendType,
        config: dict,
    ) -> LLMProvider:
        """
        Instantiate the appropriate `LLMProvider` subclass for the given backend
        and merge it with global configuration.
        """
        # Blend global config with local config (local wins)
        effective_config = self._global_config.copy()
        effective_config.update(config)

        # Fast‑path reuse if already created under the same key
        cache_key = f"{backend.value}:{model_id}"
        if cache_key in self._providers:
            return self._providers[cache_key]

        # Select provider class
        provider_class = {
            LLMBackendType.ANTHROPIC: ClaudeProvider,
            LLMBackendType.OLLAMA: OllamaProvider,
        }.get(backend)

        if not provider_class:
            raise ValueError(f"Unsupported LLM backend: {backend}")

        # Create and cache
        provider = provider_class(model_id=model_id, config=effective_config)
        self._providers[cache_key] = provider
        return provider

    def list_backends(self) -> List[LLMBackendType]:
        """
        Return the list of backend types supported by this factory.
        """
        return list(LLMBackendType)

    async def close_all(self) -> None:
        """
        Close all instantiated providers, releasing underlying connections.
        """
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
