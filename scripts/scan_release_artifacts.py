#!/usr/bin/env python3
"""Scan generated mobile release artifacts for forbidden secret markers."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


FORBIDDEN_MARKERS = [
    b"tenant_app_secret",
    b"cloudflare_api_token",
    b"client_secret",
    b"clientsecret",
    b"stripe_secret",
    b"paypal_secret",
    b"private_key",
    b"secretciphertext",
    b"secret_hash",
    b"sk_live_",
    b"sk_test_",
    b"rk_live_",
    b"whsec_",
    b"manifesturl",
]


def release_artifacts(root: Path) -> list[Path]:
    outputs = root / "build" / "app" / "outputs"
    if not outputs.exists():
        return []
    return sorted(outputs.glob("**/app-*-release.apk")) + sorted(
        outputs.glob("**/app-*-release.aab"),
    )


def scan_zip(artifact: Path) -> list[str]:
    hits: list[str] = []
    with zipfile.ZipFile(artifact) as package:
        for name in package.namelist():
            if name.endswith("/"):
                continue
            if is_known_runtime_entry(name):
                continue
            data = package.read(name).lower()
            for marker in FORBIDDEN_MARKERS:
                if marker in data:
                    hits.append(f"{name}: {marker.decode('ascii')}")
    return hits


def is_known_runtime_entry(name: str) -> bool:
    normalized = name.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    if filename == "libflutter.so":
        return True
    if normalized.startswith("BUNDLE-METADATA/com.android.tools.build.debugsymbols/"):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan release APK/AAB artifacts for secret markers.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=Path.cwd(),
        type=Path,
        help="mobile project root; defaults to the current directory",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    artifacts = release_artifacts(root)
    if not artifacts:
        print("release artifact scan failed: no release APK/AAB artifacts found", file=sys.stderr)
        return 2

    failed = False
    for artifact in artifacts:
        hits = scan_zip(artifact)
        relative = artifact.relative_to(root)
        if hits:
            failed = True
            print(f"{relative}: forbidden markers found", file=sys.stderr)
            for hit in hits:
                print(f"  {hit}", file=sys.stderr)
        else:
            print(f"{relative}: ok")

    if failed:
        return 1

    print(f"Release artifact secret scan passed for {len(artifacts)} artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
