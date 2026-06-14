#!/usr/bin/env python3
"""Export an actionable no-secret plan for external mobile completion blockers."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "completion-unblocker"

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


def build_manifest(root: Path = ROOT) -> dict[str, Any]:
    ios_matrix_path = root / "build" / "ios-build-matrix" / "ios-build-matrix.json"
    ios_ci_path = root / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
    store_evidence_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
    store_template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
    store_guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
    ios_ci_handoff_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
    store_publish_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
    store_signing_path = root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"

    actions = [
        {
            "id": "install_full_xcode",
            "owner": "developer_machine",
            "blocksFullCompletion": True,
            "status": "passed" if result_status(ios_matrix_path) == "passed" else "blocked",
            "purpose": "Produce local unsigned iOS build-matrix evidence for all four Flutter flavors.",
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
            "commands": [
                "cd mobile && python3 scripts/export_store_signing_handoff.py",
                "cd mobile && python3 scripts/export_store_publish_config.py",
                "cd mobile && python3 scripts/import_store_submission_evidence.py",
                "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
                "cd mobile && python3 scripts/mobile_completion_closure.py --skip-ios-ci-download",
            ],
            "evidence": [
                evidence_record(root, store_signing_path),
                evidence_record(root, store_publish_path),
                evidence_record(root, store_template_path),
                evidence_record(root, store_guide_path),
                evidence_record(root, store_evidence_path),
            ],
            "notes": [
                "Fill store-submission-evidence.input.json from the generated template after tenant signing and store setup are done.",
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
        lines.append("")
    lines.append(manifest["secretBoundary"])
    return "\n".join(lines).rstrip() + "\n"


def export_unblocker(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    output = output_dir or root / "build" / "completion-unblocker"
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root)
    manifest_path = output / "mobile-completion-unblocker.json"
    markdown_path = output / "mobile-completion-unblocker.md"
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
