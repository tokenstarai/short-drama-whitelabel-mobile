#!/usr/bin/env python3
"""Export a per-flavor tenant app handoff package for operator delivery."""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import export_store_submission_starter
import export_external_account_handoff
import prepare_store_submission_inputs
import store_submission_evidence_preflight
import export_ui_preview_gallery


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "app-handoff"
PACKAGE_NAME = "mobile-app-handoff"
DEFAULT_FLAVOR = "hongguo"

FORBIDDEN_MARKERS = [
    "cloudflare_api_token=",
    "cloudflare-api-token:",
    "bearer ey",
    "sk_live_",
    "sk_test_",
    "appsecret:",
    "secret_ciphertext:",
    "secretciphertext:",
    "x-signature:",
    "x-app-key:",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "-----begin private key-----",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted({marker for marker in FORBIDDEN_MARKERS if marker in text})


def by_flavor(rows: list[dict[str, Any]] | Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("flavor")): row
        for row in rows
        if isinstance(row, dict) and row.get("flavor")
    }


def release_artifacts_by_flavor(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "build" / "release-manifests" / "mobile-artifacts.json"
    if not path.exists():
        return {}
    artifacts = read_json(path).get("artifacts", [])
    result: dict[str, dict[str, Any]] = {}
    for artifact in artifacts if isinstance(artifacts, list) else []:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("platform") != "android" or artifact.get("mode") != "release":
            continue
        flavor = str(artifact.get("flavor"))
        slot = "releaseApk" if artifact.get("packageType") == "apk" else "releaseAppBundle"
        if slot not in {"releaseApk", "releaseAppBundle"}:
            continue
        result.setdefault(flavor, {})[slot] = {
            "path": artifact.get("path"),
            "sha256": artifact.get("sha256"),
            "sizeBytes": artifact.get("sizeBytes"),
            "packageType": artifact.get("packageType"),
        }
    return result


def runtime_smoke_by_flavor(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "build" / "runtime-smoke" / "android-runtime-smoke.json"
    if not path.exists():
        return {}
    report = read_json(path)
    result: dict[str, dict[str, Any]] = {}
    for run in report.get("runs", []):
        if not isinstance(run, dict):
            continue
        result[str(run.get("flavor"))] = {
            "installResult": run.get("installResult"),
            "launchResult": run.get("launchResult"),
            "apkPath": run.get("apkPath"),
            "apkSha256": run.get("apkSha256"),
            "screenshotPath": run.get("screenshotPath"),
            "screenshotSha256": run.get("screenshotSha256"),
            "deviceSerial": report.get("deviceSerial"),
            "avd": report.get("avd"),
        }
    return result


def store_submission_by_flavor(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
    if not path.exists():
        return {}
    report = read_json(path)
    result: dict[str, dict[str, Any]] = {}
    for row in report.get("submissions", []):
        if not isinstance(row, dict):
            continue
        result[str(row.get("flavor"))] = {
            "status": row.get("submissionStatus"),
            "evidenceCapturedAt": row.get("evidenceCapturedAt"),
            "publicEvidenceRefs": row.get("publicEvidenceRefs", []),
            "blockers": [],
        }
    for row in report.get("blockedFlavors", []):
        if not isinstance(row, dict):
            continue
        flavor = str(row.get("flavor"))
        result.setdefault(flavor, {})
        result[flavor].update(
            {
                "status": "blocked",
                "blockers": row.get("blockers", []),
                "remediationHints": row.get("remediationHints", []),
            },
        )
    return result


def store_submission_preflight_summary(root: Path) -> dict[str, Any]:
    report = store_submission_evidence_preflight.build_preflight_report(
        source=root / "build" / "store-submission-evidence" / "store-submission-evidence.input.json",
        source_dir=root / "build" / "store-submission-evidence" / "flavors",
        output=root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json",
        markdown=root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md",
    )
    return {
        "result": report.get("result"),
        "sourceMode": report.get("sourceMode"),
        "summary": report.get("summary", {}),
        "preflightReportPath": report.get("outputPath"),
        "preflightMarkdownPath": report.get("markdownPath"),
        "strictImportCommand": report.get("strictImportCommand"),
        "strictImportReadiness": report.get("strictImportReadiness", {}),
        "flavors": [
            {
                "flavor": row.get("flavor"),
                "primaryChannel": row.get("primaryChannel"),
                "status": row.get("status"),
                "blockers": row.get("blockers", []),
                "readyForStrictImport": row.get("readyForStrictImport", False),
                "strictImportBlockedBy": row.get("strictImportBlockedBy", []),
                "tenantEvidenceInputPath": row.get("tenantEvidenceInputPath"),
                "nextAction": row.get("nextAction"),
            }
            for row in report.get("flavors", [])
            if isinstance(row, dict)
        ],
    }


def copy_store_submission_starter(root: Path, destination: Path) -> dict[str, Any]:
    source = root / "build" / "store-submission-starter"
    with export_store_submission_starter.starter_output_lock(source):
        if not source.exists():
            raise SystemExit("Missing store submission starter; run scripts/export_store_submission_starter.py first.")
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("mobile-store-submission-starter.zip"),
        )
    return {
        "rootPath": "build/app-handoff/store-submission-starter",
        "manifestPath": "build/app-handoff/store-submission-starter/store-submission-starter-manifest.json",
        "collectorHtmlPath": "build/app-handoff/store-submission-starter/store-submission-evidence-collector.html",
        "operatorRunbookPath": "build/app-handoff/store-submission-starter/store-submission-operator-runbook.md",
        "sourcePackagePath": "build/store-submission-starter/mobile-store-submission-starter.zip",
        "embeddedPackage": False,
    }


def copy_store_submission_input_workspace(root: Path, destination: Path) -> dict[str, Any]:
    workspace = prepare_store_submission_inputs.prepare_workspace(
        root,
        root / "build" / "store-submission-evidence",
    )
    source = root / "build" / "store-submission-evidence"
    destination.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    for relative in [
        "store-submission-input-workspace.json",
        "store-submission-input-workspace.md",
        "store-submission-evidence-preflight.json",
        "store-submission-evidence-preflight.md",
    ]:
        source_path = source / relative
        if not source_path.exists():
            raise SystemExit(f"Missing store submission workspace file: {source_path.relative_to(root)}")
        target_path = destination / relative
        shutil.copyfile(source_path, target_path)
        copied_files.append(f"build/app-handoff/store-submission-evidence/{relative}")

    input_rows: list[dict[str, Any]] = []
    flavors_destination = destination / "flavors"
    flavors_destination.mkdir(parents=True, exist_ok=True)
    for row in workspace.get("inputs", []):
        if not isinstance(row, dict):
            continue
        flavor = str(row.get("flavor", ""))
        if not flavor:
            continue
        source_path = source / "flavors" / f"{flavor}.input.json"
        if not source_path.exists():
            raise SystemExit(f"Missing store submission flavor input: {source_path.relative_to(root)}")
        target_path = flavors_destination / source_path.name
        shutil.copyfile(source_path, target_path)
        copied_files.append(f"build/app-handoff/store-submission-evidence/flavors/{source_path.name}")
        input_rows.append({
            "flavor": flavor,
            "sourcePath": row.get("targetPath"),
            "embeddedPath": f"build/app-handoff/store-submission-evidence/flavors/{source_path.name}",
            "targetPath": row.get("targetPath"),
            "status": row.get("status"),
            "readyForStrictImport": row.get("readyForStrictImport", False),
            "preflightBlockers": row.get("preflightBlockers", []),
            "sha256": sha256_file(target_path),
        })

    return {
        "rootPath": "build/app-handoff/store-submission-evidence",
        "manifestPath": "build/app-handoff/store-submission-evidence/store-submission-input-workspace.json",
        "markdownPath": "build/app-handoff/store-submission-evidence/store-submission-input-workspace.md",
        "preflightReportPath": "build/app-handoff/store-submission-evidence/store-submission-evidence-preflight.json",
        "preflightMarkdownPath": "build/app-handoff/store-submission-evidence/store-submission-evidence-preflight.md",
        "sourceManifestPath": workspace.get("manifestPath"),
        "sourceMarkdownPath": workspace.get("markdownPath"),
        "preflightSummary": workspace.get("preflightSummary", {}),
        "inputs": input_rows,
        "copiedFiles": copied_files,
        "secretBoundary": workspace.get("secretBoundary"),
    }


def copy_external_account_handoff(
    root: Path,
    destination: Path,
    handoff: dict[str, Any],
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    copied_files: list[str] = []
    copied: dict[str, str] = {}
    for key in ["manifestPath", "markdownPath", "packagePath"]:
        value = handoff.get(key)
        if not isinstance(value, str):
            raise SystemExit(f"Missing external account handoff {key}.")
        source = root / value
        if not source.exists():
            raise SystemExit(f"Missing external account handoff file: {value}")
        target = destination / source.name
        shutil.copyfile(source, target)
        embedded_path = f"build/app-handoff/external-account-handoff/{source.name}"
        copied_files.append(embedded_path)
        copied[key] = embedded_path

    manifest_path = destination / "mobile-external-account-handoff.json"
    markdown_path = destination / "mobile-external-account-handoff.md"
    package_path = destination / "mobile-external-account-handoff.zip"
    return {
        "rootPath": "build/app-handoff/external-account-handoff",
        "sourceManifestPath": handoff.get("manifestPath"),
        "sourceMarkdownPath": handoff.get("markdownPath"),
        "sourcePackagePath": handoff.get("packagePath"),
        "manifestPath": copied["manifestPath"],
        "markdownPath": copied["markdownPath"],
        "packagePath": copied["packagePath"],
        "manifestSha256": sha256_file(manifest_path),
        "markdownSha256": sha256_file(markdown_path),
        "packageSha256": sha256_file(package_path),
        "sectionCount": len(handoff.get("sections", [])) if isinstance(handoff.get("sections"), list) else None,
        "flavorCount": len(handoff.get("flavors", [])) if isinstance(handoff.get("flavors"), list) else None,
        "tenantPortalEntry": handoff.get("tenantPortalEntry"),
        "strictImportCommand": handoff.get("strictImportCommand"),
        "noCredentialBoundary": handoff.get("noCredentialBoundary"),
        "disallowedValueMarkerHits": handoff.get("disallowedValueMarkerHits", []),
        "copiedFiles": copied_files,
    }


def copy_completion_closure(root: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    report_path = root / "build" / "completion-closure" / "mobile-completion-closure.json"
    markdown_path = root / "build" / "completion-closure" / "mobile-completion-closure.md"
    copied_files: list[str] = []
    report: dict[str, Any] = {}

    report_target = destination / "mobile-completion-closure.json"
    markdown_target = destination / "mobile-completion-closure.md"
    if report_path.exists():
        shutil.copyfile(report_path, report_target)
        copied_files.append("build/app-handoff/completion-closure/mobile-completion-closure.json")
        try:
            report = read_json(report_path)
        except json.JSONDecodeError:
            report = {}
    if markdown_path.exists():
        shutil.copyfile(markdown_path, markdown_target)
        copied_files.append("build/app-handoff/completion-closure/mobile-completion-closure.md")

    blockers = report.get("blockers", [])
    blocker_ids = [
        str(blocker.get("id"))
        for blocker in blockers
        if isinstance(blocker, dict) and blocker.get("id")
    ] if isinstance(blockers, list) else []

    return {
        "rootPath": "build/app-handoff/completion-closure",
        "sourceReportPath": "build/completion-closure/mobile-completion-closure.json",
        "sourceMarkdownPath": "build/completion-closure/mobile-completion-closure.md",
        "reportPath": "build/app-handoff/completion-closure/mobile-completion-closure.json",
        "markdownPath": "build/app-handoff/completion-closure/mobile-completion-closure.md",
        "reportPresent": report_target.exists(),
        "markdownPresent": markdown_target.exists(),
        "reportSha256": sha256_file(report_target) if report_target.exists() else None,
        "markdownSha256": sha256_file(markdown_target) if markdown_target.exists() else None,
        "appCompletion": report.get("appCompletion"),
        "canClaimComplete": report.get("canClaimComplete"),
        "summary": report.get("summary", {}),
        "blockerIds": blocker_ids,
        "secretBoundary": report.get("secretBoundary"),
        "copiedFiles": copied_files,
    }


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path != zip_path
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def write_markdown(manifest: dict[str, Any], path: Path) -> None:
    preflight = manifest.get("storeSubmissionPreflight", {})
    strict_import = preflight.get("strictImportReadiness", {})
    input_workspace = manifest.get("embeddedStoreSubmissionInputWorkspace", {})
    external_account = manifest.get("embeddedExternalAccountHandoff", {})
    completion_closure = manifest.get("embeddedCompletionClosure", {})
    ui_preview = manifest.get("uiPreview", {})
    lines = [
        "# Mobile App Handoff",
        "",
        f"- Generated at: `{manifest['generatedAt']}`",
        f"- Default flavor: `{manifest['defaultFlavor']}`",
        f"- Package: `{manifest['packagePath']}`",
        f"- HTML preview: `{manifest['htmlPath']}`",
        f"- UI contact sheet: `{ui_preview.get('contactSheetPath', '') if isinstance(ui_preview, dict) else ''}`",
        f"- UI contact sheet PNG: `{ui_preview.get('contactSheetPngPath', '') if isinstance(ui_preview, dict) else ''}`",
        f"- WYSIWYG runtime boards: `{len(manifest.get('embeddedWysiwygPreviewPaths', []))}`",
        f"- External account checklist: `{external_account.get('markdownPath', '') if isinstance(external_account, dict) else ''}`",
        f"- Completion closure: `{completion_closure.get('markdownPath', '') if isinstance(completion_closure, dict) else ''}`",
        "",
        "This handoff is public metadata only. It references build artifacts and tenant-owned actions, but it does not include signing material, store credentials, OAuth secrets, payment secrets, or Cloudflare tokens.",
        "",
        "## Store Submission Preflight",
        "",
        f"- Result: `{preflight.get('result', 'missing')}`",
        f"- Source mode: `{preflight.get('sourceMode', 'missing')}`",
        f"- Summary passed/blocked/failed: {preflight.get('summary', {}).get('passed', 0)}/{preflight.get('summary', {}).get('blocked', 0)}/{preflight.get('summary', {}).get('failed', 0)}",
        f"- Strict import command: `{preflight.get('strictImportCommand', 'cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict')}`",
        f"- Strict import ready: `{strict_import.get('ready', False)}`",
        "",
        "| Flavor | Channel | Status | Ready for strict import | Blockers | Tenant evidence input | Next action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in preflight.get("flavors", []):
        blockers = ", ".join(row.get("blockers", [])) or "-"
        lines.append(
            f"| {row.get('flavor')} | {row.get('primaryChannel')} | {row.get('status')} | {'yes' if row.get('readyForStrictImport') else 'no'} | {blockers} | `{row.get('tenantEvidenceInputPath')}` | {row.get('nextAction')} |",
        )
    lines.extend([
        "",
        "## External Account And Signing Checklist",
        "",
        f"- Embedded manifest: `{external_account.get('manifestPath', '') if isinstance(external_account, dict) else ''}`",
        f"- Embedded guide: `{external_account.get('markdownPath', '') if isinstance(external_account, dict) else ''}`",
        f"- Embedded package: `{external_account.get('packagePath', '') if isinstance(external_account, dict) else ''}`",
        f"- Required sections: `{external_account.get('sectionCount', 0) if isinstance(external_account, dict) else 0}`",
        f"- Flavor rows: `{external_account.get('flavorCount', 0) if isinstance(external_account, dict) else 0}`",
        f"- Tenant portal entry: `{external_account.get('tenantPortalEntry', '') if isinstance(external_account, dict) else ''}`",
        "",
        "## Completion Closure",
        "",
        f"- Embedded report: `{completion_closure.get('reportPath', '') if isinstance(completion_closure, dict) else ''}`",
        f"- Embedded guide: `{completion_closure.get('markdownPath', '') if isinstance(completion_closure, dict) else ''}`",
        f"- App completion: `{completion_closure.get('appCompletion', '') if isinstance(completion_closure, dict) else ''}`",
        f"- Can claim complete: `{completion_closure.get('canClaimComplete', False) if isinstance(completion_closure, dict) else False}`",
        f"- Blockers: `{', '.join(completion_closure.get('blockerIds', [])) if isinstance(completion_closure, dict) else ''}`",
        "",
        "",
        "## Store Submission Input Workspace",
        "",
        f"- Embedded workspace manifest: `{input_workspace.get('manifestPath', '')}`",
        f"- Embedded workspace guide: `{input_workspace.get('markdownPath', '')}`",
        f"- Embedded preflight guide: `{input_workspace.get('preflightMarkdownPath', '')}`",
        f"- Source workspace manifest: `{input_workspace.get('sourceManifestPath', '')}`",
        "",
        "| Flavor | Embedded input | Ready for strict import | Blockers |",
        "| --- | --- | --- | --- |",
    ])
    for row in input_workspace.get("inputs", []):
        blockers = ", ".join(row.get("preflightBlockers", [])) or "-"
        lines.append(
            f"| {row.get('flavor')} | `{row.get('embeddedPath')}` | {'yes' if row.get('readyForStrictImport') else 'no'} | {blockers} |",
        )
    lines.extend([
        "",
        "## Flavors",
        "",
    ])
    for flavor in manifest.get("flavors", []):
        lines.extend(
            [
                f"### {flavor['flavor']} - {flavor['appName']}",
                "",
                f"- Application ID: `{flavor['applicationId']}`",
                f"- Store mode: `{flavor['storeComplianceMode']}`",
                f"- Primary channel: `{flavor['primaryChannel']}`",
                f"- APK: `{flavor['androidArtifacts']['releaseApk'].get('path')}`",
                f"- AAB: `{flavor['androidArtifacts']['releaseAppBundle'].get('path')}`",
                f"- Runtime smoke: `{flavor['androidRuntimeSmoke'].get('launchResult', 'missing')}`",
                f"- Store evidence input: `{flavor['storeSubmission']['tenantEvidenceInputPath']}`",
                "",
            ],
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def html_escape(value: Any) -> str:
    if value is None:
        return ""
    return html_lib.escape(str(value), quote=True)


def basename(value: Any) -> str:
    if not value:
        return ""
    return Path(str(value)).name


def write_html(manifest: dict[str, Any], path: Path) -> None:
    overview_src = basename(manifest.get("embeddedPreviewPath")) or "../ui-preview-gallery/mobile-ui-readable-overview.svg"
    contact_sheet_src = basename(manifest.get("embeddedContactSheetPath")) or "../ui-preview-gallery/mobile-ui-preview-contact-sheet.svg"
    overview_png_src = basename(manifest.get("embeddedPreviewPngPath")) or "../ui-preview-gallery/mobile-ui-readable-overview.png"
    contact_sheet_png_src = basename(manifest.get("embeddedContactSheetPngPath")) or "../ui-preview-gallery/mobile-ui-preview-contact-sheet.png"
    wysiwyg_board_imgs = "\n".join(
        f'<img class="preview runtime-preview" src="{html_escape(basename(board_path))}" alt="WYSIWYG runtime preview board">'
        for board_path in manifest.get("embeddedWysiwygPreviewPaths", [])
        if isinstance(board_path, str)
    )
    wysiwyg_board_links = "\n".join(
        f'<a href="{html_escape(basename(board_path))}">Open {html_escape(basename(board_path))}</a>'
        for board_path in manifest.get("embeddedWysiwygPreviewPaths", [])
        if isinstance(board_path, str)
    )
    preflight = manifest.get("storeSubmissionPreflight", {})
    strict_import = preflight.get("strictImportReadiness", {})
    input_workspace = manifest.get("embeddedStoreSubmissionInputWorkspace", {})
    external_account = manifest.get("embeddedExternalAccountHandoff", {})
    completion_closure = manifest.get("embeddedCompletionClosure", {})
    preflight_rows = "".join(
        f"""
          <tr>
            <td>{html_escape(row.get('flavor'))}</td>
            <td>{html_escape(row.get('primaryChannel'))}</td>
            <td><span class="status warn">{html_escape(row.get('status'))}</span></td>
            <td>{'yes' if row.get('readyForStrictImport') else 'no'}</td>
            <td>{html_escape(', '.join(row.get('blockers', [])) or '-')}</td>
            <td><code>{html_escape(row.get('tenantEvidenceInputPath'))}</code></td>
            <td>{html_escape(row.get('nextAction'))}</td>
          </tr>"""
        for row in preflight.get("flavors", [])
        if isinstance(row, dict)
    )
    flavor_cards: list[str] = []
    for flavor in manifest.get("flavors", []):
        if not isinstance(flavor, dict):
            continue
        android_artifacts = flavor.get("androidArtifacts", {})
        if not isinstance(android_artifacts, dict):
            android_artifacts = {}
        release_apk = android_artifacts.get("releaseApk", {})
        release_bundle = android_artifacts.get("releaseAppBundle", {})
        if not isinstance(release_apk, dict):
            release_apk = {}
        if not isinstance(release_bundle, dict):
            release_bundle = {}
        runtime_smoke = flavor.get("androidRuntimeSmoke", {})
        if not isinstance(runtime_smoke, dict):
            runtime_smoke = {}
        store_submission = flavor.get("storeSubmission", {})
        if not isinstance(store_submission, dict):
            store_submission = {}
        actions = flavor.get("tenantRequiredActions", {})
        if not isinstance(actions, dict):
            actions = {}
        required_actions = [
            key
            for key, enabled in actions.items()
            if enabled is True
        ]
        action_items = "".join(
            f"<li>{html_escape(action)}</li>" for action in required_actions
        )
        smoke = runtime_smoke.get("launchResult", "missing")
        smoke_class = "ok" if smoke == "passed" else "warn"
        flavor_cards.append(
            f"""
      <article class="card">
        <div class="card-top">
          <div>
            <p class="eyebrow">{html_escape(flavor.get('styleTemplate'))}</p>
            <h3>{html_escape(flavor.get('appName'))}</h3>
          </div>
          <span class="pill">{html_escape(flavor.get('flavor'))}</span>
        </div>
        <dl class="meta">
          <div><dt>Application ID</dt><dd>{html_escape(flavor.get('applicationId'))}</dd></div>
          <div><dt>Bundle ID</dt><dd>{html_escape(flavor.get('bundleId'))}</dd></div>
          <div><dt>Compliance</dt><dd>{html_escape(flavor.get('storeComplianceMode'))}</dd></div>
          <div><dt>Primary channel</dt><dd>{html_escape(flavor.get('primaryChannel'))}</dd></div>
          <div><dt>Deep link</dt><dd>{html_escape(flavor.get('deepLinkScheme'))}</dd></div>
          <div><dt>Runtime smoke</dt><dd><span class="status {smoke_class}">{html_escape(smoke)}</span></dd></div>
        </dl>
        <div class="artifact-grid">
          <div>
            <b>APK</b>
            <code>{html_escape(release_apk.get('path'))}</code>
          </div>
          <div>
            <b>AAB</b>
            <code>{html_escape(release_bundle.get('path'))}</code>
          </div>
          <div>
            <b>Store evidence input</b>
            <code>{html_escape(store_submission.get('tenantEvidenceInputPath'))}</code>
          </div>
        </div>
        <details>
          <summary>Tenant required actions</summary>
          <ul>{action_items}</ul>
        </details>
      </article>""",
        )

    workspace_rows = "".join(
        f"""
          <tr>
            <td>{html_escape(row.get('flavor'))}</td>
            <td><code>{html_escape(row.get('embeddedPath'))}</code></td>
            <td>{'yes' if row.get('readyForStrictImport') else 'no'}</td>
            <td>{html_escape(', '.join(row.get('preflightBlockers', [])) or '-')}</td>
          </tr>"""
        for row in input_workspace.get("inputs", [])
        if isinstance(row, dict)
    )
    closure_blockers = ", ".join(
        str(blocker_id)
        for blocker_id in (
            completion_closure.get("blockerIds", [])
            if isinstance(completion_closure, dict)
            else []
        )
    ) or "-"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mobile App Handoff</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #5b6770;
      --line: #dfe5ea;
      --accent: #d9382f;
      --accent-soft: #fff0ee;
      --ok: #11845b;
      --warn: #a45b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      background: #11181f;
      color: #fff;
      padding: 28px 32px;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    h2 {{ font-size: 18px; margin-bottom: 14px; }}
    h3 {{ font-size: 17px; margin-bottom: 0; }}
    code {{
      display: block;
      overflow-wrap: anywhere;
      padding: 8px;
      border-radius: 6px;
      background: #f2f5f7;
      color: #26313a;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .hero-meta, .cards, .artifact-grid {{
      display: grid;
      gap: 12px;
    }}
    .hero-meta {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 18px; }}
    .panel, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .panel {{ margin-bottom: 18px; }}
    .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .preflight-table {{
      width: 100%;
      min-width: 900px;
      border-collapse: collapse;
    }}
    .table-wrap {{ overflow-x: auto; }}
    th, td {{
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .card-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0;
      margin-bottom: 4px;
      text-transform: uppercase;
    }}
    .pill, .status {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      white-space: nowrap;
      font-size: 12px;
      font-weight: 650;
    }}
    .pill {{ color: var(--accent); background: var(--accent-soft); }}
    .status.ok {{ color: var(--ok); background: #eaf7f1; }}
    .status.warn {{ color: var(--warn); background: #fff5e8; }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 14px;
      margin: 0 0 14px;
    }}
    dt {{ color: var(--muted); font-size: 12px; }}
    dd {{ margin: 2px 0 0; overflow-wrap: anywhere; }}
    .artifact-grid {{ grid-template-columns: 1fr; }}
    .preview {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    .runtime-preview {{ margin-top: 14px; }}
    .links a {{
      display: inline-flex;
      margin: 0 10px 10px 0;
      color: var(--accent);
      text-decoration: none;
      font-weight: 650;
    }}
    details {{ margin-top: 12px; }}
    summary {{ cursor: pointer; font-weight: 650; }}
    @media (max-width: 860px) {{
      header {{ padding: 22px 20px; }}
      main {{ padding: 16px; }}
      .hero-meta, .cards, .meta {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Mobile App Handoff</h1>
    <p>Generated at {html_escape(manifest.get('generatedAt'))}. Default flavor: {html_escape(manifest.get('defaultFlavor'))}.</p>
    <div class="hero-meta">
      <div><b>Package</b><code>{html_escape(manifest.get('packagePath'))}</code></div>
      <div><b>Manifest</b><code>{html_escape(manifest.get('manifestPath'))}</code></div>
      <div><b>Markdown</b><code>{html_escape(manifest.get('markdownPath'))}</code></div>
      <div><b>UI gallery</b><code>{html_escape(manifest.get('uiPreview', {}).get('htmlPath'))}</code></div>
    </div>
  </header>
  <main>
    <section class="panel">
      <h2>UI preview</h2>
      <h3>WYSIWYG runtime captures</h3>
      <p>These boards are copied from the release-rendered Flutter Web preview captures, not placeholder wireframes.</p>
      {wysiwyg_board_imgs}
      <img class="preview" src="{html_escape(overview_src)}" alt="Mobile UI readable overview">
      <img class="preview" src="{html_escape(contact_sheet_src)}" alt="Full mobile UI contact sheet" style="margin-top:14px">
      <div class="links">
        <a href="../ui-preview-gallery/mobile-ui-preview-gallery.html">Open full UI gallery</a>
        {wysiwyg_board_links}
        <a href="../ui-preview-gallery/mobile-ui-readable-overview.svg">Open overview SVG</a>
        <a href="{html_escape(overview_png_src)}">Open overview PNG</a>
        <a href="../ui-preview-gallery/mobile-ui-preview-contact-sheet.svg">Open contact sheet</a>
        <a href="{html_escape(contact_sheet_png_src)}">Open contact sheet PNG</a>
      </div>
    </section>
    <section class="panel">
      <h2>Secret boundary</h2>
      <p>{html_escape(manifest.get('secretBoundary'))}</p>
    </section>
    <section class="panel">
      <h2>External account and signing checklist</h2>
      <p>This package embeds the public-only checklist for Apple, Google Play, Android direct distribution, OAuth, consumer payments, and legal review inputs. It reserves the tenant portal entry without collecting credentials or signing files.</p>
      <div class="artifact-grid">
        <div><b>Checklist guide</b><code>{html_escape(external_account.get('markdownPath') if isinstance(external_account, dict) else '')}</code></div>
        <div><b>Checklist manifest</b><code>{html_escape(external_account.get('manifestPath') if isinstance(external_account, dict) else '')}</code></div>
        <div><b>Checklist package</b><code>{html_escape(external_account.get('packagePath') if isinstance(external_account, dict) else '')}</code></div>
      </div>
      <p>{html_escape(external_account.get('noCredentialBoundary') if isinstance(external_account, dict) else '')}</p>
    </section>
    <section class="panel">
      <h2>Completion closure</h2>
      <p>This is the latest public completion decision produced by <code>scripts/mobile_completion_closure.py</code>. It does not mark the app complete while external store, signing, or Xcode evidence remains missing.</p>
      <div class="artifact-grid">
        <div><b>Closure report</b><code>{html_escape(completion_closure.get('reportPath') if isinstance(completion_closure, dict) else '')}</code></div>
        <div><b>Closure guide</b><code>{html_escape(completion_closure.get('markdownPath') if isinstance(completion_closure, dict) else '')}</code></div>
        <div><b>Can claim complete</b><code>{html_escape(completion_closure.get('canClaimComplete') if isinstance(completion_closure, dict) else False)}</code></div>
        <div><b>Blockers</b><code>{html_escape(closure_blockers)}</code></div>
      </div>
    </section>
    <section class="panel">
      <h2>Store submission preflight</h2>
      <p>Result: <b>{html_escape(preflight.get('result', 'missing'))}</b>. Strict import ready: <b>{html_escape(strict_import.get('ready', False))}</b>. Summary passed/blocked/failed: {html_escape(preflight.get('summary', {}).get('passed', 0))}/{html_escape(preflight.get('summary', {}).get('blocked', 0))}/{html_escape(preflight.get('summary', {}).get('failed', 0))}. Fill the tenant evidence input files, then run <code>{html_escape(preflight.get('strictImportCommand', 'cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict'))}</code>.</p>
      <div class="table-wrap">
        <table class="preflight-table">
          <thead>
            <tr><th>Flavor</th><th>Channel</th><th>Status</th><th>Ready</th><th>Blockers</th><th>Input</th><th>Next action</th></tr>
          </thead>
          <tbody>{preflight_rows}</tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>Store submission input workspace</h2>
      <p>The handoff package embeds the tenant-fillable input workspace and the current field-level preflight blockers. Edit the source workspace files in <code>{html_escape(input_workspace.get('sourceManifestPath'))}</code>, rerun preflight, then strict import only after every flavor is ready.</p>
      <div class="artifact-grid">
        <div><b>Workspace manifest</b><code>{html_escape(input_workspace.get('manifestPath'))}</code></div>
        <div><b>Workspace guide</b><code>{html_escape(input_workspace.get('markdownPath'))}</code></div>
        <div><b>Preflight guide</b><code>{html_escape(input_workspace.get('preflightMarkdownPath'))}</code></div>
      </div>
      <div class="table-wrap">
        <table class="preflight-table">
          <thead>
            <tr><th>Flavor</th><th>Embedded input</th><th>Ready</th><th>Blockers</th></tr>
          </thead>
          <tbody>{workspace_rows}</tbody>
        </table>
      </div>
    </section>
    <section class="cards">
{''.join(flavor_cards)}
    </section>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def build_handoff(root: Path, output_dir: Path, *, default_flavor: str = DEFAULT_FLAVOR) -> dict[str, Any]:
    store_handoff_path = root / "build" / "release-handoff" / "mobile-store-handoff.json"
    if not store_handoff_path.exists():
        raise SystemExit("Missing store handoff manifest; run scripts/write_store_handoff_manifest.py first.")
    store_handoff = read_json(store_handoff_path)
    store_flavors = by_flavor(store_handoff.get("flavors", []))
    if default_flavor not in store_flavors:
        raise SystemExit(f"Default flavor {default_flavor!r} is not present in store handoff.")

    ui_preview = export_ui_preview_gallery.build_gallery(root, root / "build" / "ui-preview-gallery")
    starter = export_store_submission_starter.export_starter(
        root,
        root / "build" / "store-submission-starter",
    )
    external_account_handoff = export_external_account_handoff.export_handoff(
        root,
        root / "build" / "external-account-handoff",
    )
    starter_flavors = by_flavor(starter.get("flavors", []))
    artifacts = release_artifacts_by_flavor(root)
    runtime = runtime_smoke_by_flavor(root)
    submission = store_submission_by_flavor(root)

    staging_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(output_dir.parent)))
    try:
        flavor_rows: list[dict[str, Any]] = []
        for flavor, store_row in store_flavors.items():
            starter_row = starter_flavors.get(flavor, {})
            store_status = submission.get(flavor, {})
            flavor_rows.append(
                {
                    "flavor": flavor,
                    "appName": store_row.get("appName"),
                    "applicationId": store_row.get("applicationId"),
                    "bundleId": store_row.get("bundleId"),
                    "styleTemplate": store_row.get("styleTemplate"),
                    "storeComplianceMode": store_row.get("storeComplianceMode"),
                    "primaryChannel": (
                        store_row.get("distributionChannelReadiness", {})
                        if isinstance(store_row.get("distributionChannelReadiness"), dict)
                        else {}
                    ).get("primaryChannel"),
                    "deepLinkScheme": store_row.get("deepLinkScheme"),
                    "androidArtifacts": {
                        "releaseApk": artifacts.get(flavor, {}).get("releaseApk", {}),
                        "releaseAppBundle": artifacts.get(flavor, {}).get("releaseAppBundle", {}),
                    },
                    "androidRuntimeSmoke": runtime.get(flavor, {}),
                    "storeSubmission": {
                        "status": store_status.get("status", "missing"),
                        "blockers": store_status.get("blockers", []),
                        "remediationHints": store_status.get("remediationHints", []),
                        "tenantEvidenceInputPath": starter_row.get("tenantEvidenceInputPath"),
                        "inputExamplePath": (
                            f"build/store-submission-starter/{starter_row.get('inputExamplePath')}"
                            if starter_row.get("inputExamplePath")
                            else None
                        ),
                        "operatorChecklistPath": (
                            f"build/store-submission-starter/{starter_row.get('operatorChecklistPath')}"
                            if starter_row.get("operatorChecklistPath")
                            else None
                        ),
                        "submissionRunbookPath": (
                            f"build/store-submission-starter/{starter_row.get('submissionRunbookPath')}"
                            if starter_row.get("submissionRunbookPath")
                            else None
                        ),
                        "requiredChecklistFlags": starter_row.get("requiredFlags", []),
                        "allowedStatuses": starter_row.get("allowedStatuses", []),
                    },
                    "tenantRequiredActions": {
                        "replaceBundleIds": True,
                        "replaceSigningMaterial": True,
                        "configureOAuthCallbacks": bool(store_row.get("authProviders")),
                        "configureStoreProducts": bool(
                            store_row.get("storeProductRegistration", {}).get("storeProviders")
                            if isinstance(store_row.get("storeProductRegistration"), dict)
                            else False
                        ),
                        "publishLegalAndSupportUrls": True,
                        "verifyStoreComplianceMode": True,
                        "configureTenantEdgeSecretsServerSide": True,
                        "importStoreSubmissionEvidence": True,
                    },
                },
            )

        package_zip_path = staging_dir / f"{PACKAGE_NAME}.zip"
        final_manifest_path = output_dir / "mobile-app-handoff-manifest.json"
        final_markdown_path = output_dir / "mobile-app-handoff.md"
        final_html_path = output_dir / "mobile-app-handoff.html"
        final_embedded_preview_path = output_dir / "mobile-ui-readable-overview.svg"
        final_embedded_contact_sheet_path = output_dir / "mobile-ui-preview-contact-sheet.svg"
        final_embedded_preview_png_path = output_dir / "mobile-ui-readable-overview.png"
        final_embedded_contact_sheet_png_path = output_dir / "mobile-ui-preview-contact-sheet.png"
        final_package_path = output_dir / f"{PACKAGE_NAME}.zip"
        staging_html_path = staging_dir / "mobile-app-handoff.html"
        staging_embedded_preview_path = staging_dir / "mobile-ui-readable-overview.svg"
        staging_embedded_contact_sheet_path = staging_dir / "mobile-ui-preview-contact-sheet.svg"
        staging_embedded_preview_png_path = staging_dir / "mobile-ui-readable-overview.png"
        staging_embedded_contact_sheet_png_path = staging_dir / "mobile-ui-preview-contact-sheet.png"
        embedded_wysiwyg_previews: list[dict[str, Any]] = []
        staging_starter_dir = staging_dir / "store-submission-starter"
        staging_workspace_dir = staging_dir / "store-submission-evidence"
        staging_external_account_dir = staging_dir / "external-account-handoff"
        staging_completion_closure_dir = staging_dir / "completion-closure"
        readable_overview_path = root / str(ui_preview.get("readableOverview", {}).get("path", ""))
        if readable_overview_path.exists():
            shutil.copyfile(readable_overview_path, staging_embedded_preview_path)
        readable_overview_png_path = root / str(ui_preview.get("readableOverviewPng", {}).get("path", ""))
        if readable_overview_png_path.exists():
            shutil.copyfile(readable_overview_png_path, staging_embedded_preview_png_path)
        contact_sheet_path = root / str(ui_preview.get("contactSheet", {}).get("path", ""))
        if contact_sheet_path.exists():
            shutil.copyfile(contact_sheet_path, staging_embedded_contact_sheet_path)
        contact_sheet_png_path = root / str(ui_preview.get("contactSheetPng", {}).get("path", ""))
        if contact_sheet_png_path.exists():
            shutil.copyfile(contact_sheet_png_path, staging_embedded_contact_sheet_png_path)
        wysiwyg_runtime = (
            ui_preview.get("wysiwygRuntimePreviews")
            if isinstance(ui_preview.get("wysiwygRuntimePreviews"), dict)
            else {}
        )
        wysiwyg_boards = (
            wysiwyg_runtime.get("boards", [])
            if isinstance(wysiwyg_runtime, dict)
            else []
        )
        for board in wysiwyg_boards:
            if not isinstance(board, dict):
                continue
            board_path_value = board.get("path")
            if not isinstance(board_path_value, str):
                continue
            source = root / board_path_value
            if not source.exists():
                continue
            target = staging_dir / source.name
            shutil.copyfile(source, target)
            embedded_wysiwyg_previews.append(
                {
                    "id": board.get("id"),
                    "label": board.get("label"),
                    "sourcePath": board_path_value,
                    "path": rel(root, output_dir / source.name),
                    "sha256": sha256_file(target),
                    "width": board.get("width"),
                    "height": board.get("height"),
                    "screenCount": board.get("screenCount"),
                },
            )
        embedded_starter = copy_store_submission_starter(root, staging_starter_dir)
        embedded_input_workspace = copy_store_submission_input_workspace(root, staging_workspace_dir)
        embedded_external_account = copy_external_account_handoff(
            root,
            staging_external_account_dir,
            external_account_handoff,
        )
        embedded_completion_closure = copy_completion_closure(
            root,
            staging_completion_closure_dir,
        )
        preflight = store_submission_preflight_summary(root)
        manifest = {
            "schemaVersion": 1,
            "packageType": "mobile_app_handoff_package",
            "generatedAt": utc_now(),
            "defaultFlavor": default_flavor,
            "packagePath": rel(root, final_package_path),
            "storeHandoffPath": "build/release-handoff/mobile-store-handoff.json",
            "tenantReleasePackagePath": "build/release-handoff/mobile-tenant-release-package.json",
            "uiPreview": {
                "manifestPath": "build/ui-preview-gallery/ui-preview-gallery-manifest.json",
                "htmlPath": ui_preview.get("htmlPath"),
                "readableOverviewPath": ui_preview.get("readableOverview", {}).get("path"),
                "readableOverviewPngPath": ui_preview.get("readableOverviewPng", {}).get("path"),
                "contactSheetPath": ui_preview.get("contactSheet", {}).get("path"),
                "contactSheetPngPath": ui_preview.get("contactSheetPng", {}).get("path"),
                "contactSheetScreenCount": ui_preview.get("contactSheet", {}).get("screenCount"),
                "wysiwygRuntimePreviews": {
                    "source": wysiwyg_runtime.get("source") if isinstance(wysiwyg_runtime, dict) else None,
                    "sourceDirectory": wysiwyg_runtime.get("sourceDirectory") if isinstance(wysiwyg_runtime, dict) else None,
                    "captureCount": wysiwyg_runtime.get("captureCount") if isinstance(wysiwyg_runtime, dict) else None,
                    "boardCount": wysiwyg_runtime.get("boardCount") if isinstance(wysiwyg_runtime, dict) else None,
                    "boards": [
                        {
                            "id": board.get("id"),
                            "path": board.get("path"),
                            "sha256": board.get("sha256"),
                            "screenCount": board.get("screenCount"),
                        }
                        for board in wysiwyg_runtime.get("boards", [])
                        if isinstance(board, dict)
                    ] if isinstance(wysiwyg_runtime, dict) else [],
                },
                "packagePath": ui_preview.get("packagePath"),
                "screenshotCount": ui_preview.get("screenshotCount"),
            },
            "storeSubmissionPreflight": preflight,
            "embeddedStoreSubmissionStarter": embedded_starter,
            "embeddedStoreSubmissionInputWorkspace": embedded_input_workspace,
            "embeddedExternalAccountHandoff": embedded_external_account,
            "embeddedCompletionClosure": embedded_completion_closure,
            "flavors": flavor_rows,
            "secretBoundary": "Public app handoff metadata only; do not include signing material, store credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or private keys.",
            "manifestPath": rel(root, final_manifest_path),
            "markdownPath": rel(root, final_markdown_path),
            "htmlPath": rel(root, final_html_path),
            "embeddedPreviewPath": (
                rel(root, final_embedded_preview_path)
                if staging_embedded_preview_path.exists()
                else None
            ),
            "embeddedContactSheetPath": (
                rel(root, final_embedded_contact_sheet_path)
                if staging_embedded_contact_sheet_path.exists()
                else None
            ),
            "embeddedPreviewPngPath": (
                rel(root, final_embedded_preview_png_path)
                if staging_embedded_preview_png_path.exists()
                else None
            ),
            "embeddedContactSheetPngPath": (
                rel(root, final_embedded_contact_sheet_png_path)
                if staging_embedded_contact_sheet_png_path.exists()
                else None
            ),
            "embeddedWysiwygPreviewPaths": [
                str(preview["path"])
                for preview in embedded_wysiwyg_previews
                if isinstance(preview.get("path"), str)
            ],
            "embeddedWysiwygPreviews": embedded_wysiwyg_previews,
        }
        if staging_embedded_preview_path.exists():
            manifest["embeddedPreviewSha256"] = sha256_file(staging_embedded_preview_path)
        if staging_embedded_contact_sheet_path.exists():
            manifest["embeddedContactSheetSha256"] = sha256_file(staging_embedded_contact_sheet_path)
        if staging_embedded_preview_png_path.exists():
            manifest["embeddedPreviewPngSha256"] = sha256_file(staging_embedded_preview_png_path)
        if staging_embedded_contact_sheet_png_path.exists():
            manifest["embeddedContactSheetPngSha256"] = sha256_file(staging_embedded_contact_sheet_png_path)
        manifest["embeddedWysiwygPreviewSha256"] = {
            str(preview["path"]): str(preview["sha256"])
            for preview in embedded_wysiwyg_previews
            if isinstance(preview.get("path"), str) and isinstance(preview.get("sha256"), str)
        }
        write_html(manifest, staging_html_path)
        manifest["htmlSha256"] = sha256_file(staging_html_path)
        manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
        staging_manifest_path = staging_dir / "mobile-app-handoff-manifest.json"
        staging_markdown_path = staging_dir / "mobile-app-handoff.md"
        staging_manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        write_markdown(manifest, staging_markdown_path)
        write_zip(staging_dir, package_zip_path)
        manifest["packageSha256"] = sha256_file(package_zip_path)
        staging_manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        package_zip_path.unlink()
        write_zip(staging_dir, package_zip_path)
        manifest["packageSha256"] = sha256_file(package_zip_path)
        staging_manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        os.replace(staging_dir, output_dir)
        return manifest
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--default-flavor", default=DEFAULT_FLAVOR)
    args = parser.parse_args()

    manifest = build_handoff(
        ROOT,
        args.output_dir.resolve(),
        default_flavor=args.default_flavor,
    )
    print(f"Wrote app handoff manifest: {manifest['manifestPath']}")
    print(f"Wrote app handoff package: {manifest['packagePath']}")
    print(f"Flavors: {len(manifest['flavors'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
