#!/usr/bin/env python3
"""Regression tests for mobile_completion_audit.py."""

from __future__ import annotations

import os
import argparse
import concurrent.futures
import csv
import unittest
import tempfile
import zipfile
import hashlib
import json
import plistlib
import shutil
from pathlib import Path
from unittest import mock

import download_ios_ci_artifacts
import export_completion_unblocker
import export_external_account_handoff
import export_github_publish_handoff
import export_ios_ci_handoff
import export_open_source_template
import export_store_submission_starter
import export_ui_preview_gallery
import import_github_publication_evidence
import import_ios_ci_artifacts
import import_store_submission_evidence
import ios_runtime_smoke
import flutter_toolchain_audit
import mobile_completion_audit
import mobile_completion_closure


class MobileCompletionAuditTest(unittest.TestCase):
    def _copy_wysiwyg_runtime_previews(self, source_root: Path, target_root: Path) -> None:
        source_dir = source_root / "build" / "wysiwyg-preview"
        target_dir = target_root / "build" / "wysiwyg-preview"
        target_dir.mkdir(parents=True, exist_ok=True)
        for _, _, _, source_name in export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS:
            shutil.copyfile(source_dir / source_name, target_dir / source_name)
        source_manifest = source_dir / "wysiwyg-preview-manifest.json"
        if source_manifest.exists():
            shutil.copyfile(source_manifest, target_dir / source_manifest.name)

    def test_flutter_toolchain_audit_reports_timeout_without_faking_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flutter_bin = root / "flutter"
            dart_bin = root / "dart"
            flutter_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            dart_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            flutter_bin.chmod(0o755)
            dart_bin.chmod(0o755)

            def fake_run(command: list[str], timeout: int) -> flutter_toolchain_audit.CommandResult:
                if command[0] == str(dart_bin):
                    return flutter_toolchain_audit.CommandResult(
                        command=command,
                        exit_code=0,
                        stdout="Dart SDK version: 3.12.2",
                        stderr="",
                        timed_out=False,
                    )
                return flutter_toolchain_audit.CommandResult(
                    command=command,
                    exit_code=None,
                    stdout="Building flutter tool...",
                    stderr="",
                    timed_out=True,
                )

            report = flutter_toolchain_audit.build_report(
                root=root,
                flutter_bin=flutter_bin,
                dart_bin=dart_bin,
                run_command=fake_run,
                timeout_seconds=3,
            )

        self.assertEqual("blocked", report["result"])
        self.assertEqual("flutter-command-timeout", report["blockers"])
        self.assertEqual(str(flutter_bin), report["flutter"]["path"])
        self.assertTrue(report["flutter"]["timedOut"])
        self.assertEqual(0, report["dart"]["exitCode"])
        self.assertIn("FLUTTER_BIN", report["nextActions"][0])

    def test_flutter_toolchain_audit_check_is_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = {
                "schemaVersion": 1,
                "result": "blocked",
                "blockers": "flutter-command-timeout",
                "flutter": {"path": "/fake/flutter", "timedOut": True},
                "dart": {"path": "/fake/dart", "exitCode": 0},
                "nextActions": ["Set FLUTTER_BIN to a responsive Flutter SDK."],
            }
            output = root / "build" / "flutter-toolchain" / "flutter-toolchain-audit.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps(report), encoding="utf-8")

            check = mobile_completion_audit.check_flutter_toolchain_audit(root)

        self.assertEqual("flutter_toolchain_audit", check.id)
        self.assertEqual("blocked", check.status)
        self.assertFalse(check.completion_blocking)
        self.assertIn("flutter-command-timeout", check.detail)
        self.assertIn("build/flutter-toolchain/flutter-toolchain-audit.json", check.evidence)

    def test_download_ios_ci_artifacts_plans_gh_download_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "build" / "ci-ios"
            import_output = root / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"

            report = download_ios_ci_artifacts.build_plan_report(
                repo="tokenstarai/short-drama-saas",
                run_id="123456789",
                source_dir=source_dir,
                import_output=import_output,
            )

        self.assertEqual("dry_run", report["mode"])
        self.assertEqual("tokenstarai/short-drama-saas", report["repo"])
        self.assertEqual("123456789", report["runId"])
        self.assertEqual(
            [
                "mobile-coolshow-ios-unsigned",
                "mobile-hongguo-ios-unsigned",
                "mobile-douyin-ios-unsigned",
                "mobile-hippo-ios-unsigned",
                "mobile-reelshort-ios-unsigned",
            ],
            [step["artifactName"] for step in report["downloadSteps"]],
        )
        self.assertIn(
            "gh run download 123456789 --repo tokenstarai/short-drama-saas -n mobile-coolshow-ios-unsigned",
            report["downloadSteps"][0]["command"],
        )
        self.assertTrue(
            report["downloadSteps"][0]["destination"].endswith("build/ci-ios/coolshow"),
        )
        self.assertIn(
            "scripts/import_ios_ci_artifacts.py --strict",
            report["importStep"]["command"],
        )

    def test_download_ios_ci_artifacts_resolves_github_remote_urls(self) -> None:
        self.assertEqual(
            "tokenstarai/short-drama-saas",
            download_ios_ci_artifacts.parse_repo_slug(
                "https://github.com/tokenstarai/short-drama-saas.git",
            ),
        )
        self.assertEqual(
            "tokenstarai/short-drama-saas",
            download_ios_ci_artifacts.parse_repo_slug(
                "git@github.com:tokenstarai/short-drama-saas.git",
            ),
        )

    def test_download_ios_ci_artifacts_resolves_repo_from_actions_environment(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"GITHUB_REPOSITORY": "tokenstarai/short-drama-saas"},
        ):
            repo = download_ios_ci_artifacts.resolve_repo(None)

        self.assertEqual("tokenstarai/short-drama-saas", repo)

    def test_download_ios_ci_artifacts_selects_latest_successful_workflow_run(self) -> None:
        run_id = download_ios_ci_artifacts.select_latest_successful_run_id(
            [
                {"databaseId": 1003, "status": "completed", "conclusion": "failure"},
                {"databaseId": 1002, "status": "in_progress", "conclusion": None},
                {"databaseId": 1001, "status": "completed", "conclusion": "success"},
            ],
        )

        self.assertEqual("1001", run_id)

    def test_download_ios_ci_artifacts_clears_stale_flavor_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "ci-ios"
            destination = source_dir / "hongguo"
            destination.mkdir(parents=True)
            (destination / "AppFrameworkInfo.plist").write_text("stale", encoding="utf-8")

            prepared = download_ios_ci_artifacts.prepare_download_destination(
                source_dir,
                "hongguo",
            )

            self.assertEqual(destination, prepared)
            self.assertTrue(prepared.exists())
            self.assertEqual([], list(prepared.iterdir()))

    def test_store_submission_evidence_importer_requires_public_tenant_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "store-submission-evidence.input.json"
            output = root / "store-submission-evidence.json"
            template = root / "store-submission-evidence.template.json"

            blocked = import_store_submission_evidence.import_evidence(
                source,
                output,
                template,
            )
            self.assertEqual("blocked", blocked["result"])
            self.assertTrue(template.exists())
            self.assertEqual(
                list(import_store_submission_evidence.FLAVOR_DEFAULTS),
                blocked["missingFlavors"],
            )
            self.assertIn(
                "build/store-submission-starter/coolshow/store-submission-evidence.input.example.json",
                " ".join(blocked["blockedFlavors"][0]["remediationHints"]),
            )

            submissions = []
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                flags = {
                    flag: True
                    for flag in import_store_submission_evidence.required_flags(channel)
                }
                submissions.append({
                    "flavor": flavor,
                    "templateApplicationId": expected["applicationId"],
                    "templateAppName": expected["appName"],
                    "applicationId": f"{expected['applicationId']}.tenant",
                    "appName": f"{expected['appName']} Tenant",
                    "storeComplianceMode": expected["storeComplianceMode"],
                    "primaryChannel": channel,
                    "submissionStatus": status_by_channel[channel],
                    **flags,
                    "publicEvidenceRefs": [f"{flavor} public store track evidence"],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                })
            source.write_text(
                json.dumps({"schemaVersion": 1, "submissions": submissions}),
                encoding="utf-8",
            )

            passed = import_store_submission_evidence.import_evidence(
                source,
                output,
                template,
            )

        self.assertEqual("passed", passed["result"])
        self.assertFalse(passed["forbiddenMarkerHits"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(passed["submissions"]))

    def test_store_submission_evidence_importer_writes_tenant_guide(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "store-submission-evidence.input.json"
            output = root / "store-submission-evidence.json"
            template = root / "store-submission-evidence.template.json"
            guide = root / "store-submission-evidence.guide.md"

            import_store_submission_evidence.import_evidence(
                source,
                output,
                template,
            )

            self.assertTrue(guide.exists())
            guide_text = guide.read_text(encoding="utf-8")

        self.assertIn("# Store Submission Evidence Guide", guide_text)
        self.assertIn("## hongguo", guide_text)
        self.assertIn("Allowed statuses: `testflight_uploaded`", guide_text)
        self.assertIn("Required checklist flags:", guide_text)
        self.assertIn("Public evidence examples:", guide_text)
        self.assertIn("public HTTPS URL", guide_text)
        self.assertIn("not in the future", guide_text)
        self.assertIn("./scripts/import_store_submission_evidence.py --strict", guide_text)
        self.assertIn(
            "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            guide_text,
        )
        lowered = guide_text.lower()
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_store_submission_starter_package_exports_tenant_fillable_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "store-submission-starter"

            manifest = export_store_submission_starter.export_starter(
                root=Path(__file__).resolve().parents[1],
                output_dir=output_dir,
            )

            starter_zip = output_dir / "mobile-store-submission-starter.zip"
            with zipfile.ZipFile(starter_zip) as archive:
                names = set(archive.namelist())
                self.assertIn(
                    "mobile-store-submission-starter/douyin/store-submission-evidence.input.example.json",
                    names,
                )
                self.assertIn(
                    "mobile-store-submission-starter/store-submission-evidence-collector.html",
                    names,
                )
                self.assertIn(
                    "mobile-store-submission-starter/store-submission-operator-runbook.md",
                    names,
                )
                self.assertIn(
                    "mobile-store-submission-starter/reelshort/operator-checklist.md",
                    names,
                )
                self.assertIn(
                    "mobile-store-submission-starter/douyin/submission-runbook.md",
                    names,
                )
                input_example = json.loads(
                    archive.read(
                        "mobile-store-submission-starter/douyin/store-submission-evidence.input.example.json",
                    ).decode("utf-8"),
                )
                collector_html = archive.read(
                    "mobile-store-submission-starter/store-submission-evidence-collector.html",
                ).decode("utf-8")
                operator_runbook = archive.read(
                    "mobile-store-submission-starter/store-submission-operator-runbook.md",
                ).decode("utf-8")
                douyin_runbook = archive.read(
                    "mobile-store-submission-starter/douyin/submission-runbook.md",
                ).decode("utf-8")

        self.assertEqual("mobile_store_submission_starter", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "store-submission-operator-runbook.md",
            manifest["operatorRunbookPath"],
        )
        self.assertRegex(manifest["operatorRunbookSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "store-submission-evidence-collector.html",
            manifest["collectorHtmlPath"],
        )
        self.assertRegex(manifest["collectorHtmlSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence-preflight.json",
            manifest["preflightReportPath"],
        )
        self.assertIn(
            "store_submission_evidence_preflight.py",
            manifest["preflightCommand"],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors",
            manifest.get("perFlavorInputDirectory"),
        )
        self.assertIn(
            "--source-dir build/store-submission-evidence/flavors",
            manifest.get("perFlavorImportCommand", ""),
        )
        self.assertEqual(
            manifest.get("perFlavorImportCommand"),
            manifest.get("importCommand"),
        )
        self.assertEqual(
            "cd mobile && python3 scripts/import_store_submission_evidence.py --strict",
            manifest.get("combinedImportCommand"),
        )
        self.assertEqual(
            "Copy each flavor input example to build/store-submission-evidence/flavors/<flavor>.input.json after tenant-owned signing and store setup. Per-flavor input files take precedence over the combined input for preflight and source-dir strict import.",
            manifest["tenantActionSummary"],
        )
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))

        douyin = flavors["douyin"]
        self.assertEqual("android_direct", douyin["primaryChannel"])
        self.assertIn("direct_signed_package_ready", douyin["allowedStatuses"])
        self.assertIn("directSignedPackageReady", douyin["requiredFlags"])
        self.assertEqual("douyin/store-submission-evidence.input.example.json", douyin["inputExamplePath"])
        self.assertEqual("build/store-submission-evidence/flavors/douyin.input.json", douyin["tenantEvidenceInputPath"])
        self.assertEqual("douyin/operator-checklist.md", douyin["operatorChecklistPath"])
        self.assertEqual("douyin/submission-runbook.md", douyin["submissionRunbookPath"])
        self.assertRegex(douyin["submissionRunbookSha256"], r"^[a-f0-9]{64}$")

        self.assertEqual("tenant_store_submission_public_evidence_input", input_example["source"])
        self.assertEqual("douyin", input_example["submissions"][0]["flavor"])
        self.assertEqual("pending_tenant_action", input_example["submissions"][0]["submissionStatus"])
        self.assertFalse(input_example["submissions"][0]["directSignedPackageReady"])
        self.assertFalse(input_example["submissions"][0]["directDistributionPolicyPublished"])
        self.assertTrue(input_example["submissions"][0]["tenantMustReplacePlaceholders"])
        self.assertEqual(
            export_store_submission_starter.SECRET_BOUNDARY,
            input_example["secretBoundary"],
        )
        self.assertIn("publicEvidenceRefSchema", input_example)
        self.assertIn(
            "testflight_build",
            input_example["publicEvidenceRefSchema"]["allowedTypes"],
        )
        self.assertIn(
            "one of value/url/sha256",
            input_example["publicEvidenceRefSchema"]["requiredObjectFields"],
        )
        self.assertIn(
            "public HTTPS URL",
            input_example["publicEvidenceRefSchema"]["urlRequirement"],
        )
        self.assertIn(
            "not in the future",
            input_example["publicEvidenceRefSchema"]["capturedAtRequirement"],
        )
        self.assertIn("Store Submission Evidence Collector", collector_html)
        for marker in [
            "ExportOptions.plist.template",
            "android-signing.properties.template",
            "publish-config.template.json",
            "store-submission-evidence-collector.html",
            "import_store_submission_evidence.py --strict",
            "Structured public evidence refs",
            "public HTTPS URL",
            "not in the future",
            "build/store-submission-evidence/flavors",
            "Per-flavor input files take precedence",
            "store_submission_evidence_preflight.py",
            "## Per-Flavor Evidence Checklist",
            "build/store-submission-evidence/flavors/hongguo.input.json",
            "appStoreConnectRecordConfigured",
            "testFlightBuildUploaded",
            "build/store-submission-evidence/flavors/douyin.input.json",
            "directDistributionPolicyPublished",
            "build/store-submission-evidence/flavors/reelshort.input.json",
            "playInternalTrackUploaded",
        ]:
            self.assertIn(marker, operator_runbook)
        self.assertIn("douyin/store-submission-evidence.input.example.json", douyin_runbook)
        self.assertIn("build/store-submission-evidence/flavors/douyin.input.json", douyin_runbook)
        self.assertIn("Per-flavor input files take precedence", douyin_runbook)
        self.assertIn("build/store-signing-handoff/douyin/android-signing.properties.template", douyin_runbook)
        self.assertIn("build/store-publish-config/douyin/publish-config.template.json", douyin_runbook)
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, operator_runbook.lower())
            self.assertNotIn(marker, douyin_runbook.lower())
        self.assertIn(
            "./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            collector_html,
        )
        self.assertIn("Per-flavor input files take precedence", collector_html)
        self.assertIn("tenant_store_submission_public_evidence_input", collector_html)
        self.assertIn("testflight_uploaded", collector_html)
        self.assertIn("direct_signed_package_ready", collector_html)
        self.assertIn("Per-flavor JSON outputs", collector_html)
        self.assertIn("offline_tenant_public_evidence_form", collector_html)
        self.assertIn('data-evidence-form="hongguo"', collector_html)
        self.assertIn('data-generate-json', collector_html)
        self.assertIn('Ready to run preflight.', collector_html)
        self.assertIn('credentialFilePattern.test(JSON.stringify(document.submissions[0].publicEvidenceRefs))', collector_html)
        self.assertIn('data-flavor-json="hongguo"', collector_html)
        self.assertIn('download="hongguo.input.json"', collector_html)
        self.assertIn("build/store-submission-evidence/flavors/hongguo.input.json", collector_html)
        self.assertIn('data-flavor-json="douyin"', collector_html)
        self.assertIn('download="douyin.input.json"', collector_html)
        self.assertIn('data-flavor-json="hippo"', collector_html)
        self.assertIn('download="hippo.input.json"', collector_html)
        self.assertIn('data-flavor-json="reelshort"', collector_html)
        self.assertIn('download="reelshort.input.json"', collector_html)
        lowered = json.dumps(input_example, ensure_ascii=False).lower()
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)
            self.assertNotIn(marker, collector_html.lower())

    def test_store_submission_starter_export_is_parallel_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "build" / "store-submission-starter"

            def run_export(_: int) -> str:
                manifest = export_store_submission_starter.export_starter(root, output_dir)
                return manifest["packagePath"]

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                package_paths = list(pool.map(run_export, range(8)))

            self.assertEqual(
                ["build/store-submission-starter/mobile-store-submission-starter.zip"] * 8,
                package_paths,
            )
            self.assertTrue((output_dir / "store-submission-starter-manifest.json").exists())
            self.assertTrue((output_dir / "mobile-store-submission-starter.zip").exists())

    def test_completion_report_includes_ci_and_release_secret_gates(self) -> None:
        root = Path(__file__).resolve().parents[1]

        report = mobile_completion_audit.build_report(root, strict_ios=False)
        checks = {check["id"]: check for check in report["checks"]}
        workflow_path, _ = mobile_completion_audit.resolve_workflow_path(root)
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("ci_workflow", checks)
        self.assertIn(
            "scripts/download_ios_ci_artifacts.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/capture_wysiwyg_previews.mjs",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/export_external_account_handoff.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/import_store_submission_evidence.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/ios_runtime_smoke.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/store_submission_evidence_preflight.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn("ios_static_release_config", checks)
        self.assertIn("ios_ci_handoff_package", checks)
        self.assertIn("store_signing_handoff_package", checks)
        self.assertIn("store_publish_config_package", checks)
        self.assertIn("external_account_handoff_package", checks)
        self.assertIn("store_submission_starter_package", checks)
        self.assertIn("store_submission_evidence_preflight", checks)
        self.assertIn("ios_build_matrix", checks)
        self.assertIn("ios_ci_artifact_evidence", checks)
        self.assertIn("store_submission_evidence", checks)
        self.assertIn("completion_unblocker_package", checks)
        self.assertIn("github_publish_handoff_package", checks)
        self.assertIn("github_publication_evidence", checks)
        self.assertIn("store_handoff_manifest", checks)
        self.assertIn("store_assets_package", checks)
        self.assertIn("ui_preview_gallery", checks)
        self.assertIn("app_handoff_package", checks)
        self.assertIn("tenant_release_package", checks)
        self.assertIn("tenant_portal_release_handoff", checks)
        self.assertIn("prototype_responsive_viewports", checks)
        self.assertIn("mobile_open_source_release", checks)
        self.assertIn("mobile_open_source_package", checks)
        self.assertIn("release_artifact_secret_boundary", checks)
        self.assertEqual("passed", checks["ci_workflow"]["status"])
        self.assertEqual("passed", checks["ios_static_release_config"]["status"])
        self.assertEqual("passed", checks["ios_ci_handoff_package"]["status"])
        self.assertEqual("passed", checks["store_signing_handoff_package"]["status"])
        self.assertEqual("passed", checks["store_publish_config_package"]["status"])
        self.assertEqual("passed", checks["external_account_handoff_package"]["status"])
        self.assertEqual("passed", checks["store_submission_starter_package"]["status"])
        self.assertEqual("passed", checks["store_submission_evidence_preflight"]["status"])
        self.assertIn(checks["ios_build_matrix"]["status"], {"passed", "blocked"})
        self.assertIn(checks["ios_ci_artifact_evidence"]["status"], {"passed", "blocked"})
        self.assertIn(checks["store_submission_evidence"]["status"], {"passed", "blocked"})
        self.assertEqual("passed", checks["completion_unblocker_package"]["status"])
        self.assertEqual("passed", checks["github_publish_handoff_package"]["status"])
        self.assertIn(checks["github_publication_evidence"]["status"], {"passed", "blocked"})
        self.assertEqual("passed", checks["store_handoff_manifest"]["status"])
        self.assertEqual("passed", checks["store_assets_package"]["status"])
        self.assertEqual("passed", checks["ui_preview_gallery"]["status"])
        self.assertEqual("passed", checks["app_handoff_package"]["status"])
        self.assertEqual("passed", checks["tenant_release_package"]["status"])
        self.assertEqual("passed", checks["tenant_portal_release_handoff"]["status"])
        self.assertEqual("passed", checks["prototype_responsive_viewports"]["status"])
        self.assertEqual("passed", checks["mobile_open_source_release"]["status"])
        self.assertEqual("passed", checks["mobile_open_source_package"]["status"])
        self.assertIn(
            "360, 390, 430, and iPad-width",
            checks["prototype_responsive_viewports"]["detail"],
        )
        self.assertIn(
            "Apache-2.0 licensed mobile template",
            checks["mobile_open_source_release"]["detail"],
        )
        self.assertIn(
            "GitHub-ready open-source template zip",
            checks["mobile_open_source_package"]["detail"],
        )
        self.assertIn(
            "40 publish-safe screenshots",
            checks["store_assets_package"]["detail"],
        )
        self.assertIn(
            "offline HTML preview gallery",
            checks["ui_preview_gallery"]["detail"],
        )
        self.assertIn(
            "per-flavor tenant app handoff",
            checks["app_handoff_package"]["detail"],
        )
        self.assertIn(
            "completion closure report",
            checks["app_handoff_package"]["detail"],
        )
        self.assertIn(
            "manual GitHub Actions trigger",
            checks["ios_ci_handoff_package"]["detail"],
        )
        self.assertIn(
            "iOS export-options templates",
            checks["store_signing_handoff_package"]["detail"],
        )
        self.assertIn(
            "tenant-fillable App Store",
            checks["store_publish_config_package"]["detail"],
        )
        self.assertIn(
            "Apple, Google Play, Android direct, OAuth, consumer payment, and legal review",
            checks["external_account_handoff_package"]["detail"],
        )
        self.assertIn(
            "remote config template override",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "payment options compliance mismatch",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "native compliance cap",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "point card compliance entry guards",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "external payment enablement gate",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "offline payment proof reference",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "mine payment entry guards",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "oauth provider deep-link guards",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "home search routing",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "share deep link routing",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "share deep link public detail resolution",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "share deep link duplicate guard",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "catalog initial query filtering",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "account sign-out",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "player episode list sheet",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "player tenant-safe share sheet",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "player friendly playback error copy",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "playback token refresh idempotency",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "point card friendly redeem error copy",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "wallet friendly payment error copy",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "auth friendly error copy",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "library entry navigation",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "tenant release package",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "app handoff package",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "embedded input workspace",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "external account handoff checklist",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "completion closure report",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "store submission status summary",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "human-readable release guide",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "tenant release archive",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "Tenant portal exports release handoff metadata",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "external account/signing config entry points",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "generated handoff artifact references",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "release package references",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "PNG review boards",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "completion unblocker fix queue",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "completion closure report",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "actionable fix queue handoff",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "per-flavor evidence gap summary",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "tenant release archive",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "strict import readiness",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "evidence input draft",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "all-flavor evidence draft workspace",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "evidence import runbook",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "evidence workspace handoff",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "evidence completion receipt",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "evidence remediation matrix",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "store submission evidence checklist",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "store submission evidence collector",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "store submission evidence packet",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        tenant_portal_main = (root.parent / "apps" / "tenant-portal" / "src" / "main.tsx").read_text(
            encoding="utf-8",
        )
        self.assertIn("商店提交证据清单", tenant_portal_main)
        self.assertIn("完整 App 完成阻断", tenant_portal_main)
        self.assertIn("完成阻断清单", tenant_portal_main)
        self.assertIn("完成阻断指南", tenant_portal_main)
        self.assertIn("完成收口报告", tenant_portal_main)
        self.assertIn("完成收口指南", tenant_portal_main)
        self.assertIn("完成阻断修复队列", tenant_portal_main)
        self.assertIn("外部账号与签名资料接入入口", tenant_portal_main)
        self.assertIn("外部账号清单", tenant_portal_main)
        self.assertIn("外部账号指南", tenant_portal_main)
        self.assertIn("外部账号交接包", tenant_portal_main)
        self.assertIn("appExternalStoreAccountConfig", tenant_portal_main)
        self.assertIn("externalAccountHandoffManifest", tenant_portal_main)
        self.assertIn("externalAccountHandoffGuide", tenant_portal_main)
        self.assertIn("externalAccountHandoffPackage", tenant_portal_main)
        self.assertIn("completionClosureReport", tenant_portal_main)
        self.assertIn("completionClosureGuide", tenant_portal_main)
        self.assertIn("externalConfigEvidenceInput", tenant_portal_main)
        self.assertIn("修复队列说明", tenant_portal_main)
        self.assertIn("修复队列行数", tenant_portal_main)
        self.assertIn("修复后导入命令", tenant_portal_main)
        self.assertIn("证据输入草稿", tenant_portal_main)
        self.assertIn("多套模板证据草稿", tenant_portal_main)
        self.assertIn("证据导入操作流", tenant_portal_main)
        self.assertIn("证据工作区交接", tenant_portal_main)
        self.assertIn("导入验收回执", tenant_portal_main)
        self.assertIn("证据修复矩阵", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceDraft", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceDraftWorkspace", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceRemediationMatrix", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceImportRunbook", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceWorkspaceHandoff", tenant_portal_main)
        self.assertIn("storeSubmissionEvidenceCompletionReceipt", tenant_portal_main)
        self.assertIn("tenant_store_submission_evidence_remediation_matrix", tenant_portal_main)
        self.assertIn("tenant_store_submission_evidence_import_runbook", tenant_portal_main)
        self.assertIn("tenant_store_submission_evidence_workspace_handoff", tenant_portal_main)
        self.assertIn("tenant_store_submission_evidence_completion_receipt", tenant_portal_main)
        self.assertIn("remediationSteps", tenant_portal_main)
        self.assertIn("acceptedPublicEvidence", tenant_portal_main)
        self.assertIn("forbiddenEvidence", tenant_portal_main)
        self.assertIn("tenant_store_submission_public_evidence_draft_workspace", tenant_portal_main)
        self.assertIn("tenant_store_submission_public_evidence_input_draft", tenant_portal_main)
        self.assertIn("strictImportReady", tenant_portal_main)
        self.assertIn("blockedInputPath", tenant_portal_main)
        self.assertIn("workspaceManifestPath", tenant_portal_main)
        self.assertIn("workspaceGuidePath", tenant_portal_main)
        self.assertIn("tenantFillTargets", tenant_portal_main)
        self.assertIn("copyableCommands", tenant_portal_main)
        self.assertIn("acceptedDecision", tenant_portal_main)
        self.assertIn("requiredAuditChecks", tenant_portal_main)
        self.assertIn("requiredEvidenceFields", tenant_portal_main)
        self.assertIn("rejectedEvidenceStates", tenant_portal_main)
        self.assertIn("prepareWorkspaceCommand", tenant_portal_main)
        self.assertIn("completionAuditCommand", tenant_portal_main)
        self.assertIn("finalExpectedDecision", tenant_portal_main)
        self.assertIn("租户发布包指南", tenant_portal_main)
        self.assertIn("租户发布包归档", tenant_portal_main)
        self.assertIn("UI 可读 PNG", tenant_portal_main)
        self.assertIn("UI 全屏 PNG", tenant_portal_main)
        self.assertIn("uiPreviewReadableOverviewPng", tenant_portal_main)
        self.assertIn("uiPreviewContactSheetPng", tenant_portal_main)
        self.assertIn("租户提交证据包", tenant_portal_main)
        self.assertIn("证据收集页", tenant_portal_main)
        self.assertIn("完成阻断清单", tenant_portal_main)
        self.assertIn("完成阻断指南", tenant_portal_main)
        self.assertIn("完成收口报告", tenant_portal_main)
        self.assertIn("完成收口指南", tenant_portal_main)
        self.assertIn("完成阻断修复队列", tenant_portal_main)
        self.assertIn("修复队列摘要", tenant_portal_main)
        self.assertIn("修复队列说明", tenant_portal_main)
        self.assertIn("修复队列行数", tenant_portal_main)
        self.assertIn("修复后导入命令", tenant_portal_main)
        self.assertIn("storeEvidenceFixQueueHandoff", tenant_portal_main)
        self.assertIn("tenant_store_evidence_fix_queue_handoff", tenant_portal_main)
        self.assertIn("totalRowCount", tenant_portal_main)
        self.assertIn("queue.rows", tenant_portal_main)
        self.assertIn("storeEvidenceFixQueueCsv", tenant_portal_main)
        self.assertIn("storeEvidenceFixQueueRowCount", tenant_portal_main)
        self.assertIn("模板证据缺口", tenant_portal_main)
        self.assertIn("blockedFieldCount", tenant_portal_main)
        self.assertIn("baseRequiredFieldCount", tenant_portal_main)
        self.assertIn("channelRequiredFieldCount", tenant_portal_main)
        self.assertIn("evidenceMetadataFieldCount", tenant_portal_main)
        self.assertIn("completionPercent", tenant_portal_main)
        self.assertIn("nextBlockingField", tenant_portal_main)
        self.assertIn("queueNextAction", tenant_portal_main)

        gallery_manifest_path = root / "build" / "ui-preview-gallery" / "ui-preview-gallery-manifest.json"
        gallery_manifest = json.loads(gallery_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("mobile_ui_preview_gallery", gallery_manifest["packageType"])
        self.assertEqual(40, gallery_manifest["screenshotCount"])
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-readable-overview.png",
            gallery_manifest["readableOverviewPng"]["path"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
            gallery_manifest["contactSheetPng"]["path"],
        )
        self.assertEqual([], gallery_manifest["disallowedValueMarkerHits"])
        self.assertRegex(gallery_manifest["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertIn("allowedStatuses", tenant_portal_main)
        self.assertIn("requiredFlags", tenant_portal_main)
        self.assertIn("publicEvidenceExamples", tenant_portal_main)
        self.assertIn("publicEvidenceRefSchema", tenant_portal_main)
        self.assertIn("结构化证据字段", tenant_portal_main)
        self.assertIn("公网 HTTPS", tenant_portal_main)
        self.assertIn("ISO-8601", tenant_portal_main)
        self.assertIn("perFlavorImportCommand", tenant_portal_main)
        self.assertIn("分模板导入", tenant_portal_main)
        self.assertIn("importCommand", tenant_portal_main)
        self.assertIn("combinedImportCommand", tenant_portal_main)
        self.assertIn("分模板输入优先", tenant_portal_main)
        self.assertIn("publicBoundary", tenant_portal_main)
        self.assertIn("模板选择矩阵", tenant_portal_main)
        self.assertIn("templateOptions", tenant_portal_main)
        self.assertIn("setPreviewTemplate", tenant_portal_main)
        self.assertIn("defaultStoreComplianceMode", tenant_portal_main)
        self.assertIn(
            './scripts/build_flavor.sh "${{ matrix.flavor }}" android release apk',
            workflow,
        )
        self.assertIn("xcodebuild -version", workflow)
        self.assertIn("pod --version", workflow)
        self.assertIn(
            './scripts/build_flavor.sh "${{ matrix.flavor }}" ios release',
            workflow,
        )
        self.assertIn("./scripts/write_store_handoff_manifest.py", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("mobile-template-handoff", workflow)
        self.assertIn("mobile-ios-ci-handoff.zip", workflow)
        self.assertIn("mobile-store-signing-handoff.zip", workflow)
        self.assertIn("mobile-store-publish-config.zip", workflow)
        self.assertIn(
            "build/store-submission-evidence/store-submission-evidence.template.json",
            checks["store_submission_evidence"]["evidence"],
        )
        self.assertIn(
            "build/store-submission-evidence/store-submission-evidence-preflight.json",
            checks["store_submission_evidence_preflight"]["evidence"],
        )
        preflight_report = json.loads(
            (root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json").read_text(
                encoding="utf-8",
            ),
        )
        self.assertIn("public HTTPS URL", " ".join(preflight_report["qualityRules"]))
        self.assertIn("ISO-8601", " ".join(preflight_report["qualityRules"]))
        self.assertIn(
            "build/completion-unblocker/mobile-completion-unblocker.json",
            checks["completion_unblocker_package"]["evidence"],
        )
        self.assertIn(
            "build/github-publish/github-publish-manifest.json",
            checks["github_publish_handoff_package"]["evidence"],
        )
        self.assertIn(
            "build/github-publish/github-publication-evidence.json",
            checks["github_publication_evidence"]["evidence"],
        )
        self.assertIn("mobile-${{ matrix.flavor }}-ios-unsigned", workflow)
        self.assertIn("ios-ci-evidence:", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("pattern: mobile-*-ios-unsigned", workflow)
        self.assertIn("python3 scripts/import_ios_ci_artifacts.py --strict", workflow)
        self.assertIn("mobile-ios-ci-artifact-evidence", workflow)
        self.assertIn("store publish config handoff upload", checks["ci_workflow"]["detail"])
        self.assertIn("automated unsigned iOS artifact evidence import", checks["ci_workflow"]["detail"])
        self.assertIn("five-flavor unsigned iOS release builds", checks["ci_workflow"]["detail"])

    def test_completion_unblocker_package_exports_external_action_plan(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_completion_unblocker_package(root)
        manifest_path = root / "build" / "completion-unblocker" / "mobile-completion-unblocker.json"
        markdown_path = root / "build" / "completion-unblocker" / "mobile-completion-unblocker.md"
        fix_queue_csv_path = root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.csv"
        fix_queue_markdown_path = root / "build" / "completion-unblocker" / "mobile-store-evidence-fix-queue.md"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertTrue(fix_queue_csv_path.exists())
        self.assertTrue(fix_queue_markdown_path.exists())
        fix_queue_rows = list(csv.DictReader(fix_queue_csv_path.read_text(encoding="utf-8").splitlines()))
        fix_queue_markdown = fix_queue_markdown_path.read_text(encoding="utf-8")

        self.assertEqual("completion_unblocker_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/completion-unblocker/mobile-completion-unblocker.json", check.evidence)
        self.assertIn("build/completion-unblocker/mobile-completion-unblocker.md", check.evidence)
        self.assertIn("build/completion-unblocker/mobile-store-evidence-fix-queue.csv", check.evidence)
        self.assertIn("build/completion-unblocker/mobile-store-evidence-fix-queue.md", check.evidence)
        self.assertEqual("mobile_completion_unblocker", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertEqual(
            {
                "csvPath": "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
                "markdownPath": "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
                "strictImportCommand": "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
                "columns": [
                    "flavor",
                    "inputPath",
                    "field",
                    "tenantAction",
                    "acceptedPublicEvidence",
                    "forbiddenEvidence",
                ],
                "rowCount": len(fix_queue_rows),
            },
            manifest["storeEvidenceFixQueue"],
        )
        self.assertGreater(manifest["storeEvidenceFixQueue"]["rowCount"], 0)
        self.assertEqual(
            [
                "flavor",
                "inputPath",
                "field",
                "tenantAction",
                "acceptedPublicEvidence",
                "forbiddenEvidence",
            ],
            list(fix_queue_rows[0]),
        )
        self.assertEqual(
            [
                "install_full_xcode",
                "import_unsigned_ios_ci_artifacts",
                "import_store_submission_evidence",
            ],
            [action["id"] for action in manifest["actions"]],
        )
        commands = "\n".join(
            command
            for action in manifest["actions"]
            for command in action["commands"]
        )
        self.assertIn("scripts/ios_build_matrix.py all --strict", commands)
        self.assertIn("scripts/mobile_completion_closure.py --repo <owner/repo>", commands)
        self.assertIn("scripts/download_ios_ci_artifacts.py --repo <owner/repo>", commands)
        self.assertIn("scripts/export_store_submission_starter.py", commands)
        self.assertIn("scripts/prepare_store_submission_inputs.py", commands)
        self.assertIn("scripts/store_submission_evidence_preflight.py", commands)
        self.assertIn("scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict", commands)
        self.assertIn("scripts/import_store_submission_evidence.py --strict", commands)
        self.assertIn("scripts/mobile_completion_closure.py --skip-ios-ci-download", commands)
        store_action = next(
            action
            for action in manifest["actions"]
            if action["id"] == "import_store_submission_evidence"
        )
        self.assertFalse(store_action["strictImportReadiness"]["ready"])
        self.assertEqual(
            "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            store_action["strictImportReadiness"]["command"],
        )
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            len(store_action["strictImportReadiness"]["blockedBy"]),
        )
        self.assertIn(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            store_action["blockedInputPaths"],
        )
        blocked_by_flavor = {
            row["flavor"]: row
            for row in store_action["strictImportReadiness"]["blockedBy"]
        }
        self.assertTrue(blocked_by_flavor["hongguo"]["blockers"])
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            len(store_action["fieldRemediation"]),
        )
        field_remediation_by_flavor = {
            row["flavor"]: row
            for row in store_action["fieldRemediation"]
        }
        self.assertIn("hongguo", field_remediation_by_flavor)
        self.assertEqual(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            store_action["fieldRemediation"][0]["inputPath"],
        )
        hongguo_remediation = field_remediation_by_flavor["hongguo"]
        self.assertIn("appStoreConnectRecordConfigured", [
            step["field"] for step in hongguo_remediation["remediationSteps"]
        ])
        app_store_step = next(
            step
            for step in hongguo_remediation["remediationSteps"]
            if step["field"] == "appStoreConnectRecordConfigured"
        )
        app_store_queue_row = next(
            row
            for row in fix_queue_rows
            if row["flavor"] == "hongguo"
            and row["field"] == "appStoreConnectRecordConfigured"
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            app_store_queue_row["inputPath"],
        )
        self.assertIn("App Store Connect", app_store_queue_row["tenantAction"])
        self.assertTrue(app_store_queue_row["acceptedPublicEvidence"])
        self.assertTrue(app_store_queue_row["forbiddenEvidence"])
        self.assertIn("App Store Connect", app_store_step["tenantAction"])
        self.assertTrue(app_store_step["acceptedPublicEvidence"])
        self.assertTrue(app_store_step["forbiddenEvidence"])
        self.assertIn("tenantAction", json.dumps(store_action["fieldRemediation"], ensure_ascii=False))
        self.assertIn("acceptedPublicEvidence", json.dumps(store_action["fieldRemediation"], ensure_ascii=False))
        self.assertIn("forbiddenEvidence", json.dumps(store_action["fieldRemediation"], ensure_ascii=False))
        self.assertIn("npm run infra:mobile-app-completion-audit", manifest["completionGateCommand"])
        self.assertIn("build/store-submission-evidence/store-submission-evidence.guide.md", json.dumps(manifest))
        self.assertIn("build/store-submission-evidence/store-submission-input-workspace.json", json.dumps(manifest))
        self.assertIn("build/store-submission-evidence/store-submission-evidence-preflight.json", json.dumps(manifest))
        self.assertIn("build/store-submission-starter/store-submission-operator-runbook.md", json.dumps(manifest))
        self.assertIn("store-submission-operator-runbook.md", markdown)
        self.assertIn("Strict import ready: `False`", markdown)
        self.assertIn("build/store-submission-evidence/flavors/hongguo.input.json", markdown)
        self.assertIn("Field remediation:", markdown)
        self.assertIn("Store evidence fix queue:", markdown)
        self.assertIn("mobile-store-evidence-fix-queue.csv", markdown)
        self.assertIn("# Mobile Store Evidence Fix Queue", fix_queue_markdown)
        self.assertIn("appStoreConnectRecordConfigured", fix_queue_markdown)
        self.assertIn("Tenant action", fix_queue_markdown)
        self.assertIn("Accepted public evidence", fix_queue_markdown)
        self.assertIn("Forbidden evidence", fix_queue_markdown)
        self.assertIn("rerun the strict import command", fix_queue_markdown)
        self.assertIn("appStoreConnectRecordConfigured", markdown)
        self.assertIn("Tenant action:", markdown)
        self.assertIn("Accepted public evidence:", markdown)
        self.assertIn("Forbidden evidence:", markdown)
        self.assertIn("Per-flavor input files take precedence", json.dumps(manifest))
        self.assertIn("Per-flavor input files take precedence", markdown)
        self.assertIn("# Mobile Completion Unblocker", markdown)
        lowered = (
            json.dumps(manifest, ensure_ascii=False).lower()
            + markdown.lower()
            + fix_queue_csv_path.read_text(encoding="utf-8").lower()
            + fix_queue_markdown.lower()
        )
        for marker in export_completion_unblocker.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_mobile_completion_closure_summarizes_remaining_external_blockers(self) -> None:
        audit = {
            "appCompletion": "blocked",
            "summary": {"passed": 24, "missing": 0, "failed": 0, "blocked": 2},
            "checks": [
                {"id": "theme_templates", "status": "passed", "detail": "ok"},
                {
                    "id": "ios_build_matrix",
                    "status": "blocked",
                    "detail": "Local Xcode is unavailable but CI iOS evidence passed.",
                    "evidence": ["build/ios-build-matrix/ios-build-matrix.json"],
                    "completionBlocking": False,
                },
                {
                    "id": "ios_ci_artifact_evidence",
                    "status": "blocked",
                    "detail": "Unsigned iOS CI artifacts are missing.",
                    "evidence": ["build/ios-ci-evidence/ios-ci-artifacts.json"],
                },
                {
                    "id": "store_submission_evidence",
                    "status": "blocked",
                    "detail": "Tenant store submission evidence is missing.",
                    "evidence": ["build/store-submission-evidence/store-submission-evidence.json"],
                },
            ],
        }

        with mock.patch.object(
            mobile_completion_closure,
            "store_submission_remediation_hints",
            return_value=[
                {
                    "flavor": "hongguo",
                    "blockers": ["input-evidence-missing"],
                    "hints": [
                        "Copy build/store-submission-starter/hongguo/store-submission-evidence.input.example.json to build/store-submission-evidence/flavors/hongguo.input.json.",
                    ],
                },
            ],
        ):
            report = mobile_completion_closure.build_report(
                [{"command": "python3 scripts/mobile_completion_audit.py", "exitCode": 0}],
                audit,
            )

        self.assertFalse(report["canClaimComplete"])
        self.assertEqual("blocked", report["appCompletion"])
        self.assertEqual(
            ["ios_ci_artifact_evidence", "store_submission_evidence"],
            [blocker["id"] for blocker in report["blockers"]],
        )
        self.assertNotIn("ios_build_matrix", [blocker["id"] for blocker in report["blockers"]])
        self.assertIn("GITHUB_REPOSITORY", report["blockers"][0]["nextAction"])
        self.assertIn("store-submission-evidence.input.json", report["blockers"][1]["nextAction"])
        self.assertIn("build/store-submission-evidence/flavors", report["blockers"][1]["nextAction"])
        self.assertIn("store-submission-operator-runbook.md", report["blockers"][1]["nextAction"])
        self.assertEqual("hongguo", report["blockers"][1]["remediationHints"][0]["flavor"])
        self.assertIn(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            report["blockers"][1]["remediationHints"][0]["hints"][0],
        )
        self.assertIn(
            "build/store-submission-starter/store-submission-operator-runbook.md",
            report["blockers"][1]["evidence"],
        )
        lowered = json.dumps(report, ensure_ascii=False).lower()
        for marker in export_completion_unblocker.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_mobile_completion_closure_refreshes_store_submission_starter_before_import(self) -> None:
        self.assertEqual(
            ["python3", "scripts/export_store_submission_starter.py"],
            mobile_completion_closure.store_submission_starter_refresh_command(),
        )

    def test_mobile_completion_closure_markdown_includes_store_remediation_hints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "mobile-completion-closure.md"
            report = {
                "generatedAt": "2026-06-14T00:00:00Z",
                "appCompletion": "incomplete",
                "summary": {"passed": 31, "missing": 0, "failed": 0, "blocked": 1},
                "canClaimComplete": False,
                "steps": [],
                "blockers": [
                    {
                        "id": "store_submission_evidence",
                        "detail": "missing flavors: hongguo",
                        "nextAction": "Run per-flavor strict import.",
                        "remediationHints": [
                            {
                                "flavor": "hongguo",
                                "blockers": ["input-evidence-missing"],
                                "hints": [
                                    "Copy build/store-submission-starter/hongguo/store-submission-evidence.input.example.json to build/store-submission-evidence/flavors/hongguo.input.json.",
                                ],
                            },
                        ],
                    },
                ],
            }

            mobile_completion_closure.write_markdown(report, output)
            markdown = output.read_text(encoding="utf-8")

        self.assertIn("Remediation Hints", markdown)
        self.assertIn("hongguo", markdown)
        self.assertIn("input-evidence-missing", markdown)
        self.assertIn("build/store-submission-evidence/flavors/hongguo.input.json", markdown)

    def test_mobile_completion_closure_imports_per_flavor_store_evidence_by_default(self) -> None:
        args = argparse.Namespace(
            store_submission_source=None,
            store_submission_source_dir=None,
        )

        self.assertEqual(
            [
                "python3",
                "scripts/import_store_submission_evidence.py",
                "--source-dir",
                "build/store-submission-evidence/flavors",
            ],
            mobile_completion_closure.store_submission_import_command(args),
        )

    def test_mobile_completion_closure_refreshes_store_submission_preflight(self) -> None:
        self.assertEqual(
            ["python3", "scripts/store_submission_evidence_preflight.py"],
            mobile_completion_closure.store_submission_preflight_command(),
        )

    def test_mobile_completion_closure_auto_downloads_when_repo_is_resolved(self) -> None:
        args = argparse.Namespace(
            repo=None,
            run_id="123456789",
            branch="main",
            skip_ios_ci_download=False,
        )
        with mock.patch.dict(
            os.environ,
            {"GITHUB_REPOSITORY": "tokenstarai/short-drama-saas"},
        ):
            command = mobile_completion_closure.ios_ci_refresh_command(args)

        self.assertEqual(
            [
                "python3",
                "scripts/download_ios_ci_artifacts.py",
                "--repo",
                "tokenstarai/short-drama-saas",
                "--run-id",
                "123456789",
                "--branch",
                "main",
            ],
            command,
        )

    def test_mobile_completion_closure_falls_back_to_local_ios_artifact_import(self) -> None:
        args = argparse.Namespace(
            repo=None,
            run_id=None,
            branch=None,
            skip_ios_ci_download=False,
        )
        with mock.patch.object(download_ios_ci_artifacts, "resolve_repo", return_value=None):
            command = mobile_completion_closure.ios_ci_refresh_command(args)

        self.assertEqual(["python3", "scripts/import_ios_ci_artifacts.py"], command)

    def test_github_publish_handoff_package_exports_no_secret_publish_plan(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_github_publish_handoff_package(root)
        manifest_path = root / "build" / "github-publish" / "github-publish-manifest.json"
        guide_path = root / "build" / "github-publish" / "github-publish-guide.md"
        notes_path = root / "build" / "github-publish" / "github-release-notes.md"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        guide = guide_path.read_text(encoding="utf-8")
        notes = notes_path.read_text(encoding="utf-8")

        self.assertEqual("github_publish_handoff_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/github-publish/github-publish-manifest.json", check.evidence)
        self.assertIn("build/github-publish/github-publish-guide.md", check.evidence)
        self.assertEqual("mobile_github_publish_handoff", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertEqual("short-drama-whitelabel-mobile", manifest["repositoryTemplate"]["name"])
        self.assertEqual("Apache-2.0", manifest["repositoryTemplate"]["license"])
        self.assertTrue(manifest["repositoryTemplate"]["publicByDefault"])
        self.assertEqual(
            "build/open-source/short-drama-whitelabel-mobile.zip",
            manifest["sourcePackage"]["path"],
        )
        self.assertRegex(manifest["sourcePackage"]["sha256"], r"^[a-f0-9]{64}$")
        commands = "\n".join(manifest["publishCommands"])
        self.assertIn("python3 scripts/export_open_source_template.py", commands)
        self.assertIn("gh repo create <owner>/short-drama-whitelabel-mobile --public", commands)
        self.assertIn("gh release create mobile-template-v0.1.0", commands)
        self.assertIn("build/open-source/open-source-template-manifest.json", commands)
        self.assertIn("# GitHub Publish Handoff", guide)
        self.assertIn("short-drama-whitelabel-mobile", notes)
        lowered = json.dumps(manifest, ensure_ascii=False).lower() + guide.lower() + notes.lower()
        for marker in export_github_publish_handoff.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_github_publication_evidence_gate_validates_public_repo_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "github-publish"
            evidence_path = evidence_dir / "github-publication-evidence.json"
            evidence_dir.mkdir(parents=True)
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "repository": {
                        "nameWithOwner": "tokenstarai/short-drama-whitelabel-mobile",
                        "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile",
                        "visibility": "PUBLIC",
                        "defaultBranch": "main",
                        "pushedCommit": "5e730fe",
                    },
                    "release": {
                        "tagName": "mobile-template-v0.1.0",
                        "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/tag/mobile-template-v0.1.0",
                        "isDraft": False,
                        "isPrerelease": False,
                    },
                    "assets": [
                        {
                            "name": "short-drama-whitelabel-mobile.zip",
                            "contentType": "application/zip",
                            "sizeBytes": 123,
                            "downloadUrl": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/download/mobile-template-v0.1.0/short-drama-whitelabel-mobile.zip",
                            "remoteDigestSha256": "a" * 64,
                            "digestMatchesLocal": True,
                        },
                        {
                            "name": "open-source-template-manifest.json",
                            "contentType": "application/json",
                            "sizeBytes": 456,
                            "downloadUrl": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/download/mobile-template-v0.1.0/open-source-template-manifest.json",
                            "remoteDigestSha256": "b" * 64,
                            "digestMatchesLocal": True,
                        },
                    ],
                    "sourcePackageSha256": "a" * 64,
                    "sourceManifestSha256": "b" * 64,
                    "disallowedValueMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_github_publication_evidence(root)

        self.assertEqual("github_publication_evidence", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/github-publish/github-publication-evidence.json", check.evidence)

    def test_github_publication_evidence_importer_normalizes_public_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
            manifest = root / "build" / "open-source" / "open-source-template-manifest.json"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"zip")
            manifest.write_text("{}", encoding="utf-8")
            package_sha = hashlib.sha256(package.read_bytes()).hexdigest()
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()

            report = import_github_publication_evidence.build_report(
                root=root,
                repo_info={
                    "nameWithOwner": "tokenstarai/short-drama-whitelabel-mobile",
                    "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile",
                    "visibility": "PUBLIC",
                    "defaultBranchRef": {"name": "main", "target": {"oid": "abc123"}},
                },
                release_info={
                    "tagName": "mobile-template-v0.1.0",
                    "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/tag/mobile-template-v0.1.0",
                    "isDraft": False,
                    "isPrerelease": False,
                    "assets": [
                        {
                            "name": "short-drama-whitelabel-mobile.zip",
                            "contentType": "application/zip",
                            "size": 123,
                            "digest": "sha256:" + package_sha,
                            "url": "https://github.com/download/short-drama-whitelabel-mobile.zip",
                        },
                        {
                            "name": "open-source-template-manifest.json",
                            "contentType": "application/json",
                            "size": 456,
                            "digest": "sha256:" + manifest_sha,
                            "url": "https://github.com/download/open-source-template-manifest.json",
                        },
                    ],
                },
            )

        self.assertEqual("passed", report["result"])
        self.assertEqual("main", report["repository"]["defaultBranch"])
        self.assertEqual("abc123", report["repository"]["pushedCommit"])
        self.assertEqual("mobile-template-v0.1.0", report["release"]["tagName"])
        self.assertEqual(["open-source-template-manifest.json", "short-drama-whitelabel-mobile.zip"], sorted(asset["name"] for asset in report["assets"]))
        self.assertTrue(all(asset["digestMatchesLocal"] for asset in report["assets"]))
        self.assertRegex(report["sourcePackageSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(report["sourceManifestSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual([], report["disallowedValueMarkerHits"])

    def test_github_publication_evidence_importer_blocks_mismatched_release_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
            manifest = root / "build" / "open-source" / "open-source-template-manifest.json"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"zip")
            manifest.write_text("{}", encoding="utf-8")
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()

            report = import_github_publication_evidence.build_report(
                root=root,
                repo_info={
                    "nameWithOwner": "tokenstarai/short-drama-whitelabel-mobile",
                    "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile",
                    "visibility": "PUBLIC",
                    "defaultBranchRef": {"name": "main", "target": {"oid": "abc123"}},
                },
                release_info={
                    "tagName": "mobile-template-v0.1.0",
                    "url": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/tag/mobile-template-v0.1.0",
                    "isDraft": False,
                    "isPrerelease": False,
                    "assets": [
                        {
                            "name": "short-drama-whitelabel-mobile.zip",
                            "contentType": "application/zip",
                            "size": 123,
                            "digest": "sha256:" + ("0" * 64),
                            "url": "https://github.com/download/short-drama-whitelabel-mobile.zip",
                        },
                        {
                            "name": "open-source-template-manifest.json",
                            "contentType": "application/json",
                            "size": 456,
                            "digest": "sha256:" + manifest_sha,
                            "url": "https://github.com/download/open-source-template-manifest.json",
                        },
                    ],
                },
            )

        self.assertEqual("blocked", report["result"])
        self.assertIn(
            "asset:short-drama-whitelabel-mobile.zip:remoteDigestSha256",
            report["blockers"],
        )

    def test_open_source_package_uses_standalone_github_actions_paths(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package_path = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"

        with zipfile.ZipFile(package_path) as archive:
            workflow = archive.read(
                "short-drama-whitelabel-mobile/.github/workflows/mobile-flutter.yml",
            ).decode("utf-8")

        self.assertNotIn("working-directory: mobile", workflow)
        self.assertNotIn('"mobile/**"', workflow)
        self.assertNotIn("mobile/build/", workflow)
        self.assertIn("working-directory: .", workflow)
        self.assertIn("build/open-source/short-drama-whitelabel-mobile.zip", workflow)

    def test_open_source_package_uses_root_secret_safe_gitignore(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package_path = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"

        with zipfile.ZipFile(package_path) as archive:
            gitignore = archive.read("short-drama-whitelabel-mobile/.gitignore").decode(
                "utf-8",
            )

        self.assertIn(".env", gitignore)
        self.assertIn(".env.*", gitignore)
        self.assertIn(".dev.vars", gitignore)
        self.assertIn("!.env.example", gitignore)
        self.assertIn("build/", gitignore)

    def test_ios_ci_handoff_resolves_standalone_workflow_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = root / ".github" / "workflows" / "mobile-flutter.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: Mobile Flutter\nworkflow_dispatch:\n", encoding="utf-8")

            resolved = export_ios_ci_handoff.resolve_workflow_path(root)

        self.assertEqual(workflow, resolved)

    def test_ios_build_script_uses_xcconfig_selection_without_flutter_flavor_flag(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "build_flavor.sh").read_text(encoding="utf-8")

        self.assertIn('cp "$source_config" "$ios_config"', script)
        self.assertIn('"$flutter_bin" --no-version-check build ios "--$mode" --no-codesign --dart-define="APP_FLAVOR=$flavor"', script)
        self.assertNotIn('"$flutter_bin" build ios "--$mode" --flavor "$flavor"', script)

    def test_ios_ci_importer_accepts_downloaded_artifact_bundle_contents(self) -> None:
        root = Path(__file__).resolve().parents[1]
        build_root = root / "build"
        build_root.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=build_root) as temp_dir:
            temp_root = Path(temp_dir)
            source_dir = temp_root / "ci-ios"
            output = temp_root / "ios-ci-evidence" / "ios-ci-artifacts.json"
            info_dir = temp_root / "ios-ci-evidence" / "app-info"
            for flavor, expected in import_ios_ci_artifacts.FLAVORS.items():
                app_contents = source_dir / expected["artifactName"]
                app_contents.mkdir(parents=True)
                with (app_contents / "Info.plist").open("wb") as target:
                    plistlib.dump(
                        {
                            "CFBundleIdentifier": expected["applicationId"],
                            "CFBundleDisplayName": expected["appName"],
                            "CFBundleVersion": "1",
                            "CFBundleShortVersionString": "0.1.0",
                        },
                        target,
                    )

            report = import_ios_ci_artifacts.import_artifacts(
                source_dir,
                output,
                info_dir,
            )

        self.assertEqual("passed", report["result"])
        self.assertEqual([], report["missingFlavors"])
        self.assertEqual(set(import_ios_ci_artifacts.FLAVORS), {run["flavor"] for run in report["runs"]})

    def test_open_source_package_keeps_ci_scripts_executable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        output_dir = root / "build" / "open-source"
        package_path = output_dir / "short-drama-whitelabel-mobile.zip"
        manifest_path = output_dir / "open-source-template-manifest.json"
        entries = export_open_source_template.iter_entries()
        export_open_source_template.write_package(entries, package_path)
        manifest = export_open_source_template.build_manifest(entries, package_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        with zipfile.ZipFile(package_path) as archive:
            modes = {
                script: (archive.getinfo(f"short-drama-whitelabel-mobile/{script}").external_attr >> 16) & 0o777
                for script in [
                    "scripts/check_mobile.sh",
                    "scripts/build_flavor.sh",
                    "scripts/check_native_config.sh",
                    "scripts/capture_wysiwyg_previews.mjs",
                    "scripts/write_store_handoff_manifest.py",
                    "scripts/export_open_source_template.py",
                    "scripts/import_ios_ci_artifacts.py",
                ]
            }

        for script, mode in modes.items():
            self.assertEqual(0o755, mode, script)

    def test_open_source_secret_scan_ignores_scanner_patterns_in_ui_preview_exporter(self) -> None:
        root = Path(__file__).resolve().parents[1]

        hits = export_open_source_template.disallowed_value_hits([
            ("scripts/capture_wysiwyg_previews.mjs", root / "scripts" / "capture_wysiwyg_previews.mjs"),
            ("scripts/export_ui_preview_gallery.py", root / "scripts" / "export_ui_preview_gallery.py"),
        ])

        self.assertEqual([], hits)

    def test_wysiwyg_capture_script_documents_reproducible_runtime_capture(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts" / "capture_wysiwyg_previews.mjs").read_text(encoding="utf-8")

        self.assertIn("lib/preview_main.dart", script)
        self.assertIn("APP_FLAVOR=", script)
        self.assertIn("chromium.launch", script)
        self.assertIn("deviceScaleFactor: 2", script)
        self.assertIn("waitForFlutterView", script)
        self.assertIn("domcontentloaded", script)
        self.assertIn("minSizeBytes", script)
        self.assertIn("build', 'wysiwyg-preview", script)
        self.assertIn("wysiwyg-preview-manifest.json", script)
        self.assertIn("const screens = [", script)
        self.assertIn("'player'", script)
        self.assertIn("'wallet'", script)
        self.assertIn("fileName: `${flavor}-${screen}.png`", script)
        self.assertIn("requiredFlavorCount", script)
        self.assertIn("requiredScreenCount", script)
        self.assertIn("Release-rendered Flutter Web screenshots only", script)

    def test_store_handoff_manifest_is_public_and_actionable(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_store_handoff_manifest(root)
        manifest = mobile_completion_audit.load_store_handoff_manifest(root)[0]

        self.assertEqual("store_handoff_manifest", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/release-handoff/mobile-store-handoff.json", check.evidence)
        self.assertIsNotNone(manifest)
        flavors = {
            entry["flavor"]: entry
            for entry in manifest["flavors"]
        }
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        coolshow_distribution = flavors["coolshow"]["distributionChannelReadiness"]
        self.assertEqual("android_direct", coolshow_distribution["primaryChannel"])
        self.assertEqual(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            flavors["coolshow"]["storeSubmission"]["tenantEvidenceInputPath"],
        )
        hongguo_visibility = flavors["hongguo"]["paymentVisibility"]
        self.assertEqual("app_store", hongguo_visibility["storeComplianceMode"])
        self.assertEqual(["iap"], hongguo_visibility["configuredProviders"])
        self.assertEqual(["iap"], hongguo_visibility["appVisibleProviders"])
        self.assertEqual([], hongguo_visibility["hiddenByComplianceProviders"])
        self.assertFalse(hongguo_visibility["externalPaymentsAllowed"])
        hongguo_submission = flavors["hongguo"]["storeSubmission"]
        self.assertEqual("GoldFruit Drama", hongguo_submission["listing"]["displayName"])
        self.assertEqual("en-US", hongguo_submission["listing"]["defaultLocale"])
        self.assertIn(
            "Short drama episodes",
            hongguo_submission["listing"]["shortDescription"],
        )
        self.assertIn("privacyUrl", hongguo_submission["listing"])
        localized = {
            entry["locale"]: entry
            for entry in hongguo_submission["localizedListings"]
        }
        self.assertEqual(
            set(hongguo_submission["listing"]["supportedLocales"]),
            set(localized),
        )
        self.assertTrue(localized["en-US"]["isDefault"])
        self.assertFalse(localized["zh-CN"]["isDefault"])
        self.assertEqual("GoldFruit Drama", localized["zh-CN"]["displayName"])
        self.assertIn("短剧", localized["zh-CN"]["shortDescription"])
        self.assertIn("Short drama", localized["en-US"]["shortDescription"])
        callbacks = flavors["hongguo"]["authCallbackRegistration"]
        self.assertEqual("goldfruitdrama", callbacks["scheme"])
        self.assertEqual("auth", callbacks["host"])
        self.assertEqual(
            [
                "goldfruitdrama://auth/oauth/google/callback",
                "goldfruitdrama://auth/oauth/apple/callback",
            ],
            callbacks["callbackUris"],
        )
        self.assertEqual(["code"], callbacks["requiredQueryParams"])
        self.assertIn("oauthStartId", callbacks["optionalQueryParams"])
        self.assertEqual(
            "android/app/src/main/AndroidManifest.xml",
            callbacks["nativeConfig"]["androidManifest"],
        )
        self.assertEqual("ios/Runner/Info.plist", callbacks["nativeConfig"]["iosInfoPlist"])
        products = flavors["hongguo"]["storeProductRegistration"]
        self.assertEqual("app_store", products["storeComplianceMode"])
        self.assertEqual(["iap"], products["storeProviders"])
        self.assertEqual(
            "/payment/store-purchases/verify",
            products["serverVerificationEndpoint"],
        )
        self.assertTrue(products["tenantEdgeMayOverridePackages"])
        self.assertTrue(products["tenantShouldReplaceProductIds"])
        self.assertIn(
            "App Store Connect",
            products["tenantRequiredActions"][0],
        )
        self.assertEqual(1, len(products["registrations"]))
        self.assertEqual("iap", products["registrations"][0]["provider"])
        self.assertEqual("app_store_connect", products["registrations"][0]["store"])
        self.assertEqual("consumable", products["registrations"][0]["productType"])
        self.assertEqual(3, len(products["registrations"][0]["products"]))
        self.assertEqual(
            {
                "packageId": "coins_100",
                "title": "100 coins",
                "storeProductId": "com.shortdrama.coins100",
                "coins": 100,
                "bonusCoins": 0,
                "totalCoins": 100,
                "amountOriginal": 9,
                "currency": "USD",
            },
            products["registrations"][0]["products"][0],
        )
        reelshort_products = flavors["reelshort"]["storeProductRegistration"]
        self.assertEqual(["play_billing"], reelshort_products["storeProviders"])
        self.assertEqual(
            "google_play_console",
            reelshort_products["registrations"][0]["store"],
        )
        self.assertEqual("inapp", reelshort_products["registrations"][0]["productType"])
        douyin_products = flavors["douyin"]["storeProductRegistration"]
        self.assertEqual([], douyin_products["storeProviders"])
        self.assertEqual([], douyin_products["registrations"])
        native = flavors["hongguo"]["nativeCapabilityRegistration"]
        self.assertEqual("com.shortdrama.goldfruit", native["ios"]["bundleId"])
        self.assertEqual("hongguo", native["ios"]["xcodeScheme"])
        self.assertEqual("goldfruitdrama", native["ios"]["urlScheme"])
        self.assertIn("sign_in_with_apple", native["ios"]["requiredCapabilities"])
        self.assertIn("in_app_purchase", native["ios"]["requiredCapabilities"])
        self.assertIn("custom_url_scheme", native["ios"]["requiredCapabilities"])
        self.assertEqual(
            "ios/Runner/PrivacyInfo.xcprivacy",
            native["ios"]["privacyManifest"],
        )
        self.assertEqual(
            "ios/Runner/Runner.entitlements",
            native["ios"]["entitlements"],
        )
        self.assertIn(
            "tenant Apple developer account",
            " ".join(native["ios"]["tenantRequiredActions"]),
        )
        self.assertEqual("com.shortdrama.goldfruit", native["android"]["applicationId"])
        self.assertEqual("hongguo", native["android"]["productFlavor"])
        self.assertIn("internet", native["android"]["requiredCapabilities"])
        self.assertIn("custom_url_scheme", native["android"]["requiredCapabilities"])
        reelshort_native = flavors["reelshort"]["nativeCapabilityRegistration"]
        self.assertIn("play_billing", reelshort_native["android"]["requiredCapabilities"])
        douyin_native = flavors["douyin"]["nativeCapabilityRegistration"]
        self.assertIn(
            "direct_distribution_signing",
            douyin_native["android"]["requiredCapabilities"],
        )
        self.assertNotIn("play_billing", douyin_native["android"]["requiredCapabilities"])
        self.assertNotIn("in_app_purchase", douyin_native["ios"]["requiredCapabilities"])
        review = flavors["hongguo"]["storeReviewDeclarations"]
        self.assertEqual("app_store", review["storeComplianceMode"])
        self.assertEqual(
            "in_app_purchase_only",
            review["apple"]["digitalContentPaymentPolicy"],
        )
        self.assertFalse(review["apple"]["externalPaymentLinksInApp"])
        self.assertTrue(review["apple"]["accountDeletionInApp"])
        self.assertTrue(review["apple"]["signInWithAppleRequired"])
        self.assertFalse(review["apple"]["userGeneratedContent"])
        self.assertEqual(
            "ios/Runner/PrivacyInfo.xcprivacy",
            review["apple"]["privacyManifest"],
        )
        self.assertIn("App Review", review["apple"]["tenantRequiredActions"][0])
        self.assertEqual(
            "not_submitted_by_default",
            review["googlePlay"]["submissionStatus"],
        )
        reelshort_review = flavors["reelshort"]["storeReviewDeclarations"]
        self.assertEqual(
            "play_billing_only",
            reelshort_review["googlePlay"]["digitalContentPaymentPolicy"],
        )
        self.assertFalse(reelshort_review["googlePlay"]["externalPaymentLinksInApp"])
        self.assertEqual("Data safety", reelshort_review["googlePlay"]["formName"])
        douyin_review = flavors["douyin"]["storeReviewDeclarations"]
        self.assertEqual(
            "direct_distribution_only",
            douyin_review["androidDirect"]["submissionStatus"],
        )
        self.assertTrue(douyin_review["androidDirect"]["externalPaymentsInApp"])
        self.assertFalse(douyin_review["apple"]["submittedByDefault"])
        self.assertFalse(douyin_review["googlePlay"]["submittedByDefault"])
        distribution = flavors["hongguo"]["distributionChannelReadiness"]
        self.assertEqual("app_store", distribution["storeComplianceMode"])
        self.assertEqual("app_store_testflight", distribution["primaryChannel"])
        self.assertEqual(
            "ios_environment_blocked",
            distribution["channels"]["appStoreTestFlight"]["status"],
        )
        self.assertEqual(
            "./scripts/build_flavor.sh hongguo ios release",
            distribution["channels"]["appStoreTestFlight"]["buildCommand"],
        )
        self.assertTrue(
            distribution["channels"]["appStoreTestFlight"]["requiresTenantSigning"],
        )
        self.assertEqual(
            "build/app/outputs/bundle/hongguoRelease/app-hongguo-release.aab",
            distribution["channels"]["googlePlayInternal"]["artifactPath"],
        )
        self.assertEqual(
            "ready_for_tenant_signing",
            distribution["channels"]["googlePlayInternal"]["status"],
        )
        reelshort_distribution = flavors["reelshort"]["distributionChannelReadiness"]
        self.assertEqual("google_play_internal", reelshort_distribution["primaryChannel"])
        self.assertEqual(
            "build/app/outputs/bundle/reelshortRelease/app-reelshort-release.aab",
            reelshort_distribution["channels"]["googlePlayInternal"]["artifactPath"],
        )
        douyin_distribution = flavors["douyin"]["distributionChannelReadiness"]
        self.assertEqual("android_direct", douyin_distribution["primaryChannel"])
        self.assertEqual(
            "ready_for_tenant_signing",
            douyin_distribution["channels"]["androidDirect"]["status"],
        )
        self.assertEqual(
            "build/app/outputs/flutter-apk/app-douyin-release.apk",
            douyin_distribution["channels"]["androidDirect"]["artifactPaths"]["apk"],
        )
        self.assertTrue(
            douyin_distribution["channels"]["androidDirect"]["requiresTenantSigning"],
        )
        self.assertIn("tenant must answer store questionnaires", hongguo_submission["dataSafety"]["notes"])
        self.assertIn("configure tenant signing", hongguo_submission["tenantRequiredActions"])
        screenshots = hongguo_submission["screenshotAssets"]
        self.assertEqual(8, len(screenshots))
        self.assertEqual("01_splash", screenshots[0]["screen"])
        self.assertEqual(
            "test/goldens/prototypes/hongguo_01_splash.png",
            screenshots[0]["path"],
        )
        self.assertEqual("publish_safe_prototype", screenshots[0]["source"])
        self.assertTrue(screenshots[0]["tenantShouldReplace"])
        self.assertRegex(screenshots[0]["sha256"], r"^[a-f0-9]{64}$")
        self.assertGreater(screenshots[0]["sizeBytes"], 0)
        self.assertEqual(390, screenshots[0]["width"])
        self.assertEqual(844, screenshots[0]["height"])

    def test_store_assets_package_exports_store_submission_materials(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_store_assets_package(root)
        manifest_path = root / "build" / "store-assets" / "store-assets-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("store_assets_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/store-assets/store-assets-manifest.json", check.evidence)
        self.assertEqual("mobile_store_assets", manifest["packageType"])
        self.assertEqual(40, manifest["screenshotCount"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["listing"]["displayName"])
        self.assertEqual("en-US", hongguo["listing"]["defaultLocale"])
        self.assertFalse(hongguo["dataSafety"]["templateDisclosures"]["clientStoresTenantCredentials"])
        self.assertEqual(8, len(hongguo["screenshots"]))
        self.assertEqual("01_splash", hongguo["screenshots"][0]["screen"])
        self.assertRegex(hongguo["screenshots"][0]["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual("publish_safe_prototype", hongguo["screenshots"][0]["source"])

    def test_ui_preview_gallery_export_preserves_previous_package_on_failure(self) -> None:
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "mobile"
            screenshot_root = root / "test" / "goldens" / "prototypes"
            screenshot_root.mkdir(parents=True)
            for screenshot in (source_root / "test" / "goldens" / "prototypes").glob("*.png"):
                shutil.copyfile(screenshot, screenshot_root / screenshot.name)
            self._copy_wysiwyg_runtime_previews(source_root, root)
            output_dir = root / "build" / "ui-preview-gallery"

            first_manifest = export_ui_preview_gallery.build_gallery(root, output_dir)
            html_path = root / first_manifest["htmlPath"]
            package_path = root / first_manifest["packagePath"]
            original_html_sha = first_manifest["htmlSha256"]
            self.assertTrue(html_path.exists())
            self.assertTrue(package_path.exists())

            (screenshot_root / "hongguo_07_unlock.png").unlink()
            with self.assertRaises(SystemExit):
                export_ui_preview_gallery.build_gallery(root, output_dir)

            self.assertTrue(html_path.exists())
            self.assertTrue(package_path.exists())
            self.assertEqual(original_html_sha, export_ui_preview_gallery.sha256_file(html_path))

    def test_ui_preview_gallery_exports_readable_overview_for_tenant_review(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_ui_preview_gallery(root)
        manifest_path = root / "build" / "ui-preview-gallery" / "ui-preview-gallery-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        overview = manifest["readableOverview"]
        overview_path = root / overview["path"]
        overview_png = manifest["readableOverviewPng"]
        overview_png_path = root / overview_png["path"]
        contact_sheet = manifest["contactSheet"]
        contact_sheet_path = root / contact_sheet["path"]
        contact_sheet_png = manifest["contactSheetPng"]
        contact_sheet_png_path = root / contact_sheet_png["path"]
        wysiwyg_runtime = manifest["wysiwygRuntimePreviews"]
        wysiwyg_boards = {board["id"]: board for board in wysiwyg_runtime["boards"]}
        wysiwyg_home_board = wysiwyg_boards["template_home_gallery"]
        wysiwyg_coolshow_board = wysiwyg_boards["coolshow_core_flow_gallery"]
        wysiwyg_all_template_board = wysiwyg_boards["all_template_core_flow_gallery"]
        wysiwyg_home_board_path = root / wysiwyg_home_board["path"]
        wysiwyg_coolshow_board_path = root / wysiwyg_coolshow_board["path"]
        wysiwyg_all_template_board_path = root / wysiwyg_all_template_board["path"]

        self.assertEqual("ui_preview_gallery", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/ui-preview-gallery/mobile-ui-readable-overview.svg", check.evidence)
        self.assertIn("build/ui-preview-gallery/mobile-ui-readable-overview.png", check.evidence)
        self.assertIn("build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg", check.evidence)
        self.assertIn("build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png", check.evidence)
        self.assertIn("build/ui-preview-gallery/wysiwyg-template-home-gallery.png", check.evidence)
        self.assertIn("build/ui-preview-gallery/wysiwyg-coolshow-eight-screen-gallery.png", check.evidence)
        self.assertIn("build/ui-preview-gallery/wysiwyg-all-template-eight-screen-gallery.png", check.evidence)
        self.assertEqual("build/ui-preview-gallery/mobile-ui-readable-overview.svg", overview["path"])
        self.assertEqual("publish_safe_readable_overview", overview["source"])
        self.assertEqual(20, overview["screenCount"])
        self.assertEqual(["home", "detail", "player", "wallet"], overview["includedScreens"])
        self.assertRegex(overview["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(overview["sha256"], export_ui_preview_gallery.sha256_file(overview_path))
        overview_text = overview_path.read_text(encoding="utf-8")
        self.assertIn("Flutter Short Drama White-label UI Overview", overview_text)
        self.assertIn("CoolShow Short", overview_text)
        self.assertIn("GoldFruit Drama", overview_text)
        self.assertIn("Pulse Drama", overview_text)
        self.assertIn("River Drama", overview_text)
        self.assertIn("Cliff Drama", overview_text)
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-readable-overview.png",
            overview_png["path"],
        )
        self.assertEqual("publish_safe_readable_overview_png", overview_png["source"])
        self.assertEqual(20, overview_png["screenCount"])
        self.assertEqual(["home", "detail", "player", "wallet"], overview_png["includedScreens"])
        self.assertRegex(overview_png["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(overview_png["sha256"], export_ui_preview_gallery.sha256_file(overview_png_path))
        self.assertEqual((1108, 2802), export_ui_preview_gallery.png_dimensions(overview_png_path))
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
            contact_sheet["path"],
        )
        self.assertEqual("publish_safe_full_screenshot_contact_sheet", contact_sheet["source"])
        self.assertEqual(5, contact_sheet["flavorCount"])
        self.assertEqual(40, contact_sheet["screenCount"])
        self.assertEqual(
            ["01_splash", "02_auth", "03_home", "04_catalog", "05_detail", "06_player", "07_unlock", "08_mine_wallet_card"],
            contact_sheet["includedScreens"],
        )
        self.assertRegex(contact_sheet["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(contact_sheet["sha256"], export_ui_preview_gallery.sha256_file(contact_sheet_path))
        contact_sheet_text = contact_sheet_path.read_text(encoding="utf-8")
        self.assertIn("Flutter Short Drama White-label App Full UI Contact Sheet", contact_sheet_text)
        self.assertIn("screenshots/hongguo/hongguo_03_home.png", contact_sheet_text)
        self.assertIn("screenshots/douyin/douyin_06_player.png", contact_sheet_text)
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
            contact_sheet_png["path"],
        )
        self.assertEqual("publish_safe_full_screenshot_contact_sheet_png", contact_sheet_png["source"])
        self.assertEqual(5, contact_sheet_png["flavorCount"])
        self.assertEqual(40, contact_sheet_png["screenCount"])
        self.assertEqual(
            ["01_splash", "02_auth", "03_home", "04_catalog", "05_detail", "06_player", "07_unlock", "08_mine_wallet_card"],
            contact_sheet_png["includedScreens"],
        )
        self.assertRegex(contact_sheet_png["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(contact_sheet_png["sha256"], export_ui_preview_gallery.sha256_file(contact_sheet_png_path))
        self.assertEqual((1364, 1887), export_ui_preview_gallery.png_dimensions(contact_sheet_png_path))
        self.assertEqual("flutter_web_release_runtime_capture", wysiwyg_runtime["source"])
        self.assertEqual("build/wysiwyg-preview", wysiwyg_runtime["sourceDirectory"])
        if (root / "build" / "wysiwyg-preview" / "wysiwyg-preview-manifest.json").exists():
            self.assertEqual(
                "build/wysiwyg-preview/wysiwyg-preview-manifest.json",
                wysiwyg_runtime["sourceManifestPath"],
            )
            self.assertRegex(wysiwyg_runtime["sourceManifestSha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(
                "node scripts/capture_wysiwyg_previews.mjs",
                wysiwyg_runtime["captureCommand"],
            )
        self.assertEqual(len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS), wysiwyg_runtime["captureCount"])
        self.assertEqual(len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES), wysiwyg_runtime["boardCount"])
        self.assertEqual(5, wysiwyg_home_board["screenCount"])
        self.assertEqual(8, wysiwyg_coolshow_board["screenCount"])
        self.assertEqual(40, wysiwyg_all_template_board["screenCount"])
        self.assertEqual(5, wysiwyg_all_template_board["flavorCount"])
        self.assertRegex(wysiwyg_home_board["sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(wysiwyg_coolshow_board["sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(wysiwyg_all_template_board["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(wysiwyg_home_board["sha256"], export_ui_preview_gallery.sha256_file(wysiwyg_home_board_path))
        self.assertEqual(wysiwyg_coolshow_board["sha256"], export_ui_preview_gallery.sha256_file(wysiwyg_coolshow_board_path))
        self.assertEqual(wysiwyg_all_template_board["sha256"], export_ui_preview_gallery.sha256_file(wysiwyg_all_template_board_path))
        self.assertEqual(
            (wysiwyg_home_board["width"], wysiwyg_home_board["height"]),
            export_ui_preview_gallery.png_dimensions(wysiwyg_home_board_path),
        )
        self.assertEqual(
            (wysiwyg_coolshow_board["width"], wysiwyg_coolshow_board["height"]),
            export_ui_preview_gallery.png_dimensions(wysiwyg_coolshow_board_path),
        )
        self.assertEqual(
            (wysiwyg_all_template_board["width"], wysiwyg_all_template_board["height"]),
            export_ui_preview_gallery.png_dimensions(wysiwyg_all_template_board_path),
        )
        self.assertIn("build/ui-preview-gallery/wysiwyg-hongguo-home.png", check.evidence)
        self.assertIn("build/ui-preview-gallery/wysiwyg-reelshort-wallet.png", check.evidence)
        html_text = (root / manifest["htmlPath"]).read_text(encoding="utf-8")
        self.assertIn("WYSIWYG runtime captures", html_text)
        self.assertIn("wysiwyg-template-home-gallery.png", html_text)
        self.assertIn("wysiwyg-coolshow-eight-screen-gallery.png", html_text)
        self.assertIn("wysiwyg-all-template-eight-screen-gallery.png", html_text)
        self.assertIn("wysiwyg-hongguo-player.png", html_text)
        self.assertIn("wysiwyg-reelshort-wallet.png", html_text)
        self.assertIn("mobile-ui-preview-contact-sheet.svg", html_text)
        self.assertIn("mobile-ui-readable-overview.png", html_text)
        self.assertIn("mobile-ui-preview-contact-sheet.png", html_text)
        with zipfile.ZipFile(root / manifest["packagePath"]) as archive:
            self.assertIn(
                "mobile-ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/mobile-ui-readable-overview.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/wysiwyg-template-home-gallery.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/wysiwyg-coolshow-eight-screen-gallery.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/wysiwyg-all-template-eight-screen-gallery.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/wysiwyg-hongguo-home.png",
                archive.namelist(),
            )
            self.assertIn(
                "mobile-ui-preview-gallery/wysiwyg-reelshort-wallet.png",
                archive.namelist(),
            )

    def test_ios_ci_handoff_package_exports_remote_ios_build_metadata(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_ios_ci_handoff_package(root)
        manifest_path = root / "build" / "ios-ci-handoff" / "ios-ci-handoff-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("ios_ci_handoff_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/ios-ci-handoff/ios-ci-handoff-manifest.json", check.evidence)
        self.assertEqual("mobile_ios_ci_handoff", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertEqual(".github/workflows/mobile-flutter.yml", manifest["workflow"]["path"])
        self.assertTrue(manifest["workflow"]["workflowDispatch"])
        self.assertEqual("ios-build", manifest["workflow"]["iosJob"])
        self.assertEqual("macos-15", manifest["workflow"]["runner"])
        self.assertEqual([], manifest["workflow"]["missingRequiredMarkers"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(mobile_completion_audit.FLAVORS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["bundleId"])
        self.assertEqual("mobile-hongguo-ios-unsigned", hongguo["ci"]["artifactName"])
        self.assertEqual("./scripts/build_flavor.sh hongguo ios debug", hongguo["ci"]["debugCommand"])
        self.assertEqual("./scripts/build_flavor.sh hongguo ios release", hongguo["ci"]["releaseCommand"])
        self.assertEqual("gh workflow run mobile-flutter.yml", hongguo["verification"]["triggerCommand"])
        self.assertIn(
            "scripts/download_ios_ci_artifacts.py --repo <owner/repo>",
            hongguo["verification"]["downloadCommand"],
        )
        self.assertIn("latest successful", hongguo["verification"]["runIdResolution"])
        self.assertIn("ios_build_matrix.py all", hongguo["verification"]["completionGate"])
        self.assertIn("ios/Flutter/Hongguo.xcconfig", check.evidence)

    def test_store_signing_handoff_package_exports_no_secret_signing_templates(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_store_signing_handoff_package(root)
        manifest_path = root / "build" / "store-signing-handoff" / "store-signing-handoff-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("store_signing_handoff_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/store-signing-handoff/store-signing-handoff-manifest.json", check.evidence)
        self.assertEqual("mobile_store_signing_handoff", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/release-handoff/mobile-store-handoff.json",
            manifest["sourceManifests"]["storeHandoff"],
        )
        self.assertEqual(
            "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
            manifest["sourceManifests"]["iosCiHandoff"],
        )
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        coolshow = flavors["coolshow"]
        self.assertEqual("CoolShow Short", coolshow["appName"])
        self.assertEqual("com.coolshow.short", coolshow["applicationId"])
        self.assertEqual("android_direct", coolshow["storeComplianceMode"])
        self.assertEqual(
            "./scripts/build_flavor.sh coolshow android release apk",
            coolshow["android"]["directDistributionCommand"],
        )
        self.assertFalse(coolshow["secretBoundary"]["containsSigningMaterial"])
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["applicationId"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["bundleId"])
        self.assertEqual("app-store-connect", hongguo["ios"]["exportOptionsTemplate"]["method"])
        self.assertEqual("manual", hongguo["ios"]["exportOptionsTemplate"]["signingStyle"])
        self.assertIn("--flavor hongguo", hongguo["ios"]["archiveCommand"])
        self.assertEqual(
            "./scripts/build_flavor.sh hongguo android release appbundle",
            hongguo["android"]["playUploadCommand"],
        )
        self.assertEqual(
            "./scripts/build_flavor.sh hongguo android release apk",
            hongguo["android"]["directDistributionCommand"],
        )
        self.assertFalse(hongguo["secretBoundary"]["containsSigningMaterial"])
        self.assertFalse(hongguo["secretBoundary"]["containsAndroidKeystore"])
        self.assertIn(
            "build/store-signing-handoff/hongguo/ExportOptions.plist.template",
            check.evidence,
        )
        self.assertIn(
            "build/store-signing-handoff/hongguo/android-signing.properties.template",
            check.evidence,
        )

    def test_store_publish_config_package_exports_tenant_fillable_store_templates(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_store_publish_config_package(root)
        manifest_path = root / "build" / "store-publish-config" / "store-publish-config-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("store_publish_config_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/store-publish-config/store-publish-config-manifest.json", check.evidence)
        self.assertEqual("mobile_store_publish_config", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/release-handoff/mobile-store-handoff.json",
            manifest["sourceManifests"]["storeHandoff"]["path"],
        )
        self.assertEqual(
            "build/store-signing-handoff/store-signing-handoff-manifest.json",
            manifest["sourceManifests"]["storeSigningHandoff"]["path"],
        )
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(mobile_completion_audit.FLAVORS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["applicationId"])
        self.assertEqual(["appStoreConnect"], hongguo["enabledStores"])
        self.assertFalse(hongguo["containsSecrets"])
        template_path = root / "build" / "store-publish-config" / hongguo["templatePath"]
        template = json.loads(template_path.read_text(encoding="utf-8"))
        self.assertEqual("app_store", template["storeComplianceMode"])
        self.assertTrue(template["appStoreConnect"]["enabled"])
        self.assertFalse(template["googlePlayConsole"]["enabled"])
        self.assertFalse(template["androidDirect"]["enabled"])
        self.assertEqual("com.shortdrama.goldfruit", template["appIdentity"]["bundleId"])
        self.assertTrue(template["appIdentity"]["tenantMayReplaceIds"])
        self.assertIn("privacyUrl", template["legalUrls"])
        self.assertTrue(template["oauthCallbacks"]["credentialsStayServerSide"])
        self.assertEqual(3, len(template["appStoreConnect"]["inAppPurchases"]))
        self.assertIn("Apple team id", template["appStoreConnect"]["tenantMustFill"])
        self.assertFalse(template["serverSideCredentialBoundary"]["mobileClientStoresProviderCredentials"])
        self.assertFalse(template["serverSideCredentialBoundary"]["mobileClientStoresSigningMaterial"])

        reelshort_template_path = root / "build" / "store-publish-config" / flavors["reelshort"]["templatePath"]
        reelshort = json.loads(reelshort_template_path.read_text(encoding="utf-8"))
        self.assertTrue(reelshort["googlePlayConsole"]["enabled"])
        self.assertEqual(3, len(reelshort["googlePlayConsole"]["playBillingProducts"]))
        self.assertIn("payments declarations", reelshort["googlePlayConsole"]["tenantMustFill"])

        douyin_template_path = root / "build" / "store-publish-config" / flavors["douyin"]["templatePath"]
        douyin = json.loads(douyin_template_path.read_text(encoding="utf-8"))
        self.assertTrue(douyin["androidDirect"]["enabled"])
        self.assertIn("stripe", douyin["androidDirect"]["externalPaymentProviders"])
        self.assertIn("signed APK or AAB location", douyin["androidDirect"]["tenantMustFill"])

    def test_tenant_release_package_is_public_and_tenant_actionable(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_tenant_release_package(root)
        package_path = root / "build" / "release-handoff" / "mobile-tenant-release-package.json"
        markdown_path = root / "build" / "release-handoff" / "mobile-tenant-release-package.md"
        package = json.loads(package_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("tenant_release_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/release-handoff/mobile-tenant-release-package.json", check.evidence)
        self.assertIn("build/release-handoff/mobile-tenant-release-package.md", check.evidence)
        self.assertIn("build/release-handoff/mobile-tenant-release-package.zip", check.evidence)
        self.assertEqual(1, package["schemaVersion"])
        self.assertEqual("mobile_tenant_release_package", package["packageType"])
        package_flavors = {
            entry["flavor"]: entry
            for entry in package["flavors"]
        }
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(package_flavors))
        self.assertEqual("android_direct", package_flavors["coolshow"]["primaryChannel"])
        self.assertEqual(
            "com.coolshow.short",
            package_flavors["coolshow"]["applicationId"],
        )
        archive_package = package["archivePackage"]
        self.assertEqual(
            "build/release-handoff/mobile-tenant-release-package.zip",
            archive_package["packagePath"],
        )
        self.assertTrue(archive_package["packagePresent"])
        self.assertRegex(archive_package["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertGreaterEqual(archive_package["entryCount"], 10)
        self.assertEqual([], archive_package["disallowedValueMarkerHits"])
        archive_path = root / "build" / "release-handoff" / "mobile-tenant-release-package.zip"
        with zipfile.ZipFile(archive_path) as archive:
            archive_names = set(archive.namelist())
        self.assertIn(
            "mobile-tenant-release-package/mobile-tenant-release-package.json",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/mobile-tenant-release-package.md",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/release-handoff/mobile-store-handoff.json",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/app-handoff/mobile-app-handoff.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-readable-overview.png",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
            archive_names,
        )
        self.assertIn(
            f"mobile-tenant-release-package/build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
            archive_names,
        )
        self.assertIn(
            f"mobile-tenant-release-package/build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/ui-preview-gallery/wysiwyg-all-template-eight-screen-gallery.png",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/store-signing-handoff/mobile-store-signing-handoff.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/store-publish-config/mobile-store-publish-config.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.json",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.md",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/external-account-handoff/mobile-external-account-handoff.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/store-submission-starter/mobile-store-submission-starter.zip",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/completion-unblocker/mobile-completion-unblocker.json",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/completion-unblocker/mobile-completion-unblocker.md",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
            archive_names,
        )
        self.assertIn(
            "mobile-tenant-release-package/build/completion-unblocker/mobile-store-evidence-fix-queue.md",
            archive_names,
        )
        self.assertEqual(
            "build/release-handoff/mobile-tenant-release-package.md",
            package["humanReadableGuide"]["path"],
        )
        self.assertTrue(package["humanReadableGuide"]["present"])
        self.assertRegex(package["humanReadableGuide"]["sha256"], r"^[a-f0-9]{64}$")
        self.assertIn("# Mobile Tenant Release Package", markdown)
        self.assertIn("## Store Submission Status Summary", markdown)
        self.assertIn("| Flavor | Channel | Status | Input | Blockers | Next action |", markdown)
        self.assertIn("build/store-submission-evidence/flavors/hongguo.input.json", markdown)
        self.assertIn("appStoreConnectRecordConfigured", markdown)
        self.assertIn("cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict", markdown)
        self.assertIn("## Completion Unblocker", markdown)
        self.assertIn("mobile-store-evidence-fix-queue.csv", markdown)
        self.assertIn("Store evidence fix queue rows", markdown)
        self.assertIn("WYSIWYG runtime boards", markdown)
        self.assertIn("## External Account Checklist", markdown)
        self.assertIn("mobile-external-account-handoff.md", markdown)
        self.assertIn("No signing material, provider credentials, OAuth secrets, payment secrets, Cloudflare tokens, bank credentials, or crypto keys are included.", markdown)
        self.assertEqual(
            "build/release-handoff/mobile-store-handoff.json",
            package["manifests"]["storeHandoff"]["path"],
        )
        self.assertRegex(package["manifests"]["storeHandoff"]["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/store-assets/store-assets-manifest.json",
            package["manifests"]["storeAssets"]["manifestPath"],
        )
        self.assertEqual(
            "build/store-assets/mobile-store-assets.zip",
            package["manifests"]["storeAssets"]["packagePath"],
        )
        self.assertEqual(40, package["manifests"]["storeAssets"]["screenshotCount"])
        self.assertRegex(package["manifests"]["storeAssets"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["storeAssets"]["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/ui-preview-gallery/ui-preview-gallery-manifest.json",
            package["manifests"]["uiPreviewGallery"]["manifestPath"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-gallery.html",
            package["manifests"]["uiPreviewGallery"]["htmlPath"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-gallery.zip",
            package["manifests"]["uiPreviewGallery"]["packagePath"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-readable-overview.svg",
            package["manifests"]["uiPreviewGallery"]["readableOverviewPath"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-readable-overview.png",
            package["manifests"]["uiPreviewGallery"]["readableOverviewPngPath"],
        )
        self.assertEqual(
            "flutter_web_release_runtime_capture",
            package["manifests"]["uiPreviewGallery"]["wysiwygRuntimePreviews"]["source"],
        )
        self.assertEqual(
            len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS),
            package["manifests"]["uiPreviewGallery"]["wysiwygRuntimePreviews"]["captureCount"],
        )
        self.assertEqual(
            len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES),
            package["manifests"]["uiPreviewGallery"]["wysiwygRuntimePreviews"]["boardCount"],
        )
        release_wysiwyg_boards = {
            board["path"]: board
            for board in package["manifests"]["uiPreviewGallery"]["wysiwygRuntimePreviews"]["boards"]
        }
        release_home_board_path = f"build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}"
        release_all_template_board_path = f"build/ui-preview-gallery/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}"
        self.assertTrue(
            release_wysiwyg_boards[release_home_board_path]["present"],
        )
        self.assertTrue(
            release_wysiwyg_boards[release_all_template_board_path]["present"],
        )
        self.assertRegex(
            release_wysiwyg_boards[release_home_board_path]["sha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            release_wysiwyg_boards[release_all_template_board_path]["sha256"],
            r"^[a-f0-9]{64}$",
        )
        completion_unblocker = package["manifests"]["completionUnblocker"]
        self.assertEqual(
            "build/completion-unblocker/mobile-completion-unblocker.json",
            completion_unblocker["manifestPath"],
        )
        self.assertEqual(
            "build/completion-unblocker/mobile-completion-unblocker.md",
            completion_unblocker["markdownPath"],
        )
        self.assertEqual(
            "build/completion-unblocker/mobile-store-evidence-fix-queue.csv",
            completion_unblocker["fixQueueCsvPath"],
        )
        self.assertEqual(
            "build/completion-unblocker/mobile-store-evidence-fix-queue.md",
            completion_unblocker["fixQueueMarkdownPath"],
        )
        self.assertTrue(completion_unblocker["manifestPresent"])
        self.assertTrue(completion_unblocker["markdownPresent"])
        self.assertTrue(completion_unblocker["fixQueueCsvPresent"])
        self.assertTrue(completion_unblocker["fixQueueMarkdownPresent"])
        self.assertGreater(completion_unblocker["fixQueueRowCount"], 0)
        self.assertEqual([], completion_unblocker["disallowedValueMarkerHits"])
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.svg",
            package["manifests"]["uiPreviewGallery"]["contactSheetPath"],
        )
        self.assertEqual(
            "build/ui-preview-gallery/mobile-ui-preview-contact-sheet.png",
            package["manifests"]["uiPreviewGallery"]["contactSheetPngPath"],
        )
        self.assertEqual(40, package["manifests"]["uiPreviewGallery"]["screenshotCount"])
        self.assertEqual(20, package["manifests"]["uiPreviewGallery"]["readableOverviewScreenCount"])
        self.assertEqual(40, package["manifests"]["uiPreviewGallery"]["contactSheetScreenCount"])
        self.assertRegex(package["manifests"]["uiPreviewGallery"]["htmlSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["uiPreviewGallery"]["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(
            package["manifests"]["uiPreviewGallery"]["readableOverviewSha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            package["manifests"]["uiPreviewGallery"]["readableOverviewPngSha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            package["manifests"]["uiPreviewGallery"]["contactSheetSha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            package["manifests"]["uiPreviewGallery"]["contactSheetPngSha256"],
            r"^[a-f0-9]{64}$",
        )
        self.assertEqual(
            "build/app-handoff/mobile-app-handoff-manifest.json",
            package["manifests"]["appHandoff"]["manifestPath"],
        )
        self.assertEqual(
            "build/app-handoff/mobile-app-handoff.zip",
            package["manifests"]["appHandoff"]["packagePath"],
        )
        self.assertEqual(
            "build/app-handoff/store-submission-evidence/store-submission-input-workspace.json",
            package["manifests"]["appHandoff"]["embeddedStoreSubmissionInputWorkspace"]["manifestPath"],
        )
        self.assertFalse(
            package["manifests"]["appHandoff"]["embeddedStoreSubmissionInputWorkspace"]["preflightSummary"]["strictImportReady"],
        )
        self.assertRegex(package["manifests"]["appHandoff"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["appHandoff"]["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/store-submission-evidence/store-submission-input-workspace.json",
            package["manifests"]["storeSubmissionInputWorkspace"]["manifestPath"],
        )
        self.assertEqual(
            "build/store-submission-evidence/store-submission-input-workspace.md",
            package["manifests"]["storeSubmissionInputWorkspace"]["markdownPath"],
        )
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence-preflight.md",
            package["manifests"]["storeSubmissionInputWorkspace"]["preflightMarkdownPath"],
        )
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            package["manifests"]["storeSubmissionInputWorkspace"]["inputCount"],
        )
        self.assertFalse(package["manifests"]["storeSubmissionInputWorkspace"]["preflightSummary"]["strictImportReady"])
        self.assertRegex(
            package["manifests"]["storeSubmissionInputWorkspace"]["manifestSha256"],
            r"^[a-f0-9]{64}$",
        )
        status_summary = package["storeSubmissionStatusSummary"]
        self.assertEqual("blocked", status_summary["result"])
        self.assertFalse(status_summary["strictImportReady"])
        self.assertEqual(
            "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            status_summary["strictImportCommand"],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors",
            status_summary["inputDirectory"],
        )
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), status_summary["blockedCount"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(status_summary["blockedInputPaths"]))
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(status_summary["flavors"]))
        status_flavors = {entry["flavor"]: entry for entry in status_summary["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(status_flavors))
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            status_flavors["hongguo"]["inputPath"],
        )
        self.assertEqual("blocked", status_flavors["hongguo"]["status"])
        self.assertIn("appStoreConnectRecordConfigured", status_flavors["hongguo"]["blockers"])
        self.assertIn("rerun the preflight", status_flavors["hongguo"]["nextAction"])
        self.assertTrue(status_flavors["hongguo"]["remediationHints"])
        self.assertEqual(
            "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
            package["manifests"]["iosCiHandoff"]["manifestPath"],
        )
        self.assertEqual(
            "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
            package["manifests"]["iosCiHandoff"]["packagePath"],
        )
        self.assertTrue(package["manifests"]["iosCiHandoff"]["workflowDispatch"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), package["manifests"]["iosCiHandoff"]["flavorCount"])
        self.assertRegex(package["manifests"]["iosCiHandoff"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["iosCiHandoff"]["packageSha256"], r"^[a-f0-9]{64}$")

        self.assertEqual(
            "build/store-signing-handoff/store-signing-handoff-manifest.json",
            package["manifests"]["storeSigningHandoff"]["manifestPath"],
        )
        self.assertEqual(
            "build/store-signing-handoff/mobile-store-signing-handoff.zip",
            package["manifests"]["storeSigningHandoff"]["packagePath"],
        )
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            package["manifests"]["storeSigningHandoff"]["flavorCount"],
        )
        self.assertRegex(package["manifests"]["storeSigningHandoff"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["storeSigningHandoff"]["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/store-publish-config/store-publish-config-manifest.json",
            package["manifests"]["storePublishConfig"]["manifestPath"],
        )
        self.assertEqual(
            "build/store-publish-config/mobile-store-publish-config.zip",
            package["manifests"]["storePublishConfig"]["packagePath"],
        )
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), package["manifests"]["storePublishConfig"]["flavorCount"])
        self.assertRegex(package["manifests"]["storePublishConfig"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["storePublishConfig"]["packageSha256"], r"^[a-f0-9]{64}$")
        external_account = package["manifests"]["externalAccountHandoff"]
        self.assertEqual(
            "build/external-account-handoff/mobile-external-account-handoff.json",
            external_account["manifestPath"],
        )
        self.assertEqual(
            "build/external-account-handoff/mobile-external-account-handoff.md",
            external_account["markdownPath"],
        )
        self.assertEqual(
            "build/external-account-handoff/mobile-external-account-handoff.zip",
            external_account["packagePath"],
        )
        self.assertEqual(6, external_account["sectionCount"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), external_account["flavorCount"])
        self.assertIn("外部账号与签名资料接入入口", external_account["tenantPortalEntry"])
        self.assertEqual([], external_account["disallowedValueMarkerHits"])
        self.assertRegex(external_account["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(external_account["markdownSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(external_account["packageSha256"], r"^[a-f0-9]{64}$")
        completion_closure = package["manifests"]["completionClosure"]
        self.assertEqual(
            "build/completion-closure/mobile-completion-closure.json",
            completion_closure["reportPath"],
        )
        self.assertEqual(
            "build/completion-closure/mobile-completion-closure.md",
            completion_closure["markdownPath"],
        )
        self.assertIsInstance(completion_closure["canClaimComplete"], bool)
        self.assertIsInstance(completion_closure["blockerIds"], list)
        self.assertRegex(completion_closure["reportSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(completion_closure["markdownSha256"], r"^[a-f0-9]{64}$")
        store_submission_evidence = package["manifests"]["storeSubmissionEvidence"]
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence.json",
            store_submission_evidence["evidencePath"],
        )
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence.template.json",
            store_submission_evidence["templatePath"],
        )
        self.assertIn("guidePath", store_submission_evidence)
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence.guide.md",
            store_submission_evidence["guidePath"],
        )
        self.assertIn(store_submission_evidence["result"], {"blocked", "passed"})
        self.assertRegex(store_submission_evidence["evidenceSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(store_submission_evidence["templateSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(store_submission_evidence["guideSha256"], r"^[a-f0-9]{64}$")
        store_submission_starter = package["manifests"]["storeSubmissionStarter"]
        self.assertEqual(
            "build/store-submission-starter/store-submission-starter-manifest.json",
            store_submission_starter["manifestPath"],
        )
        self.assertEqual(
            "build/store-submission-starter/mobile-store-submission-starter.zip",
            store_submission_starter["packagePath"],
        )
        self.assertEqual(
            "build/store-submission-starter/store-submission-evidence-collector.html",
            store_submission_starter["collectorHtmlPath"],
        )
        self.assertEqual(
            "build/store-submission-starter/store-submission-operator-runbook.md",
            store_submission_starter["operatorRunbookPath"],
        )
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), store_submission_starter["flavorCount"])
        self.assertRegex(store_submission_starter["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(store_submission_starter["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(store_submission_starter["collectorHtmlSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(store_submission_starter["operatorRunbookSha256"], r"^[a-f0-9]{64}$")
        evidence_packet_summary = store_submission_starter["evidencePacketSummary"]
        self.assertEqual(
            "cd mobile && python3 scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            evidence_packet_summary["nextImportCommand"],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors",
            evidence_packet_summary["perFlavorInputDirectory"],
        )
        self.assertIn("Public status references only", evidence_packet_summary["secretBoundary"])
        packet_flavors = {entry["flavor"]: entry for entry in evidence_packet_summary["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(packet_flavors))
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            packet_flavors["hongguo"]["tenantEvidenceInputPath"],
        )
        self.assertEqual(
            "build/store-submission-starter/hongguo/store-submission-evidence.input.example.json",
            packet_flavors["hongguo"]["starterInputExamplePath"],
        )
        self.assertEqual("app_store_testflight", packet_flavors["hongguo"]["primaryChannel"])
        self.assertIn(
            "Use the store-submission starter package to copy no-secret tenant-fillable evidence inputs before importing public store evidence.",
            package["tenantWorkflow"],
        )
        self.assertIn(
            "Follow the store-submission operator runbook to connect signing handoff, publish config, evidence collector, and strict evidence import.",
            package["tenantWorkflow"],
        )
        self.assertIn(
            "Use the external account handoff checklist to collect Apple, Google Play, Android direct, OAuth, consumer payment, and legal public status fields without credentials.",
            package["tenantWorkflow"],
        )
        self.assertIn("docs/open-source-release.md", package["openSourceBoundary"]["docs"])
        self.assertFalse(package["secretBoundary"]["clientStoresTenantSecrets"])
        self.assertFalse(package["secretBoundary"]["clientStoresPaymentSecrets"])
        flavors = {entry["flavor"]: entry for entry in package["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["applicationId"])
        self.assertTrue(hongguo["tenantRequiredActions"]["replaceBundleIds"])
        self.assertTrue(hongguo["tenantRequiredActions"]["replaceSigningMaterial"])
        self.assertTrue(hongguo["tenantRequiredActions"]["configureOAuthCallbacks"])
        self.assertTrue(hongguo["tenantRequiredActions"]["configureStoreProducts"])
        self.assertIn("build/app/outputs/bundle/hongguoRelease/app-hongguo-release.aab", json.dumps(hongguo))

    def test_external_account_handoff_package_exports_no_secret_checklist(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_external_account_handoff_package(root)
        manifest_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.json"
        markdown_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.md"
        package_path = root / "build" / "external-account-handoff" / "mobile-external-account-handoff.zip"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("external_account_handoff_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertEqual("mobile_external_account_handoff", manifest["packageType"])
        self.assertEqual(
            "Tenant Portal > App 模板 > 外部账号与签名资料接入入口",
            manifest["tenantPortalEntry"],
        )
        self.assertEqual(6, len(manifest["sections"]))
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(manifest["flavors"]))
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertFalse(manifest["mobileClientBoundary"]["storesTenantCredentials"])
        self.assertFalse(manifest["mobileClientBoundary"]["storesSigningMaterial"])
        self.assertFalse(manifest["mobileClientBoundary"]["storesProviderCredentials"])
        section_ids = {section["id"] for section in manifest["sections"]}
        self.assertEqual(
            {
                "apple_developer",
                "google_play",
                "android_direct",
                "oauth_social_login",
                "consumer_payments",
                "legal_review",
            },
            section_ids,
        )
        flavors = {row["flavor"]: row for row in manifest["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        self.assertIn("apple_developer", flavors["hongguo"]["requiredSections"])
        self.assertIn("android_direct", flavors["douyin"]["requiredSections"])
        self.assertIn("google_play", flavors["reelshort"]["requiredSections"])
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            flavors["hongguo"]["tenantEvidenceInputPath"],
        )
        self.assertIn("Apple Developer and App Store Connect", markdown)
        self.assertIn("Google Play Console", markdown)
        self.assertIn("Android Direct Distribution", markdown)
        self.assertIn("OAuth and Social Login", markdown)
        self.assertIn("Consumer Payments", markdown)
        self.assertIn("Legal, Support, and Review", markdown)
        self.assertNotIn("client_secret", json.dumps(manifest, ensure_ascii=False).lower())
        self.assertNotIn("private_key", json.dumps(manifest, ensure_ascii=False).lower())
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
        self.assertIn(
            "mobile-external-account-handoff/mobile-external-account-handoff.json",
            names,
        )
        self.assertIn(
            "mobile-external-account-handoff/mobile-external-account-handoff.md",
            names,
        )

    def test_app_handoff_package_exports_per_flavor_operator_packet(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_app_handoff_package(root)
        manifest_path = root / "build" / "app-handoff" / "mobile-app-handoff-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual("app_handoff_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("store-submission preflight", check.detail)
        self.assertIn("embedded store-submission starter files", check.detail)
        self.assertIn("build/app-handoff/mobile-app-handoff-manifest.json", check.evidence)
        self.assertIn("build/app-handoff/mobile-app-handoff.html", check.evidence)
        self.assertIn("build/app-handoff/mobile-app-handoff.zip", check.evidence)
        self.assertEqual(1, manifest["schemaVersion"])
        self.assertEqual("mobile_app_handoff_package", manifest["packageType"])
        self.assertEqual("hongguo", manifest["defaultFlavor"])
        self.assertEqual("build/app-handoff/mobile-app-handoff.html", manifest["htmlPath"])
        self.assertRegex(manifest["htmlSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertEqual("blocked", manifest["storeSubmissionPreflight"]["result"])
        self.assertEqual(
            {
                "passed": 0,
                "blocked": len(import_store_submission_evidence.FLAVOR_DEFAULTS),
                "failed": 0,
            },
            manifest["storeSubmissionPreflight"]["summary"],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            {
                row["flavor"]: row
                for row in manifest["storeSubmissionPreflight"]["flavors"]
            }["hongguo"]["tenantEvidenceInputPath"],
        )
        self.assertFalse(manifest["storeSubmissionPreflight"]["strictImportReadiness"]["ready"])
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            {
                row["flavor"]: row
                for row in manifest["storeSubmissionPreflight"]["strictImportReadiness"]["blockedBy"]
            }["hongguo"]["inputPath"],
        )
        preflight_by_flavor = {
            row["flavor"]: row
            for row in manifest["storeSubmissionPreflight"]["flavors"]
        }
        self.assertFalse(preflight_by_flavor["hongguo"]["readyForStrictImport"])
        self.assertTrue(preflight_by_flavor["hongguo"]["strictImportBlockedBy"])
        self.assertEqual(
            "build/app-handoff/store-submission-starter",
            manifest["embeddedStoreSubmissionStarter"]["rootPath"],
        )
        self.assertEqual(
            "build/app-handoff/store-submission-starter/store-submission-evidence-collector.html",
            manifest["embeddedStoreSubmissionStarter"]["collectorHtmlPath"],
        )
        self.assertEqual(
            "build/app-handoff/store-submission-evidence",
            manifest["embeddedStoreSubmissionInputWorkspace"]["rootPath"],
        )
        self.assertEqual(
            "build/app-handoff/store-submission-evidence/store-submission-input-workspace.json",
            manifest["embeddedStoreSubmissionInputWorkspace"]["manifestPath"],
        )
        external_account = manifest["embeddedExternalAccountHandoff"]
        self.assertEqual(
            "build/app-handoff/external-account-handoff/mobile-external-account-handoff.json",
            external_account["manifestPath"],
        )
        self.assertEqual(
            "build/app-handoff/external-account-handoff/mobile-external-account-handoff.md",
            external_account["markdownPath"],
        )
        self.assertEqual(
            "build/app-handoff/external-account-handoff/mobile-external-account-handoff.zip",
            external_account["packagePath"],
        )
        self.assertEqual(6, external_account["sectionCount"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), external_account["flavorCount"])
        self.assertIn("外部账号与签名资料接入入口", external_account["tenantPortalEntry"])
        self.assertEqual([], external_account["disallowedValueMarkerHits"])
        self.assertEqual(
            "build/app-handoff/store-submission-evidence/store-submission-evidence-preflight.md",
            manifest["embeddedStoreSubmissionInputWorkspace"]["preflightMarkdownPath"],
        )
        self.assertFalse(manifest["embeddedStoreSubmissionInputWorkspace"]["preflightSummary"]["strictImportReady"])
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            {
                row["flavor"]: row
                for row in manifest["embeddedStoreSubmissionInputWorkspace"]["inputs"]
            }["hongguo"]["targetPath"],
        )
        embedded_input_by_flavor = {
            row["flavor"]: row
            for row in manifest["embeddedStoreSubmissionInputWorkspace"]["inputs"]
        }
        self.assertIn("submissionStatus", embedded_input_by_flavor["hongguo"]["preflightBlockers"])
        self.assertIn("mobile-ui-readable-overview.svg", manifest["uiPreview"]["readableOverviewPath"])
        self.assertIn("mobile-ui-readable-overview.png", manifest["uiPreview"]["readableOverviewPngPath"])
        self.assertIn("mobile-ui-preview-contact-sheet.svg", manifest["uiPreview"]["contactSheetPath"])
        self.assertIn("mobile-ui-preview-contact-sheet.png", manifest["uiPreview"]["contactSheetPngPath"])
        self.assertEqual(40, manifest["uiPreview"]["contactSheetScreenCount"])
        self.assertEqual(
            "flutter_web_release_runtime_capture",
            manifest["uiPreview"]["wysiwygRuntimePreviews"]["source"],
        )
        self.assertEqual(
            len(export_ui_preview_gallery.WYSIWYG_CAPTURE_SPECS),
            manifest["uiPreview"]["wysiwygRuntimePreviews"]["captureCount"],
        )
        self.assertEqual(len(export_ui_preview_gallery.WYSIWYG_BOARD_FILES), manifest["uiPreview"]["wysiwygRuntimePreviews"]["boardCount"])
        self.assertEqual("build/app-handoff/mobile-ui-preview-contact-sheet.svg", manifest["embeddedContactSheetPath"])
        self.assertEqual("build/app-handoff/mobile-ui-readable-overview.png", manifest["embeddedPreviewPngPath"])
        self.assertEqual("build/app-handoff/mobile-ui-preview-contact-sheet.png", manifest["embeddedContactSheetPngPath"])
        self.assertEqual(
            [
                f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
                f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
                f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}",
            ],
            manifest["embeddedWysiwygPreviewPaths"],
        )
        embedded_wysiwyg_home_path = f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}"
        embedded_wysiwyg_coolshow_path = f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}"
        embedded_wysiwyg_all_template_path = f"build/app-handoff/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}"
        self.assertRegex(
            manifest["embeddedWysiwygPreviewSha256"][embedded_wysiwyg_home_path],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            manifest["embeddedWysiwygPreviewSha256"][embedded_wysiwyg_coolshow_path],
            r"^[a-f0-9]{64}$",
        )
        self.assertRegex(
            manifest["embeddedWysiwygPreviewSha256"][embedded_wysiwyg_all_template_path],
            r"^[a-f0-9]{64}$",
        )
        html_path = root / "build" / "app-handoff" / "mobile-app-handoff.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("GoldFruit Drama", html)
        self.assertIn("app-hongguo-release.apk", html)
        self.assertIn("WYSIWYG runtime captures", html)
        self.assertIn(export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE, html)
        self.assertIn(export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE, html)
        self.assertIn(export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE, html)
        self.assertIn("mobile-ui-readable-overview.svg", html)
        self.assertIn("mobile-ui-readable-overview.png", html)
        self.assertIn("mobile-ui-preview-contact-sheet.svg", html)
        self.assertIn("mobile-ui-preview-contact-sheet.png", html)
        self.assertIn("Store submission preflight", html)
        self.assertIn("Store submission input workspace", html)
        self.assertIn("External account and signing checklist", html)
        self.assertIn("mobile-external-account-handoff.md", html)
        self.assertIn("Strict import ready", html)
        self.assertIn("hongguo", html)
        self.assertIn("store-submission-evidence/flavors/hongguo.input.json", html)
        markdown_path = root / "build" / "app-handoff" / "mobile-app-handoff.md"
        markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("Store Submission Preflight", markdown)
        self.assertIn("Store Submission Input Workspace", markdown)
        self.assertIn("External Account And Signing Checklist", markdown)
        self.assertIn("Strict import ready: `False`", markdown)
        self.assertIn("Ready for strict import", markdown)
        self.assertIn("build/store-submission-evidence/flavors/hongguo.input.json", markdown)
        with zipfile.ZipFile(root / "build" / "app-handoff" / "mobile-app-handoff.zip") as archive:
            names = archive.namelist()
            self.assertIn("mobile-app-handoff/mobile-app-handoff.html", names)
            self.assertIn("mobile-app-handoff/mobile-app-handoff.md", names)
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/store-submission-evidence-collector.html",
                names,
            )
            self.assertIn(
                f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_HOME_BOARD_FILE}",
                names,
            )
            self.assertIn(
                f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_COOLSHOW_BOARD_FILE}",
                names,
            )
            self.assertIn(
                f"mobile-app-handoff/{export_ui_preview_gallery.WYSIWYG_ALL_TEMPLATES_BOARD_FILE}",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/store-submission-operator-runbook.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/hongguo/store-submission-evidence.input.example.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/hongguo/operator-checklist.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/hongguo/submission-runbook.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/store-submission-input-workspace.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/store-submission-input-workspace.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/store-submission-evidence-preflight.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/external-account-handoff/mobile-external-account-handoff.zip",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/store-submission-evidence-preflight.md",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/flavors/hongguo.input.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-starter/coolshow/store-submission-evidence.input.example.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/store-submission-evidence/flavors/coolshow.input.json",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/mobile-ui-preview-contact-sheet.svg",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/mobile-ui-readable-overview.png",
                names,
            )
            self.assertIn(
                "mobile-app-handoff/mobile-ui-preview-contact-sheet.png",
                names,
            )

        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(flavors))
        coolshow = flavors["coolshow"]
        self.assertEqual("CoolShow Short", coolshow["appName"])
        self.assertEqual("com.coolshow.short", coolshow["applicationId"])
        self.assertEqual("android_direct", coolshow["storeComplianceMode"])
        self.assertEqual("android_direct", coolshow["primaryChannel"])
        self.assertTrue(coolshow["androidArtifacts"]["releaseApk"]["path"].endswith("app-coolshow-release.apk"))
        self.assertTrue(coolshow["androidArtifacts"]["releaseAppBundle"]["path"].endswith("app-coolshow-release.aab"))
        self.assertRegex(coolshow["androidArtifacts"]["releaseApk"]["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual("passed", coolshow["androidRuntimeSmoke"]["launchResult"])
        self.assertEqual(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            coolshow["storeSubmission"]["tenantEvidenceInputPath"],
        )
        self.assertIn("directSignedPackageReady", coolshow["storeSubmission"]["requiredChecklistFlags"])
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["applicationId"])
        self.assertEqual("app_store", hongguo["storeComplianceMode"])
        self.assertEqual("app_store_testflight", hongguo["primaryChannel"])
        self.assertEqual("passed", hongguo["androidRuntimeSmoke"]["launchResult"])
        self.assertTrue(hongguo["androidArtifacts"]["releaseApk"]["path"].endswith("app-hongguo-release.apk"))
        self.assertTrue(hongguo["androidArtifacts"]["releaseAppBundle"]["path"].endswith("app-hongguo-release.aab"))
        self.assertRegex(hongguo["androidArtifacts"]["releaseApk"]["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/store-submission-evidence/flavors/hongguo.input.json",
            hongguo["storeSubmission"]["tenantEvidenceInputPath"],
        )
        self.assertIn("storeProductsConfigured", hongguo["storeSubmission"]["requiredChecklistFlags"])
        self.assertTrue(hongguo["tenantRequiredActions"]["replaceSigningMaterial"])
        self.assertTrue(hongguo["tenantRequiredActions"]["configureTenantEdgeSecretsServerSide"])

    def test_store_submission_starter_manifest_exposes_evidence_packet_summary(self) -> None:
        import export_store_submission_starter

        root = Path(__file__).resolve().parents[1]
        manifest = export_store_submission_starter.export_starter(root, root / "build" / "store-submission-starter")

        summary = manifest["evidencePacketSummary"]
        self.assertEqual("tenant_public_store_submission_evidence_packet", summary["packetType"])
        self.assertEqual(export_store_submission_starter.PER_FLAVOR_IMPORT_COMMAND, summary["nextImportCommand"])
        self.assertEqual(export_store_submission_starter.PREFLIGHT_COMMAND, summary["preflightCommand"])
        self.assertEqual(export_store_submission_starter.PER_FLAVOR_INPUT_DIR, summary["perFlavorInputDirectory"])
        self.assertIn("Public status references only", summary["secretBoundary"])
        packet_flavors = {entry["flavor"]: entry for entry in summary["flavors"]}
        self.assertEqual(set(import_store_submission_evidence.FLAVOR_DEFAULTS), set(packet_flavors))
        self.assertEqual(
            "build/store-submission-starter/reelshort/store-submission-evidence.input.example.json",
            packet_flavors["reelshort"]["starterInputExamplePath"],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors/reelshort.input.json",
            packet_flavors["reelshort"]["tenantEvidenceInputPath"],
        )
        self.assertEqual("google_play_internal", packet_flavors["reelshort"]["primaryChannel"])
        self.assertIn("storeProductsConfigured", packet_flavors["reelshort"]["requiredChecklistFlags"])

    def test_prepare_store_submission_inputs_creates_no_secret_per_flavor_workspace(self) -> None:
        import prepare_store_submission_inputs

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_store_submission_starter.export_starter(root, root / "build" / "store-submission-starter")

            manifest = prepare_store_submission_inputs.prepare_workspace(
                root,
                root / "build" / "store-submission-evidence",
            )
            second_manifest = prepare_store_submission_inputs.prepare_workspace(
                root,
                root / "build" / "store-submission-evidence",
            )

            manifest_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.json"
            markdown_path = root / "build" / "store-submission-evidence" / "store-submission-input-workspace.md"
            preflight_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
            preflight_markdown_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md"
            hongguo_input = root / "build" / "store-submission-evidence" / "flavors" / "hongguo.input.json"
            manifest_exists = manifest_path.exists()
            markdown_exists = markdown_path.exists()
            preflight_exists = preflight_path.exists()
            preflight_markdown_exists = preflight_markdown_path.exists()
            hongguo = json.loads(hongguo_input.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
            written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            preflight_report = (
                json.loads(preflight_path.read_text(encoding="utf-8"))
                if preflight_exists
                else {}
            )
            preflight_markdown = (
                preflight_markdown_path.read_text(encoding="utf-8")
                if preflight_markdown_exists
                else ""
            )

        self.assertTrue(manifest_exists)
        self.assertTrue(markdown_exists)
        self.assertTrue(preflight_exists)
        self.assertTrue(preflight_markdown_exists)
        self.assertEqual(manifest["preflightSummary"], written_manifest["preflightSummary"])
        self.assertEqual("blocked", manifest["preflightSummary"]["result"])
        self.assertFalse(manifest["preflightSummary"]["strictImportReady"])
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            manifest["preflightSummary"]["summary"]["blocked"],
        )
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence-preflight.json",
            manifest["preflightSummary"]["preflightReportPath"],
        )
        self.assertEqual(
            "build/store-submission-evidence/store-submission-evidence-preflight.md",
            manifest["preflightSummary"]["preflightMarkdownPath"],
        )
        self.assertEqual("blocked", preflight_report["result"])
        self.assertEqual("store_submission_input_workspace", manifest["packageType"])
        self.assertEqual("created", manifest["inputs"][0]["status"])
        self.assertEqual("exists", second_manifest["inputs"][0]["status"])
        self.assertEqual("single_flavor_submission", manifest["inputs"][0]["inputShape"])
        self.assertFalse(manifest["inputs"][0]["readyForStrictImport"])
        self.assertIn("submissionStatus", manifest["inputs"][0]["preflightBlockers"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(manifest["inputs"]))
        self.assertEqual(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            manifest["inputs"][0]["targetPath"],
        )
        self.assertEqual(["pending_tenant_action"], manifest["blockingPlaceholders"])
        self.assertEqual("tenant_store_submission_public_evidence_input_single_flavor", hongguo["source"])
        self.assertEqual("hongguo", hongguo["flavor"])
        self.assertTrue(hongguo["tenantMustReplacePlaceholders"])
        self.assertEqual("pending_tenant_action", hongguo["submissionStatus"])
        next_commands = "\n".join(manifest["nextCommands"])
        self.assertIn("scripts/store_submission_evidence_preflight.py", next_commands)
        self.assertIn("scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict", next_commands)
        self.assertIn("hongguo.input.json", markdown)
        self.assertIn("Preflight result: `blocked`", markdown)
        self.assertIn("submissionStatus", markdown)
        self.assertIn("Preflight result: `blocked`", preflight_markdown)
        self.assertIn("single-flavor input files", markdown)
        self.assertIn("does not overwrite existing tenant-filled inputs", markdown)
        lowered = (
            json.dumps(manifest, ensure_ascii=False).lower()
            + markdown.lower()
            + preflight_markdown.lower()
        )
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_ios_static_release_config_gate_validates_flavor_schemes_and_plist(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_ios_static_release_config(root)

        self.assertEqual("ios_static_release_config", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("ios/Runner/Info.plist", check.evidence)
        self.assertIn("ios/Runner/PrivacyInfo.xcprivacy", check.evidence)
        self.assertIn("ios/Runner/Runner.entitlements", check.evidence)
        self.assertIn("ios/Runner.xcodeproj/project.pbxproj", check.evidence)
        for flavor in mobile_completion_audit.FLAVORS:
            self.assertIn(f"ios/Flutter/{flavor.capitalize()}.xcconfig", check.evidence)
            self.assertIn(
                f"ios/Runner.xcodeproj/xcshareddata/xcschemes/{flavor}.xcscheme",
                check.evidence,
            )
            self.assertIn(
                f"ios/Runner/Assets.xcassets/AppIcon-{flavor}.appiconset/Contents.json",
                check.evidence,
            )

    def test_open_source_package_gate_validates_zip_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_path = root / "build" / "open-source" / "short-drama-whitelabel-mobile.zip"
            manifest_path = root / "build" / "open-source" / "open-source-template-manifest.json"
            package_path.parent.mkdir(parents=True)
            required = [
                ".github/workflows/mobile-flutter.yml",
                ".gitignore",
                "LICENSE",
                "README.md",
                "docs/open-source-release.md",
                "pubspec.yaml",
                "lib/main.dart",
                "scripts/capture_wysiwyg_previews.mjs",
                "scripts/export_completion_unblocker.py",
                "scripts/export_github_publish_handoff.py",
                "scripts/import_github_publication_evidence.py",
                "scripts/import_store_submission_evidence.py",
                "scripts/ios_runtime_smoke.py",
                "scripts/mobile_completion_closure.py",
                "scripts/prepare_store_submission_inputs.py",
                "assets/config/hongguo/tenant.brand.json",
                "assets/config/douyin/tenant.brand.json",
                "assets/config/hippo/tenant.brand.json",
                "assets/config/reelshort/tenant.brand.json",
                "android/app/build.gradle.kts",
                "ios/Runner/Info.plist",
                "ios/Runner/PrivacyInfo.xcprivacy",
                "ios/Runner/Runner.entitlements",
            ]
            filler = [f"lib/generated/example_{index}.dart" for index in range(120)]
            entry_paths = required + filler
            with zipfile.ZipFile(package_path, "w") as archive:
                for entry_path in entry_paths:
                    archive.writestr(f"short-drama-whitelabel-mobile/{entry_path}", b"demo")
            manifest_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "packageName": "short-drama-whitelabel-mobile",
                    "packagePath": str(package_path.relative_to(root)),
                    "packageSha256": self._sha256(package_path),
                    "missingRequiredEntries": [],
                    "disallowedValueMarkerHits": [],
                    "entries": [
                        {
                            "path": entry_path,
                            "sizeBytes": 4,
                            "sha256": hashlib.sha256(b"demo").hexdigest(),
                        }
                        for entry_path in entry_paths
                    ],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_mobile_open_source_package(root)

        self.assertEqual("mobile_open_source_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/open-source/open-source-template-manifest.json", check.evidence)

    def test_release_artifact_secret_gate_scans_zip_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "build" / "app" / "outputs" / "flutter-apk" / "app-hongguo-release.apk"
            artifact.parent.mkdir(parents=True)
            with zipfile.ZipFile(artifact, "w") as package:
                package.writestr("assets/flutter_assets/AssetManifest.json", "{}")

            check = mobile_completion_audit.check_release_artifact_secret_boundary(root)

        self.assertEqual("release_artifact_secret_boundary", check.id)
        self.assertEqual("passed", check.status)

    def test_android_package_structure_gate_validates_apk_and_aab_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            apk = root / "build" / "app" / "outputs" / "flutter-apk" / "app-hongguo-release.apk"
            aab = root / "build" / "app" / "outputs" / "bundle" / "hongguoRelease" / "app-hongguo-release.aab"
            apk.parent.mkdir(parents=True)
            aab.parent.mkdir(parents=True)
            self._write_zip(
                apk,
                [
                    "AndroidManifest.xml",
                    "assets/flutter_assets/AssetManifest.bin",
                    "assets/flutter_assets/assets/config/hongguo/tenant.brand.json",
                    "assets/flutter_assets/assets/config/hongguo/tenant.template.json",
                    "lib/arm64-v8a/libapp.so",
                    "lib/arm64-v8a/libflutter.so",
                ],
            )
            self._write_zip(
                aab,
                [
                    "BundleConfig.pb",
                    "base/manifest/AndroidManifest.xml",
                    "base/assets/flutter_assets/AssetManifest.bin",
                    "base/assets/flutter_assets/assets/config/hongguo/tenant.brand.json",
                    "base/assets/flutter_assets/assets/config/hongguo/tenant.template.json",
                    "base/lib/arm64-v8a/libapp.so",
                    "base/lib/arm64-v8a/libflutter.so",
                ],
            )
            manifest = {
                "artifacts": [
                    {
                        "flavor": "hongguo",
                        "platform": "android",
                        "mode": "release",
                        "packageType": "apk",
                        "path": str(apk.relative_to(root)),
                    },
                    {
                        "flavor": "hongguo",
                        "platform": "android",
                        "mode": "release",
                        "packageType": "appbundle",
                        "path": str(aab.relative_to(root)),
                    },
                ],
            }

            check = mobile_completion_audit.check_android_package_structure(
                root,
                manifest,
            )

        self.assertEqual("android_package_structure", check.id)
        self.assertEqual("passed", check.status)

    def test_android_runtime_smoke_gate_validates_optional_device_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            smoke_path = root / "build" / "runtime-smoke" / "android-runtime-smoke.json"
            screenshot_dir = root / "build" / "runtime-smoke" / "screenshots"
            screenshot_dir.mkdir(parents=True)
            runs = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                apk = root / "build" / "app" / "outputs" / "flutter-apk" / f"app-{flavor}-release.apk"
                apk.parent.mkdir(parents=True, exist_ok=True)
                apk.write_bytes(f"{flavor}-apk".encode("utf-8"))
                screenshot = screenshot_dir / f"{flavor}-launch.png"
                screenshot.write_bytes(self._fake_png())
                runs.append({
                    "flavor": flavor,
                    "applicationId": expected["applicationId"],
                    "appName": expected["appName"],
                    "apkPath": str(apk.relative_to(root)),
                    "apkSha256": self._sha256(apk),
                    "installResult": "passed",
                    "launchResult": "passed",
                    "processPid": "1234",
                    "screenshotPath": str(screenshot.relative_to(root)),
                    "screenshotSha256": self._sha256(screenshot),
                    "screenshotSizeBytes": screenshot.stat().st_size,
                })
            smoke_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "deviceSerial": "emulator-5554",
                    "runs": runs,
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_android_runtime_smoke(root)

        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual("android_runtime_smoke", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/runtime-smoke/android-runtime-smoke.json", check.evidence)

    def test_ios_runtime_smoke_gate_validates_optional_simulator_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            smoke_path = root / "build" / "runtime-smoke" / "ios-runtime-smoke.json"
            screenshot_dir = root / "build" / "runtime-smoke" / "ios-screenshots"
            app_dir = root / "build" / "ios" / "iphonesimulator" / "Runner.app"
            screenshot_dir.mkdir(parents=True)
            app_dir.mkdir(parents=True)
            (app_dir / "Info.plist").write_bytes(b"fake-info")
            runs = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                screenshot = screenshot_dir / f"{flavor}-launch.png"
                screenshot.write_bytes(self._fake_png())
                runs.append({
                    "flavor": flavor,
                    "applicationId": expected["applicationId"],
                    "appName": expected["appName"],
                    "appPath": str(app_dir.relative_to(root)),
                    "appSha256": self._sha256(app_dir / "Info.plist"),
                    "appSizeBytes": 9,
                    "installResult": "passed",
                    "launchResult": "passed",
                    "processPid": "1234",
                    "screenshotPath": str(screenshot.relative_to(root)),
                    "screenshotSha256": self._sha256(screenshot),
                    "screenshotSizeBytes": screenshot.stat().st_size,
                })
            smoke_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "device": {
                        "name": "iPhone 17",
                        "udid": "SIM-UDID",
                        "state": "Booted",
                        "runtime": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                    },
                    "runs": runs,
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_ios_runtime_smoke(root)

        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual("ios_runtime_smoke", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/runtime-smoke/ios-runtime-smoke.json", check.evidence)

    def test_ios_runtime_smoke_requires_explicit_boot_when_no_simulator_is_booted(self) -> None:
        def fake_command_output(command: list[str], *, timeout: int = 60, check: bool = True) -> str:
            if command == ["xcrun", "simctl", "list", "devices", "available", "--json"]:
                return json.dumps({
                    "devices": {
                        "com.apple.CoreSimulator.SimRuntime.iOS-26-5": [
                            {
                                "name": "iPhone 17",
                                "udid": "SIM-UDID",
                                "state": "Shutdown",
                                "isAvailable": True,
                            },
                        ],
                    },
                })
            raise AssertionError(command)

        with mock.patch.object(ios_runtime_smoke, "command_output", fake_command_output):
            with self.assertRaisesRegex(ios_runtime_smoke.SmokeError, "--boot-simulator"):
                ios_runtime_smoke.select_simulator(boot_if_needed=False)

    def test_ios_runtime_smoke_uses_outer_timeout_to_resolve_flutter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flutter_dir = root / "ios" / "Flutter"
            flutter_dir.mkdir(parents=True)
            (flutter_dir / "WhitelabelDefaults.xcconfig").write_text("default", encoding="utf-8")
            (flutter_dir / "Hongguo.xcconfig").write_text("hongguo", encoding="utf-8")
            app_path = root / "build" / "ios" / "iphonesimulator" / "Runner.app"
            app_path.mkdir(parents=True)

            calls: list[tuple[list[str], int]] = []

            def fake_command_output(command: list[str], *, timeout: int = 60, check: bool = True) -> str:
                calls.append((command, timeout))
                if command[0].endswith("resolve_flutter_bin.sh"):
                    return "/tmp/flutter"
                return ""

            with (
                mock.patch.object(ios_runtime_smoke, "ROOT", root),
                mock.patch.object(ios_runtime_smoke, "command_output", fake_command_output),
            ):
                result = ios_runtime_smoke.build_simulator_app("hongguo", timeout=777)

        self.assertEqual(app_path, result)
        self.assertEqual(777, calls[0][1])
        self.assertIn("--no-pub", calls[1][0])
        self.assertNotIn("--flavor", calls[1][0])

    def test_ios_build_matrix_gate_validates_unsigned_build_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix_path = root / "build" / "ios-build-matrix" / "ios-build-matrix.json"
            info_dir = root / "build" / "ios-build-matrix" / "app-info"
            info_dir.mkdir(parents=True)
            runs = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                for mode in ["debug", "release"]:
                    snapshot = info_dir / f"{flavor}-{mode}-info.json"
                    snapshot.write_text(
                        json.dumps({
                            "flavor": flavor,
                            "mode": mode,
                            "bundleIdentifier": expected["applicationId"],
                            "displayName": expected["appName"],
                        }),
                        encoding="utf-8",
                    )
                    runs.append({
                        "flavor": flavor,
                        "mode": mode,
                        "platform": "ios",
                        "applicationId": expected["applicationId"],
                        "appName": expected["appName"],
                        "command": ["./scripts/build_flavor.sh", flavor, "ios", mode],
                        "exitCode": 0,
                        "buildResult": "passed",
                        "app": {
                            "bundleIdentifier": expected["applicationId"],
                            "displayName": expected["appName"],
                            "appSizeBytes": 1024,
                            "infoSnapshotPath": str(snapshot.relative_to(root)),
                            "infoSnapshotSha256": self._sha256(snapshot),
                        },
                    })
            matrix_path.parent.mkdir(parents=True, exist_ok=True)
            matrix_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "requiredModes": ["debug", "release"],
                    "runs": runs,
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_ios_build_matrix(root)

        self.assertEqual("ios_build_matrix", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/ios-build-matrix/ios-build-matrix.json", check.evidence)

    def test_ios_ci_artifact_evidence_gate_validates_imported_github_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "build" / "ios-ci-evidence" / "ios-ci-artifacts.json"
            info_dir = root / "build" / "ios-ci-evidence" / "app-info"
            info_dir.mkdir(parents=True)
            runs = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                snapshot = info_dir / f"{flavor}-ci-info.json"
                snapshot.write_text(
                    json.dumps({
                        "flavor": flavor,
                        "platform": "ios",
                        "source": "github_actions_unsigned_artifact",
                        "bundleIdentifier": expected["applicationId"],
                        "displayName": expected["appName"],
                    }),
                    encoding="utf-8",
                )
                runs.append({
                    "flavor": flavor,
                    "applicationId": expected["applicationId"],
                    "appName": expected["appName"],
                    "artifactName": f"mobile-{flavor}-ios-unsigned",
                    "importResult": "passed",
                    "app": {
                        "source": "github_actions_unsigned_artifact",
                        "bundleIdentifier": expected["applicationId"],
                        "displayName": expected["appName"],
                        "appSizeBytes": 2048,
                        "infoSnapshotPath": str(snapshot.relative_to(root)),
                        "infoSnapshotSha256": self._sha256(snapshot),
                    },
                })
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "runs": runs,
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_ios_ci_artifact_evidence(root)

        self.assertEqual("ios_ci_artifact_evidence", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/ios-ci-evidence/ios-ci-artifacts.json", check.evidence)

    def test_remote_ios_ci_evidence_makes_local_ios_diagnostics_nonblocking(self) -> None:
        checks = [
            mobile_completion_audit.Check(
                "ios_build_matrix",
                "blocked",
                "local Xcode unavailable",
                ["build/ios-build-matrix/ios-build-matrix.json"],
            ),
            mobile_completion_audit.Check(
                "ios_build_environment",
                "blocked",
                "local Xcode unavailable",
                ["xcode-select -p: /Library/Developer/CommandLineTools"],
            ),
            mobile_completion_audit.Check(
                "ios_ci_artifact_evidence",
                "passed",
                "Downloaded GitHub Actions unsigned iOS artifacts were imported for all five flavors.",
                ["build/ios-ci-evidence/ios-ci-artifacts.json"],
            ),
            mobile_completion_audit.Check(
                "ci_workflow",
                "passed",
                "CI covers five-flavor unsigned iOS debug builds and five-flavor unsigned iOS release builds.",
                ["../.github/workflows/mobile-flutter.yml"],
            ),
            mobile_completion_audit.Check(
                "store_submission_evidence",
                "blocked",
                "tenant store submission evidence is missing",
                ["build/store-submission-evidence/store-submission-evidence.json"],
            ),
        ]

        bounded_checks = mobile_completion_audit.apply_completion_boundaries(checks)
        by_id = {check.id: check for check in bounded_checks}
        summary = mobile_completion_audit.completion_summary(bounded_checks)

        self.assertFalse(by_id["ios_build_matrix"].completion_blocking)
        self.assertFalse(by_id["ios_build_environment"].completion_blocking)
        self.assertTrue(by_id["store_submission_evidence"].completion_blocking)
        self.assertEqual(0, summary["failed"])
        self.assertEqual(1, summary["blocked"])
        self.assertEqual("blocked", summary["allStatuses"]["ios_build_matrix"])
        self.assertEqual("blocked", summary["allStatuses"]["ios_build_environment"])

    def test_store_submission_evidence_gate_validates_public_submission_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            evidence_dir.mkdir(parents=True)
            template_path.write_text(
                json.dumps({"schemaVersion": 1, "template": True}),
                encoding="utf-8",
            )
            guide_path.write_text(
                "# Store Submission Evidence Guide\n",
                encoding="utf-8",
            )
            source_path.write_text(
                json.dumps({"schemaVersion": 1, "source": True}),
                encoding="utf-8",
            )
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            submissions = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                channel = mobile_completion_audit.STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
                checklist = {
                    flag: True
                    for flag in mobile_completion_audit.store_submission_required_flags(channel)
                }
                submissions.append({
                    "flavor": flavor,
                    "templateApplicationId": expected["applicationId"],
                    "templateAppName": expected["appName"],
                    "applicationId": f"{expected['applicationId']}.tenant",
                    "appName": f"{expected['appName']} Tenant",
                    "storeComplianceMode": "app_store" if channel == "app_store_testflight" else "play_store" if channel == "google_play_internal" else "android_direct",
                    "primaryChannel": channel,
                    "submissionStatus": status_by_channel[channel],
                    "publicChecklist": checklist,
                    "publicEvidenceRefs": [f"{flavor} tenant-owned public store evidence"],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                    "importResult": "passed",
                })
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "sourcePath": "build/store-submission-evidence/store-submission-evidence.input.json",
                    "sourceSha256": self._sha256(source_path),
                    "templatePath": "build/store-submission-evidence/store-submission-evidence.template.json",
                    "templateSha256": self._sha256(template_path),
                    "guidePath": "build/store-submission-evidence/store-submission-evidence.guide.md",
                    "guideSha256": self._sha256(guide_path),
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "submissions": submissions,
                    "missingFlavors": [],
                    "blockedFlavors": [],
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_store_submission_evidence(root)

        self.assertEqual("store_submission_evidence", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn(
            "build/store-submission-evidence/store-submission-evidence.json",
            check.evidence,
        )

    def test_store_submission_evidence_gate_rejects_forged_local_url_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            evidence_dir.mkdir(parents=True)
            template_path.write_text(
                json.dumps({"schemaVersion": 1, "template": True}),
                encoding="utf-8",
            )
            guide_path.write_text(
                "# Store Submission Evidence Guide\n",
                encoding="utf-8",
            )
            source_path.write_text(
                json.dumps({"schemaVersion": 1, "source": True}),
                encoding="utf-8",
            )
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            submissions = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                channel = mobile_completion_audit.STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
                checklist = {
                    flag: True
                    for flag in mobile_completion_audit.store_submission_required_flags(channel)
                }
                submissions.append({
                    "flavor": flavor,
                    "templateApplicationId": expected["applicationId"],
                    "templateAppName": expected["appName"],
                    "applicationId": f"{expected['applicationId']}.tenant",
                    "appName": f"{expected['appName']} Tenant",
                    "storeComplianceMode": "app_store" if channel == "app_store_testflight" else "play_store" if channel == "google_play_internal" else "android_direct",
                    "primaryChannel": channel,
                    "submissionStatus": status_by_channel[channel],
                    "publicChecklist": checklist,
                    "publicEvidenceRefs": [f"{flavor} tenant-owned public store evidence"],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                    "importResult": "passed",
                })
            submissions[0]["publicEvidenceRefs"] = [{
                "label": "Forged local review URL",
                "type": "support_url",
                "url": "https://localhost/review",
            }]
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "sourcePath": "build/store-submission-evidence/store-submission-evidence.input.json",
                    "sourceSha256": self._sha256(source_path),
                    "templatePath": "build/store-submission-evidence/store-submission-evidence.template.json",
                    "templateSha256": self._sha256(template_path),
                    "guidePath": "build/store-submission-evidence/store-submission-evidence.guide.md",
                    "guideSha256": self._sha256(guide_path),
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "submissions": submissions,
                    "missingFlavors": [],
                    "blockedFlavors": [],
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_store_submission_evidence(root)

        self.assertEqual("store_submission_evidence", check.id)
        self.assertEqual("failed", check.status)
        self.assertIn("coolshow:publicEvidenceRefsUrl", check.detail)

    def test_store_submission_evidence_gate_rejects_forged_future_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            evidence_dir.mkdir(parents=True)
            template_path.write_text(
                json.dumps({"schemaVersion": 1, "template": True}),
                encoding="utf-8",
            )
            guide_path.write_text(
                "# Store Submission Evidence Guide\n",
                encoding="utf-8",
            )
            source_path.write_text(
                json.dumps({"schemaVersion": 1, "source": True}),
                encoding="utf-8",
            )
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            submissions = []
            for flavor, expected in mobile_completion_audit.FLAVORS.items():
                channel = mobile_completion_audit.STORE_SUBMISSION_PRIMARY_CHANNEL_BY_FLAVOR[flavor]
                checklist = {
                    flag: True
                    for flag in mobile_completion_audit.store_submission_required_flags(channel)
                }
                submissions.append({
                    "flavor": flavor,
                    "templateApplicationId": expected["applicationId"],
                    "templateAppName": expected["appName"],
                    "applicationId": f"{expected['applicationId']}.tenant",
                    "appName": f"{expected['appName']} Tenant",
                    "storeComplianceMode": "app_store" if channel == "app_store_testflight" else "play_store" if channel == "google_play_internal" else "android_direct",
                    "primaryChannel": channel,
                    "submissionStatus": status_by_channel[channel],
                    "publicChecklist": checklist,
                    "publicEvidenceRefs": [f"{flavor} tenant-owned public store evidence"],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                    "importResult": "passed",
                })
            submissions[0]["evidenceCapturedAt"] = "2999-01-01T00:00:00Z"
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "passed",
                    "sourcePath": "build/store-submission-evidence/store-submission-evidence.input.json",
                    "sourceSha256": self._sha256(source_path),
                    "templatePath": "build/store-submission-evidence/store-submission-evidence.template.json",
                    "templateSha256": self._sha256(template_path),
                    "guidePath": "build/store-submission-evidence/store-submission-evidence.guide.md",
                    "guideSha256": self._sha256(guide_path),
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "submissions": submissions,
                    "missingFlavors": [],
                    "blockedFlavors": [],
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_store_submission_evidence(root)

        self.assertEqual("store_submission_evidence", check.id)
        self.assertEqual("failed", check.status)
        self.assertIn("coolshow:evidenceCapturedAt", check.detail)

    def test_store_submission_evidence_gate_requires_blocked_remediation_hints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_path = evidence_dir / "store-submission-evidence.json"
            evidence_dir.mkdir(parents=True)
            evidence_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "result": "blocked",
                    "requiredFlavors": list(mobile_completion_audit.FLAVORS),
                    "submissions": [],
                    "missingFlavors": ["hongguo"],
                    "blockedFlavors": [{
                        "flavor": "hongguo",
                        "blockers": ["missing-submission"],
                    }],
                    "forbiddenMarkerHits": [],
                }),
                encoding="utf-8",
            )

            check = mobile_completion_audit.check_store_submission_evidence(root)

        self.assertEqual("store_submission_evidence", check.id)
        self.assertEqual("failed", check.status)
        self.assertIn("blockedFlavors:hongguo:remediationHints", check.detail)

    def test_mobile_python_scripts_with_shebang_are_executable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        scripts = sorted((root / "scripts").glob("*.py"))
        non_executable = []
        for script in scripts:
            first_line = script.read_text(encoding="utf-8").splitlines()[0]
            if first_line.startswith("#!") and not os.access(script, os.X_OK):
                non_executable.append(script.name)

        self.assertEqual([], non_executable)

    def test_check_mobile_runs_runtime_smoke_regression_test(self) -> None:
        root = Path(__file__).resolve().parents[1]
        check_mobile = (root / "scripts" / "check_mobile.sh").read_text(encoding="utf-8")

        self.assertIn('"$script_dir/android_runtime_smoke_test.py"', check_mobile)
        self.assertIn('"$script_dir/ios_runtime_smoke.py"', check_mobile)
        self.assertIn('python3 "$script_dir/android_runtime_smoke_test.py"', check_mobile)

    def test_store_submission_evidence_import_blocks_signing_file_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_dir.mkdir(parents=True)
            source_path = evidence_dir / "store-submission-evidence.input.json"
            output_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            submissions = []
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                submission = import_store_submission_evidence.template_submission(expected)
                submission.update({
                    "submissionStatus": status_by_channel[channel],
                    "publicEvidenceRefs": [
                        f"{flavor} public TestFlight or direct distribution status",
                    ],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                })
                for flag in import_store_submission_evidence.required_flags(channel):
                    submission[flag] = True
                submissions.append(submission)
            submissions[0]["publicEvidenceRefs"] = [
                "ios_distribution_certificate.p12",
                "tenant TestFlight build 42",
            ]
            source_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "source": "tenant_store_submission_public_evidence_input",
                    "submissions": submissions,
                }),
                encoding="utf-8",
            )

            report = import_store_submission_evidence.import_evidence(
                source_path,
                output_path,
                template_path,
                guide_path,
            )

        self.assertEqual("blocked", report["result"])
        blocked_by_flavor = {
            item["flavor"]: item["blockers"]
            for item in report["blockedFlavors"]
        }
        first_flavor = next(iter(import_store_submission_evidence.FLAVOR_DEFAULTS))
        self.assertIn(
            "publicEvidenceRefsForbiddenMarkers",
            blocked_by_flavor[first_flavor],
        )
        blocked_hints = {
            item["flavor"]: item.get("remediationHints", [])
            for item in report["blockedFlavors"]
        }
        self.assertIn(
            "Remove signing or credential filenames",
            " ".join(blocked_hints[first_flavor]),
        )
        output_text = json.dumps(report, ensure_ascii=False).lower()
        self.assertNotIn("ios_distribution_certificate.p12", output_text)

    def test_store_submission_evidence_import_accepts_structured_public_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            evidence_dir.mkdir(parents=True)
            source_path = evidence_dir / "store-submission-evidence.input.json"
            output_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            evidence_type_by_channel = {
                "app_store_testflight": "testflight_build",
                "google_play_internal": "play_internal_track",
                "android_direct": "direct_package_checksum",
            }
            submissions = []
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                submission = import_store_submission_evidence.template_submission(expected)
                submission.update({
                    "submissionStatus": status_by_channel[channel],
                    "publicEvidenceRefs": [
                        {
                            "label": f"{flavor} public store status",
                            "type": evidence_type_by_channel[channel],
                            "value": f"{flavor}-tenant-build-42",
                            "capturedAt": "2026-06-14T00:00:00Z",
                        },
                    ],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                })
                for flag in import_store_submission_evidence.required_flags(channel):
                    submission[flag] = True
                submissions.append(submission)
            source_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "source": "tenant_store_submission_public_evidence_input",
                    "submissions": submissions,
                }),
                encoding="utf-8",
            )

            report = import_store_submission_evidence.import_evidence(
                source_path,
                output_path,
                template_path,
                guide_path,
            )

        self.assertEqual("passed", report["result"])
        refs_by_flavor = {
            submission["flavor"]: submission["publicEvidenceRefs"][0]
            for submission in report["submissions"]
        }
        self.assertEqual("direct_package_checksum", refs_by_flavor["coolshow"]["type"])
        self.assertEqual("coolshow-tenant-build-42", refs_by_flavor["coolshow"]["value"])
        self.assertEqual("testflight_build", refs_by_flavor["hongguo"]["type"])
        self.assertEqual("hongguo-tenant-build-42", refs_by_flavor["hongguo"]["value"])

    def test_store_submission_evidence_import_rejects_non_public_https_urls(self) -> None:
        invalid_urls = [
            "http://example.com/app-review",
            "file:///tmp/store-evidence.pdf",
            "https://localhost/app-review",
            "https://127.0.0.1/app-review",
            "https://[::1]/app-review",
            "https://10.0.0.9/app-review",
            "https://172.16.10.3/app-review",
            "https://192.168.1.20/app-review",
            "https://tenant-store.local/app-review",
        ]

        for invalid_url in invalid_urls:
            with self.subTest(invalid_url=invalid_url):
                normalized, blockers = import_store_submission_evidence.normalized_evidence_ref({
                    "label": "Tenant app review evidence",
                    "type": "support_url",
                    "url": invalid_url,
                })

                self.assertIsNone(normalized)
                self.assertEqual(["publicEvidenceRefsUrl"], blockers)

    def test_store_submission_evidence_import_accepts_public_https_urls(self) -> None:
        normalized, blockers = import_store_submission_evidence.normalized_evidence_ref({
            "label": "Tenant privacy URL",
            "type": "privacy_url",
            "url": "https://example.com/privacy",
        })

        self.assertEqual([], blockers)
        self.assertEqual({
            "label": "Tenant privacy URL",
            "type": "privacy_url",
            "url": "https://example.com/privacy",
        }, normalized)

    def test_store_submission_evidence_import_rejects_invalid_or_future_timestamps(self) -> None:
        for captured_at in ["not-a-date", "2999-01-01T00:00:00Z"]:
            with self.subTest(captured_at=captured_at):
                normalized, blockers = import_store_submission_evidence.normalized_evidence_ref({
                    "label": "Tenant review timestamp",
                    "type": "review_state",
                    "value": "testflight_uploaded",
                    "capturedAt": captured_at,
                })

                self.assertIsNone(normalized)
                self.assertEqual(["publicEvidenceRefsCapturedAt"], blockers)

    def test_store_submission_evidence_import_merges_per_flavor_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_dir = evidence_dir / "flavors"
            source_dir.mkdir(parents=True)
            source_path = evidence_dir / "store-submission-evidence.input.json"
            output_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                submission = import_store_submission_evidence.template_submission(expected)
                submission.update({
                    "submissionStatus": status_by_channel[channel],
                    "publicEvidenceRefs": [
                        {
                            "label": f"{flavor} public release evidence",
                            "type": "testflight_build" if channel == "app_store_testflight" else "play_internal_track" if channel == "google_play_internal" else "direct_package_checksum",
                            "value": f"{flavor}-tenant-public-evidence",
                        },
                    ],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                })
                for flag in import_store_submission_evidence.required_flags(channel):
                    submission[flag] = True
                (source_dir / f"{flavor}.input.json").write_text(
                    json.dumps({
                        "schemaVersion": 1,
                        "source": "tenant_store_submission_public_evidence_input",
                        "submissions": [submission],
                    }),
                    encoding="utf-8",
                )

            report = import_store_submission_evidence.import_evidence(
                source_path,
                output_path,
                template_path,
                guide_path,
            )

            self.assertTrue(source_path.exists())
            combined_input = json.loads(source_path.read_text(encoding="utf-8"))

        self.assertEqual("passed", report["result"])
        self.assertEqual("per_flavor", report["sourceMode"])
        self.assertEqual(
            list(import_store_submission_evidence.FLAVOR_DEFAULTS),
            [submission["flavor"] for submission in combined_input["submissions"]],
        )
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(report["sourceInputPaths"]))
        self.assertTrue(
            report["sourcePath"].endswith("build/store-submission-evidence/store-submission-evidence.input.json"),
        )

    def test_store_submission_evidence_import_source_dir_overwrites_stale_combined_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_dir = evidence_dir / "flavors"
            source_dir.mkdir(parents=True)
            source_path = evidence_dir / "store-submission-evidence.input.json"
            output_path = evidence_dir / "store-submission-evidence.json"
            template_path = evidence_dir / "store-submission-evidence.template.json"
            guide_path = evidence_dir / "store-submission-evidence.guide.md"
            source_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "source": "tenant_store_submission_public_evidence_input",
                    "submissions": [
                        {
                            "flavor": "hongguo",
                            "submissionStatus": "pending_tenant_action",
                        },
                    ],
                }),
                encoding="utf-8",
            )
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                submission = import_store_submission_evidence.template_submission(expected)
                submission.update({
                    "submissionStatus": status_by_channel[channel],
                    "publicEvidenceRefs": [f"{flavor} tenant-owned public evidence"],
                    "evidenceCapturedAt": "2026-06-14T00:00:00Z",
                })
                for flag in import_store_submission_evidence.required_flags(channel):
                    submission[flag] = True
                (source_dir / f"{flavor}.input.json").write_text(
                    json.dumps({"schemaVersion": 1, "submissions": [submission]}),
                    encoding="utf-8",
                )

            report = import_store_submission_evidence.import_evidence(
                source_path,
                output_path,
                template_path,
                guide_path,
                source_dir,
            )

        self.assertEqual("passed", report["result"])
        self.assertEqual("per_flavor", report["sourceMode"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(report["sourceInputPaths"]))

    def test_store_submission_evidence_preflight_reports_missing_per_flavor_inputs(self) -> None:
        import store_submission_evidence_preflight

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            source_dir = evidence_dir / "flavors"
            output_path = evidence_dir / "store-submission-evidence-preflight.json"
            markdown_path = evidence_dir / "store-submission-evidence-preflight.md"

            report = store_submission_evidence_preflight.build_preflight_report(
                source=source_path,
                source_dir=source_dir,
                output=output_path,
                markdown=markdown_path,
            )

            self.assertTrue(output_path.exists())
            self.assertTrue(markdown_path.exists())
            markdown_text = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("blocked", report["result"])
        self.assertEqual("missing", report["sourceMode"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), report["summary"]["blocked"])
        self.assertIn(
            "public HTTPS URL",
            " ".join(report["qualityRules"]),
        )
        self.assertIn(
            "ISO-8601",
            " ".join(report["qualityRules"]),
        )
        self.assertIn("public HTTPS URL", markdown_text)
        self.assertIn("ISO-8601", markdown_text)
        self.assertEqual(
            list(import_store_submission_evidence.FLAVOR_DEFAULTS),
            [flavor["flavor"] for flavor in report["flavors"]],
        )
        self.assertEqual(
            "build/store-submission-evidence/flavors/coolshow.input.json",
            report["flavors"][0]["tenantEvidenceInputPath"],
        )
        self.assertIn("input-evidence-missing", report["flavors"][0]["blockers"])
        self.assertIn(
            "build/store-submission-starter/coolshow/store-submission-evidence.input.example.json",
            " ".join(report["flavors"][0]["remediationHints"]),
        )
        self.assertIn("store-submission-evidence-preflight.md", report["markdownPath"])
        self.assertFalse(report["strictImportReadiness"]["ready"])
        self.assertEqual(
            "cd mobile && ./scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict",
            report["strictImportReadiness"]["command"],
        )
        self.assertEqual(
            len(import_store_submission_evidence.FLAVOR_DEFAULTS),
            len(report["strictImportReadiness"]["blockedBy"]),
        )
        blocked_by_flavor = {
            row["flavor"]: row
            for row in report["strictImportReadiness"]["blockedBy"]
        }
        self.assertEqual(
            {
                "flavor": "coolshow",
                "inputPath": "build/store-submission-evidence/flavors/coolshow.input.json",
                "blockers": ["input-evidence-missing"],
            },
            blocked_by_flavor["coolshow"],
        )
        flavors_by_name = {
            row["flavor"]: row
            for row in report["flavors"]
        }
        self.assertFalse(flavors_by_name["hongguo"]["readyForStrictImport"])
        self.assertEqual(
            ["input-evidence-missing"],
            flavors_by_name["hongguo"]["strictImportBlockedBy"],
        )

    def test_store_submission_evidence_preflight_reports_field_remediation_hints(self) -> None:
        import store_submission_evidence_preflight

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            source_dir = evidence_dir / "flavors"
            output_path = evidence_dir / "store-submission-evidence-preflight.json"
            markdown_path = evidence_dir / "store-submission-evidence-preflight.md"
            source_dir.mkdir(parents=True)
            submission = import_store_submission_evidence.template_submission(
                import_store_submission_evidence.expected_entries()["hongguo"],
            )
            submission.update({
                "submissionStatus": "pending_tenant_action",
                "publicEvidenceRefs": [
                    {
                        "label": "Local status page",
                        "type": "testflight_build",
                        "url": "http://localhost/testflight",
                    },
                ],
                "evidenceCapturedAt": "2099-01-01T00:00:00Z",
            })
            (source_dir / "hongguo.input.json").write_text(
                json.dumps({"schemaVersion": 1, "submissions": [submission]}),
                encoding="utf-8",
            )

            report = store_submission_evidence_preflight.build_preflight_report(
                source=source_path,
                source_dir=source_dir,
                output=output_path,
                markdown=markdown_path,
            )
            markdown_text = markdown_path.read_text(encoding="utf-8")

        hongguo = next(row for row in report["flavors"] if row["flavor"] == "hongguo")
        hints = " ".join(hongguo["remediationHints"])
        self.assertIn("submissionStatus", hongguo["blockers"])
        self.assertIn("publicEvidenceRefsUrl", hongguo["blockers"])
        self.assertIn("evidenceCapturedAt", hongguo["blockers"])
        self.assertIn("testflight_uploaded", hints)
        self.assertIn("public HTTPS", hints)
        self.assertIn("timezone-aware ISO-8601", hints)
        self.assertIn("tenantDeveloperAccountReady", hints)
        self.assertIn("Remediation Hints", markdown_text)

    def test_store_submission_evidence_preflight_reports_duplicate_and_unknown_flavors(self) -> None:
        import store_submission_evidence_preflight

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            source_dir = evidence_dir / "flavors"
            output_path = evidence_dir / "store-submission-evidence-preflight.json"
            markdown_path = evidence_dir / "store-submission-evidence-preflight.md"
            evidence_dir.mkdir(parents=True)

            hongguo = import_store_submission_evidence.template_submission(
                import_store_submission_evidence.expected_entries()["hongguo"],
            )
            source_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "submissions": [
                        hongguo,
                        {**hongguo, "appName": "Duplicate GoldFruit"},
                        {"flavor": "ghost", "appName": "Unknown Flavor"},
                        "not-an-object",
                    ],
                }),
                encoding="utf-8",
            )

            report = store_submission_evidence_preflight.build_preflight_report(
                source=source_path,
                source_dir=source_dir,
                output=output_path,
                markdown=markdown_path,
            )
            markdown_text = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("failed", report["result"])
        self.assertIn("duplicate-flavor:hongguo", report["sourceIssues"])
        self.assertIn("unknown-flavor:ghost", report["sourceIssues"])
        self.assertIn("submission-not-object", report["sourceIssues"])
        self.assertEqual(3, report["summary"]["failed"])
        self.assertIn("duplicate-flavor:hongguo", markdown_text)
        self.assertIn("unknown-flavor:ghost", markdown_text)

    def test_store_submission_evidence_preflight_prefers_per_flavor_inputs_over_stale_combined_source(self) -> None:
        import store_submission_evidence_preflight

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "build" / "store-submission-evidence"
            source_path = evidence_dir / "store-submission-evidence.input.json"
            source_dir = evidence_dir / "flavors"
            output_path = evidence_dir / "store-submission-evidence-preflight.json"
            markdown_path = evidence_dir / "store-submission-evidence-preflight.md"
            source_dir.mkdir(parents=True)
            source_path.write_text(
                json.dumps({
                    "schemaVersion": 1,
                    "submissions": [
                        {
                            "flavor": "hongguo",
                            "submissionStatus": "pending_tenant_action",
                        },
                    ],
                }),
                encoding="utf-8",
            )
            status_by_channel = {
                "app_store_testflight": "testflight_uploaded",
                "google_play_internal": "play_internal_uploaded",
                "android_direct": "direct_signed_package_ready",
            }
            ref_type_by_channel = {
                "app_store_testflight": "testflight_build",
                "google_play_internal": "play_internal_track",
                "android_direct": "direct_package_checksum",
            }
            for flavor, expected in import_store_submission_evidence.expected_entries().items():
                channel = expected["primaryChannel"]
                submission = import_store_submission_evidence.template_submission(expected)
                submission.update({
                    "submissionStatus": status_by_channel[channel],
                    "applicationId": f"{expected['applicationId']}.tenant",
                    "appName": f"{expected['appName']} Tenant",
                    "publicEvidenceRefs": [
                        {
                            "label": f"{flavor} tenant store evidence",
                            "type": ref_type_by_channel[channel],
                            "value": f"{flavor}-store-evidence",
                            "capturedAt": "2000-01-01T00:00:00Z",
                        },
                    ],
                    "evidenceCapturedAt": "2000-01-01T00:00:00Z",
                })
                for flag in import_store_submission_evidence.required_flags(channel):
                    submission[flag] = True
                (source_dir / f"{flavor}.input.json").write_text(
                    json.dumps({
                        "schemaVersion": 1,
                        "submissions": [submission],
                    }),
                    encoding="utf-8",
                )

            report = store_submission_evidence_preflight.build_preflight_report(
                source=source_path,
                source_dir=source_dir,
                output=output_path,
                markdown=markdown_path,
            )

        self.assertEqual("passed", report["result"])
        self.assertEqual("per_flavor", report["sourceMode"])
        self.assertEqual(len(import_store_submission_evidence.FLAVOR_DEFAULTS), len(report["sourceInputPaths"]))
        self.assertEqual({"passed": len(import_store_submission_evidence.FLAVOR_DEFAULTS), "blocked": 0, "failed": 0}, report["summary"])
        self.assertTrue(report["strictImportReadiness"]["ready"])
        self.assertEqual([], report["strictImportReadiness"]["blockedBy"])
        self.assertTrue(all(row["readyForStrictImport"] for row in report["flavors"]))

    def test_store_submission_evidence_preflight_audit_requires_quality_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.json"
            markdown_path = root / "build" / "store-submission-evidence" / "store-submission-evidence-preflight.md"
            output_path.parent.mkdir(parents=True)
            output_path.write_text("{}", encoding="utf-8")
            markdown_path.write_text("# Store Submission Evidence Preflight\n", encoding="utf-8")
            report = {
                "schemaVersion": 1,
                "outputPath": "build/store-submission-evidence/store-submission-evidence-preflight.json",
                "markdownPath": "build/store-submission-evidence/store-submission-evidence-preflight.md",
                "flavors": [
                    {"flavor": flavor, "status": "blocked", "blockers": ["input-evidence-missing"]}
                    for flavor in import_store_submission_evidence.FLAVOR_DEFAULTS
                ],
                "summary": {
                    "passed": 0,
                    "blocked": len(import_store_submission_evidence.FLAVOR_DEFAULTS),
                    "failed": 0,
                },
            }

            with mock.patch.object(
                mobile_completion_audit.store_submission_evidence_preflight,
                "build_preflight_report",
                return_value=report,
            ):
                check = mobile_completion_audit.check_store_submission_evidence_preflight(root)

        self.assertEqual("store_submission_evidence_preflight", check.id)
        self.assertEqual("failed", check.status)
        self.assertIn("qualityRules", check.detail)
        self.assertIn("remediationHints", check.detail)
        self.assertIn("strictImportReadiness", check.detail)

    def test_apk_badging_parser_extracts_publishable_manifest_fields(self) -> None:
        badging = "\n".join(
            [
                "package: name='com.shortdrama.goldfruit' versionCode='1' versionName='0.1.0' compileSdkVersion='36'",
                "sdkVersion:'24'",
                "targetSdkVersion:'36'",
                "uses-permission: name='android.permission.INTERNET'",
                "application-label:'GoldFruit Drama'",
            ],
        )

        parsed = mobile_completion_audit.parse_apk_badging(badging)

        self.assertEqual("com.shortdrama.goldfruit", parsed["packageName"])
        self.assertEqual("1", parsed["versionCode"])
        self.assertEqual("0.1.0", parsed["versionName"])
        self.assertEqual("24", parsed["minSdkVersion"])
        self.assertEqual("36", parsed["targetSdkVersion"])
        self.assertEqual("GoldFruit Drama", parsed["applicationLabel"])
        self.assertIn("android.permission.INTERNET", parsed["permissions"])

    def test_latest_android_input_ignores_flutter_generated_registrant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "lib" / "main.dart"
            generated = (
                root
                / "android"
                / "app"
                / "src"
                / "main"
                / "java"
                / "io"
                / "flutter"
                / "plugins"
                / "GeneratedPluginRegistrant.java"
            )
            source.parent.mkdir(parents=True)
            generated.parent.mkdir(parents=True)
            source.write_text("void main() {}\n", encoding="utf-8")
            generated.write_text("// generated\n", encoding="utf-8")
            os.utime(source, (100, 100))
            os.utime(generated, (200, 200))

            latest = mobile_completion_audit.latest_android_rebuild_input(root)

        self.assertEqual(source, latest)

    def _write_zip(self, path: Path, entries: list[str]) -> None:
        with zipfile.ZipFile(path, "w") as package:
            for entry in entries:
                package.writestr(entry, b"demo")

    def _fake_png(self) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\r"
            + b"IHDR"
            + (390).to_bytes(4, "big")
            + (844).to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00"
            + b"0" * 2048
        )

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
