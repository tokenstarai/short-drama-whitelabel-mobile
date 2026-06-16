import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/config/app_capabilities.dart';
import '../../core/i18n/app_strings.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../account_delete/account_delete_screen.dart';
import '../auth/auth_screen.dart';
import '../card_redeem/card_redeem_screen.dart';
import '../legal/legal_link_screen.dart';
import '../library/library_screen.dart';
import '../point_card_management/point_card_management_screen.dart';
import '../wallet/wallet_screen.dart';

class AccountScreen extends StatelessWidget {
  const AccountScreen({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final features = runtime.effectiveFeatures;
    final walletEntries = features.visibleWalletEntrypoints();
    final canRedeemConsumerPointCards = walletEntries.contains('cardRedeem') &&
        runtime.canRedeemConsumerPointCards;
    final effectivePaymentProviders = runtime.effectivePaymentProviders;
    final canUseOfflineTopup = walletEntries.contains('offlineTopup') &&
        effectivePaymentProviders.any(_usesTenantPaymentChannel);
    final canUseOnlinePayment = walletEntries.contains('onlinePayment') &&
        effectivePaymentProviders.any(_usesOnlinePayment);
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final account = runtime.account;
    final wallet = runtime.wallet;
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
      children: [
        CircleAvatar(
          radius: 24,
          backgroundColor: tokens.primary,
          child: const Icon(Icons.person, color: Colors.white),
        ),
        const SizedBox(height: 8),
        Center(
          child: Text(
            runtime.appName,
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
        ),
        Center(
          child: Text(
            tokens.name,
            style: TextStyle(
              color: tokens.primary,
              fontWeight: FontWeight.w700,
              fontSize: 12,
            ),
          ),
        ),
        const SizedBox(height: 4),
        Center(
          child: Text(
            '${account?.accountRefMasked ?? 'anon'} / ${account?.membershipTier ?? 'guest'} / ${wallet?.balanceCoins ?? 0} coins',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.black54),
          ),
        ),
        const SizedBox(height: 12),
        _AccountTile(
          icon: Icons.account_balance_wallet_outlined,
          label: strings.walletCenter,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => WalletScreen(flavor: flavor)),
          ),
        ),
        _AccountTile(
          icon: Icons.login_outlined,
          label: strings.loginRegister,
          onTap: () => Navigator.of(
            context,
          ).push(MaterialPageRoute(builder: (_) => AuthScreen(flavor: flavor))),
        ),
        if ((account?.membershipTier ?? 'guest') != 'guest')
          _AccountTile(
            icon: Icons.logout_outlined,
            label: strings.signOut,
            onTap: runtime.signOut,
          ),
        _AccountTile(
          icon: Icons.history,
          label: strings.watchHistory,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => LibraryScreen(
                flavor: flavor,
                mode: LibraryScreenMode.watchHistory,
              ),
            ),
          ),
        ),
        _AccountTile(
          icon: Icons.favorite_border,
          label: strings.favorites,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => LibraryScreen(
                flavor: flavor,
                mode: LibraryScreenMode.favorites,
              ),
            ),
          ),
        ),
        if (canRedeemConsumerPointCards)
          _AccountTile(
            icon: Icons.inventory_2_outlined,
            label: strings.pointCardManagement,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => PointCardManagementScreen(flavor: flavor),
              ),
            ),
          ),
        if (canRedeemConsumerPointCards)
          _AccountTile(
            icon: Icons.card_giftcard_outlined,
            label: strings.cardRedeem,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => CardRedeemScreen(flavor: flavor),
              ),
            ),
          ),
        if (canUseOfflineTopup)
          _AccountTile(
            icon: Icons.receipt_long_outlined,
            label: strings.offlineTopUp,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => WalletScreen(flavor: flavor)),
            ),
          ),
        if (canUseOnlinePayment)
          _AccountTile(
            icon: Icons.payments_outlined,
            label: strings.onlinePayment,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => WalletScreen(flavor: flavor)),
            ),
          ),
        _AccountTile(
          icon: Icons.language,
          label: strings.language,
          value: AppStrings.languageNameFor(runtime.localeCode),
          onTap: () => _showLanguagePicker(context, runtime),
        ),
        _AccountTile(
          icon: Icons.verified_user_outlined,
          label: capabilities.storeComplianceMode.wireValue.replaceAll(
            '_',
            ' ',
          ),
        ),
        _AccountTile(
          icon: Icons.support_agent,
          label: strings.support,
          onTap: () => _openLegalLink(context, flavor, LegalLinkKind.support),
        ),
        _AccountTile(
          icon: Icons.article_outlined,
          label: strings.termsOfService,
          onTap: () => _openLegalLink(context, flavor, LegalLinkKind.terms),
        ),
        _AccountTile(
          icon: Icons.privacy_tip_outlined,
          label: strings.privacyPolicy,
          onTap: () => _openLegalLink(context, flavor, LegalLinkKind.privacy),
        ),
        if (features.enableAccountDeletion)
          _AccountTile(
            icon: Icons.delete_outline,
            label: strings.accountDelete,
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => AccountDeleteScreen(flavor: flavor),
              ),
            ),
          ),
        _AccountTile(
          icon: Icons.settings_outlined,
          label: strings.settings,
          onTap: () => _showSettingsSheet(context, runtime, capabilities),
        ),
      ],
    );
  }
}

bool _usesTenantPaymentChannel(ConsumerPaymentProvider provider) {
  return provider == ConsumerPaymentProvider.bankTransfer ||
      provider == ConsumerPaymentProvider.localWallet ||
      provider == ConsumerPaymentProvider.crypto;
}

bool _usesOnlinePayment(ConsumerPaymentProvider provider) {
  return provider == ConsumerPaymentProvider.iap ||
      provider == ConsumerPaymentProvider.playBilling ||
      provider == ConsumerPaymentProvider.stripe ||
      provider == ConsumerPaymentProvider.paypal;
}

void _openLegalLink(
  BuildContext context,
  FlavorConfig flavor,
  LegalLinkKind kind,
) {
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => LegalLinkScreen(flavor: flavor, kind: kind),
    ),
  );
}

Future<void> _showLanguagePicker(
  BuildContext context,
  AppRuntime runtime,
) {
  final strings = runtime.strings;
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (context) {
      return SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Text(
              strings.language,
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final locale in runtime.supportedLocaleCodes)
              ListTile(
                title: Text(AppStrings.languageNameFor(locale)),
                subtitle: Text(locale),
                trailing: locale == runtime.localeCode
                    ? const Icon(Icons.check_circle)
                    : null,
                onTap: () {
                  runtime.setLocale(locale);
                  Navigator.of(context).pop();
                },
              ),
          ],
        ),
      );
    },
  );
}

Future<void> _showSettingsSheet(
  BuildContext context,
  AppRuntime runtime,
  AppCapabilities capabilities,
) {
  final strings = runtime.strings;
  final parentContext = context;
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (sheetContext) {
      return SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Text(
              strings.settings,
              style: Theme.of(sheetContext).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w900,
                  ),
            ),
            const SizedBox(height: 8),
            ListTile(
              leading: const Icon(Icons.translate_outlined),
              title: Text(strings.language),
              subtitle: Text(AppStrings.languageNameFor(runtime.localeCode)),
              onTap: () {
                Navigator.of(sheetContext).pop();
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (parentContext.mounted) {
                    _showLanguagePicker(parentContext, runtime);
                  }
                });
              },
            ),
            ListTile(
              leading: const Icon(Icons.verified_user_outlined),
              title: Text(
                capabilities.storeComplianceMode.wireValue.replaceAll(
                  '_',
                  ' ',
                ),
              ),
              subtitle: Text(
                capabilities.externalPaymentsAllowed
                    ? 'External payment entries are allowed by this build mode.'
                    : 'External payment entries are hidden by this build mode.',
              ),
            ),
            ListTile(
              leading: const Icon(Icons.payment_outlined),
              title: const Text('Payment providers'),
              subtitle: Text(
                runtime.effectivePaymentProviderWireValues.join(', '),
              ),
            ),
          ],
        ),
      );
    },
  );
}

class _AccountTile extends StatelessWidget {
  const _AccountTile({
    required this.icon,
    required this.label,
    this.value,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final String? value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 6),
      child: ListTile(
        dense: true,
        visualDensity: VisualDensity.compact,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        minLeadingWidth: 24,
        leading: Icon(icon),
        title: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Text(label),
        ),
        subtitle: value == null ? null : Text(value!),
        trailing: onTap == null ? null : const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
