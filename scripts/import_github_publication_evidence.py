#!/usr/bin/env python3
"""Import public GitHub repository/release evidence for the mobile template."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import export_github_publish_handoff


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "tokenstarai/short-drama-whitelabel-mobile"
DEFAULT_TAG = "mobile-template-v0.1.0"
DEFAULT_OUTPUT = ROOT / "build" / "github-publish" / "github-publication-evidence.json"
OPEN_SOURCE_PACKAGE = ROOT / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
OPEN_SOURCE_MANIFEST = ROOT / "build" / "open-source" / "open-source-template-manifest.json"


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


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout.strip())
    return json.loads(completed.stdout)


def asset_download_url(asset: dict[str, Any]) -> str:
    for key in ["url", "browserDownloadUrl", "downloadUrl"]:
        value = asset.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def asset_size(asset: dict[str, Any]) -> int:
    for key in ["size", "sizeBytes"]:
        value = asset.get(key)
        if isinstance(value, int):
            return value
    return 0


def default_branch(repo_info: dict[str, Any]) -> tuple[str, str | None]:
    branch = repo_info.get("defaultBranchRef")
    if isinstance(branch, dict):
        target = branch.get("target")
        oid = target.get("oid") if isinstance(target, dict) else None
        return str(branch.get("name") or ""), str(oid) if oid else None
    return "", None


def build_report(
    *,
    root: Path,
    repo_info: dict[str, Any],
    release_info: dict[str, Any],
) -> dict[str, Any]:
    branch_name, branch_oid = default_branch(repo_info)
    package_path = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
    manifest_path = root / "build" / "open-source" / "open-source-template-manifest.json"
    assets = [
        {
            "name": str(asset.get("name") or ""),
            "contentType": str(asset.get("contentType") or ""),
            "sizeBytes": asset_size(asset),
            "downloadUrl": asset_download_url(asset),
        }
        for asset in release_info.get("assets", [])
        if isinstance(asset, dict)
    ]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "passed",
        "repository": {
            "nameWithOwner": repo_info.get("nameWithOwner"),
            "url": repo_info.get("url"),
            "visibility": repo_info.get("visibility"),
            "defaultBranch": branch_name,
            "pushedCommit": branch_oid,
        },
        "release": {
            "tagName": release_info.get("tagName"),
            "url": release_info.get("url"),
            "isDraft": release_info.get("isDraft"),
            "isPrerelease": release_info.get("isPrerelease"),
        },
        "assets": assets,
        "sourcePackagePath": rel(root, package_path),
        "sourceManifestPath": rel(root, manifest_path),
        "sourcePackageSha256": sha256_file(package_path) if package_path.exists() else None,
        "sourceManifestSha256": sha256_file(manifest_path) if manifest_path.exists() else None,
        "secretBoundary": "Public GitHub repository and release metadata only; no credentials or signing material.",
    }
    problems: list[str] = []
    if report["repository"]["visibility"] not in {"PUBLIC", "public"}:
        problems.append("repository.visibility")
    if report["release"]["tagName"] != DEFAULT_TAG:
        problems.append("release.tagName")
    asset_names = {asset["name"] for asset in assets}
    for name in ["short-drama-whitelabel-mobile.zip", "open-source-template-manifest.json"]:
        if name not in asset_names:
            problems.append(f"asset:{name}")
    marker_hits = export_github_publish_handoff.marker_hits(report)
    report["disallowedValueMarkerHits"] = marker_hits
    if problems or marker_hits:
        report["result"] = "blocked"
        report["blockers"] = problems + [f"forbidden:{marker}" for marker in marker_hits]
    return report


def fetch_report(root: Path, repo: str, tag: str) -> dict[str, Any]:
    repo_info = run_json([
        "gh",
        "repo",
        "view",
        repo,
        "--json",
        "nameWithOwner,url,visibility,defaultBranchRef",
    ])
    release_info = run_json([
        "gh",
        "release",
        "view",
        tag,
        "--repo",
        repo,
        "--json",
        "tagName,url,isDraft,isPrerelease,assets",
    ])
    return build_report(root=root, repo_info=repo_info, release_info=release_info)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    report = fetch_report(root, args.repo, args.tag)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote GitHub publication evidence: {rel(root, output)}")
    print(f"Result: {report['result']}")
    if report.get("blockers"):
        print(f"Blockers: {', '.join(report['blockers'])}")
    return 1 if args.strict and report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
