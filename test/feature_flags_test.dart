import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/core/config/feature_flags.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class FeatureFlagsFakeTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) {
    throw StateError('Feature flag tests should not call Tenant Edge.');
  }
}

void main() {
  test('default flavor points to tenant edge adapter', () {
    final flavor = FlavorConfig.golden();

    expect(flavor.brand.apiAdapterBase, contains('tenant-edge'));
    expect(flavor.brand.apiAdapterBase, isNot(contains('/v1/tenant')));
  });

  test('default wallet feature entries are disabled', () {
    final flavor = FlavorConfig.golden();

    expect(flavor.features.enableCardRedeem, isFalse);
    expect(flavor.features.enableOfflineTopup, isFalse);
    expect(flavor.features.enableOnlinePayment, isFalse);
    expect(flavor.features.visibleWalletEntrypoints(), isEmpty);
  });

  testWidgets(
    'mine tab hides disabled payment entries and keeps deletion entry',
    (tester) async {
      await tester.pumpWidget(ShortDramaApp(flavor: FlavorConfig.golden()));

      await tester.tap(find.text('Mine'));
      await tester.pumpAndSettle();

      expect(find.text('Redeem Card'), findsNothing);
      expect(find.text('Offline Top Up'), findsNothing);
      expect(find.text('Online Top Up'), findsNothing);
      await tester.scrollUntilVisible(find.text('Delete Account'), 300);
      expect(find.text('Delete Account'), findsOneWidget);
    },
  );

  testWidgets(
    'mine tab hides top-up entries when external payments are disabled',
    (tester) async {
      final base = FlavorConfig.douyin();
      final flavor = FlavorConfig(
        flavor: base.flavor,
        brand: base.brand,
        capabilities: base.capabilities,
        features: const FeatureFlags(
          enableCardRedeem: true,
          enableOfflineTopup: true,
          enableOnlinePayment: true,
          enableAdsUnlock: true,
          enableAccountDeletion: true,
        ),
      );
      final runtime = AppRuntime(
        flavor: flavor,
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://tenant-edge.example.test'),
          transport: FeatureFlagsFakeTransport(),
        ),
      );
      runtime.data = AppRuntimeData(
        catalog: runtime.data.catalog,
        account: runtime.data.account,
        wallet: runtime.data.wallet,
        walletLedger: runtime.data.walletLedger,
        topupPaymentChannels: runtime.data.topupPaymentChannels,
        paymentOptions: const PaymentOptions(
          requestId: 'req_mine_external_disabled_options',
          providers: [
            'stripe',
            'bank_transfer',
            'local_wallet',
            'crypto',
            'point_card',
          ],
          packages: defaultPaymentPackages,
          externalPaymentsAllowed: false,
          ledgerScope: 'consumer',
          storeComplianceMode: 'android_direct',
        ),
      );
      addTearDown(runtime.dispose);

      await tester.pumpWidget(
        AppRuntimeScope(
          runtime: runtime,
          child: MaterialApp(home: AccountScreen(flavor: flavor)),
        ),
      );

      expect(find.text('Redeem Card'), findsNothing);
      expect(find.text('Point Card Management'), findsNothing);
      expect(find.text('Offline Top Up'), findsNothing);
      expect(find.text('Online Top Up'), findsNothing);
      expect(find.text('Wallet Center'), findsOneWidget);
    },
  );
}
