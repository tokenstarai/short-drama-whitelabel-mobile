#!/usr/bin/env python3
"""Export no-secret tenant starter inputs for store-submission evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_store_submission_evidence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-submission-starter"
PACKAGE_NAME = "mobile-store-submission-starter"
PACKAGE_FILE = "mobile-store-submission-starter.zip"

SECRET_BOUNDARY = (
    "Public status references only; do not paste signing files, provider credentials, "
    "API tokens, webhook secrets, service-account JSON, bank credentials, or private keys."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted(
        marker
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS
        if marker in text
    )


def safe_channel_status(channel: str) -> str:
    # Keep starter inputs non-passing until the tenant replaces placeholders.
    return "pending_tenant_action"


def submission_input(entry: dict[str, Any]) -> dict[str, Any]:
    channel = str(entry["primaryChannel"])
    flags = {
        flag: False
        for flag in import_store_submission_evidence.required_flags(channel)
    }
    return {
        "flavor": entry["flavor"],
        "templateApplicationId": entry["applicationId"],
        "templateAppName": entry["appName"],
        "applicationId": entry["applicationId"],
        "appName": entry["appName"],
        "storeComplianceMode": entry["storeComplianceMode"],
        "primaryChannel": channel,
        "submissionStatus": safe_channel_status(channel),
        **flags,
        "tenantMustReplacePlaceholders": True,
        "allowedSubmissionStatuses": import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel],
        "publicEvidenceRefs": [],
        "evidenceCapturedAt": None,
        "tenantNotes": [
            "Replace pending_tenant_action with one allowed status only after tenant-owned signing and store setup are complete.",
            "Set checklist flags to true only when the tenant can prove that item from public store or direct-distribution metadata.",
            "Use public evidence refs such as TestFlight build number, Play internal track, signed package checksum, legal URL, or public distribution URL.",
        ],
    }


def input_document(submissions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "source": "tenant_store_submission_public_evidence_input",
        "instructions": [
            "This starter is intentionally blocked until tenant-owned public evidence replaces placeholders.",
            "Do not add signing files, OAuth credentials, payment credentials, webhook secrets, service-account files, bank credentials, or wallet keys.",
            "After replacing placeholders, save as build/store-submission-evidence/store-submission-evidence.input.json and run scripts/import_store_submission_evidence.py --strict.",
        ],
        "submissions": submissions,
        "secretBoundary": SECRET_BOUNDARY,
    }


def checklist_markdown(entry: dict[str, Any]) -> str:
    channel = str(entry["primaryChannel"])
    statuses = import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel]
    flags = import_store_submission_evidence.required_flags(channel)
    examples = import_store_submission_evidence.evidence_examples(channel)
    lines = [
        f"# {entry['flavor']} Store Submission Starter",
        "",
        f"- App name: `{entry['appName']}`",
        f"- Application id: `{entry['applicationId']}`",
        f"- Compliance mode: `{entry['storeComplianceMode']}`",
        f"- Primary channel: `{channel}`",
        "",
        "## Allowed Statuses",
        "",
    ]
    lines.extend(f"- `{status}`" for status in statuses)
    lines.extend(["", "## Required Flags", ""])
    lines.extend(f"- `{flag}`" for flag in flags)
    lines.extend(["", "## Public Evidence Examples", ""])
    lines.extend(f"- {example}" for example in examples)
    lines.extend([
        "",
        "## Import Command",
        "",
        "```bash",
        "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
        "```",
        "",
        SECRET_BOUNDARY,
        "",
    ])
    return "\n".join(lines)


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name not in {PACKAGE_FILE, "store-submission-starter-manifest.json"}
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def export_starter(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    output = output_dir or root / "build" / "store-submission-starter"
    if output.exists():
        for path in sorted(output.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output.mkdir(parents=True, exist_ok=True)

    expected = import_store_submission_evidence.expected_entries()
    flavor_records: list[dict[str, Any]] = []
    all_submissions: list[dict[str, Any]] = []
    for flavor, entry in expected.items():
        submission = submission_input(entry)
        all_submissions.append(submission)
        flavor_dir = output / flavor
        flavor_dir.mkdir(parents=True, exist_ok=True)
        input_path = flavor_dir / "store-submission-evidence.input.example.json"
        checklist_path = flavor_dir / "operator-checklist.md"
        input_path.write_text(
            json.dumps(input_document([submission]), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        checklist_path.write_text(checklist_markdown(entry), encoding="utf-8")
        channel = str(entry["primaryChannel"])
        flavor_records.append({
            "flavor": flavor,
            "appName": entry["appName"],
            "applicationId": entry["applicationId"],
            "storeComplianceMode": entry["storeComplianceMode"],
            "primaryChannel": channel,
            "allowedStatuses": import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel],
            "requiredFlags": import_store_submission_evidence.required_flags(channel),
            "inputExamplePath": rel(output, input_path),
            "operatorChecklistPath": rel(output, checklist_path),
            "inputExampleSha256": sha256_file(input_path),
            "operatorChecklistSha256": sha256_file(checklist_path),
        })

    all_dir = output / "all-flavors"
    all_dir.mkdir(parents=True, exist_ok=True)
    all_input_path = all_dir / "store-submission-evidence.input.example.json"
    all_input_path.write_text(
        json.dumps(input_document(all_submissions), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    zip_path = output / PACKAGE_FILE
    write_zip(output, zip_path)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_store_submission_starter",
        "tenantActionSummary": "Copy each flavor input example to build/store-submission-evidence/store-submission-evidence.input.json after tenant-owned signing and store setup.",
        "packagePath": rel(root, zip_path),
        "packageSha256": sha256_file(zip_path),
        "allFlavorsInputExamplePath": rel(output, all_input_path),
        "allFlavorsInputExampleSha256": sha256_file(all_input_path),
        "flavors": flavor_records,
        "importCommand": "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
        "secretBoundary": SECRET_BOUNDARY,
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    manifest_path = output / "store-submission-starter-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else root / "build" / "store-submission-starter"
    manifest = export_starter(root, output_dir)
    print(f"Wrote store submission starter manifest: {rel(root, output_dir / 'store-submission-starter-manifest.json')}")
    print(f"Wrote store submission starter package: {manifest['packagePath']}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
    return 1 if manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
