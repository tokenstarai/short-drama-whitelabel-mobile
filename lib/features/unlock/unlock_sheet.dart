import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/config/app_capabilities.dart';
import '../../core/config/feature_gate.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../card_redeem/card_redeem_screen.dart';
import '../wallet/wallet_screen.dart';

Future<void> showUnlockSheet(
  BuildContext context, {
  required FlavorConfig flavor,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) {
      final runtime = AppRuntimeScope.of(context);
      final strings = runtime.strings;
      final capabilities = runtime.effectiveCapabilities;
      final features = runtime.effectiveFeatures;
      final tokens = templateTokensFor(
        capabilities.styleTemplate,
        runtime.effectiveBrandPrimaryColor,
      );
      final paymentProviders = runtime.effectivePaymentProviderWireValues;
      final dark = tokens.background.computeLuminance() < 0.25;
      return SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
            20,
            8,
            20,
            MediaQuery.viewInsetsOf(context).bottom + 28,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      tokens.primary,
                      tokens.secondary,
                      tokens.posterTint,
                    ],
                  ),
                  borderRadius: BorderRadius.circular(tokens.radius),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.2),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.lock_open_rounded,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            strings.unlockEpisode,
                            style: Theme.of(context)
                                .textTheme
                                .titleLarge
                                ?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      strings.episodeCostPoints(2),
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                        fontSize: 20,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      tokens.walletPitch,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.78),
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              FeatureGate(
                enabled: features.enableAdsUnlock,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: dark ? Colors.white : tokens.primary,
                  ),
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text(
                          'Ad unlock is gated by tenant ad-network configuration.',
                        ),
                      ),
                    );
                  },
                  icon: const Icon(Icons.ondemand_video_outlined),
                  label: Text(strings.watchAdToUnlock),
                ),
              ),
              FeatureGate(
                enabled: runtime.canRedeemConsumerPointCards,
                child: OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: dark ? Colors.white : tokens.primary,
                  ),
                  onPressed: () {
                    final navigator = Navigator.of(context);
                    navigator.pop();
                    navigator.push(
                      MaterialPageRoute(
                        builder: (_) => CardRedeemScreen(flavor: flavor),
                      ),
                    );
                  },
                  icon: const Icon(Icons.card_giftcard_outlined),
                  label: Text(strings.cardRedeem),
                ),
              ),
              for (final provider in paymentProviders)
                if (provider != ConsumerPaymentProvider.pointCard.wireValue)
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: dark ? Colors.white : tokens.primary,
                    ),
                    onPressed: () {
                      final navigator = Navigator.of(context);
                      navigator.pop();
                      navigator.push(
                        MaterialPageRoute(
                          builder: (_) => WalletScreen(flavor: flavor),
                        ),
                      );
                    },
                    icon: const Icon(Icons.payments_outlined),
                    label: Text(provider.replaceAll('_', ' ')),
                  ),
              if (paymentProviders.isEmpty)
                OutlinedButton.icon(
                  onPressed: null,
                  icon: const Icon(Icons.lock_outline),
                  label: Text(strings.paymentEntryGated),
                ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(),
                child: Text(strings.unlockAndPlay),
              ),
            ],
          ),
        ),
      );
    },
  );
}
