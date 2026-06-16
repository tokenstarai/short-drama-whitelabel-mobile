#!/usr/bin/env python3
"""Download unsigned iOS CI artifacts and import completion evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "build" / "ci-ios"
DEFAULT_IMPORT_OUTPUT = ROOT / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
DEFAULT_WORKFLOW = "mobile-flutter.yml"
FLAVOR_ORDER = ["coolshow", "hongguo", "douyin", "hippo", "reelshort"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_repo_slug(remote_url: str) -> str | None:
    value = remote_url.strip()
    patterns = [
        r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", value):
        return value
    return None


def resolve_repo(explicit_repo: str | None, *, required: bool = True) -> str | None:
    for candidate in [
        explicit_repo,
        os.environ.get("GH_REPO"),
        os.environ.get("GITHUB_REPOSITORY"),
    ]:
        if not candidate:
            continue
        repo = parse_repo_slug(candidate)
        if repo:
            return repo
    try:
        remote_url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        remote_url = ""
    repo = parse_repo_slug(remote_url)
    if repo:
        return repo
    if required:
        raise SystemExit(
            "GitHub repo is unavailable. Set --repo owner/name, GH_REPO, GITHUB_REPOSITORY, or configure git remote origin."
        )
    return None


def select_latest_successful_run_id(runs: list[dict[str, Any]]) -> str:
    for run_info in runs:
        if (
            str(run_info.get("status")) == "completed"
            and str(run_info.get("conclusion")) == "success"
            and run_info.get("databaseId") is not None
        ):
            return str(run_info["databaseId"])
    raise SystemExit("No successful completed mobile-flutter.yml GitHub Actions run was found.")


def latest_successful_run_id(
    *,
    repo: str,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str | None = None,
) -> str:
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--limit",
        "20",
        "--json",
        "databaseId,status,conclusion,headBranch,createdAt",
    ]
    if branch:
        command.extend(["--branch", branch])
    output = subprocess.check_output(command, cwd=ROOT, text=True)
    runs = json.loads(output)
    if not isinstance(runs, list):
        raise SystemExit("GitHub run list returned an unexpected response.")
    return select_latest_successful_run_id(runs)


def command_text(command: list[str]) -> str:
    return " ".join(command)


def artifact_name(flavor: str) -> str:
    return f"mobile-{flavor}-ios-unsigned"


def download_command(repo: str, run_id: str, flavor: str, source_dir: Path) -> list[str]:
    return [
        "gh",
        "run",
        "download",
        run_id,
        "--repo",
        repo,
        "-n",
        artifact_name(flavor),
        "-D",
        str(source_dir / flavor),
    ]


def prepare_download_destination(source_dir: Path, flavor: str) -> Path:
    destination = source_dir / flavor
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def import_command(source_dir: Path, import_output: Path) -> list[str]:
    return [
        "python3",
        "scripts/import_ios_ci_artifacts.py",
        "--strict",
        "--source-dir",
        str(source_dir),
        "--output",
        str(import_output),
    ]


def build_plan_report(
    *,
    repo: str,
    run_id: str,
    source_dir: Path,
    import_output: Path,
) -> dict[str, Any]:
    download_steps = [
        {
            "flavor": flavor,
            "artifactName": artifact_name(flavor),
            "destination": str(source_dir / flavor),
            "command": command_text(download_command(repo, run_id, flavor, source_dir)),
        }
        for flavor in FLAVOR_ORDER
    ]
    import_step_command = import_command(source_dir, import_output)
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "mode": "dry_run",
        "repo": repo,
        "workflow": DEFAULT_WORKFLOW,
        "runId": run_id,
        "sourceDir": str(source_dir),
        "importOutput": str(import_output),
        "downloadSteps": download_steps,
        "importStep": {
            "command": command_text(import_step_command),
            "output": str(import_output),
        },
        "secretBoundary": "Uses GitHub CLI authentication only. No Apple signing material, tenant secrets, OAuth secrets, payment secrets, or Cloudflare tokens are read or written.",
    }


def run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository in owner/name form.")
    parser.add_argument(
        "--run-id",
        help="GitHub Actions run id to download from. If omitted, the latest successful workflow run is used.",
    )
    parser.add_argument(
        "--branch",
        help="Optional branch filter when resolving the latest successful workflow run.",
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--import-output", type=Path, default=DEFAULT_IMPORT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true", help="Print the command plan without running gh.")
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    if repo is None:
        raise SystemExit(
            "GitHub repo is unavailable. Set --repo owner/name, GH_REPO, GITHUB_REPOSITORY, or configure git remote origin."
        )
    source_dir = args.source_dir.resolve()
    import_output = args.import_output.resolve()
    run_id = args.run_id or latest_successful_run_id(
        repo=repo,
        workflow=DEFAULT_WORKFLOW,
        branch=args.branch,
    )
    report = build_plan_report(
        repo=repo,
        run_id=run_id,
        source_dir=source_dir,
        import_output=import_output,
    )
    if args.dry_run:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    source_dir.mkdir(parents=True, exist_ok=True)
    for flavor in FLAVOR_ORDER:
        prepare_download_destination(source_dir, flavor)
        run(download_command(repo, run_id, flavor, source_dir), cwd=ROOT)
    run(import_command(source_dir, import_output), cwd=ROOT)
    print(f"Imported iOS CI artifact evidence: {import_output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
