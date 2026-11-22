"""Campaign folders under DATA_DIR.

Each campaign is one folder that holds everything about it:

    <DATA_DIR>/campaigns/<name>/
        campaign.txt     written by the group, optional (SCRIB-05)
        campaign.toml    per-campaign settings such as google_doc_id, optional
        transcripts/     created by the bot
        notes/           created by the bot

The campaign name usually comes from Discord and becomes a folder name, so it
is checked against a strict pattern before any path is built from it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Lowercase letters, digits, "-" and "_", starting with a letter or digit.
# No dots or slashes, so a name can never leave DATA_DIR/campaigns.
CAMPAIGN_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


def normalize_campaign_name(name: str) -> str:
    """Return the canonical form of a campaign name, or raise ValueError.

    Names are case-insensitive ("Grenzfeste" and "grenzfeste" are the same
    campaign) and surrounding spaces are ignored.
    """
    normalized = name.strip().lower()
    if not CAMPAIGN_NAME_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid campaign name {name!r}: use 1-40 lowercase letters, digits, "
            "'-' or '_', starting with a letter or digit"
        )
    return normalized


@dataclass(frozen=True)
class CampaignPaths:
    name: str
    root: str

    @property
    def campaign_file(self) -> str:
        return os.path.join(self.root, "campaign.txt")

    @property
    def settings_file(self) -> str:
        return os.path.join(self.root, "campaign.toml")

    @property
    def transcripts_dir(self) -> str:
        return os.path.join(self.root, "transcripts")

    @property
    def notes_dir(self) -> str:
        return os.path.join(self.root, "notes")


def campaign_paths(data_dir: str, name: str) -> CampaignPaths:
    """Paths for a campaign. Validates the name; does not touch the disk."""
    name = normalize_campaign_name(name)
    return CampaignPaths(name=name, root=os.path.join(data_dir, "campaigns", name))


def ensure_campaign_dirs(paths: CampaignPaths) -> None:
    """Create the campaign folder and its transcripts/ and notes/ subfolders.

    campaign.txt and campaign.toml are never created: they belong to the group.
    """
    os.makedirs(paths.transcripts_dir, exist_ok=True)
    os.makedirs(paths.notes_dir, exist_ok=True)
