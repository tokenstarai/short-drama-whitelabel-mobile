#!/usr/bin/env bash
set -euo pipefail

flutter_dir="${FLUTTER_DIR:-$HOME/.local/flutter}"
channel="${FLUTTER_CHANNEL:-stable}"

if [[ -x "$flutter_dir/bin/flutter" ]]; then
  echo "Flutter SDK already exists at $flutter_dir"
else
  mkdir -p "$(dirname "$flutter_dir")"
  git clone -b "$channel" https://github.com/flutter/flutter.git "$flutter_dir"
fi

export FLUTTER_SUPPRESS_ANALYTICS=true
"$flutter_dir/bin/flutter" --no-version-check --version

cat <<EOF

Flutter is ready.

Use:
  export PATH="$flutter_dir/bin:\$PATH"
  cd mobile
  flutter pub get
  flutter test
EOF
