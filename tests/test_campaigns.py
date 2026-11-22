from __future__ import annotations

import pytest

from bot.campaigns import campaign_paths, ensure_campaign_dirs, normalize_campaign_name
from bot.config import Settings


def test_campaign_defaults() -> None:
    # conftest leaves DATA_DIR and DEFAULT_CAMPAIGN blank.
    s = Settings()
    assert s.data_dir == "/app/data"
    assert s.default_campaign == "default"
    assert s.campaign().root == "/app/data/campaigns/default"


def test_campaign_layout(tmp_path) -> None:
    paths = campaign_paths(str(tmp_path), "grenzfeste")
    root = tmp_path / "campaigns" / "grenzfeste"
    assert paths.root == str(root)
    assert paths.campaign_file == str(root / "campaign.txt")
    assert paths.settings_file == str(root / "campaign.toml")
    assert paths.transcripts_dir == str(root / "transcripts")
    assert paths.notes_dir == str(root / "notes")


def test_ensure_creates_only_the_bot_folders(tmp_path) -> None:
    paths = campaign_paths(str(tmp_path), "tiamat")
    ensure_campaign_dirs(paths)
    ensure_campaign_dirs(paths)  # a second call is fine
    root = tmp_path / "campaigns" / "tiamat"
    assert sorted(p.name for p in root.iterdir()) == ["notes", "transcripts"]


def test_ensure_keeps_group_files(tmp_path) -> None:
    paths = campaign_paths(str(tmp_path), "tiamat")
    root = tmp_path / "campaigns" / "tiamat"
    root.mkdir(parents=True)
    (root / "campaign.txt").write_text("# Setting\nTiamat", encoding="utf-8")
    ensure_campaign_dirs(paths)
    assert (root / "campaign.txt").read_text(encoding="utf-8") == "# Setting\nTiamat"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("grenzfeste", "grenzfeste"),
        ("  Grenzfeste ", "grenzfeste"),
        ("tiamat-2", "tiamat-2"),
        ("curse_of_x", "curse_of_x"),
        ("a" * 40, "a" * 40),
    ],
)
def test_valid_names(raw: str, expected: str) -> None:
    assert normalize_campaign_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "..",
        "../etc",
        "a/b",
        "a\\b",
        ".hidden",
        "-flag",
        "two words",
        "grenzfeste.txt",
        "a" * 41,
        "größe",
    ],
)
def test_invalid_names(raw: str) -> None:
    with pytest.raises(ValueError, match="Invalid campaign name"):
        normalize_campaign_name(raw)


def test_campaign_name_from_discord_is_checked() -> None:
    with pytest.raises(ValueError):
        Settings().campaign("../../etc")


def test_default_campaign_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_CAMPAIGN", "Grenzfeste")
    assert Settings().default_campaign == "grenzfeste"


def test_invalid_default_campaign_stops_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEFAULT_CAMPAIGN", "../secrets")
    with pytest.raises(RuntimeError, match="DEFAULT_CAMPAIGN"):
        Settings()
