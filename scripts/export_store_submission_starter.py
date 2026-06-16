#!/usr/bin/env python3
"""Export no-secret tenant starter inputs for store-submission evidence."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import html
import hashlib
import json
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import import_store_submission_evidence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-submission-starter"
PACKAGE_NAME = "mobile-store-submission-starter"
PACKAGE_FILE = "mobile-store-submission-starter.zip"
PER_FLAVOR_INPUT_DIR = "build/store-submission-evidence/flavors"
PER_FLAVOR_IMPORT_COMMAND = (
    "cd mobile && python3 scripts/import_store_submission_evidence.py "
    "--source-dir build/store-submission-evidence/flavors --strict"
)
PREFLIGHT_REPORT_PATH = "build/store-submission-evidence/store-submission-evidence-preflight.json"
PREFLIGHT_COMMAND = "cd mobile && python3 scripts/store_submission_evidence_preflight.py"

SECRET_BOUNDARY = (
    "Public status references only; do not paste signing files, provider credentials, "
    "API tokens, webhook secrets, service-account JSON, bank credentials, private keys, "
    "or signing/credential file references such as .p12, .p8, .mobileprovision, .jks, or .keystore."
)
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_LOCK_STATE = threading.local()


def _thread_lock(lock_path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(lock_path)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[lock_path] = lock
        return lock


def _held_lock_counts() -> dict[Path, int]:
    counts = getattr(_LOCK_STATE, "starter_output_locks", None)
    if counts is None:
        counts = {}
        _LOCK_STATE.starter_output_locks = counts
    return counts


@contextlib.contextmanager
def starter_output_lock(output_dir: Path):
    output = output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / f".{output.name}.lock"
    lock = _thread_lock(lock_path)
    with lock:
        held_counts = _held_lock_counts()
        if held_counts.get(lock_path, 0) > 0:
            held_counts[lock_path] += 1
            try:
                yield
            finally:
                held_counts[lock_path] -= 1
                if held_counts[lock_path] <= 0:
                    del held_counts[lock_path]
            return
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            held_counts[lock_path] = 1
            try:
                yield
            finally:
                held_counts[lock_path] -= 1
                if held_counts[lock_path] <= 0:
                    del held_counts[lock_path]
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
            "Do not use signing or credential file names as evidence refs, including .p12, .p8, .mobileprovision, .jks, .keystore, AuthKey, upload-keystore, or service-account files.",
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
            "Do not add signing or credential file references such as .p12, .p8, .mobileprovision, .jks, .keystore, AuthKey, upload-keystore, or service-account files.",
            "After replacing placeholders, save per-flavor files under build/store-submission-evidence/flavors/<flavor>.input.json and run scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict.",
            "Per-flavor input files take precedence over the combined input for preflight and source-dir strict import; use build/store-submission-evidence/store-submission-evidence.input.json only when no per-flavor inputs are present.",
        ],
        "publicEvidenceRefSchema": import_store_submission_evidence.public_evidence_ref_schema(),
        "submissions": submissions,
        "secretBoundary": SECRET_BOUNDARY,
    }


def collector_html(expected: dict[str, dict[str, Any]]) -> str:
    sections: list[str] = []
    flavor_form_sections: list[str] = []
    flavor_json_sections: list[str] = []
    template = input_document([
        submission_input(entry)
        for entry in expected.values()
    ])
    starter_documents: dict[str, dict[str, Any]] = {}
    evidence_type_options = "\n".join(
        f'                    <option value="{html.escape(evidence_type)}">{html.escape(evidence_type)}</option>'
        for evidence_type in sorted(import_store_submission_evidence.ALLOWED_EVIDENCE_REF_TYPES)
    )
    for flavor, entry in expected.items():
        channel = str(entry["primaryChannel"])
        statuses = import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel]
        flags = import_store_submission_evidence.required_flags(channel)
        examples = import_store_submission_evidence.evidence_examples(channel)
        starter_document = input_document([submission_input(entry)])
        starter_documents[flavor] = starter_document
        status_options = "\n".join(
            f'                <option value="{html.escape(status)}">{html.escape(status)}</option>'
            for status in statuses
        )
        flag_controls = "\n".join(
            f'              <label><input type="checkbox" data-flag="{html.escape(flag)}"> <code>{html.escape(flag)}</code></label>'
            for flag in flags
        )
        evidence_rows = "\n".join(
            "\n".join([
                "              <div class=\"evidence-row\">",
                f"                <input data-ref-label placeholder=\"Evidence {index} label\">",
                "                <select data-ref-type>",
                evidence_type_options,
                "                </select>",
                "                <input data-ref-value placeholder=\"Public value, URL, or checksum\">",
                "                <input data-ref-captured-at placeholder=\"Captured at, optional ISO-8601\">",
                "              </div>",
            ])
            for index in range(1, 4)
        )
        flavor_form_sections.append(
            "\n".join([
                '<section class="flavor evidence-form" data-evidence-form="' + html.escape(flavor) + '">',
                "  <header>",
                "    <div>",
                f"      <p>Offline form output: <code>{html.escape(PER_FLAVOR_INPUT_DIR)}/{html.escape(flavor)}.input.json</code></p>",
                f"      <h2>{html.escape(entry['appName'])} evidence form</h2>",
                "    </div>",
                f"    <button type=\"button\" data-download-json>Download {html.escape(flavor)}.input.json</button>",
                "  </header>",
                "  <div class=\"form-grid\">",
                "    <label>Application id / bundle id",
                f"      <input data-field=\"applicationId\" value=\"{html.escape(entry['applicationId'])}\">",
                "    </label>",
                "    <label>App name",
                f"      <input data-field=\"appName\" value=\"{html.escape(entry['appName'])}\">",
                "    </label>",
                "    <label>Submission status",
                "      <select data-field=\"submissionStatus\">",
                status_options,
                "      </select>",
                "    </label>",
                "    <label>Evidence captured at",
                "      <input data-field=\"evidenceCapturedAt\" placeholder=\"2026-06-14T00:00:00Z\">",
                "    </label>",
                "  </div>",
                "  <div class=\"flag-list\">",
                flag_controls,
                "  </div>",
                "  <h3>Public evidence refs</h3>",
                "  <p class=\"small\">Use public build numbers, public HTTPS legal/support URLs, store product ids, review state, internal track names, direct distribution URL, or direct package checksum. Keep credentials and signing files outside this form.</p>",
                "  <div class=\"evidence-rows\">",
                evidence_rows,
                "  </div>",
                "  <div class=\"form-actions\">",
                "    <button type=\"button\" data-generate-json>Generate JSON</button>",
                "    <span data-form-status>Not generated yet.</span>",
                "  </div>",
                f"  <textarea data-generated-json=\"{html.escape(flavor)}\" spellcheck=\"false\"></textarea>",
                "</section>",
            ]),
        )
        flavor_json = json.dumps(starter_document, indent=2, ensure_ascii=False)
        flavor_json_escaped = html.escape(flavor_json)
        flavor_json_uri = quote(flavor_json)
        sections.append(
            "\n".join([
                '<section class="flavor">',
                "  <header>",
                f"    <p>{html.escape(entry['storeComplianceMode'])} / {html.escape(channel)}</p>",
                f"    <h2>{html.escape(entry['appName'])}</h2>",
                f"    <span>{html.escape(flavor)}</span>",
                "  </header>",
                "  <div class=\"grid\">",
                "    <div>",
                "      <h3>Allowed statuses</h3>",
                "      <ul>",
                *[f"        <li><code>{html.escape(status)}</code></li>" for status in statuses],
                "      </ul>",
                "    </div>",
                "    <div>",
                "      <h3>Required flags</h3>",
                "      <ul>",
                *[f"        <li><code>{html.escape(flag)}</code></li>" for flag in flags],
                "      </ul>",
                "    </div>",
                "    <div>",
                "      <h3>Public evidence examples</h3>",
                "      <ul>",
                *[f"        <li>{html.escape(example)}</li>" for example in examples],
                "      </ul>",
                "    </div>",
                "    <div>",
                "      <h3>Structured evidence refs</h3>",
                "      <ul>",
                "        <li><code>label</code> and <code>type</code> are required.</li>",
                "        <li>Use at least one of <code>value</code>, <code>url</code>, or <code>sha256</code>.</li>",
                "        <li>If <code>url</code> is present, it must be a public HTTPS URL; localhost, file URLs, plain HTTP, loopback, private IP ranges, and <code>.local</code> hosts are rejected.</li>",
                "        <li><code>evidenceCapturedAt</code> and structured <code>capturedAt</code> values must be timezone-aware ISO-8601 timestamps that are not in the future.</li>",
                "        <li>Allowed types are listed in <code>publicEvidenceRefSchema.allowedTypes</code>.</li>",
                "      </ul>",
                "    </div>",
                "  </div>",
                "</section>",
            ]),
        )
        flavor_json_sections.append(
            "\n".join([
                '<section class="flavor">',
                "  <header>",
                "    <div>",
                f"      <p>Save as <code>{html.escape(PER_FLAVOR_INPUT_DIR)}/{html.escape(flavor)}.input.json</code></p>",
                f"      <h2>{html.escape(entry['appName'])} JSON</h2>",
                "    </div>",
                f"    <a download=\"{html.escape(flavor)}.input.json\" href=\"data:application/json;charset=utf-8,{flavor_json_uri}\">Download {html.escape(flavor)}.input.json</a>",
                "  </header>",
                f"  <textarea data-flavor-json=\"{html.escape(flavor)}\" spellcheck=\"false\">{flavor_json_escaped}</textarea>",
                "</section>",
            ]),
        )
    template_json = html.escape(json.dumps(template, indent=2, ensure_ascii=False))
    starter_documents_json = json.dumps(starter_documents, ensure_ascii=False).replace("</", "<\\/")
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>Store Submission Evidence Collector</title>",
        "  <style>",
        "    * { box-sizing: border-box; }",
        "    body { margin: 0; font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f6f7f9; color: #191b21; }",
        "    main { max-width: 1180px; margin: 0 auto; padding: 30px 18px 48px; }",
        "    .hero { border-bottom: 1px solid #d8dde6; padding-bottom: 22px; margin-bottom: 24px; }",
        "    h1 { margin: 0; font-size: 30px; letter-spacing: 0; }",
        "    .hero p { max-width: 820px; color: #555f70; line-height: 1.55; }",
        "    .command, textarea { width: 100%; border: 1px solid #ccd3df; border-radius: 8px; background: #fff; }",
        "    .command { padding: 12px 14px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-x: auto; }",
        "    textarea { min-height: 360px; padding: 14px; margin-top: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; }",
        "    .flavor { background: #fff; border: 1px solid #dfe4ec; border-radius: 8px; margin-top: 18px; padding: 16px; }",
        "    .flavor header { display: flex; gap: 12px; justify-content: space-between; align-items: end; border-bottom: 1px solid #eef1f5; padding-bottom: 10px; margin-bottom: 12px; }",
        "    .flavor h2 { margin: 0; font-size: 20px; letter-spacing: 0; }",
        "    .flavor p, .flavor span { margin: 0; color: #626b7b; font-size: 13px; }",
        "    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }",
        "    h3 { margin: 0 0 8px; font-size: 14px; }",
        "    ul { margin: 0; padding-left: 18px; }",
        "    li { margin: 4px 0; line-height: 1.4; }",
        "    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }",
        "    button { border: 0; border-radius: 8px; background: #191b21; color: #fff; font: inherit; padding: 10px 14px; cursor: pointer; }",
        "    input, select { width: 100%; border: 1px solid #ccd3df; border-radius: 8px; padding: 10px 12px; font: inherit; background: #fff; }",
        "    .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }",
        "    .form-grid label { display: grid; gap: 6px; color: #4f5968; font-size: 13px; }",
        "    .flag-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 14px; margin: 14px 0; }",
        "    .flag-list label { display: flex; gap: 8px; align-items: center; min-width: 0; }",
        "    .flag-list input { width: auto; }",
        "    .evidence-row { display: grid; grid-template-columns: 1.1fr 1fr 1.5fr 1.2fr; gap: 8px; margin-top: 8px; }",
        "    .form-actions { display: flex; align-items: center; gap: 12px; margin-top: 14px; }",
        "    .small { color: #626b7b; line-height: 1.45; }",
        "    @media (max-width: 760px) { .flavor header { display: block; } .grid { grid-template-columns: 1fr; } }",
        "    @media (max-width: 760px) { .form-grid, .flag-list, .evidence-row { grid-template-columns: 1fr; } }",
        "  </style>",
        "</head>",
        "<body>",
        "  <main>",
        '    <section class="hero">',
        "      <h1>Store Submission Evidence Collector</h1>",
        "      <p>Fill this public metadata template only after tenant-owned signing, store setup, OAuth callback registration, legal URL verification, and payment configuration are complete. Save each flavor JSON under <code>build/store-submission-evidence/flavors/&lt;flavor&gt;.input.json</code>, then run the source-dir importer below. Per-flavor input files take precedence over the combined input for preflight and source-dir strict import.</p>",
        '      <div class="command">./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict</div>',
        "    </section>",
        *sections,
        "    <section class=\"flavor\">",
        "      <header>",
        "        <div>",
        "          <p>offline_tenant_public_evidence_form</p>",
        "          <h2>Generate tenant input JSON</h2>",
        "        </div>",
        "      </header>",
        "      <p>These forms run locally in the browser and only generate public metadata JSON. The importer remains the source of truth; generated files still fail preflight until every required status, checklist flag, timestamp, and evidence ref is tenant-owned and complete.</p>",
        "    </section>",
        *flavor_form_sections,
        "    <section class=\"flavor\">",
        "      <header>",
        "        <div>",
        "          <p>tenant_store_submission_public_evidence_input</p>",
        "          <h2>Per-flavor JSON outputs</h2>",
        "        </div>",
        "      </header>",
        "      <p>Use these single-flavor JSON outputs when you want source-dir strict import. Each file remains intentionally blocked until tenant-owned public evidence replaces placeholders.</p>",
        "    </section>",
        *flavor_json_sections,
        "    <section class=\"flavor\">",
        "      <header>",
        "        <div>",
        "          <p>tenant_store_submission_public_evidence_input</p>",
        "          <h2>Editable JSON template</h2>",
        "        </div>",
        "      </header>",
        f"      <textarea spellcheck=\"false\">{template_json}</textarea>",
        "    </section>",
        "  </main>",
        f"  <script type=\"application/json\" id=\"starter-documents\">{starter_documents_json}</script>",
        "  <script>",
        "    const starterDocuments = JSON.parse(document.getElementById('starter-documents').textContent);",
        "    const credentialFilePattern = /(\\.mobileprovision|\\.p12|\\.p8|\\.jks|\\.keystore|authkey_|service_account|upload-keystore)/i;",
        "    const clone = (value) => JSON.parse(JSON.stringify(value));",
        "    const normalizeIso = (value) => value.trim() || new Date().toISOString().replace(/\\.\\d{3}Z$/, 'Z');",
        "    function collectEvidenceRefs(form) {",
        "      const refs = [];",
        "      form.querySelectorAll('.evidence-row').forEach((row) => {",
        "        const label = row.querySelector('[data-ref-label]').value.trim();",
        "        const type = row.querySelector('[data-ref-type]').value;",
        "        const rawValue = row.querySelector('[data-ref-value]').value.trim();",
        "        const capturedAt = row.querySelector('[data-ref-captured-at]').value.trim();",
        "        if (!label && !rawValue && !capturedAt) return;",
        "        const ref = { label, type };",
        "        if (/^https:\\/\\//i.test(rawValue)) ref.url = rawValue;",
        "        else if (/^[a-f0-9]{64}$/i.test(rawValue)) ref.sha256 = rawValue.toLowerCase();",
        "        else ref.value = rawValue;",
        "        if (capturedAt) ref.capturedAt = capturedAt;",
        "        refs.push(ref);",
        "      });",
        "      return refs;",
        "    }",
        "    function buildDocument(form) {",
        "      const flavor = form.dataset.evidenceForm;",
        "      const document = clone(starterDocuments[flavor]);",
        "      const submission = document.submissions[0];",
        "      submission.applicationId = form.querySelector('[data-field=\"applicationId\"]').value.trim();",
        "      submission.appName = form.querySelector('[data-field=\"appName\"]').value.trim();",
        "      submission.submissionStatus = form.querySelector('[data-field=\"submissionStatus\"]').value;",
        "      submission.evidenceCapturedAt = normalizeIso(form.querySelector('[data-field=\"evidenceCapturedAt\"]').value);",
        "      form.querySelectorAll('[data-flag]').forEach((checkbox) => { submission[checkbox.dataset.flag] = checkbox.checked; });",
        "      submission.publicEvidenceRefs = collectEvidenceRefs(form);",
        "      submission.tenantMustReplacePlaceholders = false;",
        "      document.generatedAt = new Date().toISOString().replace(/\\.\\d{3}Z$/, 'Z');",
        "      return document;",
        "    }",
        "    function refreshForm(form) {",
        "      const status = form.querySelector('[data-form-status]');",
        "      const output = form.querySelector('[data-generated-json]');",
        "      const document = buildDocument(form);",
        "      const serialized = JSON.stringify(document, null, 2);",
        "      output.value = serialized;",
        "      const allFlagsChecked = Array.from(form.querySelectorAll('[data-flag]')).every((checkbox) => checkbox.checked);",
        "      const hasEvidence = document.submissions[0].publicEvidenceRefs.length > 0;",
        "      const hasCredentialFileName = credentialFilePattern.test(JSON.stringify(document.submissions[0].publicEvidenceRefs));",
        "      status.textContent = hasCredentialFileName ? 'Remove credential or signing file references before import.' : (allFlagsChecked && hasEvidence ? 'Ready to run preflight.' : 'Generated, but still missing checked flags or evidence refs.');",
        "      return serialized;",
        "    }",
        "    document.querySelectorAll('[data-evidence-form]').forEach((form) => {",
        "      form.querySelector('[data-generate-json]').addEventListener('click', () => refreshForm(form));",
        "      form.querySelector('[data-download-json]').addEventListener('click', () => {",
        "        const serialized = refreshForm(form);",
        "        const blob = new Blob([serialized + '\\n'], { type: 'application/json' });",
        "        const link = document.createElement('a');",
        "        link.href = URL.createObjectURL(blob);",
        "        link.download = `${form.dataset.evidenceForm}.input.json`;",
        "        document.body.appendChild(link);",
        "        link.click();",
        "        URL.revokeObjectURL(link.href);",
        "        link.remove();",
        "      });",
        "      refreshForm(form);",
        "    });",
        "  </script>",
        "</body>",
        "</html>",
        "",
    ])


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


def flavor_runbook_markdown(entry: dict[str, Any]) -> str:
    flavor = str(entry["flavor"])
    channel = str(entry["primaryChannel"])
    lines = [
        f"# {flavor} Store Submission Operator Runbook",
        "",
        "This runbook connects the public starter input, signing handoff, publish config, evidence collector, and strict importer for one tenant-owned release path. It is not proof that the app has been submitted.",
        "",
        "## App Target",
        "",
        f"- App name: `{entry['appName']}`",
        f"- Application id / bundle id: `{entry['applicationId']}`",
        f"- Store compliance mode: `{entry['storeComplianceMode']}`",
        f"- Primary channel: `{channel}`",
        "",
        "## Files To Use",
        "",
        f"- Starter input: `build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json`",
        f"- Operator checklist: `build/store-submission-starter/{flavor}/operator-checklist.md`",
        f"- This runbook: `build/store-submission-starter/{flavor}/submission-runbook.md`",
        f"- iOS export options template: `build/store-signing-handoff/{flavor}/ExportOptions.plist.template`",
        f"- Android signing template: `build/store-signing-handoff/{flavor}/android-signing.properties.template`",
        f"- Publish config template: `build/store-publish-config/{flavor}/publish-config.template.json`",
        f"- Store listing draft: `build/store-assets/{flavor}/listing.json`",
        "- Evidence collector: `build/store-submission-starter/store-submission-evidence-collector.html`",
        f"- Per-flavor evidence target: `{PER_FLAVOR_INPUT_DIR}/{flavor}.input.json`",
        "- Combined evidence import target: `build/store-submission-evidence/store-submission-evidence.input.json`",
        "",
        "## Operator Steps",
        "",
        "1. Replace app identity, icon, legal URLs, OAuth callback ownership, and store product ids in tenant-owned accounts.",
        "2. Fill the signing handoff templates outside Git, then produce signed TestFlight, Play internal, or Android direct artifacts in the tenant account.",
        "3. Fill the publish config template with public store fields and keep provider credentials server-side.",
        f"4. Open the evidence collector and save this flavor's public status fields as `{PER_FLAVOR_INPUT_DIR}/{flavor}.input.json`.",
        f"5. Repeat for every flavor, then run `{PER_FLAVOR_IMPORT_COMMAND}` to merge and validate all public evidence.",
        "6. If you prefer one file, merge all submissions into `build/store-submission-evidence/store-submission-evidence.input.json` and run `cd mobile && python3 scripts/import_store_submission_evidence.py --strict`.",
        "7. Run `npm run infra:mobile-app-completion-audit` from the repository root and confirm the store-submission evidence check passes.",
        "",
        "## Input Precedence",
        "",
        "Per-flavor input files take precedence over the combined input for preflight and source-dir strict import. If an older combined input conflicts with current per-flavor evidence, refresh or remove the combined input before final audit.",
        "",
        "## Secret Boundary",
        "",
        SECRET_BOUNDARY,
        "",
    ]
    return "\n".join(lines)


def operator_runbook_markdown(expected: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Store Submission Operator Runbook",
        "",
        "This runbook is the no-secret handoff path from the open-source Flutter template to tenant-owned store submission evidence. It gathers existing generated packages into one operational sequence; it does not create passing evidence by itself.",
        "",
        "## Required Generated Packages",
        "",
        "- Store signing handoff: `build/store-signing-handoff/mobile-store-signing-handoff.zip`",
        "- Store publish config: `build/store-publish-config/mobile-store-publish-config.zip`",
        "- Store submission starter: `build/store-submission-starter/mobile-store-submission-starter.zip`",
        "- Store assets: `build/store-assets/mobile-store-assets.zip`",
        "- UI preview gallery: `build/ui-preview-gallery/mobile-ui-preview-gallery.html`",
        "- Evidence collector: `build/store-submission-starter/store-submission-evidence-collector.html`",
        "",
        "## Structured public evidence refs",
        "",
        "The importer accepts either a plain public string or an object with `label`, `type`, and at least one of `value`, `url`, or `sha256`. If `url` is present, it must be a public HTTPS URL; localhost, file URLs, plain HTTP, loopback, private IP ranges, and `.local` hosts are rejected. `evidenceCapturedAt` and structured `capturedAt` values must be timezone-aware ISO-8601 timestamps that are not in the future. Allowed types are listed in `publicEvidenceRefSchema.allowedTypes` inside each starter input. Do not use signing or credential filenames as evidence refs.",
        "",
        "## Input Precedence",
        "",
        "Per-flavor input files take precedence over the combined input for preflight and source-dir strict import. Save tenant-filled files under `build/store-submission-evidence/flavors/<flavor>.input.json`; use the combined input only when no per-flavor inputs are present.",
        "",
        "## Per-Flavor Evidence Checklist",
        "",
        "Each flavor stays blocked until the tenant replaces every placeholder below with public submission evidence and reruns the strict source-dir import.",
        "",
    ]
    for flavor, entry in expected.items():
        channel = str(entry["primaryChannel"])
        statuses = import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel]
        flags = import_store_submission_evidence.required_flags(channel)
        lines.extend([
            f"### {flavor} evidence fields",
            "",
            f"- Tenant evidence input: `{PER_FLAVOR_INPUT_DIR}/{flavor}.input.json`",
            f"- Primary channel: `{channel}`",
            f"- Allowed submission statuses: `{', '.join(statuses)}`",
            "- Required checklist flags:",
            *[f"  - `{flag}`" for flag in flags],
            "",
        ])
    lines.extend([
        "## Commands",
        "",
        "```bash",
        "cd mobile",
        "./scripts/export_store_signing_handoff.py",
        "./scripts/export_store_publish_config.py",
        "./scripts/export_store_submission_starter.py",
        "./scripts/store_submission_evidence_preflight.py",
        "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
        "./scripts/import_store_submission_evidence.py --strict",
        "```",
        "",
        "## Flavor Runbooks",
        "",
    ])
    for flavor, entry in expected.items():
        lines.extend([
            f"### {flavor}",
            "",
            f"- App name: `{entry['appName']}`",
            f"- Compliance mode: `{entry['storeComplianceMode']}`",
            f"- Primary channel: `{entry['primaryChannel']}`",
            f"- Flavor runbook: `build/store-submission-starter/{flavor}/submission-runbook.md`",
            f"- Input example: `build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json`",
            f"- Signing templates: `build/store-signing-handoff/{flavor}/ExportOptions.plist.template`, `build/store-signing-handoff/{flavor}/android-signing.properties.template`",
            f"- Publish config: `build/store-publish-config/{flavor}/publish-config.template.json`",
            "",
        ])
    lines.extend([
        "## Completion Rule",
        "",
        "Full app completion remains blocked until every flavor has tenant-owned public evidence imported from TestFlight, Play internal testing, or direct distribution. Placeholder `pending_tenant_action` values must not be treated as passing evidence.",
        "",
        "## Secret Boundary",
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


def evidence_packet_summary(flavor_records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "packetType": "tenant_public_store_submission_evidence_packet",
        "preflightCommand": PREFLIGHT_COMMAND,
        "nextImportCommand": PER_FLAVOR_IMPORT_COMMAND,
        "combinedImportCommand": "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
        "perFlavorInputDirectory": PER_FLAVOR_INPUT_DIR,
        "preflightReportPath": PREFLIGHT_REPORT_PATH,
        "secretBoundary": SECRET_BOUNDARY,
        "flavors": [
            {
                "flavor": record["flavor"],
                "appName": record["appName"],
                "applicationId": record["applicationId"],
                "storeComplianceMode": record["storeComplianceMode"],
                "primaryChannel": record["primaryChannel"],
                "starterInputExamplePath": f"build/store-submission-starter/{record['inputExamplePath']}",
                "tenantEvidenceInputPath": record["tenantEvidenceInputPath"],
                "operatorChecklistPath": f"build/store-submission-starter/{record['operatorChecklistPath']}",
                "submissionRunbookPath": f"build/store-submission-starter/{record['submissionRunbookPath']}",
                "allowedSubmissionStatuses": record["allowedStatuses"],
                "requiredChecklistFlags": record["requiredFlags"],
            }
            for record in flavor_records
        ],
    }


def export_starter(root: Path = ROOT, output_dir: Path | None = None, *, lock: bool = True) -> dict[str, Any]:
    root = root.resolve()
    output = (output_dir or root / "build" / "store-submission-starter").resolve()
    if lock:
        with starter_output_lock(output):
            return export_starter(root, output, lock=False)
    if output.exists():
        shutil.rmtree(output)
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
        runbook_path = flavor_dir / "submission-runbook.md"
        input_path.write_text(
            json.dumps(input_document([submission]), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        checklist_path.write_text(checklist_markdown(entry), encoding="utf-8")
        runbook_path.write_text(flavor_runbook_markdown(entry), encoding="utf-8")
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
            "tenantEvidenceInputPath": f"{PER_FLAVOR_INPUT_DIR}/{flavor}.input.json",
            "operatorChecklistPath": rel(output, checklist_path),
            "submissionRunbookPath": rel(output, runbook_path),
            "inputExampleSha256": sha256_file(input_path),
            "operatorChecklistSha256": sha256_file(checklist_path),
            "submissionRunbookSha256": sha256_file(runbook_path),
        })

    all_dir = output / "all-flavors"
    all_dir.mkdir(parents=True, exist_ok=True)
    all_input_path = all_dir / "store-submission-evidence.input.example.json"
    all_input_path.write_text(
        json.dumps(input_document(all_submissions), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    collector_path = output / "store-submission-evidence-collector.html"
    collector_path.write_text(collector_html(expected), encoding="utf-8")
    operator_runbook_path = output / "store-submission-operator-runbook.md"
    operator_runbook_path.write_text(operator_runbook_markdown(expected), encoding="utf-8")

    zip_path = output / PACKAGE_FILE
    write_zip(output, zip_path)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_store_submission_starter",
        "tenantActionSummary": "Copy each flavor input example to build/store-submission-evidence/flavors/<flavor>.input.json after tenant-owned signing and store setup. Per-flavor input files take precedence over the combined input for preflight and source-dir strict import.",
        "packagePath": rel(root, zip_path),
        "packageSha256": sha256_file(zip_path),
        "operatorRunbookPath": rel(output, operator_runbook_path),
        "operatorRunbookSha256": sha256_file(operator_runbook_path),
        "collectorHtmlPath": rel(output, collector_path),
        "collectorHtmlSha256": sha256_file(collector_path),
        "allFlavorsInputExamplePath": rel(output, all_input_path),
        "allFlavorsInputExampleSha256": sha256_file(all_input_path),
        "preflightReportPath": PREFLIGHT_REPORT_PATH,
        "preflightCommand": PREFLIGHT_COMMAND,
        "perFlavorInputDirectory": PER_FLAVOR_INPUT_DIR,
        "perFlavorImportCommand": PER_FLAVOR_IMPORT_COMMAND,
        "flavors": flavor_records,
        "evidencePacketSummary": evidence_packet_summary(flavor_records),
        "importCommand": PER_FLAVOR_IMPORT_COMMAND,
        "combinedImportCommand": "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
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
