#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"

fail() {
  echo "native config check failed: $*" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "missing file $1"
}

require_text() {
  local file="$1"
  local pattern="$2"
  grep -Fq "$pattern" "$file" || fail "missing '$pattern' in $file"
}

require_absent_text() {
  local file="$1"
  local pattern="$2"
  if grep -Fq "$pattern" "$file"; then
    fail "forbidden '$pattern' in $file"
  fi
}

require_png_size() {
  local file="$1"
  local expected_width="$2"
  local expected_height="$3"
  require_file "$file"
  python3 - "$file" "$expected_width" "$expected_height" <<'PY'
import struct
import sys

path, expected_width, expected_height = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
with open(path, "rb") as source:
    header = source.read(24)
if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
    raise SystemExit(f"{path} is not a PNG file")
width, height = struct.unpack(">II", header[16:24])
if (width, height) != (expected_width, expected_height):
    raise SystemExit(
        f"{path} is {width}x{height}, expected {expected_width}x{expected_height}"
    )
PY
}

require_android_launcher_icons() {
  local flavor="$1"
  require_png_size "$mobile_dir/android/app/src/$flavor/res/mipmap-mdpi/ic_launcher.png" 48 48
  require_png_size "$mobile_dir/android/app/src/$flavor/res/mipmap-hdpi/ic_launcher.png" 72 72
  require_png_size "$mobile_dir/android/app/src/$flavor/res/mipmap-xhdpi/ic_launcher.png" 96 96
  require_png_size "$mobile_dir/android/app/src/$flavor/res/mipmap-xxhdpi/ic_launcher.png" 144 144
  require_png_size "$mobile_dir/android/app/src/$flavor/res/mipmap-xxxhdpi/ic_launcher.png" 192 192
}

require_ios_launcher_icons() {
  local flavor="$1"
  local icon_set="$mobile_dir/ios/Runner/Assets.xcassets/AppIcon-$flavor.appiconset"
  require_file "$icon_set/Contents.json"
  require_png_size "$icon_set/Icon-App-1024x1024@1x.png" 1024 1024
  require_png_size "$icon_set/Icon-App-60x60@2x.png" 120 120
  require_png_size "$icon_set/Icon-App-60x60@3x.png" 180 180
  require_png_size "$icon_set/Icon-App-83.5x83.5@2x.png" 167 167
}

require_file "$mobile_dir/android/app/build.gradle.kts"
require_file "$mobile_dir/android/app/src/main/AndroidManifest.xml"
require_text "$mobile_dir/android/app/build.gradle.kts" 'flavorDimensions += "template"'
require_text "$mobile_dir/android/app/build.gradle.kts" 'create("coolshow")'
require_text "$mobile_dir/android/app/build.gradle.kts" 'create("hongguo")'
require_text "$mobile_dir/android/app/build.gradle.kts" 'create("douyin")'
require_text "$mobile_dir/android/app/build.gradle.kts" 'create("hippo")'
require_text "$mobile_dir/android/app/build.gradle.kts" 'create("reelshort")'
require_text "$mobile_dir/android/app/build.gradle.kts" 'manifestPlaceholders["appName"]'
require_text "$mobile_dir/android/app/build.gradle.kts" 'manifestPlaceholders["deepLinkScheme"]'
require_text "$mobile_dir/android/app/src/main/AndroidManifest.xml" 'android:label="${appName}"'
require_text "$mobile_dir/android/app/src/main/AndroidManifest.xml" 'android:scheme="${deepLinkScheme}"'
require_text "$mobile_dir/android/app/src/main/AndroidManifest.xml" 'android:host="auth"'
require_text "$mobile_dir/pubspec.yaml" 'app_links:'
require_text "$mobile_dir/pubspec.yaml" 'url_launcher:'
require_text "$mobile_dir/pubspec.yaml" 'video_player:'

require_file "$mobile_dir/ios/Flutter/WhitelabelDefaults.xcconfig"
require_file "$mobile_dir/ios/Podfile"
require_text "$mobile_dir/ios/Podfile" "flutter_ios_podfile_setup"
require_text "$mobile_dir/ios/Podfile" "flutter_install_all_ios_pods"
require_text "$mobile_dir/ios/Podfile" "flutter_additional_ios_build_settings"
require_text "$mobile_dir/ios/Flutter/Debug.xcconfig" "Pods-Runner.debug.xcconfig"
require_text "$mobile_dir/ios/Flutter/Release.xcconfig" "Pods-Runner.release.xcconfig"
require_file "$mobile_dir/ios/Flutter/Profile.xcconfig"
require_text "$mobile_dir/ios/Flutter/Profile.xcconfig" "Pods-Runner.profile.xcconfig"
require_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" "Profile.xcconfig"
require_text "$mobile_dir/ios/Flutter/WhitelabelDefaults.xcconfig" '#include "Coolshow.xcconfig"'
require_file "$mobile_dir/ios/Runner/Info.plist"
require_file "$mobile_dir/ios/Runner/PrivacyInfo.xcprivacy"
require_file "$mobile_dir/ios/Runner/Runner.entitlements"
require_text "$mobile_dir/ios/Runner/Info.plist" '$(APP_DISPLAY_NAME)'
require_text "$mobile_dir/ios/Runner/Info.plist" '$(APP_DEEP_LINK_SCHEME)'
require_text "$mobile_dir/ios/Runner/PrivacyInfo.xcprivacy" 'NSPrivacyTracking'
require_text "$mobile_dir/ios/Runner/PrivacyInfo.xcprivacy" 'NSPrivacyCollectedDataTypes'
require_text "$mobile_dir/ios/Runner/PrivacyInfo.xcprivacy" 'NSPrivacyAccessedAPITypes'
require_text "$mobile_dir/ios/Runner/Runner.entitlements" 'com.apple.developer.applesignin'
require_text "$mobile_dir/ios/Runner/Runner.entitlements" '<string>Default</string>'
require_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" 'PRODUCT_BUNDLE_IDENTIFIER = "$(APP_BUNDLE_IDENTIFIER)"'
require_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" 'PrivacyInfo.xcprivacy in Resources'
require_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" 'Runner.entitlements'
require_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" 'CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements'
require_absent_text "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" 'ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;'

validate_ios_flavor() {
  local flavor="$1"
  local config="$2"
  local display_name="$3"
  local bundle_id="$4"
  local deep_link_scheme="$5"
  local dart_define="$6"

  local file="$mobile_dir/ios/Flutter/$config.xcconfig"
  require_file "$file"
  require_text "$file" "APP_DISPLAY_NAME=$display_name"
  require_text "$file" "APP_BUNDLE_IDENTIFIER=$bundle_id"
  require_text "$file" "APP_DEEP_LINK_SCHEME=$deep_link_scheme"
  require_text "$file" "ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon-$flavor"
  require_text "$file" "DART_DEFINES=\$(inherited),$dart_define"
  require_android_launcher_icons "$flavor"
  require_ios_launcher_icons "$flavor"

  local scheme="$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/$flavor.xcscheme"
  require_file "$scheme"
  require_text "$scheme" 'BlueprintName = "Runner"'
  require_text "$scheme" 'BuildableName = "Runner.app"'
  require_text "$scheme" "Flutter/$config.xcconfig"
  require_text "$scheme" "APP_FLAVOR"
  require_text "$scheme" "value = \"$flavor\""
  require_text "$scheme" 'buildConfiguration = "Debug"'
  require_text "$scheme" 'buildConfiguration = "Profile"'
  require_text "$scheme" 'buildConfiguration = "Release"'
}

validate_ios_flavor "coolshow" "Coolshow" "CoolShow Short" "com.coolshow.short" "coolshowshort" "QVBQX0ZMQVZPUj1jb29sc2hvdw=="
validate_ios_flavor "hongguo" "Hongguo" "GoldFruit Drama" "com.shortdrama.goldfruit" "goldfruitdrama" "QVBQX0ZMQVZPUj1ob25nZ3Vv"
validate_ios_flavor "douyin" "Douyin" "Pulse Drama" "com.shortdrama.pulse" "pulsedrama" "QVBQX0ZMQVZPUj1kb3V5aW4="
validate_ios_flavor "hippo" "Hippo" "River Drama" "com.shortdrama.river" "riverdrama" "QVBQX0ZMQVZPUj1oaXBwbw=="
validate_ios_flavor "reelshort" "Reelshort" "Cliff Drama" "com.shortdrama.cliff" "cliffdrama" "QVBQX0ZMQVZPUj1yZWVsc2hvcnQ="

for file in \
  "$mobile_dir/android/app/build.gradle.kts" \
  "$mobile_dir/android/app/src/main/AndroidManifest.xml" \
  "$mobile_dir/ios/Runner/Info.plist" \
  "$mobile_dir/ios/Runner/PrivacyInfo.xcprivacy" \
  "$mobile_dir/ios/Runner/Runner.entitlements" \
  "$mobile_dir/ios/Runner.xcodeproj/project.pbxproj" \
  "$mobile_dir/ios/Flutter/Coolshow.xcconfig" \
  "$mobile_dir/ios/Flutter/Hongguo.xcconfig" \
  "$mobile_dir/ios/Flutter/Douyin.xcconfig" \
  "$mobile_dir/ios/Flutter/Hippo.xcconfig" \
  "$mobile_dir/ios/Flutter/Reelshort.xcconfig" \
  "$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/coolshow.xcscheme" \
  "$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/hongguo.xcscheme" \
  "$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/douyin.xcscheme" \
  "$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/hippo.xcscheme" \
  "$mobile_dir/ios/Runner.xcodeproj/xcshareddata/xcschemes/reelshort.xcscheme" \
  "$mobile_dir/ios/Podfile"; do
  require_absent_text "$file" "TENANT_APP_SECRET"
  require_absent_text "$file" "CLOUDFLARE_API_TOKEN"
  require_absent_text "$file" "client_secret"
  require_absent_text "$file" "stripe_secret"
  require_absent_text "$file" "paypal_secret"
  require_absent_text "$file" "private_key"
done

echo "Native Android/iOS flavor configuration is valid."
