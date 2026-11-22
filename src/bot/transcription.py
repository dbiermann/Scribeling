"""Per-speaker live transcription via AudioSink: buffers PCM per user, flushes on a silence
debounce, transcribes via the STT model, and writes the result to a local .txt file.
"""

from __future__ import annotations

import asyncio
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
    the float32 mono 16kHz array faster-whisper expects.

    Pure numpy (no stdlib `audioop`, which Python 3.13 removed). 48kHz -> 16kHz
    is an exact factor of 3, so each output sample is the mean of 3 input
    samples, which also acts as a light anti-aliasing filter.
    """
    # Drop any partial stereo frame (4 bytes = 2 channels x 16-bit).
    samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 4], dtype=np.int16)
    mono = samples.astype(np.float32).reshape(-1, 2).mean(axis=1)
    mono = mono[: len(mono) - len(mono) % 3]
    return mono.reshape(-1, 3).mean(axis=1) / 32768.0


@dataclass
class _SpeakerState:
    member: discord.User | discord.Member
    buffer: bytearray = field(default_factory=bytearray)
    timer_handle: asyncio.TimerHandle | None = None


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
        # Every in-flight flush, including ones for speakers who already left,
        # so /stop can wait for them instead of cancelling finished work.
        self._pending_flushes: set[asyncio.Task] = set()

        os.makedirs(transcripts_dir, exist_ok=True)
        start_time = datetime.now()
        self.output_path = os.path.join(
            transcripts_dir, f"{start_time:%Y-%m-%d_%H-%M-%S}.txt"
        )
        # Stays open for the whole session; closed in cleanup().
        self._file = open(self.output_path, "w", encoding="utf-8")  # noqa: SIM115

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
        self._spawn_flush(state)

    def _spawn_flush(self, state: _SpeakerState) -> None:
        task = self.client.loop.create_task(self._flush(state))
        self._pending_flushes.add(task)
        task.add_done_callback(self._pending_flushes.discard)

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
        """Transcribe whatever's still buffered for every speaker and wait for
        any in-flight transcriptions. Call this before disconnecting so the
        last few words aren't silently dropped."""
        for state in list(self._speakers.values()):
            if state.timer_handle is not None:
                state.timer_handle.cancel()
                state.timer_handle = None
            if state.buffer:
                self._spawn_flush(state)
        if self._pending_flushes:
            await asyncio.gather(*self._pending_flushes, return_exceptions=True)

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
            self._spawn_flush(state)

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
        for task in list(self._pending_flushes):
            task.cancel()
        self._speakers.clear()
        self._file.close()
