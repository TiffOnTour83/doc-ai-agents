"""Extractor agent — pull machine-readable structure out of a .docx.

One job: turn a Word document into sections with levels, titles, and body
text. Detects structure from Word heading styles first, then falls back to
manual numbering patterns ("3.2.1 Title"). The source file is never modified.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import docx


@dataclass
class Section:
    level: int
    title: str
    number: str = ""          # manual numbering if present, e.g. "3.2.1"
    body: list[str] = field(default_factory=list)
    order: int = 0


@dataclass
class Extraction:
    source: str
    sha256: str
    sections: list[Section]
    orphan_paragraphs: list[str]
    style_headings: int       # headings found via Word styles
    pattern_headings: int     # headings found via numbering patterns


_HEADING_STYLE = re.compile(r"heading\s*(\d)", re.IGNORECASE)
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$")


def extract(path: str | Path) -> Extraction:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    document = docx.Document(str(path))

    sections: list[Section] = []
    orphans: list[str] = []
    style_count = pattern_count = 0

    for order, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = (paragraph.style.name or "") if paragraph.style else ""
        style_match = _HEADING_STYLE.search(style_name)
        if style_match:
            style_count += 1
            number_match = _NUMBERED.match(text)
            sections.append(
                Section(
                    level=int(style_match.group(1)),
                    title=number_match.group(2) if number_match else text,
                    number=number_match.group(1) if number_match else "",
                    order=order,
                )
            )
            continue

        number_match = _NUMBERED.match(text)
        if number_match and len(text) <= 120:
            pattern_count += 1
            number = number_match.group(1)
            sections.append(
                Section(
                    level=min(number.count(".") + 1, 6),
                    title=number_match.group(2),
                    number=number,
                    order=order,
                )
            )
            continue

        if sections:
            sections[-1].body.append(text)
        else:
            orphans.append(text)

    return Extraction(
        source=path.name,
        sha256=digest,
        sections=sections,
        orphan_paragraphs=orphans,
        style_headings=style_count,
        pattern_headings=pattern_count,
    )
