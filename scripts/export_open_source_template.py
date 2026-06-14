#!/usr/bin/env python3
"""Export a GitHub-ready open-source mobile template zip and manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
PACKAGE_NAME = "short-drama-whitelabel-mobile"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "open-source"

REQUIRED_ENTRIES = [
    ".github/workflows/mobile-flutter.yml",
    "LICENSE",
    "README.md",
    "docs/open-source-release.md",
    "pubspec.yaml",
    "lib/main.dart",
    "scripts/export_github_publish_handoff.py",
    "scripts/import_github_publication_evidence.py",
    "assets/config/hongguo/tenant.brand.json",
    "assets/config/douyin/tenant.brand.json",
    "assets/config/hippo/tenant.brand.json",
    "assets/config/reelshort/tenant.brand.json",
    "android/app/build.gradle.kts",
    "ios/Runner/Info.plist",
    "ios/Runner/PrivacyInfo.xcprivacy",
    "ios/Runner/Runner.entitlements",
]

EXCLUDED_PARTS = {
    ".dart_tool",
    ".gradle",
    ".pub",
    ".pub-cache",
    ".symlinks",
    ".vscode",
    "build",
    "coverage",
    "DerivedData",
    "ephemeral",
    "Pods",
    "xcuserdata",
    "__pycache__",
}

EXCLUDED_NAMES = {
    ".flutter-plugins",
    ".flutter-plugins-dependencies",
    ".metadata",
    "Generated.xcconfig",
    "GeneratedPluginRegistrant.h",
    "GeneratedPluginRegistrant.java",
    "GeneratedPluginRegistrant.m",
    "flutter_export_environment.sh",
    "local.properties",
    "key.properties",
    "ServiceDefinitions.json",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".keystore",
    ".jks",
    ".log",
    ".tsbuildinfo",
    ".xcuserstate",
}

DISALLOWED_VALUE_PATTERNS = [
    re.compile(r"cloudflare[_-]?api[_-]?token\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"bearer\s+ey[A-Za-z0-9_-]{12,}", re.IGNORECASE),
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{12,}", re.IGNORECASE),
    re.compile(
        r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]{64,}-----END (?:RSA |EC )?PRIVATE KEY-----",
        re.IGNORECASE,
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_PARTS:
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    if path.name.startswith(".env"):
        return True
    return any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def iter_mobile_files() -> Iterable[tuple[str, Path]]:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if should_exclude(relative):
            continue
        yield relative.as_posix(), path


def iter_entries() -> list[tuple[str, Path]]:
    entries = [(".github/workflows/mobile-flutter.yml", REPO_ROOT / ".github" / "workflows" / "mobile-flutter.yml")]
    entries.extend(iter_mobile_files())
    deduped: dict[str, Path] = {}
    for entry_path, source_path in entries:
        if source_path.exists() and source_path.is_file():
            deduped[entry_path] = source_path
    return sorted(deduped.items())


def standalone_workflow_text(text: str) -> str:
    return (
        text.replace('      - "mobile/**"', '      - "**"')
        .replace("working-directory: mobile", "working-directory: .")
        .replace("mobile/build/", "build/")
    )


def packaged_bytes(entry_path: str, source_path: Path) -> bytes:
    if entry_path == ".github/workflows/mobile-flutter.yml":
        text = source_path.read_text(encoding="utf-8")
        return standalone_workflow_text(text).encode("utf-8")
    return source_path.read_bytes()


def disallowed_value_hits(entries: list[tuple[str, Path]]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for entry_path, source_path in entries:
        try:
            text = packaged_bytes(entry_path, source_path).decode("utf-8", errors="ignore")
        except OSError:
            continue
        if source_path.name in {
            "export_completion_unblocker.py",
            "export_github_publish_handoff.py",
            "export_ios_ci_handoff.py",
            "export_open_source_template.py",
            "export_store_assets.py",
            "export_store_publish_config.py",
            "export_store_signing_handoff.py",
            "import_github_publication_evidence.py",
            "import_ios_ci_artifacts.py",
            "import_store_submission_evidence.py",
            "mobile_completion_closure.py",
            "mobile_completion_audit.py",
        }:
            text = "\n".join(
                line
                for line in text.splitlines()
                if not (
                    "re.compile(" in line
                    or "cloudflare_api_token" in line
                    or "cloudflare-api-token" in line
                    or "BEGIN PRIVATE KEY" in line
                    or "END PRIVATE KEY" in line
                    or "sk_live_" in line
                    or "sk_test_" in line
                )
            )
        for pattern in DISALLOWED_VALUE_PATTERNS:
            if pattern.search(text):
                hits.append({"path": entry_path, "pattern": pattern.pattern})
                break
    return hits


def write_package(entries: list[tuple[str, Path]], package_path: Path) -> None:
    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry_path, source_path in entries:
            info = zipfile.ZipInfo(f"{PACKAGE_NAME}/{entry_path}")
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, packaged_bytes(entry_path, source_path))


def build_manifest(entries: list[tuple[str, Path]], package_path: Path) -> dict[str, object]:
    entry_records = [
        {
            "path": entry_path,
            "sizeBytes": len(packaged_bytes(entry_path, source_path)),
            "sha256": sha256_bytes(packaged_bytes(entry_path, source_path)),
        }
        for entry_path, source_path in entries
    ]
    entry_paths = {record["path"] for record in entry_records}
    return {
        "schemaVersion": 1,
        "packageName": PACKAGE_NAME,
        "generatedAt": utc_now(),
        "packagePath": package_path.relative_to(ROOT).as_posix(),
        "packageSha256": sha256_file(package_path),
        "packageSizeBytes": package_path.stat().st_size,
        "entryCount": len(entry_records),
        "missingRequiredEntries": [
            entry
            for entry in REQUIRED_ENTRIES
            if entry not in entry_paths
        ],
        "disallowedValueMarkerHits": disallowed_value_hits(entries),
        "excludedBoundary": {
            "buildOutputs": True,
            "localFlutterGeneratedFiles": True,
            "cocoapods": True,
            "androidLocalProperties": True,
            "signingMaterial": True,
            "envFiles": True,
        },
        "entries": entry_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="output directory; defaults to build/open-source",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    package_path = output_dir / f"{PACKAGE_NAME}.zip"
    manifest_path = output_dir / "open-source-template-manifest.json"
    entries = iter_entries()
    write_package(entries, package_path)
    manifest = build_manifest(entries, package_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote open-source template package: {package_path.relative_to(ROOT)}")
    print(f"Wrote open-source template manifest: {manifest_path.relative_to(ROOT)}")
    print(f"Entries: {manifest['entryCount']}")
    if manifest["missingRequiredEntries"]:
        print(f"Missing required entries: {', '.join(manifest['missingRequiredEntries'])}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {json.dumps(manifest['disallowedValueMarkerHits'], ensure_ascii=False)}")
    return 1 if manifest["missingRequiredEntries"] or manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
