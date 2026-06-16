#!/usr/bin/env python3
"""Import public tenant store-submission evidence for completion audits."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = ROOT / "build" / "store-submission-evidence"
DEFAULT_SOURCE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.input.json"
DEFAULT_SOURCE_DIR = DEFAULT_EVIDENCE_DIR / "flavors"
DEFAULT_OUTPUT = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.json"
DEFAULT_TEMPLATE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.template.json"
DEFAULT_GUIDE = DEFAULT_EVIDENCE_DIR / "store-submission-evidence.guide.md"
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"

FLAVOR_DEFAULTS = {
    "coolshow": {
        "applicationId": "com.coolshow.short",
        "appName": "CoolShow Short",
        "storeComplianceMode": "android_direct",
        "primaryChannel": "android_direct",
    },
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

FORBIDDEN_EVIDENCE_REF_MARKERS = [
    ".mobileprovision",
    ".p12",
    ".p8",
    ".jks",
    ".keystore",
    "app-store-connect-api-key",
    "authkey_",
    "google-service-account",
    "provisioning_profile",
    "service_account",
    "upload-keystore",
]

ALLOWED_EVIDENCE_REF_TYPES = {
    "account_deletion_url",
    "app_store_record",
    "data_safety",
    "direct_distribution_url",
    "direct_package_checksum",
    "legal_url",
    "payment_policy",
    "play_console_record",
    "play_internal_track",
    "privacy_url",
    "review_state",
    "store_product",
    "support_url",
    "testflight_build",
}

EVIDENCE_REF_PAYLOAD_FIELDS = ["value", "url", "sha256"]
EVIDENCE_REF_OPTIONAL_FIELDS = EVIDENCE_REF_PAYLOAD_FIELDS + ["capturedAt"]


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


def evidence_ref_marker_hits(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.lower()
    else:
        text = json.dumps(value, ensure_ascii=False).lower()
    return sorted(
        marker for marker in FORBIDDEN_EVIDENCE_REF_MARKERS
        if marker in text
    )


def required_flags(channel: str) -> list[str]:
    return BASE_REQUIRED_FLAGS + CHANNEL_REQUIRED_FLAGS.get(channel, [])


def public_evidence_ref_schema() -> dict[str, Any]:
    return {
        "acceptedFormats": ["string", "object"],
        "requiredObjectFields": "label, type, and one of value/url/sha256",
        "urlRequirement": "When present, url must be a public HTTPS URL; localhost, file URLs, plain HTTP, loopback, private IP ranges, and .local hosts are rejected.",
        "capturedAtRequirement": "evidenceCapturedAt and structured capturedAt values must be timezone-aware ISO-8601 timestamps that are not in the future.",
        "allowedTypes": sorted(ALLOWED_EVIDENCE_REF_TYPES),
        "objectFields": {
            "label": "Required public human-readable evidence label.",
            "type": "Required normalized public evidence type.",
            "value": "Optional public build number, track name, product id, status, or checksum.",
            "url": "Optional public HTTPS store, legal, support, or direct-distribution URL.",
            "sha256": "Optional public checksum for signed direct-distribution artifacts.",
            "capturedAt": "Optional timezone-aware ISO-8601 timestamp when this public evidence was captured; future timestamps are rejected.",
        },
        "secretBoundary": "Do not use credential filenames, signing files, provider credentials, service-account files, webhook secrets, bank credentials, crypto keys, or Cloudflare tokens as evidence refs.",
    }


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
        "notes": "Copy this template to store-submission-evidence.input.json and replace only public status fields. Do not paste signing files, provider credentials, API tokens, webhook secrets, service-account JSON, private keys, or signing/credential file references such as .p12, .p8, .mobileprovision, .jks, or .keystore.",
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
            "Do not use signing or credential file names as evidence references, including .p12, .p8, .mobileprovision, .jks, .keystore, AuthKey, upload-keystore, or service-account files.",
        ],
        "publicEvidenceRefSchema": public_evidence_ref_schema(),
        "submissions": [
            template_submission(expected[flavor])
            for flavor in expected
        ],
        "secretBoundary": "Public store-submission status metadata only; no signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or signing/credential file references.",
    }
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return template_path


def source_dir_for(source: Path) -> Path:
    return source.parent / "flavors"


def flavor_source_candidates(source_dir: Path, flavor: str) -> list[Path]:
    return [
        source_dir / f"{flavor}.input.json",
        source_dir / f"{flavor}.json",
        source_dir / flavor / "store-submission-evidence.input.json",
    ]


def submission_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    submissions = raw.get("submissions")
    if isinstance(submissions, list):
        return [
            item
            for item in submissions
            if isinstance(item, dict)
        ]
    if non_empty_string(raw.get("flavor")):
        return [raw]
    return []


def merged_source_document(submissions: list[dict[str, Any]], input_records: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "source": "tenant_store_submission_public_evidence_input",
        "sourceMode": "per_flavor_merge",
        "sourceInputPaths": input_records,
        "submissions": submissions,
        "secretBoundary": "Public store-submission status metadata only; no signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or signing/credential file references.",
    }


def load_per_flavor_sources(
    source_dir: Path,
    expected: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, str]]]:
    submissions: list[dict[str, Any]] = []
    errors: list[str] = []
    input_records: list[dict[str, str]] = []
    for flavor in expected:
        for candidate in flavor_source_candidates(source_dir, flavor):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                errors.append(f"{flavor}:invalid-json:{error}")
                break
            items = submission_items(raw)
            if not items:
                errors.append(f"{flavor}:submission-missing")
                break
            submissions.extend(items)
            input_records.append({
                "flavor": flavor,
                "path": rel(candidate),
                "sha256": sha256_file(candidate),
            })
            break
    if not submissions:
        return None, errors, input_records
    return merged_source_document(submissions, input_records), errors, input_records


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
        "Either copy `store-submission-evidence.template.json` to `store-submission-evidence.input.json` and replace all public status fields in one file, or save per-flavor files as `build/store-submission-evidence/flavors/<flavor>.input.json`.",
        "For one combined evidence file, run:",
        "",
        "```bash",
        "./scripts/import_store_submission_evidence.py --strict",
        "```",
        "",
        "For per-flavor evidence files, run:",
        "",
        "```bash",
        "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
        "```",
        "",
        "Keep signing files, OAuth credentials, payment credentials, webhook credentials, service-account files, bank credentials, and wallet keys outside Git and outside the evidence JSON.",
        "Evidence refs must be public store or distribution metadata, not signing or credential filenames such as .p12, .p8, .mobileprovision, .jks, .keystore, AuthKey, upload-keystore, or service-account files.",
        "Evidence refs may be plain public strings or structured objects with `label`, `type`, and at least one of `value`, `url`, or `sha256`; allowed object types are listed in `publicEvidenceRefSchema.allowedTypes`.",
        "When a structured evidence ref includes `url`, it must be a public HTTPS URL; localhost, file URLs, plain HTTP, loopback, private IP ranges, and .local hosts are rejected.",
        "`evidenceCapturedAt` and structured ref `capturedAt` values must be timezone-aware ISO-8601 timestamps that are not in the future.",
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


def is_public_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    host = hostname.rstrip(".").lower()
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
        or "." not in host
    ):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global


def parse_evidence_timestamp(value: Any) -> datetime | None:
    if not non_empty_string(value):
        return None
    text = value.strip()
    if "REPLACE_" in text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def is_valid_evidence_timestamp(value: Any, now: datetime | None = None) -> bool:
    parsed = parse_evidence_timestamp(value)
    if parsed is None:
        return False
    current_time = now or datetime.now(timezone.utc)
    return parsed <= current_time


def normalized_evidence_ref(item: Any) -> tuple[str | dict[str, str] | None, list[str]]:
    if isinstance(item, str):
        item_text = item.strip()
        if not item_text or "REPLACE_" in item_text:
            return None, ["publicEvidenceRefs"]
        if evidence_ref_marker_hits(item_text):
            return None, ["publicEvidenceRefsForbiddenMarkers"]
        return item_text, []

    if not isinstance(item, dict):
        return None, ["publicEvidenceRefs"]

    if evidence_ref_marker_hits(item):
        return None, ["publicEvidenceRefsForbiddenMarkers"]

    item_text = json.dumps(item, ensure_ascii=False)
    if "REPLACE_" in item_text:
        return None, ["publicEvidenceRefs"]

    label = item.get("label")
    evidence_type = item.get("type")
    if not non_empty_string(label) or not non_empty_string(evidence_type):
        return None, ["publicEvidenceRefs"]
    evidence_type = evidence_type.strip()
    if evidence_type not in ALLOWED_EVIDENCE_REF_TYPES:
        return None, ["publicEvidenceRefs"]

    normalized = {
        "label": label.strip(),
        "type": evidence_type,
    }
    for field in EVIDENCE_REF_OPTIONAL_FIELDS:
        value = item.get(field)
        if non_empty_string(value):
            if field == "url" and not is_public_https_url(value):
                return None, ["publicEvidenceRefsUrl"]
            if field == "capturedAt" and not is_valid_evidence_timestamp(value):
                return None, ["publicEvidenceRefsCapturedAt"]
            normalized[field] = value.strip()

    if not any(field in normalized for field in EVIDENCE_REF_PAYLOAD_FIELDS):
        return None, ["publicEvidenceRefs"]

    return normalized, []


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
        cleaned_refs: list[str | dict[str, str]] = []
        for item in evidence_refs:
            normalized_ref, ref_reasons = normalized_evidence_ref(item)
            if ref_reasons:
                reasons.extend(ref_reasons)
                continue
            if normalized_ref is not None:
                cleaned_refs.append(normalized_ref)
        evidence_refs = cleaned_refs
        if not evidence_refs:
            reasons.append("publicEvidenceRefs")

    if not is_valid_evidence_timestamp(submission.get("evidenceCapturedAt")):
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


def remediation_hints(
    flavor: str,
    blockers: list[str],
    expected: dict[str, dict[str, Any]],
) -> list[str]:
    expected_entry = expected.get(flavor)
    target_path = f"build/store-submission-evidence/flavors/{flavor}.input.json"
    starter_path = f"build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json"
    if not expected_entry:
        return [f"Use one of the generated flavor ids: {', '.join(expected)}."]

    channel = str(expected_entry["primaryChannel"])
    allowed_statuses = ", ".join(ALLOWED_STATUSES_BY_CHANNEL[channel])
    hints: list[str] = []
    for blocker in blockers:
        if blocker in {"input-evidence-missing", "missing-submission"}:
            hints.append(
                f"Copy {starter_path} to {target_path}, replace placeholders with tenant-owned public store status, then rerun source-dir strict import.",
            )
        elif blocker.startswith("invalid-json:"):
            hints.append(f"Fix JSON syntax in the tenant evidence input, then rerun import. Parser detail: {blocker.removeprefix('invalid-json:')}")
        elif blocker.endswith(":invalid-json") or ":invalid-json:" in blocker:
            hints.append(f"Fix JSON syntax in {target_path} or the reported per-flavor input file, then rerun import.")
        elif blocker.endswith(":submission-missing") or blocker == "submission-not-object":
            hints.append(f"Ensure {target_path} contains either one submission object or a submissions array with one object for {flavor}.")
        elif blocker == "submissionStatus":
            hints.append(f"Set submissionStatus to one allowed {channel} value: {allowed_statuses}.")
        elif blocker in required_flags(channel):
            hints.append(f"Set {blocker}=true only after public tenant store or distribution evidence proves that checklist item.")
        elif blocker == "publicEvidenceRefs":
            hints.append("Add at least one public evidence ref such as TestFlight build number, Play internal track, signed package checksum, legal URL, support URL, or store product id.")
        elif blocker == "publicEvidenceRefsUrl":
            hints.append("Replace evidence ref URLs with public HTTPS URLs; localhost, file URLs, plain HTTP, loopback, private IP ranges, and .local hosts are rejected.")
        elif blocker in {"evidenceCapturedAt", "publicEvidenceRefsCapturedAt"}:
            hints.append("Use a timezone-aware ISO-8601 timestamp that is not in the future, for example 2026-06-14T00:00:00Z.")
        elif blocker == "publicEvidenceRefsForbiddenMarkers":
            hints.append("Remove signing or credential filenames from evidence refs; use public store or distribution metadata instead.")
        elif blocker in {"applicationId", "appName"}:
            hints.append(f"Fill the tenant-owned {blocker} value for this app flavor before importing evidence.")
        elif blocker in {"storeComplianceMode", "primaryChannel", "templateApplicationId", "templateAppName"}:
            hints.append(f"Keep {blocker} aligned with the generated handoff for {flavor}; regenerate the starter package if template metadata changed.")
        elif blocker == "duplicate-flavor":
            hints.append(f"Keep exactly one submission for {flavor} in the combined import source.")
        else:
            hints.append(f"Review and correct blocker `{blocker}` in {target_path}.")
    return hints


def blocked_flavor_entry(
    flavor: str,
    blockers: list[str],
    expected: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "flavor": flavor,
        "blockers": blockers,
        "remediationHints": remediation_hints(flavor, blockers, expected),
    }


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
            blocked_flavor_entry(flavor, [reason], expected)
            for flavor in expected
        ],
        "forbiddenMarkerHits": [],
        "secretBoundary": "Public tenant store-submission evidence only. Do not include signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or signing/credential file references.",
    }


def import_evidence(
    source: Path,
    output: Path,
    template: Path,
    guide: Path | None = None,
    source_dir: Path | None = None,
) -> dict[str, Any]:
    expected = expected_entries()
    guide_path = guide or template.with_name("store-submission-evidence.guide.md")
    write_template(template, expected)
    write_guide(guide_path, expected)

    source_mode = "combined"
    source_input_records: list[dict[str, str]] = []
    per_flavor_dir = source_dir or source_dir_for(source)
    should_try_per_flavor = source_dir is not None or not source.exists()
    if should_try_per_flavor:
        per_flavor_raw, per_flavor_errors, per_flavor_input_records = load_per_flavor_sources(
            per_flavor_dir,
            expected,
        )
        if per_flavor_errors:
            report = blocked_report(
                source=source,
                output=output,
                template=template,
                guide=guide_path,
                expected=expected,
                reason=per_flavor_errors[0],
            )
            report["result"] = "failed"
            report["sourceMode"] = "per_flavor"
            report["sourceInputPaths"] = per_flavor_input_records
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return report
        if per_flavor_raw is not None:
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps(per_flavor_raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            source_mode = "per_flavor"
            source_input_records = per_flavor_input_records
        elif not source.exists():
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
            blocked_flavors.append(blocked_flavor_entry("unknown", ["submission-not-object"], expected))
            continue
        normalized, reasons = validate_submission(item, expected)
        normalized_submissions.append(normalized)
        flavor = str(normalized.get("flavor"))
        if flavor in seen:
            reasons.append("duplicate-flavor")
        seen.add(flavor)
        if reasons:
            blocked_flavors.append(blocked_flavor_entry(flavor, sorted(set(reasons)), expected))

    missing = [flavor for flavor in expected if flavor not in seen]
    blocked_flavors.extend(
        blocked_flavor_entry(flavor, ["missing-submission"], expected)
        for flavor in missing
    )
    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "passed" if not missing and not blocked_flavors and not raw_marker_hits else "blocked",
        "sourceMode": source_mode,
        "sourcePath": rel(source),
        "sourceSha256": sha256_file(source),
        "sourceInputPaths": source_input_records,
        "templatePath": rel(template),
        "templateSha256": sha256_file(template),
        "guidePath": rel(guide_path),
        "guideSha256": sha256_file(guide_path),
        "requiredFlavors": list(expected),
        "submissions": normalized_submissions,
        "missingFlavors": missing,
        "blockedFlavors": blocked_flavors,
        "forbiddenMarkerHits": raw_marker_hits,
        "secretBoundary": "Public tenant store-submission evidence only. No signing material, provider credentials, OAuth secrets, payment secrets, webhook secrets, Cloudflare tokens, bank credentials, crypto keys, or signing/credential file references are stored in this report.",
    }
    if raw_marker_hits:
        report["result"] = "failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-dir", type=Path)
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
        args.source_dir.resolve() if args.source_dir else None,
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
