"""Auditor agent — generate the artifacts that make structure *useful*.

Outputs:
* RTM skeleton (CSV) — one row per section, ready for requirements mapping
* Metadata taxonomy (JSON) — sections classified against the profile's
  taxonomy with transparent keyword evidence
* Audit report (text) — what was done, what changed, what still needs a human
"""

from __future__ import annotations

import csv
import io
import json
import re

from .harmonize import Harmonized
from .profiles import Profile
from .suggest import SchemaProposal

_TOKEN = re.compile(r"[a-z]{3,}")


def rtm_skeleton(harmonized: Harmonized, source: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["section_number", "section_title", "level", "source_document",
         "requirement_source", "requirement_summary", "mapping_rationale",
         "review_status"]
    )
    for section in harmonized.sections:
        writer.writerow(
            [section.number, section.title, section.level, source, "", "", "", "Pending"]
        )
    return buffer.getvalue().encode("utf-8")


def classify(harmonized: Harmonized, profile: Profile) -> dict:
    """Classify each section against the profile taxonomy — with evidence."""
    results = []
    for section in harmonized.sections:
        text = (section.title + " " + " ".join(section.body)).lower()
        tokens = set(_TOKEN.findall(text))
        best_category, best_hits = "Unclassified", []
        for category, keywords in profile.taxonomy.items():
            hits = [
                k for k in keywords
                if (" " in k and k in text) or (k in tokens)
            ]
            if len(hits) > len(best_hits):
                best_category, best_hits = category, hits
        results.append(
            {
                "section": section.number,
                "title": section.title,
                "category": best_category,
                "evidence": best_hits,
            }
        )
    return {"profile": profile.name, "classifications": results}


def audit_report(
    proposal: SchemaProposal, harmonized: Harmonized, taxonomy: dict
) -> bytes:
    lines = [
        f"Doc Logic audit report — {proposal.source}",
        "=" * 50,
        f"source sha256: {proposal.source_sha256}",
        f"suggester: {proposal.suggester}   proposal: {proposal.digest()}",
        f"sections: {proposal.section_count}   "
        f"depth: {proposal.observed_depth} -> {proposal.proposed_depth}",
        "",
        f"Issues found at suggestion stage ({len(proposal.issues)}):",
    ]
    for issue in proposal.issues:
        lines.append(f"  [{issue.severity.upper():7}] {issue.check}: {issue.detail}")
    lines += ["", f"Harmonization changes ({len(harmonized.changes)}):"]
    for change in harmonized.changes:
        lines.append(f"  [{change.action:8}] {change.section}: {change.detail}")
    unclassified = [
        c["title"] for c in taxonomy["classifications"]
        if c["category"] == "Unclassified"
    ]
    lines += [
        "",
        f"Taxonomy: {len(taxonomy['classifications']) - len(unclassified)} classified, "
        f"{len(unclassified)} unclassified (need a human)",
    ]
    for title in unclassified:
        lines.append(f"  - {title}")
    return "\n".join(lines).encode("utf-8")


def structured_json(harmonized: Harmonized, source: str) -> bytes:
    tree: list[dict] = []
    stack: list[tuple[int, list]] = [(0, tree)]
    for section in harmonized.sections:
        while stack and stack[-1][0] >= section.level:
            stack.pop()
        children: list[dict] = []
        node = {
            "number": section.number,
            "title": section.title,
            "level": section.level,
            "paragraphs": section.body,
            "children": children,
        }
        (stack[-1][1] if stack else tree).append(node)
        stack.append((section.level, children))
    return json.dumps(
        {"source": source, "sections": tree}, indent=2
    ).encode("utf-8")
