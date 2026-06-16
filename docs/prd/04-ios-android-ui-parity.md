# iOS Android UI Parity PRD

## Goal

Android and iOS must feel like the same app for the same flavor. Native
differences are allowed only for platform packaging, system browser/login
handoff, store billing, safe areas, and OS-level controls.

## Shared UI Contract

| Surface | Required parity |
| --- | --- |
| Navigation | Same tab order: Home, Catalog, Theater, Mine. |
| Typography | Same Flutter text scale and no viewport-width font scaling. |
| Safe areas | No content hidden by status bar, notch, home indicator, or bottom nav. |
| Home | Same hero, card, search, language, CTA, and rail hierarchy per flavor. |
| Catalog | Same template tabs, metadata chips, search, sort, empty state, and card tap behavior. |
| Detail | Same title/summary/episode/unlock/share hierarchy. |
| Player | Same vertical player controls, unlock flow, favorite, share, and next episode behavior. |
| Wallet | Same provider visibility after compliance filtering; native store billing may hand off differently. |
| Account | Same legal, language, deletion, wallet, history, favorite, and settings entries. |

## Device Widths

- Phone: 360, 390, 430 px.
- Tablet/iPad class: 768 px minimum validation.
- No clipped text, incoherent overlap, or unreachable bottom actions.

## Acceptance

- Golden/prototype tests cover all flavors and MVP screens at the required widths.
- Runtime smoke must pass on Android emulator and iOS Simulator before handoff.
- A flavor may not show different providers, auth buttons, or navigation hierarchy across platforms unless the store compliance mode explicitly requires it.

