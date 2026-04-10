"""
Agentic Development Platform - Speech‑to‑text transcription service.

This module wraps an ASR backend and exposes a simple async interface for
turning voice audio into text, keeping the rest of the platform agnostic
to whether Whisper, Faster‑Whisper, or some cloud service is used.
"""

from abc import ABC, abstractmethod
from typing import Literal
import asyncio
import structlog

from typing_extensions import TypedDict


log = structlog.get_logger(__name__)


# Allowed languages for the agentic voice system.
SupportedLanguage = Literal[
    "en",
    "hi",
    "te",
    "ta",
    "kn",
    "ml",
    "bn",
    "gu",
    "pa",
    "mr",
    "or",
    "as",
    "und",
]


class TranscriptionInput(TypedDict):
    """
    Input payload for the transcription service.
    """
    audio_bytes: bytes
    """Raw audio data (PCM or similar format)."""
    sample_rate: int
    """Sample rate in Hz (e.g. 16000)."""
    num_channels: int
    """Number of audio channels (usually 1 or 2)."""
    language: SupportedLanguage
    """Primary language code to bias the ASR model."""
    user_id: str
    """Tenant/user ID for quota and logging."""
    device_id: str
    """Device or session ID for context."""


class TranscriptionOutput(TypedDict):
    """
    Output payload from the transcription service.
    """
    text: str
    """Recognized text; empty if no speech or confidence is too low."""
    confidence: float
    """Overall confidence score [0.0, 1.0]."""
    language: SupportedLanguage
    """Detected or assumed language."""
    duration_sec: float
    """Duration of the audio segment in seconds."""
    timestamp: float
    """Monotonic timestamp at which transcription was triggered."""


class TranscriptionServiceError(Exception):
    """
    Domain exception for anything that goes wrong in the transcription layer.

    This shields calling code from provider‑specific exceptions.
    """
    pass


class TranscriptionService(ABC):
    """
    Abstract ASR service used by the agentic platform.

    Concrete subclasses (e.g. WhisperLocal, WhisperCloud, OllamaSpeech, etc.)
    implement the actual speech recognition logic, while agents and orchestrators
    only depend on this interface.
    """

    def __init__(self) -> None:
        self._logger = log.bind(service_type=self.__class__.__name__)

    @abstractmethod
    async def transcribe(self, inp: TranscriptionInput) -> TranscriptionOutput:
        """
        Transcribe a single audio segment into text.

        The concrete implementation may:

        - Use a local model (e.g. Faster‑Whisper) or a cloud API.
        - Run VAD or caller‑provided segmentation.
        - Bias to the `language` code but fall back to multilingual.

        Args:
            inp: Audio data and metadata.

        Returns:
            Structured transcription result with text and confidence.

        Raises:
            TranscriptionServiceError: On any recognition failure.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """
        Release any long‑lived resources (model handles, HTTP clients, etc.).

        Default no‑op implementation.
        """
        pass


# Simple async helper for uniform error wrapping.
def wrap_transcription_errors(func, *args, **kwargs) -> TranscriptionOutput:
    """
    Wrap a transcription provider call with standardized error handling.

    Used by concrete ASR providers to avoid repeating try‑except blocks.
    """
    try:
        return asyncio.run(func(*args, **kwargs))
    except Exception as e:
        raise TranscriptionServiceError(f"Transcription error: {str(e)}") from e
