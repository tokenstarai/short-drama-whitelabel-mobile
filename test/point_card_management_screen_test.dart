import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/core/config/feature_flags.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/features/card_redeem/card_redeem_screen.dart';
import 'package:short_drama_whitelabel/features/point_card_management/point_card_management_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class PointCardFakeTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) {
    throw StateError(
        'Point card management tests should not call Tenant Edge.');
  }
}

void main() {
  testWidgets('mine screen opens point card management when card redeem is on',
      (
    tester,
  ) async {
    final flavor = _pointCardFlavor();
    final runtime = _runtime(flavor);
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Point Card Management'));
    await tester.pumpAndSettle();

    expect(find.text('No point card records yet'), findsOneWidget);
    expect(find.text('Redeem Card'), findsOneWidget);
  });

  testWidgets(
      'mine screen hides point card entry when app store build filters provider',
      (
    tester,
  ) async {
    final flavor = _appStorePointCardFeatureFlavor();
    final runtime = _runtime(flavor);
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: runtime.data.account,
      wallet: runtime.data.wallet,
      walletLedger: runtime.data.walletLedger,
      topupPaymentChannels: runtime.data.topupPaymentChannels,
      paymentOptions: const PaymentOptions(
        requestId: 'req_misconfigured_account_point_card_options',
        providers: ['iap', 'point_card'],
        packages: defaultPaymentPackages,
        externalPaymentsAllowed: true,
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

    expect(find.text('Point Card Management'), findsNothing);
    expect(find.text('Redeem Card'), findsNothing);
  });

  testWidgets('management screen shows only consumer point card ledger entries',
      (
    tester,
  ) async {
    final flavor = _pointCardFlavor();
    final runtime = _runtime(flavor);
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: runtime.data.account,
      wallet: runtime.data.wallet,
      paymentOptions: runtime.data.paymentOptions,
      walletLedger: const WalletLedger(
        requestId: 'ledger_point_cards',
        ledgerScope: 'consumer',
        accountRefMasked: 'anon:p...card',
        entries: [
          WalletLedgerEntry(
            ledgerId: 'card_ledger_1',
            type: 'point_card',
            title: 'Point card recharge',
            pointsDelta: 120,
            balanceAfter: 160,
            createdAt: '2026-06-14T00:00:00Z',
            status: 'posted',
          ),
          WalletLedgerEntry(
            ledgerId: 'play_ledger_1',
            type: 'playback',
            title: 'Episode unlock',
            pointsDelta: -2,
            balanceAfter: 158,
            createdAt: '2026-06-14T00:10:00Z',
            status: 'posted',
          ),
        ],
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: PointCardManagementScreen(flavor: flavor)),
      ),
    );

    expect(find.text('Point card recharge'), findsOneWidget);
    expect(find.text('+120'), findsOneWidget);
    expect(find.text('Episode unlock'), findsNothing);
    expect(find.text('consumer wallet'), findsOneWidget);
  });

  testWidgets(
      'card redeem blocks raw point_card payment options in app store builds',
      (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = _runtime(flavor);
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: runtime.data.account,
      wallet: runtime.data.wallet,
      walletLedger: runtime.data.walletLedger,
      topupPaymentChannels: runtime.data.topupPaymentChannels,
      paymentOptions: const PaymentOptions(
        requestId: 'req_misconfigured_point_card_options',
        providers: ['iap', 'point_card'],
        packages: defaultPaymentPackages,
        externalPaymentsAllowed: true,
        ledgerScope: 'consumer',
        storeComplianceMode: 'android_direct',
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: CardRedeemScreen(flavor: flavor)),
      ),
    );

    expect(find.text('Card redeem is not enabled.'), findsOneWidget);
    expect(find.text('Consumer point card'), findsNothing);
    expect(find.text('Redeem'), findsNothing);
  });
}

FlavorConfig _pointCardFlavor() {
  final base = FlavorConfig.douyin();
  return FlavorConfig(
    flavor: base.flavor,
    brand: base.brand,
    capabilities: base.capabilities,
    features: const FeatureFlags(
      enableCardRedeem: true,
      enableOfflineTopup: false,
      enableOnlinePayment: false,
      enableAdsUnlock: true,
      enableAccountDeletion: true,
    ),
  );
}

FlavorConfig _appStorePointCardFeatureFlavor() {
  final base = FlavorConfig.hongguo();
  return FlavorConfig(
    flavor: base.flavor,
    brand: base.brand,
    capabilities: base.capabilities,
    features: const FeatureFlags(
      enableCardRedeem: true,
      enableOfflineTopup: false,
      enableOnlinePayment: false,
      enableAdsUnlock: true,
      enableAccountDeletion: true,
    ),
  );
}

AppRuntime _runtime(FlavorConfig flavor) {
  return AppRuntime(
    flavor: flavor,
    localeCode: 'en-US',
    client: TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: PointCardFakeTransport(),
    ),
  );
}
