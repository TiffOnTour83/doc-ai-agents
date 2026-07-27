"""Revision diff — the drift audit, automated.

Compare two extractions of the same document (old revision vs. new) and
report what changed structurally: sections added, removed, renamed, moved,
or renumbered. Answers the question that eats compliance teams alive:
"what actually changed between Rev A and Rev B?"
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from .extract import Extraction, Section


@dataclass
class DiffEntry:
    kind: str      # "added" | "removed" | "renamed" | "moved" | "renumbered"
    detail: str


def _similarity(a: str, b: str) -> float:
    """Blend of character similarity and word overlap.

    Renames usually keep some words and swap others ("Submission Process" ->
    "Submission Workflow"), which pure character ratios underrate.
    """
    char_ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    words_a, words_b = set(a.lower().split()), set(b.lower().split())
    union = words_a | words_b
    word_ratio = len(words_a & words_b) / len(union) if union else 0.0
    return max(char_ratio, (char_ratio + word_ratio) / 2)


def diff(old: Extraction, new: Extraction) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    old_sections = list(old.sections)
    new_sections = list(new.sections)

    matched: list[tuple[Section, Section]] = []
    unmatched_new = list(new_sections)

    # Pass 1: exact title matches (first unmatched occurrence wins).
    for old_section in list(old_sections):
        for new_section in unmatched_new:
            if old_section.title.lower() == new_section.title.lower():
                matched.append((old_section, new_section))
                old_sections.remove(old_section)
                unmatched_new.remove(new_section)
                break

    # Pass 2: fuzzy matches -> renames.
    for old_section in list(old_sections):
        best, best_score = None, 0.0
        for new_section in unmatched_new:
            score = _similarity(old_section.title, new_section.title)
            if score > best_score:
                best, best_score = new_section, score
        if best is not None and best_score >= 0.55:
            entries.append(
                DiffEntry(
                    "renamed",
                    f"'{old_section.title}' -> '{best.title}' "
                    f"(similarity {best_score:.2f})",
                )
            )
            matched.append((old_section, best))
            old_sections.remove(old_section)
            unmatched_new.remove(best)

    for old_section in old_sections:
        entries.append(DiffEntry("removed", f"'{old_section.title}'"))
    for new_section in unmatched_new:
        entries.append(DiffEntry("added", f"'{new_section.title}'"))

    # Matched pairs: position and numbering drift.
    old_order = {s.title.lower(): i for i, s in enumerate(old.sections)}
    new_order = {s.title.lower(): i for i, s in enumerate(new.sections)}
    for old_section, new_section in matched:
        if old_section.number and new_section.number and (
            old_section.number != new_section.number
        ):
            entries.append(
                DiffEntry(
                    "renumbered",
                    f"'{new_section.title}': {old_section.number} -> {new_section.number}",
                )
            )
        old_neighbors = old_order.get(old_section.title.lower(), 0)
        new_neighbors = new_order.get(new_section.title.lower(), 0)
        if abs(old_neighbors - new_neighbors) > 1 and (
            old_section.number == new_section.number or not old_section.number
        ):
            entries.append(
                DiffEntry(
                    "moved",
                    f"'{new_section.title}': position {old_neighbors} -> {new_neighbors}",
                )
            )
    return entries


def render(entries: list[DiffEntry], old_name: str, new_name: str) -> str:
    lines = [f"Structural diff: {old_name} -> {new_name}", "=" * 50]
    if not entries:
        lines.append("No structural changes detected.")
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.kind] = counts.get(entry.kind, 0) + 1
        lines.append(f"[{entry.kind.upper():10}] {entry.detail}")
    if entries:
        lines.append("")
        lines.append(
            "Summary: "
            + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        )
    return "\n".join(lines)
