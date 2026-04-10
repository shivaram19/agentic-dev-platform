"""
Agentic Development Platform - Voice Command Handler.

Coordinates the end-to-end voice command pipeline:
  1. Receive audio from device.
  2. Transcribe to text.
  3. Parse intent.
  4. Dispatch to the appropriate agent or tool.
"""

import asyncio
from typing import Dict, Any
from typing_extensions import TypedDict

import structlog

from voice.transcription import TranscriptionService, TranscriptionInput, TranscriptionOutput
from voice.intent_parser import IntentParser, ParsedIntent
from core.llm.llm_factory import LLMFactory

log = structlog.get_logger(__name__)


class VoiceCommandContext(TypedDict):
    """Context metadata for a single voice command."""
    user_id: str
    project_id: str
    device_id: str
    agent_id: str


class VoiceCommandResult(TypedDict):
    """Result of processing a voice command."""
    success: bool
    error: str | None
    parsed_intent: ParsedIntent
    agent_response: str


async def wrap_transcription_errors(
    fn,
    inp: TranscriptionInput,
) -> TranscriptionOutput:
    """
    Wraps a transcription coroutine and surfaces errors uniformly.

    SRP: error wrapping is isolated here so VoiceCommandHandler
    stays clean and testable.
    """
    try:
        return await fn(inp)
    except Exception as exc:
        raise RuntimeError(f"Transcription failed: {exc}") from exc


class VoiceCommandHandler:
    """
    Coordinator for voice-command-driven agent interactions.

    Single Responsibility: orchestrate the ASR → NLU → dispatch pipeline.
    All implementation details are hidden behind injected abstractions (DIP).
    """

    # Intent → human-readable response map (OCP: extend without modifying)
    _INTENT_RESPONSES: Dict[str, str] = {
        "create_code":           "Creating a new code file for you. This may take a moment.",
        "run_tests":             "Running tests on the current project.",
        "debug_error":           "Looking into the error you mentioned.",
        "commit_code":           "Committing your changes now.",
        "refactor_code":         "Refactoring the code to improve structure and readability.",
        "add_tool":              "Adding a new tool to your project.",
        "ask_project_context":   "Fetching the current project context from the knowledge graph.",
        "unsupported":           "Sorry, I can't handle that command yet.",
    }

    def __init__(
        self,
        transcription_service: TranscriptionService,
        intent_parser: IntentParser,
        llm_factory: LLMFactory,
    ) -> None:
        """
        Args:
            transcription_service: ASR backend (Whisper, etc.)
            intent_parser:         NLU backend for intent extraction.
            llm_factory:           LLM factory for agent-level reasoning.
        """
        self._transcription_service = transcription_service
        self._intent_parser = intent_parser
        self._llm_factory = llm_factory
        self._logger = log.bind(handler_type=self.__class__.__name__)

    async def handle_voice_command(
        self,
        audio_input: TranscriptionInput,
        context: VoiceCommandContext,
    ) -> VoiceCommandResult:
        """
        End-to-end handler for a single voice command.

        Flow: Transcribe → Parse Intent → Dispatch → Return Result.
        """
        user_context = {
            "user_id":        context["user_id"],
            "current_project": context["project_id"],
            "last_agent":     context["agent_id"],
            "user_profile":   "default_profile",
        }

        try:
            # ── Step 1: Transcribe ────────────────────────────────────────
            self._logger.info(
                "VoiceCommandHandler.transcribe",
                user_id=context["user_id"],
                project_id=context["project_id"],
            )

            transcription: TranscriptionOutput = await wrap_transcription_errors(
                self._transcription_service.transcribe,
                inp=audio_input,
            )

            if not transcription["text"].strip():
                return self._empty_speech_result()

            # ── Step 2: Parse Intent ──────────────────────────────────────
            self._logger.info(
                "VoiceCommandHandler.parse_intent",
                user_id=context["user_id"],
                project_id=context["project_id"],
                text=transcription["text"],
            )

            parsed_intent: ParsedIntent = await self._intent_parser.parse_intent(
                text=transcription["text"],
                user_context=user_context,
            )

            # ── Step 3: Dispatch ──────────────────────────────────────────
            agent_response = self._resolve_response(parsed_intent["intent_type"])

            self._logger.info(
                "VoiceCommandHandler.dispatched",
                intent_type=parsed_intent["intent_type"],
                confidence=parsed_intent["confidence"],
            )

            return {
                "success":       True,
                "error":         None,
                "parsed_intent": parsed_intent,
                "agent_response": agent_response,
            }

        except Exception as exc:
            self._logger.warning(
                "VoiceCommandHandler.failed",
                user_id=context.get("user_id"),
                project_id=context.get("project_id"),
                error=str(exc),
            )
            return self._error_result(str(exc))

    # ── Private helpers ───────────────────────────────────────────────────

    def _resolve_response(self, intent_type: str) -> str:
        """Map intent type to a human-readable response string."""
        return self._INTENT_RESPONSES.get(intent_type, "I didn't understand that command.")

    def _empty_speech_result(self) -> VoiceCommandResult:
        """Return a result for when no speech was detected."""
        return {
            "success": False,
            "error": "No speech detected or transcription was empty.",
            "parsed_intent": {
                "intent_type": "unknown",
                "slots":       {},
                "raw_text":    "",
                "confidence":  0.0,
                "llm_model":   "none",
                "llm_backend": "none",
            },
            "agent_response": "I didn't hear anything.",
        }

    def _error_result(self, error_message: str) -> VoiceCommandResult:
        """Return a result for when the pipeline throws an unexpected error."""
        return {
            "success": False,
            "error": f"Voice command processing failed: {error_message}",
            "parsed_intent": {
                "intent_type": "unknown",
                "slots":       {},
                "raw_text":    "n/a",
                "confidence":  0.0,
                "llm_model":   "none",
                "llm_backend": "none",
            },
            "agent_response": "Something went wrong processing your command.",
        }