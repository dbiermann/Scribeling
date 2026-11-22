"""Centralized, env-driven configuration.

Keeping all env access in one place means the rest of the codebase never
calls os.environ directly, which makes testing and later refactors easier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from bot.campaigns import CampaignPaths, campaign_paths, normalize_campaign_name

# Walks up from this file's directory to find the project-root .env, so it
# works regardless of the CWD the bot is launched from.
load_dotenv()

# Pinned in SCRIB-01. Changing the default model is a code change; a group can
# still override it with OPENAI_MODEL_ID.
DEFAULT_OPENAI_MODEL_ID = "gpt-6-luna"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    # An empty value (`NAME=` in .env) falls back to the default, the same as
    # an unset one, so blank lines copied from .env.example are harmless.
    return value or default or ""


def _env_int(
    name: str,
    default: int = 0,
    required: bool = False,
    expected: str = "a whole number",
) -> int:
    value = _env(name, required=required)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name} must be {expected}, got: {value!r}"
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


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name).strip().lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise RuntimeError(
        f"Environment variable {name} must be true or false, got: {value!r}"
    )


@dataclass(frozen=True)
class Settings:
    # Secrets use repr=False so logging or printing Settings never leaks them.
    discord_token: str = field(
        default_factory=lambda: _env("DISCORD_TOKEN", required=True), repr=False
    )
    guild_id: str = field(
        default_factory=lambda: _env("DISCORD_GUILD_ID")
    )  # optional, speeds up slash-cmd sync in dev
    command_channel_id: int = field(
        default_factory=lambda: _env_int(
            "DISCORD_COMMAND_CHANNEL_ID",
            required=True,
            expected="a numeric channel ID",
        )
    )

    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # All campaign data lives under DATA_DIR/campaigns/<name>/ (see
    # bot.campaigns). /app/data is the same path in the prod image (a mount)
    # and in the dev container (the repo is mounted at /app).
    data_dir: str = field(default_factory=lambda: _env("DATA_DIR", "/app/data"))
    # Used when a session is started without naming a campaign.
    default_campaign: str = field(
        default_factory=lambda: _env("DEFAULT_CAMPAIGN", "default")
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

    # Session notes (epic SCRIB-E1). Off by default; when off, none of the
    # settings below are checked and the bot behaves as before.
    # There is deliberately no system prompt setting: it ships in the code
    # (SCRIB-08).
    notes_enabled: bool = field(
        default_factory=lambda: _env_bool("NOTES_ENABLED", False)
    )
    openai_api_key: str = field(
        default_factory=lambda: _env("OPENAI_API_KEY"), repr=False
    )
    openai_model_id: str = field(
        default_factory=lambda: _env("OPENAI_MODEL_ID", DEFAULT_OPENAI_MODEL_ID)
    )
    # Includes reasoning tokens. 16000 is what the SCRIB-01 spike ran with;
    # its largest reply used about 6100.
    notes_max_output_tokens: int = field(
        default_factory=lambda: _env_int("NOTES_MAX_OUTPUT_TOKENS", 16_000)
    )
    notes_timeout_s: float = field(
        default_factory=lambda: _env_float("NOTES_TIMEOUT_S", 900.0)
    )
    # Google Docs upload (SCRIB-14/15). The service account is shared by all
    # campaigns; each campaign names its own doc with google_doc_id in its
    # campaign.toml.
    google_service_account_file: str = field(
        default_factory=lambda: _env("GOOGLE_SERVICE_ACCOUNT_FILE")
    )

    def __post_init__(self) -> None:
        try:
            # Store the canonical form, e.g. "Grenzfeste" -> "grenzfeste".
            name = normalize_campaign_name(self.default_campaign)
        except ValueError as e:
            raise RuntimeError(f"Environment variable DEFAULT_CAMPAIGN: {e}") from None
        object.__setattr__(self, "default_campaign", name)

        if not self.notes_enabled:
            return
        if not self.openai_api_key:
            raise RuntimeError(
                "NOTES_ENABLED is true but OPENAI_API_KEY is not set. "
                "Set the key, or set NOTES_ENABLED=false to run without notes."
            )
        if self.notes_max_output_tokens <= 0:
            raise RuntimeError(
                "Environment variable NOTES_MAX_OUTPUT_TOKENS must be more than 0, "
                f"got: {self.notes_max_output_tokens}"
            )
        if self.notes_timeout_s <= 0:
            raise RuntimeError(
                "Environment variable NOTES_TIMEOUT_S must be more than 0, "
                f"got: {self.notes_timeout_s}"
            )

    def campaign(self, name: str | None = None) -> CampaignPaths:
        """Folders for a campaign, or for DEFAULT_CAMPAIGN when name is None.

        Raises ValueError for an invalid name (e.g. one typed in Discord).
        """
        return campaign_paths(self.data_dir, name or self.default_campaign)

    @property
    def google_docs_enabled(self) -> bool:
        """Whether upload is possible at all. A campaign also needs a
        google_doc_id in its campaign.toml to be uploaded."""
        return self.notes_enabled and bool(self.google_service_account_file)


settings = Settings()
