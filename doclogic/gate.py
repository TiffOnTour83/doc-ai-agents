"""The approval gate — human decisions as recorded artifacts.

An approval is not a keypress; it is a record: who approved which proposal
(by digest), when, and with what notes. Decisions append to a JSONL log so
the history of judgment survives alongside the artifacts it authorized.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .suggest import SchemaProposal


@dataclass
class Decision:
    proposal_digest: str
    source: str
    approved: bool
    approver: str
    notes: str
    decided_at: str


def record_decision(
    proposal: SchemaProposal,
    approved: bool,
    approver: str,
    notes: str,
    out_dir: str | Path,
) -> Decision:
    decision = Decision(
        proposal_digest=proposal.digest(),
        source=proposal.source,
        approved=approved,
        approver=approver,
        notes=notes,
        decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    log = Path(out_dir) / "decisions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(decision)) + "\n")
    return decision


def blocking_errors(proposal: SchemaProposal) -> list[str]:
    """Errors a human must consciously override to proceed."""
    return [
        f"{i.check}: {i.detail}" for i in proposal.issues if i.severity == "error"
    ]
