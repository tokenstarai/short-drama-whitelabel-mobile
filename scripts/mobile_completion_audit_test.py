#!/usr/bin/env python3
"""Regression tests for mobile_completion_audit.py."""

from __future__ import annotations

import os
import argparse
import unittest
import tempfile
import zipfile
import hashlib
import json
from pathlib import Path
from unittest import mock

import download_ios_ci_artifacts
import export_completion_unblocker
import export_github_publish_handoff
import import_github_publication_evidence
import import_store_submission_evidence
import mobile_completion_audit
import mobile_completion_closure


class MobileCompletionAuditTest(unittest.TestCase):
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
                "mobile-hongguo-ios-unsigned",
                "mobile-douyin-ios-unsigned",
                "mobile-hippo-ios-unsigned",
                "mobile-reelshort-ios-unsigned",
            ],
            [step["artifactName"] for step in report["downloadSteps"]],
        )
        self.assertIn(
            "gh run download 123456789 --repo tokenstarai/short-drama-saas -n mobile-hongguo-ios-unsigned",
            report["downloadSteps"][0]["command"],
        )
        self.assertTrue(
            report["downloadSteps"][0]["destination"].endswith("build/ci-ios/hongguo"),
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
        self.assertEqual(4, len(passed["submissions"]))

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
        self.assertIn("./scripts/import_store_submission_evidence.py --strict", guide_text)
        lowered = guide_text.lower()
        for marker in import_store_submission_evidence.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_completion_report_includes_ci_and_release_secret_gates(self) -> None:
        root = Path(__file__).resolve().parents[1]

        report = mobile_completion_audit.build_report(root, strict_ios=False)
        checks = {check["id"]: check for check in report["checks"]}
        workflow = (root.parent / ".github" / "workflows" / "mobile-flutter.yml").read_text(
            encoding="utf-8",
        )

        self.assertIn("ci_workflow", checks)
        self.assertIn(
            "scripts/download_ios_ci_artifacts.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn(
            "scripts/import_store_submission_evidence.py",
            checks["required_files"]["evidence"],
        )
        self.assertIn("ios_static_release_config", checks)
        self.assertIn("ios_ci_handoff_package", checks)
        self.assertIn("store_signing_handoff_package", checks)
        self.assertIn("store_publish_config_package", checks)
        self.assertIn("ios_build_matrix", checks)
        self.assertIn("ios_ci_artifact_evidence", checks)
        self.assertIn("store_submission_evidence", checks)
        self.assertIn("completion_unblocker_package", checks)
        self.assertIn("github_publish_handoff_package", checks)
        self.assertIn("github_publication_evidence", checks)
        self.assertIn("store_handoff_manifest", checks)
        self.assertIn("store_assets_package", checks)
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
        self.assertIn(checks["ios_build_matrix"]["status"], {"passed", "blocked"})
        self.assertIn(checks["ios_ci_artifact_evidence"]["status"], {"passed", "blocked"})
        self.assertIn(checks["store_submission_evidence"]["status"], {"passed", "blocked"})
        self.assertEqual("passed", checks["completion_unblocker_package"]["status"])
        self.assertEqual("passed", checks["github_publish_handoff_package"]["status"])
        self.assertIn(checks["github_publication_evidence"]["status"], {"passed", "blocked"})
        self.assertEqual("passed", checks["store_handoff_manifest"]["status"])
        self.assertEqual("passed", checks["store_assets_package"]["status"])
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
            "32 publish-safe screenshots",
            checks["store_assets_package"]["detail"],
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
            "mine payment entry guards",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "oauth provider deep-link guards",
            checks["test_coverage_files"]["detail"],
        )
        self.assertIn(
            "tenant release package",
            checks["tenant_release_package"]["detail"],
        )
        self.assertIn(
            "Tenant portal exports release handoff metadata",
            checks["tenant_portal_release_handoff"]["detail"],
        )
        self.assertIn(
            "release package references",
            checks["tenant_portal_release_handoff"]["detail"],
        )
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
        self.assertIn("four-flavor unsigned iOS release builds", checks["ci_workflow"]["detail"])

    def test_completion_unblocker_package_exports_external_action_plan(self) -> None:
        root = Path(__file__).resolve().parents[1]

        check = mobile_completion_audit.check_completion_unblocker_package(root)
        manifest_path = root / "build" / "completion-unblocker" / "mobile-completion-unblocker.json"
        markdown_path = root / "build" / "completion-unblocker" / "mobile-completion-unblocker.md"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("completion_unblocker_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/completion-unblocker/mobile-completion-unblocker.json", check.evidence)
        self.assertIn("build/completion-unblocker/mobile-completion-unblocker.md", check.evidence)
        self.assertEqual("mobile_completion_unblocker", manifest["packageType"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
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
        self.assertIn("scripts/import_store_submission_evidence.py --strict", commands)
        self.assertIn("scripts/mobile_completion_closure.py --skip-ios-ci-download", commands)
        self.assertIn("npm run infra:mobile-app-completion-audit", manifest["completionGateCommand"])
        self.assertIn("build/store-submission-evidence/store-submission-evidence.guide.md", json.dumps(manifest))
        self.assertIn("# Mobile Completion Unblocker", markdown)
        lowered = json.dumps(manifest, ensure_ascii=False).lower() + markdown.lower()
        for marker in export_completion_unblocker.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

    def test_mobile_completion_closure_summarizes_remaining_external_blockers(self) -> None:
        audit = {
            "appCompletion": "blocked",
            "summary": {"passed": 24, "missing": 0, "failed": 0, "blocked": 2},
            "checks": [
                {"id": "theme_templates", "status": "passed", "detail": "ok"},
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
        self.assertIn("GITHUB_REPOSITORY", report["blockers"][0]["nextAction"])
        self.assertIn("store-submission-evidence.input.json", report["blockers"][1]["nextAction"])
        lowered = json.dumps(report, ensure_ascii=False).lower()
        for marker in export_completion_unblocker.FORBIDDEN_MARKERS:
            self.assertNotIn(marker, lowered)

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
                        },
                        {
                            "name": "open-source-template-manifest.json",
                            "contentType": "application/json",
                            "sizeBytes": 456,
                            "downloadUrl": "https://github.com/tokenstarai/short-drama-whitelabel-mobile/releases/download/mobile-template-v0.1.0/open-source-template-manifest.json",
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
                            "url": "https://github.com/download/short-drama-whitelabel-mobile.zip",
                        },
                        {
                            "name": "open-source-template-manifest.json",
                            "contentType": "application/json",
                            "size": 456,
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
        self.assertRegex(report["sourcePackageSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(report["sourceManifestSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual([], report["disallowedValueMarkerHits"])

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
        self.assertEqual(32, manifest["screenshotCount"])
        self.assertEqual([], manifest["disallowedValueMarkerHits"])
        self.assertRegex(manifest["packageSha256"], r"^[a-f0-9]{64}$")
        flavors = {entry["flavor"]: entry for entry in manifest["flavors"]}
        self.assertEqual(set(mobile_completion_audit.FLAVORS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["listing"]["displayName"])
        self.assertEqual("en-US", hongguo["listing"]["defaultLocale"])
        self.assertFalse(hongguo["dataSafety"]["templateDisclosures"]["clientStoresTenantCredentials"])
        self.assertEqual(8, len(hongguo["screenshots"]))
        self.assertEqual("01_splash", hongguo["screenshots"][0]["screen"])
        self.assertRegex(hongguo["screenshots"][0]["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual("publish_safe_prototype", hongguo["screenshots"][0]["source"])

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
        self.assertEqual(set(mobile_completion_audit.FLAVORS), set(flavors))
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
        package = json.loads(package_path.read_text(encoding="utf-8"))

        self.assertEqual("tenant_release_package", check.id)
        self.assertEqual("passed", check.status)
        self.assertIn("build/release-handoff/mobile-tenant-release-package.json", check.evidence)
        self.assertEqual(1, package["schemaVersion"])
        self.assertEqual("mobile_tenant_release_package", package["packageType"])
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
        self.assertEqual(32, package["manifests"]["storeAssets"]["screenshotCount"])
        self.assertRegex(package["manifests"]["storeAssets"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["storeAssets"]["packageSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            "build/ios-ci-handoff/ios-ci-handoff-manifest.json",
            package["manifests"]["iosCiHandoff"]["manifestPath"],
        )
        self.assertEqual(
            "build/ios-ci-handoff/mobile-ios-ci-handoff.zip",
            package["manifests"]["iosCiHandoff"]["packagePath"],
        )
        self.assertTrue(package["manifests"]["iosCiHandoff"]["workflowDispatch"])
        self.assertEqual(4, package["manifests"]["iosCiHandoff"]["flavorCount"])
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
        self.assertEqual(4, package["manifests"]["storeSigningHandoff"]["flavorCount"])
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
        self.assertEqual(4, package["manifests"]["storePublishConfig"]["flavorCount"])
        self.assertRegex(package["manifests"]["storePublishConfig"]["manifestSha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(package["manifests"]["storePublishConfig"]["packageSha256"], r"^[a-f0-9]{64}$")
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
        self.assertIn("docs/open-source-release.md", package["openSourceBoundary"]["docs"])
        self.assertFalse(package["secretBoundary"]["clientStoresTenantSecrets"])
        self.assertFalse(package["secretBoundary"]["clientStoresPaymentSecrets"])
        flavors = {entry["flavor"]: entry for entry in package["flavors"]}
        self.assertEqual(set(mobile_completion_audit.FLAVORS), set(flavors))
        hongguo = flavors["hongguo"]
        self.assertEqual("GoldFruit Drama", hongguo["appName"])
        self.assertEqual("com.shortdrama.goldfruit", hongguo["applicationId"])
        self.assertTrue(hongguo["tenantRequiredActions"]["replaceBundleIds"])
        self.assertTrue(hongguo["tenantRequiredActions"]["replaceSigningMaterial"])
        self.assertTrue(hongguo["tenantRequiredActions"]["configureOAuthCallbacks"])
        self.assertTrue(hongguo["tenantRequiredActions"]["configureStoreProducts"])
        self.assertIn("build/app/outputs/bundle/hongguoRelease/app-hongguo-release.aab", json.dumps(hongguo))

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
                "LICENSE",
                "README.md",
                "docs/open-source-release.md",
                "pubspec.yaml",
                "lib/main.dart",
                "scripts/export_completion_unblocker.py",
                "scripts/export_github_publish_handoff.py",
                "scripts/import_github_publication_evidence.py",
                "scripts/import_store_submission_evidence.py",
                "scripts/mobile_completion_closure.py",
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
