# API Integration PRD

## Goal

The Flutter template is an API client for Tenant Edge only. It must never hold
tenant secrets or call the official API Worker, Cloudflare, Stream, Stripe,
PayPal, bank, wallet, or crypto provider secret APIs directly.

## Allowed Flutter Calls

| Capability | Tenant Edge endpoint | Flutter behavior |
| --- | --- | --- |
| Runtime config | `GET /config` | Merge public tenant config with native flavor limits. |
| Email auth | `POST /auth/email/start`, `POST /auth/email/verify` | Start/verify challenge and update masked account state. |
| OAuth auth | `POST /auth/oauth/{provider}/start`, `POST /auth/oauth/{provider}/complete` | Open tenant-hosted auth URL and complete callback. |
| Account | `GET /me`, `POST /me/delete-request` | Show masked account, sign-out locally, submit deletion request. |
| Wallet | `GET /wallet`, `GET /wallet/ledger` | Show C-end consumer wallet and recent ledger. |
| Payments | `GET /payment/options`, `POST /payment/intents`, `POST /payment/store-purchases/verify`, `POST /payment/offline-applications`, `POST /payment/card-redeem` | Create orders, verify store receipts, submit offline applications, redeem consumer point cards. |
| Payment channels | `GET /topups/payment-channels` | Show public bank/wallet/crypto display data only. |
| Catalog/detail | `GET /catalog`, `GET /dramas/{dramaId}` | Render tenant-selected dramas and episode lists. |
| Playback | `POST /play` | Request authorization with idempotency key; never mint entitlement locally. |
| Support | `POST /feedback` where enabled | Submit public support receipt data. |

## Data Rules

- Consumer wallet truth belongs in D1/Durable Objects behind Tenant Edge/API.
- Official tenant points and C-end consumer wallets are separate ledgers.
- App-supplied amount/currency is display-only; server-side packages decide pricing.
- Raw receipts, provider tokens, full user identifiers, and secrets must not be echoed to Flutter.
- Demo transport may return synthetic data, but it must preserve the same endpoint names and failure shapes.

## Acceptance

- Flutter code imports only mobile-side API models/client packages.
- Static scans must not find `TENANT_APP_SECRET`, `CLOUDFLARE_API_TOKEN`, `sk_`, provider secret names, signing files, or service-account JSON.
- Tests cover success, disabled, and compliance-filtered payment behavior.

