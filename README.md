# Short Drama Whitelabel Mobile

Flutter whitelabel app template for tenant-owned short-drama apps.

## Scope

- App talks only to the tenant edge adapter.
- App does not contain tenant edge secrets, Cloudflare API tokens, Stream signing keys, or R2 credentials.
- Five MVP templates are available: `coolshow`, `hongguo`, `douyin`, `hippo`, and `reelshort`.
- Legacy aliases remain for compatibility: `golden -> hongguo`, `purple -> hippo`, `blue -> douyin`.
- Store builds gate payment entries by compliance mode; Android direct builds can expose tenant-owned external providers.
- Seven locale ARB files are included: `zh`, `en`, `th`, `id`, `vi`, `ms`, and `fil`.
- Public app config includes style template, auth providers, consumer payment providers, public coin packages, wallet scope, wallet ledger, public top-up payment channels, catalog, playback, feedback, account deletion, and C-end wallet/payment endpoints.
- Each install keeps a local anonymous `endUserRef` in platform key-value storage and sends it only to Tenant Edge as `x-device-id` or request body context for C-end wallet, play, card redeem, offline top-up, and deletion flows.

## Open Source Boundary

The mobile package is prepared as an Apache-2.0 white-label template under
`mobile/LICENSE`. Before publishing or forking the template, review
`docs/open-source-release.md` for the publishable file boundary, no-secret
rules, tenant-owned signing tasks, store-compliance notes, and replacement
requirements for final tenant branding.
`docs/tenant-app-release-config-boundary.md` separates tenant portal runtime
configuration from server-side provider setup, native packaging, and store
console requirements.

## Local Commands

Run with a local Flutter SDK:

```bash
./scripts/bootstrap_flutter.sh
./scripts/check_mobile.sh
./scripts/build_flavor.sh hongguo android debug
./scripts/build_flavor.sh douyin android debug
./scripts/build_flavor.sh hippo android debug
./scripts/build_flavor.sh reelshort android debug
./scripts/build_flavor.sh hongguo android release appbundle
./scripts/build_flavor.sh hongguo ios release
./scripts/write_release_manifest.sh
./scripts/write_store_handoff_manifest.py
./scripts/export_ios_ci_handoff.py
./scripts/export_store_assets.py
./scripts/export_store_signing_handoff.py
./scripts/export_store_publish_config.py
./scripts/export_external_account_handoff.py
./scripts/export_store_submission_starter.py
./scripts/import_store_submission_evidence.py
./scripts/export_completion_unblocker.py
./scripts/mobile_completion_closure.py
./scripts/check_app_config.mjs
./scripts/check_native_config.sh
./scripts/export_open_source_template.py
./scripts/export_github_publish_handoff.py
./scripts/import_github_publication_evidence.py --repo <owner>/short-drama-whitelabel-mobile --strict
node scripts/capture_wysiwyg_previews.mjs
./scripts/export_ui_preview_gallery.py
./scripts/mobile_completion_audit.py
./scripts/update_prototype_screenshots.sh
```

Run the repository-level audit snapshot from the repo root:

```bash
npm run infra:mobile-app-completion-audit
```

If Flutter is already installed, set `FLUTTER_BIN=/path/to/flutter` or keep it on `PATH`.
The scripts prefer `FLUTTER_BIN`, then `flutter` on `PATH`, then `/tmp/flutter/bin/flutter`, then `$HOME/.local/flutter/bin/flutter`.

The prototype screenshot script renders publish-safe PNGs under
`test/goldens/prototypes`: one set per template across the eight MVP screens at 390px.
`test/prototype_layout_test.dart` also checks those screens at 360px, 390px,
430px, and 768px so text, buttons, and payment sheets do not overflow.

The WYSIWYG preview script builds `lib/preview_main.dart` as Flutter Web,
captures release-rendered 390px screens with Playwright/Chromium, and writes
public PNGs plus `build/wysiwyg-preview/wysiwyg-preview-manifest.json`.
It waits for the Flutter runtime view before capture and rejects likely blank
screenshots with unexpected dimensions or very small PNG sizes. Set
`CHROME_PATH=/path/to/Chrome` if Playwright's bundled Chromium is unavailable.
Run `node scripts/capture_wysiwyg_previews.mjs` before
`./scripts/export_ui_preview_gallery.py` when the high-fidelity UI changes.

## Tenant Adapter

The app API base comes from flavor config and must point to the tenant edge Worker, for example:

```text
https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev
```

All playback requests use `POST /play` on the tenant edge adapter. The app never signs HMAC requests itself.

## Compliance Boundary

- `app_store`: exposes App Store IAP only for digital content.
- `play_store`: exposes Play Billing only unless a separate approved user-choice build is configured.
- `regional_user_choice`: exposes approved external providers for eligible regions while keeping Play Billing available.
- `android_direct`: can expose Stripe, PayPal, bank transfer, local wallet, crypto, and consumer point cards.

Provider secrets are configured in Tenant Edge/API Worker secrets. Flutter assets and Dart defines must only contain public config.

## MVP Status

- `ThemePreset`/`TemplateTokens`, `AppCapabilities`, `FeatureGate`, and five flavor presets define the white-label template system.
- Tenant portal exposes an App template workbench and public release manifest.
- Tenant Edge exposes app-safe C-end account, wallet, payment options with coin packages, public payment-channel summaries, payment intent, offline application, and consumer point-card endpoints.
- `ShortDramaApp` loads Tenant Edge config, catalog, account, wallet, wallet ledger, and payment capability before rendering the template shell.
- Tenant Edge `theme.primaryColor` now overrides the local flavor default at runtime, so tenant portal brand changes can drive the app shell, home, catalog, wallet, auth, playback, legal, and point-card screens without embedding tenant secrets.
- If Tenant Edge config is unreachable, `ShortDramaApp` keeps the no-secret seeded catalog usable and shows a local demo-data banner instead of blocking the app on the first screen.
- `main.dart` resolves a per-install anonymous C-end identity before bootstrapping, so wallet, playback authorization, card redeem, and account deletion flows do not share a fixed tenant-wide anonymous reference.
- `AuthScreen` starts tenant email auth with the install-scoped `endUserRef`, verifies the email challenge through Tenant Edge, opens tenant-hosted Google/Facebook/Apple OAuth start URLs with the system browser, listens for the app deep-link callback, completes OAuth through Tenant Edge, and updates the local member-center account state without storing provider secrets.
- `PlayerScreen` uses `video_player` for Tenant Edge authorized playback URLs, supports previous/next ready-episode navigation, and falls back to the tenant player URL when native playback cannot initialize.
- `PlayerScreen` records successful playback in the local watch history and exposes a runtime favorite toggle; the Mine tab opens real watch-history and favorites lists.
- `WalletScreen` loads tenant public payment channels for bank transfer, local wallet, and crypto-style offline flows, shows only masked summaries or safe QR URLs, and submits the selected `paymentChannelId` with the C-end offline application.
- `WalletScreen` starts native App Store IAP or Google Play Billing purchases for `iap` / `play_billing`, then submits the receipt/token to Tenant Edge `/payment/store-purchases/verify`; Flutter never stores store shared secrets, service-account keys, or credits coins locally.
- `WalletScreen` opens Tenant Edge returned checkout URLs for online payment intents in the system browser, so Stripe/PayPal-style provider handoff stays tenant-hosted and app-safe.
- `AccountDeleteScreen` submits C-end deletion requests to `/me/delete-request` and displays only masked account references.
- The Mine tab exposes tenant-hosted support, terms, and privacy entries through `LegalLinkScreen`; Flutter only renders public URLs and does not store legal-service credentials.
- Android and iOS native project files are generated. Android includes five product flavors; iOS uses flavor xcconfig presets plus Dart defines for template selection, and includes an app-level `PrivacyInfo.xcprivacy` privacy manifest for the template shell.
- Android debug APK, release APK, and release AAB package commands are available through `scripts/build_flavor.sh`; `scripts/write_release_manifest.sh` records public package metadata and SHA256 checksums under `build/release-manifests/`.
- `scripts/write_store_handoff_manifest.py` writes `build/release-handoff/mobile-store-handoff.json` with public per-flavor app metadata, legal links, auth/payment providers, compliance-filtered payment visibility, OAuth/deep-link callback registration metadata, App Store/Google Play product registration metadata, native capability registration metadata, store review declarations, distribution channel readiness, store submission metadata with per-locale listing drafts, publish-safe screenshot asset references with SHA256/size/dimensions, release artifact references when present, tenant-owned store tasks, and secret-boundary reminders.
- `scripts/export_ios_ci_handoff.py` writes `build/ios-ci-handoff/mobile-ios-ci-handoff.zip` plus a manifest mapping all five iOS flavors to the manual GitHub Actions trigger, macOS/Xcode runner, unsigned artifact names, native metadata paths, tenant Apple actions, and no-credential boundary.
- `scripts/download_ios_ci_artifacts.py --repo <owner/repo>` downloads the five unsigned iOS GitHub Actions artifacts with `gh`, writes them under `build/ci-ios/`, and calls the importer below. If `--repo` is omitted it can resolve `GH_REPO`, `GITHUB_REPOSITORY`, or git `origin`; by default it selects the latest successful `mobile-flutter.yml` run, and `--run-id <run-id>` imports a specific run. It uses GitHub CLI auth only and does not read Apple signing material or tenant secrets.
- `scripts/export_store_assets.py` writes `build/store-assets/mobile-store-assets.zip` plus a manifest with per-flavor listing drafts, localized copy, review notes, data-safety starter facts, and 32 publish-safe screenshots for tenant store-submission handoff.
- `scripts/capture_wysiwyg_previews.mjs` writes release-rendered Flutter Web screenshots under `build/wysiwyg-preview/` plus a public manifest. It captures all five templates across the eight MVP screens from `lib/preview_main.dart`.
- `scripts/export_ui_preview_gallery.py` writes `build/ui-preview-gallery/mobile-ui-preview-gallery.html`, SVG and PNG readable overview/contact sheet files, WYSIWYG runtime preview boards, `mobile-ui-preview-gallery.zip`, and a manifest with an offline five-template/eight-screen UI preview gallery plus PNG review boards for tenant review. Runtime boards include the template home board, CoolShow eight-screen board, and full five-template/eight-screen board.
- `scripts/export_store_signing_handoff.py` writes `build/store-signing-handoff/mobile-store-signing-handoff.zip` plus per-flavor iOS export-options templates, Android signing placeholders, tenant Apple/Google/direct-distribution actions, and a no-signing-material boundary.
- `scripts/export_store_publish_config.py` writes `build/store-publish-config/mobile-store-publish-config.zip` plus tenant-fillable App Store, Google Play, and Android direct release configuration templates with legal URLs, OAuth callbacks, product ids, data-safety starters, and no client-side credentials.
- `scripts/export_external_account_handoff.py` writes `build/external-account-handoff/mobile-external-account-handoff.zip`, JSON, and Markdown with a no-secret Apple Developer, Google Play, Android direct, OAuth, C-end payments, and legal/review checklist for every flavor. It mirrors the tenant portal "外部账号与签名资料接入入口" and accepts only public status, links, product ids, build numbers, package names, callback URLs, and checksums.
- `scripts/export_store_submission_starter.py` writes `build/store-submission-starter/mobile-store-submission-starter.zip`, per-flavor public evidence input examples, operator checklists, per-flavor submission runbooks, `store-submission-operator-runbook.md`, and `store-submission-evidence-collector.html` so tenants can connect signing handoff, publish config, public evidence collection, per-flavor evidence files under `build/store-submission-evidence/flavors/`, and strict import without secrets or signing/credential file references.
- `scripts/store_submission_evidence_preflight.py` writes `build/store-submission-evidence/store-submission-evidence-preflight.json` and `.md` so tenant operators can see which flavor evidence files are missing or incomplete before running the strict import.
- `scripts/import_store_submission_evidence.py` writes `build/store-submission-evidence/store-submission-evidence.template.json`, `store-submission-evidence.guide.md`, and `store-submission-evidence.json`; it is blocked until tenants fill public TestFlight, Play internal, or direct-distribution status evidence. Tenants should save per-flavor files as `build/store-submission-evidence/flavors/<flavor>.input.json` and run `scripts/import_store_submission_evidence.py --source-dir build/store-submission-evidence/flavors --strict`; per-flavor input files take precedence over the combined input for preflight and source-dir strict import. A single `store-submission-evidence.input.json` file is still supported only when no per-flavor inputs are present. Evidence refs can be plain strings or structured objects with `label`, `type`, and at least one of `value`, `url`, or `sha256`; structured `url` values must be public HTTPS URLs, so localhost, file URLs, plain HTTP, loopback, private IP ranges, and `.local` hosts are rejected. `evidenceCapturedAt` and structured ref `capturedAt` values must be timezone-aware ISO-8601 timestamps that are not in the future. Signing material, provider credentials, and signing/credential file references such as `.p12`, `.p8`, `.mobileprovision`, `.jks`, or `.keystore` are rejected.
- `scripts/export_completion_unblocker.py` writes `build/completion-unblocker/mobile-completion-unblocker.json` and `.md` with no-secret external actions for full Xcode, unsigned iOS CI artifact import, store-submission starter/runbook refresh, tenant store-submission evidence import, field-level remediation actions for each blocked store-submission input, `mobile-store-evidence-fix-queue.csv/.md` for tenant operator assignment, and final completion-audit rerun.
- `scripts/mobile_completion_closure.py` refreshes iOS CI artifact evidence, store-submission starter/runbook output, tenant store-submission evidence, and the completion audit, then writes `build/completion-closure/mobile-completion-closure.json` and `.md` with the current `canClaimComplete` result and remaining external blockers. It also refreshes the app handoff and tenant release package so the closure report is available from the tenant-facing handoff zip. It automatically downloads iOS CI artifacts when `--repo`, `GH_REPO`, `GITHUB_REPOSITORY`, or git `origin` identifies the GitHub repository; otherwise it refreshes local artifact evidence only.
- `scripts/import_ios_ci_artifacts.py` imports downloaded GitHub Actions unsigned iOS `Runner.app` artifacts into `build/ios-ci-evidence/ios-ci-artifacts.json` so full-Xcode CI proof can be audited without Apple signing material.
- `scripts/export_open_source_template.py` writes a GitHub-ready zip and manifest under `build/open-source/`, using a publish-safe allowlist that excludes build outputs, generated Flutter files, CocoaPods caches, Android local properties, signing material, env files, and secret values.
- `scripts/export_github_publish_handoff.py` writes `build/github-publish/github-publish-manifest.json`, `github-publish-guide.md`, and `github-release-notes.md` with no-secret `gh` commands for creating a public repository and release from the open-source template package.
- `scripts/import_github_publication_evidence.py --repo <owner>/short-drama-whitelabel-mobile --strict` records public GitHub repository and release evidence after publication. It reads repo visibility, default branch, release tag, release assets, and local open-source package hashes; it does not read or store GitHub tokens.
- `scripts/check_app_config.mjs` keeps sample tenant configs, Flutter flavor constants, native bundle metadata, supported locales, and generated release manifests aligned.
- `scripts/mobile_completion_audit.py` summarizes required files, five template flavors, prototype PNGs, responsive prototype viewport coverage, test coverage, runtime identity persistence, native playback/OAuth/payment dependencies, source secret boundaries, open-source release readiness, GitHub publish handoff and publication evidence, iOS static release configuration including the app privacy manifest, iOS CI handoff package readiness, store signing handoff readiness, store publish config readiness, external account handoff readiness, unsigned iOS build-matrix evidence, imported iOS CI artifact evidence, tenant store-submission evidence, store-submission operator runbooks, completion unblocker package readiness including field-level remediation rows and store evidence fix queue files, UI preview gallery readiness with WYSIWYG runtime screenshots plus SVG/PNG review boards, Android release artifacts, store handoff manifest readiness, public tenant release package readiness, and local iOS build environment readiness.
- `scripts/mobile_completion_audit.py` writes `build/completion-audits/mobile-app-completion.json` with current completion evidence and explicitly reports local iOS environment blockers.
- The same audit writes `build/release-handoff/mobile-tenant-release-package.json`, `build/release-handoff/mobile-tenant-release-package.md`, and `build/release-handoff/mobile-tenant-release-package.zip`, a public tenant handoff manifest, human-readable guide, and downloadable archive linking store metadata, Android artifact paths, store assets, UI preview gallery plus WYSIWYG and PNG review boards, iOS CI handoff, store signing handoff, store publish config templates, external account checklist, store submission starter runbooks, store submission evidence/template/guide, top-level store-submission status summary, completion unblocker, store evidence fix queue CSV/Markdown, open-source docs, per-flavor tenant actions, and no-secret boundaries.
- `npm run infra:mobile-app-completion-audit` writes a repository-level audit snapshot under `artifacts/mobile-completion/` and `implementation/mobile-app-completion-audit.md`.
- `flutter test` covers Tenant Edge client parsing, runtime bootstrap, email verification, OAuth URL launch plus deep-link callback completion, tenant checkout launch, native store purchase receipt verification, feature gates, payment capability filtering, account deletion entry visibility, remote config rendering, and five-template prototype layout checks across mobile/iPad widths.
- GitHub Actions supports manual dispatch and runs Flutter analysis/tests, native config validation, Android debug APK, release APK, release AAB builds with manifests, uploaded handoff/signing packages, uploaded store-submission evidence templates, unsigned iOS debug/release builds for all five flavors, and an `ios-ci-evidence` job that imports the unsigned iOS artifacts into public audit metadata.
