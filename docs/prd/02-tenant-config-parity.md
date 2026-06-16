# Tenant Config Parity PRD

## Goal

Every app capability that can change at runtime must have a matching Tenant
Portal entry, Tenant Edge save path, public `/config` or related API field, and
Flutter consumer. Values that cannot change after packaging must be exported as
handoff/checklist data instead of pretending to be runtime switches.

## Runtime Config Matrix

| Capability | Tenant Portal entry | Save/read API | Flutter effect | Repackage needed |
| --- | --- | --- | --- | --- |
| App name | App runtime config | `POST /app-config`, `GET /config` | App bars, Mine, wallet labels | No |
| Style template | Template picker | `styleTemplate` | Theme tokens, layout density, template tabs | No, within compiled template set |
| Store compliance mode | Compliance selector | `storeComplianceMode` | Payment filtering and review copy | No, but native package channel must match final release target |
| Supported locales | Locale editor | `supportedLocales` | Language picker and localized copy | No, if locale resources are compiled |
| Legal/support URLs | Legal config | `legal` | Support, terms, privacy, deletion links | No |
| Auth providers | OAuth/login config | `authProviders` | Login button visibility | No, but provider console/server secrets must be configured |
| Consumer payment providers | Payment config | `consumerPaymentProviders`, `/payment/options` | Recharge provider visibility | No, but store/provider setup may still be required |
| Feature flags | Feature config | `features` | Wallet entries, point card, offline top-up, deletion | No |
| Catalog publishing | Catalog workspace | `/catalog`, `/dramas/{id}` | Home/catalog/detail cards and filters | No |
| Catalog display labels/visibility | Category operations workspace | `POST /app-config`, `GET /config.catalogDisplay` | Category tab labels, theater filters, hidden category chips | No |
| Point-card batches/rules | Point-card workspace | `/payment/card-redeem` | Redeem UI and ledger outcome | No |

## Handoff-Only Matrix

| Material | Why runtime config cannot apply it | Required handling |
| --- | --- | --- |
| iOS Bundle ID and Apple Team ID | Bound to native target, signing, and App Store Connect. | Generate/update flavor xcconfig and sign/package again. |
| iOS certificates/profiles | Signing credentials, never app runtime data. | Tenant-owned machine or protected CI only. |
| Android package name | Compiled into `applicationId` and Play record. | Generate/update flavor and build again. |
| Android upload key/App signing | Signing credentials. | Tenant-owned keystore or Play App Signing. |
| IAP/Play Billing products | Must exist in Apple/Google consoles. | Store console setup plus server-side product mapping. |
| OAuth SHA/App Links/Associated Domains | Depend on final signed app identity and domain files. | Register after package identity/signing is final. |
| Provider secrets/webhook secrets | Server-side credentials. | Tenant Edge/API Worker secrets only. |
| Launcher icon/native splash | Packaged native resources. | Regenerate assets and rebuild. |

## Acceptance

- Tenant Portal must reject secret-like values in app runtime config.
- Tenant Edge `/app-config` must forward only public fields to the API Worker.
- Flutter must constrain remote config by the compiled native build capability.
- GitHub docs must list handoff-only materials so tenants do not expect runtime switches to change store identity.
