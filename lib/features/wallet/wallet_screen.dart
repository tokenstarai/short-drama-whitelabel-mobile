import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../core/payment/store_purchase_service.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../card_redeem/card_redeem_screen.dart';

typedef PaymentUrlLauncher = Future<bool> Function(Uri uri);
typedef StorePurchaseStarter = Future<StorePurchaseReceipt> Function({
  required String provider,
  required PaymentPackage package,
});

class WalletScreen extends StatelessWidget {
  const WalletScreen({
    required this.flavor,
    this.launchPaymentUrl = _launchPaymentUrl,
    this.startStorePurchase = _startStorePurchase,
    super.key,
  });

  final FlavorConfig flavor;
  final PaymentUrlLauncher launchPaymentUrl;
  final StorePurchaseStarter startStorePurchase;

  @override
  Widget build(BuildContext context) {
    return _WalletScreenBody(
      flavor: flavor,
      launchPaymentUrl: launchPaymentUrl,
      startStorePurchase: startStorePurchase,
    );
  }
}

Future<bool> _launchPaymentUrl(Uri uri) {
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}

Future<StorePurchaseReceipt> _startStorePurchase({
  required String provider,
  required PaymentPackage package,
}) {
  return NativeStorePurchaseLauncher().purchase(
    provider: provider,
    package: package,
  );
}

class _WalletScreenBody extends StatefulWidget {
  const _WalletScreenBody({
    required this.flavor,
    required this.launchPaymentUrl,
    required this.startStorePurchase,
  });

  final FlavorConfig flavor;
  final PaymentUrlLauncher launchPaymentUrl;
  final StorePurchaseStarter startStorePurchase;

  @override
  State<_WalletScreenBody> createState() => _WalletScreenBodyState();
}

class _WalletScreenBodyState extends State<_WalletScreenBody> {
  String? selectedPackageId;
  String? selectedChannelId;
  bool requestedChannels = false;
  bool loadingChannels = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final runtime = AppRuntimeScope.of(context);
    if (requestedChannels || !_visiblePayments(runtime).any(_usesChannel)) {
      return;
    }
    requestedChannels = true;
    loadingChannels = true;
    runtime.refreshTopupPaymentChannels().whenComplete(() {
      if (mounted) {
        setState(() {
          loadingChannels = false;
        });
      }
    });
  }

  Future<void> handlePaymentProvider(
    BuildContext context,
    AppRuntime runtime,
    String provider,
    PaymentPackage package,
    TopupPaymentChannel? channel,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      if (_usesChannel(provider)) {
        if (channel == null) {
          messenger.showSnackBar(
            const SnackBar(
              content: Text('No tenant payment channel configured.'),
            ),
          );
          return;
        }
        final application =
            await runtime.client.submitConsumerOfflineApplication(
          provider: provider,
          amountOriginal: package.amountOriginal,
          currency: package.currency,
          requestedCoins: package.totalCoins,
          endUserRef: runtime.endUserRef,
          paymentChannelId: channel.id,
          idempotencyKey:
              'offline-$provider-${package.packageId}-${DateTime.now().millisecondsSinceEpoch}',
        );
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'Application ${application.applicationId}: ${application.status}',
            ),
          ),
        );
        await runtime.refreshWallet();
        return;
      }
      if (isStorePurchaseProvider(provider)) {
        final receipt = await widget.startStorePurchase(
          provider: provider,
          package: package,
        );
        final verification = await runtime.client.verifyStorePurchase(
          provider: provider,
          packageId: package.packageId,
          productId: receipt.productId,
          transactionId: receipt.transactionId,
          purchaseToken: receipt.purchaseToken,
          verificationData: receipt.verificationData,
          verificationSource: receipt.verificationSource,
          endUserRef: runtime.endUserRef,
          idempotencyKey:
              'store-$provider-${package.packageId}-${DateTime.now().millisecondsSinceEpoch}',
        );
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'Order ${verification.orderId}: store purchase verified · ${package.totalCoins} coins',
            ),
          ),
        );
        await runtime.refreshWallet();
        return;
      }
      final intent = await runtime.client.createPaymentIntent(
        provider: provider,
        packageId: package.packageId,
        amountOriginal: package.amountOriginal,
        currency: package.currency,
        endUserRef: runtime.endUserRef,
        idempotencyKey:
            'pay-$provider-${package.packageId}-${DateTime.now().millisecondsSinceEpoch}',
      );
      final checkoutUrl = intent.checkoutUrl;
      if (checkoutUrl != null && checkoutUrl.isNotEmpty) {
        final checkoutUri = Uri.tryParse(checkoutUrl);
        if (checkoutUri == null || !checkoutUri.hasScheme) {
          throw StateError('Tenant checkout URL is unavailable.');
        }
        final launched = await widget.launchPaymentUrl(checkoutUri);
        if (!launched) {
          throw StateError('Unable to open tenant checkout URL.');
        }
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'Order ${intent.orderId}: checkout opened · ${package.totalCoins} coins',
            ),
          ),
        );
      } else {
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              'Order ${intent.orderId}: ${intent.status} · ${package.totalCoins} coins',
            ),
          ),
        );
      }
      await runtime.refreshWallet();
    } catch (error) {
      messenger.showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final wallet = runtime.wallet;
    final ledgerEntries = runtime.walletLedger?.entries ?? const [];
    final packages = runtime.paymentOptions?.packages ?? defaultPaymentPackages;
    final selectedPackage = packages.firstWhere(
      (package) => package.packageId == selectedPackageId,
      orElse: () => packages.first,
    );
    final payments = _visiblePayments(runtime);
    final paymentChannels = runtime.enabledTopupPaymentChannels;
    final selectedChannel = _selectedChannel(paymentChannels);
    final usesChannels = payments.any(_usesChannel);
    return Scaffold(
      appBar: AppBar(title: Text(strings.walletCenter)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: tokens.surface,
              borderRadius: BorderRadius.circular(tokens.radius),
              border: Border.all(color: tokens.primary.withValues(alpha: 0.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.coins(wallet?.balanceCoins ?? 0),
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 6),
                Text(tokens.walletPitch),
                const SizedBox(height: 12),
                Text(
                  'Ledger scope: ${wallet?.ledgerScope ?? 'consumer'} wallet',
                  style: TextStyle(
                    color: tokens.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          if (usesChannels) ...[
            const SizedBox(height: 16),
            Text(
              'Tenant payment channels',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            if (loadingChannels)
              const LinearProgressIndicator()
            else if (paymentChannels.isEmpty)
              const _WalletRow(
                icon: Icons.account_balance_outlined,
                label: 'No tenant payment channels configured',
              )
            else
              for (final channel in paymentChannels)
                _PaymentChannelRow(
                  channel: channel,
                  selected: channel.id == selectedChannel?.id,
                  onTap: () => setState(() {
                    selectedChannelId = channel.id;
                  }),
                ),
          ],
          const SizedBox(height: 16),
          Text(
            'Coin packages',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          for (final package in packages)
            _PackageRow(
              package: package,
              selected: package.packageId == selectedPackage.packageId,
              onTap: () => setState(() {
                selectedPackageId = package.packageId;
              }),
            ),
          const SizedBox(height: 16),
          Text(
            'Payment options',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (payments.isEmpty)
            _WalletRow(
              icon: Icons.lock_outline,
              label: strings.paymentEntryGated,
            )
          else
            for (final provider in payments)
              _WalletRow(
                icon: provider == 'point_card'
                    ? Icons.card_giftcard_outlined
                    : Icons.payments_outlined,
                label: provider.replaceAll('_', ' '),
                onTap: provider == 'point_card'
                    ? () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) =>
                                CardRedeemScreen(flavor: widget.flavor),
                          ),
                        )
                    : () => handlePaymentProvider(
                          context,
                          runtime,
                          provider,
                          selectedPackage,
                          selectedChannel,
                        ),
              ),
          const SizedBox(height: 16),
          Text(
            'Build mode',
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          _WalletRow(
            icon: Icons.verified_user_outlined,
            label: capabilities.storeComplianceMode.wireValue.replaceAll(
              '_',
              ' ',
            ),
          ),
          _WalletRow(
            icon: Icons.login_outlined,
            label: capabilities.normalizedAuthProviders
                .map((provider) => provider.wireValue)
                .join(' / '),
          ),
          const SizedBox(height: 16),
          Text(
            'Recent ledger',
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (ledgerEntries.isEmpty)
            const _WalletRow(
              icon: Icons.receipt_long_outlined,
              label: 'No wallet ledger entries yet',
            )
          else
            for (final entry in ledgerEntries.take(5)) _LedgerRow(entry: entry),
        ],
      ),
    );
  }

  List<String> _visiblePayments(AppRuntime runtime) {
    return runtime.effectivePaymentProviderWireValues;
  }

  TopupPaymentChannel? _selectedChannel(List<TopupPaymentChannel> channels) {
    if (channels.isEmpty) {
      return null;
    }
    final selectedId = selectedChannelId;
    if (selectedId != null) {
      for (final channel in channels) {
        if (channel.id == selectedId) {
          return channel;
        }
      }
    }
    return channels.first;
  }
}

bool _usesChannel(String provider) {
  return provider == 'bank_transfer' ||
      provider == 'local_wallet' ||
      provider == 'crypto';
}

class _WalletRow extends StatelessWidget {
  const _WalletRow({required this.icon, required this.label, this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text(label),
        trailing: onTap == null ? null : const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

class _PackageRow extends StatelessWidget {
  const _PackageRow({
    required this.package,
    required this.selected,
    required this.onTap,
  });

  final PaymentPackage package;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      color: selected ? colorScheme.primaryContainer : null,
      child: ListTile(
        leading: Icon(
          selected ? Icons.radio_button_checked : Icons.radio_button_unchecked,
        ),
        title: Text(package.title),
        subtitle: Text(
          '${package.coins} coins'
          '${package.bonusCoins > 0 ? ' + ${package.bonusCoins} bonus' : ''}',
        ),
        trailing: Text(
          '${package.currency} ${package.amountOriginal}',
          style: const TextStyle(fontWeight: FontWeight.w900),
        ),
        onTap: onTap,
      ),
    );
  }
}

class _PaymentChannelRow extends StatelessWidget {
  const _PaymentChannelRow({
    required this.channel,
    required this.selected,
    required this.onTap,
  });

  final TopupPaymentChannel channel;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      color: selected ? colorScheme.primaryContainer : null,
      child: ListTile(
        leading: Icon(
          selected ? Icons.radio_button_checked : Icons.radio_button_unchecked,
        ),
        title: Text(channel.name),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${channel.country} · ${channel.method}'),
            Text(channel.summary),
            if (channel.qrFileName != null) Text(channel.qrFileName!),
          ],
        ),
        trailing: channel.qrImageUrl == null
            ? null
            : const Icon(Icons.qr_code_2_outlined),
        onTap: onTap,
      ),
    );
  }
}

class _LedgerRow extends StatelessWidget {
  const _LedgerRow({required this.entry});

  final WalletLedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final pointsDelta = entry.pointsDelta;
    final color = pointsDelta >= 0 ? Colors.green : Colors.redAccent;
    final prefix = pointsDelta >= 0 ? '+' : '';
    return Card(
      child: ListTile(
        leading: Icon(
          pointsDelta >= 0
              ? Icons.add_circle_outline
              : Icons.remove_circle_outline,
          color: color,
        ),
        title: Text(entry.title),
        subtitle: Text(
          '${entry.status} · balance ${entry.balanceAfter} · ${entry.createdAt}',
        ),
        trailing: Text(
          '$prefix$pointsDelta',
          style: TextStyle(color: color, fontWeight: FontWeight.w900),
        ),
      ),
    );
  }
}
