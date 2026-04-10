"""
Agentic Development Platform - Ollama provider.

An LLM provider that talks to a local Ollama server via HTTP, using the `openai`
compatibility API endpoint.
"""

import asyncio
from typing import Dict, Any, Optional, List
from typing_extensions import override

import httpx
from openai import AsyncOpenAI

from core.llm.llm_provider import LLMProvider, wrap_llm_errors


class OllamaProvider(LLMProvider):
    """
    LLM provider implementation for an Ollama server exposed via the OpenAI‑compatible API.

    This allows the platform to use any Ollama‑backed model (e.g. `llama3.1:70b`,
    `phi3`, etc.) through the same provider interface as cloud‑based models.
    """

    def __init__(self, model_id: str, config: dict) -> None:
        """
        Initialize the Ollama provider.

        Expected keys in `config`:
        - "base_url" (str): URL of the Ollama‑compatible OpenAI API (e.g. "http://localhost:11434/v1").
        - "api_key" (optional str): Ollama often ignores this, but the client expects it.

        Args:
            model_id: Ollama model name (e.g. "llama3.1:70b").
            config: Configuration dictionary.
        """
        super().__init__(model_id, config)
        self._client = AsyncOpenAI(
            api_key=config.get("api_key", "ollama"),
            base_url=config["base_url"],
        )
        self._logger.info("OllamaProvider initialized", model_id=model_id)

    @override
    async def health_check(self) -> bool:
        """
        Check Ollama connectivity by listing available models.
        """
        try:
            # List models; we don't care about the result, just whether it succeeds.
            await wrap_llm_errors(
                self._client.models.list,
            )
            self._logger.info("OllamaProvider health check success")
            return True
        except Exception as e:
            self._logger.warning("OllamaProvider health check failed", error=str(e))
            return False

    @override
    async def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
        extra_args: Optional[dict] = None,
    ) -> str:
        """
        Run a single‑turn text generation using the OpenAI‑compatible chat API.

        For Ollama, `generate` is mapped to a single `user` message; `extra_args`
        lets caller pass flags like `presence_penalty`, `frequency_penalty`, etc.
        """
        payload = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }
        if stop_sequences:
            payload["stop"] = stop_sequences
        if extra_args:
            payload.update(extra_args)

        # Use `.chat.completions.create` but treat it as a single‑turn text generation.
        resp = await wrap_llm_errors(
            self._client.chat.completions.create,
            **payload,
        )
        choice = resp.choices[0]
        return choice.message.content.strip() if choice.message.content else ""

    @override
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[List[str]] = None,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Run a chat‑style query using the OpenAI‑compatible API.

        The `messages` list is passed through, with `max_tokens` and `temperature`
        overridden by the arguments and `extra_args` merged.
        """
        payload = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if stop_sequences:
            payload["stop"] = stop_sequences
        if extra_args:
            payload.update(extra_args)

        resp = await wrap_llm_errors(
            self._client.chat.completions.create,
            **payload,
        )
        choice = resp.choices[0]
        return choice.message.content.strip() if choice.message.content else ""

    @override
    async def close(self) -> None:
        """
        Close the underlying HTTP transport.
        """
        await self._client.close()
