#!/usr/bin/env python3
"""Audit local Flutter/Dart tool availability without faking test success."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "flutter-toolchain" / "flutter-toolchain-audit.json"


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

    def to_json(self) -> dict[str, object]:
        return {
            "command": self.command,
            "exitCode": self.exit_code,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
            "timedOut": self.timed_out,
        }


CommandRunner = Callable[[list[str], int], CommandResult]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def default_run_command(command: list[str], timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            command=command,
            exit_code=None,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
            timed_out=True,
        )
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


def resolve_flutter_bin(env: dict[str, str] | None = None) -> Path | None:
    current_env = env or os.environ
    configured = current_env.get("FLUTTER_BIN")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path
    path_on_path = shutil.which("flutter")
    if path_on_path:
        return Path(path_on_path)
    for candidate in [
        Path("/tmp/flutter/bin/flutter"),
        Path.home() / ".local" / "flutter" / "bin" / "flutter",
    ]:
        if candidate.exists():
            return candidate
    return None


def resolve_dart_bin(flutter_bin: Path | None, env: dict[str, str] | None = None) -> Path | None:
    current_env = env or os.environ
    configured = current_env.get("DART_BIN")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path
    if flutter_bin is not None:
        sdk_dart = flutter_bin.parent / "cache" / "dart-sdk" / "bin" / "dart"
        if sdk_dart.exists():
            return sdk_dart
    path_on_path = shutil.which("dart")
    if path_on_path:
        return Path(path_on_path)
    return None


def command_status(command_result: CommandResult | None) -> str:
    if command_result is None:
        return "missing"
    if command_result.timed_out:
        return "timeout"
    if command_result.exit_code == 0:
        return "passed"
    return "failed"


def build_report(
    *,
    root: Path = ROOT,
    flutter_bin: Path | None = None,
    dart_bin: Path | None = None,
    run_command: CommandRunner = default_run_command,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    resolved_flutter = flutter_bin or resolve_flutter_bin()
    resolved_dart = dart_bin or resolve_dart_bin(resolved_flutter)
    dart_result: CommandResult | None = None
    flutter_result: CommandResult | None = None

    if resolved_dart is not None:
        dart_result = run_command([str(resolved_dart), "--version"], timeout_seconds)
    if resolved_flutter is not None:
        flutter_result = run_command([str(resolved_flutter), "--no-version-check", "--version"], timeout_seconds)

    blockers: list[str] = []
    if resolved_flutter is None:
        blockers.append("flutter-not-found")
    elif flutter_result is None:
        blockers.append("flutter-not-run")
    elif flutter_result.timed_out:
        blockers.append("flutter-command-timeout")
    elif flutter_result.exit_code != 0:
        blockers.append("flutter-command-failed")

    if resolved_dart is None:
        blockers.append("dart-not-found")
    elif dart_result is None:
        blockers.append("dart-not-run")
    elif dart_result.timed_out:
        blockers.append("dart-command-timeout")
    elif dart_result.exit_code != 0:
        blockers.append("dart-command-failed")

    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "passed" if not blockers else "blocked",
        "blockers": ", ".join(blockers),
        "timeoutSeconds": timeout_seconds,
        "flutter": {
            "path": str(resolved_flutter) if resolved_flutter else None,
            "status": command_status(flutter_result),
            "timedOut": bool(flutter_result and flutter_result.timed_out),
            "exitCode": flutter_result.exit_code if flutter_result else None,
            "command": flutter_result.command if flutter_result else None,
            "stdout": flutter_result.stdout.strip() if flutter_result else "",
            "stderr": flutter_result.stderr.strip() if flutter_result else "",
        },
        "dart": {
            "path": str(resolved_dart) if resolved_dart else None,
            "status": command_status(dart_result),
            "timedOut": bool(dart_result and dart_result.timed_out),
            "exitCode": dart_result.exit_code if dart_result else None,
            "command": dart_result.command if dart_result else None,
            "stdout": dart_result.stdout.strip() if dart_result else "",
            "stderr": dart_result.stderr.strip() if dart_result else "",
        },
        "nextActions": [
            "Set FLUTTER_BIN to a responsive Flutter SDK, then run `cd mobile && FLUTTER_BIN=/path/to/flutter ./scripts/check_mobile.sh`.",
            "If Flutter hangs during startup, fix the SDK git remote/network state or run the CI workflow `.github/workflows/mobile-flutter.yml` and import its artifacts.",
            "Do not treat prototype screenshots or existing build manifests as fresh Flutter test proof.",
        ],
        "diagnosticOnly": True,
    }


def write_report(report: dict[str, object], output: Path, root: Path = ROOT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_report(timeout_seconds=args.timeout_seconds)
    output = write_report(report, args.output)
    print(f"Wrote Flutter toolchain audit: {rel(ROOT, output)}")
    print(f"Result: {report['result']}")
    if report.get("blockers"):
        print(f"Blockers: {report['blockers']}")
    return 1 if args.strict and report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
