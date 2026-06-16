#!/usr/bin/env python3
"""Export a no-secret external account and signing checklist for tenant app release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import import_store_submission_evidence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "external-account-handoff"
PACKAGE_NAME = "mobile-external-account-handoff"
PACKAGE_FILE = f"{PACKAGE_NAME}.zip"

NO_CREDENTIAL_BOUNDARY = (
    "Public account status, public store links, public product ids, build numbers, "
    "package names, callback URLs, and checksums only. Signing files, provider "
    "credentials, webhook signing values, bank credentials, wallet keys, payment "
    "API keys, OAuth confidential values, Cloudflare tokens, and local credential "
    "file names stay outside Flutter, GitHub, and tenant portal pages."
)

FORBIDDEN_MARKERS = [
    *import_store_submission_evidence.FORBIDDEN_MARKERS,
    ".p12",
    ".p8",
    ".mobileprovision",
    ".jks",
    ".keystore",
    "upload-keystore",
    "authkey",
]

CHANNEL_SECTION_IDS = {
    "app_store_testflight": ["apple_developer", "oauth_social_login", "consumer_payments", "legal_review"],
    "google_play_internal": ["google_play", "oauth_social_login", "consumer_payments", "legal_review"],
    "android_direct": ["android_direct", "oauth_social_login", "consumer_payments", "legal_review"],
}


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
    return sorted({marker.lower() for marker in FORBIDDEN_MARKERS if marker.lower() in text})


def section_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "apple_developer",
            "title": "Apple Developer and App Store Connect",
            "requiredForChannels": ["app_store_testflight"],
            "tenantPublicFields": [
                "Apple team id",
                "App Store Connect app record id or public status reference",
                "Bundle id",
                "SKU",
                "TestFlight build number and processing status",
                "In-app purchase product ids and price tiers",
                "Enabled capabilities status for Sign in with Apple and associated domains",
            ],
            "acceptedPublicEvidence": [
                "App Store Connect app status screenshot reference or public metadata export",
                "TestFlight build number and uploaded build version",
                "IAP product id list without credentials",
                "Capability status summary without signing files",
            ],
            "serverSideDestination": "Apple account and CI signing environment owned by the tenant; only public status is mirrored into handoff JSON.",
            "forbiddenEvidence": [
                "Apple certificate files",
                "provisioning profile files",
                "App Store API key files",
                "signing password values",
            ],
        },
        {
            "id": "google_play",
            "title": "Google Play Console",
            "requiredForChannels": ["google_play_internal"],
            "tenantPublicFields": [
                "Developer account display name",
                "Package name",
                "Play Console app record status",
                "Play App Signing status",
                "Internal testing track version code and rollout status",
                "Play Billing product ids and price tiers",
                "OAuth SHA-1/SHA-256 fingerprint summaries",
            ],
            "acceptedPublicEvidence": [
                "Play internal testing track status reference",
                "Version code and release name",
                "Play Billing product id list without credentials",
                "Data Safety and review contact completion status",
            ],
            "serverSideDestination": "Google Play account and CI signing environment owned by the tenant; service credentials remain outside this repository.",
            "forbiddenEvidence": [
                "upload signing key files",
                "service account JSON files",
                "keystore passwords",
                "Play API credential values",
            ],
        },
        {
            "id": "android_direct",
            "title": "Android Direct Distribution",
            "requiredForChannels": ["android_direct"],
            "tenantPublicFields": [
                "Signed APK or AAB path published by the tenant",
                "Package name",
                "Version name and version code",
                "Public SHA-256 checksum",
                "Distribution URL",
                "Update, refund, support, privacy, and terms URLs",
            ],
            "acceptedPublicEvidence": [
                "Public HTTPS distribution URL",
                "Signed package checksum",
                "Version and package metadata",
                "Published policy URLs",
            ],
            "serverSideDestination": "Tenant-owned direct distribution channel; signing assets stay outside Git and Flutter.",
            "forbiddenEvidence": [
                "Android signing key files",
                "signing property files",
                "signing passwords",
                "private distribution credentials",
            ],
        },
        {
            "id": "oauth_social_login",
            "title": "OAuth and Social Login",
            "requiredForChannels": ["app_store_testflight", "google_play_internal", "android_direct"],
            "tenantPublicFields": [
                "Enabled provider list",
                "Public app id or public client id",
                "Deep link scheme",
                "Callback URL list",
                "Provider review status",
            ],
            "acceptedPublicEvidence": [
                "Provider app id without confidential values",
                "Registered callback URL list",
                "Sign in with Apple enabled status when required",
                "Provider review or production-mode status",
            ],
            "serverSideDestination": "Tenant Edge/API Worker server environment stores confidential provider values; Flutter receives only enabled provider capabilities.",
            "forbiddenEvidence": [
                "OAuth confidential values",
                "provider private key material",
                "token exchange credentials",
                "raw access tokens",
            ],
        },
        {
            "id": "consumer_payments",
            "title": "Consumer Payments",
            "requiredForChannels": ["app_store_testflight", "google_play_internal", "android_direct"],
            "tenantPublicFields": [
                "Enabled provider list by platform, country, and currency",
                "Store product ids or public price ids",
                "Payment review status",
                "Webhook endpoint public route",
                "Offline payment instruction URL when applicable",
            ],
            "acceptedPublicEvidence": [
                "Store product id and price tier list",
                "Stripe or PayPal public product/price id references",
                "Bank or wallet instruction page URL",
                "Crypto receiving policy URL without wallet keys",
                "Webhook endpoint route name without signing values",
            ],
            "serverSideDestination": "Tenant Edge/API Worker server environment stores payment credentials, webhook signing values, bank configuration, and wallet custody configuration.",
            "forbiddenEvidence": [
                "payment provider credential values",
                "webhook signing values",
                "bank account login credentials",
                "wallet seed or custody keys",
            ],
        },
        {
            "id": "legal_review",
            "title": "Legal, Support, and Review",
            "requiredForChannels": ["app_store_testflight", "google_play_internal", "android_direct"],
            "tenantPublicFields": [
                "Privacy policy URL",
                "Terms URL",
                "Support URL or email",
                "Account deletion URL or in-app flow proof",
                "Store review contact",
                "Age rating and content declaration status",
            ],
            "acceptedPublicEvidence": [
                "Public legal URLs",
                "Support contact route",
                "Account deletion flow status",
                "Store questionnaire completion status",
                "Review notes without credential values",
            ],
            "serverSideDestination": "Tenant portal stores public links and statuses; private reviewer credentials are not collected.",
            "forbiddenEvidence": [
                "reviewer login password values",
                "identity documents",
                "private legal correspondence",
                "unredacted financial documents",
            ],
        },
    ]


def per_flavor_checklist(expected: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sections = {section["id"]: section for section in section_definitions()}
    for flavor, entry in expected.items():
        channel = str(entry["primaryChannel"])
        section_ids = CHANNEL_SECTION_IDS[channel]
        rows.append(
            {
                "flavor": flavor,
                "appName": entry["appName"],
                "applicationId": entry["applicationId"],
                "storeComplianceMode": entry["storeComplianceMode"],
                "primaryChannel": channel,
                "tenantEvidenceInputPath": f"build/store-submission-evidence/flavors/{flavor}.input.json",
                "requiredSections": section_ids,
                "requiredSectionTitles": [sections[section_id]["title"] for section_id in section_ids],
                "storeSubmissionRequiredFlags": import_store_submission_evidence.required_flags(channel),
                "allowedSubmissionStatuses": import_store_submission_evidence.ALLOWED_STATUSES_BY_CHANNEL[channel],
                "nextAction": (
                    f"Fill public account, signing-status, OAuth, payment, and legal fields for {flavor}; "
                    "then rerun store-submission preflight before strict import."
                ),
            },
        )
    return rows


def markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Mobile External Account Handoff",
        "",
        "This checklist is the public, no-secret bridge between tenant-owned store accounts and the Flutter white-label app release.",
        "",
        f"- Package type: `{manifest['packageType']}`",
        f"- Generated at: `{manifest['generatedAt']}`",
        f"- Tenant portal entry: `{manifest['tenantPortalEntry']}`",
        f"- Strict import command: `{manifest['strictImportCommand']}`",
        "",
        "## No-Credential Boundary",
        "",
        manifest["noCredentialBoundary"],
        "",
        "## Required Sections",
        "",
    ]
    for section in manifest["sections"]:
        lines.extend(
            [
                f"### {section['title']}",
                "",
                f"- Section id: `{section['id']}`",
                f"- Required for channels: `{', '.join(section['requiredForChannels'])}`",
                f"- Server-side destination: {section['serverSideDestination']}",
                "- Tenant public fields:",
                *[f"  - {field}" for field in section["tenantPublicFields"]],
                "- Accepted public evidence:",
                *[f"  - {item}" for item in section["acceptedPublicEvidence"]],
                "- Forbidden evidence:",
                *[f"  - {item}" for item in section["forbiddenEvidence"]],
                "",
            ],
        )
    lines.extend(
        [
            "## Per-Flavor Checklist",
            "",
            "| Flavor | Channel | Input path | Required sections | Next action |",
            "| --- | --- | --- | --- | --- |",
        ],
    )
    for row in manifest["flavors"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["flavor"]),
                    str(row["primaryChannel"]),
                    f"`{row['tenantEvidenceInputPath']}`",
                    ", ".join(row["requiredSections"]),
                    str(row["nextAction"]),
                ],
            )
            + " |",
        )
    lines.extend(
        [
            "",
            "## Where Values Go",
            "",
            "- Tenant portal: public status, public links, public product ids, package names, build numbers, and checksums.",
            "- Tenant Edge/API Worker server environment: OAuth confidential values, payment credentials, webhook signing values, and wallet/bank configuration.",
            "- Flutter client: public `/config` capabilities only; no tenant, signing, OAuth, payment, Cloudflare, bank, or wallet credentials.",
            "- Store-submission evidence input: public proof rows under `build/store-submission-evidence/flavors/<flavor>.input.json`.",
            "",
        ],
    )
    return "\n".join(lines)


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(path for path in output_dir.rglob("*") if path.is_file() and path != zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            relative = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def export_handoff(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    output = (output_dir or DEFAULT_OUTPUT_DIR).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    expected = import_store_submission_evidence.expected_entries()
    manifest_path = output / "mobile-external-account-handoff.json"
    markdown_path = output / "mobile-external-account-handoff.md"
    package_path = output / PACKAGE_FILE
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "packageType": "mobile_external_account_handoff",
        "generatedAt": utc_now(),
        "tenantPortalEntry": "Tenant Portal > App 模板 > 外部账号与签名资料接入入口",
        "strictImportCommand": (
            "cd mobile && ./scripts/import_store_submission_evidence.py "
            "--source-dir build/store-submission-evidence/flavors --strict"
        ),
        "storeSubmissionInputDirectory": "build/store-submission-evidence/flavors",
        "noCredentialBoundary": NO_CREDENTIAL_BOUNDARY,
        "sections": section_definitions(),
        "flavors": per_flavor_checklist(expected),
        "serverSideSecretDestinations": [
            "Tenant Edge/API Worker environment for OAuth confidential values",
            "Tenant Edge/API Worker environment for payment provider credentials",
            "Tenant-owned Apple, Google, or direct-distribution signing environment",
            "Tenant-owned bank, wallet, and webhook provider dashboards",
        ],
        "mobileClientBoundary": {
            "receivesPublicConfigOnly": True,
            "storesTenantCredentials": False,
            "storesSigningMaterial": False,
            "storesProviderCredentials": False,
        },
    }
    markdown_path.write_text(markdown(manifest), encoding="utf-8")
    manifest["markdownPath"] = rel(root, markdown_path)
    manifest["markdownSha256"] = sha256_file(markdown_path)
    manifest["manifestPath"] = rel(root, manifest_path)
    manifest["packagePath"] = rel(root, package_path)
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_zip(output, package_path)
    manifest["packageSha256"] = sha256_file(package_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package_path.unlink()
    write_zip(output, package_path)
    manifest["packageSha256"] = sha256_file(package_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    manifest = export_handoff(args.root.resolve(), args.output_dir.resolve())
    print(f"Wrote external account handoff manifest: {manifest['manifestPath']}")
    print(f"Wrote external account handoff guide: {manifest['markdownPath']}")
    print(f"Wrote external account handoff package: {manifest['packagePath']}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
    return 1 if manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
