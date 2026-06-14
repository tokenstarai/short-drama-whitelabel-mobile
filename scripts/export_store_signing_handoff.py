#!/usr/bin/env python3
"""Export public tenant store-signing handoff metadata and templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-signing-handoff"
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"
IOS_CI_HANDOFF = ROOT / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
RELEASE_MANIFEST = ROOT / "build" / "release-manifests" / "mobile-artifacts.json"
PACKAGE_NAME = "mobile-store-signing-handoff"

DISALLOWED_VALUE_MARKERS = [
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
    return [marker for marker in DISALLOWED_VALUE_MARKERS if marker in text]


def release_artifacts_by_flavor(release_manifest: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    by_flavor: dict[str, dict[str, str]] = {}
    for artifact in (release_manifest or {}).get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        if artifact.get("platform") != "android" or artifact.get("mode") != "release":
            continue
        flavor = str(artifact.get("flavor"))
        package_type = str(artifact.get("packageType"))
        if flavor and package_type in {"apk", "appbundle"}:
            by_flavor.setdefault(flavor, {})[package_type] = str(artifact.get("path"))
    return by_flavor


def ios_ci_by_flavor(ios_ci_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("flavor")): entry
        for entry in (ios_ci_manifest or {}).get("flavors", [])
        if isinstance(entry, dict)
    }


def write_ios_export_options(output_dir: Path, flavor: str, bundle_id: str) -> dict[str, Any]:
    payload = {
        "method": "app-store-connect",
        "destination": "export",
        "signingStyle": "manual",
        "teamID": "TENANT_APPLE_TEAM_ID",
        "provisioningProfiles": {
            bundle_id: f"TENANT_{flavor.upper()}_APPSTORE_PROFILE_NAME",
        },
        "stripSwiftSymbols": True,
        "compileBitcode": False,
        "uploadBitcode": False,
    }
    path = output_dir / flavor / "ExportOptions.plist.template"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as target:
        plistlib.dump(payload, target, sort_keys=True)
    return {
        "path": str(path.relative_to(output_dir)),
        "sha256": sha256_file(path),
        "bundleId": bundle_id,
        "method": payload["method"],
        "signingStyle": payload["signingStyle"],
        "teamIdPlaceholder": payload["teamID"],
        "profilePlaceholder": payload["provisioningProfiles"][bundle_id],
    }


def write_android_signing_template(output_dir: Path, flavor: str, application_id: str) -> dict[str, Any]:
    text = "\n".join([
        "# Template only. Keep resolved values outside Git.",
        f"applicationId={application_id}",
        "storeFile=/absolute/path/to/tenant-upload-keystore.jks",
        "storePassword=READ_FROM_CI_OR_LOCAL_KEYCHAIN",
        "keyAlias=tenant_upload_alias",
        "keyPassword=READ_FROM_CI_OR_LOCAL_KEYCHAIN",
        "",
    ])
    path = output_dir / flavor / "android-signing.properties.template"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path.relative_to(output_dir)),
        "sha256": sha256_file(path),
        "applicationId": application_id,
        "expectedAab": f"build/app/outputs/bundle/{flavor}Release/app-{flavor}-release.aab",
        "signingStore": "tenant-owned upload keystore outside Git",
    }


def flavor_handoff(
    output_dir: Path,
    entry: dict[str, Any],
    android_artifacts: dict[str, dict[str, str]],
    ios_ci: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    flavor = str(entry["flavor"])
    application_id = str(entry.get("applicationId"))
    bundle_id = str(entry.get("bundleId") or application_id)
    ios_template = write_ios_export_options(output_dir, flavor, bundle_id)
    android_template = write_android_signing_template(output_dir, flavor, application_id)
    ci_entry = ios_ci.get(flavor, {})
    artifact_paths = android_artifacts.get(flavor, {})
    payload = {
        "flavor": flavor,
        "appName": entry.get("appName"),
        "applicationId": application_id,
        "bundleId": bundle_id,
        "styleTemplate": entry.get("styleTemplate"),
        "storeComplianceMode": entry.get("storeComplianceMode"),
        "ios": {
            "scheme": ci_entry.get("scheme") or flavor,
            "xcodeScheme": ci_entry.get("xcodeScheme") or f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{flavor}.xcscheme",
            "xcconfig": ci_entry.get("xcconfig") or f"ios/Flutter/{flavor.capitalize()}.xcconfig",
            "unsignedArtifactName": (ci_entry.get("ci") or {}).get("artifactName", f"mobile-{flavor}-ios-unsigned"),
            "unsignedArtifactPath": (ci_entry.get("ci") or {}).get("artifactPath", "mobile/build/ios/iphoneos/Runner.app"),
            "exportOptionsTemplate": ios_template,
            "archiveCommand": f"flutter build ipa --flavor {flavor} --release --dart-define=APP_FLAVOR={flavor} --export-options-plist build/store-signing-handoff/{flavor}/ExportOptions.plist",
            "tenantRequiredActions": [
                "Create or select the Apple developer team.",
                "Replace the template bundle id if the tenant uses a different final id.",
                "Enable Sign in with Apple on the App ID when Google or Facebook login is enabled.",
                "Create the App Store distribution certificate and App Store provisioning profile.",
                "Fill the export options template with the tenant team id and provisioning profile name outside Git.",
                "Create App Store Connect metadata, IAP products, privacy answers, screenshots, support URL, terms URL, and privacy URL.",
                "Upload through Transporter, Xcode Organizer, or App Store Connect after a signed archive succeeds.",
            ],
        },
        "android": {
            "releaseApk": artifact_paths.get("apk"),
            "releaseAppBundle": artifact_paths.get("appbundle"),
            "signingTemplate": android_template,
            "playUploadCommand": f"./scripts/build_flavor.sh {flavor} android release appbundle",
            "directDistributionCommand": f"./scripts/build_flavor.sh {flavor} android release apk",
            "tenantRequiredActions": [
                "Replace template debug signing with tenant-owned upload signing outside Git.",
                "Enable Play App Signing before uploading the release AAB to Google Play.",
                "Register OAuth SHA fingerprints and package name in tenant-owned provider consoles.",
                "Complete Play Console data safety, app access, content rating, target audience, and payments policy declarations.",
                "For Android direct distribution, sign the APK/AAB with tenant-owned material and publish legal/refund/support URLs.",
            ],
        },
        "secretBoundary": {
            "containsSigningMaterial": False,
            "containsAppleTeamId": False,
            "containsProvisioningProfile": False,
            "containsAndroidKeystore": False,
            "containsProviderCredentials": False,
            "storageRule": "Resolved signing files, passwords, profiles, certificates, and provider credentials stay in tenant-owned accounts or CI secrets outside Git.",
        },
    }
    path = output_dir / flavor / "store-signing.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload["handoffPath"] = str(path.relative_to(output_dir))
    payload["handoffSha256"] = sha256_file(path)
    return payload


def write_zip(output_dir: Path, zip_path: Path) -> None:
    files = sorted(path for path in output_dir.rglob("*") if path.is_file() and path != zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            rel_path = file_path.relative_to(output_dir)
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{rel_path.as_posix()}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file_path.read_bytes())


def build_handoff(output_dir: Path) -> dict[str, Any]:
    store_handoff = read_json(STORE_HANDOFF)
    if store_handoff is None:
        raise SystemExit(f"Missing store handoff manifest: {STORE_HANDOFF.relative_to(ROOT)}")
    release_manifest = read_json(RELEASE_MANIFEST)
    ios_ci_manifest = read_json(IOS_CI_HANDOFF)
    if output_dir.exists():
        for path in sorted(output_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)

    android_artifacts = release_artifacts_by_flavor(release_manifest)
    ios_ci = ios_ci_by_flavor(ios_ci_manifest)
    flavors = [
        flavor_handoff(output_dir, entry, android_artifacts, ios_ci)
        for entry in store_handoff.get("flavors", [])
        if isinstance(entry, dict)
    ]
    manifest = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_store_signing_handoff",
        "sourceManifests": {
            "storeHandoff": str(STORE_HANDOFF.relative_to(ROOT)),
            "iosCiHandoff": str(IOS_CI_HANDOFF.relative_to(ROOT)) if IOS_CI_HANDOFF.exists() else None,
            "releaseArtifacts": str(RELEASE_MANIFEST.relative_to(ROOT)) if RELEASE_MANIFEST.exists() else None,
        },
        "flavors": flavors,
        "tenantWorkflow": [
            "Choose the tenant flavor and final application id or bundle id.",
            "Replace placeholder icons, screenshots, legal URLs, OAuth callback URLs, and store product ids.",
            "Keep Apple certificates, provisioning profiles, Android upload keystores, passwords, and provider credentials outside Git.",
            "Run unsigned CI/local builds first, then apply tenant signing in a protected tenant machine or CI environment.",
            "Upload the signed iOS archive to TestFlight/App Store Connect or the signed Android AAB/APK to Google Play/direct distribution.",
        ],
        "publicBoundary": "Signing checklist and placeholder templates only. No certificates, profiles, keystores, passwords, Apple team ids, provider credentials, or Cloudflare credentials are included.",
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    manifest_path = output_dir / "store-signing-handoff-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    zip_path = output_dir / f"{PACKAGE_NAME}.zip"
    write_zip(output_dir, zip_path)
    manifest["manifestPath"] = str(manifest_path.relative_to(ROOT))
    manifest["manifestSha256"] = sha256_file(manifest_path)
    manifest["packagePath"] = str(zip_path.relative_to(ROOT))
    manifest["packageSha256"] = sha256_file(zip_path)
    manifest["packageSizeBytes"] = zip_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for store signing handoff metadata",
    )
    args = parser.parse_args()
    manifest = build_handoff(args.output_dir.resolve())
    print(f"Wrote store signing handoff manifest: {manifest['manifestPath']}")
    print(f"Wrote store signing handoff package: {manifest['packagePath']}")
    print(f"Flavors: {len(manifest['flavors'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
