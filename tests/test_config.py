from __future__ import annotations

import pytest

from bot.config import Settings


def test_settings_from_env() -> None:
    s = Settings()
    assert s.discord_token == "test-token"
    assert s.command_channel_id == 123456789
    assert s.whisper_device == "cpu"
    assert s.whisper_silence_debounce_s == 0.6
    assert s.whisper_language == ""


def test_missing_token_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "")
    with pytest.raises(RuntimeError, match="DISCORD_TOKEN"):
        Settings()


def test_non_numeric_channel_id_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_COMMAND_CHANNEL_ID", "general")
    with pytest.raises(RuntimeError, match="DISCORD_COMMAND_CHANNEL_ID"):
        Settings()


def test_float_default_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_SILENCE_DEBOUNCE_S", "")
    assert Settings().whisper_silence_debounce_s == 0.6

    monkeypatch.setenv("WHISPER_SILENCE_DEBOUNCE_S", "soon")
    with pytest.raises(RuntimeError, match="WHISPER_SILENCE_DEBOUNCE_S"):
        Settings()
