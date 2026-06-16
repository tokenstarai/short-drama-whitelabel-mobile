import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class AccountNoopTransport implements AdapterTransport {
  final List<AdapterRequest> requests = [];

  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    requests.add(request);
    return AdapterResponse(
      statusCode: 200,
      body: jsonEncode({'requestId': 'noop', 'status': 'ok'}),
    );
  }
}

void main() {
  testWidgets('mine tab signs out registered account locally', (
    tester,
  ) async {
    final flavor = FlavorConfig.douyin();
    final transport = AccountNoopTransport();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:pulsedrama-account-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: transport,
      ),
    );
    runtime.data = AppRuntimeData(
      catalog: runtime.data.catalog,
      account: const UserAccount(
        requestId: 'req_registered_account',
        tenantId: 'tenant_widget',
        accountRefMasked: 'user:r...dget',
        authProviders: ['email', 'google'],
        membershipTier: 'registered',
        deletionEndpoint: '/me/delete-request',
      ),
      wallet: runtime.data.wallet,
      walletLedger: runtime.data.walletLedger,
      paymentOptions: runtime.data.paymentOptions,
      topupPaymentChannels: runtime.data.topupPaymentChannels,
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    expect(find.textContaining('registered'), findsOneWidget);
    expect(find.text('Sign Out'), findsOneWidget);

    await tester.tap(find.text('Sign Out'));
    await tester.pumpAndSettle();

    expect(runtime.account?.membershipTier, 'guest');
    expect(runtime.account?.accountRefMasked, 'anon:pulsedrama-account-widget');
    expect(find.textContaining('guest'), findsOneWidget);
    expect(find.text('Sign Out'), findsNothing);
    expect(transport.requests, isEmpty);
  });

  testWidgets('settings entry opens runtime configuration sheet', (
    tester,
  ) async {
    final flavor = FlavorConfig.coolshow();
    final runtime = AppRuntime(
      flavor: flavor,
      endUserRef: 'anon:coolshow-settings-widget',
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: AccountNoopTransport(),
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.scrollUntilVisible(find.text('Settings'), 300);
    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();

    expect(find.text('Payment providers'), findsOneWidget);
    expect(find.textContaining('android direct'), findsWidgets);
    expect(find.textContaining('stripe'), findsOneWidget);
    expect(find.textContaining('point_card'), findsOneWidget);
  });
}
