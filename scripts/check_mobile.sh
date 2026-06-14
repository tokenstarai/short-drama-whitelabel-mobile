#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"

flutter_bin="$(bash "$script_dir/resolve_flutter_bin.sh")"

cd "$mobile_dir"

if grep -R -n -E "(TENANT_APP_SECRET|CLOUDFLARE_API_TOKEN|client_secret|clientSecret|stripe_secret|paypal_secret|private_key|secretCiphertext|secret_hash|manifestUrl)" lib assets; then
  echo "Mobile package contains forbidden secret or raw playback markers." >&2
  exit 1
fi

"$flutter_bin" pub get
"$script_dir/check_app_config.mjs"
python3 -m py_compile \
  "$script_dir/download_ios_ci_artifacts.py" \
  "$script_dir/export_completion_unblocker.py" \
  "$script_dir/export_github_publish_handoff.py" \
  "$script_dir/export_ios_ci_handoff.py" \
  "$script_dir/export_open_source_template.py" \
  "$script_dir/export_store_assets.py" \
  "$script_dir/export_store_publish_config.py" \
  "$script_dir/export_store_signing_handoff.py" \
  "$script_dir/import_ios_ci_artifacts.py" \
  "$script_dir/import_store_submission_evidence.py" \
  "$script_dir/mobile_completion_closure.py" \
  "$script_dir/mobile_completion_audit.py" \
  "$script_dir/mobile_completion_audit_test.py" \
  "$script_dir/scan_release_artifacts.py" \
  "$script_dir/write_store_handoff_manifest.py"
python3 "$script_dir/write_store_handoff_manifest.py"
python3 "$script_dir/export_ios_ci_handoff.py"
python3 "$script_dir/import_ios_ci_artifacts.py"
python3 "$script_dir/export_store_assets.py"
python3 "$script_dir/export_store_signing_handoff.py"
python3 "$script_dir/export_store_publish_config.py"
python3 "$script_dir/import_store_submission_evidence.py"
python3 "$script_dir/export_completion_unblocker.py"
python3 "$script_dir/export_open_source_template.py"
python3 "$script_dir/export_github_publish_handoff.py"
python3 "$script_dir/mobile_completion_audit_test.py"
"$flutter_bin" analyze
"$flutter_bin" test
"$script_dir/check_native_config.sh"
