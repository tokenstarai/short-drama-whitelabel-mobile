#!/usr/bin/env python3
"""Write a no-secret preflight report for tenant store-submission evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_store_submission_evidence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = ROOT / "build" / "store-submission-evidence"
DEFAULT_SOURCE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.input.json"
DEFAULT_SOURCE_DIR = DEFAULT_EVIDENCE_DIR / "flavors"
DEFAULT_OUTPUT = DEFAULT_EVIDENCE_DIR / "store-submission-evidence-preflight.json"
DEFAULT_MARKDOWN = DEFAULT_EVIDENCE_DIR / "store-submission-evidence-preflight.md"
STRICT_IMPORT_COMMAND = "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict"


def quality_rules() -> list[str]:
    schema = import_store_submission_evidence.public_evidence_ref_schema()
    return [
        "Evidence refs can be plain public strings or structured objects with label, type, and at least one of value, url, or sha256.",
        str(schema["urlRequirement"]),
        str(schema["capturedAtRequirement"]),
        str(schema["secretBoundary"]),
    ]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def submission_items_with_source_issues(
    raw: Any,
    expected: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(raw, dict):
        return [], ["source-not-object"]
    submissions = raw.get("submissions")
    if not isinstance(submissions, list):
        if import_store_submission_evidence.non_empty_string(raw.get("flavor")):
            submissions = [raw]
        else:
            return [], ["submissions-missing"]

    items: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: set[str] = set()
    for item in submissions:
        if not isinstance(item, dict):
            issues.append("submission-not-object")
            continue
        flavor = str(item.get("flavor") or "")
        if flavor not in expected:
            issues.append(f"unknown-flavor:{flavor or 'missing'}")
        elif flavor in seen:
            issues.append(f"duplicate-flavor:{flavor}")
        seen.add(flavor)
        items.append(item)
    return items, issues


def load_source(
    source: Path,
    source_dir: Path,
    expected: dict[str, dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str], list[str], list[dict[str, str]]]:
    raw, errors, input_records = import_store_submission_evidence.load_per_flavor_sources(
        source_dir,
        expected,
    )
    if errors:
        return "per_flavor", [], [], errors, input_records
    if raw is not None:
        submissions, source_issues = submission_items_with_source_issues(raw, expected)
        return "per_flavor", submissions, source_issues, [], input_records

    if source.exists():
        raw = read_json(source)
        if raw is None:
            return "combined", [], [], [f"invalid-json:{rel(source)}"], []
        submissions, source_issues = submission_items_with_source_issues(raw, expected)
        return "combined", submissions, [*source_issues], [], [
            {
                "path": rel(source),
                "sha256": import_store_submission_evidence.sha256_file(source),
            },
        ]

    return "missing", [], [], [], input_records


def remediation_hints(
    flavor: str,
    blockers: list[str],
    expected_entry: dict[str, Any],
    target_path: str,
) -> list[str]:
    channel = str(expected_entry["primaryChannel"])
    allowed_statuses = ", ".join(import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel])
    starter_path = f"build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json"
    hints: list[str] = []
    for blocker in blockers:
        if blocker == "input-evidence-missing":
            hints.append(
                f"Copy {starter_path} to {target_path}, replace placeholders with tenant-owned public store status, then rerun preflight.",
            )
        elif blocker == "submissionStatus":
            hints.append(
                f"Set submissionStatus to one allowed {channel} value: {allowed_statuses}.",
            )
        elif blocker in import_store_submission_evidence.required_flags(channel):
            hints.append(
                f"Set {blocker}=true only after public tenant store or distribution evidence proves that checklist item.",
            )
        elif blocker == "publicEvidenceRefs":
            hints.append(
                "Add at least one public evidence ref such as TestFlight build number, Play internal track, signed package checksum, legal URL, support URL, or store product id.",
            )
        elif blocker == "publicEvidenceRefsUrl":
            hints.append(
                "Replace evidence ref URLs with public HTTPS URLs; localhost, file URLs, plain HTTP, loopback, private IP ranges, and .local hosts are rejected.",
            )
        elif blocker in {"evidenceCapturedAt", "publicEvidenceRefsCapturedAt"}:
            hints.append(
                "Use a timezone-aware ISO-8601 timestamp that is not in the future, for example 2026-06-14T00:00:00Z.",
            )
        elif blocker == "publicEvidenceRefsForbiddenMarkers":
            hints.append(
                "Remove signing or credential filenames from evidence refs; use public store or distribution metadata instead.",
            )
        elif blocker in {"applicationId", "appName"}:
            hints.append(
                f"Fill the tenant-owned {blocker} value for this app flavor before importing evidence.",
            )
        elif blocker in {"storeComplianceMode", "primaryChannel", "templateApplicationId", "templateAppName"}:
            hints.append(
                f"Keep {blocker} aligned with the generated handoff for {flavor}; regenerate the starter package if template metadata changed.",
            )
        else:
            hints.append(f"Review and correct blocker `{blocker}` in {target_path}.")
    return hints


def flavor_status(
    flavor: str,
    submission: dict[str, Any] | None,
    expected: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_entry = expected[flavor]
    target_path = f"build/store-submission-evidence/flavors/{flavor}.input.json"
    if submission is None:
        return {
            "flavor": flavor,
            "appName": expected_entry["appName"],
            "primaryChannel": expected_entry["primaryChannel"],
            "status": "blocked",
            "blockers": ["input-evidence-missing"],
            "readyForStrictImport": False,
            "strictImportBlockedBy": ["input-evidence-missing"],
            "remediationHints": remediation_hints(
                flavor,
                ["input-evidence-missing"],
                expected_entry,
                target_path,
            ),
            "tenantEvidenceInputPath": target_path,
            "nextAction": f"Fill public evidence for {flavor} at {target_path}.",
        }

    normalized, reasons = import_store_submission_evidence.validate_submission(
        submission,
        expected,
    )
    blockers = sorted(set(reasons))
    return {
        "flavor": flavor,
        "appName": expected_entry["appName"],
        "primaryChannel": expected_entry["primaryChannel"],
        "status": "passed" if not blockers else "blocked",
        "submissionStatus": normalized.get("submissionStatus"),
        "blockers": blockers,
        "readyForStrictImport": not blockers,
        "strictImportBlockedBy": blockers,
        "remediationHints": remediation_hints(
            flavor,
            blockers,
            expected_entry,
            target_path,
        ),
        "tenantEvidenceInputPath": target_path,
        "publicEvidenceRefsCount": len(normalized.get("publicEvidenceRefs", [])),
        "nextAction": (
            "Ready for strict import."
            if not blockers
            else f"Fix {', '.join(blockers)} for {flavor}, then rerun the preflight."
        ),
    }


def strict_import_readiness(
    flavor_rows: list[dict[str, Any]],
    source_issues: list[str],
    source_errors: list[str],
) -> dict[str, Any]:
    blocked_by = [
        {
            "flavor": row["flavor"],
            "inputPath": row["tenantEvidenceInputPath"],
            "blockers": row.get("blockers", []),
        }
        for row in flavor_rows
        if row.get("status") != "passed"
    ]
    source_blocked_by = [*source_issues, *source_errors]
    ready = not blocked_by and not source_blocked_by
    return {
        "ready": ready,
        "command": STRICT_IMPORT_COMMAND,
        "blockedBy": blocked_by,
        "sourceBlockedBy": source_blocked_by,
        "nextAction": (
            "Run strict import now."
            if ready
            else "Fix blocked flavor inputs and source issues, then rerun preflight before strict import."
        ),
    }


def markdown_from_report(report: dict[str, Any]) -> str:
    strict_import = report.get("strictImportReadiness", {})
    lines = [
        "# Store Submission Evidence Preflight",
        "",
        f"- Generated at: `{report['generatedAt']}`",
        f"- Preflight result: `{report['result']}`",
        f"- Source mode: `{report['sourceMode']}`",
        f"- Strict import ready: `{strict_import.get('ready', False)}`",
        f"- Strict import command: `{strict_import.get('command', STRICT_IMPORT_COMMAND)}`",
        "",
        "This preflight report checks public tenant store-submission metadata only. It does not submit apps, sign builds, read signing material, or store provider credentials.",
        "",
        "## Flavor Status",
        "",
        "| Flavor | Channel | Status | Blockers | Input path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in report["flavors"]:
        blockers = ", ".join(entry.get("blockers", [])) or "-"
        lines.append(
            f"| {entry['flavor']} | {entry['primaryChannel']} | {entry['status']} | {blockers} | `{entry['tenantEvidenceInputPath']}` |",
        )
    source_issues = [*report.get("sourceIssues", []), *report.get("sourceErrors", [])]
    if source_issues:
        lines.extend([
            "",
            "## Source Issues",
            "",
        ])
        lines.extend(
            f"- {issue}"
            for issue in source_issues
        )
    lines.extend([
        "",
        "## Remediation Hints",
        "",
    ])
    for entry in report["flavors"]:
        hints = entry.get("remediationHints", [])
        if not hints:
            continue
        lines.append(f"### {entry['flavor']}")
        lines.extend(f"- {hint}" for hint in hints)
        lines.append("")
    lines.extend([
        "",
        "## Evidence Quality Rules",
        "",
    ])
    lines.extend(
        f"- {rule}"
        for rule in report.get("qualityRules", [])
    )
    lines.extend([
        "",
        "## Commands",
        "",
        "```bash",
        "cd mobile",
        "./scripts/store_submission_evidence_preflight.py",
        "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
        "```",
        "",
        report["secretBoundary"],
        "",
    ])
    return "\n".join(lines)


def build_preflight_report(
    *,
    source: Path = DEFAULT_SOURCE,
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output: Path = DEFAULT_OUTPUT,
    markdown: Path = DEFAULT_MARKDOWN,
) -> dict[str, Any]:
    expected = import_store_submission_evidence.expected_entries()
    source_mode, submissions, source_issues, source_errors, source_inputs = load_source(source, source_dir, expected)
    by_flavor = {
        str(item.get("flavor")): item
        for item in submissions
        if isinstance(item, dict)
    }
    flavor_rows = [
        flavor_status(flavor, by_flavor.get(flavor), expected)
        for flavor in expected
    ]
    summary = {
        "passed": sum(1 for row in flavor_rows if row["status"] == "passed"),
        "blocked": sum(1 for row in flavor_rows if row["status"] == "blocked"),
        "failed": len(source_errors) + len(source_issues),
    }
    result = "failed" if source_errors or source_issues else "passed" if summary["blocked"] == 0 else "blocked"
    strict_import = strict_import_readiness(flavor_rows, source_issues, source_errors)
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": result,
        "sourceMode": source_mode,
        "sourcePath": rel(source),
        "sourceDir": rel(source_dir),
        "sourceInputPaths": source_inputs,
        "sourceIssues": source_issues,
        "sourceErrors": source_errors,
        "summary": summary,
        "flavors": flavor_rows,
        "qualityRules": quality_rules(),
        "strictImportReadiness": strict_import,
        "outputPath": rel(output),
        "markdownPath": rel(markdown),
        "strictImportCommand": STRICT_IMPORT_COMMAND,
        "secretBoundary": "Public store-submission preflight metadata only. Do not include signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or signing/credential file references.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(markdown_from_report(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_preflight_report(
        source=args.source.resolve(),
        source_dir=args.source_dir.resolve(),
        output=args.output.resolve(),
        markdown=args.markdown.resolve(),
    )
    print(f"Wrote store submission evidence preflight: {rel(args.output.resolve())}")
    print(f"Wrote store submission evidence preflight markdown: {rel(args.markdown.resolve())}")
    print(f"Result: {report['result']}")
    if report["result"] != "passed":
        blocked = [
            f"{entry['flavor']}({','.join(entry.get('blockers', []))})"
            for entry in report["flavors"]
            if entry["status"] != "passed"
        ]
        if blocked:
            print(f"Blocked flavors: {', '.join(blocked)}")
    return 1 if args.strict and report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
