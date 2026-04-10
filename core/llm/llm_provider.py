"""
Agentic Development Platform - Generic LLM provider interface.

This module defines the abstract contract any LLM‑backed component must
implement, so that agents and orchestrators remain provider‑agnostic.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio
import structlog


log = structlog.get_logger(__name__)


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers in the platform.

    This interface decouples agent logic from concrete LLM vendors (Claude,
    Ollama, etc.), allowing the system to swap providers transparently and
    to support multi‑model routing later.
    """

    def __init__(self, model_id: str, config: dict) -> None:
        """
        Initialize the LLM provider.

        Args:
            model_id: Logical identifier for the model (e.g. "claude-3", "llama-3.1-70b").
            config: Provider‑specific configuration values (API key, host, etc.).
        """
        self.model_id = model_id
        self.config = config
        self._logger = log.bind(model_id=model_id, provider_type=self.__class__.__name__)

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Test whether the LLM provider is reachable and correctly configured.

        Returns:
            True if the provider is reachable and authorized; False otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
        extra_args: Optional[dict] = None,
    ) -> str:
        """
        Run a single text‑generation query against the LLM.

        The method abstracts away the concrete API (e.g. streaming vs. blocking,
        request format, JSON‑schema), so that calling code only needs to care
        about the logical prompt and sampling parameters.

        Args:
            prompt: Full text input to the model.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature; higher values increase randomness.
            stop_sequences: Optional list of strings at which to stop generation.
            extra_args: Provider‑specific extra parameters (e.g. system prompts,
                        tools, JSON‑schema, etc.), passed without interpretation.

        Returns:
            Model’s text output (without any decoration or metadata).

        Raises:
            RuntimeError: On provider‑specific communication or misconfiguration errors.
        """
        raise NotImplementedError

    @abstractmethod
    async def chat(
        self,
        messages: list[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
        extra_args: Optional[dict] = None,
    ) -> str:
        """
        Run a chat‑style query with a message history, using the same provider.

        Semantically equivalent to `generate` for the first‑class “chat” API
        exposed by many LLMs, but with a structured list of role‑message pairs.

        Args:
            messages: List of dictionaries with "role" and "content" keys.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature.
            stop_sequences: Optional stop sequences.
            extra_args: Provider‑specific extras.

        Returns:
            Assistant’s reply text.

        Raises:
            RuntimeError: On provider errors.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """
        Release any long‑lived resources (connections, sessions, etc.).

        Default no‑op implementation; concrete providers can override.
        """
        pass


class LLMProviderError(Exception):
    """
    Domain exception for anything that goes wrong with an LLM provider.

    This exception is used everywhere outside `llm_provider` itself so that
    the rest of the platform does not depend on provider‑specific error types.
    """
    pass


# async helper for raising LLM‑level errors with consistent wrapping
async def wrap_llm_errors(func, *args, **kwargs) -> str:
    """
    Helper that wraps an LLM provider call in standardized exception handling.

    Used by concrete providers to avoid repeating try‑except blocks.
    """
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        raise LLMProviderError(f"LLM provider error: {str(e)}") from e
