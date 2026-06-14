#!/usr/bin/env bash
set -euo pipefail

flavor="${1:-hongguo}"
platform="${2:-android}"
mode="${3:-debug}"
package_type="${4:-apk}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"

flutter_bin="$(bash "$script_dir/resolve_flutter_bin.sh")"
flutter_sdk_dir="$(cd "$(dirname "$flutter_bin")/.." && pwd)"

require_ios_toolchain() {
  if ! xcodebuild -version >/dev/null 2>&1; then
    developer_dir="$(xcode-select -p 2>/dev/null || echo "unavailable")"
    cat >&2 <<EOF
iOS build requires a full Xcode installation selected with xcode-select.
Current developer directory: $developer_dir
Install Xcode, then run:
  sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
  sudo xcodebuild -runFirstLaunch
EOF
    exit 4
  fi

  if ! command -v pod >/dev/null 2>&1; then
    cat >&2 <<EOF
iOS build requires CocoaPods because this template includes Flutter plugins.
Install it before building iOS:
  sudo gem install cocoapods
EOF
    exit 4
  fi
}

if [[ "$platform" == "android" ]]; then
  if [[ "${SHORT_DRAMA_KEEP_JAVA_HOME:-}" != "1" ]]; then
    for java_candidate in \
      "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home" \
      "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" \
      "/usr/local/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home" \
      "/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" \
      "/Applications/Android Studio.app/Contents/jbr/Contents/Home"; do
      if [[ -x "$java_candidate/bin/java" ]]; then
        export JAVA_HOME="$java_candidate"
        export PATH="$JAVA_HOME/bin:$PATH"
        break
      fi
    done
  fi

  android_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
  if [[ -z "$android_sdk" && -d /opt/homebrew/share/android-commandlinetools ]]; then
    android_sdk="/opt/homebrew/share/android-commandlinetools"
  fi
  if [[ -n "$android_sdk" ]]; then
    mkdir -p "$mobile_dir/android"
    {
      echo "sdk.dir=$android_sdk"
      echo "flutter.sdk=$flutter_sdk_dir"
      echo "flutter.buildMode=$mode"
      echo "flutter.versionName=0.1.0"
      echo "flutter.versionCode=1"
    } > "$mobile_dir/android/local.properties"
  fi
fi

case "$flavor" in
  hongguo|douyin|hippo|reelshort) ;;
  *)
    echo "Unknown flavor: $flavor" >&2
    echo "Use one of: hongguo, douyin, hippo, reelshort" >&2
    exit 2
    ;;
esac

case "$mode" in
  debug|profile|release) ;;
  *)
    echo "Unknown build mode: $mode" >&2
    echo "Use one of: debug, profile, release" >&2
    exit 2
    ;;
esac

case "$platform" in
  android)
    case "$package_type" in
      apk)
        (cd "$mobile_dir" && "$flutter_bin" build apk "--$mode" --flavor "$flavor" --dart-define="APP_FLAVOR=$flavor")
        ;;
      appbundle|aab)
        if [[ "$mode" == "debug" ]]; then
          echo "Android app bundles are only supported for profile/release builds." >&2
          exit 2
        fi
        (cd "$mobile_dir" && "$flutter_bin" build appbundle "--$mode" --flavor "$flavor" --dart-define="APP_FLAVOR=$flavor")
        ;;
      *)
        echo "Unknown Android package type: $package_type" >&2
        echo "Use one of: apk, appbundle" >&2
        exit 2
        ;;
    esac
    ;;
  ios)
    if [[ "$package_type" != "apk" ]]; then
      echo "Package type is Android-only. Omit the fourth argument for iOS builds." >&2
      exit 2
    fi
    require_ios_toolchain
    ios_config="$mobile_dir/ios/Flutter/WhitelabelDefaults.xcconfig"
    case "$flavor" in
      hongguo) source_config="$mobile_dir/ios/Flutter/Hongguo.xcconfig" ;;
      douyin) source_config="$mobile_dir/ios/Flutter/Douyin.xcconfig" ;;
      hippo) source_config="$mobile_dir/ios/Flutter/Hippo.xcconfig" ;;
      reelshort) source_config="$mobile_dir/ios/Flutter/Reelshort.xcconfig" ;;
    esac
    if [[ ! -f "$source_config" ]]; then
      echo "Missing iOS config: $source_config" >&2
      exit 3
    fi
    backup="$(mktemp)"
    cp "$ios_config" "$backup"
    restore() {
      cp "$backup" "$ios_config"
      rm -f "$backup"
    }
    trap restore EXIT
    cp "$source_config" "$ios_config"
    (cd "$mobile_dir" && "$flutter_bin" build ios "--$mode" --flavor "$flavor" --no-codesign --dart-define="APP_FLAVOR=$flavor")
    ;;
  *)
    echo "Unknown platform: $platform" >&2
    echo "Use one of: android, ios" >&2
    exit 2
    ;;
esac
