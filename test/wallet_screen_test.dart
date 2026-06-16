import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/core/payment/store_purchase_service.dart';
import 'package:short_drama_whitelabel/features/wallet/wallet_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class WalletFakeTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (request.path == '/topups/payment-channels') {
      return _ok({
        'requestId': 'req_channels_widget',
        'status': 'ok',
        'channels': [
          {
            'id': 'payment_bca',
            'country': 'ID',
            'method': '银行卡',
            'name': 'BCA Bank',
            'summary': 'account: 123***7800',
            'enabled': true,
            'qrFileName': 'bca-bank-qr.png',
            'qrImageUrl':
                'https://media.example.test/payment-qrs/bca-bank-qr.png',
          },
        ],
      });
    }
    if (request.path == '/payment/offline-applications') {
      return _ok({
        'requestId': 'req_offline_widget',
        'status': 'pending',
        'applicationId': 'consumer_topup_widget',
        'requestedCoins': 100,
      }, statusCode: 201);
    }
    if (request.path == '/wallet') {
      return _ok({
        'requestId': 'req_wallet_widget',
        'wallet': {
          'tenantId': 'tenant_widget',
          'accountRefMasked': 'anon:w...dget',
          'ledgerScope': 'consumer',
          'balanceCoins': 0,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      });
    }
    if (request.path == '/wallet/ledger') {
      return _ok({
        'requestId': 'req_wallet_ledger_widget',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:w...dget',
        'entries': const [],
      });
    }
    if (request.path == '/payment/options') {
      return _ok({
        'requestId': 'req_payment_options_widget',
        'providers': [
          'iap',
          'stripe',
          'bank_transfer',
          'local_wallet',
          'crypto',
          'point_card',
        ],
        'packages': [
          {
            'packageId': 'coins_100',
            'title': '100 coins',
            'storeProductId': 'com.example.drama.coins100',
            'coins': 100,
            'bonusCoins': 0,
            'amountOriginal': 9,
            'currency': 'USD',
          },
        ],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      });
    }
    if (request.path == '/payment/intents') {
      return _ok({
        'requestId': 'req_payment_intent_widget',
        'status': 'requires_provider_confirmation',
        'orderId': 'consumer_order_widget',
        'provider': 'stripe',
        'packageId': 'coins_100',
        'amountOriginal': 9,
        'currency': 'USD',
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
        'checkoutUrl':
            'https://tenant.example.test/payment/checkout?orderId=consumer_order_widget&provider=stripe',
      }, statusCode: 202);
    }
    if (request.path == '/payment/store-purchases/verify') {
      return _ok({
        'requestId': 'req_store_purchase_widget',
        'status': 'verification_received',
        'orderId': 'consumer_store_order_widget',
        'provider': 'iap',
        'packageId': 'coins_100',
        'amountOriginal': 9,
        'currency': 'USD',
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'app_store',
      }, statusCode: 202);
    }
    throw StateError('Unexpected request: ${request.path}');
  }
}

class WalletPaymentErrorTransport extends WalletFakeTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    if (request.path == '/payment/intents') {
      return const AdapterResponse(
        statusCode: 403,
        body: '''
          {
            "error": {
              "code": "APP_PAYMENT_PROVIDER_DISABLED",
              "message": "Provider stripe is disabled for this tenant.",
              "requestId": "req_pay_raw"
            }
          }
        ''',
      );
    }
    return super.send(request);
  }
}

AdapterResponse _ok(Map<String, dynamic> body, {int statusCode = 200}) {
  return AdapterResponse(statusCode: statusCode, body: jsonEncode(body));
}

void main() {
  testWidgets('wallet shows tenant payment channels and submits selected one', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = WalletFakeTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-wallet-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: WalletScreen(flavor: flavor)),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      transport.requests.map((request) => request.path),
      contains('/topups/payment-channels'),
    );
    expect(find.text('BCA Bank'), findsOneWidget);
    expect(find.text('account: 123***7800'), findsOneWidget);
    expect(find.text('bca-bank-qr.png'), findsOneWidget);

    await tester.tap(find.text('BCA Bank'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Transfer proof reference'),
      '  receipt-2026-06-14-bca  ',
    );
    await tester.pumpAndSettle();
    final bankTransferTile =
        find.byKey(const ValueKey('payment-provider-bank_transfer'));
    await tester.scrollUntilVisible(
      bankTransferTile,
      240,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(bankTransferTile);
    await tester.pumpAndSettle();

    final offlineRequest = transport.requests.singleWhere(
      (request) => request.path == '/payment/offline-applications',
    );
    expect(offlineRequest.body?['paymentChannelId'], 'payment_bca');
    expect(
      offlineRequest.body?['proofR2Key'],
      'receipt-2026-06-14-bca',
    );
    expect(
        offlineRequest.body?['requestedBy'], 'anon:pulsedrama-wallet-widget');
    expect(find.textContaining('consumer_topup_widget'), findsOneWidget);
  });

  testWidgets('wallet opens tenant hosted checkout for online payment intent', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = WalletFakeTransport();
    final launched = <Uri>[];
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-checkout-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(
          home: WalletScreen(
            flavor: flavor,
            launchPaymentUrl: (uri) async {
              launched.add(uri);
              return true;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final stripeTile = find.byKey(const ValueKey('payment-provider-stripe'));
    await tester.scrollUntilVisible(
      stripeTile,
      240,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(stripeTile);
    await tester.pumpAndSettle();

    final intentRequest = transport.requests.singleWhere(
      (request) => request.path == '/payment/intents',
    );
    expect(intentRequest.body?['provider'], 'stripe');
    expect(
        intentRequest.body?['endUserRef'], 'anon:pulsedrama-checkout-widget');
    expect(
      launched.single.toString(),
      'https://tenant.example.test/payment/checkout?orderId=consumer_order_widget&provider=stripe',
    );
    expect(find.textContaining('checkout opened'), findsOneWidget);
  });

  testWidgets(
      'wallet hides external providers when Tenant Edge disables external payments',
      (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = WalletFakeTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-external-disabled',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: runtime.data.account,
      wallet: runtime.data.wallet,
      walletLedger: runtime.data.walletLedger,
      topupPaymentChannels: runtime.data.topupPaymentChannels,
      paymentOptions: const PaymentOptions(
        requestId: 'req_external_disabled_remote_options',
        providers: [
          'stripe',
          'paypal',
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
        child: MaterialApp(home: WalletScreen(flavor: flavor)),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Payment entry gated by store compliance'),
      240,
      scrollable: find.byType(Scrollable).first,
    );
    expect(
        find.text('Payment entry gated by store compliance'), findsOneWidget);
    expect(find.text('stripe'), findsNothing);
    expect(find.text('paypal'), findsNothing);
    expect(find.text('bank transfer'), findsNothing);
    expect(find.text('local wallet'), findsNothing);
    expect(find.text('crypto'), findsNothing);
    expect(find.text('point card'), findsNothing);
    expect(
      transport.requests.where(
        (request) => request.path == '/topups/payment-channels',
      ),
      isEmpty,
    );
  });

  testWidgets('wallet verifies native store purchase for app store iap', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final transport = WalletFakeTransport();
    final purchases = <String>[];
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:goldfruit-store-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: runtime.data.account,
      wallet: runtime.data.wallet,
      walletLedger: runtime.data.walletLedger,
      topupPaymentChannels: runtime.data.topupPaymentChannels,
      paymentOptions: const PaymentOptions(
        requestId: 'req_misconfigured_remote_options',
        providers: ['iap', 'stripe'],
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
        child: MaterialApp(
          home: WalletScreen(
            flavor: flavor,
            startStorePurchase: ({required package, required provider}) async {
              purchases.add('$provider:${package.storeProductId}');
              return StorePurchaseReceipt(
                provider: provider,
                packageId: package.packageId,
                productId: package.storeProductId,
                transactionId: 'txn_widget_store_1',
                purchaseToken: 'purchase-token-widget',
                verificationData: 'signed-store-receipt-widget',
                verificationSource: 'app_store',
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.text('Build mode'), 240);
    await tester.pumpAndSettle();
    expect(find.text('app store'), findsOneWidget);
    expect(find.text('android direct'), findsNothing);
    expect(find.text('stripe'), findsNothing);

    final iapTile = find.ancestor(
      of: find.text('iap'),
      matching: find.byType(ListTile),
    );
    await tester.ensureVisible(iapTile);
    await tester.pumpAndSettle();
    await tester.tap(iapTile);
    await tester.pumpAndSettle();

    expect(purchases, ['iap:com.shortdrama.coins100']);
    expect(
      transport.requests.where((request) => request.path == '/payment/intents'),
      isEmpty,
    );
    final verifyRequest = transport.requests.singleWhere(
      (request) => request.path == '/payment/store-purchases/verify',
    );
    expect(verifyRequest.body?['provider'], 'iap');
    expect(verifyRequest.body?['packageId'], 'coins_100');
    expect(
      verifyRequest.body?['productId'],
      'com.shortdrama.coins100',
    );
    expect(verifyRequest.body?['transactionId'], 'txn_widget_store_1');
    expect(
      verifyRequest.body?['verificationData'],
      'signed-store-receipt-widget',
    );
    expect(verifyRequest.body?['endUserRef'], 'anon:goldfruit-store-widget');
    expect(find.textContaining('store purchase verified'), findsOneWidget);
  });

  testWidgets('wallet maps payment errors to friendly text', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = WalletPaymentErrorTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-payment-error',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: WalletScreen(flavor: flavor)),
      ),
    );
    await tester.pumpAndSettle();

    final stripeTile = find.byKey(const ValueKey('payment-provider-stripe'));
    await tester.scrollUntilVisible(
      stripeTile,
      360,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(stripeTile);
    await tester.pumpAndSettle();
    await tester.tapAt(tester.getCenter(stripeTile));
    await tester.pumpAndSettle();

    expect(
      find.text('Payment failed. Please choose another method or retry.'),
      findsOneWidget,
    );
    expect(find.textContaining('APP_PAYMENT_PROVIDER_DISABLED'), findsNothing);
    expect(find.textContaining('req_pay_raw'), findsNothing);
    expect(find.textContaining('Provider stripe is disabled'), findsNothing);
  });
}
