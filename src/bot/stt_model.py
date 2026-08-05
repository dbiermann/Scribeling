"""Speech-to-text backend. `TranscriptionSink` only depends on the
`Transcriber` protocol; the faster-whisper backend (and its model-loading/
fallback quirks) lives here so it doesn't touch anything else.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np
from faster_whisper import WhisperModel

from bot.config import Settings

log = logging.getLogger(__name__)


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe mono float32 16kHz samples in [-1, 1] into text.

        Transcriber protocol class allows for easy addition of other speech to text models later on.
        Only make sure that the new STT models have a transcribe class method.
        """

        ...


class FasterWhisperTranscriber:
    def __init__(
        self, model: WhisperModel, language: str | None, initial_prompt: str | None
    ) -> None:
        self._model = model
        self._language = language or None
        self._initial_prompt = initial_prompt or None
        self._lock = threading.Lock()

    def transcribe(self, audio: np.ndarray) -> str:
        with self._lock:
            segments, _info = self._model.transcribe(
                audio,
                beam_size=5,
                vad_filter=True,
                language=self._language,
                initial_prompt=self._initial_prompt,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()


def load_transcriber(settings: Settings) -> Transcriber:
    try:
        model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    except RuntimeError:
        if settings.whisper_device == "cpu":
            raise
        log.exception(
            "Failed to load the Whisper model on device=%r (compute_type=%r); "
            "falling back to CPU (int8), so the bot can still start. This "
            "usually means the host's NVIDIA driver is too old for the CUDA "
            "runtime ctranslate2 needs -- run `nvidia-smi` on the host and "
            "check the driver's max supported CUDA version, then update the "
            "driver to restore GPU transcription.",
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        model = WhisperModel(
            settings.whisper_model_size, device="cpu", compute_type="int8"
        )
    return FasterWhisperTranscriber(
        model, settings.whisper_language, settings.whisper_initial_prompt
    )
