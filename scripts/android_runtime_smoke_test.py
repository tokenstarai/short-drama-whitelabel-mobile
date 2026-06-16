#!/usr/bin/env python3
"""Regression tests for android_runtime_smoke.py."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

import android_runtime_smoke


class AndroidRuntimeSmokeTest(unittest.TestCase):
    def test_wait_for_boot_ignores_noncritical_unlock_timeout(self) -> None:
        calls: list[list[str]] = []

        def fake_command_output(
            command: list[str],
            *,
            timeout: int = 60,
            check: bool = True,
        ) -> str:
            calls.append(command)
            if command[-1] == "wait-for-device":
                return ""
            if command[-1] == "sys.boot_completed":
                return "1"
            if command[-2:] == ["keyevent", "82"]:
                raise subprocess.TimeoutExpired(command, timeout)
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch.object(android_runtime_smoke, "command_output", fake_command_output):
            android_runtime_smoke.wait_for_boot("/fake/adb", "emulator-5554", timeout=30)

        self.assertEqual(
            [
                ["/fake/adb", "-s", "emulator-5554", "wait-for-device"],
                ["/fake/adb", "-s", "emulator-5554", "shell", "getprop", "sys.boot_completed"],
                ["/fake/adb", "-s", "emulator-5554", "shell", "input", "keyevent", "82"],
            ],
            calls,
        )


if __name__ == "__main__":
    unittest.main()
