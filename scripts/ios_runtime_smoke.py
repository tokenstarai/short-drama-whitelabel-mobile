#!/usr/bin/env python3
"""Install and launch iOS simulator builds on a booted Simulator."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "runtime-smoke" / "ios-runtime-smoke.json"
DEFAULT_SCREENSHOT_DIR = ROOT / "build" / "runtime-smoke" / "ios-screenshots"

FLAVORS = {
    "coolshow": {
        "applicationId": "com.coolshow.short",
        "appName": "CoolShow Short",
        "xcconfig": "Coolshow.xcconfig",
    },
    "hongguo": {
        "applicationId": "com.shortdrama.goldfruit",
        "appName": "GoldFruit Drama",
        "xcconfig": "Hongguo.xcconfig",
    },
    "douyin": {
        "applicationId": "com.shortdrama.pulse",
        "appName": "Pulse Drama",
        "xcconfig": "Douyin.xcconfig",
    },
    "hippo": {
        "applicationId": "com.shortdrama.river",
        "appName": "River Drama",
        "xcconfig": "Hippo.xcconfig",
    },
    "reelshort": {
        "applicationId": "com.shortdrama.cliff",
        "appName": "Cliff Drama",
        "xcconfig": "Reelshort.xcconfig",
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


class SmokeError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def command_output(command: list[str], *, timeout: int = 60, check: bool = True) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = completed.stdout.strip()
    if check and completed.returncode != 0:
        raise SmokeError(f"{' '.join(command)} failed with {completed.returncode}: {output}")
    return output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_size(path: Path) -> int:
    return sum(file_path.stat().st_size for file_path in path.rglob("*") if file_path.is_file())


def validate_png(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 1024:
        raise SmokeError(f"Screenshot is too small: {path}")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SmokeError(f"Screenshot is not a PNG: {path}")


def simctl_json(command: list[str], *, timeout: int = 60) -> dict[str, Any]:
    return json.loads(command_output(["xcrun", "simctl", *command], timeout=timeout))


def available_simulators() -> list[dict[str, Any]]:
    devices = simctl_json(["list", "devices", "available", "--json"]).get("devices", {})
    sims: list[dict[str, Any]] = []
    for runtime, rows in devices.items():
        if "iOS" not in runtime:
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("isAvailable", True):
                sims.append(row)
    return sims


def select_simulator(device_id: str | None = None, *, boot_if_needed: bool = False, simulator_name: str | None = None, timeout: int = 120) -> dict[str, Any]:
    sims = available_simulators()
    if device_id:
        matches = [sim for sim in sims if sim.get("udid") == device_id]
        if not matches:
            raise SmokeError(f"Requested iOS simulator is unavailable: {device_id}")
        selected = matches[0]
    else:
        booted = [sim for sim in sims if sim.get("state") == "Booted"]
        if booted:
            return booted[0]
        if not boot_if_needed:
            raise SmokeError("No booted iOS simulator. Boot one in Simulator.app, or rerun with --boot-simulator.")
        if simulator_name:
            named = [sim for sim in sims if sim.get("name") == simulator_name]
            if not named:
                raise SmokeError(f"No available iOS simulator named {simulator_name!r}.")
            selected = named[0]
        elif sims:
            selected = sims[0]
        else:
            raise SmokeError("No available iOS simulators were found.")

    udid = str(selected["udid"])
    if selected.get("state") != "Booted":
        command_output(["xcrun", "simctl", "boot", udid], timeout=timeout, check=False)
        command_output(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=timeout)
    return {**selected, "state": "Booted"}


def resolve_flutter_bin(*, timeout: int = 30) -> str:
    return command_output([str(ROOT / "scripts" / "resolve_flutter_bin.sh")], timeout=timeout)


@contextlib.contextmanager
def flavor_xcconfig(flavor: str) -> Iterator[None]:
    target = ROOT / "ios" / "Flutter" / "WhitelabelDefaults.xcconfig"
    source = ROOT / "ios" / "Flutter" / FLAVORS[flavor]["xcconfig"]
    if not source.exists():
        raise SmokeError(f"Missing iOS flavor config: {source.relative_to(ROOT)}")
    backup = target.read_bytes()
    try:
        shutil.copyfile(source, target)
        yield
    finally:
        target.write_bytes(backup)


def build_simulator_app(flavor: str, *, timeout: int) -> Path:
    flutter_bin = resolve_flutter_bin(timeout=timeout)
    with flavor_xcconfig(flavor):
        command_output(
            [
                flutter_bin,
                "build",
                "ios",
                "--simulator",
                "--debug",
                "--no-pub",
                f"--dart-define=APP_FLAVOR={flavor}",
            ],
            timeout=timeout,
        )
    app_path = ROOT / "build" / "ios" / "iphonesimulator" / "Runner.app"
    if not app_path.exists():
        raise SmokeError("Flutter simulator build did not produce build/ios/iphonesimulator/Runner.app")
    return app_path


def launch_app(device_id: str, bundle_id: str) -> str:
    output = command_output(["xcrun", "simctl", "launch", device_id, bundle_id], timeout=60)
    parts = output.replace(":", " ").split()
    for part in reversed(parts):
        if part.isdigit():
            return part
    return output


def smoke_flavor(device: dict[str, Any], flavor: str, screenshot_dir: Path, *, timeout: int, settle_seconds: int, skip_build: bool) -> dict[str, Any]:
    expected = FLAVORS[flavor]
    bundle_id = expected["applicationId"]
    device_id = str(device["udid"])
    app_path = ROOT / "build" / "ios" / "iphonesimulator" / "Runner.app"
    if not skip_build or not app_path.exists():
        app_path = build_simulator_app(flavor, timeout=timeout)
    command_output(["xcrun", "simctl", "terminate", device_id, bundle_id], timeout=30, check=False)
    command_output(["xcrun", "simctl", "uninstall", device_id, bundle_id], timeout=30, check=False)
    command_output(["xcrun", "simctl", "install", device_id, str(app_path)], timeout=120)
    process_pid = launch_app(device_id, bundle_id)
    time.sleep(settle_seconds)

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / f"{flavor}-launch.png"
    command_output(["xcrun", "simctl", "io", device_id, "screenshot", str(screenshot)], timeout=30)
    validate_png(screenshot)
    command_output(["xcrun", "simctl", "terminate", device_id, bundle_id], timeout=30, check=False)

    return {
        "flavor": flavor,
        "applicationId": bundle_id,
        "appName": expected["appName"],
        "appPath": str(app_path.relative_to(ROOT)),
        "appSha256": sha256(app_path / "Info.plist"),
        "appSizeBytes": dir_size(app_path),
        "installResult": "passed",
        "launchResult": "passed",
        "processPid": str(process_pid),
        "screenshotPath": str(screenshot.relative_to(ROOT)),
        "screenshotSha256": sha256(screenshot),
        "screenshotSizeBytes": screenshot.stat().st_size,
    }


def marker_hits(payload: dict[str, Any]) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    return [marker for marker in FORBIDDEN_MARKERS if marker in serialized]


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def selected_flavors(values: list[str]) -> list[str]:
    if values == ["all"]:
        return list(FLAVORS)
    invalid = [value for value in values if value not in FLAVORS]
    if invalid:
        raise SystemExit(f"Unknown flavor: {', '.join(invalid)}")
    return values


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    device = select_simulator(
        args.device_id,
        boot_if_needed=args.boot_simulator,
        simulator_name=args.simulator_name,
        timeout=args.timeout,
    )
    runs = [
        smoke_flavor(
            device,
            flavor,
            args.screenshot_dir,
            timeout=args.timeout,
            settle_seconds=args.settle_seconds,
            skip_build=args.skip_build,
        )
        for flavor in selected_flavors(args.flavors)
    ]
    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "result": "passed",
        "device": {
            "name": device.get("name"),
            "udid": device.get("udid"),
            "state": "Booted",
            "runtime": device.get("runtime"),
        },
        "requestedFlavors": selected_flavors(args.flavors),
        "runs": runs,
        "secretBoundary": "Public simulator install, launch, screenshot, and bundle metadata only. No signing material, provider credentials, Tenant Edge secrets, payment secrets, Cloudflare tokens, bank credentials, or crypto keys are recorded.",
    }
    report["forbiddenMarkerHits"] = marker_hits(report)
    if report["forbiddenMarkerHits"]:
        report["result"] = "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flavors", nargs="*", default=["all"], help="flavors to smoke, or all")
    parser.add_argument("--device-id", default=None, help="iOS Simulator UDID to use")
    parser.add_argument("--boot-simulator", action="store_true", help="Boot a simulator when none is already booted")
    parser.add_argument("--simulator-name", default=None, help="Simulator name to boot when --boot-simulator is used")
    parser.add_argument("--skip-build", action="store_true", help="Install the existing build/ios/iphonesimulator/Runner.app")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--settle-seconds", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    args = parser.parse_args()

    try:
        report = build_report(args)
    except SmokeError as error:
        print(f"iOS runtime smoke blocked: {error}")
        return 1
    write_report(report, args.output)
    print(f"Wrote iOS runtime smoke: {args.output.relative_to(ROOT)}")
    print(f"Result: {report['result']}")
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
