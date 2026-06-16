# High-Fidelity Style System PRD

## Goal

Refine CoolShow plus four reference-inspired templates into high-fidelity,
brand-safe short-drama app styles. The target is visual familiarity in layout,
density, pacing, and interaction model, not copying protected brand assets.

## Product Design Brief

- Product: open-source Flutter white-label short-drama app template.
- Audience: tenants who package their own Android/iOS app and C-end users who watch short episodes and recharge coins/memberships.
- Interactivity: full MVP interactivity for existing screens; no new business modules in v1.
- Visual target: generated/public-safe assets, realistic drama posters/scenes, no placeholders, no third-party screenshots/logos/trademarks.
- Required screens per style: Splash, Login/Register, Home, Catalog/Theater, Drama Detail, Vertical Player, Unlock/Recharge, Mine/Wallet/Point Card.

## Style References

| Template | Public reference traits | Safe interpretation |
| --- | --- | --- |
| CoolShow | Overseas short-drama creator/distribution positioning. | Dark premium, poster-led, gold CTA, direct-distribution payment readiness. |
| Hongguo-inspired | Free-to-start short drama, theater discovery, hot lists, broad catalog browsing. | Light theater UI, red/orange emphasis, grid and ranking patterns. |
| Douyin-inspired | Immersive vertical feed, quick content consumption, bottom navigation, right-side actions. | Dark vertical player/feed grammar without copying Douyin marks or exact UI. |
| Hippo-inspired | Drama theater, category browsing, VIP/member value, smooth HD viewing. | Channel-first discovery, membership clarity, teal/light theater structure. |
| ReelShort-inspired | Overseas vertical drama, coins/subscription, cliffhanger premium framing. | Poster-forward premium drama, coins/trial/subscription density, strong episode hooks. |

Reference URLs:

- https://apps.apple.com/cn/app/id6451407032
- https://apps.apple.com/cn/app/id6451242037
- https://apps.apple.com/cn/app/id1142110895
- https://play.google.com/store/apps/details?id=com.ss.android.ugc.aweme.mobile
- https://apps.apple.com/us/app/reelshort-stream-drama-tv/id1636235979
- https://play.google.com/store/apps/details?id=com.newleaf.app.android.victor

## Design Workflow

1. Use the current Flutter CoolShow runtime preview as baseline source.
2. Generate exactly three public-safe high-fidelity directions before committing a new visual system.
3. After selection, translate the chosen direction into `TemplateTokens`, shared widgets, and generated image assets.
4. Refresh WYSIWYG screenshots for all styles and eight MVP screens.
5. Compare implementation screenshots against the selected direction at the same viewport before handoff.

## Acceptance

- No placeholder wireframes in the review gallery.
- Generated images must be original, drama-relevant, and fit their slots.
- UI must pass 360/390/430/768 px overflow checks.
- No third-party app screenshots, names, logos, slogans, or confusing trade dress enter the open-source package.

