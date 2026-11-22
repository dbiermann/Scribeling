"""/transcribe's campaign option, with Discord replaced by mocks.

No voice connection, model or network: the cog gets a stand-in transcriber
and the voice channel's connect() returns a mock client.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.cogs import transcribe as transcribe_mod
from bot.config import Settings


@pytest.fixture
def cog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(transcribe_mod, "settings", Settings())
    cog = transcribe_mod.TranscribeCog(bot=MagicMock())
    cog._transcriber = MagicMock()
    cog._executor = MagicMock()
    yield cog
    # Close the transcript files the sinks opened.
    for _vc, sink in cog._sessions.values():
        sink._file.close()


def make_interaction(guild_id: int = 1) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    channel = interaction.user.voice.channel
    channel.name = "Tavern"
    channel.connect = AsyncMock(return_value=MagicMock())
    return interaction


async def run(cog, interaction, campaign=None) -> None:
    await transcribe_mod.TranscribeCog.transcribe.callback(cog, interaction, campaign)


async def test_named_campaign_creates_its_folders(cog, tmp_path: Path) -> None:
    interaction = make_interaction()
    await run(cog, interaction, "Testingcampaign")

    root = tmp_path / "campaigns" / "testingcampaign"
    assert (root / "transcripts").is_dir()
    assert (root / "notes").is_dir()
    _vc, sink = cog._sessions[1]
    assert Path(sink.output_path).parent == root / "transcripts"
    assert "testingcampaign" in interaction.followup.send.call_args.args[0]


async def test_no_campaign_uses_default(cog, tmp_path: Path) -> None:
    await run(cog, make_interaction())

    _vc, sink = cog._sessions[1]
    assert (
        Path(sink.output_path).parent
        == tmp_path / "campaigns" / "default" / "transcripts"
    )


@pytest.mark.parametrize("bad", ["../etc", "has space", "x" * 41, "-dash"])
async def test_invalid_name_is_refused_before_joining(cog, tmp_path: Path, bad) -> None:
    interaction = make_interaction()
    await run(cog, interaction, bad)

    interaction.user.voice.channel.connect.assert_not_called()
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True
    assert not (tmp_path / "campaigns").exists()
    assert cog._sessions == {}


async def test_autocomplete_suggests_existing_campaigns(cog, tmp_path: Path) -> None:
    for name in ("grenzlande", "rise_of_tiamat", "test_campaign"):
        (tmp_path / "campaigns" / name).mkdir(parents=True)
    complete = transcribe_mod.TranscribeCog.campaign_autocomplete

    all_ = await complete(cog, MagicMock(), "")
    assert [c.value for c in all_] == ["grenzlande", "rise_of_tiamat", "test_campaign"]

    # Prefix matches first, then substring matches; case-insensitive.
    hits = await complete(cog, MagicMock(), "T")
    assert [c.value for c in hits] == ["test_campaign", "rise_of_tiamat"]
