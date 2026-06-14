import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../card_redeem/card_redeem_screen.dart';

class PointCardManagementScreen extends StatelessWidget {
  const PointCardManagementScreen({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final pointCardEntries = (runtime.walletLedger?.entries ?? const [])
        .where(_isPointCardEntry)
        .toList(growable: false);
    final wallet = runtime.wallet;
    final canRedeemConsumerPointCards = runtime.canRedeemConsumerPointCards;

    return Scaffold(
      appBar: AppBar(title: Text(strings.pointCardManagement)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: BorderRadius.circular(tokens.radius),
              border: Border.all(color: tokens.primary.withValues(alpha: 0.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.pointCardManagement,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  wallet?.ledgerScope == 'consumer'
                      ? strings.consumerWallet
                      : '${wallet?.ledgerScope ?? 'consumer'} wallet',
                  style: TextStyle(
                    color: tokens.primary,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(wallet?.accountRefMasked ?? runtime.endUserRef),
                const SizedBox(height: 14),
                if (canRedeemConsumerPointCards)
                  FilledButton.icon(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => CardRedeemScreen(flavor: flavor),
                      ),
                    ),
                    icon: const Icon(Icons.card_giftcard_outlined),
                    label: Text(strings.cardRedeem),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (pointCardEntries.isEmpty)
            _EmptyPointCardState(tokens: tokens)
          else
            for (final entry in pointCardEntries)
              _PointCardLedgerRow(entry: entry),
        ],
      ),
    );
  }
}

bool _isPointCardEntry(WalletLedgerEntry entry) {
  return entry.type == 'point_card' || entry.type == 'card_redeem';
}

class _EmptyPointCardState extends StatelessWidget {
  const _EmptyPointCardState({required this.tokens});

  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(Icons.card_giftcard_outlined, size: 48, color: tokens.primary),
            const SizedBox(height: 12),
            Text(
              AppRuntimeScope.of(context).strings.noPointCardRecords,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PointCardLedgerRow extends StatelessWidget {
  const _PointCardLedgerRow({required this.entry});

  final WalletLedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final prefix = entry.pointsDelta >= 0 ? '+' : '';
    return Card(
      elevation: 0,
      child: ListTile(
        leading: const Icon(Icons.card_giftcard_outlined),
        title: Text(entry.title),
        subtitle: Text(
          '${entry.status} · balance ${entry.balanceAfter} · ${entry.createdAt}',
        ),
        trailing: Text(
          '$prefix${entry.pointsDelta}',
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
      ),
    );
  }
}
