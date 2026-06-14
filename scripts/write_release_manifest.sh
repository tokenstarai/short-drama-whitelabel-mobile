#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"
output="${1:-$mobile_dir/build/release-manifests/mobile-artifacts.json}"

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

flavor_template() {
  case "$1" in
    hongguo) echo "hongguo_inspired" ;;
    douyin) echo "douyin_inspired" ;;
    hippo) echo "hippo_inspired" ;;
    reelshort) echo "reelshort_inspired" ;;
    *) echo "unknown" ;;
  esac
}

flavor_app_name() {
  case "$1" in
    hongguo) echo "GoldFruit Drama" ;;
    douyin) echo "Pulse Drama" ;;
    hippo) echo "River Drama" ;;
    reelshort) echo "Cliff Drama" ;;
    *) echo "Short Drama Whitelabel" ;;
  esac
}

flavor_application_id() {
  case "$1" in
    hongguo) echo "com.shortdrama.goldfruit" ;;
    douyin) echo "com.shortdrama.pulse" ;;
    hippo) echo "com.shortdrama.river" ;;
    reelshort) echo "com.shortdrama.cliff" ;;
    *) echo "com.dramahub.shortdrama.whitelabel" ;;
  esac
}

flavor_deep_link_scheme() {
  case "$1" in
    hongguo) echo "goldfruitdrama" ;;
    douyin) echo "pulsedrama" ;;
    hippo) echo "riverdrama" ;;
    reelshort) echo "cliffdrama" ;;
    *) echo "shortdrama" ;;
  esac
}

artifact_platform() {
  case "$1" in
    *.apk|*.aab) echo "android" ;;
    *.ipa) echo "ios" ;;
    *) echo "unknown" ;;
  esac
}

artifact_package_type() {
  case "$1" in
    *.apk) echo "apk" ;;
    *.aab) echo "appbundle" ;;
    *.ipa) echo "ipa" ;;
    *) echo "unknown" ;;
  esac
}

artifact_flavor_mode() {
  local file="$1"
  local base
  local stem
  local flavor="unknown"
  local mode="unknown"

  base="$(basename "$file")"
  base="${base%.*}"
  if [[ "$base" == app-* ]]; then
    stem="${base#app-}"
    mode="${stem##*-}"
    flavor="${stem%-$mode}"
  fi

  printf '%s %s\n' "$flavor" "$mode"
}

mkdir -p "$(dirname "$output")"

artifact_list="$(mktemp)"
temp_output="$(mktemp "$output.tmp.XXXXXX")"
cleanup() {
  rm -f "$artifact_list"
  rm -f "$temp_output"
}
trap cleanup EXIT

if [[ -d "$mobile_dir/build" ]]; then
  {
    if [[ -d "$mobile_dir/build/app/outputs/flutter-apk" ]]; then
      find "$mobile_dir/build/app/outputs/flutter-apk" -type f -name 'app-*.apk'
    fi
    if [[ -d "$mobile_dir/build/app/outputs/bundle" ]]; then
      find "$mobile_dir/build/app/outputs/bundle" -type f -name 'app-*.aab'
    fi
    if [[ -d "$mobile_dir/build/ios/ipa" ]]; then
      find "$mobile_dir/build/ios/ipa" -type f -name '*.ipa'
    fi
  } | sort > "$artifact_list"
else
  : > "$artifact_list"
fi

generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

{
  printf '{\n'
  printf '  "schemaVersion": 1,\n'
  printf '  "generatedAt": "%s",\n' "$(json_escape "$generated_at")"
  printf '  "secretBoundary": "Public build metadata only. Tenant secrets, OAuth secrets, payment secrets, Cloudflare tokens, Stream signing keys, webhook secrets, bank credentials, and crypto private keys stay in server-side configuration.",\n'
  printf '  "artifacts": [\n'

  first=true
  while IFS= read -r artifact; do
    [[ -n "$artifact" ]] || continue
    read -r flavor mode < <(artifact_flavor_mode "$artifact")
    platform="$(artifact_platform "$artifact")"
    package_type="$(artifact_package_type "$artifact")"
    relative_path="${artifact#"$mobile_dir/"}"
    sha256="$(shasum -a 256 "$artifact" | awk '{print $1}')"
    size_bytes="$(wc -c < "$artifact" | tr -d '[:space:]')"

    if [[ "$first" == true ]]; then
      first=false
    else
      printf ',\n'
    fi

    printf '    {\n'
    printf '      "flavor": "%s",\n' "$(json_escape "$flavor")"
    printf '      "styleTemplate": "%s",\n' "$(json_escape "$(flavor_template "$flavor")")"
    printf '      "platform": "%s",\n' "$(json_escape "$platform")"
    printf '      "mode": "%s",\n' "$(json_escape "$mode")"
    printf '      "packageType": "%s",\n' "$(json_escape "$package_type")"
    printf '      "appName": "%s",\n' "$(json_escape "$(flavor_app_name "$flavor")")"
    printf '      "applicationId": "%s",\n' "$(json_escape "$(flavor_application_id "$flavor")")"
    printf '      "deepLinkScheme": "%s",\n' "$(json_escape "$(flavor_deep_link_scheme "$flavor")")"
    printf '      "path": "%s",\n' "$(json_escape "$relative_path")"
    printf '      "sha256": "%s",\n' "$(json_escape "$sha256")"
    printf '      "sizeBytes": %s\n' "$size_bytes"
    printf '    }'
  done < "$artifact_list"

  printf '\n'
  printf '  ]\n'
  printf '}\n'
} > "$temp_output"

node -e 'JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));' "$temp_output"
mv "$temp_output" "$output"

echo "Wrote release manifest: ${output#"$mobile_dir/"}"
