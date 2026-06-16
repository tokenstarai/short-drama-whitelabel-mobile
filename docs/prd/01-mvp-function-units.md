# Mobile MVP Function Unit PRD

## Goal

The first app version is defined by the smallest usable C-end units. A visible
control is acceptable only when it has a real action, a disabled/hidden state,
or a clear read-only presentation.

## Screen Units

| Unit | Visible actions | Data source | Empty/failure behavior | Acceptance |
| --- | --- | --- | --- | --- |
| Splash | Load tenant config; continue with local demo if remote config is unavailable. | Tenant Edge `/config`; flavor defaults. | Show tenant-edge offline demo copy; keep app usable. | No blocking spinner on demo builds. |
| Login/Register | Email challenge, email verify, enabled OAuth providers. | `/auth/email/*`, `/auth/oauth/{provider}/*`, `/me`. | Hide disabled providers; show provider readiness/error copy. | Email and visible social provider buttons complete in demo transport. |
| Home | Bottom nav, search, language picker, hero CTA, drama cards, continue watching. | `/config`, `/catalog`, local history/favorites. | Use seeded catalog if remote catalog is empty. | All cards and CTAs navigate to catalog/detail/player-related screens. |
| Catalog/Theater | Template tabs, search, metadata chips, sort, drama cards. | `/catalog` public drama metadata. | Show a no-match empty state. | Template tabs must change filter/sort state; sort and chips are functional. |
| Drama Detail | Episode selection, start/unlock CTA, share/deep link, metadata. | `/dramas/{dramaId}` and fallback episodes. | Friendly unavailable copy on detail fetch failure. | Ready episodes can open the player; locked episodes surface unlock flow. |
| Vertical Player | Play authorization, next episode, favorite, share sheet, unlock sheet. | `/play`; local favorite/history state. | Friendly auth/payment/playback error copy. | Unlock and play records watch history and returns an authorized player state. |
| Unlock/Recharge | Store-safe packages, external payment entries when allowed, point-card route. | `/payment/options`, `/topups/payment-channels`, `/payment/*`. | Hide providers filtered by compliance mode; show review-pending for offline submissions. | App Store/Play/direct modes expose only allowed providers. |
| Mine/Wallet/Point Card | Wallet center, auth, sign out, history, favorites, point card, legal links, account deletion, settings. | `/wallet`, `/wallet/ledger`, `/payment/card-redeem`, `/me/delete-request`, legal URLs. | Hide disabled wallet entries; read-only rows must not show actionable affordances. | Every shown list tile either navigates, opens a sheet, signs out, or is visually read-only. |

## MVP Clickability Rules

- Navigation tabs must switch screens on both Android and iOS.
- Buttons with labels or icons must have an `onPressed`/`onTap` target unless they are hidden or visually disabled.
- Read-only rows must not show chevrons.
- Bottom sheets, dialogs, and share sheets must be dismissible.
- Demo transport must keep all MVP flows usable without external accounts.
- Live/staging transport may fail gracefully but must not expose raw API errors or secrets.

