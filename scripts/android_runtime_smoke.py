#!/usr/bin/env python3
"""Install and launch Android release APKs on a connected device or emulator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "runtime-smoke" / "android-runtime-smoke.json"
DEFAULT_SCREENSHOT_DIR = ROOT / "build" / "runtime-smoke" / "screenshots"

FLAVORS = {
    "coolshow": {
        "applicationId": "com.coolshow.short",
        "appName": "CoolShow Short",
    },
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


class SmokeError(RuntimeError):
    pass


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


def resolve_adb() -> str:
    candidates = [
        shutil.which("adb"),
        os.environ.get("ADB"),
        "/opt/homebrew/share/android-commandlinetools/platform-tools/adb",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    raise SmokeError("adb not found. Install Android platform-tools or set ADB.")


def resolve_emulator() -> str:
    candidates = [
        shutil.which("emulator"),
        os.environ.get("ANDROID_EMULATOR"),
        "/opt/homebrew/share/android-commandlinetools/emulator/emulator",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    raise SmokeError("Android emulator binary not found.")


def connected_devices(adb: str) -> list[str]:
    output = command_output([adb, "devices"], timeout=30)
    devices: list[str] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def wait_for_device(adb: str, *, timeout: int) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        devices = connected_devices(adb)
        if devices:
            return devices[0]
        time.sleep(2)
    raise SmokeError(f"No Android device became available within {timeout}s.")


def wait_for_boot(adb: str, device: str, *, timeout: int) -> None:
    command_output([adb, "-s", device, "wait-for-device"], timeout=timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        booted = command_output(
            [adb, "-s", device, "shell", "getprop", "sys.boot_completed"],
            timeout=10,
            check=False,
        ).strip()
        if booted == "1":
            try:
                command_output([adb, "-s", device, "shell", "input", "keyevent", "82"], timeout=10, check=False)
            except subprocess.TimeoutExpired:
                pass
            return
        time.sleep(2)
    raise SmokeError(f"Android device {device} did not finish booting within {timeout}s.")


def launch_emulator(adb: str, avd: str, *, timeout: int) -> tuple[str, subprocess.Popen[bytes]]:
    emulator = resolve_emulator()
    log_path = ROOT / "build" / "runtime-smoke" / "emulator.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    process = subprocess.Popen(
        [
            emulator,
            "-avd",
            avd,
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-gpu",
            "swiftshader_indirect",
            "-no-snapshot-save",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        device = wait_for_device(adb, timeout=timeout)
        wait_for_boot(adb, device, timeout=timeout)
        return device, process
    except Exception:
        process.terminate()
        raise


def request_emulator_shutdown(adb: str, device: str) -> None:
    subprocess.Popen(
        [adb, "-s", device, "emu", "kill"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def apk_path(flavor: str) -> Path:
    path = ROOT / "build" / "app" / "outputs" / "flutter-apk" / f"app-{flavor}-release.apk"
    if not path.exists():
        raise SmokeError(f"Missing release APK: {path.relative_to(ROOT)}")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_apk(adb: str, device: str, application_id: str, apk: Path) -> str:
    output = command_output([adb, "-s", device, "install", "-r", str(apk)], timeout=180, check=False)
    if "Success" in output:
        return output
    command_output([adb, "-s", device, "uninstall", application_id], timeout=60, check=False)
    output = command_output([adb, "-s", device, "install", str(apk)], timeout=180, check=True)
    if "Success" not in output:
        raise SmokeError(f"Install did not report Success for {application_id}: {output}")
    return output


def launch_app(adb: str, device: str, application_id: str) -> str:
    resolve_output = command_output(
        [adb, "-s", device, "shell", "cmd", "package", "resolve-activity", "--brief", application_id],
        timeout=30,
        check=False,
    )
    component = ""
    for line in reversed(resolve_output.splitlines()):
        value = line.strip()
        if "/" in value and not value.startswith("No activity"):
            component = value
            break
    if not component:
        raise SmokeError(f"Could not resolve launcher activity for {application_id}: {resolve_output}")
    return command_output(
        [adb, "-s", device, "shell", "am", "start", "-W", "-n", component],
        timeout=60,
    )


def validate_screenshot(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 1024:
        raise SmokeError(f"Screenshot is too small: {path}")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SmokeError(f"Screenshot is not a PNG: {path}")


def smoke_flavor(
    adb: str,
    device: str,
    flavor: str,
    screenshot_dir: Path,
    *,
    settle_seconds: int,
) -> dict[str, Any]:
    expected = FLAVORS[flavor]
    application_id = expected["applicationId"]
    apk = apk_path(flavor)
    command_output([adb, "-s", device, "shell", "am", "force-stop", application_id], timeout=30, check=False)
    install_output = install_apk(adb, device, application_id, apk)
    launch_output = launch_app(adb, device, application_id)
    time.sleep(settle_seconds)
    pid = command_output([adb, "-s", device, "shell", "pidof", application_id], timeout=20, check=False).strip()
    if not pid:
        raise SmokeError(f"{application_id} did not stay running after launch.")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / f"{flavor}-launch.png"
    completed = subprocess.run(
        [adb, "-s", device, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError(completed.stderr.decode("utf-8", errors="replace"))
    screenshot.write_bytes(completed.stdout)
    validate_screenshot(screenshot)
    command_output([adb, "-s", device, "shell", "am", "force-stop", application_id], timeout=30, check=False)
    return {
        "flavor": flavor,
        "applicationId": application_id,
        "appName": expected["appName"],
        "apkPath": str(apk.relative_to(ROOT)),
        "apkSha256": sha256(apk),
        "installResult": "passed",
        "launchResult": "passed",
        "processPid": pid,
        "settleSeconds": settle_seconds,
        "screenshotPath": str(screenshot.relative_to(ROOT)),
        "screenshotSha256": sha256(screenshot),
        "screenshotSizeBytes": screenshot.stat().st_size,
        "installOutput": install_output.splitlines()[-1] if install_output else "Success",
        "launchOutput": launch_output.splitlines()[-1] if launch_output else "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "flavors",
        nargs="*",
        default=["all"],
        help="Flavor(s) to smoke, or 'all'. Defaults to all.",
    )
    parser.add_argument("--device", help="Existing adb device serial to use.")
    parser.add_argument("--avd", default="HongGuo_AVD", help="AVD to launch when no device is connected.")
    parser.add_argument("--launch-emulator", action="store_true", help="Launch the configured AVD if no device is connected.")
    parser.add_argument("--keep-emulator", action="store_true", help="Do not stop an emulator launched by this script.")
    parser.add_argument("--timeout", type=int, default=180, help="Device/emulator boot timeout in seconds.")
    parser.add_argument("--settle-seconds", type=int, default=12, help="Seconds to wait after launch before capturing each screenshot.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--screenshot-dir", type=Path, default=DEFAULT_SCREENSHOT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    flavors = list(FLAVORS) if "all" in args.flavors else args.flavors
    unknown = [flavor for flavor in flavors if flavor not in FLAVORS]
    if unknown:
        raise SmokeError(f"Unknown flavor(s): {', '.join(unknown)}")

    adb = resolve_adb()
    command_output([adb, "start-server"], timeout=30)
    emulator_process: subprocess.Popen[bytes] | None = None
    launched_emulator = False
    if args.device:
        device = args.device
        wait_for_boot(adb, device, timeout=args.timeout)
    else:
        devices = connected_devices(adb)
        if devices:
            device = devices[0]
            wait_for_boot(adb, device, timeout=args.timeout)
        elif args.launch_emulator:
            device, emulator_process = launch_emulator(adb, args.avd, timeout=args.timeout)
            launched_emulator = True
        else:
            raise SmokeError(
                "No connected Android device. Connect a device or pass --launch-emulator.",
            )

    runs: list[dict[str, Any]] = []
    try:
        for flavor in flavors:
            runs.append(smoke_flavor(
                adb,
                device,
                flavor,
                args.screenshot_dir,
                settle_seconds=args.settle_seconds,
            ))
    except Exception:
        if launched_emulator and not args.keep_emulator:
            request_emulator_shutdown(adb, device)
        raise

    for run in runs:
        apk = ROOT / run["apkPath"]
        screenshot = ROOT / run["screenshotPath"]
        validate_screenshot(screenshot)
        run["apkSha256"] = sha256(apk)
        run["screenshotSha256"] = sha256(screenshot)
        run["screenshotSizeBytes"] = screenshot.stat().st_size

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "result": "passed",
        "deviceSerial": device,
        "launchedEmulator": launched_emulator,
        "avd": args.avd if launched_emulator else None,
        "secretBoundary": "Runtime smoke contains public package, device, screenshot hash, and launch evidence only. It does not contain tenant secrets, OAuth secrets, payment secrets, Cloudflare tokens, Stream signing keys, webhook secrets, bank credentials, or crypto private keys.",
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote Android runtime smoke: {args.output.relative_to(ROOT)}")
    for run in runs:
        print(f"{run['flavor']}: installed and launched {run['applicationId']} on {device}")
    if launched_emulator and not args.keep_emulator:
        request_emulator_shutdown(adb, device)
        if emulator_process and emulator_process.poll() is None:
            print(f"Requested emulator shutdown for {device}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as error:
        print(f"android runtime smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
