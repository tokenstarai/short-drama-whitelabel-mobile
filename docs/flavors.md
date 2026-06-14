# Flutter Flavors

## Primary MVP Flavors

| Flavor | Template | Tenant code | Bundle id | Compliance | Adapter base |
| --- | --- | --- | --- | --- | --- |
| `hongguo` | `hongguo_inspired` | `goldfruit` | `com.shortdrama.goldfruit` | `app_store` | `https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev` |
| `douyin` | `douyin_inspired` | `pulsedrama` | `com.shortdrama.pulse` | `android_direct` | tenant-specific edge URL |
| `hippo` | `hippo_inspired` | `riverdrama` | `com.shortdrama.river` | `app_store` | tenant-specific edge URL |
| `reelshort` | `reelshort_inspired` | `cliffdrama` | `com.shortdrama.cliff` | `play_store` | tenant-specific edge URL |

Compatibility aliases:

- `golden` maps to `hongguo`.
- `purple` maps to `hippo`.
- `blue` maps to `douyin`.

## Runtime Selection

Use a Dart define:

```bash
flutter run --flavor hongguo --dart-define=APP_FLAVOR=hongguo
flutter run --flavor douyin --dart-define=APP_FLAVOR=douyin
flutter run --flavor hippo --dart-define=APP_FLAVOR=hippo
flutter run --flavor reelshort --dart-define=APP_FLAVOR=reelshort
```

`lib/flavor/flavor.dart` maps the selected value to brand color, app name, bundle id, feature flags, tenant adapter base URL, style template, auth providers, and C-end payment capability.

## Store Compliance Modes

| Mode | Visible consumer payment providers |
| --- | --- |
| `app_store` | `iap` |
| `play_store` | `play_billing` |
| `regional_user_choice` | `play_billing`, `stripe`, `paypal`, `bank_transfer`, `local_wallet`, `point_card` |
| `android_direct` | `stripe`, `paypal`, `bank_transfer`, `local_wallet`, `crypto`, `point_card` |

The store handoff manifest exports `storeProductRegistration` only for visible
store-native providers: `iap` rows for App Store Connect and `play_billing`
rows for Google Play Console. Android direct flavors do not create fake store
products; their external payment credentials stay in Tenant Edge or API Worker
configuration.

The same manifest also exports `nativeCapabilityRegistration` for each flavor.
It maps auth/payment providers to iOS capabilities such as custom URL schemes,
Sign in with Apple, and IAP, plus Android capabilities such as internet,
custom URL schemes, OAuth SHA fingerprints, Play Billing, or direct-distribution
signing. The list is public release metadata only; tenant signing material and
provider credentials stay outside the repository.

`storeReviewDeclarations` turns the selected compliance mode into starter store
review answers. App Store flavors declare IAP-only paid digital content and
in-app account deletion, Play Store flavors declare Play Billing and Data
safety duties, and Android direct flavors declare tenant-owned external
payments plus region/legal review outside App Store or Play submission.

`distributionChannelReadiness` maps the selected mode to a primary release
channel: App Store flavors target TestFlight/App Store Connect, Play Store and
regional user-choice flavors target Play internal testing with the release AAB,
and Android direct flavors target signed APK/AAB distribution. It also records
the current local iOS blocker when full Xcode is not available.

## Native Configuration

Android and iOS native project files are present in this template.

Android has product flavors matching the four MVP templates:

```bash
flutter run --flavor hongguo --dart-define=APP_FLAVOR=hongguo
flutter run --flavor douyin --dart-define=APP_FLAVOR=douyin
flutter run --flavor hippo --dart-define=APP_FLAVOR=hippo
flutter run --flavor reelshort --dart-define=APP_FLAVOR=reelshort
```

The helper script wraps the same build contract:

```bash
./scripts/build_flavor.sh hongguo android debug
./scripts/build_flavor.sh reelshort android release
./scripts/build_flavor.sh hongguo ios release
```

iOS uses the generated `Runner` project plus flavor xcconfig presets:

- `ios/Flutter/Hongguo.xcconfig`
- `ios/Flutter/Douyin.xcconfig`
- `ios/Flutter/Hippo.xcconfig`
- `ios/Flutter/Reelshort.xcconfig`

The shared Xcode schemes are `hongguo`, `douyin`, `hippo`, and `reelshort`.
Each scheme selects the matching xcconfig before build, and each flavor
xcconfig carries the public `APP_FLAVOR` Dart define used by Flutter runtime
selection. `ios/Flutter/WhitelabelDefaults.xcconfig` keeps `hongguo` as the
default for generic Runner builds.

Native defaults included in this repo:

- Bundle ids from this document.
- App display names from `assets/config/*/tenant.brand.json`.
- Deep links and OAuth callbacks per tenant. The public store handoff manifest exports callback URIs in the form `<scheme>://auth/oauth/<provider>/callback` for enabled Google/Facebook/Apple providers, plus the native files that own the scheme.
- Original launcher icons for each flavor under Android flavor resources and
  iOS `AppIcon-<flavor>.appiconset` asset catalogs.
- Sign in with Apple when iOS builds enable Google or Facebook login.

Regenerate the publish-safe placeholder icons after changing brand colors:

```bash
./scripts/generate_launcher_icons.py
./scripts/check_app_config.mjs
./scripts/check_native_config.sh
```

`scripts/check_app_config.mjs` validates the publishable contract across:

- `assets/config/<flavor>/tenant.brand.json`
- `assets/config/<flavor>/tenant.template.json`
- `assets/config/<flavor>/tenant.features.json`
- `lib/flavor/flavor.dart`
- Android flavor application ids, app labels, and deep-link schemes
- iOS xcconfig presets, shared schemes, app icon names, and Dart defines
- generated release manifests when `build/release-manifests/mobile-artifacts.json` exists

This catches drift before a tenant exports a configuration that no longer matches the App package, supported locales, payment compliance mode, or native bundle metadata.

Do not put server-side tenant secrets in Gradle, Xcode build settings, plist files, or Dart defines.
