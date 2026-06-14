#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$script_dir/.." && pwd)"

flutter_bin="$(bash "$script_dir/resolve_flutter_bin.sh")"

cd "$mobile_dir"
"$flutter_bin" test --update-goldens tool/prototype_goldens_test.dart
