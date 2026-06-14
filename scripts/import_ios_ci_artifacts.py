#!/usr/bin/env python3
"""Import downloaded unsigned iOS CI artifacts into public audit evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "build" / "ci-ios"
DEFAULT_OUTPUT = ROOT / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
DEFAULT_INFO_DIR = ROOT / "build" / "ios-ci-evidence" / "app-info"

FLAVORS = {
    "hongguo": {
        "applicationId": "com.shortdrama.goldfruit",
        "appName": "GoldFruit Drama",
        "artifactName": "mobile-hongguo-ios-unsigned",
    },
    "douyin": {
        "applicationId": "com.shortdrama.pulse",
        "appName": "Pulse Drama",
        "artifactName": "mobile-douyin-ios-unsigned",
    },
    "hippo": {
        "applicationId": "com.shortdrama.river",
        "appName": "River Drama",
        "artifactName": "mobile-hippo-ios-unsigned",
    },
    "reelshort": {
        "applicationId": "com.shortdrama.cliff",
        "appName": "Cliff Drama",
        "artifactName": "mobile-reelshort-ios-unsigned",
    },
}

FORBIDDEN_MARKERS = [
    "tenant_app_secret",
    "cloudflare_api_token",
    "client_secret",
    "stripe_secret",
    "paypal_secret",
    "private_key",
    "sk_live_",
    "sk_test_",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_size(path: Path) -> int:
    return sum(file_path.stat().st_size for file_path in path.rglob("*") if file_path.is_file())


def marker_hits(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in text]


def candidate_app_paths(source_dir: Path, flavor: str) -> list[Path]:
    expected = FLAVORS[flavor]
    candidates = [
        source_dir / flavor / "Runner.app",
        source_dir / expected["artifactName"] / "Runner.app",
        source_dir / flavor / "Payload" / "Runner.app",
        source_dir / expected["artifactName"] / "Payload" / "Runner.app",
    ]
    candidates.extend(path for path in source_dir.rglob("Runner.app") if path.is_dir())
    deduped: dict[str, Path] = {}
    for path in candidates:
        deduped[str(path.resolve())] = path
    return list(deduped.values())


def read_app_info(app_path: Path, flavor: str, info_dir: Path) -> dict[str, Any] | None:
    expected = FLAVORS[flavor]
    plist_path = app_path / "Info.plist"
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as source:
            plist = plistlib.load(source)
    except (plistlib.InvalidFileException, OSError):
        return None
    bundle_identifier = plist.get("CFBundleIdentifier")
    display_name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName")
    if bundle_identifier != expected["applicationId"] or display_name != expected["appName"]:
        return None
    info = {
        "flavor": flavor,
        "platform": "ios",
        "source": "github_actions_unsigned_artifact",
        "artifactName": expected["artifactName"],
        "appPath": str(app_path.relative_to(ROOT)),
        "infoPlistPresent": True,
        "bundleIdentifier": bundle_identifier,
        "displayName": display_name,
        "bundleVersion": plist.get("CFBundleVersion"),
        "shortVersionString": plist.get("CFBundleShortVersionString"),
        "appSizeBytes": dir_size(app_path),
    }
    info_dir.mkdir(parents=True, exist_ok=True)
    info_path = info_dir / f"{flavor}-ci-info.json"
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    info["infoSnapshotPath"] = str(info_path.relative_to(ROOT))
    info["infoSnapshotSha256"] = sha256_file(info_path)
    return info


def import_artifacts(source_dir: Path, output: Path, info_dir: Path) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    missing: list[str] = []
    for flavor in FLAVORS:
        info = None
        for app_path in candidate_app_paths(source_dir, flavor):
            if app_path.exists() and app_path.is_dir():
                info = read_app_info(app_path, flavor, info_dir)
                if info is not None:
                    break
        if info is None:
            missing.append(flavor)
            continue
        runs.append({
            "flavor": flavor,
            "applicationId": FLAVORS[flavor]["applicationId"],
            "appName": FLAVORS[flavor]["appName"],
            "artifactName": FLAVORS[flavor]["artifactName"],
            "importResult": "passed",
            "app": info,
        })
    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "sourceDir": str(source_dir.relative_to(ROOT)) if source_dir.is_relative_to(ROOT) else str(source_dir),
        "requiredFlavors": list(FLAVORS),
        "runs": runs,
        "missingFlavors": missing,
        "secretBoundary": "Public unsigned iOS CI artifact metadata only. No Apple signing material, provisioning profiles, tenant secrets, OAuth secrets, payment secrets, or Cloudflare tokens are included.",
    }
    report["forbiddenMarkerHits"] = marker_hits(report)
    report["result"] = "passed" if not missing and not report["forbiddenMarkerHits"] else "blocked"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--info-dir", type=Path, default=DEFAULT_INFO_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = import_artifacts(args.source_dir.resolve(), args.output.resolve(), args.info_dir.resolve())
    print(f"Wrote iOS CI artifact evidence: {args.output.relative_to(ROOT)}")
    print(f"Result: {report['result']}")
    if report["missingFlavors"]:
        print(f"Missing flavors: {', '.join(report['missingFlavors'])}")
    if report["forbiddenMarkerHits"]:
        print(f"Disallowed marker hits: {', '.join(report['forbiddenMarkerHits'])}")
    return 1 if args.strict and report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
