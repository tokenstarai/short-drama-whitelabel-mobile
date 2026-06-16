# CoolShow iOS Test Install

This document covers the CoolShow Short iPhone preview package.

## What Can Be Built Locally

The repository can build a CoolShow `iphoneos` app bundle and package it as an
unsigned IPA handoff artifact:

```bash
cd mobile
./scripts/build_coolshow_ios_test.sh
```

Output:

- `build/ios-test/coolshow/CoolShowShort-release-iphoneos-unsigned.ipa`
- `build/ios-test/coolshow/coolshow-ios-test-manifest.json`
- `build/ios-test/coolshow/README.md`
- `build/ios-test/coolshow/CoolShowShort-ota-manifest.template.plist`
- `build/ios-test/coolshow/CoolShowShort-ota-install-url.template.txt`

The unsigned IPA proves the iPhone binary, bundle id, display name, deep link,
and Flutter runtime flavor, but it is not directly installable on a real iPhone.
iOS requires a valid Apple signature and provisioning profile for every real
device install.

The manifest records the current install preflight as public metadata:

- `installReady`
- `missingInstallRequirements`
- `deviceCount`
- `codeSigningIdentityCount`
- `provisioningProfileCount`
- `directInstallStatus`

## Direct Install Requirements

To install directly on an iPhone, the signing environment must provide:

- A trusted iPhone connected to this Mac, or a trusted network device visible to
  `xcrun devicectl list devices`.
- Xcode signed in to an Apple Developer account.
- A valid iOS Development or Apple Development signing certificate in Keychain.
- `IOS_DEVELOPMENT_TEAM`, the Apple Developer Team ID.
- An App ID/provisioning profile for `com.coolshow.short` that includes the
  target device UDID.

When those are available:

```bash
cd mobile
IOS_DEVELOPMENT_TEAM=YOUR_TEAM_ID IOS_INSTALL_TO_DEVICE=1 ./scripts/build_coolshow_ios_test.sh
```

Optional overrides:

```bash
IOS_DEVICE_ID=TARGET_DEVICE_UDID
IOS_SIGNED_CONFIGURATION=Debug
IOS_UNSIGNED_BUILD_MODE=release
```

The script builds the `coolshow` scheme with automatic signing, installs the
signed app through `devicectl`, and launches `com.coolshow.short`.

To re-run only the install/signing preflight against the latest generated app
bundle:

```bash
cd mobile
IOS_SKIP_UNSIGNED_BUILD=1 IOS_INSTALL_TO_DEVICE=1 ./scripts/build_coolshow_ios_test.sh
```

## OTA Install Preview After Signing

For a phone-only preview link, first produce a signed IPA with a provisioning
profile that covers the target iPhone. Upload the signed IPA to HTTPS, replace
`HTTPS_URL_TO_SIGNED_IPA` in:

```text
build/ios-test/coolshow/CoolShowShort-ota-manifest.template.plist
```

Upload the plist to HTTPS, then open this on the iPhone:

```text
itms-services://?action=download-manifest&url=HTTPS_URL_TO_OTA_MANIFEST_PLIST
```

This OTA route still requires Apple signing. It cannot install the unsigned IPA.

## Current Boundary

Do not commit Apple signing files, `.mobileprovision` profiles, `.p12`
certificates, App Store Connect API keys, OAuth secrets, payment secrets, Tenant
Edge secrets, or Cloudflare tokens. The script writes only local build evidence
and package metadata under `mobile/build/ios-test/coolshow/`.
