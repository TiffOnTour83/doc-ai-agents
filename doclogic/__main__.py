"""Doc Logic CLI.

Two commands:

  run  — the full pipeline. Without --approve it stops at the gate and prints
         the proposal; with --approve "Name" it records the decision and
         produces the artifacts.
  diff — structural comparison of two document revisions.

Examples:
  python -m doclogic run manual.docx --profile aviation-manual
  python -m doclogic run manual.docx --profile aviation-manual --approve "T. Castro" --out out/
  python -m doclogic diff rev_a.docx rev_b.docx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import audit_report, classify, rtm_skeleton, structured_json
from .diff import diff as diff_extractions
from .diff import render as render_diff
from .extract import extract
from .gate import blocking_errors, record_decision
from .harmonize import harmonize
from .manifest import build_manifest
from .profiles import load_profile
from .suggest import RuleBasedSuggester


def _cmd_run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    extraction = extract(args.source)
    proposal = RuleBasedSuggester().propose(extraction, profile)

    print(f"source     : {proposal.source}  (sha256 {proposal.source_sha256[:16]}…)")
    print(f"profile    : {profile.name}")
    print(f"sections   : {proposal.section_count}   "
          f"numbering: {proposal.numbering_style}   "
          f"depth: {proposal.observed_depth} -> {proposal.proposed_depth}")
    print(f"proposal   : {proposal.digest()}")
    print(f"issues     : {len(proposal.issues)}")
    for issue in proposal.issues:
        print(f"  [{issue.severity.upper():7}] {issue.check}: {issue.detail}")

    if not args.approve:
        print("\nGate: stopped. Review the proposal above, then re-run with "
              '--approve "Your Name" to generate artifacts.')
        return 0

    errors = blocking_errors(proposal)
    if errors and not args.override:
        print(f"\nGate: {len(errors)} blocking error(s). Fix the document, or "
              "re-run with --override to approve anyway (the override is recorded).")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = args.notes or ("override: approved despite errors" if errors else "")
    decision = record_decision(proposal, True, args.approve, notes, out_dir)

    harmonized = harmonize(extraction, profile)
    taxonomy = classify(harmonized, profile)
    stem = Path(args.source).stem

    artifacts = {
        f"{stem}_structured.json": structured_json(harmonized, proposal.source),
        f"{stem}_rtm_skeleton.csv": rtm_skeleton(harmonized, proposal.source),
        f"{stem}_taxonomy.json": __import__("json").dumps(
            taxonomy, indent=2
        ).encode("utf-8"),
        f"{stem}_audit_report.txt": audit_report(proposal, harmonized, taxonomy),
    }
    for name, content in artifacts.items():
        (out_dir / name).write_bytes(content)
    (out_dir / f"{stem}_manifest.json").write_bytes(
        build_manifest(proposal, decision, profile.name, sorted(artifacts))
    )

    print(f"\nApproved by {decision.approver} at {decision.decided_at}")
    print(f"Harmonization changes: {len(harmonized.changes)}")
    print(f"Artifacts written to {out_dir}/:")
    for name in [*sorted(artifacts), f"{stem}_manifest.json"]:
        print(f"  {name}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    old = extract(args.old)
    new = extract(args.new)
    print(render_diff(diff_extractions(old, new), old.source, new.source))
    return 0


def _cmd_formats(args: argparse.Namespace) -> int:
    from .formats import audit_document, profile_document, render_report, standardize

    profiles = [profile_document(p) for p in args.documents]

    # Within-document consistency first.
    for profile in profiles:
        findings = audit_document(profile)
        print(f"{profile.source}: {len(findings)} internal format inconsistencies")
        for finding in findings:
            print(f"  [{finding.kind}] {finding.detail}")

    # Cross-document standardization when comparing multiple documents.
    if len(profiles) > 1:
        standard, findings = standardize(profiles)
        print()
        print(render_report(profiles, standard, findings))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doclogic", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the structuring pipeline")
    run.add_argument("source", help=".docx document to process")
    run.add_argument("--profile", default="default", help="standards profile name")
    run.add_argument("--out", default="out", help="artifact output directory")
    run.add_argument("--approve", default="", metavar="NAME",
                     help="approver name; without it the pipeline stops at the gate")
    run.add_argument("--notes", default="", help="notes recorded with the decision")
    run.add_argument("--override", action="store_true",
                     help="approve despite blocking errors (recorded)")
    run.set_defaults(func=_cmd_run)

    diff_cmd = sub.add_parser("diff", help="structural diff of two revisions")
    diff_cmd.add_argument("old")
    diff_cmd.add_argument("new")
    diff_cmd.set_defaults(func=_cmd_diff)

    formats_cmd = sub.add_parser(
        "formats",
        help="format consistency audit; multiple documents -> standardization report",
    )
    formats_cmd.add_argument("documents", nargs="+", help="one or more .docx files")
    formats_cmd.set_defaults(func=_cmd_formats)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
