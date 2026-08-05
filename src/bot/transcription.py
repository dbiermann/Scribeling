"""Per-speaker live transcription via AudioSink: buffers PCM per user, flushes on a silence
debounce, transcribes via the STT model, and writes the result to a local .txt file.
"""

from __future__ import annotations

import asyncio
import audioop  # stdlib, removed in Python 3.13+; swap for the `audioop-lts`

# backport or a numpy resampler if this project ever upgrades.
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import discord
import numpy as np
from discord.ext import voice_recv

from bot.stt_model import Transcriber

log = logging.getLogger(__name__)

# 300ms of raw 48kHz/16-bit/stereo PCM. Chunks shorter than this are almost
# always a stray packet or breath, not real speech worth an inference call.
MIN_UTTERANCE_BYTES = int(0.3 * 48_000 * 2 * 2)


def pcm_stereo48k_to_mono16k_float32(pcm: bytes) -> np.ndarray:
    """Convert discord-ext-voice-recv's raw PCM (48kHz, stereo, 16-bit) into
    the float32 mono 16kHz array faster-whisper expects."""
    mono = audioop.tomono(pcm, 2, 0.5, 0.5)
    resampled, _ = audioop.ratecv(mono, 2, 1, 48_000, 16_000, None)
    samples = np.frombuffer(resampled, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


@dataclass
class _SpeakerState:
    member: discord.User | discord.Member
    buffer: bytearray = field(default_factory=bytearray)
    timer_handle: asyncio.TimerHandle | None = None
    flush_task: asyncio.Task | None = None


class TranscriptionSink(voice_recv.AudioSink):
    """Buffers each speaker's audio and transcribes it once they pause."""

    def __init__(
        self,
        *,
        transcriber: Transcriber,
        executor: ThreadPoolExecutor,
        transcripts_dir: str,
        silence_debounce_s: float,
    ) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._executor = executor
        self._silence_debounce_s = silence_debounce_s
        self._speakers: dict[int, _SpeakerState] = {}

        os.makedirs(transcripts_dir, exist_ok=True)
        start_time = datetime.now()
        self.output_path = os.path.join(
            transcripts_dir, f"{start_time:%Y-%m-%d_%H-%M-%S}.txt"
        )
        self._file = open(self.output_path, "w", encoding="utf-8")

    def wants_opus(self) -> bool:
        return False

    # -- called on the library's PacketRouter thread ------------------------
    def write(
        self, user: discord.User | discord.Member | None, data: voice_recv.VoiceData
    ) -> None:
        if user is None or getattr(user, "bot", False):
            return
        self.client.loop.call_soon_threadsafe(self._on_audio, user, bytes(data.pcm))

    # -- everything below here runs on the event loop thread ----------------
    def _on_audio(self, user: discord.User | discord.Member, pcm: bytes) -> None:
        state = self._speakers.get(user.id)
        if state is None:
            state = _SpeakerState(member=user)
            self._speakers[user.id] = state
        state.member = user  # keep the freshest Member (display name can change)
        state.buffer.extend(pcm)

        if state.timer_handle is not None:
            state.timer_handle.cancel()
        state.timer_handle = self.client.loop.call_later(
            self._silence_debounce_s, self._trigger_flush, user.id
        )

    def _trigger_flush(self, user_id: int) -> None:
        state = self._speakers.get(user_id)
        if state is None:
            return
        state.timer_handle = None
        state.flush_task = self.client.loop.create_task(self._flush(state))

    async def _flush(self, state: _SpeakerState) -> None:
        if not state.buffer:
            return
        pcm_bytes = bytes(state.buffer)
        state.buffer.clear()

        if len(pcm_bytes) < MIN_UTTERANCE_BYTES:
            return

        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(
                self._executor, self._transcribe, pcm_bytes
            )
        except Exception:
            log.exception("Transcription failed for %s", state.member)
            return

        if text:
            self._write_line(state.member, text)

    # -- runs in the executor thread, never the loop -------------------------
    def _transcribe(self, pcm_bytes: bytes) -> str:
        audio = pcm_stereo48k_to_mono16k_float32(pcm_bytes)
        return self._transcriber.transcribe(audio)

    def _write_line(self, member: discord.User | discord.Member, text: str) -> None:
        name = getattr(member, "display_name", None) or str(member)
        self._file.write(f"{name}: {text}\n")
        self._file.flush()

    async def flush_pending(self) -> None:
        """Transcribe whatever's still buffered for every speaker. Call this
        before disconnecting so the last few words aren't silently dropped."""
        for state in list(self._speakers.values()):
            if state.timer_handle is not None:
                state.timer_handle.cancel()
                state.timer_handle = None
            await self._flush(state)

    @voice_recv.AudioSink.listener()
    def on_voice_member_disconnect(
        self, member: discord.Member | None, ssrc: int | None
    ) -> None:
        if member is None:
            return
        self.client.loop.call_soon_threadsafe(self._drop_speaker, member.id)

    def _drop_speaker(self, user_id: int) -> None:
        state = self._speakers.pop(user_id, None)
        if state is None:
            return
        if state.timer_handle is not None:
            state.timer_handle.cancel()
        if state.buffer:
            self.client.loop.create_task(self._flush(state))

    # -- called from a bare (non-loop) thread by AudioReader.stop() ---------
    def cleanup(self) -> None:
        # AudioSink._voice_client is only set once a listen session actually
        # attaches (AudioReader.__init__); a sink discarded before that (e.g.
        # VoiceRecvClient.listen() raised) never gets it, and self.client
        # would raise AttributeError instead of the None it implies.
        if getattr(self, "_voice_client", None) is None:
            return
        client = self.client
        if client is None or client.loop.is_closed():
            return
        client.loop.call_soon_threadsafe(self._cleanup_on_loop)

    def _cleanup_on_loop(self) -> None:
        for state in self._speakers.values():
            if state.timer_handle is not None:
                state.timer_handle.cancel()
            if state.flush_task is not None and not state.flush_task.done():
                state.flush_task.cancel()
        self._speakers.clear()
        self._file.close()
