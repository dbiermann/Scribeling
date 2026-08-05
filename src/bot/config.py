"""Centralized, env-driven configuration.

Keeping all env access in one place means the rest of the codebase never
calls os.environ directly, which makes testing and later refactors easier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Walks up from this file's directory to find the project-root .env, so it
# works regardless of the CWD the bot is launched from.
load_dotenv()


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def _env_int(name: str, required: bool = False) -> int:
    value = _env(name, required=required)
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name} must be a numeric channel ID, got: {value!r}"
        )


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name} must be a number, got: {value!r}"
        )


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(
        default_factory=lambda: _env("DISCORD_TOKEN", required=True)
    )
    guild_id: str = field(
        default_factory=lambda: _env("DISCORD_GUILD_ID")
    )  # optional, speeds up slash-cmd sync in dev
    command_channel_id: int = field(
        default_factory=lambda: _env_int("DISCORD_COMMAND_CHANNEL_ID", required=True)
    )

    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    transcripts_dir: str = field(
        default_factory=lambda: _env("TRANSCRIPTS_DIR", "transcripts")
    )

    # Local speech-to-text (faster-whisper)
    whisper_model_size: str = field(
        default_factory=lambda: _env("WHISPER_MODEL_SIZE", "base")
    )
    whisper_device: str = field(default_factory=lambda: _env("WHISPER_DEVICE", "cuda"))
    whisper_compute_type: str = field(
        default_factory=lambda: _env("WHISPER_COMPUTE_TYPE", "float16")
    )
    whisper_silence_debounce_s: float = field(
        default_factory=lambda: _env_float("WHISPER_SILENCE_DEBOUNCE_S", 0.6)
    )
    whisper_language: str = field(default_factory=lambda: _env("WHISPER_LANGUAGE"))
    whisper_initial_prompt: str = field(
        default_factory=lambda: _env(
            "WHISPER_INITIAL_PROMPT",
        )
    )


settings = Settings()
