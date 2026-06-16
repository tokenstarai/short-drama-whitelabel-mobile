# Open Source Mobile Template PRD

## Goal

Publish the Flutter mobile app as an independent GitHub template that can be
used without cloning or exposing the three backend/admin surfaces. The template
coordinates with the platform only through public APIs, sample config, and docs.

## Publishable Boundary

Allowed:

- `mobile/lib`, `mobile/test`, `mobile/integration_test`.
- Android/iOS template project files without tenant signing material.
- Public sample config and generated demo assets.
- `mobile/docs`, PRDs, store handoff templates, and no-secret scripts.
- CI that runs analysis, tests, builds unsigned artifacts, and scans the package.

Denied:

- Backend Worker secrets or Cloudflare tokens.
- Tenant Edge HMAC secrets.
- OAuth client secrets, private keys, or provider tokens.
- Stripe/PayPal/webhook/bank/wallet/crypto credentials.
- App Store/Play signing files, certificates, provisioning profiles, keystores, service-account JSON.
- Third-party screenshots, logos, copied marks, or confusing trade dress.
- Direct imports from `apps/admin-h5`, `apps/tenant-portal`, `workers`, or backend-private packages.

## Tenant Setup Flow

1. Tenant creates/configures external store, OAuth, payment, legal, and brand materials.
2. Tenant Portal saves runtime-safe app config and exports public release handoff data.
3. Mobile template is packaged with tenant bundle/package identity and native assets.
4. App reads Tenant Edge `/config`, `/catalog`, wallet/payment/auth APIs at runtime.
5. Store submission evidence remains tenant-owned and is imported only as public metadata.

## Acceptance

- `export_open_source_template.py` must produce a package with a passing no-secret scan.
- README/docs must separate runtime config from repackage/store-console tasks.
- The mobile template must build and run with demo transport without any backend checkout.

