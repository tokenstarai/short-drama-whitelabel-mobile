#!/usr/bin/env python3
"""Refresh mobile app completion evidence and summarize remaining blockers."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import download_ios_ci_artifacts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "build" / "completion-closure" / "mobile-completion-closure.json"
DEFAULT_MARKDOWN = ROOT / "build" / "completion-closure" / "mobile-completion-closure.md"
AUDIT_PATH = ROOT / "build" / "completion-audits" / "mobile-app-completion.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_step(command: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "command": " ".join(command),
        "cwd": str(cwd),
        "exitCode": completed.returncode,
        "outputTail": completed.stdout.strip().splitlines()[-40:],
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def checks_by_id(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(check.get("id")): check
        for check in audit.get("checks", [])
        if isinstance(check, dict)
    }


def next_action(check_id: str, check: dict[str, Any]) -> str:
    if check_id == "ios_build_environment":
        return "Install full Xcode, select it with sudo xcode-select -s /Applications/Xcode.app/Contents/Developer, then rerun scripts/ios_build_matrix.py all."
    if check_id == "ios_build_matrix":
        return "Run scripts/ios_build_matrix.py all on a full-Xcode machine and keep build/ios-build-matrix/ios-build-matrix.json as public evidence."
    if check_id == "ios_ci_artifact_evidence":
        return "Run scripts/mobile_completion_closure.py after a successful mobile-flutter.yml Actions run; set --repo <owner/repo> if GH_REPO, GITHUB_REPOSITORY, or git origin cannot identify the repository."
    if check_id == "store_submission_evidence":
        return "Copy build/store-submission-evidence/store-submission-evidence.template.json to store-submission-evidence.input.json, fill public TestFlight/Play/direct status fields for every flavor, then rerun scripts/import_store_submission_evidence.py --strict."
    return f"Resolve {check_id}: {check.get('detail', 'no detail')}"


def blocker_summary(audit: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for check_id, check in checks_by_id(audit).items():
        if check.get("status") != "blocked":
            continue
        blockers.append({
            "id": check_id,
            "detail": check.get("detail"),
            "evidence": check.get("evidence", []),
            "nextAction": next_action(check_id, check),
        })
    return blockers


def write_markdown(report: dict[str, Any], path: Path) -> None:
    blockers = report.get("blockers", [])
    lines = [
        "# Mobile Completion Closure",
        "",
        f"- Generated at: `{report['generatedAt']}`",
        f"- Completion: `{report['appCompletion']}`",
        f"- Summary: {report['summary']['passed']}/{report['summary']['missing']}/{report['summary']['failed']}/{report['summary']['blocked']}",
        f"- Can claim complete: `{report['canClaimComplete']}`",
        "",
        "## Steps",
        "",
    ]
    for step in report.get("steps", []):
        lines.append(f"- `{step['command']}` -> `{step['exitCode']}`")
    lines.extend(["", "## Blockers", ""])
    if not blockers:
        lines.append("- None")
    else:
        for blocker in blockers:
            lines.extend([
                f"### {blocker['id']}",
                "",
                f"- Detail: {blocker['detail']}",
                f"- Next action: {blocker['nextAction']}",
                "",
            ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_report(steps: list[dict[str, Any]], audit: dict[str, Any]) -> dict[str, Any]:
    summary = audit.get("summary", {})
    blockers = blocker_summary(audit)
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "appCompletion": audit.get("appCompletion"),
        "summary": summary,
        "canClaimComplete": (
            audit.get("appCompletion") == "complete"
            and int(summary.get("missing", 0)) == 0
            and int(summary.get("failed", 0)) == 0
            and int(summary.get("blocked", 0)) == 0
        ),
        "steps": steps,
        "blockers": blockers,
        "secretBoundary": "Closure report contains public command status and audit metadata only. It must not include tenant secrets, Apple signing material, provider credentials, service-account files, webhook secrets, Cloudflare tokens, bank credentials, or crypto keys.",
    }


def ios_ci_refresh_command(args: argparse.Namespace) -> list[str] | None:
    if args.skip_ios_ci_download:
        return None
    repo = download_ios_ci_artifacts.resolve_repo(args.repo, required=False)
    if repo:
        command = ["python3", "scripts/download_ios_ci_artifacts.py", "--repo", repo]
        if args.run_id:
            command.extend(["--run-id", args.run_id])
        if args.branch:
            command.extend(["--branch", args.branch])
        return command
    return ["python3", "scripts/import_ios_ci_artifacts.py"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository in owner/name form for iOS CI artifact download.")
    parser.add_argument("--run-id", help="Specific GitHub Actions run id for iOS CI artifact download.")
    parser.add_argument("--branch", help="Branch filter when resolving latest successful GitHub Actions run.")
    parser.add_argument("--skip-ios-ci-download", action="store_true")
    parser.add_argument("--store-submission-source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if completion is still blocked.")
    args = parser.parse_args()

    steps: list[dict[str, Any]] = []
    command = ios_ci_refresh_command(args)
    if command is not None:
        steps.append(run_step(command))

    store_command = ["python3", "scripts/import_store_submission_evidence.py"]
    if args.store_submission_source:
        store_command.extend(["--source", str(args.store_submission_source.resolve())])
    steps.append(run_step(store_command))
    steps.append(run_step(["python3", "scripts/mobile_completion_audit.py"]))

    audit = read_json(AUDIT_PATH)
    report = build_report(steps, audit)
    output = args.output.resolve()
    markdown = args.markdown.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown)

    print(f"Wrote completion closure report: {rel(output)}")
    print(f"Wrote completion closure markdown: {rel(markdown)}")
    print(f"Can claim complete: {report['canClaimComplete']}")
    if report["blockers"]:
        print("Remaining blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker['id']}: {blocker['detail']}")
    return 1 if args.strict and not report["canClaimComplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
