#!/usr/bin/env python3
"""Write a public tenant store-handoff manifest for the mobile template."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FLAVOR_ORDER = ["coolshow", "hongguo", "douyin", "hippo", "reelshort"]

SCREEN_IDS = [
    "01_splash",
    "02_auth",
    "03_home",
    "04_catalog",
    "05_detail",
    "06_player",
    "07_unlock",
    "08_mine_wallet_card",
]

PAYMENT_PROVIDER_ORDER = [
    "iap",
    "play_billing",
    "stripe",
    "paypal",
    "bank_transfer",
    "local_wallet",
    "crypto",
    "point_card",
]

DEFAULT_PAYMENT_PACKAGES = [
    {
        "packageId": "coins_100",
        "title": "100 coins",
        "storeProductId": "com.shortdrama.coins100",
        "coins": 100,
        "bonusCoins": 0,
        "totalCoins": 100,
        "amountOriginal": 9,
        "currency": "USD",
    },
    {
        "packageId": "coins_300",
        "title": "300 coins",
        "storeProductId": "com.shortdrama.coins300",
        "coins": 300,
        "bonusCoins": 30,
        "totalCoins": 330,
        "amountOriginal": 24,
        "currency": "USD",
    },
    {
        "packageId": "coins_700",
        "title": "700 coins",
        "storeProductId": "com.shortdrama.coins700",
        "coins": 700,
        "bonusCoins": 100,
        "totalCoins": 800,
        "amountOriginal": 49,
        "currency": "USD",
    },
]

STORE_PRODUCT_PROVIDER_METADATA = {
    "iap": {
        "store": "app_store_connect",
        "productType": "consumable",
    },
    "play_billing": {
        "store": "google_play_console",
        "productType": "inapp",
    },
}

VISIBLE_PAYMENT_PROVIDERS_BY_MODE = {
    "app_store": {"iap"},
    "play_store": {"play_billing"},
    "regional_user_choice": {
        "play_billing",
        "stripe",
        "paypal",
        "bank_transfer",
        "local_wallet",
        "point_card",
    },
    "android_direct": {
        "stripe",
        "paypal",
        "bank_transfer",
        "local_wallet",
        "crypto",
        "point_card",
    },
}

LISTING_COPY_BY_TEMPLATE = {
    "coolshow": (
        "Fast overseas short drama episodes with gold unlocks, wallet, and point cards."
    ),
    "hongguo_inspired": (
        "Short drama episodes, theater picks, and store-safe coin unlocks."
    ),
    "douyin_inspired": (
        "Vertical short drama feed with tenant-owned checkout and wallet flows."
    ),
    "hippo_inspired": (
        "Channel-led short drama theater with VIP-style viewing and wallet center."
    ),
    "reelshort_inspired": (
        "Poster-led short drama series with store-safe coin packages."
    ),
}

LOCALIZED_LISTING_COPY_BY_LANGUAGE = {
    "en": "Short drama episodes, theater picks, and store-safe coin unlocks.",
    "zh": "短剧剧场、热门剧集和合规金币解锁。",
    "th": "ซีรีส์สั้น ตอนฮิต และการปลดล็อกเหรียญที่ปลอดภัยตามร้านค้า",
    "id": "Drama pendek, pilihan teater, dan buka kunci koin yang sesuai toko.",
    "vi": "Phim ngắn nhiều tập, rạp tuyển chọn và mở khóa xu theo quy định cửa hàng.",
    "ms": "Drama pendek, pilihan teater, dan buka kunci syiling patuh kedai.",
    "fil": "Maiikling drama, piling theater, at store-safe coin unlocks.",
}

SECRET_BOUNDARY = (
    "Public tenant handoff metadata only. Flutter packages must not contain "
    "tenant HMAC credentials, OAuth credentials, payment credentials, "
    "Cloudflare tokens, Stream signing keys, webhook signing credentials, "
    "bank credentials, or crypto keys."
)

TENANT_OWNED_CHECKLIST = {
    "apple": [
        "Create or select the Apple developer team.",
        "Set the final bundle id, signing certificate, and provisioning profile.",
        "Configure Sign in with Apple when Google or Facebook sign-in is enabled.",
        "Create App Store Connect app metadata, TestFlight build, IAP products, privacy answers, support URL, terms URL, and privacy URL.",
        "Register tenant-owned OAuth callback URLs and deep-link scheme ownership.",
        "Review ios/Runner/PrivacyInfo.xcprivacy after adding native SDKs or data collection.",
    ],
    "googlePlay": [
        "Create the Google Play developer account and app record.",
        "Replace template debug signing with tenant-owned upload signing and enable Play App Signing.",
        "Configure Play Billing products or approved user-choice billing before enabling paid digital content.",
        "Register OAuth clients, SHA fingerprints, callback URLs, privacy policy, support URL, and data safety answers.",
        "Upload the release AAB built from the selected flavor.",
    ],
    "androidDirect": [
        "Choose the direct-distribution channel and region policy.",
        "Keep Stripe, PayPal, local wallet, bank transfer, crypto, and point-card provider credentials in Tenant Edge or API Worker configuration.",
        "Publish support, terms, refund, and privacy URLs before enabling external payment channels.",
        "Sign APK/AAB packages with tenant-owned signing material outside this repository.",
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def release_manifest_path(root: Path) -> Path:
    return root / "build" / "release-manifests" / "mobile-artifacts.json"


def load_release_artifacts(root: Path) -> list[dict[str, Any]]:
    path = release_manifest_path(root)
    if not path.exists():
        return []
    manifest = read_json(path)
    artifacts = manifest.get("artifacts")
    return artifacts if isinstance(artifacts, list) else []


def artifact_paths(artifacts: list[dict[str, Any]]) -> dict[str, str | None]:
    paths: dict[str, str | None] = {
        "androidReleaseApk": None,
        "androidReleaseAppBundle": None,
    }
    for artifact in artifacts:
        if artifact.get("platform") != "android" or artifact.get("mode") != "release":
            continue
        package_type = artifact.get("packageType")
        if package_type == "apk":
            paths["androidReleaseApk"] = artifact.get("path")
        elif package_type == "appbundle":
            paths["androidReleaseAppBundle"] = artifact.get("path")
    return paths


def payment_visibility(template: dict[str, Any]) -> dict[str, Any]:
    mode = str(template["storeComplianceMode"])
    configured = [
        str(provider)
        for provider in template.get("consumerPaymentProviders", [])
        if str(provider) in PAYMENT_PROVIDER_ORDER
    ]
    allowed = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(mode, set())
    visible = [
        provider
        for provider in PAYMENT_PROVIDER_ORDER
        if provider in configured and provider in allowed
    ]
    hidden = [provider for provider in configured if provider not in visible]
    return {
        "storeComplianceMode": mode,
        "configuredProviders": configured,
        "appVisibleProviders": visible,
        "hiddenByComplianceProviders": hidden,
        "externalPaymentsAllowed": mode in {"android_direct", "regional_user_choice"},
    }


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a valid PNG")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def screenshot_assets(root: Path, flavor: str) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for screen_id in SCREEN_IDS:
        relative_path = f"test/goldens/prototypes/{flavor}_{screen_id}.png"
        path = root / relative_path
        content = path.read_bytes()
        width, height = png_dimensions(path)
        assets.append(
            {
                "screen": screen_id,
                "path": relative_path,
                "viewportWidth": 390,
                "width": width,
                "height": height,
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "source": "publish_safe_prototype",
                "tenantShouldReplace": True,
            },
        )
    return assets


def locale_language(locale: str) -> str:
    return locale.replace("_", "-").split("-")[0].lower()


def localized_listings(brand: dict[str, Any], supported_locales: list[str]) -> list[dict[str, Any]]:
    default_locale = supported_locales[0] if supported_locales else "en-US"
    listings: list[dict[str, Any]] = []
    for locale in supported_locales:
        language = locale_language(locale)
        listings.append(
            {
                "locale": locale,
                "displayName": brand["appName"],
                "shortDescription": LOCALIZED_LISTING_COPY_BY_LANGUAGE.get(
                    language,
                    LOCALIZED_LISTING_COPY_BY_LANGUAGE["en"],
                ),
                "supportUrl": brand["customerServiceUrl"],
                "termsUrl": brand["termsUrl"],
                "privacyUrl": brand["privacyUrl"],
                "isDefault": locale == default_locale,
            },
        )
    return listings


def auth_callback_registration(flavor: str, template: dict[str, Any]) -> dict[str, Any]:
    scheme = deep_link_scheme(flavor)
    providers = [
        str(provider)
        for provider in template.get("authProviders", [])
        if str(provider) in {"google", "facebook", "apple"}
    ]
    return {
        "scheme": scheme,
        "host": "auth",
        "callbackUris": [
            f"{scheme}://auth/oauth/{provider}/callback"
            for provider in providers
        ],
        "requiredQueryParams": ["code"],
        "optionalQueryParams": ["state", "oauthStartId", "provider"],
        "nativeConfig": {
            "androidManifest": "android/app/src/main/AndroidManifest.xml",
            "androidSchemePlaceholder": "deepLinkScheme",
            "iosInfoPlist": "ios/Runner/Info.plist",
            "iosSchemeBuildSetting": "APP_DEEP_LINK_SCHEME",
        },
        "tenantRequiredActions": [
            "register these callback URIs in each enabled OAuth provider",
            "keep provider credentials in Tenant Edge or API Worker secrets",
            "verify callbacks return code, optional state, and oauthStartId to the app scheme",
        ],
    }


def store_product_registration(visibility: dict[str, Any]) -> dict[str, Any]:
    store_providers = [
        provider
        for provider in visibility.get("appVisibleProviders", [])
        if provider in STORE_PRODUCT_PROVIDER_METADATA
    ]
    return {
        "storeComplianceMode": visibility["storeComplianceMode"],
        "storeProviders": store_providers,
        "serverVerificationEndpoint": "/payment/store-purchases/verify",
        "tenantEdgeMayOverridePackages": True,
        "tenantShouldReplaceProductIds": True,
        "registrations": [
            {
                "provider": provider,
                "store": STORE_PRODUCT_PROVIDER_METADATA[provider]["store"],
                "productType": STORE_PRODUCT_PROVIDER_METADATA[provider]["productType"],
                "products": DEFAULT_PAYMENT_PACKAGES,
            }
            for provider in store_providers
        ],
        "tenantRequiredActions": [
            "Create matching consumable products in App Store Connect or Google Play Console before store review.",
            "Keep App Store shared secrets, Google Play service-account credentials, and receipt validation keys on Tenant Edge/API Worker only.",
            "Return final package ids and store product ids from Tenant Edge /payment/options if tenants replace the template defaults.",
        ],
    }


def native_capability_registration(
    flavor: str,
    brand: dict[str, Any],
    template: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    auth_providers = {str(provider) for provider in template.get("authProviders", [])}
    visible_payments = {
        str(provider)
        for provider in visibility.get("appVisibleProviders", [])
    }
    ios_capabilities = ["custom_url_scheme"]
    if auth_providers.intersection({"apple", "google", "facebook"}):
        ios_capabilities.append("sign_in_with_apple")
    if "iap" in visible_payments:
        ios_capabilities.append("in_app_purchase")

    android_capabilities = ["internet", "custom_url_scheme"]
    if auth_providers.intersection({"google", "facebook"}):
        android_capabilities.append("oauth_sha_fingerprints")
    if "play_billing" in visible_payments:
        android_capabilities.append("play_billing")
    if visibility.get("storeComplianceMode") == "android_direct":
        android_capabilities.append("direct_distribution_signing")

    scheme = deep_link_scheme(flavor)
    config_name = flavor.capitalize()
    return {
        "ios": {
            "bundleId": brand["bundleId"],
            "xcodeScheme": flavor,
            "xcconfig": f"ios/Flutter/{config_name}.xcconfig",
            "appIconAsset": f"ios/Runner/Assets.xcassets/AppIcon-{flavor}.appiconset",
            "urlScheme": scheme,
            "privacyManifest": "ios/Runner/PrivacyInfo.xcprivacy",
            "entitlements": "ios/Runner/Runner.entitlements",
            "requiredCapabilities": ios_capabilities,
            "tenantRequiredActions": [
                "Enable listed capabilities in the tenant Apple developer account before TestFlight or App Store submission.",
                "Attach tenant-owned signing certificates and provisioning profiles outside this repository.",
                "Update PrivacyInfo.xcprivacy if tenant SDKs collect data beyond the template defaults.",
            ],
        },
        "android": {
            "applicationId": brand["bundleId"],
            "productFlavor": flavor,
            "manifest": "android/app/src/main/AndroidManifest.xml",
            "launcherIcon": f"android/app/src/{flavor}/res/mipmap-xxxhdpi/ic_launcher.png",
            "urlScheme": scheme,
            "requiredCapabilities": android_capabilities,
            "tenantRequiredActions": [
                "Replace template debug signing with tenant-owned upload signing material outside this repository.",
                "Register OAuth SHA fingerprints for Google/Facebook providers when enabled.",
                "Complete Play Console declarations or direct-distribution compliance review for the selected store mode.",
            ],
        },
    }


def store_review_declarations(
    template: dict[str, Any],
    features: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    mode = str(visibility["storeComplianceMode"])
    auth_providers = {str(provider) for provider in template.get("authProviders", [])}
    app_visible = {
        str(provider)
        for provider in visibility.get("appVisibleProviders", [])
    }
    needs_apple = "apple" in auth_providers or bool(
        auth_providers.intersection({"google", "facebook"}),
    )
    account_deletion = bool(features.get("enableAccountDeletion"))
    external_payments = bool(visibility.get("externalPaymentsAllowed"))
    return {
        "storeComplianceMode": mode,
        "apple": {
            "submittedByDefault": mode == "app_store",
            "formName": "App Review",
            "digitalContentPaymentPolicy": (
                "in_app_purchase_only"
                if "iap" in app_visible
                else "not_enabled"
            ),
            "externalPaymentLinksInApp": mode == "regional_user_choice"
            and external_payments,
            "accountDeletionInApp": account_deletion,
            "signInWithAppleRequired": needs_apple,
            "userGeneratedContent": False,
            "privacyManifest": "ios/Runner/PrivacyInfo.xcprivacy",
            "tenantRequiredActions": [
                "Answer App Review questions using the final tenant SDKs, regions, and legal URLs.",
                "Keep any external payment copy hidden in App Store builds unless Apple-approved regional rules apply.",
                "Verify account deletion and Sign in with Apple before TestFlight submission.",
            ],
        },
        "googlePlay": {
            "submittedByDefault": mode in {"play_store", "regional_user_choice"},
            "submissionStatus": (
                "not_submitted_by_default"
                if mode not in {"play_store", "regional_user_choice"}
                else "tenant_console_required"
            ),
            "formName": "Data safety",
            "digitalContentPaymentPolicy": (
                "play_billing_only"
                if "play_billing" in app_visible and not external_payments
                else (
                    "approved_user_choice_or_play_billing"
                    if mode == "regional_user_choice"
                    else "not_enabled"
                )
            ),
            "externalPaymentLinksInApp": mode == "regional_user_choice"
            and external_payments,
            "accountDeletionInApp": account_deletion,
            "userGeneratedContent": False,
            "tenantRequiredActions": [
                "Complete Play Console Data safety using the final tenant SDKs, regions, and legal URLs.",
                "Use Play Billing or approved user-choice billing for paid digital content in Play builds.",
                "Register OAuth SHA fingerprints and support account deletion before review.",
            ],
        },
        "androidDirect": {
            "submittedByDefault": mode == "android_direct",
            "submissionStatus": (
                "direct_distribution_only"
                if mode == "android_direct"
                else "not_direct_distribution"
            ),
            "externalPaymentsInApp": mode == "android_direct" and external_payments,
            "digitalContentPaymentPolicy": (
                "tenant_owned_external_payments"
                if mode == "android_direct" and external_payments
                else "not_enabled"
            ),
            "accountDeletionInApp": account_deletion,
            "tenantRequiredActions": [
                "Publish tenant terms, privacy, refund, support, and payment-dispute pages before direct distribution.",
                "Keep payment provider credentials and crypto keys on Tenant Edge/API Worker only.",
                "Review local payment and digital-asset rules for each distribution region.",
            ],
        },
    }


def distribution_channel_readiness(
    flavor: str,
    visibility: dict[str, Any],
    paths: dict[str, str | None],
) -> dict[str, Any]:
    mode = str(visibility["storeComplianceMode"])
    primary_channel = {
        "app_store": "app_store_testflight",
        "play_store": "google_play_internal",
        "regional_user_choice": "google_play_internal",
        "android_direct": "android_direct",
    }.get(mode, "android_direct")
    aab_path = paths.get("androidReleaseAppBundle")
    apk_path = paths.get("androidReleaseApk")
    return {
        "storeComplianceMode": mode,
        "primaryChannel": primary_channel,
        "channels": {
            "appStoreTestFlight": {
                "status": "ios_environment_blocked",
                "buildCommand": f"./scripts/build_flavor.sh {flavor} ios release",
                "artifactPath": None,
                "requiresTenantSigning": True,
                "localBlocker": "full Xcode is required to prove unsigned iOS release builds on this machine",
                "tenantRequiredActions": [
                    "Build on a machine or CI runner with full Xcode and CocoaPods.",
                    "Attach tenant Apple team, certificates, provisioning profiles, and App Store Connect metadata.",
                    "Upload through the tenant-owned TestFlight/App Store Connect workflow.",
                ],
            },
            "googlePlayInternal": {
                "status": (
                    "ready_for_tenant_signing"
                    if aab_path
                    else "missing_release_artifact"
                ),
                "buildCommand": f"./scripts/build_flavor.sh {flavor} android release appbundle",
                "artifactPath": aab_path,
                "requiresTenantSigning": True,
                "tenantRequiredActions": [
                    "Replace template signing with tenant upload signing material outside this repository.",
                    "Enable Play App Signing and upload the release AAB in the tenant Play Console account.",
                    "Complete Play Billing, Data safety, content rating, support, and privacy declarations.",
                ],
            },
            "androidDirect": {
                "status": (
                    "ready_for_tenant_signing"
                    if apk_path
                    else "missing_release_artifact"
                ),
                "buildCommands": {
                    "apk": f"./scripts/build_flavor.sh {flavor} android release apk",
                    "appbundle": f"./scripts/build_flavor.sh {flavor} android release appbundle",
                },
                "artifactPaths": {
                    "apk": apk_path,
                    "appbundle": aab_path,
                },
                "requiresTenantSigning": True,
                "tenantRequiredActions": [
                    "Sign the APK or AAB with tenant-owned signing material outside this repository.",
                    "Publish tenant legal, support, refund, and payment-dispute pages before distribution.",
                    "Verify local payment, wallet, crypto, and point-card rules for every target region.",
                ],
            },
        },
    }


def store_submission(
    root: Path,
    flavor: str,
    brand: dict[str, Any],
    template: dict[str, Any],
    features: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    supported_locales = list(brand.get("supportedLocales", []))
    return {
        "listing": {
            "displayName": brand["appName"],
            "defaultLocale": supported_locales[0] if supported_locales else "en-US",
            "supportedLocales": supported_locales,
            "shortDescription": LISTING_COPY_BY_TEMPLATE.get(
                str(template["styleTemplate"]),
                "Short drama episodes with tenant-managed catalog and wallet flows.",
            ),
            "supportUrl": brand["customerServiceUrl"],
            "termsUrl": brand["termsUrl"],
            "privacyUrl": brand["privacyUrl"],
        },
        "reviewNotes": [
            "Template is style-inspired only and does not include copied third-party marks or screenshots.",
            "Playback authorization, payment verification, and wallet crediting stay on Tenant Edge.",
            "Payment entry visibility is filtered by storeComplianceMode before app handoff.",
        ],
        "localizedListings": localized_listings(brand, supported_locales),
        "dataSafety": {
            "notes": "tenant must answer store questionnaires using final SDKs, regions, legal URLs, and enabled payment providers",
            "templateDisclosures": {
                "accountCreation": bool(template.get("authProviders")),
                "accountDeletion": bool(features.get("enableAccountDeletion")),
                "purchases": bool(visibility.get("appVisibleProviders")),
                "externalPaymentsAllowed": bool(
                    visibility.get("externalPaymentsAllowed"),
                ),
                "consumerContentUpload": False,
                "tenantSecretsInClient": False,
            },
        },
        "tenantRequiredActions": [
            "configure tenant signing",
            "replace placeholder icons and screenshots",
            "register OAuth callbacks and deep links",
            "create store purchase products or tenant payment channels",
            "complete store privacy and data safety questionnaires",
        ],
        "screenshotAssets": screenshot_assets(root, flavor),
    }


def flavor_entry(root: Path, flavor: str, release_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    config_dir = root / "assets" / "config" / flavor
    brand = read_json(config_dir / "tenant.brand.json")
    template = read_json(config_dir / "tenant.template.json")
    features = read_json(config_dir / "tenant.features.json")
    visibility = payment_visibility(template)
    flavor_artifacts = [
        artifact
        for artifact in release_artifacts
        if artifact.get("flavor") == flavor
        and artifact.get("platform") == "android"
        and artifact.get("mode") == "release"
        and artifact.get("packageType") in {"apk", "appbundle"}
    ]
    paths = artifact_paths(flavor_artifacts)

    return {
        "flavor": flavor,
        "appName": brand["appName"],
        "tenantCode": brand["tenantCode"],
        "styleTemplate": template["styleTemplate"],
        "storeComplianceMode": template["storeComplianceMode"],
        "applicationId": brand["bundleId"],
        "bundleId": brand["bundleId"],
        "deepLinkScheme": deep_link_scheme(flavor),
        "apiAdapterBase": brand["apiAdapterBase"],
        "authProviders": template["authProviders"],
        "consumerPaymentProviders": template["consumerPaymentProviders"],
        "paymentVisibility": visibility,
        "authCallbackRegistration": auth_callback_registration(flavor, template),
        "storeProductRegistration": store_product_registration(visibility),
        "nativeCapabilityRegistration": native_capability_registration(
            flavor,
            brand,
            template,
            visibility,
        ),
        "storeReviewDeclarations": store_review_declarations(
            template,
            features,
            visibility,
        ),
        "distributionChannelReadiness": distribution_channel_readiness(
            flavor,
            visibility,
            paths,
        ),
        "storeSubmission": store_submission(
            root,
            flavor,
            brand,
            template,
            features,
            visibility,
        ),
        "legal": {
            "customerServiceUrl": brand["customerServiceUrl"],
            "termsUrl": brand["termsUrl"],
            "privacyUrl": brand["privacyUrl"],
        },
        "buildCommands": {
            "androidReleaseApk": f"./scripts/build_flavor.sh {flavor} android release apk",
            "androidReleaseAppBundle": f"./scripts/build_flavor.sh {flavor} android release appbundle",
            "iosUnsignedRelease": f"./scripts/build_flavor.sh {flavor} ios release",
        },
        "artifactPaths": paths,
        "releaseArtifacts": sorted(
            flavor_artifacts,
            key=lambda item: str(item.get("packageType", "")),
        ),
    }


def deep_link_scheme(flavor: str) -> str:
    return {
        "coolshow": "coolshowshort",
        "hongguo": "goldfruitdrama",
        "douyin": "pulsedrama",
        "hippo": "riverdrama",
        "reelshort": "cliffdrama",
    }[flavor]


def build_manifest(root: Path) -> dict[str, Any]:
    artifacts = load_release_artifacts(root)
    release_path = release_manifest_path(root)
    return {
        "schemaVersion": 1,
        "generatedAt": utc_timestamp(),
        "secretBoundary": SECRET_BOUNDARY,
        "sourceManifests": {
            "publicTenantConfig": "assets/config/<flavor>/tenant.brand.json and tenant.template.json",
            "releaseArtifacts": str(release_path.relative_to(root)) if release_path.exists() else None,
        },
        "tenantOwnedChecklist": TENANT_OWNED_CHECKLIST,
        "flavors": [flavor_entry(root, flavor, artifacts) for flavor in FLAVOR_ORDER],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=Path.cwd(),
        type=Path,
        help="mobile project root; defaults to current directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output JSON path; defaults to build/release-handoff/mobile-store-handoff.json",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output or root / "build" / "release-handoff" / "mobile-store-handoff.json"
    manifest = build_manifest(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote store handoff manifest: {output.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
