#!/usr/bin/env python3
"""Audit the mobile white-label app completion evidence.

This is intentionally a state audit, not a build tool. Run the build/test
commands first, then use this script to prove which app-completion gates are
currently satisfied and which are blocked by the local environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import scan_release_artifacts
import export_app_handoff
import export_completion_unblocker
import export_external_account_handoff
import export_github_publish_handoff
import export_store_signing_handoff
import export_store_submission_starter
import export_ui_preview_gallery
import flutter_toolchain_audit
import import_store_submission_evidence
import store_submission_evidence_preflight


FLAVORS = {
    "coolshow": {
        "applicationId": "com.coolshow.short",
        "appName": "CoolShow Short",
        "deepLinkScheme": "coolshowshort",
        "dartDefine": "QVBQX0ZMQVZPUj1jb29sc2hvdw==",
        "styleTemplate": "coolshow",
    },
    "hongguo": {
        "applicationId": "com.shortdrama.goldfruit",
        "appName": "GoldFruit Drama",
        "deepLinkScheme": "goldfruitdrama",
        "dartDefine": "QVBQX0ZMQVZPUj1ob25nZ3Vv",
        "styleTemplate": "hongguo_inspired",
    },
    "douyin": {
        "applicationId": "com.shortdrama.pulse",
        "appName": "Pulse Drama",
        "deepLinkScheme": "pulsedrama",
        "dartDefine": "QVBQX0ZMQVZPUj1kb3V5aW4=",
        "styleTemplate": "douyin_inspired",
    },
    "hippo": {
        "applicationId": "com.shortdrama.river",
        "appName": "River Drama",
        "deepLinkScheme": "riverdrama",
        "dartDefine": "QVBQX0ZMQVZPUj1oaXBwbw==",
        "styleTemplate": "hippo_inspired",
    },
    "reelshort": {
        "applicationId": "com.shortdrama.cliff",
        "appName": "Cliff Drama",
        "deepLinkScheme": "cliffdrama",
        "dartDefine": "QVBQX0ZMQVZPUj1yZWVsc2hvcnQ=",
        "styleTemplate": "reelshort_inspired",
    },
}

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

FORBIDDEN_SOURCE_MARKERS = [
    "TENANT_APP_SECRET",
    "CLOUDFLARE_API_TOKEN",
    "client_secret",
    "clientSecret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "secretCiphertext",
    "secret_hash",
    "manifestUrl",
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

STORE_SUBMISSION_FLAVORS = import_store_submission_evidence.FLAVOR_DEFAULTS
STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR = {
    flavor: str(values["primaryChannel"])
    for flavor, values in STORE_SUBMISSION_FLAVORS.items()
}

STORE_HANDOFF_DEEP_LINK_SCHEMES = {
    "coolshow": "coolshowshort",
    "hongguo": "goldfruitdrama",
    "douyin": "pulsedrama",
    "hippo": "riverdrama",
    "reelshort": "cliffdrama",
}

STORE_SUBMISSION_ALLOWED_STATUSES_BY_CHANNEL = {
    "app_store_testflight": {
        "testflight_uploaded",
        "testflight_external_testing",
        "app_store_ready_for_review",
        "app_store_submitted",
        "app_store_approved",
    },
    "google_play_internal": {
        "play_internal_uploaded",
        "play_closed_testing",
        "play_production_submitted",
        "play_production_approved",
    },
    "android_direct": {
        "direct_signed_package_ready",
        "direct_distribution_published",
    },
}

STORE_SUBMISSION_BASE_REQUIRED_FLAGS = [
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

STORE_SUBMISSION_CHANNEL_REQUIRED_FLAGS = {
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


def store_submission_screenshot_assets(root: Path, flavor: str) -> list[dict[str, Any]]:
    coolshow_wysiwyg_path = root / "build" / "ui-preview-gallery" / "wysiwyg-coolshow-eight-screen-gallery.png"
    if flavor == "coolshow" and coolshow_wysiwyg_path.exists():
        relative_path = "build/ui-preview-gallery/wysiwyg-coolshow-eight-screen-gallery.png"
        content = coolshow_wysiwyg_path.read_bytes()
        size = png_dimensions(coolshow_wysiwyg_path)
        return [
            {
                "screen": "coolshow_wysiwyg_eight_screen_gallery",
                "path": relative_path,
                "viewportWidth": 390,
                "width": size[0] if size else None,
                "height": size[1] if size else None,
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "source": "wysiwyg_runtime_board",
                "tenantShouldReplace": True,
            },
        ]

    assets: list[dict[str, Any]] = []
    for screen_id in SCREEN_IDS:
        relative_path = f"test/goldens/prototypes/{flavor}_{screen_id}.png"
        path = root / relative_path
        content = path.read_bytes() if path.exists() else b""
        size = png_dimensions(path)
        assets.append(
            {
                "screen": screen_id,
                "path": relative_path,
                "viewportWidth": 390,
                "width": size[0] if size else None,
                "height": size[1] if size else None,
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "source": "publish_safe_prototype",
                "tenantShouldReplace": True,
            },
        )
    return assets


def locale_language(locale: str) -> str:
    return locale.replace("_", "-").split("-")[0].lower()


def store_submission_localized_listings(
    brand: dict[str, Any],
    supported_locales: list[str],
) -> list[dict[str, Any]]:
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
                "supportUrl": brand.get("customerServiceUrl"),
                "termsUrl": brand.get("termsUrl"),
                "privacyUrl": brand.get("privacyUrl"),
                "isDefault": locale == default_locale,
            },
        )
    return listings


def auth_callback_registration_payload(
    scheme: str,
    template: dict[str, Any],
) -> dict[str, Any]:
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


def store_product_registration_payload(visibility: dict[str, Any]) -> dict[str, Any]:
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


def native_capability_registration_payload(
    flavor: str,
    expected: dict[str, str],
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

    config_name = flavor.capitalize()
    return {
        "ios": {
            "bundleId": expected["applicationId"],
            "xcodeScheme": flavor,
            "xcconfig": f"ios/Flutter/{config_name}.xcconfig",
            "appIconAsset": f"ios/Runner/Assets.xcassets/AppIcon-{flavor}.appiconset",
            "urlScheme": expected["deepLinkScheme"],
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
            "applicationId": expected["applicationId"],
            "productFlavor": flavor,
            "manifest": "android/app/src/main/AndroidManifest.xml",
            "launcherIcon": f"android/app/src/{flavor}/res/mipmap-xxxhdpi/ic_launcher.png",
            "urlScheme": expected["deepLinkScheme"],
            "requiredCapabilities": android_capabilities,
            "tenantRequiredActions": [
                "Replace template debug signing with tenant-owned upload signing material outside this repository.",
                "Register OAuth SHA fingerprints for Google/Facebook providers when enabled.",
                "Complete Play Console declarations or direct-distribution compliance review for the selected store mode.",
            ],
        },
    }


def store_review_declarations_payload(
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


def distribution_channel_readiness_payload(
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


@dataclass
class Check:
    id: str
    status: str
    detail: str
    evidence: list[str]
    completion_blocking: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
            "completionBlocking": self.completion_blocking,
        }


def remote_ios_ci_build_evidence_passed(checks: list[Check]) -> bool:
    by_id = {check.id: check for check in checks}
    ci_artifacts = by_id.get("ios_ci_artifact_evidence")
    workflow = by_id.get("ci_workflow")
    return (
        ci_artifacts is not None
        and ci_artifacts.status == "passed"
        and workflow is not None
        and workflow.status == "passed"
        and "five-flavor unsigned iOS debug builds" in workflow.detail
        and "five-flavor unsigned iOS release builds" in workflow.detail
    )


def apply_completion_boundaries(checks: list[Check]) -> list[Check]:
    if not remote_ios_ci_build_evidence_passed(checks):
        return checks
    for check in checks:
        if check.id in {"ios_build_matrix", "ios_build_environment"}:
            check.completion_blocking = False
    return checks


def completion_summary(checks: list[Check]) -> dict[str, Any]:
    blocking_checks = [check for check in checks if check.completion_blocking]
    return {
        "passed": sum(1 for check in blocking_checks if check.status == "passed"),
        "missing": sum(1 for check in blocking_checks if check.status == "missing"),
        "failed": sum(1 for check in blocking_checks if check.status == "failed"),
        "blocked": sum(1 for check in blocking_checks if check.status == "blocked"),
        "diagnostic": sum(1 for check in checks if not check.completion_blocking),
        "allStatuses": {check.id: check.status for check in checks},
    }


def rel(root: Path, path: Path) -> str:
    resolved = path.resolve()
    for base in [root.resolve(), root.resolve().parent]:
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(resolved)


def resolve_workflow_path(root: Path) -> tuple[Path, str]:
    monorepo_workflow = root.parent / ".github" / "workflows" / "mobile-flutter.yml"
    standalone_workflow = root / ".github" / "workflows" / "mobile-flutter.yml"
    if monorepo_workflow.exists():
        return monorepo_workflow, "../.github/workflows/mobile-flutter.yml"
    return standalone_workflow, ".github/workflows/mobile-flutter.yml"


def resolve_repo_file(root: Path, relative: str) -> tuple[Path, str]:
    _, workflow_evidence = resolve_workflow_path(root)
    if workflow_evidence.startswith("../"):
        monorepo_path = root.parent / relative
        if monorepo_path.exists():
            return monorepo_path, f"../{relative}"
    return root / relative, relative


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as error:
        return 127, str(error)
    return completed.returncode, completed.stdout.strip()


def check_required_files(root: Path) -> Check:
    required = [
        "lib/main.dart",
        "lib/app/app_runtime.dart",
        "lib/app/short_drama_app.dart",
        "lib/core/api/tenant_adapter_client.dart",
        "lib/core/config/app_capabilities.dart",
        "lib/core/config/feature_gate.dart",
        "lib/core/i18n/app_strings.dart",
        "lib/core/identity/end_user_identity_store.dart",
        "lib/core/identity/shared_preferences_end_user_identity_storage.dart",
        "lib/core/payment/store_purchase_service.dart",
        "scripts/capture_wysiwyg_previews.mjs",
        "scripts/download_ios_ci_artifacts.py",
        "scripts/export_app_handoff.py",
        "scripts/export_completion_unblocker.py",
        "scripts/export_external_account_handoff.py",
        "scripts/export_github_publish_handoff.py",
        "scripts/export_store_submission_starter.py",
        "scripts/export_ui_preview_gallery.py",
        "scripts/import_github_publication_evidence.py",
        "scripts/import_store_submission_evidence.py",
        "scripts/ios_runtime_smoke.py",
        "scripts/mobile_completion_closure.py",
        "scripts/prepare_store_submission_inputs.py",
        "scripts/store_submission_evidence_preflight.py",
        "features-placeholder",
        "android/app/build.gradle.kts",
        "ios/Runner.xcodeproj/project.pbxproj",
        ".github-placeholder",
    ]
    feature_files = [
        "features/splash/splash_screen.dart",
        "features/auth/auth_screen.dart",
        "features/home/home_screen.dart",
        "features/catalog/catalog_screen.dart",
        "features/drama_detail/drama_detail_screen.dart",
        "features/player/player_screen.dart",
        "features/unlock/unlock_sheet.dart",
        "features/wallet/wallet_screen.dart",
        "features/account/account_screen.dart",
        "features/library/library_screen.dart",
        "features/legal/legal_link_screen.dart",
        "features/point_card_management/point_card_management_screen.dart",
        "features/card_redeem/card_redeem_screen.dart",
        "features/account_delete/account_delete_screen.dart",
    ]
    required = [
        item
        for item in required
        if item not in {"features-placeholder", ".github-placeholder"}
    ]
    required.extend(f"lib/{item}" for item in feature_files)
    workflow, workflow_evidence = resolve_workflow_path(root)
    required.append(workflow_evidence)

    missing = [item for item in required if not (root / item).exists()]
    if not workflow.exists() and workflow_evidence not in missing:
        missing.append(workflow_evidence)
    status = "passed" if not missing else "missing"
    detail = "Required mobile source, native, and CI files are present."
    if missing:
        detail = f"Missing required files: {', '.join(missing)}"
    return Check("required_files", status, detail, required)


def check_flavor_configs(root: Path) -> Check:
    missing: list[str] = []
    evidence: list[str] = []
    for flavor in FLAVORS:
        for filename in [
            "tenant.brand.json",
            "tenant.template.json",
            "tenant.features.json",
        ]:
            path = root / "assets" / "config" / flavor / filename
            evidence.append(rel(root, path))
            if not path.exists():
                missing.append(rel(root, path))
        for native_path in [
            f"android/app/src/{flavor}/res/mipmap-xxxhdpi/ic_launcher.png",
            f"ios/Flutter/{flavor.capitalize()}.xcconfig",
            f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{flavor}.xcscheme",
            f"ios/Runner/Assets.xcassets/AppIcon-{flavor}.appiconset/Contents.json",
        ]:
            evidence.append(native_path)
            if not (root / native_path).exists():
                missing.append(native_path)

    if missing:
        return Check(
            "four_template_flavors",
            "missing",
            f"Missing flavor config/native files: {', '.join(missing)}",
            evidence,
        )
    return Check(
        "four_template_flavors",
        "passed",
        "All five template flavors have public config, Android icon, iOS xcconfig, scheme, and AppIcon metadata.",
        evidence,
    )


def check_prototype_goldens(root: Path) -> Check:
    evidence: list[str] = []
    missing: list[str] = []
    for flavor in FLAVORS:
        for screen_id in SCREEN_IDS:
            path = root / "test" / "goldens" / "prototypes" / f"{flavor}_{screen_id}.png"
            evidence.append(rel(root, path))
            if not path.exists():
                missing.append(rel(root, path))
    if missing:
        return Check(
            "prototype_screens",
            "missing",
            f"Missing prototype PNGs: {', '.join(missing)}",
            evidence,
        )
    return Check(
        "prototype_screens",
        "passed",
        "Prototype PNGs cover five templates times eight MVP screens.",
        evidence,
    )


def check_prototype_responsive_viewports(root: Path) -> Check:
    layout_test_path = root / "test" / "prototype_layout_test.dart"
    support_path = root / "test" / "prototype_test_support.dart"
    layout_test = read_text(layout_test_path)
    support = read_text(support_path)
    evidence = [rel(root, support_path), rel(root, layout_test_path)]
    required_markers = [
        ("prototype_test_support.dart", "const prototypeWidths = <double>[360, 390, 430, 768]"),
        ("prototype_test_support.dart", "final prototypeFlavors = <String, FlavorConfig Function()>{"),
        ("prototype_test_support.dart", "'hongguo': FlavorConfig.hongguo"),
        ("prototype_test_support.dart", "'douyin': FlavorConfig.douyin"),
        ("prototype_test_support.dart", "'hippo': FlavorConfig.hippo"),
        ("prototype_test_support.dart", "'reelshort': FlavorConfig.reelshort"),
        ("prototype_test_support.dart", "final prototypeScreens = <PrototypeScreen>["),
        ("prototype_test_support.dart", "id: '01_splash'"),
        ("prototype_test_support.dart", "id: '02_auth'"),
        ("prototype_test_support.dart", "id: '03_home'"),
        ("prototype_test_support.dart", "id: '04_catalog'"),
        ("prototype_test_support.dart", "id: '05_detail'"),
        ("prototype_test_support.dart", "id: '06_player'"),
        ("prototype_test_support.dart", "id: '07_unlock'"),
        ("prototype_test_support.dart", "id: '08_mine_wallet_card'"),
        ("prototype_layout_test.dart", "for (final flavorEntry in prototypeFlavors.entries)"),
        ("prototype_layout_test.dart", "for (final width in prototypeWidths)"),
        ("prototype_layout_test.dart", "for (final screen in prototypeScreens)"),
        ("prototype_layout_test.dart", "tester.takeException()"),
        ("prototype_layout_test.dart", "overflowed at"),
    ]
    sources = {
        "prototype_test_support.dart": support,
        "prototype_layout_test.dart": layout_test,
    }
    missing = [
        f"{filename}:{marker}"
        for filename, marker in required_markers
        if marker not in sources[filename]
    ]
    if missing:
        return Check(
            "prototype_responsive_viewports",
            "missing",
            f"Prototype responsive viewport coverage is incomplete: {', '.join(missing)}",
            evidence,
        )
    return Check(
        "prototype_responsive_viewports",
        "passed",
        "Prototype layout tests cover all five templates and eight MVP screens at 360, 390, 430, and iPad-width viewports without Flutter overflow exceptions.",
        evidence,
    )


def check_test_coverage_files(root: Path) -> Check:
    required = [
        "test/tenant_adapter_client_test.dart",
        "test/app_runtime_test.dart",
        "test/app_bootstrap_test.dart",
        "test/auth_screen_test.dart",
        "test/prototype_layout_test.dart",
        "test/i18n_runtime_test.dart",
        "test/end_user_identity_store_test.dart",
        "test/legal_links_test.dart",
        "test/player_screen_test.dart",
        "test/library_screen_test.dart",
        "test/home_screen_test.dart",
        "test/catalog_screen_test.dart",
        "test/wallet_screen_test.dart",
        "test/point_card_management_screen_test.dart",
        "test/account_delete_screen_test.dart",
        "test/account_screen_test.dart",
        "test/feature_flags_test.dart",
        "test/template_capabilities_test.dart",
    ]
    missing = [item for item in required if not (root / item).exists()]
    if missing:
        return Check(
            "test_coverage_files",
            "missing",
            f"Missing test files: {', '.join(missing)}",
            required,
        )
    app_bootstrap = read_text(root / "test" / "app_bootstrap_test.dart")
    app_runtime_test = read_text(root / "test" / "app_runtime_test.dart")
    auth_screen_test = read_text(root / "test" / "auth_screen_test.dart")
    account_screen_test = read_text(root / "test" / "account_screen_test.dart")
    wallet_screen_test = read_text(root / "test" / "wallet_screen_test.dart")
    player_screen_test = read_text(root / "test" / "player_screen_test.dart")
    library_screen_test = read_text(root / "test" / "library_screen_test.dart")
    feature_flags_test = read_text(root / "test" / "feature_flags_test.dart")
    home_screen_test = read_text(root / "test" / "home_screen_test.dart")
    catalog_screen_test = read_text(root / "test" / "catalog_screen_test.dart")
    point_card_management_test = read_text(
        root / "test" / "point_card_management_screen_test.dart"
    )
    remote_override_markers = [
        "remote config overrides template while native build caps payments",
        "FlavorConfig.hongguo()",
        "'styleTemplate'] = 'reelshort_inspired'",
        "'Tenant Picked Drama'",
        "'Every episode ends on a cliff'",
        "'Cliffhanger Premium'",
        "'payments gated'",
        "expect(find.text('android direct'), findsNothing)",
        "'Free-to-start drama theater'",
    ]
    missing_remote_override_markers = [
        marker for marker in remote_override_markers if marker not in app_bootstrap
    ]
    if missing_remote_override_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing remote config template override widget coverage markers: "
            + ", ".join(missing_remote_override_markers),
            required,
        )
    compliance_mismatch_markers = [
        "req_misconfigured_remote_options",
        "providers: ['iap', 'stripe']",
        "storeComplianceMode: 'android_direct'",
        "expect(find.text('app store'), findsOneWidget)",
        "expect(find.text('android direct'), findsNothing)",
        "expect(find.text('stripe'), findsNothing)",
    ]
    missing_compliance_mismatch_markers = [
        marker for marker in compliance_mismatch_markers if marker not in wallet_screen_test
    ]
    if missing_compliance_mismatch_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing payment options compliance mismatch widget coverage markers: "
            + ", ".join(missing_compliance_mismatch_markers),
            required,
        )
    native_compliance_cap_markers = [
        "native store build caps remote compliance mode and payment providers",
        "'storeComplianceMode': 'android_direct'",
        "'providers': ['iap', 'stripe', 'crypto', 'point_card']",
        "StoreComplianceMode.appStore",
        "contains(AuthProvider.apple)",
        "expect(runtime.effectivePaymentProviderWireValues, ['iap'])",
    ]
    missing_native_compliance_cap_markers = [
        marker for marker in native_compliance_cap_markers if marker not in app_runtime_test
    ]
    if missing_native_compliance_cap_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing native compliance cap runtime coverage markers: "
            + ", ".join(missing_native_compliance_cap_markers),
            required,
        )
    external_payment_gate_markers = [
        "wallet hides external providers when Tenant Edge disables external payments",
        "req_external_disabled_remote_options",
        "externalPaymentsAllowed: false",
        "Payment entry gated by store compliance",
        "expect(find.text('stripe'), findsNothing)",
        "expect(find.text('point card'), findsNothing)",
        "request.path == '/topups/payment-channels'",
        "isEmpty",
    ]
    missing_external_payment_gate_markers = [
        marker for marker in external_payment_gate_markers if marker not in wallet_screen_test
    ]
    if missing_external_payment_gate_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing external payment enablement gate widget coverage markers: "
            + ", ".join(missing_external_payment_gate_markers),
            required,
        )
    wallet_error_copy_markers = [
        "wallet maps payment errors to friendly text",
        "APP_PAYMENT_PROVIDER_DISABLED",
        "req_pay_raw",
        "Payment failed. Please choose another method or retry.",
        "expect(find.textContaining('APP_PAYMENT_PROVIDER_DISABLED'), findsNothing)",
        "expect(find.textContaining('req_pay_raw'), findsNothing)",
        "expect(find.textContaining('Provider stripe is disabled'), findsNothing)",
    ]
    missing_wallet_error_copy_markers = [
        marker
        for marker in wallet_error_copy_markers
        if marker not in wallet_screen_test
    ]
    if missing_wallet_error_copy_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing wallet friendly payment error copy markers: "
            + ", ".join(missing_wallet_error_copy_markers),
            required,
        )
    offline_payment_proof_markers = [
        "Transfer proof reference",
        "receipt-2026-06-14-bca",
        "offlineRequest.body?['proofR2Key']",
        "payment-provider-bank_transfer",
        "scrollable: find.byType(Scrollable).first",
    ]
    missing_offline_payment_proof_markers = [
        marker
        for marker in offline_payment_proof_markers
        if marker not in wallet_screen_test
    ]
    if missing_offline_payment_proof_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing offline payment proof reference widget coverage markers: "
            + ", ".join(missing_offline_payment_proof_markers),
            required,
        )
    mine_payment_entry_markers = [
        "mine tab hides top-up entries when external payments are disabled",
        "req_mine_external_disabled_options",
        "enableOfflineTopup: true",
        "enableOnlinePayment: true",
        "externalPaymentsAllowed: false",
        "expect(find.text('Offline Top Up'), findsNothing)",
        "expect(find.text('Online Top Up'), findsNothing)",
        "expect(find.text('Wallet Center'), findsOneWidget)",
    ]
    missing_mine_payment_entry_markers = [
        marker for marker in mine_payment_entry_markers if marker not in feature_flags_test
    ]
    if missing_mine_payment_entry_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing mine payment entry guard widget coverage markers: "
            + ", ".join(missing_mine_payment_entry_markers),
            required,
        )
    oauth_provider_guard_markers = [
        "deep link callback ignores disabled oauth providers",
        "FlavorConfig.hongguo()",
        "provider=facebook",
        "oauth_disabled",
        "expect(transport.requests, isEmpty)",
        "Auth provider facebook is not enabled",
    ]
    missing_oauth_provider_guard_markers = [
        marker for marker in oauth_provider_guard_markers if marker not in auth_screen_test
    ]
    if missing_oauth_provider_guard_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing oauth provider deep-link guard widget coverage markers: "
            + ", ".join(missing_oauth_provider_guard_markers),
            required,
        )
    auth_error_copy_markers = [
        "auth maps Tenant Edge errors to friendly text",
        "APP_AUTH_PROVIDER_DISABLED",
        "req_auth_raw",
        "Sign-in failed. Please retry or choose another method.",
        "expect(find.textContaining('APP_AUTH_PROVIDER_DISABLED'), findsNothing)",
        "expect(find.textContaining('req_auth_raw'), findsNothing)",
        "expect(find.textContaining('Email login is disabled'), findsNothing)",
    ]
    missing_auth_error_copy_markers = [
        marker for marker in auth_error_copy_markers if marker not in auth_screen_test
    ]
    if missing_auth_error_copy_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing auth friendly error copy markers: "
            + ", ".join(missing_auth_error_copy_markers),
            required,
        )
    point_card_compliance_markers = [
        "mine screen hides point card entry when app store build filters provider",
        "card redeem blocks raw point_card payment options in app store builds",
        "req_misconfigured_account_point_card_options",
        "req_misconfigured_point_card_options",
        "providers: ['iap', 'point_card']",
        "storeComplianceMode: 'android_direct'",
        "expect(find.text('Point Card Management'), findsNothing)",
        "expect(find.text('Card redeem is not enabled.'), findsOneWidget)",
        "expect(find.text('Consumer point card'), findsNothing)",
    ]
    missing_point_card_compliance_markers = [
        marker
        for marker in point_card_compliance_markers
        if marker not in point_card_management_test
    ]
    if missing_point_card_compliance_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing point card compliance entry guard widget coverage markers: "
            + ", ".join(missing_point_card_compliance_markers),
            required,
        )
    point_card_error_copy_markers = [
        "card redeem maps Tenant Edge errors to friendly text",
        "APP_INVALID_REQUEST",
        "req_card_raw",
        "This point card cannot be used. Please check it and retry.",
        "expect(find.textContaining('APP_INVALID_REQUEST'), findsNothing)",
        "expect(find.textContaining('req_card_raw'), findsNothing)",
        "expect(find.textContaining('Card code is invalid'), findsNothing)",
    ]
    missing_point_card_error_copy_markers = [
        marker
        for marker in point_card_error_copy_markers
        if marker not in point_card_management_test
    ]
    if missing_point_card_error_copy_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing point card friendly redeem error copy markers: "
            + ", ".join(missing_point_card_error_copy_markers),
            required,
        )
    home_search_markers = [
        "home search opens catalog with submitted query",
        "TextInputAction.search",
        "expect(find.text('Palace Revenge'), findsWidgets)",
        "expect(find.text('River Vow'), findsNothing)",
        "expect(find.text('1 drama'), findsOneWidget)",
    ]
    missing_home_search_markers = [
        marker for marker in home_search_markers if marker not in home_screen_test
    ]
    if missing_home_search_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing home search routing widget coverage markers: "
            + ", ".join(missing_home_search_markers),
            required,
        )
    share_deep_link_markers = [
        "share deep link opens its player episode without network request",
        "goldfruitdrama://dramas/drama_2/episodes/drama_2_ep_003",
        "deepLinks: links",
        "expect(find.textContaining('Heiress Returns'), findsWidgets)",
        "expect(find.textContaining('Episode 3'), findsWidgets)",
        "expect(transport.requests, isEmpty)",
    ]
    missing_share_deep_link_markers = [
        marker for marker in share_deep_link_markers if marker not in app_bootstrap
    ]
    if missing_share_deep_link_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing share deep link routing widget coverage markers: "
            + ", ".join(missing_share_deep_link_markers),
            required,
        )
    share_deep_link_detail_markers = [
        "share deep link fetches public detail when catalog lacks drama",
        "goldfruitdrama://dramas/drama_remote_share/episodes/episode_remote_2",
        "Shared Public Drama",
        "Shared Episode 2",
        "expect(transport.requests.single.path, '/dramas/drama_remote_share')",
    ]
    missing_share_deep_link_detail_markers = [
        marker
        for marker in share_deep_link_detail_markers
        if marker not in app_bootstrap
    ]
    if missing_share_deep_link_detail_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing share deep link public detail resolution markers: "
            + ", ".join(missing_share_deep_link_detail_markers),
            required,
        )
    share_deep_link_duplicate_markers = [
        "share deep link ignores duplicate initial and stream uri",
        "episode_duplicate_1",
        "links.controller.add(uri)",
        "find.byType(PlayerScreen, skipOffstage: false)",
        "expect(transport.requests.single.path, '/dramas/drama_duplicate_share')",
    ]
    missing_share_deep_link_duplicate_markers = [
        marker
        for marker in share_deep_link_duplicate_markers
        if marker not in app_bootstrap
    ]
    if missing_share_deep_link_duplicate_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing share deep link duplicate guard markers: "
            + ", ".join(missing_share_deep_link_duplicate_markers),
            required,
        )
    catalog_initial_query_markers = [
        "catalog applies initial query from upstream search route",
        "initialQuery: 'palace'",
        "expect(find.text('Palace Revenge'), findsWidgets)",
        "expect(find.text('River Vow'), findsNothing)",
        "expect(find.text('1 drama'), findsOneWidget)",
    ]
    missing_catalog_initial_query_markers = [
        marker
        for marker in catalog_initial_query_markers
        if marker not in catalog_screen_test
    ]
    if missing_catalog_initial_query_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing catalog initial query filtering widget coverage markers: "
            + ", ".join(missing_catalog_initial_query_markers),
            required,
        )
    account_sign_out_markers = [
        "mine tab signs out registered account locally",
        "Sign Out",
        "runtime.account?.membershipTier, 'guest'",
        "runtime.account?.accountRefMasked, 'anon:pulsedrama-account-widget'",
        "expect(transport.requests, isEmpty)",
    ]
    missing_account_sign_out_markers = [
        marker
        for marker in account_sign_out_markers
        if marker not in account_screen_test
    ]
    if missing_account_sign_out_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing account sign-out widget coverage markers: "
            + ", ".join(missing_account_sign_out_markers),
            required,
        )
    player_episode_list_markers = [
        "player episode list sheet switches ready episodes",
        "Icons.list_alt",
        "Episode List",
        "expect(find.text('Episode 3'), findsNothing)",
        "expect(find.text('Authorized player'), findsNothing)",
        "expect(transport.requests, hasLength(1))",
    ]
    missing_player_episode_list_markers = [
        marker
        for marker in player_episode_list_markers
        if marker not in player_screen_test
    ]
    if missing_player_episode_list_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing player episode list sheet widget coverage markers: "
            + ", ".join(missing_player_episode_list_markers),
            required,
        )
    player_share_sheet_markers = [
        "player share action opens tenant-safe share sheet",
        "Icons.share_outlined",
        "Share Drama",
        "Copy Link",
        "goldfruitdrama://dramas/drama_share/episodes/episode_share_1",
        "expect(transport.requests, isEmpty)",
    ]
    missing_player_share_sheet_markers = [
        marker
        for marker in player_share_sheet_markers
        if marker not in player_screen_test
    ]
    if missing_player_share_sheet_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing player tenant-safe share sheet widget coverage markers: "
            + ", ".join(missing_player_share_sheet_markers),
            required,
        )
    player_error_copy_markers = [
        "player maps playback authorization errors to friendly text",
        "APP_INSUFFICIENT_BALANCE",
        "APP_EPISODE_NOT_READY",
        "APP_NOT_FOUND",
        "APP_PLAYBACK_TOKEN_FAILED",
        "expect(find.text(testCase.friendly), findsOneWidget)",
        "expect(find.textContaining(testCase.code), findsNothing)",
        "expect(find.textContaining('req_player_error'), findsNothing)",
    ]
    missing_player_error_copy_markers = [
        marker
        for marker in player_error_copy_markers
        if marker not in player_screen_test
    ]
    if missing_player_error_copy_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing player friendly playback error copy markers: "
            + ", ".join(missing_player_error_copy_markers),
            required,
        )
    playback_refresh_markers = [
        "player silently refreshes expired playback token",
        "https://player.example/expired",
        "https://player.example/fresh",
        "expect(transport.requests, hasLength(2))",
        "transport.requests.first.headers['idempotency-key']",
        "transport.requests.last.headers['idempotency-key']",
        "Playback authorization failed. Please retry.",
        "findsNothing",
    ]
    missing_playback_refresh_markers = [
        marker
        for marker in playback_refresh_markers
        if marker not in player_screen_test
    ]
    if missing_playback_refresh_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing playback token refresh idempotency markers: "
            + ", ".join(missing_playback_refresh_markers),
            required,
        )
    library_entry_navigation_markers = [
        "watch history entry opens its player episode",
        "favorite entry opens current drama detail from Tenant Edge",
        "runtime.recordPlayback(",
        "runtime.toggleFavorite(",
        "expect(find.text('Unlock and Play'), findsOneWidget)",
        "expect(transport.requests.single.path, '/dramas/drama_favorite')",
    ]
    missing_library_entry_navigation_markers = [
        marker
        for marker in library_entry_navigation_markers
        if marker not in library_screen_test
    ]
    if missing_library_entry_navigation_markers:
        return Check(
            "test_coverage_files",
            "failed",
            "Missing library entry navigation widget coverage markers: "
            + ", ".join(missing_library_entry_navigation_markers),
            required,
        )
    return Check(
        "test_coverage_files",
        "passed",
        "Tests exist for Tenant Edge client, runtime bootstrap, remote config template override, payment options compliance mismatch, native compliance cap, external payment enablement gate, wallet friendly payment error copy, auth friendly error copy, offline payment proof reference, mine payment entry guards, oauth provider deep-link guards, point card compliance entry guards, point card friendly redeem error copy, home search routing, share deep link routing, share deep link public detail resolution, share deep link duplicate guard, catalog initial query filtering, account sign-out, player episode list sheet, player tenant-safe share sheet, player friendly playback error copy, playback token refresh idempotency, library entry navigation, email auth verification, OAuth URL launch and deep-link callback completion, i18n, identity, legal links, playback, library history/favorites, wallet payment channels, tenant checkout launch, native store purchase receipt verification, point card management, account deletion, feature gates, capabilities, and prototype layouts.",
        required,
    )


def check_runtime_identity(root: Path) -> Check:
    main = read_text(root / "lib" / "main.dart")
    pubspec = read_text(root / "pubspec.yaml")
    identity = read_text(root / "lib" / "core" / "identity" / "end_user_identity_store.dart")
    shared = read_text(
        root / "lib" / "core" / "identity" / "shared_preferences_end_user_identity_storage.dart",
    )
    required_markers = [
        ("main.dart", "EndUserIdentityStore"),
        ("main.dart", "SharedPreferencesEndUserIdentityStorage"),
        ("main.dart", "endUserRef: endUserRef"),
        ("pubspec.yaml", "shared_preferences:"),
        ("end_user_identity_store.dart", "Random.secure()"),
        ("shared_preferences_end_user_identity_storage.dart", "SharedPreferencesAsync"),
    ]
    sources = {
        "main.dart": main,
        "pubspec.yaml": pubspec,
        "end_user_identity_store.dart": identity,
        "shared_preferences_end_user_identity_storage.dart": shared,
    }
    missing = [
        f"{source}:{marker}"
        for source, marker in required_markers
        if marker not in sources[source]
    ]
    if missing:
        return Check(
            "runtime_identity",
            "missing",
            f"Runtime identity persistence markers missing: {', '.join(missing)}",
            [
                "lib/main.dart",
                "lib/core/identity/end_user_identity_store.dart",
                "lib/core/identity/shared_preferences_end_user_identity_storage.dart",
                "pubspec.yaml",
            ],
        )
    return Check(
        "runtime_identity",
        "passed",
        "main.dart resolves one tenant-scoped anonymous endUserRef through SharedPreferences before app bootstrap.",
        [
            "lib/main.dart",
            "lib/core/identity/end_user_identity_store.dart",
            "lib/core/identity/shared_preferences_end_user_identity_storage.dart",
            "pubspec.yaml",
        ],
    )


def check_native_playback_dependency(root: Path) -> Check:
    pubspec = read_text(root / "pubspec.yaml")
    player = read_text(root / "lib" / "features" / "player" / "player_screen.dart")
    auth = read_text(root / "lib" / "features" / "auth" / "auth_screen.dart")
    wallet = read_text(root / "lib" / "features" / "wallet" / "wallet_screen.dart")
    store_purchase = read_text(root / "lib" / "core" / "payment" / "store_purchase_service.dart")
    client = read_text(root / "lib" / "core" / "api" / "tenant_adapter_client.dart")
    required_markers = [
        ("pubspec.yaml", "video_player:"),
        ("pubspec.yaml", "url_launcher:"),
        ("pubspec.yaml", "app_links:"),
        ("pubspec.yaml", "in_app_purchase:"),
        ("player_screen.dart", "package:video_player/video_player.dart"),
        ("player_screen.dart", "VideoPlayerController.networkUrl"),
        ("player_screen.dart", "VideoPlayer("),
        ("player_screen.dart", "enableNativeVideo"),
        ("auth_screen.dart", "package:app_links/app_links.dart"),
        ("auth_screen.dart", "package:url_launcher/url_launcher.dart"),
        ("auth_screen.dart", "LaunchMode.externalApplication"),
        ("auth_screen.dart", "launchOAuthUrl"),
        ("auth_screen.dart", "getInitialLink"),
        ("auth_screen.dart", "uriLinkStream"),
        ("auth_screen.dart", "handleOAuthCallbackUri"),
        ("auth_screen.dart", "completeOAuthSignIn"),
        ("auth_screen.dart", "oauth-callback-code-input"),
        ("wallet_screen.dart", "launchPaymentUrl"),
        ("wallet_screen.dart", "LaunchMode.externalApplication"),
        ("wallet_screen.dart", "checkout opened"),
        ("wallet_screen.dart", "startStorePurchase"),
        ("wallet_screen.dart", "verifyStorePurchase"),
        ("wallet_screen.dart", "store purchase verified"),
        ("store_purchase_service.dart", "package:in_app_purchase/in_app_purchase.dart"),
        ("store_purchase_service.dart", "InAppPurchase.instance"),
        ("store_purchase_service.dart", "purchaseStream"),
        ("store_purchase_service.dart", "buyConsumable"),
        ("store_purchase_service.dart", "completePurchase"),
        ("tenant_adapter_client.dart", "/payment/store-purchases/verify"),
    ]
    sources = {
        "pubspec.yaml": pubspec,
        "player_screen.dart": player,
        "auth_screen.dart": auth,
        "wallet_screen.dart": wallet,
        "store_purchase_service.dart": store_purchase,
        "tenant_adapter_client.dart": client,
    }
    missing = [
        f"{source}:{marker}"
        for source, marker in required_markers
        if marker not in sources[source]
    ]
    if missing:
        return Check(
            "native_playback_dependency",
            "missing",
            f"Native playback/OAuth/payment launch markers missing: {', '.join(missing)}",
            [
                "pubspec.yaml",
                "lib/features/player/player_screen.dart",
                "lib/features/auth/auth_screen.dart",
                "lib/features/wallet/wallet_screen.dart",
                "lib/core/payment/store_purchase_service.dart",
                "lib/core/api/tenant_adapter_client.dart",
            ],
        )
    return Check(
        "native_playback_dependency",
        "passed",
        "Player screen uses video_player, auth uses url_launcher plus app_links callbacks for Tenant Edge OAuth completion, wallet launches tenant-hosted checkout URLs, and store-compliant builds use native in-app purchase receipt verification with testable injection points.",
        [
            "pubspec.yaml",
            "lib/features/player/player_screen.dart",
            "lib/features/auth/auth_screen.dart",
            "lib/features/wallet/wallet_screen.dart",
            "lib/core/payment/store_purchase_service.dart",
            "lib/core/api/tenant_adapter_client.dart",
        ],
    )


def check_source_secret_boundary(root: Path) -> Check:
    roots = [root / "lib", root / "assets", root / "android", root / "ios"]
    hits: list[str] = []
    evidence = [rel(root, item) for item in roots]
    for scan_root in roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            try:
                data = path.read_text(encoding="utf-8", errors="ignore")
            except UnicodeDecodeError:
                continue
            for marker in FORBIDDEN_SOURCE_MARKERS:
                if marker in data:
                    hits.append(f"{rel(root, path)}:{marker}")
    if hits:
        return Check(
            "source_secret_boundary",
            "failed",
            f"Forbidden source markers found: {', '.join(hits)}",
            evidence,
        )
    return Check(
        "source_secret_boundary",
        "passed",
        "Mobile source/assets/native templates do not contain forbidden tenant secret or raw playback markers.",
        evidence,
    )


def check_mobile_open_source_release(root: Path) -> Check:
    license_path = root / "LICENSE"
    readme_path = root / "README.md"
    release_notes_path = root / "docs" / "open-source-release.md"
    gitignore_path, gitignore_evidence = resolve_repo_file(root, ".gitignore")
    evidence = [
        "LICENSE",
        "README.md",
        "docs/open-source-release.md",
        gitignore_evidence,
        "assets/config/hongguo/tenant.brand.json",
        "assets/config/douyin/tenant.brand.json",
        "assets/config/hippo/tenant.brand.json",
        "assets/config/reelshort/tenant.brand.json",
        "test/goldens/prototypes",
    ]

    files = {
        "LICENSE": license_path,
        "README.md": readme_path,
        "docs/open-source-release.md": release_notes_path,
        gitignore_evidence: gitignore_path,
    }
    missing_files = [
        name
        for name, path in files.items()
        if not path.exists()
    ]
    if missing_files:
        return Check(
            "mobile_open_source_release",
            "missing",
            f"Open-source release boundary files are missing: {', '.join(missing_files)}",
            evidence,
        )

    license_text = read_text(license_path)
    readme = read_text(readme_path)
    release_notes = read_text(release_notes_path)
    gitignore = read_text(gitignore_path)

    required_markers = [
        ("LICENSE", "Apache License"),
        ("LICENSE", "Version 2.0"),
        ("README.md", "docs/open-source-release.md"),
        ("README.md", "mobile/LICENSE"),
        ("README.md", "tenant edge secrets"),
        ("README.md", "Cloudflare API tokens"),
        ("README.md", "Flutter assets and Dart defines must only contain public config"),
        ("docs/open-source-release.md", "Apache-2.0"),
        ("docs/open-source-release.md", "## What Can Be Published"),
        ("docs/open-source-release.md", "## What Must Not Be Published"),
        ("docs/open-source-release.md", "Third-party app screenshots, copied marks, or trade dress assets"),
        ("docs/open-source-release.md", "Store-submission evidence template and guide generated by `scripts/import_store_submission_evidence.py`"),
        ("docs/open-source-release.md", "Build outputs stay under ignored `build/` directories"),
        (gitignore_evidence, ".env"),
        (gitignore_evidence, ".env.*"),
        (gitignore_evidence, ".dev.vars"),
        (gitignore_evidence, "!.env.example"),
        (gitignore_evidence, "build/"),
        (gitignore_evidence, "*.local"),
    ]
    sources = {
        "LICENSE": license_text,
        "README.md": readme,
        "docs/open-source-release.md": release_notes,
        gitignore_evidence: gitignore,
    }
    missing_markers = [
        f"{name}:{marker}"
        for name, marker in required_markers
        if marker not in sources[name]
    ]

    missing_configs = [
        f"assets/config/{flavor}/{filename}"
        for flavor in FLAVORS
        for filename in ["tenant.brand.json", "tenant.template.json", "tenant.features.json"]
        if not (root / "assets" / "config" / flavor / filename).exists()
    ]
    missing_prototypes = [
        f"test/goldens/prototypes/{flavor}_{screen_id}.png"
        for flavor in FLAVORS
        for screen_id in SCREEN_IDS
        if not (root / "test" / "goldens" / "prototypes" / f"{flavor}_{screen_id}.png").exists()
    ]

    if missing_markers or missing_configs or missing_prototypes:
        problems = missing_markers + missing_configs + missing_prototypes
        return Check(
            "mobile_open_source_release",
            "missing",
            f"Open-source release boundary is incomplete: {', '.join(problems)}",
            evidence,
        )

    return Check(
        "mobile_open_source_release",
        "passed",
        "Apache-2.0 licensed mobile template has README/docs release guidance, public sample configs, publish-safe prototype assets, ignored local build/secret files, and explicit no-secret open-source boundaries.",
        evidence,
    )


def check_mobile_open_source_package(root: Path) -> Check:
    manifest_path = root / "build" / "open-source" / "open-source-template-manifest.json"
    evidence = ["build/open-source/open-source-template-manifest.json"]
    if not manifest_path.exists():
        return Check(
            "mobile_open_source_package",
            "missing",
            "Open-source template package manifest is missing; run scripts/export_open_source_template.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "mobile_open_source_package",
            "failed",
            f"Open-source template package manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    package_path = root / str(manifest.get("packagePath", ""))
    evidence.append(rel(root, package_path))
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageName") != "short-drama-whitelabel-mobile":
        problems.append("packageName")
    if not package_path.exists():
        problems.append("missing-package")
    elif manifest.get("packageSha256") != file_sha256(package_path):
        problems.append("packageSha256")
    if manifest.get("missingRequiredEntries"):
        problems.append(f"missingRequiredEntries={manifest.get('missingRequiredEntries')!r}")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        problems.append("entries")
        entries = []
    by_path = {
        str(entry.get("path")): entry
        for entry in entries
        if isinstance(entry, dict)
    }
    required_entries = [
        ".github/workflows/mobile-flutter.yml",
        ".gitignore",
        "LICENSE",
        "README.md",
        "docs/open-source-release.md",
        "pubspec.yaml",
        "lib/main.dart",
        "scripts/capture_wysiwyg_previews.mjs",
        "scripts/export_completion_unblocker.py",
        "scripts/export_github_publish_handoff.py",
        "scripts/import_github_publication_evidence.py",
        "scripts/import_store_submission_evidence.py",
        "scripts/ios_runtime_smoke.py",
        "scripts/mobile_completion_closure.py",
        "scripts/prepare_store_submission_inputs.py",
        "assets/config/hongguo/tenant.brand.json",
        "assets/config/douyin/tenant.brand.json",
        "assets/config/hippo/tenant.brand.json",
        "assets/config/reelshort/tenant.brand.json",
        "android/app/build.gradle.kts",
        "ios/Runner/Info.plist",
        "ios/Runner/PrivacyInfo.xcprivacy",
        "ios/Runner/Runner.entitlements",
    ]
    for entry_path in required_entries:
        if entry_path not in by_path:
            problems.append(f"missing-entry:{entry_path}")
    forbidden_path_markers = [
        ".dart_tool/",
        ".gradle/",
        "Pods/",
        "build/",
        ".env",
        "Generated.xcconfig",
        "GeneratedPluginRegistrant",
        "flutter_export_environment.sh",
        "local.properties",
        "key.properties",
        ".keystore",
        ".jks",
    ]
    for entry_path in by_path:
        if any(marker in entry_path for marker in forbidden_path_markers):
            problems.append(f"forbidden-entry:{entry_path}")
    if package_path.exists():
        try:
            with zipfile.ZipFile(package_path) as archive:
                names = sorted(archive.namelist())
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        expected_prefix = "short-drama-whitelabel-mobile/"
        if not names:
            problems.append("zip-empty")
        for name in names:
            if not name.startswith(expected_prefix):
                problems.append(f"zip-prefix:{name}")
                break
        zip_entry_names = {
            name[len(expected_prefix):]
            for name in names
            if name.startswith(expected_prefix) and not name.endswith("/")
        }
        if zip_entry_names != set(by_path):
            missing_in_zip = sorted(set(by_path) - zip_entry_names)[:5]
            extra_in_zip = sorted(zip_entry_names - set(by_path))[:5]
            problems.append(f"zip-manifest-mismatch:missing={missing_in_zip},extra={extra_in_zip}")
    if len(by_path) < 120:
        problems.append(f"entryCount-too-low:{len(by_path)}")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
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
        "-----begin private key-----",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "mobile_open_source_package",
            "failed",
            f"Open-source template package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "mobile_open_source_package",
        "passed",
        "GitHub-ready open-source template zip and manifest include publish-safe source, docs, synthetic assets, native scaffolding, and CI metadata while excluding build outputs, generated files, signing material, and secret values.",
        sorted(set(evidence)),
    )


def check_ios_static_release_config(root: Path) -> Check:
    evidence = [
        "ios/Runner/Info.plist",
        "ios/Runner/PrivacyInfo.xcprivacy",
        "ios/Runner/Runner.entitlements",
        "ios/Runner.xcodeproj/project.pbxproj",
        "ios/Podfile",
        "ios/Podfile.lock",
        "ios/Flutter/Debug.xcconfig",
        "ios/Flutter/Profile.xcconfig",
        "ios/Flutter/Release.xcconfig",
        "ios/Flutter/WhitelabelDefaults.xcconfig",
    ]
    problems: list[str] = []

    info_path = root / "ios" / "Runner" / "Info.plist"
    privacy_path = root / "ios" / "Runner" / "PrivacyInfo.xcprivacy"
    entitlements_path = root / "ios" / "Runner" / "Runner.entitlements"
    pbx_path = root / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    podfile_path = root / "ios" / "Podfile"
    podfile_lock_path = root / "ios" / "Podfile.lock"
    for path in [
        info_path,
        privacy_path,
        entitlements_path,
        pbx_path,
        podfile_path,
        podfile_lock_path,
    ]:
        if not path.exists():
            problems.append(f"missing-{rel(root, path)}")

    if info_path.exists():
        try:
            info = plistlib.loads(info_path.read_bytes())
        except Exception as error:
            problems.append(f"Info.plist-invalid:{error}")
        else:
            expected_info = {
                "CFBundleDisplayName": "$(APP_DISPLAY_NAME)",
                "CFBundleName": "$(APP_DISPLAY_NAME)",
                "CFBundleIdentifier": "$(PRODUCT_BUNDLE_IDENTIFIER)",
                "CFBundleShortVersionString": "$(FLUTTER_BUILD_NAME)",
                "CFBundleVersion": "$(FLUTTER_BUILD_NUMBER)",
            }
            for key, expected in expected_info.items():
                if info.get(key) != expected:
                    problems.append(f"Info.plist:{key}={info.get(key)!r}")
            url_schemes = [
                scheme
                for entry in info.get("CFBundleURLTypes", [])
                for scheme in entry.get("CFBundleURLSchemes", [])
            ]
            if "$(APP_DEEP_LINK_SCHEME)" not in url_schemes:
                problems.append("Info.plist:missing-APP_DEEP_LINK_SCHEME")
            if info.get("LSRequiresIPhoneOS") is not True:
                problems.append("Info.plist:LSRequiresIPhoneOS")

    if privacy_path.exists():
        try:
            privacy = plistlib.loads(privacy_path.read_bytes())
        except Exception as error:
            problems.append(f"PrivacyInfo.xcprivacy-invalid:{error}")
        else:
            if privacy.get("NSPrivacyTracking") is not False:
                problems.append("PrivacyInfo.xcprivacy:NSPrivacyTracking-must-be-false")
            for key in [
                "NSPrivacyTrackingDomains",
                "NSPrivacyCollectedDataTypes",
                "NSPrivacyAccessedAPITypes",
            ]:
                if not isinstance(privacy.get(key), list):
                    problems.append(f"PrivacyInfo.xcprivacy:{key}-must-be-array")
            if privacy.get("NSPrivacyTrackingDomains"):
                problems.append("PrivacyInfo.xcprivacy:tracking-domains-must-be-empty")

    if entitlements_path.exists():
        try:
            entitlements = plistlib.loads(entitlements_path.read_bytes())
        except Exception as error:
            problems.append(f"Runner.entitlements-invalid:{error}")
        else:
            apple_sign_in = entitlements.get("com.apple.developer.applesignin")
            if not isinstance(apple_sign_in, list) or "Default" not in apple_sign_in:
                problems.append("Runner.entitlements:missing-sign-in-with-apple")

    pbx_text = read_text(pbx_path) if pbx_path.exists() else ""
    if pbx_text:
        for marker in [
            'PRODUCT_BUNDLE_IDENTIFIER = "$(APP_BUNDLE_IDENTIFIER)"',
            "PrivacyInfo.xcprivacy",
            "PrivacyInfo.xcprivacy in Resources",
            "Runner.entitlements",
            "CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements",
            "baseConfigurationReference = 9740EEB21CF90195004384FC /* Debug.xcconfig */",
            "baseConfigurationReference = 7AFA3C8E1D35360C0083082E /* Release.xcconfig */",
            "baseConfigurationReference = 7AFA3C8F1D35360C0083082E /* Profile.xcconfig */",
        ]:
            if marker not in pbx_text:
                problems.append(f"project.pbxproj:missing-{marker}")
        if "ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;" in pbx_text:
            problems.append("project.pbxproj:hardcoded-AppIcon-overrides-flavor-xcconfig")

    podfile = read_text(podfile_path) if podfile_path.exists() else ""
    for marker in [
        "platform :ios, '13.0'",
        "flutter_ios_podfile_setup",
        "flutter_install_all_ios_pods",
        "flutter_additional_ios_build_settings",
    ]:
        if podfile and marker not in podfile:
            problems.append(f"Podfile:missing-{marker}")

    for config_name in ["Debug", "Profile", "Release"]:
        config_path = root / "ios" / "Flutter" / f"{config_name}.xcconfig"
        if not config_path.exists():
            problems.append(f"missing-{rel(root, config_path)}")
            continue
        text = read_text(config_path)
        if '#include "Generated.xcconfig"' not in text:
            problems.append(f"{config_name}.xcconfig:missing-Generated-include")
        if '#include "WhitelabelDefaults.xcconfig"' not in text:
            problems.append(f"{config_name}.xcconfig:missing-WhitelabelDefaults-include")
        pods_include = (
            f'#include? "../Pods/Target Support Files/Pods-Runner/'
            f'Pods-Runner.{config_name.lower()}.xcconfig"'
        )
        if pods_include not in text:
            problems.append(f"{config_name}.xcconfig:missing-Pods-include")

    defaults = root / "ios" / "Flutter" / "WhitelabelDefaults.xcconfig"
    if defaults.exists() and '#include "Coolshow.xcconfig"' not in read_text(defaults):
        problems.append("WhitelabelDefaults.xcconfig:missing-default-flavor-include")

    for flavor, expected in FLAVORS.items():
        config_name = flavor.capitalize()
        config_path = root / "ios" / "Flutter" / f"{config_name}.xcconfig"
        scheme_path = (
            root
            / "ios"
            / "Runner.xcodeproj"
            / "xcshareddata"
            / "xcschemes"
            / f"{flavor}.xcscheme"
        )
        icon_contents_path = (
            root
            / "ios"
            / "Runner"
            / "Assets.xcassets"
            / f"AppIcon-{flavor}.appiconset"
            / "Contents.json"
        )
        evidence.extend([rel(root, config_path), rel(root, scheme_path), rel(root, icon_contents_path)])

        config = read_xcconfig(config_path)
        expected_config = {
            "APP_DISPLAY_NAME": expected["appName"],
            "APP_BUNDLE_IDENTIFIER": expected["applicationId"],
            "APP_DEEP_LINK_SCHEME": expected["deepLinkScheme"],
            "ASSETCATALOG_COMPILER_APPICON_NAME": f"AppIcon-{flavor}",
            "DART_DEFINES": f"$(inherited),{expected['dartDefine']}",
        }
        for key, value in expected_config.items():
            if config.get(key) != value:
                problems.append(f"{config_name}.xcconfig:{key}={config.get(key)!r}")

        if not scheme_path.exists():
            problems.append(f"missing-{rel(root, scheme_path)}")
        else:
            scheme = read_text(scheme_path)
            required_scheme_markers = [
                'BlueprintName = "Runner"',
                'BuildableName = "Runner.app"',
                f"Flutter/{config_name}.xcconfig",
                "key = \"APP_FLAVOR\"",
                f"value = \"{flavor}\"",
                'buildConfiguration = "Debug"',
                'buildConfiguration = "Profile"',
                'buildConfiguration = "Release"',
            ]
            for marker in required_scheme_markers:
                if marker not in scheme:
                    problems.append(f"{flavor}.xcscheme:missing-{marker}")

        problems.extend(
            f"{flavor}:appicon:{problem}"
            for problem in ios_app_icon_problems(icon_contents_path)
        )

    if problems:
        return Check(
            "ios_static_release_config",
            "failed",
            f"iOS static release configuration problems: {', '.join(problems)}",
            evidence,
        )

    return Check(
        "ios_static_release_config",
        "passed",
        "iOS plist, privacy manifest, Sign in with Apple entitlements, Podfile, build configurations, flavor schemes, bundle ids, URL schemes, Dart defines, and AppIcon assets are aligned without embedding tenant secrets.",
        evidence,
    )


def read_xcconfig(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ios_app_icon_problems(contents_path: Path) -> list[str]:
    if not contents_path.exists():
        return [f"missing-{contents_path.name}"]
    try:
        contents = json.loads(read_text(contents_path))
    except json.JSONDecodeError as error:
        return [f"invalid-Contents.json:{error}"]

    icon_dir = contents_path.parent
    images = contents.get("images")
    if not isinstance(images, list):
        return ["Contents.json:images-not-list"]

    filenames = {
        image.get("filename")
        for image in images
        if isinstance(image, dict) and image.get("filename")
    }
    required_sizes = {
        "Icon-App-1024x1024@1x.png": (1024, 1024),
        "Icon-App-60x60@2x.png": (120, 120),
        "Icon-App-60x60@3x.png": (180, 180),
        "Icon-App-83.5x83.5@2x.png": (167, 167),
    }
    problems: list[str] = []
    for filename, expected_size in required_sizes.items():
        if filename not in filenames:
            problems.append(f"Contents.json:missing-{filename}")
            continue
        path = icon_dir / filename
        size = png_dimensions(path)
        if size != expected_size:
            problems.append(f"{filename}:size={size!r},expected={expected_size!r}")
    return problems


def png_dimensions(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    with path.open("rb") as source:
        header = source.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def load_release_manifest(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = root / "build" / "release-manifests" / "mobile-artifacts.json"
    if not path.exists():
        return None, "build/release-manifests/mobile-artifacts.json is missing"
    try:
        return json.loads(read_text(path)), None
    except json.JSONDecodeError as error:
        return None, f"release manifest is invalid JSON: {error}"


def write_store_handoff_manifest(root: Path) -> Path:
    path = root / "build" / "release-handoff" / "mobile-store-handoff.json"
    release_manifest, _ = load_release_manifest(root)
    release_artifacts = android_release_manifest_artifacts(release_manifest) if release_manifest else []
    release_artifacts_by_flavor: dict[str, list[dict[str, Any]]] = {}
    for artifact in release_artifacts:
        release_artifacts_by_flavor.setdefault(str(artifact.get("flavor")), []).append(artifact)

    def public_config(flavor: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        config_dir = root / "assets" / "config" / flavor
        return (
            json.loads(read_text(config_dir / "tenant.brand.json")),
            json.loads(read_text(config_dir / "tenant.template.json")),
            json.loads(read_text(config_dir / "tenant.features.json")),
        )

    def flavor_entry(flavor: str) -> dict[str, Any]:
        brand, template, features = public_config(flavor)
        defaults = STORE_SUBMISSION_FLAVORS[flavor]
        expected = {
            "appName": str(defaults["appName"]),
            "applicationId": str(defaults["applicationId"]),
            "deepLinkScheme": STORE_HANDOFF_DEEP_LINK_SCHEMES[flavor],
            "styleTemplate": str(template.get("styleTemplate", flavor)),
        }
        artifacts = release_artifacts_by_flavor.get(flavor, [])
        store_compliance_mode = template.get("storeComplianceMode")
        configured_payments = [
            str(provider)
            for provider in template.get("consumerPaymentProviders", [])
            if str(provider) in PAYMENT_PROVIDER_ORDER
        ]
        allowed_payments = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(
            str(store_compliance_mode),
            set(),
        )
        visible_payments = [
            provider
            for provider in PAYMENT_PROVIDER_ORDER
            if provider in configured_payments and provider in allowed_payments
        ]
        supported_locales = list(brand.get("supportedLocales", []))
        payment_visibility = {
            "storeComplianceMode": store_compliance_mode,
            "configuredProviders": configured_payments,
            "appVisibleProviders": visible_payments,
            "hiddenByComplianceProviders": [
                provider
                for provider in configured_payments
                if provider not in visible_payments
            ],
            "externalPaymentsAllowed": store_compliance_mode
            in {"android_direct", "regional_user_choice"},
        }
        artifact_paths = {
            "androidReleaseApk": next(
                (
                    artifact.get("path")
                    for artifact in artifacts
                    if artifact.get("packageType") == "apk"
                ),
                None,
            ),
            "androidReleaseAppBundle": next(
                (
                    artifact.get("path")
                    for artifact in artifacts
                    if artifact.get("packageType") == "appbundle"
                ),
                None,
            ),
        }
        return {
            "flavor": flavor,
            "appName": expected["appName"],
            "applicationId": expected["applicationId"],
            "bundleId": expected["applicationId"],
            "styleTemplate": expected["styleTemplate"],
            "storeComplianceMode": store_compliance_mode,
            "deepLinkScheme": expected["deepLinkScheme"],
            "apiAdapterBase": brand.get("apiAdapterBase"),
            "authProviders": template.get("authProviders", []),
            "consumerPaymentProviders": template.get("consumerPaymentProviders", []),
            "paymentVisibility": payment_visibility,
            "authCallbackRegistration": auth_callback_registration_payload(
                expected["deepLinkScheme"],
                template,
            ),
            "storeProductRegistration": store_product_registration_payload(
                payment_visibility,
            ),
            "nativeCapabilityRegistration": native_capability_registration_payload(
                flavor,
                expected,
                template,
                payment_visibility,
            ),
            "storeReviewDeclarations": store_review_declarations_payload(
                template,
                features,
                payment_visibility,
            ),
            "distributionChannelReadiness": distribution_channel_readiness_payload(
                flavor,
                payment_visibility,
                artifact_paths,
            ),
            "storeSubmission": {
                "tenantEvidenceInputPath": f"build/store-submission-evidence/flavors/{flavor}.input.json",
                "requiredChecklistFlags": [
                    *STORE_SUBMISSION_BASE_REQUIRED_FLAGS,
                    *STORE_SUBMISSION_CHANNEL_REQUIRED_FLAGS[
                        STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
                    ],
                ],
                "allowedStatuses": sorted(
                    STORE_SUBMISSION_ALLOWED_STATUSES_BY_CHANNEL[
                        STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
                    ],
                ),
                "listing": {
                    "displayName": expected["appName"],
                    "defaultLocale": supported_locales[0] if supported_locales else "en-US",
                    "supportedLocales": supported_locales,
                    "shortDescription": LISTING_COPY_BY_TEMPLATE.get(
                        expected["styleTemplate"],
                        "Short drama episodes with tenant-managed catalog and wallet flows.",
                    ),
                    "supportUrl": brand.get("customerServiceUrl"),
                    "termsUrl": brand.get("termsUrl"),
                    "privacyUrl": brand.get("privacyUrl"),
                },
                "reviewNotes": [
                    "Template is style-inspired only and does not include copied third-party marks or screenshots.",
                    "Playback authorization, payment verification, and wallet crediting stay on Tenant Edge.",
                    "Payment entry visibility is filtered by storeComplianceMode before app handoff.",
                ],
                "localizedListings": store_submission_localized_listings(
                    brand,
                    supported_locales,
                ),
                "dataSafety": {
                    "notes": "tenant must answer store questionnaires using final SDKs, regions, legal URLs, and enabled payment providers",
                    "templateDisclosures": {
                        "accountCreation": bool(template.get("authProviders")),
                        "accountDeletion": bool(features.get("enableAccountDeletion")),
                        "purchases": bool(payment_visibility.get("appVisibleProviders")),
                        "externalPaymentsAllowed": bool(
                            payment_visibility.get("externalPaymentsAllowed"),
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
                "screenshotAssets": store_submission_screenshot_assets(root, flavor),
            },
            "legal": {
                "customerServiceUrl": brand.get("customerServiceUrl"),
                "termsUrl": brand.get("termsUrl"),
                "privacyUrl": brand.get("privacyUrl"),
            },
            "buildCommands": {
                "androidReleaseApk": f"./scripts/build_flavor.sh {flavor} android release apk",
                "androidReleaseAppBundle": f"./scripts/build_flavor.sh {flavor} android release appbundle",
                "iosUnsignedRelease": f"./scripts/build_flavor.sh {flavor} ios release",
            },
            "releaseArtifacts": [
                {
                    "packageType": artifact.get("packageType"),
                    "path": artifact.get("path"),
                    "sha256": artifact.get("sha256"),
                    "sizeBytes": artifact.get("sizeBytes"),
                }
                for artifact in artifacts
            ],
            "artifactPaths": {
                key: value
                for key, value in artifact_paths.items()
                if value
            },
            "secretPolicy": "Flutter and native clients must not contain tenant credentials.",
        }

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "secretBoundary": (
            "Public tenant handoff metadata only. Tenant signing keys, OAuth "
            "credentials, payment provider credentials, Cloudflare tokens, webhook "
            "credentials, bank credentials, and crypto keys are never included."
        ),
        "tenantOwnedChecklist": {
            "apple": [
                "select full Xcode and configure Apple Team, certificates, and profiles",
                "enable Sign in with Apple when Google or Facebook login is enabled",
                "review PrivacyInfo.xcprivacy, legal links, support URL, and content rating",
            ],
            "googlePlay": [
                "replace template signing with tenant Play App Signing setup",
                "configure Play Billing or approved user-choice billing by region",
                "review store listing, privacy, support, content rating, and data safety",
            ],
            "androidDirect": [
                "replace template signing outside the repository",
                "configure tenant-hosted checkout, wallet, bank, or crypto providers in Tenant Edge",
                "publish legal, support, refund, and payment-dispute handling pages",
            ],
        },
        "flavors": [
            flavor_entry(flavor)
            for flavor in STORE_SUBMISSION_FLAVORS
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def check_android_release_artifacts(root: Path) -> Check:
    manifest, error = load_release_manifest(root)
    evidence = ["build/release-manifests/mobile-artifacts.json"]
    if error or manifest is None:
        return Check("android_release_artifacts", "missing", error or "missing manifest", evidence)

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return Check(
            "android_release_artifacts",
            "failed",
            "release manifest artifacts must be a list",
            evidence,
        )

    missing: list[str] = []
    latest_input = latest_android_rebuild_input(root)
    for flavor, expected in FLAVORS.items():
        for package_type in ["apk", "appbundle"]:
            matches = [
                artifact
                for artifact in artifacts
                if artifact.get("flavor") == flavor
                and artifact.get("platform") == "android"
                and artifact.get("mode") == "release"
                and artifact.get("packageType") == package_type
                and artifact.get("applicationId") == expected["applicationId"]
                and artifact.get("styleTemplate") == expected["styleTemplate"]
            ]
            if not matches:
                missing.append(f"{flavor}:{package_type}")
                continue
            artifact_path = root / str(matches[0].get("path", ""))
            evidence.append(rel(root, artifact_path))
            if not artifact_path.exists():
                missing.append(f"{flavor}:{package_type}:file")
                continue
            if latest_input and artifact_path.stat().st_mtime < latest_input.stat().st_mtime:
                missing.append(
                    f"{flavor}:{package_type}:stale-before-{rel(root, latest_input)}",
                )
    if missing:
        return Check(
            "android_release_artifacts",
            "missing",
            f"Missing Android release manifest/file evidence: {', '.join(missing)}",
            evidence,
        )
    return Check(
        "android_release_artifacts",
        "passed",
        "Release manifest contains Android release APK and AAB evidence for all five flavors.",
        evidence,
    )


def android_release_manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    return [
        artifact
        for artifact in artifacts
        if artifact.get("platform") == "android"
        and artifact.get("mode") == "release"
        and artifact.get("packageType") in {"apk", "appbundle"}
    ]


def check_android_package_structure(
    root: Path,
    manifest: dict[str, Any] | None = None,
) -> Check:
    if manifest is None:
        manifest, error = load_release_manifest(root)
        if error or manifest is None:
            return Check(
                "android_package_structure",
                "missing",
                error or "missing release manifest",
                ["build/release-manifests/mobile-artifacts.json"],
            )

    artifacts = android_release_manifest_artifacts(manifest)
    evidence = [
        rel(root, root / str(artifact.get("path", "")))
        for artifact in artifacts
        if artifact.get("path")
    ]
    if not artifacts:
        return Check(
            "android_package_structure",
            "missing",
            "No Android release APK/AAB artifacts are listed in the release manifest.",
            ["build/release-manifests/mobile-artifacts.json"],
        )

    problems: list[str] = []
    for artifact in artifacts:
        flavor = str(artifact.get("flavor", "unknown"))
        package_type = str(artifact.get("packageType", "unknown"))
        path = root / str(artifact.get("path", ""))
        if not path.exists():
            problems.append(f"{flavor}:{package_type}:missing-file")
            continue
        if not zipfile.is_zipfile(path):
            problems.append(f"{flavor}:{package_type}:not-zip")
            continue
        problems.extend(
            f"{flavor}:{package_type}:{problem}"
            for problem in android_package_structure_problems(
                path,
                flavor=flavor,
                package_type=package_type,
            )
        )

    if problems:
        return Check(
            "android_package_structure",
            "failed",
            f"Android package structure problems: {', '.join(problems)}",
            evidence,
        )

    return Check(
        "android_package_structure",
        "passed",
        "Release APK/AAB packages contain Android manifests, Flutter assets, tenant config assets, and compiled Flutter runtime libraries.",
        evidence,
    )


def android_package_structure_problems(
    artifact: Path,
    *,
    flavor: str,
    package_type: str,
) -> list[str]:
    with zipfile.ZipFile(artifact) as package:
        names = set(package.namelist())

    if package_type == "apk":
        required = [
            "AndroidManifest.xml",
            "assets/flutter_assets/AssetManifest.bin",
            f"assets/flutter_assets/assets/config/{flavor}/tenant.brand.json",
            f"assets/flutter_assets/assets/config/{flavor}/tenant.template.json",
        ]
        libapp_prefix = "lib/"
        libflutter_prefix = "lib/"
    else:
        required = [
            "BundleConfig.pb",
            "base/manifest/AndroidManifest.xml",
            "base/assets/flutter_assets/AssetManifest.bin",
            f"base/assets/flutter_assets/assets/config/{flavor}/tenant.brand.json",
            f"base/assets/flutter_assets/assets/config/{flavor}/tenant.template.json",
        ]
        libapp_prefix = "base/lib/"
        libflutter_prefix = "base/lib/"

    problems = [f"missing-{entry}" for entry in required if entry not in names]
    if not any(name.startswith(libapp_prefix) and name.endswith("/libapp.so") for name in names):
        problems.append("missing-libapp.so")
    if not any(
        name.startswith(libflutter_prefix) and name.endswith("/libflutter.so")
        for name in names
    ):
        problems.append("missing-libflutter.so")
    return problems


def check_android_apk_badging(root: Path) -> Check:
    manifest, error = load_release_manifest(root)
    if error or manifest is None:
        return Check(
            "android_apk_badging",
            "missing",
            error or "missing release manifest",
            ["build/release-manifests/mobile-artifacts.json"],
        )

    aapt = resolve_aapt()
    if aapt is None:
        return Check(
            "android_apk_badging",
            "blocked",
            "Android build-tools aapt is not available to inspect release APK badging.",
            ["aapt"],
        )

    apk_artifacts = [
        artifact
        for artifact in android_release_manifest_artifacts(manifest)
        if artifact.get("packageType") == "apk"
    ]
    evidence = [rel(root, root / str(artifact.get("path", ""))) for artifact in apk_artifacts]
    missing: list[str] = []
    for flavor, expected in FLAVORS.items():
        matches = [
            artifact
            for artifact in apk_artifacts
            if artifact.get("flavor") == flavor
        ]
        if not matches:
            missing.append(f"{flavor}:missing-release-apk")
            continue
        apk = root / str(matches[0].get("path", ""))
        if not apk.exists():
            missing.append(f"{flavor}:missing-file")
            continue
        code, output = command_output([str(aapt), "dump", "badging", str(apk)])
        if code != 0:
            missing.append(f"{flavor}:aapt-failed")
            continue
        badging = parse_apk_badging(output)
        expected_values = {
            "packageName": expected["applicationId"],
            "applicationLabel": expected["appName"],
            "versionCode": "1",
            "versionName": "0.1.0",
            "minSdkVersion": "24",
            "targetSdkVersion": "36",
        }
        for key, expected_value in expected_values.items():
            if badging.get(key) != expected_value:
                missing.append(
                    f"{flavor}:{key}={badging.get(key)!r},expected={expected_value!r}",
                )
        if "android.permission.INTERNET" not in badging.get("permissions", []):
            missing.append(f"{flavor}:missing-INTERNET-permission")

    if missing:
        return Check(
            "android_apk_badging",
            "failed",
            f"Android release APK badging mismatch: {', '.join(missing)}",
            evidence,
        )

    return Check(
        "android_apk_badging",
        "passed",
        "Release APK badging matches flavor package ids, app names, version, SDK levels, and network permission.",
        evidence,
    )


def check_android_runtime_smoke(root: Path) -> Check | None:
    smoke_path = root / "build" / "runtime-smoke" / "android-runtime-smoke.json"
    if not smoke_path.exists():
        return None
    evidence = [rel(root, smoke_path)]
    try:
        smoke = json.loads(read_text(smoke_path))
    except json.JSONDecodeError as error:
        return Check(
            "android_runtime_smoke",
            "failed",
            f"Android runtime smoke evidence is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if smoke.get("result") != "passed":
        problems.append(f"result={smoke.get('result')!r}")
    if smoke.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    runs = smoke.get("runs")
    if not isinstance(runs, list):
        problems.append("runs-not-list")
        runs = []
    by_flavor = {
        str(run.get("flavor")): run
        for run in runs
        if isinstance(run, dict)
    }
    for flavor, expected in FLAVORS.items():
        run = by_flavor.get(flavor)
        if not isinstance(run, dict):
            problems.append(f"{flavor}:missing-run")
            continue
        if run.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId={run.get('applicationId')!r}")
        if run.get("installResult") != "passed":
            problems.append(f"{flavor}:installResult={run.get('installResult')!r}")
        if run.get("launchResult") != "passed":
            problems.append(f"{flavor}:launchResult={run.get('launchResult')!r}")
        if not str(run.get("processPid", "")).strip():
            problems.append(f"{flavor}:missing-processPid")
        apk_path = root / str(run.get("apkPath", ""))
        screenshot_path = root / str(run.get("screenshotPath", ""))
        evidence.extend([rel(root, apk_path), rel(root, screenshot_path)])
        if not apk_path.exists():
            problems.append(f"{flavor}:missing-apk")
        elif run.get("apkSha256") != file_sha256(apk_path):
            problems.append(f"{flavor}:apkSha256")
        if not screenshot_path.exists():
            problems.append(f"{flavor}:missing-screenshot")
        else:
            if png_dimensions(screenshot_path) is None:
                problems.append(f"{flavor}:screenshot-not-png")
            if screenshot_path.stat().st_size < 1024:
                problems.append(f"{flavor}:screenshot-too-small")
            if run.get("screenshotSha256") != file_sha256(screenshot_path):
                problems.append(f"{flavor}:screenshotSha256")
    serialized = json.dumps(smoke, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "android_runtime_smoke",
            "failed",
            f"Android runtime smoke evidence problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "android_runtime_smoke",
        "passed",
        "Android release APKs were installed and launched on an Android device/emulator for all five flavors, with launch screenshots and package hashes recorded.",
        sorted(set(evidence)),
    )


def check_ios_runtime_smoke(root: Path) -> Check | None:
    smoke_path = root / "build" / "runtime-smoke" / "ios-runtime-smoke.json"
    if not smoke_path.exists():
        return None
    evidence = [rel(root, smoke_path)]
    try:
        smoke = json.loads(read_text(smoke_path))
    except json.JSONDecodeError as error:
        return Check(
            "ios_runtime_smoke",
            "failed",
            f"iOS runtime smoke evidence is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if smoke.get("result") != "passed":
        problems.append(f"result={smoke.get('result')!r}")
    if smoke.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    device = smoke.get("device")
    if not isinstance(device, dict):
        problems.append("device")
    elif device.get("state") != "Booted":
        problems.append(f"device.state={device.get('state')!r}")
    runs = smoke.get("runs")
    if not isinstance(runs, list):
        problems.append("runs-not-list")
        runs = []
    by_flavor = {
        str(run.get("flavor")): run
        for run in runs
        if isinstance(run, dict)
    }
    for flavor, expected in FLAVORS.items():
        run = by_flavor.get(flavor)
        if not isinstance(run, dict):
            problems.append(f"{flavor}:missing-run")
            continue
        if run.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId={run.get('applicationId')!r}")
        if run.get("installResult") != "passed":
            problems.append(f"{flavor}:installResult={run.get('installResult')!r}")
        if run.get("launchResult") != "passed":
            problems.append(f"{flavor}:launchResult={run.get('launchResult')!r}")
        if not str(run.get("processPid", "")).strip():
            problems.append(f"{flavor}:missing-processPid")
        app_path = root / str(run.get("appPath", ""))
        screenshot_path = root / str(run.get("screenshotPath", ""))
        evidence.extend([rel(root, app_path), rel(root, screenshot_path)])
        if not app_path.exists():
            problems.append(f"{flavor}:missing-app")
        elif not app_path.is_dir():
            problems.append(f"{flavor}:app-not-dir")
        if not isinstance(run.get("appSizeBytes"), int) or run.get("appSizeBytes", 0) <= 0:
            problems.append(f"{flavor}:appSizeBytes")
        if not screenshot_path.exists():
            problems.append(f"{flavor}:missing-screenshot")
        else:
            if png_dimensions(screenshot_path) is None:
                problems.append(f"{flavor}:screenshot-not-png")
            if screenshot_path.stat().st_size < 1024:
                problems.append(f"{flavor}:screenshot-too-small")
            if run.get("screenshotSha256") != file_sha256(screenshot_path):
                problems.append(f"{flavor}:screenshotSha256")
    serialized = json.dumps(smoke, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "ios_runtime_smoke",
            "failed",
            f"iOS runtime smoke evidence problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "ios_runtime_smoke",
        "passed",
        "iOS simulator builds were installed and launched on a booted Simulator for all five flavors, with launch screenshots and bundle metadata recorded.",
        sorted(set(evidence)),
    )


def check_ios_build_matrix(root: Path) -> Check:
    matrix_path = root / "build" / "ios-build-matrix" / "ios-build-matrix.json"
    evidence = ["build/ios-build-matrix/ios-build-matrix.json"]
    if not matrix_path.exists():
        return Check(
            "ios_build_matrix",
            "blocked",
            "iOS build matrix evidence has not been generated; run scripts/ios_build_matrix.py on a machine with full Xcode.",
            evidence,
        )
    try:
        matrix = json.loads(read_text(matrix_path))
    except json.JSONDecodeError as error:
        return Check(
            "ios_build_matrix",
            "failed",
            f"iOS build matrix evidence is invalid JSON: {error}",
            evidence,
        )

    result = matrix.get("result")
    if result == "blocked":
        blockers = matrix.get("blockers")
        detail = "; ".join(str(blocker) for blocker in blockers) if isinstance(blockers, list) else "iOS build matrix is blocked."
        return Check(
            "ios_build_matrix",
            "blocked",
            detail,
            evidence,
        )
    if result != "passed":
        runs = matrix.get("runs") if isinstance(matrix.get("runs"), list) else []
        failed_runs = [
            f"{run.get('flavor')}:{run.get('mode')}:{run.get('buildResult')}"
            for run in runs
            if isinstance(run, dict) and run.get("buildResult") != "passed"
        ]
        return Check(
            "ios_build_matrix",
            "failed",
            f"iOS build matrix did not pass: result={result!r}; failed={', '.join(failed_runs) or 'unknown'}",
            evidence,
        )

    problems: list[str] = []
    if matrix.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    required_flavors = list(FLAVORS)
    required_modes = ["debug", "release"]
    if matrix.get("requiredFlavors") != required_flavors:
        problems.append("requiredFlavors")
    if matrix.get("requiredModes") != required_modes:
        problems.append("requiredModes")
    runs = matrix.get("runs")
    if not isinstance(runs, list):
        problems.append("runs-not-list")
        runs = []
    by_key = {
        (str(run.get("flavor")), str(run.get("mode"))): run
        for run in runs
        if isinstance(run, dict)
    }
    for flavor, expected in FLAVORS.items():
        for mode in required_modes:
            run = by_key.get((flavor, mode))
            if not isinstance(run, dict):
                problems.append(f"{flavor}:{mode}:missing-run")
                continue
            if run.get("platform") != "ios":
                problems.append(f"{flavor}:{mode}:platform={run.get('platform')!r}")
            if run.get("applicationId") != expected["applicationId"]:
                problems.append(f"{flavor}:{mode}:applicationId={run.get('applicationId')!r}")
            if run.get("appName") != expected["appName"]:
                problems.append(f"{flavor}:{mode}:appName={run.get('appName')!r}")
            if run.get("buildResult") != "passed" or run.get("exitCode") != 0:
                problems.append(f"{flavor}:{mode}:buildResult={run.get('buildResult')!r}")
            command = run.get("command")
            if command != ["./scripts/build_flavor.sh", flavor, "ios", mode]:
                problems.append(f"{flavor}:{mode}:command")
            app = run.get("app")
            if not isinstance(app, dict):
                problems.append(f"{flavor}:{mode}:missing-app")
                continue
            if app.get("bundleIdentifier") != expected["applicationId"]:
                problems.append(f"{flavor}:{mode}:bundleIdentifier={app.get('bundleIdentifier')!r}")
            if app.get("displayName") != expected["appName"]:
                problems.append(f"{flavor}:{mode}:displayName={app.get('displayName')!r}")
            if not isinstance(app.get("appSizeBytes"), int) or app.get("appSizeBytes", 0) <= 0:
                problems.append(f"{flavor}:{mode}:appSizeBytes")
            snapshot_path = root / str(app.get("infoSnapshotPath", ""))
            evidence.append(rel(root, snapshot_path))
            if not snapshot_path.exists():
                problems.append(f"{flavor}:{mode}:missing-info-snapshot")
            elif app.get("infoSnapshotSha256") != file_sha256(snapshot_path):
                problems.append(f"{flavor}:{mode}:infoSnapshotSha256")

    marker_hits = matrix.get("forbiddenMarkerHits")
    if marker_hits:
        problems.append(f"forbiddenMarkerHits={marker_hits!r}")
    serialized = json.dumps(matrix, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "ios_build_matrix",
            "failed",
            f"iOS build matrix evidence problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "ios_build_matrix",
        "passed",
        "Unsigned iOS debug and release builds passed for all five template flavors, with per-flavor bundle metadata snapshots recorded.",
        sorted(set(evidence)),
    )


def check_ios_ci_artifact_evidence(root: Path) -> Check:
    evidence_path = root / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
    evidence = ["build/ios-ci-evidence/ios-ci-artifacts.json"]
    if not evidence_path.exists():
        return Check(
            "ios_ci_artifact_evidence",
            "blocked",
            "Downloaded GitHub Actions unsigned iOS artifacts have not been imported; run scripts/download_ios_ci_artifacts.py --repo <owner/repo> --run-id <run-id>, or let the ios-ci-evidence GitHub Actions job upload mobile-ios-ci-artifact-evidence.",
            evidence,
        )
    try:
        report = json.loads(read_text(evidence_path))
    except json.JSONDecodeError as error:
        return Check(
            "ios_ci_artifact_evidence",
            "failed",
            f"iOS CI artifact evidence is invalid JSON: {error}",
            evidence,
        )

    result = report.get("result")
    if result == "blocked":
        missing = report.get("missingFlavors")
        detail = (
            "Downloaded GitHub Actions unsigned iOS artifacts are missing for: "
            + ", ".join(str(item) for item in missing)
            if isinstance(missing, list) and missing
            else "Downloaded GitHub Actions unsigned iOS artifacts are not available."
        )
        return Check("ios_ci_artifact_evidence", "blocked", detail, evidence)
    if result != "passed":
        return Check(
            "ios_ci_artifact_evidence",
            "failed",
            f"iOS CI artifact evidence did not pass: result={result!r}",
            evidence,
        )

    problems: list[str] = []
    if report.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if report.get("requiredFlavors") != list(FLAVORS):
        problems.append("requiredFlavors")
    runs = report.get("runs")
    if not isinstance(runs, list):
        problems.append("runs-not-list")
        runs = []
    by_flavor = {
        str(run.get("flavor")): run
        for run in runs
        if isinstance(run, dict)
    }
    for flavor, expected in FLAVORS.items():
        run = by_flavor.get(flavor)
        if not isinstance(run, dict):
            problems.append(f"{flavor}:missing-run")
            continue
        if run.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if run.get("appName") != expected["appName"]:
            problems.append(f"{flavor}:appName")
        if run.get("artifactName") != f"mobile-{flavor}-ios-unsigned":
            problems.append(f"{flavor}:artifactName")
        if run.get("importResult") != "passed":
            problems.append(f"{flavor}:importResult")
        app = run.get("app")
        if not isinstance(app, dict):
            problems.append(f"{flavor}:app")
            continue
        if app.get("bundleIdentifier") != expected["applicationId"]:
            problems.append(f"{flavor}:bundleIdentifier")
        if app.get("displayName") != expected["appName"]:
            problems.append(f"{flavor}:displayName")
        if app.get("source") != "github_actions_unsigned_artifact":
            problems.append(f"{flavor}:source")
        if not isinstance(app.get("appSizeBytes"), int) or app.get("appSizeBytes", 0) <= 0:
            problems.append(f"{flavor}:appSizeBytes")
        snapshot_path = root / str(app.get("infoSnapshotPath", ""))
        evidence.append(rel(root, snapshot_path))
        if not snapshot_path.exists():
            problems.append(f"{flavor}:missing-info-snapshot")
        elif app.get("infoSnapshotSha256") != file_sha256(snapshot_path):
            problems.append(f"{flavor}:infoSnapshotSha256")

    if report.get("forbiddenMarkerHits"):
        problems.append(f"forbiddenMarkerHits={report.get('forbiddenMarkerHits')!r}")
    serialized = json.dumps(report, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "ios_ci_artifact_evidence",
            "failed",
            f"iOS CI artifact evidence problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "ios_ci_artifact_evidence",
        "passed",
        "Downloaded GitHub Actions unsigned iOS artifacts were imported for all five flavors, with bundle metadata snapshots and no-secret boundaries recorded.",
        sorted(set(evidence)),
    )


def store_submission_required_flags(channel: str) -> list[str]:
    return STORE_SUBMISSION_BASE_REQUIRED_FLAGS + STORE_SUBMISSION_CHANNEL_REQUIRED_FLAGS.get(channel, [])


def ensure_store_submission_evidence(root: Path, evidence_path: Path) -> None:
    script_root = Path(__file__).resolve().parents[1]
    if root.resolve() != script_root.resolve():
        return
    template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
    guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
    if evidence_path.exists():
        expected = import_store_submission_evidence.expected_entries()
        if not template_path.exists():
            import_store_submission_evidence.write_template(template_path, expected)
        if not guide_path.exists():
            import_store_submission_evidence.write_guide(guide_path, expected)
        return
    import_store_submission_evidence.import_evidence(
        root / "build" / "store-submission-evidence" / "store-submission-evidence.input.json",
        evidence_path,
        template_path,
        guide_path,
    )


def check_store_submission_evidence(root: Path) -> Check:
    evidence_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
    template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
    evidence = [
        "build/store-submission-evidence/store-submission-evidence.json",
        "build/store-submission-evidence/store-submission-evidence.template.json",
        "build/store-submission-evidence/store-submission-evidence.guide.md",
    ]
    ensure_store_submission_evidence(root, evidence_path)
    if not evidence_path.exists():
        return Check(
            "store_submission_evidence",
            "blocked",
            "Tenant store submission evidence has not been imported; copy build/store-submission-evidence/store-submission-evidence.template.json to store-submission-evidence.input.json after tenant signing/TestFlight/Play/direct-distribution setup and run scripts/import_store_submission_evidence.py.",
            evidence,
        )
    try:
        report = json.loads(read_text(evidence_path))
    except json.JSONDecodeError as error:
        return Check(
            "store_submission_evidence",
            "failed",
            f"Store submission evidence is invalid JSON: {error}",
            evidence,
        )

    result = report.get("result")
    if result == "blocked":
        missing = report.get("missingFlavors")
        blocked = report.get("blockedFlavors")
        blocked_report_problems: list[str] = []
        if blocked is not None and not isinstance(blocked, list):
            blocked_report_problems.append("blockedFlavors")
        elif isinstance(blocked, list):
            for index, item in enumerate(blocked):
                if not isinstance(item, dict):
                    blocked_report_problems.append(f"blockedFlavors:{index}")
                    continue
                flavor = str(item.get("flavor") or index)
                blockers = item.get("blockers")
                hints = item.get("remediationHints")
                if not isinstance(blockers, list) or not blockers:
                    blocked_report_problems.append(f"blockedFlavors:{flavor}:blockers")
                if (
                    not isinstance(hints, list)
                    or not hints
                    or any(not isinstance(hint, str) or not hint.strip() for hint in hints)
                ):
                    blocked_report_problems.append(f"blockedFlavors:{flavor}:remediationHints")
        if blocked_report_problems:
            return Check(
                "store_submission_evidence",
                "failed",
                "Store submission evidence blocked report problems: "
                + ", ".join(blocked_report_problems),
                evidence,
            )
        details: list[str] = []
        if isinstance(missing, list) and missing:
            details.append("missing flavors: " + ", ".join(str(item) for item in missing))
        if isinstance(blocked, list) and blocked:
            details.append(
                "blocked flavors: "
                + ", ".join(
                    f"{item.get('flavor')}({','.join(str(reason) for reason in item.get('blockers', []))})"
                    for item in blocked
                    if isinstance(item, dict)
                ),
            )
        return Check(
            "store_submission_evidence",
            "blocked",
            "; ".join(details) or "Tenant store submission evidence is not complete.",
            evidence,
        )
    if result != "passed":
        return Check(
            "store_submission_evidence",
            "failed",
            f"Store submission evidence did not pass: result={result!r}",
            evidence,
        )

    problems: list[str] = []
    if report.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if report.get("requiredFlavors") != list(FLAVORS):
        problems.append("requiredFlavors")
    template_value = report.get("templatePath")
    if template_value != "build/store-submission-evidence/store-submission-evidence.template.json":
        problems.append("templatePath")
    elif template_path.exists() and report.get("templateSha256") != file_sha256(template_path):
        problems.append("templateSha256")
    guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
    guide_value = report.get("guidePath")
    if guide_value != "build/store-submission-evidence/store-submission-evidence.guide.md":
        problems.append("guidePath")
    elif guide_path.exists() and report.get("guideSha256") != file_sha256(guide_path):
        problems.append("guideSha256")
    source_value = report.get("sourcePath")
    if not isinstance(source_value, str) or not source_value.endswith("store-submission-evidence.input.json"):
        problems.append("sourcePath")
    elif report.get("sourceSha256"):
        source_path = root / source_value
        if source_path.exists() and report.get("sourceSha256") != file_sha256(source_path):
            problems.append("sourceSha256")

    submissions = report.get("submissions")
    if not isinstance(submissions, list):
        problems.append("submissions-not-list")
        submissions = []
    by_flavor = {
        str(item.get("flavor")): item
        for item in submissions
        if isinstance(item, dict)
    }
    if set(by_flavor) != set(STORE_SUBMISSION_FLAVORS):
        problems.append(f"flavor-set={sorted(by_flavor)}")
    for flavor, expected in STORE_SUBMISSION_FLAVORS.items():
        submission = by_flavor.get(flavor)
        if not isinstance(submission, dict):
            problems.append(f"{flavor}:missing-submission")
            continue
        channel = STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
        if submission.get("templateApplicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:templateApplicationId")
        if submission.get("templateAppName") != expected["appName"]:
            problems.append(f"{flavor}:templateAppName")
        if not isinstance(submission.get("applicationId"), str) or not submission.get("applicationId"):
            problems.append(f"{flavor}:applicationId")
        if not isinstance(submission.get("appName"), str) or not submission.get("appName"):
            problems.append(f"{flavor}:appName")
        if submission.get("primaryChannel") != channel:
            problems.append(f"{flavor}:primaryChannel")
        if submission.get("submissionStatus") not in STORE_SUBMISSION_ALLOWED_STATUSES_BY_CHANNEL[channel]:
            problems.append(f"{flavor}:submissionStatus")
        if submission.get("importResult") != "passed":
            problems.append(f"{flavor}:importResult")
        checklist = submission.get("publicChecklist")
        if not isinstance(checklist, dict):
            problems.append(f"{flavor}:publicChecklist")
        else:
            for flag in store_submission_required_flags(channel):
                if checklist.get(flag) is not True:
                    problems.append(f"{flavor}:publicChecklist:{flag}")
        refs = submission.get("publicEvidenceRefs")
        if not isinstance(refs, list) or not refs:
            problems.append(f"{flavor}:publicEvidenceRefs")
        else:
            for ref in refs:
                _, ref_problems = import_store_submission_evidence.normalized_evidence_ref(ref)
                for ref_problem in ref_problems:
                    problems.append(f"{flavor}:{ref_problem}")
        if not import_store_submission_evidence.is_valid_evidence_timestamp(submission.get("evidenceCapturedAt")):
            problems.append(f"{flavor}:evidenceCapturedAt")

    if report.get("missingFlavors"):
        problems.append(f"missingFlavors={report.get('missingFlavors')!r}")
    if report.get("blockedFlavors"):
        problems.append(f"blockedFlavors={report.get('blockedFlavors')!r}")
    if report.get("forbiddenMarkerHits"):
        problems.append(f"forbiddenMarkerHits={report.get('forbiddenMarkerHits')!r}")
    serialized = json.dumps(report, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
        "whsec_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "store_submission_evidence",
            "failed",
            f"Store submission evidence problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "store_submission_evidence",
        "passed",
        "Tenant public store-submission evidence covers all five tenant release flavors, signed-build readiness, TestFlight/Play/direct-distribution status, legal/OAuth/payment checklist completion, public evidence references, and no-secret boundaries.",
        sorted(set(evidence)),
    )


def check_store_submission_evidence_preflight(root: Path) -> Check:
    output_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
    markdown_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md"
    evidence = [
        "scripts/store_submission_evidence_preflight.py",
        "build/store-submission-evidence/store-submission-evidence-preflight.json",
        "build/store-submission-evidence/store-submission-evidence-preflight.md",
    ]
    try:
        report = store_submission_evidence_preflight.build_preflight_report(
            source=root / "build" / "store-submission-evidence" / "store-submission-evidence.input.json",
            source_dir=root / "build" / "store-submission-evidence" / "flavors",
            output=output_path,
            markdown=markdown_path,
        )
    except Exception as error:  # pragma: no cover - defensive audit path
        return Check(
            "store_submission_evidence_preflight",
            "failed",
            f"Store submission evidence preflight failed: {error}",
            evidence,
        )

    problems: list[str] = []
    if report.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if report.get("outputPath") != "build/store-submission-evidence/store-submission-evidence-preflight.json":
        problems.append("outputPath")
    if report.get("markdownPath") != "build/store-submission-evidence/store-submission-evidence-preflight.md":
        problems.append("markdownPath")
    if not output_path.exists():
        problems.append("json-missing")
    if not markdown_path.exists():
        problems.append("markdown-missing")
    flavors = report.get("flavors")
    if not isinstance(flavors, list) or {str(item.get("flavor")) for item in flavors if isinstance(item, dict)} != set(STORE_SUBMISSION_FLAVORS):
        problems.append("flavors")
    elif any(
        not isinstance(item.get("remediationHints"), list)
        for item in flavors
        if isinstance(item, dict)
    ):
        problems.append("remediationHints")
    if isinstance(flavors, list) and any(
        not isinstance(item, dict)
        or not isinstance(item.get("readyForStrictImport"), bool)
        or not isinstance(item.get("strictImportBlockedBy"), list)
        for item in flavors
    ):
        problems.append("flavorReadiness")
    summary = report.get("summary")
    if not isinstance(summary, dict) or not {"passed", "blocked", "failed"} <= set(summary):
        problems.append("summary")
    strict_import_readiness = report.get("strictImportReadiness")
    if not isinstance(strict_import_readiness, dict):
        problems.append("strictImportReadiness")
    else:
        if not isinstance(strict_import_readiness.get("ready"), bool):
            problems.append("strictImportReadiness.ready")
        if not isinstance(strict_import_readiness.get("blockedBy"), list):
            problems.append("strictImportReadiness.blockedBy")
        if not isinstance(strict_import_readiness.get("sourceBlockedBy"), list):
            problems.append("strictImportReadiness.sourceBlockedBy")
        if strict_import_readiness.get("command") != store_submission_evidence_preflight.STRICT_IMPORT_COMMAND:
            problems.append("strictImportReadiness.command")
    quality_rules = report.get("qualityRules")
    quality_text = " ".join(quality_rules) if isinstance(quality_rules, list) else ""
    if "public HTTPS URL" not in quality_text:
        problems.append("qualityRules:public-https-url")
    if "ISO-8601" not in quality_text:
        problems.append("qualityRules:iso-8601")
    serialized = json.dumps(report, ensure_ascii=False).lower()
    markdown_text = read_text(markdown_path).lower() if markdown_path.exists() else ""
    if "remediation hints" not in markdown_text:
        problems.append("markdown:remediation-hints")
    if "public https url" not in markdown_text:
        problems.append("markdown:public-https-url")
    if "iso-8601" not in markdown_text:
        problems.append("markdown:iso-8601")
    for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
        if marker in serialized or marker in markdown_text:
            problems.append(f"forbidden-marker:{marker}")
    if problems:
        return Check(
            "store_submission_evidence_preflight",
            "failed",
            f"Store submission preflight report problems: {', '.join(problems)}",
            evidence,
        )
    return Check(
        "store_submission_evidence_preflight",
        "passed",
        "Store submission evidence preflight report summarizes per-flavor public evidence readiness and strict import readiness without creating passing fake store evidence.",
        evidence,
    )


def check_completion_unblocker_package(root: Path) -> Check:
    output_dir = root / "build" / "completion-unblocker"
    manifest_path = output_dir / "mobile-completion-unblocker.json"
    markdown_path = output_dir / "mobile-completion-unblocker.md"
    fix_queue_csv_path = output_dir / "mobile-store-evidence-fix-queue.csv"
    fix_queue_markdown_path = output_dir / "mobile-store-evidence-fix-queue.md"
    evidence = [
        "build/completion-unblocker/mobile-completion-unblocker.json",
        "build/completion-unblocker/mobile-completion-unblocker.md",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
    ]
    try:
        export_completion_unblocker.export_unblocker(root, output_dir)
    except OSError as error:
        return Check(
            "completion_unblocker_package",
            "failed",
            f"Completion unblocker export failed: {error}",
            evidence,
        )
    if (
        not manifest_path.exists()
        or not markdown_path.exists()
        or not fix_queue_csv_path.exists()
        or not fix_queue_markdown_path.exists()
    ):
        return Check(
            "completion_unblocker_package",
            "missing",
            "Completion unblocker package is missing manifest, guide, or store evidence fix queue files; run scripts/export_completion_unblocker.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "completion_unblocker_package",
            "failed",
            f"Completion unblocker manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_completion_unblocker":
        problems.append("packageType")
    if manifest.get("completionGateCommand") != "npm run infra:mobile-app-completion-audit":
        problems.append("completionGateCommand")
    fix_queue = manifest.get("storeEvidenceFixQueue")
    expected_queue_columns = [
        "flavor",
        "inputPath",
        "field",
        "tenantAction",
        "acceptedPublicEvidence",
        "forbiddenEvidence",
    ]
    if not isinstance(fix_queue, dict):
        problems.append("storeEvidenceFixQueue")
        fix_queue = {}
    else:
        if fix_queue.get("csvPath") != "build/completion-unblocker/mobile-store-evidence-fix-queue.csv":
            problems.append("storeEvidenceFixQueue.csvPath")
        if fix_queue.get("markdownPath") != "build/completion-unblocker/mobile-store-evidence-fix-queue.md":
            problems.append("storeEvidenceFixQueue.markdownPath")
        if fix_queue.get("strictImportCommand") != store_submission_evidence_preflight.STRICT_IMPORT_COMMAND:
            problems.append("storeEvidenceFixQueue.strictImportCommand")
        if fix_queue.get("columns") != expected_queue_columns:
            problems.append("storeEvidenceFixQueue.columns")
        if not isinstance(fix_queue.get("rowCount"), int) or fix_queue.get("rowCount", 0) <= 0:
            problems.append("storeEvidenceFixQueue.rowCount")
    actions = manifest.get("actions")
    if not isinstance(actions, list):
        problems.append("actions")
        actions = []
    action_ids = [action.get("id") for action in actions if isinstance(action, dict)]
    expected_ids = [
        "install_full_xcode",
        "import_unsigned_ios_ci_artifacts",
        "import_store_submission_evidence",
    ]
    if action_ids != expected_ids:
        problems.append(f"actions.ids={action_ids!r}")
    action_by_id = {
        action.get("id"): action
        for action in actions
        if isinstance(action, dict)
    }
    store_action = action_by_id.get("import_store_submission_evidence")
    if not isinstance(store_action, dict):
        problems.append("actions.import_store_submission_evidence")
    else:
        readiness = store_action.get("strictImportReadiness")
        if not isinstance(readiness, dict):
            problems.append("storeAction.strictImportReadiness")
        else:
            if not isinstance(readiness.get("ready"), bool):
                problems.append("storeAction.strictImportReadiness.ready")
            if not isinstance(readiness.get("blockedBy"), list):
                problems.append("storeAction.strictImportReadiness.blockedBy")
            if not isinstance(readiness.get("sourceBlockedBy"), list):
                problems.append("storeAction.strictImportReadiness.sourceBlockedBy")
        if not isinstance(store_action.get("blockedInputPaths"), list):
            problems.append("storeAction.blockedInputPaths")
        field_remediation = store_action.get("fieldRemediation")
        if not isinstance(field_remediation, list):
            problems.append("storeAction.fieldRemediation")
        else:
            if not field_remediation:
                problems.append("storeAction.fieldRemediation.empty")
            for row in field_remediation:
                if not isinstance(row, dict):
                    problems.append("storeAction.fieldRemediation.row")
                    continue
                if not isinstance(row.get("flavor"), str) or not row.get("flavor"):
                    problems.append("storeAction.fieldRemediation.flavor")
                if not isinstance(row.get("inputPath"), str) or not row.get("inputPath"):
                    problems.append("storeAction.fieldRemediation.inputPath")
                steps = row.get("remediationSteps")
                if not isinstance(steps, list) or not steps:
                    problems.append("storeAction.fieldRemediation.remediationSteps")
                    continue
                for step in steps:
                    if not isinstance(step, dict):
                        problems.append("storeAction.fieldRemediation.step")
                        continue
                    for field in [
                        "field",
                        "tenantAction",
                        "acceptedPublicEvidence",
                        "forbiddenEvidence",
                    ]:
                        if field not in step:
                            problems.append(f"storeAction.fieldRemediation.step.{field}")
                    if not isinstance(step.get("acceptedPublicEvidence"), list) or not step.get("acceptedPublicEvidence"):
                        problems.append("storeAction.fieldRemediation.acceptedPublicEvidence")
                    if not isinstance(step.get("forbiddenEvidence"), list) or not step.get("forbiddenEvidence"):
                        problems.append("storeAction.fieldRemediation.forbiddenEvidence")
    command_text = "\n".join(
        command
        for action in actions
        if isinstance(action, dict)
        for command in action.get("commands", [])
        if isinstance(command, str)
    )
    for required_command in [
        "scripts/ios_build_matrix.py all --strict",
        "scripts/download_ios_ci_artifacts.py --repo <owner/repo>",
        "scripts/export_store_submission_starter.py",
        "scripts/prepare_store_submission_inputs.py",
        "scripts/import_store_submission_evidence.py --strict",
    ]:
        if required_command not in command_text:
            problems.append(f"commands:{required_command}")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for required_path in [
        "build/ios-build-matrix/ios-build-matrix.json",
        "build/ios-ci-evidence/ios-ci-artifacts.json",
        "build/store-submission-starter/store-submission-operator-runbook.md",
        "build/store-submission-evidence/store-submission-input-workspace.json",
        "build/store-submission-evidence/store-submission-evidence.guide.md",
        "build/store-submission-evidence/store-submission-evidence.json",
    ]:
        if required_path not in serialized:
            problems.append(f"evidence:{required_path}")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")
    markdown = read_text(markdown_path)
    fix_queue_markdown = read_text(fix_queue_markdown_path)
    try:
        fix_queue_rows = list(csv.DictReader(read_text(fix_queue_csv_path).splitlines()))
    except csv.Error as error:
        problems.append(f"fixQueue.csv:{error}")
        fix_queue_rows = []
    if fix_queue_rows:
        if list(fix_queue_rows[0]) != expected_queue_columns:
            problems.append("fixQueue.csv.columns")
        if fix_queue.get("rowCount") != len(fix_queue_rows):
            problems.append("fixQueue.csv.rowCount")
        if not any(
            row.get("flavor") == "hongguo"
            and row.get("field") == "appStoreConnectRecordConfigured"
            for row in fix_queue_rows
        ):
            problems.append("fixQueue.csv.appStoreConnectRecordConfigured")
    else:
        problems.append("fixQueue.csv.empty")
    if "# Mobile Completion Unblocker" not in markdown:
        problems.append("markdown.title")
    if "npm run infra:mobile-app-completion-audit" not in markdown:
        problems.append("markdown.completionGateCommand")
    if "Strict import ready:" not in markdown:
        problems.append("markdown.strictImportReadiness")
    for marker in [
        "Field remediation:",
        "Tenant action:",
        "Accepted public evidence:",
        "Forbidden evidence:",
        "Store evidence fix queue:",
    ]:
        if marker not in markdown:
            problems.append(f"markdown.{marker}")
    for marker in [
        "# Mobile Store Evidence Fix Queue",
        "appStoreConnectRecordConfigured",
        "Tenant action",
        "Accepted public evidence",
        "Forbidden evidence",
        "rerun the strict import command",
    ]:
        if marker not in fix_queue_markdown:
            problems.append(f"fixQueueMarkdown.{marker}")
    forbidden_hits = export_completion_unblocker.marker_hits(manifest) + [
        marker
        for marker in export_completion_unblocker.FORBIDDEN_MARKERS
        if marker in markdown.lower()
        or marker in read_text(fix_queue_csv_path).lower()
        or marker in fix_queue_markdown.lower()
    ]
    if forbidden_hits:
        problems.append(f"forbiddenMarkers={sorted(set(forbidden_hits))!r}")
    if problems:
        return Check(
            "completion_unblocker_package",
            "failed",
            f"Completion unblocker package problems: {', '.join(problems)}",
            evidence,
        )
    return Check(
        "completion_unblocker_package",
        "passed",
        "Completion unblocker package exports no-secret external actions for full Xcode, unsigned iOS CI artifact import, tenant store-submission runbook/evidence, strict import readiness, field remediation, store evidence fix queue, and final audit rerun.",
        evidence,
    )


def check_github_publish_handoff_package(root: Path) -> Check:
    output_dir = root / "build" / "github-publish"
    manifest_path = output_dir / "github-publish-manifest.json"
    guide_path = output_dir / "github-publish-guide.md"
    notes_path = output_dir / "github-release-notes.md"
    evidence = [
        "build/github-publish/github-publish-manifest.json",
        "build/github-publish/github-publish-guide.md",
        "build/github-publish/github-release-notes.md",
    ]
    try:
        export_github_publish_handoff.export_handoff(root, output_dir)
    except OSError as error:
        return Check(
            "github_publish_handoff_package",
            "failed",
            f"GitHub publish handoff export failed: {error}",
            evidence,
        )
    if not manifest_path.exists() or not guide_path.exists() or not notes_path.exists():
        return Check(
            "github_publish_handoff_package",
            "missing",
            "GitHub publish handoff package is missing; run scripts/export_github_publish_handoff.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "github_publish_handoff_package",
            "failed",
            f"GitHub publish handoff manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_github_publish_handoff":
        problems.append("packageType")
    repository = manifest.get("repositoryTemplate")
    if not isinstance(repository, dict):
        problems.append("repositoryTemplate")
        repository = {}
    if repository.get("name") != "short-drama-whitelabel-mobile":
        problems.append("repositoryTemplate.name")
    if repository.get("license") != "Apache-2.0":
        problems.append("repositoryTemplate.license")
    if repository.get("publicByDefault") is not True:
        problems.append("repositoryTemplate.publicByDefault")
    source_package = manifest.get("sourcePackage")
    source_manifest = manifest.get("sourceManifest")
    if not isinstance(source_package, dict):
        problems.append("sourcePackage")
        source_package = {}
    if not isinstance(source_manifest, dict):
        problems.append("sourceManifest")
        source_manifest = {}
    if source_package.get("path") != "build/open-source/short-drama-whitelabel-mobile.zip":
        problems.append("sourcePackage.path")
    if source_manifest.get("path") != "build/open-source/open-source-template-manifest.json":
        problems.append("sourceManifest.path")
    if source_package.get("present") is not True:
        problems.append("sourcePackage.present")
    if source_manifest.get("present") is not True:
        problems.append("sourceManifest.present")
    for key, value in [
        ("sourcePackage.sha256", source_package.get("sha256")),
        ("sourceManifest.sha256", source_manifest.get("sha256")),
    ]:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            problems.append(key)
    summary = manifest.get("openSourceManifestSummary")
    if not isinstance(summary, dict):
        problems.append("openSourceManifestSummary")
        summary = {}
    if summary.get("missingRequiredEntries"):
        problems.append(f"openSourceManifestSummary.missingRequiredEntries={summary.get('missingRequiredEntries')!r}")
    if summary.get("disallowedValueMarkerHits"):
        problems.append(f"openSourceManifestSummary.disallowedValueMarkerHits={summary.get('disallowedValueMarkerHits')!r}")
    commands = manifest.get("publishCommands")
    if not isinstance(commands, list) or not commands:
        problems.append("publishCommands")
        commands = []
    command_text = "\n".join(str(command) for command in commands)
    for expected in [
        "python3 scripts/export_open_source_template.py",
        "gh repo create <owner>/short-drama-whitelabel-mobile --public",
        "gh release create mobile-template-v0.1.0",
        "build/open-source/open-source-template-manifest.json",
    ]:
        if expected not in command_text:
            problems.append(f"publishCommands:{expected}")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")
    guide = read_text(guide_path)
    notes = read_text(notes_path)
    if "# GitHub Publish Handoff" not in guide:
        problems.append("guide.title")
    if "short-drama-whitelabel-mobile" not in notes:
        problems.append("notes.repository")
    forbidden_hits = export_github_publish_handoff.marker_hits(manifest) + [
        marker
        for marker in export_github_publish_handoff.FORBIDDEN_MARKERS
        if marker in (guide + "\n" + notes).lower()
    ]
    if forbidden_hits:
        problems.append(f"forbiddenMarkers={sorted(set(forbidden_hits))!r}")
    if problems:
        return Check(
            "github_publish_handoff_package",
            "failed",
            f"GitHub publish handoff package problems: {', '.join(problems)}",
            evidence,
        )
    return Check(
        "github_publish_handoff_package",
        "passed",
        "GitHub publish handoff package exports no-secret public repository, release asset, release-note, checksum, and command metadata for the open-source mobile template.",
        evidence,
    )


def check_github_publication_evidence(root: Path) -> Check:
    evidence_path = root / "build" / "github-publish" / "github-publication-evidence.json"
    evidence = ["build/github-publish/github-publication-evidence.json"]
    if not evidence_path.exists():
        return Check(
            "github_publication_evidence",
            "blocked",
            "GitHub publication evidence is missing; publish the open-source template repository/release and import public evidence.",
            evidence,
        )
    try:
        report = json.loads(read_text(evidence_path))
    except json.JSONDecodeError as error:
        return Check(
            "github_publication_evidence",
            "failed",
            f"GitHub publication evidence is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if report.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if report.get("result") != "passed":
        problems.append(f"result={report.get('result')!r}")
    repository = report.get("repository")
    if not isinstance(repository, dict):
        problems.append("repository")
        repository = {}
    if repository.get("nameWithOwner") != "tokenstarai/short-drama-whitelabel-mobile":
        problems.append("repository.nameWithOwner")
    if repository.get("visibility") not in {"PUBLIC", "public"}:
        problems.append("repository.visibility")
    if repository.get("defaultBranch") != "main":
        problems.append("repository.defaultBranch")
    if not isinstance(repository.get("url"), str) or "github.com/tokenstarai/short-drama-whitelabel-mobile" not in repository.get("url", ""):
        problems.append("repository.url")
    release = report.get("release")
    if not isinstance(release, dict):
        problems.append("release")
        release = {}
    if release.get("tagName") != "mobile-template-v0.1.0":
        problems.append("release.tagName")
    if release.get("isDraft") is not False:
        problems.append("release.isDraft")
    if release.get("isPrerelease") is not False:
        problems.append("release.isPrerelease")
    if not isinstance(release.get("url"), str) or "/releases/tag/mobile-template-v0.1.0" not in release.get("url", ""):
        problems.append("release.url")
    assets = report.get("assets")
    if not isinstance(assets, list):
        problems.append("assets")
        assets = []
    by_asset = {
        str(asset.get("name")): asset
        for asset in assets
        if isinstance(asset, dict)
    }
    for asset_name in [
        "short-drama-whitelabel-mobile.zip",
        "open-source-template-manifest.json",
    ]:
        asset = by_asset.get(asset_name)
        if not isinstance(asset, dict):
            problems.append(f"asset:{asset_name}")
            continue
        if not isinstance(asset.get("sizeBytes"), int) or asset.get("sizeBytes", 0) <= 0:
            problems.append(f"asset:{asset_name}:sizeBytes")
        if not isinstance(asset.get("downloadUrl"), str) or asset_name not in asset.get("downloadUrl", ""):
            problems.append(f"asset:{asset_name}:downloadUrl")
        if not isinstance(asset.get("remoteDigestSha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", asset.get("remoteDigestSha256", "")):
            problems.append(f"asset:{asset_name}:remoteDigestSha256")
        if asset.get("digestMatchesLocal") is not True:
            problems.append(f"asset:{asset_name}:digestMatchesLocal")
    for key in ["sourcePackageSha256", "sourceManifestSha256"]:
        value = report.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            problems.append(key)
    if report.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={report.get('disallowedValueMarkerHits')!r}")
    forbidden_hits = export_github_publish_handoff.marker_hits(report)
    if forbidden_hits:
        problems.append(f"forbiddenMarkers={forbidden_hits!r}")
    if problems:
        return Check(
            "github_publication_evidence",
            "failed",
            f"GitHub publication evidence problems: {', '.join(problems)}",
            evidence,
        )
    return Check(
        "github_publication_evidence",
        "passed",
        "GitHub publication evidence confirms the public template repository, release tag, zip asset, manifest asset, hashes, and no-secret boundary.",
        evidence,
    )


def parse_apk_badging(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {"permissions": []}
    for line in output.splitlines():
        if line.startswith("package:"):
            result["packageName"] = _quoted_field(line, "name")
            result["versionCode"] = _quoted_field(line, "versionCode")
            result["versionName"] = _quoted_field(line, "versionName")
        elif line.startswith("sdkVersion:"):
            result["minSdkVersion"] = _line_value(line)
        elif line.startswith("targetSdkVersion:"):
            result["targetSdkVersion"] = _line_value(line)
        elif line.startswith("uses-permission:"):
            permission = _quoted_field(line, "name")
            if permission:
                result["permissions"].append(permission)
        elif line.startswith("application-label:") and "applicationLabel" not in result:
            result["applicationLabel"] = _line_value(line)
    return result


def resolve_aapt() -> Path | None:
    found = shutil.which("aapt")
    if found:
        return Path(found)

    sdk_roots = [
        Path(value)
        for value in [
            os_environ("ANDROID_HOME"),
            os_environ("ANDROID_SDK_ROOT"),
            "/opt/homebrew/share/android-commandlinetools",
        ]
        if value
    ]
    candidates: list[Path] = []
    for root in sdk_roots:
        build_tools = root / "build-tools"
        if build_tools.exists():
            candidates.extend(build_tools.glob("*/aapt"))
    executable = [path for path in candidates if path.exists() and path.is_file()]
    if not executable:
        return None
    return sorted(executable)[-1]


def _quoted_field(line: str, field: str) -> str | None:
    match = re.search(rf"{re.escape(field)}='([^']*)'", line)
    return match.group(1) if match else None


def _line_value(line: str) -> str | None:
    match = re.search(r":'([^']*)'", line)
    return match.group(1) if match else None


def os_environ(name: str) -> str | None:
    try:
        import os

        return os.environ.get(name)
    except Exception:
        return None


def latest_android_rebuild_input(root: Path) -> Path | None:
    candidates: list[Path] = [
        root / "pubspec.yaml",
        root / "pubspec.lock",
        root / "android" / "app" / "build.gradle.kts",
        root / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
    ]
    for directory in [
        root / "lib",
        root / "assets" / "config",
        root / "android" / "app" / "src",
    ]:
        if directory.exists():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    existing = [
        path
        for path in candidates
        if path.exists() and not is_android_generated_rebuild_input(root, path)
    ]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def is_android_generated_rebuild_input(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return str(relative) == "android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java"


def check_release_artifact_secret_boundary(root: Path) -> Check:
    artifacts = scan_release_artifacts.release_artifacts(root)
    evidence = [rel(root, artifact) for artifact in artifacts]
    if not artifacts:
        return Check(
            "release_artifact_secret_boundary",
            "missing",
            "No release APK/AAB artifacts are available to scan.",
            ["build/app/outputs"],
        )

    hits: list[str] = []
    for artifact in artifacts:
        for hit in scan_release_artifacts.scan_zip(artifact):
            hits.append(f"{rel(root, artifact)}:{hit}")

    if hits:
        return Check(
            "release_artifact_secret_boundary",
            "failed",
            f"Forbidden release artifact markers found: {', '.join(hits)}",
            evidence,
        )

    return Check(
        "release_artifact_secret_boundary",
        "passed",
        f"Release artifact secret scan passed for {len(artifacts)} APK/AAB artifacts.",
        evidence,
    )


def load_store_handoff_manifest(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = root / "build" / "release-handoff" / "mobile-store-handoff.json"
    if not path.exists():
        return None, "build/release-handoff/mobile-store-handoff.json is missing"
    try:
        return json.loads(read_text(path)), None
    except json.JSONDecodeError as error:
        return None, f"store handoff manifest is invalid JSON: {error}"


def check_store_handoff_manifest(root: Path) -> Check:
    path = write_store_handoff_manifest(root)
    evidence = [rel(root, path)]
    manifest, error = load_store_handoff_manifest(root)
    if error or manifest is None:
        status = "failed" if error and "invalid JSON" in error else "missing"
        return Check("store_handoff_manifest", status, error or "missing handoff manifest", evidence)

    release_manifest, release_error = load_release_manifest(root)
    if release_manifest is not None:
        evidence.append("build/release-manifests/mobile-artifacts.json")

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append(f"schemaVersion={manifest.get('schemaVersion')!r}")
    secret_boundary = manifest.get("secretBoundary")
    if not isinstance(secret_boundary, str) or "Public tenant handoff metadata" not in secret_boundary:
        problems.append("secretBoundary")

    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    forbidden_markers = [marker.lower() for marker in FORBIDDEN_SOURCE_MARKERS] + ["sk_"]
    hits = [marker for marker in forbidden_markers if marker in serialized]
    if hits:
        problems.append(f"forbidden-markers:{','.join(sorted(set(hits)))}")

    checklist = manifest.get("tenantOwnedChecklist")
    if not isinstance(checklist, dict):
        problems.append("tenantOwnedChecklist")
    else:
        for key in ["apple", "googlePlay", "androidDirect"]:
            entries = checklist.get(key)
            if not isinstance(entries, list) or not entries:
                problems.append(f"tenantOwnedChecklist:{key}")

    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors_by_name: dict[str, dict[str, Any]] = {}
    else:
        flavors_by_name = {
            str(entry.get("flavor")): entry
            for entry in flavors
            if isinstance(entry, dict) and entry.get("flavor")
        }
        if set(flavors_by_name) != set(STORE_SUBMISSION_FLAVORS):
            problems.append(f"flavors={sorted(flavors_by_name)}")

    release_artifacts = android_release_manifest_artifacts(release_manifest or {})
    release_artifacts_by_flavor: dict[str, list[dict[str, Any]]] = {}
    for artifact in release_artifacts:
        release_artifacts_by_flavor.setdefault(str(artifact.get("flavor")), []).append(artifact)

    for flavor, defaults in STORE_SUBMISSION_FLAVORS.items():
        entry = flavors_by_name.get(flavor)
        if not entry:
            continue
        config_dir = root / "assets" / "config" / flavor
        try:
            template = json.loads(read_text(config_dir / "tenant.template.json"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            problems.append(f"{flavor}:tenant.template.json:{error}")
            continue
        expected = {
            "appName": str(defaults["appName"]),
            "applicationId": str(defaults["applicationId"]),
            "deepLinkScheme": STORE_HANDOFF_DEEP_LINK_SCHEMES[flavor],
            "styleTemplate": str(template.get("styleTemplate", flavor)),
        }
        expected_values = {
            "appName": expected["appName"],
            "applicationId": expected["applicationId"],
            "bundleId": expected["applicationId"],
            "styleTemplate": expected["styleTemplate"],
            "deepLinkScheme": expected["deepLinkScheme"],
        }
        for key, value in expected_values.items():
            if entry.get(key) != value:
                problems.append(f"{flavor}:{key}={entry.get(key)!r}")
        if not str(entry.get("apiAdapterBase", "")).startswith("https://"):
            problems.append(f"{flavor}:apiAdapterBase")
        for key in ["authProviders", "consumerPaymentProviders"]:
            if not isinstance(entry.get(key), list) or not entry.get(key):
                problems.append(f"{flavor}:{key}")
        visibility = entry.get("paymentVisibility")
        if not isinstance(visibility, dict):
            problems.append(f"{flavor}:paymentVisibility")
        else:
            mode = entry.get("storeComplianceMode")
            configured = [
                str(provider)
                for provider in entry.get("consumerPaymentProviders", [])
                if str(provider) in PAYMENT_PROVIDER_ORDER
            ]
            allowed = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(str(mode), set())
            visible = [
                provider
                for provider in PAYMENT_PROVIDER_ORDER
                if provider in configured and provider in allowed
            ]
            hidden = [provider for provider in configured if provider not in visible]
            expected_visibility = {
                "storeComplianceMode": mode,
                "configuredProviders": configured,
                "appVisibleProviders": visible,
                "hiddenByComplianceProviders": hidden,
                "externalPaymentsAllowed": mode
                in {"android_direct", "regional_user_choice"},
            }
            for key, value in expected_visibility.items():
                if visibility.get(key) != value:
                    problems.append(f"{flavor}:paymentVisibility:{key}")
        callbacks = entry.get("authCallbackRegistration")
        if not isinstance(callbacks, dict):
            problems.append(f"{flavor}:authCallbackRegistration")
        else:
            expected_callbacks = auth_callback_registration_payload(
                expected["deepLinkScheme"],
                {"authProviders": entry.get("authProviders", [])},
            )
            for key in [
                "scheme",
                "host",
                "callbackUris",
                "requiredQueryParams",
                "optionalQueryParams",
                "nativeConfig",
            ]:
                if callbacks.get(key) != expected_callbacks[key]:
                    problems.append(f"{flavor}:authCallbackRegistration:{key}")
            actions = callbacks.get("tenantRequiredActions")
            if not isinstance(actions, list):
                problems.append(f"{flavor}:authCallbackRegistration:tenantRequiredActions")
            else:
                action_text = " ".join(str(action) for action in actions)
                if "callback URIs" not in action_text:
                    problems.append(f"{flavor}:authCallbackRegistration:callback-actions")
                if "Tenant Edge" not in action_text or "credentials" not in action_text:
                    problems.append(f"{flavor}:authCallbackRegistration:secret-boundary")
        products = entry.get("storeProductRegistration")
        if not isinstance(products, dict):
            problems.append(f"{flavor}:storeProductRegistration")
        else:
            mode = entry.get("storeComplianceMode")
            configured = [
                str(provider)
                for provider in entry.get("consumerPaymentProviders", [])
                if str(provider) in PAYMENT_PROVIDER_ORDER
            ]
            allowed = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(str(mode), set())
            visible = [
                provider
                for provider in PAYMENT_PROVIDER_ORDER
                if provider in configured and provider in allowed
            ]
            expected_products = store_product_registration_payload(
                {
                    "storeComplianceMode": mode,
                    "appVisibleProviders": visible,
                },
            )
            for key in [
                "storeComplianceMode",
                "storeProviders",
                "serverVerificationEndpoint",
                "tenantEdgeMayOverridePackages",
                "tenantShouldReplaceProductIds",
                "registrations",
            ]:
                if products.get(key) != expected_products[key]:
                    problems.append(f"{flavor}:storeProductRegistration:{key}")
            actions = products.get("tenantRequiredActions")
            if not isinstance(actions, list):
                problems.append(f"{flavor}:storeProductRegistration:tenantRequiredActions")
            else:
                action_text = " ".join(str(action) for action in actions)
                if "App Store Connect" not in action_text or "Google Play Console" not in action_text:
                    problems.append(f"{flavor}:storeProductRegistration:store-actions")
                if "Tenant Edge" not in action_text or "credentials" not in action_text:
                    problems.append(f"{flavor}:storeProductRegistration:secret-boundary")
        native = entry.get("nativeCapabilityRegistration")
        if not isinstance(native, dict):
            problems.append(f"{flavor}:nativeCapabilityRegistration")
        else:
            mode = entry.get("storeComplianceMode")
            configured = [
                str(provider)
                for provider in entry.get("consumerPaymentProviders", [])
                if str(provider) in PAYMENT_PROVIDER_ORDER
            ]
            allowed = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(str(mode), set())
            visible = [
                provider
                for provider in PAYMENT_PROVIDER_ORDER
                if provider in configured and provider in allowed
            ]
            expected_native = native_capability_registration_payload(
                flavor,
                expected,
                {"authProviders": entry.get("authProviders", [])},
                {
                    "storeComplianceMode": mode,
                    "appVisibleProviders": visible,
                },
            )
            for platform in ["ios", "android"]:
                platform_native = native.get(platform)
                expected_platform = expected_native[platform]
                if not isinstance(platform_native, dict):
                    problems.append(f"{flavor}:nativeCapabilityRegistration:{platform}")
                    continue
                for key, value in expected_platform.items():
                    if platform_native.get(key) != value:
                        problems.append(f"{flavor}:nativeCapabilityRegistration:{platform}:{key}")
                actions = platform_native.get("tenantRequiredActions")
                if not isinstance(actions, list):
                    problems.append(
                        f"{flavor}:nativeCapabilityRegistration:{platform}:tenantRequiredActions",
                    )
                    continue
                action_text = " ".join(str(action) for action in actions)
                if platform == "ios" and "Apple developer account" not in action_text:
                    problems.append(f"{flavor}:nativeCapabilityRegistration:ios:apple-actions")
                if platform == "android" and "signing" not in action_text:
                    problems.append(f"{flavor}:nativeCapabilityRegistration:android:signing-actions")
        review = entry.get("storeReviewDeclarations")
        if not isinstance(review, dict):
            problems.append(f"{flavor}:storeReviewDeclarations")
        else:
            mode = entry.get("storeComplianceMode")
            configured = [
                str(provider)
                for provider in entry.get("consumerPaymentProviders", [])
                if str(provider) in PAYMENT_PROVIDER_ORDER
            ]
            allowed = VISIBLE_PAYMENT_PROVIDERS_BY_MODE.get(str(mode), set())
            visible = [
                provider
                for provider in PAYMENT_PROVIDER_ORDER
                if provider in configured and provider in allowed
            ]
            expected_review = store_review_declarations_payload(
                {"authProviders": entry.get("authProviders", [])},
                json.loads(
                    read_text(
                        root
                        / "assets"
                        / "config"
                        / flavor
                        / "tenant.features.json",
                    ),
                ),
                {
                    "storeComplianceMode": mode,
                    "appVisibleProviders": visible,
                    "externalPaymentsAllowed": mode
                    in {"android_direct", "regional_user_choice"},
                },
            )
            if review.get("storeComplianceMode") != expected_review["storeComplianceMode"]:
                problems.append(f"{flavor}:storeReviewDeclarations:storeComplianceMode")
            for section in ["apple", "googlePlay", "androidDirect"]:
                actual_section = review.get(section)
                expected_section = expected_review[section]
                if not isinstance(actual_section, dict):
                    problems.append(f"{flavor}:storeReviewDeclarations:{section}")
                    continue
                for key, value in expected_section.items():
                    if actual_section.get(key) != value:
                        problems.append(f"{flavor}:storeReviewDeclarations:{section}:{key}")
                actions = actual_section.get("tenantRequiredActions")
                if not isinstance(actions, list) or not actions:
                    problems.append(
                        f"{flavor}:storeReviewDeclarations:{section}:tenantRequiredActions",
                    )
            serialized_review = json.dumps(review, ensure_ascii=False).lower()
            for marker in ["client_secret", "stripe_secret", "paypal_secret", "private_key", "sk_"]:
                if marker in serialized_review:
                    problems.append(f"{flavor}:storeReviewDeclarations:secret-marker:{marker}")
        distribution = entry.get("distributionChannelReadiness")
        if not isinstance(distribution, dict):
            problems.append(f"{flavor}:distributionChannelReadiness")
        else:
            expected_artifacts = release_artifacts_by_flavor.get(flavor, [])
            expected_paths_for_distribution = {
                "androidReleaseApk": next(
                    (
                        artifact.get("path")
                        for artifact in expected_artifacts
                        if artifact.get("packageType") == "apk"
                    ),
                    None,
                ),
                "androidReleaseAppBundle": next(
                    (
                        artifact.get("path")
                        for artifact in expected_artifacts
                        if artifact.get("packageType") == "appbundle"
                    ),
                    None,
                ),
            }
            expected_distribution = distribution_channel_readiness_payload(
                flavor,
                {"storeComplianceMode": entry.get("storeComplianceMode")},
                expected_paths_for_distribution,
            )
            for key in ["storeComplianceMode", "primaryChannel", "channels"]:
                if distribution.get(key) != expected_distribution[key]:
                    problems.append(f"{flavor}:distributionChannelReadiness:{key}")
            serialized_distribution = json.dumps(distribution, ensure_ascii=False).lower()
            for marker in ["client_secret", "stripe_secret", "paypal_secret", "private_key", "sk_"]:
                if marker in serialized_distribution:
                    problems.append(
                        f"{flavor}:distributionChannelReadiness:secret-marker:{marker}",
                    )
        submission = entry.get("storeSubmission")
        if not isinstance(submission, dict):
            problems.append(f"{flavor}:storeSubmission")
        else:
            listing = submission.get("listing")
            if not isinstance(listing, dict):
                problems.append(f"{flavor}:storeSubmission:listing")
            else:
                expected_listing = {
                    "displayName": expected["appName"],
                    "shortDescription": LISTING_COPY_BY_TEMPLATE.get(
                        expected["styleTemplate"],
                        "Short drama episodes with tenant-managed catalog and wallet flows.",
                    ),
                }
                for key, value in expected_listing.items():
                    if listing.get(key) != value:
                        problems.append(f"{flavor}:storeSubmission:listing:{key}")
                if not listing.get("defaultLocale"):
                    problems.append(f"{flavor}:storeSubmission:listing:defaultLocale")
                if not isinstance(listing.get("supportedLocales"), list) or not listing.get("supportedLocales"):
                    problems.append(f"{flavor}:storeSubmission:listing:supportedLocales")
                for key in ["supportUrl", "termsUrl", "privacyUrl"]:
                    if not str(listing.get(key, "")).startswith("https://"):
                        problems.append(f"{flavor}:storeSubmission:listing:{key}")
            review_notes = submission.get("reviewNotes")
            if not isinstance(review_notes, list) or len(review_notes) < 3:
                problems.append(f"{flavor}:storeSubmission:reviewNotes")
            localized_listings = submission.get("localizedListings")
            if not isinstance(localized_listings, list):
                problems.append(f"{flavor}:storeSubmission:localizedListings")
            elif isinstance(listing, dict):
                supported_locales = listing.get("supportedLocales")
                if not isinstance(supported_locales, list) or not supported_locales:
                    problems.append(f"{flavor}:storeSubmission:localizedListings:supportedLocales")
                else:
                    expected_localized = store_submission_localized_listings(
                        {
                            "appName": expected["appName"],
                            "customerServiceUrl": listing.get("supportUrl"),
                            "termsUrl": listing.get("termsUrl"),
                            "privacyUrl": listing.get("privacyUrl"),
                        },
                        [str(locale) for locale in supported_locales],
                    )
                    if len(localized_listings) != len(expected_localized):
                        problems.append(f"{flavor}:storeSubmission:localizedListings:count")
                    localized_by_locale = {
                        str(item.get("locale")): item
                        for item in localized_listings
                        if isinstance(item, dict)
                    }
                    if set(localized_by_locale) != {item["locale"] for item in expected_localized}:
                        problems.append(f"{flavor}:storeSubmission:localizedListings:locales")
                    default_count = sum(
                        1
                        for item in localized_by_locale.values()
                        if item.get("isDefault") is True
                    )
                    if default_count != 1:
                        problems.append(f"{flavor}:storeSubmission:localizedListings:default")
                    for expected_item in expected_localized:
                        item = localized_by_locale.get(expected_item["locale"])
                        if not isinstance(item, dict):
                            continue
                        for key, value in expected_item.items():
                            if item.get(key) != value:
                                problems.append(
                                    f"{flavor}:storeSubmission:localizedListings:{expected_item['locale']}:{key}",
                                )
            data_safety = submission.get("dataSafety")
            if not isinstance(data_safety, dict):
                problems.append(f"{flavor}:storeSubmission:dataSafety")
            else:
                if "tenant must answer store questionnaires" not in str(data_safety.get("notes", "")):
                    problems.append(f"{flavor}:storeSubmission:dataSafety:notes")
                disclosures = data_safety.get("templateDisclosures")
                if not isinstance(disclosures, dict):
                    problems.append(f"{flavor}:storeSubmission:dataSafety:templateDisclosures")
                else:
                    if disclosures.get("tenantSecretsInClient") is not False:
                        problems.append(f"{flavor}:storeSubmission:dataSafety:tenantSecretsInClient")
                    if disclosures.get("consumerContentUpload") is not False:
                        problems.append(f"{flavor}:storeSubmission:dataSafety:consumerContentUpload")
            required_actions = submission.get("tenantRequiredActions")
            if not isinstance(required_actions, list):
                problems.append(f"{flavor}:storeSubmission:tenantRequiredActions")
            else:
                for action in [
                    "configure tenant signing",
                    "replace placeholder icons and screenshots",
                    "complete store privacy and data safety questionnaires",
                ]:
                    if action not in required_actions:
                        problems.append(
                            f"{flavor}:storeSubmission:tenantRequiredActions:{action}",
                        )
            screenshot_assets = submission.get("screenshotAssets")
            if not isinstance(screenshot_assets, list):
                problems.append(f"{flavor}:storeSubmission:screenshotAssets")
            else:
                expected_assets = store_submission_screenshot_assets(root, flavor)
                if len(screenshot_assets) != len(expected_assets):
                    problems.append(f"{flavor}:storeSubmission:screenshotAssets:count")
                for index, expected_asset in enumerate(expected_assets):
                    if index >= len(screenshot_assets):
                        continue
                    asset = screenshot_assets[index]
                    if not isinstance(asset, dict):
                        problems.append(f"{flavor}:storeSubmission:screenshotAssets:{index}")
                        continue
                    for key, value in expected_asset.items():
                        if asset.get(key) != value:
                            problems.append(
                                f"{flavor}:storeSubmission:screenshotAssets:{index}:{key}",
                            )
                    path = asset.get("path")
                    if not isinstance(path, str) or not (root / path).exists():
                        problems.append(
                            f"{flavor}:storeSubmission:screenshotAssets:{index}:missing-file",
                        )

        legal = entry.get("legal")
        if not isinstance(legal, dict):
            problems.append(f"{flavor}:legal")
        else:
            for key in ["customerServiceUrl", "termsUrl", "privacyUrl"]:
                if not str(legal.get(key, "")).startswith("https://"):
                    problems.append(f"{flavor}:legal:{key}")

        commands = entry.get("buildCommands")
        expected_commands = {
            "androidReleaseApk": f"./scripts/build_flavor.sh {flavor} android release apk",
            "androidReleaseAppBundle": f"./scripts/build_flavor.sh {flavor} android release appbundle",
            "iosUnsignedRelease": f"./scripts/build_flavor.sh {flavor} ios release",
        }
        if not isinstance(commands, dict):
            problems.append(f"{flavor}:buildCommands")
        else:
            for key, value in expected_commands.items():
                if commands.get(key) != value:
                    problems.append(f"{flavor}:buildCommands:{key}")

        expected_artifacts = release_artifacts_by_flavor.get(flavor, [])
        if expected_artifacts:
            release_entries = entry.get("releaseArtifacts")
            if not isinstance(release_entries, list):
                problems.append(f"{flavor}:releaseArtifacts")
                release_entries = []
            release_package_types = {artifact.get("packageType") for artifact in release_entries}
            for package_type in ["apk", "appbundle"]:
                matches = [
                    artifact
                    for artifact in expected_artifacts
                    if artifact.get("packageType") == package_type
                ]
                if not matches:
                    continue
                if package_type not in release_package_types:
                    problems.append(f"{flavor}:releaseArtifacts:{package_type}")
            paths = entry.get("artifactPaths")
            if not isinstance(paths, dict):
                problems.append(f"{flavor}:artifactPaths")
            else:
                expected_paths = {
                    "androidReleaseApk": next(
                        (
                            artifact.get("path")
                            for artifact in expected_artifacts
                            if artifact.get("packageType") == "apk"
                        ),
                        None,
                    ),
                    "androidReleaseAppBundle": next(
                        (
                            artifact.get("path")
                            for artifact in expected_artifacts
                            if artifact.get("packageType") == "appbundle"
                        ),
                        None,
                    ),
                }
                for key, value in expected_paths.items():
                    if value and paths.get(key) != value:
                        problems.append(f"{flavor}:artifactPaths:{key}")

    if release_error and "is missing" not in release_error:
        problems.append(release_error)

    if problems:
        return Check(
            "store_handoff_manifest",
            "failed",
            f"Store handoff manifest problems: {', '.join(problems)}",
            evidence,
        )

    return Check(
        "store_handoff_manifest",
        "passed",
        "Store handoff manifest covers all five tenant release flavors, tenant-owned store tasks, public config, compliance-filtered payment visibility, OAuth/deep-link callback registration metadata, App Store/Google Play product registration metadata, native capability registration metadata, store review declarations, distribution channel readiness, store submission metadata with per-locale listing drafts, publish-safe screenshot or WYSIWYG review assets with SHA256/size/dimensions, build commands, optional Android release artifacts, and secret boundaries.",
        evidence,
    )


def check_store_assets_package(root: Path) -> Check:
    manifest_path = root / "build" / "store-assets" / "store-assets-manifest.json"
    evidence = ["build/store-assets/store-assets-manifest.json"]
    if not manifest_path.exists():
        return Check(
            "store_assets_package",
            "missing",
            "Store assets package manifest is missing; run scripts/export_store_assets.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "store_assets_package",
            "failed",
            f"Store assets manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_store_assets":
        problems.append("packageType")
    zip_path = root / str(manifest.get("packagePath", ""))
    evidence.append(rel(root, zip_path))
    if not zip_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(zip_path):
        problems.append("packageSha256")
    if manifest.get("manifestSha256") != file_sha256(manifest_path):
        # The manifest records its final content hash before the final write would be recursive,
        # so this field is informational and not self-hashed.
        pass
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")
    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(item.get("flavor")): item
        for item in flavors
        if isinstance(item, dict)
    }
    for flavor, expected in FLAVORS.items():
        item = by_flavor.get(flavor)
        if not isinstance(item, dict):
            problems.append(f"{flavor}:missing")
            continue
        expected_app_name = expected.get("appName", expected.get("name"))
        if item.get("appName") != expected_app_name:
            problems.append(f"{flavor}:appName")
        if item.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        listing = item.get("listing")
        if not isinstance(listing, dict):
            problems.append(f"{flavor}:listing")
        else:
            if listing.get("displayName") != expected["appName"]:
                problems.append(f"{flavor}:listing:displayName")
            if not str(listing.get("supportUrl", "")).startswith("https://"):
                problems.append(f"{flavor}:listing:supportUrl")
        localized = item.get("localizedListings")
        if not isinstance(localized, list) or len(localized) < 1:
            problems.append(f"{flavor}:localizedListings")
        data_safety = item.get("dataSafety")
        disclosures = data_safety.get("templateDisclosures") if isinstance(data_safety, dict) else None
        if not isinstance(disclosures, dict):
            problems.append(f"{flavor}:dataSafety")
        else:
            if disclosures.get("clientStoresTenantCredentials") is not False:
                problems.append(f"{flavor}:clientStoresTenantCredentials")
            serialized_disclosures = json.dumps(disclosures, ensure_ascii=False).lower()
            if "secret" in serialized_disclosures:
                problems.append(f"{flavor}:dataSafety:secret-word")
        screenshots = item.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != len(SCREEN_IDS):
            problems.append(f"{flavor}:screenshots")
            screenshots = []
        for screenshot in screenshots:
            if not isinstance(screenshot, dict):
                problems.append(f"{flavor}:screenshot-entry")
                continue
            screenshot_path = root / "build" / "store-assets" / str(screenshot.get("path", ""))
            evidence.append(rel(root, screenshot_path))
            if not screenshot_path.exists():
                problems.append(f"{flavor}:{screenshot.get('screen')}:missing-screenshot")
                continue
            if png_dimensions(screenshot_path) != (screenshot.get("width"), screenshot.get("height")):
                problems.append(f"{flavor}:{screenshot.get('screen')}:dimensions")
            if screenshot.get("sha256") != file_sha256(screenshot_path):
                problems.append(f"{flavor}:{screenshot.get('screen')}:sha256")
            allowed_screenshot_sources = {"publish_safe_prototype"}
            if flavor == "coolshow":
                allowed_screenshot_sources.add(export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE)
            if screenshot.get("source") not in allowed_screenshot_sources:
                problems.append(f"{flavor}:{screenshot.get('screen')}:source")
    if manifest.get("screenshotCount") != len(FLAVORS) * len(SCREEN_IDS):
        problems.append("screenshotCount")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-store-assets/") for name in names):
            problems.append("zip-prefix")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "cloudflare_api_token=",
        "cloudflare-api-token:",
        "bearer ey",
        "sk_live_",
        "sk_test_",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "store_assets_package",
            "failed",
            f"Store assets package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "store_assets_package",
        "passed",
        "Store assets package exports per-flavor listing drafts, localized copy, review notes, data-safety starter facts, and 40 publish-safe screenshots for tenant store submission handoff.",
        sorted(set(evidence)),
    )


def check_ui_preview_gallery(root: Path) -> Check:
    output_dir = root / "build" / "ui-preview-gallery"
    manifest_path = output_dir / "ui-preview-gallery-manifest.json"
    manifest = export_ui_preview_gallery.build_gallery(root, output_dir)
    evidence = [
        "build/ui-preview-gallery/ui-preview-gallery-manifest.json",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
        "build/ui-preview-gallery/mobile-ui-readable-overview.svg",
        "build/ui-preview-gallery/mobile-ui-readable-overview.png",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
    ]
    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_ui_preview_gallery":
        problems.append("packageType")
    if manifest.get("source") != "flutter_prototype_goldens":
        problems.append("source")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(
            f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}",
        )
    html_path = root / str(manifest.get("htmlPath", ""))
    readable_overview = manifest.get("readableOverview")
    readable_overview_path: Path | None = None
    readable_overview_png = manifest.get("readableOverviewPng")
    readable_overview_png_path: Path | None = None
    contact_sheet = manifest.get("contactSheet")
    contact_sheet_path: Path | None = None
    contact_sheet_png = manifest.get("contactSheetPng")
    contact_sheet_png_path: Path | None = None
    wysiwyg_runtime = manifest.get("wysiwygRuntimePreviews")
    zip_path = root / str(manifest.get("packagePath", ""))
    if not manifest_path.exists():
        problems.append("missing-manifest")
    if not html_path.exists():
        problems.append("missing-html")
    elif manifest.get("htmlSha256") != file_sha256(html_path):
        problems.append("htmlSha256")
    if not isinstance(readable_overview, dict):
        problems.append("readableOverview")
    else:
        readable_overview_path = root / str(readable_overview.get("path", ""))
        if readable_overview.get("path") != "build/ui-preview-gallery/mobile-ui-readable-overview.svg":
            problems.append("readableOverview.path")
        if not readable_overview_path.exists():
            problems.append("missing-readable-overview")
        elif readable_overview.get("sha256") != file_sha256(readable_overview_path):
            problems.append("readableOverview.sha256")
        if readable_overview.get("screenCount") != len(export_ui_preview_gallery.FLAVORS) * 4:
            problems.append("readableOverview.screenCount")
        if readable_overview.get("includedScreens") != ["home", "detail", "player", "wallet"]:
            problems.append("readableOverview.includedScreens")
        if readable_overview.get("source") != "publish_safe_readable_overview":
            problems.append("readableOverview.source")
    if not isinstance(readable_overview_png, dict):
        problems.append("readableOverviewPng")
    else:
        readable_overview_png_path = root / str(readable_overview_png.get("path", ""))
        if readable_overview_png.get("path") != "build/ui-preview-gallery/mobile-ui-readable-overview.png":
            problems.append("readableOverviewPng.path")
        if not readable_overview_png_path.exists():
            problems.append("missing-readable-overview-png")
        elif readable_overview_png.get("sha256") != file_sha256(readable_overview_png_path):
            problems.append("readableOverviewPng.sha256")
        if readable_overview_png.get("screenCount") != len(export_ui_preview_gallery.FLAVORS) * 4:
            problems.append("readableOverviewPng.screenCount")
        if readable_overview_png.get("includedScreens") != ["home", "detail", "player", "wallet"]:
            problems.append("readableOverviewPng.includedScreens")
        if readable_overview_png.get("source") != "publish_safe_readable_overview_png":
            problems.append("readableOverviewPng.source")
        if png_dimensions(readable_overview_png_path) != (
            readable_overview_png.get("width"),
            readable_overview_png.get("height"),
        ):
            problems.append("readableOverviewPng.dimensions")
    if not isinstance(contact_sheet, dict):
        problems.append("contactSheet")
    else:
        contact_sheet_path = root / str(contact_sheet.get("path", ""))
        if contact_sheet.get("path") != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg":
            problems.append("contactSheet.path")
        if not contact_sheet_path.exists():
            problems.append("missing-contact-sheet")
        elif contact_sheet.get("sha256") != file_sha256(contact_sheet_path):
            problems.append("contactSheet.sha256")
        if contact_sheet.get("flavorCount") != len(export_ui_preview_gallery.FLAVORS):
            problems.append("contactSheet.flavorCount")
        if contact_sheet.get("screenCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
            problems.append("contactSheet.screenCount")
        if contact_sheet.get("includedScreens") != SCREEN_IDS:
            problems.append("contactSheet.includedScreens")
        if contact_sheet.get("source") != "publish_safe_full_screenshot_contact_sheet":
            problems.append("contactSheet.source")
    if not isinstance(contact_sheet_png, dict):
        problems.append("contactSheetPng")
    else:
        contact_sheet_png_path = root / str(contact_sheet_png.get("path", ""))
        if contact_sheet_png.get("path") != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png":
            problems.append("contactSheetPng.path")
        if not contact_sheet_png_path.exists():
            problems.append("missing-contact-sheet-png")
        elif contact_sheet_png.get("sha256") != file_sha256(contact_sheet_png_path):
            problems.append("contactSheetPng.sha256")
        if contact_sheet_png.get("flavorCount") != len(export_ui_preview_gallery.FLAVORS):
            problems.append("contactSheetPng.flavorCount")
        if contact_sheet_png.get("screenCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
            problems.append("contactSheetPng.screenCount")
        if contact_sheet_png.get("includedScreens") != SCREEN_IDS:
            problems.append("contactSheetPng.includedScreens")
        if contact_sheet_png.get("source") != "publish_safe_full_screenshot_contact_sheet_png":
            problems.append("contactSheetPng.source")
        if png_dimensions(contact_sheet_png_path) != (
            contact_sheet_png.get("width"),
            contact_sheet_png.get("height"),
        ):
            problems.append("contactSheetPng.dimensions")
    if not isinstance(wysiwyg_runtime, dict):
        problems.append("wysiwygRuntimePreviews")
    else:
        if wysiwyg_runtime.get("source") != export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE:
            problems.append("wysiwygRuntimePreviews.source")
        if wysiwyg_runtime.get("sourceDirectory") != "build/wysiwyg-preview":
            problems.append("wysiwygRuntimePreviews.sourceDirectory")
        if wysiwyg_runtime.get("captureCount") != len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS):
            problems.append("wysiwygRuntimePreviews.captureCount")
        if wysiwyg_runtime.get("requiredCaptureCount") != len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS):
            problems.append("wysiwygRuntimePreviews.requiredCaptureCount")
        if wysiwyg_runtime.get("boardCount") != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
            problems.append("wysiwygRuntimePreviews.boardCount")
        captures = wysiwyg_runtime.get("captures")
        if not isinstance(captures, list) or len(captures) != len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS):
            problems.append("wysiwygRuntimePreviews.captures")
            captures = []
        for capture in captures:
            if not isinstance(capture, dict):
                problems.append("wysiwygRuntimePreviews.capture-entry")
                continue
            capture_path = root / str(capture.get("path", ""))
            evidence.append(rel(root, capture_path))
            if not capture_path.exists():
                problems.append(f"wysiwygRuntimePreviews.capture:{capture.get('path')}:missing")
                continue
            if capture.get("source") != export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE:
                problems.append(f"wysiwygRuntimePreviews.capture:{capture.get('path')}:source")
            if capture.get("sha256") != file_sha256(capture_path):
                problems.append(f"wysiwygRuntimePreviews.capture:{capture.get('path')}:sha256")
            if png_dimensions(capture_path) != (capture.get("width"), capture.get("height")):
                problems.append(f"wysiwygRuntimePreviews.capture:{capture.get('path')}:dimensions")
        boards = wysiwyg_runtime.get("boards")
        if not isinstance(boards, list) or len(boards) != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
            problems.append("wysiwygRuntimePreviews.boards")
            boards = []
        expected_board_paths = {
            f"build/ui-preview-gallery/{file_name}"
            for file_name in export_ui_preview_gallery.WYSIWYG_BOARD_FILES
        }
        actual_board_paths: set[str] = set()
        for board in boards:
            if not isinstance(board, dict):
                problems.append("wysiwygRuntimePreviews.board-entry")
                continue
            board_path_value = str(board.get("path", ""))
            actual_board_paths.add(board_path_value)
            board_path = root / board_path_value
            evidence.append(rel(root, board_path))
            if board.get("source") != export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE:
                problems.append(f"wysiwygRuntimePreviews.board:{board.get('id')}:source")
            if not board_path.exists():
                problems.append(f"wysiwygRuntimePreviews.board:{board.get('id')}:missing")
                continue
            if board.get("sha256") != file_sha256(board_path):
                problems.append(f"wysiwygRuntimePreviews.board:{board.get('id')}:sha256")
            if png_dimensions(board_path) != (board.get("width"), board.get("height")):
                problems.append(f"wysiwygRuntimePreviews.board:{board.get('id')}:dimensions")
        if actual_board_paths != expected_board_paths:
            problems.append("wysiwygRuntimePreviews.boardPaths")
    if not zip_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(zip_path):
        problems.append("packageSha256")
    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(item.get("flavor")): item
        for item in flavors
        if isinstance(item, dict)
    }
    for flavor, expected in export_ui_preview_gallery.FLAVORS.items():
        item = by_flavor.get(flavor)
        if not isinstance(item, dict):
            problems.append(f"{flavor}:missing")
            continue
        expected_app_name = expected.get("appName", expected.get("name"))
        if item.get("appName") != expected_app_name:
            problems.append(f"{flavor}:appName")
        if item.get("styleTemplate") != expected["styleTemplate"]:
            problems.append(f"{flavor}:styleTemplate")
        screenshots = item.get("screenshots")
        if not isinstance(screenshots, list) or len(screenshots) != len(SCREEN_IDS):
            problems.append(f"{flavor}:screenshots")
            screenshots = []
        for screenshot in screenshots:
            if not isinstance(screenshot, dict):
                problems.append(f"{flavor}:screenshot-entry")
                continue
            screenshot_path = output_dir / str(screenshot.get("path", ""))
            evidence.append(rel(root, screenshot_path))
            if not screenshot_path.exists():
                problems.append(f"{flavor}:{screenshot.get('screen')}:missing-screenshot")
                continue
            if png_dimensions(screenshot_path) != (screenshot.get("width"), screenshot.get("height")):
                problems.append(f"{flavor}:{screenshot.get('screen')}:dimensions")
            if screenshot.get("sha256") != file_sha256(screenshot_path):
                problems.append(f"{flavor}:{screenshot.get('screen')}:sha256")
            allowed_screenshot_sources = {"publish_safe_prototype"}
            if flavor == "coolshow":
                allowed_screenshot_sources.add(export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE)
            if screenshot.get("source") not in allowed_screenshot_sources:
                problems.append(f"{flavor}:{screenshot.get('screen')}:source")
    if manifest.get("screenshotCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
        problems.append("screenshotCount")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-ui-preview-gallery/") for name in names):
            problems.append("zip-prefix")
        if "mobile-ui-preview-gallery/mobile-ui-preview-gallery.html" not in names:
            problems.append("zip-html")
        if "mobile-ui-preview-gallery/mobile-ui-readable-overview.svg" not in names:
            problems.append("zip-readable-overview")
        if "mobile-ui-preview-gallery/mobile-ui-readable-overview.png" not in names:
            problems.append("zip-readable-overview-png")
        if "mobile-ui-preview-gallery/mobile-ui-preview-contact-sheet.svg" not in names:
            problems.append("zip-contact-sheet")
        if "mobile-ui-preview-gallery/mobile-ui-preview-contact-sheet.png" not in names:
            problems.append("zip-contact-sheet-png")
        if (
            f"mobile-ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-wysiwyg-home-board")
        if (
            f"mobile-ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-wysiwyg-coolshow-board")
        if (
            f"mobile-ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-wysiwyg-all-template-board")
        if "mobile-ui-preview-gallery/wysiwyg-hongguo-home.png" not in names:
            problems.append("zip-wysiwyg-hongguo-home")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "cloudflare_api_token=",
        "cloudflare-api-token:",
        "bearer ey",
        "sk_live_",
        "sk_test_",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "ui_preview_gallery",
            "failed",
            f"UI preview gallery problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "ui_preview_gallery",
        "passed",
        "UI preview gallery exports an offline HTML preview gallery, WYSIWYG Flutter runtime screenshots, readable template overview, full screenshot contact sheet, PNG review boards, deterministic zip package, and 40 publish-safe Flutter prototype screenshots for tenant review.",
        sorted(set(evidence)),
    )


def check_app_handoff_package(root: Path) -> Check:
    write_store_handoff_manifest(root)
    output_dir = root / "build" / "app-handoff"
    manifest = export_app_handoff.build_handoff(root, output_dir)
    manifest_path = output_dir / "mobile-app-handoff-manifest.json"
    markdown_path = output_dir / "mobile-app-handoff.md"
    html_path = output_dir / "mobile-app-handoff.html"
    embedded_preview_path = output_dir / "mobile-ui-readable-overview.svg"
    embedded_contact_sheet_path = output_dir / "mobile-ui-preview-contact-sheet.svg"
    embedded_preview_png_path = output_dir / "mobile-ui-readable-overview.png"
    embedded_contact_sheet_png_path = output_dir / "mobile-ui-preview-contact-sheet.png"
    embedded_wysiwyg_home_board_path = output_dir / export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE
    embedded_wysiwyg_coolshow_board_path = output_dir / export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE
    embedded_wysiwyg_all_template_board_path = output_dir / export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE
    embedded_external_account_manifest_path = (
        output_dir / "external-account-handoff" / "mobile-external-account-handoff.json"
    )
    embedded_external_account_markdown_path = (
        output_dir / "external-account-handoff" / "mobile-external-account-handoff.md"
    )
    embedded_external_account_package_path = (
        output_dir / "external-account-handoff" / "mobile-external-account-handoff.zip"
    )
    embedded_completion_closure_report_path = (
        output_dir / "completion-closure" / "mobile-completion-closure.json"
    )
    embedded_completion_closure_markdown_path = (
        output_dir / "completion-closure" / "mobile-completion-closure.md"
    )
    package_path = output_dir / "mobile-app-handoff.zip"
    evidence = [
        "build/app-handoff/mobile-app-handoff-manifest.json",
        "build/app-handoff/mobile-app-handoff.md",
        "build/app-handoff/mobile-app-handoff.html",
        "build/app-handoff/mobile-ui-readable-overview.svg",
        "build/app-handoff/mobile-ui-readable-overview.png",
        "build/app-handoff/mobile-ui-preview-contact-sheet.svg",
        "build/app-handoff/mobile-ui-preview-contact-sheet.png",
        f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
        f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
        f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}",
        "build/app-handoff/external-account-handoff/mobile-external-account-handoff.json",
        "build/app-handoff/external-account-handoff/mobile-external-account-handoff.md",
        "build/app-handoff/external-account-handoff/mobile-external-account-handoff.zip",
        "build/app-handoff/completion-closure/mobile-completion-closure.json",
        "build/app-handoff/completion-closure/mobile-completion-closure.md",
        "build/app-handoff/mobile-app-handoff.zip",
    ]
    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_app_handoff_package":
        problems.append("packageType")
    if manifest.get("defaultFlavor") != "hongguo":
        problems.append("defaultFlavor")
    if manifest.get("htmlPath") != "build/app-handoff/mobile-app-handoff.html":
        problems.append("htmlPath")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("htmlSha256", ""))):
        problems.append("htmlSha256")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(
            f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}",
        )
    ui_preview = manifest.get("uiPreview")
    if not isinstance(ui_preview, dict):
        problems.append("uiPreview")
    else:
        if ui_preview.get("readableOverviewPath") != "build/ui-preview-gallery/mobile-ui-readable-overview.svg":
            problems.append("uiPreview.readableOverviewPath")
        if ui_preview.get("readableOverviewPngPath") != "build/ui-preview-gallery/mobile-ui-readable-overview.png":
            problems.append("uiPreview.readableOverviewPngPath")
        if ui_preview.get("contactSheetPath") != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg":
            problems.append("uiPreview.contactSheetPath")
        if ui_preview.get("contactSheetPngPath") != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png":
            problems.append("uiPreview.contactSheetPngPath")
        if ui_preview.get("contactSheetScreenCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
            problems.append("uiPreview.contactSheetScreenCount")
        if ui_preview.get("screenshotCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
            problems.append("uiPreview.screenshotCount")
        wysiwyg_runtime = ui_preview.get("wysiwygRuntimePreviews")
        if not isinstance(wysiwyg_runtime, dict):
            problems.append("uiPreview.wysiwygRuntimePreviews")
        else:
            if wysiwyg_runtime.get("source") != export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE:
                problems.append("uiPreview.wysiwygRuntimePreviews.source")
            if wysiwyg_runtime.get("captureCount") != len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS):
                problems.append("uiPreview.wysiwygRuntimePreviews.captureCount")
            if wysiwyg_runtime.get("boardCount") != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
                problems.append("uiPreview.wysiwygRuntimePreviews.boardCount")
            boards = wysiwyg_runtime.get("boards")
            if not isinstance(boards, list) or len(boards) != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
                problems.append("uiPreview.wysiwygRuntimePreviews.boards")
    if manifest.get("embeddedPreviewPngPath") != "build/app-handoff/mobile-ui-readable-overview.png":
        problems.append("embeddedPreviewPngPath")
    if not embedded_preview_png_path.exists():
        problems.append("missing-embedded-preview-png")
    elif manifest.get("embeddedPreviewPngSha256") != file_sha256(embedded_preview_png_path):
        problems.append("embeddedPreviewPngSha256")
    if manifest.get("embeddedContactSheetPath") != "build/app-handoff/mobile-ui-preview-contact-sheet.svg":
        problems.append("embeddedContactSheetPath")
    if not embedded_contact_sheet_path.exists():
        problems.append("missing-embedded-contact-sheet")
    elif manifest.get("embeddedContactSheetSha256") != file_sha256(embedded_contact_sheet_path):
        problems.append("embeddedContactSheetSha256")
    if manifest.get("embeddedContactSheetPngPath") != "build/app-handoff/mobile-ui-preview-contact-sheet.png":
        problems.append("embeddedContactSheetPngPath")
    if not embedded_contact_sheet_png_path.exists():
        problems.append("missing-embedded-contact-sheet-png")
    elif manifest.get("embeddedContactSheetPngSha256") != file_sha256(embedded_contact_sheet_png_path):
        problems.append("embeddedContactSheetPngSha256")
    expected_wysiwyg_paths = [
        f"build/app-handoff/{file_name}"
        for file_name in export_ui_preview_gallery.WYSIWYG_BOARD_FILES
    ]
    if manifest.get("embeddedWysiwygPreviewPaths") != expected_wysiwyg_paths:
        problems.append("embeddedWysiwygPreviewPaths")
    embedded_wysiwyg_sha = manifest.get("embeddedWysiwygPreviewSha256")
    if not isinstance(embedded_wysiwyg_sha, dict):
        problems.append("embeddedWysiwygPreviewSha256")
        embedded_wysiwyg_sha = {}
    for embedded_wysiwyg_path in [
        embedded_wysiwyg_home_board_path,
        embedded_wysiwyg_coolshow_board_path,
        embedded_wysiwyg_all_template_board_path,
    ]:
        if not embedded_wysiwyg_path.exists():
            problems.append(f"missing-{embedded_wysiwyg_path.name}")
            continue
        expected_sha = embedded_wysiwyg_sha.get(rel(root, embedded_wysiwyg_path))
        if expected_sha != file_sha256(embedded_wysiwyg_path):
            problems.append(f"{embedded_wysiwyg_path.name}:sha256")
    store_preflight = manifest.get("storeSubmissionPreflight")
    if not isinstance(store_preflight, dict):
        problems.append("storeSubmissionPreflight")
    else:
        if store_preflight.get("result") not in {"blocked", "passed", "failed"}:
            problems.append("storeSubmissionPreflight.result")
        summary = store_preflight.get("summary")
        if not isinstance(summary, dict):
            problems.append("storeSubmissionPreflight.summary")
        preflight_flavors = store_preflight.get("flavors")
        if not isinstance(preflight_flavors, list):
            problems.append("storeSubmissionPreflight.flavors")
            preflight_flavors = []
        preflight_by_name = {
            str(item.get("flavor")): item
            for item in preflight_flavors
            if isinstance(item, dict)
        }
        if set(preflight_by_name) != set(STORE_SUBMISSION_FLAVORS):
            problems.append("storeSubmissionPreflight.flavors.set")
        for flavor in STORE_SUBMISSION_FLAVORS:
            row = preflight_by_name.get(flavor)
            if not isinstance(row, dict):
                continue
            if row.get("tenantEvidenceInputPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                problems.append(f"{flavor}:storeSubmissionPreflight.tenantEvidenceInputPath")
            if not row.get("nextAction"):
                problems.append(f"{flavor}:storeSubmissionPreflight.nextAction")
    embedded_starter = manifest.get("embeddedStoreSubmissionStarter")
    if not isinstance(embedded_starter, dict):
        problems.append("embeddedStoreSubmissionStarter")
    else:
        if embedded_starter.get("rootPath") != "build/app-handoff/store-submission-starter":
            problems.append("embeddedStoreSubmissionStarter.rootPath")
        if embedded_starter.get("collectorHtmlPath") != "build/app-handoff/store-submission-starter/store-submission-evidence-collector.html":
            problems.append("embeddedStoreSubmissionStarter.collectorHtmlPath")
        if embedded_starter.get("operatorRunbookPath") != "build/app-handoff/store-submission-starter/store-submission-operator-runbook.md":
            problems.append("embeddedStoreSubmissionStarter.operatorRunbookPath")
    external_account = manifest.get("embeddedExternalAccountHandoff")
    if not isinstance(external_account, dict):
        problems.append("embeddedExternalAccountHandoff")
    else:
        if external_account.get("rootPath") != "build/app-handoff/external-account-handoff":
            problems.append("embeddedExternalAccountHandoff.rootPath")
        if external_account.get("manifestPath") != "build/app-handoff/external-account-handoff/mobile-external-account-handoff.json":
            problems.append("embeddedExternalAccountHandoff.manifestPath")
        if external_account.get("markdownPath") != "build/app-handoff/external-account-handoff/mobile-external-account-handoff.md":
            problems.append("embeddedExternalAccountHandoff.markdownPath")
        if external_account.get("packagePath") != "build/app-handoff/external-account-handoff/mobile-external-account-handoff.zip":
            problems.append("embeddedExternalAccountHandoff.packagePath")
        if external_account.get("sectionCount") != 6:
            problems.append("embeddedExternalAccountHandoff.sectionCount")
        if external_account.get("flavorCount") != len(STORE_SUBMISSION_FLAVORS):
            problems.append("embeddedExternalAccountHandoff.flavorCount")
        if external_account.get("strictImportCommand") != "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
            problems.append("embeddedExternalAccountHandoff.strictImportCommand")
        if "外部账号与签名资料接入入口" not in str(external_account.get("tenantPortalEntry", "")):
            problems.append("embeddedExternalAccountHandoff.tenantPortalEntry")
        if "Public account status" not in str(external_account.get("noCredentialBoundary", "")):
            problems.append("embeddedExternalAccountHandoff.noCredentialBoundary")
        if external_account.get("disallowedValueMarkerHits") != []:
            problems.append("embeddedExternalAccountHandoff.disallowedValueMarkerHits")
        if (
            not embedded_external_account_manifest_path.exists()
            or external_account.get("manifestSha256") != file_sha256(embedded_external_account_manifest_path)
        ):
            problems.append("embeddedExternalAccountHandoff.manifestSha256")
        if (
            not embedded_external_account_markdown_path.exists()
            or external_account.get("markdownSha256") != file_sha256(embedded_external_account_markdown_path)
        ):
            problems.append("embeddedExternalAccountHandoff.markdownSha256")
        if (
            not embedded_external_account_package_path.exists()
            or external_account.get("packageSha256") != file_sha256(embedded_external_account_package_path)
        ):
            problems.append("embeddedExternalAccountHandoff.packageSha256")
    completion_closure = manifest.get("embeddedCompletionClosure")
    if not isinstance(completion_closure, dict):
        problems.append("embeddedCompletionClosure")
    else:
        if completion_closure.get("rootPath") != "build/app-handoff/completion-closure":
            problems.append("embeddedCompletionClosure.rootPath")
        if completion_closure.get("reportPath") != "build/app-handoff/completion-closure/mobile-completion-closure.json":
            problems.append("embeddedCompletionClosure.reportPath")
        if completion_closure.get("markdownPath") != "build/app-handoff/completion-closure/mobile-completion-closure.md":
            problems.append("embeddedCompletionClosure.markdownPath")
        if completion_closure.get("reportPresent") is not True:
            problems.append("embeddedCompletionClosure.reportPresent")
        if completion_closure.get("markdownPresent") is not True:
            problems.append("embeddedCompletionClosure.markdownPresent")
        if not isinstance(completion_closure.get("canClaimComplete"), bool):
            problems.append("embeddedCompletionClosure.canClaimComplete")
        if not isinstance(completion_closure.get("blockerIds"), list):
            problems.append("embeddedCompletionClosure.blockerIds")
        if (
            not embedded_completion_closure_report_path.exists()
            or completion_closure.get("reportSha256") != file_sha256(embedded_completion_closure_report_path)
        ):
            problems.append("embeddedCompletionClosure.reportSha256")
        if (
            not embedded_completion_closure_markdown_path.exists()
            or completion_closure.get("markdownSha256") != file_sha256(embedded_completion_closure_markdown_path)
        ):
            problems.append("embeddedCompletionClosure.markdownSha256")
    input_workspace = manifest.get("embeddedStoreSubmissionInputWorkspace")
    if not isinstance(input_workspace, dict):
        problems.append("embeddedStoreSubmissionInputWorkspace")
        workspace_inputs = []
    else:
        if input_workspace.get("rootPath") != "build/app-handoff/store-submission-evidence":
            problems.append("embeddedStoreSubmissionInputWorkspace.rootPath")
        if input_workspace.get("manifestPath") != "build/app-handoff/store-submission-evidence/store-submission-input-workspace.json":
            problems.append("embeddedStoreSubmissionInputWorkspace.manifestPath")
        if input_workspace.get("markdownPath") != "build/app-handoff/store-submission-evidence/store-submission-input-workspace.md":
            problems.append("embeddedStoreSubmissionInputWorkspace.markdownPath")
        if input_workspace.get("preflightReportPath") != "build/app-handoff/store-submission-evidence/store-submission-evidence-preflight.json":
            problems.append("embeddedStoreSubmissionInputWorkspace.preflightReportPath")
        if input_workspace.get("preflightMarkdownPath") != "build/app-handoff/store-submission-evidence/store-submission-evidence-preflight.md":
            problems.append("embeddedStoreSubmissionInputWorkspace.preflightMarkdownPath")
        summary = input_workspace.get("preflightSummary")
        if not isinstance(summary, dict):
            problems.append("embeddedStoreSubmissionInputWorkspace.preflightSummary")
        elif summary.get("strictImportReady") is True and store_preflight and store_preflight.get("result") != "passed":
            problems.append("embeddedStoreSubmissionInputWorkspace.preflightSummary.strictImportReady")
        workspace_inputs = input_workspace.get("inputs")
        if not isinstance(workspace_inputs, list):
            problems.append("embeddedStoreSubmissionInputWorkspace.inputs")
            workspace_inputs = []
        workspace_by_name = {
            str(item.get("flavor")): item
            for item in workspace_inputs
            if isinstance(item, dict)
        }
        if set(workspace_by_name) != set(STORE_SUBMISSION_FLAVORS):
            problems.append("embeddedStoreSubmissionInputWorkspace.inputs.set")
        for flavor in STORE_SUBMISSION_FLAVORS:
            row = workspace_by_name.get(flavor)
            if not isinstance(row, dict):
                continue
            if row.get("embeddedPath") != f"build/app-handoff/store-submission-evidence/flavors/{flavor}.input.json":
                problems.append(f"{flavor}:embeddedStoreSubmissionInputWorkspace.embeddedPath")
            if row.get("targetPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                problems.append(f"{flavor}:embeddedStoreSubmissionInputWorkspace.targetPath")
            if row.get("readyForStrictImport") is True and store_preflight and store_preflight.get("result") != "passed":
                problems.append(f"{flavor}:embeddedStoreSubmissionInputWorkspace.readyForStrictImport")
            if not row.get("preflightBlockers") and store_preflight and store_preflight.get("result") != "passed":
                problems.append(f"{flavor}:embeddedStoreSubmissionInputWorkspace.preflightBlockers")
    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_name = {
        str(item.get("flavor")): item
        for item in flavors
        if isinstance(item, dict)
    }
    if set(by_name) != set(STORE_SUBMISSION_FLAVORS):
        problems.append("flavors.set")
    for flavor, defaults in STORE_SUBMISSION_FLAVORS.items():
        item = by_name.get(flavor)
        if not isinstance(item, dict):
            continue
        if item.get("appName") != defaults["appName"]:
            problems.append(f"{flavor}:appName")
        if item.get("applicationId") != defaults["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if item.get("bundleId") != defaults["applicationId"]:
            problems.append(f"{flavor}:bundleId")
        if item.get("storeComplianceMode") != defaults["storeComplianceMode"]:
            problems.append(f"{flavor}:storeComplianceMode")
        if item.get("primaryChannel") != defaults["primaryChannel"]:
            problems.append(f"{flavor}:primaryChannel")
        artifacts = item.get("androidArtifacts")
        if not isinstance(artifacts, dict):
            problems.append(f"{flavor}:androidArtifacts")
            artifacts = {}
        if flavor in FLAVORS:
            for key in ["releaseApk", "releaseAppBundle"]:
                artifact = artifacts.get(key)
                if not isinstance(artifact, dict):
                    problems.append(f"{flavor}:{key}")
                    continue
                path = artifact.get("path")
                if not path or not (root / str(path)).exists():
                    problems.append(f"{flavor}:{key}:path")
                if not re.fullmatch(r"[a-f0-9]{64}", str(artifact.get("sha256", ""))):
                    problems.append(f"{flavor}:{key}:sha256")
        runtime_smoke = item.get("androidRuntimeSmoke")
        if not isinstance(runtime_smoke, dict):
            problems.append(f"{flavor}:androidRuntimeSmoke")
        elif flavor in FLAVORS and runtime_smoke.get("launchResult") != "passed":
            problems.append(f"{flavor}:androidRuntimeSmoke.launchResult")
        store_submission = item.get("storeSubmission")
        if not isinstance(store_submission, dict):
            problems.append(f"{flavor}:storeSubmission")
        else:
            expected_path = f"build/store-submission-evidence/flavors/{flavor}.input.json"
            if store_submission.get("tenantEvidenceInputPath") != expected_path:
                problems.append(f"{flavor}:storeSubmission.tenantEvidenceInputPath")
            if not store_submission.get("requiredChecklistFlags"):
                problems.append(f"{flavor}:storeSubmission.requiredChecklistFlags")
        actions = item.get("tenantRequiredActions")
        if not isinstance(actions, dict):
            problems.append(f"{flavor}:tenantRequiredActions")
        else:
            for key in [
                "replaceSigningMaterial",
                "configureTenantEdgeSecretsServerSide",
                "importStoreSubmissionEvidence",
            ]:
                if actions.get(key) is not True:
                    problems.append(f"{flavor}:tenantRequiredActions.{key}")
    if not manifest_path.exists():
        problems.append("missing-manifest")
    if not markdown_path.exists():
        problems.append("missing-markdown")
    if not html_path.exists():
        problems.append("missing-html")
    else:
        if manifest.get("htmlSha256") != file_sha256(html_path):
            problems.append("htmlSha256-mismatch")
        html = html_path.read_text(encoding="utf-8")
        for snippet in [
            "GoldFruit Drama",
            "app-hongguo-release.apk",
            "mobile-ui-readable-overview.svg",
            "mobile-ui-readable-overview.png",
            "mobile-ui-preview-contact-sheet.svg",
            "mobile-ui-preview-contact-sheet.png",
            export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE,
            export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE,
            export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE,
            "store-submission-evidence/flavors/hongguo.input.json",
            "Store submission input workspace",
            "External account and signing checklist",
            "mobile-external-account-handoff.md",
        ]:
            if snippet not in html:
                problems.append(f"html-missing:{snippet}")
    if not embedded_preview_path.exists():
        problems.append("missing-embedded-preview")
    elif manifest.get("embeddedPreviewSha256") != file_sha256(embedded_preview_path):
        problems.append("embeddedPreviewSha256")
    if not package_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(package_path):
        problems.append("packageSha256")
    if package_path.exists():
        try:
            with zipfile.ZipFile(package_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-app-handoff/") for name in names):
            problems.append("zip-prefix")
        if "mobile-app-handoff/mobile-app-handoff.md" not in names:
            problems.append("zip-markdown")
        if "mobile-app-handoff/mobile-app-handoff.html" not in names:
            problems.append("zip-html")
        if "mobile-app-handoff/mobile-ui-readable-overview.svg" not in names:
            problems.append("zip-embedded-preview")
        if "mobile-app-handoff/mobile-ui-readable-overview.png" not in names:
            problems.append("zip-embedded-preview-png")
        if "mobile-app-handoff/mobile-ui-preview-contact-sheet.svg" not in names:
            problems.append("zip-embedded-contact-sheet")
        if "mobile-app-handoff/mobile-ui-preview-contact-sheet.png" not in names:
            problems.append("zip-embedded-contact-sheet-png")
        if (
            f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-embedded-wysiwyg-home-board")
        if (
            f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-embedded-wysiwyg-coolshow-board")
        if (
            f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}"
            not in names
        ):
            problems.append("zip-embedded-wysiwyg-all-template-board")
        if "mobile-app-handoff/store-submission-starter/store-submission-evidence-collector.html" not in names:
            problems.append("zip-starter-collector")
        if "mobile-app-handoff/store-submission-starter/store-submission-operator-runbook.md" not in names:
            problems.append("zip-starter-runbook")
        if "mobile-app-handoff/store-submission-evidence/store-submission-input-workspace.json" not in names:
            problems.append("zip-input-workspace-manifest")
        if "mobile-app-handoff/store-submission-evidence/store-submission-input-workspace.md" not in names:
            problems.append("zip-input-workspace-markdown")
        if "mobile-app-handoff/store-submission-evidence/store-submission-evidence-preflight.json" not in names:
            problems.append("zip-input-workspace-preflight")
        if "mobile-app-handoff/store-submission-evidence/store-submission-evidence-preflight.md" not in names:
            problems.append("zip-input-workspace-preflight-markdown")
        if "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.json" not in names:
            problems.append("zip-external-account-manifest")
        if "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.md" not in names:
            problems.append("zip-external-account-markdown")
        if "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.zip" not in names:
            problems.append("zip-external-account-package")
        for flavor in STORE_SUBMISSION_FLAVORS:
            if f"mobile-app-handoff/store-submission-starter/{flavor}/store-submission-evidence.input.example.json" not in names:
                problems.append(f"{flavor}:zip-starter-input")
            if f"mobile-app-handoff/store-submission-starter/{flavor}/operator-checklist.md" not in names:
                problems.append(f"{flavor}:zip-starter-checklist")
            if f"mobile-app-handoff/store-submission-starter/{flavor}/submission-runbook.md" not in names:
                problems.append(f"{flavor}:zip-starter-submission-runbook")
            if f"mobile-app-handoff/store-submission-evidence/flavors/{flavor}.input.json" not in names:
                problems.append(f"{flavor}:zip-input-workspace-input")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")
    if problems:
        return Check(
            "app_handoff_package",
            "failed",
            f"App handoff package problems: {', '.join(problems)}",
        sorted(set(evidence)),
    )
    return Check(
        "app_handoff_package",
        "passed",
        "App handoff package exports per-flavor tenant app handoff metadata, five tenant release flavor rows, Android release artifacts/runtime smoke evidence for native template flavors, CoolShow store-submission handoff metadata, offline HTML UI preview, embedded SVG/PNG contact sheets, external account handoff checklist, completion closure report, store evidence input paths, embedded store-submission starter files, store-submission preflight next actions, tenant actions, and no-secret boundaries.",
        sorted(set(evidence)),
    )


def check_ios_ci_handoff_package(root: Path) -> Check:
    manifest_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
    evidence = ["build/ios-ci-handoff/ios-ci-handoff-manifest.json"]
    if not manifest_path.exists():
        return Check(
            "ios_ci_handoff_package",
            "missing",
            "iOS CI handoff manifest is missing; run scripts/export_ios_ci_handoff.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "ios_ci_handoff_package",
            "failed",
            f"iOS CI handoff manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_ios_ci_handoff":
        problems.append("packageType")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")

    zip_path = root / str(manifest.get("packagePath", ""))
    evidence.append(rel(root, zip_path))
    if not zip_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(zip_path):
        problems.append("packageSha256")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-ios-ci-handoff/") for name in names):
            problems.append("zip-prefix")

    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict):
        problems.append("workflow")
    else:
        if workflow.get("path") != ".github/workflows/mobile-flutter.yml":
            problems.append("workflow.path")
        if workflow.get("workflowDispatch") is not True:
            problems.append("workflow.workflowDispatch")
        if workflow.get("iosJob") != "ios-build":
            problems.append("workflow.iosJob")
        if workflow.get("runner") != "macos-15":
            problems.append("workflow.runner")
        if workflow.get("xcodeVersion") != "latest-stable":
            problems.append("workflow.xcodeVersion")
        if workflow.get("missingRequiredMarkers"):
            problems.append(f"workflow.missingRequiredMarkers={workflow.get('missingRequiredMarkers')!r}")

    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(item.get("flavor")): item
        for item in flavors
        if isinstance(item, dict)
    }
    for flavor, expected in FLAVORS.items():
        item = by_flavor.get(flavor)
        if not isinstance(item, dict):
            problems.append(f"{flavor}:missing")
            continue
        if item.get("appName") != expected["appName"]:
            problems.append(f"{flavor}:appName")
        if item.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if item.get("bundleId") != expected["applicationId"]:
            problems.append(f"{flavor}:bundleId")
        if item.get("styleTemplate") != expected["styleTemplate"]:
            problems.append(f"{flavor}:styleTemplate")
        for key in ["xcconfig", "xcodeScheme", "infoPlist", "privacyManifest", "entitlements", "appIcon"]:
            path_value = item.get(key)
            if not isinstance(path_value, str) or not (root / path_value).exists():
                problems.append(f"{flavor}:{key}")
            elif key in {"xcconfig", "xcodeScheme", "appIcon"}:
                evidence.append(path_value)
        ci = item.get("ci")
        if not isinstance(ci, dict):
            problems.append(f"{flavor}:ci")
        else:
            if ci.get("job") != "ios-build":
                problems.append(f"{flavor}:ci.job")
            if ci.get("runner") != "macos-15":
                problems.append(f"{flavor}:ci.runner")
            if ci.get("artifactName") != f"mobile-{flavor}-ios-unsigned":
                problems.append(f"{flavor}:ci.artifactName")
            if ci.get("debugCommand") != f"./scripts/build_flavor.sh {flavor} ios debug":
                problems.append(f"{flavor}:ci.debugCommand")
            if ci.get("releaseCommand") != f"./scripts/build_flavor.sh {flavor} ios release":
                problems.append(f"{flavor}:ci.releaseCommand")
        verification = item.get("verification")
        if not isinstance(verification, dict):
            problems.append(f"{flavor}:verification")
        else:
            if verification.get("triggerCommand") != "gh workflow run mobile-flutter.yml":
                problems.append(f"{flavor}:verification.triggerCommand")
            if "ios_build_matrix.py all" not in str(verification.get("completionGate", "")):
                problems.append(f"{flavor}:verification.completionGate")

    if set(by_flavor) != set(FLAVORS):
        problems.append("flavor-set")
    workflow_steps = manifest.get("tenantWorkflow")
    if not isinstance(workflow_steps, list) or len(workflow_steps) < 5:
        problems.append("tenantWorkflow")

    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "cloudflare_api_token=",
        "cloudflare-api-token:",
        "bearer ey",
        "sk_live_",
        "sk_test_",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "ios_ci_handoff_package",
            "failed",
            f"iOS CI handoff package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "ios_ci_handoff_package",
        "passed",
        "iOS CI handoff package maps all five flavors to the manual GitHub Actions trigger, macOS/Xcode runner, unsigned build artifact names, native metadata paths, tenant Apple actions, and no-credential boundary.",
        sorted(set(evidence)),
    )


def check_store_signing_handoff_package(root: Path) -> Check:
    output_dir = root / "build" / "store-signing-handoff"
    manifest_path = output_dir / "store-signing-handoff-manifest.json"
    evidence = ["build/store-signing-handoff/store-signing-handoff-manifest.json"]
    try:
        write_store_handoff_manifest(root)
        manifest = export_store_signing_handoff.build_handoff(output_dir)
    except (OSError, json.JSONDecodeError, SystemExit) as error:
        return Check(
            "store_signing_handoff_package",
            "failed",
            f"Store signing handoff package could not be exported: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_store_signing_handoff":
        problems.append("packageType")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")

    zip_path = root / str(manifest.get("packagePath", ""))
    evidence.append(rel(root, zip_path))
    if not zip_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(zip_path):
        problems.append("packageSha256")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-store-signing-handoff/") for name in names):
            problems.append("zip-prefix")

    source_manifests = manifest.get("sourceManifests")
    if not isinstance(source_manifests, dict):
        problems.append("sourceManifests")
    else:
        if source_manifests.get("storeHandoff") != "build/release-handoff/mobile-store-handoff.json":
            problems.append("sourceManifests.storeHandoff")
        if source_manifests.get("iosCiHandoff") != "build/ios-ci-handoff/ios-ci-handoff-manifest.json":
            problems.append("sourceManifests.iosCiHandoff")

    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(entry.get("flavor")): entry
        for entry in flavors
        if isinstance(entry, dict)
    }
    if set(by_flavor) != set(STORE_SUBMISSION_FLAVORS):
        problems.append(f"flavors={sorted(by_flavor)}")
    for flavor, defaults in STORE_SUBMISSION_FLAVORS.items():
        entry = by_flavor.get(flavor)
        if not isinstance(entry, dict):
            problems.append(f"{flavor}:missing")
            continue
        config_dir = root / "assets" / "config" / flavor
        try:
            template = json.loads(read_text(config_dir / "tenant.template.json"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            problems.append(f"{flavor}:tenant.template.json:{error}")
            continue
        expected = {
            "appName": str(defaults["appName"]),
            "applicationId": str(defaults["applicationId"]),
            "styleTemplate": str(template.get("styleTemplate", flavor)),
        }
        if entry.get("appName") != expected["appName"]:
            problems.append(f"{flavor}:appName")
        if entry.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if entry.get("bundleId") != expected["applicationId"]:
            problems.append(f"{flavor}:bundleId")
        ios = entry.get("ios")
        if not isinstance(ios, dict):
            problems.append(f"{flavor}:ios")
        else:
            template = ios.get("exportOptionsTemplate")
            if not isinstance(template, dict):
                problems.append(f"{flavor}:ios.exportOptionsTemplate")
            else:
                template_path = root / "build" / "store-signing-handoff" / str(template.get("path", ""))
                evidence.append(rel(root, template_path))
                if not template_path.exists():
                    problems.append(f"{flavor}:ios.exportOptionsTemplate:file")
                elif template.get("sha256") != file_sha256(template_path):
                    problems.append(f"{flavor}:ios.exportOptionsTemplate:sha256")
                if template.get("method") != "app-store-connect":
                    problems.append(f"{flavor}:ios.exportOptionsTemplate:method")
                if template.get("signingStyle") != "manual":
                    problems.append(f"{flavor}:ios.exportOptionsTemplate:signingStyle")
            if f"--flavor {flavor}" not in str(ios.get("archiveCommand", "")):
                problems.append(f"{flavor}:ios.archiveCommand")
            ios_actions = ios.get("tenantRequiredActions")
            if not isinstance(ios_actions, list) or len(ios_actions) < 5:
                problems.append(f"{flavor}:ios.tenantRequiredActions")
        android = entry.get("android")
        if not isinstance(android, dict):
            problems.append(f"{flavor}:android")
        else:
            template = android.get("signingTemplate")
            if not isinstance(template, dict):
                problems.append(f"{flavor}:android.signingTemplate")
            else:
                template_path = root / "build" / "store-signing-handoff" / str(template.get("path", ""))
                evidence.append(rel(root, template_path))
                if not template_path.exists():
                    problems.append(f"{flavor}:android.signingTemplate:file")
                elif template.get("sha256") != file_sha256(template_path):
                    problems.append(f"{flavor}:android.signingTemplate:sha256")
                if template.get("applicationId") != expected["applicationId"]:
                    problems.append(f"{flavor}:android.signingTemplate:applicationId")
            if android.get("playUploadCommand") != f"./scripts/build_flavor.sh {flavor} android release appbundle":
                problems.append(f"{flavor}:android.playUploadCommand")
            if android.get("directDistributionCommand") != f"./scripts/build_flavor.sh {flavor} android release apk":
                problems.append(f"{flavor}:android.directDistributionCommand")
        secret_boundary = entry.get("secretBoundary")
        if not isinstance(secret_boundary, dict):
            problems.append(f"{flavor}:secretBoundary")
        else:
            for key in [
                "containsSigningMaterial",
                "containsAppleTeamId",
                "containsProvisioningProfile",
                "containsAndroidKeystore",
                "containsProviderCredentials",
            ]:
                if secret_boundary.get(key) is not False:
                    problems.append(f"{flavor}:secretBoundary:{key}")

    workflow_steps = manifest.get("tenantWorkflow")
    if not isinstance(workflow_steps, list) or len(workflow_steps) < 5:
        problems.append("tenantWorkflow")

    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "cloudflare_api_token=",
        "cloudflare-api-token:",
        "bearer ey",
        "sk_live_",
        "sk_test_",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "store_signing_handoff_package",
            "failed",
            f"Store signing handoff package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "store_signing_handoff_package",
        "passed",
        "Store signing handoff package exports iOS export-options templates, Android signing placeholders, tenant Apple/Google/direct-distribution actions, release artifact references, and a no-signing-material boundary for all five tenant release flavors.",
        sorted(set(evidence)),
    )


def check_store_publish_config_package(root: Path) -> Check:
    manifest_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
    evidence = ["build/store-publish-config/store-publish-config-manifest.json"]
    if not manifest_path.exists():
        return Check(
            "store_publish_config_package",
            "missing",
            "Store publish config manifest is missing; run scripts/export_store_publish_config.py.",
            evidence,
        )
    try:
        manifest = json.loads(read_text(manifest_path))
    except json.JSONDecodeError as error:
        return Check(
            "store_publish_config_package",
            "failed",
            f"Store publish config manifest is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_store_publish_config":
        problems.append("packageType")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append(f"disallowedValueMarkerHits={manifest.get('disallowedValueMarkerHits')!r}")

    zip_path = root / str(manifest.get("packagePath", ""))
    evidence.append(rel(root, zip_path))
    if not zip_path.exists():
        problems.append("missing-zip")
    elif manifest.get("packageSha256") != file_sha256(zip_path):
        problems.append("packageSha256")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = []
        if not names or not all(name.startswith("mobile-store-publish-config/") for name in names):
            problems.append("zip-prefix")

    source_manifests = manifest.get("sourceManifests")
    if not isinstance(source_manifests, dict):
        problems.append("sourceManifests")
    else:
        for key, expected_path in [
            ("storeHandoff", "build/release-handoff/mobile-store-handoff.json"),
            ("storeAssets", "build/store-assets/store-assets-manifest.json"),
            ("storeSigningHandoff", "build/store-signing-handoff/store-signing-handoff-manifest.json"),
        ]:
            item = source_manifests.get(key)
            if not isinstance(item, dict) or item.get("path") != expected_path:
                problems.append(f"sourceManifests.{key}.path")

    flavors = manifest.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(entry.get("flavor")): entry
        for entry in flavors
        if isinstance(entry, dict)
    }
    if set(by_flavor) != set(FLAVORS):
        problems.append("flavor-set")
    for flavor, expected in FLAVORS.items():
        entry = by_flavor.get(flavor)
        if not isinstance(entry, dict):
            problems.append(f"{flavor}:missing")
            continue
        if entry.get("appName") != expected["appName"]:
            problems.append(f"{flavor}:appName")
        if entry.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if entry.get("bundleId") != expected["applicationId"]:
            problems.append(f"{flavor}:bundleId")
        if entry.get("containsSecrets") is not False:
            problems.append(f"{flavor}:containsSecrets")
        template_path = root / "build" / "store-publish-config" / str(entry.get("templatePath", ""))
        evidence.append(rel(root, template_path))
        if not template_path.exists():
            problems.append(f"{flavor}:template:file")
            continue
        if entry.get("templateSha256") != file_sha256(template_path):
            problems.append(f"{flavor}:template:sha256")
        try:
            template = json.loads(read_text(template_path))
        except json.JSONDecodeError as error:
            problems.append(f"{flavor}:template:json:{error}")
            continue
        identity = template.get("appIdentity")
        if not isinstance(identity, dict):
            problems.append(f"{flavor}:appIdentity")
        else:
            if identity.get("applicationId") != expected["applicationId"]:
                problems.append(f"{flavor}:appIdentity.applicationId")
            if identity.get("tenantMayReplaceIds") is not True:
                problems.append(f"{flavor}:appIdentity.tenantMayReplaceIds")
        legal_urls = template.get("legalUrls")
        if not isinstance(legal_urls, dict):
            problems.append(f"{flavor}:legalUrls")
        else:
            for key in ["supportUrl", "termsUrl", "privacyUrl"]:
                if not legal_urls.get(key):
                    problems.append(f"{flavor}:legalUrls:{key}")
        oauth_callbacks = template.get("oauthCallbacks")
        if not isinstance(oauth_callbacks, dict) or oauth_callbacks.get("credentialsStayServerSide") is not True:
            problems.append(f"{flavor}:oauthCallbacks")
        app_store = template.get("appStoreConnect")
        google_play = template.get("googlePlayConsole")
        android_direct = template.get("androidDirect")
        if not isinstance(app_store, dict) or not isinstance(google_play, dict) or not isinstance(android_direct, dict):
            problems.append(f"{flavor}:storeSections")
        else:
            enabled_stores = {
                "appStoreConnect": bool(app_store.get("enabled")),
                "googlePlayConsole": bool(google_play.get("enabled")),
                "androidDirect": bool(android_direct.get("enabled")),
            }
            listed_enabled = set(entry.get("enabledStores", []))
            if listed_enabled != {key for key, enabled in enabled_stores.items() if enabled}:
                problems.append(f"{flavor}:enabledStores")
            if template.get("storeComplianceMode") == "app_store" and not app_store.get("inAppPurchases"):
                problems.append(f"{flavor}:appStoreConnect.inAppPurchases")
            if template.get("storeComplianceMode") == "play_store" and not google_play.get("playBillingProducts"):
                problems.append(f"{flavor}:googlePlayConsole.playBillingProducts")
            if template.get("storeComplianceMode") == "android_direct" and not android_direct.get("externalPaymentProviders"):
                problems.append(f"{flavor}:androidDirect.externalPaymentProviders")
        server_boundary = template.get("serverSideCredentialBoundary")
        if not isinstance(server_boundary, dict):
            problems.append(f"{flavor}:serverSideCredentialBoundary")
        else:
            if server_boundary.get("mobileClientStoresProviderCredentials") is not False:
                problems.append(f"{flavor}:serverSideCredentialBoundary.mobileClientStoresProviderCredentials")
            if server_boundary.get("mobileClientStoresSigningMaterial") is not False:
                problems.append(f"{flavor}:serverSideCredentialBoundary.mobileClientStoresSigningMaterial")

    workflow_steps = manifest.get("tenantWorkflow")
    if not isinstance(workflow_steps, list) or len(workflow_steps) < 5:
        problems.append("tenantWorkflow")
    serialized = json.dumps(manifest, ensure_ascii=False).lower()
    for marker in [
        "cloudflare_api_token=",
        "cloudflare-api-token:",
        "bearer ey",
        "sk_live_",
        "sk_test_",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "store_publish_config_package",
            "failed",
            f"Store publish config package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "store_publish_config_package",
        "passed",
        "Store publish config package exports tenant-fillable App Store, Google Play, and Android direct release templates with legal URLs, OAuth callbacks, product ids, data-safety starters, and no client-side credentials for all five flavors.",
        sorted(set(evidence)),
    )


def check_external_account_handoff_package(root: Path) -> Check:
    output_dir = root / "build" / "external-account-handoff"
    manifest_path = output_dir / "mobile-external-account-handoff.json"
    markdown_path = output_dir / "mobile-external-account-handoff.md"
    package_path = output_dir / "mobile-external-account-handoff.zip"
    evidence = [
        "scripts/export_external_account_handoff.py",
        rel(root, manifest_path),
        rel(root, markdown_path),
        rel(root, package_path),
    ]
    try:
        manifest = export_external_account_handoff.export_handoff(root, output_dir)
    except Exception as error:  # pragma: no cover - defensive audit path
        return Check(
            "external_account_handoff_package",
            "failed",
            f"External account handoff export failed: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if manifest.get("packageType") != "mobile_external_account_handoff":
        problems.append("packageType")
    if manifest.get("manifestPath") != "build/external-account-handoff/mobile-external-account-handoff.json":
        problems.append("manifestPath")
    if manifest.get("markdownPath") != "build/external-account-handoff/mobile-external-account-handoff.md":
        problems.append("markdownPath")
    if manifest.get("packagePath") != "build/external-account-handoff/mobile-external-account-handoff.zip":
        problems.append("packagePath")
    if manifest.get("strictImportCommand") != "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
        problems.append("strictImportCommand")
    if "外部账号与签名资料接入入口" not in str(manifest.get("tenantPortalEntry", "")):
        problems.append("tenantPortalEntry")
    if "Public account status" not in str(manifest.get("noCredentialBoundary", "")):
        problems.append("noCredentialBoundary")
    if manifest.get("disallowedValueMarkerHits") != []:
        problems.append("disallowedValueMarkerHits")
    if not markdown_path.exists() or manifest.get("markdownSha256") != file_sha256(markdown_path):
        problems.append("markdownSha256")
    if not package_path.exists() or manifest.get("packageSha256") != file_sha256(package_path):
        problems.append("packageSha256")
    sections = manifest.get("sections")
    if not isinstance(sections, list) or len(sections) != 6:
        problems.append("sections")
        sections = []
    section_ids = {
        str(section.get("id"))
        for section in sections
        if isinstance(section, dict)
    }
    for section_id in [
        "apple_developer",
        "google_play",
        "android_direct",
        "oauth_social_login",
        "consumer_payments",
        "legal_review",
    ]:
        if section_id not in section_ids:
            problems.append(f"section:{section_id}")
    flavors = manifest.get("flavors")
    if not isinstance(flavors, list) or len(flavors) != len(STORE_SUBMISSION_FLAVORS):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(row.get("flavor")): row
        for row in flavors
        if isinstance(row, dict)
    }
    if set(by_flavor) != set(STORE_SUBMISSION_FLAVORS):
        problems.append("flavor-set")
    for flavor, row in by_flavor.items():
        if row.get("tenantEvidenceInputPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
            problems.append(f"{flavor}:tenantEvidenceInputPath")
        required_sections = row.get("requiredSections")
        if not isinstance(required_sections, list) or len(required_sections) < 4:
            problems.append(f"{flavor}:requiredSections")
        if not row.get("storeSubmissionRequiredFlags"):
            problems.append(f"{flavor}:storeSubmissionRequiredFlags")
    if not manifest_path.exists():
        problems.append("manifestFile")
    if package_path.exists():
        try:
            with zipfile.ZipFile(package_path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
            names = set()
        for expected_name in [
            "mobile-external-account-handoff/mobile-external-account-handoff.json",
            "mobile-external-account-handoff/mobile-external-account-handoff.md",
        ]:
            if expected_name not in names:
                problems.append(f"zip-entry:{expected_name}")
    if markdown_path.exists():
        markdown = read_text(markdown_path)
        for marker in [
            "# Mobile External Account Handoff",
            "Apple Developer and App Store Connect",
            "Google Play Console",
            "Android Direct Distribution",
            "OAuth and Social Login",
            "Consumer Payments",
            "Legal, Support, and Review",
            "No-Credential Boundary",
        ]:
            if marker not in markdown:
                problems.append(f"markdown:{marker}")

    if problems:
        return Check(
            "external_account_handoff_package",
            "failed",
            f"External account handoff package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "external_account_handoff_package",
        "passed",
        "External account handoff package exports no-secret Apple, Google Play, Android direct, OAuth, consumer payment, and legal review checklists for all configured store-submission flavors.",
        sorted(set(evidence)),
    )


def check_store_submission_starter_package(root: Path) -> Check:
    output_dir = root / "build" / "store-submission-starter"
    with export_store_submission_starter.starter_output_lock(output_dir):
        return _check_store_submission_starter_package_locked(root, output_dir)


def _check_store_submission_starter_package_locked(root: Path, output_dir: Path) -> Check:
    manifest_path = output_dir / "store-submission-starter-manifest.json"
    package_path = output_dir / "mobile-store-submission-starter.zip"
    evidence = [
        "scripts/export_store_submission_starter.py",
        rel(root, manifest_path),
        rel(root, package_path),
    ]
    try:
        manifest = export_store_submission_starter.export_starter(root, output_dir, lock=False)
    except Exception as error:  # pragma: no cover - defensive audit path
        return Check(
            "store_submission_starter_package",
            "failed",
            f"Store submission starter export failed: {error}",
            evidence,
        )

    problems: list[str] = []
    if manifest.get("packageType") != "mobile_store_submission_starter":
        problems.append("packageType")
    if manifest.get("disallowedValueMarkerHits"):
        problems.append("disallowedValueMarkerHits")
    if not package_path.exists() or manifest.get("packageSha256") != file_sha256(package_path):
        problems.append("packageSha256")
    collector_path = output_dir / str(manifest.get("collectorHtmlPath", ""))
    evidence.append(rel(root, collector_path))
    if manifest.get("collectorHtmlPath") != "store-submission-evidence-collector.html":
        problems.append("collectorHtmlPath")
    if not collector_path.exists() or manifest.get("collectorHtmlSha256") != file_sha256(collector_path):
        problems.append("collectorHtmlSha256")
    else:
        collector_text = read_text(collector_path)
        for marker in [
            "Store Submission Evidence Collector",
            "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            "Per-flavor input files take precedence",
            "tenant_store_submission_public_evidence_input",
        ]:
            if marker not in collector_text:
                problems.append(f"collectorHtml:{marker}")
    operator_runbook_path = output_dir / str(manifest.get("operatorRunbookPath", ""))
    evidence.append(rel(root, operator_runbook_path))
    if manifest.get("operatorRunbookPath") != "store-submission-operator-runbook.md":
        problems.append("operatorRunbookPath")
    if not operator_runbook_path.exists() or manifest.get("operatorRunbookSha256") != file_sha256(operator_runbook_path):
        problems.append("operatorRunbookSha256")
    else:
        operator_runbook_text = read_text(operator_runbook_path)
        for marker in [
            "ExportOptions.plist.template",
            "android-signing.properties.template",
            "publish-config.template.json",
            "store-submission-evidence-collector.html",
            "import_store_submission_evidence.py --strict",
        ]:
            if marker not in operator_runbook_text:
                problems.append(f"operatorRunbook:{marker}")
        if export_store_submission_starter.marker_hits(operator_runbook_text):
            problems.append("operatorRunbook:forbiddenMarkers")
    zip_names: set[str] = set()
    if package_path.exists():
        try:
            with zipfile.ZipFile(package_path) as archive:
                zip_names = set(archive.namelist())
        except zipfile.BadZipFile as error:
            problems.append(f"bad-zip:{error}")
    if "mobile-store-submission-starter/store-submission-evidence-collector.html" not in zip_names:
        problems.append("zipCollectorHtml")
    if "mobile-store-submission-starter/store-submission-operator-runbook.md" not in zip_names:
        problems.append("zipOperatorRunbook")

    flavors = {
        str(entry.get("flavor")): entry
        for entry in manifest.get("flavors", [])
        if isinstance(entry, dict)
    }
    if set(flavors) != set(STORE_SUBMISSION_FLAVORS):
        problems.append("flavor-set")
    for flavor, entry in flavors.items():
        channel = str(entry.get("primaryChannel"))
        input_path = output_dir / str(entry.get("inputExamplePath", ""))
        checklist_path = output_dir / str(entry.get("operatorChecklistPath", ""))
        runbook_path = output_dir / str(entry.get("submissionRunbookPath", ""))
        evidence.extend([rel(root, input_path), rel(root, checklist_path), rel(root, runbook_path)])
        if set(entry.get("allowedStatuses", [])) != STORE_SUBMISSION_ALLOWED_STATUSES_BY_CHANNEL.get(channel):
            problems.append(f"{flavor}:allowedStatuses")
        if entry.get("requiredFlags") != store_submission_required_flags(channel):
            problems.append(f"{flavor}:requiredFlags")
        if f"mobile-store-submission-starter/{entry.get('inputExamplePath')}" not in zip_names:
            problems.append(f"{flavor}:zipInputExample")
        if f"mobile-store-submission-starter/{entry.get('operatorChecklistPath')}" not in zip_names:
            problems.append(f"{flavor}:zipOperatorChecklist")
        if f"mobile-store-submission-starter/{entry.get('submissionRunbookPath')}" not in zip_names:
            problems.append(f"{flavor}:zipSubmissionRunbook")
        if not input_path.exists() or entry.get("inputExampleSha256") != file_sha256(input_path):
            problems.append(f"{flavor}:inputExampleSha256")
            continue
        if not checklist_path.exists() or entry.get("operatorChecklistSha256") != file_sha256(checklist_path):
            problems.append(f"{flavor}:operatorChecklistSha256")
        if not runbook_path.exists() or entry.get("submissionRunbookSha256") != file_sha256(runbook_path):
            problems.append(f"{flavor}:submissionRunbookSha256")
        else:
            runbook_text = read_text(runbook_path)
            for marker in [
                f"build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json",
                f"build/store-signing-handoff/{flavor}/android-signing.properties.template",
                f"build/store-publish-config/{flavor}/publish-config.template.json",
                "import_store_submission_evidence.py --strict",
            ]:
                if marker not in runbook_text:
                    problems.append(f"{flavor}:submissionRunbook:{marker}")
            if export_store_submission_starter.marker_hits(runbook_text):
                problems.append(f"{flavor}:submissionRunbookForbiddenMarkers")
        try:
            input_doc = json.loads(read_text(input_path))
        except json.JSONDecodeError as error:
            problems.append(f"{flavor}:inputJson:{error}")
            continue
        submissions = input_doc.get("submissions")
        submission = submissions[0] if isinstance(submissions, list) and submissions else None
        if not isinstance(submission, dict):
            problems.append(f"{flavor}:submission")
            continue
        if submission.get("submissionStatus") != "pending_tenant_action":
            problems.append(f"{flavor}:placeholderStatus")
        if submission.get("tenantMustReplacePlaceholders") is not True:
            problems.append(f"{flavor}:tenantMustReplacePlaceholders")
        for flag in store_submission_required_flags(channel):
            if submission.get(flag) is not False:
                problems.append(f"{flavor}:placeholderFlag:{flag}")
                break
        if export_store_submission_starter.marker_hits(input_doc):
            problems.append(f"{flavor}:forbiddenMarkers")

    if problems:
        return Check(
            "store_submission_starter_package",
            "failed",
            f"Store submission starter package problems: {', '.join(problems)}",
            sorted(set(evidence)),
        )
    return Check(
        "store_submission_starter_package",
        "passed",
        "Store submission starter package exports no-secret tenant-fillable input examples, operator checklists, operator runbooks, and an offline evidence collector for all five tenant release flavors without creating passing fake store evidence.",
        sorted(set(evidence)),
    )


def markdown_escape_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_tenant_release_package_markdown(package: dict[str, Any]) -> str:
    status_summary = package.get("storeSubmissionStatusSummary", {})
    if not isinstance(status_summary, dict):
        status_summary = {}
    manifests = package.get("manifests", {})
    if not isinstance(manifests, dict):
        manifests = {}
    lines = [
        "# Mobile Tenant Release Package",
        "",
        f"- Generated at: `{package.get('generatedAt', '')}`",
        f"- Package type: `{package.get('packageType', '')}`",
        "",
        "This guide is public handoff metadata for tenant app publishing. It does not sign builds, submit store records, or import placeholder store evidence.",
        "",
        "## Store Submission Status Summary",
        "",
        f"- Result: `{status_summary.get('result', 'blocked')}`",
        f"- Strict import ready: `{status_summary.get('strictImportReady', False)}`",
        f"- Strict import command: `{status_summary.get('strictImportCommand', '')}`",
        f"- Input directory: `{status_summary.get('inputDirectory', '')}`",
        f"- Preflight report: `{status_summary.get('preflightReportPath', '')}`",
        "",
        "| Flavor | Channel | Status | Input | Blockers | Next action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in status_summary.get("flavors", []):
        if not isinstance(row, dict):
            continue
        blockers = ", ".join(str(blocker) for blocker in row.get("blockers", [])) or "-"
        lines.append(
            "| "
            + " | ".join([
                markdown_escape_cell(row.get("flavor")),
                markdown_escape_cell(row.get("primaryChannel")),
                markdown_escape_cell(row.get("status")),
                f"`{markdown_escape_cell(row.get('inputPath'))}`",
                markdown_escape_cell(blockers),
                markdown_escape_cell(row.get("nextAction")),
            ])
            + " |",
        )
    blocked_paths = status_summary.get("blockedInputPaths", [])
    if isinstance(blocked_paths, list) and blocked_paths:
        lines.extend([
            "",
            "Blocked input files:",
            "",
        ])
        lines.extend(f"- `{path}`" for path in blocked_paths if isinstance(path, str))
    lines.extend([
        "",
        "## Handoff Files",
        "",
        f"- Store handoff: `{manifests.get('storeHandoff', {}).get('path', '') if isinstance(manifests.get('storeHandoff'), dict) else ''}`",
        f"- App handoff package: `{manifests.get('appHandoff', {}).get('packagePath', '') if isinstance(manifests.get('appHandoff'), dict) else ''}`",
        f"- UI preview gallery: `{manifests.get('uiPreviewGallery', {}).get('htmlPath', '') if isinstance(manifests.get('uiPreviewGallery'), dict) else ''}`",
        f"- UI preview contact sheet: `{manifests.get('uiPreviewGallery', {}).get('contactSheetPath', '') if isinstance(manifests.get('uiPreviewGallery'), dict) else ''}`",
        f"- UI preview PNG contact sheet: `{manifests.get('uiPreviewGallery', {}).get('contactSheetPngPath', '') if isinstance(manifests.get('uiPreviewGallery'), dict) else ''}`",
        f"- WYSIWYG runtime boards: `{(manifests.get('uiPreviewGallery', {}).get('wysiwygRuntimePreviews', {}) if isinstance(manifests.get('uiPreviewGallery'), dict) else {}).get('boardCount', 0)}`",
        f"- Store assets package: `{manifests.get('storeAssets', {}).get('packagePath', '') if isinstance(manifests.get('storeAssets'), dict) else ''}`",
        f"- Store signing handoff: `{manifests.get('storeSigningHandoff', {}).get('packagePath', '') if isinstance(manifests.get('storeSigningHandoff'), dict) else ''}`",
        f"- Store publish config: `{manifests.get('storePublishConfig', {}).get('packagePath', '') if isinstance(manifests.get('storePublishConfig'), dict) else ''}`",
        f"- External account checklist: `{manifests.get('externalAccountHandoff', {}).get('markdownPath', '') if isinstance(manifests.get('externalAccountHandoff'), dict) else ''}`",
        f"- Completion closure: `{manifests.get('completionClosure', {}).get('markdownPath', '') if isinstance(manifests.get('completionClosure'), dict) else ''}`",
        f"- Store submission input workspace: `{manifests.get('storeSubmissionInputWorkspace', {}).get('manifestPath', '') if isinstance(manifests.get('storeSubmissionInputWorkspace'), dict) else ''}`",
        f"- Store submission starter: `{manifests.get('storeSubmissionStarter', {}).get('packagePath', '') if isinstance(manifests.get('storeSubmissionStarter'), dict) else ''}`",
        "",
        "## External Account Checklist",
        "",
    ])
    external_account = manifests.get("externalAccountHandoff")
    if not isinstance(external_account, dict):
        external_account = {}
    lines.extend([
        f"- Manifest: `{external_account.get('manifestPath', '')}`",
        f"- Guide: `{external_account.get('markdownPath', '')}`",
        f"- Package: `{external_account.get('packagePath', '')}`",
        f"- Required sections: `{external_account.get('sectionCount', 0)}`",
        f"- Flavor rows: `{external_account.get('flavorCount', 0)}`",
        f"- Tenant portal entry: `{external_account.get('tenantPortalEntry', '')}`",
        "",
        "## Completion Closure",
        "",
    ])
    completion_closure = manifests.get("completionClosure")
    if not isinstance(completion_closure, dict):
        completion_closure = {}
    lines.extend([
        f"- Report: `{completion_closure.get('reportPath', '')}`",
        f"- Guide: `{completion_closure.get('markdownPath', '')}`",
        f"- App completion: `{completion_closure.get('appCompletion', '')}`",
        f"- Can claim complete: `{completion_closure.get('canClaimComplete', False)}`",
        f"- Blockers: `{', '.join(completion_closure.get('blockerIds', [])) if isinstance(completion_closure.get('blockerIds'), list) else ''}`",
        "",
        "## Completion Unblocker",
        "",
    ])
    completion_unblocker = manifests.get("completionUnblocker")
    if not isinstance(completion_unblocker, dict):
        completion_unblocker = {}
    lines.extend([
        f"- Manifest: `{completion_unblocker.get('manifestPath', '')}`",
        f"- Guide: `{completion_unblocker.get('markdownPath', '')}`",
        f"- Store evidence fix queue CSV: `{completion_unblocker.get('fixQueueCsvPath', '')}`",
        f"- Store evidence fix queue Markdown: `{completion_unblocker.get('fixQueueMarkdownPath', '')}`",
        f"- Store evidence fix queue rows: `{completion_unblocker.get('fixQueueRowCount', 0)}`",
        "",
        "## Tenant Workflow",
        "",
    ])
    lines.extend(
        f"{index}. {step}"
        for index, step in enumerate(package.get("tenantWorkflow", []), start=1)
        if isinstance(step, str)
    )
    lines.extend([
        "",
        "## Secret Boundary",
        "",
        "No signing material, provider credentials, OAuth secrets, payment secrets, Cloudflare tokens, bank credentials, or crypto keys are included.",
        "",
    ])
    return "\n".join(lines)


def tenant_release_archive_marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    markers = [
        *(marker.lower() for marker in FORBIDDEN_SOURCE_MARKERS),
        *(marker.lower() for marker in import_store_submission_evidence.FORBIDDEN_MARKERS),
        "sk_live_",
        "sk_test_",
        "whsec_",
    ]
    return sorted({marker for marker in markers if marker in text})


def write_tenant_release_archive(
    root: Path,
    output: Path,
    markdown_output: Path,
    archive_path: Path,
) -> dict[str, Any]:
    candidates = [
        output,
        markdown_output,
        root / "build" / "release-handoff" / "mobile-store-handoff.json",
        root / "build" / "release-manifests" / "mobile-artifacts.json",
        root / "build" / "store-assets" / "store-assets-manifest.json",
        root / "build" / "store-assets" / "mobile-store-assets.zip",
        root / "build" / "ui-preview-gallery" / "ui-preview-gallery-manifest.json",
        root / "build" / "ui-preview-gallery" / "mobile-ui-preview-gallery.html",
        root / "build" / "ui-preview-gallery" / "mobile-ui-readable-overview.svg",
        root / "build" / "ui-preview-gallery" / "mobile-ui-readable-overview.png",
        root / "build" / "ui-preview-gallery" / "mobile-ui-preview-contact-sheet.svg",
        root / "build" / "ui-preview-gallery" / "mobile-ui-preview-contact-sheet.png",
        root / "build" / "ui-preview-gallery" / export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE,
        root / "build" / "ui-preview-gallery" / export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE,
        root / "build" / "ui-preview-gallery" / export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE,
        root / "build" / "ui-preview-gallery" / "mobile-ui-preview-gallery.zip",
        root / "build" / "app-handoff" / "mobile-app-handoff-manifest.json",
        root / "build" / "app-handoff" / "mobile-app-handoff.md",
        root / "build" / "app-handoff" / "mobile-app-handoff.html",
        root / "build" / "app-handoff" / "mobile-app-handoff.zip",
        root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json",
        root / "build" / "ios-ci-handoff" / "mobile-ios-ci-handoff.zip",
        root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json",
        root / "build" / "store-signing-handoff" / "mobile-store-signing-handoff.zip",
        root / "build" / "store-publish-config" / "store-publish-config-manifest.json",
        root / "build" / "store-publish-config" / "mobile-store-publish-config.zip",
        root / "build" / "external-account-handoff" / "mobile-external-account-handoff.json",
        root / "build" / "external-account-handoff" / "mobile-external-account-handoff.md",
        root / "build" / "external-account-handoff" / "mobile-external-account-handoff.zip",
        root / "build" / "store-submission-evidence" / "store-submission-evidence.json",
        root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json",
        root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md",
        root / "build" / "store-submission-evidence" / "store-submission-input-workspace.json",
        root / "build" / "store-submission-evidence" / "store-submission-input-workspace.md",
        root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json",
        root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md",
        root / "build" / "store-submission-starter" / "store-submission-starter-manifest.json",
        root / "build" / "store-submission-starter" / "store-submission-evidence-collector.html",
        root / "build" / "store-submission-starter" / "store-submission-operator-runbook.md",
        root / "build" / "store-submission-starter" / "mobile-store-submission-starter.zip",
        root / "build" / "completion-unblocker" / "mobile-completion-unblocker.json",
        root / "build" / "completion-unblocker" / "mobile-completion-unblocker.md",
        root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.csv",
        root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.md",
        root / "build" / "completion-closure" / "mobile-completion-closure.json",
        root / "build" / "completion-closure" / "mobile-completion-closure.md",
    ]
    entries: list[dict[str, Any]] = []
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    starter_output_dir = root / "build" / "store-submission-starter"
    with export_store_submission_starter.starter_output_lock(starter_output_dir):
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in candidates:
                if not file_path.exists() or not file_path.is_file() or file_path == archive_path:
                    continue
                if file_path == output:
                    entry_name = "mobile-tenant-release-package.json"
                elif file_path == markdown_output:
                    entry_name = "mobile-tenant-release-package.md"
                else:
                    entry_name = rel(root, file_path)
                zip_name = f"mobile-tenant-release-package/{entry_name}"
                info = zipfile.ZipInfo(zip_name)
                info.date_time = (2026, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, file_path.read_bytes())
                entries.append({
                    "path": entry_name,
                    "zipPath": zip_name,
                    "sizeBytes": file_path.stat().st_size,
                    "sha256": file_sha256(file_path),
                })
    return {
        "packagePath": rel(root, archive_path),
        "packagePresent": archive_path.exists(),
        "packageSha256": file_sha256(archive_path) if archive_path.exists() else None,
        "entryCount": len(entries),
        "entries": entries,
        "disallowedValueMarkerHits": tenant_release_archive_marker_hits(entries),
    }


def write_tenant_release_package(root: Path) -> Path:
    output = root / "build" / "release-handoff" / "mobile-tenant-release-package.json"
    markdown_output = root / "build" / "release-handoff" / "mobile-tenant-release-package.md"
    archive_output = root / "build" / "release-handoff" / "mobile-tenant-release-package.zip"
    store_handoff_path = write_store_handoff_manifest(root)
    store_manifest, _ = load_store_handoff_manifest(root)
    release_manifest, _ = load_release_manifest(root)
    store_assets_manifest_path = root / "build" / "store-assets" / "store-assets-manifest.json"
    store_assets_manifest: dict[str, Any] | None = None
    if store_assets_manifest_path.exists():
        try:
            store_assets_manifest = json.loads(read_text(store_assets_manifest_path))
        except json.JSONDecodeError:
            store_assets_manifest = None
    store_assets_package_path = (
        root / str(store_assets_manifest.get("packagePath", ""))
        if isinstance(store_assets_manifest, dict)
        else root / "build" / "store-assets" / "mobile-store-assets.zip"
    )
    ui_preview_output_dir = root / "build" / "ui-preview-gallery"
    ui_preview_manifest = export_ui_preview_gallery.build_gallery(root, ui_preview_output_dir)
    ui_preview_manifest_path = ui_preview_output_dir / "ui-preview-gallery-manifest.json"
    ui_preview_html_path = root / str(
        ui_preview_manifest.get("htmlPath", "build/ui-preview-gallery/mobile-ui-preview-gallery.html"),
    )
    ui_preview_readable_overview = (
        ui_preview_manifest.get("readableOverview")
        if isinstance(ui_preview_manifest.get("readableOverview"), dict)
        else {}
    )
    ui_preview_readable_overview_path = root / str(
        ui_preview_readable_overview.get(
            "path",
            "build/ui-preview-gallery/mobile-ui-readable-overview.svg",
        ),
    )
    ui_preview_readable_overview_png = (
        ui_preview_manifest.get("readableOverviewPng")
        if isinstance(ui_preview_manifest.get("readableOverviewPng"), dict)
        else {}
    )
    ui_preview_readable_overview_png_path = root / str(
        ui_preview_readable_overview_png.get(
            "path",
            "build/ui-preview-gallery/mobile-ui-readable-overview.png",
        ),
    )
    ui_preview_contact_sheet = (
        ui_preview_manifest.get("contactSheet")
        if isinstance(ui_preview_manifest.get("contactSheet"), dict)
        else {}
    )
    ui_preview_contact_sheet_path = root / str(
        ui_preview_contact_sheet.get(
            "path",
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
        ),
    )
    ui_preview_contact_sheet_png = (
        ui_preview_manifest.get("contactSheetPng")
        if isinstance(ui_preview_manifest.get("contactSheetPng"), dict)
        else {}
    )
    ui_preview_contact_sheet_png_path = root / str(
        ui_preview_contact_sheet_png.get(
            "path",
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
        ),
    )
    ui_preview_package_path = root / str(
        ui_preview_manifest.get("packagePath", "build/ui-preview-gallery/mobile-ui-preview-gallery.zip"),
    )
    ui_preview_wysiwyg_runtime = (
        ui_preview_manifest.get("wysiwygRuntimePreviews")
        if isinstance(ui_preview_manifest.get("wysiwygRuntimePreviews"), dict)
        else {}
    )
    ui_preview_wysiwyg_boards = (
        ui_preview_wysiwyg_runtime.get("boards", [])
        if isinstance(ui_preview_wysiwyg_runtime, dict)
        else []
    )
    app_handoff_output_dir = root / "build" / "app-handoff"
    app_handoff_manifest = export_app_handoff.build_handoff(root, app_handoff_output_dir)
    app_handoff_manifest_path = app_handoff_output_dir / "mobile-app-handoff-manifest.json"
    app_handoff_markdown_path = app_handoff_output_dir / "mobile-app-handoff.md"
    app_handoff_html_path = app_handoff_output_dir / "mobile-app-handoff.html"
    app_handoff_package_path = app_handoff_output_dir / "mobile-app-handoff.zip"
    embedded_input_workspace = (
        app_handoff_manifest.get("embeddedStoreSubmissionInputWorkspace")
        if isinstance(app_handoff_manifest.get("embeddedStoreSubmissionInputWorkspace"), dict)
        else {}
    )
    ios_ci_manifest_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
    ios_ci_manifest: dict[str, Any] | None = None
    if ios_ci_manifest_path.exists():
        try:
            ios_ci_manifest = json.loads(read_text(ios_ci_manifest_path))
        except json.JSONDecodeError:
            ios_ci_manifest = None
    ios_ci_package_path = (
        root / str(ios_ci_manifest.get("packagePath", ""))
        if isinstance(ios_ci_manifest, dict)
        else root / "build" / "ios-ci-handoff" / "mobile-ios-ci-handoff.zip"
    )
    store_signing_manifest_path = root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"
    store_signing_manifest: dict[str, Any] | None = None
    if store_signing_manifest_path.exists():
        try:
            store_signing_manifest = json.loads(read_text(store_signing_manifest_path))
        except json.JSONDecodeError:
            store_signing_manifest = None
    store_signing_package_path = (
        root / str(store_signing_manifest.get("packagePath", ""))
        if isinstance(store_signing_manifest, dict)
        else root / "build" / "store-signing-handoff" / "mobile-store-signing-handoff.zip"
    )
    store_publish_manifest_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
    store_publish_manifest: dict[str, Any] | None = None
    if store_publish_manifest_path.exists():
        try:
            store_publish_manifest = json.loads(read_text(store_publish_manifest_path))
        except json.JSONDecodeError:
            store_publish_manifest = None
    store_publish_package_path = (
        root / str(store_publish_manifest.get("packagePath", ""))
        if isinstance(store_publish_manifest, dict)
        else root / "build" / "store-publish-config" / "mobile-store-publish-config.zip"
    )
    external_account_output_dir = root / "build" / "external-account-handoff"
    external_account_handoff = export_external_account_handoff.export_handoff(
        root,
        external_account_output_dir,
    )
    external_account_manifest_path = external_account_output_dir / "mobile-external-account-handoff.json"
    external_account_markdown_path = external_account_output_dir / "mobile-external-account-handoff.md"
    external_account_package_path = external_account_output_dir / "mobile-external-account-handoff.zip"
    store_submission_starter_dir = root / "build" / "store-submission-starter"
    store_submission_starter_manifest = export_store_submission_starter.export_starter(
        root,
        store_submission_starter_dir,
    )
    store_submission_starter_manifest_path = (
        store_submission_starter_dir / "store-submission-starter-manifest.json"
    )
    store_submission_starter_package_path = root / str(
        store_submission_starter_manifest.get(
            "packagePath",
            "build/store-submission-starter/mobile-store-submission-starter.zip",
        ),
    )
    store_submission_starter_collector_path = (
        store_submission_starter_dir
        / str(store_submission_starter_manifest.get("collectorHtmlPath", "store-submission-evidence-collector.html"))
    )
    store_submission_starter_operator_runbook_path = (
        store_submission_starter_dir
        / str(store_submission_starter_manifest.get("operatorRunbookPath", "store-submission-operator-runbook.md"))
    )
    store_submission_evidence_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
    store_submission_preflight_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
    store_submission_preflight_markdown_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md"
    store_submission_template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
    store_submission_guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
    store_submission_input_workspace_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.json"
    store_submission_input_workspace_markdown_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.md"
    store_submission_input_workspace: dict[str, Any] | None = None
    if store_submission_input_workspace_path.exists():
        try:
            store_submission_input_workspace = json.loads(read_text(store_submission_input_workspace_path))
        except json.JSONDecodeError:
            store_submission_input_workspace = None
    ensure_store_submission_evidence(root, store_submission_evidence_path)
    store_submission_preflight = store_submission_evidence_preflight.build_preflight_report(
        source=root / "build" / "store-submission-evidence" / "store-submission-evidence.input.json",
        source_dir=root / "build" / "store-submission-evidence" / "flavors",
        output=root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json",
        markdown=root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md",
    )
    store_submission_evidence: dict[str, Any] | None = None
    if store_submission_evidence_path.exists():
        try:
            store_submission_evidence = json.loads(read_text(store_submission_evidence_path))
        except json.JSONDecodeError:
            store_submission_evidence = None
    ios_matrix_path = root / "build" / "ios-build-matrix" / "ios-build-matrix.json"
    ios_matrix: dict[str, Any] | None = None
    if ios_matrix_path.exists():
        try:
            ios_matrix = json.loads(read_text(ios_matrix_path))
        except json.JSONDecodeError:
            ios_matrix = None
    completion_unblocker_output_dir = root / "build" / "completion-unblocker"
    completion_unblocker_manifest = export_completion_unblocker.export_unblocker(
        root,
        completion_unblocker_output_dir,
    )
    completion_unblocker_manifest_path = (
        completion_unblocker_output_dir / "mobile-completion-unblocker.json"
    )
    completion_unblocker_markdown_path = (
        completion_unblocker_output_dir / "mobile-completion-unblocker.md"
    )
    completion_unblocker_fix_queue_csv_path = (
        completion_unblocker_output_dir / "mobile-store-evidence-fix-queue.csv"
    )
    completion_unblocker_fix_queue_markdown_path = (
        completion_unblocker_output_dir / "mobile-store-evidence-fix-queue.md"
    )
    completion_unblocker_fix_queue = (
        completion_unblocker_manifest.get("storeEvidenceFixQueue")
        if isinstance(completion_unblocker_manifest.get("storeEvidenceFixQueue"), dict)
        else {}
    )
    completion_closure_report_path = root / "build" / "completion-closure" / "mobile-completion-closure.json"
    completion_closure_markdown_path = root / "build" / "completion-closure" / "mobile-completion-closure.md"
    completion_closure_report: dict[str, Any] | None = None
    if completion_closure_report_path.exists():
        try:
            completion_closure_report = json.loads(read_text(completion_closure_report_path))
        except json.JSONDecodeError:
            completion_closure_report = None
    completion_closure_blockers = (
        completion_closure_report.get("blockers", [])
        if isinstance(completion_closure_report, dict)
        and isinstance(completion_closure_report.get("blockers"), list)
        else []
    )
    completion_closure_blocker_ids = [
        str(blocker.get("id"))
        for blocker in completion_closure_blockers
        if isinstance(blocker, dict) and blocker.get("id")
    ]

    flavors: list[dict[str, Any]] = []
    for entry in (store_manifest or {}).get("flavors", []):
        if not isinstance(entry, dict):
            continue
        distribution = entry.get("distributionChannelReadiness")
        channels = distribution.get("channels", {}) if isinstance(distribution, dict) else {}
        store_products = entry.get("storeProductRegistration")
        auth_callbacks = entry.get("authCallbackRegistration")
        flavors.append(
            {
                "flavor": entry.get("flavor"),
                "appName": entry.get("appName"),
                "applicationId": entry.get("applicationId"),
                "bundleId": entry.get("bundleId"),
                "styleTemplate": entry.get("styleTemplate"),
                "storeComplianceMode": entry.get("storeComplianceMode"),
                "primaryChannel": distribution.get("primaryChannel") if isinstance(distribution, dict) else None,
                "artifactPaths": entry.get("artifactPaths", {}),
                "releaseArtifacts": entry.get("releaseArtifacts", []),
                "authCallbackRegistration": {
                    "scheme": auth_callbacks.get("scheme") if isinstance(auth_callbacks, dict) else None,
                    "callbackUris": auth_callbacks.get("callbackUris", []) if isinstance(auth_callbacks, dict) else [],
                },
                "storeProductRegistration": {
                    "storeProviders": store_products.get("storeProviders", []) if isinstance(store_products, dict) else [],
                    "serverVerificationEndpoint": store_products.get("serverVerificationEndpoint") if isinstance(store_products, dict) else None,
                    "tenantShouldReplaceProductIds": bool(store_products.get("tenantShouldReplaceProductIds")) if isinstance(store_products, dict) else False,
                },
                "distributionChannels": channels,
                "tenantRequiredActions": {
                    "replaceBundleIds": True,
                    "replaceSigningMaterial": True,
                    "configureOAuthCallbacks": bool(entry.get("authProviders")),
                    "configureStoreProducts": bool(
                        isinstance(store_products, dict)
                        and store_products.get("storeProviders"),
                    ),
                    "publishLegalAndSupportUrls": True,
                    "verifyStoreComplianceMode": True,
                    "configureTenantEdgeSecretsServerSide": True,
                },
            },
        )

    strict_import_readiness = (
        store_submission_preflight.get("strictImportReadiness", {})
        if isinstance(store_submission_preflight.get("strictImportReadiness"), dict)
        else {}
    )
    blocked_by = (
        strict_import_readiness.get("blockedBy", [])
        if isinstance(strict_import_readiness.get("blockedBy"), list)
        else []
    )
    store_submission_status_summary = {
        "result": store_submission_preflight.get("result", "blocked"),
        "summary": store_submission_preflight.get("summary", {}),
        "strictImportReady": bool(strict_import_readiness.get("ready", False)),
        "strictImportCommand": strict_import_readiness.get(
            "command",
            store_submission_preflight.get(
                "strictImportCommand",
                "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            ),
        ),
        "preflightReportPath": store_submission_preflight.get(
            "outputPath",
            "build/store-submission-evidence/store-submission-evidence-preflight.json",
        ),
        "preflightMarkdownPath": store_submission_preflight.get(
            "markdownPath",
            "build/store-submission-evidence/store-submission-evidence-preflight.md",
        ),
        "inputDirectory": store_submission_preflight.get(
            "sourceDir",
            "build/store-submission-evidence/flavors",
        ),
        "blockedCount": len(blocked_by),
        "blockedInputPaths": [
            row.get("inputPath")
            for row in blocked_by
            if isinstance(row, dict) and isinstance(row.get("inputPath"), str)
        ],
        "sourceBlockedBy": strict_import_readiness.get("sourceBlockedBy", [])
        if isinstance(strict_import_readiness.get("sourceBlockedBy"), list)
        else [],
        "nextAction": strict_import_readiness.get(
            "nextAction",
            "Fix blocked flavor inputs and source issues, then rerun preflight before strict import.",
        ),
        "flavors": [
            {
                "flavor": row.get("flavor"),
                "appName": row.get("appName"),
                "primaryChannel": row.get("primaryChannel"),
                "status": row.get("status"),
                "submissionStatus": row.get("submissionStatus"),
                "inputPath": row.get("tenantEvidenceInputPath"),
                "readyForStrictImport": bool(row.get("readyForStrictImport", False)),
                "blockers": row.get("blockers", []) if isinstance(row.get("blockers"), list) else [],
                "nextAction": row.get("nextAction"),
                "remediationHints": row.get("remediationHints", [])
                if isinstance(row.get("remediationHints"), list)
                else [],
                "publicEvidenceRefsCount": row.get("publicEvidenceRefsCount"),
            }
            for row in store_submission_preflight.get("flavors", [])
            if isinstance(row, dict)
        ],
    }

    release_manifest_path = root / "build" / "release-manifests" / "mobile-artifacts.json"
    package = {
        "schemaVersion": 1,
        "packageType": "mobile_tenant_release_package",
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "openSourceBoundary": {
            "license": "LICENSE",
            "readme": "README.md",
            "docs": [
                "docs/open-source-release.md",
                "docs/native-builds.md",
                "docs/flavors.md",
                "docs/api-boundary.md",
            ],
            "publishableRoots": [
                "lib",
                "assets/config",
                "android",
                "ios",
                "docs",
                "test/goldens/prototypes",
            ],
        },
        "storeSubmissionStatusSummary": store_submission_status_summary,
        "manifests": {
            "storeHandoff": {
                "path": rel(root, store_handoff_path),
                "sha256": file_sha256(store_handoff_path),
            },
            "releaseArtifacts": {
                "path": "build/release-manifests/mobile-artifacts.json",
                "present": release_manifest_path.exists(),
                "sha256": file_sha256(release_manifest_path) if release_manifest_path.exists() else None,
                "androidArtifactCount": len(android_release_manifest_artifacts(release_manifest or {})),
            },
            "storeAssets": {
                "manifestPath": "build/store-assets/store-assets-manifest.json",
                "manifestPresent": store_assets_manifest_path.exists(),
                "manifestSha256": file_sha256(store_assets_manifest_path) if store_assets_manifest_path.exists() else None,
                "packagePath": str(store_assets_package_path.relative_to(root))
                if store_assets_package_path.exists()
                else "build/store-assets/mobile-store-assets.zip",
                "packagePresent": store_assets_package_path.exists(),
                "packageSha256": file_sha256(store_assets_package_path) if store_assets_package_path.exists() else None,
                "screenshotCount": store_assets_manifest.get("screenshotCount")
                if isinstance(store_assets_manifest, dict)
                else None,
            },
            "uiPreviewGallery": {
                "manifestPath": "build/ui-preview-gallery/ui-preview-gallery-manifest.json",
                "manifestPresent": ui_preview_manifest_path.exists(),
                "manifestSha256": file_sha256(ui_preview_manifest_path)
                if ui_preview_manifest_path.exists()
                else None,
                "htmlPath": str(ui_preview_html_path.relative_to(root))
                if ui_preview_html_path.exists()
                else "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
                "htmlPresent": ui_preview_html_path.exists(),
                "htmlSha256": file_sha256(ui_preview_html_path)
                if ui_preview_html_path.exists()
                else None,
                "readableOverviewPath": str(ui_preview_readable_overview_path.relative_to(root))
                if ui_preview_readable_overview_path.exists()
                else "build/ui-preview-gallery/mobile-ui-readable-overview.svg",
                "readableOverviewPresent": ui_preview_readable_overview_path.exists(),
                "readableOverviewSha256": file_sha256(ui_preview_readable_overview_path)
                if ui_preview_readable_overview_path.exists()
                else None,
                "readableOverviewScreenCount": ui_preview_readable_overview.get("screenCount")
                if isinstance(ui_preview_readable_overview, dict)
                else None,
                "readableOverviewPngPath": str(ui_preview_readable_overview_png_path.relative_to(root))
                if ui_preview_readable_overview_png_path.exists()
                else "build/ui-preview-gallery/mobile-ui-readable-overview.png",
                "readableOverviewPngPresent": ui_preview_readable_overview_png_path.exists(),
                "readableOverviewPngSha256": file_sha256(ui_preview_readable_overview_png_path)
                if ui_preview_readable_overview_png_path.exists()
                else None,
                "readableOverviewPngScreenCount": ui_preview_readable_overview_png.get("screenCount")
                if isinstance(ui_preview_readable_overview_png, dict)
                else None,
                "contactSheetPath": str(ui_preview_contact_sheet_path.relative_to(root))
                if ui_preview_contact_sheet_path.exists()
                else "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
                "contactSheetPresent": ui_preview_contact_sheet_path.exists(),
                "contactSheetSha256": file_sha256(ui_preview_contact_sheet_path)
                if ui_preview_contact_sheet_path.exists()
                else None,
                "contactSheetScreenCount": ui_preview_contact_sheet.get("screenCount")
                if isinstance(ui_preview_contact_sheet, dict)
                else None,
                "contactSheetPngPath": str(ui_preview_contact_sheet_png_path.relative_to(root))
                if ui_preview_contact_sheet_png_path.exists()
                else "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
                "contactSheetPngPresent": ui_preview_contact_sheet_png_path.exists(),
                "contactSheetPngSha256": file_sha256(ui_preview_contact_sheet_png_path)
                if ui_preview_contact_sheet_png_path.exists()
                else None,
                "contactSheetPngScreenCount": ui_preview_contact_sheet_png.get("screenCount")
                if isinstance(ui_preview_contact_sheet_png, dict)
                else None,
                "wysiwygRuntimePreviews": {
                    "source": ui_preview_wysiwyg_runtime.get("source")
                    if isinstance(ui_preview_wysiwyg_runtime, dict)
                    else None,
                    "sourceDirectory": ui_preview_wysiwyg_runtime.get("sourceDirectory")
                    if isinstance(ui_preview_wysiwyg_runtime, dict)
                    else None,
                    "captureCount": ui_preview_wysiwyg_runtime.get("captureCount")
                    if isinstance(ui_preview_wysiwyg_runtime, dict)
                    else None,
                    "boardCount": ui_preview_wysiwyg_runtime.get("boardCount")
                    if isinstance(ui_preview_wysiwyg_runtime, dict)
                    else None,
                    "boards": [
                        {
                            "id": board.get("id"),
                            "path": board.get("path"),
                            "present": (root / str(board.get("path", ""))).exists(),
                            "sha256": file_sha256(root / str(board.get("path", "")))
                            if (root / str(board.get("path", ""))).exists()
                            else None,
                            "screenCount": board.get("screenCount"),
                        }
                        for board in ui_preview_wysiwyg_boards
                        if isinstance(board, dict)
                    ],
                },
                "packagePath": str(ui_preview_package_path.relative_to(root))
                if ui_preview_package_path.exists()
                else "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
                "packagePresent": ui_preview_package_path.exists(),
                "packageSha256": file_sha256(ui_preview_package_path)
                if ui_preview_package_path.exists()
                else None,
                "screenshotCount": ui_preview_manifest.get("screenshotCount")
                if isinstance(ui_preview_manifest, dict)
                else None,
            },
            "appHandoff": {
                "manifestPath": "build/app-handoff/mobile-app-handoff-manifest.json",
                "manifestPresent": app_handoff_manifest_path.exists(),
                "manifestSha256": file_sha256(app_handoff_manifest_path)
                if app_handoff_manifest_path.exists()
                else None,
                "markdownPath": "build/app-handoff/mobile-app-handoff.md",
                "markdownPresent": app_handoff_markdown_path.exists(),
                "markdownSha256": file_sha256(app_handoff_markdown_path)
                if app_handoff_markdown_path.exists()
                else None,
                "htmlPath": "build/app-handoff/mobile-app-handoff.html",
                "htmlPresent": app_handoff_html_path.exists(),
                "htmlSha256": file_sha256(app_handoff_html_path)
                if app_handoff_html_path.exists()
                else None,
                "packagePath": "build/app-handoff/mobile-app-handoff.zip",
                "packagePresent": app_handoff_package_path.exists(),
                "packageSha256": file_sha256(app_handoff_package_path)
                if app_handoff_package_path.exists()
                else None,
                "embeddedStoreSubmissionInputWorkspace": embedded_input_workspace,
                "disallowedValueMarkerHits": app_handoff_manifest.get("disallowedValueMarkerHits", []),
            },
            "iosCiHandoff": {
                "manifestPath": "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
                "manifestPresent": ios_ci_manifest_path.exists(),
                "manifestSha256": file_sha256(ios_ci_manifest_path) if ios_ci_manifest_path.exists() else None,
                "packagePath": str(ios_ci_package_path.relative_to(root))
                if ios_ci_package_path.exists()
                else "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
                "packagePresent": ios_ci_package_path.exists(),
                "packageSha256": file_sha256(ios_ci_package_path) if ios_ci_package_path.exists() else None,
                "workflowDispatch": bool(
                    isinstance(ios_ci_manifest, dict)
                    and isinstance(ios_ci_manifest.get("workflow"), dict)
                    and ios_ci_manifest["workflow"].get("workflowDispatch") is True
                ),
                "flavorCount": len(ios_ci_manifest.get("flavors", []))
                if isinstance(ios_ci_manifest, dict)
                and isinstance(ios_ci_manifest.get("flavors"), list)
                else None,
            },
            "storeSigningHandoff": {
                "manifestPath": "build/store-signing-handoff/store-signing-handoff-manifest.json",
                "manifestPresent": store_signing_manifest_path.exists(),
                "manifestSha256": file_sha256(store_signing_manifest_path)
                if store_signing_manifest_path.exists()
                else None,
                "packagePath": str(store_signing_package_path.relative_to(root))
                if store_signing_package_path.exists()
                else "build/store-signing-handoff/mobile-store-signing-handoff.zip",
                "packagePresent": store_signing_package_path.exists(),
                "packageSha256": file_sha256(store_signing_package_path)
                if store_signing_package_path.exists()
                else None,
                "flavorCount": len(store_signing_manifest.get("flavors", []))
                if isinstance(store_signing_manifest, dict)
                and isinstance(store_signing_manifest.get("flavors"), list)
                else None,
            },
            "storePublishConfig": {
                "manifestPath": "build/store-publish-config/store-publish-config-manifest.json",
                "manifestPresent": store_publish_manifest_path.exists(),
                "manifestSha256": file_sha256(store_publish_manifest_path)
                if store_publish_manifest_path.exists()
                else None,
                "packagePath": str(store_publish_package_path.relative_to(root))
                if store_publish_package_path.exists()
                else "build/store-publish-config/mobile-store-publish-config.zip",
                "packagePresent": store_publish_package_path.exists(),
                "packageSha256": file_sha256(store_publish_package_path)
                if store_publish_package_path.exists()
                else None,
                "flavorCount": len(store_publish_manifest.get("flavors", []))
                if isinstance(store_publish_manifest, dict)
                and isinstance(store_publish_manifest.get("flavors"), list)
                else None,
            },
            "externalAccountHandoff": {
                "manifestPath": "build/external-account-handoff/mobile-external-account-handoff.json",
                "manifestPresent": external_account_manifest_path.exists(),
                "manifestSha256": file_sha256(external_account_manifest_path)
                if external_account_manifest_path.exists()
                else None,
                "markdownPath": "build/external-account-handoff/mobile-external-account-handoff.md",
                "markdownPresent": external_account_markdown_path.exists(),
                "markdownSha256": file_sha256(external_account_markdown_path)
                if external_account_markdown_path.exists()
                else None,
                "packagePath": "build/external-account-handoff/mobile-external-account-handoff.zip",
                "packagePresent": external_account_package_path.exists(),
                "packageSha256": file_sha256(external_account_package_path)
                if external_account_package_path.exists()
                else None,
                "sectionCount": len(external_account_handoff.get("sections", []))
                if isinstance(external_account_handoff.get("sections"), list)
                else None,
                "flavorCount": len(external_account_handoff.get("flavors", []))
                if isinstance(external_account_handoff.get("flavors"), list)
                else None,
                "tenantPortalEntry": external_account_handoff.get("tenantPortalEntry"),
                "strictImportCommand": external_account_handoff.get("strictImportCommand"),
                "noCredentialBoundary": external_account_handoff.get("noCredentialBoundary"),
                "disallowedValueMarkerHits": external_account_handoff.get(
                    "disallowedValueMarkerHits",
                    [],
                ),
            },
            "storeSubmissionEvidence": {
                "evidencePath": "build/store-submission-evidence/store-submission-evidence.json",
                "evidencePresent": store_submission_evidence_path.exists(),
                "evidenceSha256": file_sha256(store_submission_evidence_path)
                if store_submission_evidence_path.exists()
                else None,
                "preflightPath": "build/store-submission-evidence/store-submission-evidence-preflight.json",
                "preflightPresent": store_submission_preflight_path.exists(),
                "preflightSha256": file_sha256(store_submission_preflight_path)
                if store_submission_preflight_path.exists()
                else None,
                "preflightMarkdownPath": "build/store-submission-evidence/store-submission-evidence-preflight.md",
                "preflightMarkdownPresent": store_submission_preflight_markdown_path.exists(),
                "preflightMarkdownSha256": file_sha256(store_submission_preflight_markdown_path)
                if store_submission_preflight_markdown_path.exists()
                else None,
                "templatePath": "build/store-submission-evidence/store-submission-evidence.template.json",
                "templatePresent": store_submission_template_path.exists(),
                "templateSha256": file_sha256(store_submission_template_path)
                if store_submission_template_path.exists()
                else None,
                "guidePath": "build/store-submission-evidence/store-submission-evidence.guide.md",
                "guidePresent": store_submission_guide_path.exists(),
                "guideSha256": file_sha256(store_submission_guide_path)
                if store_submission_guide_path.exists()
                else None,
                "result": store_submission_evidence.get("result")
                if isinstance(store_submission_evidence, dict)
                else None,
                "flavorCount": len(store_submission_evidence.get("submissions", []))
                if isinstance(store_submission_evidence, dict)
                and isinstance(store_submission_evidence.get("submissions"), list)
                else None,
            },
            "storeSubmissionInputWorkspace": {
                "manifestPath": "build/store-submission-evidence/store-submission-input-workspace.json",
                "manifestPresent": store_submission_input_workspace_path.exists(),
                "manifestSha256": file_sha256(store_submission_input_workspace_path)
                if store_submission_input_workspace_path.exists()
                else None,
                "markdownPath": "build/store-submission-evidence/store-submission-input-workspace.md",
                "markdownPresent": store_submission_input_workspace_markdown_path.exists(),
                "markdownSha256": file_sha256(store_submission_input_workspace_markdown_path)
                if store_submission_input_workspace_markdown_path.exists()
                else None,
                "preflightReportPath": "build/store-submission-evidence/store-submission-evidence-preflight.json",
                "preflightReportPresent": store_submission_preflight_path.exists(),
                "preflightReportSha256": file_sha256(store_submission_preflight_path)
                if store_submission_preflight_path.exists()
                else None,
                "preflightMarkdownPath": "build/store-submission-evidence/store-submission-evidence-preflight.md",
                "preflightMarkdownPresent": store_submission_preflight_markdown_path.exists(),
                "preflightMarkdownSha256": file_sha256(store_submission_preflight_markdown_path)
                if store_submission_preflight_markdown_path.exists()
                else None,
                "inputDirectory": "build/store-submission-evidence/flavors",
                "inputCount": len(store_submission_input_workspace.get("inputs", []))
                if isinstance(store_submission_input_workspace, dict)
                and isinstance(store_submission_input_workspace.get("inputs"), list)
                else None,
                "inputs": store_submission_input_workspace.get("inputs", [])
                if isinstance(store_submission_input_workspace, dict)
                and isinstance(store_submission_input_workspace.get("inputs"), list)
                else [],
                "preflightSummary": store_submission_input_workspace.get("preflightSummary", {})
                if isinstance(store_submission_input_workspace, dict)
                else {},
            },
            "storeSubmissionStarter": {
                "manifestPath": "build/store-submission-starter/store-submission-starter-manifest.json",
                "manifestPresent": store_submission_starter_manifest_path.exists(),
                "manifestSha256": file_sha256(store_submission_starter_manifest_path)
                if store_submission_starter_manifest_path.exists()
                else None,
                "packagePath": "build/store-submission-starter/mobile-store-submission-starter.zip",
                "packagePresent": store_submission_starter_package_path.exists(),
                "packageSha256": file_sha256(store_submission_starter_package_path)
                if store_submission_starter_package_path.exists()
                else None,
                "collectorHtmlPath": str(store_submission_starter_collector_path.relative_to(root))
                if store_submission_starter_collector_path.exists()
                else "build/store-submission-starter/store-submission-evidence-collector.html",
                "collectorHtmlPresent": store_submission_starter_collector_path.exists(),
                "collectorHtmlSha256": file_sha256(store_submission_starter_collector_path)
                if store_submission_starter_collector_path.exists()
                else None,
                "operatorRunbookPath": str(store_submission_starter_operator_runbook_path.relative_to(root))
                if store_submission_starter_operator_runbook_path.exists()
                else "build/store-submission-starter/store-submission-operator-runbook.md",
                "operatorRunbookPresent": store_submission_starter_operator_runbook_path.exists(),
                "operatorRunbookSha256": file_sha256(store_submission_starter_operator_runbook_path)
                if store_submission_starter_operator_runbook_path.exists()
                else None,
                "flavorCount": len(store_submission_starter_manifest.get("flavors", []))
                if isinstance(store_submission_starter_manifest.get("flavors"), list)
                else None,
                "evidencePacketSummary": store_submission_starter_manifest.get("evidencePacketSummary")
                if isinstance(store_submission_starter_manifest.get("evidencePacketSummary"), dict)
                else None,
                "disallowedValueMarkerHits": store_submission_starter_manifest.get(
                    "disallowedValueMarkerHits",
                    [],
                ),
            },
            "completionUnblocker": {
                "manifestPath": "build/completion-unblocker/mobile-completion-unblocker.json",
                "manifestPresent": completion_unblocker_manifest_path.exists(),
                "manifestSha256": file_sha256(completion_unblocker_manifest_path)
                if completion_unblocker_manifest_path.exists()
                else None,
                "markdownPath": "build/completion-unblocker/mobile-completion-unblocker.md",
                "markdownPresent": completion_unblocker_markdown_path.exists(),
                "markdownSha256": file_sha256(completion_unblocker_markdown_path)
                if completion_unblocker_markdown_path.exists()
                else None,
                "fixQueueCsvPath": "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
                "fixQueueCsvPresent": completion_unblocker_fix_queue_csv_path.exists(),
                "fixQueueCsvSha256": file_sha256(completion_unblocker_fix_queue_csv_path)
                if completion_unblocker_fix_queue_csv_path.exists()
                else None,
                "fixQueueMarkdownPath": "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
                "fixQueueMarkdownPresent": completion_unblocker_fix_queue_markdown_path.exists(),
                "fixQueueMarkdownSha256": file_sha256(completion_unblocker_fix_queue_markdown_path)
                if completion_unblocker_fix_queue_markdown_path.exists()
                else None,
                "fixQueueRowCount": completion_unblocker_fix_queue.get("rowCount"),
                "strictImportCommand": completion_unblocker_fix_queue.get("strictImportCommand"),
                "disallowedValueMarkerHits": completion_unblocker_manifest.get(
                    "disallowedValueMarkerHits",
                    [],
                ),
            },
            "completionClosure": {
                "reportPath": "build/completion-closure/mobile-completion-closure.json",
                "reportPresent": completion_closure_report_path.exists(),
                "reportSha256": file_sha256(completion_closure_report_path)
                if completion_closure_report_path.exists()
                else None,
                "markdownPath": "build/completion-closure/mobile-completion-closure.md",
                "markdownPresent": completion_closure_markdown_path.exists(),
                "markdownSha256": file_sha256(completion_closure_markdown_path)
                if completion_closure_markdown_path.exists()
                else None,
                "appCompletion": completion_closure_report.get("appCompletion")
                if isinstance(completion_closure_report, dict)
                else None,
                "canClaimComplete": completion_closure_report.get("canClaimComplete")
                if isinstance(completion_closure_report, dict)
                else None,
                "summary": completion_closure_report.get("summary", {})
                if isinstance(completion_closure_report, dict)
                else {},
                "blockerIds": completion_closure_blocker_ids,
                "secretBoundary": completion_closure_report.get("secretBoundary")
                if isinstance(completion_closure_report, dict)
                else None,
            },
            "completionAudit": {
                "path": "build/completion-audits/mobile-app-completion.json",
                "generatedBy": "scripts/mobile_completion_audit.py",
            },
            "iosBuildMatrix": {
                "path": "build/ios-build-matrix/ios-build-matrix.json",
                "present": ios_matrix_path.exists(),
                "result": ios_matrix.get("result") if isinstance(ios_matrix, dict) else None,
                "blockers": ios_matrix.get("blockers", []) if isinstance(ios_matrix, dict) else [],
            },
        },
        "tenantWorkflow": [
            "Select one flavor and style template in the tenant portal.",
            "Replace app name, icon, bundle id/application id, support URL, terms URL, and privacy URL.",
            "Configure OAuth providers and callback URIs in tenant-owned developer accounts.",
            "Configure store products or approved regional payment providers in Tenant Edge/API Worker secrets.",
            "Review the UI preview gallery to approve the selected template screens before replacing tenant branding.",
            "Review and replace store-assets package screenshots, localized copy, review notes, and data-safety starter facts.",
            "Use the iOS CI handoff package to trigger and download unsigned iOS builds on a macOS GitHub Actions runner when local Xcode is unavailable.",
            "Use the store-signing handoff package to fill tenant-owned Apple export options and Android upload-signing placeholders outside Git.",
            "Use the store-publish config package to fill tenant-owned App Store, Google Play, or direct-distribution public release fields before submission.",
            "Use the external account handoff checklist to collect Apple, Google Play, Android direct, OAuth, consumer payment, and legal public status fields without credentials.",
            "Use the app handoff package to review UI, Android artifacts, store starter files, and the embedded input workspace in one offline bundle.",
            "Use the store-submission input workspace to fill per-flavor public evidence fields and rerun preflight before strict import.",
            "Use the store-submission starter package to copy no-secret tenant-fillable evidence inputs before importing public store evidence.",
            "Follow the store-submission operator runbook to connect signing handoff, publish config, evidence collector, and strict evidence import.",
            "Import public store-submission evidence after tenant signing, TestFlight, Play internal testing, or direct-distribution setup is complete.",
            "Replace template signing material outside this repository before store submission.",
            "Run scripts/mobile_completion_closure.py to refresh canClaimComplete and the public blocker handoff after every new iOS CI or store evidence import.",
            "Run check_mobile, release manifest generation, store handoff, store assets export, tenant release package, and completion audit.",
        ],
        "flavors": flavors,
        "secretBoundary": {
            "clientStoresTenantSecrets": False,
            "clientStoresPaymentSecrets": False,
            "clientStoresCloudflareTokens": False,
            "tenantSecretsLocation": "Tenant Edge/API Worker secrets only",
            "signingMaterialLocation": "tenant-owned Apple/Google/direct-distribution accounts outside Git",
        },
    }
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_tenant_release_package_markdown(package), encoding="utf-8")
    package["humanReadableGuide"] = {
        "path": "build/release-handoff/mobile-tenant-release-package.md",
        "present": markdown_output.exists(),
        "sha256": file_sha256(markdown_output) if markdown_output.exists() else None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package["archivePackage"] = write_tenant_release_archive(
        root,
        output,
        markdown_output,
        archive_output,
    )
    output.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def check_tenant_release_package(root: Path) -> Check:
    starter_output_dir = root / "build" / "store-submission-starter"
    with export_store_submission_starter.starter_output_lock(starter_output_dir):
        return _check_tenant_release_package_locked(root)


def _check_tenant_release_package_locked(root: Path) -> Check:
    path = write_tenant_release_package(root)
    markdown_path = root / "build" / "release-handoff" / "mobile-tenant-release-package.md"
    archive_path = root / "build" / "release-handoff" / "mobile-tenant-release-package.zip"
    evidence = [
        rel(root, path),
        rel(root, markdown_path),
        rel(root, archive_path),
        "build/release-handoff/mobile-store-handoff.json",
        "build/store-assets/store-assets-manifest.json",
        "build/store-assets/mobile-store-assets.zip",
        "build/ui-preview-gallery/ui-preview-gallery-manifest.json",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
        "build/ui-preview-gallery/mobile-ui-readable-overview.png",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
        f"build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
        f"build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
        f"build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
        "build/app-handoff/mobile-app-handoff-manifest.json",
        "build/app-handoff/mobile-app-handoff.md",
        "build/app-handoff/mobile-app-handoff.html",
        "build/app-handoff/mobile-app-handoff.zip",
        "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
        "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
        "build/store-signing-handoff/store-signing-handoff-manifest.json",
        "build/store-signing-handoff/mobile-store-signing-handoff.zip",
        "build/store-publish-config/store-publish-config-manifest.json",
        "build/store-publish-config/mobile-store-publish-config.zip",
        "build/external-account-handoff/mobile-external-account-handoff.json",
        "build/external-account-handoff/mobile-external-account-handoff.md",
        "build/external-account-handoff/mobile-external-account-handoff.zip",
        "build/store-submission-evidence/store-submission-evidence.json",
        "build/store-submission-evidence/store-submission-evidence.template.json",
        "build/store-submission-evidence/store-submission-input-workspace.json",
        "build/store-submission-evidence/store-submission-input-workspace.md",
        "build/store-submission-starter/store-submission-starter-manifest.json",
        "build/store-submission-starter/store-submission-evidence-collector.html",
        "build/store-submission-starter/store-submission-operator-runbook.md",
        "build/store-submission-starter/mobile-store-submission-starter.zip",
        "build/completion-unblocker/mobile-completion-unblocker.json",
        "build/completion-unblocker/mobile-completion-unblocker.md",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
        "build/completion-closure/mobile-completion-closure.json",
        "build/completion-closure/mobile-completion-closure.md",
        "build/release-manifests/mobile-artifacts.json",
        "README.md",
        "docs/open-source-release.md",
    ]
    try:
        package = json.loads(read_text(path))
    except json.JSONDecodeError as error:
        return Check(
            "tenant_release_package",
            "failed",
            f"Tenant release package is invalid JSON: {error}",
            evidence,
        )

    problems: list[str] = []
    if package.get("schemaVersion") != 1:
        problems.append("schemaVersion")
    if package.get("packageType") != "mobile_tenant_release_package":
        problems.append("packageType")
    archive_package = package.get("archivePackage")
    if not isinstance(archive_package, dict):
        problems.append("archivePackage")
    else:
        if archive_package.get("packagePath") != "build/release-handoff/mobile-tenant-release-package.zip":
            problems.append("archivePackage.packagePath")
        if archive_package.get("packagePresent") is not True:
            problems.append("archivePackage.packagePresent")
        if not archive_path.exists() or archive_package.get("packageSha256") != file_sha256(archive_path):
            problems.append("archivePackage.packageSha256")
        if archive_package.get("disallowedValueMarkerHits"):
            problems.append("archivePackage.disallowedValueMarkerHits")
        entries = archive_package.get("entries")
        if not isinstance(entries, list) or len(entries) < 10:
            problems.append("archivePackage.entries")
            entries = []
        if archive_package.get("entryCount") != len(entries):
            problems.append("archivePackage.entryCount")
        entry_paths = {
            str(entry.get("zipPath"))
            for entry in entries
            if isinstance(entry, dict)
        }
        for required_entry in [
            "mobile-tenant-release-package/mobile-tenant-release-package.json",
            "mobile-tenant-release-package/mobile-tenant-release-package.md",
            "mobile-tenant-release-package/build/release-handoff/mobile-store-handoff.json",
            "mobile-tenant-release-package/build/app-handoff/mobile-app-handoff.zip",
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-readable-overview.png",
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
            f"mobile-tenant-release-package/build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
            f"mobile-tenant-release-package/build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
            f"mobile-tenant-release-package/build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}",
            "mobile-tenant-release-package/build/store-signing-handoff/mobile-store-signing-handoff.zip",
            "mobile-tenant-release-package/build/store-publish-config/mobile-store-publish-config.zip",
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.json",
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.md",
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.zip",
            "mobile-tenant-release-package/build/store-submission-starter/mobile-store-submission-starter.zip",
            "mobile-tenant-release-package/build/completion-unblocker/mobile-completion-unblocker.json",
            "mobile-tenant-release-package/build/completion-unblocker/mobile-completion-unblocker.md",
            "mobile-tenant-release-package/build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
            "mobile-tenant-release-package/build/completion-unblocker/mobile-store-evidence-fix-queue.md",
            "mobile-tenant-release-package/build/completion-closure/mobile-completion-closure.json",
            "mobile-tenant-release-package/build/completion-closure/mobile-completion-closure.md",
        ]:
            if required_entry not in entry_paths:
                problems.append(f"archivePackage.entry:{required_entry}")
        if archive_path.exists():
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    zip_names = set(archive.namelist())
            except zipfile.BadZipFile as error:
                problems.append(f"archivePackage.badZip:{error}")
                zip_names = set()
            if entry_paths and zip_names != entry_paths:
                problems.append("archivePackage.zipEntries")
    human_readable_guide = package.get("humanReadableGuide")
    if not isinstance(human_readable_guide, dict):
        problems.append("humanReadableGuide")
    else:
        if human_readable_guide.get("path") != "build/release-handoff/mobile-tenant-release-package.md":
            problems.append("humanReadableGuide.path")
        if human_readable_guide.get("present") is not True:
            problems.append("humanReadableGuide.present")
        if not markdown_path.exists() or human_readable_guide.get("sha256") != file_sha256(markdown_path):
            problems.append("humanReadableGuide.sha256")
        elif markdown_path.exists():
            markdown = read_text(markdown_path)
            for marker in [
                "# Mobile Tenant Release Package",
                "## Store Submission Status Summary",
                "| Flavor | Channel | Status | Input | Blockers | Next action |",
                "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
                "## Completion Unblocker",
                "## Completion Closure",
                "## External Account Checklist",
                "mobile-external-account-handoff.md",
                "mobile-completion-closure.md",
                "mobile-store-evidence-fix-queue.csv",
                "Store evidence fix queue rows",
                "No signing material, provider credentials, OAuth secrets, payment secrets, Cloudflare tokens, bank credentials, or crypto keys are included.",
            ]:
                if marker not in markdown:
                    problems.append(f"humanReadableGuide:{marker}")
            if any(marker in markdown.lower() for marker in [
                "tenant_app_secret",
                "cloudflare_api_token",
                "client_secret",
                "stripe_secret",
                "paypal_secret",
                "private_key",
                "sk_live_",
                "sk_test_",
            ]):
                problems.append("humanReadableGuide.forbiddenMarker")
    manifests = package.get("manifests")
    if not isinstance(manifests, dict):
        problems.append("manifests")
    else:
        store_handoff = manifests.get("storeHandoff")
        store_handoff_path = root / "build" / "release-handoff" / "mobile-store-handoff.json"
        if not isinstance(store_handoff, dict):
            problems.append("manifests.storeHandoff")
        else:
            if store_handoff.get("path") != "build/release-handoff/mobile-store-handoff.json":
                problems.append("manifests.storeHandoff.path")
            if not store_handoff_path.exists() or store_handoff.get("sha256") != file_sha256(store_handoff_path):
                problems.append("manifests.storeHandoff.sha256")
        release_artifacts = manifests.get("releaseArtifacts")
        if not isinstance(release_artifacts, dict):
            problems.append("manifests.releaseArtifacts")
        else:
            if release_artifacts.get("androidArtifactCount") != len(FLAVORS) * 2:
                problems.append("manifests.releaseArtifacts.androidArtifactCount")
        store_assets = manifests.get("storeAssets")
        store_assets_manifest_path = root / "build" / "store-assets" / "store-assets-manifest.json"
        store_assets_package_path = root / "build" / "store-assets" / "mobile-store-assets.zip"
        if not isinstance(store_assets, dict):
            problems.append("manifests.storeAssets")
        else:
            if store_assets.get("manifestPath") != "build/store-assets/store-assets-manifest.json":
                problems.append("manifests.storeAssets.manifestPath")
            if store_assets.get("packagePath") != "build/store-assets/mobile-store-assets.zip":
                problems.append("manifests.storeAssets.packagePath")
            if store_assets.get("screenshotCount") != len(FLAVORS) * len(SCREEN_IDS):
                problems.append("manifests.storeAssets.screenshotCount")
            if (
                not store_assets_manifest_path.exists()
                or store_assets.get("manifestSha256") != file_sha256(store_assets_manifest_path)
            ):
                problems.append("manifests.storeAssets.manifestSha256")
            if (
                not store_assets_package_path.exists()
                or store_assets.get("packageSha256") != file_sha256(store_assets_package_path)
            ):
                problems.append("manifests.storeAssets.packageSha256")
        ui_preview = manifests.get("uiPreviewGallery")
        ui_preview_manifest_path = root / "build" / "ui-preview-gallery" / "ui-preview-gallery-manifest.json"
        ui_preview_html_path = root / "build" / "ui-preview-gallery" / "mobile-ui-preview-gallery.html"
        ui_preview_readable_overview_path = (
            root / "build" / "ui-preview-gallery" / "mobile-ui-readable-overview.svg"
        )
        ui_preview_readable_overview_png_path = (
            root / "build" / "ui-preview-gallery" / "mobile-ui-readable-overview.png"
        )
        ui_preview_contact_sheet_path = (
            root / "build" / "ui-preview-gallery" / "mobile-ui-preview-contact-sheet.svg"
        )
        ui_preview_contact_sheet_png_path = (
            root / "build" / "ui-preview-gallery" / "mobile-ui-preview-contact-sheet.png"
        )
        ui_preview_wysiwyg_board_paths = [
            root / "build" / "ui-preview-gallery" / file_name
            for file_name in export_ui_preview_gallery.WYSIWYG_BOARD_FILES
        ]
        ui_preview_package_path = root / "build" / "ui-preview-gallery" / "mobile-ui-preview-gallery.zip"
        if not isinstance(ui_preview, dict):
            problems.append("manifests.uiPreviewGallery")
        else:
            if ui_preview.get("manifestPath") != "build/ui-preview-gallery/ui-preview-gallery-manifest.json":
                problems.append("manifests.uiPreviewGallery.manifestPath")
            if ui_preview.get("htmlPath") != "build/ui-preview-gallery/mobile-ui-preview-gallery.html":
                problems.append("manifests.uiPreviewGallery.htmlPath")
            if ui_preview.get("packagePath") != "build/ui-preview-gallery/mobile-ui-preview-gallery.zip":
                problems.append("manifests.uiPreviewGallery.packagePath")
            if ui_preview.get("screenshotCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
                problems.append("manifests.uiPreviewGallery.screenshotCount")
            if (
                not ui_preview_manifest_path.exists()
                or ui_preview.get("manifestSha256") != file_sha256(ui_preview_manifest_path)
            ):
                problems.append("manifests.uiPreviewGallery.manifestSha256")
            if (
                not ui_preview_html_path.exists()
                or ui_preview.get("htmlSha256") != file_sha256(ui_preview_html_path)
            ):
                problems.append("manifests.uiPreviewGallery.htmlSha256")
            if (
                ui_preview.get("readableOverviewPath")
                != "build/ui-preview-gallery/mobile-ui-readable-overview.svg"
            ):
                problems.append("manifests.uiPreviewGallery.readableOverviewPath")
            if ui_preview.get("readableOverviewScreenCount") != len(export_ui_preview_gallery.FLAVORS) * 4:
                problems.append("manifests.uiPreviewGallery.readableOverviewScreenCount")
            if (
                not ui_preview_readable_overview_path.exists()
                or ui_preview.get("readableOverviewSha256")
                != file_sha256(ui_preview_readable_overview_path)
            ):
                problems.append("manifests.uiPreviewGallery.readableOverviewSha256")
            if (
                ui_preview.get("readableOverviewPngPath")
                != "build/ui-preview-gallery/mobile-ui-readable-overview.png"
            ):
                problems.append("manifests.uiPreviewGallery.readableOverviewPngPath")
            if ui_preview.get("readableOverviewPngScreenCount") != len(export_ui_preview_gallery.FLAVORS) * 4:
                problems.append("manifests.uiPreviewGallery.readableOverviewPngScreenCount")
            if (
                not ui_preview_readable_overview_png_path.exists()
                or ui_preview.get("readableOverviewPngSha256")
                != file_sha256(ui_preview_readable_overview_png_path)
            ):
                problems.append("manifests.uiPreviewGallery.readableOverviewPngSha256")
            if (
                ui_preview.get("contactSheetPath")
                != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg"
            ):
                problems.append("manifests.uiPreviewGallery.contactSheetPath")
            if ui_preview.get("contactSheetScreenCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
                problems.append("manifests.uiPreviewGallery.contactSheetScreenCount")
            if (
                not ui_preview_contact_sheet_path.exists()
                or ui_preview.get("contactSheetSha256")
                != file_sha256(ui_preview_contact_sheet_path)
            ):
                problems.append("manifests.uiPreviewGallery.contactSheetSha256")
            if (
                ui_preview.get("contactSheetPngPath")
                != "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png"
            ):
                problems.append("manifests.uiPreviewGallery.contactSheetPngPath")
            if ui_preview.get("contactSheetPngScreenCount") != len(export_ui_preview_gallery.FLAVORS) * len(SCREEN_IDS):
                problems.append("manifests.uiPreviewGallery.contactSheetPngScreenCount")
            if (
                not ui_preview_contact_sheet_png_path.exists()
                or ui_preview.get("contactSheetPngSha256")
                != file_sha256(ui_preview_contact_sheet_png_path)
            ):
                problems.append("manifests.uiPreviewGallery.contactSheetPngSha256")
            wysiwyg_runtime = ui_preview.get("wysiwygRuntimePreviews")
            if not isinstance(wysiwyg_runtime, dict):
                problems.append("manifests.uiPreviewGallery.wysiwygRuntimePreviews")
            else:
                if wysiwyg_runtime.get("source") != export_ui_preview_gallery.WYSIWYG_RUNTIME_CAPTURE_SOURCE:
                    problems.append("manifests.uiPreviewGallery.wysiwygRuntimePreviews.source")
                if wysiwyg_runtime.get("captureCount") != len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS):
                    problems.append("manifests.uiPreviewGallery.wysiwygRuntimePreviews.captureCount")
                if wysiwyg_runtime.get("boardCount") != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
                    problems.append("manifests.uiPreviewGallery.wysiwygRuntimePreviews.boardCount")
                boards = wysiwyg_runtime.get("boards")
                if not isinstance(boards, list) or len(boards) != len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES):
                    problems.append("manifests.uiPreviewGallery.wysiwygRuntimePreviews.boards")
                    boards = []
                board_by_path = {
                    str(board.get("path")): board
                    for board in boards
                    if isinstance(board, dict)
                }
                for board_path in ui_preview_wysiwyg_board_paths:
                    board = board_by_path.get(rel(root, board_path))
                    if not isinstance(board, dict):
                        problems.append(f"manifests.uiPreviewGallery.wysiwygRuntimePreviews.{board_path.name}")
                        continue
                    if board.get("present") is not True:
                        problems.append(f"manifests.uiPreviewGallery.wysiwygRuntimePreviews.{board_path.name}.present")
                    if not board_path.exists() or board.get("sha256") != file_sha256(board_path):
                        problems.append(f"manifests.uiPreviewGallery.wysiwygRuntimePreviews.{board_path.name}.sha256")
            if (
                not ui_preview_package_path.exists()
                or ui_preview.get("packageSha256") != file_sha256(ui_preview_package_path)
            ):
                problems.append("manifests.uiPreviewGallery.packageSha256")
        app_handoff = manifests.get("appHandoff")
        app_handoff_manifest_path = root / "build" / "app-handoff" / "mobile-app-handoff-manifest.json"
        app_handoff_markdown_path = root / "build" / "app-handoff" / "mobile-app-handoff.md"
        app_handoff_html_path = root / "build" / "app-handoff" / "mobile-app-handoff.html"
        app_handoff_package_path = root / "build" / "app-handoff" / "mobile-app-handoff.zip"
        if not isinstance(app_handoff, dict):
            problems.append("manifests.appHandoff")
        else:
            if app_handoff.get("manifestPath") != "build/app-handoff/mobile-app-handoff-manifest.json":
                problems.append("manifests.appHandoff.manifestPath")
            if app_handoff.get("markdownPath") != "build/app-handoff/mobile-app-handoff.md":
                problems.append("manifests.appHandoff.markdownPath")
            if app_handoff.get("htmlPath") != "build/app-handoff/mobile-app-handoff.html":
                problems.append("manifests.appHandoff.htmlPath")
            if app_handoff.get("packagePath") != "build/app-handoff/mobile-app-handoff.zip":
                problems.append("manifests.appHandoff.packagePath")
            if app_handoff.get("manifestPresent") is not True:
                problems.append("manifests.appHandoff.manifestPresent")
            if app_handoff.get("markdownPresent") is not True:
                problems.append("manifests.appHandoff.markdownPresent")
            if app_handoff.get("htmlPresent") is not True:
                problems.append("manifests.appHandoff.htmlPresent")
            if app_handoff.get("packagePresent") is not True:
                problems.append("manifests.appHandoff.packagePresent")
            if (
                not app_handoff_manifest_path.exists()
                or app_handoff.get("manifestSha256") != file_sha256(app_handoff_manifest_path)
            ):
                problems.append("manifests.appHandoff.manifestSha256")
            if (
                not app_handoff_markdown_path.exists()
                or app_handoff.get("markdownSha256") != file_sha256(app_handoff_markdown_path)
            ):
                problems.append("manifests.appHandoff.markdownSha256")
            if (
                not app_handoff_html_path.exists()
                or app_handoff.get("htmlSha256") != file_sha256(app_handoff_html_path)
            ):
                problems.append("manifests.appHandoff.htmlSha256")
            if (
                not app_handoff_package_path.exists()
                or app_handoff.get("packageSha256") != file_sha256(app_handoff_package_path)
            ):
                problems.append("manifests.appHandoff.packageSha256")
            embedded_workspace = app_handoff.get("embeddedStoreSubmissionInputWorkspace")
            if not isinstance(embedded_workspace, dict):
                problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace")
            else:
                if embedded_workspace.get("manifestPath") != "build/app-handoff/store-submission-evidence/store-submission-input-workspace.json":
                    problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.manifestPath")
                summary = embedded_workspace.get("preflightSummary")
                if not isinstance(summary, dict):
                    problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.preflightSummary")
                elif summary.get("strictImportReady") is True:
                    problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.strictImportReady")
                embedded_inputs = embedded_workspace.get("inputs")
                if not isinstance(embedded_inputs, list):
                    problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.inputs")
                else:
                    embedded_by_flavor = {
                        str(row.get("flavor")): row
                        for row in embedded_inputs
                        if isinstance(row, dict)
                    }
                    if set(embedded_by_flavor) != set(STORE_SUBMISSION_FLAVORS):
                        problems.append("manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.inputs")
                    for flavor in STORE_SUBMISSION_FLAVORS:
                        row = embedded_by_flavor.get(flavor)
                        if not isinstance(row, dict):
                            continue
                        if row.get("targetPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                            problems.append(f"manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.{flavor}.targetPath")
                        if not row.get("preflightBlockers"):
                            problems.append(f"manifests.appHandoff.embeddedStoreSubmissionInputWorkspace.{flavor}.inputBlockers")
        ios_ci = manifests.get("iosCiHandoff")
        ios_ci_manifest_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
        ios_ci_package_path = root / "build" / "ios-ci-handoff" / "mobile-ios-ci-handoff.zip"
        if not isinstance(ios_ci, dict):
            problems.append("manifests.iosCiHandoff")
        else:
            if ios_ci.get("manifestPath") != "build/ios-ci-handoff/ios-ci-handoff-manifest.json":
                problems.append("manifests.iosCiHandoff.manifestPath")
            if ios_ci.get("packagePath") != "build/ios-ci-handoff/mobile-ios-ci-handoff.zip":
                problems.append("manifests.iosCiHandoff.packagePath")
            if ios_ci.get("workflowDispatch") is not True:
                problems.append("manifests.iosCiHandoff.workflowDispatch")
            if ios_ci.get("flavorCount") != len(FLAVORS):
                problems.append("manifests.iosCiHandoff.flavorCount")
            if (
                not ios_ci_manifest_path.exists()
                or ios_ci.get("manifestSha256") != file_sha256(ios_ci_manifest_path)
            ):
                problems.append("manifests.iosCiHandoff.manifestSha256")
            if (
                not ios_ci_package_path.exists()
                or ios_ci.get("packageSha256") != file_sha256(ios_ci_package_path)
            ):
                problems.append("manifests.iosCiHandoff.packageSha256")
        store_signing = manifests.get("storeSigningHandoff")
        store_signing_manifest_path = root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"
        store_signing_package_path = root / "build" / "store-signing-handoff" / "mobile-store-signing-handoff.zip"
        if not isinstance(store_signing, dict):
            problems.append("manifests.storeSigningHandoff")
        else:
            if store_signing.get("manifestPath") != "build/store-signing-handoff/store-signing-handoff-manifest.json":
                problems.append("manifests.storeSigningHandoff.manifestPath")
            if store_signing.get("packagePath") != "build/store-signing-handoff/mobile-store-signing-handoff.zip":
                problems.append("manifests.storeSigningHandoff.packagePath")
            if store_signing.get("flavorCount") != len(STORE_SUBMISSION_FLAVORS):
                problems.append("manifests.storeSigningHandoff.flavorCount")
            if (
                not store_signing_manifest_path.exists()
                or store_signing.get("manifestSha256") != file_sha256(store_signing_manifest_path)
            ):
                problems.append("manifests.storeSigningHandoff.manifestSha256")
            if (
                not store_signing_package_path.exists()
                or store_signing.get("packageSha256") != file_sha256(store_signing_package_path)
            ):
                problems.append("manifests.storeSigningHandoff.packageSha256")
        store_publish = manifests.get("storePublishConfig")
        store_publish_manifest_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
        store_publish_package_path = root / "build" / "store-publish-config" / "mobile-store-publish-config.zip"
        if not isinstance(store_publish, dict):
            problems.append("manifests.storePublishConfig")
        else:
            if store_publish.get("manifestPath") != "build/store-publish-config/store-publish-config-manifest.json":
                problems.append("manifests.storePublishConfig.manifestPath")
            if store_publish.get("packagePath") != "build/store-publish-config/mobile-store-publish-config.zip":
                problems.append("manifests.storePublishConfig.packagePath")
            if store_publish.get("flavorCount") != len(FLAVORS):
                problems.append("manifests.storePublishConfig.flavorCount")
            if (
                not store_publish_manifest_path.exists()
                or store_publish.get("manifestSha256") != file_sha256(store_publish_manifest_path)
            ):
                problems.append("manifests.storePublishConfig.manifestSha256")
            if (
                not store_publish_package_path.exists()
                or store_publish.get("packageSha256") != file_sha256(store_publish_package_path)
            ):
                problems.append("manifests.storePublishConfig.packageSha256")
        external_account = manifests.get("externalAccountHandoff")
        external_account_manifest_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.json"
        external_account_markdown_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.md"
        external_account_package_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.zip"
        if not isinstance(external_account, dict):
            problems.append("manifests.externalAccountHandoff")
        else:
            if external_account.get("manifestPath") != "build/external-account-handoff/mobile-external-account-handoff.json":
                problems.append("manifests.externalAccountHandoff.manifestPath")
            if external_account.get("markdownPath") != "build/external-account-handoff/mobile-external-account-handoff.md":
                problems.append("manifests.externalAccountHandoff.markdownPath")
            if external_account.get("packagePath") != "build/external-account-handoff/mobile-external-account-handoff.zip":
                problems.append("manifests.externalAccountHandoff.packagePath")
            if external_account.get("manifestPresent") is not True:
                problems.append("manifests.externalAccountHandoff.manifestPresent")
            if external_account.get("markdownPresent") is not True:
                problems.append("manifests.externalAccountHandoff.markdownPresent")
            if external_account.get("packagePresent") is not True:
                problems.append("manifests.externalAccountHandoff.packagePresent")
            if external_account.get("sectionCount") != 6:
                problems.append("manifests.externalAccountHandoff.sectionCount")
            if external_account.get("flavorCount") != len(STORE_SUBMISSION_FLAVORS):
                problems.append("manifests.externalAccountHandoff.flavorCount")
            if external_account.get("strictImportCommand") != "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
                problems.append("manifests.externalAccountHandoff.strictImportCommand")
            if "外部账号与签名资料接入入口" not in str(external_account.get("tenantPortalEntry", "")):
                problems.append("manifests.externalAccountHandoff.tenantPortalEntry")
            if "Public account status" not in str(external_account.get("noCredentialBoundary", "")):
                problems.append("manifests.externalAccountHandoff.noCredentialBoundary")
            if external_account.get("disallowedValueMarkerHits") != []:
                problems.append("manifests.externalAccountHandoff.disallowedValueMarkerHits")
            if (
                not external_account_manifest_path.exists()
                or external_account.get("manifestSha256") != file_sha256(external_account_manifest_path)
            ):
                problems.append("manifests.externalAccountHandoff.manifestSha256")
            if (
                not external_account_markdown_path.exists()
                or external_account.get("markdownSha256") != file_sha256(external_account_markdown_path)
            ):
                problems.append("manifests.externalAccountHandoff.markdownSha256")
            if (
                not external_account_package_path.exists()
                or external_account.get("packageSha256") != file_sha256(external_account_package_path)
            ):
                problems.append("manifests.externalAccountHandoff.packageSha256")
        store_submission = manifests.get("storeSubmissionEvidence")
        store_submission_evidence_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.json"
        store_submission_preflight_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
        store_submission_preflight_markdown_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md"
        store_submission_template_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.template.json"
        store_submission_guide_path = root / "build" / "store-submission-evidence" / "store-submission-evidence.guide.md"
        if not isinstance(store_submission, dict):
            problems.append("manifests.storeSubmissionEvidence")
        else:
            if store_submission.get("evidencePath") != "build/store-submission-evidence/store-submission-evidence.json":
                problems.append("manifests.storeSubmissionEvidence.evidencePath")
            if store_submission.get("preflightPath") != "build/store-submission-evidence/store-submission-evidence-preflight.json":
                problems.append("manifests.storeSubmissionEvidence.preflightPath")
            if store_submission.get("preflightMarkdownPath") != "build/store-submission-evidence/store-submission-evidence-preflight.md":
                problems.append("manifests.storeSubmissionEvidence.preflightMarkdownPath")
            if store_submission.get("templatePath") != "build/store-submission-evidence/store-submission-evidence.template.json":
                problems.append("manifests.storeSubmissionEvidence.templatePath")
            if store_submission.get("guidePath") != "build/store-submission-evidence/store-submission-evidence.guide.md":
                problems.append("manifests.storeSubmissionEvidence.guidePath")
            if store_submission.get("evidencePresent") is not True:
                problems.append("manifests.storeSubmissionEvidence.evidencePresent")
            if store_submission.get("preflightPresent") is not True:
                problems.append("manifests.storeSubmissionEvidence.preflightPresent")
            if store_submission.get("preflightMarkdownPresent") is not True:
                problems.append("manifests.storeSubmissionEvidence.preflightMarkdownPresent")
            if store_submission.get("templatePresent") is not True:
                problems.append("manifests.storeSubmissionEvidence.templatePresent")
            if store_submission.get("guidePresent") is not True:
                problems.append("manifests.storeSubmissionEvidence.guidePresent")
            if store_submission.get("result") not in {"blocked", "passed"}:
                problems.append("manifests.storeSubmissionEvidence.result")
            if (
                not store_submission_evidence_path.exists()
                or store_submission.get("evidenceSha256") != file_sha256(store_submission_evidence_path)
            ):
                problems.append("manifests.storeSubmissionEvidence.evidenceSha256")
            if (
                not store_submission_preflight_path.exists()
                or store_submission.get("preflightSha256") != file_sha256(store_submission_preflight_path)
            ):
                problems.append("manifests.storeSubmissionEvidence.preflightSha256")
            if (
                not store_submission_preflight_markdown_path.exists()
                or store_submission.get("preflightMarkdownSha256") != file_sha256(store_submission_preflight_markdown_path)
            ):
                problems.append("manifests.storeSubmissionEvidence.preflightMarkdownSha256")
            if (
                not store_submission_template_path.exists()
                or store_submission.get("templateSha256") != file_sha256(store_submission_template_path)
            ):
                problems.append("manifests.storeSubmissionEvidence.templateSha256")
            if (
                not store_submission_guide_path.exists()
                or store_submission.get("guideSha256") != file_sha256(store_submission_guide_path)
            ):
                problems.append("manifests.storeSubmissionEvidence.guideSha256")
        store_submission_starter = manifests.get("storeSubmissionStarter")
        store_submission_starter_manifest_path = (
            root / "build" / "store-submission-starter" / "store-submission-starter-manifest.json"
        )
        store_submission_starter_package_path = (
            root / "build" / "store-submission-starter" / "mobile-store-submission-starter.zip"
        )
        if not isinstance(store_submission_starter, dict):
            problems.append("manifests.storeSubmissionStarter")
        else:
            if store_submission_starter.get("manifestPath") != "build/store-submission-starter/store-submission-starter-manifest.json":
                problems.append("manifests.storeSubmissionStarter.manifestPath")
            if store_submission_starter.get("packagePath") != "build/store-submission-starter/mobile-store-submission-starter.zip":
                problems.append("manifests.storeSubmissionStarter.packagePath")
            if store_submission_starter.get("collectorHtmlPath") != "build/store-submission-starter/store-submission-evidence-collector.html":
                problems.append("manifests.storeSubmissionStarter.collectorHtmlPath")
            if store_submission_starter.get("operatorRunbookPath") != "build/store-submission-starter/store-submission-operator-runbook.md":
                problems.append("manifests.storeSubmissionStarter.operatorRunbookPath")
            if store_submission_starter.get("manifestPresent") is not True:
                problems.append("manifests.storeSubmissionStarter.manifestPresent")
            if store_submission_starter.get("packagePresent") is not True:
                problems.append("manifests.storeSubmissionStarter.packagePresent")
            if store_submission_starter.get("collectorHtmlPresent") is not True:
                problems.append("manifests.storeSubmissionStarter.collectorHtmlPresent")
            if store_submission_starter.get("operatorRunbookPresent") is not True:
                problems.append("manifests.storeSubmissionStarter.operatorRunbookPresent")
            if store_submission_starter.get("flavorCount") != len(STORE_SUBMISSION_FLAVORS):
                problems.append("manifests.storeSubmissionStarter.flavorCount")
            if store_submission_starter.get("disallowedValueMarkerHits") != []:
                problems.append("manifests.storeSubmissionStarter.disallowedValueMarkerHits")
            if (
                not store_submission_starter_manifest_path.exists()
                or store_submission_starter.get("manifestSha256") != file_sha256(store_submission_starter_manifest_path)
            ):
                problems.append("manifests.storeSubmissionStarter.manifestSha256")
            if (
                not store_submission_starter_package_path.exists()
                or store_submission_starter.get("packageSha256") != file_sha256(store_submission_starter_package_path)
            ):
                problems.append("manifests.storeSubmissionStarter.packageSha256")
            store_submission_starter_collector_path = (
                root / "build" / "store-submission-starter" / "store-submission-evidence-collector.html"
            )
            if (
                not store_submission_starter_collector_path.exists()
                or store_submission_starter.get("collectorHtmlSha256") != file_sha256(store_submission_starter_collector_path)
            ):
                problems.append("manifests.storeSubmissionStarter.collectorHtmlSha256")
            store_submission_starter_operator_runbook_path = (
                root / "build" / "store-submission-starter" / "store-submission-operator-runbook.md"
            )
            if (
                not store_submission_starter_operator_runbook_path.exists()
                or store_submission_starter.get("operatorRunbookSha256") != file_sha256(store_submission_starter_operator_runbook_path)
            ):
                problems.append("manifests.storeSubmissionStarter.operatorRunbookSha256")
            evidence_packet_summary = store_submission_starter.get("evidencePacketSummary")
            if not isinstance(evidence_packet_summary, dict):
                problems.append("manifests.storeSubmissionStarter.evidencePacketSummary")
            else:
                if evidence_packet_summary.get("packetType") != "tenant_public_store_submission_evidence_packet":
                    problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.packetType")
                if evidence_packet_summary.get("nextImportCommand") != "cd mobile && python3 scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
                    problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.nextImportCommand")
                if evidence_packet_summary.get("perFlavorInputDirectory") != "build/store-submission-evidence/flavors":
                    problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.perFlavorInputDirectory")
                if "Public status references only" not in str(evidence_packet_summary.get("secretBoundary", "")):
                    problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.secretBoundary")
                packet_flavors = evidence_packet_summary.get("flavors")
                if not isinstance(packet_flavors, list):
                    problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.flavors")
                else:
                    packet_by_flavor = {
                        str(entry.get("flavor")): entry
                        for entry in packet_flavors
                        if isinstance(entry, dict)
                    }
                    if set(packet_by_flavor) != set(STORE_SUBMISSION_FLAVORS):
                        problems.append("manifests.storeSubmissionStarter.evidencePacketSummary.flavorSet")
                    for flavor in STORE_SUBMISSION_FLAVORS:
                        packet = packet_by_flavor.get(flavor)
                        if not isinstance(packet, dict):
                            continue
                        if packet.get("tenantEvidenceInputPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                            problems.append(f"manifests.storeSubmissionStarter.evidencePacketSummary.{flavor}.tenantEvidenceInputPath")
                        if packet.get("starterInputExamplePath") != f"build/store-submission-starter/{flavor}/store-submission-evidence.input.example.json":
                            problems.append(f"manifests.storeSubmissionStarter.evidencePacketSummary.{flavor}.starterInputExamplePath")
                        if packet.get("primaryChannel") != STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]:
                            problems.append(f"manifests.storeSubmissionStarter.evidencePacketSummary.{flavor}.primaryChannel")
                if not isinstance(packet.get("requiredChecklistFlags"), list) or not packet.get("requiredChecklistFlags"):
                    problems.append(f"manifests.storeSubmissionStarter.evidencePacketSummary.{flavor}.requiredChecklistFlags")
        completion_unblocker = manifests.get("completionUnblocker")
        completion_unblocker_manifest_path = (
            root / "build" / "completion-unblocker" / "mobile-completion-unblocker.json"
        )
        completion_unblocker_markdown_path = (
            root / "build" / "completion-unblocker" / "mobile-completion-unblocker.md"
        )
        completion_unblocker_fix_queue_csv_path = (
            root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.csv"
        )
        completion_unblocker_fix_queue_markdown_path = (
            root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.md"
        )
        if not isinstance(completion_unblocker, dict):
            problems.append("manifests.completionUnblocker")
        else:
            if completion_unblocker.get("manifestPath") != "build/completion-unblocker/mobile-completion-unblocker.json":
                problems.append("manifests.completionUnblocker.manifestPath")
            if completion_unblocker.get("markdownPath") != "build/completion-unblocker/mobile-completion-unblocker.md":
                problems.append("manifests.completionUnblocker.markdownPath")
            if completion_unblocker.get("fixQueueCsvPath") != "build/completion-unblocker/mobile-store-evidence-fix-queue.csv":
                problems.append("manifests.completionUnblocker.fixQueueCsvPath")
            if completion_unblocker.get("fixQueueMarkdownPath") != "build/completion-unblocker/mobile-store-evidence-fix-queue.md":
                problems.append("manifests.completionUnblocker.fixQueueMarkdownPath")
            if completion_unblocker.get("manifestPresent") is not True:
                problems.append("manifests.completionUnblocker.manifestPresent")
            if completion_unblocker.get("markdownPresent") is not True:
                problems.append("manifests.completionUnblocker.markdownPresent")
            if completion_unblocker.get("fixQueueCsvPresent") is not True:
                problems.append("manifests.completionUnblocker.fixQueueCsvPresent")
            if completion_unblocker.get("fixQueueMarkdownPresent") is not True:
                problems.append("manifests.completionUnblocker.fixQueueMarkdownPresent")
            if not isinstance(completion_unblocker.get("fixQueueRowCount"), int) or completion_unblocker.get("fixQueueRowCount", 0) <= 0:
                problems.append("manifests.completionUnblocker.fixQueueRowCount")
            if completion_unblocker.get("strictImportCommand") != "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
                problems.append("manifests.completionUnblocker.strictImportCommand")
            if completion_unblocker.get("disallowedValueMarkerHits") != []:
                problems.append("manifests.completionUnblocker.disallowedValueMarkerHits")
            if (
                not completion_unblocker_manifest_path.exists()
                or completion_unblocker.get("manifestSha256") != file_sha256(completion_unblocker_manifest_path)
            ):
                problems.append("manifests.completionUnblocker.manifestSha256")
            if (
                not completion_unblocker_markdown_path.exists()
                or completion_unblocker.get("markdownSha256") != file_sha256(completion_unblocker_markdown_path)
            ):
                problems.append("manifests.completionUnblocker.markdownSha256")
            if (
                not completion_unblocker_fix_queue_csv_path.exists()
                or completion_unblocker.get("fixQueueCsvSha256") != file_sha256(completion_unblocker_fix_queue_csv_path)
            ):
                problems.append("manifests.completionUnblocker.fixQueueCsvSha256")
            if (
                not completion_unblocker_fix_queue_markdown_path.exists()
                or completion_unblocker.get("fixQueueMarkdownSha256") != file_sha256(completion_unblocker_fix_queue_markdown_path)
            ):
                problems.append("manifests.completionUnblocker.fixQueueMarkdownSha256")
        completion_closure = manifests.get("completionClosure")
        completion_closure_report_path = root / "build" / "completion-closure" / "mobile-completion-closure.json"
        completion_closure_markdown_path = root / "build" / "completion-closure" / "mobile-completion-closure.md"
        if not isinstance(completion_closure, dict):
            problems.append("manifests.completionClosure")
        else:
            if completion_closure.get("reportPath") != "build/completion-closure/mobile-completion-closure.json":
                problems.append("manifests.completionClosure.reportPath")
            if completion_closure.get("markdownPath") != "build/completion-closure/mobile-completion-closure.md":
                problems.append("manifests.completionClosure.markdownPath")
            if completion_closure.get("reportPresent") is not True:
                problems.append("manifests.completionClosure.reportPresent")
            if completion_closure.get("markdownPresent") is not True:
                problems.append("manifests.completionClosure.markdownPresent")
            if not isinstance(completion_closure.get("canClaimComplete"), bool):
                problems.append("manifests.completionClosure.canClaimComplete")
            if completion_closure.get("appCompletion") not in {"blocked", "incomplete", "complete"}:
                problems.append("manifests.completionClosure.appCompletion")
            if not isinstance(completion_closure.get("blockerIds"), list):
                problems.append("manifests.completionClosure.blockerIds")
            if "secret" not in str(completion_closure.get("secretBoundary", "")).lower():
                problems.append("manifests.completionClosure.secretBoundary")
            if (
                not completion_closure_report_path.exists()
                or completion_closure.get("reportSha256") != file_sha256(completion_closure_report_path)
            ):
                problems.append("manifests.completionClosure.reportSha256")
            if (
                not completion_closure_markdown_path.exists()
                or completion_closure.get("markdownSha256") != file_sha256(completion_closure_markdown_path)
            ):
                problems.append("manifests.completionClosure.markdownSha256")
        store_submission_input_workspace = manifests.get("storeSubmissionInputWorkspace")
        store_submission_input_workspace_path = (
            root / "build" / "store-submission-evidence" / "store-submission-input-workspace.json"
        )
        store_submission_input_workspace_markdown_path = (
            root / "build" / "store-submission-evidence" / "store-submission-input-workspace.md"
        )
        store_submission_input_dir = root / "build" / "store-submission-evidence" / "flavors"
        if not isinstance(store_submission_input_workspace, dict):
            problems.append("manifests.storeSubmissionInputWorkspace")
        else:
            if store_submission_input_workspace.get("manifestPath") != "build/store-submission-evidence/store-submission-input-workspace.json":
                problems.append("manifests.storeSubmissionInputWorkspace.manifestPath")
            if store_submission_input_workspace.get("markdownPath") != "build/store-submission-evidence/store-submission-input-workspace.md":
                problems.append("manifests.storeSubmissionInputWorkspace.markdownPath")
            if store_submission_input_workspace.get("preflightReportPath") != "build/store-submission-evidence/store-submission-evidence-preflight.json":
                problems.append("manifests.storeSubmissionInputWorkspace.preflightReportPath")
            if store_submission_input_workspace.get("preflightMarkdownPath") != "build/store-submission-evidence/store-submission-evidence-preflight.md":
                problems.append("manifests.storeSubmissionInputWorkspace.preflightMarkdownPath")
            if store_submission_input_workspace.get("inputDirectory") != "build/store-submission-evidence/flavors":
                problems.append("manifests.storeSubmissionInputWorkspace.inputDirectory")
            if store_submission_input_workspace.get("manifestPresent") is not True:
                problems.append("manifests.storeSubmissionInputWorkspace.manifestPresent")
            if store_submission_input_workspace.get("markdownPresent") is not True:
                problems.append("manifests.storeSubmissionInputWorkspace.markdownPresent")
            if store_submission_input_workspace.get("preflightReportPresent") is not True:
                problems.append("manifests.storeSubmissionInputWorkspace.preflightReportPresent")
            if store_submission_input_workspace.get("preflightMarkdownPresent") is not True:
                problems.append("manifests.storeSubmissionInputWorkspace.preflightMarkdownPresent")
            if store_submission_input_workspace.get("inputCount") != len(STORE_SUBMISSION_FLAVORS):
                problems.append("manifests.storeSubmissionInputWorkspace.inputCount")
            if (
                not store_submission_input_workspace_path.exists()
                or store_submission_input_workspace.get("manifestSha256") != file_sha256(store_submission_input_workspace_path)
            ):
                problems.append("manifests.storeSubmissionInputWorkspace.manifestSha256")
            if (
                not store_submission_input_workspace_markdown_path.exists()
                or store_submission_input_workspace.get("markdownSha256") != file_sha256(store_submission_input_workspace_markdown_path)
            ):
                problems.append("manifests.storeSubmissionInputWorkspace.markdownSha256")
            summary = store_submission_input_workspace.get("preflightSummary")
            if not isinstance(summary, dict):
                problems.append("manifests.storeSubmissionInputWorkspace.preflightSummary")
            elif summary.get("strictImportReady") is True:
                problems.append("manifests.storeSubmissionInputWorkspace.strictImportReady")
            workspace_inputs = store_submission_input_workspace.get("inputs")
            if not isinstance(workspace_inputs, list):
                problems.append("manifests.storeSubmissionInputWorkspace.inputs")
                workspace_inputs = []
            workspace_by_flavor = {
                str(row.get("flavor")): row
                for row in workspace_inputs
                if isinstance(row, dict)
            }
            if set(workspace_by_flavor) != set(STORE_SUBMISSION_FLAVORS):
                problems.append("manifests.storeSubmissionInputWorkspace.inputs.set")
            for flavor in STORE_SUBMISSION_FLAVORS:
                input_path = store_submission_input_dir / f"{flavor}.input.json"
                row = workspace_by_flavor.get(flavor)
                if not input_path.exists():
                    problems.append(f"manifests.storeSubmissionInputWorkspace.{flavor}.inputFile")
                if not isinstance(row, dict):
                    continue
                if row.get("targetPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                    problems.append(f"manifests.storeSubmissionInputWorkspace.{flavor}.targetPath")
                if not row.get("preflightBlockers"):
                    problems.append(f"manifests.storeSubmissionInputWorkspace.{flavor}.preflightBlockers")
        store_submission_status_summary = package.get("storeSubmissionStatusSummary")
        if not isinstance(store_submission_status_summary, dict):
            problems.append("storeSubmissionStatusSummary")
        else:
            if store_submission_status_summary.get("inputDirectory") != "build/store-submission-evidence/flavors":
                problems.append("storeSubmissionStatusSummary.inputDirectory")
            if store_submission_status_summary.get("preflightReportPath") != "build/store-submission-evidence/store-submission-evidence-preflight.json":
                problems.append("storeSubmissionStatusSummary.preflightReportPath")
            if store_submission_status_summary.get("preflightMarkdownPath") != "build/store-submission-evidence/store-submission-evidence-preflight.md":
                problems.append("storeSubmissionStatusSummary.preflightMarkdownPath")
            if store_submission_status_summary.get("strictImportCommand") != "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict":
                problems.append("storeSubmissionStatusSummary.strictImportCommand")
            if store_submission_status_summary.get("strictImportReady") is True:
                summary = (
                    store_submission_input_workspace.get("preflightSummary")
                    if isinstance(store_submission_input_workspace, dict)
                    else {}
                )
                if not isinstance(summary, dict) or summary.get("strictImportReady") is not True:
                    problems.append("storeSubmissionStatusSummary.strictImportReady")
            status_flavors = store_submission_status_summary.get("flavors")
            if not isinstance(status_flavors, list):
                problems.append("storeSubmissionStatusSummary.flavors")
                status_flavors = []
            status_by_flavor = {
                str(row.get("flavor")): row
                for row in status_flavors
                if isinstance(row, dict)
            }
            if set(status_by_flavor) != set(STORE_SUBMISSION_FLAVORS):
                problems.append("storeSubmissionStatusSummary.flavors.set")
            blocked_inputs = store_submission_status_summary.get("blockedInputPaths")
            if not isinstance(blocked_inputs, list):
                problems.append("storeSubmissionStatusSummary.blockedInputPaths")
                blocked_inputs = []
            if store_submission_status_summary.get("blockedCount") != len(blocked_inputs):
                problems.append("storeSubmissionStatusSummary.blockedCount")
            for flavor in STORE_SUBMISSION_FLAVORS:
                row = status_by_flavor.get(flavor)
                if not isinstance(row, dict):
                    continue
                if row.get("inputPath") != f"build/store-submission-evidence/flavors/{flavor}.input.json":
                    problems.append(f"storeSubmissionStatusSummary.{flavor}.inputPath")
                if row.get("status") not in {"blocked", "passed"}:
                    problems.append(f"storeSubmissionStatusSummary.{flavor}.status")
                if row.get("status") == "blocked" and not row.get("blockers"):
                    problems.append(f"storeSubmissionStatusSummary.{flavor}.blockers")
                if not row.get("nextAction"):
                    problems.append(f"storeSubmissionStatusSummary.{flavor}.nextAction")
                if row.get("status") == "blocked" and not row.get("remediationHints"):
                    problems.append(f"storeSubmissionStatusSummary.{flavor}.remediationHints")
    open_source = package.get("openSourceBoundary")
    if not isinstance(open_source, dict):
        problems.append("openSourceBoundary")
    else:
        docs = open_source.get("docs")
        if not isinstance(docs, list) or "docs/open-source-release.md" not in docs:
            problems.append("openSourceBoundary.docs")
        if open_source.get("license") != "LICENSE" or open_source.get("readme") != "README.md":
            problems.append("openSourceBoundary.license-readme")
    secret_boundary = package.get("secretBoundary")
    if not isinstance(secret_boundary, dict):
        problems.append("secretBoundary")
    else:
        for key in [
            "clientStoresTenantSecrets",
            "clientStoresPaymentSecrets",
            "clientStoresCloudflareTokens",
        ]:
            if secret_boundary.get(key) is not False:
                problems.append(f"secretBoundary.{key}")

    flavors = package.get("flavors")
    if not isinstance(flavors, list):
        problems.append("flavors")
        flavors = []
    by_flavor = {
        str(entry.get("flavor")): entry
        for entry in flavors
        if isinstance(entry, dict)
    }
    for flavor, expected in FLAVORS.items():
        entry = by_flavor.get(flavor)
        if not isinstance(entry, dict):
            problems.append(f"{flavor}:missing")
            continue
        if entry.get("appName") != expected["appName"]:
            problems.append(f"{flavor}:appName")
        if entry.get("applicationId") != expected["applicationId"]:
            problems.append(f"{flavor}:applicationId")
        if entry.get("styleTemplate") != expected["styleTemplate"]:
            problems.append(f"{flavor}:styleTemplate")
        actions = entry.get("tenantRequiredActions")
        if not isinstance(actions, dict):
            problems.append(f"{flavor}:tenantRequiredActions")
        else:
            for action in [
                "replaceBundleIds",
                "replaceSigningMaterial",
                "configureOAuthCallbacks",
                "publishLegalAndSupportUrls",
                "verifyStoreComplianceMode",
                "configureTenantEdgeSecretsServerSide",
            ]:
                if actions.get(action) is not True:
                    problems.append(f"{flavor}:tenantRequiredActions:{action}")
        artifact_paths = json.dumps(entry.get("artifactPaths", {}), ensure_ascii=False)
        if flavor in FLAVORS and f"app-{flavor}-release" not in artifact_paths:
            problems.append(f"{flavor}:artifactPaths")

    serialized = json.dumps(package, ensure_ascii=False).lower()
    for marker in [
        "tenant_app_secret",
        "cloudflare_api_token",
        "client_secret",
        "stripe_secret",
        "paypal_secret",
        "private_key",
        "sk_live_",
        "sk_test_",
    ]:
        if marker in serialized:
            problems.append(f"forbidden-marker:{marker}")

    if problems:
        return Check(
            "tenant_release_package",
            "failed",
            f"Tenant release package problems: {', '.join(problems)}",
            evidence,
        )
    return Check(
        "tenant_release_package",
        "passed",
        "Public tenant release package links store handoff, app handoff package, embedded input workspace, external account handoff checklist, store submission status summary, completion closure report, completion unblocker, store evidence fix queue, human-readable release guide, tenant release archive, store assets package, UI preview gallery, iOS CI handoff, store signing handoff, store publish config, store submission starter, store submission operator runbook, store submission evidence, Android artifacts, open-source docs, per-flavor tenant actions, and no-secret boundaries for tenant app publishing.",
        evidence,
    )


def check_tenant_portal_release_handoff(root: Path) -> Check:
    model = root.parent / "apps" / "tenant-portal" / "src" / "tenantAppTemplateConfig.ts"
    test = root.parent / "apps" / "tenant-portal" / "src" / "tenantAppTemplateConfig.test.ts"
    main = root.parent / "apps" / "tenant-portal" / "src" / "main.tsx"
    evidence = [
        "../apps/tenant-portal/src/tenantAppTemplateConfig.ts",
        "../apps/tenant-portal/src/tenantAppTemplateConfig.test.ts",
        "../apps/tenant-portal/src/main.tsx",
    ]
    missing_paths = [
        str(path.relative_to(root.parent))
        for path in [model, test, main]
        if not path.exists()
    ]
    if missing_paths:
        return Check(
            "tenant_portal_release_handoff",
            "missing",
            f"Tenant portal release handoff files are missing: {', '.join(missing_paths)}",
            evidence,
        )

    model_text = read_text(model)
    test_text = read_text(test)
    main_text = read_text(main)
    required_model_markers = [
        "TenantAppTemplateReleaseHandoff",
        "releaseHandoff: TenantAppTemplateReleaseHandoff",
        "authCallbackRegistration",
        "storeProductRegistration",
        "nativeCapabilityRegistration",
        "storeReviewDeclarations",
        "storeSubmissionEvidenceChecklist",
        "storeSubmissionEvidencePacket",
        "storeSubmissionEvidenceProgress",
        "storeSubmissionEvidenceDraft",
        "storeSubmissionEvidenceDraftWorkspace",
        "storeSubmissionEvidenceRemediationMatrix",
        "storeEvidenceFixQueueHandoff",
        "storeSubmissionEvidenceImportRunbook",
        "storeSubmissionEvidenceWorkspaceHandoff",
        "storeSubmissionEvidenceCompletionReceipt",
        "tenant_public_store_submission_evidence_packet",
        "tenant_store_submission_evidence_remediation_matrix",
        "tenant_store_evidence_fix_queue_handoff",
        "tenant_store_submission_evidence_import_runbook",
        "tenant_store_submission_evidence_workspace_handoff",
        "tenant_store_submission_evidence_completion_receipt",
        "full_app_completion",
        "tenant_public_store_submission_evidence_imported",
        "mobile-template-built-store-submission-blocked",
        "acceptedDecision",
        "requiredAuditChecks",
        "requiredEvidenceFields",
        "rejectedEvidenceStates",
        "strictImportReady",
        "blockedInputPath",
        "tenant_store_submission_public_evidence_input_draft",
        "tenant_store_submission_public_evidence_draft_workspace",
        "remediationSteps",
        "totalRowCount",
        "blockedFieldCount",
        "baseRequiredFieldCount",
        "channelRequiredFieldCount",
        "evidenceMetadataFieldCount",
        "completionPercent",
        "nextBlockingField",
        "nextAction",
        "sourceManifestPath",
        "csvPath",
        "markdownPath",
        "rows",
        "tenantAction",
        "acceptedPublicEvidence",
        "forbiddenEvidence",
        "workspaceManifestPath",
        "workspaceGuidePath",
        "tenantFillTargets",
        "copyableCommands",
        "prepareWorkspaceCommand",
        "completionAuditCommand",
        "finalExpectedDecision",
        "tenantMustReplacePlaceholders",
        "copyInstruction",
        "tenantEvidenceInputPath",
        "starterInputExamplePath",
        "nextImportCommand",
        "storeSubmissionAllowedStatuses",
        "storeSubmissionBaseRequiredFlags",
        "storeSubmissionChannelRequiredFlags",
        "allowedStatuses",
        "requiredFlags",
        "publicEvidenceExamples",
        "evidenceTemplatePath",
        "evidenceGuidePath",
        "importCommand",
        "perFlavorImportCommand",
        "combinedImportCommand",
        "--source-dir build/store-submission-evidence/flavors",
        "publicBoundary",
        "testFlightBuildUploaded",
        "playInternalTrackUploaded",
        "directSignedPackageReady",
        "distributionChannelReadiness",
        "ios/Runner/Runner.entitlements",
        "approved_user_choice_or_play_billing",
        "/payment/store-purchases/verify",
        "://auth/oauth/${provider}/callback",
        "build/app/outputs/bundle/",
        "build/app/outputs/flutter-apk/",
        "releasePackageReferences",
        "build/release-handoff/mobile-tenant-release-package.json",
        "build/release-handoff/mobile-tenant-release-package.md",
        "build/release-handoff/mobile-tenant-release-package.zip",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
        "uiPreviewReadableOverviewPng",
        "build/ui-preview-gallery/mobile-ui-readable-overview.png",
        "uiPreviewContactSheetPng",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
        "build/store-assets/mobile-store-assets.zip",
        "build/store-assets/store-assets-manifest.json",
        "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
        "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
        "build/store-signing-handoff/mobile-store-signing-handoff.zip",
        "build/store-signing-handoff/store-signing-handoff-manifest.json",
        "build/store-publish-config/mobile-store-publish-config.zip",
        "build/store-publish-config/store-publish-config-manifest.json",
        "build/store-submission-evidence/store-submission-evidence.json",
        "build/store-submission-evidence/store-submission-evidence-preflight.json",
        "build/store-submission-evidence/store-submission-evidence-preflight.md",
        "build/store-submission-evidence/store-submission-evidence.template.json",
        "build/store-submission-evidence/store-submission-evidence.guide.md",
        "build/store-submission-starter/store-submission-evidence-collector.html",
        "build/store-submission-starter/store-submission-operator-runbook.md",
        "build/open-source/short-drama-whitelabel-mobile.zip",
        "build/open-source/open-source-template-manifest.json",
        "build/completion-audits/mobile-app-completion.json",
        "completionUnblockerManifest",
        "build/completion-unblocker/mobile-completion-unblocker.json",
        "completionUnblockerGuide",
        "build/completion-unblocker/mobile-completion-unblocker.md",
        "storeEvidenceFixQueueCsv",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
        "storeEvidenceFixQueueMarkdown",
        "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
        "storeEvidenceFixQueueRowCount",
        "storeEvidenceFixQueueStrictImportCommand",
        "storeEvidenceFixQueueColumns",
        "public_metadata_only",
    ]
    required_test_markers = [
        "exports public native store and distribution handoff metadata",
        "exports user-choice billing review metadata",
        "tenantShouldReplaceProductIds",
        "ios/Runner/Runner.entitlements",
        "approved_user_choice_or_play_billing",
        "google_play_internal",
        "releasePackageReferences",
        "build/release-handoff/mobile-tenant-release-package.json",
        "build/release-handoff/mobile-tenant-release-package.md",
        "build/release-handoff/mobile-tenant-release-package.zip",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
        "uiPreviewReadableOverviewPng",
        "build/ui-preview-gallery/mobile-ui-readable-overview.png",
        "uiPreviewContactSheetPng",
        "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
        "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
        "build/store-assets/mobile-store-assets.zip",
        "build/store-assets/store-assets-manifest.json",
        "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
        "build/store-signing-handoff/mobile-store-signing-handoff.zip",
        "build/store-publish-config/mobile-store-publish-config.zip",
        "build/store-submission-evidence/store-submission-evidence.json",
        "build/store-submission-evidence/store-submission-evidence-preflight.json",
        "build/store-submission-evidence/store-submission-evidence-preflight.md",
        "build/store-submission-evidence/store-submission-evidence.template.json",
        "build/store-submission-evidence/store-submission-evidence.guide.md",
        "build/store-submission-starter/store-submission-evidence-collector.html",
        "build/store-submission-starter/store-submission-operator-runbook.md",
        "storeSubmissionEvidenceChecklist",
        "storeSubmissionEvidencePacket",
        "storeSubmissionEvidenceProgress",
        "exposes completion unblocker fix queue references for tenant release handoff",
        "completionUnblockerManifest",
        "completionUnblockerGuide",
        "完成收口报告",
        "完成收口指南",
        "completionClosureReport",
        "completionClosureGuide",
        "storeEvidenceFixQueueCsv",
        "storeEvidenceFixQueueMarkdown",
        "storeEvidenceFixQueueRowCount",
        "storeEvidenceFixQueueStrictImportCommand",
        "storeSubmissionEvidenceDraft",
        "storeSubmissionEvidenceDraftWorkspace",
        "storeSubmissionEvidenceRemediationMatrix",
        "storeEvidenceFixQueueHandoff",
        "storeSubmissionEvidenceImportRunbook",
        "storeSubmissionEvidenceWorkspaceHandoff",
        "storeSubmissionEvidenceCompletionReceipt",
        "exports a public remediation matrix for blocked store submission evidence fields",
        "exports an actionable store evidence fix queue handoff matching the completion unblocker queue",
        "exports a store submission evidence import runbook for final completion",
        "exports a store submission evidence workspace handoff for tenant operators",
        "exports a completion receipt contract for imported store submission evidence",
        "exports store submission evidence progress for the full app completion blocker",
        "exports a no-secret public store evidence input draft for the active flavor",
        "exports all-flavor public store evidence input drafts for full app completion",
        "tenant_store_submission_evidence_import_runbook",
        "tenant_store_submission_evidence_workspace_handoff",
        "tenant_store_submission_evidence_completion_receipt",
        "tenant_store_submission_evidence_remediation_matrix",
        "tenant_store_evidence_fix_queue_handoff",
        "tenant_public_store_submission_evidence_imported",
        "remediationSteps",
        "totalRowCount",
        "blockedFieldCount",
        "baseRequiredFieldCount",
        "channelRequiredFieldCount",
        "evidenceMetadataFieldCount",
        "completionPercent",
        "nextBlockingField",
        "nextAction",
        "sourceManifestPath",
        "tenantAction",
        "acceptedPublicEvidence",
        "forbiddenEvidence",
        "mobile-template-built-store-submission-blocked",
        "acceptedDecision",
        "requiredAuditChecks",
        "requiredEvidenceFields",
        "rejectedEvidenceStates",
        "workspaceManifestPath",
        "workspaceGuidePath",
        "tenantFillTargets",
        "copyableCommands",
        "prepareWorkspaceCommand",
        "completionAuditCommand",
        "finalExpectedDecision",
        "blocked_pending_tenant_public_store_evidence",
        "tenant_store_submission_public_evidence_input_draft",
        "tenant_store_submission_public_evidence_draft_workspace",
        "fullAppFlavorCount",
        "tenantMustReplacePlaceholders",
        "pending_tenant_action",
        "strictImportReady",
        "blockedInputPath",
        "exports a tenant evidence packet summary for portal release handoff",
        "tenant_public_store_submission_evidence_packet",
        "tenantEvidenceInputPath",
        "exports android direct submission evidence checklist for tenant distribution",
        "TestFlight build number",
        "Signed APK or AAB checksum",
        "directSignedPackageReady",
    ]
    missing = [
        f"model:{marker}"
        for marker in required_model_markers
        if marker not in model_text
    ] + [
        f"test:{marker}"
        for marker in required_test_markers
        if marker not in test_text
    ]
    if "enableAccountDeletion" not in main_text:
        missing.append("main:enableAccountDeletion")
    if "发布包交接" not in main_text:
        missing.append("main:发布包交接")
    if "租户发布包指南" not in main_text:
        missing.append("main:租户发布包指南")
    if "租户发布包归档" not in main_text:
        missing.append("main:租户发布包归档")
    if "tenantReleasePackageGuide" not in main_text:
        missing.append("main:tenantReleasePackageGuide")
    if "tenantReleasePackageArchive" not in main_text:
        missing.append("main:tenantReleasePackageArchive")
    if "UI 预览图库" not in main_text:
        missing.append("main:UI 预览图库")
    if "UI 总览图" not in main_text:
        missing.append("main:UI 总览图")
    if "UI 可读 PNG" not in main_text:
        missing.append("main:UI 可读 PNG")
    if "UI 全屏 PNG" not in main_text:
        missing.append("main:UI 全屏 PNG")
    if "UI 预览包" not in main_text:
        missing.append("main:UI 预览包")
    if "uiPreviewGalleryHtml" not in main_text:
        missing.append("main:uiPreviewGalleryHtml")
    if "uiPreviewContactSheet" not in main_text:
        missing.append("main:uiPreviewContactSheet")
    if "uiPreviewReadableOverviewPng" not in main_text:
        missing.append("main:uiPreviewReadableOverviewPng")
    if "uiPreviewContactSheetPng" not in main_text:
        missing.append("main:uiPreviewContactSheetPng")
    if "uiPreviewGalleryPackage" not in main_text:
        missing.append("main:uiPreviewGalleryPackage")
    if "商店素材" not in main_text:
        missing.append("main:商店素材")
    if "证据预检" not in main_text:
        missing.append("main:证据预检")
    if "签名交接" not in main_text:
        missing.append("main:签名交接")
    if "iosCiHandoffPackage" not in main_text:
        missing.append("main:iosCiHandoffPackage")
    if "storeSigningHandoffPackage" not in main_text:
        missing.append("main:storeSigningHandoffPackage")
    if "storePublishConfigPackage" not in main_text:
        missing.append("main:storePublishConfigPackage")
    if "storeSubmissionEvidence" not in main_text:
        missing.append("main:storeSubmissionEvidence")
    if "storeSubmissionEvidenceGuide" not in main_text:
        missing.append("main:storeSubmissionEvidenceGuide")
    if "storeSubmissionEvidenceCollector" not in main_text:
        missing.append("main:storeSubmissionEvidenceCollector")
    if "storeSubmissionOperatorRunbook" not in main_text:
        missing.append("main:storeSubmissionOperatorRunbook")
    if "storeSubmissionEvidencePacket" not in main_text:
        missing.append("main:storeSubmissionEvidencePacket")
    if "storeSubmissionEvidenceProgress" not in main_text:
        missing.append("main:storeSubmissionEvidenceProgress")
    if "storeSubmissionEvidenceDraft" not in main_text:
        missing.append("main:storeSubmissionEvidenceDraft")
    if "storeSubmissionEvidenceDraftWorkspace" not in main_text:
        missing.append("main:storeSubmissionEvidenceDraftWorkspace")
    if "storeSubmissionEvidenceRemediationMatrix" not in main_text:
        missing.append("main:storeSubmissionEvidenceRemediationMatrix")
    if "storeEvidenceFixQueueHandoff" not in main_text:
        missing.append("main:storeEvidenceFixQueueHandoff")
    if "storeSubmissionEvidenceImportRunbook" not in main_text:
        missing.append("main:storeSubmissionEvidenceImportRunbook")
    if "storeSubmissionEvidenceWorkspaceHandoff" not in main_text:
        missing.append("main:storeSubmissionEvidenceWorkspaceHandoff")
    if "storeSubmissionEvidenceCompletionReceipt" not in main_text:
        missing.append("main:storeSubmissionEvidenceCompletionReceipt")
    if "完整 App 完成阻断" not in main_text:
        missing.append("main:完整 App 完成阻断")
    if "证据导入操作流" not in main_text:
        missing.append("main:证据导入操作流")
    if "证据工作区交接" not in main_text:
        missing.append("main:证据工作区交接")
    if "导入验收回执" not in main_text:
        missing.append("main:导入验收回执")
    if "证据修复矩阵" not in main_text:
        missing.append("main:证据修复矩阵")
    if "修复队列摘要" not in main_text:
        missing.append("main:修复队列摘要")
    if "证据输入草稿" not in main_text:
        missing.append("main:证据输入草稿")
    if "多套模板证据草稿" not in main_text:
        missing.append("main:多套模板证据草稿")
    if "tenant_store_submission_evidence_import_runbook" not in main_text:
        missing.append("main:tenant_store_submission_evidence_import_runbook")
    if "tenant_store_submission_evidence_workspace_handoff" not in main_text:
        missing.append("main:tenant_store_submission_evidence_workspace_handoff")
    if "tenant_store_submission_evidence_completion_receipt" not in main_text:
        missing.append("main:tenant_store_submission_evidence_completion_receipt")
    if "tenant_store_submission_evidence_remediation_matrix" not in main_text:
        missing.append("main:tenant_store_submission_evidence_remediation_matrix")
    if "tenant_store_evidence_fix_queue_handoff" not in main_text:
        missing.append("main:tenant_store_evidence_fix_queue_handoff")
    if "tenant_store_submission_public_evidence_input_draft" not in main_text:
        missing.append("main:tenant_store_submission_public_evidence_input_draft")
    if "tenant_store_submission_public_evidence_draft_workspace" not in main_text:
        missing.append("main:tenant_store_submission_public_evidence_draft_workspace")
    if "strictImportReady" not in main_text:
        missing.append("main:strictImportReady")
    if "blockedInputPath" not in main_text:
        missing.append("main:blockedInputPath")
    if "strictImportCommand" not in main_text:
        missing.append("main:strictImportCommand")
    if "remediationSteps" not in main_text:
        missing.append("main:remediationSteps")
    if "tenantAction" not in main_text:
        missing.append("main:tenantAction")
    if "acceptedPublicEvidence" not in main_text:
        missing.append("main:acceptedPublicEvidence")
    if "forbiddenEvidence" not in main_text:
        missing.append("main:forbiddenEvidence")
    if "prepareWorkspaceCommand" not in main_text:
        missing.append("main:prepareWorkspaceCommand")
    if "completionAuditCommand" not in main_text:
        missing.append("main:completionAuditCommand")
    if "完成阻断修复队列" not in main_text:
        missing.append("main:完成阻断修复队列")
    if "completionUnblockerManifest" not in main_text:
        missing.append("main:completionUnblockerManifest")
    if "completionUnblockerGuide" not in main_text:
        missing.append("main:completionUnblockerGuide")
    if "storeEvidenceFixQueueCsv" not in main_text:
        missing.append("main:storeEvidenceFixQueueCsv")
    if "storeEvidenceFixQueueMarkdown" not in main_text:
        missing.append("main:storeEvidenceFixQueueMarkdown")
    if "storeEvidenceFixQueueRowCount" not in main_text:
        missing.append("main:storeEvidenceFixQueueRowCount")
    if "storeEvidenceFixQueueStrictImportCommand" not in main_text:
        missing.append("main:storeEvidenceFixQueueStrictImportCommand")
    if "totalRowCount" not in main_text:
        missing.append("main:totalRowCount")
    if "queue.rows" not in main_text:
        missing.append("main:queue.rows")
    if "模板证据缺口" not in main_text:
        missing.append("main:模板证据缺口")
    if "blockedFieldCount" not in main_text:
        missing.append("main:blockedFieldCount")
    if "baseRequiredFieldCount" not in main_text:
        missing.append("main:baseRequiredFieldCount")
    if "channelRequiredFieldCount" not in main_text:
        missing.append("main:channelRequiredFieldCount")
    if "evidenceMetadataFieldCount" not in main_text:
        missing.append("main:evidenceMetadataFieldCount")
    if "completionPercent" not in main_text:
        missing.append("main:completionPercent")
    if "nextBlockingField" not in main_text:
        missing.append("main:nextBlockingField")
    if "queueNextAction" not in main_text:
        missing.append("main:queueNextAction")
    if "queueTenantAction" not in main_text:
        missing.append("main:queueTenantAction")
    if "queueAcceptedPublicEvidence" not in main_text:
        missing.append("main:queueAcceptedPublicEvidence")
    if "queueForbiddenEvidence" not in main_text:
        missing.append("main:queueForbiddenEvidence")
    if "workspaceManifestPath" not in main_text:
        missing.append("main:workspaceManifestPath")
    if "workspaceGuidePath" not in main_text:
        missing.append("main:workspaceGuidePath")
    if "tenantFillTargets" not in main_text:
        missing.append("main:tenantFillTargets")
    if "copyableCommands" not in main_text:
        missing.append("main:copyableCommands")
    if "acceptedDecision" not in main_text:
        missing.append("main:acceptedDecision")
    if "requiredAuditChecks" not in main_text:
        missing.append("main:requiredAuditChecks")
    if "requiredEvidenceFields" not in main_text:
        missing.append("main:requiredEvidenceFields")
    if "rejectedEvidenceStates" not in main_text:
        missing.append("main:rejectedEvidenceStates")
    required_main_markers = [
        "模板选择矩阵",
        "templateOptions",
        "setPreviewTemplate",
        "defaultStoreComplianceMode",
        "商店提交证据清单",
        "allowedStatuses",
        "requiredFlags",
        "publicEvidenceExamples",
        "evidenceTemplatePath",
        "evidenceGuidePath",
        "importCommand",
        "perFlavorImportCommand",
        "combinedImportCommand",
        "分模板输入优先",
        "publicBoundary",
        "证据收集页",
        "操作手册",
        "租户提交证据包",
        "appSubmissionEvidencePacket",
        "appSubmissionEvidenceProgress",
        "appSubmissionEvidenceDraft",
        "appSubmissionEvidenceDraftWorkspace",
        "appSubmissionEvidenceImportRunbook",
        "appSubmissionEvidenceWorkspaceHandoff",
        "appSubmissionEvidenceCompletionReceipt",
        "appStoreEvidenceFixQueueHandoff",
        "tenantEvidenceInputPath",
        "starterInputExamplePath",
        "nextImportCommand",
        "requiredChecklistFlags",
        "Tenant evidence blocked",
        "blockedFields",
        "workspaceManifestPath",
        "workspaceGuidePath",
        "tenantFillTargets",
        "copyableCommands",
        "acceptedDecision",
        "requiredAuditChecks",
        "requiredEvidenceFields",
        "rejectedEvidenceStates",
        "prepareWorkspaceCommand",
        "completionAuditCommand",
        "完成阻断修复队列",
        "修复队列摘要",
        "storeEvidenceFixQueueHandoff",
        "tenant_store_evidence_fix_queue_handoff",
        "totalRowCount",
        "模板证据缺口",
        "blockedFieldCount",
        "baseRequiredFieldCount",
        "channelRequiredFieldCount",
        "evidenceMetadataFieldCount",
        "completionPercent",
        "nextBlockingField",
        "queueNextAction",
        "queue.rows",
        "queueTenantAction",
        "queueAcceptedPublicEvidence",
        "queueForbiddenEvidence",
        "completionUnblockerManifest",
        "completionUnblockerGuide",
        "storeEvidenceFixQueueCsv",
        "storeEvidenceFixQueueMarkdown",
        "storeEvidenceFixQueueRowCount",
        "storeEvidenceFixQueueStrictImportCommand",
        "finalExpectedDecision",
        "completionDecisionAfterImport",
        "appExternalStoreAccountConfig",
        "externalStoreAccountConfig",
        "外部账号与签名资料接入入口",
        "外部账号清单",
        "外部账号指南",
        "外部账号交接包",
        "externalAccountHandoffManifest",
        "externalAccountHandoffGuide",
        "externalAccountHandoffPackage",
        "externalConfigEvidenceInput",
        "externalConfigNoCredentialBoundary",
        "storeSubmissionEvidenceDraft",
        "tenantMustReplacePlaceholders",
        "fullAppFlavorCount",
        "feature-draft-grid",
    ]
    missing.extend(
        f"main:{marker}"
        for marker in required_main_markers
        if marker not in main_text
    )
    forbidden_runtime_markers = [
        "sk_live_",
        "sk_test_",
        "rk_live_",
        "whsec_",
        "private_key",
        "secretCiphertext",
        "secret_hash",
    ]
    leaked = [
        marker
        for marker in forbidden_runtime_markers
        if marker.lower() in f"{model_text}\n{test_text}".lower()
    ]
    if missing or leaked:
        problems = missing + [f"forbidden:{marker}" for marker in leaked]
        return Check(
            "tenant_portal_release_handoff",
            "failed",
            f"Tenant portal release handoff coverage problems: {', '.join(problems)}",
            evidence,
        )

    return Check(
        "tenant_portal_release_handoff",
        "passed",
        "Tenant portal exports release handoff metadata for OAuth callbacks, store products, native capabilities, store review declarations, distribution channels, external account/signing config entry points and generated handoff artifact references, UI preview gallery/contact sheet, PNG review boards, store assets, iOS CI handoff, store signing handoff, store submission evidence, store submission evidence checklist, store submission evidence packet, strict import readiness, evidence input draft, all-flavor evidence draft workspace, evidence remediation matrix, actionable fix queue handoff, per-flavor evidence gap summary, evidence import runbook, evidence workspace handoff, evidence completion receipt, completion closure report, completion unblocker fix queue, store submission evidence collector, store submission operator runbook, release package references, tenant release archive, and regional user-choice billing without client-side provider secrets.",
        evidence,
    )


def check_ci_workflow(root: Path) -> Check:
    workflow, workflow_evidence = resolve_workflow_path(root)
    evidence = [workflow_evidence]
    if not workflow.exists():
        return Check(
            "ci_workflow",
            "missing",
            "Mobile Flutter GitHub Actions workflow is missing.",
            evidence,
        )

    text = read_text(workflow)
    required_markers = [
        "workflow_dispatch:",
        "jobs:",
        "test:",
        "android-build:",
        "ios-build:",
        "ios-ci-evidence:",
        "needs: ios-build",
        "runs-on: macos-15",
        "flavor: [coolshow, hongguo, douyin, hippo, reelshort]",
        "./scripts/check_mobile.sh",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" android debug apk",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" android release apk",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" android release appbundle",
        "./scripts/scan_release_artifacts.py",
        "./scripts/write_store_handoff_manifest.py",
        "xcodebuild -version",
        "pod --version",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" ios debug",
        "./scripts/build_flavor.sh \"${{ matrix.flavor }}\" ios release",
        "actions/download-artifact@v4",
        "pattern: mobile-*-ios-unsigned",
        "python3 scripts/import_ios_ci_artifacts.py --strict",
        "actions/upload-artifact@v4",
        "mobile-template-handoff",
        "mobile-ios-ci-handoff.zip",
        "mobile-store-signing-handoff.zip",
        "mobile-store-publish-config.zip",
        "store-submission-evidence.json",
        "store-submission-evidence.template.json",
        "store-submission-evidence.guide.md",
        "mobile-${{ matrix.flavor }}-ios-unsigned",
        "mobile-ios-ci-artifact-evidence",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if not any(
        marker in text
        for marker in [
            "mobile/build/ios-ci-evidence/ios-ci-artifacts.json",
            "build/ios-ci-evidence/ios-ci-artifacts.json",
        ]
    ):
        missing.append("ios-ci-evidence artifact path")
    if missing:
        return Check(
            "ci_workflow",
            "missing",
            f"Mobile CI workflow is missing required markers: {', '.join(missing)}",
            evidence,
        )

    return Check(
        "ci_workflow",
        "passed",
        "CI covers manual workflow dispatch, check_mobile handoff package upload, store signing, store publish config handoff upload, and store submission evidence handoff upload, five-flavor Android debug APK, release APK, release AAB builds, store handoff manifests, artifact secret scans, uploaded package metadata, five-flavor unsigned iOS debug builds, five-flavor unsigned iOS release builds, and automated unsigned iOS artifact evidence import.",
        evidence,
    )


def check_flutter_toolchain_audit(root: Path) -> Check:
    output = root / "build" / "flutter-toolchain" / "flutter-toolchain-audit.json"
    evidence = [
        "scripts/flutter_toolchain_audit.py",
        "scripts/resolve_flutter_bin.sh",
        "scripts/check_mobile.sh",
        "build/flutter-toolchain/flutter-toolchain-audit.json",
    ]
    if output.exists():
        try:
            report = json.loads(read_text(output))
        except json.JSONDecodeError as error:
            return Check(
                "flutter_toolchain_audit",
                "failed",
                f"Flutter toolchain audit JSON is invalid: {error}",
                evidence,
                completion_blocking=False,
            )
    else:
        report = flutter_toolchain_audit.build_report(root=root, timeout_seconds=10)
        flutter_toolchain_audit.write_report(report, output, root=root)

    result = report.get("result")
    if result == "passed":
        detail = "Local Flutter and Dart commands are responsive for fresh Flutter tests."
        status = "passed"
    elif result == "blocked":
        detail = f"Local Flutter toolchain is not ready for fresh Flutter tests: {report.get('blockers') or 'unknown blocker'}"
        status = "blocked"
    else:
        detail = f"Flutter toolchain audit returned an unexpected result: {result!r}"
        status = "failed"
    return Check(
        "flutter_toolchain_audit",
        status,
        detail,
        evidence,
        completion_blocking=False,
    )


def check_ios_environment(strict_ios: bool) -> Check:
    code, developer_dir = command_output(["xcode-select", "-p"])
    full_xcode_selected = code == 0 and "Xcode" in developer_dir and "CommandLineTools" not in developer_dir
    applications_xcode = Path("/Applications/Xcode.app").exists()
    pod_path = shutil.which("pod")
    pod_version = None
    if pod_path:
        _, pod_version = command_output([pod_path, "--version"])

    blockers: list[str] = []
    if not applications_xcode:
        blockers.append("/Applications/Xcode.app is missing")
    if not full_xcode_selected:
        blockers.append(f"full Xcode is not selected; xcode-select={developer_dir or 'unavailable'}")
    if not pod_path:
        blockers.append("CocoaPods not installed")

    evidence = [
        f"xcode-select -p: {developer_dir or 'unavailable'}",
        f"/Applications/Xcode.app: {'present' if applications_xcode else 'missing'}",
        f"pod: {pod_version or 'missing'}",
    ]
    if blockers:
        return Check(
            "ios_build_environment",
            "blocked" if not strict_ios else "failed",
            "; ".join(blockers),
            evidence,
        )
    return Check(
        "ios_build_environment",
        "passed",
        "Full Xcode and CocoaPods are available for unsigned iOS build verification.",
        evidence,
    )


def build_report(root: Path, strict_ios: bool) -> dict[str, Any]:
    optional_checks = [
        check
        for check in [
            check_android_runtime_smoke(root),
            check_ios_runtime_smoke(root),
        ]
        if check is not None
    ]
    checks = [
        check_required_files(root),
        check_flavor_configs(root),
        check_prototype_goldens(root),
        check_prototype_responsive_viewports(root),
        check_test_coverage_files(root),
        check_runtime_identity(root),
        check_native_playback_dependency(root),
        check_source_secret_boundary(root),
        check_mobile_open_source_release(root),
        check_mobile_open_source_package(root),
        check_github_publish_handoff_package(root),
        check_github_publication_evidence(root),
        check_ios_static_release_config(root),
        check_ios_ci_handoff_package(root),
        check_store_signing_handoff_package(root),
        check_store_publish_config_package(root),
        check_external_account_handoff_package(root),
        check_store_submission_starter_package(root),
        check_ios_build_matrix(root),
        check_ios_ci_artifact_evidence(root),
        check_store_handoff_manifest(root),
        check_store_submission_evidence(root),
        check_store_submission_evidence_preflight(root),
        check_completion_unblocker_package(root),
        check_store_assets_package(root),
        check_ui_preview_gallery(root),
        check_app_handoff_package(root),
        check_tenant_release_package(root),
        check_tenant_portal_release_handoff(root),
        check_android_release_artifacts(root),
        check_android_package_structure(root),
        check_android_apk_badging(root),
        *optional_checks,
        check_release_artifact_secret_boundary(root),
        check_ci_workflow(root),
        check_flutter_toolchain_audit(root),
        check_ios_environment(strict_ios),
    ]
    checks = apply_completion_boundaries(checks)
    summary = completion_summary(checks)
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "appCompletion": "complete" if summary["missing"] == 0 and summary["failed"] == 0 and summary["blocked"] == 0 else "incomplete",
        "summary": summary,
        "checks": [check.to_json() for check in checks],
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
        "--strict-ios",
        action="store_true",
        help="treat missing full Xcode/CocoaPods as a failure instead of an environment blocker",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON output path; defaults to build/completion-audits/mobile-app-completion.json",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output or root / "build" / "completion-audits" / "mobile-app-completion.json"
    report = build_report(root, strict_ios=args.strict_ios)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote completion audit: {output.relative_to(root)}")
    for check in report["checks"]:
        print(f"{check['status']:>7} {check['id']}: {check['detail']}")

    summary = report["summary"]
    if summary["missing"] or summary["failed"]:
        return 1
    if summary["blocked"] and args.strict_ios:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
