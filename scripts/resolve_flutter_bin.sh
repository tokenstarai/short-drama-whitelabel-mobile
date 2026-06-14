#!/usr/bin/env bash
set -euo pipefail

flutter_bin="${FLUTTER_BIN:-}"

if [[ -z "$flutter_bin" ]]; then
  if command -v flutter >/dev/null 2>&1; then
    flutter_bin="flutter"
  elif [[ -x "/tmp/flutter/bin/flutter" ]]; then
    flutter_bin="/tmp/flutter/bin/flutter"
  elif [[ -x "$HOME/.local/flutter/bin/flutter" ]]; then
    flutter_bin="$HOME/.local/flutter/bin/flutter"
  else
    echo "Flutter SDK not found. Run mobile/scripts/bootstrap_flutter.sh or set FLUTTER_BIN." >&2
    exit 127
  fi
fi

if [[ "$flutter_bin" != */* ]]; then
  command -v "$flutter_bin"
else
  echo "$(cd "$(dirname "$flutter_bin")" && pwd)/$(basename "$flutter_bin")"
fi
