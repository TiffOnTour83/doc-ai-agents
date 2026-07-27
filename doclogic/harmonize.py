"""Harmonizer agent — normalize structure against an approved profile.

Runs only after the gate. Every transformation is recorded in a change log:
the output should never contain a change nobody can account for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .extract import Extraction, Section
from .profiles import Profile


@dataclass
class Change:
    action: str      # "promote" | "flatten" | "renumber"
    section: str
    detail: str


@dataclass
class Harmonized:
    sections: list[Section]
    changes: list[Change] = field(default_factory=list)


def harmonize(extraction: Extraction, profile: Profile) -> Harmonized:
    changes: list[Change] = []
    result: list[Section] = []

    previous_level = 0
    for section in extraction.sections:
        level = section.level

        # Close level jumps: a section can sit at most one level deeper
        # than its predecessor.
        if level > previous_level + 1:
            changes.append(
                Change(
                    "promote",
                    section.title,
                    f"level {level} -> {previous_level + 1} (closed level jump)",
                )
            )
            level = previous_level + 1

        # Enforce the profile's maximum depth.
        if level > profile.max_depth:
            changes.append(
                Change(
                    "flatten",
                    section.title,
                    f"level {level} -> {profile.max_depth} (profile max depth)",
                )
            )
            level = profile.max_depth

        result.append(
            Section(
                level=level,
                title=section.title,
                number=section.number,
                body=list(section.body),
                order=section.order,
            )
        )
        previous_level = level

    # Canonical renumbering: deterministic dotted numbers from the final tree.
    counters: list[int] = []
    for section in result:
        while len(counters) < section.level:
            counters.append(0)
        del counters[section.level:]
        counters[section.level - 1] += 1
        new_number = ".".join(str(c) for c in counters)
        if section.number != new_number:
            changes.append(
                Change(
                    "renumber",
                    section.title,
                    f"'{section.number or '(none)'}' -> '{new_number}'",
                )
            )
        section.number = new_number

    return Harmonized(sections=result, changes=changes)
