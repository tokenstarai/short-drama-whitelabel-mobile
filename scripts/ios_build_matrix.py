#!/usr/bin/env python3
"""Build unsigned iOS flavor matrix and write public completion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "ios-build-matrix" / "ios-build-matrix.json"
DEFAULT_INFO_DIR = ROOT / "build" / "ios-build-matrix" / "app-info"

FLAVORS = {
    "hongguo": {
        "applicationId": "com.shortdrama.goldfruit",
        "appName": "GoldFruit Drama",
    },
    "douyin": {
        "applicationId": "com.shortdrama.pulse",
        "appName": "Pulse Drama",
    },
    "hippo": {
        "applicationId": "com.shortdrama.river",
        "appName": "River Drama",
    },
    "reelshort": {
        "applicationId": "com.shortdrama.cliff",
        "appName": "Cliff Drama",
    },
}

MODES = ["debug", "release"]
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


def command_output(command: list[str], *, timeout: int = 60) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_size(path: Path) -> int:
    total = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            total += file_path.stat().st_size
    return total


def xcode_environment() -> dict[str, Any]:
    select_code, developer_dir = command_output(["xcode-select", "-p"], timeout=10)
    xcodebuild_path = shutil.which("xcodebuild")
    xcodebuild_code, xcodebuild_version = command_output(["xcodebuild", "-version"], timeout=20) if xcodebuild_path else (127, "")
    pod_path = shutil.which("pod")
    pod_code, pod_version = command_output([pod_path, "--version"], timeout=20) if pod_path else (127, "")
    flutter_bin = shutil.which("flutter") or str(ROOT / "scripts" / "resolve_flutter_bin.sh")

    blockers: list[str] = []
    if not Path("/Applications/Xcode.app").exists():
        blockers.append("/Applications/Xcode.app is missing")
    if select_code != 0 or "CommandLineTools" in developer_dir or "Xcode" not in developer_dir:
        blockers.append(f"full Xcode is not selected; xcode-select={developer_dir or 'unavailable'}")
    if not xcodebuild_path or xcodebuild_code != 0:
        blockers.append("xcodebuild is not available")
    if not pod_path or pod_code != 0:
        blockers.append("CocoaPods is not available")

    return {
        "xcodeSelectPath": developer_dir or "unavailable",
        "applicationsXcodePresent": Path("/Applications/Xcode.app").exists(),
        "xcodebuildPath": xcodebuild_path,
        "xcodebuildVersion": xcodebuild_version,
        "podPath": pod_path,
        "podVersion": pod_version if pod_code == 0 else None,
        "flutterPath": flutter_bin,
        "blockers": blockers,
    }


def planned_builds(flavors: list[str], modes: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "flavor": flavor,
            "mode": mode,
            "platform": "ios",
            "command": ["./scripts/build_flavor.sh", flavor, "ios", mode],
        }
        for flavor in flavors
        for mode in modes
    ]


def app_info(app_path: Path, flavor: str, mode: str, info_dir: Path) -> dict[str, Any]:
    plist_path = app_path / "Info.plist"
    if not plist_path.exists():
        return {
            "appPath": str(app_path.relative_to(ROOT)),
            "infoPlistPresent": False,
        }
    with plist_path.open("rb") as source:
        plist = plistlib.load(source)

    info = {
        "flavor": flavor,
        "mode": mode,
        "appPath": str(app_path.relative_to(ROOT)),
        "infoPlistPresent": True,
        "bundleIdentifier": plist.get("CFBundleIdentifier"),
        "displayName": plist.get("CFBundleDisplayName") or plist.get("CFBundleName"),
        "bundleVersion": plist.get("CFBundleVersion"),
        "shortVersionString": plist.get("CFBundleShortVersionString"),
        "appSizeBytes": dir_size(app_path),
    }
    info_dir.mkdir(parents=True, exist_ok=True)
    info_json = info_dir / f"{flavor}-{mode}-info.json"
    info_json.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    info["infoSnapshotPath"] = str(info_json.relative_to(ROOT))
    info["infoSnapshotSha256"] = sha256(info_json)
    return info


def build_one(flavor: str, mode: str, info_dir: Path, timeout: int) -> dict[str, Any]:
    expected = FLAVORS[flavor]
    command = ["./scripts/build_flavor.sh", flavor, "ios", mode]
    start = time.time()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    duration = round(time.time() - start, 3)
    output_tail = completed.stdout.strip().splitlines()[-40:]
    run: dict[str, Any] = {
        "flavor": flavor,
        "mode": mode,
        "platform": "ios",
        "applicationId": expected["applicationId"],
        "appName": expected["appName"],
        "command": command,
        "exitCode": completed.returncode,
        "durationSeconds": duration,
        "outputTail": output_tail,
    }
    if completed.returncode == 0:
        app_path = ROOT / "build" / "ios" / "iphoneos" / "Runner.app"
        run["buildResult"] = "passed"
        run["app"] = app_info(app_path, flavor, mode, info_dir)
    else:
        run["buildResult"] = "failed"
    return run


def validate_no_forbidden_markers(payload: dict[str, Any]) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in serialized]


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def selected_values(values: list[str], allowed: list[str], label: str) -> list[str]:
    if values == ["all"]:
        return list(allowed)
    invalid = [value for value in values if value not in allowed]
    if invalid:
        raise SystemExit(f"Unknown {label}: {', '.join(invalid)}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "flavors",
        nargs="*",
        default=["all"],
        help="flavors to build, or all; defaults to all",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=MODES,
        help="build modes to verify; defaults to debug release",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="timeout per flavor/mode build in seconds",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON output path",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when the iOS toolchain is blocked",
    )
    args = parser.parse_args()

    flavors = selected_values(args.flavors, list(FLAVORS), "flavor")
    modes = selected_values(args.modes, MODES, "mode")
    environment = xcode_environment()
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "requiredFlavors": list(FLAVORS),
        "requiredModes": MODES,
        "requestedFlavors": flavors,
        "requestedModes": modes,
        "environment": environment,
        "plannedBuilds": planned_builds(flavors, modes),
        "runs": [],
        "secretBoundary": "Public local build metadata only. No Apple signing material, provisioning profiles, tenant secrets, OAuth secrets, payment secrets, or Cloudflare tokens are included.",
    }

    if environment["blockers"]:
        report["result"] = "blocked"
        report["blockers"] = environment["blockers"]
        write_report(report, args.output)
        print(f"Wrote blocked iOS build matrix: {args.output.relative_to(ROOT)}")
        for blocker in environment["blockers"]:
            print(f"blocked: {blocker}")
        return 1 if args.strict else 0

    info_dir = DEFAULT_INFO_DIR
    runs = [
        build_one(flavor, mode, info_dir, args.timeout)
        for flavor in flavors
        for mode in modes
    ]
    report["runs"] = runs
    failed = [run for run in runs if run["buildResult"] != "passed"]
    marker_hits = validate_no_forbidden_markers(report)
    report["forbiddenMarkerHits"] = marker_hits
    report["result"] = "failed" if failed or marker_hits else "passed"
    write_report(report, args.output)
    print(f"Wrote iOS build matrix: {args.output.relative_to(ROOT)}")
    for run in runs:
        print(f"{run['flavor']} {run['mode']}: {run['buildResult']}")
    return 1 if report["result"] != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
