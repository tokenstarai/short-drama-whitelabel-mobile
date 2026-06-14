#!/usr/bin/env python3
"""Import public tenant store-submission evidence for completion audits."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = ROOT / "build" / "store-submission-evidence"
DEFAULT_SOURCE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.input.json"
DEFAULT_OUTPUT = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.json"
DEFAULT_TEMPLATE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.template.json"
DEFAULT_GUIDE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.guide.md"
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"

FLAVOR_DEFAULTS = {
    "hongguo": {
        "applicationId": "com.shortdrama.goldfruit",
        "appName": "GoldFruit Drama",
        "storeComplianceMode": "app_store",
        "primaryChannel": "app_store_testflight",
    },
    "douyin": {
        "applicationId": "com.shortdrama.pulse",
        "appName": "Pulse Drama",
        "storeComplianceMode": "android_direct",
        "primaryChannel": "android_direct",
    },
    "hippo": {
        "applicationId": "com.shortdrama.river",
        "appName": "River Drama",
        "storeComplianceMode": "app_store",
        "primaryChannel": "app_store_testflight",
    },
    "reelshort": {
        "applicationId": "com.shortdrama.cliff",
        "appName": "Cliff Drama",
        "storeComplianceMode": "play_store",
        "primaryChannel": "google_play_internal",
    },
}

ALLOWED_STATUSES_BY_CHANNEL = {
    "app_store_testflight": [
        "testflight_uploaded",
        "testflight_external_testing",
        "app_store_ready_for_review",
        "app_store_submitted",
        "app_store_approved",
    ],
    "google_play_internal": [
        "play_internal_uploaded",
        "play_closed_testing",
        "play_production_submitted",
        "play_production_approved",
    ],
    "android_direct": [
        "direct_signed_package_ready",
        "direct_distribution_published",
    ],
}

BASE_REQUIRED_FLAGS = [
    "tenantDeveloperAccountReady",
    "signedBuildProduced",
    "signingMaterialOutsideRepository",
    "storeRecordConfigured",
    "legalUrlsVerified",
    "oauthCallbacksConfigured",
    "paymentConfigurationServerSide",
    "privacyQuestionnaireCompleted",
    "reviewContactConfigured",
]

CHANNEL_REQUIRED_FLAGS = {
    "app_store_testflight": [
        "appStoreConnectRecordConfigured",
        "appleCapabilitiesConfigured",
        "storeProductsConfigured",
        "testFlightBuildUploaded",
    ],
    "google_play_internal": [
        "playConsoleRecordConfigured",
        "playAppSigningConfigured",
        "storeProductsConfigured",
        "playInternalTrackUploaded",
    ],
    "android_direct": [
        "directSignedPackageReady",
        "directDistributionPolicyPublished",
    ],
}

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


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
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
    return json.loads(path.read_text(encoding="utf-8"))


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted({marker for marker in FORBIDDEN_MARKERS if marker in text})


def required_flags(channel: str) -> list[str]:
    return BASE_REQUIRED_FLAGS + CHANNEL_REQUIRED_FLAGS.get(channel, [])


def expected_entries() -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {
        flavor: {"flavor": flavor, **values}
        for flavor, values in FLAVOR_DEFAULTS.items()
    }
    handoff = read_json(STORE_HANDOFF)
    if not isinstance(handoff, dict):
        return expected
    for entry in handoff.get("flavors", []):
        if not isinstance(entry, dict):
            continue
        flavor = str(entry.get("flavor"))
        if flavor not in expected:
            continue
        distribution = entry.get("distributionChannelReadiness")
        primary_channel = (
            distribution.get("primaryChannel")
            if isinstance(distribution, dict)
            else None
        )
        expected[flavor] = {
            "flavor": flavor,
            "applicationId": entry.get("applicationId") or expected[flavor]["applicationId"],
            "appName": entry.get("appName") or expected[flavor]["appName"],
            "storeComplianceMode": entry.get("storeComplianceMode") or expected[flavor]["storeComplianceMode"],
            "primaryChannel": primary_channel or expected[flavor]["primaryChannel"],
        }
    return expected


def template_submission(entry: dict[str, Any]) -> dict[str, Any]:
    channel = str(entry["primaryChannel"])
    flags = {name: False for name in required_flags(channel)}
    return {
        "flavor": entry["flavor"],
        "templateApplicationId": entry["applicationId"],
        "templateAppName": entry["appName"],
        "applicationId": entry["applicationId"],
        "appName": entry["appName"],
        "storeComplianceMode": entry["storeComplianceMode"],
        "primaryChannel": channel,
        "submissionStatus": "pending_tenant_action",
        **flags,
        "publicEvidenceRefs": [],
        "evidenceCapturedAt": None,
        "notes": "Copy this template to store-submission-evidence.input.json and replace only public status fields. Do not paste signing files, provider credentials, API tokens, webhook secrets, service-account JSON, or private keys.",
    }


def write_template(template_path: Path, expected: dict[str, dict[str, Any]]) -> Path:
    template = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "source": "tenant_store_submission_public_evidence_template",
        "instructions": [
            "Fill one submission object per flavor after tenant-owned signing and store setup are complete.",
            "Use only public status references such as TestFlight build number, Play internal track name, or direct-distribution package checksum.",
            "Keep Apple signing assets, Google service-account files, OAuth credentials, payment provider keys, webhook secrets, bank credentials, and crypto keys outside this file and outside Git.",
        ],
        "submissions": [
            template_submission(expected[flavor])
            for flavor in expected
        ],
        "secretBoundary": "Public store-submission status metadata only; no signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, or crypto keys.",
    }
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return template_path


def evidence_examples(channel: str) -> list[str]:
    if channel == "app_store_testflight":
        return [
            "TestFlight build number, version, upload date, and external-testing or review state.",
            "App Store Connect app record, IAP product ids, support URL, privacy URL, and account deletion URL confirmation.",
        ]
    if channel == "google_play_internal":
        return [
            "Play Console package name, version code, internal track name, upload date, and testing or review state.",
            "Play Billing product ids, Data safety status, support URL, privacy URL, and account deletion URL confirmation.",
        ]
    if channel == "android_direct":
        return [
            "Signed APK or AAB checksum, version code, distribution URL or channel name, and release date.",
            "Published payment policy, refund policy, support URL, privacy URL, and account deletion URL confirmation.",
        ]
    return ["Tenant-owned public release status reference."]


def write_guide(guide_path: Path, expected: dict[str, dict[str, Any]]) -> Path:
    lines = [
        "# Store Submission Evidence Guide",
        "",
        f"Generated at: `{utc_now()}`",
        "",
        "Use this guide after tenant-owned signing, store setup, OAuth callback registration, legal URL verification, and payment configuration are complete.",
        "Copy `store-submission-evidence.template.json` to `store-submission-evidence.input.json`, replace only public status fields, then run:",
        "",
        "```bash",
        "./scripts/import_store_submission_evidence.py --strict",
        "```",
        "",
        "Keep signing files, OAuth credentials, payment credentials, webhook credentials, service-account files, bank credentials, and wallet keys outside Git and outside the evidence JSON.",
        "",
    ]
    for flavor, entry in expected.items():
        channel = str(entry["primaryChannel"])
        statuses = ", ".join(
            f"`{status}`"
            for status in ALLOWED_STATUSES_BY_CHANNEL.get(channel, [])
        )
        lines.extend([
            f"## {flavor}",
            "",
            f"- App name: `{entry['appName']}`",
            f"- Application id: `{entry['applicationId']}`",
            f"- Compliance mode: `{entry['storeComplianceMode']}`",
            f"- Primary channel: `{channel}`",
            f"- Allowed statuses: {statuses}",
            "- Required checklist flags:",
        ])
        lines.extend(
            f"  - `{flag}`"
            for flag in required_flags(channel)
        )
        lines.append("- Public evidence examples:")
        lines.extend(
            f"  - {example}"
            for example in evidence_examples(channel)
        )
        lines.append("")
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return guide_path


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_submission(
    submission: dict[str, Any],
    expected: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    flavor = str(submission.get("flavor", ""))
    expected_entry = expected.get(flavor)
    if not expected_entry:
        return {
            "flavor": flavor or "unknown",
            "importResult": "blocked",
            "blockers": ["unknown-flavor"],
        }, ["unknown-flavor"]

    channel = str(expected_entry["primaryChannel"])
    if submission.get("templateApplicationId") not in {None, expected_entry["applicationId"]}:
        reasons.append("templateApplicationId")
    if submission.get("templateAppName") not in {None, expected_entry["appName"]}:
        reasons.append("templateAppName")
    if submission.get("storeComplianceMode") != expected_entry["storeComplianceMode"]:
        reasons.append("storeComplianceMode")
    if submission.get("primaryChannel") != channel:
        reasons.append("primaryChannel")
    if not non_empty_string(submission.get("applicationId")):
        reasons.append("applicationId")
    if not non_empty_string(submission.get("appName")):
        reasons.append("appName")
    status = str(submission.get("submissionStatus", ""))
    allowed_statuses = ALLOWED_STATUSES_BY_CHANNEL.get(channel, set())
    if status not in allowed_statuses:
        reasons.append("submissionStatus")

    checklist: dict[str, bool] = {}
    for flag in required_flags(channel):
        is_ready = submission.get(flag) is True
        checklist[flag] = is_ready
        if not is_ready:
            reasons.append(flag)

    evidence_refs = submission.get("publicEvidenceRefs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        reasons.append("publicEvidenceRefs")
        evidence_refs = []
    else:
        cleaned_refs: list[str] = []
        for item in evidence_refs:
            if not non_empty_string(item) or "REPLACE_" in str(item):
                reasons.append("publicEvidenceRefs")
                continue
            cleaned_refs.append(str(item))
        evidence_refs = cleaned_refs

    if not non_empty_string(submission.get("evidenceCapturedAt")):
        reasons.append("evidenceCapturedAt")

    normalized = {
        "flavor": flavor,
        "templateApplicationId": expected_entry["applicationId"],
        "templateAppName": expected_entry["appName"],
        "applicationId": str(submission.get("applicationId") or ""),
        "appName": str(submission.get("appName") or ""),
        "storeComplianceMode": expected_entry["storeComplianceMode"],
        "primaryChannel": channel,
        "submissionStatus": status,
        "publicChecklist": checklist,
        "publicEvidenceRefs": evidence_refs,
        "evidenceCapturedAt": submission.get("evidenceCapturedAt"),
        "importResult": "passed" if not reasons else "blocked",
    }
    if reasons:
        normalized["blockers"] = sorted(set(reasons))
    return normalized, reasons


def blocked_report(
    *,
    source: Path,
    output: Path,
    template: Path,
    guide: Path,
    expected: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "blocked",
        "sourcePath": rel(source),
        "templatePath": rel(template),
        "guidePath": rel(guide),
        "requiredFlavors": list(expected),
        "submissions": [],
        "missingFlavors": list(expected),
        "blockedFlavors": [
            {"flavor": flavor, "blockers": [reason]}
            for flavor in expected
        ],
        "forbiddenMarkerHits": [],
        "secretBoundary": "Public tenant store-submission evidence only. Do not include signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, or crypto keys.",
    }


def import_evidence(source: Path, output: Path, template: Path, guide: Path | None = None) -> dict[str, Any]:
    expected = expected_entries()
    guide_path = guide or template.with_name("store-submission-evidence.guide.md")
    write_template(template, expected)
    write_guide(guide_path, expected)

    if not source.exists():
        report = blocked_report(
            source=source,
            output=output,
            template=template,
            guide=guide_path,
            expected=expected,
            reason="input-evidence-missing",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return report

    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report = blocked_report(
            source=source,
            output=output,
            template=template,
            guide=guide_path,
            expected=expected,
            reason=f"invalid-json:{error}",
        )
        report["result"] = "failed"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return report

    raw_marker_hits = marker_hits(raw)
    submissions = raw.get("submissions") if isinstance(raw, dict) else None
    if not isinstance(submissions, list):
        submissions = []

    normalized_submissions: list[dict[str, Any]] = []
    blocked_flavors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in submissions:
        if not isinstance(item, dict):
            blocked_flavors.append({"flavor": "unknown", "blockers": ["submission-not-object"]})
            continue
        normalized, reasons = validate_submission(item, expected)
        normalized_submissions.append(normalized)
        flavor = str(normalized.get("flavor"))
        if flavor in seen:
            reasons.append("duplicate-flavor")
        seen.add(flavor)
        if reasons:
            blocked_flavors.append({
                "flavor": flavor,
                "blockers": sorted(set(reasons)),
            })

    missing = [flavor for flavor in expected if flavor not in seen]
    blocked_flavors.extend(
        {"flavor": flavor, "blockers": ["missing-submission"]}
        for flavor in missing
    )
    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "passed" if not missing and not blocked_flavors and not raw_marker_hits else "blocked",
        "sourcePath": rel(source),
        "sourceSha256": sha256_file(source),
        "templatePath": rel(template),
        "templateSha256": sha256_file(template),
        "guidePath": rel(guide_path),
        "guideSha256": sha256_file(guide_path),
        "requiredFlavors": list(expected),
        "submissions": normalized_submissions,
        "missingFlavors": missing,
        "blockedFlavors": blocked_flavors,
        "forbiddenMarkerHits": raw_marker_hits,
        "secretBoundary": "Public tenant store-submission evidence only. No signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, or crypto keys are stored in this report.",
    }
    if raw_marker_hits:
        report["result"] = "failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = import_evidence(
        args.source.resolve(),
        args.output.resolve(),
        args.template.resolve(),
        args.guide.resolve(),
    )
    print(f"Wrote store submission evidence template: {rel(args.template.resolve())}")
    print(f"Wrote store submission evidence guide: {rel(args.guide.resolve())}")
    print(f"Wrote store submission evidence: {rel(args.output.resolve())}")
    print(f"Result: {report['result']}")
    if report.get("missingFlavors"):
        print(f"Missing flavors: {', '.join(report['missingFlavors'])}")
    if report.get("blockedFlavors"):
        blocked = ", ".join(
            f"{item.get('flavor')}({','.join(item.get('blockers', []))})"
            for item in report["blockedFlavors"]
        )
        print(f"Blocked flavors: {blocked}")
    if report.get("forbiddenMarkerHits"):
        print(f"Disallowed marker hits: {', '.join(report['forbiddenMarkerHits'])}")
    return 1 if args.strict and report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
