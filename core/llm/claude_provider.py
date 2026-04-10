"""
Agentic Development Platform - Claude LLM provider.

An MCP‑compatible LLM provider that talks to Anthropic’s Claude API.
"""

import asyncio
from typing import Dict, Any, Optional
from typing_extensions import override

from anthropic import AsyncAnthropic, APIError  # type: ignore
from anthropic.types import Message as AnthropicMessage  # type: ignore

from core.llm.llm_provider import LLMProvider, wrap_llm_errors


class ClaudeProvider(LLMProvider):
    """
    LLM provider implementation for Anthropic Claude.

    Uses the official `anthropic` client in async mode, and exposes the minimal
    `LLMProvider` interface so that agents can treat it as a black‑box endpoint.
    """

    def __init__(self, model_id: str, config: dict) -> None:
        """
        Initialize the Claude provider.

        Expected keys in `config`:
        - "api_key" (str): Anthropic API key.
        - Optional: "base_url" (str), "default_max_tokens" (int), "default_temperature" (float).

        Args:
            model_id: Claude model identifier (e.g. "claude-3-sonnet-20240229").
            config: Configuration dictionary.
        """
        super().__init__(model_id, config)
        self._client = AsyncAnthropic(
            api_key=config["api_key"],
            base_url=config.get("base_url"),
        )
        self._logger.info("ClaudeProvider initialized", model_id=model_id)

    @override
    async def health_check(self) -> bool:
        """
        Test connectivity to the Claude API by sending a small test message
        through the `messages` API.
        """
        try:
            # Use a generic tiny message to avoid long waits.
            resp: AnthropicMessage = await wrap_llm_errors(
                self._client.messages.create,
                model=self.model_id,
                max_tokens=1,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": "Can you respond with the word 'ok' only?",
                    },
                ],
            )
            is_ok = "ok" in (resp.content[0].text if resp.content else "").strip()
            self._logger.info("ClaudeProvider health check success", ok=is_ok)
            return is_ok
        except Exception as e:
            self._logger.warning("ClaudeProvider health check failed", error=str(e))
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
        Run a single‑turn text generation using the `messages` API.

        For Claude, `generate` is implemented as a single `user`‑role message;
        `extra_args` is merged into the top‑level request.
        """
        # Default call options
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

        # Override or augment with stop sequences
        if stop_sequences:
            payload["stop_sequences"] = stop_sequences

        # Merge any extra_args (e.g. system, tools, JSON schema)
        if extra_args:
            payload.update(extra_args)

        # Call with wrapper
        resp: AnthropicMessage = await wrap_llm_errors(
            self._client.messages.create,
            **payload,
        )
        content = resp.content[0].text if resp.content else ""
        return content.strip()

    @override
    async def chat(
        self,
        messages: list[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
        extra_args: Optional[dict] = None,
    ) -> str:
        """
        Run a chat‑style query using the same `messages` API.

        The `messages` list is passed unchanged except for `max_tokens`,
        `temperature`, and `stop_sequences`.
        """
        payload = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if stop_sequences:
            payload["stop_sequences"] = stop_sequences
        if extra_args:
            payload.update(extra_args)

        resp: AnthropicMessage = await wrap_llm_errors(
            self._client.messages.create,
            **payload,
        )
        content = resp.content[0].text if resp.content else ""
        return content.strip()

    @override
    async def close(self) -> None:
        """
        Close the underlying HTTP session in the Anthropic client.
        """
        await self._client.close()
