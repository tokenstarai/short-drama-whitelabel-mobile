# Mobile Current-State Audit PRD

Generated: 2026-06-17

## Goal

Keep the mobile product as one open-source Flutter codebase with multiple
flavor/style templates. The first version must make the current MVP usable
before adding new business modules.

## Current State

| Area | Status | Evidence | Next requirement |
| --- | --- | --- | --- |
| Flutter template architecture | Built | `FlavorConfig` exposes CoolShow, Hongguo-inspired, Douyin-inspired, Hippo-inspired, and ReelShort-inspired presets. | Keep one codebase; styles change through flavor/native config and `/config`. |
| Android/iOS native shell | Built, store submission blocked by external tenant evidence | Android flavors and iOS xcconfig presets exist. | Tenant must provide signing, package identity, store products, and store-track evidence before publishing. |
| Runtime config | Partially closed | Tenant Portal saves public app config through Tenant Edge `/app-config`; Flutter consumes `/config`. | Maintain a field-level parity matrix so every visible app switch has a backend entry. |
| C-end account/wallet/payment APIs | Contracted and tested at Tenant Edge level | `/auth/*`, `/me`, `/wallet`, `/payment/*`, `/catalog`, `/dramas/{id}`, `/play`. | Flutter must only call Tenant Edge and never call backend workers or providers directly. |
| MVP app screens | Built | Splash, Login/Register, Home, Catalog, Detail, Player, Unlock/Recharge, Mine/Wallet/Point Card. | Every visible button/tab/card/form must either work or be hidden/clearly non-actionable. |
| UI previews | Built for template review | Golden and WYSIWYG capture scripts exist. | Add no-overflow and clickability checks before future visual refresh. |
| Open-source package | Prepared | `export_open_source_template.py` and docs define a no-secret package. | Re-audit imports, dependencies, sample configs, and generated package before GitHub release. |

## Classification

| Classification | Meaning | Examples |
| --- | --- | --- |
| Passed | Works in Flutter demo and has API/backend contract coverage. | Bottom navigation, catalog search/filter, wallet demo flows, playback authorization smoke. |
| Partially integrated | UI exists and contract exists, but tenant/staging proof or provider setup is still needed. | OAuth providers, Stripe/PayPal checkout, IAP/Play Billing verification. |
| Demo-only | Safe local preview behavior with synthetic data. | Generated posters, demo wallet balances, prototype payment channels. |
| Externally blocked | Cannot be completed inside the repo. | Apple/Google signing, App Store Connect app, Play Console products, OAuth SHA fingerprints, merchant approvals. |

## Non-goals For V1

- Do not split templates into separate Flutter apps.
- Do not add new business modules beyond the current MVP screens.
- Do not embed tenant secrets, provider secrets, Cloudflare tokens, signing files, or store credentials.
- Do not copy third-party logos, screenshots, names, or confusing trade dress.

