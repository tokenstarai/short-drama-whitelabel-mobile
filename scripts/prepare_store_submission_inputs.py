#!/usr/bin/env python3
"""Prepare tenant-fillable per-flavor store-submission evidence inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import export_store_submission_starter
import import_store_submission_evidence
import store_submission_evidence_preflight


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-submission-evidence"
WORKSPACE_MANIFEST = "store-submission-input-workspace.json"
WORKSPACE_MARKDOWN = "store-submission-input-workspace.md"
PREFLIGHT_REPORT = "store-submission-evidence-preflight.json"
PREFLIGHT_MARKDOWN = "store-submission-evidence-preflight.md"
STRICT_IMPORT_COMMAND = "cd mobile && python3 scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict"
PREFLIGHT_COMMAND = "cd mobile && python3 scripts/store_submission_evidence_preflight.py"
PREPARE_COMMAND = "cd mobile && python3 scripts/prepare_store_submission_inputs.py"

SECRET_BOUNDARY = (
    "Public evidence workspace only. Keep signing files, provider credentials, OAuth credentials, "
    "payment credentials, webhook credentials, Cloudflare credentials, bank credentials, and wallet keys "
    "outside Git and outside mobile clients."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted(
        marker
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS
        if marker in text
    )


def starter_input_path(root: Path, flavor: str) -> Path:
    return root / "build" / "store-submission-starter" / flavor / "store-submission-evidence.input.example.json"


def target_input_path(output_dir: Path, flavor: str) -> Path:
    return output_dir / "flavors" / f"{flavor}.input.json"


def ensure_starter(root: Path) -> None:
    starter_root = root / "build" / "store-submission-starter"
    if all(starter_input_path(root, flavor).exists() for flavor in import_store_submission_evidence.FLAVOR_DEFAULTS):
        return
    export_store_submission_starter.export_starter(root, starter_root)


def single_flavor_input(source: Path, flavor: str) -> dict[str, Any]:
    raw = json.loads(source.read_text(encoding="utf-8"))
    submissions = raw.get("submissions")
    if not isinstance(submissions, list) or len(submissions) != 1 or not isinstance(submissions[0], dict):
        raise ValueError(f"{source} must contain exactly one submission object.")
    submission = dict(submissions[0])
    if submission.get("flavor") != flavor:
        raise ValueError(f"{source} flavor does not match {flavor}.")
    return {
        "schemaVersion": raw.get("schemaVersion", 1),
        "generatedAt": utc_now(),
        "source": "tenant_store_submission_public_evidence_input_single_flavor",
        "instructions": raw.get("instructions", []),
        "publicEvidenceRefSchema": raw.get("publicEvidenceRefSchema", {}),
        "secretBoundary": raw.get("secretBoundary", SECRET_BOUNDARY),
        **submission,
    }


def generated_placeholder_input(path: Path, flavor: str) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw.get("submissions"), list):
        return False
    items = import_store_submission_evidence.submission_items(raw)
    if len(items) != 1:
        return False
    item = items[0]
    return (
        item.get("flavor") == flavor
        and item.get("tenantMustReplacePlaceholders") is True
        and item.get("submissionStatus") == "pending_tenant_action"
        and item.get("publicEvidenceRefs") == []
        and not item.get("evidenceCapturedAt")
    )


def write_single_input(source: Path, target: Path, flavor: str) -> None:
    target.write_text(
        json.dumps(single_flavor_input(source, flavor), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def copy_input(root: Path, output_dir: Path, flavor: str, *, force: bool) -> dict[str, Any]:
    source = starter_input_path(root, flavor)
    target = target_input_path(output_dir, flavor)
    target.parent.mkdir(parents=True, exist_ok=True)
    status = "exists"
    if not target.exists():
        write_single_input(source, target, flavor)
        status = "created"
    elif force:
        write_single_input(source, target, flavor)
        status = "overwritten"
    elif generated_placeholder_input(target, flavor):
        write_single_input(source, target, flavor)
        status = "migrated"
    return {
        "flavor": flavor,
        "status": status,
        "sourcePath": rel(root, source),
        "targetPath": rel(root, target),
        "sha256": sha256_file(target),
        "inputShape": "single_flavor_submission",
        "tenantMustReplacePlaceholders": True,
    }


def refresh_preflight(output_dir: Path) -> dict[str, Any]:
    return store_submission_evidence_preflight.build_preflight_report(
        source=output_dir / "store-submission-evidence.input.json",
        source_dir=output_dir / "flavors",
        output=output_dir / PREFLIGHT_REPORT,
        markdown=output_dir / PREFLIGHT_MARKDOWN,
    )


def attach_preflight_status(inputs: list[dict[str, Any]], preflight: dict[str, Any]) -> list[dict[str, Any]]:
    by_flavor = {
        str(row.get("flavor")): row
        for row in preflight.get("flavors", [])
        if isinstance(row, dict)
    }
    enriched: list[dict[str, Any]] = []
    for row in inputs:
        status = by_flavor.get(row["flavor"], {})
        enriched.append({
            **row,
            "preflightStatus": status.get("status", "blocked"),
            "preflightBlockers": list(status.get("blockers", ["input-evidence-missing"])),
            "readyForStrictImport": bool(status.get("readyForStrictImport", False)),
            "preflightNextAction": status.get(
                "nextAction",
                f"Fill public evidence for {row['flavor']} at {row['targetPath']}.",
            ),
            "preflightRemediationHints": list(status.get("remediationHints", [])),
        })
    return enriched


def preflight_summary(root: Path, output_dir: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    strict_import = preflight.get("strictImportReadiness", {})
    blocked_by = [
        {
            "flavor": row.get("flavor"),
            "inputPath": row.get("tenantEvidenceInputPath"),
            "blockers": list(row.get("blockers", [])),
        }
        for row in preflight.get("flavors", [])
        if isinstance(row, dict) and row.get("status") != "passed"
    ]
    return {
        "result": preflight.get("result", "blocked"),
        "summary": preflight.get("summary", {"passed": 0, "blocked": 0, "failed": 0}),
        "strictImportReady": bool(strict_import.get("ready", False)),
        "strictImportCommand": strict_import.get("command", STRICT_IMPORT_COMMAND),
        "preflightReportPath": rel(root, output_dir / PREFLIGHT_REPORT),
        "preflightMarkdownPath": rel(root, output_dir / PREFLIGHT_MARKDOWN),
        "blockedInputPaths": [
            row["inputPath"]
            for row in blocked_by
            if isinstance(row.get("inputPath"), str)
        ],
        "blockedBy": blocked_by,
        "nextAction": strict_import.get(
            "nextAction",
            "Fix blocked flavor inputs and source issues, then rerun preflight before strict import.",
        ),
    }


def markdown_from_manifest(manifest: dict[str, Any]) -> str:
    preflight = manifest.get("preflightSummary", {})
    lines = [
        "# Store Submission Input Workspace",
        "",
        f"- Generated at: `{manifest['generatedAt']}`",
        f"- Prepare command: `{manifest['prepareCommand']}`",
        f"- Preflight command: `{manifest['preflightCommand']}`",
        f"- Strict import command: `{manifest['strictImportCommand']}`",
        f"- Preflight result: `{preflight.get('result', 'blocked')}`",
        f"- Strict import ready: `{preflight.get('strictImportReady', False)}`",
        f"- Preflight report: `{preflight.get('preflightReportPath', '')}`",
        "",
        "This workspace converts no-secret starter examples into single-flavor input files. It does not overwrite existing tenant-filled inputs unless `--force` is used.",
        "Generated placeholder files may be migrated from the older `submissions[0]` wrapper into the flatter single-flavor shape.",
        "",
        "| Flavor | Status | Shape | Input path | Preflight | Blockers |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in manifest["inputs"]:
        blockers = ", ".join(row.get("preflightBlockers", [])) or "-"
        lines.append(
            f"| {row['flavor']} | {row['status']} | {row.get('inputShape', 'single_flavor_submission')} | `{row['targetPath']}` | {row.get('preflightStatus', 'blocked')} | {blockers} |",
        )
    lines.extend([
        "",
        "Next steps:",
        "",
        "1. Replace `pending_tenant_action`, false checklist flags, empty evidence refs, and empty timestamps with tenant-owned public store or distribution evidence.",
        "2. Run the preflight command.",
        "3. Run the strict import command only after preflight reports ready.",
        "",
        manifest["secretBoundary"],
        "",
    ])
    return "\n".join(lines)


def prepare_workspace(root: Path = ROOT, output_dir: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    output = output_dir or root / "build" / "store-submission-evidence"
    ensure_starter(root)
    inputs = [
        copy_input(root, output, flavor, force=force)
        for flavor in import_store_submission_evidence.FLAVOR_DEFAULTS
    ]
    preflight = refresh_preflight(output)
    inputs = attach_preflight_status(inputs, preflight)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "packageType": "store_submission_input_workspace",
        "generatedAt": utc_now(),
        "source": "store_submission_starter_examples",
        "force": force,
        "inputDirectory": rel(root, output / "flavors"),
        "prepareCommand": PREPARE_COMMAND,
        "preflightCommand": PREFLIGHT_COMMAND,
        "strictImportCommand": STRICT_IMPORT_COMMAND,
        "nextCommands": [
            PREPARE_COMMAND,
            PREFLIGHT_COMMAND,
            STRICT_IMPORT_COMMAND,
            "cd mobile && python3 scripts/mobile_completion_closure.py --skip-ios-ci-download",
            "npm run infra:mobile-app-completion-audit",
        ],
        "blockingPlaceholders": ["pending_tenant_action"],
        "preflightSummary": preflight_summary(root, output, preflight),
        "inputs": inputs,
        "secretBoundary": SECRET_BOUNDARY,
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / WORKSPACE_MANIFEST
    markdown_path = output / WORKSPACE_MARKDOWN
    manifest["manifestPath"] = rel(root, manifest_path)
    manifest["markdownPath"] = rel(root, markdown_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_from_manifest(manifest), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else root / "build" / "store-submission-evidence"
    manifest = prepare_workspace(root, output_dir, force=args.force)
    print(f"Wrote store submission input workspace: {manifest['manifestPath']}")
    print(f"Wrote store submission input workspace guide: {manifest['markdownPath']}")
    print(f"Inputs: {len(manifest['inputs'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
    return 1 if manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
