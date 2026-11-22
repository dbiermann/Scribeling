"""Smoke tests: every module imports, and the pure helpers work.

None of these need a GPU, Discord or network access.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

MODULES = [
    "bot.campaigns",
    "bot.config",
    "bot.stt_model",
    "bot.transcription",
    "bot.voice_compat",
    "bot.main",
    "bot.cogs.ping",
    "bot.cogs.transcribe",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


def test_build_bot_does_not_connect() -> None:
    from bot.main import build_bot

    bot = build_bot()
    assert bot.command_prefix == "!"
    assert bot.intents.voice_states


def test_pcm_conversion_shape_and_range() -> None:
    from bot.transcription import pcm_stereo48k_to_mono16k_float32

    # 100 ms of 48 kHz stereo 16-bit PCM: a full-scale square wave on both channels.
    frames = 4_800
    samples = np.tile(
        np.array([32767, 32767, -32768, -32768], dtype=np.int16), frames // 2
    )
    out = pcm_stereo48k_to_mono16k_float32(samples.tobytes())

    assert out.dtype == np.float32
    assert abs(len(out) - frames // 3) <= 1  # 48 kHz -> 16 kHz, stereo -> mono
    assert out.min() >= -1.0 and out.max() <= 1.0


def test_pcm_conversion_silence_is_zero() -> None:
    from bot.transcription import pcm_stereo48k_to_mono16k_float32

    out = pcm_stereo48k_to_mono16k_float32(bytes(48_000 * 2 * 2 // 10))
    assert np.all(out == 0.0)


def test_fixtures_dir(fixtures_dir) -> None:
    lines = (
        (fixtures_dir / "sample_transcript.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert all(": " in line for line in lines)


async def test_async_tests_run() -> None:
    """pytest-asyncio is wired up, for the async notes pipeline later."""
    import asyncio

    await asyncio.sleep(0)
