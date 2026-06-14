#!/usr/bin/env python3
"""Export a no-secret GitHub publishing handoff for the mobile template."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "github-publish"
OPEN_SOURCE_PACKAGE = ROOT / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
OPEN_SOURCE_MANIFEST = ROOT / "build" / "open-source" / "open-source-template-manifest.json"
PACKAGE_NAME = "short-drama-whitelabel-mobile"
RELEASE_TAG = "mobile-template-v0.1.0"

FORBIDDEN_MARKERS = [
    "tenant_app_secret",
    "cloudflare_api_token",
    "cloudflare-api-token:",
    "bearer ey",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "sk_live_",
    "sk_test_",
    "whsec_",
    "-----begin private key-----",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def zip_entry_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            return len([name for name in archive.namelist() if not name.endswith("/")])
    except zipfile.BadZipFile:
        return None


def artifact_record(root: Path, path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": rel(root, path),
        "present": path.exists(),
    }
    if path.exists():
        record["sha256"] = sha256_file(path)
        record["sizeBytes"] = path.stat().st_size
    if path.suffix == ".zip":
        record["entryCount"] = zip_entry_count(path)
    return record


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return sorted({marker for marker in FORBIDDEN_MARKERS if marker in text})


def build_manifest(root: Path = ROOT) -> dict[str, Any]:
    package_path = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
    manifest_path = root / "build" / "open-source" / "open-source-template-manifest.json"
    open_source_manifest = read_json(manifest_path) or {}
    publish_commands = [
        "cd mobile && python3 scripts/export_open_source_template.py",
        "rm -rf /tmp/short-drama-whitelabel-mobile-publish && mkdir -p /tmp/short-drama-whitelabel-mobile-publish",
        "unzip -q mobile/build/open-source/short-drama-whitelabel-mobile.zip -d /tmp/short-drama-whitelabel-mobile-publish",
        "cd /tmp/short-drama-whitelabel-mobile-publish/short-drama-whitelabel-mobile && git init -b main",
        "cd /tmp/short-drama-whitelabel-mobile-publish/short-drama-whitelabel-mobile && git add . && git commit -m \"Publish Flutter short-drama white-label app template\"",
        "cd /tmp/short-drama-whitelabel-mobile-publish/short-drama-whitelabel-mobile && gh repo create <owner>/short-drama-whitelabel-mobile --public --source . --remote origin --push --description \"Flutter white-label short-drama app template\"",
        "cd <source-repo-root> && gh release create mobile-template-v0.1.0 mobile/build/open-source/short-drama-whitelabel-mobile.zip mobile/build/open-source/open-source-template-manifest.json --repo <owner>/short-drama-whitelabel-mobile --title \"Mobile template v0.1.0\" --notes-file mobile/build/github-publish/github-release-notes.md",
    ]
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "packageType": "mobile_github_publish_handoff",
        "generatedAt": utc_now(),
        "repositoryTemplate": {
            "name": PACKAGE_NAME,
            "visibility": "public",
            "publicByDefault": True,
            "license": "Apache-2.0",
            "defaultBranch": "main",
            "description": "Flutter white-label short-drama app template",
        },
        "sourcePackage": artifact_record(root, package_path),
        "sourceManifest": artifact_record(root, manifest_path),
        "openSourceManifestSummary": {
            "entryCount": open_source_manifest.get("entryCount"),
            "missingRequiredEntries": open_source_manifest.get("missingRequiredEntries"),
            "disallowedValueMarkerHits": open_source_manifest.get("disallowedValueMarkerHits"),
        },
        "publishCommands": publish_commands,
        "releaseTag": RELEASE_TAG,
        "releaseAssets": [
            rel(root, package_path),
            rel(root, manifest_path),
        ],
        "preflightChecks": [
            "Confirm the open-source manifest has no missing required entries.",
            "Confirm disallowedValueMarkerHits is empty before publishing.",
            "Review README, LICENSE, docs, generated screenshots, and sample tenant config before making the repository public.",
            "Do not publish tenant secrets, signing files, provider credentials, service-account JSON, webhook credentials, bank credentials, wallet keys, or Cloudflare credentials.",
        ],
        "secretBoundary": "Public GitHub publishing handoff only. It contains commands, package checksums, release notes, and no credentials.",
    }
    manifest["disallowedValueMarkerHits"] = marker_hits(manifest)
    return manifest


def guide_from_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "# GitHub Publish Handoff",
        "",
        f"Generated at: `{manifest['generatedAt']}`",
        "",
        f"- Repository: `<owner>/{manifest['repositoryTemplate']['name']}`",
        f"- Visibility: `{manifest['repositoryTemplate']['visibility']}`",
        f"- License: `{manifest['repositoryTemplate']['license']}`",
        f"- Release tag: `{manifest['releaseTag']}`",
        "",
        "## Preflight",
        "",
    ]
    lines.extend(f"- {item}" for item in manifest["preflightChecks"])
    lines.extend(["", "## Commands", ""])
    lines.extend(f"```bash\n{command}\n```" for command in manifest["publishCommands"])
    lines.extend([
        "",
        "## Artifacts",
        "",
        f"- `{manifest['sourcePackage']['path']}`",
        f"- `{manifest['sourceManifest']['path']}`",
        "",
        manifest["secretBoundary"],
    ])
    return "\n".join(lines).rstrip() + "\n"


def release_notes_from_manifest(manifest: dict[str, Any]) -> str:
    return "\n".join([
        "# Mobile template v0.1.0",
        "",
        "Apache-2.0 Flutter white-label short-drama app template: short-drama-whitelabel-mobile.",
        "",
        "Included:",
        "",
        "- Four style templates: hongguo, douyin, hippo, and reelshort inspired layouts.",
        "- Tenant Edge-only API boundary with no tenant secrets in Flutter.",
        "- Store-compliance gates for App Store, Play Store, Android direct, and regional user-choice modes.",
        "- Publish-safe prototype screenshots, native Android/iOS scaffolding, and CI workflow metadata.",
        "",
        "Before store submission, tenants must replace branding, configure signing outside Git, configure provider secrets server-side, and import public store-submission evidence.",
    ]).rstrip() + "\n"


def export_handoff(root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    output = output_dir or root / "build" / "github-publish"
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root)
    manifest_path = output / "github-publish-manifest.json"
    guide_path = output / "github-publish-guide.md"
    notes_path = output / "github-release-notes.md"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    guide_path.write_text(guide_from_manifest(manifest), encoding="utf-8")
    notes_path.write_text(release_notes_from_manifest(manifest), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else root / "build" / "github-publish"
    manifest = export_handoff(root, output_dir)
    print(f"Wrote GitHub publish handoff manifest: {rel(root, output_dir / 'github-publish-manifest.json')}")
    print(f"Wrote GitHub publish handoff guide: {rel(root, output_dir / 'github-publish-guide.md')}")
    print(f"Wrote GitHub release notes: {rel(root, output_dir / 'github-release-notes.md')}")
    if manifest["disallowedValueMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(manifest['disallowedValueMarkerHits'])}")
    return 1 if manifest["disallowedValueMarkerHits"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
