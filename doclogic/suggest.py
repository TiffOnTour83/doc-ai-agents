"""Schema Suggester agent — propose the document's schema for human review.

The suggester never decides; it proposes. Its output is a schema proposal the
human approves (or rejects) at the gate before harmonization runs.

Two implementations:

* RuleBasedSuggester — deterministic, transparent, works offline. Default.
* LLMSuggester — optional adapter showing where a model plugs in. It requires
  the `anthropic` package and an ANTHROPIC_API_KEY, and it is deliberately
  scoped to the *suggestion* stage only: even a smarter suggester still faces
  the same human gate. The line between machine proposal and human decision
  is architectural, not cosmetic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .extract import Extraction
from .profiles import Profile


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    check: str
    detail: str


@dataclass
class SchemaProposal:
    source: str
    source_sha256: str
    suggester: str
    numbering_style: str          # "explicit" | "styles-only" | "mixed"
    observed_depth: int
    proposed_depth: int
    section_count: int
    issues: list[Issue] = field(default_factory=list)

    def digest(self) -> str:
        """Stable hash of the proposal — what the approval record points at."""
        payload = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


class RuleBasedSuggester:
    name = "rule-based/v1"

    def propose(self, extraction: Extraction, profile: Profile) -> SchemaProposal:
        issues: list[Issue] = []

        if not extraction.sections:
            issues.append(
                Issue("error", "no-structure", "No headings detected at all.")
            )
            return SchemaProposal(
                source=extraction.source,
                source_sha256=extraction.sha256,
                suggester=self.name,
                numbering_style="none",
                observed_depth=0,
                proposed_depth=0,
                section_count=0,
                issues=issues,
            )

        numbered = sum(1 for s in extraction.sections if s.number)
        if numbered == len(extraction.sections):
            numbering = "explicit"
        elif numbered == 0:
            numbering = "styles-only"
        else:
            numbering = "mixed"
            issues.append(
                Issue(
                    "warning",
                    "mixed-numbering",
                    f"{numbered} of {len(extraction.sections)} sections carry "
                    "manual numbers; the rest rely on styles alone.",
                )
            )

        if profile.require_numbering and numbering != "explicit":
            issues.append(
                Issue(
                    "error",
                    "numbering-required",
                    f"Profile '{profile.name}' requires explicit numbering.",
                )
            )

        observed_depth = max(s.level for s in extraction.sections)
        if observed_depth > profile.max_depth:
            issues.append(
                Issue(
                    "warning",
                    "too-deep",
                    f"Observed depth {observed_depth} exceeds profile max "
                    f"{profile.max_depth}; harmonizer will flatten.",
                )
            )

        previous = 0
        for section in extraction.sections:
            if section.level > previous + 1:
                issues.append(
                    Issue(
                        "error",
                        "level-jump",
                        f"'{section.title}' jumps level {previous} -> {section.level}.",
                    )
                )
            previous = section.level

        if profile.forbid_duplicate_titles:
            seen: dict[str, int] = {}
            for section in extraction.sections:
                key = section.title.lower()
                seen[key] = seen.get(key, 0) + 1
            for title, count in seen.items():
                if count > 1:
                    issues.append(
                        Issue(
                            "error",
                            "duplicate-title",
                            f"'{title}' appears {count} times.",
                        )
                    )

        if extraction.orphan_paragraphs:
            issues.append(
                Issue(
                    "warning",
                    "orphan-text",
                    f"{len(extraction.orphan_paragraphs)} paragraph(s) precede "
                    "the first heading.",
                )
            )

        return SchemaProposal(
            source=extraction.source,
            source_sha256=extraction.sha256,
            suggester=self.name,
            numbering_style=numbering,
            observed_depth=observed_depth,
            proposed_depth=min(observed_depth, profile.max_depth),
            section_count=len(extraction.sections),
            issues=issues,
        )


class LLMSuggester:
    """Optional Claude-backed suggester. Same contract, same human gate.

    Not used by default. Requires: `pip install anthropic` and an
    ANTHROPIC_API_KEY in the environment. Kept intentionally small — the
    point is the extension seam, not a framework.
    """

    name = "llm/claude"

    def propose(self, extraction: Extraction, profile: Profile) -> SchemaProposal:
        try:
            import os

            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LLMSuggester requires the 'anthropic' package: pip install anthropic"
            ) from exc
        if not os.environ.get("ANTHROPIC_API_KEY"):  # pragma: no cover
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        # Start from the deterministic baseline, then let the model refine
        # issue detection. Baseline-first means an API failure can never make
        # the pipeline worse than rule-based.
        baseline = RuleBasedSuggester().propose(extraction, profile)

        outline = "\n".join(
            f"{'  ' * (s.level - 1)}{s.number or '-'} {s.title} "
            f"({len(s.body)} paragraphs)"
            for s in extraction.sections[:200]
        )
        client = anthropic.Anthropic()  # pragma: no cover - network
        response = client.messages.create(  # pragma: no cover - network
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Review this document outline for structural problems "
                        "(missing intermediate levels, inconsistent numbering, "
                        "placeholder sections). Reply with a JSON list of "
                        '{"severity","check","detail"} objects only.\n\n'
                        + outline
                    ),
                }
            ],
        )
        try:  # pragma: no cover - network
            extra = json.loads(response.content[0].text)
            for item in extra:
                baseline.issues.append(
                    Issue(
                        severity=item.get("severity", "warning"),
                        check="llm/" + item.get("check", "observation"),
                        detail=str(item.get("detail", "")),
                    )
                )
            baseline.suggester = self.name
        except (ValueError, KeyError, IndexError):
            pass  # keep the deterministic baseline untouched
        return baseline
