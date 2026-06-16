#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"
flutter_bin="$(bash "$script_dir/resolve_flutter_bin.sh")"

mode="${IOS_UNSIGNED_BUILD_MODE:-release}"
signed_configuration="${IOS_SIGNED_CONFIGURATION:-Debug}"
team_id="${IOS_DEVELOPMENT_TEAM:-}"
device_id="${IOS_DEVICE_ID:-}"
install_mode="${IOS_INSTALL_TO_DEVICE:-auto}"
load_remote_config="${LOAD_REMOTE_CONFIG:-false}"
output_dir="${IOS_TEST_OUTPUT_DIR:-$mobile_dir/build/ios-test/coolshow}"
ota_ipa_url="${IOS_OTA_IPA_URL:-HTTPS_URL_TO_SIGNED_IPA}"
ota_manifest_url="${IOS_OTA_MANIFEST_URL:-HTTPS_URL_TO_OTA_MANIFEST_PLIST}"

defaults_config="$mobile_dir/ios/Flutter/WhitelabelDefaults.xcconfig"
coolshow_config="$mobile_dir/ios/Flutter/Coolshow.xcconfig"
defaults_backup=""

restore_defaults() {
  if [[ -n "$defaults_backup" && -f "$defaults_backup" ]]; then
    cp "$defaults_backup" "$defaults_config"
    rm -f "$defaults_backup"
  fi
}
trap restore_defaults EXIT

fail() {
  echo "error: $*" >&2
  exit 1
}

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

xml_escape() {
  printf '%s' "$1" | sed \
    -e 's/&/\&amp;/g' \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&apos;/g"
}

case "$mode" in
  debug|profile|release) ;;
  *) fail "IOS_UNSIGNED_BUILD_MODE must be debug, profile, or release" ;;
esac

case "$signed_configuration" in
  Debug|Profile|Release) ;;
  *) fail "IOS_SIGNED_CONFIGURATION must be Debug, Profile, or Release" ;;
esac

case "$install_mode" in
  auto|0|1|false|true) ;;
  *) fail "IOS_INSTALL_TO_DEVICE must be auto, 0, 1, false, or true" ;;
esac

if ! xcodebuild -version >/dev/null 2>&1; then
  developer_dir="$(xcode-select -p 2>/dev/null || echo "unavailable")"
  cat >&2 <<EOF
Full Xcode is required for iOS test packaging.
Current developer directory: $developer_dir
EOF
  exit 4
fi

if ! command -v pod >/dev/null 2>&1; then
  cat >&2 <<'EOF'
CocoaPods is required because the Flutter template includes native plugins.
Install it before building iOS:
  sudo gem install cocoapods
EOF
  exit 4
fi

if [[ ! -f "$coolshow_config" ]]; then
  fail "missing CoolShow iOS config: $coolshow_config"
fi

mkdir -p "$output_dir"

defaults_backup="$(mktemp)"
cp "$defaults_config" "$defaults_backup"
cp "$coolshow_config" "$defaults_config"

if [[ "${IOS_SKIP_UNSIGNED_BUILD:-0}" != "1" ]]; then
  run "$script_dir/build_flavor.sh" coolshow ios "$mode"
fi

device_app="$mobile_dir/build/ios/iphoneos/Runner.app"
if [[ ! -d "$device_app" ]]; then
  case "$mode" in
    debug) candidate="$mobile_dir/build/ios/Debug-iphoneos/Runner.app" ;;
    profile) candidate="$mobile_dir/build/ios/Profile-iphoneos/Runner.app" ;;
    release) candidate="$mobile_dir/build/ios/Release-iphoneos/Runner.app" ;;
  esac
  if [[ -d "$candidate" ]]; then
    device_app="$candidate"
  fi
fi

if [[ ! -d "$device_app" ]]; then
  fail "missing built iPhone app bundle under build/ios/iphoneos"
fi

bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$device_app/Info.plist")"
display_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "$device_app/Info.plist" 2>/dev/null || /usr/libexec/PlistBuddy -c 'Print :CFBundleName' "$device_app/Info.plist")"
version_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$device_app/Info.plist")"
version_code="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$device_app/Info.plist")"

if [[ "$bundle_id" != "com.coolshow.short" ]]; then
  fail "built bundle id is $bundle_id, expected com.coolshow.short"
fi

payload_dir="$output_dir/Payload"
unsigned_ipa="$output_dir/CoolShowShort-${mode}-iphoneos-unsigned.ipa"
rm -rf "$payload_dir" "$unsigned_ipa"
mkdir -p "$payload_dir"
cp -R "$device_app" "$payload_dir/Runner.app"
(cd "$output_dir" && /usr/bin/zip -qry "$(basename "$unsigned_ipa")" Payload)

unsigned_size="$(stat -f '%z' "$unsigned_ipa")"
unsigned_sha="$(shasum -a 256 "$unsigned_ipa" | awk '{print $1}')"
app_size_bytes="$(du -sk "$device_app" | awk '{print $1 * 1024}')"
signing_status="unsigned"
if codesign -dv "$device_app" >/tmp/coolshow-ios-codesign.log 2>&1; then
  signing_status="signed"
fi
cp /tmp/coolshow-ios-codesign.log "$output_dir/codesign-device-app.txt" 2>/dev/null || true

xcodebuild -version > "$output_dir/xcodebuild-version.txt"
"$flutter_bin" --version > "$output_dir/flutter-version.txt"
security find-identity -v -p codesigning > "$output_dir/code-signing-identities.txt" 2>&1 || true
xcrun devicectl list devices --json-output "$output_dir/devices.json" > "$output_dir/devices.txt" 2>&1 || true

identity_count="$(awk '/valid identities found/{print $1}' "$output_dir/code-signing-identities.txt" | tail -1)"
identity_count="${identity_count:-0}"
profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"
profile_count="0"
if [[ -d "$profile_dir" ]]; then
  profile_count="$(find "$profile_dir" -maxdepth 1 -type f -name '*.mobileprovision' | wc -l | tr -d ' ')"
fi
device_count="$(python3 - "$output_dir/devices.json" <<'PY'
import json
import sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print(0)
    raise SystemExit(0)
print(len(data.get("result", {}).get("devices", [])))
PY
)"

resolved_device_id="$device_id"
if [[ -z "$resolved_device_id" ]]; then
  resolved_device_id="$(python3 - "$output_dir/devices.json" <<'PY'
import json
import sys
path = sys.argv[1]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
devices = data.get("result", {}).get("devices", [])
if devices:
    print(devices[0].get("identifier") or devices[0].get("udid") or "")
else:
    print("")
PY
)"
fi

ios_team_configured="false"
if [[ -n "$team_id" ]]; then
  ios_team_configured="true"
fi
generated_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
ota_manifest_template="$output_dir/CoolShowShort-ota-manifest.template.plist"
ota_install_url_template="$output_dir/CoolShowShort-ota-install-url.template.txt"
escaped_ota_ipa_url="$(xml_escape "$ota_ipa_url")"
escaped_bundle_id="$(xml_escape "$bundle_id")"
escaped_version_name="$(xml_escape "$version_name")"
escaped_display_name="$(xml_escape "$display_name")"

cat > "$ota_manifest_template" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>items</key>
  <array>
    <dict>
      <key>assets</key>
      <array>
        <dict>
          <key>kind</key>
          <string>software-package</string>
          <key>url</key>
          <string>$escaped_ota_ipa_url</string>
        </dict>
      </array>
      <key>metadata</key>
      <dict>
        <key>bundle-identifier</key>
        <string>$escaped_bundle_id</string>
        <key>bundle-version</key>
        <string>$escaped_version_name</string>
        <key>kind</key>
        <string>software</string>
        <key>title</key>
        <string>$escaped_display_name</string>
      </dict>
    </dict>
  </array>
</dict>
</plist>
EOF

cat > "$ota_install_url_template" <<EOF
itms-services://?action=download-manifest&url=$ota_manifest_url
EOF

install_status="skipped"
install_blocker="none"
signed_app_path=""
signed_ipa=""

install_blockers=()
if [[ -z "$resolved_device_id" ]]; then
  install_blockers+=("no trusted iPhone detected")
fi
if [[ "$identity_count" == "0" ]]; then
  install_blockers+=("no valid Apple code signing identity found")
fi
if [[ -z "$team_id" ]]; then
  install_blockers+=("IOS_DEVELOPMENT_TEAM is not set")
fi

install_ready="true"
if (( ${#install_blockers[@]} > 0 )); then
  install_ready="false"
  install_blocker="$(printf '%s; ' "${install_blockers[@]}")"
  install_blocker="${install_blocker%; }"
fi
missing_requirements_json="$(python3 - "${install_blockers[@]}" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1:], ensure_ascii=False))
PY
)"

should_install="0"
if [[ "$install_mode" == "1" || "$install_mode" == "true" ]]; then
  should_install="1"
elif [[ "$install_mode" == "auto" && -n "$team_id" && -n "$resolved_device_id" && "$identity_count" != "0" ]]; then
  should_install="1"
fi

if [[ "$should_install" == "1" ]]; then
  if [[ "$install_blocker" != "none" ]]; then
    install_status="blocked"
  else
    derived_data="$output_dir/DerivedData"
    rm -rf "$derived_data"
    run xcodebuild \
      -workspace "$mobile_dir/ios/Runner.xcworkspace" \
      -scheme coolshow \
      -configuration "$signed_configuration" \
      -destination "id=$resolved_device_id" \
      -derivedDataPath "$derived_data" \
      -allowProvisioningUpdates \
      -allowProvisioningDeviceRegistration \
      DEVELOPMENT_TEAM="$team_id" \
      CODE_SIGN_STYLE=Automatic \
      FLUTTER_TARGET=lib/main.dart \
      DART_DEFINES="QVBQX0ZMQVZPUj1jb29sc2hvdw==,TE9BRF9SRU1PVEVfQ09ORklHPWZhbHNl" \
      build

    signed_app_path="$derived_data/Build/Products/${signed_configuration}-iphoneos/Runner.app"
    if [[ ! -d "$signed_app_path" ]]; then
      fail "signed build completed but app bundle was not found: $signed_app_path"
    fi

    signed_payload_root="$output_dir/signed-ipa"
    signed_payload="$signed_payload_root/Payload"
    signed_ipa="$output_dir/CoolShowShort-${signed_configuration}-iphoneos-signed.ipa"
    rm -rf "$signed_payload_root" "$signed_ipa"
    mkdir -p "$signed_payload"
    cp -R "$signed_app_path" "$signed_payload/Runner.app"
    (cd "$signed_payload_root" && /usr/bin/zip -qry "$signed_ipa" Payload)

    run xcrun devicectl device install app \
      --device "$resolved_device_id" \
      "$signed_app_path" \
      --json-output "$output_dir/install-result.json"
    run xcrun devicectl device process launch \
      --device "$resolved_device_id" \
      --terminate-existing \
      --json-output "$output_dir/launch-result.json" \
      "$bundle_id"
    install_status="installed"
  fi
else
  if [[ "$install_blocker" == "none" ]]; then
    install_blocker="IOS_INSTALL_TO_DEVICE is disabled"
  fi
fi

manifest="$output_dir/coolshow-ios-test-manifest.json"
cat > "$manifest" <<EOF
{
  "schemaVersion": 1,
  "generatedAt": "$generated_at",
  "flavor": "coolshow",
  "bundleId": "$bundle_id",
  "displayName": "$display_name",
  "versionName": "$version_name",
  "versionCode": "$version_code",
  "loadRemoteConfig": "$load_remote_config",
  "unsignedBuildMode": "$mode",
  "unsignedAppPath": "${device_app#$mobile_dir/}",
  "unsignedAppSigningStatus": "$signing_status",
  "unsignedAppSizeBytes": $app_size_bytes,
  "unsignedIpaPath": "${unsigned_ipa#$mobile_dir/}",
  "unsignedIpaSizeBytes": $unsigned_size,
  "unsignedIpaSha256": "$unsigned_sha",
  "otaManifestTemplatePath": "${ota_manifest_template#$mobile_dir/}",
  "otaInstallUrlTemplatePath": "${ota_install_url_template#$mobile_dir/}",
  "otaRequiresSignedIpa": true,
  "deviceCount": $device_count,
  "codeSigningIdentityCount": $identity_count,
  "provisioningProfileCount": $profile_count,
  "resolvedDeviceId": "${resolved_device_id:-}",
  "iosDevelopmentTeamConfigured": $ios_team_configured,
  "installReady": $install_ready,
  "requestedInstallMode": "$install_mode",
  "missingInstallRequirements": $missing_requirements_json,
  "directInstallStatus": "$install_status",
  "directInstallBlocker": "$install_blocker",
  "signedConfiguration": "$signed_configuration",
  "signedAppPath": "${signed_app_path#$mobile_dir/}",
  "signedIpaPath": "${signed_ipa#$mobile_dir/}",
  "secretBoundary": "No Apple signing material, provisioning profiles, tenant secrets, OAuth secrets, payment secrets, or Cloudflare tokens are written by this script."
}
EOF

cat > "$output_dir/README.md" <<EOF
# CoolShow Short iOS Test Package

Generated for the CoolShow Short white-label template.

## Current Artifacts

- Unsigned iPhone app: \`${device_app#$mobile_dir/}\`
- Unsigned IPA handoff package: \`${unsigned_ipa#$mobile_dir/}\`
- Manifest: \`${manifest#$mobile_dir/}\`
- OTA manifest template: \`${ota_manifest_template#$mobile_dir/}\`
- OTA install URL template: \`${ota_install_url_template#$mobile_dir/}\`
- Code signing log: \`build/ios-test/coolshow/codesign-device-app.txt\`
- Device probe: \`build/ios-test/coolshow/devices.json\`

The unsigned IPA is useful for signing handoff, but iOS will not install it on a
real iPhone until it is signed by an Apple Developer team and a provisioning
profile that includes \`$bundle_id\` and the target device.

## Direct iPhone Install

Connect and trust an iPhone, make sure Xcode is signed in to the Apple Developer
account, then run:

\`\`\`bash
cd mobile
IOS_DEVELOPMENT_TEAM=YOUR_TEAM_ID IOS_INSTALL_TO_DEVICE=1 ./scripts/build_coolshow_ios_test.sh
\`\`\`

Optional:

\`\`\`bash
IOS_DEVICE_ID=TARGET_DEVICE_UDID
IOS_SIGNED_CONFIGURATION=Debug
IOS_UNSIGNED_BUILD_MODE=release
\`\`\`

When the required signing material is present, the script builds the CoolShow
scheme with automatic signing, installs the signed app with \`devicectl\`, and
launches \`$bundle_id\` on the phone.

## OTA Install Preview After Signing

For HTTPS over-the-air preview distribution, sign the IPA first, upload the
signed IPA to an HTTPS URL, then replace \`HTTPS_URL_TO_SIGNED_IPA\` in:

\`\`\`text
${ota_manifest_template#$mobile_dir/}
\`\`\`

Upload that plist to HTTPS and open this URL on the iPhone:

\`\`\`text
itms-services://?action=download-manifest&url=HTTPS_URL_TO_OTA_MANIFEST_PLIST
\`\`\`

The OTA path still requires Apple signing and a provisioning profile that covers
the target device.

## Current Machine Result

- Signing identities found: $identity_count
- Provisioning profiles found: $profile_count
- Trusted iPhone count: $device_count
- Trusted iPhone device id: ${resolved_device_id:-none}
- Apple team configured: $([[ -n "$team_id" ]] && echo yes || echo no)
- Install ready: $install_ready
- Direct install status: $install_status
- Direct install blocker: $install_blocker

No signing material, provisioning profiles, tenant secrets, OAuth secrets,
payment secrets, or Cloudflare tokens are included in this directory.
EOF

echo "Wrote CoolShow iOS test package:"
echo "  $unsigned_ipa"
echo "  $manifest"
echo "Direct install status: $install_status"
if [[ "$install_status" != "installed" ]]; then
  echo "Direct install blocker: $install_blocker"
fi
