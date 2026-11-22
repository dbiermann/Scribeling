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


def test_blank_string_setting_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # `WHISPER_DEVICE=` copied blank from .env.example must not become "".
    monkeypatch.setenv("WHISPER_DEVICE", "")
    assert Settings().whisper_device == "cuda"


# -- Session notes (SCRIB-03) -------------------------------------------------


def _enable_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTES_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_notes_off_by_default_and_needs_nothing() -> None:
    # conftest leaves every notes setting blank, including OPENAI_API_KEY.
    s = Settings()
    assert s.notes_enabled is False
    assert s.google_docs_enabled is False


def test_notes_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_notes(monkeypatch)
    s = Settings()
    assert s.openai_model_id == "gpt-6-luna"
    assert s.notes_context_tokens == 0  # 0 = the model's own context window
    assert s.notes_max_output_tokens == 16_000
    assert s.notes_timeout_s == 900.0


def test_notes_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_notes(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL_ID", "gpt-7")
    monkeypatch.setenv("NOTES_CONTEXT_TOKENS", "50000")
    monkeypatch.setenv("NOTES_MAX_OUTPUT_TOKENS", "8000")
    monkeypatch.setenv("NOTES_TIMEOUT_S", "120.5")
    s = Settings()
    assert s.openai_model_id == "gpt-7"
    assert s.notes_context_tokens == 50_000
    assert s.notes_max_output_tokens == 8_000
    assert s.notes_timeout_s == 120.5


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_notes_enabled_true_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _enable_notes(monkeypatch)
    monkeypatch.setenv("NOTES_ENABLED", value)
    assert Settings().notes_enabled is True


def test_notes_enabled_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTES_ENABLED", "maybe")
    with pytest.raises(RuntimeError, match="NOTES_ENABLED"):
        Settings()


def test_notes_enabled_without_api_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTES_ENABLED", "true")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        Settings()


def test_missing_campaign_folder_is_fine(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Notes on, a campaign with no folder and no campaign.txt: startup is fine
    # and nothing is created until a session starts.
    _enable_notes(monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEFAULT_CAMPAIGN", "grenzfeste")
    s = Settings()
    assert s.campaign().campaign_file == str(
        tmp_path / "campaigns" / "grenzfeste" / "campaign.txt"
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NOTES_CONTEXT_TOKENS", "-1"),
        ("NOTES_CONTEXT_TOKENS", "lots"),
        ("NOTES_MAX_OUTPUT_TOKENS", "0"),
        ("NOTES_TIMEOUT_S", "0"),
    ],
)
def test_notes_numbers_validated(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    _enable_notes(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name):
        Settings()


def test_api_key_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_notes(monkeypatch)
    text = repr(Settings())
    assert "sk-test" not in text
    assert "test-token" not in text


def test_google_docs_needs_service_account(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_notes(monkeypatch)
    assert Settings().google_docs_enabled is False

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/secrets/key.json")
    assert Settings().google_docs_enabled is True

    # Never on while notes are off.
    monkeypatch.setenv("NOTES_ENABLED", "false")
    assert Settings().google_docs_enabled is False


def test_startup_logs_google_docs_off(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from bot.main import log_notes_status

    _enable_notes(monkeypatch)
    with caplog.at_level("INFO", logger="bot.main"):
        log_notes_status(Settings())
    assert "Google Docs upload off" in caplog.text
    assert "saved locally only" in caplog.text


def test_startup_logs_google_docs_on(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from bot.main import log_notes_status

    _enable_notes(monkeypatch)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/secrets/key.json")
    with caplog.at_level("INFO", logger="bot.main"):
        log_notes_status(Settings())
    assert "Google Docs upload on" in caplog.text


def test_startup_silent_when_notes_off(caplog: pytest.LogCaptureFixture) -> None:
    from bot.main import log_notes_status

    with caplog.at_level("DEBUG", logger="bot.main"):
        log_notes_status(Settings())
    assert caplog.records == []
