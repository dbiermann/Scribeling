"""Shared test setup.

`bot.config` builds its Settings when it is imported and requires a Discord
token, so placeholder values are set here, before any test imports `bot.*`.
Setting every variable explicitly (even to an empty string) also stops
`load_dotenv()` from pulling in a developer's real `.env`, because it never
overrides variables that already exist. Tests therefore behave the same
locally and in CI, and never need real credentials, Discord, a GPU or an API key.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_ENV = {
    "DISCORD_TOKEN": "test-token",
    "DISCORD_GUILD_ID": "",
    "DISCORD_COMMAND_CHANNEL_ID": "123456789",
    "LOG_LEVEL": "WARNING",
    "DATA_DIR": "",
    "DEFAULT_CAMPAIGN": "",
    "WHISPER_MODEL_SIZE": "tiny",
    "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE_TYPE": "int8",
    "WHISPER_SILENCE_DEBOUNCE_S": "0.6",
    "WHISPER_LANGUAGE": "",
    "WHISPER_INITIAL_PROMPT": "",
    # Session notes: off, and blank so the code defaults apply.
    "NOTES_ENABLED": "false",
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL_ID": "",
    "NOTES_MAX_OUTPUT_TOKENS": "",
    "NOTES_TIMEOUT_S": "",
    "GOOGLE_SERVICE_ACCOUNT_FILE": "",
}
os.environ.update(TEST_ENV)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to tests/fixtures/, for sample transcripts and other test data."""
    return FIXTURES
