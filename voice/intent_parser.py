"""
Agentic Development Platform - Voice intent parser.

Turns transcribed text into a structured “intent + slots” object, decoupled
from the concrete LLM or NLU backend used.
"""

import asyncio
from typing import Dict, Any, List, Literal
import structlog
from typing_extensions import TypedDict

from core.llm.llm_provider import LLMProvider, LLMProviderError
from core.llm.llm_factory import LLMFactory


log = structlog.get_logger(__name__)


# Example intent types for the agentic voice system.
IntentType = Literal[
    "create_code",
    "run_tests",
    "debug_error",
    "commit_code",
    "refactor_code",
    "add_tool",
    "ask_project_context",
    "unknown",
    "unsupported",
]


class IntentParserConfig(TypedDict):
    """
    Configuration for the intent parser.
    """
    default_model_id: str
    """LLM model used for intent extraction."""
    default_backend: Literal["anthropic", "ollama"]
    """LLM backend type."""
    max_tokens: int
    """Maximum tokens for the parsing query."""
    temperature: float
    """Sampling temperature (usually low for deterministic parsing)."""


class ParsedIntent(TypedDict):
    """
    Output of the intent parser.
    """
    intent_type: IntentType
    """Normalized intent name."""
    slots: Dict[str, Any]
    """Structured arguments (e.g. file path, tool name, error message)."""
    raw_text: str
    """Original transcribed text."""
    confidence: float
    """Confidence in the parsed intent [0.0, 1.0]."""
    llm_model: str
    """LLM model string used for parsing."""
    llm_backend: str
    """LLM backend used (e.g. "anthropic")."""


class IntentParserError(Exception):
    """
    Domain exception for failures in intent parsing.
    """
    pass


class IntentParser:
    """
    NLU component that converts transcribed voice text into a structured intent.

    This class is intentionally kept small and contract‑driven:

    - It depends only on the `LLMProvider` and `LLMFactory` abstractions.
    - It does not care whether the underlying model is Claude, Ollama, or something else.

    In production you can extend it with:

    - Example‑based prompt templates per intent.
    - Caching of recently seen utterances.
    - Local fallbacks for low‑confidence parses.
    """

    def __init__(
        self,
        factory: LLMFactory,
        config: IntentParserConfig,
    ) -> None:
        """
        Initialize the intent parser.

        Args:
            factory: LLM factory to obtain the LLM provider.
            config: Parser configuration.
        """
        self._factory = factory
        self._config = config
        self._logger = log.bind(intent_parser_type=self.__class__.__name__)

        # Eager‑type mappings for the enum.
        self._intent_names: List[str] = list(
            IntentParserConfig.__annotations__["intent_type"].__args__
        )
        self._logger.info("IntentParser initialized", intent_types=self._intent_names)

    async def parse_intent(self, text: str, user_context: Dict[str, Any]) -> ParsedIntent:
        """
        Parse an utterance (from transcription) into a structured intent.

        The method sends a single query to the configured LLM and expects
        a deterministic JSON‑like output, even if the underlying model is large‑scale
        and generative.

        Args:
            text: Transcribed voice text.
            user_context: Additional context (project, agent, device, etc.).

        Returns:
            Structured intent object with type, slots, and confidence.

        Raises:
            IntentParserError: On provider or parsing errors.
        """
        backend_type = {
            "anthropic": "anthropic",
            "ollama": "ollama",
        }.get(self._config["default_backend"], "anthropic")

        backend = (
            "anthropic"
            if self._config["default_backend"] == "anthropic"
            else "ollama"
        )
        provider = self._factory.create_provider(
            model_id=self._config["default_model_id"],
            backend=backend_type,
            config={},
        )

        # Build a compact system prompt focused purely on intent classification.
        system_prompt = (
            "You are an intent parser for a voice‑driven agentic developer platform.\n"
            "Your task is to convert a user command into a structured intent type and slots.\n"
            "You must respond only with a JSON object that has exactly these fields:\n"
            "  - `intent_type` (one of: create_code, run_tests, debug_error, commit_code, refactor_code, add_tool, ask_project_context, unknown, unsupported)\n"
            "  - `slots` (a dictionary of key–value arguments, e.g. file_path, target_func, error_message)\n"
            "  - `confidence` (float between 0.0 and 1.0; estimate how clearly the intent is stated in the utterance)\n"
            "If the command is ambiguous or cannot be mapped to one of the given types, use `intent_type: \"unknown\"`.\n"
            "If the command is outside the platform’s capabilities, use `intent_type: \"unsupported\"`.\n"
        )

        # Build a concrete user‑message context.
        context_str = (
            f"User profile: {user_context.get('user_profile', 'no profile')}; "
            f"Current project: {user_context.get('current_project', 'no project')}; "
            f"Last agent: {user_context.get('last_agent', 'no agent')}."
        )

        try:
            # For a real system you’d flesh out a richer prompt template.
            prompt = (
                f"{system_prompt}\n\n"
                f"Context: {context_str}\n\n"
                f"User command: {text}\n\n"
                "Respond only with the structured JSON object as described."
            )

            # Run the LLM and then parse the output.
            raw_response = await provider.generate(
                prompt=prompt,
                max_tokens=self._config["max_tokens"],
                temperature=self._config["temperature"],
                stop_sequences=["}"],
            )

            # In a real system you’d parse raw_response as JSON and validate the schema.
            # For simplicity here we mock a fixed‑field schema.
            # Assume the model outputs something like:
            # { "intent_type": "create_code", "slots": {"file_path": "src/main.py"}, "confidence": 0.95 }
            # and that this is already valid.

            # Example: make this deterministic for demo.
            if "create" in text.lower() and "file" in text.lower():
                intent_type: IntentType = "create_code"
                slots = {"file_path": "src/auto_generated.py"}
                confidence = 0.9
            elif "test" in text.lower():
                intent_type = "run_tests"
                slots = {"test_suite": "unit_tests"}
                confidence = 0.8
            elif "debug" in text.lower():
                intent_type = "debug_error"
                slots = {"error_message": "HTTP 500 on /api/users"}
                confidence = 0.85
            elif "commit" in text.lower():
                intent_type = "commit_code"
                slots = {"message": "Auto‑generated commit from voice command"}
                confidence = 0.9
            else:
                intent_type = "unknown"
                slots = {}
                confidence = 0.5

            return {
                "intent_type": intent_type,
                "slots": slots,
                "raw_text": text,
                "confidence": confidence,
                "llm_model": self._config["default_model_id"],
                "llm_backend": self._config["default_backend"],
            }

        except LLMProviderError as e:
            raise IntentParserError(f"LLM provider error in intent parsing: {str(e)}") from e
        except Exception as e:
            raise IntentParserError(f"Failed to parse intent for text '{text}': {str(e)}") from e
