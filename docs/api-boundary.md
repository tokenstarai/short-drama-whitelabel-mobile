# App API Boundary

The Flutter app calls only tenant edge adapter endpoints. The adapter base comes from flavor config such as:

```text
https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev
```

## Allowed App Endpoints

- `GET /config`
- `POST /auth/email/start`
- `POST /auth/email/verify`
- `POST /auth/oauth/{provider}/start`
- `POST /auth/oauth/{provider}/complete`
- `GET /me`
- `POST /me/delete-request`
- `GET /wallet`
- `GET /wallet/ledger`
- `GET /payment/options`
- `GET /topups/payment-channels`
- `POST /payment/intents`
- `POST /payment/store-purchases/verify`
- `POST /payment/offline-applications`
- `POST /payment/card-redeem`
- `GET /catalog`
- `GET /dramas/{dramaId}`
- `POST /play`
- `POST /cards/redeem`
- `POST /topups/offline-applications`
- `POST /feedback`
- `POST /account/delete-request`

## Endpoint Contract

### `GET /config`

Returns tenant public brand config, feature flags, app template config, theme, legal URLs, and App endpoint paths. It may include public `appKey`, but it must not include `TENANT_APP_SECRET` or any secret material.

The `config.app` object contains only public capability fields:

```json
{
  "styleTemplate": "reelshort_inspired",
  "storeComplianceMode": "app_store",
  "authProviders": ["email", "google", "facebook", "apple"],
  "consumerPaymentProviders": ["iap"],
  "externalPaymentsAllowed": false,
  "consumerLedgerScope": "consumer"
}
```

### C-end account and wallet endpoints

- `POST /auth/email/start` starts an email challenge without exposing email service secrets. The app passes its opaque `endUserRef` so Tenant Edge can bind the challenge to the current installed tenant app identity.
- `POST /auth/email/verify` verifies the challenge code and returns a masked C-end account object. It must not echo the raw email, full `endUserRef`, email provider secrets, or tenant secrets.
- `POST /auth/oauth/{provider}/start` returns provider readiness for `google`, `facebook`, or `apple` plus an app-safe `authUrl`. Flutter opens that tenant-hosted URL with the system browser. The URL may contain `oauthStartId`, provider, tenant id, callback state, and public OAuth client identifiers, but it must not contain provider client secrets, private keys, full `endUserRef`, or tenant HMAC secrets.
- `POST /auth/oauth/{provider}/complete` accepts the app callback `code`, optional `state`, `oauthStartId`, and `endUserRef`, then returns the same masked `account` shape as email verification. Flutter listens for the tenant app URL scheme deep link, completes this call automatically when the browser returns, and keeps a manual callback input only as a debug fallback. The provider token exchange and provider client secret handling belong inside Tenant Edge/API Worker secrets; Flutter never receives those secrets.
- `GET /me` returns masked account references and enabled auth providers.
- `POST /me/delete-request` mirrors account deletion request behavior for the member center.
- `GET /wallet` and `GET /wallet/ledger` expose only the C-end consumer wallet scope. Tenant Edge HMAC-forwards these reads to API Worker `GET /v1/tenant/consumer-wallet` and `GET /v1/tenant/consumer-wallet/ledger`, which read `end_user_wallets` and `end_user_wallet_ledger`. Ledger responses must use masked account references and append-only event rows; they must not expose official tenant wallet rows, raw receipts, purchase tokens, or full end-user identifiers.

The app generates one anonymous `endUserRef` per installed tenant app bundle and persists it in platform key-value storage. It is sent as `x-device-id` for `GET /me`, `GET /wallet`, and `GET /wallet/ledger`, and as body context for play, card redeem, offline top-up, and deletion requests. This reference is an opaque client identifier only; it is not a tenant secret, not an OAuth secret, and not wallet truth. Tenant Edge and the backing D1/Durable Object wallet remain authoritative.

`GET /wallet/ledger` returns a compact recent-history shape:

```json
{
  "requestId": "req_wallet_ledger",
  "status": "ok",
  "ledgerScope": "consumer",
  "accountRefMasked": "anon:d...3456",
  "entries": [
    {
      "ledgerId": "consumer_ledger_1",
      "type": "point_card",
      "title": "Point card recharge",
      "pointsDelta": 100,
      "balanceAfter": 120,
      "createdAt": "2026-06-14T00:00:00Z",
      "status": "posted"
    }
  ]
}
```

### C-end payment endpoints

- `GET /payment/options` returns providers already filtered by store compliance mode plus public coin packages. Packages are public offer metadata only: package id, title, store product id, coins, bonus coins, amount, and currency.
- `GET /topups/payment-channels` returns only app-safe payment-channel display data for bank transfer, local wallet, and crypto-style offline flows: channel id, country, method, display name, masked summary, enabled flag, optional QR file name, and optional safe QR image URL. It must not return raw config JSON, signed admin bearer tokens, account numbers, private wallet keys, provider secrets, or signed object URLs.
- `POST /payment/store-purchases/verify` submits native App Store IAP or Google Play Billing purchase receipts/tokens to Tenant Edge. Tenant Edge validates the provider against the active store compliance mode, prices the package from server config, and HMAC-forwards the request to API Worker `POST /v1/tenant/consumer-store-purchases/verify` for C-end wallet crediting in `end_user_wallets`, `end_user_wallet_ledger`, and `consumer_payment_orders`. Flutter can start the native purchase and forward receipt material, but it must not verify receipts locally, mint coins locally, or store App Store/Google Play shared secrets, service-account keys, or provider API credentials. Tenant Edge/API responses must not echo raw receipts, purchase tokens, full end-user refs, or provider secrets.
- `POST /payment/intents` creates an app-safe order receipt and never returns provider client secrets. For online providers such as Stripe or PayPal in compliant builds, Tenant Edge prices the order from the selected server-side package id and HMAC-forwards to API Worker `POST /v1/tenant/consumer-payment-orders`, which writes `consumer_payment_orders` with `requires_provider_confirmation` but does not credit wallet coins until provider confirmation. Flutter opens the tenant-hosted `checkoutUrl`; App-supplied amount and currency are display hints and must not be trusted as ledger truth.
- `POST /payment/offline-applications` records consumer bank/wallet/crypto-style recharge applications. Flutter submits the selected public `paymentChannelId`; Tenant Edge HMAC-forwards to API Worker `POST /v1/tenant/consumer-payment-orders/offline-applications`, which writes `consumer_payment_orders` with `pending_review` and never writes official tenant topups or official wallet ledgers.
- `POST /payment/card-redeem` redeems consumer point cards against the C-end wallet scope. Tenant Edge HMAC-forwards this to API Worker `POST /v1/tenant/consumer-point-cards/redeem`, which writes `consumer_point_cards`, `end_user_wallets`, and `end_user_wallet_ledger`. It must not call the official tenant `/v1/tenant/cards/redeem` endpoint or write official tenant wallet ledger rows.

Consumer payment endpoints are separate from official tenant top-up endpoints. Official tenant point cards remain under `/cards/redeem` and the official wallet ledger.

### `GET /catalog`

Returns authorized drama cards for the current tenant. Tenant Edge injects the tenant identity server-side before calling the control plane.

### `GET /dramas/{dramaId}`

Returns a single authorized drama and generated episode rows:

```json
{
  "requestId": "req_edge_detail",
  "status": "ok",
  "drama": {
    "dramaId": "drama_1",
    "title": "Seed Drama",
    "posterUrl": "/assets/posters/1.png",
    "episodeCount": 12,
    "readyEpisodeCount": 3,
    "pointPrice": 2,
    "episodes": [
      {
        "episodeId": "episode_1",
        "episodeNumber": 1,
        "title": "第 1 集",
        "pointPrice": 2,
        "ready": true,
        "locked": false
      }
    ]
  }
}
```

Unavailable dramas return `404 APP_DRAMA_NOT_AVAILABLE`.

### `POST /play`

Requires `Idempotency-Key`. Returns a short-lived playback manifest from Tenant Edge after the adapter signs the upstream control-plane request.

### `POST /cards/redeem`

Requires `Idempotency-Key` and `x-turnstile-token` when risk policy requires it. Default feature flag is off. Disabled responses use `403 APP_FEATURE_DISABLED`.

### `POST /topups/offline-applications`

Requires `Idempotency-Key` and bearer forwarding configured inside Tenant Edge. Default feature flag is off. The App never receives the control-plane bearer token.

### `POST /feedback`

Accepts category, message, drama/episode references, and an anonymous user reference. Returns `202 accepted` with a `feedbackId`. Current staging stores no permanent feedback record; the response is an app-facing receipt for support workflows.

### `POST /account/delete-request`

Accepts `accountRef`, `endUserRef`, or `x-device-id`. Returns `202 accepted`, `deletionRequestId`, and `accountRefMasked`. The endpoint does not echo the complete account reference.

## Error Shape

Tenant Edge errors use:

```json
{
  "error": {
    "code": "APP_FEATURE_DISABLED",
    "message": "Feature disabled.",
    "requestId": "req_edge_error"
  }
}
```

The Flutter client maps this into `AppApiException`.

## Denied Calls

The app must not call:

- `/v1/tenant/*` on the official API Worker directly.
- Cloudflare Stream signing endpoints.
- R2 APIs.
- Cloudflare account APIs.
- Stripe, PayPal, or crypto provider secret APIs directly.

## Denied Secrets

The app must not contain server-side tenant signing secrets, Cloudflare account tokens, Stream signing keys, or R2 access credentials.

Static scans should not find:

- `TENANT_APP_SECRET`
- `CLOUDFLARE_API_TOKEN`
- `secret_hash`
- `secret_ciphertext`
- `appSecret`
- `sk_`
