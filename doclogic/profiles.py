"""Standards profiles — what "good structure" means, as configuration.

A profile defines the quality bar precisely enough that the pipeline can
enforce it without a human in the room. Profiles are plain JSON so teams can
version them, review them, and disagree about them in pull requests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


@dataclass
class Profile:
    name: str
    max_depth: int = 4
    require_numbering: bool = False
    min_body_paragraphs: int = 0     # sections with fewer are flagged
    forbid_duplicate_titles: bool = True
    taxonomy: dict[str, list[str]] = field(default_factory=dict)
    # taxonomy: category -> keywords used by the Auditor to classify sections


def load_profile(name: str) -> Profile:
    path = PROFILE_DIR / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
        raise FileNotFoundError(
            f"profile '{name}' not found; available: {available}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return Profile(
        name=data.get("name", name),
        max_depth=int(data.get("max_depth", 4)),
        require_numbering=bool(data.get("require_numbering", False)),
        min_body_paragraphs=int(data.get("min_body_paragraphs", 0)),
        forbid_duplicate_titles=bool(data.get("forbid_duplicate_titles", True)),
        taxonomy=data.get("taxonomy", {}),
    )
