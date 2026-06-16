#!/usr/bin/env python3
"""Export public GitHub Actions iOS build handoff metadata for tenants."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "ios-ci-handoff"
PACKAGE_NAME = "mobile-ios-ci-handoff"

FLAVOR_XCCONFIG = {
    "coolshow": "Coolshow.xcconfig",
    "hongguo": "Hongguo.xcconfig",
    "douyin": "Douyin.xcconfig",
    "hippo": "Hippo.xcconfig",
    "reelshort": "Reelshort.xcconfig",
}

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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required manifest: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path, base: Path = ROOT) -> str:
    return path.relative_to(base).as_posix()


def resolve_workflow_path(root: Path = ROOT) -> Path:
    candidates = [
        root.parent / ".github" / "workflows" / "mobile-flutter.yml",
        root / ".github" / "workflows" / "mobile-flutter.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def standalone_layout(root: Path = ROOT) -> bool:
    return resolve_workflow_path(root).is_relative_to(root)


def workflow_artifact_path(root: Path = ROOT) -> str:
    return "build/ios/iphoneos/Runner.app" if standalone_layout(root) else "mobile/build/ios/iphoneos/Runner.app"


def workflow_metadata(root: Path = ROOT) -> dict[str, Any]:
    workflow_path = resolve_workflow_path(root)
    if not workflow_path.exists():
        try:
            display_path = workflow_path.relative_to(root.parent)
        except ValueError:
            display_path = workflow_path
        raise SystemExit(f"Missing workflow: {display_path}")
    text = workflow_path.read_text(encoding="utf-8")
    required_markers = [
        "workflow_dispatch:",
        "ios-build:",
        "runs-on: macos-15",
        "flavor: [coolshow, hongguo, douyin, hippo, reelshort]",
        "maxim-lobanov/setup-xcode@v1",
        "xcode-version: latest-stable",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" ios debug",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" ios release",
        "actions/upload-artifact@v4",
        "mobile-${{ matrix.flavor }}-ios-unsigned",
    ]
    return {
        "path": ".github/workflows/mobile-flutter.yml",
        "sha256": sha256_file(workflow_path),
        "workflowDispatch": "workflow_dispatch:" in text,
        "iosJob": "ios-build",
        "runner": "macos-15",
        "xcodeSetupAction": "maxim-lobanov/setup-xcode@v1",
        "xcodeVersion": "latest-stable",
        "artifactPath": workflow_artifact_path(root),
        "requiredMarkersPresent": [
            marker
            for marker in required_markers
            if marker in text
        ],
        "missingRequiredMarkers": [
            marker
            for marker in required_markers
            if marker not in text
        ],
    }


def flavor_handoff(entry: dict[str, Any]) -> dict[str, Any]:
    flavor = str(entry["flavor"])
    artifact_name = f"mobile-{flavor}-ios-unsigned"
    deep_link = entry.get("authCallbackRegistration", {})
    return {
        "flavor": flavor,
        "appName": entry.get("appName"),
        "bundleId": entry.get("bundleId"),
        "applicationId": entry.get("applicationId"),
        "styleTemplate": entry.get("styleTemplate"),
        "storeComplianceMode": entry.get("storeComplianceMode"),
        "scheme": flavor,
        "xcconfig": f"ios/Flutter/{FLAVOR_XCCONFIG[flavor]}",
        "xcodeScheme": f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{flavor}.xcscheme",
        "infoPlist": "ios/Runner/Info.plist",
        "privacyManifest": "ios/Runner/PrivacyInfo.xcprivacy",
        "entitlements": "ios/Runner/Runner.entitlements",
        "appIcon": f"ios/Runner/Assets.xcassets/AppIcon-{flavor}.appiconset/Contents.json",
        "deepLinkScheme": deep_link.get("scheme") if isinstance(deep_link, dict) else None,
        "callbackUris": deep_link.get("callbackUris", []) if isinstance(deep_link, dict) else [],
        "ci": {
            "workflow": ".github/workflows/mobile-flutter.yml",
            "job": "ios-build",
            "runner": "macos-15",
            "matrixFlavor": flavor,
            "artifactName": artifact_name,
            "artifactPath": workflow_artifact_path(),
            "debugCommand": f"./scripts/build_flavor.sh {flavor} ios debug",
            "releaseCommand": f"./scripts/build_flavor.sh {flavor} ios release",
        },
        "verification": {
            "triggerCommand": "gh workflow run mobile-flutter.yml",
            "downloadCommand": "python3 scripts/download_ios_ci_artifacts.py --repo <owner/repo>",
            "downloadSpecificRunCommand": "python3 scripts/download_ios_ci_artifacts.py --repo <owner/repo> --run-id <run-id>",
            "runIdResolution": "By default the download script selects the latest successful mobile-flutter.yml workflow run; pass --run-id to import a specific run.",
            "downloadDestination": f"build/ci-ios/{flavor}",
            "legacyDownloadCommand": f"gh run download <run-id> -n {artifact_name} -D build/ci-ios/{flavor}",
            "expectedInfoPlistKeys": [
                "CFBundleIdentifier",
                "CFBundleDisplayName",
                "CFBundleURLTypes",
                "CFBundleShortVersionString",
            ],
            "completionGate": "scripts/ios_build_matrix.py all must pass on a full Xcode machine before full app completion is claimed.",
        },
        "tenantRequiredActions": [
            "Configure the final Apple developer team, bundle id, signing certificate, and provisioning profile outside Git.",
            "Enable Sign in with Apple on the tenant App ID when Google or Facebook login is enabled.",
            "Register OAuth callback URLs and URL-scheme ownership in tenant-owned provider consoles.",
            "Create App Store Connect metadata, IAP products, privacy answers, support URL, terms URL, and privacy URL.",
            "Upload a signed tenant archive or TestFlight build after the unsigned CI build passes.",
        ],
        "publicBoundary": "Unsigned iOS CI build metadata only; tenant signing material and provider credentials stay outside the Flutter repository.",
    }


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


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return [marker for marker in DISALLOWED_VALUE_MARKERS if marker in text]


def build_handoff(output_dir: Path) -> dict[str, Any]:
    store_handoff = read_json(STORE_HANDOFF)
    if output_dir.exists():
        for path in sorted(output_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)

    flavors = []
    for entry in store_handoff.get("flavors", []):
        if not isinstance(entry, dict):
            continue
        flavor = str(entry.get("flavor"))
        if flavor not in FLAVOR_XCCONFIG:
            continue
        payload = flavor_handoff(entry)
        flavor_path = output_dir / flavor / "ios-ci.json"
        flavor_path.parent.mkdir(parents=True, exist_ok=True)
        flavor_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        payload["handoffPath"] = str(flavor_path.relative_to(output_dir))
        payload["handoffSha256"] = sha256_file(flavor_path)
        flavors.append(payload)

    manifest = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_ios_ci_handoff",
        "sourceManifest": str(STORE_HANDOFF.relative_to(ROOT)),
        "workflow": workflow_metadata(),
        "flavors": flavors,
        "tenantWorkflow": [
            "Open the GitHub repository Actions tab or use GitHub CLI.",
            "Run the Mobile Flutter workflow on a macOS runner with latest stable Xcode.",
            "Confirm every ios-build matrix flavor finishes both unsigned debug and release builds.",
            "Download each mobile-<flavor>-ios-unsigned artifact and inspect Runner.app Info.plist metadata.",
            "Use tenant-owned Apple signing and App Store Connect configuration for TestFlight or App Store submission.",
        ],
        "publicBoundary": "Public CI workflow, unsigned build artifact names, native metadata paths, and tenant-owned Apple action checklist only.",
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    manifest_path = output_dir / "ios-ci-handoff-manifest.json"
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
        help="directory for iOS CI handoff metadata",
    )
    args = parser.parse_args()
    manifest = build_handoff(args.output_dir.resolve())
    print(f"Wrote iOS CI handoff manifest: {manifest['manifestPath']}")
    print(f"Wrote iOS CI handoff package: {manifest['packagePath']}")
    print(f"Flavors: {len(manifest['flavors'])}")
    if manifest["workflow"]["missingRequiredMarkers"]:
        print(f"Missing workflow markers: {', '.join(manifest['workflow']['missingRequiredMarkers'])}")
        return 1
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
