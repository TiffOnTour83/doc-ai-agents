"""Provenance manifest — every artifact can answer "where did you come from?"

The manifest ties together the source hash, pipeline version, profile,
proposal digest, and approval record for one run. It ships alongside the
artifacts it describes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import PIPELINE, __version__
from .gate import Decision
from .suggest import SchemaProposal


def build_manifest(
    proposal: SchemaProposal,
    decision: Decision,
    profile_name: str,
    artifacts: list[str],
) -> bytes:
    manifest = {
        "tool": f"doclogic/{__version__}",
        "pipeline": PIPELINE,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"file": proposal.source, "sha256": proposal.source_sha256},
        "profile": profile_name,
        "suggester": proposal.suggester,
        "proposal_digest": proposal.digest(),
        "approval": {
            "approver": decision.approver,
            "approved": decision.approved,
            "decided_at": decision.decided_at,
            "notes": decision.notes,
        },
        "artifacts": artifacts,
    }
    return json.dumps(manifest, indent=2).encode("utf-8")
