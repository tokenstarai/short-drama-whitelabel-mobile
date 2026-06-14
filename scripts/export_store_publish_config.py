#!/usr/bin/env python3
"""Export public tenant store-publish configuration templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "store-publish-config"
STORE_HANDOFF = ROOT / "build" / "release-handoff" / "mobile-store-handoff.json"
STORE_ASSETS = ROOT / "build" / "store-assets" / "store-assets-manifest.json"
STORE_SIGNING = ROOT / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"
PACKAGE_NAME = "mobile-store-publish-config"

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


def source_manifest_ref(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "present": path.exists(),
        "sha256": sha256_file(path) if path.exists() else None,
    }


def store_products(entry: dict[str, Any], provider: str) -> list[dict[str, Any]]:
    registration = entry.get("storeProductRegistration")
    if not isinstance(registration, dict):
        return []
    products: list[dict[str, Any]] = []
    for item in registration.get("registrations", []):
        if not isinstance(item, dict) or item.get("provider") != provider:
            continue
        for product in item.get("products", []):
            if not isinstance(product, dict):
                continue
            products.append({
                "packageId": product.get("packageId"),
                "storeProductId": product.get("storeProductId"),
                "title": product.get("title"),
                "coins": product.get("coins"),
                "bonusCoins": product.get("bonusCoins"),
                "totalCoins": product.get("totalCoins"),
                "amountOriginal": product.get("amountOriginal"),
                "currency": product.get("currency"),
                "tenantMayReplace": True,
            })
    return products


def distribution_channel(entry: dict[str, Any], channel: str) -> dict[str, Any]:
    distribution = entry.get("distributionChannelReadiness")
    if not isinstance(distribution, dict):
        return {}
    channels = distribution.get("channels")
    if not isinstance(channels, dict):
        return {}
    payload = channels.get(channel)
    return payload if isinstance(payload, dict) else {}


def build_flavor_config(entry: dict[str, Any]) -> dict[str, Any]:
    flavor = str(entry.get("flavor"))
    listing = ((entry.get("storeSubmission") or {}).get("listing") or {})
    data_safety = ((entry.get("storeSubmission") or {}).get("dataSafety") or {})
    payment_visibility = entry.get("paymentVisibility") or {}
    legal = entry.get("legal") or {}
    app_store = distribution_channel(entry, "appStoreTestFlight")
    google_play = distribution_channel(entry, "googlePlayInternal")
    android_direct = distribution_channel(entry, "androidDirect")
    app_store_products = store_products(entry, "iap")
    play_products = store_products(entry, "play_billing")
    callbacks = entry.get("authCallbackRegistration") or {}
    native = entry.get("nativeCapabilityRegistration") or {}
    return {
        "schemaVersion": 1,
        "flavor": flavor,
        "styleTemplate": entry.get("styleTemplate"),
        "storeComplianceMode": entry.get("storeComplianceMode"),
        "appIdentity": {
            "displayName": entry.get("appName"),
            "bundleId": entry.get("bundleId"),
            "applicationId": entry.get("applicationId"),
            "deepLinkScheme": entry.get("deepLinkScheme"),
            "tenantMayReplaceIds": True,
        },
        "legalUrls": {
            "supportUrl": legal.get("customerServiceUrl") or listing.get("supportUrl"),
            "termsUrl": legal.get("termsUrl") or listing.get("termsUrl"),
            "privacyUrl": legal.get("privacyUrl") or listing.get("privacyUrl"),
            "tenantMustOwnFinalUrls": True,
        },
        "oauthCallbacks": {
            "callbackUris": callbacks.get("callbackUris", []),
            "requiredQueryParams": callbacks.get("requiredQueryParams", ["code"]),
            "tenantRegistersProviderApps": bool(entry.get("authProviders")),
            "credentialsStayServerSide": True,
        },
        "appStoreConnect": {
            "enabled": entry.get("storeComplianceMode") == "app_store",
            "bundleId": entry.get("bundleId"),
            "xcodeScheme": (native.get("ios") or {}).get("xcodeScheme") or flavor,
            "primaryLocale": listing.get("defaultLocale"),
            "localizedListings": (entry.get("storeSubmission") or {}).get("localizedListings", []),
            "testFlight": {
                "expectedUnsignedBuild": app_store.get("artifactPath"),
                "requiresTenantSigning": bool(app_store.get("requiresTenantSigning")),
                "localStatus": app_store.get("status"),
            },
            "inAppPurchases": app_store_products,
            "privacyManifest": (native.get("ios") or {}).get("privacyManifest"),
            "requiredCapabilities": (native.get("ios") or {}).get("requiredCapabilities", []),
            "tenantMustFill": [
                "Apple team id",
                "final bundle id if changed",
                "App Store Connect SKU",
                "review contact",
                "age rating",
                "privacy answers",
                "IAP product records",
            ],
        },
        "googlePlayConsole": {
            "enabled": entry.get("storeComplianceMode") in {"play_store", "regional_user_choice"},
            "packageName": entry.get("applicationId"),
            "releaseTrack": "internal",
            "releaseAppBundle": google_play.get("artifactPath"),
            "requiresTenantSigning": bool(google_play.get("requiresTenantSigning")),
            "playBillingProducts": play_products,
            "dataSafetyStarter": data_safety,
            "paymentPolicy": ((entry.get("storeReviewDeclarations") or {}).get("googlePlay") or {}).get("digitalContentPaymentPolicy"),
            "tenantMustFill": [
                "Play Console app record",
                "upload key setup",
                "data safety answers",
                "content rating",
                "target audience",
                "payments declarations",
                "OAuth SHA fingerprints",
            ],
        },
        "androidDirect": {
            "enabled": entry.get("storeComplianceMode") == "android_direct",
            "releaseApk": (android_direct.get("artifactPaths") or {}).get("apk"),
            "releaseAppBundle": (android_direct.get("artifactPaths") or {}).get("appbundle"),
            "requiresTenantSigning": bool(android_direct.get("requiresTenantSigning")),
            "externalPaymentProviders": payment_visibility.get("appVisibleProviders", []),
            "tenantMustFill": [
                "direct distribution host",
                "refund policy URL",
                "payment dispute process",
                "regional payment compliance notes",
                "signed APK or AAB location",
            ],
        },
        "serverSideCredentialBoundary": {
            "tenantEdgeStoresPaymentProviderCredentials": True,
            "tenantEdgeStoresOAuthProviderCredentials": True,
            "mobileClientStoresProviderCredentials": False,
            "mobileClientStoresSigningMaterial": False,
        },
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


def build_handoff(output_dir: Path) -> dict[str, Any]:
    store_handoff = read_json(STORE_HANDOFF)
    if store_handoff is None:
        raise SystemExit(f"Missing store handoff manifest: {STORE_HANDOFF.relative_to(ROOT)}")
    if output_dir.exists():
        for path in sorted(output_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    output_dir.mkdir(parents=True, exist_ok=True)

    flavors: list[dict[str, Any]] = []
    for entry in store_handoff.get("flavors", []):
        if not isinstance(entry, dict):
            continue
        config = build_flavor_config(entry)
        flavor = str(config["flavor"])
        path = output_dir / flavor / "publish-config.template.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        flavors.append({
            "flavor": flavor,
            "appName": config["appIdentity"]["displayName"],
            "applicationId": config["appIdentity"]["applicationId"],
            "bundleId": config["appIdentity"]["bundleId"],
            "storeComplianceMode": config["storeComplianceMode"],
            "templatePath": str(path.relative_to(output_dir)),
            "templateSha256": sha256_file(path),
            "enabledStores": [
                name
                for name, enabled in {
                    "appStoreConnect": config["appStoreConnect"]["enabled"],
                    "googlePlayConsole": config["googlePlayConsole"]["enabled"],
                    "androidDirect": config["androidDirect"]["enabled"],
                }.items()
                if enabled
            ],
            "containsSecrets": False,
            "tenantMustFillCount": (
                len(config["appStoreConnect"]["tenantMustFill"])
                + len(config["googlePlayConsole"]["tenantMustFill"])
                + len(config["androidDirect"]["tenantMustFill"])
            ),
        })

    manifest = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "packageType": "mobile_store_publish_config",
        "sourceManifests": {
            "storeHandoff": source_manifest_ref(STORE_HANDOFF),
            "storeAssets": source_manifest_ref(STORE_ASSETS),
            "storeSigningHandoff": source_manifest_ref(STORE_SIGNING),
        },
        "flavors": flavors,
        "tenantWorkflow": [
            "Choose one flavor and copy the matching publish-config.template.json into the tenant release workspace.",
            "Replace public app identity, legal URLs, screenshots, store product ids, app listing fields, and review answers.",
            "Keep signing files, provider credentials, webhooks, payment keys, and service-account files outside Git and outside the Flutter client.",
            "Run a store-compliance build mode check before exposing payment providers in the app.",
            "Submit through the tenant-owned Apple, Google Play, or direct-distribution account only after signed builds are produced.",
        ],
        "publicBoundary": "Public store publish configuration templates only; no certificates, passwords, provider credentials, webhook credentials, or service-account files are included.",
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    manifest_path = output_dir / "store-publish-config-manifest.json"
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
        help="directory for store publish configuration metadata",
    )
    args = parser.parse_args()
    manifest = build_handoff(args.output_dir.resolve())
    print(f"Wrote store publish config manifest: {manifest['manifestPath']}")
    print(f"Wrote store publish config package: {manifest['packagePath']}")
    print(f"Flavors: {len(manifest['flavors'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
