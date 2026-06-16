#!/usr/bin/env python3
"""Export an actionable no-secret plan for external mobile completion blockers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "completion-unblocker"
FIX_QUEUE_CSV = "mobile-store-evidence-fix-queue.csv"
FIX_QUEUE_MARKDOWN = "mobile-store-evidence-fix-queue.md"
FIX_QUEUE_COLUMNS = [
    "flavor",
    "inputPath",
    "field",
    "tenantAction",
    "acceptedPublicEvidence",
    "forbiddenEvidence",
]

FORBIDDEN_MARKERS = [
    "tenant_app_secret",
    "cloudflare_api_token",
    "cloudflare-api-token:",
    "bearer ey",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "sk_live_",
    "sk_test_",
    "whsec_",
    "-----begin private key-----",
]

FIELD_REMEDIATION_CATALOG: dict[str, dict[str, list[str] | str]] = {
    "tenantDeveloperAccountReady": {
        "tenantAction": "Confirm the tenant-owned Apple Developer, Google Play, or direct distribution account is active for this flavor.",
        "acceptedPublicEvidence": ["Developer account team name, public app owner name, or console record status without credential values."],
        "forbiddenEvidence": ["Login cookies, access tokens, password screenshots, recovery codes, or account credential values."],
    },
    "signedBuildProduced": {
        "tenantAction": "Produce a tenant-signed build artifact outside the repository and record only public build metadata.",
        "acceptedPublicEvidence": ["Build number, version, package id, artifact filename, CI run URL, or store upload status page."],
        "forbiddenEvidence": ["Signing files, provisioning profiles, keystores, export passwords, or certificate material."],
    },
    "signingMaterialOutsideRepository": {
        "tenantAction": "Confirm signing material is stored in the tenant-controlled CI vault or local signing environment, not in Git.",
        "acceptedPublicEvidence": ["Public statement of external signing storage and redacted CI variable names."],
        "forbiddenEvidence": ["Keystore files, certificate exports, provisioning profiles, passwords, or raw signing configuration."],
    },
    "storeRecordConfigured": {
        "tenantAction": "Create the store or distribution record for the flavor and copy public metadata into the input file.",
        "acceptedPublicEvidence": ["App name, bundle id/package name, store console record id, status label, and public listing URL when available."],
        "forbiddenEvidence": ["Console session exports, internal-only screenshots with credential values, or account access data."],
    },
    "appStoreConnectRecordConfigured": {
        "tenantAction": "Create the App Store Connect app record for this flavor and fill the public app metadata fields.",
        "acceptedPublicEvidence": ["App Store Connect app name, bundle id, SKU, app Apple ID, status label, and TestFlight/public listing URL when available."],
        "forbiddenEvidence": ["Apple account cookies, App Store Connect API key material, issuer keys, or certificate files."],
    },
    "appleCapabilitiesConfigured": {
        "tenantAction": "Enable required Apple capabilities such as Sign in with Apple, associated domains, and push/deep-link settings.",
        "acceptedPublicEvidence": ["Capability names, bundle id, associated domain names, and redacted capability checklist status."],
        "forbiddenEvidence": ["Provisioning profile contents, signing certificates, or private portal exports."],
    },
    "storeProductsConfigured": {
        "tenantAction": "Configure store products or subscription items required by the compliance mode for this flavor.",
        "acceptedPublicEvidence": ["Product ids, display names, price tiers, status labels, and approved/ready screenshots with sensitive values redacted."],
        "forbiddenEvidence": ["Payment provider keys, webhook signing values, banking files, or tax identity documents."],
    },
    "testFlightBuildUploaded": {
        "tenantAction": "Upload the signed iOS build to TestFlight and record the public build/version status.",
        "acceptedPublicEvidence": ["TestFlight build number, version, processing/ready status, app Apple ID, and public beta link when used."],
        "forbiddenEvidence": ["IPA signing assets, transporter credentials, App Store Connect key material, or account session dumps."],
    },
    "playConsoleRecordConfigured": {
        "tenantAction": "Create the Google Play Console app record and fill public app/package metadata.",
        "acceptedPublicEvidence": ["Package name, app name, Play app id, track name, status label, and listing URL when available."],
        "forbiddenEvidence": ["Google service account JSON, Play API keys, login cookies, or payment profile documents."],
    },
    "playAppSigningConfigured": {
        "tenantAction": "Enable Play App Signing or document the tenant signing path for this flavor.",
        "acceptedPublicEvidence": ["Play App Signing enabled status, package name, upload certificate fingerprint metadata, and track status."],
        "forbiddenEvidence": ["Upload keystore, signing passwords, certificate files, or private signing exports."],
    },
    "playInternalTrackUploaded": {
        "tenantAction": "Upload the signed Android artifact to the Google Play internal track and record public track metadata.",
        "acceptedPublicEvidence": ["Track name, version code, package name, release status, and tester link/listing URL when available."],
        "forbiddenEvidence": ["AAB signing files, Play service account material, account cookies, or private tester personal data."],
    },
    "directSignedPackageReady": {
        "tenantAction": "Build the tenant-signed direct distribution package and host it behind the tenant's approved distribution process.",
        "acceptedPublicEvidence": ["Package name, version code, APK/AAB filename, checksum, public download page, and release policy URL."],
        "forbiddenEvidence": ["Signing keys, keystore passwords, private download credentials, or device management enrollment files."],
    },
    "directDistributionPolicyPublished": {
        "tenantAction": "Publish the Android direct distribution policy and user safety instructions for the tenant channel.",
        "acceptedPublicEvidence": ["Public policy URL, download page URL, region availability, malware scan summary, and support contact URL."],
        "forbiddenEvidence": ["Private server credentials, internal firewall rules, unredacted user contact lists, or wallet keys."],
    },
    "legalUrlsVerified": {
        "tenantAction": "Verify privacy, terms, account deletion, refund, and support URLs are live for the tenant app.",
        "acceptedPublicEvidence": ["Public HTTPS legal URLs and status confirmation date."],
        "forbiddenEvidence": ["Draft legal documents with private account data or unpublished internal review comments."],
    },
    "oauthCallbacksConfigured": {
        "tenantAction": "Configure OAuth callback/deep-link URLs in tenant-controlled provider consoles and record public callback metadata.",
        "acceptedPublicEvidence": ["Callback URL, bundle/package id, provider name, and enabled login method labels."],
        "forbiddenEvidence": ["OAuth credential values, provider app credentials, login cookies, or account recovery material."],
    },
    "paymentConfigurationServerSide": {
        "tenantAction": "Confirm payment provider configuration is stored server-side in Tenant Edge/API worker settings for the selected compliance mode.",
        "acceptedPublicEvidence": ["Provider name, region/currency, compliance mode, public product ids, and server-side configuration status."],
        "forbiddenEvidence": ["Payment provider keys, webhook signing values, bank credentials, wallet private keys, or raw provider dashboard exports."],
    },
    "privacyQuestionnaireCompleted": {
        "tenantAction": "Complete the store privacy/data safety questionnaire for the tenant app.",
        "acceptedPublicEvidence": ["Questionnaire status, last completed date, data categories summary, and public privacy label URL when available."],
        "forbiddenEvidence": ["Internal legal notes with personal data, account credentials, or private reviewer messages."],
    },
    "reviewContactConfigured": {
        "tenantAction": "Configure store review/support contact details owned by the tenant.",
        "acceptedPublicEvidence": ["Support URL, support email alias, review contact role, and region support coverage."],
        "forbiddenEvidence": ["Personal phone numbers, private inbox credentials, identity documents, or unredacted staff records."],
    },
    "submissionStatus": {
        "tenantAction": "Record the current store/direct distribution submission status for this flavor.",
        "acceptedPublicEvidence": ["Status label such as ready, uploaded, internal testing, submitted, approved, or direct package published."],
        "forbiddenEvidence": ["Screenshots or exports containing credential values, private account identifiers, or signing material."],
    },
    "evidenceCapturedAt": {
        "tenantAction": "Capture the evidence timestamp after all public status fields are filled.",
        "acceptedPublicEvidence": ["ISO-8601 timestamp at or before the current audit run."],
        "forbiddenEvidence": ["Future timestamps, unverifiable local-only URLs, or private machine paths."],
    },
    "publicEvidenceRefs": {
        "tenantAction": "Attach public HTTPS references proving the tenant-owned store/direct distribution state.",
        "acceptedPublicEvidence": ["Public listing URLs, public policy URLs, public TestFlight/beta links, public release notes, or public CI run URLs."],
        "forbiddenEvidence": ["localhost URLs, private file paths, signed URLs with credential query values, account session links, or private dashboard-only URLs."],
    },
}


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


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def evidence_record(root: Path, path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": rel(root, path),
        "present": path.exists(),
    }
    if path.exists():
        record["sha256"] = sha256_file(path)
    return record


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted({marker for marker in FORBIDDEN_MARKERS if marker in text})


def result_status(path: Path) -> str:
    report = read_json(path)
    if not isinstance(report, dict):
        return "missing"
    result = report.get("result")
    if result == "passed":
        return "passed"
    if result == "blocked":
        return "blocked"
    return "review_required"


def strict_import_readiness(preflight_path: Path) -> dict[str, Any]:
    report = read_json(preflight_path)
    if not isinstance(report, dict):
        return {
            "ready": False,
            "command": "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            "blockedBy": [],
            "sourceBlockedBy": ["preflight-missing"],
            "nextAction": "Run store submission evidence preflight before strict import.",
        }
    readiness = report.get("strictImportReadiness")
    if not isinstance(readiness, dict):
        return {
            "ready": False,
            "command": report.get("strictImportCommand", "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict"),
            "blockedBy": [],
            "sourceBlockedBy": ["strict-import-readiness-missing"],
            "nextAction": "Regenerate store submission evidence preflight before strict import.",
        }
    return {
        "ready": readiness.get("ready") is True,
        "command": readiness.get("command", report.get("strictImportCommand")),
        "blockedBy": readiness.get("blockedBy", []) if isinstance(readiness.get("blockedBy"), list) else [],
        "sourceBlockedBy": readiness.get("sourceBlockedBy", []) if isinstance(readiness.get("sourceBlockedBy"), list) else [],
        "nextAction": readiness.get("nextAction", "Fix blocked flavor inputs and rerun preflight before strict import."),
    }


def blocked_input_paths(readiness: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for row in readiness.get("blockedBy", []):
        if not isinstance(row, dict):
            continue
        input_path = row.get("inputPath")
        if isinstance(input_path, str) and input_path:
            paths.append(input_path)
    return paths


def remediation_for_field(field: str) -> dict[str, Any]:
    fallback = {
        "tenantAction": f"Fill `{field}` with public tenant-owned store or distribution evidence, then rerun preflight.",
        "acceptedPublicEvidence": ["Public status label, public HTTPS reference, or redacted console metadata that proves the field."],
        "forbiddenEvidence": ["Credential values, signing files, private account exports, personal data, or local-only machine paths."],
    }
    entry = FIELD_REMEDIATION_CATALOG.get(field, fallback)
    return {
        "field": field,
        "tenantAction": entry["tenantAction"],
        "acceptedPublicEvidence": list(entry["acceptedPublicEvidence"]),
        "forbiddenEvidence": list(entry["forbiddenEvidence"]),
    }


def field_remediation(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness.get("blockedBy", []):
        if not isinstance(row, dict):
            continue
        blockers = [
            blocker
            for blocker in row.get("blockers", [])
            if isinstance(blocker, str) and blocker
        ]
        rows.append(
            {
                "flavor": row.get("flavor", ""),
                "inputPath": row.get("inputPath", ""),
                "remediationSteps": [remediation_for_field(blocker) for blocker in blockers],
            },
        )
    return rows


def fix_queue_rows(remediation_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    queue: list[dict[str, str]] = []
    for row in remediation_rows:
        flavor = str(row.get("flavor", ""))
        input_path = str(row.get("inputPath", ""))
        steps = row.get("remediationSteps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            accepted = step.get("acceptedPublicEvidence", [])
            forbidden = step.get("forbiddenEvidence", [])
            queue.append({
                "flavor": flavor,
                "inputPath": input_path,
                "field": str(step.get("field", "")),
                "tenantAction": str(step.get("tenantAction", "")),
                "acceptedPublicEvidence": "; ".join(str(item) for item in accepted if isinstance(item, str)),
                "forbiddenEvidence": "; ".join(str(item) for item in forbidden if isinstance(item, str)),
            })
    return queue


def fix_queue_markdown(rows: list[dict[str, str]], strict_import_command: str) -> str:
    lines = [
        "# Mobile Store Evidence Fix Queue",
        "",
        "Use this public queue to assign each blocked store-submission field to a tenant operator.",
        "Fill the matching per-flavor input files with public evidence only, then rerun the strict import command.",
        "",
        f"- Strict import command: `{strict_import_command}`",
        f"- Queue rows: `{len(rows)}`",
        "",
        "| Flavor | Input | Field | Tenant action | Accepted public evidence | Forbidden evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row.get(column, "")).replace("|", "\\|")
                for column in FIX_QUEUE_COLUMNS
            )
            + " |",
        )
    return "\n".join(lines).rstrip() + "\n"


def write_fix_queue(output: Path, rows: list[dict[str, str]], strict_import_command: str) -> None:
    csv_path = output / FIX_QUEUE_CSV
    markdown_path = output / FIX_QUEUE_MARKDOWN
    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIX_QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    markdown_path.write_text(
        fix_queue_markdown(rows, strict_import_command),
        encoding="utf-8",
    )


def build_manifest(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    ios_matrix_path = root / "build" / "ios-build-matrix" / "ios-build-matrix.json"
    ios_ci_path = root / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
    store_evidence_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
    store_preflight_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
    store_template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
    store_guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
    store_input_workspace_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.json"
    store_input_workspace_markdown_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.md"
    store_starter_manifest_path = root / "build" / "store-submission-starter" / "store-submission-starter-manifest.json"
    store_operator_runbook_path = root / "build" / "store-submission-starter" / "store-submission-operator-runbook.md"
    ios_ci_handoff_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
    store_publish_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
    store_signing_path = root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"
    store_strict_import = strict_import_readiness(store_preflight_path)
    store_field_remediation = field_remediation(store_strict_import)
    queue_rows = fix_queue_rows(store_field_remediation)
    output = output_dir or DEFAULT_OUTPUT_DIR
    fix_queue_csv_path = output / FIX_QUEUE_CSV
    fix_queue_markdown_path = output / FIX_QUEUE_MARKDOWN

    actions = [
        {
            "id": "install_full_xcode",
            "owner": "developer_machine",
            "blocksFullCompletion": True,
            "status": "passed" if result_status(ios_matrix_path) == "passed" else "blocked",
            "purpose": "Produce local unsigned iOS build-matrix evidence for all five Flutter flavors.",
            "commands": [
                "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer",
                "xcodebuild -version",
                "pod --version",
                "cd mobile && scripts/ios_build_matrix.py all --strict",
            ],
            "evidence": [
                evidence_record(root, ios_matrix_path),
            ],
            "notes": [
                "Requires full Xcode and CocoaPods on the machine that runs the command.",
                "The build remains unsigned; tenant App Store signing stays outside the repository.",
            ],
        },
        {
            "id": "import_unsigned_ios_ci_artifacts",
            "owner": "github_actions",
            "blocksFullCompletion": True,
            "status": result_status(ios_ci_path),
            "purpose": "Import GitHub Actions unsigned iOS artifacts into public audit metadata.",
            "commands": [
                "gh workflow run mobile-flutter.yml --repo <owner/repo>",
                "cd mobile && python3 scripts/mobile_completion_closure.py --repo <owner/repo>",
                "cd mobile && python3 scripts/download_ios_ci_artifacts.py --repo <owner/repo>",
                "cd mobile && python3 scripts/import_ios_ci_artifacts.py --strict",
            ],
            "evidence": [
                evidence_record(root, ios_ci_handoff_path),
                evidence_record(root, ios_ci_path),
            ],
            "notes": [
                "Use a GitHub repo that contains this template and the mobile workflow.",
                "The imported metadata must cover hongguo, douyin, hippo, and reelshort.",
            ],
        },
        {
            "id": "import_store_submission_evidence",
            "owner": "tenant_operator",
            "blocksFullCompletion": True,
            "status": result_status(store_evidence_path),
            "purpose": "Import public tenant-owned store, TestFlight, Play, or direct-distribution status evidence.",
            "strictImportReadiness": store_strict_import,
            "blockedInputPaths": blocked_input_paths(store_strict_import),
            "fieldRemediation": store_field_remediation,
            "commands": [
                "cd mobile && python3 scripts/export_store_signing_handoff.py",
                "cd mobile && python3 scripts/export_store_publish_config.py",
                "cd mobile && python3 scripts/export_store_submission_starter.py",
                "cd mobile && python3 scripts/prepare_store_submission_inputs.py",
                "cd mobile && python3 scripts/store_submission_evidence_preflight.py",
                "cd mobile && python3 scripts/import_store_submission_evidence.py",
                "cd mobile && python3 scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
                "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
                "cd mobile && python3 scripts/mobile_completion_closure.py --skip-ios-ci-download",
            ],
            "evidence": [
                evidence_record(root, store_signing_path),
                evidence_record(root, store_publish_path),
                evidence_record(root, store_starter_manifest_path),
                evidence_record(root, store_operator_runbook_path),
                evidence_record(root, store_template_path),
                evidence_record(root, store_guide_path),
                evidence_record(root, store_input_workspace_path),
                evidence_record(root, store_input_workspace_markdown_path),
                evidence_record(root, store_preflight_path),
                evidence_record(root, store_evidence_path),
            ],
            "notes": [
                "Start from build/store-submission-starter/store-submission-operator-runbook.md to connect signing, publish config, evidence collection, and strict import.",
                "Run prepare_store_submission_inputs.py to copy starter examples into build/store-submission-evidence/flavors/*.input.json; it does not overwrite existing tenant-filled inputs unless --force is used.",
                "For per-flavor handoff, save tenant-filled JSON files under build/store-submission-evidence/flavors/<flavor>.input.json and run the source-dir import command.",
                "Per-flavor input files take precedence over the combined input for preflight and source-dir strict import.",
                "For one-file handoff, fill store-submission-evidence.input.json from the generated template after tenant signing and store setup are done.",
                "Use only public status references, checklist flags, legal URL confirmation, and release artifact references.",
            ],
        },
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "packageType": "mobile_completion_unblocker",
        "generatedAt": utc_now(),
        "source": "mobile_completion_external_blocker_plan",
        "completionGateCommand": "npm run infra:mobile-app-completion-audit",
        "storeEvidenceFixQueue": {
            "csvPath": rel(root, fix_queue_csv_path),
            "markdownPath": rel(root, fix_queue_markdown_path),
            "strictImportCommand": store_strict_import.get("command", ""),
            "columns": FIX_QUEUE_COLUMNS,
            "rowCount": len(queue_rows),
        },
        "actions": actions,
        "secretBoundary": "Public command and evidence-path plan only. Keep signing files, OAuth credentials, payment credentials, webhook credentials, Cloudflare credentials, bank credentials, and wallet keys outside Git and outside mobile clients.",
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    return manifest


def markdown_from_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "# Mobile Completion Unblocker",
        "",
        f"Generated at: `{manifest['generatedAt']}`",
        "",
        "These actions close the external gates that prevent a full app-completion claim.",
        f"After the actions pass, rerun `{manifest['completionGateCommand']}`.",
        "",
    ]
    fix_queue = manifest.get("storeEvidenceFixQueue", {})
    if isinstance(fix_queue, dict):
        lines.extend([
            "## Store Evidence Fix Queue",
            "",
            f"- CSV: `{fix_queue.get('csvPath', '-')}`",
            f"- Markdown: `{fix_queue.get('markdownPath', '-')}`",
            f"- Rows: `{fix_queue.get('rowCount', 0)}`",
            "- Store evidence fix queue: assign each row to a tenant operator, update the matching per-flavor input, then rerun strict import.",
            "",
        ])
    for action in manifest["actions"]:
        lines.extend([
            f"## {action['id']}",
            "",
            f"- Owner: `{action['owner']}`",
            f"- Status: `{action['status']}`",
            f"- Purpose: {action['purpose']}",
            "- Commands:",
        ])
        lines.extend(f"  - `{command}`" for command in action["commands"])
        lines.append("- Evidence:")
        lines.extend(
            f"  - `{record['path']}` ({'present' if record['present'] else 'missing'})"
            for record in action["evidence"]
        )
        lines.append("- Notes:")
        lines.extend(f"  - {note}" for note in action["notes"])
        readiness = action.get("strictImportReadiness")
        if isinstance(readiness, dict):
            lines.append(f"- Strict import ready: `{readiness.get('ready', False)}`")
            lines.append(f"- Strict import command: `{readiness.get('command', '-')}`")
            blocked_paths = action.get("blockedInputPaths", [])
            if blocked_paths:
                lines.append("- Blocked input paths:")
                lines.extend(f"  - `{path}`" for path in blocked_paths)
            remediation_rows = action.get("fieldRemediation", [])
            if remediation_rows:
                lines.append("- Field remediation:")
                for row in remediation_rows:
                    lines.append(f"  - `{row.get('flavor', '-')}` input `{row.get('inputPath', '-')}`")
                    for step in row.get("remediationSteps", []):
                        accepted = "; ".join(step.get("acceptedPublicEvidence", []))
                        forbidden = "; ".join(step.get("forbiddenEvidence", []))
                        lines.append(f"    - `{step.get('field', '-')}`")
                        lines.append(f"      - Tenant action: {step.get('tenantAction', '-')}")
                        lines.append(f"      - Accepted public evidence: {accepted or '-'}")
                        lines.append(f"      - Forbidden evidence: {forbidden or '-'}")
        lines.append("")
    lines.append(manifest["secretBoundary"])
    return "\n".join(lines).rstrip() + "\n"


def export_unblocker(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    output = output_dir or root / "build" / "completion-unblocker"
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root, output)
    manifest_path = output / "mobile-completion-unblocker.json"
    markdown_path = output / "mobile-completion-unblocker.md"
    fix_queue_rows_value = fix_queue_rows(
        next(
            action["fieldRemediation"]
            for action in manifest["actions"]
            if action.get("id") == "import_store_submission_evidence"
        ),
    )
    strict_import_command = str(
        manifest.get("storeEvidenceFixQueue", {}).get("strictImportCommand", ""),
    )
    write_fix_queue(output, fix_queue_rows_value, strict_import_command)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_from_manifest(manifest), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else root / "build" / "completion-unblocker"
    manifest = export_unblocker(root, output_dir)
    manifest_path = output_dir / "mobile-completion-unblocker.json"
    markdown_path = output_dir / "mobile-completion-unblocker.md"
    print(f"Wrote completion unblocker manifest: {rel(root, manifest_path)}")
    print(f"Wrote completion unblocker guide: {rel(root, markdown_path)}")
    print(f"Actions: {len(manifest['actions'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
    return 1 if manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
